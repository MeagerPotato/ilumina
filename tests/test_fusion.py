import numpy as np
import pytest

from ilumina.acoustic import FEATURES
from ilumina.emotion import Channel
from ilumina.fusion import CHANNEL_WEIGHTS, fuse, fuse_learning
from ilumina.state import LEARNING_STATES, Reading
from ilumina.voice_model import EMOTIONS, SpeakerNormaliser, VoiceModel, likelihood


def reading(*levels: float) -> Reading:
    value = sum(i * p for i, p in enumerate(levels)) / 4
    return Reading(value, max(levels), tuple(levels))


CALM = reading(0.8, 0.15, 0.05, 0.0, 0.0)
UPSET = reading(0.0, 0.0, 0.1, 0.4, 0.5)


def test_the_voice_outweighs_the_words_when_they_disagree():
    # "I'm fine" said through gritted teeth: the words read calm, the voice reads upset.
    channels = {
        "voice": Channel({"frustration": UPSET}, None),
        "words": Channel({"frustration": CALM}, None),
    }
    readings, sources = fuse(channels)
    assert CHANNEL_WEIGHTS["frustration"]["voice"] > CHANNEL_WEIGHTS["frustration"]["words"]
    assert readings["frustration"].value > 0.5
    assert sources["frustration"] == pytest.approx(
        {"voice": UPSET.value, "words": CALM.value}, abs=1e-3
    )


def test_a_missing_channel_leaves_the_other_one_in_charge():
    readings, sources = fuse({"words": Channel({"confusion": UPSET}, None)})
    assert readings["confusion"].probabilities == pytest.approx(UPSET.probabilities, abs=0.02)
    assert set(sources["confusion"]) == {"words"}
    assert fuse({}) == ({}, {})


def test_a_voice_that_sounds_like_usual_changes_nothing():
    channels = {"voice": Channel({"frustration": CALM}, None)}
    alone, _ = fuse(channels)
    same, sources = fuse(channels, {"ratios": {"frustration": 1.0}, "maturity": 1.0})
    assert same["frustration"].value == pytest.approx(alone["frustration"].value)
    assert sources["frustration"]["voice_model"] == 1.0


def test_an_angrier_voice_than_usual_raises_frustration_more_once_the_usual_is_known():
    channels = {"voice": Channel({"frustration": reading(0.3, 0.3, 0.2, 0.1, 0.1)}, None)}
    alone, _ = fuse(channels)
    early, _ = fuse(channels, {"ratios": {"frustration": 4.0}, "maturity": 0.25})
    known, _ = fuse(channels, {"ratios": {"frustration": 4.0}, "maturity": 0.9})
    assert alone["frustration"].value < early["frustration"].value < known["frustration"].value


def test_the_learning_state_is_pooled_toward_the_voice():
    voice = {s: 0.05 for s in LEARNING_STATES} | {"frustrated": 0.8}
    words = {s: 0.05 for s in LEARNING_STATES} | {"neutral": 0.8}
    pooled = fuse_learning({"voice": Channel({}, voice), "words": Channel({}, words)})
    assert max(pooled, key=pooled.get) == "frustrated"
    assert fuse_learning({"voice": Channel({}, None)}) is None


def test_the_voice_model_likelihood_points_the_right_way():
    up = likelihood("frustration", 3.0)
    assert up[4] > up[2] > up[0]
    flat = likelihood("engagement", 3.0)  # the engagement cue is a flatter voice
    assert flat[0] > flat[2] > flat[4]
    assert likelihood("frustration", 1.0) == pytest.approx([1.0] * 5)
    assert likelihood("confusion", 3.0) is None


def test_the_normaliser_starts_at_the_population_and_moves_to_the_student():
    norm = SpeakerNormaliser([0.0, 10.0], [1.0, 2.0], prior_turns=3)
    assert norm.z(np.array([1.0, 10.0])) == pytest.approx([1.0, 0.0])
    # This student's first feature sits around 5 (4 to 6), five population spreads up.
    for i in range(50):
        norm.learn(np.array([4.0 + 2 * (i % 2), 10.0]))
    z = norm.z(np.array([5.0, 10.0]))
    assert abs(z[0]) < 0.5 and norm.turns == 50


def test_the_shipped_voice_model_loads_and_reads_a_turn():
    model = VoiceModel()
    turn = {name: 0.0 for name in FEATURES}
    first = model.read(turn)
    assert set(first["emotions"]) == set(EMOTIONS)
    assert sum(first["emotions"].values()) == pytest.approx(1.0, abs=0.01)
    assert first["maturity"] == 0.0
    assert set(first["ratios"]) == {"frustration", "engagement", "confidence"}
    assert model.read(turn)["maturity"] > 0
