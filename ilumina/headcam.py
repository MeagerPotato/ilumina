"""The head-worn GoPro as the tutor's camera.

Wraps the live feed in gopro/ (see gopro/README.md). There is one HeadCam per
bot process, because only one program can own the GoPro preview at a time. The
feed runs only while the student has the camera turned on. Nothing is saved.
"""

import io
import sys
import threading
import time
from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image

from ilumina import config

sys.path.insert(0, str(Path(__file__).parent.parent / "gopro"))
from gopro_cam import GoProFeed

# Same rule as the browser camera: an older frame is not shown to the tutor.
_MAX_FRAME_AGE_SECONDS = 2.0
# Wide enough to read handwriting on a page. The tutor gets one frame per turn.
_WIDTH = 768


def _gopro_feed():
    return GoProFeed(ip=config.GOPRO_IP, width=_WIDTH)


class HeadCam:
    def __init__(self, feed_factory=_gopro_feed):
        self._feed_factory = feed_factory
        self._feed = None
        self._lock = threading.Lock()

    @property
    def on(self) -> bool:
        return self._feed is not None

    @property
    def status(self) -> str:
        """The feed's own words, such as "finding camera" or "streaming"."""
        feed = self._feed
        return feed.status if feed else "off"

    def turn(self, on: bool) -> None:
        """Start or stop the feed. Stopping talks to the camera, so call it off the event loop."""
        with self._lock:
            if on and self._feed is None:
                self._feed = self._feed_factory().start(block=False)
            elif not on and self._feed is not None:
                feed, self._feed = self._feed, None
                try:
                    feed.stop()
                except Exception as e:  # noqa: BLE001 - off must always leave the camera unused
                    logger.warning(f"GoPro feed did not stop cleanly: {e}")

    def _newest(self) -> Image.Image | None:
        feed = self._feed
        frame = feed.latest() if feed else None
        if frame is None or time.monotonic() - frame.t > _MAX_FRAME_AGE_SECONDS:
            return None
        return Image.fromarray(np.ascontiguousarray(frame.image[:, :, ::-1]))  # BGR to RGB

    def picture(self) -> tuple[str, tuple[int, int], bytes] | None:
        """(format, size, raw bytes) of the newest frame for the tutor, or None."""
        image = self._newest()
        return ("RGB", image.size, image.tobytes()) if image else None

    def jpeg(self) -> bytes | None:
        """The newest frame as a JPEG for the dashboard preview, or None."""
        image = self._newest()
        if image is None:
            return None
        out = io.BytesIO()
        image.save(out, "JPEG", quality=70)
        return out.getvalue()
