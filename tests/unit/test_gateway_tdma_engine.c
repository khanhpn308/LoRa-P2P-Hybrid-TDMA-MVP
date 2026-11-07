/**
 * @file test_gateway_tdma_engine.c
 * @brief Unit tests for Gateway Master V2 Static TDMA Engine & Event ACK Loop.
 *
 * Authority: Issue #240, C Coding Standard v2, contracts/radio-mac/specification.md,
 *            contracts/radio-mac/tdma-schedule.md, DEC-127-01..06, DEC-MH-01..08.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "gateway_tdma_master.h"
#include "gateway_wal.h"
#include "gateway_crypto.h"
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

#define ASSERT_FALSE(cond) do { \
    if (cond) { \
        fprintf(stderr, "\nAssertion failed: NOT %s at %s:%d\n", #cond, __FILE__, __LINE__); \
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
 * Mock Hardware & Radio Simulation Environment
 * ========================================================================= */

#define MOCK_MAX_TX_RECORDS 32
#define MOCK_MAX_RX_STAGED  16

typedef struct {
    uint8_t  payload[128];
    uint8_t  length;
    uint32_t timestamp_ms;
} mock_tx_record_t;

typedef struct {
    uint8_t  slot_id;
    uint8_t  payload[128];
    uint8_t  length;
    int16_t  rssi;
    int8_t   snr;
    bool     consumed;
} mock_rx_staged_t;

static uint32_t s_mock_time_ms = 0;
static mock_tx_record_t s_tx_history[MOCK_MAX_TX_RECORDS];
static size_t s_tx_count = 0;

static mock_rx_staged_t s_rx_staged[MOCK_MAX_RX_STAGED];
static size_t s_rx_staged_count = 0;
static const gateway_tdma_engine_t *s_active_engine = NULL;

static bool s_mock_rx_active = false;
static bool s_mock_standby_called = false;

static void mock_reset(void)
{
    s_mock_time_ms = 1000U;
    s_tx_count = 0U;
    s_rx_staged_count = 0U;
    s_active_engine = NULL;
    s_mock_rx_active = false;
    s_mock_standby_called = false;
    (void)memset(s_tx_history, 0, sizeof(s_tx_history));
    (void)memset(s_rx_staged, 0, sizeof(s_rx_staged));
    airtime_policy_reset();
}

static void mock_stage_rx_frame(uint8_t slot_id, const uint8_t *payload, uint8_t length, int16_t rssi, int8_t snr)
{
    if (s_rx_staged_count < MOCK_MAX_RX_STAGED) {
        s_rx_staged[s_rx_staged_count].slot_id = slot_id;
        (void)memcpy(s_rx_staged[s_rx_staged_count].payload, payload, length);
        s_rx_staged[s_rx_staged_count].length = length;
        s_rx_staged[s_rx_staged_count].rssi = rssi;
        s_rx_staged[s_rx_staged_count].snr = snr;
        s_rx_staged[s_rx_staged_count].consumed = false;
        s_rx_staged_count++;
    }
}

static esp_err_t mock_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (payload == NULL || length == 0U) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_tx_count < MOCK_MAX_TX_RECORDS) {
        (void)memcpy(s_tx_history[s_tx_count].payload, payload, length);
        s_tx_history[s_tx_count].length = length;
        s_tx_history[s_tx_count].timestamp_ms = s_mock_time_ms;
        s_tx_count++;
    }
    return ESP_OK;
}

static esp_err_t mock_radio_rx_start(void)
{
    s_mock_rx_active = true;
    return ESP_OK;
}

static esp_err_t mock_radio_rx_stop(void)
{
    s_mock_rx_active = false;
    return ESP_OK;
}

static esp_err_t mock_radio_read_frame(uint8_t *out_buf, size_t *out_len, int16_t *out_rssi, int8_t *out_snr, uint32_t timeout_ms)
{
    (void)timeout_ms;
    uint8_t cur_slot = (s_active_engine != NULL) ? s_active_engine->current_slot : 0U;
    for (size_t i = 0; i < s_rx_staged_count; i++) {
        if (!s_rx_staged[i].consumed && (s_rx_staged[i].slot_id == cur_slot || s_rx_staged[i].slot_id == 0U)) {
            s_rx_staged[i].consumed = true;
            if (out_buf != NULL) {
                (void)memcpy(out_buf, s_rx_staged[i].payload, s_rx_staged[i].length);
            }
            if (out_len != NULL) {
                *out_len = s_rx_staged[i].length;
            }
            if (out_rssi != NULL) {
                *out_rssi = s_rx_staged[i].rssi;
            }
            if (out_snr != NULL) {
                *out_snr = s_rx_staged[i].snr;
            }
            return ESP_OK;
        }
    }
    return ESP_ERR_TIMEOUT;
}

