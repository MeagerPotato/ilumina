# How Ilumina reads a student, and the research behind it

Ilumina estimates how a student sounds on each turn. Every number is an estimate with
its own uncertainty, never a fact about how the student feels. This page lists the
sources each design choice comes from, and says plainly where a number is our own
tuning rather than a published value.

## The pipeline for one student turn

Every turn is read in three separate ways, and the voice counts most.

1. **Measured evidence (no model).**
   - From Deepgram Flux word timings (`ilumina/evidence.py`): pace, longest pause,
     total silence inside the answer, filler words, hedges such as "maybe" or "I think",
     and how long the student waited before answering.
   - From the turn's own audio (`ilumina/acoustic.py`, `ilumina/prosody.py`): an
     eGeMAPS-style set of 48 acoustic features covering pitch, loudness, voice quality,
     spectral balance and rhythm, plus the dashboard's pitch, range, end rise or fall
     and loudness.
   - Against the student's own usual this session (`ilumina/baseline.py`): after three
     turns, which measurements are clearly away from their median.
2. **Three readings (`ilumina/emotion.py`, `ilumina/voice_model.py`).**
   - *Voice channel:* Gemini Decision 1 hears the audio with the timing and acoustic
     measurements, and **no transcript or conversation**. Its rubrics describe only
     how a voice sounds.
   - *Words channel:* Gemini Decision 1 reads the conversation and the transcript, with
     **no audio**, plus the filler and hedge counts.
   - *Voice model:* a small word-blind classifier that reads the 48 acoustic features
     against the student's usual voice. Trained on acted speech from CREMA-D, EARS and
     RAVDESS; see the numbers below.
   The two Decision 1 calls run at the same time. If one fails, the turn uses the other.
3. **Fusion (`ilumina/fusion.py`).** A weighted logarithmic opinion pool of the two
   channels, weighted toward the voice, and then the voice model's likelihood ratio.
4. **Tracking over turns (`ilumina/state.py`).** Bayesian smoothing of the fused
   probabilities, with a different persistence for each state, and a confirmed level
   that only moves when the probability has clearly moved.
5. **The tutor note.** One line, such as
   `confusion high (for 3 turns), frustration low (unsure). Overall the student sounds confused.`

## Why the voice is read on its own

