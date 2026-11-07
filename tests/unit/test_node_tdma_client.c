/**
 * @file test_node_tdma_client.c
 * @brief Unit tests for Sensor Node V2 Static TDMA Slot Client and Event Transmission Loop.
 *
 * Authority: Issue #239, C Coding Standard v2, contracts/radio-mac/specification.md,
 *            contracts/radio-mac/tdma-schedule.md.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "node_tdma_client.h"
#include "airtime_policy.h"
#include "tdma_common.h"

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

/* =========================================================================
 * Mock Radio & Time Simulation Environment
 * ========================================================================= */

static uint32_t s_mock_time_ms = 0;
static uint32_t s_tx_count = 0;
static uint32_t s_out_of_slot_tx_count = 0;
static uint8_t s_last_tx_payload[128];
static uint8_t s_last_tx_len = 0;

static uint8_t s_mock_rx_queue[4][128];
static size_t s_mock_rx_lens[4] = {0};
static size_t s_mock_rx_head = 0;
static size_t s_mock_rx_tail = 0;

static bool s_mock_sleep_called = false;
static bool s_mock_standby_called = false;
static uint32_t s_expected_slot_usable_start = 0;
static uint32_t s_expected_slot_usable_end = 0;

static void mock_reset(void)
{
    s_mock_time_ms = 1000U;
    s_tx_count = 0U;
    s_out_of_slot_tx_count = 0U;
    s_last_tx_len = 0U;
    s_mock_rx_head = 0U;
    s_mock_rx_tail = 0U;
    s_mock_sleep_called = false;
    s_mock_standby_called = false;
    s_expected_slot_usable_start = 0U;
    s_expected_slot_usable_end = 0U;
    (void)memset(s_mock_rx_lens, 0, sizeof(s_mock_rx_lens));
}

static void mock_queue_rx_packet(const uint8_t *data, size_t len)
{
    if (len <= sizeof(s_mock_rx_queue[0])) {
        (void)memcpy(s_mock_rx_queue[s_mock_rx_tail], data, len);
        s_mock_rx_lens[s_mock_rx_tail] = len;
        s_mock_rx_tail = (s_mock_rx_tail + 1U) % 4U;
    }
}

static esp_err_t mock_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (payload == NULL || length == 0U) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Verify if TX occurs strictly within assigned slot window */
    if (s_expected_slot_usable_start > 0U && s_expected_slot_usable_end > 0U) {
        if (s_mock_time_ms < s_expected_slot_usable_start ||
            (s_mock_time_ms + 60U) > s_expected_slot_usable_end) {
            s_out_of_slot_tx_count++;
        }
    }

    (void)memcpy(s_last_tx_payload, payload, length);
    s_last_tx_len = length;
    s_tx_count++;

    /* Simulate RF transmission time */
    s_mock_time_ms += 60U;
    return ESP_OK;
}

static esp_err_t mock_radio_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    return ESP_OK;
}

static esp_err_t mock_radio_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    (void)wait_ms;
    if (out_buf == NULL || out_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_mock_rx_head == s_mock_rx_tail) {
        /* No frame in queue: timeout */
        s_mock_time_ms += wait_ms;
        *out_len = 0U;
        return ESP_ERR_TIMEOUT;
    }

    size_t len = s_mock_rx_lens[s_mock_rx_head];
    (void)memcpy(out_buf, s_mock_rx_queue[s_mock_rx_head], len);
    *out_len = len;
    s_mock_rx_head = (s_mock_rx_head + 1U) % 4U;
    return ESP_OK;
}

static esp_err_t mock_radio_sleep(void)
{
    s_mock_sleep_called = true;
    return ESP_OK;
}

static esp_err_t mock_radio_standby(void)
{
    s_mock_standby_called = true;
    return ESP_OK;
}

static uint32_t mock_get_time_ms(void)
{
    return s_mock_time_ms;
}

static void mock_delay_ms(uint32_t ms)
{
    s_mock_time_ms += ms;
}

static node_tdma_radio_hal_t s_mock_hal = {
    .radio_tx = mock_radio_tx,
    .radio_rx_single = mock_radio_rx_single,
    .radio_read_frame = mock_radio_read_frame,
    .radio_sleep = mock_radio_sleep,
    .radio_standby = mock_radio_standby,
    .get_time_ms = mock_get_time_ms,
    .delay_ms = mock_delay_ms,
};

