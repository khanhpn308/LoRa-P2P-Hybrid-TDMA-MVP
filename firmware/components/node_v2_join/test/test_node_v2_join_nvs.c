/**
 * @file test_node_v2_join_nvs.c
 * @brief Unit tests for Node V2 Join NVS session persistence and recovery (Issue #322).
 *
 * Authority: Issue #322, DEC-SEC-01, DEC-SEC-05, DEC-SEC-07, C Coding Standard v2.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "node_v2_join.h"
#include "lora_mac.h"
#include "lora_mac_join_crypto.h"
#include "nvs.h"
#include "nvs_flash.h"

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

#define ASSERT_EQUAL_MEM(ptr1, ptr2, len) do { \
    if (memcmp((ptr1), (ptr2), (len)) != 0) { \
        fprintf(stderr, "\nAssertion failed: memcmp(%s, %s, %u) == 0 at %s:%d\n", \
                #ptr1, #ptr2, (unsigned int)(len), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

static int test_nvs_empty_returns_not_found(void)
{
    (void)nvs_flash_erase();
    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    esp_err_t err = node_v2_join_load_session(&ctx);
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_UNJOINED, ctx.state);
    return 0;
}

static int test_nvs_save_and_load_roundtrip(void)
{
    (void)nvs_flash_erase();

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    ctx.state = NODE_V2_JOIN_STATE_INSTALLED_INACTIVE;
    ctx.assigned_node_id = 42U;
    for (uint8_t i = 0; i < 16; i++) {
        ctx.session_keys.k_session_up[i] = (uint8_t)(0x10 + i);
        ctx.session_keys.k_session_dl[i] = (uint8_t)(0x80 + i);
    }

    ASSERT_TRUE(node_v2_join_is_joined(&ctx));

    /* Save to NVS */
    esp_err_t save_err = node_v2_join_save_session(&ctx);
    ASSERT_EQUAL_INT(ESP_OK, save_err);

    /* Load into fresh context */
    node_v2_join_context_t recovered_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&recovered_ctx));
    esp_err_t load_err = node_v2_join_load_session(&recovered_ctx);
    ASSERT_EQUAL_INT(ESP_OK, load_err);

    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, recovered_ctx.state);
    ASSERT_EQUAL_INT(42U, recovered_ctx.assigned_node_id);
    ASSERT_EQUAL_MEM(ctx.session_keys.k_session_up, recovered_ctx.session_keys.k_session_up, 16);
    ASSERT_EQUAL_MEM(ctx.session_keys.k_session_dl, recovered_ctx.session_keys.k_session_dl, 16);
    ASSERT_TRUE(node_v2_join_is_joined(&recovered_ctx));

    return 0;
}

static int test_nvs_erase_session_preserves_counter(void)
{
    (void)nvs_flash_erase();

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    /* Commit join counter first (DEC-SEC-06) */
    uint32_t committed_ctr = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_commit_counter(&ctx, &committed_ctr));
    ASSERT_EQUAL_INT(1, (int)committed_ctr);

    /* Set up installed session */
    ctx.state = NODE_V2_JOIN_STATE_INSTALLED_INACTIVE;
    ctx.assigned_node_id = 7U;
    memset(ctx.session_keys.k_session_up, 0xAA, 16);
    memset(ctx.session_keys.k_session_dl, 0xBB, 16);
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_save_session(&ctx));

    /* Invalidate / erase session */
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_erase_session(&ctx));
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_UNJOINED, ctx.state);
    ASSERT_EQUAL_INT(0, ctx.assigned_node_id);
    ASSERT_TRUE(!node_v2_join_is_joined(&ctx));

    /* Verify load now fails */
    node_v2_join_context_t check_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&check_ctx));
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, node_v2_join_load_session(&check_ctx));

    /* Verify join counter in NVS was NOT wiped and cannot rollback */
    nvs_handle_t handle = 0;
    ASSERT_EQUAL_INT(ESP_OK, nvs_open(NODE_V2_JOIN_NVS_NAMESPACE, NVS_READONLY, &handle));
    uint32_t nvs_ctr = 0;
    ASSERT_EQUAL_INT(ESP_OK, nvs_get_u32(handle, NODE_V2_JOIN_NVS_KEY_COUNTER, &nvs_ctr));
    ASSERT_EQUAL_INT(1, (int)nvs_ctr);
    nvs_close(handle);

    return 0;
}

