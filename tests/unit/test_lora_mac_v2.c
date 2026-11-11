/**
 * @file test_lora_mac_v2.c
 * @brief Unit tests for V2 LoRa MAC Framing, Codecs, and Nonce Construction.
 *
 * Authority: C Coding Standard v2, Issue #131, Issue #127, contracts/radio-mac/specification.md.
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

#define ASSERT_EQUAL_U32(expected, actual) do { \
    if ((uint32_t)(expected) != (uint32_t)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %u, got %u) at %s:%d\n", \
                #expected, #actual, (uint32_t)(expected), (uint32_t)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

static int test_lora_mac_v2_header_roundtrip(void)
{
    lora_mac_v2_header_t in_hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = 42U,
        .session_sel = 1U,
        .frame_counter = 0x01020304U,
    };
    uint8_t wire[LORA_MAC_V2_HEADER_LEN];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_header_encode(&in_hdr, wire, sizeof(wire), &written));
    ASSERT_EQUAL_INT(LORA_MAC_V2_HEADER_LEN, written);
    ASSERT_EQUAL_INT(0x41, wire[0]);
    ASSERT_EQUAL_INT(42, wire[1]);
    ASSERT_EQUAL_INT(1, wire[2]);
    ASSERT_EQUAL_INT(0x01, wire[3]);
    ASSERT_EQUAL_INT(0x02, wire[4]);
    ASSERT_EQUAL_INT(0x03, wire[5]);
    ASSERT_EQUAL_INT(0x04, wire[6]);

    lora_mac_v2_header_t out_hdr;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_header_parse(wire, sizeof(wire), &out_hdr));
    ASSERT_EQUAL_INT(in_hdr.ver_type, out_hdr.ver_type);
    ASSERT_EQUAL_INT(in_hdr.node_id, out_hdr.node_id);
    ASSERT_EQUAL_INT(in_hdr.session_sel, out_hdr.session_sel);
    ASSERT_EQUAL_U32(in_hdr.frame_counter, out_hdr.frame_counter);

    return 0;
}

static int test_lora_mac_v2_header_negative(void)
{
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = 1U,
        .session_sel = 0U,
        .frame_counter = 100U,
    };
    uint8_t wire[10];
    size_t written = 0;

    /* NULL check */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_header_encode(NULL, wire, sizeof(wire), &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_header_encode(&hdr, NULL, sizeof(wire), &written));

    /* Buffer too small */
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_v2_header_encode(&hdr, wire, 6, &written));

    /* Invalid version in ver_type */
    hdr.ver_type = 0x20U; /* version 1 */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_header_encode(&hdr, wire, sizeof(wire), &written));

    /* Parse NULL check */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_header_parse(NULL, 7, &hdr));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_header_parse(wire, 7, NULL));

    /* Parse buffer too small */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_header_parse(wire, 6, &hdr));

    /* Parse invalid version */
    wire[0] = 0x21U; /* version 1 */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_VERSION, lora_mac_v2_header_parse(wire, 7, &hdr));

    return 0;
}

static int test_lora_mac_v2_build_nonce(void)
{
    const uint8_t prefix[8] = { 0xAA, 0xBB, 0xCC, 0xDD, 0x11, 0x22, 0x33, 0x44 };
    uint8_t nonce[LORA_MAC_V2_CCM_NONCE_LEN];

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_build_nonce(prefix, LORA_MAC_V2_DIR_UPLINK, 0x0A0B0C0DU, nonce));
    ASSERT_EQUAL_INT(0, memcmp(nonce, prefix, 8));
    ASSERT_EQUAL_INT(LORA_MAC_V2_DIR_UPLINK, nonce[8]);
    ASSERT_EQUAL_INT(0x0A, nonce[9]);
    ASSERT_EQUAL_INT(0x0B, nonce[10]);
    ASSERT_EQUAL_INT(0x0C, nonce[11]);
    ASSERT_EQUAL_INT(0x0D, nonce[12]);

    /* Test downlink direction */
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_build_nonce(prefix, LORA_MAC_V2_DIR_DOWNLINK, 1U, nonce));
    ASSERT_EQUAL_INT(LORA_MAC_V2_DIR_DOWNLINK, nonce[8]);

    /* Test invalid direction */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_build_nonce(prefix, 0x00, 1U, nonce));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_build_nonce(prefix, 0x03, 1U, nonce));

    /* Test NULL pointers */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_build_nonce(NULL, LORA_MAC_V2_DIR_UPLINK, 1U, nonce));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_build_nonce(prefix, LORA_MAC_V2_DIR_UPLINK, 1U, NULL));

    return 0;
}

