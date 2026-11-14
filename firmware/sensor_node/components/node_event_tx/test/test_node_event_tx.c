/**
 * @file test_node_event_tx.c
 * @brief Unit tests for Node Event TX and explicit ACK indicator logic.
 *
 * Authority: Issue #396, C Coding Standard v2.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "esp_err.h"
#include "node_event_fifo.h"
#include "node_event_tx.h"
#include "lora_mac.h"

/* Assert macros */
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

/* Mock state */
typedef enum {
    MOCK_SCENARIO_SUCCESS_ACK,
    MOCK_SCENARIO_FIFO_ACK_FAIL,
    MOCK_SCENARIO_CAD_BUSY,
    MOCK_SCENARIO_TX_FAIL,
    MOCK_SCENARIO_ACK_TIMEOUT,
    MOCK_SCENARIO_DOWN_REVOKE,
    MOCK_SCENARIO_REF_MISMATCH,
    MOCK_SCENARIO_CORRUPT_HEADER,
} mock_scenario_t;

static mock_scenario_t s_scenario = MOCK_SCENARIO_SUCCESS_ACK;
static uint32_t s_mock_target_ack_ref = 1;
static node_event_fifo_t *s_test_fifo_hook = NULL;

/* Mock sx1276_driver functions */
esp_err_t sx1276_cad(bool *activity_detected, uint32_t timeout_ticks)
{
    (void)timeout_ticks;
    if (s_scenario == MOCK_SCENARIO_CAD_BUSY) {
        *activity_detected = true;
    } else {
        *activity_detected = false;
    }
    return ESP_OK;
}

esp_err_t sx1276_tx(const uint8_t *data, size_t len, uint32_t timeout_ticks)
{
    (void)data;
    (void)len;
    (void)timeout_ticks;
    if (s_scenario == MOCK_SCENARIO_TX_FAIL) {
        return ESP_ERR_TIMEOUT;
    }
    return ESP_OK;
}

esp_err_t sx1276_standby(void)
{
    return ESP_OK;
}

esp_err_t sx1276_sleep(void)
{
    return ESP_OK;
}

/* Mock backoff / hal functions */
uint32_t node_get_cad_contention_window_ms(uint8_t attempt)
{
    (void)attempt;
    return 16;
}

uint32_t node_calculate_cad_backoff_ms(uint8_t attempt)
{
    (void)attempt;
    return 10;
}

esp_err_t node_smart_backoff(uint32_t duration_ms)
{
    (void)duration_ms;
    return ESP_OK;
}

esp_err_t node_radio_hal_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    return ESP_OK;
}

esp_err_t node_radio_hal_read_frame(uint8_t *buffer, size_t *out_length, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (s_scenario == MOCK_SCENARIO_ACK_TIMEOUT || s_scenario == MOCK_SCENARIO_CAD_BUSY || s_scenario == MOCK_SCENARIO_TX_FAIL) {
        return ESP_ERR_TIMEOUT;
    }

    if (s_scenario == MOCK_SCENARIO_CORRUPT_HEADER) {
        memset(buffer, 0, 19);
        *out_length = 19;
        return ESP_OK;
    }

    if (s_scenario == MOCK_SCENARIO_DOWN_REVOKE) {
        /* Construct a valid 19-byte DOWN_REVOKE frame: 7B hdr, 4B ct, 8B tag */
        buffer[0] = (uint8_t)(LORA_MAC_V2_TYPE_DOWN_REVOKE & 0xFF);
        buffer[1] = 1; /* node_id */
        buffer[2] = 0; /* session_sel */
        buffer[3] = 1; buffer[4] = 0; buffer[5] = 0; buffer[6] = 0; /* frame_counter */
        memset(&buffer[7], 0xAA, 4); /* ciphertext */
        memset(&buffer[11], 0xBB, 8); /* MIC/tag */
        *out_length = 19;
        return ESP_OK;
    }

    if (s_scenario == MOCK_SCENARIO_FIFO_ACK_FAIL && s_test_fifo_hook != NULL) {
        /* Simulate concurrent purge/corruption right before ACK evaluation */
        s_test_fifo_hook->count = 0;
    }

    /* Nominal DOWN_EVENT_ACK frame: 7B hdr, 4B ct, 8B tag */
    buffer[0] = (uint8_t)(LORA_MAC_V2_TYPE_DOWN_EVENT_ACK & 0xFF);
    buffer[1] = 1; /* node_id */
    buffer[2] = 0; /* session_sel */
    buffer[3] = 1; buffer[4] = 0; buffer[5] = 0; buffer[6] = 0; /* frame_counter */
    memset(&buffer[7], 0xAA, 4); /* ciphertext */
    memset(&buffer[11], 0xBB, 8); /* MIC/tag */
    *out_length = 19;
    return ESP_OK;
}

