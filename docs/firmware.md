# Firmware

## Supported boards

| Board | `platformio.ini` env | Transport | VID:PID | Status |
|-------|---------------------|-----------|:-------:|:------:|
| ESP32-C3 | `esp32-c3` | Native USB CDC | `303A:1001` | ✅ Tested |
| ESP32-S3 | `esp32-s3` | Native USB CDC | `303A:1001` | ✅ Tested |
| ESP32-S2 | `esp32-s2` | Native USB (OTG) | `303A:0002` | ✅ Tested |
| Classic ESP32 devkit (WROOM-32) | `esp32-devkit` | External USB-UART (CP2102/CH340) | chip-dependent | ✅ Tested |

## Key build flags

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

## Flashing with PlatformIO

```bash
cd firmware/

# Flash + open serial monitor
pio run -e esp32-c3 --target upload && pio device monitor

# Confirm boot — should print: ESP32_READY
# Heartbeat JSON appears every 5s: {"uptime":5000,"heap":250336,"type":"heartbeat"}
```

## Flashing pre-built binaries

Pre-built `.bin` files are on the [Releases](https://github.com/7wp81x/nrsuite/releases) page.

### From a PC / laptop

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

### From Android only (Termux, no root)

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

[← Back to README](../README.md)
