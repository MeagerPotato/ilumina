"""All model IDs and keys in one place, read from the environment."""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_VOICE_ID = os.getenv("DEEPGRAM_VOICE_ID") or "aura-2-helena-en"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_MODEL = os.getenv("GOOGLE_MODEL") or "gemini-4-argon"
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
