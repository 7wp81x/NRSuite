# NRSuite

> Turn a $3–5 ESP32 into a wireless research toolkit for Termux — **no root required.**

NRSuite bypasses Android's locked-down radio APIs by offloading the radio layer to an ESP32 over USB OTG. Today that means full Wi-Fi monitor mode, packet capture, and frame injection on a stock, unrooted Android phone. The firmware and bridge protocol are built to grow — Bluetooth LE, IR, NRF24, and CC1101 modules are on the roadmap — so the same phone-plus-ESP32 setup becomes a general-purpose wireless toolkit, not a single-purpose tool.

<p align="center">
  <img src="docs/images/architecture_hw.jpg" width="700" alt="Architecture diagram">
</p>

<p align="center">
  <img src="docs/images/hardware.jpg" width="600" alt="ESP32-C3-SuperMini connected to Android phone via OTG cable">
</p>

> ⚠️ **Authorized use only.** Only use this tool on networks and devices you own or have explicit written permission to test. Unauthorized interception of network traffic is illegal in most jurisdictions.

---

## Why this exists

Android has never exposed monitor mode, raw packet injection, or low-level radio control to user-space apps — not even with root on most devices. The traditional path required a rooted phone, a custom kernel (e.g. NetHunter), a supported external USB adapter, and a lot of luck matching hardware versions.

NRSuite sidesteps the entire problem:

- The **ESP32** handles everything radio-level — promiscuous capture, channel hopping, raw frame injection
- **Termux** talks to it over USB CDC using `termux-usb` + libusb — no root, no kernel modules, no custom ROM
- The **Python bridge** speaks a compact framed binary protocol with flow control, not serial ASCII
- The **firmware and protocol are modular** — new radio backends register their own CMDs without touching the transport layer

Total hardware cost: under $5. Works on any Android phone with USB-C or micro-USB and an OTG cable.

---

## What works today

Wi-Fi is the first fully implemented module. Everything below is tested and working:

| | |
|---|---|
| **Wi-Fi scan** | Active scan with SSID, BSSID, channel, RSSI, and security type |
| **Packet capture** | Fixed channel or channel-hopping promiscuous capture, saved as `.pcap` with radiotap headers (Wireshark-compatible) |
| **EAPOL capture** | Passive handshake capture, optionally filtered by BSSID |
| **Deauth + capture** | Send deauth frames to trigger a handshake, capture EAPOL simultaneously |
| **Live streaming** | Pipe pcap output to termshark via named FIFO for real-time analysis |
| **Heartbeat** | ESP32 sends uptime and free heap every 5 seconds for health monitoring |

