"""Measured evidence about how one student turn was spoken, from Deepgram Flux word timings.

These are measurements, not judgements. The dashboard shows them beside each reading,
and Decision 1 gets them as one line next to the audio.
"""

from itertools import pairwise

_FILLERS = frozenset({"um", "umm", "uh", "uhh", "er", "erm", "hmm", "mm"})
# Below this a pace is noise: "yes, four" is not fast or slow speech.
_MIN_WORDS_FOR_PACE, _MIN_SECONDS_FOR_PACE = 3, 1.0


def _timed(word) -> bool:
    return (
        isinstance(word, dict)
        and isinstance(word.get("word"), str)
        and isinstance(word.get("start"), (int, float))
        and isinstance(word.get("end"), (int, float))
    )


def voice_evidence(result: dict | None, waited: float | None = None) -> dict | None:
    """Evidence from one Flux end-of-turn message, or None if it has no timed words.

    `waited` is the silence between the tutor finishing and the student starting, in
    seconds, when the student did not cut the tutor off.
    """
    words = [w for w in (result or {}).get("words") or [] if _timed(w)]
    if not words:
        return None
    seconds = words[-1]["end"] - words[0]["start"]
    pauses = [later["start"] - earlier["end"] for earlier, later in pairwise(words)]
    paced = len(words) >= _MIN_WORDS_FOR_PACE and seconds >= _MIN_SECONDS_FOR_PACE
    return {
        "words": len(words),
        "seconds": round(seconds, 1),
        "words_per_minute": round(len(words) / seconds * 60) if paced else None,
        "longest_pause": round(max(pauses, default=0.0), 1),
        "fillers": sum(w["word"].strip(".,?!").lower() in _FILLERS for w in words),
        "waited": None if waited is None else round(waited, 1),
    }


def describe_evidence(evidence: dict) -> str:
    """The same measurements as one line of plain text, for Decision 1."""
    parts = [f"{evidence['words']} words in {evidence['seconds']} seconds"]
    if evidence["words_per_minute"] is not None:
        parts[0] += f" ({evidence['words_per_minute']} words a minute)"
    parts.append(f"longest pause between words {evidence['longest_pause']} seconds")
    parts.append(f"filler words such as um or uh: {evidence['fillers']}")
    if evidence["waited"] is not None:
        parts.append(f"started answering {evidence['waited']} seconds after the tutor finished")
    return "Measured from this turn's audio by Deepgram: " + ", ".join(parts) + "."
