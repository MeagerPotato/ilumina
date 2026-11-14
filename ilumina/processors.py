"""Pipecat processor that hands the latest student state to the tutor model."""

import asyncio

from pipecat.frames.frames import Frame, LLMContextFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

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

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, LLMContextFrame) and not frame.speculation:
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