bool node_arq_should_retry(uint8_t current_retry, uint8_t max_retries)
{
    return current_retry < max_retries;
}

uint32_t node_calculate_arq_backoff_ms(void)
{
    return 10;
}

esp_err_t node_reset_sx1276_fifo_tx_ptr(void)
{
    return ESP_OK;
}

/* Mock crypto functions */
esp_err_t lora_mac_crypto_encrypt_up_event(const uint8_t *key, const uint8_t *nonce,
                                          const uint8_t *aad, size_t aad_len,
                                          const uint8_t *plaintext, size_t pt_len,
                                          uint8_t *ciphertext, uint8_t *tag)
{
    (void)key; (void)nonce; (void)aad; (void)aad_len;
    memcpy(ciphertext, plaintext, pt_len);
    memset(tag, 0xCC, 8);
    return ESP_OK;
}

void lora_mac_crypto_zeroize(void *buf, size_t len)
{
    if (buf && len > 0) {
        memset(buf, 0, len);
    }
}

esp_err_t lora_mac_crypto_decrypt_down_ack(const uint8_t *key, const uint8_t *nonce,
                                          const uint8_t *aad, size_t aad_len,
                                          const uint8_t *ciphertext, size_t ct_len,
                                          const uint8_t *tag, uint8_t *plaintext)
{
    (void)key; (void)nonce; (void)aad; (void)aad_len; (void)ciphertext; (void)ct_len; (void)tag;
    /* Deserialize will read 4 bytes for event_ref */
    uint32_t ref = (s_scenario == MOCK_SCENARIO_REF_MISMATCH) ? 9999 : s_mock_target_ack_ref;
    plaintext[0] = (uint8_t)((ref >> 24) & 0xFF);
    plaintext[1] = (uint8_t)((ref >> 16) & 0xFF);
    plaintext[2] = (uint8_t)((ref >> 8) & 0xFF);
    plaintext[3] = (uint8_t)(ref & 0xFF);
    return ESP_OK;
}

esp_err_t lora_mac_crypto_decrypt_down_revoke(const uint8_t *key, const uint8_t *nonce,
                                             const uint8_t *aad, size_t aad_len,
                                             const uint8_t *ciphertext, size_t ct_len,
                                             const uint8_t *tag, uint8_t *plaintext)
{
    (void)key; (void)nonce; (void)aad; (void)aad_len; (void)ciphertext; (void)ct_len; (void)tag;
    memset(plaintext, 0, 4);
    return ESP_OK;
}

/* Unit Tests */
static int test_arg_validation(void)
{
    node_mac_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    node_event_fifo_t fifo;
    memset(&fifo, 0, sizeof(fifo));
    uint32_t counter = 0;
    bool acked = false;

    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_cad_event_tx_and_ack(NULL, &fifo, &counter, &acked));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_cad_event_tx_and_ack(&cfg, NULL, &counter, &acked));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_cad_event_tx_and_ack(&cfg, &fifo, NULL, &acked));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_cad_event_tx_and_ack(&cfg, &fifo, &counter, NULL));

    return 0;
}

static int test_empty_fifo(void)
{
    node_mac_config_t cfg;
    memset(&cfg, 0, sizeof(cfg));
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t counter = 0;
    bool acked = true;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_TRUE(!acked);
    ASSERT_EQUAL_INT(0, (int)counter);

    return 0;
}