static int test_nvs_save_invalid_arguments_and_states(void)
{
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_v2_join_save_session(NULL));

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    /* State is UNJOINED */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, node_v2_join_save_session(&ctx));

    /* State is INSTALLED_INACTIVE but node_id is 0 */
    ctx.state = NODE_V2_JOIN_STATE_INSTALLED_INACTIVE;
    ctx.assigned_node_id = 0U;
    memset(ctx.session_keys.k_session_up, 0x55, 16);
    memset(ctx.session_keys.k_session_dl, 0x66, 16);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, node_v2_join_save_session(&ctx));

    /* State is INSTALLED_INACTIVE, node_id valid, but keys are all zeros */
    ctx.assigned_node_id = 10U;
    memset(ctx.session_keys.k_session_up, 0, 16);
    memset(ctx.session_keys.k_session_dl, 0, 16);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_v2_join_save_session(&ctx));

    return 0;
}

static int test_nvs_load_corrupted_keys_fails(void)
{
    (void)nvs_flash_erase();

    /* Manually write invalid (all zeros) keys with joined=1 */
    nvs_handle_t handle = 0;
    ASSERT_EQUAL_INT(ESP_OK, nvs_open(NODE_V2_JOIN_NVS_NAMESPACE, NVS_READWRITE, &handle));
    uint8_t zero_keys[16] = {0};
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_blob(handle, NODE_V2_JOIN_NVS_KEY_K_UP, zero_keys, 16));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_blob(handle, NODE_V2_JOIN_NVS_KEY_K_DL, zero_keys, 16));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_u32(handle, NODE_V2_JOIN_NVS_KEY_NODE_ID, 12U));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_u32(handle, NODE_V2_JOIN_NVS_KEY_JOINED, 1U));
    ASSERT_EQUAL_INT(ESP_OK, nvs_commit(handle));
    nvs_close(handle);

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));
    esp_err_t err = node_v2_join_load_session(&ctx);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, err);

    return 0;
}

static int test_cold_boot_recovery_bypasses_join_handshake(void)
{
    (void)nvs_flash_erase();

    /* 1. Simulate prior successful join saved to NVS */
    node_v2_join_context_t init_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&init_ctx));
    init_ctx.state = NODE_V2_JOIN_STATE_INSTALLED_INACTIVE;
    init_ctx.assigned_node_id = 42U;
    for (uint8_t i = 0; i < 16; i++) {
        init_ctx.session_keys.k_session_up[i] = (uint8_t)(0xA0 + i);
        init_ctx.session_keys.k_session_dl[i] = (uint8_t)(0xB0 + i);
    }
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_save_session(&init_ctx));

    /* 2. Simulate Cold Boot (power loss / reset): clean context */
    node_v2_join_context_t boot_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&boot_ctx));
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_UNJOINED, boot_ctx.state);
    ASSERT_TRUE(!node_v2_join_is_joined(&boot_ctx));

    /* 3. Execute recovery check in app_main */
    esp_err_t load_err = node_v2_join_load_session(&boot_ctx);
    ASSERT_EQUAL_INT(ESP_OK, load_err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, boot_ctx.state);
    ASSERT_EQUAL_INT(42U, boot_ctx.assigned_node_id);
    ASSERT_TRUE(node_v2_join_is_joined(&boot_ctx));
    ASSERT_EQUAL_MEM(init_ctx.session_keys.k_session_up, boot_ctx.session_keys.k_session_up, 16);
    ASSERT_EQUAL_MEM(init_ctx.session_keys.k_session_dl, boot_ctx.session_keys.k_session_dl, 16);

    /* 4. Verify OTA V2 Join campaign condition evaluates to false (handshake bypassed) */
    bool ota_join_campaign_required = (boot_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE);
    ASSERT_TRUE(!ota_join_campaign_required);

    return 0;
}

