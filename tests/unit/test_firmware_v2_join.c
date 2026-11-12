/**
 * @file test_firmware_v2_join.c
 * @brief Unit tests for Firmware V2 OTA Join Handshake across Sensor Node and Gateway Master.
 *
 * Authority: Issue #241, DEC-SEC-01..07, ADR-0003, C Coding Standard v2,
 *            contracts/radio-mac/specification.md, contracts/mqtt/schemas/join-hello.schema.json.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "lora_mac.h"
#include "lora_mac_join_crypto.h"
#include "node_v2_join.h"
#include "gateway_v2_join.h"
#include "session_key_store.h"
#include "gateway_transport.h"
#include "nvs.h"

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

#define ASSERT_EQUAL_MEM(ptr1, ptr2, len) do { \
    if (memcmp((ptr1), (ptr2), (len)) != 0) { \
        fprintf(stderr, "\nAssertion failed: memcmp(%s, %s, %u) == 0 at %s:%d\n", \
                #ptr1, #ptr2, (unsigned int)(len), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

/* =========================================================================
 * Mock Implementations for Gateway Dependencies (session_key_store, transport)
 * ========================================================================= */

static bool s_mock_session_key_installed = false;
static uint8_t s_mock_session_node_id = 0;
static size_t s_mock_mqtt_publish_count = 0;
static char s_mock_mqtt_last_payload[GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN];

