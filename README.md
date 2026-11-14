# Ilumina

Ilumina is a voice tutor that listens to how a student sounds, not only what they say, and changes how it teaches.

Built at VexoHacks on Pipecat, with Deepgram for all listening and speaking and Gemini for the thinking.

## How it works

- **Voice path.** Browser mic, Deepgram Flux speech to text and turn detection, a Gemini tutor model, Deepgram Aura-2 text to speech.
- **Emotion path.** The audio of each student turn goes to Gemini Decision 1, which scores confusion, frustration, confidence and engagement with a confidence value for each.
- **State tracker.** Plain Python that smooths the scores over turns. A single odd turn is a blip. Two turns in a row, or one very confident reading, is a trend.
- **Adaptation.** Before each reply the tutor gets a one-line state note. It waits at most 0.4 seconds for it, so voice never blocks on emotion.
- **Camera path.** Optional. With the camera on, the newest frame is shown to the tutor with each student turn, replacing the one before it. Pictures are not saved, and with the camera off the tutor carries on by voice. The camera is the browser's by default. Start the bot with `ILUMINA_CAMERA=gopro` to use the head-worn GoPro from [`gopro/`](gopro/README.md) instead: the same "Turn camera on" button then starts the GoPro feed, and the panel shows the frame the tutor gets.
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

## Lecture capture with Vexo (no band needed)

Ilumina can listen to a class, remember it, and plan study from it. Sound goes through the
[Vexo Open kit](https://github.com/VexoAI-Org/vexo-open-kit)'s band library (`vexo-open`):
we have no band, so the Mac's microphone stands in for the band's microphone. Its sound is
turned into the band's own format (Opus, 16 kHz, 20 ms packets) and played by Vexo's pretend
band through the real Vexo protocol. With a band, add `--band 42` (your band's number) and
the same code listens to the band over Bluetooth.

```bash
uv run lecture.py record              # Mac mic; press Ctrl+C when the lecture ends
uv run lecture.py record --file class.m4a   # or a recording (plays at real speed)
uv run lecture.py plan                # a 3-day study plan from what Ilumina remembers
uv run lecture.py show                # what Ilumina remembers
uv run lecture.py forget              # delete it all
```

After a recording: Deepgram turns the sound into text, Gemini writes study notes (key ideas,
likely sticking points, check questions), and you are asked whether to save them. **Nothing
is saved on your computer unless you say yes.** The sound does go to Deepgram, and the text
to Google Gemini, before you are asked. Saved lectures go to the local `memory/` folder (never in
git), and the tutor is told about them at the start of the next session. With
`ILUMINA_MEMORY=on` in `.env`, the tutor also saves the moments a student sounded confused
or frustrated, and `plan` puts those first. The first time, macOS asks to let Terminal use
the microphone: click Allow.

## Settings

All in `.env`:

| Name | What it does |
| --- | --- |
| `DEEPGRAM_API_KEY` | Deepgram speech to text and text to speech |
| `DEEPGRAM_VOICE_ID` | Aura-2 voice, default `aura-2-helena-en` |
| `GOOGLE_API_KEY` | Google AI Studio key |
| `GOOGLE_MODEL` | Tutor brain, default `gemini-4-argon`. Use `gemini-4-hydrogen` if Argon is slow |
| `DECISION_MODEL` | Emotion scoring, default `gemini-decision-1` |
| `ILUMINA_CAMERA` | `browser` (default) or `gopro` for the head-worn GoPro over USB. Needs FFmpeg (`brew install ffmpeg`) |
| `GOPRO_IP` | Only if the GoPro is not found by itself |
| `ILUMINA_MEMORY` | `on` saves the hard moments of each tutoring session to `memory/`. Default `off` |

## Layout

| File | Job |
| --- | --- |
| `bot.py` | The Pipecat pipeline and wiring |
| `ilumina/emotion.py` | Decision 1 rubrics and the scoring call |
| `ilumina/state.py` | State tracker, no model calls, reusable outside tutoring |
| `ilumina/headcam.py` | Runs the GoPro feed while the student has the camera on, and hands out its newest frame |
| `ilumina/processors.py` | Hands the camera picture and the state note to the tutor before each reply, and reads its teaching move after |
| `ilumina/prompts.py` | Ilumina's persona and teaching rules |
| `ilumina/config.py` | Keys and model IDs from the environment |
| `lecture.py` | Record a lecture, make a study plan, show or delete memory |
| `ilumina/vexo_band.py` | Mic or file to band packets, through the Vexo band library |
| `ilumina/transcribe.py` | A recorded lecture to text with Deepgram |
| `ilumina/memory.py` | Lecture notes, opt-in memory, the tutor's memory note, study plans |
| `dashboard/` | The live page. `vendor/pipecat.js` is `@pipecat-ai/client-js` 1.16.0 and `@pipecat-ai/small-webrtc-transport` 1.11.2 bundled with esbuild |

## Tests

```bash
uv run pytest
```