static int test_lora_mac_v2_up_event_roundtrip(void)
{
    lora_mac_v2_up_event_t ev_in = {
        .event_ref = 0x12345678U,
        .event_time = 1715000000U,
        .event_code = 0x05U,
        .event_value = -1250,
    };
    uint8_t buf[16];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_event_serialize(&ev_in, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(11, written);

    lora_mac_v2_up_event_t ev_out;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_event_deserialize(buf, written, &ev_out));
    ASSERT_EQUAL_U32(ev_in.event_ref, ev_out.event_ref);
    ASSERT_EQUAL_U32(ev_in.event_time, ev_out.event_time);
    ASSERT_EQUAL_INT(ev_in.event_code, ev_out.event_code);
    ASSERT_EQUAL_INT(ev_in.event_value, ev_out.event_value);

    /* Negative check: buffer too small */
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_v2_up_event_serialize(&ev_in, buf, 10, &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_up_event_deserialize(buf, 10, &ev_out));

    return 0;
}

static int test_lora_mac_v2_down_event_ack_roundtrip(void)
{
    lora_mac_v2_down_event_ack_t ack_in = {
        .event_ref = 0xCAFEBABE,
    };
    uint8_t buf[8];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_event_ack_serialize(&ack_in, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(4, written);

    lora_mac_v2_down_event_ack_t ack_out;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_event_ack_deserialize(buf, written, &ack_out));
    ASSERT_EQUAL_U32(ack_in.event_ref, ack_out.event_ref);

    /* Negative check: buffer too small */
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_v2_down_event_ack_serialize(&ack_in, buf, 3, &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_event_ack_deserialize(buf, 3, &ack_out));

    return 0;
}

static int test_lora_mac_v2_up_health_reply_roundtrip(void)
{
    lora_mac_v2_up_health_reply_t hr_in = {
        .battery_mv = 3280U,
        .uptime_sec = 86400U,
        .pending_count = 3U,
    };
    uint8_t buf[10];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_health_reply_serialize(&hr_in, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(6, written);

    lora_mac_v2_up_health_reply_t hr_out;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_health_reply_deserialize(buf, written, &hr_out));
    ASSERT_EQUAL_INT(hr_in.battery_mv, hr_out.battery_mv);
    ASSERT_EQUAL_U32(hr_in.uptime_sec, hr_out.uptime_sec);
    ASSERT_EQUAL_INT(hr_in.pending_count, hr_out.pending_count);

    return 0;
}

static int test_lora_mac_v2_up_diag_metrics_roundtrip(void)
{
    lora_mac_v2_up_diag_metrics_t diag_in = {
        .dropped_event_count = 17U,
        .diag_seq = 42U,
    };
    uint8_t buf[12];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_diag_metrics_serialize(&diag_in, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(8, written);

    lora_mac_v2_up_diag_metrics_t diag_out;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_diag_metrics_deserialize(buf, written, &diag_out));
    ASSERT_EQUAL_U32(diag_in.dropped_event_count, diag_out.dropped_event_count);
    ASSERT_EQUAL_U32(diag_in.diag_seq, diag_out.diag_seq);

    return 0;
}