esp_err_t session_key_store_install(const sk_install_aad_params_t *params,
                                   const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                   const uint8_t ciphertext[SK_PLAINTEXT_SIZE],
                                   const uint8_t tag[SK_TAG_SIZE],
                                   uint64_t now_ms)
{
    (void)k_gw_wrap;
    (void)ciphertext;
    (void)tag;
    (void)now_ms;
    if (params == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_mock_session_key_installed = true;
    s_mock_session_node_id = params->node_id;
    return ESP_OK;
}

esp_err_t gateway_transport_publish_join_relay(const uint8_t *payload, size_t len)
{
    if (payload == NULL || len == 0 || len >= sizeof(s_mock_mqtt_last_payload)) {
        return ESP_ERR_INVALID_ARG;
    }
    memcpy(s_mock_mqtt_last_payload, payload, len);
    s_mock_mqtt_last_payload[len] = '\0';
    s_mock_mqtt_publish_count++;
    return ESP_OK;
}

/* =========================================================================
 * 1. Frame Codecs Roundtrip Tests (0x45, 0x46, 0x47, 0x48, 0x49)
 * ========================================================================= */

static int test_join_frame_codecs_roundtrip(void)
{
    /* 1.1 UP_JOIN_HELLO (0x45, 68 bytes) */
    {
        lora_mac_v2_up_join_hello_t in_hello;
        memset(&in_hello, 0, sizeof(in_hello));
        in_hello.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_HELLO;
        uint8_t mac[6] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};
        memcpy(in_hello.device_mac, mac, 6);
        in_hello.target_gw_id = 7U;
        in_hello.join_counter = 1005U;
        for (int i = 0; i < 8; i++) in_hello.node_nonce[i] = (uint8_t)(i + 1);
        for (int i = 0; i < 32; i++) in_hello.node_x25519_pub[i] = (uint8_t)(i + 0x20);
        for (int i = 0; i < 16; i++) in_hello.join_proof[i] = (uint8_t)(i + 0x80);

        uint8_t wire[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
        size_t written = 0;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_hello_serialize(&in_hello, wire, sizeof(wire), &written));
        ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_UP_JOIN_HELLO, (uint32_t)written);
        ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_UP_JOIN_HELLO, wire[0]);

        lora_mac_v2_up_join_hello_t out_hello;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_hello_deserialize(wire, written, &out_hello));
        ASSERT_EQUAL_INT(in_hello.ver_type, out_hello.ver_type);
        ASSERT_EQUAL_MEM(in_hello.device_mac, out_hello.device_mac, 6);
        ASSERT_EQUAL_INT(in_hello.target_gw_id, out_hello.target_gw_id);
        ASSERT_EQUAL_U32(in_hello.join_counter, out_hello.join_counter);
        ASSERT_EQUAL_MEM(in_hello.node_nonce, out_hello.node_nonce, 8);
        ASSERT_EQUAL_MEM(in_hello.node_x25519_pub, out_hello.node_x25519_pub, 32);
        ASSERT_EQUAL_MEM(in_hello.join_proof, out_hello.join_proof, 16);

        /* Truncation / boundary check */
        ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_up_join_hello_deserialize(wire, 67, &out_hello));
        ASSERT_EQUAL_INT(ESP_ERR_NO_MEM, lora_mac_v2_up_join_hello_serialize(&in_hello, wire, 67, &written));
    }

    /* 1.2 DOWN_JOIN_GRANT (0x46, 66 bytes) */
    {
        lora_mac_v2_down_join_grant_t in_grant;
        memset(&in_grant, 0, sizeof(in_grant));
        in_grant.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT;
        uint8_t mac[6] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66};
        memcpy(in_grant.device_mac, mac, 6);
        in_grant.node_id = 4U;
        in_grant.join_counter = 2048U;
        for (int i = 0; i < 6; i++) in_grant.gw_nonce[i] = (uint8_t)(i + 0x10);
        for (int i = 0; i < 32; i++) in_grant.gw_x25519_pub[i] = (uint8_t)(i + 0x40);
        for (int i = 0; i < 16; i++) in_grant.grant_proof[i] = (uint8_t)(i + 0x90);

        uint8_t wire[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
        size_t written = 0;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_grant_serialize(&in_grant, wire, sizeof(wire), &written));
        ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_DOWN_JOIN_GRANT, (uint32_t)written);
        ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT, wire[0]);

        lora_mac_v2_down_join_grant_t out_grant;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_grant_deserialize(wire, written, &out_grant));
        ASSERT_EQUAL_INT(in_grant.ver_type, out_grant.ver_type);
        ASSERT_EQUAL_MEM(in_grant.device_mac, out_grant.device_mac, 6);
        ASSERT_EQUAL_INT(in_grant.node_id, out_grant.node_id);
        ASSERT_EQUAL_U32(in_grant.join_counter, out_grant.join_counter);
        ASSERT_EQUAL_MEM(in_grant.gw_nonce, out_grant.gw_nonce, 6);
        ASSERT_EQUAL_MEM(in_grant.gw_x25519_pub, out_grant.gw_x25519_pub, 32);
        ASSERT_EQUAL_MEM(in_grant.grant_proof, out_grant.grant_proof, 16);

        ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_join_grant_deserialize(wire, 65, &out_grant));
    }

    /* 1.3 UP_JOIN_KEY_CONFIRM (0x47, 31 bytes) */
    {
        lora_mac_v2_up_join_key_confirm_t in_conf;
        memset(&in_conf, 0, sizeof(in_conf));
        in_conf.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF;
        in_conf.gw_id = 1U;
        in_conf.node_id = 4U;
        in_conf.join_counter = 2048U;
        for (int i = 0; i < 8; i++) in_conf.gw_kc_tag[i] = (uint8_t)(i + 0x30);
        for (int i = 0; i < 16; i++) in_conf.backend_proof[i] = (uint8_t)(i + 0xA0);

        uint8_t wire[LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF];
        size_t written = 0;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_key_confirm_serialize(&in_conf, wire, sizeof(wire), &written));
        ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF, (uint32_t)written);
        ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF, wire[0]);

        lora_mac_v2_up_join_key_confirm_t out_conf;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_key_confirm_deserialize(wire, written, &out_conf));
        ASSERT_EQUAL_INT(in_conf.ver_type, out_conf.ver_type);
        ASSERT_EQUAL_INT(in_conf.gw_id, out_conf.gw_id);
        ASSERT_EQUAL_INT(in_conf.node_id, out_conf.node_id);
        ASSERT_EQUAL_U32(in_conf.join_counter, out_conf.join_counter);
        ASSERT_EQUAL_MEM(in_conf.gw_kc_tag, out_conf.gw_kc_tag, 8);
        ASSERT_EQUAL_MEM(in_conf.backend_proof, out_conf.backend_proof, 16);

        ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_up_join_key_confirm_deserialize(wire, 30, &out_conf));
    }

    /* 1.4 DOWN_JOIN_FINISH (0x48, 31 bytes) */
    {
        lora_mac_v2_down_join_finish_t in_finish;
        memset(&in_finish, 0, sizeof(in_finish));
        in_finish.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH;
        in_finish.gw_id = 1U;
        in_finish.node_id = 4U;
        in_finish.join_counter = 2048U;
        for (int i = 0; i < 8; i++) in_finish.gw_finish_tag[i] = (uint8_t)(i + 0x50);
        for (int i = 0; i < 16; i++) in_finish.backend_finish_proof[i] = (uint8_t)(i + 0xB0);

        uint8_t wire[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
        size_t written = 0;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_finish_serialize(&in_finish, wire, sizeof(wire), &written));
        ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_DOWN_JOIN_FINISH, (uint32_t)written);
        ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH, wire[0]);

        lora_mac_v2_down_join_finish_t out_finish;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_finish_deserialize(wire, written, &out_finish));
        ASSERT_EQUAL_INT(in_finish.ver_type, out_finish.ver_type);
        ASSERT_EQUAL_INT(in_finish.gw_id, out_finish.gw_id);
        ASSERT_EQUAL_INT(in_finish.node_id, out_finish.node_id);
        ASSERT_EQUAL_U32(in_finish.join_counter, out_finish.join_counter);
        ASSERT_EQUAL_MEM(in_finish.gw_finish_tag, out_finish.gw_finish_tag, 8);
        ASSERT_EQUAL_MEM(in_finish.backend_finish_proof, out_finish.backend_finish_proof, 16);

        ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_down_join_finish_deserialize(wire, 30, &out_finish));
    }

    /* 1.5 UP_JOIN_READY (0x49, 31 bytes) */
    {
        lora_mac_v2_up_join_ready_t in_ready;
        memset(&in_ready, 0, sizeof(in_ready));
        in_ready.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_READY;
        in_ready.gw_id = 1U;
        in_ready.node_id = 4U;
        in_ready.join_counter = 2048U;
        for (int i = 0; i < 8; i++) in_ready.gw_ready_tag[i] = (uint8_t)(i + 0x70);
        for (int i = 0; i < 16; i++) in_ready.backend_ready_proof[i] = (uint8_t)(i + 0xC0);

        uint8_t wire[LORA_MAC_V2_LEN_UP_JOIN_READY];
        size_t written = 0;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_ready_serialize(&in_ready, wire, sizeof(wire), &written));
        ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_UP_JOIN_READY, (uint32_t)written);
        ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_UP_JOIN_READY, wire[0]);

        lora_mac_v2_up_join_ready_t out_ready;
        ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_ready_deserialize(wire, written, &out_ready));
        ASSERT_EQUAL_INT(in_ready.ver_type, out_ready.ver_type);
        ASSERT_EQUAL_INT(in_ready.gw_id, out_ready.gw_id);
        ASSERT_EQUAL_INT(in_ready.node_id, out_ready.node_id);
        ASSERT_EQUAL_U32(in_ready.join_counter, out_ready.join_counter);
        ASSERT_EQUAL_MEM(in_ready.gw_ready_tag, out_ready.gw_ready_tag, 8);
        ASSERT_EQUAL_MEM(in_ready.backend_ready_proof, out_ready.backend_ready_proof, 16);

        ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, lora_mac_v2_up_join_ready_deserialize(wire, 30, &out_ready));
    }

    return 0;
}

/* =========================================================================
 * 2. Cryptographic Derivations and Verification Tests
 * ========================================================================= */

