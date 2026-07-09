#include "sniffer.h"

Sniffer* Sniffer::_instance = nullptr;

#pragma pack(push, 1)
struct RadiotapHeader {
    uint8_t  version;
    uint8_t  pad;
    uint16_t len;
    uint32_t present;
    uint16_t chan_freq;
    uint16_t chan_flags;
    int8_t   dbm_signal;
};
#pragma pack(pop)

static uint16_t channelToFreqMHz(uint8_t ch) {
    if (ch >= 1 && ch <= 13) return 2407 + ch * 5;
    if (ch == 14) return 2484;
    return 2412;
}

// ── begin ─────────────────────────────────────────────────────────────────
void Sniffer::begin(BridgeProtocol& proto) {
    _proto = &proto;
    _instance = this;
    _queue = xQueueCreate(SNIFF_QUEUE_DEPTH, sizeof(CapturedFrame));

    WiFi.disconnect();
    esp_wifi_set_promiscuous(false);
}

// ── buildRadiotap ────────────────────────────────────────────────────────
size_t Sniffer::buildRadiotap(uint8_t* out, uint8_t channel, int8_t rssi) {
    RadiotapHeader* rt = (RadiotapHeader*)out;
    rt->version = 0;
    rt->pad = 0;
    rt->len = sizeof(RadiotapHeader);
    rt->present = (1u << 3) | (1u << 5);
    rt->chan_freq = channelToFreqMHz(channel);
    rt->chan_flags = 0x00A0;
    rt->dbm_signal = rssi;
    return sizeof(RadiotapHeader);
}

// ── startFixed / startHop / stop / setChannel ─────────────────────────────
bool Sniffer::startFixed(uint8_t channel) {
    if (channel < 1 || channel > 13) return false;

    wifi_promiscuous_filter_t filter;
    filter.filter_mask = WIFI_PROMIS_FILTER_MASK_MGMT | WIFI_PROMIS_FILTER_MASK_DATA;
    esp_wifi_set_promiscuous_filter(&filter);
    esp_wifi_set_promiscuous_rx_cb(&Sniffer::promiscuousCb);
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);

    _channel = channel;
    _hopMode = false;
    _active = true;
    _stats = SniffStats{};
    return true;
}

bool Sniffer::startHop(uint16_t intervalMs) {
    if (!startFixed(1)) return false;
    _hopMode = true;
    _hopIntervalMs = intervalMs;
    _lastHopMs = millis();
    return true;
}

void Sniffer::stop() {
    esp_wifi_set_promiscuous(false);
    _active = false;
    _hopMode = false;
}

bool Sniffer::setChannel(uint8_t channel) {
    if (channel < 1 || channel > 13) return false;
    esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);
    _channel = channel;
    return true;
}

void Sniffer::handleHop() {
    if (!_active || !_hopMode) return;
    if (millis() - _lastHopMs < _hopIntervalMs) return;
    _lastHopMs = millis();
    _channel = (_channel % 13) + 1;
    esp_wifi_set_channel(_channel, WIFI_SECOND_CHAN_NONE);
}

// ── Filter ────────────────────────────────────────────────────────────────
void Sniffer::setEapolFilter(bool enable, const uint8_t bssid[6]) {
    _eapolOnly = enable;
    _hasTargetBssid = (bssid != nullptr && enable);
    if (_hasTargetBssid) memcpy(_targetBssid, bssid, 6);
    _beaconCaptured = false;
}

bool Sniffer::isEapolFrame(const wifi_promiscuous_pkt_t* pkt) const {
    uint16_t len = pkt->rx_ctrl.sig_len;
    const uint8_t* p = pkt->payload;
    if (len < 40) return false;

    uint8_t fc0 = p[0];
    if (((fc0 >> 2) & 0x3) != 2) return false; // Data only

    size_t offset = 24;
    if (((fc0 >> 4) & 0xF) & 0x08) offset += 2; // QoS

    for (size_t i = offset; i < len - 8; ++i) {
        if (p[i] == 0xAA && p[i+1] == 0xAA && p[i+2] == 0x03 &&
            p[i+6] == 0x88 && p[i+7] == 0x8E) {
            return true;
        }
    }
    return false;
}

bool Sniffer::isBeaconFrame(const wifi_promiscuous_pkt_t* pkt) const {
    if (!pkt || pkt->rx_ctrl.sig_len < 38) return false;
    const uint8_t* p = pkt->payload;
    uint8_t fc0 = p[0];
    return ((fc0 >> 2) & 0x3) == 0 && ((fc0 >> 4) & 0xF) == 8;
}

