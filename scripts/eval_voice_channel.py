"""Measure how much each channel hears the voice, on clips where the words carry no emotion.

CREMA-D actors say the same neutral sentences ("Don't forget a jacket") in each
emotion, so any channel that tells an angry clip from a calm one must be hearing the
voice. This sends a balanced sample through:

- the voice channel (Decision 1 with the audio and acoustic measurements, no words),
- the words channel (Decision 1 with the sentence as a transcript, no audio),
- the word-blind voice model (speaker-normalised over each actor's earlier clips).

and reports, for each, how well its frustration and engagement readings separate the
emotions (AUC: 0.5 is chance, 1.0 is perfect) and how often its learning state is
right. It needs GOOGLE_API_KEY and costs one or two cents of Decision 1 calls.

    uv run scripts/eval_voice_channel.py crema/ --per-emotion 20

The shipped voice model was trained on every CREMA-D actor, so its numbers here are
optimistic. Use scripts/train_voice_model.py's held-out numbers for the model itself;
here it is a reference point for the two Decision 1 channels.
"""

import argparse
import asyncio
import json
import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai

from ilumina import config
from ilumina.acoustic import measure
from ilumina.emotion import score_voice, score_words
from ilumina.prosody import describe_prosody, from_analysis
from ilumina.voice_model import VoiceModel

SENTENCES = {
    "IEO": "It's eleven o'clock.",
    "TIE": "That is exactly what happened.",
    "IOM": "I'm on my way to the meeting.",
    "IWW": "I wonder what this is about.",
    "TAI": "The airplane is almost full.",
    "MTI": "Maybe tomorrow it will be cold.",
    "IWL": "I would like a new alarm clock.",
    "ITH": "I think I have a doctor's appointment.",
    "DFA": "Don't forget a jacket.",
    "ITS": "I think I've seen this before.",
    "TSI": "The surface is slick.",
    "WSI": "We'll stop in a couple of minutes.",
}
CODES = {"ANG": "angry", "FEA": "fearful", "HAP": "happy", "NEU": "neutral", "SAD": "sad"}
# What a tutor should read from each acted emotion, for scoring the learning state.
EXPECTED_STATE = {"angry": "frustrated", "sad": "bored", "neutral": "neutral"}


def auc(positive: np.ndarray, score: np.ndarray) -> float:
    order = np.argsort(score, kind="stable")
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    n_pos, n_neg = positive.sum(), (~positive).sum()
    if not n_pos or not n_neg:
        return float("nan")
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def summarise(rows: list[dict], key: str) -> dict:
    """Separation for one channel's readings: frustration for angry clips, engagement for flat."""
    emotion = np.array([r["emotion"] for r in rows])
    out = {}
    frustration = np.array([r[key].get("frustration", np.nan) for r in rows], dtype=float)
    engagement = np.array([r[key].get("engagement", np.nan) for r in rows], dtype=float)
    ok = ~np.isnan(frustration)
    if ok.any():
        out["frustration_auc_angry_vs_rest"] = round(
            auc(emotion[ok] == "angry", frustration[ok]), 3
        )
    ok = ~np.isnan(engagement)
    if ok.any():
        flat = np.isin(emotion[ok], ["neutral", "sad"])
        lively = np.isin(emotion[ok], ["angry", "fearful", "happy"])
        keep = flat | lively
        out["engagement_auc_lively_vs_flat"] = round(auc(lively[keep], engagement[ok][keep]), 3)
    states = [(r["emotion"], r[key].get("state")) for r in rows if r[key].get("state")]
    scored = [(e, s) for e, s in states if e in EXPECTED_STATE]
    if scored:
        out["learning_state_accuracy"] = round(
            sum(EXPECTED_STATE[e] == s for e, s in scored) / len(scored), 3
        )
        out["learning_state_counts"] = {
            e: {s: sum(1 for e2, s2 in states if e2 == e and s2 == s) for _, s in states}
            for e in CODES.values()
        }
    return out


async def run(folder: Path, per_emotion: int, seed: int):
    random.seed(seed)
    paths = sorted(folder.glob("*.wav"))
    by_actor: dict[str, list[Path]] = {}
    for p in paths:
        actor, _, code, _ = p.stem.split("_")
        if code in CODES:
            by_actor.setdefault(actor, []).append(p)
    # A balanced sample, at most two clips from any one actor.
    shuffled = random.sample(paths, len(paths))
    picked: dict[str, list[Path]] = {e: [] for e in CODES.values()}
    per_actor: dict[str, int] = {}
    for p in shuffled:
        actor, _, code, _ = p.stem.split("_")
        if code not in CODES or per_actor.get(actor, 0) >= 2:
            continue
        if len(picked[CODES[code]]) < per_emotion:
            picked[CODES[code]].append(p)
            per_actor[actor] = per_actor.get(actor, 0) + 1
    clips = [p for v in picked.values() for p in v]
    client = genai.Client(api_key=config.GOOGLE_API_KEY)
    rows = []
    for p in clips:
        actor, sentence, code, _ = p.stem.split("_")
        wav = p.read_bytes()
        analysis, feats = measure(wav)
        voice = from_analysis(analysis)
        # The voice model learns the actor's usual from up to 6 of their other clips first.
        model = VoiceModel()
        for other in [q for q in by_actor[actor] if q != p][:6]:
            _, f = measure(other.read_bytes())
            if f:
                model.read(f)
        acoustic = model.read(feats) if feats else None
        voice_text = describe_prosody(voice) if voice else ""
        voice_ch, words_ch = await asyncio.gather(
            score_voice(client, config.DECISION_MODEL, wav, voice_text),
            score_words(
                client, config.DECISION_MODEL, "Tutor: How is it going?", SENTENCES[sentence]
            ),
            return_exceptions=True,
        )
        row = {"clip": p.name, "emotion": CODES[code]}
        for name, ch in (("voice", voice_ch), ("words", words_ch)):
            if isinstance(ch, BaseException):
                row[name] = {"error": str(ch)}
                continue
            row[name] = {d: r.value for d, r in ch.readings.items()}
            if ch.learning:
                row[name]["state"] = max(ch.learning, key=ch.learning.get)
        if acoustic:
            # Higher ratio = more of the cue than usual: angry for frustration; for
            # engagement the cue is flatness, so its inverse is the engagement score.
            row["voice_model"] = {
                "frustration": acoustic["ratios"]["frustration"],
                "engagement": 1 / acoustic["ratios"]["engagement"],
            }
        else:
            row["voice_model"] = {}
        rows.append(row)
        print(json.dumps(row))
    summary = {k: summarise(rows, k) for k in ("voice", "words", "voice_model")}
    print(json.dumps({"clips": len(rows), **summary}, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("crema", type=Path, help="folder of CREMA-D AudioWAV files")
    parser.add_argument("--per-emotion", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if not config.GOOGLE_API_KEY:
        sys.exit("Set GOOGLE_API_KEY (for example in .env) to run this evaluation.")
    asyncio.run(run(args.crema, args.per_emotion, args.seed))


if __name__ == "__main__":
    main()
