#!/usr/bin/env bash
# One command to start the GoPro preview: ./gopro/run.sh [options]   (see --help)
set -euo pipefail
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg missing: brew install ffmpeg"; exit 1; }
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating Python env..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m gopro_cam "$@"