static int test_cold_boot_unjoined_requires_join_handshake(void)
{
    (void)nvs_flash_erase();

    /* Cold boot without any prior session */
    node_v2_join_context_t boot_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&boot_ctx));
    esp_err_t load_err = node_v2_join_load_session(&boot_ctx);
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, load_err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_UNJOINED, boot_ctx.state);
    ASSERT_TRUE(!node_v2_join_is_joined(&boot_ctx));

    /* OTA join handshake must be triggered */
    bool ota_join_campaign_required = (boot_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE);
    ASSERT_TRUE(ota_join_campaign_required);

    return 0;
}

static int test_cold_boot_joined_zero_flag_requires_join(void)
{
    (void)nvs_flash_erase();

    /* Write joined=0 explicitly in NVS */
    nvs_handle_t handle = 0;
    ASSERT_EQUAL_INT(ESP_OK, nvs_open(NODE_V2_JOIN_NVS_NAMESPACE, NVS_READWRITE, &handle));
    uint8_t dummy_key[16] = {0x01, 0x02, 0x03, 0x04};
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_blob(handle, NODE_V2_JOIN_NVS_KEY_K_UP, dummy_key, 16));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_blob(handle, NODE_V2_JOIN_NVS_KEY_K_DL, dummy_key, 16));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_u32(handle, NODE_V2_JOIN_NVS_KEY_NODE_ID, 5U));
    ASSERT_EQUAL_INT(ESP_OK, nvs_set_u32(handle, NODE_V2_JOIN_NVS_KEY_JOINED, 0U));
    ASSERT_EQUAL_INT(ESP_OK, nvs_commit(handle));
    nvs_close(handle);

    node_v2_join_context_t boot_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&boot_ctx));
    esp_err_t load_err = node_v2_join_load_session(&boot_ctx);
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, load_err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_UNJOINED, boot_ctx.state);
    ASSERT_TRUE(!node_v2_join_is_joined(&boot_ctx));

    bool ota_join_campaign_required = (boot_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE);
    ASSERT_TRUE(ota_join_campaign_required);

    return 0;
}

/* =========================================================================
 * Issue #340: Button Join, DOWN_JOIN_WAIT and DOWN_JOIN_REJECT Unit Tests
 * ========================================================================= */

typedef enum {
    MOCK_SCENARIO_WAIT_THEN_GRANT = 0,
    MOCK_SCENARIO_WAIT_THEN_REJECT,
    MOCK_SCENARIO_DIRECT_REJECT,
    MOCK_SCENARIO_WAIT_TIMEOUTS_NOISE_THEN_GRANT,
} mock_scenario_t;

static mock_scenario_t s_mock_scenario = MOCK_SCENARIO_WAIT_THEN_GRANT;
static size_t s_mock_step = 0;
static uint8_t s_last_tx[128];
static size_t s_last_tx_len = 0;
static uint32_t s_sleep_calls = 0;
static uint32_t s_rx_single_calls = 0;
static uint32_t s_standby_calls = 0;
static uint32_t s_delay_calls = 0;
static uint32_t s_standby_during_wait = 0;
static uint32_t s_rx_single_during_wait = 0;
static uint32_t s_delay_during_wait = 0;
static node_v2_join_config_t s_mock_peer_cfg;
static lora_mac_k_join_expanded_keys_t s_mock_peer_k_join_keys;
static uint8_t s_mock_th[32];
static lora_mac_session_keys_t s_mock_peer_session_keys;

static esp_err_t mock_radio_cad(bool *out_activity_detected)
{
    if (out_activity_detected != NULL) {
        *out_activity_detected = false;
    }
    return ESP_OK;
}

static esp_err_t mock_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (payload == NULL || length > sizeof(s_last_tx)) {
        return ESP_ERR_INVALID_ARG;
    }
    memcpy(s_last_tx, payload, length);
    s_last_tx_len = length;
    return ESP_OK;
}

static esp_err_t mock_radio_sleep(void)
{
    s_sleep_calls++;
    return ESP_OK;
}