/* Helper: Build a valid 32B DOWN_SYNC_BEACON frame */
static void build_valid_beacon(const node_tdma_client_config_t *cfg,
                               uint32_t sf_seq,
                               uint32_t epoch_sec,
                               uint8_t out_wire[32])
{
    lora_mac_v2_beacon_t bcn = {
        .magic = LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON,
        .gw_id = cfg->gw_id,
        .epoch_sec = epoch_sec,
        .sf_seq = sf_seq,
        .sched_ver = 1U,
        .flags = 0U,
        .key_id = cfg->beacon_key_id,
        .reserved = {0, 0, 0},
    };
    uint8_t raw[32];
    size_t written = 0U;
    (void)lora_mac_v2_beacon_serialize(&bcn, raw, sizeof(raw), &written);

    /* Compute HMAC on first 16 bytes */
    uint8_t tag[16];
    (void)node_crypto_compute_beacon_hmac(cfg->k_beacon, raw, 16U, tag);
    (void)memcpy(&raw[16], tag, 16);
    (void)memcpy(out_wire, raw, 32);
}

/* Helper: Build a valid 19B DOWN_EVENT_ACK frame */
static void build_valid_down_ack(const node_tdma_client_config_t *cfg,
                                 uint32_t event_ref,
                                 uint32_t frame_counter,
                                 uint8_t out_wire[19])
{
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_DOWN_EVENT_ACK,
        .node_id = cfg->node_id,
        .session_sel = cfg->session_sel,
        .frame_counter = frame_counter,
    };
    uint8_t raw_hdr[7];
    size_t hdr_w = 0U;
    (void)lora_mac_v2_header_encode(&hdr, raw_hdr, sizeof(raw_hdr), &hdr_w);

    uint8_t dl_nonce[13];
    (void)lora_mac_v2_build_nonce(cfg->session_nonce_prefix, LORA_MAC_V2_DIR_DOWNLINK, frame_counter, dl_nonce);

    lora_mac_v2_down_event_ack_t ack_payload = { .event_ref = event_ref };
    uint8_t pt[4];
    size_t pt_w = 0U;
    (void)lora_mac_v2_down_event_ack_serialize(&ack_payload, pt, sizeof(pt), &pt_w);

    uint8_t ct[4];
    uint8_t tag[8];
    (void)node_crypto_encrypt_down_ack(cfg->k_session_down, dl_nonce, raw_hdr, 7U, pt, 4U, ct, tag);

    (void)memcpy(&out_wire[0], raw_hdr, 7);
    (void)memcpy(&out_wire[7], ct, 4);
    (void)memcpy(&out_wire[11], tag, 8);
}

/* =========================================================================
 * Unit Test Functions
 * ========================================================================= */

static int test_node_tdma_client_init_and_config(void)
{
    node_tdma_client_config_t cfg;
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_get_default_config(&cfg));
    ASSERT_EQUAL_INT(1, cfg.node_id);
    ASSERT_EQUAL_INT(1, cfg.gw_id);
    ASSERT_EQUAL_INT(250, cfg.beacon_window_ms);
    ASSERT_EQUAL_INT(600, cfg.slot_duration_ms);
    ASSERT_EQUAL_INT(50, cfg.slot_guard_ms);

    node_tdma_client_state_t state;
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_init(&cfg, &state));
    ASSERT_EQUAL_U32(1, state.uplink_frame_counter);
    ASSERT_EQUAL_U32(0, state.last_sf_seq);
    ASSERT_EQUAL_U32(0, state.n_missed_beacons);
    ASSERT_TRUE(!state.is_synchronized);
    ASSERT_TRUE(!state.is_disconnected);

    /* Negative check: invalid node ID 0 or 16 */
    cfg.node_id = 0;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_tdma_client_init(&cfg, &state));
    cfg.node_id = 16;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_tdma_client_init(&cfg, &state));

    /* NULL pointers */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_tdma_client_init(NULL, &state));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_tdma_client_init(&cfg, NULL));

    return 0;
}

