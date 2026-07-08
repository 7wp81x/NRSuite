#include "BridgeProtocol.h"

void BridgeProtocol::update() {
    while (true) {
        while (_stream.available()) {
            if (_bufLen < sizeof(_buf)) {
                _buf[_bufLen++] = _stream.read();
            } else {
                _resync();
                if (_bufLen >= sizeof(_buf)) {
                    memmove(_buf, _buf + 1, --_bufLen);
                }
            }
            while (_tryParse());
        }

        delay(1);
        if (!_stream.available()) break;
    }
}

bool BridgeProtocol::_tryParse() {
    if (_bufLen < PROTO_HEADER_SZ) return false;

    if (_buf[0] != PROTO_MAGIC_0 || _buf[1] != PROTO_MAGIC_1) {
        _resync();
        return false;
    }

    uint8_t  ptype = _buf[2];
    uint8_t  pid   = _buf[3];
    uint32_t len;
    memcpy(&len, _buf + 4, 4);  // little-endian

    if (len > PROTO_MAX_CHUNK) {
        _oversizedFrames++;
        _resync();
        return false;
    }

    uint32_t total = PROTO_HEADER_SZ + len;
    if (total > sizeof(_buf)) {
        _oversizedFrames++;
        _resync();
        return false;
    }

    if (_bufLen < total) {
        return false;
    }

    ProtoFrame f;
    f.type    = ptype;
    f.id      = pid;
    f.length  = len;
    f.payload = _buf + PROTO_HEADER_SZ;
    f.valid   = true;

    _dispatch(f);

    // Shift buffer
    memmove(_buf, _buf + total, _bufLen - total);
    _bufLen -= total;
    return true;
}

void BridgeProtocol::_resync() {
    if (_bufLen < 2) {
        _bufLen = 0;
        return;
    }
    for (uint32_t i = 1; i < _bufLen - 1; i++) {
        if (_buf[i] == PROTO_MAGIC_0 && _buf[i+1] == PROTO_MAGIC_1) {
            memmove(_buf, _buf + i, _bufLen - i);
            _bufLen -= i;
            return;
        }
    }
    _bufLen = 0;  // nothing found, discard everything
}

// ── _dispatch — route frame to correct callback ───────────────────────────────
void BridgeProtocol::_dispatch(ProtoFrame& f) {
    if (f.type == TYPE_CMD && _onCmd) {
        JsonDocument* doc = new JsonDocument();
        if (!doc) return;  // OOM
        
        DeserializationError err = deserializeJson(*doc, f.payload, f.length);
        if (!err) {
            _onCmd(f.id, *doc);
        }
        delete doc;
    }
    else if (f.type == TYPE_ACK && _onAck) {
        JsonDocument* doc = new JsonDocument();
        if (!doc) return;

        DeserializationError err = deserializeJson(*doc, f.payload, f.length);
        if (!err && (*doc)["chunk"].is<uint32_t>()) {
            _onAck((*doc)["chunk"].as<uint32_t>());
        }
        delete doc;
    }

    else if (f.type == TYPE_HTML) {
        if (_onHtml) {
            _onHtml(f.payload, f.length);
        }
    }
}

// ── sendResp ──────────────────────────────────────────────────────────────────
void BridgeProtocol::sendResp(uint8_t id, bool ok, const char* msg) {
    JsonDocument doc;
    doc["ok"] = ok;
    if (msg) doc["msg"] = msg;
    String json;
    serializeJson(doc, json);
    sendRaw(TYPE_RESP, id, (const uint8_t*)json.c_str(), json.length());
}

// ── sendEvent ─────────────────────────────────────────────────────────────────
void BridgeProtocol::sendEvent(const char* type, JsonDocument& doc) {
    doc["type"] = type;
    String json;
    serializeJson(doc, json);
    sendRaw(TYPE_EVENT, 0, (const uint8_t*)json.c_str(), json.length());
}

// ── sendPcapChunk ─────────────────────────────────────────────────────────────
void BridgeProtocol::sendPcapChunk(uint8_t chunk_idx, const uint8_t* data, uint32_t len) {
    sendRaw(TYPE_PCAP, chunk_idx, data, len);
}

// ── sendRaw — write a complete frame to the stream ───────────────────────────
void BridgeProtocol::sendRaw(uint8_t type, uint8_t id, const uint8_t* payload, uint32_t len) {
    uint8_t header[PROTO_HEADER_SZ];
    header[0] = PROTO_MAGIC_0;
    header[1] = PROTO_MAGIC_1;
    header[2] = type;
    header[3] = id;
    memcpy(header + 4, &len, 4);  // little-endian
    _stream.write(header, PROTO_HEADER_SZ);
    if (len > 0 && payload) {
        _stream.write(payload, len);
    }
}