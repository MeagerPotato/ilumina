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

## Shots and talking points

Say these in your own words. Times are a guide to stay under 2 minutes.

**1. Hook (0:00–0:12)** · *Show: your face or the dashboard*
- AI tutors hear what you say, not how you say it
- "Yeah, I think I get it" after a long pause means no
- A human tutor backs up, an AI tutor moves on
- Ilumina hears the difference

**2. Start (0:12–0:25)** · *Do: click Start session, Ilumina greets you*
- Voice tutor, one Pipecat pipeline
- Deepgram Flux listens and detects turns, Gemini 4 Hydrogen thinks, Deepgram Aura-2 speaks
- First words in under 2 seconds

**3. Camera (0:25–0:45)** · *Do: Turn camera on, show the big handwritten problem, ask for help*
- GoPro on your head shows Ilumina your page
- Gemini 4 reads the handwriting and points at the exact step
- Pictures are never saved

**4. Hearing hesitation (0:45–1:15)** · *Do: answer slowly with a long pause, twice. Point at the dashboard*
- Flux word timings give pace, longest pause, and wait before answering
- Gemini scores confusion, frustration, confidence and engagement from your voice, each with how sure it is
- One odd turn = blip, ignored. Two in a row = trend
- Ilumina changes its teaching move (new explanation) and writes the math on the board in LaTeX

**5. Status bar (1:15–1:25)** · **(PR 17–19)** *Do: let the bar cycle, click Done talking once*
- Bar shows whose turn it is: Your turn, Hearing you, Heard you, Ilumina is speaking
- Done talking ends your turn right away

**6. Lecture review with Vexo (1:25–1:42)** · **(PR 17–19)** *Do: switch to Lecture review, or show the memory panel*
- Vexo open kit: Ilumina listened to MIT 18.01 Lecture 3
- Wrote study notes and a study plan, now reviews them with you
- No band in hand, so the Mac mic runs through Vexo's simulated band on the real protocol

**7. Privacy (1:42–1:50)** · **(PR 17–19)** *Do: End session, show the ask-to-save prompt*
- Nothing is saved unless you say yes
- Every reading is an estimate of how you sound, not a fact about how you feel

**8. Close (1:50–1:55)** · *Show: end card "Ilumina · Pipecat · Deepgram · Gemini 4 · Vexo"*
- A tutor that notices when you're lost, even when you say you're fine

## Tips

- Do two takes and keep the better one. A real pause on camera is the whole point, so don't cut it.
- If the GoPro won't connect, restart with plain `uv run bot.py` and use the C270 webcam through Chrome.
- Trim in QuickTime (Edit, Trim). Upload to YouTube as Unlisted (not Private, or judges can't watch) and paste the link into Devpost.
- Keep the file on the desktop as a backup if you're a finalist and the live demo breaks.
