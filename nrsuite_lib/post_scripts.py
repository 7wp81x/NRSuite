"""Built-in post scripts for the interactive interpreter."""

import os
import struct


def count_pcap_packets(path: str) -> int:
    """Count packet records in a classic pcap file."""
    count = 0
    with open(path, "rb") as f:
        header = f.read(24)
        if len(header) < 24:
            return 0
        while True:
            rec = f.read(16)
            if len(rec) < 16:
                break
            _ts_sec, _ts_usec, incl_len, _orig_len = struct.unpack("<IIII", rec)
            f.seek(incl_len, os.SEEK_CUR)
            count += 1
    return count


def post_count_packet(context) -> dict:
    files = context.get("files") or []
    pcap = next((f for f in files if str(f).endswith(".pcap")), None)
    if not pcap or not os.path.exists(pcap):
        return {"ok": False, "error": "no .pcap file available"}
    return {"ok": True, "file": pcap, "packets": count_pcap_packets(pcap)}


def register_builtin(registry) -> None:
    registry.register_post(
        "post/wifi/count_packet",
        post_count_packet,
        "Count packets in the most recent capture file",
    )
