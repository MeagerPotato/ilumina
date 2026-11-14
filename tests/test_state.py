from types import SimpleNamespace

from ilumina.emotion import RUBRICS, build_questions, parse_answers
from ilumina.state import Reading, StateTracker, describe


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
    assert set(questions) == set(RUBRICS)
    assert all(q["type"] == "score" and len(q["criteria"]) == 5 for q in questions.values())
    answers = {"confusion": SimpleNamespace(score=3.0, confidence=0.7)}
    readings = parse_answers(answers)
    assert readings == {"confusion": Reading(0.75, 0.7)}
