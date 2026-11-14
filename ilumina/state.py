"""Student-state tracker: turns noisy per-turn readings into a steady estimate.

Plain Python with no model calls. It knows nothing about tutoring, so it can sit
behind any voice agent.

How it works (see docs/emotion-research.md for the sources):

- Each dimension is a hidden level from 0 to 4, the same scale as the rubric. The
  tracker keeps a probability for every level, not one number, so it always knows
  how sure it is.
- Between turns a level tends to stay where it was. How strongly differs by state:
  in Baker et al. (2010) boredom was the most persistent state and frustration was
  less persistent, so low engagement is "stickier" here than frustration.
- Each turn, Decision 1's calibrated probabilities for the five rubric levels are
  folded in with Bayes' rule. They are tempered (raised to a power below 1)
  because neighbouring turns share context, so they are not independent evidence,
  and they are tempered more when a turn is too short to carry much voice evidence.
- The level shown to the tutor changes only when the new band holds most of the
  probability, so one odd turn is a "blip" unless the model was very sure.

The learning-state tracker does the same over one categorical question (engaged,
confused, frustrated, bored, neutral) with transitions that follow the
D'Mello and Graesser (2012) model of affect dynamics during learning.
"""

from dataclasses import dataclass

DIMENSIONS = ("confusion", "frustration", "confidence", "engagement")
LEVELS = 5  # rubric levels 0 to 4
BANDS = ("low", "medium", "high")

# A single reading this confident may change the level without a second turn.
# Confidence is the chance of the whole low/medium/high band, so a 70/30 split
# between two bands must not count as strong.
STRONG_CONFIDENCE = 0.8

# The confirmed level moves to a new band once the tracker gives that band at least
# this much probability. Below it, a reading in a new band is a blip.
SWITCH_AT = 0.6
# Or at least this much, when the newest turn also reads that band.
MAJORITY = 0.5
# A level kept with less than this much probability is dropped for the likeliest band.
LEAST_BELIEVABLE = 1 / 3

# Chance a dimension stays at its level from one turn to the next, before the new
# reading. Ordered by the persistence findings of Baker et al. (2010): boredom (low
# engagement) persisted most, frustration least. The exact numbers are our tuning,
# not values from the paper.
PERSISTENCE = {
    "confusion": 0.80,
    "frustration": 0.70,
    "confidence": 0.80,
    "engagement": 0.85,
}
_DEFAULT_PERSISTENCE = 0.80

# How much one turn's calibrated probabilities count. 1.0 would treat each turn as
# fully independent evidence, which it is not.
EVIDENCE_WEIGHT = 0.7
_FLOOR = 0.02  # no level is ever ruled out completely by one reading


@dataclass
class Reading:
    """One model reading for one dimension on one turn."""

    value: float  # 0 (none) to 1 (very strong)
    confidence: float  # 0 to 1, how sure the model is of the band `value` falls in
    # The model's probability for each rubric level 0..4, when the API gave them.
    probabilities: tuple[float, ...] | None = None


def level_of(value: float) -> str:
    if value >= 0.65:
        return "high"
    if value >= 0.35:
        return "medium"
    return "low"


def _band_of_level(level: int) -> str:
    return level_of(level / (LEVELS - 1))


def _normalise(p: list[float]) -> list[float]:
    total = sum(p)
    if total <= 0:
        return [1 / len(p)] * len(p)
    return [x / total for x in p]


def _bands(p: list[float]) -> dict[str, float]:
    out = dict.fromkeys(BANDS, 0.0)
    for level, mass in enumerate(p):
        out[_band_of_level(level)] += mass
    return out


def _likelihood(reading: Reading) -> list[float]:
    """The reading as a probability for each level 0..4."""
    if reading.probabilities and len(reading.probabilities) == LEVELS:
        return _normalise([max(0.0, float(x)) for x in reading.probabilities])
    # No per-level probabilities: put the band confidence on the reading's band,
    # mostly on the levels nearest the value, and spread the rest over the other bands.
    position = max(0.0, min(1.0, reading.value)) * (LEVELS - 1)
    band = level_of(reading.value)
    inside = [lv for lv in range(LEVELS) if _band_of_level(lv) == band]
    others = [lv for lv in range(LEVELS) if _band_of_level(lv) != band]
    conf = max(0.0, min(1.0, reading.confidence))
    near = {lv: 1 / (1 + 2 * abs(lv - position)) for lv in inside}
    p = [0.0] * LEVELS
    for lv in inside:
        p[lv] = conf * near[lv] / sum(near.values())
    for lv in others:
        p[lv] = (1 - conf) / len(others)
    return _normalise(p)