static esp_err_t mock_radio_rx_single(uint32_t window_ms)
{
    (void)window_ms;
    s_rx_single_calls++;
    return ESP_OK;
}

static esp_err_t mock_radio_standby(void)
{
    s_standby_calls++;
    return ESP_OK;
}

static void mock_delay_ms(uint32_t ms)
{
    (void)ms;
    s_delay_calls++;
}

static esp_err_t mock_radio_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    (void)wait_ms;
    if (out_buf == NULL || out_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_mock_scenario == MOCK_SCENARIO_DIRECT_REJECT) {
        if (s_last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
            return ESP_ERR_INVALID_SIZE;
        }
        lora_mac_v2_up_join_hello_t hello;
        if (lora_mac_v2_up_join_hello_deserialize(s_last_tx, s_last_tx_len, &hello) != ESP_OK) {
            return ESP_ERR_INVALID_ARG;
        }
        lora_mac_v2_down_join_reject_t reject;
        memset(&reject, 0, sizeof(reject));
        reject.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT;
        memcpy(reject.device_mac, hello.device_mac, 6);
        reject.gw_id = hello.target_gw_id;
        reject.join_counter = hello.join_counter;
        memset(reject.auth_tag, 0xEE, sizeof(reject.auth_tag));

        size_t written = 0;
        esp_err_t ser_err = lora_mac_v2_down_join_reject_serialize(&reject, out_buf, 128, &written);
        if (ser_err != ESP_OK) {
            return ser_err;
        }
        *out_len = written;
        return ESP_OK;
    }

    if (s_mock_scenario == MOCK_SCENARIO_WAIT_THEN_REJECT) {
        if (s_mock_step == 0) {
            if (s_last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
                return ESP_ERR_INVALID_SIZE;
            }
            lora_mac_v2_up_join_hello_t hello;
            if (lora_mac_v2_up_join_hello_deserialize(s_last_tx, s_last_tx_len, &hello) != ESP_OK) {
                return ESP_ERR_INVALID_ARG;
            }
            lora_mac_v2_down_join_wait_t wait_frame;
            memset(&wait_frame, 0, sizeof(wait_frame));
            wait_frame.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT;
            memcpy(wait_frame.device_mac, hello.device_mac, 6);
            wait_frame.gw_id = hello.target_gw_id;
            wait_frame.join_counter = hello.join_counter;
            memset(wait_frame.auth_tag, 0x51, sizeof(wait_frame.auth_tag));

            size_t written = 0;
            esp_err_t ser_err = lora_mac_v2_down_join_wait_serialize(&wait_frame, out_buf, 128, &written);
            if (ser_err != ESP_OK) {
                return ser_err;
            }
            *out_len = written;
            s_mock_step = 1;
            return ESP_OK;
        } else if (s_mock_step == 1) {
            lora_mac_v2_up_join_hello_t hello;
            if (lora_mac_v2_up_join_hello_deserialize(s_last_tx, s_last_tx_len, &hello) != ESP_OK) {
                return ESP_ERR_INVALID_ARG;
            }
            lora_mac_v2_down_join_reject_t reject;
            memset(&reject, 0, sizeof(reject));
            reject.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_REJECT;
            memcpy(reject.device_mac, hello.device_mac, 6);
            reject.gw_id = hello.target_gw_id;
            reject.join_counter = hello.join_counter;
            memset(reject.auth_tag, 0x52, sizeof(reject.auth_tag));

            size_t written = 0;
            esp_err_t ser_err = lora_mac_v2_down_join_reject_serialize(&reject, out_buf, 128, &written);
            if (ser_err != ESP_OK) {
                return ser_err;
            }
            *out_len = written;
            s_mock_step = 2;
            return ESP_OK;
        }
    }

    if (s_mock_scenario == MOCK_SCENARIO_WAIT_TIMEOUTS_NOISE_THEN_GRANT) {
        if (s_mock_step >= 100 && s_mock_step < 110) {
            s_mock_step++;
            return ESP_ERR_TIMEOUT;
        } else if (s_mock_step == 111) {
            memset(out_buf, 0, 26);
            out_buf[0] = LORA_MAC_V2_TYPE_UP_EVENT;
            *out_len = 26;
            s_mock_step = 112;
            return ESP_OK;
        } else if (s_mock_step == 112) {
            s_standby_during_wait = s_standby_calls;
            s_rx_single_during_wait = s_rx_single_calls;
            s_delay_during_wait = s_delay_calls;
            s_mock_scenario = MOCK_SCENARIO_WAIT_THEN_GRANT;
            s_mock_step = 1;
        }
    }

    if (s_mock_scenario == MOCK_SCENARIO_WAIT_THEN_GRANT ||
        s_mock_scenario == MOCK_SCENARIO_WAIT_TIMEOUTS_NOISE_THEN_GRANT) {
        if (s_mock_step == 0 || s_mock_step == 110) {
            if (s_last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
                return ESP_ERR_INVALID_SIZE;
            }
            lora_mac_v2_up_join_hello_t hello;
            if (lora_mac_v2_up_join_hello_deserialize(s_last_tx, s_last_tx_len, &hello) != ESP_OK) {
                return ESP_ERR_INVALID_ARG;
            }
            lora_mac_v2_down_join_wait_t wait_frame;
            memset(&wait_frame, 0, sizeof(wait_frame));
            wait_frame.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_WAIT;
            memcpy(wait_frame.device_mac, hello.device_mac, 6);
            wait_frame.gw_id = hello.target_gw_id;
            wait_frame.join_counter = hello.join_counter;
            memset(wait_frame.auth_tag, 0x51, sizeof(wait_frame.auth_tag));

            size_t written = 0;
            esp_err_t ser_err = lora_mac_v2_down_join_wait_serialize(&wait_frame, out_buf, 128, &written);
            if (ser_err != ESP_OK) {
                return ser_err;
            }
            *out_len = written;
            if (s_mock_scenario == MOCK_SCENARIO_WAIT_TIMEOUTS_NOISE_THEN_GRANT) {
                s_mock_step = (s_mock_step == 0) ? 100 : 111;
            } else {
                s_mock_step = 1;
            }
            return ESP_OK;
        } else if (s_mock_step == 1) {
            lora_mac_v2_up_join_hello_t hello;
            if (lora_mac_v2_up_join_hello_deserialize(s_last_tx, s_last_tx_len, &hello) != ESP_OK) {
                return ESP_ERR_INVALID_ARG;
            }
            lora_mac_v2_down_join_grant_t grant;
            memset(&grant, 0, sizeof(grant));
            grant.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT;
            memcpy(grant.device_mac, hello.device_mac, 6);
            grant.node_id = 9U;
            grant.join_counter = hello.join_counter;
            for (int i = 0; i < 6; i++) {
                grant.gw_nonce[i] = (uint8_t)(i + 0x40);
            }

            uint8_t priv_gw[32], pub_gw[32];
            lora_mac_crypto_x25519_keypair(priv_gw, pub_gw);
            memcpy(grant.gw_x25519_pub, pub_gw, 32);

            uint8_t z[32];
            lora_mac_crypto_x25519_ecdh(priv_gw, hello.node_x25519_pub, z);

            uint8_t grant_wire[66];
            size_t wr = 0;
            lora_mac_v2_down_join_grant_serialize(&grant, grant_wire, sizeof(grant_wire), &wr);

            lora_mac_join_compute_grant_proof(s_mock_peer_cfg.network_id, s_last_tx, grant_wire,
                                             s_mock_peer_k_join_keys.k_jgrant, grant.grant_proof);
            lora_mac_v2_down_join_grant_serialize(&grant, grant_wire, sizeof(grant_wire), &wr);

            lora_mac_join_compute_th(s_mock_peer_cfg.network_id, s_last_tx, grant_wire, s_mock_th);
            lora_mac_join_derive_session_keys(s_mock_th, z, &s_mock_peer_session_keys);

            memcpy(out_buf, grant_wire, 66);
            *out_len = 66;
            s_mock_step = 2;
            return ESP_OK;
        } else if (s_mock_step == 2) {
            if (s_last_tx_len != LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF) {
                return ESP_ERR_INVALID_SIZE;
            }
            lora_mac_v2_up_join_key_confirm_t conf;
            if (lora_mac_v2_up_join_key_confirm_deserialize(s_last_tx, s_last_tx_len, &conf) != ESP_OK) {
                return ESP_ERR_INVALID_ARG;
            }
            lora_mac_v2_down_join_finish_t finish;
            memset(&finish, 0, sizeof(finish));
            finish.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH;
            finish.gw_id = conf.gw_id;
            finish.node_id = conf.node_id;
            finish.join_counter = conf.join_counter;

            uint8_t finish_prefix7[7] = {
                finish.ver_type, finish.gw_id, finish.node_id,
                (uint8_t)(finish.join_counter >> 24), (uint8_t)(finish.join_counter >> 16),
                (uint8_t)(finish.join_counter >> 8), (uint8_t)(finish.join_counter)
            };
            lora_mac_join_compute_finish_tags(s_mock_peer_cfg.network_id, s_mock_th, finish_prefix7,
                                             s_mock_peer_session_keys.k_kc_down, s_mock_peer_k_join_keys.k_jfinish,
                                             finish.gw_finish_tag, finish.backend_finish_proof);

            uint8_t finish_wire[31];
            size_t wr = 0;
            lora_mac_v2_down_join_finish_serialize(&finish, finish_wire, sizeof(finish_wire), &wr);
            memcpy(out_buf, finish_wire, 31);
            *out_len = 31;
            s_mock_step = 3;
            return ESP_OK;
        }
    }

    return ESP_ERR_TIMEOUT;
}

