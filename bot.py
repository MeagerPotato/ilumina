"""Ilumina: Ally, an emotionally aware voice tutor.

Voice path:   browser -> Deepgram Flux STT -> Gemini tutor -> Deepgram Aura-2 TTS -> browser
Emotion path: each student turn's audio -> Gemini Decision 1 -> StateTracker
              -> a state note for the tutor and a live message for the dashboard

Run with:  uv run bot.py   then open http://localhost:7860/client
"""

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
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.workers.runner import WorkerRunner

from ilumina import config
from ilumina.emotion import score_turn
from ilumina.processors import StudentStateInjector
from ilumina.prompts import GREETING_NOTE, TUTOR_SYSTEM_PROMPT
from ilumina.state import StateTracker


def recent_text(context: LLMContext, limit: int = 6) -> str:
    """The last few spoken lines, as plain text, for the emotion model."""
    lines = []
    for message in context.get_messages():
        role, content = message.get("role"), message.get("content")
        if role in ("user", "assistant") and isinstance(content, str):
            lines.append(f"{'Student' if role == 'user' else 'Tutor'}: {content}")
    return "\n".join(lines[-limit:])


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    logger.info(f"Starting Ally (tutor model: {config.GOOGLE_MODEL})")

    stt = DeepgramFluxSTTService(api_key=config.DEEPGRAM_API_KEY)
    tts = DeepgramTTSService(
        api_key=config.DEEPGRAM_API_KEY,
        settings=DeepgramTTSService.Settings(voice=config.DEEPGRAM_VOICE_ID),
    )
    llm = GoogleLLMService(
        api_key=config.GOOGLE_API_KEY,
        settings=GoogleLLMService.Settings(
            model=config.GOOGLE_MODEL,
            system_instruction=TUTOR_SYSTEM_PROMPT,
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
    state_injector = StudentStateInjector(wait_seconds=config.STATE_WAIT_SECONDS)
    audio_buffer = AudioBufferProcessor(enable_turn_audio=True, auto_start_recording=True)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            state_injector,
            llm,
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
            readings = await score_turn(
                decisions_client, config.DECISION_MODEL, wav, recent_text(context)
            )
        except Exception as e:  # noqa: BLE001 - any emotion failure must not stop the voice loop
            logger.warning(f"Emotion scoring failed, tutor continues on last state: {e}")
            await worker.queue_frame(
                RTVIServerMessageFrame(data={"type": "student_state_error", "error": str(e)})
            )
            return
        if not readings:
            return
        snapshot = tracker.update(readings)
        state_injector.set_snapshot(snapshot)
        logger.info(f"Student state: {snapshot}")
        await worker.queue_frame(RTVIServerMessageFrame(data={"type": "student_state", **snapshot}))

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        context.add_message({"role": "developer", "content": GREETING_NOTE})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Entry point used by the Pipecat runner."""
    transport_params = {
        "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    }
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
