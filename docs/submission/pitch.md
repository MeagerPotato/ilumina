# Ilumina pitch (about 2.5 minutes)

Read at a normal pace. Lines in *italics* are what to do, not what to say. Swap who says what between Allen and Aiden as you like.

---

**Hook (15 s)**

Every tutor app knows what you said. None of them know how you said it.

When a student says "yeah, I think I get it" with a long pause and a flat voice, a human tutor stops and backs up. An AI tutor says "Great! Next problem." That gap is where students quietly give up.

**What it is (20 s)**

This is Ilumina, a voice tutor that listens to how you sound, not only what you say, and changes how it teaches.

You talk to it out loud, like a real tutor. You can wear a camera on your head so it sees the page you're writing on. And it can remember the lecture you sat in this morning.

**Live demo (75 s)**

*Start a session on the dashboard. Put on the headband GoPro. Write a calculus problem in big handwriting.*

I'm working on a derivative. *Speak the problem.* Ilumina reads my handwriting from the camera and points at the exact step.

*Answer hesitantly, with a long pause.*

Watch the left side. Deepgram Flux gives us word timings for every turn, so we measure pace, the longest pause and how long I waited before answering. Gemini scores the audio of my turn for confusion, frustration, confidence and engagement, each with how sure it is.

One odd turn is a blip and Ilumina ignores it. Two in a row is a trend, and you can see it change its teaching move to a new explanation, with the math drawn on the board while it talks.

*Point at the teaching move and the board.*

**How it works (25 s)**

It's one Pipecat pipeline. Deepgram Flux for listening and turn detection, Aura-2 for the voice, and Gemini 4 Hydrogen as the tutor, with first words in about one and a half to two seconds. Emotion scoring runs as a side call, and the tutor waits at most 0.4 seconds for it, so the voice never stalls on emotion.

For lectures we used the Vexo open kit. We didn't have a band, so the Mac mic plays through Vexo's simulated band over the real Vexo protocol. Ilumina writes study notes from the lecture, asks before saving anything, and opens your next session from that class.

**Why it matters and close (15 s)**

Everything on screen is a real model output, labeled as an estimate, never a fact about how you feel. Nothing is saved unless you say yes.

Ilumina: a tutor that notices when you're lost, even when you say you're fine.
