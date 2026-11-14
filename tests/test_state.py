import asyncio
from types import SimpleNamespace

import pytest

from ilumina.emotion import (
    LEARNING_STATE_QUESTION,
    RUBRICS,
    build_questions,
    parse_answers,
    parse_learning_state,
    score_turn,
)
from ilumina.state import (
    LONG_CONFUSION_TURNS,
    LearningStateTracker,
    Reading,
    StateTracker,
    describe,
    level_of,
)


def turn(tracker, value, confidence=0.6):
    return tracker.update({"confusion": Reading(value, confidence)})["dimensions"]["confusion"]


def test_single_odd_turn_is_a_blip_and_level_holds():
    t = StateTracker()
    assert turn(t, 0.1)["level"] == "low"
    d = turn(t, 0.9)
    assert d["status"] == "blip" and d["level"] == "low"
    d = turn(t, 0.1)
    assert d["status"] == "steady" and d["level"] == "low"


def test_two_turns_in_a_row_make_a_trend():
    t = StateTracker()
    turn(t, 0.1)
    turn(t, 0.9)
    d = turn(t, 0.8)
    assert d["status"] == "trend" and d["level"] == "high"


def test_one_very_confident_reading_changes_level_at_once():
    t = StateTracker()
    turn(t, 0.1)
    d = turn(t, 0.9, confidence=0.9)
    assert d["status"] == "trend" and d["level"] == "high"


def test_mixed_readings_away_from_level_follow_the_estimate():
    t = StateTracker()
    turn(t, 0.1)
    assert turn(t, 0.9)["status"] == "blip"
    d = turn(t, 0.5)
    assert d["status"] == "trend" and d["level"] != "low"


def test_low_confidence_moves_the_estimate_less():
    sure, unsure = StateTracker(), StateTracker()
    turn(sure, 0.0)
    turn(unsure, 0.0)
    assert turn(sure, 1.0, 0.8)["estimate"] > turn(unsure, 1.0, 0.2)["estimate"]


def test_describe_marks_blips_for_the_tutor():
    t = StateTracker()
    turn(t, 0.1)
    snapshot = t.update({"confusion": Reading(0.9, 0.5)})
    text = describe(snapshot)
    assert "confusion low" in text and "blip" in text and "turn 2" in text


def test_questions_and_answer_parsing():
    questions = build_questions()
    assert set(questions) == set(RUBRICS) | {LEARNING_STATE_QUESTION}
    scores = [q for name, q in questions.items() if name in RUBRICS]
    assert all(q["type"] == "score" and len(q["criteria"]) == 5 for q in scores)
    assert questions[LEARNING_STATE_QUESTION]["type"] == "choice"
    answers = {
        "confusion": SimpleNamespace(type="score", score=3.0, confidence=0.7),
        "frustration": SimpleNamespace(type="unknown"),
    }
    readings = parse_answers(answers)
    assert readings == {"confusion": Reading(0.75, 0.7)}


def test_confidence_is_the_chance_of_the_band_not_of_one_rubric_level():
    # Shaped like turn 6 of the first live session: the model split its vote between
    # "confused" and "lost", so its own confidence (the top level alone) read 38%.
    answer = SimpleNamespace(
        type="score",
        score=2.918,
        confidence=0.382,
        probabilities={"0": 0.0, "1": 0.1, "2": 0.2, "3": 0.382, "4": 0.318},
    )
    reading = parse_answers({"confusion": answer})["confusion"]
    assert level_of(reading.value) == "high"
    assert reading.confidence == pytest.approx(0.7)


def test_a_vote_split_across_bands_stays_unsure():
    answer = SimpleNamespace(
        type="score",
        score=2.0,
        confidence=0.5,
        probabilities={"0": 0.5, "4": 0.5},
    )
    assert parse_answers({"confusion": answer})["confusion"].confidence == 0


def test_one_sure_reading_carries_the_estimate_into_the_new_level():
    t = StateTracker()
    turn(t, 0.1)
    d = turn(t, 0.9, confidence=0.9)
    assert d["level"] == "high" and d["estimate"] >= 0.65


def test_fairly_sure_readings_that_disagree_do_not_flip_the_level_each_turn():
    t = StateTracker()
    turn(t, 0.2, confidence=0.75)
    for _ in range(2):
        d = turn(t, 0.72, confidence=0.7)
        assert d["status"] == "blip" and d["level"] == "low" and d["seen"] == "high"
        d = turn(t, 0.2, confidence=0.75)
        assert d["status"] == "steady" and d["level"] == "low"


def test_unreadable_probability_keys_fall_back_to_the_api_confidence():
    answer = SimpleNamespace(
        type="score", score=3.0, confidence=0.6, probabilities={"level-3": 1.0}
    )
    assert parse_answers({"confusion": answer})["confusion"].confidence == 0.6


