"""Checks the student's work with Gemini Decision 1 (the Decisions API).

One call per student turn, apart from the emotion call, so that neither can break the
other. The model hears the turn, reads the last few lines of the conversation and, when
the camera is on, sees the page. It answers four questions: is the step right, what kind
of mistake is it, where is it, and what would fix it. Each answer comes with a
probability. The tutor gets the result as a one-line note and the dashboard shows it.
"""

import base64

from google import genai

# The Decisions API is only served under v1beta; the SDK's default path returns 404.
_API_VERSION = "v1beta"

_CONTEXT_NOTE = (
    "Recent tutoring conversation, oldest first. The audio that follows is the student's "
    "newest turn. Its words may already be the last Student line here."
)
_PICTURE_NOTE = "The picture is the student's page as they spoke. It may show their working."

_TASK = (
    "You are checking a math student's work during a tutoring session. Judge only what the "
    "student gave in their newest turn, which is the audio: a step, an answer or an "
    "explanation. Use the conversation to know which problem and step they are on, and "
    "their written work if a picture is included. Work the step out yourself before you "
    "decide."
)

# Each question: option id -> (plain words for the tutor and the dashboard, what the
# option means for the model). The Decisions API returns no text of its own, so what is
# wrong, where and what to do about it are each a choice between these.
QUESTIONS: dict[str, tuple[str, dict[str, tuple[str, str]]]] = {
    "verdict": (
        "Is what the student just gave correct?",
        {
            "correct": ("looks correct", "The step, answer or explanation is correct."),
            "mistake": ("a mistake", "The step, answer or explanation contains a mistake."),
            "nothing": (
                "nothing to check",
                "Nothing to judge: the student asked a question, is stuck, or only said hello.",
            ),
        },
    ),
    "kind": (
        "If there is a mistake, what kind is it?",
        {
            "none": ("no mistake", "There is no mistake, or nothing to judge."),
            "slip": (
                "a small slip",
                "A small slip: arithmetic, a wrong or dropped sign, or a copying error.",
            ),
            "rule": (
                "the wrong rule or formula",
                "The wrong rule or formula, or the right one applied incorrectly.",
            ),
            "concept": (
                "a misunderstanding of the idea",
                "The student misunderstands the idea behind the step.",
            ),
            "misread": (
                "a misreading of the problem",
                "The student misread the problem or answered a different question.",
            ),
            "unfinished": (
                "an unfinished step",
                "Right so far, but a needed step was skipped or the answer is incomplete.",
            ),
        },
    ),
    "place": (
        "If there is a mistake, where did it go wrong?",
        {
            "none": ("nowhere", "There is no mistake, or nothing to judge."),
            "setup": (
                "setting up the problem",
                "Setting up: what is given, what is asked, or how it was written down.",
            ),
            "method": (
                "choosing the method",
                "Choosing which method, rule or formula to use.",
            ),
            "working": (
                "carrying out the steps",
                "Carrying out the steps: the algebra, the arithmetic or the signs.",
            ),
            "answer": (
                "the final answer",
                "The final answer or how it is stated, after correct working.",
            ),
        },
    ),
    "fix": (
        "What should the tutor have the student do next?",
        {
            "confirm": ("confirm it and move on", "Nothing to fix. Confirm it and move on."),
            "redo_line": (
                "redo one line of the working",
                "Redo one specific line of the working, slowly.",
            ),
            "recall_rule": (
                "recall the rule or formula",
                "Recall or look up the rule or formula before trying again.",
            ),
            "rebuild_idea": (
                "go back to the idea with a simpler example",
                "Go back to the idea behind the step with a simpler example.",
            ),
            "reread": ("read the problem again", "Read the problem again, out loud."),
            "finish": ("finish the missing step", "Finish the step that was left out."),
            "ask": (
                "say what they have tried",
                "There is no work yet. Ask what the student has tried or where they are.",
            ),
        },
    ),
}


def build_questions() -> dict:
    return {
        name: {
            "type": "choice",
            "instructions": f"{_TASK} {question}",
            "criteria": {option: meaning for option, (_, meaning) in options.items()},
        }
        for name, (question, options) in QUESTIONS.items()
    }


def parse_answers(answers: dict) -> dict | None:
    """Turn Decision 1 choice answers into {question: {"choice", "label", "sure"}}.

    None when the model gave no usable verdict. An answer outside the options is left out.
    """
    check = {}
    for name, (_, options) in QUESTIONS.items():
        answer = answers.get(name)
        choice = getattr(answer, "choice", None)
        if getattr(answer, "type", None) != "choice" or choice not in options:
            continue
        check[name] = {
            "choice": choice,
            "label": options[choice][0],
            "sure": round(answer.confidence, 2),
        }
    return check if "verdict" in check else None


def _percent(part: dict) -> str:
    return f"{round(part['sure'] * 100)}%"


def describe(check: dict, which: str = "newest") -> str:
    """One short line for the tutor model. Empty when there was nothing to check.

    `which` is "newest" for the turn the tutor is about to answer, or "previous" when the
    check came too late for its own turn.
    """
    verdict = check["verdict"]
    if verdict["choice"] == "nothing":
        return ""
    late = " (it arrived after you answered that turn)" if which == "previous" else ""
    start = f"Work check on the student's {which} turn{late}, estimate only: "
    if verdict["choice"] == "correct":
        return start + f"looks correct ({_percent(verdict)})."
    parts = [f"probably a mistake ({_percent(verdict)})"]
    kind, place, fix = check.get("kind"), check.get("place"), check.get("fix")
    if kind and kind["choice"] != "none":
        parts.append(f"likely {kind['label']} ({_percent(kind)})")
    if place and place["choice"] != "none":
        parts.append(f"in {place['label']} ({_percent(place)})")
    line = start + ", ".join(parts) + "."
    if fix and fix["choice"] != "confirm":
        line += f" Suggested next step: have the student {fix['label']} ({_percent(fix)})."
    return line


async def check_work(
    client: genai.Client, model: str, wav: bytes, recent_text: str, jpeg: bytes | None = None
) -> dict | None:
    """Check the work in one student turn. `jpeg` is the student's page, if the camera is on."""
    content = [
        {"type": "text", "text": f"{_CONTEXT_NOTE}\n{recent_text}"},
        {"type": "audio", "mime_type": "audio/wav", "data": base64.b64encode(wav).decode()},
    ]
    if jpeg:
        content += [
            {"type": "text", "text": _PICTURE_NOTE},
            {"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()},
        ]
    response = await client.aio.decisions.create(
        model=model,
        input=content,
        questions=build_questions(),
        api_version=_API_VERSION,
        timeout=5,
    )
    return parse_answers(response.answers or {})