static int test_node_tdma_slot_boundary_calculation(void)
{
    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);

    /* Node 1: offset = 250 + 0*600 = 250; usable_start = 250 + 50 = 300; usable_end = 300 + 500 = 800 */
    cfg.node_id = 1U;
    uint32_t usable_start = 0, usable_end = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_compute_slot_boundaries(&cfg, 1000U, &usable_start, &usable_end));
    ASSERT_EQUAL_U32(1300U, usable_start);
    ASSERT_EQUAL_U32(1800U, usable_end);

    /* Node 2: offset = 250 + 1*600 = 850; usable_start = 850 + 50 = 900; usable_end = 900 + 500 = 1400 */
    cfg.node_id = 2U;
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_compute_slot_boundaries(&cfg, 1000U, &usable_start, &usable_end));
    ASSERT_EQUAL_U32(1900U, usable_start);
    ASSERT_EQUAL_U32(2400U, usable_end);

    /* Node 15: offset = 250 + 14*600 = 8650; usable_start = 8650 + 50 = 8700; usable_end = 9200 */
    cfg.node_id = 15U;
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_compute_slot_boundaries(&cfg, 1000U, &usable_start, &usable_end));
    ASSERT_EQUAL_U32(9700U, usable_start);
    ASSERT_EQUAL_U32(10200U, usable_end);

    return 0;
}

/**
 * Transition 1: Button event in FIFO -> Beacon sync -> static slot TX -> ACK reception -> FIFO pop.
 */
static int test_state_transition_success_pop(void)
{
    mock_reset();
    (void)airtime_policy_init(10U);

    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);
    cfg.node_id = 1U;

    node_tdma_client_state_t state;
    (void)node_tdma_client_init(&cfg, &state);

    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);

    /* Push button event */
    uint32_t ref = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 1700000000U, 0x01, 1, &ref));
    ASSERT_EQUAL_INT(1, node_event_fifo_get_pending_count(&fifo));

    /* Prepare simulated incoming Beacon and ACK */
    uint8_t beacon_wire[32];
    build_valid_beacon(&cfg, 101U, 1700000000U, beacon_wire);
    mock_queue_rx_packet(beacon_wire, 32U);

    uint8_t ack_wire[19];
    build_valid_down_ack(&cfg, ref, 50U, ack_wire);
    mock_queue_rx_packet(ack_wire, 19U);

    /* Expected slot boundary for Node 1: beacon at 1000ms -> usable start = 1300, end = 1800 */
    s_expected_slot_usable_start = 1300U;
    s_expected_slot_usable_end = 1800U;

    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));

    /* Verify 1 packet transmitted */
    ASSERT_EQUAL_U32(1, s_tx_count);
    ASSERT_EQUAL_INT(26, s_last_tx_len);
    ASSERT_EQUAL_U32(0, s_out_of_slot_tx_count);

    /* Verify FIFO popped (pending count drops to 0) */
    ASSERT_EQUAL_INT(0, node_event_fifo_get_pending_count(&fifo));

    /* Verify state machine properties */
    ASSERT_EQUAL_U32(2, state.uplink_frame_counter);
    ASSERT_EQUAL_U32(101, state.last_sf_seq);
    ASSERT_EQUAL_U32(0, state.n_missed_beacons);
    ASSERT_TRUE(state.is_synchronized);
    ASSERT_TRUE(!state.is_disconnected);
    ASSERT_EQUAL_INT(NODE_TDMA_STATE_REARM_SLEEP, state.state);
    ASSERT_TRUE(s_mock_sleep_called);

    return 0;
}

/**
 * Transition 2: Missed ACK / Corrupted ACK -> retry counter increment, event retained in FIFO.
 */
