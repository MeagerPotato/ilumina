"""Joins the voice channel, the words channel and the voice model into one reading per turn.

Each channel gives a probability for every rubric level. They are combined with a
weighted logarithmic opinion pool (a weighted geometric mean, renormalised), the
usual way to join calibrated probability estimates: a channel that is unsure spreads
its probability and so moves the result little, and the weights set how much each
channel counts when both are sure.

The weights put the voice first. Audio language models lean on the words (Chen et
al. 2025), so the words channel only gets the share we give it here. Confusion is
the exception that keeps the most weight on words: saying "I don't get it" is real
evidence, and CREMA-D's acted emotions give the voice model nothing on confusion.
The numbers are our choice, not fitted; scripts/eval_voice_channel.py measures the
voice channel so they can be tuned.

The word-blind voice model then multiplies in its likelihood ratio against the
student's usual voice (`ilumina.voice_model`), scaled by how well the usual is known.
"""

import math

from ilumina.state import LEARNING_STATES, LEVELS, Reading, _likelihood, level_of
from ilumina.voice_model import likelihood

# Share of each channel per dimension. Each row sums to 1.
CHANNEL_WEIGHTS = {
    "confusion": {"voice": 0.55, "words": 0.45},
    "frustration": {"voice": 0.65, "words": 0.35},
    "confidence": {"voice": 0.65, "words": 0.35},
    "engagement": {"voice": 0.65, "words": 0.35},
}
LEARNING_WEIGHTS = {"voice": 0.6, "words": 0.4}
# How much the voice model's evidence counts, once the student's usual is well known.
VOICE_MODEL_WEIGHT = {"frustration": 0.8, "engagement": 0.8, "confidence": 0.6}
_FLOOR = 0.01


def _pool(distributions: list[tuple[list[float], float]]) -> list[float]:
    total = sum(w for _, w in distributions)
    logs = [0.0] * len(distributions[0][0])
    for dist, w in distributions:
        for i, p in enumerate(dist):
            logs[i] += (w / total) * math.log(max(p, _FLOOR))
    top = max(logs)
    out = [math.exp(v - top) for v in logs]
    s = sum(out)
    return [v / s for v in out]


def _reading(p: list[float]) -> Reading:
    value = sum(level * q for level, q in enumerate(p)) / (LEVELS - 1)
    band = level_of(value)
    confidence = sum(q for level, q in enumerate(p) if level_of(level / (LEVELS - 1)) == band)
    return Reading(value=value, confidence=confidence, probabilities=tuple(p))


def fuse(channels: dict, voice_model: dict | None = None) -> tuple[dict[str, Reading], dict]:
    """One reading per dimension from the channels that answered, and where it came from.

    `channels` maps "voice" and "words" to `emotion.Channel`. `voice_model` is
    `VoiceModel.read`'s result, or None. Returns (readings, sources), where
    sources[dim] has each channel's own 0-to-1 value and the voice model's ratio
    (1 means the voice sounded like the student's usual).
    """
    readings, sources = {}, {}
    for dim, weights in CHANNEL_WEIGHTS.items():
        parts, source = [], {}
        for name, weight in weights.items():
            channel = channels.get(name)
            reading = channel.readings.get(dim) if channel else None
            if reading is None:
                continue
            parts.append((_likelihood(reading), weight))
            source[name] = round(reading.value, 3)
        if not parts:
            continue
        pooled = _pool(parts)
        ratio = (voice_model or {}).get("ratios", {}).get(dim)
        evidence = likelihood(dim, ratio) if ratio is not None else None
        if evidence:
            strength = VOICE_MODEL_WEIGHT.get(dim, 0.0) * voice_model.get("maturity", 0.0)
            pooled = _normalise([p * e**strength for p, e in zip(pooled, evidence)])
            source["voice_model"] = round(ratio, 3)
        readings[dim] = _reading(pooled)
        sources[dim] = source
    return readings, sources


def fuse_learning(channels: dict) -> dict[str, float] | None:
    """The learning-state probabilities, pooled the same way. None if no channel gave any."""
    parts = []
    for name, weight in LEARNING_WEIGHTS.items():
        channel = channels.get(name)
        if channel and channel.learning:
            parts.append(([channel.learning.get(s, 0.0) for s in LEARNING_STATES], weight))
    if not parts:
        return None
    return dict(zip(LEARNING_STATES, _pool(parts)))


def _normalise(p: list[float]) -> list[float]:
    s = sum(p)
    return [v / s for v in p] if s > 0 else [1 / len(p)] * len(p)