See [Roadmap](#roadmap) for what's planned beyond Wi-Fi — BLE, HID emulation, AP mode, and additional radio hardware.

---

## Hardware

| Component | Status | Notes |
|-----------|:------:|-------|
| **ESP32-C3 SuperMini** | ✅ Tested | Primary target — ~$3, native USB CDC built-in |
| **ESP32-S3** (any board) | ✅ Tested | More RAM/flash, native USB CDC, dual-core |
| ESP32-S2 (any board) | ⚠️ Untested | Single-core, native USB CDC, lower cost |
| USB OTG cable / adapter | — | USB-C OTG or micro-USB OTG depending on your phone |
| Android phone | — | Any version with USB host support — no root required |

All supported boards use **native USB CDC** — no external USB-UART bridge chip (CP2102/CH340) needed. They show up as `303A:xxxx` on Android and communicate directly over USB.

The Wi-Fi module uses the ESP32's built-in 2.4 GHz radio — no external antenna needed. Future modules (NRF24, CC1101, IR) will use external add-on hardware — see [Roadmap](#roadmap).

---

## Quick Start

### 1. Install dependencies (Termux)

```bash
pkg update && pkg install python termux-api libusb
pip install pyusb
```

Also install the **Termux:API** companion app from [F-Droid](https://f-droid.org) — *not* the Play Store version, which is outdated.

### 2. Clone the repo

```bash
git clone https://github.com/7wp81x/NRSuite
cd NRSuite
```

### 3. Flash the firmware

```bash
cd firmware/
pio run -e esp32-c3-supermini --target upload   # or esp32-s3 / esp32-s2
```

Confirm it booted correctly — `pio device monitor --baud 115200` should print `ESP32_READY`. See [Firmware](#firmware) below for pre-built binaries and `esptool.py` instructions.

### 4. Connect and run

Plug the ESP32 into your phone via OTG cable. On first run, Android shows a USB permission dialog — tap **OK**. The permission persists until you unplug.

```bash
chmod +x nrsuite
./nrsuite scan
```

**Or use the automated installer:**
```bash
curl -sSL https://raw.githubusercontent.com/7wp81x/NRSuite/main/install.sh | bash
```

---

## Usage

All commands follow the same pattern — the script detects the USB device, requests permission via `termux-usb`, and re-invokes itself with the granted file descriptor. Wi-Fi is the only module implemented so far; commands below are all `nrsuite <module-style subcommands>` under one CLI, so future modules (`ble`, `ir`, ...) slot in the same way.

### Scan nearby networks

```bash
./nrsuite scan
```

```
Found device: /dev/bus/usb/002/008
Requesting USB permission (tap OK)...

[2026-06-19 17:38:32] === WiFi Network Scan ===
[2026-06-19 17:38:32] Device: 303A:1001  ESP32-S3 native USB CDC

==========================================================================================
SSID                           BSSID               CH   RSSI  SECURITY
------------------------------------------------------------------------------------------
HomeNetwork                    C8:3A:35:CA:75:48   11    -64  WPA/WPA2-PSK
OfficeWifi                     B0:4E:26:CC:2E:F8    3    -66  WPA2-PSK

2 networks found.
```

### Capture packets

```bash
# Fixed channel
./nrsuite sniff --channel 6
./nrsuite sniff --channel 6 -o capture.pcap

# Channel hopping (hops 1–13 every 300ms, stop with Ctrl+C)
./nrsuite sniff --hop --interval 300
```

### Open in Wireshark / termshark

```bash
# Transfer the file and open on PC
wireshark capture.pcap

# Live via termshark on the phone
mkfifo /tmp/live.pcap
termshark -i /tmp/live.pcap &
./nrsuite sniff --channel 6 -o /tmp/live.pcap
```

### Capture EAPOL handshake (passive)

```bash
./nrsuite sniff --channel 6 --eapol-only --bssid C8:3A:35:CA:75:48
```

### Deauth + handshake capture

```bash
./nrsuite deauth \
    --bssid C8:3A:35:CA:75:48 \
    --channel 11 \
    --count 15 \
    --capture-secs 30
```

Sends 15 deauth frames to disconnect clients, then captures EAPOL frames for 30 seconds. The resulting pcap can be used with Hashcat or Aircrack-ng for offline WPA2 key testing.

> ⚠️ Only use this on your own network or with explicit written permission from the network owner.

---

## Environments

NRSuite supports three runtime environments, detected automatically via `detect_backend()`. The same CLI commands work identically in all three.

### No root (stock Termux)

The most unique use-case. Works on any unmodified Android phone.

```
Android USB host stack
        ↓
   termux-usb  (requests permission, grants fd)
        ↓
libusb_wrap_sys_device(fd)
        ↓
   nrsuite Python
```

```bash
pkg install python termux-api libusb && pip install pyusb
# Install Termux:API from F-Droid
./nrsuite scan  # permission popup appears on first run
```

### With root (Termux + tsu/sudo)

When running as uid 0, libusb opens `/dev/bus/usb` directly — no `termux-usb`, no permission dialog, no bootstrap subprocess. Faster and simpler.

```bash
pkg install python libusb && pip install pyusb
tsu  # or: sudo ./nrsuite scan
./nrsuite scan
```

### Kali NetHunter

Works in both the NetHunter terminal (Kali chroot, root) and a Termux session running alongside it.

```bash
# In the NetHunter terminal (root)
apt update && apt install python3 python3-pip libusb-1.0-0
pip3 install pyusb
./nrsuite scan

# Note: if cdc_acm claimed the interface, nrsuite detaches it automatically
```

### Backend summary

| Environment | uid | USB access |
|---|:---:|---|
| Stock Termux (no root) | 1000 | `termux-usb` → `libusb_wrap_sys_device(fd)` |
| Termux + root (tsu/sudo) | 0 | libusb → `/dev/bus/usb` directly |
| NetHunter terminal | 0 | libusb → `/dev/bus/usb` directly |
| NetHunter + Termux (no root) | 1000 | `termux-usb` → `libusb_wrap_sys_device(fd)` |

Detection is fully automatic — no `--root` flag or manual configuration needed.

---

## Comparison

| | NRSuite (no root) | NRSuite (root) | NetHunter + ext. adapter |
|--|:-----------------:|:--------------:|:------------------------:|
| Root required | ✗ | ✓ | ✓ |
| Custom kernel / ROM | ✗ | ✗ | ✓ |
| Hardware cost | ~$5 | ~$5 | $150–400+ |
| Supported devices | Any Android | Any Android | NetHunter-supported only |
| Monitor mode | ✓ (ESP32) | ✓ (ESP32) | ✓ |
| Packet injection | ✓ | ✓ | ✓ |
| USB permission dialog | First use only | ✗ | ✗ |
| Live Wireshark (FIFO) | ✓ | ✓ | ✓ |
| Beyond Wi-Fi (BLE / IR / RF) | Planned | Planned | ✗ |

---

## Firmware

### Supported boards

| Board | `platformio.ini` env | VID:PID | Status |
|-------|---------------------|:-------:|:------:|
| ESP32-C3 SuperMini | `esp32-c3-supermini` | `303A:1001` | ✅ Tested |
| ESP32-S3 | `esp32-s3` | `303A:1001` | ✅ Tested |
| ESP32-S2 | `esp32-s2` | `303A:0002` | ⚠️ Untested |

### Key build flags

```ini
build_flags =
    -DARDUINO_USB_MODE=1           ; route Serial to native USB, not UART pins
    -DARDUINO_USB_CDC_ON_BOOT=1    ; enable CDC before setup() runs  ← CRITICAL
    -DCONFIG_AUTOSTART_ARDUINO=1   ; loop() won't run without this
    -DCONFIG_ESP_WIFI_ENABLE_SNIFFER=1
```

> **`ARDUINO_USB_CDC_ON_BOOT=1` is critical** — without it `Serial` maps to UART0 (TX/RX pins) and the bridge protocol gets no data over USB.

### Flashing with PlatformIO

```bash
cd firmware/

# Flash + open serial monitor
pio run -e esp32-c3-supermini --target upload && pio device monitor

# Confirm boot — should print: ESP32_READY
# Heartbeat JSON appears every 5s: {"uptime":5000,"heap":250336,"type":"heartbeat"}
```

### Flashing pre-built binaries

Pre-built `.bin` files are on the [Releases](https://github.com/7wp81x/nrsuite/releases) page.

```bash
pip install esptool

esptool.py --chip esp32c3 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-c3.bin
esptool.py --chip esp32s3 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-s3.bin
esptool.py --chip esp32s2 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-s2.bin
```

Or use the [ESP32 Flash Download Tool](https://www.espressif.com/en/support/download/other-tools) on Windows.

---

## Bridge Protocol

NRSuite uses a compact binary framing protocol over USB CDC bulk transfer. It's transport for the whole suite, not just Wi-Fi — future modules (BLE, IR, NRF24) reuse the same framing and add their own CMD types.

```
[0xAD 0xDE][TYPE 1B][ID 1B][LENGTH 4B LE][PAYLOAD NB]
```

| Type | Hex | Direction | Payload |
|------|:---:|-----------|---------|
| CMD | `0x01` | Termux → ESP32 | JSON `{"cmd": "...", "args": {...}}` |
| RESP | `0x02` | ESP32 → Termux | JSON response, same ID as CMD |
| EVENT | `0x03` | ESP32 → Termux | JSON async event (scan results, heartbeat) |
| PCAP | `0x04` | ESP32 → Termux | Raw binary: radiotap header + 802.11 frame |
| ACK | `0x05` | Termux → ESP32 | JSON `{"chunk": N}` — flow control |

PCAP frames use sliding-window flow control: the ESP32 buffers up to `SNIFF_MAX_INFLIGHT` (default 4) unacknowledged frames before pausing.

### Supported CMDs (Wi-Fi module)

| CMD | Args | Response |
|-----|------|----------|
| `PING` | — | `{"ok": true, "msg": "pong"}` |
| `STATUS` | — | `{"ok": true, "uptime": ms, "heap": bytes, "chip": "...", "sniffing": bool}` |
| `SCAN_WIFI` | — | `{"ok": true, "count": N}` + N `scan_ap` events |
| `START_SNIFF` | `{"mode": "fixed"\|"hop", "channel": 1-13, ...}` | `{"ok": true}` |
| `STOP_SNIFF` | — | `{"ok": true, "captured": N, "sent": N, "dropped": N}` |
| `DEAUTH` | `{"bssid": "...", "channel": N, "count": N, ...}` | `{"ok": true, "sent": N}` |
| `DEAUTH_CAPTURE` | same as DEAUTH | `{"ok": true, "sent": N, "sniffing": true}` |

---

## Project Structure

```
nrsuite/
├── firmware/
│   ├── platformio.ini            # multi-board build config (C3/S3/S2)
│   ├── src/
│   │   ├── main.cpp              # Arduino entry point, CMD dispatcher
│   │   ├── sniffer.cpp / .h      # Promiscuous capture, radiotap builder
│   │   └── override_sanity.cpp   # Bypass IDF raw frame sanity check
│   └── lib/
│       └── BridgeProtocol/       # Framed binary protocol (ESP32 side)
├── nrsuite                       # Main CLI (chmod +x, run as ./nrsuite)
├── protocol.py                   # FrameParser + Protocol class
├── receiver.py                   # USB bulk IN background thread
├── sender.py                     # Thread-safe USB bulk OUT
├── usb_device.py                 # Device detection, fd wrapping, endpoints
├── pcap_writer.py                # pcap writer, buffered + stream modes
├── data/                         # Logs and captures (auto-created, gitignored)
└── README.md
```

---


## Roadmap

Wi-Fi is the first module. These are next:

- [X] AP Mode — Captive Portal support
- [ ] Beacon Broadcasting — beacon spam, custom SSIDs, hidden SSIDs
- [ ] Bluetooth — BLE scanning, advertising, device discovery, BLE spam
- [ ] HID Emulation — BLE BadUSB, keyboard injection
- [ ] Hardware expansion — IR, NRF24, CC1101 modules

---

## Legal

This tool is intended for authorized security research, penetration testing on your own infrastructure, and educational use only. The authors are not responsible for misuse.

Sending deauthentication frames disrupts connectivity for affected clients. Do not use on networks you do not own or manage. In many jurisdictions, unauthorized disruption of network communications is a criminal offense.

Always obtain explicit written permission before testing any network or device you do not own.

---

## License

MIT — see [`LICENSE`](LICENSE).

---

## Acknowledgements

- [Bruce firmware](https://github.com/pr3y/Bruce) — ESP32 multi-tool firmware; referenced for radio patterns and IR implementation
- [esp32-deauther](https://github.com/SpacehuhnTech/esp8266_deauther) — original concept inspiration
- [Espressif IDF team](https://github.com/espressif/esp-idf) — for the raw `esp_wifi_*` API that makes promiscuous mode and frame injection possible without kernel drivers
- [Termux](https://termux.dev) and termux-api contributors — for making Android a real Linux environment
- [PyUSB / libusb](https://github.com/pyusb/pyusb) — for `libusb_wrap_sys_device`, the key primitive that makes no-root USB access possible