static int test_node_v2_join_state_strings(void)
{
    ASSERT_TRUE(strcmp("UNJOINED", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_UNJOINED)) == 0);
    ASSERT_TRUE(strcmp("CAD_EVAL", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_CAD_EVAL)) == 0);
    ASSERT_TRUE(strcmp("COUNTER_COMMIT", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_COUNTER_COMMIT)) == 0);
    ASSERT_TRUE(strcmp("HELLO_TX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_HELLO_TX)) == 0);
    ASSERT_TRUE(strcmp("GRANT_RX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_GRANT_RX)) == 0);
    ASSERT_TRUE(strcmp("WAIT_RX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_WAIT_RX)) == 0);
    ASSERT_TRUE(strcmp("CONFIRM_TX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_CONFIRM_TX)) == 0);
    ASSERT_TRUE(strcmp("FINISH_RX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_FINISH_RX)) == 0);
    ASSERT_TRUE(strcmp("READY_TX", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_READY_TX)) == 0);
    ASSERT_TRUE(strcmp("INSTALLED_INACTIVE", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE)) == 0);
    ASSERT_TRUE(strcmp("ABORTED", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_ABORTED)) == 0);
    ASSERT_TRUE(strcmp("LOCKED_OUT", node_v2_join_state_to_str(NODE_V2_JOIN_STATE_LOCKED_OUT)) == 0);
    ASSERT_TRUE(strcmp("UNKNOWN", node_v2_join_state_to_str((node_v2_join_state_t)999)) == 0);
    return 0;
}

static int test_node_v2_join_reject_helper(void)
{
    ASSERT_TRUE(!node_v2_join_is_rejected(NULL));

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));
    ASSERT_TRUE(!node_v2_join_is_rejected(&ctx));

    ctx.join_rejected = true;
    ASSERT_TRUE(node_v2_join_is_rejected(&ctx));

    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_erase_session(&ctx));
    ASSERT_TRUE(!node_v2_join_is_rejected(&ctx));
    return 0;
}

static int test_node_v2_join_direct_reject(void)
{
    (void)nvs_flash_erase();
    s_mock_scenario = MOCK_SCENARIO_DIRECT_REJECT;
    s_mock_step = 0;
    s_last_tx_len = 0;
    s_sleep_calls = 0;

    node_v2_join_config_t cfg;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_get_default_config(&cfg));
    for (int i = 0; i < 32; i++) {
        cfg.k_join[i] = (uint8_t)(0x33 + i);
    }

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_radio_cad;
    hal.radio_tx = mock_radio_tx;
    hal.radio_read_frame = mock_radio_read_frame;
    hal.radio_sleep = mock_radio_sleep;
    hal.radio_rx_single = mock_radio_rx_single;
    hal.radio_standby = mock_radio_standby;
    hal.delay_ms = mock_delay_ms;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    esp_err_t err = node_v2_join_run(&cfg, &hal, &ctx);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_RESPONSE, err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_ABORTED, ctx.state);
    ASSERT_TRUE(node_v2_join_is_rejected(&ctx));
    ASSERT_TRUE(!node_v2_join_is_joined(&ctx));
    ASSERT_TRUE(s_sleep_calls > 0);
    return 0;
}

static int test_node_v2_join_wait_then_reject(void)
{
    (void)nvs_flash_erase();
    s_mock_scenario = MOCK_SCENARIO_WAIT_THEN_REJECT;
    s_mock_step = 0;
    s_last_tx_len = 0;
    s_sleep_calls = 0;

    node_v2_join_config_t cfg;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_get_default_config(&cfg));
    for (int i = 0; i < 32; i++) {
        cfg.k_join[i] = (uint8_t)(0x44 + i);
    }

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_radio_cad;
    hal.radio_tx = mock_radio_tx;
    hal.radio_read_frame = mock_radio_read_frame;
    hal.radio_sleep = mock_radio_sleep;
    hal.radio_rx_single = mock_radio_rx_single;
    hal.radio_standby = mock_radio_standby;
    hal.delay_ms = mock_delay_ms;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    esp_err_t err = node_v2_join_run(&cfg, &hal, &ctx);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_RESPONSE, err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_ABORTED, ctx.state);
    ASSERT_TRUE(node_v2_join_is_rejected(&ctx));
    ASSERT_TRUE(!node_v2_join_is_joined(&ctx));
    ASSERT_TRUE(s_sleep_calls > 0);
    return 0;
}

