"""USB device enumeration, selection, and Termux bootstrap helpers."""

import json
import os
import shlex
import subprocess
import sys

from . import config
from .ui import C, log
from .espbridge_compat import (
    auto_detect_device,
    describe_device,
    detect_backend,
    launch_with_fd,
    list_usb_devices,
    request_permission,
    wrap_direct,
)


def _enumerate_usb_paths() -> list:
    """Return list of USB device path strings (Termux) or synthetic labels (root)."""
    paths = []
    try:
        paths = list(list_usb_devices() or [])
    except Exception:
        paths = []
    if paths:
        return paths
    # Fallback: termux-usb -l
    try:
        out = subprocess.check_output(
            ["termux-usb", "-l"], stderr=subprocess.STDOUT, timeout=8, text=True
        )
        data = json.loads(out.strip() or "[]")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict):
                    p = item.get("device") or item.get("path")
                    if p:
                        paths.append(p)
    except Exception:
        pass
    return paths


def resolve_device(spec: str | None = None) -> str:
    """
    Resolve a device specifier to a USB path.
      None / empty  -> auto_detect_device() (first usable)
      digit         -> index into enumerated list (0-based)
      path / substr -> exact or unique substring match
    """
    paths = _enumerate_usb_paths()

    if not spec:
        if len(paths) == 1:
            return paths[0]
        if len(paths) > 1:
            # Prefer auto_detect when multiple; it may apply VID:PID heuristics
            try:
                return auto_detect_device()
            except Exception:
                lines = "\n".join(f"  [{i}] {p}" for i, p in enumerate(paths))
                raise RuntimeError(
                    f"Multiple USB devices found — pick one with -d/--device:\n{lines}"
                )
        return auto_detect_device()

    spec = str(spec).strip()

    # Numeric index
    if spec.isdigit():
        idx = int(spec)
        if not paths:
            raise RuntimeError("No USB devices found to index.")
        if idx < 0 or idx >= len(paths):
            lines = "\n".join(f"  [{i}] {p}" for i, p in enumerate(paths))
            raise RuntimeError(
                f"Device index {idx} out of range.\n{lines}"
            )
        return paths[idx]

    # Exact path
    if paths and spec in paths:
        return spec
    if spec.startswith("/dev/"):
        return spec  # trust explicit path even if list is stale

    # Unique substring match
    matches = [p for p in paths if spec in p]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        lines = "\n".join(f"  [{i}] {p}" for i, p in enumerate(matches))
        raise RuntimeError(f"Ambiguous device spec {spec!r}:\n{lines}")

    if paths:
        lines = "\n".join(f"  [{i}] {p}" for i, p in enumerate(paths))
        raise RuntimeError(f"No device matching {spec!r}.\n{lines}")
    raise RuntimeError(f"No USB devices found (spec={spec!r}).")


def do_list_devices():
    """Print enumerated USB devices with indices for -d/--device."""
    paths = _enumerate_usb_paths()
    if not paths:
        # Root: try describe via wrap_direct
        try:
            backend = detect_backend()
        except Exception:
            backend = "?"
        if backend == "root":
            try:
                dev = wrap_direct()
                print(f"[0] {describe_device(dev)}  (direct libusb)")
                return
            except Exception as e:
                log(f"No USB device found: {e}", C.RED, level="err")
                return
        log("No USB devices found. Plug in the ESP32 via OTG and retry.", level="warn")
        return
    print(f"{C.CYAN}[*]{C.RESET} {len(paths)} device(s):")
    for i, p in enumerate(paths):
        mark = f"{C.GREEN}[{i}]{C.RESET}"
        print(f"  {mark} {p}")
    print(f"\n{C.GRAY}Use:  ./nrsuite -d 0 scan   or   ./nrsuite -d {paths[0]} scan{C.RESET}")


def _launch_with_fd_tty(device_path: str, cmd: str) -> None:
    """Launch termux-api Usb open callback with the terminal still attached.

    This deliberately mirrors espbridge's proven launch_with_fd() callback
    protocol, but skips the log-file/stdout redirection so an interactive
    prompt can be flushed immediately.
    """
    env = os.environ.copy()
    env["TERMUX_CALLBACK"] = cmd
    env["TERMUX_EXPORT_FD"] = "true"
    argv = [
        config.TERMUX_API, "Usb", "-a", "open",
        "--ez", "request", "true", "--es", "device", device_path,
    ]

    pid = os.fork()
    if pid == 0:
        try:
            os.execve(config.TERMUX_API, argv, env)
        except Exception:
            os._exit(1)

    # The connected child owns the terminal while it runs. If the parent also
    # handled SIGINT here, Ctrl+C inside the child would make the parent return
    # early and fight the child for the prompt.
    import signal
    old_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        _, status = os.waitpid(pid, 0)
    finally:
        signal.signal(signal.SIGINT, old_sigint)

    exit_code = os.waitstatus_to_exitcode(status)
    if exit_code != 0:
        print(
            f"\033[0;91m[!]\033[0m termux-api interactive launch exited {exit_code}.",
            file=sys.stderr,
        )
        sys.exit(1)


def bootstrap(subcommand: str, extra_args: list[str], device_spec: str | None = None,
              interactive: bool = False) -> None:
    try:
        device_path = resolve_device(device_spec)
        print(f"\033[0;92m[+]\033[0m Found device: \033[0;92m{device_path}\033[0m", file=sys.stderr)
    except RuntimeError as e:
        print(f"\033[0;91m[!]\033[0m ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("\033[0;96m[*]\033[0;93m Requesting USB permission...\n\033[0m")

    granted = request_permission(device_path)
    if not granted:
        print("\033[0;91m[!]\033[0m Permission denied or timed out.", file=sys.stderr)
        sys.exit(1)

    script = config.ENTRYPOINT
    cmd = f"env NRSUITE_CHILD=1 python {script} {subcommand} " + ' '.join(shlex.quote(arg) for arg in extra_args)

    if interactive:
        # Keep the terminal directly attached for interactive prompts. The
        # normal launch_with_fd() path redirects stdout/stderr to a log file
        # and only flushes complete lines, which hides a no-newline prompt.
        _launch_with_fd_tty(device_path, cmd)
        return

    def _tail(line: str) -> None:
        print(line, end="", file=sys.stderr, flush=True)

    child_pid, child_done, tail_thread = launch_with_fd(
        cmd=cmd, device_path=device_path, log_file=config.LOG_FILE, tail_fn=_tail
    )

    try:
        _, status = os.waitpid(child_pid, 0)
        exit_code = os.waitstatus_to_exitcode(status)
    except KeyboardInterrupt:
        import signal
        os.kill(child_pid, signal.SIGTERM)
        _, status = os.waitpid(child_pid, 0)
        exit_code = os.waitstatus_to_exitcode(status)

    child_done.set()
    tail_thread.join(timeout=2)

    print(f"\n\033[0;92m[+] \033[0mProcess finished (exit {exit_code}).", file=sys.stderr)
