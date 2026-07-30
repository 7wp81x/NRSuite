# Bridge Protocol

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
| HTML | `0x06` | Termux → ESP32 | Chunked raw payload upload — used for the captive portal's custom HTML page |

PCAP frames use sliding-window flow control: the ESP32 buffers up to `SNIFF_MAX_INFLIGHT` (default 4) unacknowledged frames before pausing.

## Supported CMDs (Wi-Fi module)

| CMD | Args | Response |
|-----|------|----------|
| `PING` | — | `{"ok": true, "msg": "pong"}` |
| `STATUS` | — | `{"ok": true, "uptime": ms, "heap": bytes, "chip": "...", "sniffing": bool}` |
| `SCAN_WIFI` | — | `{"ok": true, "count": N}` + N `scan_ap` events |
| `START_SNIFF` | `{"mode": "fixed"\|"hop", "channel": 1-13, ...}` | `{"ok": true}` |
| `STOP_SNIFF` | — | `{"ok": true, "captured": N, "sent": N, "dropped": N}` |
| `DEAUTH` | `{"bssid": "...", "channel": N, "count": N, ...}` | `{"ok": true, "sent": N}` |
| `DEAUTH_CAPTURE` | same as DEAUTH | `{"ok": true, "sent": N, "sniffing": true}` |

## Supported CMDs (BLE HID module)

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

## Supported CMDs (Mass Storage module)

> `MSC_SETUP` requires a board with native USB-OTG (S2, S3) and responds `{"ok": false, "msg": "storage not supported on this chip"}` elsewhere. `MSC_LIST`/`MSC_READ`/`MSC_WRITE`/`MSC_DELETE`/`MSC_SPACE` work on any chip — they only touch the onboard FFat filesystem, not USB-OTG hardware.

| CMD | Args | Response |
|-----|------|----------|
| `MSC_SETUP` | — | `{"ok": true, "msg": "msc mode active"}` |
| `MSC_LIST` | — | `{"ok": true, "files": [{"name": "...", "size": N}, ...], "total": N, "used": N, "free": N}` |
| `MSC_READ` | `{"path": "..."}` | `{"ok": true, "path": "...", "content": "...", "size": N}` |
| `MSC_WRITE` | `{"path": "...", "content": "...", "append": bool}` | `{"ok": true}` |
| `MSC_DELETE` | `{"path": "..."}` | `{"ok": true}` |
| `MSC_SPACE` | — | `{"ok": true, "total": N, "used": N, "free": N}` |

## Supported CMDs (BadUSB module)

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

[← Back to README](../README.md)
