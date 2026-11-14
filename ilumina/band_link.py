"""The student's Vexo band during a tutoring session.

The band is on the wrist while the student works on paper, so it does two things a screen
cannot: a double tap means "done talking", and its light shows whose turn it is. It can
also be the session's microphone: its sound then goes into the voice pipeline in place of
the computer's, live. The band connects in the background and keeps trying, so a band that
is not found, or drops out, never holds up or stops the tutor: the computer's microphone
is used whenever the band's sound is not arriving.

While the band's microphone is on, the band keeps its light solid blue by itself, so the
light shows whose turn it is only when the computer's microphone is used.
"""

import subprocess
import sys
import threading
import time

from loguru import logger
from vexo_open import audio
from vexo_open.sync import Band

# The light for each stage of a turn, in the colours the dashboard uses for that stage.
LIGHTS = {
    "listening": ("#2b6fe3", "solid"),  # your turn
    "hearing": ("#0e9384", "solid"),  # hearing you
    "thinking": ("#ffaa00", "blink"),  # heard you
    "speaking": ("#7a4fe0", "breathe"),  # the tutor is speaking
}
_RETRY_SECONDS = 2  # a band can only be found for a minute after its double tap
# The band's sound: 16 kHz, one channel, 16 bit. At most this much waits to be used, so the
# tutor never hears the student late. With none for this long, the band is not the mic.
_MAX_WAITING_BYTES = 32000 * 3 // 10
# Bluetooth delivers the sound in uneven bursts, so this much is collected before any is
# handed on (60 ms), and again after the band falls behind.
_HEAD_START_BYTES = 32000 * 6 // 100
_SILENT_AFTER_SECONDS = 1.0

# macOS does not refuse Bluetooth to a program it has not allowed: it kills the program.
# So the first scan is made by a throwaway process, and only if that one lives does the
# bot itself touch Bluetooth.
_PROBE = "import asyncio, bleak; asyncio.run(bleak.BleakScanner.discover(timeout=0.5))"


def bluetooth_is_safe() -> bool:
    try:
        probe = subprocess.run(
            [sys.executable, "-c", _PROBE], capture_output=True, timeout=30, check=False
        )
    except Exception as e:  # noqa: BLE001 - could not even ask: do not risk the bot
        logger.warning(f"Could not test Bluetooth: {e}")
        return False
    return probe.returncode >= 0  # negative means the probe was killed by a signal


