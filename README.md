# Ilumina

Ilumina is a voice tutor that listens to how a student sounds, not only what they say, and changes how it teaches.

Built at VexoHacks on Pipecat, with Deepgram for all listening and speaking and Gemini for the thinking.

## How it works

- **Voice path.** Browser mic, Deepgram Flux speech to text and turn detection, a Gemini tutor model, Deepgram Aura-2 text to speech.
- **Emotion path.** The audio of each student turn goes to Gemini Decision 1, which scores confusion, frustration, confidence and engagement with a confidence value for each.
- **Voice evidence.** Deepgram Flux sends word timings with every finished turn. From them Ilumina measures speaking pace, the longest pause, filler words and how long the student waited before answering. The dashboard shows these numbers, and Decision 1 gets them as one line beside the audio.
- **Mic meter.** Once a second the bot tells the dashboard how loud the microphone is, as speech to text gets it, and logs it every 5 seconds. A silent microphone shows as "Mic is silent".
- **Two kinds of session.** The student picks one on the dashboard before starting. In **Homework** the tutor works through a problem the student brings, usually on paper in front of the camera. In **Lecture review** the tutor goes back over the newest saved class one idea at a time, with its notes and its transcript in hand. A review with no saved class starts as homework and says so.
- **Where the conversation is.** A bar at the top of the dashboard says whose turn it is: "Your turn", "Hearing you" with the words heard so far, "Heard you" while the tutor thinks, and "Ilumina is speaking". It follows the bot's own events. In a loud room Deepgram Flux can wait a long time to be sure a turn is over, so "Done talking" switches the microphone to silence until the tutor answers, which ends the turn at once.
- **State tracker.** Plain Python that smooths the scores over turns. A single odd turn is a blip. Two turns in a row, or one very confident reading, is a trend.
- **Adaptation.** Before each reply the tutor gets a one-line state note. It waits at most 0.4 seconds for it, so voice never blocks on emotion.
- **Camera path.** Optional. With the camera on, the newest frame is shown to the tutor with each student turn, replacing the one before it. Pictures are not saved, and with the camera off the tutor carries on by voice. The camera is the browser's by default. Start the bot with `ILUMINA_CAMERA=gopro` to use the head-worn GoPro from [`gopro/`](gopro/README.md) instead: the same "Turn camera on" button then starts the GoPro feed, and the panel shows the frame the tutor gets.
- **Math on screen.** The tutor may add a `[show: ...]` tag with the equation it is talking about, in LaTeX. The tag is stripped before speech and drawn on the dashboard's board, so math is spoken in plain words and shown properly. Lecture notes and study plans write math in LaTeX too. KaTeX 0.16.11 is bundled in `dashboard/vendor/katex/`, so it works offline.
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
uv run lecture.py record --text class.txt   # or a transcript you already have (skips the band and Deepgram)
uv run lecture.py plan                # a 3-day study plan from what Ilumina remembers
uv run lecture.py show                # what Ilumina remembers
uv run lecture.py forget              # delete it all
```

After a recording: Deepgram turns the sound into text, Gemini writes study notes (key ideas,
likely sticking points, check questions), and you are asked whether to save them. **Nothing
is saved on your computer unless you say yes.** The sound does go to Deepgram, and the text
to Google Gemini, before you are asked. Saved lectures go to the local `memory/` folder (never in
git), and the tutor is told about them at the start of the next session: it opens from the
most recent class, and the dashboard shows the classes it remembers and the study plan. When a
session had moments where the student sounded confused or frustrated, the dashboard asks
before it ends whether to save them, and saves only on a yes; `plan` puts those first.
`ILUMINA_MEMORY=on` in `.env` saves them without asking. The first time, macOS asks to let Terminal use
the microphone: click Allow.

## Settings

All in `.env`:

| Name | What it does |
| --- | --- |
| `DEEPGRAM_API_KEY` | Deepgram speech to text and text to speech |
| `DEEPGRAM_VOICE_ID` | Aura-2 voice, default `aura-2-helena-en` |
| `GOOGLE_API_KEY` | Google AI Studio key |
| `GOOGLE_MODEL` | Tutor brain, default `gemini-4-hydrogen` (first words in about 1.5 s). `gemini-4-argon` thinks deeper but took over 4 s |
| `DECISION_MODEL` | Emotion scoring, default `gemini-decision-1` |
| `ILUMINA_CAMERA` | `browser` (default) or `gopro` for the head-worn GoPro over USB. Needs FFmpeg (`brew install ffmpeg`) |
| `GOPRO_IP` | Only if the GoPro is not found by itself |
| `ILUMINA_MEMORY` | `on` saves the hard moments of each tutoring session to `memory/` without asking. Default `off`: the dashboard asks the student |

## Layout

| File | Job |
| --- | --- |
| `bot.py` | The Pipecat pipeline and wiring |
| `ilumina/emotion.py` | Decision 1 rubrics and the scoring call |
| `ilumina/evidence.py` | Pace, pauses, fillers and wait for one turn, from Deepgram's word timings |
| `ilumina/state.py` | State tracker, no model calls, reusable outside tutoring |
| `ilumina/headcam.py` | Runs the GoPro feed while the student has the camera on, and hands out its newest frame |
| `ilumina/processors.py` | Measures each turn's voice evidence, hands the camera picture and the state note to the tutor before each reply, and reads its teaching move after |
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