def _predict(p: list[float], stay: float) -> list[float]:
    """One turn passes: each level mostly stays, and otherwise drifts, nearer levels first."""
    out = [0.0] * len(p)
    for i, mass in enumerate(p):
        weights = [0.0 if j == i else 1 / abs(i - j) for j in range(len(p))]
        total = sum(weights)
        for j in range(len(p)):
            out[j] += mass * (stay if j == i else (1 - stay) * weights[j] / total)
    return out


def _fold(prior: list[float], likelihood: list[float], weight: float) -> list[float]:
    return _normalise([pr * (max(lk, _FLOOR) ** weight) for pr, lk in zip(prior, likelihood)])


class StateTracker:
    """Keeps a probability for each level of each dimension, and a confirmed level.

    The level changes when the new band holds most of the probability, which takes
    two agreeing turns, or one turn the model was very sure about. Until then the
    shift is a "blip".
    """

    def __init__(self, evidence_weight: float = EVIDENCE_WEIGHT):
        self._evidence_weight = evidence_weight
        self._turn = 0
        self._belief: dict[str, list[float]] = {}
        self._level: dict[str, str] = {}
        self._since: dict[str, int] = {}  # turn the current level was confirmed

    def update(self, readings: dict[str, Reading], weight: float = 1.0) -> dict:
        """Fold in one turn of readings and return a snapshot for the tutor and UI.

        `weight` from 0 to 1 says how much this turn's audio can tell, for example
        lower for a one-word answer. It scales how far the readings move the belief.
        """
        self._turn += 1
        dims = {}
        for name, reading in readings.items():
            likelihood = _likelihood(reading)
            seen = level_of(reading.value)
            if name not in self._belief:
                belief = _fold([1 / LEVELS] * LEVELS, likelihood, 1.0)
                self._belief[name] = belief
                self._level[name] = max(_bands(belief), key=_bands(belief).get)
                self._since[name] = self._turn
                status = "steady"
            else:
                stay = PERSISTENCE.get(name, _DEFAULT_PERSISTENCE)
                prior = _predict(self._belief[name], stay)
                strength = self._evidence_weight * max(0.0, min(1.0, weight))
                if reading.confidence >= STRONG_CONFIDENCE and seen != self._level[name]:
                    strength = max(strength, 1.0)  # one very sure reading may move the level
                self._belief[name] = _fold(prior, likelihood, strength)
                status = self._confirm(name, seen, reading.confidence)
            bands = _bands(self._belief[name])
            level = self._level[name]
            dims[name] = {
                "estimate": round(
                    sum(lv * p for lv, p in enumerate(self._belief[name])) / (LEVELS - 1), 3
                ),
                "level": level,
                "status": status,
                "reading": round(reading.value, 3),
                "seen": seen,  # the band `confidence` is about
                "confidence": round(reading.confidence, 3),
                # Added: how sure the tracker is of `level`, the whole spread, and how
                # many turns in a row the level has held (1 on the turn it changed).
                "certainty": round(bands[level], 3),
                "bands": {b: round(p, 3) for b, p in bands.items()},
                "turns_at_level": self._turn - self._since[name] + 1,
            }
        return {"turn": self._turn, "dimensions": dims}

    def _confirm(self, name: str, seen: str, confidence: float) -> str:
        bands = _bands(self._belief[name])
        best = max(bands, key=bands.get)
        current = self._level[name]
        if best != current and (
            bands[best] >= SWITCH_AT
            # Most of the probability, and this turn agrees: two turns in a row.
            or (bands[best] >= MAJORITY and best == seen)
            or (confidence >= STRONG_CONFIDENCE and best == seen)
            # The old level is no longer believable, even if no one band has won.
            or bands[current] < LEAST_BELIEVABLE
        ):
            self._level[name] = best
            self._since[name] = self._turn
            return "trend"
        if seen != self._level[name]:
            return "blip"
        return "steady"


# The learning-centred states that BROMP observers code, and that D'Mello and
# Graesser (2012) and Baker et al. (2010) track. "neutral" covers turns with no
# clear affect.
LEARNING_STATES = ("engaged", "confused", "frustrated", "bored", "neutral")

