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
#include "lora_mac_crypto.h"
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

TEST_CASE("lora_mac crypto init returns ESP_OK", "[lora_mac][crypto]")
{
    TEST_ASSERT_EQUAL(ESP_OK, lora_mac_crypto_init());
}

TEST_CASE("lora_mac AES-CCM-8 UP_EVENT encryption and decryption roundtrip", "[lora_mac][crypto]")
{
    const uint8_t key[16] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
                             0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10};
    const uint8_t nonce[13] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00, 0x11,
                               0x01, 0x00, 0x00, 0x00, 0x01};
    const uint8_t aad[7] = {0x41, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01};
    const uint8_t plaintext[11] = "EVENT_ALERT";
    uint8_t ciphertext[11] = {0};
    uint8_t tag[8] = {0};

    esp_err_t err = lora_mac_crypto_encrypt_up_event(key, nonce, aad, sizeof(aad),
                                                    plaintext, sizeof(plaintext),
                                                    ciphertext, tag);
    TEST_ASSERT_EQUAL(ESP_OK, err);

    uint8_t decrypted[11] = {0};
    err = lora_mac_crypto_decrypt_up_event(key, nonce, aad, sizeof(aad),
                                          ciphertext, sizeof(ciphertext),
                                          tag, decrypted);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_MEMORY(plaintext, decrypted, sizeof(plaintext));

    /* Corrupted tag check */
    tag[0] ^= 0x55U;
    err = lora_mac_crypto_decrypt_up_event(key, nonce, aad, sizeof(aad),
                                          ciphertext, sizeof(ciphertext),
                                          tag, decrypted);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_CRC, err);
    tag[0] ^= 0x55U; /* restore */

    /* Corrupted ciphertext check */
    ciphertext[0] ^= 0xAAU;
    err = lora_mac_crypto_decrypt_up_event(key, nonce, aad, sizeof(aad),
                                          ciphertext, sizeof(ciphertext),
                                          tag, decrypted);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_CRC, err);
}

TEST_CASE("lora_mac AES-CCM-8 DOWN_EVENT_ACK encryption and decryption roundtrip", "[lora_mac][crypto]")
{
    const uint8_t key[16] = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
                             0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30};
    const uint8_t nonce[13] = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80,
                               0x02, 0x00, 0x00, 0x00, 0x05};
    const uint8_t aad[7] = {0x42, 0x01, 0x00, 0x00, 0x00, 0x00, 0x05};
    const uint8_t plaintext[4] = {0x00, 0x00, 0x00, 0x2A}; /* event_ref = 42 */
    uint8_t ciphertext[4] = {0};
    uint8_t tag[8] = {0};

    esp_err_t err = lora_mac_crypto_encrypt_down_ack(key, nonce, aad, sizeof(aad),
                                                     plaintext, sizeof(plaintext),
                                                     ciphertext, tag);
    TEST_ASSERT_EQUAL(ESP_OK, err);

    uint8_t decrypted[4] = {0};
    err = lora_mac_crypto_decrypt_down_ack(key, nonce, aad, sizeof(aad),
                                           ciphertext, sizeof(ciphertext),
                                           tag, decrypted);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_MEMORY(plaintext, decrypted, sizeof(plaintext));

    /* Corrupted tag check */
    tag[7] ^= 0x01U;
    err = lora_mac_crypto_decrypt_down_ack(key, nonce, aad, sizeof(aad),
                                           ciphertext, sizeof(ciphertext),
                                           tag, decrypted);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_CRC, err);
}

TEST_CASE("lora_mac Beacon HMAC computation and verification", "[lora_mac][crypto]")
{
    const uint8_t k_beacon[32] = {
        0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
        0x99, 0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x00,
        0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10
    };
    const uint8_t header[16] = {
        0x43, 0x01, 0x00, 0x00, 0x00, 0x64, 0x00, 0x00,
        0x00, 0x01, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00
    };
    uint8_t tag[16] = {0};

    esp_err_t err = lora_mac_crypto_compute_beacon_hmac(k_beacon, header, sizeof(header), tag);
    TEST_ASSERT_EQUAL(ESP_OK, err);

    err = lora_mac_crypto_verify_beacon_hmac(k_beacon, header, sizeof(header), tag);
    TEST_ASSERT_EQUAL(ESP_OK, err);

    /* Tamper with tag */
    tag[0] ^= 0xFFU;
    err = lora_mac_crypto_verify_beacon_hmac(k_beacon, header, sizeof(header), tag);
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_CRC, err);
}

