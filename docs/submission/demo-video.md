# Backup demo video (1 minute)

The video is optional, but it's the backup if the live demo fails in front of the judges. Keep it to 1 minute. Record it as soon as one clean run works.

Record on the Mac with QuickTime: File, New Screen Recording, Options, Microphone: MacBook microphone. Use earbuds so Ilumina doesn't hear itself.

Features marked **(PR 17–19)** only appear once those pull requests are merged. If they aren't merged when you record, skip that shot and give its seconds to shot 4.

## Before you press record

1. In Terminal, in the ilumina folder: `ILUMINA_CAMERA=gopro uv run bot.py`
2. Wait about 20 seconds, then open http://localhost:7860/dashboard/ in Chrome.
3. GoPro on the headband, plugged in by USB. Write the problem big with a thick marker, within about 30 cm of the camera.
4. Turn on Focus mode so no notifications pop up.

## Shots

| # | Time | On screen | Narration (say it live or record over it) |
| --- | --- | --- | --- |
| 1 | 0:00–0:08 | Dashboard, click Start session, Ilumina greets you | "Ilumina is a voice tutor that hears how you sound, not just what you say." |
| 2 | 0:08–0:22 | Turn camera on, show the handwritten problem, ask for help. Ilumina points at the step | "A GoPro on my head shows it my page, and Gemini 4 reads my handwriting." |
| 3 | 0:22–0:45 | Answer slowly twice, "uh... I think so?" Show the readings, then the teaching move changing and the math on the board | "Deepgram Flux word timings and Gemini's emotion scores show I'm confused. Two turns in a row is a trend, so Ilumina explains it a different way." |
| 4 | 0:45–0:55 | **(PR 17–19)** Status bar and Lecture review switch, or the memory panel with the saved class | "With the Vexo open kit it remembers my lecture and reviews it with me." |
| 5 | 0:55–1:00 | Dashboard, end session | "Ilumina. Built on Pipecat, Deepgram and Gemini 4." |

## Tips

- Do two takes and keep the better one.
- If the GoPro won't connect, restart with plain `uv run bot.py` and use the C270 webcam through Chrome.
- Trim in QuickTime (Edit, Trim). Upload to YouTube as Unlisted and paste the link into Devpost. Also keep the file on the desktop to play offline at judging.
