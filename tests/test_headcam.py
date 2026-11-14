import time
from types import SimpleNamespace

import numpy as np

from ilumina.headcam import HeadCam


class FakeFeed:
    status = "streaming"

    def __init__(self, age_seconds=0.0):
        blue_first = np.zeros((2, 3, 3), np.uint8)
        blue_first[:, :, 0] = 255  # OpenCV order: blue, green, red
        self._frame = SimpleNamespace(image=blue_first, t=time.monotonic() - age_seconds)
        self.stopped = False

    def start(self, block=True):
        return self

    def latest(self):
        return self._frame

    def stop(self):
        self.stopped = True


def test_off_until_turned_on_and_stops_the_feed_when_turned_off():
    feed = FakeFeed()
    cam = HeadCam(feed_factory=lambda: feed)
    assert not cam.on and cam.picture() is None and cam.status == "off"
    cam.turn(True)
    assert cam.on and cam.picture() is not None and cam.status == "streaming"
    cam.turn(False)
    assert feed.stopped and not cam.on and cam.picture() is None


def test_picture_is_rgb_with_width_then_height():
    cam = HeadCam(feed_factory=FakeFeed)
    cam.turn(True)
    format, size, image = cam.picture()
    assert format == "RGB" and size == (3, 2)
    assert image[:3] == bytes([0, 0, 255])  # the blue pixel, now red-green-blue order
    assert cam.jpeg()[:2] == b"\xff\xd8"


def test_a_stale_frame_is_not_a_picture():
    cam = HeadCam(feed_factory=lambda: FakeFeed(age_seconds=10))
    cam.turn(True)
    assert cam.picture() is None and cam.jpeg() is None


def test_only_the_newest_session_turns_the_camera_off():
    cam = HeadCam(feed_factory=FakeFeed)
    old, new = object(), object()
    cam.claim(old)
    cam.turn(True)
    cam.claim(new)  # a new session starts with the camera off
    assert not cam.on
    cam.turn(True)
    cam.release(old)  # the old session ends late
    assert cam.on
    cam.release(new)
    assert not cam.on


def test_a_feed_that_fails_to_stop_still_counts_as_off():
    class BrokenFeed(FakeFeed):
        def stop(self):
            raise RuntimeError("camera unplugged")

    cam = HeadCam(feed_factory=BrokenFeed)
    cam.turn(True)
    cam.turn(False)
    assert not cam.on and cam.picture() is None
