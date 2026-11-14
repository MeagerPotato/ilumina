"""Measured voice features for one student turn, from the turn's own audio.

Pitch (F0), loudness and how much of the turn was voiced, worked out with numpy from
the same WAV that goes to Decision 1. These are measurements, not judgements. They
are the turn-level features the spoken-tutoring uncertainty studies used (Liscombe,
Hirschberg and Venditti 2005; Pon-Barry and Shieber 2011): pitch level, range and
movement, loudness and its spread, and the voiced share as a speaking-rate proxy.
Both studies compared pitch and loudness with each speaker's own usual, which
`ilumina.baseline` does across the session.

Nothing here is kept: the audio is read once and dropped.
"""

import io
import wave

import numpy as np

_FRAME_SECONDS, _HOP_SECONDS = 0.04, 0.01
_MIN_HZ, _MAX_HZ = 70.0, 450.0
# A frame counts as voiced when its periodicity is this strong and it is not near silence.
_VOICED_CORRELATION = 0.5
_QUIET_DBFS = -50.0
_MIN_VOICED_FRAMES = 10  # 0.1 s of voicing; below this, pitch numbers mean nothing
_END_SECONDS = 0.5  # the stretch at the end of the turn used for its final rise or fall


def _pcm(wav: bytes) -> tuple[np.ndarray, int]:
    """Mono float samples in -1..1 and the sample rate."""
    with wave.open(io.BytesIO(wav)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit audio, got {width * 8}-bit")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def _frames(samples: np.ndarray, size: int, hop: int) -> np.ndarray:
    if len(samples) < size:
        return np.empty((0, size))
    count = 1 + (len(samples) - size) // hop
    index = np.arange(size)[None, :] + hop * np.arange(count)[:, None]
    return samples[index]


def _pitch(frames: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """F0 in Hz per frame (0 where unvoiced) and each frame's periodicity, by autocorrelation."""
    windowed = (frames - frames.mean(axis=1, keepdims=True)) * np.hanning(frames.shape[1])
    n = 1 << int(np.ceil(np.log2(2 * frames.shape[1])))
    spectrum = np.fft.rfft(windowed, n=n, axis=1)
    acf = np.fft.irfft(spectrum * np.conj(spectrum), n=n, axis=1)[:, : frames.shape[1]]
    energy = acf[:, :1]
    acf = np.where(energy > 0, acf / np.maximum(energy, 1e-12), 0)
    low, high = int(rate / _MAX_HZ), min(int(rate / _MIN_HZ), frames.shape[1] - 1)
    lags = np.argmax(acf[:, low:high], axis=1) + low
    strength = acf[np.arange(len(acf)), lags]
    return np.where(strength >= _VOICED_CORRELATION, rate / lags, 0.0), strength


def _semitones(hz: np.ndarray, reference: float) -> np.ndarray:
    return 12 * np.log2(hz / reference)


def prosody(wav: bytes) -> dict | None:
    """Voice measurements for one turn, or None when too little of it was voiced."""
    samples, rate = _pcm(wav)
    size, hop = int(_FRAME_SECONDS * rate), int(_HOP_SECONDS * rate)
    frames = _frames(samples, size, hop)
    if not len(frames):
        return None
    rms = np.sqrt(np.mean(frames**2, axis=1))
    dbfs = 20 * np.log10(np.maximum(rms, 1e-6))
    f0, _ = _pitch(frames, rate)
    voiced = (f0 > 0) & (dbfs > _QUIET_DBFS)
    if voiced.sum() < _MIN_VOICED_FRAMES:
        return None
    hz = f0[voiced]
    median = float(np.median(hz))
    # Octave errors are the usual autocorrelation mistake: drop frames an octave away.
    keep = np.abs(_semitones(hz, median)) < 12
    times = np.flatnonzero(voiced)[keep] * _HOP_SECONDS
    st = _semitones(hz[keep], median)
    if len(st) < _MIN_VOICED_FRAMES:
        return None
    sounding = dbfs > _QUIET_DBFS
    span = np.flatnonzero(sounding)
    talking = (span[-1] - span[0] + 1) if len(span) else 0
    # Pitch movement: the average absolute change, in semitones a second, between
    # neighbouring voiced frames that are close in time (not across a pause).
    steps = np.diff(st) / np.maximum(np.diff(times), _HOP_SECONDS)
    close = np.diff(times) <= 3 * _HOP_SECONDS
    movement = float(np.mean(np.abs(steps[close]))) if close.any() else 0.0
    end = times >= times[-1] - _END_SECONDS
    end_change = 0.0
    if end.sum() >= 5:
        slope = np.polyfit(times[end], st[end], 1)[0]
        end_change = float(slope * (times[end][-1] - times[end][0]))
    return {
        "pitch_hz": round(median),
        "pitch_range": round(float(np.percentile(st, 90) - np.percentile(st, 10)), 1),
        "pitch_movement": round(movement, 1),
        "end_change": round(end_change, 1),  # semitones over the last half second
        "loudness": round(float(np.median(dbfs[voiced]))),
        "loudness_spread": round(float(np.std(dbfs[voiced])), 1),
        "voiced_share": round(float(voiced.sum() / max(talking, 1)), 2),
    }


def describe_prosody(measured: dict) -> str:
    """The same measurements as one line of plain text, for Decision 1."""
    end = measured["end_change"]
    if end >= 2:
        ending = f"rises {end} semitones at the end"
    elif end <= -2:
        ending = f"falls {-end} semitones at the end"
    else:
        ending = "is level at the end"
    return (
        f"Measured from the voice: pitch about {measured['pitch_hz']} Hz with a range of "
        f"{measured['pitch_range']} semitones, and it {ending}; loudness "
        f"{measured['loudness']} dBFS; voiced for {round(measured['voiced_share'] * 100)}% "
        "of the time they were talking."
    )
