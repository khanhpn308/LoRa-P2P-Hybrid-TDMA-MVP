#include "gateway_radio_bridge.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "sx1276_driver.h"
#include "gateway_transport.h"
#include "gateway_wal.h"
#include "gateway_session_mgr.h"
#include "gateway_liveness.h"
#include "gateway_rf_metrics.h"

static const char *TAG = "gateway_master";

static StackType_t s_gateway_task_stack[GATEWAY_TASK_STACK_SIZE_BYTES];
static StaticTask_t s_gateway_task_tcb;
static TaskHandle_t s_gateway_rx_task_handle = NULL;
static uint32_t s_downlink_frame_counter = 0;
static gateway_v2_join_engine_t *s_join_engine_ptr = NULL;
static gateway_wal_t *s_wal_ptr = NULL;
static char s_gateway_id[32] = "gw-a";

esp_err_t gateway_radio_bridge_init(const gateway_radio_bridge_config_t *cfg)
{
    if (cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_join_engine_ptr = cfg->join_engine;
    s_wal_ptr = cfg->wal;
    if (cfg->gateway_id != NULL) {
        strncpy(s_gateway_id, cfg->gateway_id, sizeof(s_gateway_id) - 1);
        s_gateway_id[sizeof(s_gateway_id) - 1] = '\0';
    }
    esp_err_t rf_init_err = gateway_rf_metrics_init(s_gateway_id, cfg->gateway_epoch);
    if (rf_init_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway RF metrics: %s", esp_err_to_name(rf_init_err));
        return rf_init_err;
    }
    return ESP_OK;
}

esp_err_t process_radio_frame(const sx1276_rx_frame_t *frame)
{
    if (frame == NULL || frame->length == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    const uint8_t *payload = frame->payload;
    size_t length = frame->length;
    int16_t rssi = frame->rssi_dbm;
    int8_t snr = frame->snr_db_quarter;
    uint8_t channel_idx = frame->channel_idx;
    uint64_t rx_monotonic_us = frame->timestamp_us;
    uint8_t msg_type = payload[0];
    float snr_f = (float)snr / 4.0f;

    switch (msg_type) {
        case LORA_MAC_V2_TYPE_UP_JOIN_HELLO: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_HELLO && s_join_engine_ptr != NULL) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_HELLO (68B): MAC=%02X:%02X:%02X:%02X:%02X:%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[1], payload[2], payload[3], payload[4], payload[5], payload[6],
                         rssi, (double)snr_f);

                uint8_t req_mac[6];
                memcpy(req_mac, &payload[1], 6);
                approved_node_entry_t *entry = find_or_create_node_entry(req_mac);
                if (entry) {
                    /* Cache this hello packet in case approval arrives while waiting */
                    memcpy(entry->cached_hello, payload, LORA_MAC_V2_LEN_UP_JOIN_HELLO);
                    entry->cached_rssi = rssi;
                    entry->cached_snr = snr;
                    entry->has_cached_hello = true;
                    entry->approved = false; /* Stateless bridge: no auto-grant */
                }

                /* Build and immediately transmit DOWN_JOIN_WAIT (20B) to the Node */
                uint8_t wait_buf[LORA_MAC_V2_LEN_DOWN_JOIN_WAIT];
                size_t wait_len = 0;
                esp_err_t b_err = gateway_v2_join_build_wait(
                    s_join_engine_ptr,
                    payload,
                    length,
                    NULL,
                    wait_buf,
                    &wait_len
                );
                if (b_err == ESP_OK) {
                    /* Allow Node time to switch from TX to RX (RF turnaround margin ~40ms) */
                    vTaskDelay(pdMS_TO_TICKS(40));
                    ESP_LOGI(TAG, "[JOIN TX] Transmitting immediate DOWN_JOIN_WAIT (%zu bytes) to MAC %02X:%02X:%02X:%02X:%02X:%02X...",
                             wait_len, req_mac[0], req_mac[1], req_mac[2], req_mac[3], req_mac[4], req_mac[5]);
                    esp_err_t tx_err = sx1276_tx(wait_buf, (uint8_t)wait_len, pdMS_TO_TICKS(300));
                    if (tx_err == ESP_OK) {
                        ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_WAIT transmitted successfully for MAC %02X:%02X:%02X:%02X:%02X:%02X",
                                 req_mac[0], req_mac[1], req_mac[2], req_mac[3], req_mac[4], req_mac[5]);
                    } else {
                        ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_WAIT: %s", esp_err_to_name(tx_err));
                    }
                } else {
                    ESP_LOGE(TAG, "[JOIN TX] Failed to build DOWN_JOIN_WAIT: %s", esp_err_to_name(b_err));
                }

                /* Forward Join Request to Backend over MQTT for User Approval */
                char join_json[256];
                int join_len = snprintf(join_json, sizeof(join_json),
                    "{\"gateway_id\":\"%s\",\"device_mac\":\"%02x%02x%02x%02x%02x%02x\",\"rssi\":%d,\"snr\":%.1f}",
                    s_gateway_id,
                    req_mac[0], req_mac[1], req_mac[2], req_mac[3], req_mac[4], req_mac[5],
                    rssi, (double)snr_f);
                if (join_len > 0) {
                    (void)gateway_transport_publish_join_relay((const uint8_t *)join_json, (size_t)join_len);
                    ESP_LOGI(TAG, "[JOIN RELAY] Forwarded UP_JOIN_HELLO (MAC=%02X:%02X:%02X:%02X:%02X:%02X) to Backend MQTT for user approval",
                             req_mac[0], req_mac[1], req_mac[2], req_mac[3], req_mac[4], req_mac[5]);
                }

                /* Re-enable 24/7 continuous RX on Gateway */
                (void)sx1276_start_rx_continuous();
                return ESP_OK;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF && s_join_engine_ptr != NULL) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_KEY_CONFIRM (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                uint8_t finish_buf[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
                size_t finish_len = 0;
                esp_err_t c_err = gateway_v2_join_handle_confirm(
                    s_join_engine_ptr,
                    payload,
                    length,
                    NULL, /* edge finish */
                    finish_buf,
                    &finish_len
                );
                if (c_err == ESP_OK) {
                    /* Allow Node time to switch from TX to RXSINGLE (RF turnaround margin) */
                    vTaskDelay(pdMS_TO_TICKS(40));
                    ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_FINISH (%zu bytes) to Node #%u on 920.250 MHz (CH0)...", finish_len, payload[2]);
                    esp_err_t tx_err = sx1276_tx(finish_buf, (uint8_t)finish_len, pdMS_TO_TICKS(300));
                    if (tx_err == ESP_OK) {
                        ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_FINISH transmitted successfully");
                    } else {
                        ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_FINISH: %s", esp_err_to_name(tx_err));
                    }
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_KEY_CONFIRM: %s", esp_err_to_name(c_err));
                }
                return c_err;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_JOIN_READY: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_READY && s_join_engine_ptr != NULL) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_READY (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                esp_err_t r_err = gateway_v2_join_handle_ready(
                    s_join_engine_ptr,
                    payload,
                    length
                );
                if (r_err == ESP_OK) {
                    ESP_LOGI(TAG, "[JOIN SUCCESS] Node #%u Join complete! Session committed in INSTALLED_INACTIVE state.", payload[2]);
                    (void)gateway_save_node_session(payload[2]);
                    gateway_session_mgr_clear_revocation(payload[2]);
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_READY: %s", esp_err_to_name(r_err));
                }
                return r_err;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_EVENT: {
            if (length == LORA_MAC_V2_LEN_UP_EVENT) {
                lora_mac_v2_header_t hdr;
                esp_err_t hdr_err = lora_mac_v2_header_parse(payload, length, &hdr);
                if (hdr_err != ESP_OK || hdr.ver_type != LORA_MAC_V2_TYPE_UP_EVENT) {
                    ESP_LOGW(TAG, "[EVENT RX] Invalid UP_EVENT header");
                    return ESP_ERR_INVALID_ARG;
                }

                if (hdr.node_id > 0 && gateway_session_mgr_is_node_revoked(hdr.node_id)) {
                    gateway_revoked_node_info_t *rev_info = gateway_session_mgr_get_revoked_info(hdr.node_id);
                    ESP_LOGW(TAG, "[EVENT RX] Node #%u is REVOKED. Sending DOWN_REVOKE instead of ACK.", hdr.node_id);
                    vTaskDelay(pdMS_TO_TICKS(20));

                    uint8_t revoke_packet[19];
                    lora_mac_v2_header_t rev_hdr = {
                        .ver_type = LORA_MAC_V2_TYPE_DOWN_REVOKE,
                        .node_id = hdr.node_id,
                        .session_sel = hdr.session_sel,
                        .frame_counter = ++s_downlink_frame_counter,
                    };
                    size_t rev_hdr_written = 0;
                    (void)lora_mac_v2_header_encode(&rev_hdr, revoke_packet, 19U, &rev_hdr_written);

                    lora_mac_v2_down_revoke_t rev_payload = {
                        .revoke_reason = 0x01,
                    };
                    uint8_t rev_pt[4];
                    size_t pt_written = 0;
                    (void)lora_mac_v2_down_revoke_serialize(&rev_payload, rev_pt, 4U, &pt_written);

                    if (rev_info != NULL) {
                        uint8_t dl_nonce[13];
                        (void)lora_mac_v2_build_nonce(rev_info->nonce_prefix,
                                                      LORA_MAC_V2_DIR_DOWNLINK,
                                                      rev_hdr.frame_counter,
                                                      dl_nonce);

                        esp_err_t enc_err = lora_mac_crypto_encrypt_down_revoke(
                            rev_info->k_session_dl,
                            dl_nonce,
                            revoke_packet, 7U,
                            rev_pt, 4U,
                            &revoke_packet[7],
                            &revoke_packet[11]);
                        if (enc_err == ESP_OK) {
                            ESP_LOGI(TAG, "[REVOKE TX] Sending DOWN_REVOKE (19B) to Node #%u...", hdr.node_id);
                            esp_err_t tx_err = sx1276_tx(revoke_packet, 19U, pdMS_TO_TICKS(100));
                            if (tx_err == ESP_OK) {
                                ESP_LOGI(TAG, "[REVOKE TX] DOWN_REVOKE transmitted successfully to Node #%u", hdr.node_id);
                            } else {
                                ESP_LOGE(TAG, "[REVOKE TX] Failed to transmit DOWN_REVOKE: %s", esp_err_to_name(tx_err));
                            }
                        }
                    }
                    return ESP_OK;
                }

                uint8_t k_session_up[16];
                uint8_t k_session_dl[16];
                uint8_t nonce_prefix[8];
                memcpy(nonce_prefix, DEFAULT_NONCE_PREFIX, sizeof(nonce_prefix));
                esp_err_t key_err = hal_session_key_lookup(hdr.node_id, NULL, k_session_up, k_session_dl, nonce_prefix);
                if (key_err != ESP_OK && s_join_engine_ptr != NULL) {
                    /* Fallback to in-memory pending joins */
                    size_t slot_idx = (size_t)(hdr.node_id - 1);
                    if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS && s_join_engine_ptr->pending_joins[slot_idx].active) {
                        memcpy(k_session_up, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_up, 16);
                        memcpy(k_session_dl, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_dl, 16);
                        key_err = ESP_OK;
                    }
                }
                if (key_err != ESP_OK) {
                    ESP_LOGW(TAG, "[EVENT RX] Unknown keys for Node #%u", hdr.node_id);
                    return key_err;
                }

                uint8_t nonce[13];
                (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_UPLINK, hdr.frame_counter, nonce);

                uint8_t pt[11];
                esp_err_t dec_err = lora_mac_crypto_decrypt_up_event(k_session_up,
                                                                     nonce,
                                                                     payload, 7U,
                                                                     &payload[7], 11U,
                                                                     &payload[18],
                                                                     pt);
                if (dec_err != ESP_OK) {
                    ESP_LOGW(TAG, "[EVENT RX] Decryption/MIC verification failed for Node #%u", hdr.node_id);
                    return dec_err;
                }

                lora_mac_v2_up_event_t up_ev;
                (void)lora_mac_v2_up_event_deserialize(pt, 11U, &up_ev);
                ESP_LOGI(TAG, "==================================================");
                ESP_LOGI(TAG, ">>> VALID UP_EVENT RECEIVED! <<< Node #%u: Ref=%" PRIu32 ", Code=%u, Val=%d | RSSI=%d dBm, SNR=%.1f dB",
                         hdr.node_id, up_ev.event_ref, up_ev.event_code, up_ev.event_value, rssi, (double)snr_f);
                ESP_LOGI(TAG, "==================================================");

                /* Update node liveness tracking */
                gateway_liveness_record_event(hdr.node_id);

                /* Record and publish RF metrics for validated UP_EVENT (MIC verified) */
                uint64_t sample_seq = 0;
                (void)gateway_rf_metrics_record_and_publish_node(
                    hdr.node_id,
                    channel_idx,
                    rssi,
                    snr,
                    rx_monotonic_us,
                    "UP_EVENT",
                    true,
                    &sample_seq
                );

                /* Commit to WAL with RF measurement identity */
                if (s_wal_ptr != NULL) {
                    gateway_wal_event_t wal_ev = {
                        .node_id = hdr.node_id,
                        .session_sel = hdr.session_sel,
                        .frame_counter = hdr.frame_counter,
                        .event_ref = up_ev.event_ref,
                        .event_time = up_ev.event_time,
                        .event_code = up_ev.event_code,
                        .event_value = up_ev.event_value,
                        .received_at_ms = (uint32_t)(esp_timer_get_time() / 1000ULL),
                        .rssi_dbm = rssi,
                        .snr_db_quarter = snr,
                        .channel_idx = channel_idx,
                        .rx_monotonic_us = rx_monotonic_us,
                        .sample_seq = sample_seq,
                    };
                    (void)gateway_wal_push(s_wal_ptr, &wal_ev);
                }

                /* Format optional 'rf' block for alert JSON (Issue #392 / #400) */
                char rf_block[160] = "";
                esp_err_t rf_fmt_err = gateway_rf_metrics_format_alert_block(
                    rf_block,
                    sizeof(rf_block),
                    sample_seq,
                    rx_monotonic_us,
                    channel_idx,
                    rssi,
                    snr
                );
                if (rf_fmt_err != ESP_OK) {
                    ESP_LOGW(TAG, "[EVENT RX] RF alert block formatting failed (%s); proceeding without RF block",
                             esp_err_to_name(rf_fmt_err));
                    rf_block[0] = '\0';
                }

                /* Publish Event to Backend over MQTT for UI Charts */
                const char *gw_epoch = gateway_rf_metrics_get_epoch();
                char alert_payload[512];
                int alert_len;
                if (rf_block[0] != '\0') {
                    alert_len = snprintf(alert_payload, sizeof(alert_payload),
                        "{\"schema_version\":\"1.0-draft\",\"event_id\":\"%s:%s:%" PRIu64 "\",\"gateway_id\":\"%s\",\"gateway_epoch\":\"%s\",\"event_seq\":\"%" PRIu64 "\",\"observed_at\":null,\"observed_time_source\":\"unknown\",\"radio_rx_monotonic_us\":\"%" PRIu64 "\",\"buffered\":false,\"node_id\":%u,\"superframe_seq\":1,\"seq_num\":1,\"schedule_version\":1,\"event_code\":%u,\"event_value\":%d,\"battery_mv\":3300,\"severity\":\"P3_NORMAL\",\"radio_ack_sent\":true,\"data\":{\"event_ref\":%" PRIu32 ",\"event_code\":%u,\"event_value\":%d},%s}",
                        s_gateway_id, gw_epoch, sample_seq,
                        s_gateway_id, gw_epoch, sample_seq,
                        rx_monotonic_us,
                        hdr.node_id, up_ev.event_code, up_ev.event_value,
                        up_ev.event_ref, up_ev.event_code, up_ev.event_value,
                        rf_block);
                } else {
                    alert_len = snprintf(alert_payload, sizeof(alert_payload),
                        "{\"schema_version\":\"1.0-draft\",\"event_id\":\"%s:%s:%" PRIu32 "\",\"gateway_id\":\"%s\",\"gateway_epoch\":\"%s\",\"event_seq\":\"%" PRIu32 "\",\"observed_at\":null,\"observed_time_source\":\"unknown\",\"radio_rx_monotonic_us\":\"%" PRIu64 "\",\"buffered\":false,\"node_id\":%u,\"superframe_seq\":1,\"seq_num\":1,\"schedule_version\":1,\"event_code\":%u,\"event_value\":%d,\"battery_mv\":3300,\"severity\":\"P3_NORMAL\",\"radio_ack_sent\":true,\"data\":{\"event_ref\":%" PRIu32 ",\"event_code\":%u,\"event_value\":%d}}",
                        s_gateway_id, gw_epoch, up_ev.event_ref,
                        s_gateway_id, gw_epoch, up_ev.event_ref,
                        rx_monotonic_us,
                        hdr.node_id, up_ev.event_code, up_ev.event_value,
                        up_ev.event_ref, up_ev.event_code, up_ev.event_value);
                }

                if (alert_len > 0 && (size_t)alert_len < sizeof(alert_payload)) {
                    esp_err_t pub_err = gateway_transport_publish_event((const uint8_t *)alert_payload, (size_t)alert_len);
                    if (pub_err == ESP_OK) {
                        ESP_LOGI(TAG, "[EVENT TX] Published event to MQTT: Node #%u, Code=%u, Val=%d",
                                 hdr.node_id, up_ev.event_code, up_ev.event_value);
                    } else {
                        ESP_LOGW(TAG, "[EVENT TX] Failed to enqueue event to transport: %s", esp_err_to_name(pub_err));
                    }
                } else {
                    ESP_LOGE(TAG, "[EVENT TX] Alert payload format error or truncation: len=%d", alert_len);
                }

                /* Small turnaround delay before sending ACK */
                vTaskDelay(pdMS_TO_TICKS(20));

                uint8_t ack_packet[19];
                lora_mac_v2_header_t ack_hdr = {
                    .ver_type = LORA_MAC_V2_TYPE_DOWN_EVENT_ACK,
                    .node_id = hdr.node_id,
                    .session_sel = hdr.session_sel,
                    .frame_counter = ++s_downlink_frame_counter,
                };
                size_t ack_hdr_written = 0;
                (void)lora_mac_v2_header_encode(&ack_hdr, ack_packet, 19U, &ack_hdr_written);

                lora_mac_v2_down_event_ack_t ack_payload = {
                    .event_ref = up_ev.event_ref,
                };
                uint8_t ack_pt[4];
                size_t pt_written = 0;
                (void)lora_mac_v2_down_event_ack_serialize(&ack_payload, ack_pt, 4U, &pt_written);

                uint8_t dl_nonce[13];
                (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_DOWNLINK, ack_hdr.frame_counter, dl_nonce);

                esp_err_t enc_err = lora_mac_crypto_encrypt_down_ack(k_session_dl,
                                                                     dl_nonce,
                                                                     ack_packet, 7U,
                                                                     ack_pt, 4U,
                                                                     &ack_packet[7],
                                                                     &ack_packet[11]);
                if (enc_err == ESP_OK) {
                    ESP_LOGI(TAG, "[EVENT ACK TX] Sending DOWN_EVENT_ACK (19B) for Ref=%" PRIu32 " to Node #%u...",
                             up_ev.event_ref, hdr.node_id);
                    esp_err_t tx_ack_err = sx1276_tx(ack_packet, 19U, pdMS_TO_TICKS(100));
                    if (tx_ack_err == ESP_OK) {
                        ESP_LOGI(TAG, "[EVENT ACK TX] DOWN_EVENT_ACK transmitted successfully");
                    } else {
                        ESP_LOGE(TAG, "[EVENT ACK TX] Failed to transmit ACK: %s", esp_err_to_name(tx_ack_err));
                    }
                }
                return ESP_OK;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_HEARTBEAT_ACK: {
            if (length >= 2) {
                uint8_t ack_node_id = payload[1];
                gateway_liveness_record_node_alive(ack_node_id);
                ESP_LOGI(TAG, "[HEARTBEAT ACK] Node #%u confirmed ALIVE via LoRa (RSSI=%d dBm)",
                         ack_node_id, rssi);

                /* Record and publish RF metrics for UP_HEARTBEAT_ACK (unverified / CRC only) */
                uint64_t hb_seq = 0;
                (void)gateway_rf_metrics_record_and_publish_node(
                    ack_node_id,
                    channel_idx,
                    rssi,
                    snr,
                    rx_monotonic_us,
                    "UP_HEARTBEAT_ACK",
                    false,
                    &hb_seq
                );

                if (ack_node_id > 0 && gateway_session_mgr_is_node_revoked(ack_node_id)) {
                    gateway_revoked_node_info_t *rev_info = gateway_session_mgr_get_revoked_info(ack_node_id);
                    ESP_LOGW(TAG, "[HEARTBEAT ACK] Node #%u is REVOKED. Sending DOWN_REVOKE in RX window.", ack_node_id);
                    vTaskDelay(pdMS_TO_TICKS(20));

                    uint8_t revoke_packet[19];
                    lora_mac_v2_header_t rev_hdr = {
                        .ver_type = LORA_MAC_V2_TYPE_DOWN_REVOKE,
                        .node_id = ack_node_id,
                        .session_sel = 0,
                        .frame_counter = ++s_downlink_frame_counter,
                    };
                    size_t rev_hdr_written = 0;
                    (void)lora_mac_v2_header_encode(&rev_hdr, revoke_packet, 19U, &rev_hdr_written);

                    lora_mac_v2_down_revoke_t rev_payload = {
                        .revoke_reason = 0x01,
                    };
                    uint8_t rev_pt[4];
                    size_t pt_written = 0;
                    (void)lora_mac_v2_down_revoke_serialize(&rev_payload, rev_pt, 4U, &pt_written);

                    if (rev_info != NULL) {
                        uint8_t dl_nonce[13];
                        (void)lora_mac_v2_build_nonce(rev_info->nonce_prefix,
                                                      LORA_MAC_V2_DIR_DOWNLINK,
                                                      rev_hdr.frame_counter,
                                                      dl_nonce);

                        esp_err_t enc_err = lora_mac_crypto_encrypt_down_revoke(
                            rev_info->k_session_dl,
                            dl_nonce,
                            revoke_packet, 7U,
                            rev_pt, 4U,
                            &revoke_packet[7],
                            &revoke_packet[11]);
                        if (enc_err == ESP_OK) {
                            ESP_LOGI(TAG, "[HEARTBEAT REVOKE TX] Sending DOWN_REVOKE (19B) to Node #%u...", ack_node_id);
                            esp_err_t tx_err = sx1276_tx(revoke_packet, 19U, pdMS_TO_TICKS(100));
                            if (tx_err == ESP_OK) {
                                ESP_LOGI(TAG, "[HEARTBEAT REVOKE TX] DOWN_REVOKE transmitted successfully to Node #%u", ack_node_id);
                            } else {
                                ESP_LOGE(TAG, "[HEARTBEAT REVOKE TX] Failed to transmit DOWN_REVOKE: %s", esp_err_to_name(tx_err));
                            }
                        }
                    }
                    return ESP_OK;
                }
            }
            return ESP_OK;
        }

        default:
            ESP_LOGD(TAG, "[RF RX] Non-join frame: type=0x%02X, len=%zu", msg_type, length);
            break;
    }
    return ESP_OK;
}

esp_err_t process_join_packet(const uint8_t *payload, size_t length, int16_t rssi, int8_t snr)
{
    sx1276_rx_frame_t f;
    memset(&f, 0, sizeof(f));
    if (payload != NULL && length <= sizeof(f.payload)) {
        memcpy(f.payload, payload, length);
        f.length = (uint8_t)length;
    }
    f.rssi_dbm = rssi;
    f.snr_db_quarter = snr;
    f.channel_idx = 0;
    f.timestamp_us = (uint64_t)esp_timer_get_time();
    return process_radio_frame(&f);
}

void gateway_radio_rx_task(void *pvParameters)
{
    (void)pvParameters;
    ESP_LOGI(TAG, "Gateway Continuous RX Task running (24/7 active on 920.250 MHz CH0)");

    /* Start in continuous RX to listen for OTA join handshakes and event uplinks */
    (void)sx1276_start_rx_continuous();

    int64_t last_channel_poll_us = esp_timer_get_time();

    while (1) {
        /* Check for incoming LoRa packet with 20ms wait */
        sx1276_rx_frame_t rx_frame;
        esp_err_t rx_err = sx1276_read_frame(&rx_frame, pdMS_TO_TICKS(20));
        if (rx_err == ESP_OK && rx_frame.length > 0) {
            ESP_LOGI(TAG, "[RF RX] Frame received: len=%u B, Type=0x%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                     rx_frame.length, rx_frame.payload[0], rx_frame.rssi_dbm, (float)rx_frame.snr_db_quarter / 4.0f);
            (void)process_radio_frame(&rx_frame);
            (void)sx1276_start_rx_continuous();
        }

        /* Periodic channel RSSI sampling (every 30 seconds, matching heartbeat cadence) */
        int64_t now_us = esp_timer_get_time();
        if (now_us - last_channel_poll_us >= 30000000LL) {
            last_channel_poll_us = now_us;
            (void)gateway_rf_metrics_sample_and_publish_channel();
        }
    }
}

esp_err_t gateway_radio_bridge_start(void)
{
    s_gateway_rx_task_handle = xTaskCreateStatic(
        gateway_radio_rx_task,
        "gw_rx_task",
        GATEWAY_TASK_STACK_SIZE_BYTES,
        NULL,
        5, /* Priority */
        s_gateway_task_stack,
        &s_gateway_task_tcb
    );
    if (s_gateway_rx_task_handle == NULL) {
        ESP_LOGE(TAG, "Failed to create gateway radio RX task");
        return ESP_FAIL;
    }
    return ESP_OK;
}
