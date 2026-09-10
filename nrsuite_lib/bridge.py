"""ESP bridge setup and lifecycle helpers."""

from .ui import C, log
from .espbridge_compat import (
    claim_device,
    find_cdc_control_interface,
    get_cdc_endpoints,
    init_uart_bridge,
    is_native_cdc,
    open_native_cdc_port,
    reset_endpoint_toggles,
    Protocol,
    ReceiverThread,
    Sender,
    wrap_direct,
    wrap_fd,
)


def _setup_bridge(fd=None, reset=False):
    if fd is None:
        log("Backend: \033[0;92mroot (direct libusb)\033[0m", C.GREEN)
        device = wrap_direct()
    else:
        device = wrap_fd(fd)

    log("Starting bridge, please wait...", C.GREEN, level="ok")

    ep_in, ep_out, intf = get_cdc_endpoints(device)
    claim_device(device, intf, fd_wrapped=(fd is not None))
    reset_endpoint_toggles(device, ep_in, ep_out)

    init_uart_bridge(device, reset=reset)
    if is_native_cdc(device):
        ctrl_intf = find_cdc_control_interface(device, intf)
        if ctrl_intf != intf:
            claim_device(device, ctrl_intf, fd_wrapped=(fd is not None))
        open_native_cdc_port(device, control_interface=ctrl_intf)
        log(f"Native USB-CDC port opened (DTR asserted, ctrl intf {ctrl_intf}).", C.GREEN, level="ok")

    rx = ReceiverThread(device, ep_in, log_func=log)
    rx.start()
    rx.drain_stale(duration=0.5)

    tx = Sender(device, ep_out, log_func=log)
    proto = Protocol(tx, rx)
    proto.log = lambda x: None
    return device, rx, tx, proto


def _drain_stale(rx):
    for _ in range(12):
        rx.readline(timeout=0.08)


def _wait_for_ready(proto, timeout=2.0):
    """Poll PING until ESP32 responds, instead of waiting for a one-shot boot string."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = proto.send_cmd("PING", timeout=2)
        if resp and resp.get("ok"):
            return True
        time.sleep(0.2)
    return False