static int test_node_v2_join_wait_then_grant(void)
{
    (void)nvs_flash_erase();
    s_mock_scenario = MOCK_SCENARIO_WAIT_THEN_GRANT;
    s_mock_step = 0;
    s_last_tx_len = 0;
    s_sleep_calls = 0;

    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_get_default_config(&s_mock_peer_cfg));
    for (int i = 0; i < 32; i++) {
        s_mock_peer_cfg.k_join[i] = (uint8_t)(0x55 + i);
    }

    lora_mac_join_derive_k_join_keys(s_mock_peer_cfg.network_id, s_mock_peer_cfg.device_mac,
                                     s_mock_peer_cfg.device_generation, s_mock_peer_cfg.k_join,
                                     &s_mock_peer_k_join_keys);

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_radio_cad;
    hal.radio_tx = mock_radio_tx;
    hal.radio_read_frame = mock_radio_read_frame;
    hal.radio_sleep = mock_radio_sleep;
    hal.radio_rx_single = mock_radio_rx_single;
    hal.radio_standby = mock_radio_standby;
    hal.delay_ms = mock_delay_ms;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    esp_err_t err = node_v2_join_run(&s_mock_peer_cfg, &hal, &ctx);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, ctx.state);
    ASSERT_TRUE(node_v2_join_is_joined(&ctx));
    ASSERT_TRUE(!node_v2_join_is_rejected(&ctx));
    ASSERT_EQUAL_INT(9U, ctx.assigned_node_id);
    ASSERT_EQUAL_MEM(s_mock_peer_session_keys.k_session_up, ctx.session_keys.k_session_up, 16);
    ASSERT_EQUAL_MEM(s_mock_peer_session_keys.k_session_dl, ctx.session_keys.k_session_dl, 16);

    /* Verify session persistence to NVS */
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_save_session(&ctx));

    node_v2_join_context_t loaded_ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&loaded_ctx));
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_load_session(&loaded_ctx));
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, loaded_ctx.state);
    ASSERT_EQUAL_INT(9U, loaded_ctx.assigned_node_id);
    ASSERT_TRUE(node_v2_join_is_joined(&loaded_ctx));

    return 0;
}