# Chance of staying in each state from one turn to the next. Boredom persisted most in
# Baker et al. (2010) and frustration less. Our numbers, ordered by that finding.
_STATE_PERSISTENCE = {
    "engaged": 0.80,
    "confused": 0.75,
    "frustrated": 0.65,
    "bored": 0.85,
    "neutral": 0.70,
}
# Moves the D'Mello and Graesser (2012) model predicts, weighted double when the
# state does change: engaged <-> confused, confused -> frustrated, frustrated ->
# confused, frustrated -> bored, bored -> frustrated (their time series confirmed
# confusion-engagement, confusion-frustration and boredom-frustration oscillations).
_LIKELY_MOVES = {
    ("engaged", "confused"),
    ("confused", "engaged"),
    ("confused", "frustrated"),
    ("frustrated", "confused"),
    ("frustrated", "bored"),
    ("bored", "frustrated"),
}


def _state_transition(src: str, dst: str) -> float:
    stay = _STATE_PERSISTENCE[src]
    if src == dst:
        return stay
    weights = {d: (2.0 if (src, d) in _LIKELY_MOVES else 1.0) for d in LEARNING_STATES if d != src}
    return (1 - stay) * weights[dst] / sum(weights.values())


# Five states share the probability, so the bar for a change is lower than SWITCH_AT.
STATE_SWITCH_AT = 0.5


class LearningStateTracker:
    """Smooths one categorical reading per turn: which learning state the student is in."""

    def __init__(self, evidence_weight: float = EVIDENCE_WEIGHT):
        self._evidence_weight = evidence_weight
        self._belief: dict[str, float] | None = None
        self._state: str | None = None
        self._since = 0
        self._turn = 0

    def update(self, probabilities: dict[str, float], weight: float = 1.0) -> dict | None:
        """Fold in this turn's probabilities. Returns None if there were none to use."""
        seen = {s: max(0.0, float(probabilities.get(s, 0.0))) for s in LEARNING_STATES}
        if sum(seen.values()) <= 0:
            return None
        seen = dict(zip(LEARNING_STATES, _normalise(list(seen.values()))))
        self._turn += 1
        if self._belief is None:
            prior, strength = dict.fromkeys(LEARNING_STATES, 1 / len(LEARNING_STATES)), 1.0
        else:
            prior = {
                d: sum(self._belief[s] * _state_transition(s, d) for s in LEARNING_STATES)
                for d in LEARNING_STATES
            }
            strength = self._evidence_weight * max(0.0, min(1.0, weight))
        post = [prior[s] * max(seen[s], _FLOOR) ** strength for s in LEARNING_STATES]
        self._belief = dict(zip(LEARNING_STATES, _normalise(post)))
        best = max(self._belief, key=self._belief.get)
        if self._state is None or (best != self._state and self._belief[best] >= STATE_SWITCH_AT):
            if best != self._state:
                self._since = self._turn
            self._state = best
        reading = max(seen, key=seen.get)
        return {
            "state": self._state,
            "certainty": round(self._belief[self._state], 3),
            "distribution": {s: round(p, 3) for s, p in self._belief.items()},
            "reading": reading,  # this turn alone
            "reading_confidence": round(seen[reading], 3),
            "turns": self._turn - self._since + 1,
        }


# Confusion is useful while the student is working through it and then resolves it
# (D'Mello, Lehman, Pekrun and Graesser, doi:10.1016/j.learninstruc.2012.05.003),
# and becomes a problem when it lasts. After this many turns we say so.
LONG_CONFUSION_TURNS = 3


def describe(snapshot: dict) -> str:
    """One short line for the tutor model."""
    parts = []
    for name, d in snapshot["dimensions"].items():
        part = f"{name} {d['level']}"
        if d["status"] == "trend":
            part += " (just changed)"
        elif d["status"] == "blip":
            part += f" (blip: one turn read {d['seen']})"
        elif (
            name == "confusion"
            and d["level"] == "high"
            and d.get("turns_at_level", 0) >= LONG_CONFUSION_TURNS
        ):
            part += f" (for {d['turns_at_level']} turns)"
        if d.get("certainty") is not None and d["certainty"] < 0.5:
            part += " (unsure)"
        parts.append(part)
    line = f"Student state, turn {snapshot['turn']}, estimate only: " + ", ".join(parts)
    learning = snapshot.get("learning_state")
    if learning and learning.get("certainty", 0) >= 0.5:
        line += f". Overall the student sounds {learning['state']}"
    return line + "."
