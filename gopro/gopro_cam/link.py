"""python -m gopro_cam.link [--target 1234] [--wifi-iface en0]

Bring up the wireless link to the GoPro and hold it, so the camera can be worn
with no cable. It pairs over Bluetooth, turns on the camera's own Wi-Fi, joins
it with this Mac's Wi-Fi, then stays connected so the camera does not go to
sleep. Ctrl-C closes the link.

While this runs the Mac's Wi-Fi is on the GoPro, so internet has to come from
somewhere else. An iPhone on a cable with Personal Hotspot on is enough.

Anything that reads the feed (`GoProFeed`, or Ilumina started with
ILUMINA_CAMERA=gopro) then finds the camera at 10.5.5.9 by itself, as long as
the GoPro is not also plugged in over USB.
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys

import requests

from .camera import WIFI_AP_IP, ping_http


async def _camera_answers(seconds: float) -> bool:
    for _ in range(int(seconds)):
        if await asyncio.to_thread(ping_http, WIFI_AP_IP, 1.0):
            return True
        await asyncio.sleep(1)
    return False


def _online() -> bool:
    try:
        return requests.get("https://www.gstatic.com/generate_204", timeout=5).status_code == 204
    except requests.RequestException:
        return False


async def hold(target: str | None, iface: str):
    from open_gopro import WirelessGoPro

    print("Looking for the GoPro over Bluetooth. Accept the pairing request if the Mac shows one.")
    # Bluetooth only: we join the Wi-Fi ourselves, because the SDK's own join first
    # scans for the network name, which recent macOS versions hide from scripts.
    async with WirelessGoPro(target=target, interfaces={WirelessGoPro.Interface.BLE}) as gp:
        ssid = (await gp.ble_command.get_wifi_ssid()).data
        password = (await gp.ble_command.get_wifi_password()).data
        if not (await gp.ble_command.enable_wifi_ap(enable=True)).ok:
            sys.exit("The camera refused to turn its Wi-Fi on.")
        print(f'The camera\'s Wi-Fi "{ssid}" is on. Joining it with {iface}...')
        await asyncio.sleep(3)  # the network takes a moment to appear
        await asyncio.to_thread(
            subprocess.run, ["networksetup", "-setairportnetwork", iface, ssid, password],
            capture_output=True,
        )
        if not await _camera_answers(30):
            print(f'Could not join by itself. In the Wi-Fi menu pick "{ssid}" and type this password: {password}')
            while not await _camera_answers(10):
                pass
        print(f"The GoPro answers at {WIFI_AP_IP}. The wireless link is up.")
        if await asyncio.to_thread(_online):
            print("Internet still works through the other connection.")
        else:
            print("NO INTERNET right now. Plug in the iPhone with Personal Hotspot on, and in "
                  "System Settings > Network > ... > Set Service Order put it above Wi-Fi.")
        print("Leave this window open. Ctrl-C closes the link.")
        await asyncio.Event().wait()


def main(argv=None):
    p = argparse.ArgumentParser(prog="gopro_cam.link", description="Hold a wireless link to the GoPro")
    p.add_argument("--target", help="last 4 digits of the camera's Bluetooth name, if several are near")
    p.add_argument("--wifi-iface", default="en0", help="this Mac's Wi-Fi interface (default en0)")
    a = p.parse_args(argv)
    try:
        asyncio.run(hold(a.target, a.wifi_iface))
    except KeyboardInterrupt:
        print("\nLink closed. The Mac stays on the GoPro's Wi-Fi until you pick another network.")


if __name__ == "__main__":
    main()