static int test_join_crypto_derivations_and_proofs(void)
{
    uint32_t network_id = 0x00010203U;
    uint8_t device_mac[6] = {0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
    uint16_t device_generation = 1U;
    uint8_t k_join[32];
    for (int i = 0; i < 32; i++) k_join[i] = (uint8_t)(0x10 + i);

    lora_mac_k_join_expanded_keys_t keys;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_derive_k_join_keys(network_id, device_mac, device_generation, k_join, &keys));

    /* Verify keys are non-zero */
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(keys.k_jreq, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(keys.k_jgrant, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(keys.k_jconf, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(keys.k_jfinish, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(keys.k_jready, 32));

    /* Test UP_JOIN_HELLO Proof */
    uint8_t hello_prefix52[52];
    for (int i = 0; i < 52; i++) hello_prefix52[i] = (uint8_t)(i + 0x05);
    uint8_t hello_proof[16];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_hello_proof(network_id, hello_prefix52, keys.k_jreq, hello_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_hello_proof(network_id, hello_prefix52, keys.k_jreq, hello_proof));

    /* Tampered proof must fail with ESP_ERR_INVALID_CRC */
    uint8_t bad_proof[16];
    memcpy(bad_proof, hello_proof, 16);
    bad_proof[0] ^= 0xFF;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, lora_mac_join_verify_hello_proof(network_id, hello_prefix52, keys.k_jreq, bad_proof));

    /* Test DOWN_JOIN_GRANT Proof */
    uint8_t hello68[68];
    memcpy(hello68, hello_prefix52, 52);
    memcpy(hello68 + 52, hello_proof, 16);

    uint8_t grant_prefix50[50];
    for (int i = 0; i < 50; i++) grant_prefix50[i] = (uint8_t)(i + 0x22);
    uint8_t grant_proof[16];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_grant_proof(network_id, hello68, grant_prefix50, keys.k_jgrant, grant_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_grant_proof(network_id, hello68, grant_prefix50, keys.k_jgrant, grant_proof));

    bad_proof[0] = grant_proof[0] ^ 0x01;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, lora_mac_join_verify_grant_proof(network_id, hello68, grant_prefix50, keys.k_jgrant, bad_proof));

    /* Test TH and Session Keys Derivation */
    uint8_t grant66[66];
    memcpy(grant66, grant_prefix50, 50);
    memcpy(grant66 + 50, grant_proof, 16);

    uint8_t th[32];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_th(network_id, hello68, grant66, th));

    uint8_t z_shared[32];
    for (int i = 0; i < 32; i++) z_shared[i] = (uint8_t)(i + 0x77);

    lora_mac_session_keys_t session_keys;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_derive_session_keys(th, z_shared, &session_keys));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(session_keys.k_session_up, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(session_keys.k_session_dl, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(session_keys.k_kc_up, 32));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(session_keys.k_kc_down, 32));

    /* Test Confirm Dual Tags */
    uint8_t conf_prefix7[7] = {0x47, 0x01, 0x04, 0x00, 0x00, 0x08, 0x00};
    uint8_t gw_kc_tag[8];
    uint8_t backend_proof[16];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_confirm_tags(network_id, th, conf_prefix7,
                                                               session_keys.k_kc_up, keys.k_jconf,
                                                               gw_kc_tag, backend_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_confirm_gw_tag(th, conf_prefix7, session_keys.k_kc_up, gw_kc_tag));

    uint8_t bad_tag[8];
    memcpy(bad_tag, gw_kc_tag, 8);
    bad_tag[0] ^= 0x42;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, lora_mac_join_verify_confirm_gw_tag(th, conf_prefix7, session_keys.k_kc_up, bad_tag));

    /* Test Finish Dual Tags */
    uint8_t finish_prefix7[7] = {0x48, 0x01, 0x04, 0x00, 0x00, 0x08, 0x00};
    uint8_t gw_finish_tag[8];
    uint8_t backend_finish_proof[16];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_finish_tags(network_id, th, finish_prefix7,
                                                              session_keys.k_kc_down, keys.k_jfinish,
                                                              gw_finish_tag, backend_finish_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_finish_tags(network_id, th, finish_prefix7,
                                                             session_keys.k_kc_down, keys.k_jfinish,
                                                             gw_finish_tag, backend_finish_proof));

    /* Test Ready Dual Tags */
    uint8_t finish31[31];
    memcpy(finish31, finish_prefix7, 7);
    memcpy(finish31 + 7, gw_finish_tag, 8);
    memcpy(finish31 + 15, backend_finish_proof, 16);

    uint8_t ready_prefix7[7] = {0x49, 0x01, 0x04, 0x00, 0x00, 0x08, 0x00};
    uint8_t gw_ready_tag[8];
    uint8_t backend_ready_proof[16];
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_ready_tags(network_id, th, finish31, ready_prefix7,
                                                             session_keys.k_kc_up, keys.k_jready,
                                                             gw_ready_tag, backend_ready_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_ready_gw_tag(th, finish31, ready_prefix7,
                                                              session_keys.k_kc_up, gw_ready_tag));

    return 0;
}

/* =========================================================================
 * 3. RFC 7748 All-Zeros Shared Secret Abort (DEC-SEC-07)
 * ========================================================================= */

static int test_rfc7748_all_zeros_shared_secret_abort(void)
{
    uint8_t priv[32];
    uint8_t peer_pub[32];
    uint8_t shared[32];

    memset(priv, 0x11, 32);
    memset(peer_pub, 0x22, 32);

    /* Normal ECDH succeeds */
    lora_mac_crypto_mock_set_force_zero_shared(false);
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_crypto_x25519_ecdh(priv, peer_pub, shared));
    ASSERT_TRUE(!lora_mac_crypto_is_all_zero(shared, 32));

    /* Peer public key all zeros -> abort per DEC-SEC-07 */
    memset(peer_pub, 0, 32);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_RESPONSE, lora_mac_crypto_x25519_ecdh(priv, peer_pub, shared));
    ASSERT_TRUE(lora_mac_crypto_is_all_zero(shared, 32));

    /* Simulated Z == 0^32 through mock hook -> abort per RFC 7748 §6.1 */
    memset(peer_pub, 0x22, 32);
    lora_mac_crypto_mock_set_force_zero_shared(true);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_RESPONSE, lora_mac_crypto_x25519_ecdh(priv, peer_pub, shared));
    ASSERT_TRUE(lora_mac_crypto_is_all_zero(shared, 32));

    lora_mac_crypto_mock_set_force_zero_shared(false);
    return 0;
}

/* =========================================================================
 * 4. Monotonic NVS Counter Commit and Rollback Lockout (DEC-SEC-06)
 * ========================================================================= */

