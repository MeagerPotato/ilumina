"""Acoustic measurements of one student turn: how it sounds, never what it says.

A numpy take on the extended Geneva Minimalistic Acoustic Parameter Set (eGeMAPS;
Eyben et al. 2016, IEEE Transactions on Affective Computing 7(2), 190-202), the
standard small feature set for voice-based affect research. It covers the same four
groups: pitch, loudness, voice quality, and spectral balance, plus the rhythm of
voiced and unvoiced stretches. These features do not depend on the words, which is
the point: they are the word-blind half of the reading.

The implementations are simplified, so the numbers are close to, but not the same
as, openSMILE's eGeMAPS values. Jitter and shimmer here are measured frame to frame
rather than cycle to cycle, so read them as "pitch and loudness micro-variation".

Nothing is kept: the audio is read once and dropped.
"""

import io
import wave
from dataclasses import dataclass

import numpy as np

FRAME_SECONDS, HOP_SECONDS = 0.04, 0.01
_MIN_HZ, _MAX_HZ = 60.0, 500.0
_VOICED_CORRELATION = 0.5
_OCTAVE_TOLERANCE = 0.9  # a shorter-period peak this close to the best one wins
_QUIET_DBFS = -50.0
MIN_VOICED_FRAMES = 10  # 0.1 s of voicing; below this the turn is not measured
_MEL_BANDS, _MFCCS = 26, 4
_SEMITONE_REFERENCE_HZ = 27.5  # eGeMAPS expresses F0 in semitones from 27.5 Hz
# Everything is measured at 16 kHz, the rate the voice model was trained at. Pipecat's
# audio buffer hands over turns at the output rate (24 kHz), and spectral and loudness
# values shift with the rate, so other rates are resampled first.
ANALYSIS_RATE = 16000


@dataclass
class Analysis:
    """Frame-by-frame measurements of one turn, 10 ms apart."""

    rate: int
    f0: np.ndarray  # Hz, 0 where unvoiced
    periodicity: np.ndarray  # autocorrelation peak, 0 to 1
    dbfs: np.ndarray  # frame level
    voiced: np.ndarray  # bool
    sounding: np.ndarray  # bool, louder than near-silence
    loudness: np.ndarray  # auditory-spectrum loudness (Stevens power law)
    alpha_ratio: np.ndarray  # dB, energy 50-1000 Hz over 1-5 kHz
    hammarberg: np.ndarray  # dB, strongest peak 0-2 kHz over 2-5 kHz
    slope_low: np.ndarray  # dB per kHz, 0-500 Hz
    slope_mid: np.ndarray  # dB per kHz, 500-1500 Hz
    centroid: np.ndarray  # Hz
    flux: np.ndarray  # spectral change from the previous frame
    mfcc: np.ndarray  # frames x _MFCCS (coefficients 1 to 4)


