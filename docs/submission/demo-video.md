# Devpost demo video (2 minutes) — this is what judges see first

Judges pick finalists from this video, so it has to carry the whole pitch with nobody in the room to explain it. Show the real app working, say the problem in the first 5 seconds, and name the sponsor tech out loud. Keep it under 2 minutes; aim for 1:50 so nothing gets cut.

Judges need to hear Ilumina's voice, and QuickTime's screen recording only records the microphone, not the Mac's sound. So play Ilumina through the MacBook speakers, not earbuds, and the mic picks up both of you. Chrome's echo cancellation usually stops Ilumina hearing itself. Do a 20 second test first: if Ilumina interrupts itself or answers its own words, switch to filming the screen with your iPhone instead, with the Mac on speakers and the iPhone's mic recording the room.

To record: QuickTime, File, New Screen Recording, Options, Microphone: MacBook microphone, then Record.

Features marked **(PR 17–19)** only appear once those pull requests are merged. If they aren't merged when you record, skip that shot and give its seconds to shot 4.

## Before you press record

1. In Terminal, in the ilumina folder: `ILUMINA_CAMERA=gopro uv run bot.py`
2. Wait about 20 seconds, then open http://localhost:7860/dashboard/ in Chrome. Make the window full screen so the dashboard is readable on a phone.
3. GoPro on the headband, plugged in by USB. Write the problem big with a thick marker, within about 30 cm of the camera.
4. Turn on Focus mode so no notifications pop up.

## Shots

| # | Time | On screen | Narration (say it live, or record it over the video afterwards) |
| --- | --- | --- | --- |
| 1 | 0:00–0:12 | Your face or the dashboard before starting | "AI tutors hear what you say. When a student says 'yeah, I think I get it' after a long pause, a human tutor backs up. An AI tutor says 'great, next problem.' Ilumina hears the difference." |
| 2 | 0:12–0:25 | Click Start session. Ilumina greets you (and names your last class if one is saved) | "Ilumina is a voice tutor. One Pipecat pipeline: Deepgram Flux listens, Gemini 4 Hydrogen thinks, Aura-2 speaks, first words in under two seconds." |
| 3 | 0:25–0:45 | Turn camera on, show the handwritten problem, ask for help. Ilumina points at the exact step | "A GoPro on my head shows it my page. Gemini 4 reads my handwriting and points at the exact step." |
| 4 | 0:45–1:15 | Answer slowly, "uh... I think so?", with a long pause. Do it twice. Point at the voice evidence, the emotion readings and confidence, then the teaching move changing and the math on the board | "Flux's word timings give my pace, my longest pause and how long I waited. Gemini scores confusion, frustration, confidence and engagement from my voice, with how sure it is. One odd turn is a blip and gets ignored. Two in a row is a trend, so Ilumina switches to a new explanation and writes the math on the board." |
| 5 | 1:15–1:25 | **(PR 17–19)** Status bar going Your turn, Hearing you, Heard you, Ilumina is speaking. Click Done talking once | "The status bar always shows whose turn it is, and Done talking ends my turn right away." |
| 6 | 1:25–1:42 | **(PR 17–19)** Switch to Lecture review and start, or show the memory panel with the saved class and study plan | "With the Vexo open kit, Ilumina listened to MIT's 18.01 lecture, wrote study notes and a study plan, and now reviews it with me. We had no band, so the Mac mic runs through Vexo's simulated band on the real protocol." |
| 7 | 1:42–1:50 | **(PR 17–19)** End session, the ask-to-save prompt | "Nothing is saved unless I say yes, and every reading is an estimate, never a fact about how I feel." |
| 8 | 1:50–1:55 | End card: "Ilumina · Pipecat · Deepgram · Gemini 4 · Vexo" | "Ilumina: a tutor that notices when you're lost, even when you say you're fine." |

## Tips

- Do two takes and keep the better one. A real pause on camera is the whole point, so don't cut it.
- If the GoPro won't connect, restart with plain `uv run bot.py` and use the C270 webcam through Chrome.
- Trim in QuickTime (Edit, Trim). Upload to YouTube as Unlisted (not Private, or judges can't watch) and paste the link into Devpost.
- Keep the file on the desktop as a backup if you're a finalist and the live demo breaks.
