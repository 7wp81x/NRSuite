"""NRSuite command implementations.

These modules keep the original command behavior while getting the CLI entry
point out of a single monolithic file.
"""

import base64
import os
import re
import struct
import sys
import threading
import time

from ..config import DATA_DIR, HTML_CHUNK_SIZE, MAX_B64_LEN
from ..ui import C, _signal_bars, log
from ..bridge import _drain_stale, _setup_bridge, _wait_for_ready
from ..duckyscript import looks_like_script_line, split_pipe_commands as _split_pipe_commands
from ..eapol import parse_eapol_message

def do_ble_badble(fd: int = None, args=None):
    log("Starting BLE HID (script mode)...", C.CYAN)

    if not os.path.exists(args.payload):
        log(f"Payload file not found: {args.payload}", C.RED, level="err")
        return

    with open(args.payload, "r") as f:
        script = f.read()

    _, rx, tx, proto = _setup_bridge(fd)
    _drain_stale(rx)
    _wait_for_ready(proto)
    proto.start()
    start_resp = proto.send_cmd("BLE_START", {"name": args.advertise}, timeout=8)
    if not start_resp or not start_resp.get("ok"):
        log("Failed to start BLE advertising.", C.RED, level="err")
        proto.stop(); rx.stop(); rx.join(timeout=2)
        return

    log(f"Advertising as \033[1;92m{args.advertise}\033[0m — waiting for target to pair...", C.YELLOW)

    deadline = time.time() + args.pair_timeout
    connected = False
    while time.time() < deadline:
        status = proto.send_cmd("BLE_STATUS", timeout=3)
        if status and status.get("connected"):
            connected = True
            log(f"Paired with {status.get('peer', 'unknown')}", C.GREEN, level="ok")
            break
        time.sleep(0.5)

    if not connected:
        log("Timed out waiting for BLE pairing.", C.RED, level="err")
        proto.send_cmd("BLE_STOP", timeout=5)
        proto.stop(); rx.stop(); rx.join(timeout=2)
        return

    log("Running payload...", C.CYAN)
    if args.run_delay > 0:
        time.sleep(args.run_delay)

    resp = proto.send_cmd("BLE_RUN_SCRIPT", {"script": script}, timeout=max(30, len(script) // 20))

    if resp and resp.get("ok"):
        log(f"Payload finished ({resp.get('lines')} lines executed).", C.GREEN, level="ok")
    else:
        log("Payload execution failed or timed out.", C.RED, level="err")

    if not args.keep_alive:
        proto.send_cmd("BLE_STOP", timeout=5)

    proto.stop()
    rx.stop()
    rx.join(timeout=3)


def do_ble_keyboard(fd: int = None, args=None):
    log("Starting BLE HID (realtime keyboard mode)...", C.CYAN)
    log("Type text normally (sent as STRINGLN), or use script commands directly:", C.YELLOW)
    log("  GUI r          — key combo", C.YELLOW)
    log("  CTRL ALT DEL   — multi-key combo", C.YELLOW)
    log("  STRING hello   — no newline", C.YELLOW)
    log("  DELAY 500      — pause in ms", C.YELLOW)
    log("Use | to chain multiple commands on one line:", C.YELLOW)
    log("  DELAY 3000|STRINGLN test|STRING HELLO WORLD|", C.YELLOW)
    log("  || = literal '|' character, ||| = literal '|' + newline", C.YELLOW)
    log("Ctrl+C to stop.", C.YELLOW)

    _, rx, tx, proto = _setup_bridge(fd)
    _drain_stale(rx)
    _wait_for_ready(proto)
    proto.start()
    start_resp = proto.send_cmd("BLE_START", {"name": args.advertise}, timeout=8)
    if not start_resp or not start_resp.get("ok"):
        log("Failed to start BLE advertising.", C.RED, level="err")
        proto.stop(); rx.stop(); rx.join(timeout=2)
        return

    log(f"Advertising as \033[1;92m{args.advertise}\033[0m — waiting for target to pair...", C.YELLOW)

    deadline = time.time() + args.pair_timeout
    connected = False
    while time.time() < deadline:
        status = proto.send_cmd("BLE_STATUS", timeout=3)
        if status and status.get("connected"):
            connected = True
            log(f"Paired with {status.get('peer', 'unknown')}", C.GREEN, level="ok")
            break
        time.sleep(0.5)

    if not connected:
        log("Timed out waiting for BLE pairing.", C.RED, level="err")
        proto.send_cmd("BLE_STOP", timeout=5)
        proto.stop(); rx.stop(); rx.join(timeout=2)
        return

    time.sleep(1.0)

    try:
        while True:
            log("[SEND KEY (STRINGLN)] >>", C.CYAN)
            line = sys.stdin.readline()
            if not line:
                break
            raw = line.rstrip("\n")
            if not raw:
                continue

            for text in _split_pipe_commands(raw):
                if not text:
                    continue

                if looks_like_script_line(text):
                    script = text
                else:
                    script = f"STRINGLN {text}"

                resp = proto.send_cmd("BLE_RUN_SCRIPT", {"script": script}, timeout=10)
                if not resp or not resp.get("ok"):
                    msg = resp.get("msg") if resp else "timed out"
                    log(f"Failed to send {text!r}: {msg}", C.RED, level="err")
    except KeyboardInterrupt:
        log("\nStopping realtime session...", C.YELLOW)
    finally:
        proto.send_cmd("BLE_RELEASE_ALL", timeout=5)
        if not args.keep_alive:
            proto.send_cmd("BLE_STOP", timeout=5)
        proto.stop()
        rx.stop()
        rx.join(timeout=3)
