"""Single import point for the external espbridge package.

The package is deliberately not vendored or modified here. If it is missing,
the same lazy runtime install behavior as the original nrsuite script is kept.
"""

import subprocess
import sys

try:
    from espbridge import (
        detect_backend, auto_detect_device, request_permission, launch_with_fd,
        describe_device, get_cdc_endpoints, claim_device, reset_endpoint_toggles,
        init_uart_bridge, is_native_cdc, open_native_cdc_port,
        find_cdc_control_interface, wrap_direct, wrap_fd, list_usb_devices,
        ReceiverThread, Sender, Protocol,
    )
except ImportError:
    print("\033[0;93m[*]\033[0m espbridge not found, installing...", file=sys.stderr)
    subprocess.check_call([sys.executable, "-m", "pip", "install", "espbridge"])
    from espbridge import (
        detect_backend, auto_detect_device, request_permission, launch_with_fd,
        describe_device, get_cdc_endpoints, claim_device, reset_endpoint_toggles,
        init_uart_bridge, is_native_cdc, open_native_cdc_port,
        find_cdc_control_interface, wrap_direct, wrap_fd, list_usb_devices,
        ReceiverThread, Sender, Protocol,
    )

__all__ = [
    "detect_backend", "auto_detect_device", "request_permission", "launch_with_fd",
    "describe_device", "get_cdc_endpoints", "claim_device", "reset_endpoint_toggles",
    "init_uart_bridge", "is_native_cdc", "open_native_cdc_port",
    "find_cdc_control_interface", "wrap_direct", "wrap_fd", "list_usb_devices",
    "ReceiverThread", "Sender", "Protocol",
]
