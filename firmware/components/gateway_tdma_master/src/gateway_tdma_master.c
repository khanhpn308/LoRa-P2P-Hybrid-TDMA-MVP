#include "gateway_tdma_master.h"
#include <string.h>
#include <inttypes.h>
#include "esp_log.h"

static const char *TAG = "gw_tdma_master";

/* Default project test keys (used when unprovisioned in development) */
static const uint8_t DEFAULT_K_BEACON[32] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F, 0x20
};

const char *gateway_tdma_state_to_str(gateway_tdma_state_t state)
{
    switch (state) {
        case GW_TDMA_STATE_IDLE:                 return "IDLE";
        case GW_TDMA_STATE_BEACON_TX:            return "BEACON_TX";
        case GW_TDMA_STATE_BEACON_GUARD:         return "BEACON_GUARD";
        case GW_TDMA_STATE_SLOT_RX:              return "SLOT_RX";
        case GW_TDMA_STATE_SLOT_PROCESS:         return "SLOT_PROCESS";
        case GW_TDMA_STATE_SLOT_ACK_TX:          return "SLOT_ACK_TX";
        case GW_TDMA_STATE_SUPERFRAME_COMPLETE:  return "SUPERFRAME_COMPLETE";
        default:                                 return "UNKNOWN";
    }
}