bool Sniffer::matchesTargetBssid(const wifi_promiscuous_pkt_t* pkt) const {
    if (pkt->rx_ctrl.sig_len < 22) return false;
    const uint8_t* p = pkt->payload;
    const uint8_t* addr1 = p + 4;
    const uint8_t* addr2 = p + 10;
    const uint8_t* addr3 = p + 16;
    return memcmp(addr1, _targetBssid, 6) == 0 ||
           memcmp(addr2, _targetBssid, 6) == 0 ||
           memcmp(addr3, _targetBssid, 6) == 0;
}

// ── Callback & Packet Handler ─────────────────────────────────────────────
void Sniffer::promiscuousCb(void* buf, wifi_promiscuous_pkt_type_t type) {
    if (_instance) _instance->handlePacket((wifi_promiscuous_pkt_t*)buf);
}

bool Sniffer::isAssociationRequest(const wifi_promiscuous_pkt_t* pkt) const {
    if (!pkt) return false;
    uint16_t len = pkt->rx_ctrl.sig_len;
    if (len < 24) return false;
    const uint8_t* p = pkt->payload;
    uint8_t fc0 = p[0];
    uint8_t ftype = (fc0 >> 2) & 0x3;
    uint8_t subtype = (fc0 >> 4) & 0xF;
    return (ftype == 0) && (subtype == 0);  // Management + Assoc Request
}

void Sniffer::handlePacket(wifi_promiscuous_pkt_t* pkt) {
    if (!_active) return;

    bool shouldCapture = false;

    if (_eapolOnly) {
        if (!_hasTargetBssid || matchesTargetBssid(pkt)) {
            if (isEapolFrame(pkt)) {
                shouldCapture = true;
            } else if (isBeaconFrame(pkt) && !_beaconCaptured) {
                shouldCapture = true;
                _beaconCaptured = true;
            }
        }
    } else {
        shouldCapture = true;
    }

    if (!shouldCapture) return;

    _stats.captured++;

    CapturedFrame f;
    uint16_t onAirLen = pkt->rx_ctrl.sig_len;
    f.orig_len = onAirLen;
    f.cap_len = (onAirLen < SNIFF_SNAPLEN) ? onAirLen : SNIFF_SNAPLEN;
    f.channel = pkt->rx_ctrl.channel;
    f.rssi = pkt->rx_ctrl.rssi;
    memcpy(f.data, pkt->payload, f.cap_len);

    if (xQueueSend(_queue, &f, 0) != pdTRUE) {
        _stats.dropped++;
    }

    // Association events
    if (isAssociationRequest(pkt)) {
        const uint8_t* addr2 = pkt->payload + 10; // Client MAC (TA)
        const uint8_t* addr3 = pkt->payload + 16; // BSSID

        if (!_eapolOnly || !_hasTargetBssid || memcmp(addr3, _targetBssid, 6) == 0) {
            char client_mac[18], bssid_str[18];
            snprintf(client_mac, sizeof(client_mac), "%02X:%02X:%02X:%02X:%02X:%02X",
                     addr2[0], addr2[1], addr2[2], addr2[3], addr2[4], addr2[5]);
            snprintf(bssid_str, sizeof(bssid_str), "%02X:%02X:%02X:%02X:%02X:%02X",
                     addr3[0], addr3[1], addr3[2], addr3[3], addr3[4], addr3[5]);

            JsonDocument ev;
            ev["type"] = "client_associated";
            ev["client"] = client_mac;
            ev["bssid"] = bssid_str;
            ev["rssi"] = pkt->rx_ctrl.rssi;
            _proto->sendEvent("client_associated", ev);
        }
    }
}

// ── processQueue — call from loop() ──────────────────────────────────────
void Sniffer::processQueue() {
    if (!_proto) return;

    CapturedFrame f;
    while (_inFlight < SNIFF_MAX_INFLIGHT && xQueueReceive(_queue, &f, 0) == pdTRUE) {
        uint8_t out[sizeof(RadiotapHeader) + SNIFF_SNAPLEN];
        size_t  rtLen = buildRadiotap(out, f.channel, f.rssi);
        memcpy(out + rtLen, f.data, f.cap_len);

        _proto->sendPcapChunk(_chunkCtr++, out, rtLen + f.cap_len);
        _inFlight++;
        _stats.sent++;
    }
    // If _inFlight is maxed, captured frames simply pile up in _queue
    // (and eventually get dropped there) until ACKs free up credit.
}

// ── onAck — wire to BridgeProtocol::onAck ───────────────────────────────────
void Sniffer::onAck(uint32_t chunkIndex) {
    (void)chunkIndex;
    if (_inFlight > 0) _inFlight--;
}