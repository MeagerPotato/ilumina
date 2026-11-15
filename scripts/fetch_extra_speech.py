"""Fetch the extra emotional speech the voice model trains on beside CREMA-D.

Only the five emotions the tutor uses are kept (angry, fearful, happy, neutral, sad).
**Both datasets are licensed for non-commercial use only**, and so may be a model
trained on them. Retrain without `--extra` for any commercial use.

- EARS (Richter, J. et al. 2024, "EARS: An anechoic fullband speech dataset benchmarked
  for speech enhancement and dereverberation", Interspeech; CC BY-NC 4.0;
  https://github.com/facebookresearch/ears_dataset). 107 speakers reading and
  improvising in each emotion. Only anger, fear, neutral and sadness are fetched (EARS
  has no plain "happy"), straight from the official release zips, by HTTP range
  requests, so the rest of each 1-2 GB zip is never downloaded. Each 15-30 s recording
  is cut at its pauses into utterance-length clips (0.8 to 8 s of speech).
- RAVDESS (Livingstone, S.R. & Russo, F.A. 2018, PLoS ONE 13(5): e0196391; CC BY-NC-SA
  4.0; https://zenodo.org/records/1188976). 24 actors, speech only. Neutral, happy,
  sad, angry and fearful are kept; calm, disgust and surprised are left out.

    uv run scripts/fetch_extra_speech.py extra/            # about 600 MB, needs ffmpeg
    uv run scripts/train_voice_model.py crema/ --extra extra/manifest.csv

Writes 16 kHz mono 16-bit WAV files under the folder and `manifest.csv` with the
columns path,dataset,speaker,emotion,license (paths relative to the folder).
"""

import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

RATE = 16000
EARS_URL = "https://github.com/facebookresearch/ears_dataset/releases/download/dataset/p{:03d}.zip"
EARS_SPEAKERS = range(1, 108)
EARS_EMOTIONS = {"anger": "angry", "fear": "fearful", "neutral": "neutral", "sadness": "sad"}
RAVDESS_URL = "https://zenodo.org/records/1188976/files/Audio_Speech_Actors_01-24.zip"
# RAVDESS file names: modality-channel-emotion-intensity-statement-repetition-actor.
RAVDESS_EMOTIONS = {"01": "neutral", "03": "happy", "04": "sad", "05": "angry", "06": "fearful"}
LICENSES = {"ears": "CC BY-NC 4.0", "ravdess": "CC BY-NC-SA 4.0"}


class RangedFile(io.RawIOBase):
    """A remote file read by HTTP range requests, so zipfile can pick out single members."""

    def __init__(self, url: str):
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Range": "bytes=0-0"}), timeout=60
        ) as r:
            self.url, self.size = r.geturl(), int(r.headers["Content-Range"].split("/")[-1])
        self.pos = 0

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (offset, self.pos + offset, self.size + offset)[whence]
        return self.pos

    def readinto(self, buffer):
        if self.pos >= self.size or not len(buffer):
            return 0
        end = min(self.pos + max(len(buffer), 1 << 16), self.size) - 1
        request = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(request, timeout=120) as r:
            data = r.read()[: len(buffer)]
        buffer[: len(data)] = data
        self.pos += len(data)
        return len(data)


def decode(audio: bytes) -> np.ndarray:
    """Any audio file's bytes to 16 kHz mono int16 samples, by ffmpeg."""
    pcm = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(RATE),
         "-f", "s16le", "-c:a", "pcm_s16le", "pipe:1"],
        input=audio, capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(pcm, dtype=np.int16)


def write_wav(path: Path, samples: np.ndarray):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.astype(np.int16).tobytes())


