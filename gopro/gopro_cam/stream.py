"""Receive the GoPro preview (MPEG-TS over UDP) and expose decoded frames.

FFmpeg does the UDP receive + H.264/HEVC decode and pipes raw BGR frames to us.
A reader thread keeps only the newest frame, so consumers never fall behind.
A supervisor thread restarts the camera preview and FFmpeg if frames stop.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .camera import DEFAULT_UDP_PORT, CameraNotFound, GoProHTTP, discover

log = logging.getLogger("gopro")


@dataclass
class Frame:
    image: np.ndarray  # HxWx3 uint8, BGR (OpenCV order)
    t: float           # time.monotonic() when the frame finished decoding
    index: int         # running frame counter since start()


class FFmpegUDPReader:
    """One FFmpeg process reading udp://:port and emitting BGR frames."""

    def __init__(self, port: int, width: int | None = None):
        if not shutil.which("ffmpeg"):
            raise RuntimeError("ffmpeg not found; install with `brew install ffmpeg`")
        self.port = port
        self.width = width
        self.size: tuple[int, int] | None = None
        self.codec: str | None = None
        self.src_size: tuple[int, int] | None = None
        self.src_fps: float | None = None
        self.proc: subprocess.Popen | None = None
        self._size_ready = threading.Event()
        self.stderr_tail: list[str] = []

    def start(self):
        url = f"udp://@0.0.0.0:{self.port}?overrun_nonfatal=1&fifo_size=5000000&buffer_size=4194304&reuse=1"
        vf = ["-vf", f"scale={self.width}:-2"] if self.width else []
        cmd = [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "info",
            "-fflags", "nobuffer+discardcorrupt", "-flags", "low_delay",
            "-probesize", "1000000", "-analyzeduration", "1000000",
            "-i", url, "-an", *vf,
            "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
        ]
        log.debug("ffmpeg: %s", " ".join(cmd))
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        threading.Thread(target=self._read_stderr, daemon=True, name="ffmpeg-stderr").start()

    def _read_stderr(self):
        in_output = False
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode(errors="replace").rstrip()
            self.stderr_tail = (self.stderr_tail + [line])[-30:]
            if line.startswith("Output #0"):
                in_output = True
            m = re.search(r"Video: (\w+).*?, (\d{2,5})x(\d{2,5})", line)
            if m:
                w, h = int(m.group(2)), int(m.group(3))
                if not in_output:
                    self.codec, self.src_size = m.group(1), (w, h)
                    f = re.search(r"([\d.]+) fps", line)
                    self.src_fps = float(f.group(1)) if f else None
                elif self.size is None:
                    self.size = (w, h)
                    self._size_ready.set()

    def wait_for_size(self, timeout: float) -> bool:
        return self._size_ready.wait(timeout)

    def read(self) -> np.ndarray | None:
        w, h = self.size
        n = w * h * 3
        buf = bytearray()
        while len(buf) < n:
            chunk = self.proc.stdout.read(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return np.frombuffer(bytes(buf), np.uint8).reshape(h, w, 3)

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(2)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class GoProFeed:
    """Live GoPro frames with automatic reconnection.

    feed = GoProFeed().start()
    frame = feed.latest()          # newest Frame or None
    frame = feed.wait_frame(5)     # block until a frame newer than the last one
    feed.save_latest("shot.jpg")
    feed.stop()
    """

    def __init__(self, ip: str | None = None, serial: str | None = None,
                 port: int = DEFAULT_UDP_PORT, width: int | None = None,
                 wifi: bool = False, stall_timeout: float = 4.0, connect_timeout: float = 30.0):
        self.ip, self.serial, self.port, self.width, self.wifi = ip, serial, port, width, wifi
        self.stall_timeout, self.connect_timeout = stall_timeout, connect_timeout
        self.http: GoProHTTP | None = None
        self.reader: FFmpegUDPReader | None = None
        self._latest: Frame | None = None
        self._count = 0
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self.reconnects = 0
        self.status = "idle"
        self.arrivals: list[float] = []  # monotonic times of recent frames (for fps)

    # ---- lifecycle -------------------------------------------------------
    def start(self, block: bool = True) -> "GoProFeed":
        self._stop.clear()
        t = threading.Thread(target=self._supervise, daemon=True, name="gopro-supervisor")
        t.start()
        self._threads.append(t)
        if block and not self.wait_frame(self.connect_timeout, newer_than=-1):
            reason = self.status
            self.stop()
            raise TimeoutError(f"no video from GoPro within {self.connect_timeout:.0f}s ({reason})")
        return self

    def stop(self):
        self._stop.set()
        if self.reader:
            self.reader.stop()
        if self.http:
            self.http.close()
        self.status = "stopped"
        with self._cond:
            self._cond.notify_all()

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # ---- consumer API ----------------------------------------------------
    def latest(self) -> Frame | None:
        return self._latest

    def wait_frame(self, timeout: float = 5.0, newer_than: int | None = None) -> Frame | None:
        if newer_than is None:
            newer_than = self._latest.index if self._latest else -1
        deadline = time.monotonic() + timeout
        with self._cond:
            while not self._stop.is_set():
                if self._latest and self._latest.index > newer_than:
                    return self._latest
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._cond.wait(left)
        return None

    def save_latest(self, path: str | Path) -> Path | None:
        import cv2
        f = self._latest
        if f is None:
            return None
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(path), f.image)
        return path

    def fps(self, window: float = 2.0) -> float:
        now = time.monotonic()
        recent = [t for t in self.arrivals if now - t <= window]
        return (len(recent) - 1) / (recent[-1] - recent[0]) if len(recent) > 2 else 0.0

    # ---- internals -------------------------------------------------------
    def _connect(self):
        self.status = "finding camera"
        ip = discover(self.ip, self.serial, self.wifi)
        self.ip = ip
        if self.http:
            self.http.close()
        self.http = GoProHTTP(ip)
        try:
            info = self.http.info()
            log.info("camera %s fw %s at %s", info.get("model_name"), info.get("firmware_version"), ip)
        except Exception:
            log.info("camera at %s", ip)
        self.reader = FFmpegUDPReader(self.port, self.width)
        self.reader.start()          # listen before the camera starts sending
        time.sleep(0.3)
        self.status = "starting preview"
        self.http.start_preview(self.port)
        self.http.start_keep_alive()
        self.status = "waiting for video"
        if not self.reader.wait_for_size(15):
            tail = "\n".join(self.reader.stderr_tail[-5:])
            raise RuntimeError(f"preview started but no decodable video on UDP {self.port}\n{tail}")
        log.info("stream %s %s @ %s fps -> frames %s", self.reader.codec, self.reader.src_size,
                 self.reader.src_fps, self.reader.size)
        self.status = "streaming"

    def _pump(self) -> str:
        """Read frames until stall/EOF. Returns the reason it stopped."""
        reader = self.reader
        result = {"why": "eof"}

        def read_loop():
            while not self._stop.is_set():
                img = reader.read()
                if img is None:
                    return
                now = time.monotonic()
                with self._cond:
                    self._count += 1
                    self._latest = Frame(img, now, self._count)
                    self.arrivals = (self.arrivals + [now])[-120:]
                    self._cond.notify_all()

        t = threading.Thread(target=read_loop, daemon=True, name="gopro-reader")
        t.start()
        last_seen = time.monotonic()
        last_idx = self._count
        while not self._stop.is_set() and t.is_alive():
            time.sleep(0.25)
            if self._count != last_idx:
                last_idx, last_seen = self._count, time.monotonic()
            elif time.monotonic() - last_seen > self.stall_timeout:
                result["why"] = f"no frames for {self.stall_timeout:.0f}s"
                break
        reader.stop()
        return "stopped" if self._stop.is_set() else result["why"]

    def _supervise(self):
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._connect()
                backoff = 1.0
                why = self._pump()
                if self._stop.is_set():
                    return
                log.warning("stream lost (%s); reconnecting", why)
            except CameraNotFound as e:
                self.status = "camera not found"
                log.warning("%s", e)
            except Exception as e:
                self.status = f"error: {e}"
                log.warning("connect failed: %s", e)
            if self.reader:
                self.reader.stop()
            self.reconnects += 1
            self.status = f"reconnecting in {backoff:.0f}s"
            if self._stop.wait(backoff):
                return
            backoff = min(backoff * 2, 10.0)
