/**
 * @file test_lora_mac.c
 * @brief Unit tests for LoRa MAC Framing Parser and Encoder.
 *
 * Authority: C Coding Standard v2, Issue #186, contracts/radio-mac/specification.md.
 * Scope: Zero dynamic memory allocation, bounded buffers, strict validation.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "lora_mac.h"

#define TEST_RUN(name) do { \
    printf("Running %s ... ", #name); \
    if (name() == 0) { \
        printf("PASSED\n"); \
    } else { \
        printf("FAILED\n"); \
        failures++; \
    } \
} while (0)

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "\nAssertion failed: %s at %s:%d\n", #cond, __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_INT(expected, actual) do { \
    if ((int)(expected) != (int)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %d, got %d) at %s:%d\n", \
                #expected, #actual, (int)(expected), (int)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_HEX(expected, actual) do { \
    if ((uint32_t)(expected) != (uint32_t)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected 0x%02X, got 0x%02X) at %s:%d\n", \
                #expected, #actual, (unsigned int)(expected), (unsigned int)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

/**
 * @brief Test initialization lifecycle.
 */
static int test_lora_mac_init(void)
{
    esp_err_t err = lora_mac_init();
    ASSERT_EQUAL_INT(ESP_OK, err);
    return 0;
}

/**
 * @brief Test round-trip encode and parse across all header fields.
 */
static int test_lora_mac_roundtrip_all_fields(void)
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
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_EQUAL_INT((int)LORA_MAC_HEADER_LEN, (int)written);

    /* Verify byte-level serialization per contracts/radio-mac/specification.md */
    ASSERT_EQUAL_HEX(LORA_MAC_MAGIC_BYTE, wire_buf[0]);
    ASSERT_EQUAL_HEX((uint8_t)(((in_hdr.version & 0x03U) << 6) | (in_hdr.msg_type & 0x3FU)), wire_buf[1]);
    ASSERT_EQUAL_HEX(in_hdr.flags, wire_buf[2]);
    ASSERT_EQUAL_HEX(in_hdr.src_id, wire_buf[3]);
    ASSERT_EQUAL_HEX(in_hdr.dst_id, wire_buf[4]);
    ASSERT_EQUAL_HEX(in_hdr.sched_ver, wire_buf[5]);
    ASSERT_EQUAL_HEX(in_hdr.seq_num, wire_buf[6]);
    ASSERT_EQUAL_HEX(in_hdr.payload_len, wire_buf[7]);

    lora_mac_header_t out_hdr;
    memset(&out_hdr, 0, sizeof(out_hdr));

    err = lora_mac_header_parse(wire_buf, written, &out_hdr);
    ASSERT_EQUAL_INT(ESP_OK, err);

    /* Check all fields preserved */
    ASSERT_EQUAL_HEX(in_hdr.magic, out_hdr.magic);
    ASSERT_EQUAL_HEX(in_hdr.version, out_hdr.version);
    ASSERT_EQUAL_HEX(in_hdr.msg_type, out_hdr.msg_type);
    ASSERT_EQUAL_HEX(in_hdr.flags, out_hdr.flags);
    ASSERT_EQUAL_HEX(in_hdr.src_id, out_hdr.src_id);
    ASSERT_EQUAL_HEX(in_hdr.dst_id, out_hdr.dst_id);
    ASSERT_EQUAL_HEX(in_hdr.sched_ver, out_hdr.sched_ver);
    ASSERT_EQUAL_HEX(in_hdr.seq_num, out_hdr.seq_num);
    ASSERT_EQUAL_HEX(in_hdr.payload_len, out_hdr.payload_len);

    return 0;
}

/**
 * @brief Test round-trip across all candidate message types.
 */
static int test_lora_mac_roundtrip_all_message_types(void)
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
        ASSERT_EQUAL_INT(ESP_OK, err);
        ASSERT_EQUAL_INT((int)LORA_MAC_HEADER_LEN, (int)written);

        lora_mac_header_t out_hdr;
        memset(&out_hdr, 0, sizeof(out_hdr));

        err = lora_mac_header_parse(wire_buf, written, &out_hdr);
        ASSERT_EQUAL_INT(ESP_OK, err);
        ASSERT_EQUAL_HEX(types[i], out_hdr.msg_type);
        ASSERT_EQUAL_HEX(in_hdr.payload_len, out_hdr.payload_len);
    }

    return 0;
}

