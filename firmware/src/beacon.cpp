#include "beacon.h"
#include <esp_wifi.h>
#include <WiFi.h>

void BeaconSpammer::begin(BridgeProtocol& proto) {
    _proto = &proto;
}

void BeaconSpammer::_randomMac(uint8_t out[6]) {
    // Locally administered, unicast
    out[0] = (esp_random() & 0xFE) | 0x02;
    for (int i = 1; i < 6; i++) {
        out[i] = esp_random() & 0xFF;
    }
}

void BeaconSpammer::_parseSsids(const String& raw) {
    _ssidCount = 0;
    String s = raw;
    // Normalize separators: commas → newlines
    s.replace(',', '\n');

    int start = 0;
    while (start < (int)s.length() && _ssidCount < BEACON_MAX_SSIDS) {
        int nl = s.indexOf('\n', start);
        String line = (nl == -1) ? s.substring(start) : s.substring(start, nl);
        line.trim();
        start = (nl == -1) ? s.length() : nl + 1;

        if (line.length() == 0) continue;
        if (line.length() > BEACON_SSID_MAX_LEN) {
            line = line.substring(0, BEACON_SSID_MAX_LEN);
        }

        strncpy(_ssids[_ssidCount], line.c_str(), BEACON_SSID_MAX_LEN);
        _ssids[_ssidCount][BEACON_SSID_MAX_LEN] = '\0';

        if (_randomBssid) {
            _randomMac(_bssids[_ssidCount]);
        } else {
            // Derive a stable BSSID from the SSID hash so restarts look the same
            uint32_t h = 0;
            for (size_t i = 0; _ssids[_ssidCount][i]; i++) {
                h = h * 31 + (uint8_t)_ssids[_ssidCount][i];
            }
            _bssids[_ssidCount][0] = 0x02;  // locally administered
            _bssids[_ssidCount][1] = (h >> 24) & 0xFF;
            _bssids[_ssidCount][2] = (h >> 16) & 0xFF;
            _bssids[_ssidCount][3] = (h >> 8)  & 0xFF;
            _bssids[_ssidCount][4] =  h        & 0xFF;
            _bssids[_ssidCount][5] = (_ssidCount + 1) & 0xFF;
        }
        _ssidCount++;
    }
}

size_t BeaconSpammer::_buildFrame(uint8_t* out, int idx) {
    // 802.11 Beacon frame (management subtype 8)
    // FC | Dur | Addr1(bcast) | Addr2(BSSID) | Addr3(BSSID) | Seq | Fixed params | Tags
    size_t pos = 0;

    // Frame Control: type=mgmt (0), subtype=beacon (8) → 0x80 0x00
    out[pos++] = 0x80;
    out[pos++] = 0x00;

    // Duration
    out[pos++] = 0x00;
    out[pos++] = 0x00;

    // Addr1 — broadcast
    memset(out + pos, 0xFF, 6);
    pos += 6;

    // Addr2 — BSSID (transmitter)
    memcpy(out + pos, _bssids[idx], 6);
    pos += 6;

    // Addr3 — BSSID
    memcpy(out + pos, _bssids[idx], 6);
    pos += 6;

    // Sequence control (incremented loosely; radio stack may rewrite)
    static uint16_t seq = 0;
    out[pos++] = (seq << 4) & 0xFF;
    out[pos++] = (seq >> 4) & 0xFF;
    seq = (seq + 1) & 0x0FFF;

    // Fixed parameters (12 bytes)
    // Timestamp (8 bytes) — use millis as a stand-in; clients ignore accuracy for discovery
    uint64_t ts = (uint64_t)millis() * 1000ULL;
    memcpy(out + pos, &ts, 8);
    pos += 8;

    // Beacon interval: 100 TU (102.4 ms) → little-endian 0x0064
    out[pos++] = 0x64;
    out[pos++] = 0x00;

    // Capability: ESS | Privacy optional bit off for open look
    out[pos++] = 0x01;  // ESS
    out[pos++] = 0x00;

    // Tagged parameter: SSID (tag 0)
    out[pos++] = 0x00;  // tag number
    if (_hidden) {
        out[pos++] = 0x00;  // length 0 → hidden SSID
    } else {
        size_t slen = strlen(_ssids[idx]);
        out[pos++] = (uint8_t)slen;
        memcpy(out + pos, _ssids[idx], slen);
        pos += slen;
    }

    // Supported Rates (tag 1) — 1, 2, 5.5, 11 Mbps basic
    out[pos++] = 0x01;
    out[pos++] = 0x08;
    out[pos++] = 0x82;  // 1 Mbps (basic)
    out[pos++] = 0x84;  // 2 Mbps (basic)
    out[pos++] = 0x8B;  // 5.5 Mbps (basic)
    out[pos++] = 0x96;  // 11 Mbps (basic)
    out[pos++] = 0x0C;  // 6 Mbps
    out[pos++] = 0x12;  // 9 Mbps
    out[pos++] = 0x18;  // 12 Mbps
    out[pos++] = 0x24;  // 18 Mbps

    // DS Parameter Set (tag 3) — current channel
    out[pos++] = 0x03;
    out[pos++] = 0x01;
    out[pos++] = _channel;

    return pos;
}

void BeaconSpammer::_transmit(int idx) {
    uint8_t frame[BEACON_FRAME_MAX];
    size_t len = _buildFrame(frame, idx);
    if (len == 0 || len > BEACON_FRAME_MAX) return;

    esp_err_t err = esp_wifi_80211_tx(WIFI_IF_AP, frame, len, false);
    if (err == ESP_OK) {
        _stats.sent++;
    }
}

bool BeaconSpammer::start(const String& ssids, uint8_t channel, uint16_t intervalMs,
                          bool randomizeBssid, bool hidden) {
    if (channel < 1 || channel > 13) return false;

    stop();

    _randomBssid = randomizeBssid;
    _hidden      = hidden;
    _channel     = channel;
    _intervalMs  = intervalMs > 0 ? intervalMs : BEACON_DEFAULT_INTERVAL_MS;
    _nextIdx     = 0;
    _stats       = BeaconStats{};
    _stats.channel = channel;

    _parseSsids(ssids);
    if (_ssidCount == 0) return false;

    _stats.ssids = (uint32_t)_ssidCount;

    // Align radio + AP interface to the target channel (same pattern as deauth)
    esp_wifi_set_promiscuous(false);
    esp_wifi_set_channel(_channel, WIFI_SECOND_CHAN_NONE);

    wifi_config_t ap_cfg = {};
    if (esp_wifi_get_config(WIFI_IF_AP, &ap_cfg) == ESP_OK) {
        ap_cfg.ap.channel = _channel;
        esp_wifi_set_config(WIFI_IF_AP, &ap_cfg);
    }
    esp_wifi_start();
    delay(100);

    _active    = true;
    _lastTxMs  = 0;  // transmit immediately on next update()
    return true;
}

void BeaconSpammer::stop() {
    _active = false;
    _ssidCount = 0;
}

void BeaconSpammer::update() {
    if (!_active || _ssidCount == 0) return;

    uint32_t now = millis();
    if (_lastTxMs != 0 && (now - _lastTxMs) < _intervalMs) return;
    _lastTxMs = now;

    _transmit(_nextIdx);
    _nextIdx = (_nextIdx + 1) % _ssidCount;
}
