"""Who hears the student and who speaks for the tutor: Deepgram, with ElevenLabs as backup.

Deepgram comes first (Flux for speech to text, Aura-2 for the voice). When a session
starts, Deepgram is asked two small, real things: to open a Flux connection and to speak
one word. If either fails and an ElevenLabs key is set, that session runs on ElevenLabs
instead (Scribe realtime for speech to text, Flash for the voice). The choice is made once
per session, so a session never changes voice half way: if Deepgram stops in the middle,
the next session picks the backup by itself.

`ILUMINA_SPEECH` can force one of them: `deepgram`, `elevenlabs`, or `auto` (the default).
"""

import asyncio

import httpx
from loguru import logger
from websockets.asyncio.client import connect

from ilumina import config

# What the dashboard shows for each, so it never names a service that is not in use.
NAMES = {
    "deepgram": "Deepgram Flux + Aura-2",
    "elevenlabs": "ElevenLabs Scribe + Flash",
}
_FLUX_URL = (
    "wss://api.deepgram.com/v2/listen?model=flux-general-en&encoding=linear16&sample_rate=16000"
)
_SPEAK_URL = "https://api.deepgram.com/v1/speak"
# A healthy Deepgram answers both in a few hundred milliseconds. The student waits for
# this before the tutor says hello, so it is kept short.
_CHECK_SECONDS = 3.0


async def _flux_opens(api_key: str) -> None:
    async with connect(_FLUX_URL, additional_headers={"Authorization": f"Token {api_key}"}):
        pass


async def _aura_speaks(api_key: str, voice: str) -> None:
    async with httpx.AsyncClient(timeout=_CHECK_SECONDS) as client:
        response = await client.post(
            _SPEAK_URL,
            params={"model": voice},
            headers={"Authorization": f"Token {api_key}"},
            json={"text": "Hi."},
        )
        response.raise_for_status()


async def deepgram_works(api_key: str, voice: str) -> str:
    """Empty when Deepgram can hear and speak right now, else why not, in a few words."""
    try:
        async with asyncio.timeout(_CHECK_SECONDS):
            await asyncio.gather(_flux_opens(api_key), _aura_speaks(api_key, voice))
    except TimeoutError:
        return f"no answer in {_CHECK_SECONDS:g} seconds"
    except httpx.HTTPStatusError as e:
        return f"error {e.response.status_code}"
    except Exception as e:  # noqa: BLE001 - any failure here means: use the backup
        return type(e).__name__
    return ""


# The last answer about Deepgram and when it came, so sessions started close together
# (or a page reloaded) do not each wait for the check.
_checked: tuple[float, str] | None = None
_REUSE_SECONDS = 60


async def choose(check=deepgram_works) -> tuple[str, str]:
    """Which one this session uses, and why when it is not simply the first choice.

    Returns ("deepgram" or "elevenlabs", reason). The reason is empty for the usual case.
    """
    global _checked
    wanted = config.SPEECH
    has_deepgram, has_backup = bool(config.DEEPGRAM_API_KEY), bool(config.ELEVENLABS_API_KEY)
    if wanted == "elevenlabs" and has_backup:
        return "elevenlabs", "picked with ILUMINA_SPEECH"
    if wanted == "deepgram" or not has_backup:
        return "deepgram", ""
    if not has_deepgram:
        return "elevenlabs", "no Deepgram key is set"
    now = asyncio.get_running_loop().time()
    if _checked and now - _checked[0] < _REUSE_SECONDS:
        problem = _checked[1]
    else:
        problem = await check(config.DEEPGRAM_API_KEY, config.DEEPGRAM_VOICE_ID)
        _checked = (now, problem)
    if problem:
        logger.warning(f"Deepgram is not working ({problem}); this session uses ElevenLabs")
        return "elevenlabs", f"Deepgram is not answering ({problem})"
    return "deepgram", ""


def services(provider: str):
    """The speech-to-text and text-to-speech services of one provider, for one session."""
    if provider == "elevenlabs":
        # Imported here so a setup without the ElevenLabs extra still runs on Deepgram.
        from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
        from pipecat.services.elevenlabs.tts import ElevenLabsTTSService

        stt = ElevenLabsRealtimeSTTService(
            api_key=config.ELEVENLABS_API_KEY,
            # Word timings, for the same measured evidence Flux gives (pace, pauses).
            include_timestamps=True,
        )
        tts = ElevenLabsTTSService(
            api_key=config.ELEVENLABS_API_KEY,
            settings=ElevenLabsTTSService.Settings(voice=config.ELEVENLABS_VOICE_ID),
        )
        return stt, tts
    from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
    from pipecat.services.deepgram.tts import DeepgramTTSService

    stt = DeepgramFluxSTTService(api_key=config.DEEPGRAM_API_KEY)
    tts = DeepgramTTSService(
        api_key=config.DEEPGRAM_API_KEY,
        settings=DeepgramTTSService.Settings(voice=config.DEEPGRAM_VOICE_ID),
    )
    return stt, tts
