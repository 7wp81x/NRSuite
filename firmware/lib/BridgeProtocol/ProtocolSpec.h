#pragma once

#include <stddef.h>
#include <stdint.h>

// ── Frame constants (shared by firmware and native host tests) ────────────────
#define PROTO_MAGIC_0   0xAD
#define PROTO_MAGIC_1   0xDE
#define PROTO_HEADER_SZ 8       // 2 magic + 1 type + 1 id + 4 length
#define PROTO_MAX_CHUNK 1024

#define TYPE_CMD    0x01
#define TYPE_RESP   0x02
#define TYPE_EVENT  0x03
#define TYPE_PCAP   0x04
#define TYPE_ACK    0x05
#define TYPE_HTML   0x06

// Decode and validate a protocol header without touching project hardware
// dependencies. The 32-bit payload length is little-endian.
static inline bool protoDecodeHeader(const uint8_t* buf, size_t len,
                                     uint8_t& type, uint8_t& id,
                                     uint32_t& payloadLen) {
    if (buf == nullptr || len < PROTO_HEADER_SZ) return false;
    if (buf[0] != PROTO_MAGIC_0 || buf[1] != PROTO_MAGIC_1) return false;

    type = buf[2];
    id   = buf[3];
    payloadLen = (uint32_t)buf[4]
               | ((uint32_t)buf[5] << 8)
               | ((uint32_t)buf[6] << 16)
               | ((uint32_t)buf[7] << 24);
    return true;
}
