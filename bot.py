"""Ilumina: Ilumina, an emotionally aware voice tutor.

Voice path:   browser -> Deepgram Flux STT -> Gemini tutor -> Deepgram Aura-2 TTS -> browser
Emotion path: each student turn's audio -> Gemini Decision 1 -> StateTracker
              -> a state note for the tutor and a live message for the dashboard
Evidence:     Deepgram Flux word timings -> pace, pauses, fillers and wait per turn
              -> shown on the dashboard and given to Decision 1 beside the audio
Camera path:  the newest camera frame is shown to the tutor with each student turn
              (the browser's camera, or the head-worn GoPro with ILUMINA_CAMERA=gopro)
Move path:    the tutor tags each reply with the teaching move it chose; the tag is
              stripped before speech and shown on the dashboard

Run with:  uv run bot.py   then open http://localhost:7860/dashboard/
"""

import asyncio
import os
import time
from pathlib import Path

import certifi

# Some Python installs on macOS ship without root certificates, which makes the
# Deepgram websocket connections fail with CERTIFICATE_VERIFY_FAILED. Point
# Python at certifi's bundle unless the user already set one. Must run before
# any connection is opened.
os.environ.setdefault("SSL_CERT_FILE", certifi.where())

from fastapi.staticfiles import StaticFiles
from google import genai
from loguru import logger
from pipecat.audio.utils import pcm_to_wav
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
from pipecat.processors.frameworks.rtvi import RTVIServerMessageFrame
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.deepgram.flux.stt import DeepgramFluxSTTService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.transports.base_transport import (
    BaseTransport,
    TransportParams,
    VideoInSourceParams,
)
from pipecat.workers.runner import WorkerRunner

from ilumina import config, memory
from ilumina.emotion import score_turn
from ilumina.evidence import describe_evidence
from ilumina.processors import (
    CameraView,
    MicLevel,
    StudentStateInjector,
    TeachingMoveTagger,
    VoiceEvidence,
)
from ilumina.prompts import (
    GREETING_NOTE,
    GREETING_REVIEW_NOTE,
    HOMEWORK_NOTE,
    REVIEW_NOTE,
    TUTOR_SYSTEM_PROMPT,
)
from ilumina.state import StateTracker, describe

headcam = None
if config.CAMERA == "gopro":
    from ilumina.headcam import HeadCam

    headcam = HeadCam()


