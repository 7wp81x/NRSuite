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

def do_portal(fd: int = None, args=None):
    _, rx, tx, proto = _setup_bridge(fd)
    _drain_stale(rx)
    _wait_for_ready(proto)

    def on_event(ev):
        if ev and ev.get("type") == "captive_data":
            uip = ev.get('ip', 'N/A')
            log(f"\033[1;92m{uip}\033[0m: {str(ev)}")
        if ev.get("type") == "client_associated":
            client = ev.get("client")
            log(f"{client}: connected (RSSI: {ev.get('rssi')})", C.GREEN, level="ok")
        if ev_type == "portal_viewed":
            ip = ev.get("client_ip")
            log(f"{ip} Client connected...", C.GREEN, level="ok")
        if ev and ev.get("type") == "deauth_stats":
            log(f"Deauth stats: {ev.get('sent_frames')} frames sent", C.YELLOW)

    proto.on_event = on_event
    proto.start()

    try:
        
        if args.action == "start":
            portal_status = proto.send_cmd("PORTAL_STATUS", timeout=5)
            if portal_status and portal_status.get("ok"):
                if portal_status.get('running'):
                    log("Portal is running, stopping...", C.YELLOW)
                    proto.send_cmd("STOP_PORTAL", {}, timeout=8)

            if args.channel == None:
                args.channel = 3
            log(f"Starting portal with SSID: \033[1;92m{args.ssid}\033[0m, Channel: \033[1;92m{args.channel}\033[0m", C.GREEN)
            
            portal_args = {
                "ssid": args.ssid,
                "channel": args.channel,
                "bssid": args.bssid or ""
            }
            start_resp = proto.send_cmd("START_PORTAL", portal_args, timeout=15)

            if not start_resp or not start_resp.get("ok"):
                log("Failed to start portal.", C.RED, level="err")
                return


            if args.file and os.path.exists(args.file):
                with open(args.file, "rb") as f:
                    html_data = f.read()

                reset_resp = proto.send_cmd("RESET_HTML", {"size": len(html_data)}, timeout=10)

                if not reset_resp or not reset_resp.get("ok"):
                    log("ESP32 rejected upload (size/heap check failed)", C.RED, level="err")
                    return

                log("Uploading HTML file...", C.YELLOW)
                time.sleep(1)
                uploaded = 0
                total    = len(html_data)
                raw_chunk_size = (MAX_B64_LEN * 3) // 4
                chunks = list(range(0, total, raw_chunk_size))

                for idx, i in enumerate(chunks):
                    chunk   = html_data[i:i + raw_chunk_size]
                    is_last = (idx == len(chunks) - 1)
                    b64data = base64.b64encode(chunk).decode("ascii")
                    resp = None
                    for attempt in range(3):
                        resp = proto.send_cmd("SET_HTML_CHUNK",
                                            {"data": b64data, "last": is_last},
                                            timeout=5.0)
                        if resp and resp.get("ok"):
                            break
                        log(f"Chunk {idx} attempt {attempt+1} failed: {resp}", C.YELLOW, level="warn")
                        time.sleep(0.3)
                    else:
                        log(f"Chunk {idx} failed after 3 attempts, aborting", C.RED, level="err")
                        return

                    uploaded += len(chunk)
                    percent = int((uploaded / total) * 100)
                    log(f"Uploading {percent}% ({uploaded}/{total} bytes)  chunk {idx+1}/{len(chunks)}...", C.CYAN)
                    time.sleep(0.05)

                print("")

                status = proto.send_cmd("PORTAL_STATUS", {}, timeout=5.0)
                if not status or not status.get("html_complete"):
                    log("Device did not report html_complete after upload", C.RED, level="err")
                    return
                device_size = status.get("html_size", 0)
                if device_size < total:
                    log(f"Size mismatch: sent {total} bytes, device reports {device_size}", C.RED, level="err")
                    return

                log(f"HTML uploaded successfully ({total} bytes, device reports {device_size})", C.GREEN)
            log("Portal is ready, Press Ctrl+C to stop it.", C.CYAN)
            log("="*40, C.GREEN)
            print()
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                log("\nStopping portal via Ctrl+C...", C.YELLOW)
                proto.send_cmd("STOP_PORTAL", {}, timeout=8)
                log("Portal stopped.", C.GREEN)


        elif args.action == "stop":
            resp = proto.send_cmd("STOP_PORTAL", {}, timeout=8)
            if resp and resp.get("ok"):
                log("Portal stopped.", C.GREEN)
            else:
                log("Failed to stop portal.", C.RED, level="err")

        elif args.action == "status":
            resp = proto.send_cmd("PORTAL_STATUS", timeout=5)
            if resp and resp.get("ok"):
                log(f"Portal running: {resp.get('running')}", C.YELLOW)
                log(f"HTML size: {resp.get('html_size')} bytes", C.YELLOW)
                log(f"HTML complete: {resp.get('html_complete')}", C.YELLOW)
            else:
                log("Failed to get portal status", C.RED, level="err")

    finally:
        proto.stop()
        rx.stop()
        rx.join(timeout=2)
