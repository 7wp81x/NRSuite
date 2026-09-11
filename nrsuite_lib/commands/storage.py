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

def do_masstorage_start(fd: int = None, args=None):
    log("Entering USB Mass Storage mode...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)
    if not ensure_usb_otg(proto, "USB mass storage mode", log_func=log):
        _stop_bridge(proto, rx, timeout=3)
        return

    resp = proto.send_cmd("START_MSC", timeout=5.0)

    if resp is None:
        # Expected: RESP may or may not make it back before USB re-enumerates.
        log("No response (expected — USB is about to switch to mass storage "
            "and drop this connection).", C.YELLOW)
    elif not resp.get("ok"):
        log(f"ESP32 refused: {resp.get('msg')}", C.RED, level="err")
        proto.stop(); rx.stop(); rx.join(timeout=3)
        return

    proto.stop()
    rx.stop()
    rx.join(timeout=3)

    log("Device is now a USB mass storage drive on this machine.", C.GREEN, level="ok")
    log("Press ESC on the device to exit mass storage mode — there is no "
        "USB command that can do this, the CDC link is gone until it exits.",
        C.YELLOW)
    log("Ctrl+C here only exits this script; it does not stop mass storage "
        "mode on the device.", C.YELLOW)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("Exiting script (device stays in mass storage mode until you "
            "press ESC on it).", C.YELLOW)


def do_masstorage_files(fd: int = None, args=None):
    log("Listing files on device storage...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)

    resp = proto.send_cmd("MSC_LIST", timeout=5.0)

    if not resp or not resp.get("ok"):
        log(f"Failed to list files: {resp.get('msg') if resp else 'timed out'}",
            C.RED, level="err")
    else:
        files = resp.get("files", [])
        if not files:
            log("  (no files)", C.YELLOW)
        else:
            for f in files:
                log(f"  {f.get('name', '?'):<30} {f.get('size', 0)} bytes", C.CYAN)
        total = resp.get("total", 0)
        used  = resp.get("used", 0)
        free  = resp.get("free", 0)
        log(f"  [usage] {used}/{total} bytes used, {free} bytes free", C.YELLOW)

    proto.stop()
    rx.stop()
    rx.join(timeout=3)


def do_masstorage_delete(fd: int = None, args=None):
    path = args.file
    log(f"Deleting {path}...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)

    list_resp = proto.send_cmd("MSC_LIST", timeout=5.0)
    exists = False
    if list_resp and list_resp.get("ok"):
        exists = any(f.get("name") == path or f.get("name") == f"/{path}"
                     for f in list_resp.get("files", []))

    if not exists:
        log(f"File not found: {path}", C.YELLOW)
        proto.stop(); rx.stop(); rx.join(timeout=3)
        return

    resp = proto.send_cmd("MSC_DELETE", {"path": path}, timeout=5.0)
    if not resp or not resp.get("ok"):
        log(f"Delete failed: {resp.get('msg') if resp else 'timed out'}",
            C.RED, level="err")
    else:
        log(f"Deleted {path}", C.GREEN, level="ok")

    proto.stop()
    rx.stop()
    rx.join(timeout=3)


def do_masstorage_free(fd: int = None, args=None):
    log("Checking storage usage...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)

    resp = proto.send_cmd("MSC_SPACE", timeout=5.0)
    if not resp or not resp.get("ok"):
        log(f"Failed to get storage info: {resp.get('msg') if resp else 'timed out'}",
            C.RED, level="err")
    else:
        total = resp.get("total", 0)
        used  = resp.get("used", 0)
        free  = resp.get("free", 0)
        log(f"Total: {total} bytes", C.CYAN)
        log(f"Used:  {used} bytes", C.CYAN)
        log(f"Free:  {free} bytes", C.CYAN)

    proto.stop()
    rx.stop()
    rx.join(timeout=3)


def do_masstorage(fd: int = None, args=None):
    action = getattr(args, "msc_action", None)
    if action == "start":
        do_masstorage_start(fd, args)
    elif action == "files":
        do_masstorage_files(fd, args)
    elif action == "delete":
        do_masstorage_delete(fd, args)
    elif action == "free":
        do_masstorage_free(fd, args)
    else:
        log("No mass storage action given. Use: start | files | delete <file> | free", C.YELLOW)
