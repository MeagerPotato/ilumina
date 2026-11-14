"""Find and control a GoPro over the Open GoPro HTTP API (USB or Wi-Fi).

Verified against https://gopro.github.io/OpenGoPro/http (spec v2.0):
  * USB: camera is a USB network adapter at 172.2X.1YZ.51:8080, where XYZ are
    the last 3 digits of the serial. LIT HERO needs Preferences > Connections >
    GoPro Connect enabled on the camera (no wired_usb command needed).
  * Wi-Fi AP: camera is at 10.5.5.9:8080 (AP must be enabled over BLE first).
  * Preview: GET /gopro/camera/stream/start?port=N makes the camera send
    MPEG-TS over UDP to the requesting host on port N (default 8554).
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
import threading
import time

import requests

HTTP_PORT = 8080
WIFI_AP_IP = "10.5.5.9"
DEFAULT_UDP_PORT = 8554


class CameraNotFound(RuntimeError):
    pass


def ip_from_serial(serial: str) -> str:
    """172.2X.1YZ.51 from the last three digits XYZ of the serial number."""
    digits = re.sub(r"\D", "", serial)[-3:]
    if len(digits) != 3:
        raise ValueError(f"need at least 3 digits in serial, got {serial!r}")
    return f"172.2{digits[0]}.1{digits[1:]}.51"


def usb_candidate_ips() -> list[str]:
    """Camera IPs implied by any local interface on a 172.2X.1YZ.0/24 subnet."""
    out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    ips = []
    for m in re.finditer(r"inet (172\.2\d\.1\d\d)\.(\d+)", out):
        cam = f"{m.group(1)}.51"
        if cam not in ips:
            ips.append(cam)
    return ips


def ping_http(ip: str, timeout: float = 1.5) -> bool:
    try:
        r = requests.get(f"http://{ip}:{HTTP_PORT}/gopro/camera/keep_alive", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def discover(ip: str | None = None, serial: str | None = None, wifi: bool = False) -> str:
    """Return a reachable camera IP or raise CameraNotFound with a helpful hint."""
    tried = []
    candidates = []
    if ip:
        candidates.append(ip)
    if serial:
        candidates.append(ip_from_serial(serial))
    candidates += usb_candidate_ips()
    if wifi or not candidates:
        candidates.append(WIFI_AP_IP)
    for c in dict.fromkeys(candidates):
        tried.append(c)
        if ping_http(c):
            return c
    raise CameraNotFound(
        "No GoPro answered on " + ", ".join(tried) + ".\n"
        "USB: plug in a USB-C *data* cable, power the camera on, and enable "
        "Preferences > Connections > GoPro Connect on the camera. A new "
        "network interface with a 172.2x.1xx.x address should appear (check "
        "`ifconfig`).\n"
        "Wi-Fi: run with --wifi so Bluetooth turns on the camera's access point."
    )


class GoProHTTP:
    """Thin wrapper over the few HTTP endpoints we need, plus a keep-alive."""

    def __init__(self, ip: str, timeout: float = 3.0):
        self.ip = ip
        self.base = f"http://{ip}:{HTTP_PORT}"
        self.timeout = timeout
        self._ka_stop = threading.Event()
        self._ka_thread: threading.Thread | None = None

    def get(self, path: str, **params):
        r = requests.get(self.base + path, params=params or None, timeout=self.timeout)
        r.raise_for_status()
        try:
            return r.json()
        except ValueError:
            return r.text

    def info(self) -> dict:
        return self.get("/gopro/camera/info")

    def start_preview(self, port: int = DEFAULT_UDP_PORT):
        # Stop first: start fails with 409 if a preview is already running.
        try:
            self.stop_preview()
        except requests.RequestException:
            pass
        params = {} if port == DEFAULT_UDP_PORT else {"port": port}
        return self.get("/gopro/camera/stream/start", **params)

    def stop_preview(self):
        return self.get("/gopro/camera/stream/stop")

    def keep_alive(self) -> bool:
        return ping_http(self.ip, timeout=self.timeout)

    def start_keep_alive(self, interval: float = 3.0):
        def loop():
            while not self._ka_stop.wait(interval):
                self.keep_alive()

        self._ka_stop.clear()
        self._ka_thread = threading.Thread(target=loop, name="gopro-keepalive", daemon=True)
        self._ka_thread.start()

    def close(self):
        self._ka_stop.set()
        try:
            self.stop_preview()
        except requests.RequestException:
            pass