static int test_state_transition_missed_and_corrupted_ack_retry(void)
{
    mock_reset();
    (void)airtime_policy_init(10U);

    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);
    cfg.node_id = 2U;

    node_tdma_client_state_t state;
    (void)node_tdma_client_init(&cfg, &state);

    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);

    uint32_t ref = 0;
    (void)node_event_fifo_push(&fifo, 1700000000U, 0x01, 1, &ref);

    /* Scenario A: Missed ACK (no packet received) */
    uint8_t beacon_wire[32];
    build_valid_beacon(&cfg, 201U, 1700000000U, beacon_wire);
    mock_queue_rx_packet(beacon_wire, 32U);
    /* No ACK queued */

    s_expected_slot_usable_start = 1900U;
    s_expected_slot_usable_end = 2400U;

    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));

    /* Event retained in FIFO, retry count incremented to 1 */
    ASSERT_EQUAL_INT(1, node_event_fifo_get_pending_count(&fifo));
    node_event_fifo_item_t peek_item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &peek_item));
    ASSERT_EQUAL_INT(1, peek_item.retry_count);
    ASSERT_EQUAL_U32(1, state.uplink_frame_counter); /* Counter not advanced */

    /* Scenario B: Corrupted ACK (bad tag / bad event ref) */
    mock_reset();
    build_valid_beacon(&cfg, 202U, 1700000010U, beacon_wire);
    mock_queue_rx_packet(beacon_wire, 32U);

    /* ACK with wrong event ref 9999 */
    uint8_t bad_ack[19];
    build_valid_down_ack(&cfg, 9999U, 51U, bad_ack);
    mock_queue_rx_packet(bad_ack, 19U);

    s_expected_slot_usable_start = 1900U;
    s_expected_slot_usable_end = 2400U;

    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));

    /* Event retained in FIFO, retry count incremented to 2 */
    ASSERT_EQUAL_INT(1, node_event_fifo_get_pending_count(&fifo));
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &peek_item));
    ASSERT_EQUAL_INT(2, peek_item.retry_count);
    ASSERT_EQUAL_U32(1, state.uplink_frame_counter);

    return 0;
}

/**
 * Transition 3: Airtime budget exhaustion -> TX suppressed, event retained in FIFO.
 */
static int test_state_transition_airtime_exhaustion_suppression(void)
{
    mock_reset();
    /* Set airtime budget to minimal 1 permille (3600 ms / hr) and exhaust it */
    (void)airtime_policy_init(1U);
    (void)airtime_policy_record_tx(3600U); /* Budget full */

    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);
    cfg.node_id = 1U;

    node_tdma_client_state_t state;
    (void)node_tdma_client_init(&cfg, &state);

    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);
    uint32_t ref = 0;
    (void)node_event_fifo_push(&fifo, 1700000000U, 0x01, 1, &ref);

    uint8_t beacon_wire[32];
    build_valid_beacon(&cfg, 301U, 1700000000U, beacon_wire);
    mock_queue_rx_packet(beacon_wire, 32U);

    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));

    /* TX suppressed: tx_count must be 0 */
    ASSERT_EQUAL_U32(0, s_tx_count);
    /* Event retained in FIFO */
    ASSERT_EQUAL_INT(1, node_event_fifo_get_pending_count(&fifo));

    return 0;
}

/**
 * Transition 4: Beacon loss (N_MISSED > 3) -> fail-closed lock on DATA TX emissions.
 */
static int test_state_transition_beacon_loss_lock(void)
{
    mock_reset();
    (void)airtime_policy_init(10U);

    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);
    cfg.node_id = 1U;

    node_tdma_client_state_t state;
    (void)node_tdma_client_init(&cfg, &state);

    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);
    uint32_t ref = 0;
    (void)node_event_fifo_push(&fifo, 1700000000U, 0x01, 1, &ref);

    /* Simulate 3 missed beacons (no RX queued) with drift guard exceeded */
    for (int i = 1; i <= 3; i++) {
        mock_reset();
        state.last_beacon_sync_time_ms = 0; /* Forces drift guard fail */
        ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));
        ASSERT_EQUAL_U32(0, s_tx_count);
        ASSERT_EQUAL_U32((uint32_t)i, state.n_missed_beacons);
        ASSERT_TRUE(!state.is_disconnected);
    }

    /* 4th miss (N_MISSED > 3 threshold reached) */
    mock_reset();
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));
    ASSERT_EQUAL_U32(0, s_tx_count);
    ASSERT_EQUAL_U32(4, state.n_missed_beacons);
    ASSERT_TRUE(state.is_disconnected);
    ASSERT_EQUAL_INT(NODE_TDMA_STATE_DISCONNECTED, state.state);

    /* Attempt cycle while in DISCONNECTED state: DATA TX emissions locked */
    mock_reset();
    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));
    ASSERT_EQUAL_U32(0, s_tx_count);
    ASSERT_EQUAL_INT(NODE_TDMA_STATE_DISCONNECTED, state.state);
    ASSERT_EQUAL_INT(1, node_event_fifo_get_pending_count(&fifo));

    return 0;
}

/**
 * Transition 5: Zero out-of-slot RF transmission.
 */
