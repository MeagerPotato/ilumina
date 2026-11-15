"""The voice measurements shown on the dashboard and given to the voice channel.

Pitch (F0), loudness and how much of the turn was voiced, read from the frame-level
analysis in `ilumina.acoustic`. These are the turn-level features the spoken-tutoring
uncertainty studies used (Liscombe, Hirschberg and Venditti 2005; Pon-Barry and
Shieber 2011): pitch level, range and movement, the rise or fall at the end, loudness
and its spread, and the voiced share as a speaking-rate proxy. Both studies compared
pitch and loudness with each speaker's own usual, which `ilumina.baseline` does.

Nothing here is kept: the audio is read once and dropped.
"""

import numpy as np

from ilumina.acoustic import HOP_SECONDS, MIN_VOICED_FRAMES, Analysis, analyse, read_wav

_END_SECONDS = 0.5  # the stretch at the end of the turn used for its final rise or fall


def from_analysis(a: Analysis | None) -> dict | None:
    """The dashboard's voice numbers for one turn, or None when too little was voiced."""
    if a is None or a.voiced.sum() < MIN_VOICED_FRAMES:
        return None
    hz = a.f0[a.voiced]
    median = float(np.median(hz))
    st_all = 12 * np.log2(hz / median)
    keep = np.abs(st_all) < 12  # drop octave errors
    times = np.flatnonzero(a.voiced)[keep] * HOP_SECONDS
    st = st_all[keep]
    if len(st) < MIN_VOICED_FRAMES:
        return None
    steps = np.diff(st) / np.maximum(np.diff(times), HOP_SECONDS)
    close = np.diff(times) <= 3 * HOP_SECONDS
    movement = float(np.mean(np.abs(steps[close]))) if close.any() else 0.0
    end = times >= times[-1] - _END_SECONDS
    end_change = 0.0
    if end.sum() >= 5:
        slope = np.polyfit(times[end], st[end], 1)[0]
        end_change = float(slope * (times[end][-1] - times[end][0]))
    span = np.flatnonzero(a.sounding)
    talking = (span[-1] - span[0] + 1) if len(span) else 0
    level = a.dbfs[a.voiced]
    return {
        "pitch_hz": round(median),
        "pitch_range": round(float(np.percentile(st, 90) - np.percentile(st, 10)), 1),
        "pitch_movement": round(movement, 1),
        "end_change": round(end_change, 1),  # semitones over the last half second
        "loudness": round(float(np.median(level))),
        "loudness_spread": round(float(np.std(level)), 1),
        "voiced_share": round(float(a.voiced.sum() / max(talking, 1)), 2),
    }


def prosody(wav: bytes) -> dict | None:
    """Voice measurements for one turn's WAV, or None when too little of it was voiced."""
    samples, rate = read_wav(wav)
    return from_analysis(analyse(samples, rate))


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
