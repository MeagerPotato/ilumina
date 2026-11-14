"""Ilumina: Ilumina, an emotionally aware voice tutor.

Voice path:   browser -> Deepgram Flux STT -> Gemini tutor -> Deepgram Aura-2 TTS -> browser
Emotion path: each student turn's audio, its measured voice features and how they
              compare with the student's usual -> Gemini Decision 1 -> StateTracker
              (Bayesian smoothing with per-state persistence)
              -> a state note for the tutor and a live message for the dashboard
Work check:   the same audio, the last lines and the camera picture -> Gemini Decision 1
              -> is the step right, what kind of mistake, where, and what to do next
              -> a note for the tutor and a live message for the dashboard
Evidence:     Deepgram Flux word timings -> pace, pauses, fillers and wait per turn
              -> shown on the dashboard and given to Decision 1 beside the audio
Camera path:  the newest camera frame is shown to the tutor with each student turn
              (the browser's camera, or the head-worn GoPro with ILUMINA_CAMERA=gopro)
Band:         with ILUMINA_BAND set, the student's Vexo band: a double tap means "done
              talking" and its light shows whose turn it is
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
# Pipecat's debug log would otherwise carry every word of the conversation. The student's
# words stay out of the log file. Must be set before the first reply is made.
os.environ.setdefault("PIPECAT_LOG_LLM_CONTEXT", "off")

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
from ilumina.baseline import SpeakerBaseline
from ilumina.emotion import score_turn
from ilumina.measured import measure_turn
from ilumina.processors import (
    BandLight,
    CameraView,
    MicLevel,
    StudentStateInjector,
    TeachingMoveTagger,
    VoiceEvidence,
)
from ilumina.prompts import (
    GREETING_NOTE,
    HOMEWORK_NOTE,
    TUTOR_SYSTEM_PROMPT,
    review_greeting,
    review_note,
)
from ilumina.state import LearningStateTracker, StateTracker, describe
from ilumina.workcheck import check_work


def _keep_words_out_of_the_log(record) -> None:
    """Pipecat's debug log prints the tutor's whole instructions (with the student's class
    notes, and in a review the transcript) and every sentence it speaks. Keep the line,
    drop the words."""
    message = record["message"]
    if record["function"] == "_compose_system_instruction":
        record["message"] = message.split(":", 1)[0] + ": instructions composed (text not logged)"
    elif "Generating TTS [" in message:
        record["message"] = message.split("[", 1)[0] + "[text not logged]"


logger.configure(patcher=_keep_words_out_of_the_log)

# The kind of session the dashboard asked for, set just before it connects. One student
# uses this bot at a time, so the next session to start is theirs.
picked = {"mode": "homework"}

headcam = None
if config.CAMERA == "gopro":
    from ilumina.headcam import HeadCam

    headcam = HeadCam()


band_link = None
if config.BAND_USB or config.BAND_NUMBER:
    from ilumina.band_link import BandLink

    band_link = BandLink(config.BAND_NUMBER, usb=config.BAND_USB)


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
    asked_for_review = picked["mode"] == "review"
    review = None
    if asked_for_review:
        try:
            review = memory.review_material()
        except Exception as e:  # noqa: BLE001 - a session still starts, as homework
            logger.warning(f"Could not read the class to review: {e}")
    mode_note = review_note(review) if review else HOMEWORK_NOTE
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
    learning_tracker = LearningStateTracker()
    baseline = SpeakerBaseline()  # this student's usual voice, for this session only
    voice_evidence = VoiceEvidence()
    state_injector = StudentStateInjector(
        wait_seconds=config.STATE_WAIT_SECONDS,
        work_check_wait_seconds=config.WORK_CHECK_WAIT_SECONDS if config.WORK_CHECK else 0,
    )
    camera_view = CameraView(headcam=headcam)
    work_checks = set()  # checks still running, held here so none is dropped part-way
    audio_buffer = AudioBufferProcessor(enable_turn_audio=True, auto_start_recording=True)
    hard_moments = []  # turns where the student sounded confused or frustrated
    kept = False

    def keep_hard_moments() -> int:
        """Save this session's hard moments to memory, once. Returns how many are saved."""
        nonlocal kept
        if not hard_moments:
            return 0
        if not kept:
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
            *([BandLight(band_link)] if band_link else []),
            camera_view,
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

    async def check_turn(wav: bytes):
        """Check the work in the turn that just ended. A failure here never stops the tutor."""
        started = time.monotonic()
        try:
            jpeg = await asyncio.to_thread(camera_view.jpeg)
            check = await check_work(
                decisions_client, config.DECISION_MODEL, wav, recent_text(context), jpeg
            )
        except Exception as e:  # noqa: BLE001 - the tutor answers without the check
            logger.warning(f"Work check failed, tutor continues without it: {e}")
            await worker.queue_frame(
                RTVIServerMessageFrame(data={"type": "work_check_error", "error": str(e)})
            )
            return
        if not check:
            return
        check["checked_ms"] = round((time.monotonic() - started) * 1000)
        check["with_picture"] = jpeg is not None
        state_injector.set_work_check(check, started)
        logger.info(f"Work check: {check}")  # option names and numbers only, never the words
        await worker.queue_frame(RTVIServerMessageFrame(data={"type": "work_check", **check}))

    # "on_user_turn_audio_data" fires the moment the student stops speaking.
    # The newer "on_user_turn_audio" only fires after the bot has replied, which
    # is too late to shape that reply. Deprecated in Pipecat 2.0; we pin <2.
    @audio_buffer.event_handler("on_user_turn_audio_data")
    async def on_user_turn_audio(buffer, audio, sample_rate, num_channels):
        """Score the turn that just ended. A failure here never stops the tutor."""
        try:
            wav = pcm_to_wav(audio, sample_rate, num_channels)
            if config.WORK_CHECK:  # runs beside the emotion scoring, not after it
                task = asyncio.create_task(check_turn(wav))
                work_checks.add(task)
                task.add_done_callback(work_checks.discard)
            evidence = voice_evidence.take()
            started = time.monotonic()
            # A few milliseconds of numpy; off the event loop so audio keeps flowing.
            measured = await asyncio.to_thread(measure_turn, wav, evidence, baseline)
            readings, learning = await score_turn(
                decisions_client,
                config.DECISION_MODEL,
                wav,
                recent_text(context),
                measured["text"],
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
        snapshot = tracker.update(readings, weight=measured["weight"])
        if learning:
            learning_state = learning_tracker.update(learning, weight=measured["weight"])
            if learning_state:
                snapshot["learning_state"] = learning_state
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
                    # Measured, not judged: voice features of this turn, clear changes
                    # from the student's usual, and how much this turn counted (0 to 1).
                    "voice": measured["voice"],
                    "vs_usual": measured["vs_usual"],
                    "weight": measured["weight"],
                    **snapshot,
                }
            )
        )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    loop = asyncio.get_running_loop()

    def from_band(message: dict):
        """A change on the Vexo band, or a double tap. Called on the band's own thread."""
        asyncio.run_coroutine_threadsafe(
            worker.queue_frame(RTVIServerMessageFrame(data=message)), loop
        )

    if band_link:
        band_link.start(from_band)

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
                    "work_check": config.WORK_CHECK,
                    "mode": "review" if review else "homework",
                    "no_class_to_review": asked_for_review and not review,
                    # With the setting on, hard moments are saved without a question.
                    "saves_without_asking": config.SAVE_MEMORY,
                }
            )
        )
        if band_link:
            # Where the band stands right now. Later changes arrive by themselves.
            await worker.queue_frame(RTVIServerMessageFrame(data=band_link.status))
        if remembered:
            # What the tutor was told it remembers, so the student can see it too.
            reviewing = (review["title"] or "your most recent class") if review else ""
            await worker.queue_frame(
                RTVIServerMessageFrame(
                    data={"type": "memory", "reviewing": reviewing, **remembered}
                )
            )
        greeting = review_greeting(review) if review else GREETING_NOTE
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
        if band_link:
            band_link.stop(from_band)
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

    from fastapi import HTTPException, Request, Response

    def only_the_dashboard(request: Request):
        # Other websites open in the same browser must not switch or see the camera,
        # or choose the kind of session.
        same_site = request.headers.get("sec-fetch-site", "same-origin") == "same-origin"
        if not same_site or request.url.hostname not in ("localhost", "127.0.0.1"):
            raise HTTPException(status_code=403)

    @app.post("/mode/{name}")
    def pick_mode(name: str, request: Request):
        """The dashboard says which kind of session it is about to start."""
        only_the_dashboard(request)
        picked["mode"] = "review" if name == "review" else "homework"
        return picked

    if headcam:

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
