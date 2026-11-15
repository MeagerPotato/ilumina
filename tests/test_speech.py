"""Deepgram first, ElevenLabs when Deepgram is down, and the evidence from either."""

import asyncio

import httpx

from ilumina import config, speech, transcribe
from ilumina.evidence import voice_evidence


def pick(monkeypatch, problem="", wanted="auto", deepgram="dg", backup="el"):
    monkeypatch.setattr(config, "SPEECH", wanted)
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", deepgram)
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", backup)
    monkeypatch.setattr(speech, "_checked", None)
    asked = []

    async def check(key, voice):
        asked.append(key)
        return problem

    return asyncio.run(speech.choose(check)), asked


def test_deepgram_when_it_works(monkeypatch):
    assert pick(monkeypatch) == (("deepgram", ""), ["dg"])


def test_elevenlabs_when_deepgram_is_down(monkeypatch):
    (provider, reason), _ = pick(monkeypatch, problem="error 503")
    assert provider == "elevenlabs" and "503" in reason


def test_no_backup_key_means_deepgram_without_asking(monkeypatch):
    assert pick(monkeypatch, problem="error 503", backup=None) == (("deepgram", ""), [])


def test_the_setting_forces_either(monkeypatch):
    assert pick(monkeypatch, wanted="elevenlabs")[0][0] == "elevenlabs"
    assert pick(monkeypatch, wanted="deepgram", problem="error 503")[0][0] == "deepgram"


def test_no_deepgram_key_uses_the_backup(monkeypatch):
    assert pick(monkeypatch, deepgram=None)[0][0] == "elevenlabs"


def test_both_services_build(monkeypatch):
    monkeypatch.setattr(config, "DEEPGRAM_API_KEY", "dg")
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "el")
    for provider in ("deepgram", "elevenlabs"):
        stt, tts = speech.services(provider)
        assert provider in type(stt).__name__.lower() and provider in type(tts).__name__.lower()


def test_elevenlabs_word_timings_give_the_same_evidence():
    flux = {
        "words": [
            {"word": w, "start": s, "end": s + 0.3}
            for w, s in [("um", 0), ("two", 0.5), ("x", 1.4)]
        ]
    }
    eleven = {
        "words": [
            {"text": "um", "start": 0, "end": 0.3, "type": "word"},
            {"text": " ", "start": 0.3, "end": 0.5, "type": "spacing"},
            {"text": "two", "start": 0.5, "end": 0.8, "type": "word"},
            {"text": " ", "start": 0.8, "end": 1.4, "type": "spacing"},
            {"text": "x", "start": 1.4, "end": 1.7, "type": "word"},
        ]
    }
    assert voice_evidence(eleven, 1.0) == voice_evidence(flux, 1.0)
    assert voice_evidence(eleven)["fillers"] == 1


def test_a_lecture_goes_to_elevenlabs_when_deepgram_fails(monkeypatch):
    def deepgram_down(pcm, key, client=None):
        raise RuntimeError("Deepgram said 503.")

    seen = {}

    def handler(request):
        seen["key"] = request.headers["xi-api-key"]
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"text": " Two x. "})

    monkeypatch.setattr(transcribe, "transcribe", deepgram_down)
    real = transcribe.transcribe_elevenlabs
    monkeypatch.setattr(
        transcribe,
        "transcribe_elevenlabs",
        lambda pcm, key: real(pcm, key, httpx.Client(transport=httpx.MockTransport(handler))),
    )
    assert transcribe.transcribe_any(bytes(3200), "dg", "el") == "Two x."
    assert seen == {"key": "el", "url": transcribe.ELEVENLABS_URL}
