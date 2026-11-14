# GoPro LIT HERO live feed

Streams the head-mounted GoPro LIT HERO to the Mac and exposes live frames to
Python. Uses the official Open GoPro HTTP API over **USB**, so the Mac's Wi-Fi
stays on the normal network and keeps internet.

## Start / stop

```bash
./gopro/run.sh              # live window: q quit, s save frame, l latency test
./gopro/run.sh --headless   # no window, logs fps
./gopro/run.sh --bench 30   # 30 s test, prints JSON stats
./gopro/run.sh --latency    # flash-the-screen latency test (camera must face the screen)
```

First run creates `gopro/.venv` and installs `requirements.txt`. FFmpeg comes
from Homebrew (`brew install ffmpeg`). Ctrl-C or `q` stops the stream and tells
the camera to stop the preview. Running it again restarts cleanly.

## Camera setup (once)

1. Firmware with Open GoPro support (LIT HERO minimum v01.10.00; tested on `H25.03.02.10.00`).
2. On the camera: **Preferences → Connections → GoPro Connect: On**.
3. Plug into the Mac with a USB-C **data** cable and power the camera on.

No Bluetooth pairing or Wi-Fi joining is needed. The camera appears as a USB
network adapter with an address like `172.26.162.52`; the camera itself is
`172.2X.1YZ.51`, where XYZ are the last three digits of its serial. The script
finds it automatically (or pass `--ip` / `--serial`).

LIT HERO quirk (from the official docs): with GoPro Connect on, **unplugging USB
powers the camera off**. Plug back in and power it on; the running script
reconnects by itself within ~7 s.

## Use the frames from Python

```python
import sys; sys.path.insert(0, "gopro")
from gopro_cam import GoProFeed

with GoProFeed() as feed:              # blocks until the first frame (30 s timeout)
    while True:
        f = feed.wait_frame(timeout=2)  # newest frame, never a backlog
        if f is None:
            continue                    # stalled; feed reconnects in the background
        bgr = f.image                   # numpy HxWx3 uint8, BGR (OpenCV order)
        ...                             # f.t = time.monotonic() at decode, f.index = counter
```

`feed.latest()` returns the newest frame without waiting, `feed.save_latest(path)`
writes a JPEG, `feed.status` / `feed.fps()` / `feed.reconnects` report health,
`GoProFeed(width=512)` downscales in FFmpeg. Only one process can own the
preview at a time.

## How it works

`gopro_cam/camera.py` finds the camera and calls `GET /gopro/camera/stream/start`
(plus a keep-alive every 3 s). The camera sends MPEG-TS over UDP to port 8554.
`gopro_cam/stream.py` runs FFmpeg (low-delay flags) to decode it into raw BGR
frames; a reader thread keeps only the newest frame. A supervisor restarts the
preview and FFmpeg if no frame arrives for 4 s.

## Measured on this Mac (USB, Nov 2026)

| | |
|---|---|
| Preview stream | H.264 Main, 768x432, 29.97 fps, keyframe every 1 s, ~1.3 Mbit/s, plus an AAC audio track (ignored) |
| 60 s run | 0 reconnects, worst frame gap 47 ms, p95 gap 42 ms |
| Recovery | camera-side stop → back streaming in ~7 s, no intervention |
| Internet | stays on Wi-Fi (en0) the whole time |

One earlier run reported 640x480, so the preview size can differ between starts;
read the size from `f.image.shape`, not a constant. The preview is "moderate
quality, for framing" per GoPro; LIT HERO does not support Webcam mode or
camera-on-home-network (COHN) in the Open GoPro spec, so USB preview is the
supported low-latency path.

## Wireless, for wearing the camera with no cable

```bash
./gopro/wireless.sh        # run it from Terminal itself; Ctrl-C closes the link
```

It pairs with the camera over Bluetooth, turns on the camera's own Wi-Fi, joins
it with the Mac's Wi-Fi, and then stays connected so the camera does not go to
sleep. Leave it running. Anything that reads the feed (`GoProFeed()`, Ilumina
with `ILUMINA_CAMERA=gopro`) then finds the camera at `10.5.5.9` by itself, as
long as the camera is not also plugged in over USB.

- The Mac's Wi-Fi is on the GoPro while the link is up, so internet must come
  from somewhere else. An iPhone on a cable with Personal Hotspot on works. If
  the script prints "NO INTERNET", open System Settings > Network > ... > Set
  Service Order and drag the iPhone above Wi-Fi.
- First time: put the camera in pairing mode and accept the Mac's Bluetooth
  pairing request. macOS also asks once to let Terminal use Bluetooth.
- If the Mac cannot join the camera's Wi-Fi by itself, the script prints the
  network name and password to pick in the Wi-Fi menu, and carries on once the
  camera answers.

Checked only against a stand-in for the Bluetooth SDK and the fake camera. The
real camera over Bluetooth and Wi-Fi is untested.

## Wi-Fi fallback inside run.sh (older, not needed with USB or wireless.sh)

`./gopro/run.sh --wifi` pairs over Bluetooth with the official `open-gopro` SDK,
turns on the camera's access point and joins it (camera at `10.5.5.9`). On a Mac
with a single Wi-Fi radio this **drops internet**; to keep it, join the GoPro
with a second Wi-Fi interface (`--wifi-iface enX` for a USB Wi-Fi dongle) or use
Ethernet for internet. This path is untested on this camera.

## Testing without the camera

`tests/fake_camera.py` serves the same HTTP endpoints on 127.0.0.1 and streams a
synthetic HEVC test pattern, for checking the pipeline: run it, then
`./gopro/run.sh --ip 127.0.0.1 --bench 10`. It is not a substitute for the real camera.