class BandLink:
    """One band, looked for and held on a thread of its own.

    number: the band's number for Bluetooth. usb=True uses the cable instead, where any
    band that is plugged in will do. `connect` is only replaced in tests.
    """

    def __init__(
        self,
        number: int | None,
        usb: bool = False,
        mic: bool = False,
        connect=Band.connect,
        safe=bluetooth_is_safe,
    ):
        self._number, self._usb, self._connect, self._safe = number, usb, connect, safe
        self.mic = mic  # whether the band should be the session's microphone
        self._sound = bytearray()  # the band's sound that the pipeline has not taken yet
        self._sound_lock = threading.Lock()
        self._collecting = True
        self._heard_at = 0.0
        self._tell = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._changed = threading.Event()
        self._stage: str | None = None
        self.status = {"type": "band", "state": "off", "number": number}

    def start(self, tell) -> None:
        """Start looking for the band. `tell(message)` gets every change and every double
        tap, as a message for the dashboard. It is called on the band's thread."""
        self._tell = tell
        if self._thread and self._thread.is_alive() and not self._stop.is_set():
            return  # a new session takes over the band the last one found
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(self._stop,), name="band-link", daemon=True
        )
        self._thread.start()

    def stop(self, tell) -> None:
        """Let the band go, unless a newer session has taken it over."""
        if self._tell is tell:
            self._stop.set()
            self._changed.set()

    def show(self, stage: str) -> None:
        """Ask for the light of this stage. Returns at once; the band's thread sets it."""
        self._stage = stage
        self._changed.set()

    def use_mic(self, on: bool) -> None:
        """Make the band the session's microphone, or go back to the computer's."""
        self.mic = on
        self._changed.set()

    def sound(self, size: int) -> bytes | None:
        """The next `size` bytes of the band's sound, or None when the band is not the
        microphone right now (off, not connected, or its sound has stopped arriving)."""
        if not self.mic or time.monotonic() - self._heard_at > _SILENT_AFTER_SECONDS:
            return None
        with self._sound_lock:
            enough = max(size, _HEAD_START_BYTES) if self._collecting else size
            self._collecting = len(self._sound) < enough
            if self._collecting:
                return bytes(size)  # a short gap is silence, not a wait
            taken = bytes(self._sound[:size])
            del self._sound[:size]
        return taken

    def _heard(self, pcm: bytes) -> None:
        with self._sound_lock:
            self._sound += pcm
            del self._sound[: max(0, len(self._sound) - _MAX_WAITING_BYTES)]  # newest wins
        self._heard_at = time.monotonic()

    def _say(self, stop: threading.Event, state: str, **more) -> None:
        if self._stop is not stop:
            return  # this thread belongs to a session that ended: the band is not its to report
        self.status = {"type": "band", "state": state, "number": self._number, **more}
        self._send(self.status)

    def _send(self, message: dict) -> None:
        try:
            self._tell(message)
        except Exception as e:  # noqa: BLE001 - a session that just ended cannot be told
            logger.debug(f"Band message not delivered: {e}")

    def _run(self, stop: threading.Event) -> None:
        if not self._usb and not self._safe():
            logger.warning("This program may not use Bluetooth, so the Vexo band is left alone")
            self._say(stop, "blocked")
            return
        problem = None  # why the last try failed, for the dashboard
        while not stop.is_set():
            self._say(stop, "looking", problem=problem)
            try:
                band = self._connect(self._number, **({"transport": "serial"} if self._usb else {}))
            except Exception as e:  # noqa: BLE001 - not found yet, or Bluetooth is off
                problem = getattr(e, "code", type(e).__name__)
                logger.debug(f"Vexo band not connected yet: {e}")
                stop.wait(_RETRY_SECONDS)
                continue
            try:
                if not stop.is_set():  # the session may have ended while the band was found
                    self._serve(band, stop)
                problem = None
            except Exception as e:  # noqa: BLE001 - the tutor goes on without the band
                problem = getattr(e, "code", type(e).__name__)
                logger.warning(f"Vexo band link dropped: {e}")
                stop.wait(_RETRY_SECONDS)  # a band that fails every time must not spin
            finally:
                self._heard_at = 0.0  # whatever is left is not live sound any more
                try:
                    if band.connected:
                        band.configure(audio=False)
                        band.led_off()
                    band.disconnect()
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Vexo band did not disconnect cleanly: {e}")
        self._say(stop, "off")

    def _serve(self, band, stop: threading.Event) -> None:
        band.on("double-tap", lambda _event: self._send({"type": "band_tap"}))
        decoder = audio.PcmDecoder()
        band.on("audio", lambda packet: self._heard(decoder.feed(packet)))
        band.set_events(kinds=["double-tap"])
        band.configure(events=True)
        battery = band.get_battery().percent
        logger.info("Vexo band connected")
        mic_on, shown = None, None
        while not stop.is_set() and band.connected:
            if self.mic != mic_on:
                band.configure(audio=self.mic)
                mic_on, shown = self.mic, None  # the band's microphone takes over its light
                self._say(stop, "connected", battery=battery, mic=mic_on)
                logger.info(f"Vexo band microphone {'on' if mic_on else 'off'}")
            stage = self._stage
            if not mic_on and stage != shown and stage in LIGHTS:
                colour, pattern = LIGHTS[stage]
                band.set_led(colour, pattern=pattern)
                shown = stage
            self._changed.wait(0.5)
            self._changed.clear()