static int test_node_v2_join_wait_rx_keeps_continuous_rx(void)
{
    (void)nvs_flash_erase();
    s_mock_scenario = MOCK_SCENARIO_WAIT_TIMEOUTS_NOISE_THEN_GRANT;
    s_mock_step = 0;
    s_last_tx_len = 0;
    s_sleep_calls = 0;
    s_rx_single_calls = 0;
    s_standby_calls = 0;
    s_delay_calls = 0;
    s_standby_during_wait = 0;
    s_rx_single_during_wait = 0;
    s_delay_during_wait = 0;

    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_get_default_config(&s_mock_peer_cfg));
    for (int i = 0; i < 32; i++) {
        s_mock_peer_cfg.k_join[i] = (uint8_t)(0x66 + i);
    }

    lora_mac_join_derive_k_join_keys(s_mock_peer_cfg.network_id, s_mock_peer_cfg.device_mac,
                                     s_mock_peer_cfg.device_generation, s_mock_peer_cfg.k_join,
                                     &s_mock_peer_k_join_keys);

    node_v2_join_radio_hal_t hal;
    memset(&hal, 0, sizeof(hal));
    hal.radio_cad = mock_radio_cad;
    hal.radio_tx = mock_radio_tx;
    hal.radio_read_frame = mock_radio_read_frame;
    hal.radio_sleep = mock_radio_sleep;
    hal.radio_rx_single = mock_radio_rx_single;
    hal.radio_standby = mock_radio_standby;
    hal.delay_ms = mock_delay_ms;

    node_v2_join_context_t ctx;
    ASSERT_EQUAL_INT(ESP_OK, node_v2_join_init(&ctx));

    esp_err_t err = node_v2_join_run(&s_mock_peer_cfg, &hal, &ctx);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_EQUAL_INT(NODE_V2_JOIN_STATE_INSTALLED_INACTIVE, ctx.state);
    ASSERT_EQUAL_INT(9U, ctx.assigned_node_id);

    /* Continuous RXCONT was never interrupted by standby/rx_single/delay during WAIT_RX */
    ASSERT_EQUAL_INT(0, (int)s_standby_during_wait);
    ASSERT_EQUAL_INT(1, (int)s_rx_single_during_wait);
    ASSERT_EQUAL_INT(0, (int)s_delay_during_wait);
    ASSERT_EQUAL_INT(2, (int)s_rx_single_calls);
    ASSERT_EQUAL_INT(2, (int)s_standby_calls);

    return 0;
}

