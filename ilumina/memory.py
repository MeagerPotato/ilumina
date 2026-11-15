"""Ilumina's memory: lectures heard through the Vexo band, tutoring sessions, study plans.

Nothing is saved on this computer unless the student says yes. (The sound always goes to
Deepgram for text, and the text to Google Gemini for notes, before the student is asked.) Lectures are saved only after the student
agrees at the end of `lecture.py record` (or passes --save). The hard moments of a
tutoring session are saved only when the student says yes on the dashboard as the session
ends, or when ILUMINA_MEMORY=on is set in .env. Everything stays in the local `memory/`
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
PLAN_PATH = MEMORY_DIR / "study-plan.md"

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
a lecture, say so in the summary and leave the lists short. Write every formula and math \
expression in LaTeX between single dollar signs, like $x^2$ or $\\frac{{u}}{{v}}$. Keep \
the title in plain words with no LaTeX, because the tutor says it aloud.

Transcript:
{transcript}"""

PLAN_PROMPT = """You are Ilumina, a math tutor. Write a short study plan for your student \
for the next {days} days, in Markdown.

Use what the student heard in class (lecture notes, recorded by their Vexo band) and how \
their tutoring sessions went (moments where they sounded confused or frustrated). Put the \
ideas they struggled with first. For each day give one goal, two or three concrete \
practice tasks, and one question to check they got it. End with one line on what you \
will watch for in the next tutoring session. Keep it under 300 words. Write every formula \
and math expression in LaTeX between single dollar signs, like $x^2$.

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
    if not response.text:
        raise RuntimeError("Gemini returned no notes.")
    return json.loads(response.text)


def empty_notes() -> dict:
    """Notes for a lecture whose notes could not be made: the transcript is still kept."""
    return {
        "title": "Untitled lecture",
        "subject": "unknown",
        "summary": "No notes yet; the transcript is saved.",
        "key_concepts": [],
        "formulas": [],
        "likely_confusions": [],
        "check_questions": [],
    }


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
    records = []
    for p in paths:
        try:
            records.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue  # a damaged file is skipped, never fatal
    return records


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
        n = lec.get("notes") or {}
        concepts = ", ".join(c.get("name", "") for c in n.get("key_concepts", [])[:6])
        lines.append(f'- Class "{n.get("title", "untitled")}": {concepts or "no notes"}.')
        if n.get("likely_confusions"):
            lines.append(f"  Likely sticking points: {'; '.join(n['likely_confusions'][:3])}.")
    for s in sessions:
        for moment in s.get("hard_moments", [])[-2:]:
            lines.append(
                f"- Earlier session, they struggled ({moment.get('state', '?')}) here: "
                f"{str(moment.get('said', ''))[:200]}"
            )
    return "\n".join(lines)


def review_material(root: Path = MEMORY_DIR, max_chars: int = 60_000) -> dict | None:
    """The newest class in full, for a lecture review session: its title (empty when the
    class has none), the notes, the transcript, and whether the transcript was cut.
    None when no class is saved."""
    lectures = load("lectures", root=root)  # all of them, so a damaged newest file is skipped
    if not lectures:
        return None
    n = lectures[-1].get("notes") or {}
    lines = [n.get("summary", "")]
    lines += [
        f"- {c.get('name', '')}: {c.get('explanation', '')}" for c in n.get("key_concepts", [])
    ]
    for label, key in (
        ("Formulas", "formulas"),
        ("Likely sticking points", "likely_confusions"),
        ("Questions you can ask", "check_questions"),
    ):
        if n.get(key):
            lines.append(f"{label}: {'; '.join(n[key])}")
    title = n.get("title", "")
    transcript = str(lectures[-1].get("transcript", ""))
    return {
        "title": "" if title == empty_notes()["title"] else title,
        "notes": "\n".join(filter(None, lines)),
        # A long class is cut so that a spoken reply still starts quickly.
        "transcript": transcript[:max_chars],
        "cut": len(transcript) > max_chars,
    }


def overview(root: Path = MEMORY_DIR, limit: int = 3) -> dict:
    """What the dashboard shows of memory: what `tutor_note` tells the tutor, as data,
    plus the newest study plan if one was made. Notes only, never a transcript."""
    lectures = []
    for lec in load("lectures", limit, root):
        n = lec.get("notes") or {}
        lectures.append(
            {
                "title": n.get("title", "untitled"),
                "subject": n.get("subject", ""),
                "concepts": [c.get("name", "") for c in n.get("key_concepts", [])[:6]],
                "sticking_points": n.get("likely_confusions", [])[:3],
            }
        )
    hard_moments = sum(len(s.get("hard_moments", [])[-2:]) for s in load("sessions", limit, root))
    try:
        plan = (root / PLAN_PATH.name).read_text().strip()
    except (OSError, ValueError):  # missing, or not readable as text
        plan = ""
    return {"lectures": lectures, "hard_moments": hard_moments, "plan": plan}


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
    if not response.text:
        raise RuntimeError("Gemini returned no study plan. Try again.")
    return response.text.strip()
