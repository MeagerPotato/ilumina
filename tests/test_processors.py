import asyncio

from pipecat.frames.frames import LLMFullResponseEndFrame, LLMFullResponseStartFrame, LLMTextFrame
from pipecat.processors.frame_processor import FrameDirection
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame

from ilumina.processors import TeachingMoveTagger


def run_reply(chunks: list[str]) -> tuple[str, list[str]]:
    """Feed one LLM reply through the tagger. Returns (spoken text, moves reported)."""

    async def go():
        tagger = TeachingMoveTagger()
        out = []

        async def capture(frame, direction=FrameDirection.DOWNSTREAM):
            out.append(frame)

        tagger.push_frame = capture
        frames = [
            LLMFullResponseStartFrame(),
            *map(LLMTextFrame, chunks),
            LLMFullResponseEndFrame(),
        ]
        for frame in frames:
            await TeachingMoveTagger.process_frame(tagger, frame, FrameDirection.DOWNSTREAM)
        spoken = "".join(f.text for f in out if isinstance(f, LLMTextFrame))
        moves = [f.data["move"] for f in out if isinstance(f, RTVIServerMessageFrame)]
        return spoken, moves

    return asyncio.run(go())


def test_tag_in_one_chunk_is_stripped_and_reported():
    assert run_reply(["[move: smaller_hint] Look at the first term.", " What is it?"]) == (
        "Look at the first term. What is it?",
        ["smaller_hint"],
    )


def test_tag_split_across_chunks():
    assert run_reply(["[mo", "ve: check", "_in] How are", " you doing?"]) == (
        "How are you doing?",
        ["check_in"],
    )


def test_reply_without_a_tag_is_spoken_unchanged():
    assert run_reply(["Nice work.", " Next one."]) == ("Nice work. Next one.", [])


def test_bracket_that_never_closes_is_still_spoken():
    text = "[this is not a tag and it just keeps going for a long while"
    assert run_reply([text, " ok"]) == (text + " ok", [])


def test_short_reply_that_ends_while_held_is_spoken():
    assert run_reply(["[hm"]) == ("[hm", [])
