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

def do_scan(fd: int = None):
    log("Starting network scan...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)
    networks = []

    def on_event(ev):
        if ev and ev.get("type") == "scan_ap":
            networks.append(ev)

    proto.on_event = on_event
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)

    resp = proto.send_cmd("SCAN_WIFI", timeout=30)

    if resp and resp.get("ok"):
        status_str = "OK"
        msg_str = resp.get("msg", "wireless network scan initialized")
        log(f"ESP32: {status_str}, {msg_str}", C.YELLOW)
    elif resp is None:
        log("SCAN_WIFI command timed out — no response from ESP32 "
            "(try unplugging and re-plugging, then run again)", C.RED, level="err")
    else:
        status_str = "FAILED"
        msg_str = resp.get("msg", "internal radio transceiver scanning failure")
        log(f"ESP32: {status_str}, {msg_str}", C.RED, level="err")

    time.sleep(1)
    proto.stop()
    rx.stop()
    rx.join(timeout=3)

    if not networks:
        log("No networks found.", level="warn")
        return

    # Dedupe by BSSID (some APs beacon on multiple channels during scan)
    seen = {}
    for n in networks:
        bssid = n.get("bssid", "")
        if bssid not in seen or n.get("rssi", -999) > seen[bssid].get("rssi", -999):
            seen[bssid] = n
    networks = list(seen.values())
    networks.sort(key=lambda n: n.get("rssi", -999), reverse=True)

    open_count = sum(1 for n in networks if "OPEN" in (n.get("security") or "").upper())
    print("",flush=True)
    for n in networks:
        ssid = n.get("ssid") or "(hidden)"
        ssid = ssid if len(ssid) <= 31 else ssid[:28] + "..."
        rssi = n.get("rssi", 0)
        bssid = n.get("bssid", "")
        channel = n.get("channel", "")
        security = n.get("security", "") or "?"
        bars = _signal_bars(rssi)

        sig_color = C.GREEN if rssi > -65 else C.YELLOW if rssi > -80 else C.RED
        sec_color = C.RED if "OPEN" in security.upper() else C.RESET

        line = (f"{ssid:<32} {bssid:<18} {channel:>3}  {rssi:>4}  "
                f"{bars:<6} {sec_color}{security}{C.RESET}")
        print(f"\033[0;34m  [*] {sig_color}{line}{C.RESET}", file=sys.stderr, flush=True)

    print(f"\n\033[1;32m[+]\033[0m {len(networks)} networks found"
          + (f", {C.RED}{open_count} open{C.RESET}" if open_count else "")
          + ".\n", file=sys.stderr, flush=True)
