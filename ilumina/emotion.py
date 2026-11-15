"""Scores one student turn with Gemini Decision 1 (the Decisions API), in two channels.

Audio language models lean on the words: on the LISTEN benchmark (Chen et al. 2025),
Gemini 2.5 and other audio models answered "neutral" when the words were neutral,
whatever the voice did, and adding the transcript sometimes made them worse than
audio alone. So the words and the voice are scored separately and joined in code
(`ilumina.fusion`), where we decide how much each counts:

- the voice channel hears the audio with no transcript and no conversation, and is
  asked only how the voice sounds;
- the words channel reads the conversation and the transcript, with no audio.

Each channel is one call with the same four scores and the learning-state choice.
The two calls run at the same time.
"""

import asyncio
import base64
from dataclasses import dataclass

from google import genai

from ilumina.state import Reading, level_of

# The Decisions API is only served under v1beta; the SDK's default path returns 404.
_API_VERSION = "v1beta"
_TIMEOUT_SECONDS = 5

_VOICE_NOTE = (
    "Listen only to how the student's voice sounds in this audio: pitch and intonation, "
    "loudness, pace, pauses, sighs and voice quality. Do not use what the words mean. The "
    "same sentence can be said calmly or angrily, and only the sound counts here. When the "
    "sound gives no clear sign either way, choose the level that fits an ordinary, relaxed "
    "voice. People differ in how they normally speak, so where the measurements say how "
    "this turn compares with the student's usual, weigh that change more than the raw numbers."
)

_WORDS_NOTE = (
    "Judge only from the words: what the student said in their newest turn, read against "
    "the conversation. Does it answer the tutor's last question, do they hedge, ask for a "
    "repeat, say they are lost, criticise themselves, or ask a question of their own? You "
    "cannot hear the voice, so do not guess at tone. When the words give no clear sign, "
    "choose the level that fits an ordinary, neutral reply."
)

_VOICE_CONTEXT = "One student turn from a spoken tutoring session."
_WORDS_CONTEXT = "Recent tutoring conversation, oldest first."

# Each rubric runs from level 0 (none) to level 4 (very strong). The scale is kept
# linear because Decision 1's score is the probability-weighted average level.
# Wording draws on the BROMP coding manual (Ocumpaugh, Baker and Rodrigo) and on the
# spoken-tutoring uncertainty studies in docs/emotion-research.md.

# How the voice sounds. Pauses, silences and a rise at the end go with uncertainty
# (Liscombe et al. 2005; Pon-Barry and Shieber 2011); energy, tension and pitch
# movement carry arousal (Eyben et al. 2016).
VOICE_RUBRICS: dict[str, list[str]] = {
    "confusion": [
        "Sounds sure of what they are saying: smooth, steady delivery.",
        "Mostly smooth, with one brief hesitation.",
        "Sounds unsure: hesitant or drawn-out words, or a rise at the end like a question.",
        "Sounds confused: halting, with long pauses, restarts or trailing off.",
        "Sounds lost: long silences, stops and starts, or the voice fades away.",
    ],
    "frustration": [
        "Relaxed, easy voice.",
        "Slightly tight or impatient voice, or a small sigh.",
        "Noticeably tense: clipped, strained, or flat and terse.",
        "Frustrated sound: heavy sighs, a sharp or strained voice, or a tense laugh.",
        "Very frustrated or upset sound: exasperated, raised or shaking voice.",
    ],
    "confidence": [
        "Very unsure voice: barely audible, shaky or fading.",
        "Low confidence: quiet and hesitant, ending on a rise like a question.",
        "Moderate: steady enough, but tentative.",
        "Confident: clear, steady voice that falls at the end of the answer.",
        "Very confident: fluent, firm and quick.",
    ],
    "engagement": [
        "No energy: flat, monotone and slow; sounds bored.",
        "Low energy: quiet and flat.",
        "Moderate energy: an ordinary, even voice.",
        "Lively: varied pitch and good energy.",
        "Very lively: animated, quick and expressive.",
    ],
}

# What the words say, read against the conversation.
RUBRICS: dict[str, list[str]] = {
    "confusion": [
        "Answers the tutor's question directly and correctly, without hedging.",
        "Mostly follows: a small slip or a quick self-correction.",
        (
            "Unsure: hedges such as 'I think' or 'maybe', answers with a question, or asks for "
            "a repeat."
        ),
        (
            "Confused: guesses, contradicts themselves, or gives an answer that does not fit "
            "the question."
        ),
        "Lost: says they do not understand, cannot start, or asks to go back.",
    ],
    "frustration": [
        "Neutral or positive wording.",
        "Slight impatience, such as 'okay, okay' or 'ugh'.",
        "Terse or curt replies that show annoyance.",
        ("Frustrated: self-criticism such as 'I'm so bad at this', or complaining about the work."),
        "Very frustrated: wants to give up, or is upset or rude about the work.",
    ],
    "confidence": [
        "Refuses to try, or says they have no idea.",
        "Low: many hedges, or asks whether the answer is right.",
        "Moderate: tries an answer but checks for approval.",
        "Confident: gives a clear, direct answer.",
        "Very confident: answers and explains their reasoning.",
    ],
    "engagement": [
        "Checked out: minimal or off-topic reply.",
        "Low: one-word answers with nothing added.",
        "Moderate: answers what was asked.",
        "Engaged: asks questions or builds on the idea.",
        "Highly engaged: curious and driving the work, suggesting next steps.",
    ],
}

