# Hosting on Vercel

The whole demo runs on one Vercel project (`ilumina`):

| Path | What it is |
| --- | --- |
| `/` | The landing page from `landing/`, with a "Try Ilumina" link |
| `/app/` | The dashboard from `dashboard/` |
| `/api/bot` | The bot, `api/bot.py`: a Python Vercel Function that runs `bot.py` |

## How a hosted session works

1. The dashboard sees it is served at `/app/`, wakes the function and asks it whether a
   passcode is needed. It shows the passcode box only if one is.
2. It POSTs the passcode to `/api/bot`. Wrong passcode: 401. Keys or passcode not set: 503.
3. It opens a WebSocket to `/api/bot?passcode=...`. The function runs the same pipeline
   as a local run, with Pipecat's WebSocket transport instead of WebRTC.
4. WebSockets carry no video, so the dashboard shows the camera itself and sends the
   tutor one JPEG still a second as a `camera_frame` message (under the client's
   64 KiB message limit). The bot uses it exactly like a video frame. Nothing is saved,
   and the function logs at INFO so the stills never reach the logs.
5. A Vercel Function's WebSocket closes at the function's maximum duration: 300 s on
   Hobby, up to 800 s on Pro ([Vercel limits](https://vercel.com/docs/limits)).
   `ILUMINA_SESSION_SECONDS` tells the dashboard how long a session may last, so it
   counts down and ends the session cleanly just before the cut.

In the browser, the WebSocket transport uses Daily's audio handling (echo
cancellation), loaded from Daily's CDN. No Daily account is involved. `/app/?media=wav`
uses plain Web Audio instead, which is how it is checked offline.

The GoPro head camera needs USB on a Mac, so it stays a local option
(`ILUMINA_CAMERA=gopro`, see the README).

## Environment variables (Vercel project settings)

| Name | Value |
| --- | --- |
| `DEEPGRAM_API_KEY` | Deepgram key (sensitive) |
| `GOOGLE_API_KEY` | Google AI Studio key (sensitive) |
| `ILUMINA_PASSCODE` | What visitors type before "Start session" (sensitive). Unset or `off` means anyone can start a session, which spends the Deepgram and Gemini credits |
| `ILUMINA_SESSION_SECONDS` | `285` on Hobby (function max 300). Raise it with `maxDuration` on Pro |

`GOOGLE_MODEL`, `DECISION_MODEL` and `DEEPGRAM_VOICE_ID` work as in `.env`.

## Deploying

Vercel's GitHub integration on this account cannot see the repo, so a deployment is made
from uploaded files (Vercel API or MCP `create_deployment`, project `ilumina`):

- From `deploy/vercel/`, at the deployment root: `vercel.json`, `package.json`,
  `requirements.txt`, and `vercel-install.sh` with `__COMMIT_SHA__` replaced by the
  commit to deploy.
- `api/bot.py` from the repo, at the same path.

The install script downloads that commit, puts `landing/` at the root, `dashboard/`
into `public/app/` and `bot.py` and `ilumina/` beside `api/`, and Vite builds the pages
into `dist/`. Vercel builds the Python function
from the uploaded `requirements.txt`, a slim list without WebRTC, the GoPro feed or the
Vexo band (about 290 MB installed, under the 500 MB limit for Python functions).
