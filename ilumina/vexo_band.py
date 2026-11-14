"""Lecture audio through the Vexo Open band library, with a real band or without one.

The band sends its microphone as Opus packets (16 kHz mono, 20 ms each). With a band,
pass its number (Bluetooth) or usb=True (the cable) and this listens to the band's own
microphone. Without one, or when the band cannot be reached, the Mac's microphone (or a
sound file) stands in: its sound is turned into the same Opus packets and handed to Vexo's
own pretend band (`SimTransport`), which plays them on its `audio` stream through the real
Vexo protocol. Everything after that is the same code either way.

    pcm = record(band_number=42, seconds=60)              # a real Vexo band over Bluetooth
    pcm = record(usb=True, seconds=60)                    # a real Vexo band on the USB cable
    pcm = record(source=mic_packets(), seconds=60)        # Mac mic as the band's mic
"""

from __future__ import annotations

import itertools
import queue
import signal
import threading
import time
from collections.abc import Iterable, Iterator
from pathlib import Path

import av
from vexo_open import audio
from vexo_open.sync import Band
from vexo_open.transports.sim import SimTransport

SAMPLE_RATE = audio.SAMPLE_RATE  # 16000
FRAME_SAMPLES = audio.FRAME_SAMPLES  # 320 samples = 20 ms
FRAME_BYTES = 2 * FRAME_SAMPLES
PRETEND_BAND = 42  # any number 1..999 works for the pretend band
# The pretend band cannot hear the packets, so it is told a speaking-level loudness.
SPEECH_LEVEL = 0.7


class OpusEncoder:
    """20 ms of 16 bit mono samples in, Opus packets out (the band's format)."""

    def __init__(self) -> None:
        self._ctx = av.CodecContext.create("libopus", "w")
        self._ctx.sample_rate = SAMPLE_RATE
        self._ctx.layout = "mono"
        self._ctx.format = "s16"
        self._ctx.bit_rate = 24000
        self._pts = 0

    def encode(self, pcm: bytes) -> list[bytes]:
        frame = av.AudioFrame(format="s16", layout="mono", samples=FRAME_SAMPLES)
        frame.planes[0].update(pcm.ljust(FRAME_BYTES, b"\0")[:FRAME_BYTES])
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._pts
        self._pts += FRAME_SAMPLES
        return [bytes(p) for p in self._ctx.encode(frame)]

    def flush(self) -> list[bytes]:
        return [bytes(p) for p in self._ctx.encode(None)]


def pcm_frames(pcm: bytes) -> Iterator[bytes]:
    for i in range(0, len(pcm), FRAME_BYTES):
        yield pcm[i : i + FRAME_BYTES]


def encode_pcm(pcm: bytes) -> list[bytes]:
    encoder = OpusEncoder()
    packets = [p for frame in pcm_frames(pcm) for p in encoder.encode(frame)]
    return packets + encoder.flush()


def file_pcm(path: str | Path) -> bytes:
    """Any sound file (m4a, mp3, wav, ogg...) as 16 kHz mono 16 bit samples."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    out = bytearray()
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            for r in resampler.resample(frame):
                out += bytes(r.planes[0])[: 2 * r.samples]
    for r in resampler.resample(None):
        out += bytes(r.planes[0])[: 2 * r.samples]
    return bytes(out)


def file_packets(path: str | Path) -> list[bytes]:
    """A sound file as band packets (re-encoded, so any format and rate works)."""
    return encode_pcm(file_pcm(path))


def mic_packets(stop: threading.Event | None = None) -> Iterator[bytes]:
    """The computer's microphone, live, as band packets, until `stop` is set."""
    import sounddevice as sd  # imported here: it needs a sound system (macOS has one)

    stop = stop or threading.Event()
    frames: queue.Queue[bytes] = queue.Queue()
    encoder = OpusEncoder()

    def on_sound(indata, _frames, _time, _status):
        frames.put(bytes(indata))

    with sd.RawInputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
        callback=on_sound,
    ):
        while not stop.is_set():
            try:
                pcm = frames.get(timeout=0.2)
            except queue.Empty:
                continue
            yield from encoder.encode(pcm)


