#pragma once
#include <Arduino.h>
#include "BridgeProtocol.h"

// Tunables
#define BEACON_MAX_SSIDS       32
#define BEACON_SSID_MAX_LEN    32
#define BEACON_DEFAULT_INTERVAL_MS  20
#define BEACON_FRAME_MAX       128

struct BeaconStats {
    uint32_t sent     = 0;
    uint32_t ssids    = 0;
    uint8_t  channel  = 1;
};

class BeaconSpammer {
public:
    void begin(BridgeProtocol& proto);

    // ssids: newline- or comma-separated list (empty entries skipped)
    // channel: 1-13
    // intervalMs: delay between consecutive beacon transmissions
    // randomizeBssid: if true, each SSID gets a unique random BSSID
    // hidden: if true, SSID length field is 0 (hidden networks)
    bool start(const String& ssids, uint8_t channel, uint16_t intervalMs,
               bool randomizeBssid = true, bool hidden = false);
    void stop();
    void update();   // call from loop() — transmits next beacon if due

    bool        active()  const { return _active; }
    BeaconStats stats()   const { return _stats; }

private:
    BridgeProtocol* _proto = nullptr;
    bool     _active       = false;
    bool     _hidden       = false;
    bool     _randomBssid  = true;
    uint8_t  _channel      = 1;
    uint16_t _intervalMs   = BEACON_DEFAULT_INTERVAL_MS;
    uint32_t _lastTxMs     = 0;
    int      _nextIdx      = 0;

    char     _ssids[BEACON_MAX_SSIDS][BEACON_SSID_MAX_LEN + 1];
    uint8_t  _bssids[BEACON_MAX_SSIDS][6];
    int      _ssidCount    = 0;

    BeaconStats _stats;

    void _parseSsids(const String& raw);
    void _randomMac(uint8_t out[6]);
    size_t _buildFrame(uint8_t* out, int idx);
    void _transmit(int idx);
};
