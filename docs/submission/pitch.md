# Live demo for judging (2 minutes, then 1 minute Q&A)

In person, right after submissions close at 6 PM. This is the main pitch. Say these in your own words. Before walking up: bot running, dashboard open, GoPro on the headband, problem already written big.

**Hook (0:00–0:15)**
- AI tutors hear what you say, not how you say it
- "I think I get it" after a long pause means no; Ilumina hears that

**Start and camera (0:15–0:40)** · *Do: Start session, Turn camera on, ask for help*
- Voice tutor, GoPro on your head shows it your page
- Gemini 4 reads the handwriting and points at the exact step

**Hesitation (0:40–1:20)** · *Do: answer slowly with a long pause, twice*
- Flux word timings: pace, longest pause, wait before answering
- Gemini scores confusion, frustration, confidence, engagement, with confidence values
- One odd turn = blip; two in a row = trend, so the teaching move changes and math goes on the board

**How it's built (1:20–1:45)**
- One Pipecat pipeline: Flux STT, Gemini 4 Hydrogen tutor, Aura-2 voice
- First words in about 1.5 to 2 s; emotion runs beside the conversation, voice waits at most 0.4 s for it
- Vexo open kit: listens to your lecture, writes notes, next session opens from that class
- Nothing saved without a yes

**Close (1:45–2:00)**
- Every number on screen is a real model output, shown as an estimate
- A tutor that notices when you're lost, even when you say you're fine

## If the live demo breaks
- Play the 1 minute backup video from the desktop

## Q&A prep
- **Creepy or wrong?** Estimate of how you sound, not how you feel. Only changes the teaching move. Nothing saved without a yes, pictures never stored.
- **How accurate?** No formal accuracy test today. Smoothing makes it usable: one odd reading is ignored.
- **Slow talkers or accents?** No personal baseline yet; learning each student's normal pace is next.
- **Why not just read the words?** The words say yes; the 3 second pause says no. Flux word timings give that for free.
- **Why Hydrogen, not a bigger model?** Argon took over 4 s to start talking. In voice, latency is the product.
- **Where's the Vexo band?** Didn't have one; Mac mic through Vexo's simulated band on the real protocol. With a band it's one flag: `--band 42`.
- **Cost to run?** Not measured. Per turn: one Deepgram stream, one tutor call, one small emotion call.
