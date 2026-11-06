/**
 * @file test_lora_mac.c
 * @brief ESP-IDF Component Unit Tests for lora_mac framing parser/encoder.
 *
 * Authority: C Coding Standard v2, Issue #186, contracts/radio-mac/specification.md.
 */

#include <stdint.h>
#include <string.h>
#include "esp_err.h"
#include "lora_mac.h"
#include "unity.h"

TEST_CASE("lora_mac init returns ESP_OK", "[lora_mac]")
{
    TEST_ASSERT_EQUAL(ESP_OK, lora_mac_init());
}

TEST_CASE("lora_mac roundtrip encode parse all fields", "[lora_mac]")
{
    const lora_mac_header_t in_hdr = {
        .magic = LORA_MAC_MAGIC_BYTE,
        .version = LORA_MAC_PROTOCOL_VERSION_DRAFT,
        .msg_type = LORA_MAC_TYPE_DATA_TELEMETRY,
        .flags = (uint8_t)(LORA_MAC_FLAG_ACK_REQ | LORA_MAC_FLAG_IS_RETRY),
        .src_id = 0x0A,
        .dst_id = 0x00,
        .sched_ver = 0x02,
        .seq_num = 0x42,
        .payload_len = 16,
    };

    uint8_t wire_buf[16] = {0};
    size_t written = 0;

    esp_err_t err = lora_mac_header_encode(&in_hdr, wire_buf, sizeof(wire_buf), &written);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL(LORA_MAC_HEADER_LEN, written);

    lora_mac_header_t out_hdr;
    memset(&out_hdr, 0, sizeof(out_hdr));

    err = lora_mac_header_parse(wire_buf, written, &out_hdr);
    TEST_ASSERT_EQUAL(ESP_OK, err);

    TEST_ASSERT_EQUAL_HEX8(in_hdr.magic, out_hdr.magic);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.version, out_hdr.version);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.msg_type, out_hdr.msg_type);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.flags, out_hdr.flags);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.src_id, out_hdr.src_id);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.dst_id, out_hdr.dst_id);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.sched_ver, out_hdr.sched_ver);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.seq_num, out_hdr.seq_num);
    TEST_ASSERT_EQUAL_HEX8(in_hdr.payload_len, out_hdr.payload_len);
}

TEST_CASE("lora_mac roundtrip all message types", "[lora_mac]")
{
    static const lora_mac_msg_type_t types[] = {
        LORA_MAC_TYPE_BEACON,
        LORA_MAC_TYPE_SCHED_ANNOUNCE,
        LORA_MAC_TYPE_DATA_TELEMETRY,
        LORA_MAC_TYPE_PRIORITY_ALERT,
        LORA_MAC_TYPE_ACK_PACKET,
        LORA_MAC_TYPE_CMD_DOWNLINK,
        LORA_MAC_TYPE_JOIN_SLOT_REQ,
        LORA_MAC_TYPE_JOIN_SLOT_RSP,
    };

    for (size_t i = 0; i < sizeof(types) / sizeof(types[0]); i++) {
        lora_mac_header_t in_hdr = {
            .magic = LORA_MAC_MAGIC_BYTE,
            .version = LORA_MAC_PROTOCOL_VERSION_DRAFT,
            .msg_type = (uint8_t)types[i],
            .flags = 0,
            .src_id = 0x01,
            .dst_id = 0x02,
            .sched_ver = 0x01,
            .seq_num = (uint8_t)(i + 1),
            .payload_len = (uint8_t)(i * 4),
        };

        uint8_t wire_buf[LORA_MAC_HEADER_LEN] = {0};
        size_t written = 0;

        esp_err_t err = lora_mac_header_encode(&in_hdr, wire_buf, sizeof(wire_buf), &written);
        TEST_ASSERT_EQUAL(ESP_OK, err);
        TEST_ASSERT_EQUAL(LORA_MAC_HEADER_LEN, written);

        lora_mac_header_t out_hdr;
        memset(&out_hdr, 0, sizeof(out_hdr));

        err = lora_mac_header_parse(wire_buf, written, &out_hdr);
        TEST_ASSERT_EQUAL(ESP_OK, err);
        TEST_ASSERT_EQUAL_HEX8(types[i], out_hdr.msg_type);
        TEST_ASSERT_EQUAL_HEX8(in_hdr.payload_len, out_hdr.payload_len);
    }
}

TEST_CASE("lora_mac header parse negative tests", "[lora_mac]")
{
    uint8_t valid_wire[LORA_MAC_HEADER_LEN] = {
        LORA_MAC_MAGIC_BYTE,
        (uint8_t)((LORA_MAC_PROTOCOL_VERSION_DRAFT << 6) | LORA_MAC_TYPE_DATA_TELEMETRY),
        0x00, 0x01, 0x00, 0x01, 0x01, 10
    };
    lora_mac_header_t out_hdr;

    /* NULL pointers */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_header_parse(NULL, sizeof(valid_wire), &out_hdr));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_header_parse(valid_wire, sizeof(valid_wire), NULL));

    /* Short buffer */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(valid_wire, 7, &out_hdr));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(valid_wire, 0, &out_hdr));

    /* Magic mismatch */
    uint8_t bad_magic[LORA_MAC_HEADER_LEN];
    memcpy(bad_magic, valid_wire, sizeof(bad_magic));
    bad_magic[0] = 0x5AU;
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_magic, sizeof(bad_magic), &out_hdr));

    /* Unsupported version */
    uint8_t bad_version[LORA_MAC_HEADER_LEN];
    memcpy(bad_version, valid_wire, sizeof(bad_version));
    bad_version[1] = (uint8_t)((2U << 6) | LORA_MAC_TYPE_DATA_TELEMETRY);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_version, sizeof(bad_version), &out_hdr));

    /* Oversized payload length */
    uint8_t bad_len[LORA_MAC_HEADER_LEN];
    memcpy(bad_len, valid_wire, sizeof(bad_len));
    bad_len[7] = (uint8_t)(LORA_MAC_MAX_PAYLOAD_LEN + 1U);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(bad_len, sizeof(bad_len), &out_hdr));
}

TEST_CASE("lora_mac header encode negative tests", "[lora_mac]")
{
    const lora_mac_header_t valid_hdr = {
        .magic = LORA_MAC_MAGIC_BYTE,
        .version = LORA_MAC_PROTOCOL_VERSION_DRAFT,
        .msg_type = LORA_MAC_TYPE_DATA_TELEMETRY,
        .flags = 0,
        .src_id = 0x01,
        .dst_id = 0x00,
        .sched_ver = 0x01,
        .seq_num = 0x01,
        .payload_len = 10,
    };

    uint8_t wire_buf[16] = {0};
    size_t written = 0;

    /* NULL pointers */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_header_encode(NULL, wire_buf, sizeof(wire_buf), &written));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_header_encode(&valid_hdr, NULL, sizeof(wire_buf), &written));

    /* Destination buffer too small */
    TEST_ASSERT_EQUAL(ESP_ERR_NO_MEM, lora_mac_header_encode(&valid_hdr, wire_buf, 7, &written));
    TEST_ASSERT_EQUAL(ESP_ERR_NO_MEM, lora_mac_header_encode(&valid_hdr, wire_buf, 0, &written));

    /* Oversized payload length */
    lora_mac_header_t bad_hdr = valid_hdr;
    bad_hdr.payload_len = (uint8_t)(LORA_MAC_MAX_PAYLOAD_LEN + 1U);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_header_encode(&bad_hdr, wire_buf, sizeof(wire_buf), &written));
}
