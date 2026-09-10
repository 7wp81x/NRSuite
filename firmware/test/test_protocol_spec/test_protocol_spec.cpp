#include <unity.h>

#include "ProtocolSpec.h"

void setUp(void) {}
void tearDown(void) {}

void test_protocol_constants(void) {
    TEST_ASSERT_EQUAL_HEX8(0xAD, PROTO_MAGIC_0);
    TEST_ASSERT_EQUAL_HEX8(0xDE, PROTO_MAGIC_1);
    TEST_ASSERT_EQUAL_INT(8, PROTO_HEADER_SZ);
    TEST_ASSERT_EQUAL_INT(1024, PROTO_MAX_CHUNK);

    TEST_ASSERT_EQUAL_HEX8(0x01, TYPE_CMD);
    TEST_ASSERT_EQUAL_HEX8(0x02, TYPE_RESP);
    TEST_ASSERT_EQUAL_HEX8(0x03, TYPE_EVENT);
    TEST_ASSERT_EQUAL_HEX8(0x04, TYPE_PCAP);
    TEST_ASSERT_EQUAL_HEX8(0x05, TYPE_ACK);
    TEST_ASSERT_EQUAL_HEX8(0x06, TYPE_HTML);
}

void test_proto_decode_valid_header(void) {
    const uint8_t frame[PROTO_HEADER_SZ] = {
        PROTO_MAGIC_0, PROTO_MAGIC_1, TYPE_CMD, 0x2A, 0x00, 0x00, 0x00, 0x00
    };
    uint8_t type = 0;
    uint8_t id = 0;
    uint32_t len = 0;

    TEST_ASSERT_TRUE(protoDecodeHeader(frame, sizeof(frame), type, id, len));
    TEST_ASSERT_EQUAL_HEX8(TYPE_CMD, type);
    TEST_ASSERT_EQUAL_HEX8(0x2A, id);
    TEST_ASSERT_EQUAL_UINT32(0, len);
}

void test_proto_decode_little_endian_length(void) {
    const uint8_t frame[PROTO_HEADER_SZ] = {
        PROTO_MAGIC_0, PROTO_MAGIC_1, TYPE_PCAP, 0x01,
        0x01, 0x02, 0x03, 0x04
    };
    uint8_t type = 0;
    uint8_t id = 0;
    uint32_t len = 0;

    TEST_ASSERT_TRUE(protoDecodeHeader(frame, sizeof(frame), type, id, len));
    TEST_ASSERT_EQUAL_UINT32(0x04030201UL, len);
}

void test_proto_decode_rejects_short_buffer(void) {
    const uint8_t frame[PROTO_HEADER_SZ - 1] = {
        PROTO_MAGIC_0, PROTO_MAGIC_1, TYPE_CMD, 0x01, 0x00, 0x00, 0x00
    };
    uint8_t type = 0;
    uint8_t id = 0;
    uint32_t len = 0;

    TEST_ASSERT_FALSE(protoDecodeHeader(frame, sizeof(frame), type, id, len));
}

void test_proto_decode_rejects_bad_magic(void) {
    const uint8_t frame[PROTO_HEADER_SZ] = {
        0x00, 0x00, TYPE_CMD, 0x01, 0x00, 0x00, 0x00, 0x00
    };
    uint8_t type = 0;
    uint8_t id = 0;
    uint32_t len = 0;

    TEST_ASSERT_FALSE(protoDecodeHeader(frame, sizeof(frame), type, id, len));
}

void test_proto_decode_rejects_null_buffer(void) {
    uint8_t type = 0;
    uint8_t id = 0;
    uint32_t len = 0;

    TEST_ASSERT_FALSE(protoDecodeHeader(nullptr, PROTO_HEADER_SZ, type, id, len));
}

int main(int argc, char** argv) {
    UNITY_BEGIN();
    RUN_TEST(test_protocol_constants);
    RUN_TEST(test_proto_decode_valid_header);
    RUN_TEST(test_proto_decode_little_endian_length);
    RUN_TEST(test_proto_decode_rejects_short_buffer);
    RUN_TEST(test_proto_decode_rejects_bad_magic);
    RUN_TEST(test_proto_decode_rejects_null_buffer);
    return UNITY_END();
}