static int test_monotonic_nvs_counter_commit_and_rollback_lockout(void)
{
    mock_nvs_reset();

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    /* Step 1: Initial commit -> counter becomes 1 */
    uint32_t ctr = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_commit_counter(&ctx, &ctr));
    ASSERT_EQUAL_U32(1U, ctr);
    ASSERT_EQUAL_U32(1U, ctx.committed_join_counter);
    ASSERT_TRUE(!ctx.radio_permanently_locked);

    /* Step 2: Next commit -> counter becomes 2 */
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_commit_counter(&ctx, &ctr));
    ASSERT_EQUAL_U32(2U, ctr);
    ASSERT_EQUAL_U32(2U, ctx.committed_join_counter);

    /* Step 3: Next commit -> counter becomes 3 */
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_commit_counter(&ctx, &ctr));
    ASSERT_EQUAL_U32(3U, ctr);
    ASSERT_EQUAL_U32(3U, ctx.committed_join_counter);

    /* Step 4: Inject Rollback Anomaly in NVS (reverting stored counter to 1 while ctx expects >= 3) */
    nvs_handle_t h = 0;
    ASSERT_EQUAL_INT(ESP_OK, nvs_open(NODE_V2_JOIN_NVS_NAMESPACE, NVS_READWRITE, &h));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_u32(h, NODE_V2_JOIN_NVS_KEY_COUNTER, 1U));
    ASSERT_EQUAL_INT(ESP_OK, nvs_commit(h));
    nvs_close(h);

    /* Step 5: Next commit must detect rollback and permanently lock the radio (DEC-SEC-06) */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, node_v2_join_commit_counter(&ctx, &ctr));
    ASSERT_TRUE(ctx.radio_permanently_locked);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_LOCKED_OUT, ctx.state);

    /* Step 6: Subsequent attempts fail-closed without touching NVS or Radio */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, node_v2_join_commit_counter(&ctx, &ctr));

    /* node_v2_join_run while locked out must immediately abort */
    node_v2_join_config_t cfg;
    node_v2_join_get_default_config(&cfg);
    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_tx = (esp_err_t (*)(const uint8_t *, uint8_t, uint32_t))1;
    hal.radio_read_frame = (esp_err_t (*)(uint8_t *, size_t *, uint32_t))1;

    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, node_v2_join_run(&cfg, &hal, &ctx));
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_LOCKED_OUT, ctx.state);

    return 0;
}

/* =========================================================================
 * 5. CAD Retry Exhaustion Test (RAD-003, 3 Attempts -> Sleep)
 * ========================================================================= */

static uint32_t s_cad_calls = 0;
static uint32_t s_delays_count = 0;
static uint32_t s_sleep_calls = 0;

static esp_err_t mock_radio_cad_always_busy(bool *out_activity_detected)
{
    s_cad_calls++;
    if (out_activity_detected != NULL) {
        *out_activity_detected = true; /* Channel always busy */
    }
    return ESP_OK;
}

static void mock_delay_ms(uint32_t ms)
{
    (void)ms;
    s_delays_count++;
}

static esp_err_t mock_radio_sleep(void)
{
    s_sleep_calls++;
    return ESP_OK;
}

static esp_err_t mock_dummy_tx(const uint8_t *payload, uint8_t len, uint32_t timeout_ms)
{
    (void)payload; (void)len; (void)timeout_ms;
    return ESP_OK;
}

static esp_err_t mock_dummy_read_frame(uint8_t *buf, size_t *len, uint32_t timeout_ms)
{
    (void)buf; (void)len; (void)timeout_ms;
    return ESP_ERR_TIMEOUT;
}

static int test_cad_retry_exhaustion(void)
{
    mock_nvs_reset();
    s_cad_calls = 0;
    s_delays_count = 0;
    s_sleep_calls = 0;

    node_v2_join_config_t cfg;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_get_default_config(&cfg));
    cfg.max_cad_retries = 3U;

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_radio_cad_always_busy;
    hal.delay_ms = mock_delay_ms;
    hal.radio_sleep = mock_radio_sleep;
    hal.radio_tx = mock_dummy_tx;
    hal.radio_read_frame = mock_dummy_read_frame;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    /* Execution should exhaust 3 retries and return ESP_ERR_TIMEOUT */
    esp_err_t res = node_v2_join_run(&cfg, &hal, &ctx);
    ASSERT_EQUAL_INT(ESP_ERR_TIMEOUT, res);
    ASSERT_EQUAL_U32(3U, s_cad_calls);
    ASSERT_EQUAL_U32(2U, s_delays_count); /* 2 backoffs between 3 tries */
    ASSERT_EQUAL_U32(1U, s_sleep_calls);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_ABORTED, ctx.state);

    return 0;
}

/* =========================================================================
 * 6. Sensor Node Full Sequential Handshake End-to-End Test (Phase 1..4b)
 * ========================================================================= */

typedef struct {
    uint8_t last_tx_buf[128];
    size_t  last_tx_len;
    uint32_t step;
    node_v2_join_config_t cfg;
    lora_mac_k_join_expanded_keys_t k_join_keys;
    uint8_t th[32];
    lora_mac_session_keys_t gw_session_keys;
    uint8_t finish31[31];
} mock_gw_peer_t;

static mock_gw_peer_t s_mock_gw;

static esp_err_t mock_e2e_radio_cad(bool *out_activity_detected)
{
    if (out_activity_detected) *out_activity_detected = false; /* Clear channel */
    return ESP_OK;
}

static esp_err_t mock_e2e_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (length > sizeof(s_mock_gw.last_tx_buf)) return ESP_ERR_NO_MEM;
    memcpy(s_mock_gw.last_tx_buf, payload, length);
    s_mock_gw.last_tx_len = length;
    return ESP_OK;
}