static esp_err_t mock_radio_standby(void)
{
    s_mock_standby_called = true;
    return ESP_OK;
}

static esp_err_t mock_radio_sleep(void)
{
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

static const gateway_tdma_radio_hal_t s_mock_hal = {
    .radio_tx = mock_radio_tx,
    .radio_rx_start = mock_radio_rx_start,
    .radio_rx_stop = mock_radio_rx_stop,
    .radio_read_frame = mock_radio_read_frame,
    .radio_standby = mock_radio_standby,
    .radio_sleep = mock_radio_sleep,
    .get_time_ms = mock_get_time_ms,
    .delay_ms = mock_delay_ms,
};

/* Test keys */
static const uint8_t TEST_K_BEACON[32] = {
    0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f,0x10,
    0x11,0x12,0x13,0x14,0x15,0x16,0x17,0x18,0x19,0x1a,0x1b,0x1c,0x1d,0x1e,0x1f,0x20
};

static const uint8_t TEST_K_UP[16] = {
    0xAA,0xBB,0xCC,0xDD,0xEE,0xFF,0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88,0x99
};

static const uint8_t TEST_K_DL[16] = {
    0x12,0x34,0x56,0x78,0x9A,0xBC,0xDE,0xF0,0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88
};

static const uint8_t TEST_NONCE_PREFIX[8] = {
    0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08
};

static void setup_test_config(gateway_tdma_config_t *cfg)
{
    (void)gateway_tdma_get_default_config(cfg);
    (void)memcpy(cfg->k_beacon, TEST_K_BEACON, 32);

    /* Populate keys for slots 1..15 */
    for (uint8_t i = 1; i <= GW_TDMA_MAX_DATA_SLOTS; i++) {
        cfg->static_keys[i].is_active = true;
        cfg->static_keys[i].session_sel = 0U;
        (void)memcpy(cfg->static_keys[i].k_session_up, TEST_K_UP, 16);
        (void)memcpy(cfg->static_keys[i].k_session_dl, TEST_K_DL, 16);
        (void)memcpy(cfg->static_keys[i].session_nonce_prefix, TEST_NONCE_PREFIX, 8);
    }
}

/* =========================================================================
 * Unit Test Implementations
 * ========================================================================= */

/**
 * @brief Test 1: Cryptographic operations round-trip (HMAC-SHA256 & AES-128-CCM-8)
 */
static int test_crypto_operations_roundtrip(void)
{
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_init());

    /* Beacon HMAC generation & verification */
    uint8_t header[16] = {
        0x43, 0x01, 0x00, 0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x01, 0x01, 0x00, 0x01, 0x00, 0x00, 0x00
    };
    uint8_t hmac_tag[16];
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_compute_beacon_hmac(TEST_K_BEACON, header, 16, hmac_tag));
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_verify_beacon_hmac(TEST_K_BEACON, header, 16, hmac_tag));

    /* Tampered tag rejected */
    uint8_t bad_tag[16];
    (void)memcpy(bad_tag, hmac_tag, 16);
    bad_tag[15] ^= 0xFFU;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, gateway_crypto_verify_beacon_hmac(TEST_K_BEACON, header, 16, bad_tag));

    /* UP_EVENT (11B) encryption & decryption roundtrip */
    uint8_t aad[7] = {0x41, 0x01, 0x00, 0x00, 0x00, 0x00, 0x05};
    uint8_t nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_UPLINK, 5U, nonce);

    uint8_t plaintext[11] = {
        0x00, 0x00, 0x00, 0x42, /* event_ref = 0x42 */
        0x67, 0x00, 0x00, 0x01, /* event_time */
        0x07,                   /* event_code */
        0x01, 0x2C              /* event_value = 300 */
    };
    uint8_t ciphertext[11];
    uint8_t tag[8];

    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_encrypt_up_event(TEST_K_UP, nonce, aad, 7, plaintext, 11, ciphertext, tag));

    uint8_t decrypted[11];
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_decrypt_up_event(TEST_K_UP, nonce, aad, 7, ciphertext, 11, tag, decrypted));
    ASSERT_EQUAL_INT(0, memcmp(plaintext, decrypted, 11));

    /* Corrupted tag rejected fail-closed */
    tag[7] ^= 0x01U;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_CRC, gateway_crypto_decrypt_up_event(TEST_K_UP, nonce, aad, 7, ciphertext, 11, tag, decrypted));

    return 0;
}