def test_the_scorer_gets_the_voice_and_the_conversation_and_is_told_to_weigh_both():
    sent = {}

    async def create(**kwargs):
        sent.update(kwargs)
        return SimpleNamespace(answers={})

    client = SimpleNamespace(aio=SimpleNamespace(decisions=SimpleNamespace(create=create)))
    talk = "Tutor: What is 3x when x is 4?\nStudent: um, seven?"
    asyncio.run(score_turn(client, "gemini-decision-1", b"RIFF", talk))

    text, audio = sent["input"]
    assert text["type"] == "text" and talk in text["text"]
    assert audio["type"] == "audio" and audio["mime_type"] == "audio/wav"
    for question in sent["questions"].values():
        assert "how they sound" in question["instructions"]
        assert "what they say" in question["instructions"]


def probs(*levels: float) -> Reading:
    """A reading shaped like Decision 1's, from its five level probabilities."""
    value = sum(i * p for i, p in enumerate(levels)) / 4
    return Reading(value, max(levels), tuple(levels))


def test_the_api_level_probabilities_are_kept_for_the_tracker():
    answer = SimpleNamespace(
        type="score", score=3.0, confidence=0.6,
        probabilities={"0": 0.0, "1": 0.0, "2": 0.2, "3": 0.6, "4": 0.2},
    )  # fmt: skip
    reading = parse_answers({"confusion": answer})["confusion"]
    assert reading.probabilities == (0.0, 0.0, 0.2, 0.6, 0.2)


def test_the_tracker_reports_how_sure_it_is_and_how_long_a_level_has_held():
    t = StateTracker()
    first = t.update({"confusion": probs(0.0, 0.05, 0.05, 0.6, 0.3)})["dimensions"]["confusion"]
    assert first["level"] == "high" and first["turns_at_level"] == 1
    assert set(first["bands"]) == {"low", "medium", "high"}
    assert abs(sum(first["bands"].values()) - 1) < 0.01
    assert first["certainty"] == first["bands"]["high"]
    for _ in range(2):
        d = t.update({"confusion": probs(0.0, 0.05, 0.05, 0.6, 0.3)})["dimensions"]["confusion"]
    assert d["turns_at_level"] == 3 and d["certainty"] > first["certainty"]


def test_a_one_word_turn_moves_the_estimate_less():
    full, short = StateTracker(), StateTracker()
    for t in (full, short):
        t.update({"confusion": probs(0.7, 0.2, 0.1, 0.0, 0.0)})
    high = {"confusion": probs(0.0, 0.0, 0.1, 0.5, 0.4)}
    assert (
        full.update(high)["dimensions"]["confusion"]["estimate"]
        > short.update(high, weight=0.5)["dimensions"]["confusion"]["estimate"]
    )


def test_frustration_fades_faster_than_low_engagement_persists():
    # Baker et al. (2010): boredom persisted most, frustration less.
    t = StateTracker()
    t.update({"frustration": probs(0, 0, 0, 0.2, 0.8), "engagement": probs(0.8, 0.2, 0, 0, 0)})
    unsure = Reading(0.5, 0.2, (0.2, 0.2, 0.2, 0.2, 0.2))  # a turn that says nothing
    d = t.update({"frustration": unsure, "engagement": unsure})["dimensions"]
    assert d["frustration"]["bands"]["high"] < d["engagement"]["bands"]["low"]


def test_describe_flags_long_confusion_and_unsure_levels():
    t = StateTracker()
    for _ in range(LONG_CONFUSION_TURNS):
        snapshot = t.update({"confusion": probs(0, 0, 0.05, 0.55, 0.4)})
    assert f"confusion high (for {LONG_CONFUSION_TURNS} turns)" in describe(snapshot)
    split = StateTracker().update({"engagement": probs(0.3, 0.15, 0.2, 0.15, 0.2)})
    assert "(unsure)" in describe(split)


def test_learning_state_is_smoothed_and_one_odd_turn_does_not_flip_it():
    t = LearningStateTracker()
    engaged = {"engaged": 0.7, "confused": 0.1, "frustrated": 0.05, "bored": 0.05, "neutral": 0.1}
    bored = {"engaged": 0.1, "confused": 0.05, "frustrated": 0.05, "bored": 0.7, "neutral": 0.1}
    assert t.update(engaged)["state"] == "engaged"
    t.update(engaged)
    odd = t.update(bored)
    assert odd["state"] == "engaged" and odd["reading"] == "bored"
    assert t.update(bored)["state"] == "bored"
    assert t.update({}) is None


def test_learning_state_parsing_and_the_tutor_note():
    answer = SimpleNamespace(
        type="choice", choice="confused", confidence=0.6,
        probabilities={"confused": 0.6, "engaged": 0.3, "neutral": 0.1},
    )  # fmt: skip
    parsed = parse_learning_state({LEARNING_STATE_QUESTION: answer})
    assert parsed["confused"] == 0.6 and parsed["bored"] == 0.0
    assert parse_learning_state({}) is None
    snapshot = StateTracker().update({"confusion": probs(0, 0, 0.1, 0.6, 0.3)})
    snapshot["learning_state"] = LearningStateTracker().update(parsed)
    assert describe(snapshot).endswith("Overall the student sounds confused.")