static esp_err_t mock_e2e_radio_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    (void)wait_ms;
    if (s_mock_gw.step == 1) {
        /* Node just sent UP_JOIN_HELLO (68B). Mock Gateway creates DOWN_JOIN_GRANT (66B). */
        if (s_mock_gw.last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_HELLO) return ESP_ERR_INVALID_SIZE;
        lora_mac_v2_up_join_hello_t hello;
        lora_mac_v2_up_join_hello_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &hello);

        lora_mac_v2_down_join_grant_t grant;
        grant.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT;
        memcpy(grant.device_mac, hello.device_mac, 6);
        grant.node_id = 5U;
        grant.join_counter = hello.join_counter;
        for (int i = 0; i < 6; i++) grant.gw_nonce[i] = (uint8_t)(i + 0x33);

        uint8_t priv_gw[32], pub_gw[32];
        lora_mac_crypto_x25519_keypair(priv_gw, pub_gw);
        memcpy(grant.gw_x25519_pub, pub_gw, 32);

        /* Derive mock ECDH */
        uint8_t z[32];
        lora_mac_crypto_x25519_ecdh(priv_gw, hello.node_x25519_pub, z);

        /* Compute grant prefix 50B */
        uint8_t grant_wire[66];
        size_t wr = 0;
        lora_mac_v2_down_join_grant_serialize(&grant, grant_wire, sizeof(grant_wire), &wr);

        lora_mac_join_compute_grant_proof(s_mock_gw.cfg.network_id, s_mock_gw.last_tx_buf, grant_wire,
                                         s_mock_gw.k_join_keys.k_jgrant, grant.grant_proof);
        lora_mac_v2_down_join_grant_serialize(&grant, grant_wire, sizeof(grant_wire), &wr);

        /* Derive gateway session keys */
        lora_mac_join_compute_th(s_mock_gw.cfg.network_id, s_mock_gw.last_tx_buf, grant_wire, s_mock_gw.th);
        lora_mac_join_derive_session_keys(s_mock_gw.th, z, &s_mock_gw.gw_session_keys);

        memcpy(out_buf, grant_wire, 66);
        *out_len = 66;
        s_mock_gw.step = 2;
        return ESP_OK;
    } else if (s_mock_gw.step == 2) {
        /* Node just sent UP_JOIN_KEY_CONFIRM (31B). Mock Gateway creates DOWN_JOIN_FINISH (31B). */
        if (s_mock_gw.last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF) return ESP_ERR_INVALID_SIZE;
        lora_mac_v2_up_join_key_confirm_t conf;
        lora_mac_v2_up_join_key_confirm_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &conf);

        lora_mac_v2_down_join_finish_t finish;
        finish.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH;
        finish.gw_id = conf.gw_id;
        finish.node_id = conf.node_id;
        finish.join_counter = conf.join_counter;

        uint8_t finish_prefix7[7] = {finish.ver_type, finish.gw_id, finish.node_id,
                                     (uint8_t)(finish.join_counter >> 24), (uint8_t)(finish.join_counter >> 16),
                                     (uint8_t)(finish.join_counter >> 8), (uint8_t)(finish.join_counter)};
        lora_mac_join_compute_finish_tags(s_mock_gw.cfg.network_id, s_mock_gw.th, finish_prefix7,
                                         s_mock_gw.gw_session_keys.k_kc_down, s_mock_gw.k_join_keys.k_jfinish,
                                         finish.gw_finish_tag, finish.backend_finish_proof);

        uint8_t finish_wire[31];
        size_t wr = 0;
        lora_mac_v2_down_join_finish_serialize(&finish, finish_wire, sizeof(finish_wire), &wr);
        memcpy(s_mock_gw.finish31, finish_wire, 31);

        memcpy(out_buf, finish_wire, 31);
        *out_len = 31;
        s_mock_gw.step = 3;
        return ESP_OK;
    }

    return ESP_ERR_TIMEOUT;
}

static int test_node_complete_handshake_end_to_end(void)
{
    mock_nvs_reset();
    memset(&s_mock_gw, 0, sizeof(s_mock_gw));
    s_mock_gw.step = 1;

    node_v2_join_get_default_config(&s_mock_gw.cfg);
    for (int i = 0; i < 32; i++) s_mock_gw.cfg.k_join[i] = (uint8_t)(0xAA + i);

    lora_mac_join_derive_k_join_keys(s_mock_gw.cfg.network_id, s_mock_gw.cfg.device_mac,
                                     s_mock_gw.cfg.device_generation, s_mock_gw.cfg.k_join,
                                     &s_mock_gw.k_join_keys);

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_e2e_radio_cad;
    hal.radio_tx = mock_e2e_radio_tx;
    hal.radio_read_frame = mock_e2e_radio_read_frame;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    /* Execute complete handshake */
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_run(&s_mock_gw.cfg, &hal, &ctx));

    /* Acceptance checks:
     * 1. State must be NODE_V2_JOIN_STATE_INSTALLED_INACTIVE (DEC-SEC-05)
     * 2. Assigned node ID is 5
     * 3. Session keys are established and match Gateway derivation
     * 4. Last transmitted frame was UP_JOIN_READY (0x49, 31 bytes)
     */
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, ctx.state);
    ASSERT_EQUAL_INT(5U, ctx.assigned_node_id);
    ASSERT_EQUAL_MEM(s_mock_gw.gw_session_keys.k_session_up, ctx.session_keys.k_session_up, 32);
    ASSERT_EQUAL_MEM(s_mock_gw.gw_session_keys.k_session_dl, ctx.session_keys.k_session_dl, 32);
    ASSERT_EQUAL_U32(31U, (uint32_t)s_mock_gw.last_tx_len);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_UP_JOIN_READY, s_mock_gw.last_tx_buf[0]);

    /* Verify final UP_JOIN_READY frame binds FINISH31 */
    lora_mac_v2_up_join_ready_t ready;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_ready_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &ready));
    uint8_t ready_prefix7[7] = {ready.ver_type, ready.gw_id, ready.node_id,
                                (uint8_t)(ready.join_counter >> 24), (uint8_t)(ready.join_counter >> 16),
                                (uint8_t)(ready.join_counter >> 8), (uint8_t)(ready.join_counter)};
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_verify_ready_gw_tag(s_mock_gw.th, s_mock_gw.finish31, ready_prefix7,
                                                              s_mock_gw.gw_session_keys.k_kc_up, ready.gw_ready_tag));

    return 0;
}

typedef struct {
    uint32_t step;
    uint32_t rx_single_calls;
    uint32_t standby_calls;
    uint32_t delay_calls;
    uint32_t standby_calls_during_wait;
    uint32_t rx_single_calls_during_wait;
} wait_rx_probe_t;

static wait_rx_probe_t s_wait_probe;

static esp_err_t mock_wait_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    s_wait_probe.rx_single_calls++;
    return ESP_OK;
}

static esp_err_t mock_wait_rx_standby(void)
{
    s_wait_probe.standby_calls++;
    return ESP_OK;
}

static void mock_wait_rx_delay(uint32_t ms)
{
    (void)ms;
    s_wait_probe.delay_calls++;
}