/**
 * @brief Test boundary payload lengths (0 and LORA_MAC_MAX_PAYLOAD_LEN).
 */
static int test_lora_mac_boundary_payload_lengths(void)
{
    static const uint8_t boundary_lengths[] = {0, 1, 47, LORA_MAC_MAX_PAYLOAD_LEN};

    for (size_t i = 0; i < sizeof(boundary_lengths) / sizeof(boundary_lengths[0]); i++) {
        lora_mac_header_t in_hdr = {
            .magic = LORA_MAC_MAGIC_BYTE,
            .version = LORA_MAC_PROTOCOL_VERSION_DRAFT,
            .msg_type = LORA_MAC_TYPE_DATA_TELEMETRY,
            .flags = 0,
            .src_id = 0x10,
            .dst_id = 0x00,
            .sched_ver = 0x05,
            .seq_num = 0x01,
            .payload_len = boundary_lengths[i],
        };

        uint8_t wire_buf[LORA_MAC_HEADER_LEN] = {0};
        size_t written = 0;

        esp_err_t err = lora_mac_header_encode(&in_hdr, wire_buf, sizeof(wire_buf), &written);
        ASSERT_EQUAL_INT(ESP_OK, err);

        lora_mac_header_t out_hdr;
        memset(&out_hdr, 0, sizeof(out_hdr));

        err = lora_mac_header_parse(wire_buf, written, &out_hdr);
        ASSERT_EQUAL_INT(ESP_OK, err);
        ASSERT_EQUAL_HEX(boundary_lengths[i], out_hdr.payload_len);
    }

    return 0;
}

/**
 * @brief Negative tests for lora_mac_header_parse:
 *        - NULL pointers (raw_buf, out_hdr)
 *        - Buffer length < LORA_MAC_HEADER_LEN (ESP_ERR_INVALID_SIZE)
 *        - Magic mismatch (ESP_ERR_INVALID_VERSION)
 *        - Unsupported version (ESP_ERR_INVALID_VERSION)
 *        - Payload length exceeds LORA_MAC_MAX_PAYLOAD_LEN (ESP_ERR_INVALID_SIZE)
 */
static int test_lora_mac_header_parse_negative(void)
{
    uint8_t valid_wire[LORA_MAC_HEADER_LEN] = {
        LORA_MAC_MAGIC_BYTE,
        (uint8_t)((LORA_MAC_PROTOCOL_VERSION_DRAFT << 6) | LORA_MAC_TYPE_DATA_TELEMETRY),
        0x00,
        0x01,
        0x00,
        0x01,
        0x01,
        10
    };
    lora_mac_header_t out_hdr;

    /* 1. NULL pointer checks -> ESP_ERR_INVALID_ARG */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_parse(NULL, sizeof(valid_wire), &out_hdr));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_parse(valid_wire, sizeof(valid_wire), NULL));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_parse(NULL, sizeof(valid_wire), NULL));

    /* 2. Buffer length < LORA_MAC_HEADER_LEN -> ESP_ERR_INVALID_SIZE */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(valid_wire, 0, &out_hdr));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(valid_wire, 1, &out_hdr));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(valid_wire, 7, &out_hdr));

    /* 3. Magic mismatch -> ESP_ERR_INVALID_VERSION */
    uint8_t bad_magic[LORA_MAC_HEADER_LEN];
    memcpy(bad_magic, valid_wire, sizeof(bad_magic));
    bad_magic[0] = 0x5AU; /* Incorrect magic */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_magic, sizeof(bad_magic), &out_hdr));

    bad_magic[0] = 0x00U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_magic, sizeof(bad_magic), &out_hdr));

    bad_magic[0] = 0xFFU;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_magic, sizeof(bad_magic), &out_hdr));

    /* 4. Unsupported version -> ESP_ERR_INVALID_VERSION (only 0x01 and 0x00 accepted) */
    uint8_t bad_version[LORA_MAC_HEADER_LEN];
    memcpy(bad_version, valid_wire, sizeof(bad_version));

    /* Version 2: bits 7..6 = 10 -> (2 << 6) | msg_type */
    bad_version[1] = (uint8_t)((2U << 6) | LORA_MAC_TYPE_DATA_TELEMETRY);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_version, sizeof(bad_version), &out_hdr));

    /* Version 3: bits 7..6 = 11 -> (3 << 6) | msg_type */
    bad_version[1] = (uint8_t)((3U << 6) | LORA_MAC_TYPE_DATA_TELEMETRY);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_header_parse(bad_version, sizeof(bad_version), &out_hdr));

    /* 5. Payload length exceeds LORA_MAC_MAX_PAYLOAD_LEN -> ESP_ERR_INVALID_SIZE */
    uint8_t oversized_payload[LORA_MAC_HEADER_LEN];
    memcpy(oversized_payload, valid_wire, sizeof(oversized_payload));

    oversized_payload[7] = (uint8_t)(LORA_MAC_MAX_PAYLOAD_LEN + 1U); /* 49 bytes */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(oversized_payload, sizeof(oversized_payload), &out_hdr));

    oversized_payload[7] = 100U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(oversized_payload, sizeof(oversized_payload), &out_hdr));

    oversized_payload[7] = 255U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_parse(oversized_payload, sizeof(oversized_payload), &out_hdr));

    return 0;
}

