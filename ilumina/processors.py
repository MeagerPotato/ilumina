"""Pipecat processors: voice evidence, camera view and state note in, teaching move out."""

import asyncio
import io
import math
import time

import numpy as np
from loguru import logger
from PIL import Image
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    Frame,
    InputAudioRawFrame,
    LLMContextFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    ProposedUserStartedSpeakingFrame,
    TranscriptionFrame,
    UserImageRawFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.evidence import timed_words, voice_evidence
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
        self._latest: tuple[str, tuple[int, int], bytes] | None = None
        self._latest_at = 0.0
        self._shown: dict | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, UserImageRawFrame):
            self._latest = (frame.format, frame.size, frame.image)
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
        if self._latest is None or time.monotonic() - self._latest_at > _MAX_FRAME_AGE_SECONDS:
            return None
        return self._latest

    def take_jpeg(self, jpeg: bytes) -> None:
        """A camera frame the dashboard sent as a JPEG message.

        The hosted app talks to the bot over a WebSocket, which carries no video, so
        the dashboard sends one still a second instead. It counts like a video frame.
        """
        image = Image.open(io.BytesIO(jpeg))
        if image.width * image.height > 1280 * 1280:
            raise ValueError(f"camera still is too large: {image.size}")
        image = image.convert("RGB")
        self._latest = ("RGB", image.size, image.tobytes())
        self._latest_at = time.monotonic()

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


class PushToTalkGate(FrameProcessor):
    """Sits right after the transport input and silences the microphone between holds.

    With push to talk on, the dashboard says when Space or the Talk button is held.
    Between holds every audio frame still goes on, but as silence: speech to text
    keeps getting audio, so a turn ends as soon as the student lets go, and nothing
    said near the microphone in between reaches the tutor. The dashboard also
    switches its own microphone track off; this gate holds whatever the browser's
    audio path does. Off by default, so a dashboard that never says otherwise is
    heard all the time, as before.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.closed = False

    def set(self, on, held) -> None:
        self.closed = bool(on) and not bool(held)

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if self.closed and isinstance(frame, InputAudioRawFrame) and frame.audio:
            frame.audio = bytes(len(frame.audio))  # same length and timing, all zero
        await self.push_frame(frame, direction)


# Quieter than this, in dB below full scale, the microphone is sending near silence.
SILENT_BELOW_DBFS = -50
_LEVEL_EVERY_SECONDS, _LOG_EVERY_LEVELS = 1.0, 5


class MicLevel(FrameProcessor):
    """Sits right after the transport input and reports how loud the microphone is.

    Once a second it tells the dashboard the loudest moment of that second, and every
    few seconds it logs it. This is the sound exactly as speech to text gets it, so a
    silent microphone and a turn that was not detected can be told apart. Only a
    level is measured; no audio is kept. Every frame passes through untouched.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._peak = 0  # loudest sample since the last report
        self._since = time.monotonic()
        self._reports = 0
        self._loudest_logged = SILENT_BELOW_DBFS * 2

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame) and frame.audio:
            try:
                samples = np.frombuffer(frame.audio, dtype=np.int16)
                self._peak = max(self._peak, int(np.abs(samples.astype(np.int32)).max()))
                if time.monotonic() - self._since >= _LEVEL_EVERY_SECONDS:
                    await self._report()
            except Exception as e:  # noqa: BLE001 - the meter must never cost a frame of audio
                logger.debug(f"Mic level not measured: {e}")
        await self.push_frame(frame, direction)

    async def _report(self):
        dbfs = round(20 * math.log10(max(self._peak, 1) / 32768))
        self._peak, self._since = 0, time.monotonic()
        self._reports += 1
        self._loudest_logged = max(self._loudest_logged, dbfs)
        if self._reports % _LOG_EVERY_LEVELS == 0:
            logger.info(
                f"Mic level: loudest {self._loudest_logged} dBFS in the last "
                f"{_LOG_EVERY_LEVELS} seconds"
            )
            self._loudest_logged = SILENT_BELOW_DBFS * 2
        await self.push_frame(
            RTVIServerMessageFrame(
                data={"type": "mic_level", "dbfs": dbfs, "silent": dbfs < SILENT_BELOW_DBFS}
            )
        )


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
        self._latest_text = ""
        self._turn_open = False  # a turn has started and not ended yet
        self._words: list[dict] = []  # this turn's timed words so far

    def take(self) -> dict | None:
        """The newest turn's evidence, once. A later turn never gets an old one."""
        latest, self._latest = self._latest, None
        return latest

    def take_text(self) -> str:
        """The newest turn's transcript, once, for the words channel. Never logged."""
        text, self._latest_text = self._latest_text, ""
        return text

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
        elif isinstance(frame, ProposedUserStartedSpeakingFrame) or (
            # Flux proposes every turn first. Without Flux (the ElevenLabs backup) the
            # turn's start comes back from the user aggregator instead.
            isinstance(frame, UserStartedSpeakingFrame) and not self._turn_open
        ):
            # No wait when the student cut the tutor off. One wait per tutor reply:
            # a second student turn in a row has none either.
            self._turn_open = True
            self._tutor_speaking = False
            stopped, self._tutor_stopped_at = self._tutor_stopped_at, None
            self._waited = None if stopped is None else time.monotonic() - stopped
            self._latest = None  # evidence nobody took belongs to an earlier turn
            self._latest_text = ""
            self._words = []
        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._turn_open = False
        elif isinstance(frame, TranscriptionFrame):
            # ElevenLabs sends a turn in pieces, one per pause; Flux sends it whole.
            # The pieces are joined so the turn is measured and read as one.
            self._latest_text = " ".join(filter(None, [self._latest_text, frame.text or ""]))
            try:
                words = timed_words(frame.result)
                # Join the timings only when they run on from the last piece; timings
                # that start again from zero would make false pauses.
                if self._words and words and words[0]["start"] >= self._words[-1]["end"]:
                    words = self._words + words
                self._words = words
                self._latest = voice_evidence({"words": words}, self._waited)
            except Exception as e:  # noqa: BLE001 - evidence is a bonus, the turn goes on
                logger.warning(f"Voice evidence not measured for this turn: {e}")
                self._latest = None
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


