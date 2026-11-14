import asyncio

from pipecat.frames.frames import LLMContextFrame, UserImageRawFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina import processors
from ilumina.processors import CameraView


def camera_frame() -> UserImageRawFrame:
    return UserImageRawFrame(image=bytes(4 * 4 * 3), size=(4, 4), format="RGB")


def images_in(context: LLMContext) -> int:
    return sum(
        1
        for message in context.get_messages()
        if isinstance(message.get("content"), list)
        and any(part.get("type") == "image_url" for part in message["content"])
    )


def run(steps: list) -> tuple[LLMContext, list[bool], list]:
    """Feed frames (or callables that return one) through a CameraView.

    Returns (context, the `seen` value reported per student turn, frames passed on).
    """

    async def go():
        view = CameraView()
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        view.push_frame = capture
        context = LLMContext()
        for step in steps:
            frame = step(context) if callable(step) else step
            await CameraView.process_frame(view, frame, FrameDirection.DOWNSTREAM)
        seen = [f.data["seen"] for f in out if isinstance(f, RTVIServerMessageFrame)]
        return context, seen, out

    return asyncio.run(go())


def student_turn(text: str):
    def step(context: LLMContext) -> LLMContextFrame:
        context.add_message({"role": "user", "content": text})
        return LLMContextFrame(context=context)

    return step


def test_newest_frame_is_shown_with_a_student_turn():
    context, seen, out = run([camera_frame(), student_turn("I am stuck on this one")])
    assert seen == [True]
    assert images_in(context) == 1
    assert not any(isinstance(f, UserImageRawFrame) for f in out)


def test_each_turn_replaces_the_previous_picture():
    context, seen, _ = run(
        [camera_frame(), student_turn("first"), camera_frame(), student_turn("second")]
    )
    assert seen == [True, True]
    assert images_in(context) == 1
    assert context.get_messages()[-1]["content"][-1]["type"] == "image_url"


def test_no_camera_means_no_picture_and_the_turn_still_goes_through():
    context, seen, out = run([student_turn("hello")])
    assert seen == [False]
    assert images_in(context) == 0
    assert any(isinstance(f, LLMContextFrame) for f in out)


def test_a_stale_frame_is_not_shown_and_the_old_picture_is_removed(monkeypatch):
    def later_turn(context: LLMContext) -> LLMContextFrame:
        # By now every frame counts as too old, as if the camera was switched off.
        monkeypatch.setattr(processors, "_MAX_FRAME_AGE_SECONDS", -1.0)
        return student_turn("second")(context)

    context, seen, _ = run([camera_frame(), student_turn("first"), later_turn])
    assert seen == [True, False]
    assert images_in(context) == 0


def test_the_greeting_gets_no_picture():
    def greeting(context: LLMContext) -> LLMContextFrame:
        context.add_message({"role": "developer", "content": "Greet the student."})
        return LLMContextFrame(context=context)

    context, seen, _ = run([camera_frame(), greeting])
    assert seen == []
    assert images_in(context) == 0


def test_a_reply_that_is_not_to_the_student_drops_the_old_picture():
    def nudge(context: LLMContext) -> LLMContextFrame:
        context.add_message({"role": "developer", "content": "The student went quiet."})
        return LLMContextFrame(context=context)

    context, seen, _ = run([camera_frame(), student_turn("first"), nudge])
    assert seen == [True]
    assert images_in(context) == 0


class FakeHeadCam:
    def __init__(self, picture):
        self._picture = picture

    def picture(self):
        return self._picture


def run_with_headcam(headcam, steps: list) -> tuple[LLMContext, list[bool]]:
    async def go():
        view = CameraView(headcam=headcam)
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        view.push_frame = capture
        context = LLMContext()
        for step in steps:
            frame = step(context) if callable(step) else step
            await CameraView.process_frame(view, frame, FrameDirection.DOWNSTREAM)
        return context, [f.data["seen"] for f in out if isinstance(f, RTVIServerMessageFrame)]

    return asyncio.run(go())


def test_head_camera_picture_is_shown_instead_of_the_browser_camera():
    headcam = FakeHeadCam(("RGB", (4, 4), bytes(4 * 4 * 3)))
    context, seen = run_with_headcam(headcam, [student_turn("what is this one asking?")])
    assert seen == [True]
    assert images_in(context) == 1


def test_head_camera_that_is_off_shows_nothing_even_if_the_browser_sent_a_frame():
    context, seen = run_with_headcam(FakeHeadCam(None), [camera_frame(), student_turn("hello")])
    assert seen == [False]
    assert images_in(context) == 0
