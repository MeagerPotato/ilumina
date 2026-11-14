"""The Vexo band in a tutoring session, against the kit's own pretend band."""

import time

from vexo_open.sync import Band, VexoError
from vexo_open.transports.sim import SimTransport

import lecture
from ilumina import band_link, vexo_band
from ilumina.band_link import LIGHTS, BandLink


def wait_for(check, seconds: float = 5.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.02)
    return False


def pretend_band():
    """A link to the kit's pretend band, the band itself, and what the dashboard is told."""
    sim = SimTransport(42, auto_tap=False)
    link = BandLink(
        42, connect=lambda number, **options: Band.connect(number, transport=sim), safe=lambda: True
    )
    told = []
    link.start(told.append)
    assert wait_for(lambda: link.status["state"] == "connected")
    return link, sim, told


def colour(sim) -> str:
    led = sim.led
    return f"#{led['r']:02x}{led['g']:02x}{led['b']:02x}"


def test_a_double_tap_reaches_the_dashboard_and_the_light_follows_the_turn():
    link, sim, told = pretend_band()
    try:
        assert told[0]["state"] == "looking"
        assert told[-1]["state"] == "connected" and told[-1]["number"] == 42
        assert isinstance(told[-1]["battery"], int)

        sim.tap("double-tap")
        assert wait_for(lambda: {"type": "band_tap"} in told)
        sim.tap("tap")  # a single tap, such as the wrist landing on the desk, means nothing
        time.sleep(0.2)
        assert told.count({"type": "band_tap"}) == 1

        for stage in ("hearing", "thinking", "speaking", "listening"):
            link.show(stage)
            assert wait_for(lambda stage=stage: colour(sim) == LIGHTS[stage][0])
    finally:
        link.stop(lambda message: None)  # an older session ending late: the band is kept
        time.sleep(0.2)
        assert link.status["state"] == "connected"
        link.stop(link._tell)
    assert wait_for(lambda: link.status["state"] == "off")


def test_a_band_that_is_not_found_is_looked_for_again(monkeypatch):
    monkeypatch.setattr(band_link, "_RETRY_SECONDS", 0.05)
    sim = SimTransport(42, auto_tap=False)
    tries = []

    def connect(number, **options):
        tries.append(number)
        if len(tries) < 3:
            raise VexoError("not-found-nearby", "Could not see the band.")
        return Band.connect(number, transport=sim)

    link = BandLink(42, connect=connect, safe=lambda: True)
    told = []
    link.start(told.append)
    try:
        assert wait_for(lambda: link.status["state"] == "connected")
        assert len(tries) == 3
        link.show("speaking")  # asked before or after connecting, the light is set
        assert wait_for(lambda: colour(sim) == LIGHTS["speaking"][0])
    finally:
        link.stop(link._tell)
    assert wait_for(lambda: link.status["state"] == "off")


def test_the_cable_is_asked_for_by_name():
    asked = []

    def connect(number, **options):
        asked.append((number, options))
        raise VexoError("not-found", "No band on USB.")

    link = BandLink(None, usb=True, connect=connect)
    link.start(lambda message: None)
    assert wait_for(lambda: asked)
    link.stop(link._tell)
    assert asked[0] == (None, {"transport": "serial"})


def test_a_lecture_falls_back_to_the_computer_when_the_band_does_not_connect(monkeypatch, capsys):
    calls = []

    def record(source=None, seconds=None, band_number=None, usb=False, on_progress=None):
        calls.append((band_number, usb, source is not None))
        if band_number or usb:
            raise VexoError("not-found-nearby", "Could not see Vexo-HACK-42.")
        return b"\0\0" * vexo_band.SAMPLE_RATE

    monkeypatch.setattr(vexo_band, "record", record)
    monkeypatch.setattr(vexo_band, "mic_packets", lambda: iter([b"packet"]))
    monkeypatch.setattr(lecture, "transcribe", lambda pcm, key: "the derivative of sine")
    monkeypatch.setattr(lecture.config, "DEEPGRAM_API_KEY", "x")
    monkeypatch.setattr(lecture.config, "GOOGLE_API_KEY", "x")
    args = lecture.argparse.Namespace(band=42, usb=False, file=None, seconds=1)

    assert lecture.listen(args) == "the derivative of sine"
    assert calls == [(42, False, False), (None, False, True)]
    assert args.band is None  # so a saved lecture says it came from the computer
    out = capsys.readouterr().out
    assert "The band did not connect" in out and "this computer's microphone" in out


def test_bluetooth_that_would_kill_the_bot_is_never_touched():
    asked = []
    link = BandLink(42, connect=lambda number, **options: asked.append(number), safe=lambda: False)
    told = []
    link.start(told.append)
    assert wait_for(lambda: link.status["state"] == "blocked")
    time.sleep(0.1)
    assert asked == [] and told[-1]["state"] == "blocked"
