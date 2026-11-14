# Demo video: shot list and narration

Target length: 2 minutes. Record on the Mac with QuickTime (File, New Screen Recording, choose the Mac microphone under Options). Use earbuds so Ilumina doesn't hear itself.

Features marked **(PR 17–19)** are only on screen once those pull requests are merged into main. If they aren't merged when you record, skip those lines.

## Before you press record

1. In Terminal, in the ilumina folder: `ILUMINA_CAMERA=gopro uv run bot.py`
2. Wait about 20 seconds, then open http://localhost:7860/dashboard/ in Chrome.
3. GoPro on the headband, plugged in by USB. Paper and a thick marker. Write big, and keep the page within about 30 cm of the camera.
4. If you want the lecture shot: a class must be saved already (`uv run lecture.py record --text <transcript file>`, answer yes to save).
5. Close other apps and notifications (Focus mode on).

## Shots

| # | Time | On screen | Narration (voice over, or say it live) |
| --- | --- | --- | --- |
| 1 | 0:00–0:10 | Dashboard before starting, or your face | "Tutor apps know what you said. Ilumina listens to how you said it." |
| 2 | 0:10–0:25 | Click Start session. Ilumina greets you (it names your last class if one is saved) | "Ilumina is a voice tutor built on Pipecat, Deepgram and Gemini 4." |
| 3 | 0:25–0:45 | Click Turn camera on. Show the handwritten problem, ask for help | "A GoPro on my head shows Ilumina my page. It reads my handwriting and points at the exact step." |
| 4 | 0:45–1:05 | Answer slowly, with a long pause and "I think so?". Zoom or point at the voice evidence and the emotion readings | "Deepgram Flux word timings give pace, pauses and wait time. Gemini scores confusion, frustration, confidence and engagement from the audio, with how sure it is." |
| 5 | 1:05–1:25 | Do it once more so it becomes a trend. Show the teaching move changing and the LaTeX on the board | "One odd turn is a blip. Two in a row is a trend, so Ilumina switches to a new explanation and writes the math on the board." |
| 6 | 1:25–1:35 | **(PR 17–19)** Status bar going Your turn, Hearing you, Heard you, Ilumina is speaking. Click Done talking once | "The status bar shows whose turn it is, and Done talking ends my turn right away." |
| 7 | 1:35–1:50 | **(PR 17–19)** Switch to Lecture review and start a session, or show the memory panel with the saved class and study plan | "With the Vexo open kit, Ilumina listened to MIT's 18.01 lecture, wrote study notes and quizzes me on it." |
| 8 | 1:50–2:00 | **(PR 17–19)** End session, the ask-to-save prompt, click No or Yes | "Nothing is saved unless I say yes. Ilumina: a tutor that notices when you're lost." |

## Tips

- Do two takes and keep the better one. A short real pause is fine; viewers should see it's live.
- If the GoPro won't connect, switch to the C270 webcam: restart the bot with plain `uv run bot.py` and pick the webcam in Chrome.
- Trim with QuickTime (Edit, Trim). Upload to YouTube as Unlisted and paste the link into Devpost.
