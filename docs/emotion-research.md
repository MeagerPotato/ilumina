# How Ilumina reads a student, and the research behind it

Ilumina estimates how a student sounds on each turn. Every number is an estimate with
its own uncertainty, never a fact about how the student feels. This page lists the
sources each design choice comes from, and says plainly where a number is our own
tuning rather than a published value.

## The pipeline for one student turn

1. **Measured evidence (no model).**
   - From Deepgram Flux word timings (`ilumina/evidence.py`): pace, longest pause,
     total silence inside the answer, filler words, hedges such as "maybe" or "I think",
     and how long the student waited before answering.
   - From the turn's own audio (`ilumina/prosody.py`): pitch level, pitch range, pitch
     movement, the rise or fall over the last half second, loudness and its spread, and
     the voiced share of the time they were talking.
   - Against the student's own usual this session (`ilumina/baseline.py`): after three
     turns, which of those measurements are clearly away from their median.
2. **Gemini Decision 1 (`ilumina/emotion.py`).** One call with the conversation, the
   audio, and the measurements as plain text. Four score questions (confusion,
   frustration, confidence, engagement) on five-level rubrics, and one choice question
   for the learning state (engaged, confused, frustrated, bored, neutral).
3. **Tracking over turns (`ilumina/state.py`).** Bayesian smoothing of the calibrated
   probabilities, with a different persistence for each state, and a confirmed level
   that only moves when the probability has clearly moved.
4. **The tutor note.** One line, such as
   `confusion high (for 3 turns), frustration low (unsure). Overall the student sounds confused.`

## What the research says, and what we did with it

### Which states matter for learning

