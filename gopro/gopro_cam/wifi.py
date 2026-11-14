"""Wi-Fi fallback: use the official open-gopro SDK to pair over BLE, turn on the
camera's access point, and join it. Afterwards the camera is at 10.5.5.9.

WARNING: on a Mac with one Wi-Fi radio, joining the GoPro AP disconnects you
from your normal Wi-Fi, so there is no internet unless you have a second
network interface (Ethernet / USB tether / USB Wi-Fi dongle). Prefer USB.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("gopro")


async def _connect(target: str | None, wifi_iface: str | None, keep_ble: bool):
    from open_gopro import WirelessGoPro

    gp = WirelessGoPro(target=target, host_wifi_interface=wifi_iface)
    await gp.open()
    log.info("connected over BLE + Wi-Fi AP: %s", gp.identifier)
    if not keep_ble:
        return gp
    return gp


def connect_wifi_ap(target: str | None = None, wifi_iface: str | None = None):
    """Blocking helper. Returns the open WirelessGoPro (call close_wifi on exit).

    target: last 4 digits of the camera name (e.g. "1234" for "GoPro 1234").
    wifi_iface: macOS interface to join the GoPro AP with (default: first Wi-Fi).
    """
    loop = asyncio.new_event_loop()
    gp = loop.run_until_complete(_connect(target, wifi_iface, True))
    gp._ogp_loop = loop  # keep the loop alive for close
    return gp


def close_wifi(gp):
    try:
        gp._ogp_loop.run_until_complete(gp.close())
    except Exception as e:  # best effort
        log.warning("closing GoPro BLE/Wi-Fi: %s", e)
