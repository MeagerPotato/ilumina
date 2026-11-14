"""Pipecat processors: voice evidence, camera view and state note in, teaching move out."""

import asyncio
import time

from loguru import logger
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ProposedUserStartedSpeakingFrame,
    TranscriptionFrame,
    UserImageRawFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.evidence import voice_evidence
from ilumina.prompts import CAMERA_NOTE
from ilumina.state import describe

# A camera frame older than this is not shown to the tutor (camera off or stalled).
# Frames arrive about a second apart, so this allows for one late frame.
_MAX_FRAME_AGE_SECONDS = 2.0


def _answers_student(frame: Frame) -> bool:
    """True when the tutor is about to answer something the student just said."""
    if not isinstance(frame, LLMContextFrame) or frame.speculation:
        return False
    messages = frame.context.get_messages()
    last = messages[-1] if messages else None
    return isinstance(last, dict) and last.get("role") == "user"


class CameraView(FrameProcessor):
    """Sits before the LLM and shows the tutor what the student's camera sees.

    It keeps only the newest camera frame. When a student turn is about to be
    answered, that one frame is added to the context, replacing the frame from
    the previous turn. Nothing is saved. With the camera off, or if anything
    here fails, the tutor simply answers without a picture.
    """

    def __init__(self, headcam=None, **kwargs):
        super().__init__(**kwargs)
        self._headcam = headcam  # the head-worn GoPro, when it replaces the browser camera
        self._latest: UserImageRawFrame | None = None
        self._latest_at = 0.0
        self._shown: dict | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserImageRawFrame):
            self._latest = frame
            self._latest_at = time.monotonic()
            # Stop here: passed on, each frame would split the tutor's reply in the context.
            return
        if isinstance(frame, LLMContextFrame) and not frame.speculation:
            self._remove_shown(frame.context)
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

    def _remove_shown(self, context):
        """Take the previous turn's picture out, so no reply sees an old one as current."""
        if self._shown is not None:
            context.set_messages([m for m in context.get_messages() if m is not self._shown])
            self._shown = None

    def _newest(self) -> tuple[str, tuple[int, int], bytes] | None:
        """(format, size, image) of a current picture, or None."""
        if self._headcam is not None:
            return self._headcam.picture()
        frame = self._latest
        if frame is None or time.monotonic() - self._latest_at > _MAX_FRAME_AGE_SECONDS:
            return None
        return frame.format, frame.size, frame.image

    async def _show(self, context) -> bool:
        picture = self._newest()
        if picture is None:
            return False
        format, size, image = picture
        await context.add_image_frame_message(
            format=format, size=size, image=image, text=CAMERA_NOTE
        )
        self._shown = context.get_messages()[-1]
        return True


class VoiceEvidence(FrameProcessor):
    """Sits right after speech to text and measures how each student turn was spoken.

    Deepgram Flux sends word timings with every finished turn. From them, and from how
    long the student waited before answering, this works out the turn's measured
    evidence, reports it to the dashboard, and keeps it for the emotion scorer.
    Every frame passes through untouched, and a failure here never stops the turn.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._tutor_speaking = False
        self._tutor_stopped_at: float | None = None  # set when the tutor finishes by itself
        self._waited: float | None = None
        self._latest: dict | None = None

    def take(self) -> dict | None:
        """The newest turn's evidence, once. A later turn never gets an old one."""
        latest, self._latest = self._latest, None
        return latest

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._tutor_speaking, self._tutor_stopped_at = True, None
        elif isinstance(frame, BotStoppedSpeakingFrame):
            # A stop the student caused (they cut in, so the tutor was no longer
            # counted as speaking) is not the tutor finishing.
            if self._tutor_speaking:
                self._tutor_stopped_at = time.monotonic()
            self._tutor_speaking = False
        elif isinstance(frame, ProposedUserStartedSpeakingFrame):
            # No wait when the student cut the tutor off. One wait per tutor reply:
            # a second student turn in a row has none either.
            self._tutor_speaking = False
            stopped, self._tutor_stopped_at = self._tutor_stopped_at, None
            self._waited = None if stopped is None else time.monotonic() - stopped
            self._latest = None  # evidence nobody took belongs to an earlier turn
        elif isinstance(frame, TranscriptionFrame):
            try:
                self._latest = voice_evidence(frame.result, self._waited)
            except Exception as e:  # noqa: BLE001 - evidence is a bonus, the turn goes on
                logger.warning(f"Voice evidence not measured for this turn: {e}")
                self._latest = None
            self._waited = None
            logger.info(f"Voice evidence: {self._latest}")  # numbers only, never the words
            # Sent even when empty, so the dashboard never shows an older turn's numbers.
            await self.push_frame(
                RTVIServerMessageFrame(data={"type": "voice_evidence", **(self._latest or {})})
            )
        await self.push_frame(frame, direction)


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
