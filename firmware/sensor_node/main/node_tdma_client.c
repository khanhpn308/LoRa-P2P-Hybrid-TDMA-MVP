#include "node_tdma_client.h"
#include <string.h>
#include "esp_log.h"
#include "airtime_policy.h"
#include "tdma_common.h"

static const char *TAG = "node_tdma_client";

/* Default project test keys (used when unprovisioned in development) */
static const uint8_t DEFAULT_K_BEACON[32] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20
};

static const uint8_t DEFAULT_K_SESSION_UP[16] = {
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, 0xA6, 0xA7,
    0xA8, 0xA9, 0xAA, 0xAB, 0xAC, 0xAD, 0xAE, 0xAF
};

static const uint8_t DEFAULT_K_SESSION_DOWN[16] = {
    0xB0, 0xB1, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7,
    0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF
};

static const uint8_t DEFAULT_NONCE_PREFIX[8] = {
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57
};

const char *node_tdma_state_to_str(node_tdma_state_t state)
{
    switch (state) {
        case NODE_TDMA_STATE_IDLE:           return "IDLE";
        case NODE_TDMA_STATE_WAKE_CHECK:     return "WAKE_CHECK";
        case NODE_TDMA_STATE_FIFO_EVAL:      return "FIFO_EVAL";
        case NODE_TDMA_STATE_BEACON_SYNC:    return "BEACON_SYNC";
        case NODE_TDMA_STATE_SLOT_SCHEDULER: return "SLOT_SCHEDULER";
        case NODE_TDMA_STATE_AIRTIME_CHECK:  return "AIRTIME_CHECK";
        case NODE_TDMA_STATE_EVENT_TX:       return "EVENT_TX";
        case NODE_TDMA_STATE_ACK_RX:         return "ACK_RX";
        case NODE_TDMA_STATE_ACK_EVAL:       return "ACK_EVAL";
        case NODE_TDMA_STATE_REARM_SLEEP:    return "REARM_SLEEP";
        case NODE_TDMA_STATE_DISCONNECTED:   return "DISCONNECTED";
        default:                             return "UNKNOWN";
    }
}

