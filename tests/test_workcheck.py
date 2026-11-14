import asyncio
import time
from types import SimpleNamespace

from pipecat.frames.frames import LLMContextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.processors import CameraView, StudentStateInjector
from ilumina.workcheck import QUESTIONS, build_questions, check_work, describe, parse_answers


def answer(choice: str, confidence: float):
    return SimpleNamespace(type="choice", choice=choice, confidence=confidence)


MISTAKE = {
    "verdict": answer("mistake", 0.82),
    "kind": answer("slip", 0.64),
    "place": answer("working", 0.71),
    "fix": answer("redo_line", 0.58),
}


def test_every_question_is_a_choice_the_api_accepts():
    questions = build_questions()
    assert set(questions) == {"verdict", "kind", "place", "fix"}
    for question in questions.values():
        assert question["type"] == "choice"
        assert 2 <= len(question["criteria"]) <= 255
        assert all(option == option.strip() and option for option in question["criteria"])


def test_a_mistake_is_described_with_what_where_and_the_fix():
    check = parse_answers(MISTAKE)
    assert check["kind"] == {"choice": "slip", "label": "a small slip", "sure": 0.64}
    note = describe(check)
    assert note.startswith("Work check on the student's newest turn, estimate only: ")
    assert "probably a mistake (82%)" in note
    assert "likely a small slip (64%)" in note
    assert "in carrying out the steps (71%)" in note
    assert "have the student redo one line of the working (58%)" in note


def test_correct_work_gets_a_short_note_and_no_work_gets_none():
    correct = parse_answers({**MISTAKE, "verdict": answer("correct", 0.9)})
    assert describe(correct).endswith("estimate only: looks correct (90%).")
    nothing = parse_answers({**MISTAKE, "verdict": answer("nothing", 0.7)})
    assert describe(nothing) == ""


def test_a_late_check_says_which_turn_it_is_about():
    note = describe(parse_answers(MISTAKE), "previous")
    assert "the student's previous turn (it arrived after you answered that turn)" in note


def test_answers_the_model_should_not_give_are_left_out():
    assert parse_answers({}) is None
    assert parse_answers({"kind": answer("slip", 0.6)}) is None  # no verdict, no check
    odd = parse_answers({**MISTAKE, "kind": answer("made_up", 0.9), "place": None})
    assert set(odd) == {"verdict", "fix"}
    assert "probably a mistake (82%). Suggested" in describe(odd)
    scored = SimpleNamespace(type="score", score=3, confidence=0.9)
    assert parse_answers({"verdict": scored}) is None


def test_every_option_has_plain_words_for_the_dashboard():
    for _, options in QUESTIONS.values():
        assert all(label and meaning for label, meaning in options.values())


class FakeDecisions:
    def __init__(self):
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(answers=MISTAKE)


def test_the_picture_is_sent_only_when_there_is_one():
    decisions = FakeDecisions()
    client = SimpleNamespace(aio=SimpleNamespace(decisions=decisions))

    async def go():
        await check_work(client, "model", b"wav", "Tutor: What is 2 plus 2?")
        return await check_work(client, "model", b"wav", "Tutor: What is 2 plus 2?", b"jpeg")

    check = asyncio.run(go())
    assert check["verdict"]["choice"] == "mistake"
    without, with_picture = ([part["type"] for part in call["input"]] for call in decisions.calls)
    assert without == ["text", "audio"]
    assert with_picture == ["text", "audio", "text", "image"]
    assert decisions.calls[1]["api_version"] == "v1beta"


def test_the_camera_picture_becomes_a_jpeg():
    view = CameraView()
    assert view.jpeg() is None  # camera off
    view._latest = SimpleNamespace(image=bytes(4 * 4 * 3), size=(4, 4), format="RGB")
    view._latest_at = time.monotonic()
    assert view.jpeg()[:2] == b"\xff\xd8"


def run_turns(steps: list, expect_work_check: bool = True) -> tuple[list[str], list[str]]:
    """Feed student turns through the injector. A callable step runs first with the injector.

    Returns (the developer notes added per turn, joined, and what the dashboard was told).
    """

    async def go():
        injector = StudentStateInjector(wait_seconds=0.05, expect_work_check=expect_work_check)
        told = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            if isinstance(frame, RTVIServerMessageFrame):
                told.append(frame.data["which"])

        injector.push_frame = capture
        notes = []
        for step in steps:
            if callable(step):
                step(injector)
                continue
            context = LLMContext()
            context.add_message({"role": "user", "content": step})
            frame = LLMContextFrame(context=context)
            await StudentStateInjector.process_frame(injector, frame, FrameDirection.DOWNSTREAM)
            notes.append(
                " ".join(m["content"] for m in context.get_messages() if m["role"] == "developer")
            )
        return notes, told

    return asyncio.run(go())


def a_check_arrives(injector):
    injector.set_work_check(parse_answers(MISTAKE), time.monotonic())


def test_a_check_that_is_in_time_goes_with_its_own_turn():
    notes, told = run_turns([a_check_arrives, "it is five"])
    assert "student's newest turn" in notes[0]
    assert told == ["newest"]


def test_a_check_that_is_late_goes_with_the_next_turn_and_says_so():
    started = time.monotonic()

    def late(injector):  # the first turn's check finishes after that turn was answered
        injector.set_work_check(parse_answers(MISTAKE), started)

    notes, told = run_turns(["it is five", late, "oh wait"])
    assert notes[0] == ""
    assert "student's previous turn" in notes[1]
    assert told == ["previous"]


def test_a_check_is_given_once_and_an_older_one_never_replaces_a_newer_one():
    started = time.monotonic()

    def older(injector):
        a_check_arrives(injector)
        injector.set_work_check(
            parse_answers({**MISTAKE, "verdict": answer("correct", 0.9)}), started
        )

    notes, told = run_turns([older, "it is five", "next one"])
    assert "probably a mistake" in notes[0]
    assert notes[1] == ""
    assert told == ["newest"]


def test_nothing_to_check_tells_the_tutor_nothing():
    def nothing(injector):
        check = parse_answers({**MISTAKE, "verdict": answer("nothing", 0.8)})
        injector.set_work_check(check, time.monotonic())

    notes, told = run_turns([nothing, "what is a derivative"])
    assert notes == [""] and told == []
