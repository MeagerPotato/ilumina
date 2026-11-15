# Changelog

## Unreleased · 2026-11-14

The first recorded milestone covers voice tutoring, lecture capture, the GoPro feed, and the hosted demo setup. The Python manifest identifies the project as `0.1.0`.

| Area | Change |
| --- | --- |
| **Voice tutor** | Run a browser voice session with Deepgram and Gemini. Combine separate voice and text scores with a local acoustic model to guide the tutor’s next move. |
| **Dashboard** | See what the bot heard, how the turn was scored, and how the tutor adapted. Inspect the timeline, equations, and saved lecture material. |
| **Lecture capture** | Import a microphone or Vexo recording, an audio file, or an existing transcript. Save notes for a later tutoring session or study plan. |
| **GoPro LIT HERO** | Run a standalone USB preview or use the local feed as the tutor’s camera. |
| **Hosting** | Serve the landing page and passcode-gated dashboard with a Python bot over WebSocket on Vercel. |

### Documentation & presentation

- Show a [replay in the redesigned dashboard](docs/dashboard/mid-session.png) in the README and retain the [earlier prototype replay](assets/readme/dashboard.webp) here for reference. Both use sample data.
- Document local setup, the tutoring pipeline, configuration, data flow to providers, and local memory behavior in the [README](README.md).

### Tooling & hygiene

- Ignore macOS Finder metadata and local `.env` variants while keeping the example configuration available.

### Verification

- `uv sync --locked --python 3.12` installed the pinned environment on macOS.
- `uv run --locked pytest -q` passed 85 tests.
- Loaded the dashboard and Pipecat test client from the local runner.
