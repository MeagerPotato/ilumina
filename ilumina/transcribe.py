"""A recorded lecture to text with Deepgram (pre-recorded audio API, one request), or with
ElevenLabs Scribe when Deepgram fails and an ElevenLabs key is set."""

import io
import wave

import httpx

URL = "https://api.deepgram.com/v1/listen"
ELEVENLABS_URL = "https://api.elevenlabs.io/v1/speech-to-text"
PARAMS = {"model": "nova-3", "smart_format": "true", "paragraphs": "true", "language": "en"}


def to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def transcript_from_response(body: dict) -> str:
    alt = body["results"]["channels"][0]["alternatives"][0]
    paragraphs = alt.get("paragraphs", {}).get("transcript")
    return (paragraphs or alt.get("transcript") or "").strip()


def transcribe(pcm: bytes, api_key: str, client: httpx.Client | None = None) -> str:
    """16 kHz mono 16 bit samples in, the lecture's text out."""
    if not api_key:
        raise RuntimeError("Set DEEPGRAM_API_KEY in .env to turn the lecture into text.")
    client = client or httpx.Client(timeout=300)
    try:
        response = client.post(
            URL,
            params=PARAMS,
            headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"},
            content=to_wav(pcm),
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = " Check DEEPGRAM_API_KEY in .env." if code in (401, 403) else ""
        raise RuntimeError(f"Deepgram said {code}: {e.response.text[:200]}.{hint}") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not reach Deepgram: {e}") from e
    return transcript_from_response(response.json())


def transcribe_elevenlabs(pcm: bytes, api_key: str, client: httpx.Client | None = None) -> str:
    """The same as `transcribe`, with ElevenLabs Scribe."""
    client = client or httpx.Client(timeout=300)
    try:
        response = client.post(
            ELEVENLABS_URL,
            headers={"xi-api-key": api_key},
            data={"model_id": "scribe_v2", "language_code": "en", "tag_audio_events": "false"},
            files={"file": ("lecture.wav", to_wav(pcm), "audio/wav")},
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        hint = " Check ELEVENLABS_API_KEY in .env." if code in (401, 403) else ""
        raise RuntimeError(f"ElevenLabs said {code}: {e.response.text[:200]}.{hint}") from e
    except httpx.HTTPError as e:
        raise RuntimeError(f"Could not reach ElevenLabs: {e}") from e
    return str(response.json().get("text") or "").strip()


def transcribe_any(pcm: bytes, deepgram_key: str | None, elevenlabs_key: str | None) -> str:
    """Deepgram first; ElevenLabs if Deepgram fails or has no key. Raises if both fail."""
    if deepgram_key:
        try:
            return transcribe(pcm, deepgram_key)
        except RuntimeError as e:
            if not elevenlabs_key:
                raise
            print(f"{e} Trying ElevenLabs instead...")
    if elevenlabs_key:
        return transcribe_elevenlabs(pcm, elevenlabs_key)
    raise RuntimeError(
        "Set DEEPGRAM_API_KEY or ELEVENLABS_API_KEY in .env to turn the lecture into text."
    )