static int test_zero_out_of_slot_rf_transmission(void)
{
    mock_reset();
    (void)airtime_policy_init(10U);

    node_tdma_client_config_t cfg;
    (void)node_tdma_client_get_default_config(&cfg);
    cfg.node_id = 3U;

    node_tdma_client_state_t state;
    (void)node_tdma_client_init(&cfg, &state);

    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);
    uint32_t ref = 0;
    (void)node_event_fifo_push(&fifo, 1700000000U, 0x01, 1, &ref);

    /* Beacon arrival at 1000ms.
     * Node 3 slot offset = 250 + 2*600 = 1450.
     * Usable slot start = 1000 + 1450 + 50 = 2500ms.
     * Usable slot end = 2500 + 500 = 3000ms.
     */
    s_expected_slot_usable_start = 2500U;
    s_expected_slot_usable_end = 3000U;

    uint8_t beacon_wire[32];
    build_valid_beacon(&cfg, 401U, 1700000000U, beacon_wire);
    mock_queue_rx_packet(beacon_wire, 32U);

    uint8_t ack_wire[19];
    build_valid_down_ack(&cfg, ref, 60U, ack_wire);
    mock_queue_rx_packet(ack_wire, 19U);

    ASSERT_EQUAL_INT(ESP_OK, node_tdma_client_run_cycle(&cfg, &s_mock_hal, &state, &fifo));

    /* Confirm transmission occurred AND zero out-of-slot transmissions */
    ASSERT_EQUAL_U32(1, s_tx_count);
    ASSERT_EQUAL_U32(0, s_out_of_slot_tx_count);

    return 0;
}

/**
 * Test 6: Cryptographic roundtrip and constant-time HMAC check
 */
static int test_crypto_operations_roundtrip(void)
{
    uint8_t k_beacon[32];
    (void)memset(k_beacon, 0x42, sizeof(k_beacon));
    uint8_t bcn_hdr[16] = {0x43, 0x01, 0, 0, 0, 10, 0, 0, 0, 20, 1, 0, 1, 0, 0, 0};

    uint8_t tag[16];
    ASSERT_EQUAL_INT(ESP_OK, node_crypto_compute_beacon_hmac(k_beacon, bcn_hdr, 16, tag));
    ASSERT_EQUAL_INT(ESP_OK, node_crypto_verify_beacon_hmac(k_beacon, bcn_hdr, 16, tag));

    /* Tamper with tag */
    tag[0] ^= 0xFFU;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, node_crypto_verify_beacon_hmac(k_beacon, bcn_hdr, 16, tag));

    /* AES-128-CCM roundtrip */
    uint8_t key[16] = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16};
    uint8_t nonce[13] = {0xAA, 0xBB, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11};
    uint8_t aad[7] = {0x41, 1, 0, 0, 0, 0, 1};
    uint8_t pt[11] = "Hello LoRa!";
    uint8_t ct[11];
    uint8_t ccm_tag[8];

    ASSERT_EQUAL_INT(ESP_OK, node_crypto_encrypt_up_event(key, nonce, aad, 7, pt, 11, ct, ccm_tag));

    uint8_t dec_pt[11];
    ASSERT_EQUAL_INT(ESP_OK, node_crypto_decrypt_down_ack(key, nonce, aad, 7, ct, 11, ccm_tag, dec_pt));
    ASSERT_EQUAL_INT(0, memcmp(pt, dec_pt, 11));

    /* Corrupted tag */
    ccm_tag[7] ^= 0x01;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, node_crypto_decrypt_down_ack(key, nonce, aad, 7, ct, 11, ccm_tag, dec_pt));

    return 0;
}

int main(void)
{
    int failures = 0;
    printf("============================================================\n");
    printf("Running Node TDMA Slot Client Unit Tests (Issue #239)\n");
    printf("============================================================\n");

    TEST_RUN(test_node_tdma_client_init_and_config);
    TEST_RUN(test_node_tdma_slot_boundary_calculation);
    TEST_RUN(test_crypto_operations_roundtrip);
    TEST_RUN(test_state_transition_success_pop);
    TEST_RUN(test_state_transition_missed_and_corrupted_ack_retry);
    TEST_RUN(test_state_transition_airtime_exhaustion_suppression);
    TEST_RUN(test_state_transition_beacon_loss_lock);
    TEST_RUN(test_zero_out_of_slot_rf_transmission);

    printf("============================================================\n");
    if (failures == 0) {
        printf("All Node TDMA Slot Client unit tests PASSED successfully!\n");
        return 0;
    } else {
        printf("%d test(s) FAILED!\n", failures);
        return 1;
    }
}
