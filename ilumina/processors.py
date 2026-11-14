"""Pipecat processors: camera view and state note into the tutor, teaching move out."""

import asyncio
import time

from loguru import logger
from pipecat.frames.frames import (
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    UserImageRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.prompts import CAMERA_NOTE
from ilumina.state import describe

# A camera frame older than this is not shown to the tutor (camera off or stalled).
_MAX_FRAME_AGE_SECONDS = 3.0


def _answers_student(frame: Frame) -> bool:
    """True when the tutor is about to answer something the student just said."""
    if not isinstance(frame, LLMContextFrame) or frame.speculation:
        return False
    messages = frame.context.get_messages()
    return bool(messages) and messages[-1].get("role") == "user"


class CameraView(FrameProcessor):
    """Sits before the LLM and shows the tutor what the student's camera sees.

    It keeps only the newest camera frame. When a student turn is about to be
    answered, that one frame is added to the context, replacing the frame from
    the previous turn. Nothing is saved. With the camera off, or if anything
    here fails, the tutor simply answers without a picture.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._latest: UserImageRawFrame | None = None
        self._latest_at = 0.0
        self._shown: dict | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserImageRawFrame):
            self._latest = frame
            self._latest_at = time.monotonic()
            return  # nothing after this needs the raw camera frames
        if _answers_student(frame):
            try:
                seen = await self._show(frame.context)
            except Exception as e:  # noqa: BLE001 - a camera problem must not stop the voice loop
                logger.warning(f"Camera frame not shown, tutor continues without it: {e}")
                seen = False
            await self.push_frame(
                RTVIServerMessageFrame(data={"type": "camera_view", "seen": seen})
            )
        await self.push_frame(frame, direction)

    async def _show(self, context) -> bool:
        if self._shown is not None:
            context.set_messages([m for m in context.get_messages() if m is not self._shown])
            self._shown = None
        frame = self._latest
        if frame is None or time.monotonic() - self._latest_at > _MAX_FRAME_AGE_SECONDS:
            return False
        await context.add_image_frame_message(
            format=frame.format, size=frame.size, image=frame.image, text=CAMERA_NOTE
        )
        self._shown = context.get_messages()[-1]
        return True


class StudentStateInjector(FrameProcessor):
    """Sits right before the LLM.

    When a student turn is about to be answered, it waits briefly for that
    turn's emotion reading, then adds a one-line state note to the context.
    If the reading is late or missing, the tutor answers without a new note,
    so voice never blocks on emotion.
    """

    def __init__(self, wait_seconds: float, **kwargs):
        super().__init__(**kwargs)
        self._wait_seconds = wait_seconds
        self._fresh = asyncio.Event()
        self._snapshot: dict | None = None

    def set_snapshot(self, snapshot: dict):
        self._snapshot = snapshot
        self._fresh.set()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if _answers_student(frame):
            try:
                await asyncio.wait_for(self._fresh.wait(), self._wait_seconds)
            except TimeoutError:
                pass
            if self._fresh.is_set() and self._snapshot:
                frame.context.add_message(
                    {"role": "developer", "content": describe(self._snapshot)}
                )
                self._fresh.clear()
        await self.push_frame(frame, direction)


# Longest opening we will hold back while looking for a move tag.
_MAX_TAG_CHARS = 48


class TeachingMoveTagger(FrameProcessor):
    """Sits right after the LLM.

    The tutor starts each reply with a tag such as ``[move: smaller_hint]``.
    This removes the tag before it is spoken and reports the move to the
    dashboard. A reply with no tag passes through untouched.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._held: str | None = None  # None means we are not looking for a tag

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMFullResponseStartFrame):
            self._held = ""
        elif isinstance(frame, LLMTextFrame) and self._held is not None:
            self._held += frame.text
            text = self._held.lstrip()
            if text.startswith("[") and "]" in text:
                tag, _, rest = text[1:].partition("]")
                move = tag.removeprefix("move:").strip().lower()
                await self.push_frame(
                    RTVIServerMessageFrame(data={"type": "teaching_move", "move": move})
                )
                text = rest.lstrip()
            elif not text or (text.startswith("[") and len(text) < _MAX_TAG_CHARS):
                return  # keep holding until the tag closes or clearly is not one
            self._held = None
            if not text:
                return
            frame.text = text
        elif isinstance(frame, LLMFullResponseEndFrame) and self._held:
            # The reply ended while we were still holding text. Speak it.
            await self.push_frame(LLMTextFrame(self._held), direction)
            self._held = None
        await self.push_frame(frame, direction)
