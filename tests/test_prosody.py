import io
import wave

import numpy as np

from ilumina.baseline import MIN_TURNS, SpeakerBaseline, describe_change
from ilumina.evidence import voice_evidence
from ilumina.measured import SHORT_TURN_WEIGHT, measure_turn
from ilumina.prosody import describe_prosody, prosody

RATE = 16000


def voice(f0, rate=RATE) -> bytes:
    """A buzzy voice-like tone following the pitch track `f0`, with a little silence round it."""
    phase = np.cumsum(2 * np.pi * np.asarray(f0, dtype=float) / rate)
    x = sum(np.sin(k * phase) / k for k in range(1, 6)) * 0.15
    x = np.r_[np.zeros(rate // 4), x, np.zeros(rate // 4)]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((x * 32767).astype(np.int16).tobytes())
    return buffer.getvalue()


def test_pitch_and_a_rise_at_the_end_are_measured():
    rising = prosody(voice(np.r_[np.full(RATE, 180.0), np.linspace(180, 250, RATE // 2)]))
    assert abs(rising["pitch_hz"] - 180) <= 3
    assert 4.5 <= rising["end_change"] <= 6.5  # 180 to 250 Hz is 5.7 semitones
    assert "rises" in describe_prosody(rising)
    falling = prosody(voice(np.r_[np.full(RATE, 180.0), np.linspace(180, 130, RATE // 2)]))
    assert falling["end_change"] <= -4.5 and "falls" in describe_prosody(falling)


def test_silence_and_noise_give_no_voice_features():
    assert prosody(voice(np.zeros(0))) is None
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        noise = np.random.default_rng(0).normal(0, 0.05, RATE)
        w.writeframes((noise * 32767).astype(np.int16).tobytes())
    assert prosody(buffer.getvalue()) is None


def test_the_usual_is_learned_before_any_change_is_reported():
    baseline = SpeakerBaseline()
    for _ in range(MIN_TURNS):
        assert baseline.compare({"words_per_minute": 150, "pitch_hz": 200, "loudness": -20}) == {}
    changes = baseline.compare({"words_per_minute": 90, "pitch_hz": 200, "loudness": -28})
    assert changes == {"pace": "slower", "loudness": "quieter"}
    assert describe_change(changes) == (
        "Compared with this student's usual turns this session: pace slower, loudness quieter."
    )
    assert describe_change({}) == ""


def test_a_short_or_unvoiced_turn_counts_for_less():
    wav = voice(np.full(RATE, 200.0))
    words = [{"word": w, "start": i * 0.3, "end": i * 0.3 + 0.2} for i, w in enumerate("x" * 8)]
    full = measure_turn(wav, voice_evidence({"words": words}), SpeakerBaseline())
    assert full["weight"] == 1.0 and full["voice"] is not None
    assert "Measured from the voice" in full["text"]
    one = {"words": [{"word": "yes", "start": 0.0, "end": 0.4}]}
    short = measure_turn(wav, voice_evidence(one), SpeakerBaseline())
    assert short["weight"] == SHORT_TURN_WEIGHT
    broken = measure_turn(b"not a wav", None, SpeakerBaseline())
    assert broken["voice"] is None and broken["weight"] == SHORT_TURN_WEIGHT