static esp_err_t mock_wait_rx_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    (void)wait_ms;
    if (s_wait_probe.step == 0U) {
        /* 1. Initial response in GRANT_RX is DOWN_JOIN_WAIT */
        lora_mac_v2_up_join_hello_t hello;
        lora_mac_v2_up_join_hello_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &hello);

        lora_mac_v2_down_join_wait_t wait_f;
        memset(&wait_f, 0, sizeof(wait_f));
        wait_f.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT;
        memcpy(wait_f.device_mac, hello.device_mac, 6);
        wait_f.gw_id = hello.target_gw_id;
        wait_f.join_counter = hello.join_counter;

        size_t wr = 0;
        lora_mac_v2_down_join_wait_serialize(&wait_f, out_buf, 128, &wr);
        *out_len = wr;
        s_wait_probe.step = 1U;
        return ESP_OK;
    }

    if (s_wait_probe.step <= 10U) {
        /* Snapshot that GRANT_RX -> WAIT_RX did NOT leave RXCONT or re-arm rx_single */
        s_wait_probe.standby_calls_during_wait = s_wait_probe.standby_calls;
        s_wait_probe.rx_single_calls_during_wait = s_wait_probe.rx_single_calls;
        s_wait_probe.step++;
        return ESP_ERR_TIMEOUT;
    }

    if (s_wait_probe.step == 11U) {
        /* Repeated DOWN_JOIN_WAIT during continuous WAIT_RX */
        lora_mac_v2_up_join_hello_t hello;
        lora_mac_v2_up_join_hello_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &hello);

        lora_mac_v2_down_join_wait_t wait_f;
        memset(&wait_f, 0, sizeof(wait_f));
        wait_f.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT;
        memcpy(wait_f.device_mac, hello.device_mac, 6);
        wait_f.gw_id = hello.target_gw_id;
        wait_f.join_counter = hello.join_counter;

        size_t wr = 0;
        lora_mac_v2_down_join_wait_serialize(&wait_f, out_buf, 128, &wr);
        *out_len = wr;
        s_wait_probe.step = 12U;
        return ESP_OK;
    }

    if (s_wait_probe.step == 12U) {
        /* Unrelated frame / different MAC GRANT must be ignored without leaving WAIT_RX */
        lora_mac_v2_up_join_hello_t hello;
        lora_mac_v2_up_join_hello_deserialize(s_mock_gw.last_tx_buf, s_mock_gw.last_tx_len, &hello);

        lora_mac_v2_down_join_grant_t wrong_grant;
        memset(&wrong_grant, 0, sizeof(wrong_grant));
        wrong_grant.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT;
        memcpy(wrong_grant.device_mac, hello.device_mac, 6);
        wrong_grant.device_mac[5] ^= 0xFFU;
        wrong_grant.node_id = 3U;
        wrong_grant.join_counter = hello.join_counter;

        size_t wr = 0;
        lora_mac_v2_down_join_grant_serialize(&wrong_grant, out_buf, 128, &wr);
        *out_len = wr;
        s_wait_probe.step = 13U;
        return ESP_OK;
    }

    if (s_wait_probe.step == 13U) {
        /* Matching DOWN_JOIN_GRANT finally arrives after extended WAIT_RX */
        s_wait_probe.standby_calls_during_wait = s_wait_probe.standby_calls;
        s_wait_probe.rx_single_calls_during_wait = s_wait_probe.rx_single_calls;
        s_mock_gw.step = 1U;
        s_wait_probe.step = 14U;
        return mock_e2e_radio_read_frame(out_buf, out_len, wait_ms);
    }

    /* Phase 4a: DOWN_JOIN_FINISH */
    return mock_e2e_radio_read_frame(out_buf, out_len, wait_ms);
}

static int test_node_wait_rx_continuous_indefinite_until_grant(void)
{
    mock_nvs_reset();
    memset(&s_mock_gw, 0, sizeof(s_mock_gw));
    memset(&s_wait_probe, 0, sizeof(s_wait_probe));

    node_v2_join_get_default_config(&s_mock_gw.cfg);
    for (int i = 0; i < 32; i++) s_mock_gw.cfg.k_join[i] = (uint8_t)(0x55 + i);

    lora_mac_join_derive_k_join_keys(s_mock_gw.cfg.network_id, s_mock_gw.cfg.device_mac,
                                     s_mock_gw.cfg.device_generation, s_mock_gw.cfg.k_join,
                                     &s_mock_gw.k_join_keys);

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_e2e_radio_cad;
    hal.radio_tx = mock_e2e_radio_tx;
    hal.radio_rx_single = mock_wait_rx_single;
    hal.radio_read_frame = mock_wait_rx_read_frame;
    hal.radio_standby = mock_wait_rx_standby;
    hal.delay_ms = mock_wait_rx_delay;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_run(&s_mock_gw.cfg, &hal, &ctx));
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, ctx.state);
    ASSERT_EQUAL_INT(5U, ctx.assigned_node_id);

    /* Throughout entire WAIT_RX (10 timeouts + repeated WAIT + wrong-MAC frame), RXCONT was never interrupted */
    ASSERT_EQUAL_U32(0U, s_wait_probe.standby_calls_during_wait);
    ASSERT_EQUAL_U32(1U, s_wait_probe.rx_single_calls_during_wait);
    ASSERT_EQUAL_U32(0U, s_wait_probe.delay_calls);
    /* Overall: rx_single called twice (GRANT_RX and FINISH_RX), standby called twice (exit GRANT and exit FINISH) */
    ASSERT_EQUAL_U32(2U, s_wait_probe.rx_single_calls);
    ASSERT_EQUAL_U32(2U, s_wait_probe.standby_calls);

    return 0;
}

/* =========================================================================
 * 7. Gateway Relay Engine and MQTT Schema Conformance Test
 * ========================================================================= */

