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

def do_sniff(fd: int = None, args=None):
    from pcap_writer import PcapWriter
    log("Starting packet sniffer...", C.CYAN)
    _, rx, tx, proto = _setup_bridge(fd)

    out_path = args.output or os.path.join(DATA_DIR, f"capture_{int(time.time())}.pcap")

    if out_path != "-":
        log(f"Initializing PCAP storage target -> \033[1;92m{out_path}\033[0m", C.BLUE)
    else:
        log("Streaming live binary PCAP payload straight to stdout...", C.BLUE)

    writer = PcapWriter(out_path, stream_mode=args.stream)
    packet_count = 0

    HS_state = {"M1": False, "M2": False, "M3": False, "M4": False}
    stop_sniff_event = threading.Event()

    

    def on_pcap(payload, _):
        nonlocal packet_count
        writer.write_packet(payload)
        packet_count += 1

        parse_eapol_message(payload, HS_state, log)

        if args.eapol_only:
            try:
                rt_len = struct.unpack("<H", payload[2:4])[0]
                mac_base = rt_len
                fc0 = payload[mac_base]
                ftype = (fc0 >> 2) & 0x03
                subtype = (fc0 >> 4) & 0x0F

                if ftype == 0 and subtype == 8:
                    log("Beacon captured", C.CYAN)
            except:
                pass

        if not args.eapol_only and (packet_count % 40 == 0 or packet_count <= 10):
            log(f"Captured {packet_count} packets...", C.MAGENTA)

        if args.eapol_only and args.bssid:
            if all(HS_state.values()):
                log("[+] Valid 4-Way Handshake captured!", C.GREEN)
                stop_sniff_event.set()

    proto.on_pcap = on_pcap
    proto.start()
    _drain_stale(rx)
    _wait_for_ready(proto)

    if getattr(args, 'deauth', False) and args.bssid:
        log("Sending deauth burst before capture...", C.YELLOW)
        deauth_args = {
            "bssid": args.bssid,
            "client": getattr(args, 'client', "FF:FF:FF:FF:FF:FF"),
            "channel": args.channel,
            "count": getattr(args, 'count', 120),
            "deauth_interval_ms": 80,
            "reason": 7
        }
        proto.send_cmd("DEAUTH", deauth_args, timeout=20)

    # Start sniffing
    sniff_args = {"mode": "hop" if args.hop else "fixed"}
    if args.hop:
        sniff_args["interval_ms"] = args.interval
    else:
        sniff_args["channel"] = args.channel

    if args.eapol_only:
        sniff_args["eapol_only"] = True
    if args.bssid:
        sniff_args["bssid"] = args.bssid

    resp = proto.send_cmd("START_SNIFF", sniff_args, timeout=12)
    log(f"Sniffing started on {'hopping' if args.hop else f'channel {args.channel}'}...", C.BOLD)

    try:
        while not stop_sniff_event.is_set():
            stop_sniff_event.wait(timeout=0.3)
    except KeyboardInterrupt:
        log("\nStopping capture...", C.YELLOW)

    proto.send_cmd("STOP_SNIFF", timeout=6)
    writer.close()
    proto.stop()
    rx.stop()
    rx.join(timeout=3)

    log(f"Capture saved: \033[1;92m{out_path}\033[0m ({packet_count} packets)", C.GREEN)
