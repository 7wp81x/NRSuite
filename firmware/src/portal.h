// portal.h
#pragma once
#include <Arduino.h>
#include <ESPAsyncWebServer.h>
#include <DNSServer.h>
#include "BridgeProtocol.h"
#include "sniffer.h"

class PortalManager {
public:
    void begin(BridgeProtocol& proto);
    bool start(const char* ssid, uint8_t channel, const uint8_t* targetBssid = nullptr);
    void stop();
    void setHtmlChunk(const uint8_t* data, size_t len, bool isLast = false);
    bool isRunning() const { return _running; }
    void update();   // call in loop()

    bool isComplete() const { return _htmlComplete; }
    size_t getBufferSize() const { return _htmlLen; }
    bool resetHtml(size_t expectedSize = 0);


private:
    AsyncWebServer* _server = nullptr;
    DNSServer* _dnsServer = nullptr;
    BridgeProtocol* _proto = nullptr;
    bool _running = false;
    uint8_t* _htmlBuffer = nullptr;
    uint8_t _targetBssid[6] = {0};
    bool _hasTarget = false;
    bool _htmlComplete = false;
    size_t   _htmlLen    = 0;
    size_t   _htmlCap    = 0;
    TaskHandle_t _deauthTaskHandle = nullptr;
    static String _servedSnapshot;
    static void deauthTaskFn(void* pvParameters);

    void setupDNSSpoof();
    void setupRoutes();
    String loadingPlaceholder() const;
    String noticePage() const;

};

extern PortalManager portal;