static int test_gateway_relay_engine_and_mqtt_schema(void)
{
    s_mock_session_key_installed = false;
    s_mock_session_node_id = 0;
    s_mock_mqtt_publish_count = 0;
    memset(s_mock_mqtt_last_payload, 0, sizeof(s_mock_mqtt_last_payload));

    gateway_v2_join_engine_t engine;
    gateway_v2_join_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    snprintf(cfg.gateway_id, sizeof(cfg.gateway_id), "%s", "gw-pilot-01");
    snprintf(cfg.gateway_epoch, sizeof(cfg.gateway_epoch), "%s", "01234567-89ab-cdef-0123-456789abcdef");
    cfg.target_gw_id = 1U;
    cfg.network_id = 0x00010203U;

    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_init(&engine, &cfg));

    /* Synthesize valid UP_JOIN_HELLO */
    lora_mac_v2_up_join_hello_t hello;
    memset(&hello, 0, sizeof(hello));
    hello.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_HELLO;
    uint8_t mac[6] = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66};
    memcpy(hello.device_mac, mac, 6);
    hello.target_gw_id = 1U;
    hello.join_counter = 42U;
    for (int i = 0; i < 8; i++) hello.node_nonce[i] = (uint8_t)(i + 1);
    uint8_t priv_n[32], pub_n[32];
    lora_mac_crypto_x25519_keypair(priv_n, pub_n);
    memcpy(hello.node_x25519_pub, pub_n, 32);
    memset(hello.join_proof, 0xEE, 16);

    uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    size_t hello_written = 0;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_hello_serialize(&hello, hello_raw, sizeof(hello_raw), &hello_written));

    /* 7.1 Test gateway_v2_join_build_relay_json schema conformance */
    char relay_json[GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN];
    size_t json_written = 0;
    int16_t rssi = -75;
    float snr = 9.5f;
    uint64_t rx_mono_us = 123456789ULL;

    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_build_relay_json(&engine, hello_raw, 1U, rssi, snr, rx_mono_us,
                                                              relay_json, sizeof(relay_json), &json_written));

    /* Verify JSON schema invariants per contracts/mqtt/schemas/join-hello.schema.json */
    ASSERT_TRUE(strstr(relay_json, "\"schema_version\":\"1.0-draft\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"event_id\":\"gw-pilot-01:01234567-89ab-cdef-0123-456789abcdef:1\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"gateway_id\":\"gw-pilot-01\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"gateway_epoch\":\"01234567-89ab-cdef-0123-456789abcdef\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"event_seq\":\"1\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"observed_at\":null") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"observed_time_source\":\"gateway_utc\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"radio_rx_monotonic_us\":\"123456789\"") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"buffered\":false") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"target_gw_id\":1") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"rssi\":-75") != NULL);
    ASSERT_TRUE(strstr(relay_json, "\"snr\":9.5") != NULL);

    /* Verify raw_frame_hex is exactly 136 hex characters (68 bytes) */
    char *hex_start = strstr(relay_json, "\"raw_frame_hex\":\"");
    ASSERT_TRUE(hex_start != NULL);
    hex_start += strlen("\"raw_frame_hex\":\"");
    char *hex_end = strchr(hex_start, '"');
    ASSERT_TRUE(hex_end != NULL);
    ASSERT_EQUAL_U32(136U, (uint32_t)(hex_end - hex_start));

    /* 7.2 Process UP_JOIN_HELLO at Gateway */
    uint8_t out_grant[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
    size_t out_grant_len = 0;
    uint8_t backend_grant_proof[16];
    memset(backend_grant_proof, 0x88, 16);

    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_handle_hello(&engine, hello_raw, hello_written,
                                                          rssi, snr, rx_mono_us,
                                                          backend_grant_proof, out_grant, &out_grant_len));
    ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_DOWN_JOIN_GRANT, (uint32_t)out_grant_len);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT, out_grant[0]);
    ASSERT_TRUE(s_mock_session_key_installed);
    ASSERT_EQUAL_U32(1U, (uint32_t)s_mock_mqtt_publish_count);

    /* Check assigned node ID */
    lora_mac_v2_down_join_grant_t parsed_grant;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_grant_deserialize(out_grant, out_grant_len, &parsed_grant));
    ASSERT_EQUAL_INT(s_mock_session_node_id, parsed_grant.node_id);

    /* 7.3 Gateway handles UP_JOIN_KEY_CONFIRM and produces DOWN_JOIN_FINISH */
    uint8_t conf_wire[LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF];
    size_t conf_len = 0;
    lora_mac_v2_up_join_key_confirm_t conf;
    conf.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF;
    conf.gw_id = cfg.target_gw_id;
    conf.node_id = parsed_grant.node_id;
    conf.join_counter = hello.join_counter;

    /* Compute gateway KC tag */
    uint8_t conf_prefix7[7] = {conf.ver_type, conf.gw_id, conf.node_id,
                               (uint8_t)(conf.join_counter >> 24), (uint8_t)(conf.join_counter >> 16),
                               (uint8_t)(conf.join_counter >> 8), (uint8_t)(conf.join_counter)};
    gateway_v2_pending_join_t *pend = &engine.pending_joins[parsed_grant.node_id - 1];
    uint8_t dummy_k_jconf[32];
    uint8_t dummy_be_proof[16];
    memset(dummy_k_jconf, 0x11, sizeof(dummy_k_jconf));
    memset(dummy_be_proof, 0, sizeof(dummy_be_proof));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_confirm_tags(cfg.network_id, pend->th, conf_prefix7,
                                                               pend->session_keys.k_kc_up, dummy_k_jconf,
                                                               conf.gw_kc_tag, dummy_be_proof));
    memcpy(conf.backend_proof, dummy_be_proof, 16);

    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_key_confirm_serialize(&conf, conf_wire, sizeof(conf_wire), &conf_len));

    uint8_t out_finish[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
    size_t out_finish_len = 0;
    uint8_t backend_finish_proof[16];
    memset(backend_finish_proof, 0xAA, 16);

    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_handle_confirm(&engine, conf_wire, conf_len,
                                                            backend_finish_proof, out_finish, &out_finish_len));
    ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_DOWN_JOIN_FINISH, (uint32_t)out_finish_len);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH, out_finish[0]);

    /* 7.4 Gateway handles UP_JOIN_READY */
    lora_mac_v2_up_join_ready_t ready;
    ready.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_READY;
    ready.gw_id = cfg.target_gw_id;
    ready.node_id = parsed_grant.node_id;
    ready.join_counter = hello.join_counter;

    uint8_t ready_prefix7[7] = {ready.ver_type, ready.gw_id, ready.node_id,
                                (uint8_t)(ready.join_counter >> 24), (uint8_t)(ready.join_counter >> 16),
                                (uint8_t)(ready.join_counter >> 8), (uint8_t)(ready.join_counter)};
    uint8_t dummy_k_jready[32];
    memset(dummy_k_jready, 0x22, sizeof(dummy_k_jready));
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_join_compute_ready_tags(cfg.network_id, pend->th, out_finish, ready_prefix7,
                                                             pend->session_keys.k_kc_up, dummy_k_jready,
                                                             ready.gw_ready_tag, ready.backend_ready_proof));

    uint8_t ready_wire[LORA_MAC_V2_LEN_UP_JOIN_READY];
    size_t ready_len = 0;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_ready_serialize(&ready, ready_wire, sizeof(ready_wire), &ready_len));

    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_handle_ready(&engine, ready_wire, ready_len));

    return 0;
}

