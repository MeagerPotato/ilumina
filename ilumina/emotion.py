"""Scores one student turn with Gemini Decision 1 (the Decisions API).

One call per turn. The model hears the audio clip directly and reads the last few
lines of the conversation, so it can weigh tone and pacing together with the words
and what they were an answer to.
"""

import base64

from google import genai

from ilumina.state import Reading, level_of

# The Decisions API is only served under v1beta; the SDK's default path returns 404.
_API_VERSION = "v1beta"

_SCALE_NOTE = (
    "Judge only the student's newest turn, which is the audio. Weigh two kinds of evidence "
    "together: how they sound (tone, pace, pauses, sighs, energy) and what they say, read "
    "against the conversation (does it answer the tutor's last question, do they hedge, ask "
    "for a repeat, or say they are lost). When the voice and the words disagree, let neither "
    "decide alone."
)

# The turn's own words may or may not have reached the conversation text when the audio
# is scored, so the model is told which is which instead of guessing.
_CONTEXT_NOTE = (
    "Recent tutoring conversation, oldest first. The audio that follows is the student's "
    "newest turn. Its words may already be the last Student line here."
)

# Each rubric runs from level 0 (none) to level 4 (very strong).
RUBRICS: dict[str, list[str]] = {
    "confusion": [
        "Clearly understands. Answers directly and correctly paced.",
        "Mostly follows, with a brief hesitation.",
        "Unsure. Hedges, asks for a repeat, or trails off.",
        "Confused. Guessing, contradicting themselves, or long pauses.",
        "Lost. Says they do not understand or cannot start.",
    ],
    "frustration": [
        "Calm and relaxed.",
        "Slight impatience or a small sigh.",
        "Noticeably tense, clipped, or flat.",
        "Frustrated. Sighing, sharp tone, or self-criticism.",
        "Very frustrated. Wants to give up or is upset.",
    ],
    "confidence": [
        "No confidence. Barely audible or refuses to try.",
        "Low confidence. Many hedges such as 'maybe' or 'I think'.",
        "Moderate. Tries an answer but checks for approval.",
        "Confident. Clear, steady answer.",
        "Very confident. Fast, fluent, and explains their reasoning.",
    ],
    "engagement": [
        "Checked out. Minimal or off-topic reply.",
        "Low. Short answers and little energy.",
        "Moderate. Follows along and responds.",
        "Engaged. Asks questions or builds on the idea.",
        "Highly engaged. Curious, energetic, and driving the work.",
    ],
}


def build_questions() -> dict:
    return {
        name: {
            "type": "score",
            "instructions": f"Rate the student's {name}. {_SCALE_NOTE}",
            "criteria": criteria,
        }
        for name, criteria in RUBRICS.items()
    }


def _band_confidence(answer, value: float, top: int) -> float:
    """How sure the model is that the student is in the reading's low/medium/high band.

    The API's own confidence is the chance of one exact rubric level, so it looks
    unsure when the model is split between two neighbours that mean the same thing
    to the tutor, such as "confused" and "lost".
    """
    probabilities = getattr(answer, "probabilities", None)
    if not probabilities:
        return answer.confidence
    band = level_of(value)
    try:
        return sum(p for level, p in probabilities.items() if level_of(int(level) / top) == band)
    except ValueError:  # level keys in a shape we have not seen: keep the API's own number
        return answer.confidence


def parse_answers(answers: dict) -> dict[str, Reading]:
    """Turn Decision 1 score answers into 0-to-1 readings."""
    readings = {}
    for name, criteria in RUBRICS.items():
        answer = answers.get(name)
        if getattr(answer, "type", None) != "score":
            continue
        top = len(criteria) - 1
        value = answer.score / top
        readings[name] = Reading(value=value, confidence=_band_confidence(answer, value, top))
    return readings


async def score_turn(
    client: genai.Client, model: str, wav: bytes, recent_text: str
) -> dict[str, Reading]:
    """Score one turn. `recent_text` is the last few lines of conversation for context."""
    response = await client.aio.decisions.create(
        model=model,
        input=[
            {"type": "text", "text": f"{_CONTEXT_NOTE}\n{recent_text}"},
            {
                "type": "audio",
                "mime_type": "audio/wav",
                "data": base64.b64encode(wav).decode(),
            },
        ],
        questions=build_questions(),
        api_version=_API_VERSION,
        timeout=5,
    )
    return parse_answers(response.answers or {})
