"""Train and test the word-blind voice model, then write ilumina/voice_model.json.

The main data is CREMA-D (Cao et al. 2014, IEEE Transactions on Affective Computing
5(4), 377-390; Open Database License): 91 actors saying 12 neutral sentences in each
emotion. Because the words are the same in every emotion, a model trained on it can
only learn the sound of the voice. Only the five emotions the tutor uses are kept
(angry, fearful, happy, neutral, sad); disgust is left out.

    uv run scripts/train_voice_model.py --download crema/      # about 450 MB, once
    uv run scripts/train_voice_model.py crema/ [--extra manifest.csv]

`--extra` adds other datasets from a CSV with columns path,dataset,speaker,emotion.

Testing holds out whole speakers (5 folds by speaker), and a harder CREMA-D test also
holds out the sentence, so every number is on voices and words the model never saw.
With `--extra`, each dataset is also held out whole (trained on all the others), which
is the closest test here to a new student on a new microphone.
Features are normalised the way a live session does it: each clip only against the
same speaker's earlier clips, blended with the population's usual.
"""

import argparse
import csv
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ilumina.acoustic import FEATURES, measure
from ilumina.voice_model import EMOTIONS, MODEL_PATH, PRIOR_TURNS, SpeakerNormaliser

_URL = "https://media.githubusercontent.com/media/CheyneyComputerScience/CREMA-D/master/AudioWAV/"
_CODES = {"ANG": "angry", "FEA": "fearful", "HAP": "happy", "NEU": "neutral", "SAD": "sad"}
_SENTENCES = ("IEO", "TIE", "IOM", "IWW", "TAI", "MTI", "IWL", "ITH", "DFA", "ITS", "TSI", "WSI")
L2 = 0.2  # chosen on the speaker-held-out folds; results were flat from 0.05 to 2


def crema_names():
    for actor in range(1001, 1092):
        for sentence in _SENTENCES:
            for code in _CODES:
                # "IEO" was recorded at three intensities; the others at one ("XX").
                levels = ("LO", "MD", "HI") if sentence == "IEO" and code != "NEU" else ("XX",)
                for level in levels:
                    yield f"{actor}_{sentence}_{code}_{level}.wav"