def recent_text(context: LLMContext, limit: int = 6) -> str:
    """The last few spoken lines, as plain text, for the emotion model."""
    lines = []
    for message in context.get_messages():
        if not isinstance(message, dict):
            continue  # model-specific entries, such as Gemini's thinking records, are not speech
        role, content = message.get("role"), message.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            lines.append(f"{'Student' if role == 'user' else 'Tutor'}: {content}")
    return "\n".join(lines[-limit:])


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info(f"Starting Ilumina (tutor model: {config.GOOGLE_MODEL})")
    session = object()
    if headcam:
        await asyncio.to_thread(headcam.claim, session)

    try:
        memory_note = memory.tutor_note()
    except Exception as e:  # noqa: BLE001 - memory is a bonus; the tutor must still start
        logger.warning(f"Could not read memory, starting without it: {e}")
        memory_note = ""
    try:
        remembered = memory.overview()
    except Exception as e:  # noqa: BLE001 - the panel is a bonus on top of that
        logger.warning(f"Could not read memory for the dashboard: {e}")
        remembered = None

    # The student picks homework or lecture review on the dashboard. A review needs a
    # saved class; without one the session is a homework session and says so.
    body = runner_args.body if isinstance(runner_args.body, dict) else {}
    asked_for_review = body.get("mode") == "review"
    review = None
    if asked_for_review:
        try:
            review = memory.review_material()
        except Exception as e:  # noqa: BLE001 - a session still starts, as homework
            logger.warning(f"Could not read the class to review: {e}")
    mode_note = REVIEW_NOTE.format(**review) if review else HOMEWORK_NOTE
    logger.info(f"Session mode: {'review' if review else 'homework'}")

    stt = DeepgramFluxSTTService(api_key=config.DEEPGRAM_API_KEY)
    tts = DeepgramTTSService(
        api_key=config.DEEPGRAM_API_KEY,
        settings=DeepgramTTSService.Settings(voice=config.DEEPGRAM_VOICE_ID),
    )
    llm = GoogleLLMService(
        api_key=config.GOOGLE_API_KEY,
        settings=GoogleLLMService.Settings(
            model=config.GOOGLE_MODEL,
            # Lectures the student saved from the Vexo band, and past sessions, if any.
            system_instruction=TUTOR_SYSTEM_PROMPT + memory_note + mode_note,
            # A spoken reply has to start fast. "low" is valid on every Gemini 4
            # model; left unset, Hydrogen thinks at "high" before it speaks.
            thinking=GoogleLLMService.ThinkingConfig(thinking_level="low"),
        ),
    )

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    # Emotion path
    decisions_client = genai.Client(api_key=config.GOOGLE_API_KEY)
    tracker = StateTracker()
    voice_evidence = VoiceEvidence()
    state_injector = StudentStateInjector(wait_seconds=config.STATE_WAIT_SECONDS)
    audio_buffer = AudioBufferProcessor(enable_turn_audio=True, auto_start_recording=True)
    hard_moments = []  # turns where the student sounded confused or frustrated
    kept = False

    def keep_hard_moments() -> int:
        """Save this session's hard moments to memory, once. Returns how many were saved."""
        nonlocal kept
        if kept or not hard_moments:
            return 0
        path = memory.save("sessions", {"hard_moments": hard_moments})
        kept = True
        logger.info(f"Saved {len(hard_moments)} hard moments of this session to {path}")
        return len(hard_moments)

    pipeline = Pipeline(
        [
            transport.input(),
            MicLevel(),
            stt,
            voice_evidence,
            user_aggregator,
            CameraView(headcam=headcam),
            state_injector,
            llm,
            TeachingMoveTagger(),
            tts,
            transport.output(),
            audio_buffer,
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
    )

    # "on_user_turn_audio_data" fires the moment the student stops speaking.
    # The newer "on_user_turn_audio" only fires after the bot has replied, which
    # is too late to shape that reply. Deprecated in Pipecat 2.0; we pin <2.
    @audio_buffer.event_handler("on_user_turn_audio_data")
    async def on_user_turn_audio(buffer, audio, sample_rate, num_channels):
        """Score the turn that just ended. A failure here never stops the tutor."""
        try:
            wav = pcm_to_wav(audio, sample_rate, num_channels)
            evidence = voice_evidence.take()
            started = time.monotonic()
            readings = await score_turn(
                decisions_client,
                config.DECISION_MODEL,
                wav,
                recent_text(context),
                describe_evidence(evidence) if evidence else "",
            )
            scored_ms = round((time.monotonic() - started) * 1000)
        except Exception as e:  # noqa: BLE001 - any emotion failure must not stop the voice loop
            logger.warning(f"Emotion scoring failed, tutor continues on last state: {e}")
            await worker.queue_frame(
                RTVIServerMessageFrame(data={"type": "student_state_error", "error": str(e)})
            )
            return
        if not readings:
            return
        snapshot = tracker.update(readings)
        struggling = [
            name
            for name in ("confusion", "frustration")
            if snapshot["dimensions"].get(name, {}).get("level") == "high"
        ]
        if struggling:
            hard_moments.append(
                {"state": " and ".join(struggling), "said": recent_text(context, 2)}
            )
        state_injector.set_snapshot(snapshot)
        logger.info(f"Student state: {snapshot}")
        await worker.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "student_state",
                    "note": describe(snapshot),
                    "scored_ms": scored_ms,
                    # So the dashboard knows whether there is anything to ask about saving.
                    "hard_moments": len(hard_moments),
                    **snapshot,
                }
            )
        )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Tell the dashboard which models this session is really running on.
        await worker.queue_frame(
            RTVIServerMessageFrame(
                data={
                    "type": "session_info",
                    "tutor_model": config.GOOGLE_MODEL,
                    "emotion_model": config.DECISION_MODEL,
                    "camera": config.CAMERA,
                    "mode": "review" if review else "homework",
                    "no_class_to_review": asked_for_review and not review,
                }
            )
        )
        if remembered:
            # What the tutor was told it remembers, so the student can see it too.
            reviewing = review["title"] if review else ""
            await worker.queue_frame(
                RTVIServerMessageFrame(
                    data={"type": "memory", "reviewing": reviewing, **remembered}
                )
            )
        greeting = GREETING_REVIEW_NOTE.format(title=review["title"]) if review else GREETING_NOTE
        context.add_message({"role": "developer", "content": greeting})
        await worker.queue_frames([LLMRunFrame()])

    @worker.rtvi.event_handler("on_client_message")
    async def on_client_message(rtvi, message):
        # The dashboard asks the student before a session ends. Only a yes arrives here.
        if message.type != "save_session":
            return
        try:
            await rtvi.send_server_response(message, {"saved": keep_hard_moments()})
        except Exception as e:  # noqa: BLE001 - the student must still get an answer
            logger.warning(f"Could not save this session to memory: {e}")
            await rtvi.send_error_response(message, "Could not save this session.")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        try:
            if config.SAVE_MEMORY:  # the setting saves without asking
                keep_hard_moments()
        except Exception as e:  # noqa: BLE001 - never block shutting the session down
            logger.warning(f"Could not save this session to memory: {e}")
        finally:
            await runner.cancel()

    try:
        await runner.run()
    finally:
        if headcam:
            # The camera stops with the session, however the session ended.
            await asyncio.to_thread(headcam.release, session)


async def bot(runner_args: RunnerArguments):
    """Entry point used by the Pipecat runner."""
    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            # One camera frame a second is plenty: only the newest is shown to the tutor.
            video_in_enabled=True,
            video_in_sources={"camera": VideoInSourceParams(framerate=1)},
        ),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import app, main

    # The live dashboard, served by the same local server as the bot.
    app.mount(
        "/dashboard",
        StaticFiles(directory=Path(__file__).parent / "dashboard", html=True),
        name="dashboard",
    )

    if headcam:
        from fastapi import HTTPException, Request, Response

        def only_the_dashboard(request: Request):
            # Other websites open in the same browser must not switch or see the camera.
            same_site = request.headers.get("sec-fetch-site", "same-origin") == "same-origin"
            if not same_site or request.url.hostname not in ("localhost", "127.0.0.1"):
                raise HTTPException(status_code=403)

        @app.post("/headcam/{state}")
        def switch_headcam(state: str, request: Request):
            only_the_dashboard(request)
            headcam.turn(state == "on")
            return {"on": headcam.on}

        @app.get("/headcam/frame.jpg")
        def headcam_frame(request: Request):
            """The newest GoPro frame for the dashboard preview. Empty while there is none."""
            only_the_dashboard(request)
            jpeg = headcam.jpeg()
            headers = {"X-Headcam-Status": headcam.status, "Cache-Control": "no-store"}
            if jpeg is None:
                return Response(status_code=204, headers=headers)
            return Response(jpeg, media_type="image/jpeg", headers=headers)

    main()
