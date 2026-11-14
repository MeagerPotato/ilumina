"""python -m gopro_cam [--headless] [--save-dir DIR] [--bench SECONDS] ...

Keys in the preview window: q / Esc quit, s save a frame, l latency test
(point the camera at the window first).
"""
from __future__ import annotations

import argparse
import json
import logging
import signal
import statistics
import sys
import time
from pathlib import Path

from .camera import CameraNotFound
from .stream import GoProFeed

log = logging.getLogger("gopro")


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="gopro_cam", description="Live GoPro LIT HERO preview")
    p.add_argument("--ip", help="camera IP (default: auto-detect USB, then 10.5.5.9)")
    p.add_argument("--serial", help="camera serial number (USB IP is derived from it)")
    p.add_argument("--wifi", action="store_true", help="pair over Bluetooth and join the camera Wi-Fi AP (drops internet on single-Wi-Fi Macs)")
    p.add_argument("--wifi-iface", help="Wi-Fi interface for the GoPro AP, e.g. en7 for a USB dongle")
    p.add_argument("--target", help="last 4 digits of the camera's Bluetooth name, for --wifi")
    p.add_argument("--port", type=int, default=8554, help="UDP port for the preview (default 8554)")
    p.add_argument("--width", type=int, help="resize frames to this width (keeps aspect)")
    p.add_argument("--headless", action="store_true", help="no window; just log stats")
    p.add_argument("--save-dir", default="captures", help="where 's' / --save-every write JPEGs")
    p.add_argument("--save-every", type=float, help="also save a frame every N seconds")
    p.add_argument("--bench", type=float, help="run N seconds, print JSON stats, exit")
    p.add_argument("--latency", action="store_true", help="run the screen-flash latency test (camera must face the screen) and exit")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def latency_test(feed, cv2, np, rounds=8):
    """Flash the preview window white/black and time how long until the camera
    sees it. Requires the camera to be pointed at this window."""
    win = "GoPro latency test"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(win, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    black = np.zeros((720, 1280, 3), np.uint8)
    white = black + 255

    def brightness():
        f = feed.latest()
        h, w = f.image.shape[:2]
        return float(f.image[h // 4: 3 * h // 4, w // 4: 3 * w // 4].mean())

    results = []
    for i in range(rounds):
        cv2.imshow(win, black)
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            cv2.waitKey(10)
        dark = brightness()
        cv2.imshow(win, white)
        cv2.waitKey(1)
        t0 = time.monotonic()
        hit = None
        while time.monotonic() - t0 < 3:
            cv2.waitKey(1)
            f = feed.latest()
            if f.t > t0 and brightness() > dark + 40:
                hit = f.t - t0
                break
        if hit is not None:
            results.append(hit)
        print(f"  round {i + 1}: " + (f"{hit * 1000:.0f} ms" if hit else "no change seen"))
    cv2.destroyWindow(win)
    if results:
        print(f"latency: median {statistics.median(results) * 1000:.0f} ms, "
              f"min {min(results) * 1000:.0f} ms, max {max(results) * 1000:.0f} ms "
              f"(includes ~1 display refresh)")
    else:
        print("latency test failed: point the camera at the screen and retry")
    return results


def main(argv=None):
    a = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    import cv2
    import numpy as np

    wifi_gp = None
    if a.wifi:
        from .wifi import close_wifi, connect_wifi_ap
        print("Pairing over Bluetooth and joining the GoPro Wi-Fi (internet on that radio will drop)...")
        wifi_gp = connect_wifi_ap(a.target, a.wifi_iface)
        a.ip = a.ip or "10.5.5.9"

    feed = GoProFeed(ip=a.ip, serial=a.serial, port=a.port, width=a.width, wifi=a.wifi)
    stop = {"flag": False}
    signal.signal(signal.SIGINT, lambda *_: stop.__setitem__("flag", True))
    signal.signal(signal.SIGTERM, lambda *_: stop.__setitem__("flag", True))

    try:
        print("Connecting to GoPro...")
        feed.start()
    except (TimeoutError, CameraNotFound) as e:
        print(f"\nERROR: {e}\n\nLast status: {feed.status}", file=sys.stderr)
        if wifi_gp:
            close_wifi(wifi_gp)
        return 2

    r = feed.reader
    print(f"Streaming from {feed.ip}: {r.codec} {r.src_size} @ {r.src_fps} fps -> frames {r.size}")
    save_dir = Path(a.save_dir)
    if a.latency:
        print("Point the camera at the screen. Starting in 5 s...")
        time.sleep(5)
        res = latency_test(feed, cv2, np)
        feed.stop()
        return 0 if res else 1
    t_start = time.monotonic()
    last_save = last_log = t_start
    gaps, prev_t, frames0 = [], None, feed.latest().index
    shown = None

    try:
        while not stop["flag"]:
            if a.bench and time.monotonic() - t_start >= a.bench:
                break
            f = feed.wait_frame(0.5)
            now = time.monotonic()
            if f:
                if prev_t is not None:
                    gaps.append(f.t - prev_t)
                prev_t = f.t
            if a.save_every and f and now - last_save >= a.save_every:
                last_save = now
                p = feed.save_latest(save_dir / f"frame_{time.strftime('%Y%m%d_%H%M%S')}_{f.index}.jpg")
                log.info("saved %s", p)
            if a.headless or a.bench:
                if now - last_log >= 2:
                    last_log = now
                    log.info("%s fps=%.1f frames=%d reconnects=%d", feed.status, feed.fps(),
                             feed.latest().index, feed.reconnects)
                continue
            if f and f is not shown:
                shown = f
                img = f.image.copy()
                age = time.monotonic() - f.t
                txt = f"{img.shape[1]}x{img.shape[0]}  {feed.fps():.1f} fps  {feed.status}"
                cv2.putText(img, txt, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
                cv2.putText(img, txt, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                cv2.imshow("GoPro (q quit, s save, l latency)", img)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                p = feed.save_latest(save_dir / f"frame_{time.strftime('%Y%m%d_%H%M%S')}.jpg")
                print(f"saved {p}")
            if key == ord("l"):
                latency_test(feed, cv2, np)
    finally:
        elapsed = time.monotonic() - t_start
        n = feed.latest().index - frames0 if feed.latest() else 0
        feed.stop()
        if wifi_gp:
            close_wifi(wifi_gp)
        cv2.destroyAllWindows()
        stats = {
            "camera_ip": feed.ip, "codec": r.codec, "source_size": r.src_size,
            "source_fps": r.src_fps, "frame_size": r.size, "seconds": round(elapsed, 1),
            "frames": n, "avg_fps": round(n / elapsed, 2) if elapsed else 0,
            "max_gap_ms": round(max(gaps) * 1000) if gaps else None,
            "p95_gap_ms": round(sorted(gaps)[int(len(gaps) * 0.95)] * 1000) if len(gaps) > 20 else None,
            "reconnects": feed.reconnects,
        }
        print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