/**
 * @brief Test 2: Bounded in-memory WAL buffer overflow & drop oldest policy (D12 §6.3)
 */
static int test_wal_buffer_bounded_overflow(void)
{
    gateway_wal_t wal;
    ASSERT_EQUAL_INT(ESP_OK, gateway_wal_init(&wal));
    ASSERT_EQUAL_U32(0, gateway_wal_count(&wal));
    ASSERT_EQUAL_U32(0, gateway_wal_get_dropped_count(&wal));

    /* Fill WAL to maximum capacity (64) */
    for (uint32_t i = 1; i <= GATEWAY_WAL_CAPACITY; i++) {
        gateway_wal_event_t ev = {
            .node_id = (uint8_t)(i % 15 + 1),
            .event_ref = i,
            .frame_counter = i,
            .event_code = 1,
            .event_value = (int16_t)i,
        };
        ASSERT_EQUAL_INT(ESP_OK, gateway_wal_push(&wal, &ev));
    }
    ASSERT_EQUAL_U32(GATEWAY_WAL_CAPACITY, gateway_wal_count(&wal));
    ASSERT_EQUAL_U32(0, gateway_wal_get_dropped_count(&wal));
    ASSERT_TRUE(gateway_wal_is_full(&wal));

    /* Push 5 more items -> drops oldest 5 entries and increments drop counter */
    for (uint32_t i = 101; i <= 105; i++) {
        gateway_wal_event_t ev = {
            .node_id = 1,
            .event_ref = i,
            .frame_counter = i,
            .event_code = 1,
            .event_value = (int16_t)i,
        };
        ASSERT_EQUAL_INT(ESP_OK, gateway_wal_push(&wal, &ev));
    }

    ASSERT_EQUAL_U32(GATEWAY_WAL_CAPACITY, gateway_wal_count(&wal));
    ASSERT_EQUAL_U32(5, gateway_wal_get_dropped_count(&wal));

    /* Oldest 5 entries (1..5) were dropped, so next peek is event_ref = 6 */
    gateway_wal_event_t popped;
    ASSERT_EQUAL_INT(ESP_OK, gateway_wal_pop(&wal, &popped));
    ASSERT_EQUAL_U32(6, popped.event_ref);
    ASSERT_EQUAL_U32(GATEWAY_WAL_CAPACITY - 1, gateway_wal_count(&wal));

    gateway_wal_clear(&wal);
    ASSERT_EQUAL_U32(0, gateway_wal_count(&wal));

    return 0;
}

/**
 * @brief Test 3: Superframe epoch trigger -> Beacon 0x43 emission with valid HMAC
 */
static int test_superframe_beacon_broadcast(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* At least Beacon was transmitted */
    ASSERT_TRUE(s_tx_count >= 1);
    ASSERT_EQUAL_U32(1, engine.beacon_tx_count);

    /* Inspect Beacon frame */
    const mock_tx_record_t *bcn_rec = &s_tx_history[0];
    ASSERT_EQUAL_INT(32, bcn_rec->length);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON, bcn_rec->payload[0]);
    ASSERT_EQUAL_INT(cfg.gw_id, bcn_rec->payload[1]);

    /* Verify HMAC tag over first 16 bytes of Beacon */
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_verify_beacon_hmac(cfg.k_beacon,
                                                               bcn_rec->payload,
                                                               16,
                                                               &bcn_rec->payload[16]));

    /* Radio entered standby during turnaround guard */
    ASSERT_TRUE(s_mock_standby_called);
    ASSERT_EQUAL_INT(GW_TDMA_STATE_SUPERFRAME_COMPLETE, engine.state);
    ASSERT_EQUAL_U32(2, engine.superframe_seq); /* Incremented after completion */

    return 0;
}

/**
 * @brief Test 4: Slot idle timeout advances slot pointer with 0 stray TX
 */