# One categorical question beside the four scores: which learning-centred state the
# turn shows, with the categories BROMP observers code. Questions are scored
# independently, so this does not change the four scores.
LEARNING_STATE_QUESTION = "learning_state"
VOICE_STATE_CRITERIA: dict[str, str] = {
    "engaged": "Engaged concentration: an even, attentive voice with steady energy.",
    "confused": "Confusion: a hesitant, halting voice, with pauses, restarts or endings "
    "that rise like a question.",
    "frustrated": "Frustration: a tense, strained or sharp voice, sighs, or an exasperated tone.",
    "bored": "Boredom: a flat, monotone, low-energy voice, slow and dragging.",
    "neutral": "No clear sign in the voice: an ordinary, relaxed tone.",
}
LEARNING_STATE_CRITERIA: dict[str, str] = {
    "engaged": "Engaged concentration: working on the problem, answering or reasoning about it.",
    "confused": "Confusion: says or shows they do not understand, hedges, or asks for help "
    "or an explanation.",
    "frustrated": "Frustration: self-criticism, complaining, or wanting to give up.",
    "bored": "Boredom: minimal, off-topic or dismissive replies.",
    "neutral": "None of these clearly: a plain, short or social reply.",
}


@dataclass
class Channel:
    """One channel's answers for one turn."""

    readings: dict[str, Reading]
    learning: dict[str, float] | None


def _questions(rubrics: dict, criteria: dict, note: str) -> dict:
    questions = {
        name: {"type": "score", "instructions": f"Rate the student's {name}. {note}", "criteria": c}
        for name, c in rubrics.items()
    }
    questions[LEARNING_STATE_QUESTION] = {
        "type": "choice",
        "instructions": "Which learning state does the student's newest turn show most? " + note,
        "criteria": criteria,
    }
    return questions


def build_voice_questions() -> dict:
    return _questions(VOICE_RUBRICS, VOICE_STATE_CRITERIA, _VOICE_NOTE)


def build_questions() -> dict:
    """The words channel's questions."""
    return _questions(RUBRICS, LEARNING_STATE_CRITERIA, _WORDS_NOTE)


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


def parse_answers(answers: dict, rubrics: dict = RUBRICS) -> dict[str, Reading]:
    """Turn Decision 1 score answers into 0-to-1 readings."""
    readings = {}
    for name, criteria in rubrics.items():
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
    known = {s: float(probabilities.get(s, 0.0)) for s in LEARNING_STATE_CRITERIA}  # same keys
    return known if sum(known.values()) > 0 else None


async def _decide(client, model: str, content: list, questions: dict, rubrics: dict) -> Channel:
    response = await client.aio.decisions.create(
        model=model,
        input=content,
        questions=questions,
        api_version=_API_VERSION,
        timeout=_TIMEOUT_SECONDS,
    )
    answers = response.answers or {}
    return Channel(parse_answers(answers, rubrics), parse_learning_state(answers))


async def score_voice(client: genai.Client, model: str, wav: bytes, measured: str = "") -> Channel:
    """How the voice sounds: the audio and acoustic measurements only, no words."""
    text = _VOICE_CONTEXT + (f"\n\n{measured}" if measured else "")
    content = [
        {"type": "text", "text": text},
        {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(wav).decode()},
    ]
    return await _decide(client, model, content, build_voice_questions(), VOICE_RUBRICS)


async def score_words(
    client: genai.Client, model: str, recent_text: str, transcript: str = "", measured: str = ""
) -> Channel:
    """What the words say: the conversation and this turn's transcript, no audio."""
    text = f"{_WORDS_CONTEXT}\n{recent_text}"
    if transcript:
        text += f'\n\nThe student\'s newest turn, as transcribed: "{transcript}"'
    else:
        text += "\n\nThe student's newest turn is the last Student line."
    if measured:
        text += f"\n{measured}"
    return await _decide(
        client, model, [{"type": "text", "text": text}], build_questions(), RUBRICS
    )


async def score_turn(
    client: genai.Client,
    model: str,
    wav: bytes,
    recent_text: str,
    voice_measured: str = "",
    transcript: str = "",
    words_measured: str = "",
) -> dict[str, Channel]:
    """Score one turn in both channels at once. Returns {"voice": ..., "words": ...}.

    A channel that fails is left out, so one slow or failed call never costs the turn.
    Raises only when every channel failed.
    """
    calls = {"voice": score_voice(client, model, wav, voice_measured)}
    if transcript or recent_text.strip():
        calls["words"] = score_words(client, model, recent_text, transcript, words_measured)
    results = await asyncio.gather(*calls.values(), return_exceptions=True)
    channels = {name: r for name, r in zip(calls, results) if isinstance(r, Channel)}
    if not channels:
        raise next(r for r in results if isinstance(r, BaseException))
    return channels
