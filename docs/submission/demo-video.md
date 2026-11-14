# Devpost demo video (1 minute) — this is what judges see first

Judges pick finalists from this video, so it has to carry the whole pitch with nobody in the room to explain it. Show the real app working, say the problem in the first 5 seconds, and name the sponsor tech out loud. Keep it to 1 minute.

Judges need to hear Ilumina's voice, and QuickTime's screen recording only records the microphone, not the Mac's sound. So play Ilumina through the MacBook speakers, not earbuds, and the mic picks up both of you. Chrome's echo cancellation usually stops Ilumina hearing itself. Do a 20 second test first: if Ilumina interrupts itself or answers its own words, switch to filming the screen with your iPhone instead, with the Mac on speakers and the iPhone's mic recording the room.

To record: QuickTime, File, New Screen Recording, Options, Microphone: MacBook microphone, then Record.

Features marked **(PR 17–19)** only appear once those pull requests are merged. If they aren't merged when you record, skip that shot and give its seconds to shot 3.

## Before you press record

1. In Terminal, in the ilumina folder: `ILUMINA_CAMERA=gopro uv run bot.py`
2. Wait about 20 seconds, then open http://localhost:7860/dashboard/ in Chrome. Make the window full screen so the dashboard is readable on a phone.
3. GoPro on the headband, plugged in by USB. Write the problem big with a thick marker, within about 30 cm of the camera.
4. Turn on Focus mode so no notifications pop up.

## Shots

| # | Time | On screen | Narration (say it live, or record it over the video afterwards) |
| --- | --- | --- | --- |
| 1 | 0:00–0:07 | Dashboard, click Start session, Ilumina greets you | "AI tutors hear what you say. Ilumina hears how you say it, and changes how it teaches." |
| 2 | 0:07–0:20 | Turn camera on, show the handwritten problem, ask for help. Ilumina points at the step | "It's a voice tutor. A GoPro on my head shows it my page, and Gemini 4 reads my handwriting." |
| 3 | 0:20–0:42 | Answer slowly twice, "uh... I think so?" Show the readings and voice evidence, then the teaching move changing and the math on the board | "Deepgram Flux word timings catch my long pause. Gemini scores confusion from my voice. Two hesitant turns is a trend, so Ilumina explains it a different way and writes it on the board." |
| 4 | 0:42–0:52 | **(PR 17–19)** Lecture review switch or the memory panel with the saved class | "With the Vexo open kit, it listened to my lecture and reviews it with me. Nothing is saved without a yes." |
| 5 | 0:52–1:00 | Dashboard, end session. Optional end card: "Ilumina · Pipecat · Deepgram · Gemini 4 · Vexo" | "One Pipecat pipeline, first words in under two seconds. Ilumina: a tutor that notices when you're lost." |

## Tips

- Do two takes and keep the better one. A real pause on camera is the whole point, so don't cut it.
- If the GoPro won't connect, restart with plain `uv run bot.py` and use the C270 webcam through Chrome.
- Trim in QuickTime (Edit, Trim). Upload to YouTube as Unlisted (not Private, or judges can't watch) and paste the link into Devpost.
- Keep the file on the desktop as a backup if you're a finalist and the live demo breaks.