TEST_CASE("lora_mac crypto zeroize and negative bounds checks", "[lora_mac][crypto]")
{
    uint8_t sensitive[16] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
                             0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    lora_mac_crypto_zeroize(sensitive, sizeof(sensitive));
    for (size_t i = 0; i < sizeof(sensitive); i++) {
        TEST_ASSERT_EQUAL_HEX8(0x00, sensitive[i]);
    }

    uint8_t dummy[16] = {0};
    uint8_t tag[8] = {0};
    /* NULL pointer checks */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_encrypt_up_event(NULL, dummy, dummy, 7, dummy, 11, dummy, tag));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_decrypt_up_event(dummy, NULL, dummy, 7, dummy, 11, tag, dummy));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_compute_beacon_hmac(NULL, dummy, 16, dummy));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_verify_beacon_hmac(dummy, dummy, 0, tag));

    /* Bounds checking: oversized payloads and AADs */
    uint8_t oversized_buf[64] = {0};
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_ccm_encrypt(dummy, dummy, dummy, 7, oversized_buf, 49, dummy, tag));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_ccm_decrypt(dummy, dummy, dummy, 7, oversized_buf, 49, tag, dummy));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_crypto_ccm_encrypt(dummy, dummy, oversized_buf, 49, dummy, 4, dummy, tag));
}

TEST_CASE("lora_mac V2 DOWN_JOIN_WAIT wire size and codec roundtrip", "[lora_mac][join_v2]")
{
    /* 1. Verify standard wire size and struct size are exactly 20 bytes */
    TEST_ASSERT_EQUAL_UINT32(20, LORA_MAC_V2_LEN_DOWN_JOIN_WAIT);
    TEST_ASSERT_EQUAL_UINT32(20, sizeof(lora_mac_v2_down_join_wait_t));

    const lora_mac_v2_down_join_wait_t in_wait = {
        .ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT,
        .device_mac = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55},
        .gw_id = 0x07,
        .join_counter = 0xA1B2C3D4,
        .auth_tag = {0x10, 0x20, 0x30, 0x40, 0x50, 0x60, 0x70, 0x80},
    };

    uint8_t wire_buf[32] = {0};
    size_t written = 0;

    /* 2. Positive serialization */
    esp_err_t err = lora_mac_v2_down_join_wait_serialize(&in_wait, wire_buf, sizeof(wire_buf), &written);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_UINT32(20, written);

    /* Verify wire layout: offset 0 = ver_type */
    TEST_ASSERT_EQUAL_HEX8(0x51, wire_buf[0]);
    /* Offsets 1..6 = device_mac */
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_wait.device_mac, &wire_buf[1], 6);
    /* Offset 7 = gw_id */
    TEST_ASSERT_EQUAL_HEX8(0x07, wire_buf[7]);
    /* Offsets 8..11 = Big-Endian join_counter */
    TEST_ASSERT_EQUAL_HEX8(0xA1, wire_buf[8]);
    TEST_ASSERT_EQUAL_HEX8(0xB2, wire_buf[9]);
    TEST_ASSERT_EQUAL_HEX8(0xC3, wire_buf[10]);
    TEST_ASSERT_EQUAL_HEX8(0xD4, wire_buf[11]);
    /* Offsets 12..19 = auth_tag */
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_wait.auth_tag, &wire_buf[12], 8);

    /* 3. Positive deserialization */
    lora_mac_v2_down_join_wait_t out_wait;
    memset(&out_wait, 0, sizeof(out_wait));

    err = lora_mac_v2_down_join_wait_deserialize(wire_buf, written, &out_wait);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_HEX8(in_wait.ver_type, out_wait.ver_type);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_wait.device_mac, out_wait.device_mac, 6);
    TEST_ASSERT_EQUAL_HEX8(in_wait.gw_id, out_wait.gw_id);
    TEST_ASSERT_EQUAL_HEX32(in_wait.join_counter, out_wait.join_counter);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_wait.auth_tag, out_wait.auth_tag, 8);

    /* 4. Serialize with ver_type = 0 defaults to LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT (0x51) */
    lora_mac_v2_down_join_wait_t zero_ver = in_wait;
    zero_ver.ver_type = 0U;
    memset(wire_buf, 0, sizeof(wire_buf));
    err = lora_mac_v2_down_join_wait_serialize(&zero_ver, wire_buf, sizeof(wire_buf), &written);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_HEX8(0x51, wire_buf[0]);

    /* 5. Negative tests */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_wait_serialize(NULL, wire_buf, sizeof(wire_buf), &written));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_wait_serialize(&in_wait, NULL, sizeof(wire_buf), &written));
    TEST_ASSERT_EQUAL(ESP_ERR_NO_MEM, lora_mac_v2_down_join_wait_serialize(&in_wait, wire_buf, 19, &written));

    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_wait_deserialize(NULL, written, &out_wait));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_wait_deserialize(wire_buf, written, NULL));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_join_wait_deserialize(wire_buf, 19, &out_wait));

    /* Wrong message type */
    uint8_t bad_type_buf[20];
    memcpy(bad_type_buf, wire_buf, 20);
    bad_type_buf[0] = 0x52; /* REJECT type on WAIT deserializer */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_VERSION, lora_mac_v2_down_join_wait_deserialize(bad_type_buf, 20, &out_wait));
}

