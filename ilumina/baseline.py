"""This student's usual voice, learned over the session, so each turn can be read against it.

People differ a lot in how they normally sound: one student always speaks slowly,
another always pauses. The uncertainty studies in docs/emotion-research.md compared
pitch and loudness with each speaker's own usual for that reason. This keeps the
median of each measurement over the student's earlier turns and says, in plain words,
which ones this turn is clearly away from. Numbers only, kept in memory for one session.
"""

from math import log2
from statistics import median

# Earlier turns needed before a usual is trusted.
MIN_TURNS = 3
_KEEP = 20  # the usual follows the most recent turns, as the student settles in

# (measurement, words, how far from the usual counts as clearly different, how):
# "ratio" compares as a share of the usual, "semitones" as a musical interval, and
# "difference" in the measurement's own units (seconds or dB).
_CHECKS = (
    ("words_per_minute", "pace", 0.25, "ratio"),
    ("longest_pause", "longest pause", 0.75, "difference"),
    ("waited", "wait before answering", 1.0, "difference"),
    ("silence", "silence inside the answer", 1.0, "difference"),
    ("pitch_hz", "pitch", 2.0, "semitones"),
    ("pitch_range", "pitch range", 0.4, "ratio"),
    ("loudness", "loudness", 4.0, "difference"),
)
_WORDS = {
    "pace": ("faster", "slower"),
    "longest pause": ("longer", "shorter"),
    "wait before answering": ("longer", "shorter"),
    "silence inside the answer": ("more", "less"),
    "pitch": ("higher", "lower"),
    "pitch range": ("wider", "narrower"),
    "loudness": ("louder", "quieter"),
}


def _change(kind: str, now: float, usual: float) -> float | None:
    """How far `now` is from `usual`, in the check's own units. None when not comparable."""
    if kind == "ratio":
        return None if usual <= 0 else now / usual - 1
    if kind == "semitones":
        if now <= 0 or usual <= 0:
            return None
        return 12 * log2(now / usual)
    return now - usual


class SpeakerBaseline:
    """Remembers the student's earlier turns and compares each new one with them."""

    def __init__(self):
        self._history: dict[str, list[float]] = {}

    def compare(self, measured: dict) -> dict[str, str]:
        """How this turn differs from the usual, e.g. {"pace": "slower"}. Then learns from it.

        Only clear differences are returned, and nothing until MIN_TURNS earlier turns.
        """
        out = {}
        for key, label, threshold, kind in _CHECKS:
            now = measured.get(key)
            past = self._history.get(key, [])
            if not isinstance(now, (int, float)) or len(past) < MIN_TURNS:
                continue
            change = _change(kind, float(now), median(past))
            if change is None or abs(change) < threshold:
                continue
            out[label] = _WORDS[label][0 if change > 0 else 1]
        for key, *_ in _CHECKS:
            now = measured.get(key)
            if isinstance(now, (int, float)):
                self._history.setdefault(key, []).append(float(now))
                del self._history[key][:-_KEEP]
        return out


def describe_change(changes: dict[str, str]) -> str:
    """One line for Decision 1, or "" when nothing stands out."""
    if not changes:
        return ""
    parts = [f"{label} {word}" for label, word in changes.items()]
    return "Compared with this student's usual turns this session: " + ", ".join(parts) + "."
