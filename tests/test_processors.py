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
        sent = [f.data for f in out if isinstance(f, RTVIServerMessageFrame)]
        shown.extend(d["latex"] for d in sent if d["type"] == "board")
        return spoken, [d["move"] for d in sent if d["type"] == "teaching_move"]

    return asyncio.run(go())


shown: list[str] = []  # what the last run_reply calls put on the board


def run_shown(chunks: list[str]) -> tuple[str, list[str], list[str]]:
    """(spoken text, moves reported, math put on the board) for one reply."""
    shown.clear()
    spoken, moves = run_reply(chunks)
    return spoken, moves, list(shown)


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


FRAC = r"\frac{d}{dx}\sin x = \cos x"


def test_a_show_tag_goes_to_the_board_and_is_never_spoken():
    reply = [f"[move: worked_example] [show: {FRAC}] The derivative", " of sine x is cosine x."]
    assert run_shown(reply) == (
        "The derivative of sine x is cosine x.",
        ["worked_example"],
        [FRAC],
    )


def test_tags_split_across_chunks_in_any_place():
    reply = ["[move: smaller", "_hint]", " [sh", "ow: x^2 ", "- 9]", " What", " factors?"]
    assert run_shown(reply) == ("What factors?", ["smaller_hint"], ["x^2 - 9"])


def test_a_move_tag_alone_still_works_when_speech_follows_in_the_next_chunk():
    assert run_shown(["[move: continue]", " Nice.", " Go on."]) == (
        "Nice. Go on.",
        ["continue"],
        [],
    )


def test_a_show_tag_that_never_closes_is_dropped_not_spoken():
    runaway = "[show: " + "x + " * 120
    spoken, moves, board = run_shown(["[move: continue] ", runaway, " ok"])
    assert (spoken, moves, board) == (" ok", ["continue"], [])


def test_square_brackets_inside_the_latex_do_not_end_the_tag():
    integral = r"\int_0^1 2x\,dx = \left[x^2\right]_0^1"
    reply = f"[move: worked_example] [show: {integral}] So we evaluate."
    expected = ("So we evaluate.", ["worked_example"], [integral])
    assert run_shown([reply]) == expected
    assert run_shown(list(reply)) == expected  # one character at a time


def test_tags_in_either_order_and_a_second_show_tag_are_never_spoken():
    assert run_shown(list("[show: x^2] [move: continue] Hi")) == ("Hi", ["continue"], ["x^2"])
    assert run_shown(["[move: continue] [show: x^2] [show: 2x] Hi"]) == (
        "Hi",
        ["continue"],
        ["2x"],
    )


def test_a_reply_that_is_only_tags_says_nothing():
    assert run_shown(["[move: check_in] [show: x]"]) == ("", ["check_in"], ["x"])


def test_brackets_after_the_tags_are_speech():
    assert run_shown(["[move: continue] [show: x] [sighs] Okay."]) == (
        "[sighs] Okay.",
        ["continue"],
        ["x"],
    )
