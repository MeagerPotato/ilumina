# Ilumina finalist live demo (2 minutes, then 1 minute Q&A)

Only needed if we make the finals: judges first pick from the Devpost video (see demo-video.md), then finalists get 2 minutes of live demo and 1 minute of questions. Mostly show, barely tell. Lines in *italics* are actions. Allen drives the demo, Aiden talks (or swap).

Have the bot running, the dashboard open on Start session, the GoPro on the headband and a problem already written big on paper before you walk up.

---

**0:00 Hook (15 s)**

Every tutor app knows what you said. None of them know how you said it. When a student says "yeah, I think I get it" after a long pause, a human tutor backs up. An AI tutor says "Great, next problem." Ilumina hears the difference.

**0:15 Start talking (25 s)**

*Click Start session. Ilumina greets you by voice, and names your last class if one is saved. Click Turn camera on.*

It's a voice tutor. Allen just talks to it, and the GoPro on his head shows it his page.

*Allen: "Can you help me with this derivative?"* Ilumina reads the handwriting and points at the exact step.

**0:40 The emotional part (40 s)**

*Allen answers slowly, with a long pause, "uh... I think so?" Do it twice.*

Look at the dashboard. Deepgram Flux gives word timings, so we measure pace, the longest pause and how long he waited. Gemini scores the audio for confusion, frustration, confidence and engagement, each with how sure it is.

One odd turn is a blip and gets ignored. Two in a row is a trend, so Ilumina changes its teaching move, here to a new explanation, and writes the math on the board while it talks.

**1:20 How it's built (25 s)**

One Pipecat pipeline. Deepgram Flux listens and detects turns, Aura-2 is the voice, Gemini 4 Hydrogen is the tutor, with first words in about 1.5 to 2 seconds. Emotion runs beside the conversation, so the voice never waits more than 0.4 seconds for it.

And with the Vexo open kit, Ilumina listens to your lecture, writes study notes, and opens your next session from that class. Nothing is saved unless you say yes.

**1:45 Close (15 s)**

Every number on screen is a real model output, shown as an estimate, never a fact about how you feel. Ilumina: a tutor that notices when you're lost, even when you say you're fine.

---

## If the live demo breaks

Say "here's the same thing recorded an hour ago" and play the 1 minute video. Keep talking over it with the script above.

## Q&A prep (1 minute, keep answers to one or two sentences)

- **Isn't reading emotion creepy or wrong?** It's labeled as an estimate of how you sound, not how you feel. It only changes the teaching move, nothing is saved without a yes, and camera pictures are never stored.
- **How accurate is it?** We didn't run a formal accuracy test today. What makes it usable is smoothing: one odd reading is ignored, and the tutor only changes course on a trend.
- **What about slow talkers or accents?** Right now it doesn't know your personal baseline. Learning each student's normal pace is the next thing we'd build.
- **Why not just read the words?** "I think I get it" says yes. The 3 second pause before it says no. Flux's word timings give us that pause for free.
- **Why Hydrogen and not a bigger model?** Argon gave deeper answers but took over 4 seconds to start talking. In voice, latency is the product.
- **Where's the Vexo band?** We didn't have one, so the Mac mic runs through Vexo's simulated band on the real Vexo protocol. With a band it's one flag: `--band 42`.
- **What does it cost to run?** Not measured yet. Per turn it's one Deepgram stream, one tutor call and one small emotion call.
