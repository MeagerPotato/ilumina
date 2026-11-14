"""Everything measured about one student turn, put together for Decision 1 and the tracker.

Word timings from Deepgram, voice features from the turn's audio, and how both compare
with this student's usual. Also how much the turn can tell at all: a one-word answer
carries little voice evidence, so it moves the estimate less.
"""

from loguru import logger

from ilumina.baseline import SpeakerBaseline, describe_change
from ilumina.evidence import describe_evidence
from ilumina.prosody import describe_prosody, prosody

# Turns shorter than this many words count for less in the tracker.
_SHORT_TURN_WORDS = 3
SHORT_TURN_WEIGHT = 0.5


def measure_turn(wav: bytes, evidence: dict | None, baseline: SpeakerBaseline) -> dict:
    """Measure one turn. Never raises: a failed measurement is left out.

    Returns {"text": the lines for Decision 1, "voice": voice features or None,
    "vs_usual": clear changes from the student's usual, "weight": 0 to 1}.
    """
    try:
        voice = prosody(wav)
    except Exception as e:  # noqa: BLE001 - measurements are a bonus, the turn goes on
        logger.warning(f"Voice features not measured for this turn: {e}")
        voice = None
    combined = {**(evidence or {}), **(voice or {})}
    try:
        changes = baseline.compare(combined)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not compare this turn with the student's usual: {e}")
        changes = {}
    lines = [
        describe_evidence(evidence) if evidence else "",
        describe_prosody(voice) if voice else "",
        describe_change(changes),
    ]
    short = evidence is not None and evidence.get("words", 0) < _SHORT_TURN_WORDS
    weight = SHORT_TURN_WEIGHT if short or voice is None else 1.0
    return {
        "text": " ".join(line for line in lines if line),
        "voice": voice,
        "vs_usual": changes,
        "weight": weight,
    }
