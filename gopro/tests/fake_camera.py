"""Software stand-in for the GoPro HTTP + UDP preview, for testing the pipeline
without hardware. NOT a substitute for a real-camera test.

python tests/fake_camera.py   # serves 127.0.0.1:8080, streams HEVC MPEG-TS to the caller's UDP port
"""
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

proc = {"p": None}
lock = threading.Lock()


def start_stream(host, port):
    with lock:
        stop_stream()
        proc["p"] = subprocess.Popen([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-re",
            "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
            "-c:v", "libx265", "-preset", "ultrafast", "-tune", "zerolatency",
            "-x265-params", "log-level=error", "-g", "30",
            "-f", "mpegts", f"udp://{host}:{port}?pkt_size=1316",
        ])


def stop_stream():
    p = proc["p"]
    if p and p.poll() is None:
        p.terminate()
        p.wait()
    proc["p"] = None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, body=b"{}"):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/gopro/camera/stream/start":
            port = int(parse_qs(u.query).get("port", ["8554"])[0])
            start_stream(self.client_address[0], port)
            return self._ok()
        if u.path == "/gopro/camera/stream/stop":
            stop_stream()
            return self._ok()
        if u.path == "/gopro/camera/info":
            return self._ok(b'{"model_name":"FAKE","firmware_version":"test"}')
        if u.path == "/gopro/camera/keep_alive":
            return self._ok()
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    srv = ThreadingHTTPServer(("127.0.0.1", 8080), H)
    try:
        srv.serve_forever()
    finally:
        stop_stream()
