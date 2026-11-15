"""Lecture capture through the Vexo pretend band, transcription parsing, and memory."""

import json
import math
import struct
from types import SimpleNamespace

import httpx
from vexo_open import audio

import lecture
from ilumina import memory, transcribe, vexo_band


def tone(seconds: float, freq: float = 440.0) -> bytes:
    n = int(seconds * vexo_band.SAMPLE_RATE)
    return struct.pack(
        f"<{n}h",
        *(int(8000 * math.sin(2 * math.pi * freq * i / vexo_band.SAMPLE_RATE)) for i in range(n)),
    )


def test_sound_goes_through_the_vexo_pretend_band():
    packets = vexo_band.encode_pcm(tone(2.0))
    pcm = vexo_band.record(source=iter(packets), seconds=10)
    seconds = len(pcm) / (2 * vexo_band.SAMPLE_RATE)
    assert 1.9 <= seconds <= 3.5  # the tone, plus a little silence around it
    assert audio.level_db(pcm) > -40  # the tone arrived, not the pretend band's silence


def test_transcribe_sends_wav_and_reads_paragraphs():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = request.content[:4]
        body = {
            "results": {
                "channels": [
                    {
                        "alternatives": [
                            {"transcript": "flat", "paragraphs": {"transcript": "\nTwo x.\n"}}
                        ]
                    }
                ]
            }
        }
        return httpx.Response(200, json=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert transcribe.transcribe(tone(0.1), "k", client) == "Two x."
    assert seen == {"auth": "Token k", "body": b"RIFF"}


NOTES = {
    "title": "Derivatives",
    "subject": "Calculus",
    "summary": "Slopes.",
    "key_concepts": [{"name": "Power rule", "explanation": "n x^(n-1)"}],
    "formulas": [],
    "likely_confusions": ["Forgetting to lower the power"],
    "check_questions": ["What is the derivative of x^3?"],
}


class FakeModels:
    def __init__(self, text):
        self.text, self.calls = text, []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=self.text)


def test_notes_save_and_tutor_note(tmp_path):
    client = SimpleNamespace(models=FakeModels(json.dumps(NOTES)))
    notes = memory.lecture_notes(client, "m", "today: derivatives")
    assert notes["title"] == "Derivatives"
    assert memory.tutor_note(tmp_path) == ""  # nothing saved, nothing told

    memory.save("lectures", {"source": "mic", "transcript": "t", "notes": notes}, tmp_path)
    memory.save("sessions", {"hard_moments": [{"state": "confusion", "said": "x^3?"}]}, tmp_path)
    note = memory.tutor_note(tmp_path)
    assert "Derivatives" in note and "Power rule" in note and "x^3?" in note

    memory.forget(tmp_path)
    assert memory.load("lectures", root=tmp_path) == []


def test_study_plan_uses_memory(tmp_path):
    memory.save("lectures", {"source": "mic", "transcript": "t", "notes": NOTES}, tmp_path)
    models = FakeModels("## Day 1\nPower rule")
    plan = memory.study_plan(SimpleNamespace(models=models), "m", root=tmp_path)
    assert plan.startswith("## Day 1")
    assert "Forgetting to lower the power" in models.calls[0]["contents"]


def test_a_broken_sound_source_is_reported_not_recorded_as_silence():
    def broken():
        yield vexo_band.encode_pcm(tone(0.1))[0]
        raise OSError("no microphone")

    try:
        vexo_band.record(source=broken())
    except RuntimeError as e:
        assert "no microphone" in str(e)
    else:
        raise AssertionError("record() should have raised")


def test_a_damaged_memory_file_is_skipped(tmp_path):
    (tmp_path / "lectures").mkdir()
    (tmp_path / "lectures" / "bad.json").write_text("{half")
    memory.save(
        "lectures", {"source": "mic", "transcript": "t", "notes": memory.empty_notes()}, tmp_path
    )
    assert "Untitled lecture" in memory.tutor_note(tmp_path)