- **D'Mello, S. & Graesser, A. (2012). Dynamics of affective states during complex
  learning. *Learning and Instruction*, 22(2), 145–157.
  doi:[10.1016/j.learninstruc.2011.10.001](https://doi.org/10.1016/j.learninstruc.2011.10.001)**
  Their model: an engaged learner hits an impasse and becomes confused; resolving it
  returns them to engagement; failing to resolve it leads to frustration, and
  unresolved frustration to boredom. Their time series analyses confirmed
  confusion–engagement, confusion–frustration and boredom–frustration oscillations
  (abstract, [record](https://mail.editlib.org/p/110193)).
  *Used for:* the learning-state question, and the transitions in
  `LearningStateTracker`, which weight those moves double when the state changes.
  The weights are ours; the paper's abstract gives no transition probabilities.
- **Baker, R.S.J.d., D'Mello, S.K., Rodrigo, M.M.T. & Graesser, A.C. (2010). Better to
  be frustrated than bored. *International Journal of Human-Computer Studies*, 68,
  223–241. doi:[10.1016/j.ijhcs.2009.12.003](https://doi.org/10.1016/j.ijhcs.2009.12.003)**
  Across three learning environments, "boredom was very persistent ... and was
  associated with poorer learning", while "frustration was less persistent".
  Confusion and engaged concentration were the most common states.
  *Used for:* persistence differs by state. Low engagement and boredom stay longest,
  frustration fades fastest (`PERSISTENCE` and `_STATE_PERSISTENCE`). The order follows
  the paper; the exact values (0.65 to 0.85) are our tuning.
- **D'Mello, S., Lehman, B., Pekrun, R. & Graesser, A. Confusion can be beneficial for
  learning. *Learning and Instruction* (online 2012).
  doi:[10.1016/j.learninstruc.2012.05.003](https://doi.org/10.1016/j.learninstruc.2012.05.003)**
  Confusion helped learning when it was "properly induced, effectively regulated and
  ultimately resolved", and students should be "productively instead of hopelessly
  confused" ([press release](https://www.sciencedaily.com/releases/2012/06/120620103233.htm)).
  *Used for:* the tutor no longer jumps in on the first confused turn. It gives a
  smaller hint first, and changes the explanation once confusion has lasted three turns
  or comes with frustration (`LONG_CONFUSION_TURNS`, `ilumina/prompts.py`).

### How observers define the states

- **Ocumpaugh, J., Baker, R.S. & Rodrigo, M.M.T. Baker Rodrigo Ocumpaugh Monitoring
  Protocol (BROMP) 2.0 Technical and Training Manual.**
  [PDF](https://learninganalytics.upenn.edu/ryanbaker/BROMP.pdf). The coding scheme
  for engaged concentration, confusion, frustration and boredom used in classroom
  studies. Our reading of its definitions (focused attention on the task; difficulty
  understanding, including asking for help or an explanation; distress or annoyance;
  finding the activity dull or tedious) shaped the rubric wording and the
  learning-state options. We could only confirm the definitions from a summary of the
  manual's appendix, not word for word.

### What voices and words show about uncertainty

- **Liscombe, J., Hirschberg, J. & Venditti, J.J. (2005). Detecting certainness in
  spoken tutorial dialogues. *Interspeech 2005*.
  doi:[10.21437/Interspeech.2005-581](https://www.isca-archive.org/interspeech_2005/liscombe05_interspeech.html)**
  Physics tutoring (ITSPOKE corpus). Turn-level pitch, loudness, voiced-frame ratio and
  timing features, z-scored per speaker, classified certain, neutral and uncertain at
  76.4% against a 66.0% majority baseline.
  *Used for:* the turn-level voice features in `prosody.py` and comparing each turn with
  the student's own usual.
- **Pon-Barry, H. & Shieber, S.M. (2011). Recognizing uncertainty in speech. *EURASIP
  Journal on Advances in Signal Processing*, 251753.
  doi:[10.1155/2011/251753](https://doi.org/10.1155/2011/251753)** ([arXiv copy](https://arxiv.org/abs/1103.1898))
  The prosodic cues most correlated with perceived certainty were total silence
  (r = −0.643) and total duration (r = −0.592), well ahead of pitch slope (0.275).
  *Used for:* the new `silence` and `silence_share` measurements, and the rubric
  wording that names silences inside the answer. Their speech was read aloud, not
  spontaneous tutoring, so the numbers may not carry over exactly.
- **Forbes-Riley, K. & Litman, D. (2011). Using performance trajectories to analyze the
  immediate impact of user state misclassification in an adaptive spoken dialogue
  system. *SIGDIAL 2011*, 216–226.
  [PDF](https://aclanthology.org/W11-2024.pdf)**
  Summarises their earlier ITSPOKE result: adapting to uncertainty improved learning when uncertainty was labelled
  by a person, but not when the system detected it automatically, largely because the
  automatic detector caught only about 20% of uncertain turns.
  *Used for:* a reason not to over-smooth. Two agreeing turns, or one very sure turn,
  are enough to change a level, so real confusion is not held back as a blip.

### What the APIs give us

- **Gemini Decisions API, `gemini-decision-1`** ([Google blog, Nov 11, 2026](https://blog.google/innovation-and-ai/technology/developers-tools/gemini-decisions-api/)).
  Score questions return a probability for every rubric level and a probability-weighted
  score; questions in one request are independent. Latency is stated as 150–250 ms
  end to end and "nearly flat from 1 to 100 questions per request", so the extra
  learning-state question should not slow scoring. The tracker uses the full level
  probabilities as Bayesian evidence instead of one number and one confidence.
  A third-party guide ([Flavio Copes](https://flaviocopes.com/gemini-decisions-api/))
  advises keeping score scales linear and computing derived facts in code; both are
  what the rubrics and measurement lines do. We have not run a calibration check of our
  own on student audio.
- **Deepgram Flux** ([TurnInfo reference](https://developers.deepgram.com/reference/speech-to-text/listen-flux)).
  Each `EndOfTurn` carries per-word `word`, `confidence`, `start` and `end`. Flux sends
  no sentiment, emotion or pitch, so voice features are measured from the audio here.

## Tuning choices that are ours, not the papers'

| Setting | Value | Where |
| --- | --- | --- |
| Persistence per dimension | confusion 0.80, frustration 0.70, confidence 0.80, engagement 0.85 | `state.PERSISTENCE` |
| Persistence per learning state | engaged 0.80, confused 0.75, frustrated 0.65, bored 0.85, neutral 0.70 | `state._STATE_PERSISTENCE` |
| Evidence weight per turn | 0.7, halved for turns under 3 words or with too little voicing | `state.EVIDENCE_WEIGHT`, `measured.SHORT_TURN_WEIGHT` |
| Level change | new band at 60%, or 50% with this turn agreeing, or one reading 80% sure | `state.SWITCH_AT`, `MAJORITY`, `STRONG_CONFIDENCE` |
| Usual-voice thresholds | pace ±25%, pitch ±2 semitones, range ±40%, loudness ±4 dB, pauses and waits ±0.75–1 s | `baseline._CHECKS` |
| Long confusion | 3 turns | `state.LONG_CONFUSION_TURNS` |

These should be checked against labelled sessions. A good next step is to record a few
sessions, label turns by hand with the BROMP categories, and compare.

## What the dashboard receives

`student_state` keeps every field it had. These are added:

| Field | Meaning |
| --- | --- |
| `dimensions.<name>.certainty` | How sure the tracker is of `level`, 0 to 1 |
| `dimensions.<name>.bands` | Probability of `low`, `medium` and `high` |
| `dimensions.<name>.turns_at_level` | Turns in a row the level has held, 1 on the turn it changed |
| `learning_state` | Present when Decision 1 answered it: `state` (engaged, confused, frustrated, bored, neutral), `certainty`, `distribution` over all five, `reading` and `reading_confidence` for this turn alone, `turns` in this state |
| `voice` | This turn's measured voice features (`pitch_hz`, `pitch_range`, `pitch_movement`, `end_change`, `loudness`, `loudness_spread`, `voiced_share`), or `null` |
| `vs_usual` | Clear changes from the student's usual, such as `{"pace": "slower"}`; empty for the first three turns |
| `weight` | How much this turn counted, 1 or 0.5 |

`voice_evidence` adds `silence` (seconds), `silence_share` (0 to 1) and `hedges` (count).
