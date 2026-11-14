import asyncio
from types import SimpleNamespace

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    ProposedUserStartedSpeakingFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina import processors
from ilumina.emotion import score_turn
from ilumina.evidence import describe_evidence, voice_evidence
from ilumina.processors import VoiceEvidence


def flux_turn(*words: tuple[str, float, float]) -> dict:
    """An end-of-turn message shaped like Deepgram Flux's, with made-up words."""
    return {
        "type": "TurnInfo",
        "event": "EndOfTurn",
        "words": [{"word": w, "confidence": 0.9, "start": s, "end": e} for w, s, e in words],
    }


HESITANT = flux_turn(
    ("Um,", 10.0, 10.3), ("I", 10.4, 10.5), ("think", 10.6, 10.9),
    ("maybe", 12.9, 13.3), ("uh", 13.4, 13.6), ("four?", 15.6, 16.0),
)  # fmt: skip


def test_pace_pause_and_fillers_come_from_the_word_timings():
    assert voice_evidence(HESITANT, waited=3.14) == {
        "words": 6,
        "seconds": 6.0,
        "words_per_minute": 60,
        "longest_pause": 2.0,
        "fillers": 2,
        "waited": 3.1,
    }


def test_a_short_answer_has_no_pace():
    evidence = voice_evidence(flux_turn(("Yes.", 4.0, 4.4)))
    assert evidence["words_per_minute"] is None
    assert (evidence["words"], evidence["longest_pause"], evidence["waited"]) == (1, 0.0, None)


def test_overlapping_word_timings_never_give_a_negative_pause():
    evidence = voice_evidence(flux_turn(("uh...", 1.0, 1.6), ("four", 1.5, 2.0)))
    assert (evidence["longest_pause"], evidence["fillers"]) == (0.0, 1)


def test_no_timed_words_means_no_evidence():
    assert voice_evidence(None) is None
    assert voice_evidence({"words": []}) is None
    assert voice_evidence({"words": [{"word": "hi", "confidence": 0.9}]}) is None


def test_the_line_for_the_scorer_says_only_what_was_measured():
    line = describe_evidence(voice_evidence(HESITANT, waited=3.14))
    assert "6 words in 6.0 seconds (60 words a minute)" in line
    assert "longest pause between words 2.0 seconds" in line
    assert "um or uh: 2" in line
    assert "3.1 seconds after the tutor finished" in line
    short = describe_evidence(voice_evidence(flux_turn(("Yes.", 4.0, 4.4))))
    assert "words a minute" not in short and "after the tutor" not in short
    assert "1 word in" in short


def run_frames(frames, clock) -> tuple[VoiceEvidence, list]:
    """Feed frames through VoiceEvidence. `clock` gives the time each one arrives."""

    async def go():
        evidence = VoiceEvidence()
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        evidence.push_frame = capture
        for frame in frames:
            await VoiceEvidence.process_frame(evidence, frame, FrameDirection.DOWNSTREAM)
        return evidence, out

    # Swap the clock for processors.py only: asyncio reads the real one.
    times, real = iter(clock), processors.time
    processors.time = SimpleNamespace(monotonic=lambda: next(times))
    try:
        return asyncio.run(go())
    finally:
        processors.time = real


def transcription(result) -> TranscriptionFrame:
    return TranscriptionFrame("made-up words", "student", "2026-11-14T00:00:00Z", result=result)


def test_the_wait_runs_from_the_tutor_finishing_to_the_student_starting():
    frames = [
        BotStartedSpeakingFrame(),
        BotStoppedSpeakingFrame(),
        ProposedUserStartedSpeakingFrame(),
        transcription(HESITANT),
    ]
    evidence, out = run_frames(frames, clock=[100.0, 102.5])
    sent = [f.data for f in out if isinstance(f, RTVIServerMessageFrame)]
    assert sent == [{"type": "voice_evidence", **voice_evidence(HESITANT, 2.5)}]
    assert [f for f in out if not isinstance(f, RTVIServerMessageFrame)] == frames
    assert evidence.take()["waited"] == 2.5
    assert evidence.take() is None  # a later turn never gets this one's evidence


def waits(frames, clock) -> list:
    _, out = run_frames(frames, clock)
    return [f.data["waited"] for f in out if isinstance(f, RTVIServerMessageFrame)]


def test_cutting_the_tutor_off_has_no_wait_even_on_the_turn_after():
    # Live order: the student starts, and only then does the cut-off tutor stop.
    cut_off = [
        BotStartedSpeakingFrame(),
        ProposedUserStartedSpeakingFrame(),
        BotStoppedSpeakingFrame(),
        transcription(HESITANT),
        ProposedUserStartedSpeakingFrame(),
        transcription(HESITANT),
    ]
    assert waits(cut_off, clock=[]) == [None, None]


def test_speaking_twice_in_a_row_has_one_wait():
    twice = [
        BotStartedSpeakingFrame(),
        BotStoppedSpeakingFrame(),
        ProposedUserStartedSpeakingFrame(),
        transcription(HESITANT),
        ProposedUserStartedSpeakingFrame(),
        transcription(HESITANT),
    ]
    assert waits(twice, clock=[100.0, 101.0]) == [1.0, None]


def test_evidence_nobody_took_is_dropped_when_the_next_turn_starts():
    evidence, _ = run_frames(
        [transcription(HESITANT), ProposedUserStartedSpeakingFrame()], clock=[]
    )
    assert evidence.take() is None


def test_a_turn_without_word_timings_passes_through_and_reports_nothing():
    frame = transcription(None)
    evidence, out = run_frames([frame], clock=[])
    sent = [f.data for f in out if isinstance(f, RTVIServerMessageFrame)]
    assert sent == [{"type": "voice_evidence"}]  # tells the dashboard to clear old numbers
    assert out[-1] is frame and evidence.take() is None


def test_the_scorer_gets_the_measurements_beside_the_conversation():
    class Decisions:
        async def create(self, **kwargs):
            self.kwargs = kwargs
            return type("Response", (), {"answers": {}})()

    decisions = Decisions()
    client = type("Client", (), {"aio": type("Aio", (), {"decisions": decisions})()})()
    line = describe_evidence(voice_evidence(HESITANT))
    asyncio.run(score_turn(client, "gemini-decision-1", b"RIFF", "Tutor: What is two x?", line))
    text = decisions.kwargs["input"][0]["text"]
    assert text.endswith(line) and "Tutor: What is two x?" in text