def test_the_dashboard_overview_has_notes_and_the_plan_but_never_the_transcript(tmp_path):
    assert memory.overview(tmp_path) == {"lectures": [], "hard_moments": 0, "plan": ""}
    memory.save(
        "lectures", {"source": "mic", "transcript": "SECRET WORDS", "notes": NOTES}, tmp_path
    )
    (tmp_path / "study-plan.md").write_text("## Day 1\nPower rule\n")
    overview = memory.overview(tmp_path)
    memory.save("sessions", {"hard_moments": [{"state": "confusion", "said": "x^3?"}]}, tmp_path)
    overview = memory.overview(tmp_path)
    assert overview == {
        "lectures": [
            {
                "title": "Derivatives",
                "subject": "Calculus",
                "concepts": ["Power rule"],
                "sticking_points": ["Forgetting to lower the power"],
            }
        ],
        "hard_moments": 1,
        "plan": "## Day 1\nPower rule",
    }
    assert "SECRET WORDS" not in json.dumps(overview) and "x^3?" not in json.dumps(overview)

    (tmp_path / "study-plan.md").write_bytes(b"\xff\xfe plan saved in another encoding")
    assert memory.overview(tmp_path)["plan"] == ""  # unreadable plan, the rest still shows


def test_a_text_transcript_is_read_without_the_band_or_deepgram(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(lecture.config, "GOOGLE_API_KEY", "k")
    monkeypatch.setattr(lecture.config, "DEEPGRAM_API_KEY", None)  # not needed for text
    talk = tmp_path / "talk.txt"
    talk.write_text("\n  Today: the product rule.  \n")
    assert lecture.read_text(str(talk)) == "Today: the product rule."
    assert "did not come through the Vexo band" in capsys.readouterr().out

    talk.write_text("   ")
    not_text = tmp_path / "talk.docx"
    not_text.write_bytes(b"\xff\xfe\x00 not plain text")
    for path in (talk, not_text, tmp_path / "missing.txt"):
        try:
            lecture.read_text(str(path))
        except SystemExit as e:
            assert str(path) in str(e)
        else:
            raise AssertionError("read_text() should have stopped")


def test_a_lecture_review_gets_the_newest_class_in_full(tmp_path):
    from ilumina.prompts import review_greeting, review_note

    assert memory.review_material(tmp_path) is None  # no class saved, nothing to review

    def put(name, transcript, notes):  # files are named by the second, so name them here
        path = tmp_path / "lectures" / f"{name}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({"transcript": transcript, "notes": notes}))
        return path

    put("1", "old words", NOTES)
    newest = {**NOTES, "title": "Chain rule", "formulas": ["$(f(g))' = f'(g) g'$"]}
    path = put("2", "x" * 50, newest)
    review = memory.review_material(tmp_path, max_chars=20)
    assert review["title"] == "Chain rule"
    assert "Power rule" in review["notes"] and "$(f(g))' = f'(g) g'$" in review["notes"]
    assert "What is the derivative of x^3?" in review["notes"]
    assert review["transcript"] == "x" * 20 and review["cut"]  # a long class is cut, and says so

    # The tutor's instructions take the class as it is, braces and all, and say it was cut.
    note = review_note({**review, "notes": "$\\frac{d}{dx}$"})
    assert '"Chain rule"' in note and "$\\frac{d}{dx}$" in note
    assert "stops before the end of the class" in note
    assert "=== transcript starts ===\n" + "x" * 20 + "\n=== transcript ends ===" in note
    assert '"Chain rule"' in review_greeting(review)
    whole = memory.review_material(tmp_path)
    assert not whole["cut"] and "stops before the end" not in review_note(whole)

    # A damaged newest file is skipped, and a class without a title has no name to say.
    path.write_text("{not json")
    assert memory.review_material(tmp_path)["title"] == "Derivatives"
    put("3", "t", memory.empty_notes())
    untitled = memory.review_material(tmp_path)
    assert untitled["title"] == ""
    assert "Untitled" not in review_greeting(untitled) + review_note(untitled)
