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
from ..bridge import _drain_stale, _setup_bridge, _stop_bridge, _wait_for_ready
from ..duckyscript import looks_like_script_line, split_pipe_commands as _split_pipe_commands
from ..eapol import parse_eapol_message
from ..capabilities import ensure_usb_otg

def do_badusb(fd: int = None, args=None):
    _, rx, tx, proto = _setup_bridge(fd)
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)
    if not ensure_usb_otg(proto, "BadUSB", log_func=log):
        _stop_bridge(proto, rx, timeout=3)
        return
    
    local_path = args.payload
    if not os.path.exists(args.payload):
        log(f"Payload file not found: {args.payload}", C.RED, level="err")
        return

    with open(local_path, "rb") as f:
        data = f.read()

    remote_filename = "ducky.txt"
    ext = os.path.splitext(remote_filename)[1].lower()
    if ext not in (".txt", ".conf"):
        log(f"Rejected: only .txt/.conf allowed, got '{ext}'", C.RED, level="err")
        return

    log(f"Uploading ducky script as \033[1;92m{remote_filename}\033[0m...", C.YELLOW)
    total = len(data)
    raw_chunk_size = (MAX_B64_LEN * 3) // 4
    chunks = list(range(0, total, raw_chunk_size)) or [0]  # handle empty file

    for idx, i in enumerate(chunks):
        chunk   = data[i:i + raw_chunk_size]
        is_last = (idx == len(chunks) - 1)
        b64data = base64.b64encode(chunk).decode("ascii")

        resp = None
        for attempt in range(3):
            resp = proto.send_cmd("SET_FILE_CHUNK", {
                "filename": remote_filename,
                "data": b64data,
                "last": is_last,
            }, timeout=5.0)
            if resp and resp.get("ok"):
                break
            log(f"Chunk {idx} attempt {attempt+1} failed: {resp}", C.YELLOW, level="warn")
            time.sleep(0.3)
        else:
            log(f"Chunk {idx} failed after 3 attempts, aborting", C.RED, level="err")
            return

        percent = int(((i + len(chunk)) / total) * 100) if total else 100
        log(f"Uploading {percent}% chunk {idx+1}/{len(chunks)}...", C.CYAN)

    log(f"'{remote_filename}' written to device storage.", C.GREEN, level="ok")
    time.sleep(0.5)
    log(f"Arming {remote_filename} script..", C.GREEN, level="ok")
    time.sleep(2)
    resp = proto.send_cmd("START_BADUSB", {"filename": remote_filename, "msc": args.masstorage}, timeout=10)

    if resp and resp.get("ok"):
        log(f"Script has been armed, you can now unplug the device.", C.GREEN, level="info")
        log(f"\033[1;93mCAUTION\033[m: Once you re-plug it, it will execute the ducky script once.", C.GREEN, level="warn")

    else:
        log(f"Failed to arm script...", C.RED, level="ok")
    
    proto.stop()
    rx.stop()
    rx.join(timeout=3)
