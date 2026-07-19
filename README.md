# NRSuite

> Turn a $3–5 ESP32 into a wireless research toolkit for Termux — **no root required.**

NRSuite bypasses Android's locked-down radio APIs by offloading the radio layer to an ESP32 over USB OTG, turning a stock, unrooted Android phone into a wireless research toolkit. See [Features](#features) for exactly what's implemented today. The firmware and bridge protocol are modular by design — new radio backends and capabilities register their own CMDs without touching the transport layer, so the toolkit keeps growing without becoming a single-purpose tool.

<p align="center">
  <img src="docs/images/architecture_bw.jpg" width="700" alt="Architecture diagram">
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

> BLE HID requires a chip with a Bluetooth radio (C3, S3, or classic ESP32). ESP32-S2 is Wi-Fi only and does not support this feature — see [Hardware](#hardware).

> USB Mass Storage and BadUSB require a chip with **native USB-OTG** (S2, S3). File read/write/delete/list operations work on any chip via the bridge protocol regardless of USB-OTG support — only entering actual MSC/HID device mode needs it. ESP32-C3 and classic ESP32 devkits have no USB-OTG peripheral, so `masstorage start` and `badusb` are unavailable on those boards — see [Hardware](#hardware).

---

## Hardware

| Component | Status | Notes |
|-----------|:------:|-------|
| **ESP32-C3** | ✅ Tested | Native USB CDC, ~$3 — covers both SuperMini and regular C3 devkit boards, WiFi + BLE HID support. No USB-OTG — mass storage device mode and BadUSB HID injection are unavailable (file read/write/delete/list over the bridge still work) |
| **ESP32-S3** (any board) | ✅ Tested | More RAM/flash, native USB CDC, dual-core, WiFi + BLE HID + USB Mass Storage + BadUSB support |
| ESP32-S2 (any board) | ✅ Tested | Native USB (OTG), single-core, WiFi + USB Mass Storage + BadUSB support — **no BLE radio**, so BadBLE/keyboard is unavailable on this chip regardless of testing status |
| **Classic ESP32 devkit (WROOM-32)** | ✅ Tested | Requires external USB-UART bridge on the board — no native USB CDC and no USB-OTG. CP2102, CH340, CH9102, and FTDI FT232 are explicitly supported with correct reset/init handling; other bridge chips will likely still work via generic CDC/bulk-endpoint fallback, but without guaranteed reset timing. WiFi + BLE HID support — mass storage device mode and BadUSB unavailable (no USB-OTG hardware) |
| USB OTG cable / adapter | — | USB-C OTG or micro-USB OTG depending on your phone |
| Android phone | — | Any version with USB host support — no root required |

NRSuite supports **both native USB CDC and external USB-UART** boards:

- **Native USB** boards (C3, S3, S2) show up as `303A:xxxx` and communicate directly over USB — no bridge chip needed. C3 uses USB-Serial-JTAG; S2 (and optionally S3) uses USB-OTG — see [build flags](#key-build-flags) for the distinction.
- **UART-based** boards (classic ESP32 devkits) use an onboard USB-to-serial chip and show up under that chip's own VID:PID. CP2102, CH340, CH9102, and FTDI FT232 are explicitly recognized (with correct reset/DTR handling); other bridge chips generally still work via a generic bulk-endpoint fallback. The bridge protocol works identically across all transports — `nrsuite` autodetects the connected device type.

The Wi-Fi module uses the ESP32's built-in 2.4 GHz radio — no external antenna needed. Future modules (NRF24, CC1101, IR) will use external add-on hardware — see [Roadmap](#roadmap).

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

All commands follow the same pattern — the script detects the USB device, requests permission via `termux-usb`, and re-invokes itself with the granted file descriptor. Wi-Fi and BLE HID are implemented so far; commands below are all `nrsuite <module-style subcommands>` under one CLI, so future modules (`ir`, ...) slot in the same way.

### Scan nearby networks

```bash
./nrsuite scan
```

```
_____ _____ _____     _ _       
|   | | __  |   __|_ _|_| |_ ___ 
| | | |    -|__   | | | |  _| -_|
|_|___|__|__|_____|___|_|_| |___| v1.2

[+] Github @7wp81x/NRSuite

[*] Backend: termux-api (no-root)
[+] Found device: /dev/bus/usb/002/051
[*] Requesting USB permission...

[*] Starting network scan...
[+] Starting bridge, Please wait...
[+] Native USB-CDC port opened (DTR asserted, ctrl intf 2).
[*] ESP32-S3: OK, wireless network scan initialized

  [*] HomeWifi                     XX:XX:XX:XX:2E:F8    3   -59  ▂▄▆_   WPA2-PSK
  [*] OfficeWifi                   XX:XX:XX:XX:75:48   11   -66  ▂▄__   WPA/WPA2-PSK
  [*] Free Wifi                    XX:XX:XX:XX:2A:BF    6   -70  ▂▄__   OPEN
  [*] Hotspot 1                    XX:XX:XX:XX:DA:D6    1   -78  ▂___   OPEN
  [*] Network_Kid                  XX:XX:XX:XX:XX:A7    1   -81  ▂___   OPEN

[+] 5 networks found, 3 open.

[+] Process finished (exit 0).

```

### Capture packets

```bash
# Fixed channel
./nrsuite sniff --channel 6
./nrsuite sniff --channel 6 -o capture.pcap

# Channel hopping (stop with Ctrl+C)
./nrsuite sniff --hop --interval 300

# EAPOL-only, filtered to a target BSSID/client
./nrsuite sniff --channel 6 --eapol-only --bssid C8:3A:35:CA:75:48 --client AA:BB:CC:DD:EE:FF

# Trigger deauth while sniffing, capped by count/duration
./nrsuite sniff --channel 6 --deauth --count 15 --duration 30

# Stream to a FIFO instead of writing a file
./nrsuite sniff --channel 6 --stream -o /tmp/live.pcap
```

Run `./nrsuite sniff --help` for the full flag list — options like `--count`, `--duration`, `--client`, and `--stream` combine with the modes above.

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

### Deauth

```bash
./nrsuite deauth \
    --bssid C8:3A:35:CA:75:48 \
    --channel 11 \
    --client FF:FF:FF:FF:FF:FF \ # Specific client or All client (remove)
    --count 15 \
    --interval 100
```

Sends 15 deauth frames to disconnect clients on the target BSSID. To capture the resulting EAPOL handshake at the same time, use `sniff --deauth` (see above) instead of standalone `deauth` — that combined mode is what produces a pcap usable with Hashcat or Aircrack-ng for offline WPA2 key testing.

> ⚠️ Only use this on your own network or with explicit written permission from the network owner.

### Captive portal / AP mode

```bash
./nrsuite portal start --ssid "Free WiFi" --channel 6
./nrsuite portal status
./nrsuite portal stop

# Serve a custom HTML page
./nrsuite portal start --ssid "Free WiFi" --file login.html

# Auto-capture EAPOL from a target BSSID while the portal is up
# This will also send deauth frames on target BSSID
./nrsuite portal start --ssid "Free WiFi" --bssid C8:3A:35:CA:75:48
```

> ⚠️ Only deploy a captive portal against networks/devices you own or have explicit written permission to test.

### BLE HID (BadBLE / keyboard)

> Requires a board with a Bluetooth radio — C3, S3, or classic ESP32 devkit. Not available on ESP32-S2 (WiFi-only silicon).

```bash
# Run a DuckyScript payload over BLE once a host pairs
./nrsuite ble badble --advertise "Keyboard" --payload payload.txt

# Keep advertising after the payload finishes, so you can re-trigger it
./nrsuite ble badble --advertise "Keyboard" --payload payload.txt --keep-alive

# Realtime keystroke passthrough — types whatever you type in this terminal
./nrsuite ble keyboard --advertise "Keyboard"
```

> ⚠️ Only use BLE HID injection on devices you own or have explicit written permission to test.

### USB Mass Storage

> `masstorage start` and `badusb` require a chip with native USB-OTG (S2, S3). `files`/`delete`/`free` work on any chip over the bridge protocol. See [Hardware](#hardware).

```bash
# Enter USB mass storage mode — host sees the ESP32 as a USB drive
./nrsuite masstorage start

# List files without entering MSC mode (works even on C3/devkit)
./nrsuite masstorage files

# Delete a file if it exists
./nrsuite masstorage delete secret.txt

# Show storage free / used / total size
./nrsuite masstorage free
```

`masstorage start` re-enumerates the USB connection as a mass storage device — there is no software command to exit this mode; press the physical button (or reset) on the device to return to CDC bridge mode.

### BadUSB

> Requires a chip with native USB-OTG (S2, S3). Not available on C3 or classic ESP32 devkit — see [Hardware](#hardware).

```bash
# Run a DuckyScript payload over native USB HID
./nrsuite badusb --payload payload.txt

# Also expose mass storage alongside the HID device
./nrsuite badusb --payload payload.txt --masstorage
```

Payload scripts support a few extra device-control lines alongside standard DuckyScript:

```
DEVICE_REBOOT       # restart the ESP32
DEVICE_MSC_START    # start mass storage mode from within the script (if not launched with --masstorage)
DEVICE_MSC_STOP     # hide/detach the mass storage device without a full reboot
```

> ⚠️ Only use BadUSB injection on devices you own or have explicit written permission to test.

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
pkg install python termux-api libusb && pip install espbridge
# Install Termux:API from F-Droid
./nrsuite scan  # permission popup appears on first run
```

### With root (Termux + tsu/sudo)

When running as uid 0, libusb opens `/dev/bus/usb` directly — no `termux-usb`, no permission dialog, no bootstrap subprocess. Faster and simpler.

```bash
pkg install python libusb && pip install espbridge
tsu  # or: sudo ./nrsuite scan
./nrsuite scan
```

### Kali NetHunter

Works in both the NetHunter terminal (Kali chroot, root) and a Termux session running alongside it.

```bash
# In the NetHunter terminal (root)
apt update && apt install python3 python3-pip libusb-1.0-0
pip3 install espbridge
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
| Beyond Wi-Fi (BLE HID / IR / RF) | BLE HID shipped, IR/RF planned | BLE HID shipped, IR/RF planned | ✗ |

---

## Firmware

### Supported boards

| Board | `platformio.ini` env | Transport | VID:PID | Status |
|-------|---------------------|-----------|:-------:|:------:|
| ESP32-C3 | `esp32-c3` | Native USB CDC | `303A:1001` | ✅ Tested |
| ESP32-S3 | `esp32-s3` | Native USB CDC | `303A:1001` | ✅ Tested |
| ESP32-S2 | `esp32-s2` | Native USB (OTG) | `303A:0002` | ✅ Tested |
| Classic ESP32 devkit (WROOM-32) | `esp32-devkit` | External USB-UART (CP2102/CH340) | chip-dependent | ✅ Tested |

### Key build flags

USB-Serial-JTAG boards (C3, S3):

```ini
build_flags =
    -DARDUINO_USB_MODE=1           ; route Serial to the USB-Serial-JTAG peripheral
    -DARDUINO_USB_CDC_ON_BOOT=1    ; enable CDC before setup() runs  ← CRITICAL
    -DCONFIG_AUTOSTART_ARDUINO=1   ; loop() won't run without this
    -DCONFIG_ESP_WIFI_ENABLE_SNIFFER=1
```

USB-OTG boards (S2 — and S3 if you prefer OTG mode over JTAG-Serial):

```ini
build_flags =
    -DARDUINO_USB_MODE=0           ; S2 has no USB-Serial-JTAG peripheral — must use OTG/TinyUSB
    -DARDUINO_USB_CDC_ON_BOOT=1    ; enable CDC before setup() runs  ← CRITICAL
    -DCONFIG_AUTOSTART_ARDUINO=1
    -DCONFIG_ESP_WIFI_ENABLE_SNIFFER=1
```

> **`ARDUINO_USB_CDC_ON_BOOT=1` is critical on both native-USB variants** — without it `Serial` maps to UART0 (TX/RX pins) instead of native USB, and the bridge protocol gets no data over the OTG cable.

> `ARDUINO_USB_MODE` controls *which* native USB peripheral `Serial` binds to — `1` = USB-Serial-JTAG (only present on C3/S3/C6/H2 silicon), `0` = USB-OTG/TinyUSB (present on S2/S3). Setting `MODE=1` on a chip without the JTAG-Serial peripheral (like S2) causes a build error (`'HWCDCSerial' was not declared in this scope`) since that class was never compiled in for that chip.

External USB-UART boards (classic ESP32 devkit — no native USB peripheral at all):

```ini
build_flags =
    -DARDUINO_USB_MODE=0            ; no native USB peripheral on classic ESP32
    -DARDUINO_USB_CDC_ON_BOOT=0     ; Serial routes to UART0, out through the onboard CP2102/CH340
    -DCONFIG_AUTOSTART_ARDUINO=1
    -DCONFIG_ESP_WIFI_ENABLE_SNIFFER=1
```

The bridge protocol and every CMD work identically across all three configurations — the only difference is the physical/USB layer. `nrsuite` autodetects which one is connected.

### Flashing with PlatformIO

```bash
cd firmware/

# Flash + open serial monitor
pio run -e esp32-c3 --target upload && pio device monitor

# Confirm boot — should print: ESP32_READY
# Heartbeat JSON appears every 5s: {"uptime":5000,"heap":250336,"type":"heartbeat"}
```

### Flashing pre-built binaries

Pre-built `.bin` files are on the [Releases](https://github.com/7wp81x/nrsuite/releases) page.

#### From a PC / laptop

```bash
pip install esptool

esptool.py --chip esp32c3 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-esp32c3.bin
esptool.py --chip esp32s3 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-esp32s3.bin
esptool.py --chip esp32s2 --port /dev/ttyUSB0 write_flash 0x0 nrsuite-esp32s2.bin
esptool.py --chip esp32   --port /dev/ttyUSB0 write_flash 0x0 nrsuite-esp32-generic.bin
```

No Python environment handy? Espressif also runs a browser-based flasher that works over WebSerial — no install required, just Chrome/Edge and a USB cable:

- [ESP Web Flasher](https://espressif.github.io/esptool-js/) — drag in the `.bin`, pick the offset (`0x0`), flash from the browser
- [ESP32 Flash Download Tool](https://www.espressif.com/en/support/download/other-tools) — Windows GUI alternative

#### From Android only (Termux, no root)

`esptool.py` depends on pyserial, which expects a `/dev/ttyUSB*` node — Android doesn't expose one to unrooted apps, so plain `esptool.py` **will not work** in stock Termux. Use [Termux-ESP-Flasher](https://github.com/7wp81x/Termux-ESP-Flasher) instead. A Termux-native flasher that talks to the USB endpoints directly (same `termux-usb` fd-wrapping approach NRSuite itself uses), with no root and no pyserial required:

```bash
pkg update && pkg install python termux-api libusb
pip install pyusb
```

Install the **Termux:API** companion app from [F-Droid](https://f-droid.org/packages/com.termux.api/) — *not* the Play Store version, which is outdated.

```bash
pip3 install nrflash

# Auto-detects the chip — omit --chip unless you want to force it
nrflash write --offset 0x0 nrsuite-*

# No stub, if above failed, try also holding the boot btn while plugging in the device.
nrflash write --offset 0x0 nrsuite-* --no-stub
```

See the [Termux-ESP-Flasher README](https://github.com/7wp81x/Termux-ESP-Flasher) for more informations.

---

## Bridge Protocol

NRSuite uses a compact binary framing protocol over the serial link (native USB CDC bulk transfer, or a UART bridge chip depending on board). It's transport for the whole suite, not just Wi-Fi — BLE HID already reuses it, and future modules (IR, NRF24, CC1101) will add their own CMD types on top of the same framing.

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

### Supported CMDs (BLE HID module)

> Only available on boards with a Bluetooth radio (C3, S3, classic ESP32 devkit). Not compiled in on ESP32-S2 builds — that chip has no Bluetooth radio.

| CMD | Args | Response |
|-----|------|----------|
| `BLE_BEGIN` | `{"name": "..."}` | `{"ok": true}` |
| `BLE_STATUS` | — | `{"ok": true, "connected": bool, "advertising": bool, "peer": "..."}` |
| `BLE_RUN_SCRIPT` | `{"script": "...DuckyScript text..."}` | `{"ok": true, "lines": N}` |
| `BLE_KEY_DOWN` | `{"key": "..."}` | `{"ok": true}` |
| `BLE_KEY_UP` | `{"key": "..."}` | `{"ok": true}` |
| `BLE_STOP` | — | `{"ok": true}` |
| `BLE_END` | — | `{"ok": true}` |

### Supported CMDs (Mass Storage module)

> `MSC_SETUP` requires a board with native USB-OTG (S2, S3) and responds `{"ok": false, "msg": "storage not supported on this chip"}` elsewhere. `MSC_LIST`/`MSC_READ`/`MSC_WRITE`/`MSC_DELETE`/`MSC_SPACE` work on any chip — they only touch the onboard FFat filesystem, not USB-OTG hardware.

| CMD | Args | Response |
|-----|------|----------|
| `MSC_SETUP` | — | `{"ok": true, "msg": "msc mode active"}` |
| `MSC_LIST` | — | `{"ok": true, "files": [{"name": "...", "size": N}, ...], "total": N, "used": N, "free": N}` |
| `MSC_READ` | `{"path": "..."}` | `{"ok": true, "path": "...", "content": "...", "size": N}` |
| `MSC_WRITE` | `{"path": "...", "content": "...", "append": bool}` | `{"ok": true}` |
| `MSC_DELETE` | `{"path": "..."}` | `{"ok": true}` |
| `MSC_SPACE` | — | `{"ok": true, "total": N, "used": N, "free": N}` |

### Supported CMDs (BadUSB module)

> Only available on boards with native USB-OTG (S2, S3). Not compiled in on ESP32-C3 or classic ESP32 devkit builds — those chips have no USB-OTG peripheral.

| CMD | Args | Response |
|-----|------|----------|
| `START_MSC` | — | May not respond — USB re-enumerates as mass storage, dropping the CDC link |

In addition to standard DuckyScript, payload scripts can include device-control lines (parsed inline, not sent as separate bridge CMDs):

| Script line | Effect |
|-------------|--------|
| `DEVICE_REBOOT` | Restarts the ESP32 (`ESP.restart()`) |
| `DEVICE_MSC_START` | Starts mass storage mode mid-script (equivalent to `MassStorage::setup()`) — useful if the device wasn't launched with `--masstorage` |
| `DEVICE_MSC_STOP` | Detaches the mass storage device (`setMediaPresent(false)`) without a full reboot |

---

## Project Structure

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


## Roadmap

See the [Features](#features) checklist at the top for exactly what's shipped vs. planned — it's kept up to date as things land, so this section won't drift out of sync with it.

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