static int test_slot_idle_advancement_zero_stray_tx(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    /* Run superframe with zero incoming packets */
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* Exactly 15 slot idle events recorded for slots 1..15 */
    ASSERT_EQUAL_U32(15, engine.slot_idle_count);
    ASSERT_EQUAL_U32(0, engine.up_event_received_count);
    ASSERT_EQUAL_U32(0, engine.ack_sent_count);

    /* Only 1 TX emission across entire superframe (Beacon in Slot 0), zero stray TX */
    ASSERT_EQUAL_U32(1, s_tx_count);
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON, s_tx_history[0].payload[0]);

    return 0;
}

/**
 * @brief Test 5: Valid UP_EVENT (0x41) receipt -> WAL commit -> immediate in-slot DOWN_EVENT_ACK (0x42)
 */
static int test_up_event_valid_receipt_wal_commit_in_slot_ack(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    /* Build valid UP_EVENT for Node 1 in Slot 1 */
    uint8_t up_packet[26];
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = 1U,
        .session_sel = 0U,
        .frame_counter = 100U
    };
    size_t hdr_written = 0;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_header_encode(&hdr, up_packet, 26, &hdr_written));

    lora_mac_v2_up_event_t ev_data = {
        .event_ref = 0x12345678U,
        .event_time = 1700000000U,
        .event_code = 0x03U,
        .event_value = -45
    };
    uint8_t pt[11];
    size_t pt_written = 0;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_up_event_serialize(&ev_data, pt, 11, &pt_written));

    uint8_t nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_UPLINK, 100U, nonce);

    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_encrypt_up_event(TEST_K_UP, nonce,
                                                            up_packet, 7,
                                                            pt, 11,
                                                            &up_packet[7], &up_packet[18]));

    /* Stage incoming packet for Slot 1 */
    mock_stage_rx_frame(1U, up_packet, 26U, -75, 28);

    /* Run superframe */
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* Metrics check */
    ASSERT_EQUAL_U32(1, engine.up_event_received_count);
    ASSERT_EQUAL_U32(1, engine.ack_sent_count);
    ASSERT_EQUAL_U32(14, engine.slot_idle_count); /* Slots 2..15 were idle */

    /* Verify WAL commit */
    ASSERT_EQUAL_U32(1, gateway_wal_count(&engine.wal));
    gateway_wal_event_t wal_ev;
    ASSERT_EQUAL_INT(ESP_OK, gateway_wal_pop(&engine.wal, &wal_ev));
    ASSERT_EQUAL_INT(1, wal_ev.node_id);
    ASSERT_EQUAL_U32(0x12345678U, wal_ev.event_ref);
    ASSERT_EQUAL_INT(0x03, wal_ev.event_code);
    ASSERT_EQUAL_INT(-45, wal_ev.event_value);
    ASSERT_EQUAL_INT(-75, wal_ev.rssi_dbm);

    /* Verify transmitted DOWN_EVENT_ACK (0x42, 19 bytes) */
    ASSERT_EQUAL_U32(2, s_tx_count); /* [0] = Beacon, [1] = ACK */
    const mock_tx_record_t *ack_rec = &s_tx_history[1];
    ASSERT_EQUAL_INT(19, ack_rec->length);

    lora_mac_v2_header_t ack_hdr;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_header_parse(ack_rec->payload, 19, &ack_hdr));
    ASSERT_EQUAL_INT(LORA_MAC_V2_TYPE_DOWN_EVENT_ACK, ack_hdr.ver_type);
    ASSERT_EQUAL_INT(1, ack_hdr.node_id);
    ASSERT_EQUAL_U32(1, ack_hdr.frame_counter);

    /* Decrypt ACK payload under K_SESSION_DL with nonce (dir=0x02) */
    uint8_t dl_nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_DOWNLINK, 1U, dl_nonce);

    uint8_t ack_decrypted[4];
    ASSERT_EQUAL_INT(ESP_OK, gateway_crypto_decrypt_down_ack(TEST_K_DL, dl_nonce,
                                                            ack_rec->payload, 7,
                                                            &ack_rec->payload[7], 4,
                                                            &ack_rec->payload[11],
                                                            ack_decrypted));

    lora_mac_v2_down_event_ack_t echoed_ack;
    ASSERT_EQUAL_INT(ESP_OK, lora_mac_v2_down_event_ack_deserialize(ack_decrypted, 4, &echoed_ack));
    ASSERT_EQUAL_U32(0x12345678U, echoed_ack.event_ref); /* Echoed exact event_ref! */

    return 0;
}

/**
 * @brief Test 6: Corrupted MIC / invalid header rejects cleanly without ACK emission and without buffer modification
 */