def record(
    source: Iterable[bytes] | None = None,
    seconds: float | None = None,
    band_number: int | None = None,
    usb: bool = False,
    on_progress=None,
    stop: threading.Event | None = None,
) -> bytes:
    """Listen through the Vexo band library and return 16 kHz mono 16 bit samples.

    source: band packets to play through Vexo's pretend band (mic_packets() or
    file_packets()). band_number instead: a real band over Bluetooth, its own microphone.
    usb=True: a real band on the USB cable (no number needed, no double tap).
    Stops after `seconds`, when the source ends, when `stop` is set, or on Ctrl+C.
    """
    stop = stop or threading.Event()
    packets = None
    real = band_number is not None or usb
    if not real and source is not None:
        # Start the source here, so a microphone that cannot open fails now, not silently
        # inside the feeding thread.
        packets = iter(source)
        first = next(packets, None)
        packets = itertools.chain([] if first is None else [first], packets)

    if real:
        band = Band.connect(band_number, **({"transport": "serial"} if usb else {}))
    else:
        band = Band.connect(PRETEND_BAND, transport=SimTransport(PRETEND_BAND, auto_tap=False))

    decoder = audio.PcmDecoder()
    pcm = bytearray()
    band.on("audio", lambda a: pcm.extend(decoder.feed(a)))
    # A real band's light goes solid blue: the microphone is on. On the pretend band the
    # mic-level stream also takes up the loudness curves that go with each batch.
    band.configure(audio=True, mic_level=not real)

    sent = [0]  # packets handed to the pretend band
    finished = threading.Event()
    failure = []

    def feed():
        try:
            batch = []
            for packet in packets:
                if stop.is_set():
                    break
                batch.append(packet)
                # 200 ms first, so the band always has sound queued, then 100 ms at a time.
                if len(batch) == (10 if sent[0] == 0 else 5):
                    band.transport.play_loudness(
                        SPEECH_LEVEL, seconds=0.02 * len(batch), packets=batch
                    )
                    sent[0] += len(batch)
                    batch = []
                    # A file is ready at once; keep at most ~1 s queued so it plays in step.
                    while sent[0] * 0.02 > time.monotonic() - start + 1 and not stop.is_set():
                        time.sleep(0.05)
            if hasattr(packets, "close"):
                packets.close()
            if hasattr(source, "close"):
                source.close()  # lets the live microphone close
            if batch:
                band.transport.play_loudness(SPEECH_LEVEL, seconds=0.02 * len(batch), packets=batch)
                sent[0] += len(batch)
        except Exception as e:  # noqa: BLE001 - handed to the main thread below
            failure.append(e)
        finished.set()

    def queued_seconds() -> float:
        """Sound handed to the pretend band that it has not sent yet."""
        return sent[0] * 0.02 + 0.2 - (time.monotonic() - start)

    # The band library's wait() swallows Ctrl+C, so catch it here to end the recording.
    old_handler = None
    if threading.current_thread() is threading.main_thread():
        old_handler = signal.signal(signal.SIGINT, lambda *_: stop.set())

    start = time.monotonic()
    feeder = None
    if packets is not None:
        feeder = threading.Thread(target=feed, daemon=True)
        feeder.start()
    try:
        while not stop.is_set():
            if not band.wait(0.25):
                break  # the band went away
            elapsed = time.monotonic() - start
            if on_progress:
                on_progress(elapsed)
            if seconds is not None and elapsed >= seconds:
                break
            if failure or (finished.is_set() and queued_seconds() <= 0):
                break
    finally:
        stop.set()
        if feeder:
            feeder.join(timeout=2)
            if 0 < queued_seconds() < 3:
                band.wait(queued_seconds())  # let the last queued sound arrive
        if old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)
        if band.connected:
            band.configure(audio=False, mic_level=False)
        band.disconnect()
    if failure:
        raise RuntimeError(f"The sound source stopped: {failure[0]}") from failure[0]
    return bytes(pcm) + decoder.flush()
