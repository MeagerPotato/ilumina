"""All model IDs and keys in one place, read from the environment."""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_VOICE_ID = os.getenv("DEEPGRAM_VOICE_ID") or "aura-2-helena-en"
# The backup for speech when Deepgram is down (see ilumina/speech.py). Optional.
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID") or "EXAVITQu4vr4xnSDxMaL"  # "Sarah"
# "auto" (Deepgram, ElevenLabs if Deepgram fails), "deepgram" or "elevenlabs".
SPEECH = (os.getenv("ILUMINA_SPEECH") or "auto").lower()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
# Hydrogen starts speaking in about 1.5 s on the demo Mac; Argon took over 4 s.
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL") or "gemini-4-hydrogen"
DECISION_MODEL = os.getenv("DECISION_MODEL") or "gemini-decision-1"

# Which camera the tutor sees: "browser" (the dashboard's camera) or "gopro"
# (the head-worn GoPro over USB, see gopro/README.md).
CAMERA = (os.getenv("ILUMINA_CAMERA") or "browser").lower()
# Only needed if the GoPro is not found by itself.
GOPRO_IP = os.getenv("GOPRO_IP") or None

# The tutor waits at most this long for the emotion reading of the turn that
# just ended. After that it answers with the last known state.
STATE_WAIT_SECONDS = 0.4

# Opt-in: save tutoring sessions (the moments the student struggled) to memory/.
# Lectures from the Vexo band are saved only when the student says yes in lecture.py.
SAVE_MEMORY = (os.getenv("ILUMINA_MEMORY") or "off").lower() in ("on", "yes", "true", "1")

# How long one session may last, in seconds. 0 (the default) is no limit. The hosted
# app sets it a little under the Vercel Function's maximum duration, so the dashboard
# can end the session cleanly before the connection is cut.
SESSION_SECONDS = int(os.getenv("ILUMINA_SESSION_SECONDS") or 0)
