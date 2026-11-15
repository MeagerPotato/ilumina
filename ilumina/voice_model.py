"""A word-blind voice emotion model, and what its reading means for tutoring.

The model only sees acoustic features (`ilumina.acoustic`), never words. It is a
multinomial logistic regression trained on CREMA-D (Cao et al. 2014): 91 actors
saying the same neutral sentences in each emotion, so it can only learn how an
emotion sounds. It knows the five emotions that matter for tutoring (angry, fearful,
happy, neutral, sad); CREMA-D's disgust clips are left out.
`scripts/train_voice_model.py` builds `voice_model.json` and records its accuracy on
speakers it never saw.

Each feature is compared with this student's own usual voice before the model reads
it (`SpeakerNormaliser`). That one step was worth 9 points of accuracy in our tests,
in line with the speaker-normalised features of the uncertainty studies.

The acted emotions are not tutoring states, so they are turned into evidence
through the control-value theory of achievement emotions (Pekrun 2006), which sorts
learning emotions by valence and activation:
- frustration and anger are negative and activating: a voice angrier than usual
  raises frustration;
- boredom is negative and deactivating: a voice flatter than usual (the neutral and
  sad profiles) lowers engagement;
- anxiety and hopelessness come with low perceived control: a voice more fearful or
  sad than usual lowers confidence.
The evidence is a likelihood ratio against the student's usual voice, so a turn that
sounds like them changes nothing. Confusion has no acoustic profile in CREMA-D, so the
model gives no evidence about it.
"""

import json
from functools import cache
from pathlib import Path

import numpy as np

from ilumina.acoustic import FEATURES

MODEL_PATH = Path(__file__).with_name("voice_model.json")
EMOTIONS = ("angry", "fearful", "happy", "neutral", "sad")

# Turns of this student needed before their usual counts as much as the population's.
PRIOR_TURNS = 3
# Out-of-domain safety: acted speech is more extreme than a student's, so one turn's
# evidence is capped at this likelihood ratio either way.
MAX_RATIO = 6.0

# (tutoring dimension, emotions whose share is the cue, level the cue points away from)
# Levels run 0..4 as in the rubrics. The likelihood of level L is ratio ** ((L - pivot) / 4)
# with the sign set so a stronger cue favours the end named here.
CUES = {
    "frustration": (("angry",), "high"),
    "engagement": (("neutral", "sad"), "low"),
    "confidence": (("fearful", "sad"), "low"),
}


@cache
def _load() -> dict | None:
    try:
        return json.loads(MODEL_PATH.read_text())
    except (OSError, ValueError):
        return None


class SpeakerNormaliser:
    """Turns raw features into z-scores against this student's usual voice.

    Before the student has spoken, the usual is the training population's. Each turn
    moves it toward the student's own mean and spread, counting the population as
    PRIOR_TURNS turns, so one odd first turn cannot set the usual.
    """

    def __init__(self, population_mean, population_std, prior_turns: int = PRIOR_TURNS):
        self._mu0 = np.asarray(population_mean, dtype=float)
        self._var0 = np.asarray(population_std, dtype=float) ** 2
        self._k = prior_turns
        self._n = 0
        self._sum = np.zeros_like(self._mu0)
        self._sumsq = np.zeros_like(self._mu0)

    @property
    def turns(self) -> int:
        return self._n

    def z(self, x: np.ndarray) -> np.ndarray:
        n, k = self._n, self._k
        mu = (self._sum + k * self._mu0) / (n + k)
        # Spread around the blended mean: the student's own squared deviations plus the
        # population's variance counted as k turns.
        own = self._sumsq - 2 * mu * self._sum + n * mu**2
        var = (own + k * self._var0) / (n + k)
        return (x - mu) / np.sqrt(np.maximum(var, 1e-12))

    def learn(self, x: np.ndarray):
        self._n += 1
        self._sum += x
        self._sumsq += x**2


def _softmax(logits: np.ndarray) -> np.ndarray:
    e = np.exp(logits - logits.max())
    return e / e.sum()


class VoiceModel:
    """Reads one turn's acoustic features against the student's usual. One per session."""

    def __init__(self, params: dict | None = None):
        params = params or _load()
        if not params:
            raise FileNotFoundError(f"voice model weights not found at {MODEL_PATH}")
        self._features = params["features"]
        if tuple(self._features) != FEATURES:
            raise ValueError("voice model was trained on a different feature list")
        self._scale_mean = np.asarray(params["scaler_mean"])
        self._scale_std = np.asarray(params["scaler_std"])
        self._coef = np.asarray(params["coef"])
        self._intercept = np.asarray(params["intercept"])
        self._emotions = tuple(params["classes"])
        self._normaliser = SpeakerNormaliser(params["population_mean"], params["population_std"])
        # What the model hears in this student's usual voice (z = 0 for every feature).
        self._usual = self._probabilities(np.zeros(len(self._features)))

    def _probabilities(self, z: np.ndarray) -> np.ndarray:
        scaled = (z - self._scale_mean) / self._scale_std
        return _softmax(self._coef @ scaled + self._intercept)

    def read(self, features: dict[str, float]) -> dict:
        """This turn's reading, then the turn is added to the student's usual.

        Returns the emotion probabilities, each cue's change from the usual voice
        as a likelihood ratio, and how much the usual can be trusted yet (0 to 1).
        """
        x = np.array([features[name] for name in self._features], dtype=float)
        p = self._probabilities(self._normaliser.z(x))
        maturity = self._normaliser.turns / (self._normaliser.turns + PRIOR_TURNS)
        self._normaliser.learn(x)
        ratios = {}
        for dim, (emotions, _) in CUES.items():
            idx = [self._emotions.index(e) for e in emotions]
            share, usual = float(p[idx].sum()), float(self._usual[idx].sum())
            odds = share / max(1 - share, 1e-6)
            usual_odds = usual / max(1 - usual, 1e-6)
            ratios[dim] = float(np.clip(odds / usual_odds, 1 / MAX_RATIO, MAX_RATIO))
        return {
            "emotions": {e: round(float(v), 3) for e, v in zip(self._emotions, p)},
            "ratios": {d: round(r, 3) for d, r in ratios.items()},
            "maturity": round(maturity, 3),
        }


def likelihood(dimension: str, ratio: float, levels: int = 5) -> list[float] | None:
    """The cue for one dimension as a likelihood over its rubric levels, or None.

    A ratio of 1 (sounds like their usual) gives a flat likelihood, which changes nothing.
    """
    if dimension not in CUES:
        return None
    _, end = CUES[dimension]
    top = levels - 1
    out = []
    for level in range(levels):
        toward = level if end == "high" else top - level  # 0..top, larger is the cue's end
        out.append(ratio ** ((toward - top / 2) / top))
    return out
