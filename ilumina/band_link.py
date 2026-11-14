"""The student's Vexo band during a tutoring session.

The band is on the wrist while the student works on paper, so it does two things a screen
cannot: its light shows whose turn it is, and a double tap means "done talking". The band
connects in the background and keeps trying, so a band that is not found, or drops out,
never holds up or stops the tutor. Only taps are read. The band's microphone stays off:
a session's sound still comes from the computer's microphone.
"""

import subprocess
import sys
import threading

from loguru import logger
from vexo_open.sync import Band

# The light for each stage of a turn, in the colours the dashboard uses for that stage.
LIGHTS = {
    "listening": ("#2b6fe3", "solid"),  # your turn
    "hearing": ("#0e9384", "solid"),  # hearing you
    "thinking": ("#ffaa00", "blink"),  # heard you
    "speaking": ("#7a4fe0", "breathe"),  # the tutor is speaking
}
_RETRY_SECONDS = 2  # a band can only be found for a minute after its double tap

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
        self, number: int | None, usb: bool = False, connect=Band.connect, safe=bluetooth_is_safe
    ):
        self._number, self._usb, self._connect, self._safe = number, usb, connect, safe
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

    def _say(self, state: str, **more) -> None:
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
            self._say("blocked")
            return
        while not stop.is_set():
            self._say("looking")
            try:
                band = self._connect(self._number, **({"transport": "serial"} if self._usb else {}))
            except Exception as e:  # noqa: BLE001 - not found yet, or Bluetooth is off
                logger.debug(f"Vexo band not connected yet: {e}")
                stop.wait(_RETRY_SECONDS)
                continue
            try:
                self._serve(band, stop)
            except Exception as e:  # noqa: BLE001 - the tutor goes on without the band
                logger.warning(f"Vexo band link dropped: {e}")
            finally:
                try:
                    if band.connected:
                        band.led_off()
                    band.disconnect()
                except Exception as e:  # noqa: BLE001
                    logger.debug(f"Vexo band did not disconnect cleanly: {e}")
        self._say("off")

    def _serve(self, band, stop: threading.Event) -> None:
        band.on("double-tap", lambda _event: self._send({"type": "band_tap"}))
        band.set_events(kinds=["double-tap"])
        band.configure(events=True)
        self._say("connected", battery=band.get_battery().percent)
        logger.info("Vexo band connected")
        shown = None
        while not stop.is_set() and band.connected:
            stage = self._stage
            if stage != shown and stage in LIGHTS:
                colour, pattern = LIGHTS[stage]
                band.set_led(colour, pattern=pattern)
                shown = stage
            self._changed.wait(0.5)
            self._changed.clear()
