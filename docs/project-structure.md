# Project Structure

```
nrsuite/
├── firmware/
│   ├── platformio.ini            # multi-board build config (C3/S3/S2/devkit)
│   ├── src/
│   │   ├── main.cpp              # Arduino entry point, CMD dispatcher
│   │   ├── sniffer.cpp / .h      # Promiscuous capture, radiotap builder
│   │   ├── ble_hid.cpp / .h      # BLE HID keyboard (BadBLE / realtime), C3/S3/devkit only
│   │   ├── mass_storage.cpp / .h # USB mass storage + file ops, MSC mode requires S2/S3
│   │   ├── UsbHID.cpp / .h       # Native USB HID keyboard (BadUSB), S2/S3 only
│   │   └── override_sanity.cpp   # Bypass IDF raw frame sanity check
│   └── lib/
│       └── BridgeProtocol/       # Framed binary protocol (ESP32 side)
├── nrsuite                       # Main CLI (chmod +x, run as ./nrsuite)
├── pcap_writer.py                # pcap writer, buffered + stream modes
├── data/                         # Logs and captures (auto-created, gitignored)
└── README.md
```

USB/bridge-protocol plumbing (`protocol.py`, `receiver.py`, `sender.py`, `usb_device.py`) has moved out of this repo into a standalone pip package, [`espbridge`](https://github.com/7wp81x/ESP-Bridge) — `nrsuite` imports it directly and auto-installs it on first run if missing:

```python
from espbridge import (
    detect_backend, auto_detect_device, request_permission, launch_with_fd,
    describe_device, get_cdc_endpoints, claim_device, reset_endpoint_toggles,
    init_uart_bridge, is_native_cdc, open_native_cdc_port,
    find_cdc_control_interface, wrap_direct, wrap_fd,
    ReceiverThread, Sender, Protocol,
)
```

If you're vendoring NRSuite offline or on a device without pip network access, install it manually first:

```bash
pip install espbridge
```

---

[← Back to README](../README.md)
