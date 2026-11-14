# Ilumina

Ilumina is a voice tutor that listens to how a student sounds, not only what they say, and changes how it teaches.

Built at VexoHacks on Pipecat, with Deepgram for all listening and speaking and Gemini for the thinking.

## How it works

- **Voice path.** Browser mic, Deepgram Flux speech to text and turn detection, a Gemini tutor model, Deepgram Aura-2 text to speech.
- **Emotion path.** The audio of each student turn goes to Gemini Decision 1, which scores confusion, frustration, confidence and engagement with a confidence value for each.
- **State tracker.** Plain Python that smooths the scores over turns. A single odd turn is a blip. Two turns in a row, or one very confident reading, is a trend.
- **Adaptation.** Before each reply the tutor gets a one-line state note. It waits at most 0.4 seconds for it, so voice never blocks on emotion.
- **Camera path.** Optional. With the camera on, the newest frame is shown to the tutor with each student turn, replacing the one before it. Pictures are not saved, and with the camera off the tutor carries on by voice.
- **Dashboard feed.** Every state update is sent to the browser as a `student_state` server message.

All readings are estimates of how the student sounds, not facts about how they feel.

## Run it

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env      # then add your Deepgram and Google keys
uv sync
uv run bot.py
```

Open http://localhost:7860/dashboard/, click Start session, and talk. Use earbuds so Ilumina does not hear itself.

The dashboard shows only what the bot sends: the reading for each turn, how sure the model was, the smoothed estimate, and the one-line note Ilumina was given. The plain Pipecat test client is still at http://localhost:7860/client.

The first run downloads the voice activity model, so give it about 20 seconds.

## Settings

All in `.env`:

| Name | What it does |
| --- | --- |
| `DEEPGRAM_API_KEY` | Deepgram speech to text and text to speech |
| `DEEPGRAM_VOICE_ID` | Aura-2 voice, default `aura-2-helena-en` |
| `GOOGLE_API_KEY` | Google AI Studio key |
| `GOOGLE_MODEL` | Tutor brain, default `gemini-4-argon`. Use `gemini-4-hydrogen` if Argon is slow |
| `DECISION_MODEL` | Emotion scoring, default `gemini-decision-1` |

## Layout

| File | Job |
| --- | --- |
| `bot.py` | The Pipecat pipeline and wiring |
| `ilumina/emotion.py` | Decision 1 rubrics and the scoring call |
| `ilumina/state.py` | State tracker, no model calls, reusable outside tutoring |
| `ilumina/processors.py` | Hands the camera picture and the state note to the tutor before each reply, and reads its teaching move after |
| `ilumina/prompts.py` | Ilumina's persona and teaching rules |
| `ilumina/config.py` | Keys and model IDs from the environment |
| `dashboard/` | The live page. `vendor/pipecat.js` is `@pipecat-ai/client-js` 1.16.0 and `@pipecat-ai/small-webrtc-transport` 1.11.2 bundled with esbuild |

## Tests

```bash
uv run pytest
```