- **Chen, J., Guo, Z., Chun, J., Wang, P., Perrault, A. & Elsner, M. (2025). Do audio
  LLMs really LISTEN, or just transcribe? Measuring lexical vs. acoustic emotion cues
  reliance.** [arXiv:2510.10444](https://arxiv.org/abs/2510.10444).
  On their LISTEN benchmark, six audio language models, Gemini 2.5 Flash and Pro among
  them, showed "a consistent lexical dominance". They predicted "neutral" when the
  words were neutral or absent, even when the voice was emotional. When the words were
  neutral, Gemini 2.5 Pro was right 34.9% of the time from audio alone, and some models
  did *worse* once the transcript was added (Qwen2.5-Omni-7B fell from 34.0% to 19.8%).
  On non-verbal sounds such as sighs and laughs, the models were close to chance.
  *Used for:* this matches what live sessions showed, readings that follow the words.
  The voice and the words are now scored in separate calls, and code decides how much
  each counts.
  It is also why a word-blind model sits beside Decision 1: the paper found no prompt
  that fixes the bias, so we do not rely on asking the model to ignore the words.
- **Wagner, J. et al. (2023). Dawn of the transformer era in speech emotion
  recognition: closing the valence gap. *IEEE TPAMI*, 45(9), 10745–10759.
  doi:[10.1109/TPAMI.2023.3263585](https://doi.org/10.1109/TPAMI.2023.3263585)**
  Their state-of-the-art valence results came from "implicit linguistic information"
  that the transformer learned during fine-tuning. A speech model's
  pleasant-or-unpleasant reading can quietly be a reading of the words.
  *Used for:* the voice model uses hand-built acoustic features, which cannot pick up
  words, rather than a transformer speech model.
- **Eyben, F. et al. (2016). The Geneva Minimalistic Acoustic Parameter Set (GeMAPS)
  for voice research and affective computing. *IEEE Transactions on Affective
  Computing*. doi:[10.1109/TAFFC.2015.2457417](https://doi.org/10.1109/TAFFC.2015.2457417)**
  ([PDF](https://msp.utdallas.edu/publications/Eyben_2016.pdf))
  The standard small acoustic set for affect: frequency (pitch, jitter), energy
  (loudness, shimmer, harmonics-to-noise ratio), spectral balance (alpha ratio,
  Hammarberg index, spectral slopes, MFCC 1–4, flux) and temporal parameters (voiced
  and unvoiced stretch lengths, loudness peak rate). The parameters were chosen for
  their "potential to index affective physiological changes in voice production".
  *Used for:* `ilumina/acoustic.py` computes a numpy version of those groups (48
  features). It is our own implementation, not openSMILE, whose licence rules out use
  in a product. Jitter and shimmer are measured frame to frame, not cycle to cycle.
- **Pekrun, R. (2006). The control-value theory of achievement emotions. *Educational
  Psychology Review*, 18, 315–341.
  doi:[10.1007/s10648-006-9029-9](https://doi.org/10.1007/s10648-006-9029-9)**
  Sorts learning emotions by valence and activation. Anger is negative and
  activating, boredom negative and deactivating, and anxiety and hopelessness go
  with low perceived control.
  *Used for:* turning the voice model's acted emotions into tutoring evidence. An
  angrier voice than usual raises frustration. A flatter voice (neutral or sad
  profile) lowers engagement. A more fearful or sad voice lowers confidence. The voice
  model says nothing about confusion.
- **Genest, C. & Zidek, J.V. (1986). Combining probability distributions: a critique
  and an annotated bibliography. *Statistical Science*, 1(1), 114–148.** The
  logarithmic opinion pool (a weighted geometric mean of the distributions) is the
  standard way to join calibrated forecasts. *Used for:* `ilumina/fusion.py`.

## The voice model, tested

- **Data:** 10,224 clips from 222 speakers, five emotions only (angry, fearful, happy,
  neutral, sad). Disgust, calm and surprise are left out.
  - CREMA-D (Cao, H. et al. 2014. *IEEE Transactions on Affective Computing*, 5(4),
    377–390. doi:[10.1109/TAFFC.2014.2336244](https://doi.org/10.1109/TAFFC.2014.2336244);
    [repository](https://github.com/CheyneyComputerScience/CREMA-D); Open Database
    License). 91 actors say 12 neutral sentences in each emotion, so the words cannot
    give the emotion away. 6,170 clips.
  - EARS (Richter, J. et al. 2024. EARS: an anechoic fullband speech dataset benchmarked
    for speech enhancement and dereverberation. *Interspeech 2024*;
    [repository](https://github.com/facebookresearch/ears_dataset); CC BY-NC 4.0). 107
    speakers reading and improvising in anger, fear, neutral and sadness (EARS has no
    plain "happy"). Recordings are cut at pauses into 3,203 clips.
  - RAVDESS (Livingstone, S.R. & Russo, F.A. 2018. *PLoS ONE*, 13(5), e0196391.
    doi:[10.1371/journal.pone.0196391](https://doi.org/10.1371/journal.pone.0196391);
    CC BY-NC-SA 4.0). 24 actors, two neutral sentences. 851 clips.
  - `scripts/fetch_extra_speech.py` fetches EARS and RAVDESS. It was tested here on
    EARS; RAVDESS's official Zenodo download is blocked from this environment, so the
    clips used came from a GitHub mirror with the same 1,440 files.
- **Licence.** EARS and RAVDESS allow non-commercial use only (RAVDESS also asks for
  share-alike), and we cannot confirm whether trained weights count as an adapted work.
  Treat `voice_model.json` as non-commercial. For commercial use, retrain on CREMA-D
  alone: `uv run scripts/train_voice_model.py crema/` (results for that model are below).
- **Left out after testing.** TESS (2 speakers; its licence forbids derivatives) and
  the URDU dataset (its speakers each have one emotion, so a speaker's usual voice is
  that emotion and per-speaker normalisation erases it; it also has no formal licence).
- **Tests.** Five folds that hold out whole speakers; a CREMA-D test that also holds out
  the sentence; and the hardest, a whole dataset held out, so new voices, microphones and
  rooms. Features are normalised the way a live session does it, each clip only against
  the same speaker's earlier clips. The numbers are stored in `ilumina/voice_model.json`
  under `tested`.

| Shipped model, tested on | Clips | Accuracy (chance 20%) | Angry vs the rest (AUC) | Lively vs flat (AUC) | Calibration error |
| --- | --- | --- | --- | --- | --- |
| New speakers, all three datasets | 10,224 | 59.0% | 0.947 | 0.906 | 0.014 |
| New speakers, CREMA-D | 6,170 | 60.0% | 0.945 | 0.910 | 0.025 |
| New speakers, EARS (4 emotions, chance 25%) | 3,203 | 59.2% | 0.956 | 0.911 | 0.024 |
| New speakers, RAVDESS | 851 | 55.5% | 0.930 | 0.903 | 0.071 |
| New speakers and new sentences, CREMA-D | 6,170 | 57.2% | 0.934 | 0.896 | 0.023 |

Accuracy is the average of the per-emotion recalls, so every emotion counts the same.
Recalls for new speakers across all three datasets: angry 77.7%, sad 57.8%, neutral
58.5%, happy 55.6%, fearful 45.4%. An AUC is the chance that a random clip of the first
kind scores above a random clip of the second kind (0.5 is chance). "Lively" is angry,
fearful or happy; "flat" is neutral or sad. The calibration error is the gap between
the stated probability and how often the model was right, averaged over ten bins; near
0 means its probabilities can be taken at face value, which the fusion relies on. For
reference, human listeners in the CREMA-D paper recognised the intended emotion from
audio alone 40.9% of the time across six emotions; that is a different task.

**Why the extra datasets.** A student on a laptop microphone is a new dataset to the
model, so the test that matters most holds a whole dataset out. Training on more
datasets helped there, and cost some accuracy on CREMA-D itself:

| Held-out dataset | Trained on CREMA-D only | Trained on the other datasets |
| --- | --- | --- |
| EARS (all 3,203 clips) | 39.8% accuracy, angry AUC 0.867, lively AUC 0.855, calibration error 0.288 | 43.3%, 0.871, 0.872, 0.218 (CREMA-D + RAVDESS) |
| EARS improvised speech only | 41.5%, angry AUC 0.860 | 44.0%, 0.860 (CREMA-D + RAVDESS) |
| RAVDESS | 48.8%, 0.916, 0.829, 0.265 | 49.1%, 0.904, 0.884, 0.165 (CREMA-D + EARS) |
| TESS (never trained on) | 65.3%, 0.936, 0.984, 0.067 | 72.4%, 0.961, 1.000, 0.056 (all three) |
| CREMA-D, new speakers | 63.7%, 0.949, 0.919, 0.025 | 60.0%, 0.945, 0.910, 0.025 (all three) |

The gain on unfamiliar recordings is modest in accuracy (0.3 to 7.1 points) and
clearer in separating lively from flat voices (up to 0.055 AUC) and in calibration
(error down by 16% to 38%). Telling angry from the rest held steady at
0.87–0.96 everywhere except one place: on URDU's spontaneous talk-show speech, a
CREMA-D model was at chance (angry AUC 0.52 without per-speaker normalisation), so
acted speech may not carry over to natural speech, or to Urdu.

- **Speaker normalisation matters.** On CREMA-D with new speakers, comparing each clip
  only with the population gave 57.8% accuracy. Comparing it with the speaker's own
  earlier clips, as a live session does, gave 63.7%. Using all of the speaker's clips,
  which a live session cannot, gave 66.1%. In a session the usual starts at the
  population's and moves to the student's own as they talk (`SpeakerNormaliser`), and
  the voice model's evidence counts for less until then (`maturity`).
- **Sample rate.** Everything is measured at 16 kHz, the rate the model learned from.
  Pipecat's audio buffer hands each turn over at the output rate (24 kHz). Before this
  was fixed, 24 kHz turns read up to 0.8 population SDs off on quiet-loudness features
  and changed the top emotion on 4 of 50 CREMA-D clips; after it, the largest shift is
  0.02 SDs and none change (`tests/test_prosody.py`).
- **Limits.** All three datasets are acted. Students are subtler, and browser audio goes
  through echo cancellation and automatic gain control, which flattens loudness. The
  model's evidence is capped at a likelihood ratio of 4 either way, and it is one input
  among three. How well it transfers to real tutoring audio is untested; that needs
  labelled student recordings.

## Measuring the Decision 1 channels

`scripts/eval_voice_channel.py` sends a balanced CREMA-D sample through the voice
channel, the words channel and the voice model. It reports how well each separates
angry clips (frustration) and lively clips from flat ones (engagement). The sentences
are neutral, so a words channel near 0.5 AUC and a voice channel well above it would
show the split works. It needs `GOOGLE_API_KEY` and has not been run yet, because this
environment has no key. The channel weights in `fusion.py` are our choice until it
has been run.

## Earlier research behind the rubrics and the tracker

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
| Voice and words channel shares | voice 0.65, words 0.35 for frustration, confidence and engagement; voice 0.55, words 0.45 for confusion | `fusion.CHANNEL_WEIGHTS` |
| Learning-state shares | voice 0.6, words 0.4 | `fusion.LEARNING_WEIGHTS` |
| Voice model weight, once the usual is known | frustration 0.8, engagement 0.8, confidence 0.6, confusion none | `fusion.VOICE_MODEL_WEIGHT` |
| How fast the usual is trusted | population counted as 3 turns; the voice model's weight grows as turns / (turns + 3) | `voice_model.PRIOR_TURNS` |
| Cap on the voice model's evidence | likelihood ratio between 1/4 and 4, and each feature at most 3 spreads from the student's usual (no change on held-out speakers; live audio hit the old cap of 6 on most turns) | `voice_model.MAX_RATIO`, `Z_LIMIT` |
| Voice model penalty | L2 0.2 (results were flat from 0.05 to 2) | `scripts/train_voice_model.py` |

These should be checked against labelled sessions. A good next step is to record a few
sessions, label turns by hand with the BROMP categories, and compare. The channel shares
put the voice first on purpose (see Chen et al. above); `scripts/eval_voice_channel.py`
measures each channel so they can be set from data.

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
| `dimensions.<name>.sources` | Where this turn's reading came from: the voice channel's and the words channel's own 0-to-1 readings (`voice`, `words`), and the voice model's likelihood ratio against the student's usual (`voice_model`; 1 means it sounded like their usual, above 1 means more of that dimension's cue: angrier for frustration, flatter for engagement, more fearful or sad for confidence). A channel that did not answer is missing |
| `acoustic` | The voice model's reading of this turn, or `null`: `emotions` (probability of angry, fearful, happy, neutral and sad), `ratios` for frustration, engagement and confidence, and `maturity` (0 to 1, how well the student's usual is known yet) |
| `channels` | Which Decision 1 channels answered this turn, such as `["voice", "words"]` |

`voice_evidence` adds `silence` (seconds), `silence_share` (0 to 1) and `hedges` (count).