static int test_corrupted_mic_and_invalid_header_rejection(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    /* Build an UP_EVENT with corrupted CCM-8 tag */
    uint8_t up_packet[26];
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = 2U,
        .session_sel = 0U,
        .frame_counter = 50U
    };
    (void)lora_mac_v2_header_encode(&hdr, up_packet, 26, NULL);
    (void)memset(&up_packet[7], 0xAA, 11);
    (void)memset(&up_packet[18], 0x55, 8); /* Invalid tag */

    mock_stage_rx_frame(2U, up_packet, 26U, -80, 20);

    /* Run superframe */
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* Must increment corrupted_mic_count */
    ASSERT_EQUAL_U32(1, engine.corrupted_mic_count);
    ASSERT_EQUAL_U32(0, engine.up_event_received_count);

    /* Zero ACK transmitted: only Beacon was emitted in Slot 0 */
    ASSERT_EQUAL_U32(1, s_tx_count);
    ASSERT_EQUAL_U32(0, engine.ack_sent_count);

    /* WAL buffer completely unmodified */
    ASSERT_EQUAL_U32(0, gateway_wal_count(&engine.wal));

    return 0;
}

/**
 * @brief Test 7: Gateway airtime budget exhaustion blocks Beacon and ACK emissions gracefully
 */
static int test_airtime_exhaustion_suppression(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    /* Consume entire 10% airtime budget (360,000 ms in 1h window) */
    (void)airtime_policy_record_tx(360000U);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(cfg.packet_toa_beacon_ms));

    /* Stage valid UP_EVENT for Node 1 */
    uint8_t up_packet[26];
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = 1U,
        .session_sel = 0U,
        .frame_counter = 1U
    };
    (void)lora_mac_v2_header_encode(&hdr, up_packet, 26, NULL);
    lora_mac_v2_up_event_t ev_data = { .event_ref = 100, .event_time = 0, .event_code = 1, .event_value = 10 };
    uint8_t pt[11];
    (void)lora_mac_v2_up_event_serialize(&ev_data, pt, 11, NULL);
    uint8_t nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_UPLINK, 1U, nonce);
    (void)gateway_crypto_encrypt_up_event(TEST_K_UP, nonce, up_packet, 7, pt, 11, &up_packet[7], &up_packet[18]);

    mock_stage_rx_frame(1U, up_packet, 26U, -70, 30);

    /* Run superframe under airtime exhaustion */
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* Beacon was blocked gracefully */
    ASSERT_EQUAL_U32(1, engine.beacon_blocked_count);
    ASSERT_EQUAL_U32(0, engine.beacon_tx_count);

    /* Event was still decrypted and committed to WAL safely */
    ASSERT_EQUAL_U32(1, engine.up_event_received_count);
    ASSERT_EQUAL_U32(1, gateway_wal_count(&engine.wal));

    /* In-slot ACK was suppressed gracefully due to airtime */
    ASSERT_EQUAL_U32(1, engine.airtime_blocked_ack_count);
    ASSERT_EQUAL_U32(0, engine.ack_sent_count);

    /* Zero RF emissions took place */
    ASSERT_EQUAL_U32(0, s_tx_count);

    return 0;
}

/**
 * @brief Test 8: Maintenance Superframe Management (UP_HEALTH_REPLY & UP_DIAG_METRICS DEC-MH-08)
 */
