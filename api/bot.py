"""The hosted tutor: the same bot as bot.py, run in a Vercel Function.

The dashboard at /app/ first POSTs the passcode here, then opens a WebSocket to
/api/bot?passcode=... and the bot runs for that one connection, voice only.
Keys and the passcode come from the Vercel project's environment variables.
See docs/hosting.md.
"""

import hmac
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from loguru import logger
from pipecat.runner.types import WebSocketRunnerArguments

from bot import bot

# Pipecat's debug logs print every client message, which would put the camera
# stills in the function logs. Pictures are not saved, so log at INFO.
logger.remove()
logger.add(sys.stderr, level="INFO")

app = FastAPI()


def _check(passcode: str) -> int:
    """200 if the passcode is right, 401 if not, 503 if the app is not set up."""
    expected = os.getenv("ILUMINA_PASSCODE", "")
    keys = os.getenv("DEEPGRAM_API_KEY") and os.getenv("GOOGLE_API_KEY")
    if not expected or not keys:
        return 503  # never run open, and never start a bot that cannot speak
    if not hmac.compare_digest(passcode.encode(), expected.encode()):
        return 401
    return 200


@app.post("/api/bot")
async def check_passcode(request: Request):
    try:
        passcode = str((await request.json()).get("passcode", ""))
    except Exception:  # noqa: BLE001 - a malformed body is just a wrong passcode
        passcode = ""
    status = _check(passcode)
    return JSONResponse({"ok": status == 200}, status_code=status)


@app.websocket("/api/bot")
async def session(websocket: WebSocket, passcode: str = ""):
    if _check(passcode) != 200:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    runner_args = WebSocketRunnerArguments(websocket=websocket, transport_type="websocket")
    runner_args.handle_sigint = False
    await bot(runner_args)