static int test_cad_busy_timeout(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = true;
    s_scenario = MOCK_SCENARIO_CAD_BUSY;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_ERR_TIMEOUT, err);
    ASSERT_TRUE(!acked);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    return 0;
}

static int test_tx_fail_timeout(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = true;
    s_scenario = MOCK_SCENARIO_TX_FAIL;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_ERR_TIMEOUT, err);
    ASSERT_TRUE(!acked);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    return 0;
}

static int test_down_revoke(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = true;
    s_scenario = MOCK_SCENARIO_DOWN_REVOKE;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, err);
    ASSERT_TRUE(!acked);

    return 0;
}

static int test_successful_ack(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = false;
    s_scenario = MOCK_SCENARIO_SUCCESS_ACK;
    s_mock_target_ack_ref = 1;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_TRUE(acked);
    ASSERT_EQUAL_INT(0, (int)node_event_fifo_get_pending_count(&fifo));

    return 0;
}

static int test_multi_event_fifo_partial_ack(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));

    uint32_t ref1 = 0;
    uint32_t ref2 = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref1));
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 101, 0x01, 95, &ref2));
    ASSERT_EQUAL_INT(2, (int)node_event_fifo_get_pending_count(&fifo));

    uint32_t counter = 0;
    bool acked = false;
    s_scenario = MOCK_SCENARIO_SUCCESS_ACK;
    s_mock_target_ack_ref = 1;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_TRUE(acked);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    /* Verify remaining item in FIFO is Ref 2 */
    node_event_fifo_item_t item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_INT(2, (int)item.event_ref);

    return 0;
}

static int test_fifo_ack_failure_non_fatal(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = true;
    s_scenario = MOCK_SCENARIO_FIFO_ACK_FAIL;
    s_mock_target_ack_ref = 1;
    s_test_fifo_hook = &fifo;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    s_test_fifo_hook = NULL;

    /* Must return the error code from FIFO ACK, not ESP_OK and not ESP_ERR_INVALID_STATE */
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, err);
    ASSERT_TRUE(!acked);

    return 0;
}

static int test_negative_ref_mismatch_no_ack(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = false;
    s_scenario = MOCK_SCENARIO_REF_MISMATCH;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_ERR_TIMEOUT, err);
    ASSERT_TRUE(!acked);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    return 0;
}

static int test_negative_corrupt_header_no_ack(void)
{
    node_mac_config_t cfg = { .node_id = 1, .gw_id = 1, .session_sel = 0 };
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 100, 0x01, 88, &ref));

    uint32_t counter = 0;
    bool acked = false;
    s_scenario = MOCK_SCENARIO_CORRUPT_HEADER;

    esp_err_t err = node_cad_event_tx_and_ack(&cfg, &fifo, &counter, &acked);
    ASSERT_EQUAL_INT(ESP_ERR_TIMEOUT, err);
    ASSERT_TRUE(!acked);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    return 0;
}

#define TEST_RUN(name) do { \
    printf("Running %s ... ", #name); \
    if (name() == 0) { \
        printf("PASSED\n"); \
    } else { \
        printf("FAILED\n"); \
        failures++; \
    } \
} while (0)

int main(void)
{
    int failures = 0;
    printf("=== Running Node Event TX Unit Tests ===\n");

    TEST_RUN(test_arg_validation);
    TEST_RUN(test_empty_fifo);
    TEST_RUN(test_cad_busy_timeout);
    TEST_RUN(test_tx_fail_timeout);
    TEST_RUN(test_down_revoke);
    TEST_RUN(test_successful_ack);
    TEST_RUN(test_multi_event_fifo_partial_ack);
    TEST_RUN(test_fifo_ack_failure_non_fatal);
    TEST_RUN(test_negative_ref_mismatch_no_ack);
    TEST_RUN(test_negative_corrupt_header_no_ack);

    printf("\nTest summary: %s (%d failures)\n", failures == 0 ? "ALL PASSED" : "FAILED", failures);
    return failures;
}
