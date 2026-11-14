"""Scores one student turn with Gemini Decision 1 (the Decisions API).

One call per turn. The model hears the audio clip directly, so it can use tone
and pacing as well as the words.
"""

import base64

from google import genai

from ilumina.state import Reading

_SCALE_NOTE = (
    "Judge only the student's most recent turn in the audio. "
    "Use how they sound (tone, pace, pauses, hedging) as well as what they say."
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


def parse_answers(answers: dict) -> dict[str, Reading]:
    """Turn Decision 1 score answers into 0-to-1 readings."""
    readings = {}
    for name, criteria in RUBRICS.items():
        answer = answers.get(name)
        if answer is None:
            continue
        readings[name] = Reading(
            value=answer.score / (len(criteria) - 1),
            confidence=answer.confidence,
        )
    return readings


async def score_turn(
    client: genai.Client, model: str, wav: bytes, recent_text: str
) -> dict[str, Reading]:
    """Score one turn. `recent_text` is the last few lines of conversation for context."""
    response = await client.aio.decisions.create(
        model=model,
        input=[
            {"type": "text", "text": f"Recent tutoring conversation:\n{recent_text}"},
            {
                "type": "audio",
                "mime_type": "audio/wav",
                "data": base64.b64encode(wav).decode(),
            },
        ],
        questions=build_questions(),
    )
    return parse_answers(response.answers or {})
