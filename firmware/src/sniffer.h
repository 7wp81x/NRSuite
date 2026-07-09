#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include "BridgeProtocol.h"

// Tunables
#define SNIFF_SNAPLEN      400
#define SNIFF_QUEUE_DEPTH  24
#define SNIFF_MAX_INFLIGHT 4

struct CapturedFrame {
    uint16_t cap_len;
    uint16_t orig_len;
    uint8_t  channel;
    int8_t   rssi;
    uint8_t  data[SNIFF_SNAPLEN];
};

struct SniffStats {
    uint32_t captured = 0;
    uint32_t sent     = 0;
    uint32_t dropped  = 0;
};

class Sniffer {
public:
    void begin(BridgeProtocol& proto);
    static Sniffer* instance() { return _instance; }

    bool startFixed(uint8_t channel);
    bool startHop(uint16_t intervalMs);
    void stop();
    bool setChannel(uint8_t channel);

    void setEapolFilter(bool enable, const uint8_t bssid[6] = nullptr);

    void processQueue();
    void handleHop();
    void onAck(uint32_t chunkIndex);

    bool       active()  const { return _active; }
    uint8_t    channel() const { return _channel; }
    bool       hopping() const { return _hopMode; }
    SniffStats stats()   const { return _stats; }

private:
    BridgeProtocol* _proto = nullptr;
    QueueHandle_t   _queue = nullptr;

    bool     _active       = false;
    bool     _hopMode      = false;
    uint8_t  _channel      = 1;
    uint16_t _hopIntervalMs = 300;
    uint32_t _lastHopMs    = 0;

    volatile int _inFlight = 0;
    uint8_t      _chunkCtr = 0;

    bool    _eapolOnly      = false;
    bool    _beaconCaptured = false;
    bool    _hasTargetBssid = false;
    uint8_t _targetBssid[6] = {0};
    
    SniffStats _stats;

    static Sniffer* _instance;
    static void promiscuousCb(void* buf, wifi_promiscuous_pkt_type_t type);
    void   handlePacket(wifi_promiscuous_pkt_t* pkt);
    size_t buildRadiotap(uint8_t* out, uint8_t channel, int8_t rssi);
    bool   isEapolFrame(const wifi_promiscuous_pkt_t* pkt) const;
    bool   isBeaconFrame(const wifi_promiscuous_pkt_t* pkt) const;
    bool   isAssociationRequest(const wifi_promiscuous_pkt_t* pkt) const;
    bool   matchesTargetBssid(const wifi_promiscuous_pkt_t* pkt) const;
};