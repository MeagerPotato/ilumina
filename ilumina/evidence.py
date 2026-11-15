"""Measured evidence about how one student turn was spoken, from the word timings of
Deepgram Flux or, when it is the backup, ElevenLabs Scribe.

These are measurements, not judgements. The dashboard shows them beside each reading,
and Decision 1 gets them as one line next to the audio.
"""

from itertools import pairwise

_FILLERS = frozenset({"um", "umm", "uh", "uhh", "er", "erm", "hmm", "mm"})
# Hedges: the words students use when they are not sure. In spoken tutoring, hedged
# and question-like answers go with uncertainty (Liscombe et al. 2005; Forbes-Riley
# and Litman). Counted as phrases of one to three words.
_HEDGES = frozenset(
    {
        ("maybe",), ("probably",), ("perhaps",), ("guess",), ("dunno",),
        ("i", "think"), ("not", "sure"), ("kind", "of"), ("sort", "of"),
        ("i", "dont", "know"), ("no", "idea"),
    }
)  # fmt: skip
# Gaps between words shorter than this are part of normal speech, not silence.
_SILENT_GAP_SECONDS = 0.25
# Below this a pace is noise: "yes, four" is not fast or slow speech.
_MIN_WORDS_FOR_PACE, _MIN_SECONDS_FOR_PACE = 3, 1.0


def _timed(word) -> bool:
    return (
        isinstance(word, dict)
        and isinstance(word.get("word"), str)
        and isinstance(word.get("start"), (int, float))
        and isinstance(word.get("end"), (int, float))
    )


def _letters(word: str) -> str:
    return "".join(filter(str.isalpha, word)).lower()


def _words(result: dict | None) -> list[dict]:
    """Timed words, as {"word", "start", "end"}. Flux gives "word"; ElevenLabs gives
    "text" and also lists the spaces between words, which are left out."""
    words = []
    for w in (result or {}).get("words") or []:
        if isinstance(w, dict) and "word" not in w and w.get("type", "word") == "word":
            w = {**w, "word": w.get("text")}
        if _timed(w):
            words.append(w)
    return words


def voice_evidence(result: dict | None, waited: float | None = None) -> dict | None:
    """Evidence from one Flux end-of-turn message, or None if it has no timed words.

    `waited` is the silence between the tutor finishing and the student starting, in
    seconds, when the student did not cut the tutor off.
    """
    words = _words(result)
    if not words:
        return None
    seconds = words[-1]["end"] - words[0]["start"]
    pauses = [later["start"] - earlier["end"] for earlier, later in pairwise(words)]
    paced = len(words) >= _MIN_WORDS_FOR_PACE and seconds >= _MIN_SECONDS_FOR_PACE
    silence = sum(p for p in pauses if p >= _SILENT_GAP_SECONDS)
    return {
        "words": len(words),
        "seconds": round(seconds, 1),
        "words_per_minute": round(len(words) / seconds * 60) if paced else None,
        "longest_pause": round(max([0.0, *pauses]), 1),
        "fillers": sum(_letters(w["word"]) in _FILLERS for w in words),
        "waited": None if waited is None else round(waited, 1),
        # Added: all the silence inside the turn, which predicted uncertainty best in
        # Pon-Barry and Shieber (2011), and hedges such as "maybe" or "I think".
        "silence": round(silence, 1),
        "silence_share": round(silence / seconds, 2) if seconds > 0 else 0.0,
        "hedges": _count_hedges([_letters(w["word"]) for w in words]),
    }


def _count_hedges(words: list[str]) -> int:
    count, i = 0, 0
    while i < len(words):
        for size in (3, 2, 1):
            if tuple(words[i : i + size]) in _HEDGES:
                count += 1
                i += size
                break
        else:
            i += 1
    return count


def describe_timing(evidence: dict) -> str:
    """The timing half, for the voice channel: how the turn was paced, not what it said."""
    parts = [f"{evidence['seconds']} seconds of speech"]
    if evidence["words_per_minute"] is not None:
        parts[0] += f" at {evidence['words_per_minute']} words a minute"
    parts.append(f"longest pause {evidence['longest_pause']} seconds")
    if evidence.get("silence") is not None:
        parts.append(f"silent for {evidence['silence']} seconds in all inside the turn")
    if evidence["waited"] is not None:
        parts.append(f"started {evidence['waited']} seconds after the tutor finished")
    return "Measured timing: " + ", ".join(parts) + "."


def describe_wording(evidence: dict) -> str:
    """The wording half, for the words channel: fillers and hedges counted in the transcript."""
    parts = [f"filler words such as um or uh: {evidence['fillers']}"]
    if evidence.get("hedges") is not None:
        parts.append(f"hedges such as maybe or I think: {evidence['hedges']}")
    return "Counted in the transcript: " + ", ".join(parts) + "."


def describe_evidence(evidence: dict) -> str:
    """All the measurements as one line of plain text."""
    count = "1 word" if evidence["words"] == 1 else f"{evidence['words']} words"
    parts = [f"{count} in {evidence['seconds']} seconds"]
    if evidence["words_per_minute"] is not None:
        parts[0] += f" ({evidence['words_per_minute']} words a minute)"
    parts.append(f"longest pause between words {evidence['longest_pause']} seconds")
    if evidence.get("silence") is not None:
        parts.append(f"silent for {evidence['silence']} seconds in all inside the answer")
    parts.append(f"filler words such as um or uh: {evidence['fillers']}")
    if evidence.get("hedges") is not None:
        parts.append(f"hedges such as maybe or I think: {evidence['hedges']}")
    if evidence["waited"] is not None:
        parts.append(f"started answering {evidence['waited']} seconds after the tutor finished")
    return "Measured from this turn's audio by Deepgram: " + ", ".join(parts) + "."
