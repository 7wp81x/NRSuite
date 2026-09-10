"""NRSuite argparse CLI and command dispatch."""

import argparse
import os
import sys

from .commands import (
    do_badusb,
    do_beacon,
    do_ble_badble,
    do_ble_keyboard,
    do_deauth,
    do_masstorage,
    do_portal,
    do_scan,
    do_sniff,
)
from .devices import bootstrap, do_list_devices
from .espbridge_compat import detect_backend
from .ui import C, banner, log


def _extract_device_flag(argv: list[str]):
    """
    Pull -d/--device out of argv so both of these work:
      nrsuite -d 0 scan
      nrsuite scan -d 0
    Subparsers alone treat a leading "0" as the command name (invalid choice).
    Returns (device_spec | None, argv_without_device_flag).
    """
    device = None
    out = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-d", "--device"):
            if i + 1 >= len(argv):
                raise SystemExit("error: -d/--device requires a path or index (see: nrsuite devices)")
            device = argv[i + 1]
            i += 2
            continue
        if a.startswith("--device="):
            device = a.split("=", 1)[1]
            i += 1
            continue
        out.append(a)
        i += 1
    return device, out

def main():
    parser = argparse.ArgumentParser(
        description="NRSuite - A wireless toolkit without root.",
        epilog="Device select:  nrsuite -d 0 scan  |  nrsuite scan -d 0  |  nrsuite devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-d", "--device",
        metavar="PATH|INDEX",
        default=None,
        help="USB device path or index (also accepted after the subcommand)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("devices", help="List connected USB devices (for -d/--device)")
    subparsers.add_parser("scan", help="Scan nearby WiFi networks")

    # Sniff
    sniff_p = subparsers.add_parser("sniff", help="Packet sniffing")
    sniff_p.add_argument("--channel", type=int, default=1)
    sniff_p.add_argument("--hop", action="store_true")
    sniff_p.add_argument("--interval", type=int, default=300)
    sniff_p.add_argument("--eapol-only", action="store_true")
    sniff_p.add_argument("--bssid")
    sniff_p.add_argument("--client", default="FF:FF:FF:FF:FF:FF")
    sniff_p.add_argument("--deauth", action="store_true")
    sniff_p.add_argument("--count", type=int, default=0)
    sniff_p.add_argument("--duration", type=int, default=0)
    sniff_p.add_argument("-o", "--output")
    sniff_p.add_argument("--stream", action="store_true")

    # Pure Deauth
    deauth_p = subparsers.add_parser("deauth", help="Send deauthentication frames")
    deauth_p.add_argument("--bssid", required=True)
    deauth_p.add_argument("--channel", type=int, required=True)
    deauth_p.add_argument("--client", default="FF:FF:FF:FF:FF:FF")
    deauth_p.add_argument("--count", type=int, default=0)
    deauth_p.add_argument("--duration", type=int, default=0)
    deauth_p.add_argument("--interval", type=int, default=100)

    # Beacon spam
    beacon_p = subparsers.add_parser("beacon", help="Broadcast 802.11 beacons (beacon spam / custom SSIDs)")
    beacon_p.add_argument("beacon_action", nargs="?", default="start", choices=["start", "stop", "status"], help="start (default) | stop | status")
    beacon_p.add_argument("--ssid", action="append", default=[],help="SSID to advertise (repeat for multiple)")
    beacon_p.add_argument("--file", help="Text file with one SSID per line (# comments allowed)")
    beacon_p.add_argument("--channel", type=int, default=6, help="Channel 1-13 (default 6)")
    beacon_p.add_argument("--interval", type=int, default=20,help="Milliseconds between consecutive beacon TX (default 20)")
    beacon_p.add_argument("--stable-bssid", action="store_true",help="Derive BSSID from SSID hash instead of randomizing each run")
    beacon_p.add_argument("--hidden", action="store_true",help="Advertise as hidden networks (SSID length 0 in the beacon)")

    portal_p = subparsers.add_parser("portal", help="Captive Portal")
    portal_p.add_argument("action", choices=["start", "stop", "status"])
    portal_p.add_argument("--ssid", default="Free WiFi")
    portal_p.add_argument("--channel", type=int, default=6)
    portal_p.add_argument("--bssid", help="Target BSSID for auto EAPOL")
    portal_p.add_argument("--file", help="HTML file to upload (for start or html action)")

    # BLE HID
    ble_p = subparsers.add_parser("ble", help="BLE HID keyboard / DuckyScript injection")
    ble_sub = ble_p.add_subparsers(dest="ble_action", required=True)

    badble_p = ble_sub.add_parser("badble", help="Run a DuckyScript payload over BLE")
    badble_p.add_argument("--advertise", default="Keyboard", help="BLE device name to advertise")
    badble_p.add_argument("--payload", required=True, help="Path to DuckyScript .txt file")
    badble_p.add_argument("--pair-timeout", type=int, default=60, help="Seconds to wait for pairing")
    badble_p.add_argument("--run-delay", type=float, default=0, help="Seconds to wait after pairing before running")
    badble_p.add_argument("--keep-alive", action="store_true", help="Keep BLE advertising after payload finishes")

    keyboard_p = ble_sub.add_parser("keyboard", help="Realtime keystroke passthrough from this terminal")
    keyboard_p.add_argument("--advertise", default="Keyboard", help="BLE device name to advertise")
    keyboard_p.add_argument("--pair-timeout", type=int, default=60, help="Seconds to wait for pairing")
    keyboard_p.add_argument("--keep-alive", action="store_true", help="Keep BLE advertising after session ends")

    masstorage_p = subparsers.add_parser("masstorage", help="Mass storage operations")
    masstorage_sub = masstorage_p.add_subparsers(dest="msc_action", required=True)
    msc_start_p = masstorage_sub.add_parser("start", help="Enter USB mass storage mode")
    msc_files_p = masstorage_sub.add_parser("files", help="List files without entering MSC mode")
    msc_delete_p = masstorage_sub.add_parser("delete", help="Delete a file if it exists")
    msc_delete_p.add_argument("file", help="Path/name of the file to delete")
    msc_free_p = masstorage_sub.add_parser("free", help="Show storage free/used/total size")
    
    masstorage_p.set_defaults(func=do_masstorage)
    
    
    badusb_p = subparsers.add_parser("badusb", help="USB BadUSB for supported devices.")
    badusb_p.add_argument("--payload", required=True, help="Path to DuckyScript .txt file")
    badusb_p.add_argument("--masstorage", action="store_true", help="Enable also mass storage mode")
    

    # Strip -d/--device first so it can appear before or after the subcommand.
    device_pre, argv_rest = _extract_device_flag(sys.argv[1:])
    args = parser.parse_args(argv_rest)
    if not os.environ.get("NRSUITE_CHILD"):
        banner()

    if args.command == "devices":
        do_list_devices()
        return

    try:
        backend = detect_backend()
    except RuntimeError as e:
        print(f"\033[0;91m[!]\033[0m {e}", file=sys.stderr)
        sys.exit(1)

    device_spec = device_pre or getattr(args, "device", None) or os.environ.get("NRSUITE_DEVICE")

    fd_str = os.environ.get("TERMUX_USB_FD")
    if backend == "root":
        # Root path: currently opens first matching device via wrap_direct().
        # --device is recorded for future multi-device root selection.
        if device_spec:
            log(f"Device selector: {device_spec} (root backend uses first matching libusb device)", C.YELLOW)
        if args.command == "scan":
            do_scan()
        elif args.command == "sniff":
            do_sniff(args=args)
        elif args.command == "deauth":
            do_deauth(args=args)
        elif args.command == "beacon":
            do_beacon(args=args)
        elif args.command == "portal": do_portal(args=args)
        elif args.command == "ble":
            if args.ble_action == "badble": do_ble_badble(args=args)
            elif args.ble_action == "keyboard": do_ble_keyboard(args=args)
        elif args.command == "masstorage":
            do_masstorage(args=args)
        elif args.command == "badusb":
            do_badusb(args=args)
    elif fd_str is None:
        print("\033[0;93m[*]\033[0m Backend: termux-api (no-root)", file=sys.stderr)
        extra = argv_rest[1:]
        bootstrap(args.command, extra, device_spec=device_spec)
    else:
        fd = int(fd_str)
        if args.command == "scan":do_scan(fd=fd)
        elif args.command == "sniff":do_sniff(fd=fd, args=args)
        elif args.command == "deauth":do_deauth(fd=fd, args=args)
        elif args.command == "beacon": do_beacon(fd=fd, args=args)
        elif args.command == "portal": do_portal(fd=fd, args=args)
        elif args.command == "ble":
            if args.ble_action == "badble": do_ble_badble(fd=fd, args=args)
            elif args.ble_action == "keyboard": do_ble_keyboard(fd=fd, args=args)
        elif args.command == "masstorage": do_masstorage(fd=fd, args=args)
        elif args.command == "badusb": do_badusb(fd=fd, args=args)