def read_wav(wav: bytes) -> tuple[np.ndarray, int]:
    """Mono float samples in -1..1 and the sample rate, from 16-bit WAV bytes."""
    with wave.open(io.BytesIO(wav)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError(f"expected 16-bit audio, got {width * 8}-bit")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def resample(samples: np.ndarray, rate: int, target: int = ANALYSIS_RATE) -> np.ndarray:
    """Band-limited resampling by FFT: keeps everything below both Nyquist limits."""
    if rate == target or len(samples) < 2:
        return samples
    n, m = len(samples), max(1, round(len(samples) * target / rate))
    spectrum = np.fft.rfft(samples)
    keep = m // 2 + 1
    if keep <= len(spectrum):
        spectrum = spectrum[:keep]
    else:
        spectrum = np.pad(spectrum, (0, keep - len(spectrum)))
    return np.fft.irfft(spectrum, n=m) * (m / n)


def _frames(samples: np.ndarray, size: int, hop: int) -> np.ndarray:
    if len(samples) < size:
        return np.empty((0, size))
    count = 1 + (len(samples) - size) // hop
    index = np.arange(size)[None, :] + hop * np.arange(count)[:, None]
    return samples[index]


def _pitch(windowed: np.ndarray, rate: int) -> tuple[np.ndarray, np.ndarray]:
    """F0 per frame by normalised autocorrelation, with sub-sample peak interpolation."""
    size = windowed.shape[1]
    n = 1 << int(np.ceil(np.log2(2 * size)))
    spectrum = np.fft.rfft(windowed, n=n, axis=1)
    acf = np.fft.irfft(np.abs(spectrum) ** 2, n=n, axis=1)[:, :size]
    # Divide by the window's own autocorrelation so long lags are not penalised.
    window_acf = np.fft.irfft(np.abs(np.fft.rfft(np.hanning(size), n=n)) ** 2, n=n)[:size]
    acf = acf / np.maximum(window_acf / window_acf[0], 1e-3)
    energy = acf[:, :1]
    acf = np.where(energy > 0, acf / np.maximum(energy, 1e-12), 0)
    low, high = int(rate / _MAX_HZ), min(int(rate / _MIN_HZ), size - 2)
    search = acf[:, low - 1 : high + 1]
    inner = search[:, 1:-1]
    peaks = (inner >= search[:, :-2]) & (inner > search[:, 2:])
    # Take the shortest-period peak that is nearly as strong as the strongest one. A
    # periodic voice also peaks at twice its period, and picking that would halve the
    # pitch (the usual octave error).
    best = np.where(peaks, inner, -np.inf).max(axis=1, keepdims=True)
    good = peaks & (inner >= _OCTAVE_TOLERANCE * best)
    lags = np.where(good.any(axis=1), np.argmax(good, axis=1), np.argmax(inner, axis=1)) + low
    rows = np.arange(len(acf))
    strength = np.clip(acf[rows, lags], 0, 1)
    # Parabolic interpolation around the peak for a finer period.
    left, mid, right = acf[rows, lags - 1], acf[rows, lags], acf[rows, lags + 1]
    denom = left - 2 * mid + right
    safe = np.abs(denom) > 1e-9
    shift = np.zeros_like(denom)
    shift[safe] = 0.5 * (left[safe] - right[safe]) / denom[safe]
    period = lags + np.clip(shift, -0.5, 0.5)
    f0 = np.where(strength >= _VOICED_CORRELATION, rate / period, 0.0)
    return f0, strength


def _mel_filters(rate: int, n_fft: int) -> np.ndarray:
    def mel(hz):
        return 2595 * np.log10(1 + hz / 700)

    def hz(m):
        return 700 * (10 ** (m / 2595) - 1)

    top = min(8000.0, rate / 2)
    points = hz(np.linspace(mel(20.0), mel(top), _MEL_BANDS + 2))
    bins = np.fft.rfftfreq(n_fft, 1 / rate)
    filters = np.zeros((_MEL_BANDS, len(bins)))
    for i in range(_MEL_BANDS):
        lo, centre, hi = points[i], points[i + 1], points[i + 2]
        rising = (bins - lo) / (centre - lo)
        falling = (hi - bins) / (hi - centre)
        filters[i] = np.clip(np.minimum(rising, falling), 0, None)
    return filters


def _band(power: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs < hi)
    return power[:, mask]


def _slope(db: np.ndarray, freqs: np.ndarray, lo: float, hi: float) -> np.ndarray:
    mask = (freqs >= lo) & (freqs <= hi)
    x = freqs[mask] / 1000
    y = db[:, mask]
    x = x - x.mean()
    return (y - y.mean(axis=1, keepdims=True)) @ x / np.sum(x**2)


def analyse(samples: np.ndarray, rate: int) -> Analysis | None:
    """Frame-level measurements at 16 kHz, or None if the audio is shorter than one frame."""
    samples, rate = resample(samples, rate), ANALYSIS_RATE
    size, hop = int(FRAME_SECONDS * rate), int(HOP_SECONDS * rate)
    frames = _frames(samples, size, hop)
    if not len(frames):
        return None
    centred = frames - frames.mean(axis=1, keepdims=True)
    windowed = centred * np.hanning(size)
    rms = np.sqrt(np.mean(frames**2, axis=1))
    dbfs = 20 * np.log10(np.maximum(rms, 1e-6))
    f0, periodicity = _pitch(windowed, rate)
    sounding = dbfs > _QUIET_DBFS
    voiced = (f0 > 0) & sounding

    n_fft = 1 << int(np.ceil(np.log2(size)))
    power = np.abs(np.fft.rfft(windowed, n=n_fft, axis=1)) ** 2 + 1e-12
    freqs = np.fft.rfftfreq(n_fft, 1 / rate)
    db = 10 * np.log10(power)
    mel_power = power @ _mel_filters(rate, n_fft).T + 1e-12
    loudness = np.sum(mel_power**0.3, axis=1)
    log_mel = np.log(mel_power)
    k = np.arange(_MEL_BANDS)
    dct = np.cos(np.pi / _MEL_BANDS * (k[None, :] + 0.5) * np.arange(1, _MFCCS + 1)[:, None])
    mfcc = log_mel @ dct.T
    low_e = _band(power, freqs, 50, 1000).sum(axis=1)
    high_e = _band(power, freqs, 1000, min(5000, rate / 2)).sum(axis=1)
    alpha = 10 * np.log10(low_e / np.maximum(high_e, 1e-12))
    peak_low = _band(db, freqs, 0, 2000).max(axis=1)
    peak_high = _band(db, freqs, 2000, min(5000, rate / 2)).max(axis=1)
    norm_spec = power / power.sum(axis=1, keepdims=True)
    centroid = norm_spec @ freqs
    flux = np.r_[0.0, np.sqrt(np.sum(np.diff(np.sqrt(norm_spec), axis=0) ** 2, axis=1))]
    return Analysis(
        rate=rate,
        f0=f0,
        periodicity=periodicity,
        dbfs=dbfs,
        voiced=voiced,
        sounding=sounding,
        loudness=loudness,
        alpha_ratio=alpha,
        hammarberg=peak_low - peak_high,
        slope_low=_slope(db, freqs, 0, 500),
        slope_mid=_slope(db, freqs, 500, 1500),
        centroid=centroid,
        flux=flux,
        mfcc=mfcc,
    )


def _segments(mask: np.ndarray) -> tuple[list[int], list[int]]:
    """Lengths (in frames) of the voiced runs and of the unvoiced runs between them."""
    runs_on, runs_off, count, state = [], [], 0, None
    for value in mask:
        if value == state:
            count += 1
            continue
        if state is True:
            runs_on.append(count)
        elif state is False:
            runs_off.append(count)
        state, count = bool(value), 1
    if state is True:
        runs_on.append(count)
    # Silence before the first and after the last voiced run is not inside the turn.
    if runs_off and mask[0] == 0:
        runs_off = runs_off[1:]
    if runs_off and mask[-1] == 0:
        runs_off = runs_off[:-1]
    return runs_on, runs_off


def _slopes(values: np.ndarray, voiced: np.ndarray) -> tuple[float, float]:
    """Mean rising and mean falling slope per second, over neighbouring voiced frames."""
    both = voiced[1:] & voiced[:-1]
    steps = np.diff(values)[both] / HOP_SECONDS
    rising, falling = steps[steps > 0], steps[steps < 0]
    return (
        float(rising.mean()) if len(rising) else 0.0,
        float(-falling.mean()) if len(falling) else 0.0,
    )


def _stats(x: np.ndarray) -> tuple[float, float]:
    return (float(np.mean(x)), float(np.std(x))) if len(x) else (0.0, 0.0)


FEATURES = (
    "f0_mean", "f0_std", "f0_p20", "f0_p50", "f0_p80", "f0_range",
    "f0_rise", "f0_fall", "f0_end",
    "loud_mean", "loud_cv", "loud_p20", "loud_p50", "loud_p80", "loud_range",
    "loud_rise", "loud_fall", "loud_peaks",
    "jitter", "shimmer", "hnr_mean", "hnr_std",
    "alpha_v", "alpha_v_std", "hammarberg_v", "hammarberg_v_std",
    "slope_low_v", "slope_mid_v", "centroid_v", "centroid_v_std", "flux_v",
    "mfcc1", "mfcc2", "mfcc3", "mfcc4", "mfcc1_std", "mfcc2_std", "mfcc3_std", "mfcc4_std",
    "alpha_uv", "hammarberg_uv", "flux_uv",
    "voiced_rate", "voiced_len", "voiced_len_std", "gap_len", "gap_len_std", "voiced_share",
)  # fmt: skip


def features(analysis: Analysis) -> dict[str, float] | None:
    """One value per name in FEATURES for the whole turn, or None if too little was voiced."""
    a = analysis
    voiced = a.voiced
    if voiced.sum() < MIN_VOICED_FRAMES:
        return None
    st = np.where(voiced, 12 * np.log2(np.maximum(a.f0, 1e-6) / _SEMITONE_REFERENCE_HZ), 0.0)
    median_st = np.median(st[voiced])
    # Octave errors are the usual autocorrelation mistake: drop frames an octave away.
    voiced = voiced & (np.abs(st - median_st) < 12)
    if voiced.sum() < MIN_VOICED_FRAMES:
        return None
    sv = st[voiced]
    p20, p50, p80 = np.percentile(sv, [20, 50, 80])
    f0_rise, f0_fall = _slopes(st, voiced)
    times = np.flatnonzero(voiced) * HOP_SECONDS
    end = times >= times[-1] - 0.5
    f0_end = 0.0
    if end.sum() >= 5:
        f0_end = float(np.polyfit(times[end], sv[end], 1)[0] * (times[end][-1] - times[end][0]))

    sounding = a.sounding
    loud = a.loudness[sounding] if sounding.any() else a.loudness
    loud_mean = float(np.mean(loud))
    lp20, lp50, lp80 = np.percentile(loud, [20, 50, 80])
    loud_rise, loud_fall = _slopes(a.loudness, sounding)
    smooth = np.convolve(a.loudness, np.ones(5) / 5, mode="same")
    peaks = (smooth[1:-1] > smooth[:-2]) & (smooth[1:-1] >= smooth[2:]) & (smooth[1:-1] > lp50)
    span = np.flatnonzero(sounding)
    talking_frames = (span[-1] - span[0] + 1) if len(span) else len(a.loudness)
    talking_seconds = max(talking_frames * HOP_SECONDS, HOP_SECONDS)

    # Frame-to-frame micro-variation of period and level over neighbouring voiced frames.
    pairs = voiced[1:] & voiced[:-1]
    periods = 1 / np.maximum(a.f0, 1e-6)
    jitter = (
        float(np.mean(np.abs(np.diff(periods))[pairs]) / np.mean(periods[voiced]))
        if pairs.any()
        else 0.0
    )
    shimmer = float(np.mean(np.abs(np.diff(a.dbfs))[pairs])) if pairs.any() else 0.0
    r = np.clip(a.periodicity[voiced], 1e-3, 0.999)
    hnr = 10 * np.log10(r / (1 - r))

    unvoiced = sounding & ~voiced
    on, off = _segments(voiced[span[0] : span[-1] + 1] if len(span) else voiced)
    values = {
        "f0_mean": float(np.mean(sv)),
        "f0_std": float(np.std(sv)),
        "f0_p20": float(p20),
        "f0_p50": float(p50),
        "f0_p80": float(p80),
        "f0_range": float(p80 - p20),
        "f0_rise": f0_rise,
        "f0_fall": f0_fall,
        "f0_end": f0_end,
        "loud_mean": loud_mean,
        "loud_cv": float(np.std(loud) / max(loud_mean, 1e-9)),
        "loud_p20": float(lp20),
        "loud_p50": float(lp50),
        "loud_p80": float(lp80),
        "loud_range": float(lp80 - lp20),
        "loud_rise": loud_rise,
        "loud_fall": loud_fall,
        "loud_peaks": float(peaks.sum() / talking_seconds),
        "jitter": jitter,
        "shimmer": shimmer,
        "hnr_mean": float(np.mean(hnr)),
        "hnr_std": float(np.std(hnr)),
    }
    for name, series in (("alpha", a.alpha_ratio), ("hammarberg", a.hammarberg)):
        values[f"{name}_v"], values[f"{name}_v_std"] = _stats(series[voiced])
        values[f"{name}_uv"] = _stats(series[unvoiced])[0]
    values["slope_low_v"] = _stats(a.slope_low[voiced])[0]
    values["slope_mid_v"] = _stats(a.slope_mid[voiced])[0]
    values["centroid_v"], values["centroid_v_std"] = _stats(a.centroid[voiced])
    values["flux_v"] = _stats(a.flux[voiced])[0]
    values["flux_uv"] = _stats(a.flux[unvoiced])[0]
    for i in range(_MFCCS):
        values[f"mfcc{i + 1}"], values[f"mfcc{i + 1}_std"] = _stats(a.mfcc[voiced, i])
    values["voiced_rate"] = len(on) / talking_seconds
    values["voiced_len"], values["voiced_len_std"] = _stats(np.array(on) * HOP_SECONDS)
    values["gap_len"], values["gap_len_std"] = _stats(np.array(off) * HOP_SECONDS)
    values["voiced_share"] = float(voiced.sum() / talking_frames)
    return {name: values[name] for name in FEATURES}


def measure(wav: bytes) -> tuple[Analysis | None, dict[str, float] | None]:
    """Analyse one turn's WAV and summarise it. Both are None for silence or noise."""
    samples, rate = read_wav(wav)
    analysis = analyse(samples, rate)
    if analysis is None:
        return None, None
    return analysis, features(analysis)
