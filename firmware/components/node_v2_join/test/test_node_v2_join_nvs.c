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

    printf("\n=== Test Results: %s (Failures: %d) ===\n\n",
           (failures == 0) ? "ALL TESTS PASSED" : "TESTS FAILED", failures);

    return (failures == 0) ? 0 : 1;
}
