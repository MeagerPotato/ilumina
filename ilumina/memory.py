"""Ilumina's memory: lectures heard through the Vexo band, tutoring sessions, study plans.

Nothing is saved unless the student says yes. Lectures are saved only after the student
agrees at the end of `lecture.py record` (or passes --save). Tutoring sessions are saved
only when ILUMINA_MEMORY=on is set in .env. Everything stays in the local `memory/`
folder (not in git); `uv run lecture.py forget` deletes it all.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"

NOTES_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "subject": {"type": "string"},
        "summary": {"type": "string", "description": "Three to five sentences."},
        "key_concepts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["name", "explanation"],
            },
        },
        "formulas": {"type": "array", "items": {"type": "string"}},
        "likely_confusions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Steps or ideas a student is likely to get stuck on.",
        },
        "check_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short questions a tutor can ask to check understanding.",
        },
    },
    "required": [
        "title",
        "subject",
        "summary",
        "key_concepts",
        "likely_confusions",
        "check_questions",
    ],
}

NOTES_PROMPT = """Below is the transcript of a lecture or class conversation, recorded by \
the student's Vexo band. Turn it into study notes for an AI tutor that will later help \
this student. Use only what is in the transcript. If the transcript is too short or not \
a lecture, say so in the summary and leave the lists short.

Transcript:
{transcript}"""

PLAN_PROMPT = """You are Ilumina, a math tutor. Write a short study plan for your student \
for the next {days} days, in Markdown.

Use what the student heard in class (lecture notes, recorded by their Vexo band) and how \
their tutoring sessions went (moments where they sounded confused or frustrated). Put the \
ideas they struggled with first. For each day give one goal, two or three concrete \
practice tasks, and one question to check they got it. End with one line on what you \
will watch for in the next tutoring session. Keep it under 300 words.

Lecture notes:
{lectures}

Tutoring sessions:
{sessions}"""


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def _config(**extra) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_level="low"), **extra
    )


def lecture_notes(client: genai.Client, model: str, transcript: str) -> dict:
    response = client.models.generate_content(
        model=model,
        contents=NOTES_PROMPT.format(transcript=transcript),
        config=_config(response_mime_type="application/json", response_json_schema=NOTES_SCHEMA),
    )
    return json.loads(response.text)


def save(kind: str, record: dict, root: Path = MEMORY_DIR) -> Path:
    folder = root / kind
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{_now()}.json"
    path.write_text(json.dumps({"saved_at": _now(), **record}, indent=2))
    return path


def load(kind: str, limit: int | None = None, root: Path = MEMORY_DIR) -> list[dict]:
    folder = root / kind
    if not folder.is_dir():
        return []
    paths = sorted(folder.glob("*.json"))
    if limit:
        paths = paths[-limit:]
    return [json.loads(p.read_text()) for p in paths]


def forget(root: Path = MEMORY_DIR) -> None:
    shutil.rmtree(root, ignore_errors=True)


def tutor_note(root: Path = MEMORY_DIR, limit: int = 3) -> str:
    """A short block for the tutor's instructions: what the student heard in class lately.
    Empty when nothing was saved."""
    lectures = load("lectures", limit, root)
    sessions = load("sessions", limit, root)
    if not lectures and not sessions:
        return ""
    lines = [
        (
            "\n\nWhat you remember about this student (from their Vexo band and past "
            "sessions). Use it to connect to what they heard in class; do not recite it."
        )
    ]
    for lec in lectures:
        n = lec["notes"]
        concepts = ", ".join(c["name"] for c in n.get("key_concepts", [])[:6])
        lines.append(f'- Class "{n["title"]}": {concepts}.')
        if n.get("likely_confusions"):
            lines.append(f"  Likely sticking points: {'; '.join(n['likely_confusions'][:3])}.")
    for s in sessions:
        for moment in s.get("hard_moments", [])[-2:]:
            lines.append(
                f"- Earlier session, they struggled ({moment['state']}) here: "
                f"{moment['said'][:200]}"
            )
    return "\n".join(lines)


def _lectures_text(lectures: list[dict]) -> str:
    if not lectures:
        return "(none saved)"
    return "\n\n".join(json.dumps(lec["notes"], indent=1) for lec in lectures)


def _sessions_text(sessions: list[dict]) -> str:
    moments = [m for s in sessions for m in s.get("hard_moments", [])]
    if not moments:
        return "(no hard moments saved)"
    return "\n".join(f"- {m['state']}: {m['said'][:300]}" for m in moments[-12:])


def study_plan(client: genai.Client, model: str, days: int = 3, root: Path = MEMORY_DIR) -> str:
    lectures, sessions = load("lectures", 5, root), load("sessions", 5, root)
    if not lectures and not sessions:
        raise RuntimeError(
            "Nothing in memory yet. Record a lecture first: uv run lecture.py record"
        )
    response = client.models.generate_content(
        model=model,
        contents=PLAN_PROMPT.format(
            days=days, lectures=_lectures_text(lectures), sessions=_sessions_text(sessions)
        ),
        config=_config(),
    )
    return response.text.strip()
