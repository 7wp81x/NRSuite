"""Long-lived NRSuite USB/protocol session for interpreter mode.

The session owns one bridge and one Protocol instance. Existing one-shot
command handlers can reuse it through a small proxy layer: when a session is
active, ``bridge._setup_bridge()`` returns proxies whose ``start()``/``stop()``
calls are no-ops, so a command cannot tear down the shared session.
"""

from .bridge import (
    _drain_stale,
    _setup_bridge,
    _stop_bridge,
    _wait_for_ready,
    clear_active_session,
    set_active_session,
)
from .capabilities import get_chip
from .ui import C, log


class _RxProxy:
    """Delegate reads to the shared receiver but make stop()/join() no-ops."""

    def __init__(self, rx):
        object.__setattr__(self, "_rx", rx)

    def stop(self):
        return None

    def join(self, timeout=None):
        return None

    def __getattr__(self, name):
        return getattr(self._rx, name)


class _ProtoProxy:
    """Delegate protocol work to the shared Protocol without restarting it."""

    def __init__(self, proto):
        object.__setattr__(self, "_proto", proto)

    def start(self):
        return None

    def stop(self):
        return None

    def __getattr__(self, name):
        return getattr(self._proto, name)

    def __setattr__(self, name, value):
        if name == "_proto":
            object.__setattr__(self, name, value)
        else:
            setattr(self._proto, name, value)


class NRSuiteSession:
    """One open USB bridge + Protocol session."""

    def __init__(self, fd=None):
        self.fd = fd
        self.device = None
        self.rx = None
        self.tx = None
        self.proto = None
        self.chip = None
        self.alive = False

    def open(self) -> None:
        if self.alive:
            return

        self.device, self.rx, self.tx, self.proto = _setup_bridge(self.fd)
        self.proto.start()
        _drain_stale(self.rx)
        _wait_for_ready(self.proto)
        self.chip = get_chip(self.proto, log_func=log)
        self.alive = True

    def close(self) -> None:
        if not self.alive:
            return
        try:
            _stop_bridge(self.proto, self.rx, timeout=3)
        finally:
            self.device = None
            self.rx = None
            self.tx = None
            self.proto = None
            self.chip = None
            self.alive = False

    def proxy_bundle(self):
        return (self.device, _RxProxy(self.rx), self.tx, _ProtoProxy(self.proto))

    def begin_command(self) -> None:
        """Clear parser state/callbacks before a foreground command."""
        if self.proto is None:
            return
        self.proto.on_event = None
        self.proto.on_pcap = None
        self.proto.reset()

    def end_command(self) -> None:
        """Clear parser state/callbacks after a foreground command."""
        if self.proto is None:
            return
        self.proto.on_event = None
        self.proto.on_pcap = None
        self.proto.reset()

    def activate(self) -> None:
        set_active_session(self)

    def deactivate(self) -> None:
        clear_active_session()
        self.end_command()

    def send_cmd(self, cmd: str, args=None, timeout: float = 5.0):
        return self.proto.send_cmd(cmd, args or {}, timeout=timeout)
