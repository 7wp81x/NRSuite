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

def do_beacon(fd: int = None, args=None):
    """Broadcast 802.11 beacons continuously until Ctrl+C."""
    action = getattr(args, "beacon_action", "start") or "start"

    _, rx, tx, proto = _setup_bridge(fd)
    _drain_stale(rx)
    _wait_for_ready(proto)
    proto.start()

    started = False
    try:
        if action == "stop":
            resp = proto.send_cmd("STOP_BEACON", timeout=5)
            if resp and resp.get("ok"):
                log(f"Beacon spam stopped. Frames sent: {resp.get('sent', 0)}",
                    C.GREEN, level="ok")
            else:
                log("Failed to stop beacon spam.", C.RED, level="err")
            return

        if action == "status":
            resp = proto.send_cmd("BEACON_STATUS", timeout=5)
            if resp and resp.get("ok"):
                log(f"Active:  {resp.get('active')}", C.CYAN)
                log(f"SSIDs:   {resp.get('ssids')}", C.CYAN)
                log(f"Sent:    {resp.get('sent')}", C.CYAN)
                log(f"Channel: {resp.get('channel')}", C.CYAN)
            else:
                log("Failed to get beacon status.", C.RED, level="err")
            return

        # --- start (runs continuously until Ctrl+C) ---
        ssids = []
        if getattr(args, "file", None):
            if not os.path.exists(args.file):
                log(f"SSID list file not found: {args.file}", C.RED, level="err")
                return
            with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        ssids.append(line)
        if getattr(args, "ssid", None):
            for s in args.ssid:
                ssids.append(s)

        if not ssids:
            log("No SSIDs given. Use --ssid NAME (repeatable) or --file list.txt",
                C.RED, level="err")
            return

        if len(ssids) > 32:
            log(f"Truncating SSID list from {len(ssids)} to 32 (firmware max).",
                C.YELLOW, level="warn")
            ssids = ssids[:32]

        ssids_payload = "\n".join(ssids)
        channel = int(getattr(args, "channel", 6) or 6)
        interval = int(getattr(args, "interval", 20) or 20)
        random_bssid = not getattr(args, "stable_bssid", False)
        hidden = bool(getattr(args, "hidden", False))

        log(f"Starting beacon spam: {len(ssids)} SSID(s) on channel {channel}, "
            f"interval {interval} ms", C.CYAN)
        for s in ssids[:8]:
            log(f"  • {s}", C.YELLOW)
        if len(ssids) > 8:
            log(f"  … and {len(ssids) - 8} more", C.YELLOW)

        resp = proto.send_cmd("START_BEACON", {
            "ssids": ssids_payload,
            "channel": channel,
            "interval_ms": interval,
            "random_bssid": random_bssid,
            "hidden": hidden,
        }, timeout=10)

        if not resp or not resp.get("ok"):
            msg = resp.get("msg") if resp else "timed out"
            log(f"Failed to start beacon spam: {msg}", C.RED, level="err")
            return

        started = True
        log(f"Beacon spam running continuously ({resp.get('ssids')} SSIDs). "
            f"Press Ctrl+C to stop.", C.GREEN, level="ok")

        # Stay alive — firmware keeps transmitting in loop(); we just wait.
        # Occasional status tick so the session doesn't look frozen.
        last_log = 0
        while True:
            time.sleep(0.5)
            now = time.time()
            if now - last_log >= 5.0:
                last_log = now
                st = proto.send_cmd("BEACON_STATUS", timeout=3)
                if st and st.get("ok"):
                    log(f"  still running — sent={st.get('sent')} frames",
                        C.MAGENTA)

    except KeyboardInterrupt:
        log("\nCtrl+C — stopping beacon spam...", C.YELLOW)
    finally:
        if started:
            try:
                stop = proto.send_cmd("STOP_BEACON", timeout=5)
                if stop and stop.get("ok"):
                    log(f"Stopped. Total frames sent: {stop.get('sent', 0)}",
                        C.GREEN, level="ok")
                else:
                    log("Stop command failed (device may still be transmitting "
                        "until reset).", C.YELLOW, level="warn")
            except Exception:
                pass
        try:
            proto.stop()
        except Exception:
            pass
        try:
            rx.stop()
            rx.join(timeout=3)
        except Exception:
            pass
