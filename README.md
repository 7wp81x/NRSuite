# NRSuite

> Turn a $3–5 ESP32 into a wireless research toolkit for Termux — **no root required.**

NRSuite bypasses Android's locked-down radio APIs by offloading the radio layer to an ESP32 over USB OTG, turning a stock, unrooted Android phone into a wireless research toolkit. See [Features](#features) for exactly what's implemented today. The firmware and bridge protocol are modular by design — new radio backends and capabilities register their own CMDs without touching the transport layer, so the toolkit keeps growing without becoming a single-purpose tool.

<p align="center">
  <img src="docs/images/architecture_bw.jpg" width="700" alt="Architecture diagram">
</p>

<p align="center">
  <img src="docs/images/nrsuite1_nanoUART-ESP32S2.jpg" width="600" alt="ESP32-C3-SuperMini connected to Android phone via OTG cable">
</p>

> ⚠️ **Authorized use only.** Only use this tool on networks and devices you own or have explicit written permission to test. Unauthorized interception of network traffic is illegal in most jurisdictions.

---

## Why this exists

Android has never exposed monitor mode, raw packet injection, or low-level radio control to user-space apps — not even with root on most devices. The traditional path required a rooted phone, a custom kernel (e.g. NetHunter), a supported external USB adapter, and a lot of luck matching hardware versions.

NRSuite sidesteps the entire problem:

- The **ESP32** handles everything radio-level — promiscuous capture, channel hopping, raw frame injection
- **Termux** talks to it over USB (native CDC or external UART bridge, depending on board) using `termux-usb` + libusb — no root, no kernel modules, no custom ROM
- The **Python bridge** speaks a compact framed binary protocol with flow control, not serial ASCII
- The **firmware and protocol are modular** — new radio backends register their own CMDs without touching the transport layer

Total hardware cost: under $5. Works on any Android phone with USB-C or micro-USB and an OTG cable.

---

## Features

Checklist of implemented functionality — update this when adding/removing features so it stays accurate at a glance.

- [x] **WiFi scan** — active scan with SSID, BSSID, channel, RSSI, security type
- [x] **Packet sniffing** — fixed channel or channel-hopping promiscuous capture, `.pcap` output, live stream via FIFO
- [x] **EAPOL capture** — passive handshake capture, optional BSSID/client filtering
- [x] **Deauthentication** — standalone deauth, or combined with sniffing to trigger + capture a handshake
- [x] **Captive portal / AP mode** — start/stop/status, custom SSID + channel, custom HTML upload, optional auto EAPOL capture against a target BSSID
- [x] **BLE HID (BadBLE)** — advertise as a BLE keyboard, run a DuckyScript payload against a paired host
- [x] **BLE HID (realtime keyboard)** — live keystroke passthrough from your terminal to a paired BLE host
- [x] **USB Mass Storage** — expose onboard flash as a real USB drive to the host; list/read/write/delete files over the bridge without entering MSC mode
- [x] **BadUSB** — run a DuckyScript payload over native USB HID, with optional simultaneous mass storage exposure
- [x] **Heartbeat** — uptime + free heap reported every 5 seconds for health monitoring
- [ ] Beacon broadcasting (beacon spam, custom/hidden SSIDs)
- [ ] BLE scanning, advertising, device discovery, BLE spam
- [ ] Hardware expansion — IR, NRF24, CC1101 modules

> BLE HID requires a chip with a Bluetooth radio (C3, S3, or classic ESP32). ESP32-S2 is Wi-Fi only and does not support this feature — see [Hardware](docs/hardware.md).

> USB Mass Storage and BadUSB require a chip with **native USB-OTG** (S2, S3). File read/write/delete/list operations work on any chip via the bridge protocol regardless of USB-OTG support — only entering actual MSC/HID device mode needs it. ESP32-C3 and classic ESP32 devkits have no USB-OTG peripheral, so `masstorage start` and `badusb` are unavailable on those boards — see [Hardware](docs/hardware.md).

This checklist is kept up to date as things land, so it's the single source of truth for what's shipped vs. planned — no separate Roadmap page to drift out of sync.

---

## Quick Start

### 1. Install dependencies (Termux)

```bash
pkg update && pkg install python termux-api libusb
pip install espbridge
```

`espbridge` pulls in `pyusb` automatically — `nrsuite` will also auto-install `espbridge` itself on first run if it's missing.

Also install the **Termux:API** companion app from [F-Droid](https://f-droid.org/packages/com.termux.api/) — *not* the Play Store version, which is outdated.

### 2. Clone the repo

```bash
git clone https://github.com/7wp81x/NRSuite
cd NRSuite
```

### 3. Flash the firmware

```bash
cd firmware/
pio run -e esp32-c3 --target upload   # or esp32-s3 / esp32-s2 / esp32-devkit
```

Confirm it booted correctly — `pio device monitor --baud 115200` should print `ESP32_READY`. See [Firmware](docs/firmware.md) for pre-built binaries and `esptool.py` instructions.

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

## Documentation

Full usage examples, protocol details, and hardware notes have moved into [`/docs`](docs/) to keep this page short:

| Doc | Covers |
|---|---|
| [Usage](docs/usage.md) | Full command reference — scan, sniff, deauth, portal, BLE HID, mass storage, BadUSB |
| [Hardware](docs/hardware.md) | Supported boards, chip capabilities, USB transport differences |
| [Environments](docs/environments.md) | No-root Termux, rooted Termux, and Kali NetHunter setup |
| [Comparison](docs/comparison.md) | NRSuite vs. NetHunter + external adapter |
| [Firmware](docs/firmware.md) | Build flags, flashing with PlatformIO/esptool/nrflash |
| [Bridge Protocol](docs/protocol.md) | Binary framing format and full CMD reference |
| [Project Structure](docs/project-structure.md) | Repo layout and the `espbridge` package |

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
