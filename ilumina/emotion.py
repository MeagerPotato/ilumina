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
    "decide alone. People differ in how they normally speak, so where the measurements say "
    "how this turn compares with the student's usual, weigh that change more than the raw "
    "numbers."
)

# The turn's own words may or may not have reached the conversation text when the audio
# is scored, so the model is told which is which instead of guessing.
_CONTEXT_NOTE = (
    "Recent tutoring conversation, oldest first. The audio that follows is the student's "
    "newest turn. Its words may already be the last Student line here."
)

# Each rubric runs from level 0 (none) to level 4 (very strong). The scale is kept
# linear because Decision 1's score is the probability-weighted average level.
# Wording draws on the BROMP coding manual (Ocumpaugh, Baker and Rodrigo) and on the
# spoken-tutoring uncertainty studies in docs/emotion-research.md: hedges, answers
# spoken as questions and silences inside the answer are the strongest signs.
RUBRICS: dict[str, list[str]] = {
    "confusion": [
        "Clearly follows. Answers the tutor's question directly, without hedging.",
        "Mostly follows, with one brief hesitation or a quick self-correction.",
        (
            "Unsure. Hedges such as 'I think' or 'maybe', answers as a question, asks for a "
            "repeat, or trails off."
        ),
        (
            "Confused. Stuck: guessing, contradicting themselves, or long silences before or "
            "inside the answer."
        ),
        "Lost. Says they do not understand, cannot start, or asks to go back.",
    ],
    "frustration": [
        "Calm and relaxed.",
        "Slight impatience or a small sigh.",
        "Noticeably tense, clipped, or flat.",
        (
            "Frustrated. Sighing, a sharp or strained tone, a tense laugh, or self-criticism "
            "such as 'I'm so bad at this'."
        ),
        "Very frustrated. Wants to give up, or is upset or annoyed with the work.",
    ],
    "confidence": [
        "No confidence. Barely audible or refuses to try.",
        "Low confidence. Many hedges, or the answer rises at the end like a question.",
        "Moderate. Tries an answer but checks for approval.",
        "Confident. Clear, steady answer.",
        "Very confident. Fast, fluent, and explains their reasoning.",
    ],
    "engagement": [
        "Checked out. Minimal, flat or off-topic reply; sounds bored with the task.",
        "Low. Short answers and little energy.",
        "Moderate. Follows along and responds.",
        "Engaged. Asks questions or builds on the idea.",
        "Highly engaged. Curious, energetic, and driving the work.",
    ],
}

# One categorical question beside the four scores: which learning-centred state
# the turn shows, with the definitions BROMP observers use. Questions are scored
# independently, so this does not change the four scores.
LEARNING_STATE_QUESTION = "learning_state"
LEARNING_STATE_CRITERIA: dict[str, str] = {
    "engaged": "Engaged concentration: focused on the problem and working on it.",
    "confused": "Confusion: having difficulty understanding. Unsure, hedging, asking for "
    "help or an explanation, or stuck.",
    "frustrated": "Frustration: distress or annoyance. Sighing, a strained tone, "
    "self-criticism, or wanting to give up.",
    "bored": "Boredom: finds the activity dull or tedious. Flat, minimal or off-topic "
    "replies with little energy.",
    "neutral": "None of these clearly. A plain, short or social reply with no sign of "
    "the other states.",
}


def build_questions() -> dict:
    questions = {
        name: {
            "type": "score",
            "instructions": f"Rate the student's {name}. {_SCALE_NOTE}",
            "criteria": criteria,
        }
        for name, criteria in RUBRICS.items()
    }
    questions[LEARNING_STATE_QUESTION] = {
        "type": "choice",
        "instructions": "Which learning state does the student's newest turn show most? "
        + _SCALE_NOTE,
        "criteria": LEARNING_STATE_CRITERIA,
    }
    return questions


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
        readings[name] = Reading(
            value=value,
            confidence=_band_confidence(answer, value, top),
            probabilities=_level_probabilities(answer, top),
        )
    return readings


def _level_probabilities(answer, top: int) -> tuple[float, ...] | None:
    """The API's probability for each rubric level 0..top, or None if it gave none we can read."""
    probabilities = getattr(answer, "probabilities", None)
    if not probabilities:
        return None
    levels = [0.0] * (top + 1)
    try:
        for level, p in probabilities.items():
            levels[int(level)] = float(p)
    except (ValueError, IndexError, TypeError):
        return None
    return tuple(levels) if sum(levels) > 0 else None


def parse_learning_state(answers: dict) -> dict[str, float] | None:
    """The learning-state choice as a probability for each state, or None."""
    answer = answers.get(LEARNING_STATE_QUESTION)
    if getattr(answer, "type", None) != "choice":
        return None
    probabilities = getattr(answer, "probabilities", None) or {}
    known = {s: float(probabilities.get(s, 0.0)) for s in LEARNING_STATE_CRITERIA}
    return known if sum(known.values()) > 0 else None


async def score_turn(
    client: genai.Client, model: str, wav: bytes, recent_text: str, measured: str = ""
) -> tuple[dict[str, Reading], dict[str, float] | None]:
    """Score one turn. `recent_text` is the last few lines of conversation for context.
    `measured` is the turn's measured evidence as plain text (word timings, voice
    measurements, and how they compare with this student's usual), if there is any.

    Returns the four readings and the learning-state probabilities (or None)."""
    context = f"{_CONTEXT_NOTE}\n{recent_text}"
    if measured:
        context += f"\n\n{measured}"
    response = await client.aio.decisions.create(
        model=model,
        input=[
            {"type": "text", "text": context},
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
    answers = response.answers or {}
    return parse_answers(answers), parse_learning_state(answers)
