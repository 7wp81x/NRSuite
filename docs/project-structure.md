# Project Structure

```text
nrsuite/
├── nrsuite                       # Thin executable launcher (chmod +x, run as ./nrsuite)
├── nrsuite_lib/
│   ├── cli.py                    # argparse construction + backend dispatch
│   ├── config.py                 # paths, protocol constants, storage init
│   ├── ui.py                     # colors, logging, banner, signal bars
│   ├── espbridge_compat.py       # external espbridge import/dependency shim
│   ├── devices.py                # USB enumeration/selection + Termux bootstrap
│   ├── bridge.py                 # bridge setup/drain/ready helpers
│   ├── eapol.py                  # pure EAPOL / 4-way-handshake parsing
│   ├── duckyscript.py            # pure DuckyScript helpers
│   └── commands/
│       ├── scan.py
│       ├── sniff.py
│       ├── deauth.py
│       ├── beacon.py
│       ├── portal.py
│       ├── ble.py
│       ├── storage.py
│       └── badusb.py
├── tests/                        # host-side unittest coverage
│   ├── test_cli.py
│   ├── test_commands_import.py
│   ├── test_devices.py
│   ├── test_duckyscript.py
│   ├── test_eapol.py
│   └── test_ui.py
├── firmware/
│   ├── platformio.ini            # multi-board build config (C3/S3/S2/devkit)
│   ├── src/
│   │   ├── main.cpp              # Arduino entry point, CMD dispatcher
│   │   ├── sniffer.cpp / .h      # Promiscuous capture, radiotap builder
│   │   ├── beacon.cpp / .h       # Beacon spam (custom/hidden SSIDs, up to 32)
│   │   ├── ble_hid.cpp / .h      # BLE HID keyboard (BadBLE / realtime), C3/S3/devkit only
│   │   ├── mass_storage.cpp / .h # USB mass storage + file ops, MSC mode requires S2/S3
│   │   ├── UsbHID.cpp / .h       # Native USB HID keyboard (BadUSB), S2/S3 only
│   │   └── override_sanity.cpp   # Bypass IDF raw frame sanity check
│   └── lib/
│       └── BridgeProtocol/       # Framed binary protocol (ESP32 side)
├── pcap_writer.py                # pcap writer, buffered + stream modes
├── data/                         # Logs and captures (auto-created, gitignored)
├── .github/workflows/ci.yml      # Python + firmware + host-native CI
└── README.md
```

The public entry point remains `./nrsuite`. It is intentionally thin; the CLI
logic, device/backend handling, command implementations, and pure parsing
helpers live under `nrsuite_lib/` so they can be imported and tested without
touching hardware.

USB/bridge-protocol plumbing (`protocol.py`, `receiver.py`, `sender.py`,
`usb_device.py`) still lives in the standalone pip package
[`espbridge`](https://github.com/7wp81x/ESP-Bridge). NRSuite does not modify or
vendor that package; `nrsuite_lib/espbridge_compat.py` is the single import
point and preserves the existing auto-install behavior when `espbridge` is
missing.

Run the host-side test suite with:

```bash
python -m unittest discover -s tests -v
```

---

[← Back to README](../README.md)
