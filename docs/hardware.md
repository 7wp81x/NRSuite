# Hardware

| Component | Status | Notes |
|-----------|:------:|-------|
| **ESP32-C3** | ✅ Tested | Native USB CDC, ~$3 — covers both SuperMini and regular C3 devkit boards, WiFi + BLE HID support. No USB-OTG — mass storage device mode and BadUSB HID injection are unavailable (file read/write/delete/list over the bridge still work) |
| **ESP32-S3** (any board) | ✅ Tested | More RAM/flash, native USB CDC, dual-core, WiFi + BLE HID + USB Mass Storage + BadUSB support |
| ESP32-S2 (any board) | ✅ Tested | Native USB (OTG), single-core, WiFi + USB Mass Storage + BadUSB support — **no BLE radio**, so BadBLE/keyboard is unavailable on this chip regardless of testing status |
| **Classic ESP32 devkit (WROOM-32)** | ✅ Tested | Requires external USB-UART bridge on the board — no native USB CDC and no USB-OTG. CP2102, CH340, CH9102, and FTDI FT232 are explicitly supported with correct reset/init handling; other bridge chips will likely still work via generic CDC/bulk-endpoint fallback, but without guaranteed reset timing. WiFi + BLE HID support — mass storage device mode and BadUSB unavailable (no USB-OTG hardware) |
| USB OTG cable / adapter | — | USB-C OTG or micro-USB OTG depending on your phone |
| Android phone | — | Any version with USB host support — no root required |

NRSuite supports **both native USB CDC and external USB-UART** boards:

- **Native USB** boards (C3, S3, S2) show up as `303A:xxxx` and communicate directly over USB — no bridge chip needed. C3 uses USB-Serial-JTAG; S2 (and optionally S3) uses USB-OTG — see [build flags](firmware.md#key-build-flags) for the distinction.
- **UART-based** boards (classic ESP32 devkits) use an onboard USB-to-serial chip and show up under that chip's own VID:PID. CP2102, CH340, CH9102, and FTDI FT232 are explicitly recognized (with correct reset/DTR handling); other bridge chips generally still work via a generic bulk-endpoint fallback. The bridge protocol works identically across all transports — `nrsuite` autodetects the connected device type.

The Wi-Fi module uses the ESP32's built-in 2.4 GHz radio — no external antenna needed. Future modules (NRF24, CC1101, IR) will use external add-on hardware — see the [Roadmap](../README.md#roadmap).

---

[← Back to README](../README.md)
