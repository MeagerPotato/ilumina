"""Everything measured about one student turn, split into what it sounded like and what it said.

The voice channel gets timing from Deepgram's word timings, voice features from the
turn's audio, and how both compare with this student's usual. The words channel gets
the counts taken from the transcript (fillers and hedges). The word-blind voice model
reads the acoustic features against the student's usual voice. Also decided here: how
much the turn can tell at all, since a one-word answer carries little voice evidence.
"""

from loguru import logger

from ilumina.acoustic import analyse, read_wav
from ilumina.acoustic import features as acoustic_features
from ilumina.baseline import SpeakerBaseline, describe_change
from ilumina.evidence import describe_timing, describe_wording
from ilumina.prosody import describe_prosody, from_analysis

# Turns shorter than this many words count for less in the tracker.
_SHORT_TURN_WORDS = 3
SHORT_TURN_WEIGHT = 0.5


def measure_turn(
    wav: bytes, evidence: dict | None, baseline: SpeakerBaseline, voice_model=None
) -> dict:
    """Measure one turn. Never raises: a failed measurement is left out.

    Returns {"voice_text": lines for the voice channel, "words_text": lines for the
    words channel, "voice": the dashboard's voice numbers or None, "vs_usual": clear
    changes from the student's usual, "acoustic": the voice model's reading or None,
    "weight": 0 to 1}.
    """
    analysis = voice = feats = reading = None
    try:
        samples, rate = read_wav(wav)
        analysis = analyse(samples, rate)
        voice = from_analysis(analysis)
        feats = acoustic_features(analysis) if analysis is not None else None
    except Exception as e:  # noqa: BLE001 - measurements are a bonus, the turn goes on
        logger.warning(f"Voice features not measured for this turn: {e}")
    if voice_model is not None and feats is not None:
        try:
            reading = voice_model.read(feats)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Voice model did not read this turn: {e}")
    try:
        changes = baseline.compare({**(evidence or {}), **(voice or {})})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not compare this turn with the student's usual: {e}")
        changes = {}
    voice_lines = [
        describe_timing(evidence) if evidence else "",
        describe_prosody(voice) if voice else "",
        describe_change(changes),
    ]
    short = evidence is not None and evidence.get("words", 0) < _SHORT_TURN_WORDS
    return {
        "voice_text": " ".join(line for line in voice_lines if line),
        "words_text": describe_wording(evidence) if evidence else "",
        "voice": voice,
        "vs_usual": changes,
        "acoustic": reading,
        "weight": SHORT_TURN_WEIGHT if short or voice is None else 1.0,
    }
