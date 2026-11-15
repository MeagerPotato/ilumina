import asyncio
from types import SimpleNamespace

import numpy as np
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    InputAudioRawFrame,
    ProposedUserStartedSpeakingFrame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina import processors
from ilumina.emotion import score_turn
from ilumina.evidence import describe_evidence, describe_timing, describe_wording, voice_evidence
from ilumina.processors import MicLevel, VoiceEvidence


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
        "silence": 4.0,
        "silence_share": 0.67,
        "hedges": 2,  # "I think" and "maybe"
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


def run_frames(frames, clock, kind=VoiceEvidence) -> tuple:
    """Feed frames through one processor. `clock` gives the time at each reading of it."""

    async def go():
        processor = kind()
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        processor.push_frame = capture
        for frame in frames:
            await kind.process_frame(processor, frame, FrameDirection.DOWNSTREAM)
        return processor, out

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


def test_each_channel_gets_only_its_own_measurements():
    class Decisions:
        def __init__(self):
            self.calls = []

        async def create(self, **kwargs):
            self.calls.append(kwargs)
            return type("Response", (), {"answers": {}})()

    decisions = Decisions()
    client = type("Client", (), {"aio": type("Aio", (), {"decisions": decisions})()})()
    evidence = voice_evidence(HESITANT)
    timing, wording = describe_timing(evidence), describe_wording(evidence)
    asyncio.run(
        score_turn(
            client, "gemini-decision-1", b"RIFF", "Tutor: What is two x?",
            voice_measured=timing, transcript="um I think maybe four", words_measured=wording,
        )
    )  # fmt: skip
    by_kind = {
        "voice" if any(c["type"] == "audio" for c in call["input"]) else "words": call
        for call in decisions.calls
    }
    voice_text = by_kind["voice"]["input"][0]["text"]
    words_text = by_kind["words"]["input"][0]["text"]
    assert voice_text.endswith(timing) and "two x" not in voice_text and "maybe" not in voice_text
    assert "hedges" not in voice_text and "fillers" not in timing
    assert "Tutor: What is two x?" in words_text and "um I think maybe four" in words_text
    assert words_text.endswith(wording) and "seconds" not in words_text
    assert len(by_kind["words"]["input"]) == 1  # the words channel never gets the audio


def sound(peak: int) -> InputAudioRawFrame:
    samples = np.zeros(320, dtype=np.int16)
    samples[7] = peak
    return InputAudioRawFrame(audio=samples.tobytes(), sample_rate=16000, num_channels=1)


def test_the_mic_level_is_the_loudest_moment_of_each_second():
    # Times: made at 0, then one reading per frame, then one more at each report.
    frames = [sound(3), sound(-16384), sound(100), sound(0), sound(-32768)]
    _, out = run_frames(frames, clock=[0.0, 0.4, 1.0, 1.0, 1.5, 2.0, 2.0, 2.4], kind=MicLevel)
    levels = [f.data for f in out if isinstance(f, RTVIServerMessageFrame)]
    assert levels == [
        {"type": "mic_level", "dbfs": -6, "silent": False},  # half of full scale
        {"type": "mic_level", "dbfs": -50, "silent": False},
    ]
    assert [f for f in out if not isinstance(f, RTVIServerMessageFrame)] == frames


def test_a_dead_microphone_is_reported_as_silent():
    _, out = run_frames([sound(0), sound(2)], clock=[0.0, 0.5, 1.2, 1.2], kind=MicLevel)
    levels = [f.data for f in out if isinstance(f, RTVIServerMessageFrame)]
    assert levels == [{"type": "mic_level", "dbfs": -84, "silent": True}]


def test_audio_the_meter_cannot_read_still_reaches_speech_to_text():
    odd = InputAudioRawFrame(audio=b"\x01\x02\x03", sample_rate=16000, num_channels=1)
    _, out = run_frames([odd], clock=[0.0], kind=MicLevel)
    assert out == [odd]


def test_hedges_and_silence_are_counted():
    turn = flux_turn(("I", 0.0, 0.1), ("dont", 0.2, 0.4), ("know,", 0.5, 0.7),
                     ("sort", 1.5, 1.7), ("of", 1.8, 1.9), ("five", 2.0, 2.3))  # fmt: skip
    evidence = voice_evidence(turn)
    assert evidence["hedges"] == 2  # "I dont know" and "sort of"
    assert evidence["silence"] == 0.8  # the one gap of 0.25 s or more


def eleven_piece(*words) -> dict:
    """One ElevenLabs piece of a turn: its words, with the spaces it also lists."""
    out = []
    for text, start, end in words:
        out += [{"text": text, "start": start, "end": end, "type": "word"},
                {"text": " ", "start": end, "end": end + 0.1, "type": "spacing"}]  # fmt: skip
    return {"words": out}


def test_an_elevenlabs_turn_in_pieces_is_measured_as_one():
    # Without Flux there is no proposed start: the aggregator's start opens the turn,
    # and each pause sends a piece of the turn.
    frames = [
        BotStartedSpeakingFrame(),
        BotStoppedSpeakingFrame(),
        UserStartedSpeakingFrame(),
        transcription(eleven_piece(("um", 0.0, 0.3), ("I", 0.5, 0.6), ("think", 0.6, 0.9))),
        transcription(eleven_piece(("it's", 2.9, 3.1), ("four", 3.1, 3.5))),
        UserStoppedSpeakingFrame(),
    ]
    evidence, _ = run_frames(frames, clock=[100.0, 101.0])
    measured = evidence.take()
    assert measured["words"] == 5 and measured["fillers"] == 1 and measured["hedges"] == 1
    assert measured["longest_pause"] == 2.0  # the pause between the two pieces
    assert measured["waited"] == 1.0
    assert evidence.take_text() == "made-up words made-up words"


def test_pieces_whose_timings_start_again_are_not_joined():
    frames = [
        UserStartedSpeakingFrame(),
        transcription(eleven_piece(("two", 0.0, 0.3), ("x", 0.4, 0.6))),
        transcription(eleven_piece(("four", 0.0, 0.4))),
    ]
    evidence, _ = run_frames(frames, clock=[])
    assert evidence.take()["words"] == 1