static int test_gateway_v2_join_build_wait_and_reject(void)
{
    gateway_v2_join_engine_t engine;
    gateway_v2_join_config_t cfg = {
        .gateway_id = "gw-test-01",
        .gateway_epoch = "01234567-89ab-cdef-0123-456789abcdef",
        .target_gw_id = 7,
        .network_id = 100,
    };
    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_init(&engine, &cfg));

    /* Synthesize valid UP_JOIN_HELLO (68 bytes) */
    lora_mac_v2_up_join_hello_t hello = {
        .ver_type = LORA_MAC_V2_TYPE_UP_JOIN_HELLO,
        .device_mac = {0x11, 0x22, 0x33, 0x44, 0x55, 0x66},
        .target_gw_id = 7,
        .join_counter = 0x12345678,
    };
    memset(hello.node_nonce, 0xAA, 8);
    memset(hello.node_x25519_pub, 0xBB, 32);
    memset(hello.join_proof, 0xCC, 16);

    uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    size_t hello_len = 0;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_join_hello_serialize(&hello, hello_raw, sizeof(hello_raw), &hello_len));
    ASSERT_EQUAL_U32(LORA_MAC_V2_LEN_UP_JOIN_HELLO, (uint32_t)hello_len);

    /* 1. Test gateway_v2_join_build_wait */
    uint8_t wait_wire[LORA_MAC_V2_LEN_DOWN_JOIN_WAIT];
    size_t wait_len = 0;
    const uint8_t sample_tag[8] = {0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08};

    /* Positive build with custom auth_tag */
    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_build_wait(&engine, hello_raw, hello_len,
                                                        sample_tag, wait_wire, &wait_len));
    ASSERT_EQUAL_U32(20, (uint32_t)wait_len);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT, wait_wire[0]);
    ASSERT_EQUAL_INT(0x51, wait_wire[0]);
    ASSERT_EQUAL_MEM(hello.device_mac, &wait_wire[1], 6);
    ASSERT_EQUAL_INT(7, wait_wire[7]);
    ASSERT_EQUAL_MEM(sample_tag, &wait_wire[12], 8);

    /* Deserialize wait frame and verify */
    lora_mac_v2_down_join_wait_t parsed_wait;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_wait_deserialize(wait_wire, wait_len, &parsed_wait));
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT, parsed_wait.ver_type);
    ASSERT_EQUAL_MEM(hello.device_mac, parsed_wait.device_mac, 6);
    ASSERT_EQUAL_INT(7, parsed_wait.gw_id);
    ASSERT_EQUAL_U32(0x12345678, parsed_wait.join_counter);
    ASSERT_EQUAL_MEM(sample_tag, parsed_wait.auth_tag, 8);

    /* Build with NULL auth_tag -> zeroed */
    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_build_wait(&engine, hello_raw, hello_len,
                                                        NULL, wait_wire, &wait_len));
    ASSERT_EQUAL_U32(20, (uint32_t)wait_len);
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_wait_deserialize(wait_wire, wait_len, &parsed_wait));
    uint8_t zero_tag[8] = {0};
    ASSERT_EQUAL_MEM(zero_tag, parsed_wait.auth_tag, 8);

    /* Negative tests for wait */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_wait(NULL, hello_raw, hello_len, sample_tag, wait_wire, &wait_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_wait(&engine, NULL, hello_len, sample_tag, wait_wire, &wait_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_wait(&engine, hello_raw, hello_len, sample_tag, NULL, &wait_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_wait(&engine, hello_raw, hello_len, sample_tag, wait_wire, NULL));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, gateway_v2_join_build_wait(&engine, hello_raw, hello_len - 1, sample_tag, wait_wire, &wait_len));

    /* 2. Test gateway_v2_join_build_reject */
    uint8_t reject_wire[LORA_MAC_V2_LEN_DOWN_JOIN_REJECT];
    size_t reject_len = 0;

    /* Positive build with custom auth_tag */
    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_build_reject(&engine, hello_raw, hello_len,
                                                          sample_tag, reject_wire, &reject_len));
    ASSERT_EQUAL_U32(20, (uint32_t)reject_len);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT, reject_wire[0]);
    ASSERT_EQUAL_INT(0x52, reject_wire[0]);
    ASSERT_EQUAL_MEM(hello.device_mac, &reject_wire[1], 6);
    ASSERT_EQUAL_INT(7, reject_wire[7]);
    ASSERT_EQUAL_MEM(sample_tag, &reject_wire[12], 8);

    /* Deserialize reject frame and verify */
    lora_mac_v2_down_join_reject_t parsed_reject;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_reject_deserialize(reject_wire, reject_len, &parsed_reject));
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT, parsed_reject.ver_type);
    ASSERT_EQUAL_MEM(hello.device_mac, parsed_reject.device_mac, 6);
    ASSERT_EQUAL_INT(7, parsed_reject.gw_id);
    ASSERT_EQUAL_U32(0x12345678, parsed_reject.join_counter);
    ASSERT_EQUAL_MEM(sample_tag, parsed_reject.auth_tag, 8);

    /* Build with NULL auth_tag -> zeroed */
    ASSERT_EQUAL_INT(ESP_OK, gateway_v2_join_build_reject(&engine, hello_raw, hello_len,
                                                          NULL, reject_wire, &reject_len));
    ASSERT_EQUAL_U32(20, (uint32_t)reject_len);
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_join_reject_deserialize(reject_wire, reject_len, &parsed_reject));
    ASSERT_EQUAL_MEM(zero_tag, parsed_reject.auth_tag, 8);

    /* Negative tests for reject */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_reject(NULL, hello_raw, hello_len, sample_tag, reject_wire, &reject_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_reject(&engine, NULL, hello_len, sample_tag, reject_wire, &reject_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_reject(&engine, hello_raw, hello_len, sample_tag, NULL, &reject_len));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, gateway_v2_join_build_reject(&engine, hello_raw, hello_len, sample_tag, reject_wire, NULL));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_SIZE, gateway_v2_join_build_reject(&engine, hello_raw, hello_len - 1, sample_tag, reject_wire, &reject_len));

    return 0;
}

/* =========================================================================
 * Main Runner
 * ========================================================================= */

int main(void)
{
    int failures = 0;
    printf("\n=== Running Firmware V2 OTA Join Handshake Unit Tests ===\n\n");

    TEST_RUN(test_join_frame_codecs_roundtrip);
    TEST_RUN(test_join_crypto_derivations_and_proofs);
    TEST_RUN(test_rfc7748_all_zeros_shared_secret_abort);
    TEST_RUN(test_monotonic_nvs_counter_commit_and_rollback_lockout);
    TEST_RUN(test_cad_retry_exhaustion);
    TEST_RUN(test_node_complete_handshake_end_to_end);
    TEST_RUN(test_node_wait_rx_continuous_indefinite_until_grant);
    TEST_RUN(test_gateway_relay_engine_and_mqtt_schema);
    TEST_RUN(test_gateway_v2_join_build_wait_and_reject);

    printf("\n=== Test Results: %s (Failures: %d) ===\n\n",
           (failures == 0) ? "ALL TESTS PASSED" : "TESTS FAILED", failures);

    return (failures == 0) ? 0 : 1;
}