def utterances(x: np.ndarray) -> list[tuple[int, int]]:
    """Cut a long recording at its pauses: (start, end) sample ranges of 0.8 to 8 s."""
    frame, hop = 400, 160  # 25 ms frames every 10 ms
    level = np.cumsum(np.r_[0.0, (x / 32768.0) ** 2])
    n = max(0, (len(x) - frame) // hop + 1)
    if not n:
        return []
    starts = np.arange(n) * hop
    db = 10 * np.log10((level[starts + frame] - level[starts]) / frame + 1e-12)
    speech = db > max(np.percentile(db, 5) + 15, np.percentile(db, 99) - 45)
    runs, i = [], 0
    while i < n:
        if speech[i]:
            j = i
            while j < n and speech[j]:
                j += 1
            if runs and i - runs[-1][1] < 30:  # bridge pauses under 0.3 s
                runs[-1][1] = j
            else:
                runs.append([i, j])
            i = j
        else:
            i += 1
    out = []

    def split(a, b):
        if (b - a) * hop / RATE <= 8.0:
            out.append((a, b))
            return
        cut = a + 300 + int(np.argmin(db[a + 300 : b - 300]))  # quietest point, 3 s from each end
        split(a, cut)
        split(cut, b)

    for a, b in runs:
        if (b - a) * hop / RATE >= 0.8:
            split(a, b)
    pad = RATE // 10
    return [(max(0, a * hop - pad), min(len(x), b * hop + frame + pad)) for a, b in out]


def fetch_ears_speaker(folder: Path, number: int) -> list[list[str]]:
    speaker = f"ears_p{number:03d}"
    names = re.compile(r"emo_(anger|fear|neutral|sadness)_(sentences|freeform)\.wav$")
    rows = []
    with zipfile.ZipFile(io.BufferedReader(RangedFile(EARS_URL.format(number)), 1 << 20)) as z:
        for member in z.infolist():
            m = names.search(member.filename)
            if not m:
                continue
            x = decode(z.read(member))
            for k, (a, b) in enumerate(utterances(x)):
                rel = f"ears/{speaker}/{m[1]}_{m[2]}_{k:02d}.wav"
                write_wav(folder / rel, x[a:b])
                rows.append([rel, "ears", speaker, EARS_EMOTIONS[m[1]], LICENSES["ears"]])
    return rows


def fetch_ravdess(folder: Path, source: str) -> list[list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(source)
        if not path.exists():
            path = Path(tmp) / "ravdess.zip"
            print(f"Downloading {source}")
            with urllib.request.urlopen(source, timeout=120) as r, path.open("wb") as f:
                shutil.copyfileobj(r, f)
        rows = []
        with zipfile.ZipFile(path) as z:
            for member in z.infolist():
                name = Path(member.filename).name
                parts = name.removesuffix(".wav").split("-")
                # Speech only (03 = audio only, 01 = speech), five emotions.
                if len(parts) != 7 or parts[:2] != ["03", "01"]:
                    continue
                if parts[2] not in RAVDESS_EMOTIONS:
                    continue
                speaker = f"ravdess_{parts[6]}"
                rel = f"ravdess/{speaker}/{name}"
                write_wav(folder / rel, decode(z.read(member)))
                rows.append(
                    [rel, "ravdess", speaker, RAVDESS_EMOTIONS[parts[2]], LICENSES["ravdess"]]
                )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--ravdess", default=RAVDESS_URL, help="zip URL or a local copy")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if not shutil.which("ffmpeg"):
        sys.exit("Needs ffmpeg (brew install ffmpeg).")
    args.folder.mkdir(parents=True, exist_ok=True)
    rows = fetch_ravdess(args.folder, args.ravdess)
    print(f"RAVDESS: {len(rows)} clips")
    with ThreadPoolExecutor(args.workers) as pool:
        for got in pool.map(lambda n: fetch_ears_speaker(args.folder, n), EARS_SPEAKERS):
            rows += got
    print(f"EARS and RAVDESS: {len(rows)} clips")
    with (args.folder / "manifest.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["path", "dataset", "speaker", "emotion", "license"])
        writer.writerows(rows)
    print(f"Wrote {args.folder / 'manifest.csv'}")


if __name__ == "__main__":
    main()
