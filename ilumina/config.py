"""All model IDs and keys in one place, read from the environment."""

import os

from dotenv import load_dotenv

load_dotenv(override=True)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_VOICE_ID = os.getenv("DEEPGRAM_VOICE_ID") or "aura-2-helena-en"
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

# The student's Vexo band in a tutoring session: its number for Bluetooth, such as 42,
# or "usb" for the cable. A double tap means "done talking" and the light shows whose turn
# it is. Left unset, sessions run without a band.
BAND = (os.getenv("ILUMINA_BAND") or "").strip().lower()
BAND_USB = BAND == "usb"
BAND_NUMBER = int(BAND) if BAND.isdigit() else None

# Check each step the student gives for mistakes: a second Decision 1 call per turn,
# beside the emotion call. Set ILUMINA_WORK_CHECK=off to run without it.
WORK_CHECK = (os.getenv("ILUMINA_WORK_CHECK") or "on").lower() not in ("off", "no", "false", "0")
# The tutor waits at most this long for the check of the turn that just ended, so that it
# can use it in its answer. On the demo Mac a check takes 0.5 to 0.9 seconds. A check that
# is later than this goes with the next turn instead.
WORK_CHECK_WAIT_SECONDS = float(os.getenv("ILUMINA_WORK_CHECK_WAIT") or 0.9)

# Opt-in: save tutoring sessions (the moments the student struggled) to memory/.
# Lectures from the Vexo band are saved only when the student says yes in lecture.py.
SAVE_MEMORY = (os.getenv("ILUMINA_MEMORY") or "off").lower() in ("on", "yes", "true", "1")
