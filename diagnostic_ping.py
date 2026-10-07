#!/usr/bin/env python3
"""
CH340 / ESP32 PING diagnostic for the original Termux NRSuite path.

Run from the NRSuite-Termux repository root:

    python3 diagnostic_ping.py

Optional:

    python3 diagnostic_ping.py --no-reset
    python3 diagnostic_ping.py --scan
    python3 diagnostic_ping.py --timeout 3

This script monkeypatches PyUSB so you can see the exact USB control and
bulk-transfer sequence used by the working Termux/ESP-Bridge implementation.
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback

try:
    import usb.core
except Exception as exc:  # pragma: no cover
    print(f"PyUSB import failed: {exc}", file=sys.stderr)
    raise SystemExit(2)

from nrsuite_lib.bridge import _drain_stale, _setup_bridge, _stop_bridge


def _fmt_hex(value: int) -> str:
    return f"0x{value:04X}"


def install_usb_trace() -> None:
    """Wrap PyUSB Device methods with logging."""
    orig_ctrl = usb.core.Device.ctrl_transfer
    orig_write = usb.core.Device.write
    orig_read = usb.core.Device.read
    orig_clear_halt = usb.core.Device.clear_halt

    def traced_ctrl(self, *args, **kwargs):
        result = orig_ctrl(self, *args, **kwargs)
        bm = args[0] if len(args) > 0 else kwargs.get("bmRequestType")
        req = args[1] if len(args) > 1 else kwargs.get("bRequest")
        val = args[2] if len(args) > 2 else kwargs.get("wValue", 0)
        idx = args[3] if len(args) > 3 else kwargs.get("wIndex", 0)
        data = args[4] if len(args) > 4 else kwargs.get("data_or_wLength")
        try:
            data_len = len(data) if data is not None else 0
        except TypeError:
            data_len = data
        print(
            f"[CTRL] bm=0x{bm:02X} req=0x{req:02X} "
            f"val={_fmt_hex(val)} idx={_fmt_hex(idx)} len={data_len} -> {result}",
            flush=True,
        )
        return result

    def traced_write(self, endpoint, data, *args, **kwargs):
        result = orig_write(self, endpoint, data, *args, **kwargs)
        print(
            f"[BULK OUT] ep=0x{endpoint:02X} len={len(data)} -> {result}",
            flush=True,
        )
        return result

    def traced_read(self, endpoint, size, *args, **kwargs):
        result = orig_read(self, endpoint, size, *args, **kwargs)
        if result:
            print(
                f"[BULK IN] ep=0x{endpoint:02X} requested={size} -> {len(result)}",
                flush=True,
            )
        return result

    def traced_clear_halt(self, endpoint):
        result = orig_clear_halt(self, endpoint)
        print(f"[CLEAR_HALT] ep=0x{endpoint:02X} -> {result}", flush=True)
        return result

    usb.core.Device.ctrl_transfer = traced_ctrl
    usb.core.Device.write = traced_write
    usb.core.Device.read = traced_read
    usb.core.Device.clear_halt = traced_clear_halt


def run_ping(proto, label: str, args: dict | None, timeout: float) -> object:
    print(f"\n--- {label} ---", flush=True)
    try:
        response = proto.send_cmd("PING", args or {}, timeout=timeout)
    except Exception as exc:
        print(f"{label} raised: {exc}", file=sys.stderr, flush=True)
        return None
    print(f"{label}: {response}", flush=True)
    return response


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trace/inspect the working Termux NRSuite CH340 PING path.",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="Call _setup_bridge(reset=False) instead of reset=True.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=3.0,
        help="PING timeout in seconds (default: 3).",
    )
    parser.add_argument(
        "--post-setup-delay",
        type=float,
        default=0.0,
        help="Extra delay after bridge setup before PING.",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Also send SCAN_WIFI after PING tests.",
    )
    args = parser.parse_args()

    install_usb_trace()

    proto = None
    rx = None
    try:
        reset = not args.no_reset
        print(f"[*] _setup_bridge(reset={reset}) ...", flush=True)
        _dev, rx, _tx, proto = _setup_bridge(reset=reset)

        if args.post_setup_delay > 0:
            print(f"[*] extra delay {args.post_setup_delay:.2f}s", flush=True)
            time.sleep(args.post_setup_delay)

        proto.start()
        _drain_stale(rx)

        normal = run_ping(proto, "PING normal", None, args.timeout)
        padded = run_ping(proto, "PING padded", {"pad": "x"}, args.timeout)

        normal_ok = bool(normal and isinstance(normal, dict) and normal.get("ok"))
        padded_ok = bool(padded and isinstance(padded, dict) and padded.get("ok"))

        if args.scan:
            print("\n--- SCAN_WIFI ---", flush=True)
            try:
                scan = proto.send_cmd("SCAN_WIFI", {}, timeout=30)
                print(f"SCAN_WIFI: {scan}", flush=True)
            except Exception as exc:
                print(f"SCAN_WIFI raised: {exc}", file=sys.stderr, flush=True)

        print("\n=== SUMMARY ===", flush=True)
        print(f"normal_ping={'PASS' if normal_ok else 'FAIL'}", flush=True)
        print(f"padded_ping={'PASS' if padded_ok else 'FAIL'}", flush=True)

        return 0 if normal_ok or padded_ok else 1

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr, flush=True)
        return 130
    except Exception:
        traceback.print_exc()
        return 2
    finally:
        try:
            if proto is not None:
                _stop_bridge(proto, rx)
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    raise SystemExit(main())
