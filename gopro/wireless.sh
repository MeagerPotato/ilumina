#!/usr/bin/env bash
# Hold a wireless link to the GoPro (Bluetooth, then its Wi-Fi): ./gopro/wireless.sh   Ctrl-C closes it.
# Run it from Terminal itself, so macOS can ask to allow Bluetooth.
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First run: creating Python env..."
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
fi
exec .venv/bin/python -m gopro_cam.link "$@"
