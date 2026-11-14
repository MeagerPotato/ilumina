# Devpost submission

Copy each section into the matching Devpost field.

## Project name

Ilumina

## Tagline (short description)

A voice tutor that hears how you sound, not just what you say, and changes how it teaches.

## Inspiration

A good tutor doesn't wait for you to say "I'm lost." They hear it: the long pause before you answer, the "yeah, I think so" that means no, the voice that gets flatter every problem. AI tutors today only read the words, so they cheer you on right up to the moment you quit.

We wanted a tutor that notices what a person would notice, and that you can talk to with your hands busy on a page of math, the way real studying works.

## What it does

Ilumina is a real-time voice tutor for math.

- **You talk, it talks back.** A natural voice conversation with first words in about 1.5 to 2 seconds.
- **It hears how you sound.** Every turn, Ilumina measures your speaking pace, your longest pause and how long you waited before answering, and Gemini scores the audio for confusion, frustration, confidence and engagement, each with how sure it is.
- **Blip or trend.** One odd turn is a blip and gets ignored. Two in a row, or one very confident reading, is a trend, and the tutor changes its teaching move: a smaller hint, a new explanation, a worked example, a harder problem or a check-in.
- **It sees your work.** A GoPro on a headband (or any webcam) shows Ilumina your page. It reads your handwriting and points at the exact step. Pictures are never saved.
- **Math on the board.** While it talks, the equation it means appears on the dashboard in LaTeX, so it speaks math in plain words and shows it properly.
- **It remembers your class.** With the Vexo open kit, Ilumina listens to a lecture, writes study notes (key ideas, sticking points, check questions), makes a 3-day study plan, and opens your next session from that class. Lecture review mode quizzes you on it; we used MIT 18.01 Lecture 3.
- **You stay in control.** Nothing is saved unless you say yes. Every reading is shown as an estimate of how you sound, never a fact about how you feel.
- **A live dashboard** shows every real model output: the per-turn reading and confidence, the smoothed state, the voice evidence, the teaching move, a mic meter, and whose turn it is.

## How we built it

- **Pipecat** runs the whole thing as one pipeline on a laptop, with a browser client over SmallWebRTC.
- **Deepgram Flux** does speech to text and turn detection, and its word timings feed our voice evidence (pace, longest pause, wait before answering). **Deepgram Aura-2** is Ilumina's voice.
- **Gemini 4 Hydrogen** is the tutor brain. We tried Gemini 4 Argon, which thinks deeper, but its first words took over 4 seconds; Hydrogen gets there in about 1.5 to 2.
- **Gemini Decision 1** scores each student turn from the audio plus the voice evidence, against rubrics for confusion, frustration, confidence and engagement, with a confidence value for each.
- **A plain Python state tracker** smooths those scores across turns into blip or trend, with no model calls, so it's cheap and predictable.
- **Never block the voice.** Emotion scoring runs beside the conversation. The tutor waits at most 0.4 seconds for the state note before replying, so a slow score never makes Ilumina go quiet.
- **Camera:** a GoPro over USB, read with FFmpeg, hands the newest frame to Gemini with each turn. A C270 webcam or the browser camera works too.
- **Vexo:** we didn't have a band, so we ran the Mac microphone through the Vexo open kit's simulated band, turned into the band's own format (Opus, 16 kHz, 20 ms packets) over the real Vexo protocol. With a real band the same code listens over Bluetooth.
- **Gemini** turns lecture transcripts into study notes and study plans. KaTeX draws the math, bundled so it works offline.
- The dashboard is plain HTML and JavaScript fed by Pipecat RTVI server messages.

## Challenges we ran into

- **Speed versus depth.** The deeper Gemini model gave better answers but a 4-second pause feels broken in a voice conversation. We switched to Hydrogen and kept emotion scoring off the critical path.
- **Not overreacting.** A tutor that changes course on every reading feels jumpy, so we built the blip-versus-trend tracker before wiring in adaptation.
- **Seeing handwriting.** A head-worn camera sees the page at an angle and from a distance. Big handwriting within about 30 cm reads reliably; small writing doesn't, so we tell the student to hold it closer.
- **No band in hand.** We built the lecture path against the Vexo simulated band so it works today and with real hardware later.
- **Filler words disappear.** Deepgram Flux drops "um" and "uh" from transcripts, so pauses and wait time carry the hesitation signal instead.
- **The small stuff:** macOS root certificates, the Decisions API needing the v1beta endpoint, and the tutor hearing itself through laptop speakers (earbuds fix it).

## Accomplishments that we're proud of

- First words in about 1.3 to 2.1 seconds, measured live, while scoring emotion on every turn.
- A tutor that really reads a handwritten calculus problem from a camera on your head.
- Every number on the dashboard is a real model output, not a mock.
- Privacy by default: nothing saved without a yes, pictures never stored.

## What we learned

- How someone says something carries information the words don't, and word timings alone (pauses, wait time) are a strong signal.
- In voice, latency is the product. Anything slow has to run beside the conversation, not in it.
- Smoothing matters as much as scoring: a tutor that reacts to every reading feels anxious, not caring.

## What's next for Ilumina

- Run on a real Vexo band, so Ilumina can follow a whole school day of lectures.
- Learn each student's own baseline, so a naturally slow talker isn't read as confused.
- Track progress across sessions and focus study plans on the moments a student struggled.
- More subjects beyond math.

## Built with

pipecat, deepgram, deepgram-flux, deepgram-aura, gemini, gemini-4, google-ai-studio, python, uv, javascript, html, css, katex, webrtc, ffmpeg, gopro, vexo

## Track notes (for the "which prizes" field or the judges)

- **Google DeepMind, Best Use of Gemini 4:** Gemini 4 Hydrogen is the tutor and sees the student's handwriting each turn. Gemini Decision 1 scores emotion from audio plus voice evidence. Gemini also writes lecture notes and study plans.
- **Deepgram, Best Voice on Pipecat:** Flux handles listening and turn detection, and its word timings are our voice evidence. Aura-2 is the voice. All in one Pipecat pipeline with first words in about 1.5 to 2 seconds.
- **Vexo main track:** the lecture path runs through the Vexo open kit's band library and protocol, with the Mac mic standing in for the band, ready for a real band with one flag.

## Links to add

- Demo video (YouTube, Unlisted)
- GitHub: https://github.com/MeagerPotato/ilumina
- Landing page: Aiden's page from PR 7 (screenshots or the HTML file, since we are not hosting)