int main(void)
{
    int failures = 0;
    printf("\n=== Running Node V2 Join NVS Persistence Unit Tests ===\n\n");

    TEST_RUN(test_nvs_empty_returns_not_found);
    TEST_RUN(test_nvs_save_and_load_roundtrip);
    TEST_RUN(test_nvs_erase_session_preserves_counter);
    TEST_RUN(test_nvs_save_invalid_arguments_and_states);
    TEST_RUN(test_nvs_load_corrupted_keys_fails);
    TEST_RUN(test_cold_boot_recovery_bypasses_join_handshake);
    TEST_RUN(test_cold_boot_unjoined_requires_join_handshake);
    TEST_RUN(test_cold_boot_joined_zero_flag_requires_join);
    TEST_RUN(test_node_v2_join_state_strings);
    TEST_RUN(test_node_v2_join_reject_helper);
    TEST_RUN(test_node_v2_join_direct_reject);
    TEST_RUN(test_node_v2_join_wait_then_reject);
    TEST_RUN(test_node_v2_join_wait_then_grant);
    TEST_RUN(test_node_v2_join_wait_rx_keeps_continuous_rx);

    printf("\n=== Test Results: %s (Failures: %d) ===\n\n",
           (failures == 0) ? "ALL TESTS PASSED" : "TESTS FAILED", failures);

    return (failures == 0) ? 0 : 1;
}