esp_err_t gateway_tdma_get_default_config(gateway_tdma_config_t *out_cfg)
{
    if (out_cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    (void)memset(out_cfg, 0, sizeof(*out_cfg));
    out_cfg->gw_id = 1U;
    out_cfg->sched_ver = 1U;
    out_cfg->beacon_key_id = 1U;
    (void)memcpy(out_cfg->k_beacon, DEFAULT_K_BEACON, sizeof(out_cfg->k_beacon));
    out_cfg->slot_count = GW_TDMA_MAX_DATA_SLOTS;
    out_cfg->slot_duration_ms = GW_TDMA_DEFAULT_SLOT_DURATION_MS;
    out_cfg->slot_guard_ms = GW_TDMA_DEFAULT_GUARD_MS;
    out_cfg->slot_usable_ms = GW_TDMA_DEFAULT_W_MS;
    out_cfg->beacon_window_ms = GW_TDMA_DEFAULT_BEACON_WINDOW_MS;
    out_cfg->turnaround_guard_ms = GW_TDMA_DEFAULT_TURNAROUND_MS;
    out_cfg->maintenance_interval_sf = GW_TDMA_DEFAULT_MAINT_SF_INTERVAL;
    out_cfg->packet_toa_beacon_ms = GW_TDMA_DEFAULT_TOA_BEACON_MS;
    out_cfg->packet_toa_ack_ms = GW_TDMA_DEFAULT_TOA_ACK_MS;

    return ESP_OK;
}

esp_err_t gateway_tdma_init(gateway_tdma_engine_t *engine,
                            const gateway_tdma_config_t *cfg,
                            const gateway_tdma_radio_hal_t *hal)
{
    if (engine == NULL || cfg == NULL || hal == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (hal->radio_tx == NULL || hal->radio_read_frame == NULL ||
        hal->radio_standby == NULL || hal->get_time_ms == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (cfg->slot_count == 0U || cfg->slot_count > GW_TDMA_MAX_DATA_SLOTS) {
        return ESP_ERR_INVALID_ARG;
    }
    if (cfg->slot_usable_ms + 2U * cfg->slot_guard_ms > cfg->slot_duration_ms) {
        return ESP_ERR_INVALID_ARG;
    }

    (void)memset(engine, 0, sizeof(*engine));
    engine->cfg = *cfg;
    engine->hal = *hal;
    engine->state = GW_TDMA_STATE_IDLE;
    engine->superframe_seq = 1U;
    engine->downlink_frame_counter = 0U;

    esp_err_t err = gateway_wal_init(&engine->wal);
    if (err != ESP_OK) {
        return err;
    }

    err = gateway_crypto_init();
    if (err != ESP_OK) {
        return err;
    }

    /* Initialize airtime policy to 10.0% (100 permille) for Gateway per RAD-001 */
    err = airtime_policy_init(100U);
    if (err != ESP_OK) {
        return err;
    }

    return ESP_OK;
}

static esp_err_t resolve_node_keys(const gateway_tdma_engine_t *engine,
                                   uint8_t node_id,
                                   uint8_t *out_session_sel,
                                   uint8_t out_k_session_up[16],
                                   uint8_t out_k_session_dl[16],
                                   uint8_t out_nonce_prefix[8])
{
    if (engine->cfg.key_lookup_fn != NULL) {
        return engine->cfg.key_lookup_fn(node_id,
                                         out_session_sel,
                                         out_k_session_up,
                                         out_k_session_dl,
                                         out_nonce_prefix);
    }

    if (node_id > GW_TDMA_MAX_DATA_SLOTS) {
        return ESP_ERR_INVALID_ARG;
    }

    const gateway_node_key_entry_t *entry = &engine->cfg.static_keys[node_id];
    if (!entry->is_active) {
        return ESP_ERR_NOT_FOUND;
    }

    if (out_session_sel != NULL) {
        *out_session_sel = entry->session_sel;
    }
    if (out_k_session_up != NULL) {
        (void)memcpy(out_k_session_up, entry->k_session_up, 16);
    }
    if (out_k_session_dl != NULL) {
        (void)memcpy(out_k_session_dl, entry->k_session_dl, 16);
    }
    if (out_nonce_prefix != NULL) {
        (void)memcpy(out_nonce_prefix, entry->session_nonce_prefix, 8);
    }

    return ESP_OK;
}

esp_err_t gateway_tdma_run_superframe(gateway_tdma_engine_t *engine)
{
    if (engine == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    engine->superframe_epoch_ms = engine->hal.get_time_ms();
    engine->is_maintenance = (engine->superframe_seq % engine->cfg.maintenance_interval_sf == 0U);

    /* =========================================================================
     * Phase 1: Slot 0 Beacon Broadcast (DOWN_SYNC_BEACON 0x43, 32 octets)
     * ========================================================================= */
    engine->state = GW_TDMA_STATE_BEACON_TX;

    /* Enforce Gateway regulatory airtime policy check (RAD-001) */
    esp_err_t airtime_err = airtime_policy_check(engine->cfg.packet_toa_beacon_ms);
    if (airtime_err != ESP_OK) {
        /* Fail-closed: airtime budget exhausted -> suppress Beacon emission */
        engine->beacon_blocked_count++;
        ESP_LOGW(TAG, "Beacon TX suppressed fail-closed: airtime duty limit reached (%s)",
                 esp_err_to_name(airtime_err));
    } else {
        uint8_t beacon_buf[32];
        uint32_t epoch_sec = engine->hal.get_time_ms() / 1000U;

        beacon_buf[0] = LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON;
        beacon_buf[1] = engine->cfg.gw_id;
        beacon_buf[2] = (uint8_t)((epoch_sec >> 24) & 0xFFU);
        beacon_buf[3] = (uint8_t)((epoch_sec >> 16) & 0xFFU);
        beacon_buf[4] = (uint8_t)((epoch_sec >> 8) & 0xFFU);
        beacon_buf[5] = (uint8_t)(epoch_sec & 0xFFU);

        beacon_buf[6] = (uint8_t)((engine->superframe_seq >> 24) & 0xFFU);
        beacon_buf[7] = (uint8_t)((engine->superframe_seq >> 16) & 0xFFU);
        beacon_buf[8] = (uint8_t)((engine->superframe_seq >> 8) & 0xFFU);
        beacon_buf[9] = (uint8_t)(engine->superframe_seq & 0xFFU);

        beacon_buf[10] = engine->cfg.sched_ver;
        beacon_buf[11] = engine->is_maintenance ? 0x01U : 0x00U;
        beacon_buf[12] = engine->cfg.beacon_key_id;
        beacon_buf[13] = 0U;
        beacon_buf[14] = 0U;
        beacon_buf[15] = 0U;

        esp_err_t hmac_err = gateway_crypto_compute_beacon_hmac(engine->cfg.k_beacon,
                                                                beacon_buf,
                                                                16U,
                                                                &beacon_buf[16]);
        if (hmac_err == ESP_OK) {
            esp_err_t tx_err = engine->hal.radio_tx(beacon_buf, 32U, 200U);
            if (tx_err == ESP_OK) {
                (void)airtime_policy_record_tx(engine->cfg.packet_toa_beacon_ms);
                engine->beacon_tx_count++;
                ESP_LOGI(TAG, "Beacon TX successful: SF_SEQ=%" PRIu32 ", GW_ID=%u, SchedVer=%u, Maint=%u (32B on-air)",
                         engine->superframe_seq, engine->cfg.gw_id, engine->cfg.sched_ver,
                         engine->is_maintenance ? 1U : 0U);
            } else {
                ESP_LOGE(TAG, "Beacon radio_tx failed: %s", esp_err_to_name(tx_err));
            }
        } else {
            ESP_LOGE(TAG, "Beacon HMAC computation failed: %s", esp_err_to_name(hmac_err));
        }
    }

    /* Turnaround guard from TX Beacon to RX Slot 1 (DEC-MH-06) */
    engine->state = GW_TDMA_STATE_BEACON_GUARD;
    (void)engine->hal.radio_standby();

    /* =========================================================================
     * Phase 2: Static DATA Slots 1..15 Execution Loop
     * ========================================================================= */
    for (uint8_t slot = 1U; slot <= engine->cfg.slot_count; slot++) {
        engine->current_slot = slot;

        uint32_t slot_start_offset = (uint32_t)slot * engine->cfg.slot_duration_ms;
        uint32_t usable_start_offset = slot_start_offset + engine->cfg.slot_guard_ms;
        uint32_t usable_end_offset = usable_start_offset + engine->cfg.slot_usable_ms;
        uint32_t slot_end_offset = slot_start_offset + engine->cfg.slot_duration_ms;

        uint32_t t_usable_start = engine->superframe_epoch_ms + usable_start_offset;
        uint32_t t_usable_end = engine->superframe_epoch_ms + usable_end_offset;
        uint32_t t_slot_end = engine->superframe_epoch_ms + slot_end_offset;

        /* Align to slot usable start window (after leading guard) */
        uint32_t now = engine->hal.get_time_ms();
        if (now < t_usable_start && engine->hal.delay_ms != NULL) {
            engine->hal.delay_ms(t_usable_start - now);
        }

        /* Open Continuous/Timed RX for assigned NODE_ID == slot */
        engine->state = GW_TDMA_STATE_SLOT_RX;
        if (engine->hal.radio_rx_start != NULL) {
            (void)engine->hal.radio_rx_start();
        }

        now = engine->hal.get_time_ms();
        uint32_t wait_ms = (now < t_usable_end) ? (t_usable_end - now) : 0U;

        uint8_t rx_buf[128];
        size_t rx_len = 0U;
        int16_t rssi = 0;
        int8_t snr = 0;

        esp_err_t rx_err = engine->hal.radio_read_frame(rx_buf, &rx_len, &rssi, &snr, wait_ms);

        if (engine->hal.radio_rx_stop != NULL) {
            (void)engine->hal.radio_rx_stop();
        }
        (void)engine->hal.radio_standby();

        if (rx_err != ESP_OK || rx_len == 0U) {
            /* Slot idle timeout: node had no event or packet missed */
            engine->slot_idle_count++;
            /* Zero stray TX: advance cleanly */
        } else {
            /* Frame received: enter process state */
            engine->state = GW_TDMA_STATE_SLOT_PROCESS;

            ESP_LOGI(TAG, "[RF RX SLOT #%u] Frame received: %zu bytes, Type=0x%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                     slot, rx_len, rx_buf[0], (int)rssi, (double)snr / 4.0);

            if (rx_buf[0] == LORA_MAC_V2_TYPE_UP_JOIN_HELLO ||
                rx_buf[0] == LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF ||
                rx_buf[0] == LORA_MAC_V2_TYPE_UP_JOIN_READY) {
                if (engine->cfg.join_frame_fn != NULL) {
                    (void)engine->cfg.join_frame_fn(rx_buf, rx_len, rssi, snr);
                }
            } else if (!engine->is_maintenance) {
                /* --- Normal Superframe: Expect UP_EVENT (0x41, 26 octets) --- */
                if (rx_len != LORA_MAC_V2_LEN_UP_EVENT) {
                    engine->corrupted_packet_count++;
                } else {
                    lora_mac_v2_header_t hdr;
                    esp_err_t hdr_err = lora_mac_v2_header_parse(rx_buf, rx_len, &hdr);

                    if (hdr_err != ESP_OK ||
                        hdr.ver_type != LORA_MAC_V2_TYPE_UP_EVENT ||
                        hdr.node_id != slot) {
                        /* Header invalid or node ID does not match current slot */
                        engine->corrupted_packet_count++;
                    } else if (hdr.frame_counter <= engine->node_last_frame_counter[slot]) {
                        /* Anti-replay violation: frame counter must strictly increase */
                        engine->corrupted_packet_count++;
                    } else {
                        uint8_t k_session_up[16];
                        uint8_t k_session_dl[16];
                        uint8_t nonce_prefix[8];
                        uint8_t session_sel = 0U;

                        esp_err_t key_err = resolve_node_keys(engine, slot, &session_sel,
                                                              k_session_up, k_session_dl, nonce_prefix);

                        if (key_err != ESP_OK) {
                            engine->corrupted_packet_count++;
                        } else {
                            uint8_t nonce[13];
                            (void)lora_mac_v2_build_nonce(nonce_prefix,
                                                          LORA_MAC_V2_DIR_UPLINK,
                                                          hdr.frame_counter,
                                                          nonce);

                            uint8_t pt[11];
                            esp_err_t dec_err = gateway_crypto_decrypt_up_event(k_session_up,
                                                                                nonce,
                                                                                rx_buf,
                                                                                7U,
                                                                                &rx_buf[7],
                                                                                11U,
                                                                                &rx_buf[18],
                                                                                pt);

                            if (dec_err != ESP_OK) {
                                /* Corrupted MIC / tag mismatch: reject cleanly without ACK or WAL */
                                engine->corrupted_mic_count++;
                            } else {
                                /* Valid UP_EVENT authenticated */
                                engine->node_last_frame_counter[slot] = hdr.frame_counter;

                                lora_mac_v2_up_event_t up_ev;
                                (void)lora_mac_v2_up_event_deserialize(pt, 11U, &up_ev);

                                /* Commit verified event intent into bounded WAL (DEC-127-05 / D12 §6.3) */
                                gateway_wal_event_t wal_ev;
                                wal_ev.node_id = hdr.node_id;
                                wal_ev.session_sel = hdr.session_sel;
                                wal_ev.frame_counter = hdr.frame_counter;
                                wal_ev.event_ref = up_ev.event_ref;
                                wal_ev.event_time = up_ev.event_time;
                                wal_ev.event_code = up_ev.event_code;
                                wal_ev.event_value = up_ev.event_value;
                                wal_ev.received_at_ms = engine->hal.get_time_ms();
                                wal_ev.rssi_dbm = rssi;
                                wal_ev.snr_db_quarter = snr;

                                (void)gateway_wal_push(&engine->wal, &wal_ev);
                                engine->up_event_received_count++;

                                /* Prepare and emit immediate in-slot DOWN_EVENT_ACK (0x42, 19B) */
                                engine->state = GW_TDMA_STATE_SLOT_ACK_TX;

                                esp_err_t ack_airtime_err = airtime_policy_check(engine->cfg.packet_toa_ack_ms);
                                if (ack_airtime_err != ESP_OK) {
                                    /* Airtime budget exhausted: suppress ACK gracefully */
                                    engine->airtime_blocked_ack_count++;
                                } else {
                                    uint8_t ack_packet[19];
                                    lora_mac_v2_header_t ack_hdr;
                                    ack_hdr.ver_type = LORA_MAC_V2_TYPE_DOWN_EVENT_ACK;
                                    ack_hdr.node_id = slot;
                                    ack_hdr.session_sel = hdr.session_sel;
                                    ack_hdr.frame_counter = ++engine->downlink_frame_counter;

                                    size_t hdr_written = 0;
                                    (void)lora_mac_v2_header_encode(&ack_hdr, ack_packet, 19U, &hdr_written);

                                    lora_mac_v2_down_event_ack_t ack_payload;
                                    ack_payload.event_ref = up_ev.event_ref;

                                    uint8_t ack_pt[4];
                                    size_t pt_written = 0;
                                    (void)lora_mac_v2_down_event_ack_serialize(&ack_payload, ack_pt, 4U, &pt_written);

                                    uint8_t dl_nonce[13];
                                    (void)lora_mac_v2_build_nonce(nonce_prefix,
                                                                  LORA_MAC_V2_DIR_DOWNLINK,
                                                                  engine->downlink_frame_counter,
                                                                  dl_nonce);

                                    esp_err_t enc_err = gateway_crypto_encrypt_down_ack(k_session_dl,
                                                                                        dl_nonce,
                                                                                        ack_packet,
                                                                                        7U,
                                                                                        ack_pt,
                                                                                        4U,
                                                                                        &ack_packet[7],
                                                                                        &ack_packet[11]);

                                    if (enc_err == ESP_OK) {
                                        esp_err_t tx_ack_err = engine->hal.radio_tx(ack_packet, 19U, 100U);
                                        if (tx_ack_err == ESP_OK) {
                                            (void)airtime_policy_record_tx(engine->cfg.packet_toa_ack_ms);
                                            engine->ack_sent_count++;
                                        }
                                    }
                                    gateway_crypto_zeroize(ack_pt, sizeof(ack_pt));
                                }
                            }
                            gateway_crypto_zeroize(k_session_up, sizeof(k_session_up));
                            gateway_crypto_zeroize(k_session_dl, sizeof(k_session_dl));
                        }
                    }
                }
            } else {
                /* --- Maintenance Superframe: Process UP_HEALTH_REPLY or UP_DIAG_METRICS --- */
                if (rx_len == LORA_MAC_V2_LEN_UP_HEALTH_REPLY) {
                    lora_mac_v2_header_t hdr;
                    esp_err_t hdr_err = lora_mac_v2_header_parse(rx_buf, rx_len, &hdr);

                    if (hdr_err == ESP_OK &&
                        hdr.ver_type == LORA_MAC_V2_TYPE_UP_HEALTH_REPLY &&
                        hdr.node_id == slot) {
                        uint8_t k_session_up[16];
                        uint8_t nonce_prefix[8];
                        esp_err_t key_err = resolve_node_keys(engine, slot, NULL, k_session_up, NULL, nonce_prefix);

                        if (key_err == ESP_OK) {
                            uint8_t nonce[13];
                            (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_UPLINK, hdr.frame_counter, nonce);

                            uint8_t pt[6];
                            esp_err_t dec_err = gateway_crypto_decrypt_up_health(k_session_up, nonce, rx_buf, 7U,
                                                                                 &rx_buf[7], 6U, &rx_buf[13], pt);
                            if (dec_err == ESP_OK) {
                                engine->maintenance_health_count++;
                            } else {
                                engine->corrupted_mic_count++;
                            }
                            gateway_crypto_zeroize(k_session_up, sizeof(k_session_up));
                        }
                    } else {
                        engine->corrupted_packet_count++;
                    }
                } else if (rx_len == LORA_MAC_V2_LEN_UP_DIAG_METRICS) {
                    lora_mac_v2_header_t hdr;
                    esp_err_t hdr_err = lora_mac_v2_header_parse(rx_buf, rx_len, &hdr);

                    if (hdr_err == ESP_OK &&
                        hdr.ver_type == LORA_MAC_V2_TYPE_UP_DIAG_METRICS &&
                        hdr.node_id == slot) {
                        uint8_t k_session_up[16];
                        uint8_t nonce_prefix[8];
                        esp_err_t key_err = resolve_node_keys(engine, slot, NULL, k_session_up, NULL, nonce_prefix);

                        if (key_err == ESP_OK) {
                            uint8_t nonce[13];
                            (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_UPLINK, hdr.frame_counter, nonce);

                            uint8_t pt[8];
                            esp_err_t dec_err = gateway_crypto_decrypt_up_diag(k_session_up, nonce, rx_buf, 7U,
                                                                               &rx_buf[7], 8U, &rx_buf[15], pt);
                            if (dec_err == ESP_OK) {
                                lora_mac_v2_up_diag_metrics_t diag;
                                (void)lora_mac_v2_up_diag_metrics_deserialize(pt, 8U, &diag);
                                engine->node_last_diag_seq[slot] = diag.diag_seq;
                                engine->node_last_dropped_event_count[slot] = diag.dropped_event_count;
                                engine->maintenance_diag_count++;
                            } else {
                                engine->corrupted_mic_count++;
                            }
                            gateway_crypto_zeroize(k_session_up, sizeof(k_session_up));
                        }
                    } else {
                        engine->corrupted_packet_count++;
                    }
                } else {
                    engine->corrupted_packet_count++;
                }
            }
        }

        /* Hold in STANDBY until slot trailing boundary */
        (void)engine->hal.radio_standby();
        now = engine->hal.get_time_ms();
        if (now < t_slot_end && engine->hal.delay_ms != NULL) {
            engine->hal.delay_ms(t_slot_end - now);
        }
    }

    engine->superframe_seq++;
    engine->state = GW_TDMA_STATE_SUPERFRAME_COMPLETE;
    return ESP_OK;
}
