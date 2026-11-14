"""Pipecat processors: state note into the tutor, teaching move out of the tutor."""

import asyncio

from pipecat.frames.frames import (
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.state import describe


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

    @staticmethod
    def _answers_student(frame: LLMContextFrame) -> bool:
        """True when the reply is to something the student just said (not the greeting)."""
        messages = frame.context.get_messages()
        return bool(messages) and messages[-1].get("role") == "user"

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if (
            isinstance(frame, LLMContextFrame)
            and not frame.speculation
            and self._answers_student(frame)
        ):
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