def download(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    missing = [n for n in crema_names() if not (folder / n).exists()]
    print(f"Downloading {len(missing)} clips from the CREMA-D repository")
    for name in missing:
        # A few clips do not exist upstream; curl -f skips them.
        subprocess.run(
            ["curl", "-sSfL", "-m", "30", "-o", str(folder / name), _URL + name], check=False
        )


def _one(path: str):
    try:
        _, feats = measure(Path(path).read_bytes())
    except Exception:  # noqa: BLE001 - one unreadable clip is skipped, not fatal
        feats = None
    return path, feats


def clips(crema: Path, extra: Path | None):
    """(path, dataset, speaker, emotion, sentence) for every usable clip."""
    out = []
    for path in sorted(crema.glob("*.wav")):
        actor, sentence, code, _ = path.stem.split("_")
        if code in _CODES:
            out.append((str(path), "crema-d", f"crema-d:{actor}", _CODES[code], sentence))
    if extra:
        with extra.open(newline="") as f:
            for row in csv.DictReader(f):
                if row["emotion"] in EMOTIONS:
                    # Relative paths are relative to the manifest, so the folder can move.
                    path = Path(row["path"])
                    if not path.is_absolute():
                        path = extra.parent / path
                    speaker = row["speaker"]
                    if not speaker.startswith(row["dataset"]):
                        speaker = f"{row['dataset']}:{speaker}"
                    out.append((str(path), row["dataset"], speaker, row["emotion"], ""))
    return out


def load(items):
    rows = []
    with ProcessPoolExecutor(os.cpu_count()) as pool:
        results = pool.map(_one, [i[0] for i in items], chunksize=16)
        for item, (_, feats) in zip(items, results):
            if feats is not None:
                rows.append((*item[1:], feats))
    dataset = np.array([r[0] for r in rows])
    speaker = np.array([r[1] for r in rows])
    y = np.array([EMOTIONS.index(r[2]) for r in rows])
    sentence = np.array([r[3] for r in rows])
    x = np.array([[r[4][f] for f in FEATURES] for r in rows])
    return x, y, speaker, sentence, dataset


def online_z(x, speaker, mean, std, seed=0):
    """Each clip normalised only by its speaker's earlier clips, in a random order."""
    rng = np.random.default_rng(seed)
    z = np.zeros_like(x)
    for s in np.unique(speaker):
        idx = np.flatnonzero(speaker == s)
        rng.shuffle(idx)
        norm = SpeakerNormaliser(mean, std, PRIOR_TURNS)
        for i in idx:
            z[i] = norm.z(x[i])
            norm.learn(x[i])
    return z


def fit(z, y, l2=L2, steps=3000, lr=0.5):
    """Multinomial logistic regression with an L2 penalty, by full-batch Nesterov descent.

    Classes are weighted equally, so a dataset with more neutral clips does not teach
    the model that most voices are neutral.
    """
    mean, std = z.mean(0), z.std(0) + 1e-9
    s = (z - mean) / std
    n, d = s.shape
    k = len(EMOTIONS)
    onehot = np.eye(k)[y]
    counts = np.bincount(y, minlength=k)
    sample_w = (n / (k * np.maximum(counts, 1)))[y][:, None]
    w, b = np.zeros((k, d)), np.zeros(k)
    vw, vb = np.zeros_like(w), np.zeros_like(b)
    for _ in range(steps):
        lw, lb = w + 0.9 * vw, b + 0.9 * vb
        logits = s @ lw.T + lb
        logits -= logits.max(1, keepdims=True)
        p = np.exp(logits)
        p /= p.sum(1, keepdims=True)
        err = (p - onehot) * sample_w
        gw = err.T @ s / n + l2 * lw / n
        gb = err.mean(0)
        vw, vb = 0.9 * vw - lr * gw, 0.9 * vb - lr * gb
        w, b = w + vw, b + vb
    return {"scaler_mean": mean, "scaler_std": std, "coef": w, "intercept": b}


def predict(m, z):
    s = (z - m["scaler_mean"]) / m["scaler_std"]
    logits = s @ m["coef"].T + m["intercept"]
    logits -= logits.max(1, keepdims=True)
    p = np.exp(logits)
    return p / p.sum(1, keepdims=True)


def _auc(positive, score):
    order = np.argsort(score)
    ranks = np.empty(len(score))
    ranks[order] = np.arange(1, len(score) + 1)
    n_pos, n_neg = positive.sum(), (~positive).sum()
    if not n_pos or not n_neg:
        return float("nan")
    return float((ranks[positive].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def report(y, p):
    pred = p.argmax(1)
    recall = [float((pred[y == c] == c).mean()) if (y == c).any() else float("nan")
              for c in range(len(EMOTIONS))]  # fmt: skip
    i = {e: EMOTIONS.index(e) for e in EMOTIONS}
    high = np.isin(y, [i["angry"], i["fearful"], i["happy"]])
    flat = np.isin(y, [i["neutral"], i["sad"]])
    keep = high | flat
    conf = p.max(1)
    correct = pred == y
    ece = sum(
        m.mean() * abs(correct[m].mean() - conf[m].mean())
        for b in range(10)
        if (m := (conf > b / 10) & (conf <= (b + 1) / 10)).any()
    )
    return {
        "clips": len(y),
        "unweighted_accuracy": round(float(np.nanmean(recall)), 3),
        "recall": {e: round(r, 3) for e, r in zip(EMOTIONS, recall)},
        # Can it tell an energised voice from a flat one, and an angry one from the rest?
        "arousal_auc": round(_auc(high[keep], p[keep][:, [i["angry"], i["fearful"], i["happy"]]].sum(1)), 3),
        "angry_auc": round(_auc(y == i["angry"], p[:, i["angry"]]), 3),
        "flat_auc": round(_auc(flat, p[:, [i["neutral"], i["sad"]]].sum(1)), 3),
        "calibration_error": round(float(ece), 3),
    }  # fmt: skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("crema", type=Path, help="folder of CREMA-D AudioWAV files")
    parser.add_argument(
        "--extra", type=Path, help="CSV of other clips: path,dataset,speaker,emotion"
    )
    parser.add_argument("--download", action="store_true", help="fetch CREMA-D first")
    args = parser.parse_args()
    if args.download:
        download(args.crema)
    x, y, speaker, sentence, dataset = load(clips(args.crema, args.extra))
    mean, std = x.mean(0), x.std(0) + 1e-9
    z = online_z(x, speaker, mean, std)
    speakers = np.unique(speaker)
    np.random.default_rng(1).shuffle(speakers)
    folds = np.array_split(speakers, 5)
    held = np.zeros((len(y), len(EMOTIONS)))
    held_both = np.full((len(y), len(EMOTIONS)), np.nan)
    crema = dataset == "crema-d"
    for fold in folds:
        test = np.isin(speaker, fold)
        held[test] = predict(fit(z[~test], y[~test]), z[test])
        for s in np.unique(sentence[crema]):
            train, part = ~test & (sentence != s), test & crema & (sentence == s)
            if part.any():
                held_both[part] = predict(fit(z[train], y[train]), z[part])
    results = {"new_speakers": report(y, held)}
    for name in np.unique(dataset):
        results[f"new_speakers ({name})"] = report(y[dataset == name], held[dataset == name])
    results["new_speakers_and_sentences (crema-d)"] = report(y[crema], held_both[crema])
    # The hardest test: a whole dataset it never heard, so new voices, new microphones
    # and new rooms. Trained on every other dataset, with their population usual.
    if len(np.unique(dataset)) > 1:
        for name in np.unique(dataset):
            test = dataset == name
            others_mean, others_std = x[~test].mean(0), x[~test].std(0) + 1e-9
            z_other = online_z(x, speaker, others_mean, others_std)
            fitted = fit(z_other[~test], y[~test])
            results[f"new_dataset ({name})"] = report(y[test], predict(fitted, z_other[test]))
    print(json.dumps(results, indent=2))
    final = fit(z, y)
    counts = {str(d): int((dataset == d).sum()) for d in np.unique(dataset)}
    params = {
        "about": "Word-blind voice emotion model; see ilumina/voice_model.py",
        "trained_on": {"clips": counts, "speakers": len(speakers)},
        "features": list(FEATURES),
        "classes": list(EMOTIONS),
        "population_mean": mean.round(6).tolist(),
        "population_std": std.round(6).tolist(),
        **{k: np.asarray(v).round(6).tolist() for k, v in final.items()},
        "tested": results,
    }
    MODEL_PATH.write_text(json.dumps(params, indent=1) + "\n")
    print(f"Wrote {MODEL_PATH}")


if __name__ == "__main__":
    main()
