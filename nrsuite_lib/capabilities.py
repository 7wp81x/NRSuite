"""ESP32 chip capability checks.

The firmware reports its build chip in the STATUS response. The CLI uses that
to block features the connected board cannot physically support.
"""

from .ui import C, log


BLUETOOTH_CHIPS = {
    "ESP32-C3",
    "ESP32-S3",
    "ESP32",
}

USB_OTG_CHIPS = {
    "ESP32-S3",
    "ESP32-S2",
}

KNOWN_CHIPS = BLUETOOTH_CHIPS | USB_OTG_CHIPS


def _warn(message: str, log_func=None) -> None:
    (log_func or log)(message, C.YELLOW, level="warn")


def get_chip(proto, log_func=None):
    """Return the remote chip name, caching it on the Protocol object."""
    cached = getattr(proto, "_nrsuite_chip", None)
    if cached is not None:
        return cached

    resp = proto.send_cmd("STATUS", timeout=5)
    chip = resp.get("chip") if resp else None
    try:
        setattr(proto, "_nrsuite_chip", chip)
    except Exception:
        pass
    return chip


def _check_supported(proto, supported_chips, feature_label, reason, log_func=None) -> bool:
    chip = get_chip(proto, log_func=log_func)
    if not chip:
        _warn(
            f"Could not determine ESP32 chip; cannot verify {feature_label} support — proceeding anyway.",
            log_func=log_func,
        )
        return True

    chip_upper = chip.upper()
    if chip_upper not in KNOWN_CHIPS:
        _warn(
            f"Unrecognized ESP32 chip {chip}; cannot verify {feature_label} support — proceeding anyway.",
            log_func=log_func,
        )
        return True

    if chip_upper not in supported_chips:
        _warn(
            f"{feature_label} is not supported on {chip}: {reason}.",
            log_func=log_func,
        )
        return False

    return True


def ensure_bluetooth(proto, log_func=None) -> bool:
    """Return False if the connected chip has no Bluetooth radio."""
    return _check_supported(
        proto,
        BLUETOOTH_CHIPS,
        "BLE HID",
        "this chip has no Bluetooth radio",
        log_func=log_func,
    )


def ensure_usb_otg(proto, feature_label: str = "USB-OTG features", log_func=None) -> bool:
    """Return False if the connected chip has no native USB-OTG peripheral."""
    return _check_supported(
        proto,
        USB_OTG_CHIPS,
        feature_label,
        "this chip has no native USB-OTG peripheral",
        log_func=log_func,
    )