static int test_lora_mac_v2_beacon_roundtrip(void)
{
    lora_mac_v2_beacon_t bcn_in = {
        .magic = LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON,
        .gw_id = 0x01,
        .epoch_sec = 1715001234U,
        .sf_seq = 500U,
        .sched_ver = 2U,
        .flags = 0x00,
        .key_id = 0x01,
        .reserved = {0, 0, 0},
    };
    for (int i = 0; i < 16; i++) {
        bcn_in.hmac_tag[i] = (uint8_t)(i + 1);
    }

    uint8_t buf[36];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_beacon_serialize(&bcn_in, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(32, written);

    lora_mac_v2_beacon_t bcn_out;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_beacon_deserialize(buf, written, &bcn_out));
    ASSERT_EQUAL_INT(bcn_in.magic, bcn_out.magic);
    ASSERT_EQUAL_INT(bcn_in.gw_id, bcn_out.gw_id);
    ASSERT_EQUAL_U32(bcn_in.epoch_sec, bcn_out.epoch_sec);
    ASSERT_EQUAL_U32(bcn_in.sf_seq, bcn_out.sf_seq);
    ASSERT_EQUAL_INT(bcn_in.sched_ver, bcn_out.sched_ver);
    ASSERT_EQUAL_INT(bcn_in.flags, bcn_out.flags);
    ASSERT_EQUAL_INT(bcn_in.key_id, bcn_out.key_id);
    ASSERT_EQUAL_INT(0, memcmp(bcn_in.hmac_tag, bcn_out.hmac_tag, 16));

    return 0;
}

static int test_lora_mac_v2_down_revoke_roundtrip(void)
{
    lora_mac_v2_down_revoke_t in_rev = {
        .revoke_reason = 0xDEADBEEFU,
    };
    uint8_t buf[10];
    size_t written = 0;

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_revoke_serialize(&in_rev, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(4, written);
    ASSERT_EQUAL_INT(0xDE, buf[0]);
    ASSERT_EQUAL_INT(0xAD, buf[1]);
    ASSERT_EQUAL_INT(0xBE, buf[2]);
    ASSERT_EQUAL_INT(0xEF, buf[3]);

    lora_mac_v2_down_revoke_t out_rev;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_revoke_deserialize(buf, written, &out_rev));
    ASSERT_EQUAL_U32(in_rev.revoke_reason, out_rev.revoke_reason);

    return 0;
}

static int test_lora_mac_v2_down_revoke_negative(void)
{
    lora_mac_v2_down_revoke_t rev = { .revoke_reason = 1U };
    uint8_t buf[4];
    size_t written = 0;

    /* NULL checks */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_down_revoke_serialize(NULL, buf, sizeof(buf), &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_down_revoke_serialize(&rev, NULL, sizeof(buf), &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_down_revoke_deserialize(NULL, sizeof(buf), &rev));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, lora_mac_v2_down_revoke_deserialize(buf, sizeof(buf), NULL));

    /* Buffer too small */
    ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_v2_down_revoke_serialize(&rev, buf, 3, &written));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_revoke_deserialize(buf, 3, &rev));

    return 0;
}

int main(void)
{
    int failures = 0;
    printf("--- LoRa MAC V2 Framing & Codec Unit Tests ---\n");

    TEST_RUN(test_lora_mac_v2_header_roundtrip);
    TEST_RUN(test_lora_mac_v2_header_negative);
    TEST_RUN(test_lora_mac_v2_build_nonce);
    TEST_RUN(test_lora_mac_v2_up_event_roundtrip);
    TEST_RUN(test_lora_mac_v2_down_event_ack_roundtrip);
    TEST_RUN(test_lora_mac_v2_down_revoke_roundtrip);
    TEST_RUN(test_lora_mac_v2_down_revoke_negative);
    TEST_RUN(test_lora_mac_v2_up_health_reply_roundtrip);
    TEST_RUN(test_lora_mac_v2_up_diag_metrics_roundtrip);
    TEST_RUN(test_lora_mac_v2_beacon_roundtrip);

    if (failures == 0) {
        printf("All LoRa MAC V2 unit tests PASSED successfully!\n");
        return 0;
    }

    fprintf(stderr, "%d test(s) FAILED.\n", failures);
    return 1;
}

