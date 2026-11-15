"""Checks both speech services with the real keys, without printing any key.

    uv run python scripts/check_speech.py

Says whether Deepgram answers right now (what each session checks first), then makes
ElevenLabs speak a fixed test sentence and hears it back, live and as a lecture would.
"""

import asyncio
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from websockets.asyncio.client import connect  # noqa: E402

from ilumina import config, speech, transcribe  # noqa: E402

SENTENCE = "Two x plus three equals eleven, so x is four."


def elevenlabs_says(text: str) -> bytes:
    """The test sentence spoken by the backup voice, as 16 kHz mono 16 bit samples."""
    response = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}",
        params={"output_format": "pcm_16000"},
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        json={"text": text, "model_id": "eleven_flash_v2_5"},
        timeout=30,
    )
    response.raise_for_status()
    return response.content


async def elevenlabs_hears_live(pcm: bytes) -> tuple[str, int]:
    url = (
        "wss://api.elevenlabs.io/v1/speech-to-text/realtime?model_id=scribe_v2_realtime"
        "&audio_format=pcm_16000&commit_strategy=manual&include_timestamps=true"
    )
    async with connect(url, additional_headers={"xi-api-key": config.ELEVENLABS_API_KEY}) as ws:
        for i in range(0, len(pcm), 3200):  # 100 ms at a time, at real speed
            chunk = base64.b64encode(pcm[i : i + 3200]).decode()
            await ws.send(
                json.dumps(
                    {
                        "message_type": "input_audio_chunk",
                        "audio_base_64": chunk,
                        "commit": False,
                        "sample_rate": 16000,
                    }
                )
            )
            await asyncio.sleep(0.1)
        await ws.send(
            json.dumps(
                {
                    "message_type": "input_audio_chunk",
                    "audio_base_64": "",
                    "commit": True,
                    "sample_rate": 16000,
                }
            )
        )
        async with asyncio.timeout(15):
            async for raw in ws:
                data = json.loads(raw)
                if data.get("message_type") == "committed_transcript_with_timestamps":
                    timed = [w for w in data.get("words") or [] if w.get("type") == "word"]
                    return data.get("text", ""), len(timed)
                if "error" in str(data.get("message_type", "")):
                    raise RuntimeError(data)
    return "", 0


def main() -> None:
    print(
        "Keys set:",
        "Deepgram" if config.DEEPGRAM_API_KEY else "-",
        "ElevenLabs" if config.ELEVENLABS_API_KEY else "-",
    )
    if config.DEEPGRAM_API_KEY:
        started = time.monotonic()
        problem = asyncio.run(
            speech.deepgram_works(config.DEEPGRAM_API_KEY, config.DEEPGRAM_VOICE_ID)
        )
        print(
            f"Deepgram: {'works' if not problem else 'NOT working: ' + problem} ({time.monotonic() - started:.1f} s)"
        )
    if not config.ELEVENLABS_API_KEY:
        sys.exit("ElevenLabs: no ELEVENLABS_API_KEY in .env")
    pcm = elevenlabs_says(SENTENCE)
    print(f"ElevenLabs voice: spoke {len(pcm) / 32000:.1f} s of the test sentence")
    text, timed = asyncio.run(elevenlabs_hears_live(pcm))
    print(f"ElevenLabs live listening: heard {text!r} with {timed} timed words")
    print(
        f"ElevenLabs lecture text: {transcribe.transcribe_elevenlabs(pcm, config.ELEVENLABS_API_KEY)!r}"
    )


if __name__ == "__main__":
    main()