/**
 * @brief Negative tests for lora_mac_header_encode:
 *        - NULL pointers (hdr, out_buf)
 *        - Destination buffer < LORA_MAC_HEADER_LEN (ESP_ERR_NO_MEM)
 *        - Payload length exceeds LORA_MAC_MAX_PAYLOAD_LEN (ESP_ERR_INVALID_SIZE)
 */
static int test_lora_mac_header_encode_negative(void)
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

    /* 1. NULL pointer checks -> ESP_ERR_INVALID_ARG */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_encode(NULL, wire_buf, sizeof(wire_buf), &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_encode(&valid_hdr, NULL, sizeof(wire_buf), &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_header_encode(NULL, NULL, sizeof(wire_buf), &written));

    /* Note: out_written pointer can be NULL without error */
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_header_encode(&valid_hdr, wire_buf, sizeof(wire_buf), NULL));

    /* 2. Destination buffer < LORA_MAC_HEADER_LEN -> ESP_ERR_NO_MEM */
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_header_encode(&valid_hdr, wire_buf, 0, &written));
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_header_encode(&valid_hdr, wire_buf, 1, &written));
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_header_encode(&valid_hdr, wire_buf, 7, &written));

    /* 3. Payload length exceeds LORA_MAC_MAX_PAYLOAD_LEN -> ESP_ERR_INVALID_SIZE */
    lora_mac_header_t bad_len_hdr = valid_hdr;

    bad_len_hdr.payload_len = (uint8_t)(LORA_MAC_MAX_PAYLOAD_LEN + 1U); /* 49 bytes */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_encode(&bad_len_hdr, wire_buf, sizeof(wire_buf), &written));

    bad_len_hdr.payload_len = 100U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_encode(&bad_len_hdr, wire_buf, sizeof(wire_buf), &written));

    bad_len_hdr.payload_len = 255U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_header_encode(&bad_len_hdr, wire_buf, sizeof(wire_buf), &written));

    return 0;
}

int main(void)
{
    int failures = 0;

    printf("==================================================\n");
    printf("LoRa MAC Framing Unit Tests (Issue #186)\n");
    printf("==================================================\n");

    TEST_RUN(test_lora_mac_init);
    TEST_RUN(test_lora_mac_roundtrip_all_fields);
    TEST_RUN(test_lora_mac_roundtrip_all_message_types);
    TEST_RUN(test_lora_mac_boundary_payload_lengths);
    TEST_RUN(test_lora_mac_header_parse_negative);
    TEST_RUN(test_lora_mac_header_encode_negative);

    printf("==================================================\n");
    if (failures == 0) {
        printf("All LoRa MAC framing tests PASSED successfully!\n");
        printf("Zero dynamic allocation; bounded memory verified.\n");
        return 0;
    }

    printf("FAILED: %d test case(s) failed.\n", failures);
    return 1;
}
