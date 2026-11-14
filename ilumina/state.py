"""Student-state tracker: turns noisy per-turn readings into a steady estimate.

Plain Python with no model calls. It knows nothing about tutoring, so it can sit
behind any voice agent.
"""

from dataclasses import dataclass

DIMENSIONS = ("confusion", "frustration", "confidence", "engagement")

# A single reading this confident may change the level without a second turn.
STRONG_CONFIDENCE = 0.85


@dataclass
class Reading:
    """One model reading for one dimension on one turn."""

    value: float  # 0 (none) to 1 (very strong)
    confidence: float  # 0 to 1, how sure the model is


def level_of(value: float) -> str:
    if value >= 0.65:
        return "high"
    if value >= 0.35:
        return "medium"
    return "low"


class StateTracker:
    """Keeps a smoothed estimate and a confirmed level per dimension.

    The level changes only when two turns in a row land in the new level, or
    one turn does with very high confidence. Until then the shift is a "blip".
    """

    def __init__(self, smoothing: float = 0.6):
        self._smoothing = smoothing
        self._turn = 0
        self._estimate: dict[str, float] = {}
        self._level: dict[str, str] = {}
        self._pending: dict[str, str] = {}  # level seen last turn, not yet confirmed

    def update(self, readings: dict[str, Reading]) -> dict:
        """Fold in one turn of readings and return a snapshot for the tutor and UI."""
        self._turn += 1
        dims = {}
        for name, reading in readings.items():
            if name not in self._estimate:
                self._estimate[name] = reading.value
                self._level[name] = level_of(reading.value)
                status = "steady"
            else:
                # Low-confidence readings move the estimate less.
                weight = self._smoothing * reading.confidence
                self._estimate[name] += weight * (reading.value - self._estimate[name])
                status = self._confirm(name, reading)
            dims[name] = {
                "estimate": round(self._estimate[name], 3),
                "level": self._level[name],
                "status": status,
                "reading": round(reading.value, 3),
                "confidence": round(reading.confidence, 3),
            }
        return {"turn": self._turn, "dimensions": dims}

    def _confirm(self, name: str, reading: Reading) -> str:
        seen = level_of(reading.value)
        if seen == self._level[name]:
            self._pending.pop(name, None)
            return "steady"
        if self._pending.get(name) == seen or reading.confidence >= STRONG_CONFIDENCE:
            self._level[name] = seen
            self._pending.pop(name, None)
            return "trend"
        self._pending[name] = seen
        return "blip"


def describe(snapshot: dict) -> str:
    """One short line for the tutor model."""
    parts = []
    for name, d in snapshot["dimensions"].items():
        part = f"{name} {d['level']}"
        if d["status"] == "trend":
            part += " (just changed)"
        elif d["status"] == "blip":
            part += f" (blip: one turn read {level_of(d['reading'])})"
        parts.append(part)
    return f"Student state, turn {snapshot['turn']}, estimate only: " + ", ".join(parts) + "."