# Longest opening we will hold back while looking for a tag that never closes.
_MAX_TAG_CHARS = 48
_MAX_SHOW_CHARS = 400  # a show tag carries a line of LaTeX


def _closing_bracket(text: str) -> int:
    """Where the bracket that opens `text` closes, counting brackets inside it. -1 if not yet."""
    depth = 0
    for i, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _read_tags(text: str) -> tuple[dict[str, str], str, bool]:
    """Read the tags a reply opens with: (tags, the words after them, undecided).

    `undecided` is True while more text is needed to know where the tags end.
    """
    tags: dict[str, str] = {}
    rest = text.lstrip()
    while rest.startswith("["):
        start = rest[1:].lstrip().lower()
        end = _closing_bracket(rest)
        if end < 0:  # still arriving
            if start.startswith("show:") or "show:".startswith(start):
                # LaTeX must never be spoken: a show tag that runs away is dropped.
                return (tags, rest, True) if len(rest) < _MAX_SHOW_CHARS else (tags, "", False)
            if "move" in tags:
                return tags, rest, False
            return tags, rest, len(rest) < _MAX_TAG_CHARS
        body = rest[1:end]
        if start.startswith("show:"):
            tags["show"] = body.split(":", 1)[1].strip()  # the last one written stays up
        elif "move" in tags:
            return tags, rest, False  # a second plain bracket is speech
        else:
            tags["move"] = body.removeprefix("move:").strip().lower()
        rest = rest[end + 1 :].lstrip()
    # With nothing after the tags yet, another tag may still be on its way.
    return tags, rest, not rest


class TeachingMoveTagger(FrameProcessor):
    """Sits right after the LLM.

    The tutor starts each reply with a tag such as ``[move: smaller_hint]``, and may
    add ``[show: x^2 - 9]`` with the math it is talking about, in LaTeX. This removes
    the tags before the reply is spoken and reports them to the dashboard. A reply
    with no tag passes through untouched.
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
            tags, text, undecided = _read_tags(self._held)
            if undecided:
                return  # keep holding until the tags close or clearly are not tags
            await self._report(tags)
            self._held = None
            if not text:
                return
            frame.text = text
        elif isinstance(frame, LLMFullResponseEndFrame) and self._held:
            # The reply ended while we were still holding text. Speak what is not a tag.
            tags, text, _ = _read_tags(self._held)
            await self._report(tags)
            if text:
                await self.push_frame(LLMTextFrame(text), direction)
            self._held = None
        await self.push_frame(frame, direction)

    async def _report(self, tags: dict[str, str]):
        if "move" in tags:
            await self.push_frame(
                RTVIServerMessageFrame(data={"type": "teaching_move", "move": tags["move"]})
            )
        if tags.get("show"):
            await self.push_frame(
                RTVIServerMessageFrame(data={"type": "board", "latex": tags["show"]})
            )