TEST_CASE("lora_mac V2 DOWN_JOIN_REJECT wire size and codec roundtrip", "[lora_mac][join_v2]")
{
    /* 1. Verify standard wire size and struct size are exactly 20 bytes */
    TEST_ASSERT_EQUAL_UINT32(20, LORA_MAC_V2_LEN_DOWN_JOIN_REJECT);
    TEST_ASSERT_EQUAL_UINT32(20, sizeof(lora_mac_v2_down_join_reject_t));

    const lora_mac_v2_down_join_reject_t in_reject = {
        .ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT,
        .device_mac = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF},
        .gw_id = 0x0E,
        .join_counter = 0xFEDCBA98,
        .auth_tag = {0x88, 0x77, 0x66, 0x55, 0x44, 0x33, 0x22, 0x11},
    };

    uint8_t wire_buf[32] = {0};
    size_t written = 0;

    /* 2. Positive serialization */
    esp_err_t err = lora_mac_v2_down_join_reject_serialize(&in_reject, wire_buf, sizeof(wire_buf), &written);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_UINT32(20, written);

    /* Verify wire layout: offset 0 = ver_type */
    TEST_ASSERT_EQUAL_HEX8(0x52, wire_buf[0]);
    /* Offsets 1..6 = device_mac */
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_reject.device_mac, &wire_buf[1], 6);
    /* Offset 7 = gw_id */
    TEST_ASSERT_EQUAL_HEX8(0x0E, wire_buf[7]);
    /* Offsets 8..11 = Big-Endian join_counter */
    TEST_ASSERT_EQUAL_HEX8(0xFE, wire_buf[8]);
    TEST_ASSERT_EQUAL_HEX8(0xDC, wire_buf[9]);
    TEST_ASSERT_EQUAL_HEX8(0xBA, wire_buf[10]);
    TEST_ASSERT_EQUAL_HEX8(0x98, wire_buf[11]);
    /* Offsets 12..19 = auth_tag */
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_reject.auth_tag, &wire_buf[12], 8);

    /* 3. Positive deserialization */
    lora_mac_v2_down_join_reject_t out_reject;
    memset(&out_reject, 0, sizeof(out_reject));

    err = lora_mac_v2_down_join_reject_deserialize(wire_buf, written, &out_reject);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_HEX8(in_reject.ver_type, out_reject.ver_type);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_reject.device_mac, out_reject.device_mac, 6);
    TEST_ASSERT_EQUAL_HEX8(in_reject.gw_id, out_reject.gw_id);
    TEST_ASSERT_EQUAL_HEX32(in_reject.join_counter, out_reject.join_counter);
    TEST_ASSERT_EQUAL_HEX8_ARRAY(in_reject.auth_tag, out_reject.auth_tag, 8);

    /* 4. Serialize with ver_type = 0 defaults to LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT (0x52) */
    lora_mac_v2_down_join_reject_t zero_ver = in_reject;
    zero_ver.ver_type = 0U;
    memset(wire_buf, 0, sizeof(wire_buf));
    err = lora_mac_v2_down_join_reject_serialize(&zero_ver, wire_buf, sizeof(wire_buf), &written);
    TEST_ASSERT_EQUAL(ESP_OK, err);
    TEST_ASSERT_EQUAL_HEX8(0x52, wire_buf[0]);

    /* 5. Negative tests */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_reject_serialize(NULL, wire_buf, sizeof(wire_buf), &written));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_reject_serialize(&in_reject, NULL, sizeof(wire_buf), &written));
    TEST_ASSERT_EQUAL(ESP_ERR_NO_MEM, lora_mac_v2_down_join_reject_serialize(&in_reject, wire_buf, 19, &written));

    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_reject_deserialize(NULL, written, &out_reject));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_ARG, lora_mac_v2_down_join_reject_deserialize(wire_buf, written, NULL));
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_join_reject_deserialize(wire_buf, 19, &out_reject));

    /* Wrong message type */
    uint8_t bad_type_buf[20];
    memcpy(bad_type_buf, wire_buf, 20);
    bad_type_buf[0] = 0x51; /* WAIT type on REJECT deserializer */
    TEST_ASSERT_EQUAL(ESP_ERR_INVALID_VERSION, lora_mac_v2_down_join_reject_deserialize(bad_type_buf, 20, &out_reject));
}