static int test_maintenance_superframe_management(void)
{
    mock_reset();

    gateway_tdma_config_t cfg;
    setup_test_config(&cfg);

    gateway_tdma_engine_t engine;
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_init(&engine, &cfg, &s_mock_hal));
    s_active_engine = &engine;

    /* Align superframe sequence to maintenance epoch (seq = 30) */
    engine.superframe_seq = 30U;

    /* Stage UP_HEALTH_REPLY (0x44, 21B) for Slot 1 */
    uint8_t health_packet[21];
    lora_mac_v2_header_t h_hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_HEALTH_REPLY,
        .node_id = 1U,
        .session_sel = 0U,
        .frame_counter = 200U
    };
    (void)lora_mac_v2_header_encode(&h_hdr, health_packet, 21, NULL);
    lora_mac_v2_up_health_reply_t h_data = { .battery_mv = 3280, .uptime_sec = 12000, .pending_count = 2 };
    uint8_t h_pt[6];
    (void)lora_mac_v2_up_health_reply_serialize(&h_data, h_pt, 6, NULL);
    uint8_t h_nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_UPLINK, 200U, h_nonce);
    (void)gateway_crypto_encrypt_up_health(TEST_K_UP, h_nonce, health_packet, 7, h_pt, 6, &health_packet[7], &health_packet[13]);
    mock_stage_rx_frame(1U, health_packet, 21U, -72, 25);

    /* Stage UP_DIAG_METRICS (0x4A, 23B) for Slot 2 per DEC-MH-08 */
    uint8_t diag_packet[23];
    lora_mac_v2_header_t d_hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_DIAG_METRICS,
        .node_id = 2U,
        .session_sel = 0U,
        .frame_counter = 201U
    };
    (void)lora_mac_v2_header_encode(&d_hdr, diag_packet, 23, NULL);
    lora_mac_v2_up_diag_metrics_t d_data = { .dropped_event_count = 7U, .diag_seq = 42U };
    uint8_t d_pt[8];
    (void)lora_mac_v2_up_diag_metrics_serialize(&d_data, d_pt, 8, NULL);
    uint8_t d_nonce[13];
    (void)lora_mac_v2_build_nonce(TEST_NONCE_PREFIX, LORA_MAC_V2_DIR_UPLINK, 201U, d_nonce);
    (void)gateway_crypto_encrypt_up_diag(TEST_K_UP, d_nonce, diag_packet, 7, d_pt, 8, &diag_packet[7], &diag_packet[15]);
    mock_stage_rx_frame(2U, diag_packet, 23U, -74, 24);

    /* Run maintenance superframe */
    ASSERT_EQUAL_INT(ESP_OK, gateway_tdma_run_superframe(&engine));

    /* Beacon had maintenance flag (0x01) */
    ASSERT_EQUAL_INT(0x01, s_tx_history[0].payload[11]);

    /* Verification of metrics processing */
    ASSERT_EQUAL_U32(1, engine.maintenance_health_count);
    ASSERT_EQUAL_U32(1, engine.maintenance_diag_count);
    ASSERT_EQUAL_U32(7U, engine.node_last_dropped_event_count[2]);
    ASSERT_EQUAL_U32(42U, engine.node_last_diag_seq[2]);

    return 0;
}

/**
 * @brief Test 9: V2 Static TDMA slot timing calculations (DEC-127-03, DEC-127-06)
 */
static int test_tdma_v2_timing_boundaries(void)
{
    /* Out of bounds */
    uint32_t s_start, u_start, u_end, s_end;
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_v2_get_slot_timing(0, &s_start, &u_start, &u_end, &s_end));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_v2_get_slot_timing(16, &s_start, &u_start, &u_end, &s_end));

    /* Slot 1..15 nominal checks */
    for (uint8_t slot = 1; slot <= 15; slot++) {
        ASSERT_EQUAL_INT(ESP_OK, tdma_v2_get_slot_timing(slot, &s_start, &u_start, &u_end, &s_end));
        ASSERT_EQUAL_U32(slot * 600U, s_start);
        ASSERT_EQUAL_U32(s_start + 50U, u_start);
        ASSERT_EQUAL_U32(u_start + 500U, u_end);
        ASSERT_EQUAL_U32(s_start + 600U, s_end);
    }
    return 0;
}

int main(void)
{
    int failures = 0;
    printf("============================================================\n");
    printf("Running Gateway TDMA Master Engine Unit Tests (Issue #240)\n");
    printf("============================================================\n");

    TEST_RUN(test_crypto_operations_roundtrip);
    TEST_RUN(test_wal_buffer_bounded_overflow);
    TEST_RUN(test_superframe_beacon_broadcast);
    TEST_RUN(test_slot_idle_advancement_zero_stray_tx);
    TEST_RUN(test_up_event_valid_receipt_wal_commit_in_slot_ack);
    TEST_RUN(test_corrupted_mic_and_invalid_header_rejection);
    TEST_RUN(test_airtime_exhaustion_suppression);
    TEST_RUN(test_maintenance_superframe_management);
    TEST_RUN(test_tdma_v2_timing_boundaries);

    printf("============================================================\n");
    if (failures == 0) {
        printf("All Gateway TDMA Master Engine unit tests PASSED successfully!\n");
    } else {
        printf("Gateway TDMA Master Engine unit tests FAILED (%d failures)\n", failures);
    }
    printf("============================================================\n");

    return failures;
}
