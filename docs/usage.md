# Usage

All commands follow the same pattern — the script detects the USB device, requests permission via `termux-usb`, and re-invokes itself with the granted file descriptor. Wi-Fi and BLE HID are implemented so far; commands below are all `nrsuite <module-style subcommands>` under one CLI, so future modules (`ir`, ...) slot in the same way.

## Scan nearby networks

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

## Capture packets

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

## Open in Wireshark / termshark

```bash
# Transfer the file and open on PC
wireshark capture.pcap

# Live via termshark on the phone
mkfifo /tmp/live.pcap
termshark -i /tmp/live.pcap &
./nrsuite sniff --channel 6 -o /tmp/live.pcap
```

## Capture EAPOL handshake (passive)

```bash
./nrsuite sniff --channel 6 --eapol-only --bssid C8:3A:35:CA:75:48
```

## Deauth

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

## Captive portal / AP mode

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

## BLE HID (BadBLE / keyboard)

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

## USB Mass Storage

> `masstorage start` and `badusb` require a chip with native USB-OTG (S2, S3). `files`/`delete`/`free` work on any chip over the bridge protocol. See [Hardware](hardware.md).

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

## BadUSB

> Requires a chip with native USB-OTG (S2, S3). Not available on C3 or classic ESP32 devkit — see [Hardware](hardware.md).

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

[← Back to README](../README.md)