esp_err_t node_tdma_client_get_default_config(node_tdma_client_config_t *out_cfg)
{
    if (out_cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    (void)memset(out_cfg, 0, sizeof(*out_cfg));

    out_cfg->node_id = 1U;
    out_cfg->gw_id = 1U;
    out_cfg->session_sel = 0U;
    out_cfg->beacon_key_id = 1U;

    (void)memcpy(out_cfg->k_beacon, DEFAULT_K_BEACON, sizeof(out_cfg->k_beacon));
    (void)memcpy(out_cfg->k_session_up, DEFAULT_K_SESSION_UP, sizeof(out_cfg->k_session_up));
    (void)memcpy(out_cfg->k_session_down, DEFAULT_K_SESSION_DOWN, sizeof(out_cfg->k_session_down));
    (void)memcpy(out_cfg->session_nonce_prefix, DEFAULT_NONCE_PREFIX, sizeof(out_cfg->session_nonce_prefix));

    out_cfg->beacon_window_ms = NODE_TDMA_BEACON_WINDOW_MS;
    out_cfg->slot_duration_ms = NODE_TDMA_SLOT_PERIOD_MS;
    out_cfg->slot_guard_ms = NODE_TDMA_GUARD_MS;
    out_cfg->ack_timeout_ms = NODE_TDMA_ACK_TIMEOUT_MS;
    out_cfg->clock_drift_ppm = NODE_TDMA_DEFAULT_DRIFT_PPM;
    out_cfg->packet_toa_ms = NODE_TDMA_NOMINAL_TOA_MS;

    return ESP_OK;
}

esp_err_t node_tdma_client_init(const node_tdma_client_config_t *cfg,
                                node_tdma_client_state_t *state)
{
    if (cfg == NULL || state == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!tdma_is_valid_slot_id(cfg->node_id)) {
        ESP_LOGE(TAG, "Invalid Node ID %u (must be 1..15)", cfg->node_id);
        return ESP_ERR_INVALID_ARG;
    }

    (void)memset(state, 0, sizeof(*state));
    state->uplink_frame_counter = 1U;
    state->last_sf_seq = 0U;
    state->last_beacon_sync_time_ms = 0U;
    state->n_missed_beacons = 0U;
    state->state = NODE_TDMA_STATE_IDLE;
    state->is_synchronized = false;
    state->is_disconnected = false;

    return ESP_OK;
}

esp_err_t node_tdma_compute_slot_boundaries(const node_tdma_client_config_t *cfg,
                                            uint32_t beacon_arrival_ms,
                                            uint32_t *out_usable_start,
                                            uint32_t *out_usable_end)
{
    if (cfg == NULL || out_usable_start == NULL || out_usable_end == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!tdma_is_valid_slot_id(cfg->node_id)) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Geometry per contracts/radio-mac/tdma-schedule.md:
     * reserved_start(i) = DATA_ORIGIN + (i-1)*600
     * usable_start(i)   = reserved_start(i) + 50
     * usable_end(i)     = usable_start(i) + 500
     */
    uint32_t slot_offset_ms = cfg->beacon_window_ms +
                             (uint32_t)(cfg->node_id - 1U) * cfg->slot_duration_ms;
    *out_usable_start = beacon_arrival_ms + slot_offset_ms + cfg->slot_guard_ms;
    *out_usable_end = *out_usable_start + (cfg->slot_duration_ms - 2U * cfg->slot_guard_ms);

    return ESP_OK;
}

esp_err_t node_tdma_client_run_cycle(const node_tdma_client_config_t *cfg,
                                     const node_tdma_radio_hal_t *hal,
                                     node_tdma_client_state_t *state,
                                     node_event_fifo_t *fifo)
{
    if (cfg == NULL || hal == NULL || state == NULL || fifo == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (hal->radio_tx == NULL || hal->radio_rx_single == NULL ||
        hal->radio_read_frame == NULL || hal->radio_sleep == NULL ||
        hal->get_time_ms == NULL || hal->delay_ms == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    state->state = NODE_TDMA_STATE_WAKE_CHECK;

    /* 1. FIFO_EVAL: Check if any pending events exist */
    state->state = NODE_TDMA_STATE_FIFO_EVAL;
    size_t pending = node_event_fifo_get_pending_count(fifo);
    if (pending == 0U) {
        ESP_LOGD(TAG, "No pending events in FIFO; sleeping immediately");
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* 2. Disconnection Check (DEC-MH-04): N_MISSED > 3 lock DATA emissions */
    if (state->is_disconnected || state->n_missed_beacons > NODE_TDMA_MAX_MISSED_BEACONS) {
        state->is_disconnected = true;
        state->state = NODE_TDMA_STATE_DISCONNECTED;
        ESP_LOGW(TAG, "Node in DISCONNECTED state (missed beacons: %" PRIu32 " > %u); DATA TX locked",
                 state->n_missed_beacons, NODE_TDMA_MAX_MISSED_BEACONS);
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* 3. BEACON_SYNC: Listen for Gateway Beacon 0x43 */
    state->state = NODE_TDMA_STATE_BEACON_SYNC;
    ESP_LOGD(TAG, "Listening for Gateway Beacon (window: %" PRIu32 " ms)...", cfg->beacon_window_ms);

    esp_err_t rx_start_err = hal->radio_rx_single(cfg->beacon_window_ms);
    if (rx_start_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start Beacon RxSingle: %s", esp_err_to_name(rx_start_err));
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return rx_start_err;
    }

    uint8_t rx_buf[64];
    size_t rx_len = 0U;
    esp_err_t bcn_rx_err = hal->radio_read_frame(rx_buf, &rx_len, cfg->beacon_window_ms);
    uint32_t beacon_arrival_time = hal->get_time_ms();
    bool beacon_valid = false;

    if (bcn_rx_err == ESP_OK && rx_len >= LORA_MAC_V2_LEN_DOWN_SYNC_BEACON) {
        lora_mac_v2_beacon_t bcn;
        esp_err_t deser_err = lora_mac_v2_beacon_deserialize(rx_buf, rx_len, &bcn);
        if (deser_err == ESP_OK && bcn.gw_id == cfg->gw_id) {
            /* Anti-replay & freshness check */
            if (bcn.sf_seq > state->last_sf_seq || state->last_sf_seq == 0U) {
                if (bcn.key_id == cfg->beacon_key_id) {
                    /* Verify HMAC-SHA256-128 tag */
                    esp_err_t hmac_err = node_crypto_verify_beacon_hmac(cfg->k_beacon,
                                                                        rx_buf,
                                                                        16U,
                                                                        bcn.hmac_tag);
                    if (hmac_err == ESP_OK) {
                        beacon_valid = true;
                        state->last_sf_seq = bcn.sf_seq;
                        state->last_beacon_sync_time_ms = beacon_arrival_time;
                        state->n_missed_beacons = 0U;
                        state->is_synchronized = true;
                        state->is_disconnected = false;
                        ESP_LOGI(TAG, "Beacon sync successful (SF_SEQ: %" PRIu32 ", Epoch: %" PRIu32 ")",
                                 bcn.sf_seq, bcn.epoch_sec);
                    } else {
                        ESP_LOGW(TAG, "Beacon HMAC validation FAILED (tag mismatch)");
                    }
                } else {
                    ESP_LOGW(TAG, "Beacon KEY_ID mismatch (%u != expected %u)", bcn.key_id, cfg->beacon_key_id);
                }
            } else {
                ESP_LOGW(TAG, "Stale or replayed SF_SEQ: %" PRIu32 " <= %" PRIu32, bcn.sf_seq, state->last_sf_seq);
            }
        }
    }

    if (!beacon_valid) {
        state->n_missed_beacons++;
        state->is_synchronized = false;
        ESP_LOGW(TAG, "Beacon missed/corrupted (consecutive misses: %" PRIu32 ")", state->n_missed_beacons);

        if (state->n_missed_beacons > NODE_TDMA_MAX_MISSED_BEACONS) {
            state->is_disconnected = true;
            state->state = NODE_TDMA_STATE_DISCONNECTED;
            ESP_LOGE(TAG, "Entering DISCONNECTED state (n_missed > %u); DATA TX locked", NODE_TDMA_MAX_MISSED_BEACONS);
            (void)hal->radio_sleep();
            return ESP_OK;
        }

        /* Holdover check: verify if estimated clock drift exceeds guard time (50ms) */
        uint32_t now = hal->get_time_ms();
        uint32_t elapsed_s = (state->last_beacon_sync_time_ms > 0U && now >= state->last_beacon_sync_time_ms)
                             ? ((now - state->last_beacon_sync_time_ms) / 1000U) : 9999U;
        uint32_t drift_ms = tdma_calculate_drift_guard_ms(cfg->clock_drift_ppm, elapsed_s);
        if (drift_ms > NODE_TDMA_MAX_HOLD_DRIFT_MS || state->last_beacon_sync_time_ms == 0U) {
            ESP_LOGW(TAG, "Clock drift (%u ms) exceeds guard (%u ms) or no prior sync; DATA TX inhibited",
                     drift_ms, NODE_TDMA_MAX_HOLD_DRIFT_MS);
            state->state = NODE_TDMA_STATE_REARM_SLEEP;
            (void)hal->radio_sleep();
            return ESP_OK;
        }

        /* Within allowable holdover margin */
        beacon_arrival_time = state->last_beacon_sync_time_ms;
    }

    /* 4. SLOT_SCHEDULER: Align to Node's own static slot boundary */
    state->state = NODE_TDMA_STATE_SLOT_SCHEDULER;
    uint32_t usable_start = 0U;
    uint32_t usable_end = 0U;
    esp_err_t bound_err = node_tdma_compute_slot_boundaries(cfg, beacon_arrival_time, &usable_start, &usable_end);
    if (bound_err != ESP_OK) {
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return bound_err;
    }

    uint32_t current_time = hal->get_time_ms();
    if (current_time < usable_start) {
        uint32_t wait_ms = usable_start - current_time;
        ESP_LOGD(TAG, "Waiting %" PRIu32 " ms until slot start...", wait_ms);
        hal->delay_ms(wait_ms);
        current_time = hal->get_time_ms();
    }

    /* Strict slot boundary adherence check (MAC-002: Zero out-of-slot RF transmission) */
    if (current_time < usable_start || (current_time + cfg->packet_toa_ms) > usable_end) {
        ESP_LOGW(TAG, "Outside usable slot window (%u..%u, current: %u); TX suppressed",
                 usable_start, usable_end, current_time);
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* 5. AIRTIME_CHECK (RAD-001): Query duty cycle limiter before emission */
    state->state = NODE_TDMA_STATE_AIRTIME_CHECK;
    esp_err_t air_err = airtime_policy_check(cfg->packet_toa_ms);
    if (air_err != ESP_OK) {
        ESP_LOGW(TAG, "Airtime duty cycle exhausted; TX suppressed fail-closed: %s", esp_err_to_name(air_err));
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* 6. EVENT_TX: Build and transmit encrypted UP_EVENT (0x41, 26B) */
    state->state = NODE_TDMA_STATE_EVENT_TX;
    node_event_fifo_item_t event_item;
    esp_err_t peek_err = node_event_fifo_peek_pending(fifo, &event_item);
    if (peek_err != ESP_OK) {
        ESP_LOGD(TAG, "No pending event at TX boundary: %s", esp_err_to_name(peek_err));
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* Encode 7B Unicast Header */
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = cfg->node_id,
        .session_sel = cfg->session_sel,
        .frame_counter = state->uplink_frame_counter,
    };
    uint8_t raw_hdr[LORA_MAC_V2_HEADER_LEN];
    size_t hdr_written = 0U;
    esp_err_t hdr_enc_err = lora_mac_v2_header_encode(&hdr, raw_hdr, sizeof(raw_hdr), &hdr_written);
    if (hdr_enc_err != ESP_OK) {
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return hdr_enc_err;
    }

    /* Build 13B Nonce with Direction 0x01 (Uplink) */
    uint8_t nonce[LORA_MAC_V2_CCM_NONCE_LEN];
    esp_err_t nonce_err = lora_mac_v2_build_nonce(cfg->session_nonce_prefix,
                                                  LORA_MAC_V2_DIR_UPLINK,
                                                  state->uplink_frame_counter,
                                                  nonce);
    if (nonce_err != ESP_OK) {
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return nonce_err;
    }

    /* Serialize 11B Plaintext Payload */
    lora_mac_v2_up_event_t up_evt = {
        .event_ref = event_item.event_ref,
        .event_time = event_item.event_time,
        .event_code = event_item.event_code,
        .event_value = event_item.event_value,
    };
    uint8_t pt[11];
    size_t pt_written = 0U;
    esp_err_t pt_ser_err = lora_mac_v2_up_event_serialize(&up_evt, pt, sizeof(pt), &pt_written);
    if (pt_ser_err != ESP_OK) {
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return pt_ser_err;
    }

    /* Encrypt with AES-128-CCM-8 */
    uint8_t ct[11];
    uint8_t ccm_tag[NODE_CRYPTO_CCM_TAG_LEN];
    esp_err_t enc_err = node_crypto_encrypt_up_event(cfg->k_session_up,
                                                     nonce,
                                                     raw_hdr, sizeof(raw_hdr),
                                                     pt, sizeof(pt),
                                                     ct, ccm_tag);
    node_crypto_zeroize(pt, sizeof(pt));
    if (enc_err != ESP_OK) {
        ESP_LOGE(TAG, "UP_EVENT encryption failed: %s", esp_err_to_name(enc_err));
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return enc_err;
    }

    /* Assemble complete 26-byte wire frame */
    uint8_t wire_tx[LORA_MAC_V2_LEN_UP_EVENT];
    (void)memcpy(&wire_tx[0], raw_hdr, LORA_MAC_V2_HEADER_LEN);
    (void)memcpy(&wire_tx[7], ct, 11);
    (void)memcpy(&wire_tx[18], ccm_tag, NODE_CRYPTO_CCM_TAG_LEN);

    /* Final out-of-slot check before physical RF emission */
    current_time = hal->get_time_ms();
    if (current_time < usable_start || (current_time + cfg->packet_toa_ms) > usable_end) {
        ESP_LOGW(TAG, "Timing overrun before TX (%u..%u, current: %u); RF emission aborted",
                 usable_start, usable_end, current_time);
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    /* Transmit over radio and record airtime */
    esp_err_t tx_err = hal->radio_tx(wire_tx, LORA_MAC_V2_LEN_UP_EVENT, cfg->packet_toa_ms * 2U);
    (void)airtime_policy_record_tx(cfg->packet_toa_ms);
    if (tx_err != ESP_OK) {
        ESP_LOGE(TAG, "RF transmission error: %s; recording retry", esp_err_to_name(tx_err));
        (void)node_event_fifo_record_retry(fifo, event_item.event_ref);
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    ESP_LOGI(TAG, "Transmitted UP_EVENT (Ref: %" PRIu32 ", Counter: %" PRIu32 ", Slot: %u)",
             event_item.event_ref, state->uplink_frame_counter, cfg->node_id);

    /* 7. ACK_RX: Switch to RxSingle within the slot to await DOWN_EVENT_ACK (0x42, 19B) */
    state->state = NODE_TDMA_STATE_ACK_RX;
    esp_err_t rx_ack_start = hal->radio_rx_single(cfg->ack_timeout_ms);
    if (rx_ack_start != ESP_OK) {
        ESP_LOGW(TAG, "Failed to start ACK RxSingle: %s", esp_err_to_name(rx_ack_start));
        (void)node_event_fifo_record_retry(fifo, event_item.event_ref);
        state->state = NODE_TDMA_STATE_REARM_SLEEP;
        (void)hal->radio_sleep();
        return ESP_OK;
    }

    uint8_t ack_buf[64];
    size_t ack_len = 0U;
    esp_err_t ack_rx_err = hal->radio_read_frame(ack_buf, &ack_len, cfg->ack_timeout_ms);

    /* 8. ACK_EVAL: Validate ACK and pop event or record retry */
    state->state = NODE_TDMA_STATE_ACK_EVAL;
    bool ack_valid = false;

    if (ack_rx_err == ESP_OK && ack_len >= LORA_MAC_V2_LEN_DOWN_EVENT_ACK) {
        lora_mac_v2_header_t ack_hdr;
        esp_err_t ack_hdr_err = lora_mac_v2_header_parse(ack_buf, ack_len, &ack_hdr);
        if (ack_hdr_err == ESP_OK &&
            ack_hdr.ver_type == LORA_MAC_V2_TYPE_DOWN_EVENT_ACK &&
            ack_hdr.node_id == cfg->node_id) {

            uint8_t dl_nonce[LORA_MAC_V2_CCM_NONCE_LEN];
            esp_err_t dl_nonce_err = lora_mac_v2_build_nonce(cfg->session_nonce_prefix,
                                                             LORA_MAC_V2_DIR_DOWNLINK,
                                                             ack_hdr.frame_counter,
                                                             dl_nonce);
            if (dl_nonce_err == ESP_OK) {
                uint8_t dl_pt[4];
                esp_err_t dec_ack_err = node_crypto_decrypt_down_ack(cfg->k_session_down,
                                                                     dl_nonce,
                                                                     ack_buf, LORA_MAC_V2_HEADER_LEN,
                                                                     &ack_buf[7], 4U,
                                                                     &ack_buf[11],
                                                                     dl_pt);
                if (dec_ack_err == ESP_OK) {
                    lora_mac_v2_down_event_ack_t ack_payload;
                    esp_err_t deser_ack_err = lora_mac_v2_down_event_ack_deserialize(dl_pt, 4U, &ack_payload);
                    if (deser_ack_err == ESP_OK && ack_payload.event_ref == event_item.event_ref) {
                        ack_valid = true;
                        ESP_LOGI(TAG, "Valid DOWN_EVENT_ACK received (Ref: %" PRIu32 ")", ack_payload.event_ref);
                    } else {
                        ESP_LOGW(TAG, "ACK event_ref mismatch (%" PRIu32 " != %" PRIu32 ")",
                                 ack_payload.event_ref, event_item.event_ref);
                    }
                    node_crypto_zeroize(dl_pt, sizeof(dl_pt));
                } else {
                    ESP_LOGW(TAG, "DOWN_EVENT_ACK decryption/tag verification failed");
                }
            }
        } else {
            ESP_LOGW(TAG, "Corrupted ACK header (type: 0x%02X, node: %u)", ack_hdr.ver_type, ack_hdr.node_id);
        }
    } else {
        ESP_LOGW(TAG, "No ACK received within slot timeout (err: %s, len: %zu)",
                 esp_err_to_name(ack_rx_err), ack_len);
    }

    if (ack_valid) {
        /* Successfully ACKed: Pop event from FIFO and advance frame counter */
        (void)node_event_fifo_ack(fifo, event_item.event_ref);
        state->uplink_frame_counter++;
        ESP_LOGI(TAG, "Event %" PRIu32 " completed and popped from FIFO. Next counter: %" PRIu32,
                 event_item.event_ref, state->uplink_frame_counter);
    } else {
        /* Missed or corrupted ACK: increment retry counter on FIFO head and retain */
        (void)node_event_fifo_record_retry(fifo, event_item.event_ref);
        ESP_LOGW(TAG, "Event %" PRIu32 " retained in FIFO for retry in next superframe", event_item.event_ref);
    }

    /* 9. REARM_SLEEP: Put radio into low-power sleep */
    state->state = NODE_TDMA_STATE_REARM_SLEEP;
    (void)hal->radio_sleep();

    return ESP_OK;
}
