#include "node_event_tx.h"

#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"
#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "node_event_fifo.h"
#include "node_smart_backoff.h"
#include "node_cad_backoff.h"
#include "node_radio_hal.h"
#include "node_arq.h"

static const char *TAG = "node_event_tx";

esp_err_t node_cad_event_tx_and_ack(const node_mac_config_t *cfg,
                                    node_event_fifo_t *fifo,
                                    uint32_t *inout_uplink_counter,
                                    bool *out_event_acked)
{
    if (cfg == NULL || fifo == NULL || inout_uplink_counter == NULL || out_event_acked == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_event_acked = false;

    node_event_fifo_item_t event_item;
    esp_err_t peek_err = node_event_fifo_peek_pending(fifo, &event_item);
    if (peek_err != ESP_OK) {
        ESP_LOGD(TAG, "No pending event in FIFO");
        return ESP_OK;
    }

    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, ">>> CAD + ARQ EVENT TRANSMISSION SESSION <<<");
    ESP_LOGI(TAG, "Pending Event: Ref=%" PRIu32 ", Code=%u, Value=%" PRIu32,
             event_item.event_ref, event_item.event_code, event_item.event_value);
    ESP_LOGI(TAG, "==================================================");

    /* 1. Assemble and encrypt UP_EVENT (26 bytes) once for this session */
    uint32_t uplink_counter = ++(*inout_uplink_counter);
    lora_mac_v2_header_t hdr = {
        .ver_type = LORA_MAC_V2_TYPE_UP_EVENT,
        .node_id = cfg->node_id,
        .session_sel = cfg->session_sel,
        .frame_counter = uplink_counter,
    };
    uint8_t raw_hdr[7];
    size_t hdr_written = 0U;
    (void)lora_mac_v2_header_encode(&hdr, raw_hdr, sizeof(raw_hdr), &hdr_written);

    uint8_t nonce[13];
    (void)lora_mac_v2_build_nonce(cfg->session_nonce_prefix, LORA_MAC_V2_DIR_UPLINK, uplink_counter, nonce);

    lora_mac_v2_up_event_t up_evt = {
        .event_ref = event_item.event_ref,
        .event_time = event_item.event_time,
        .event_code = event_item.event_code,
        .event_value = (int16_t)event_item.event_value,
    };
    uint8_t pt[11];
    size_t pt_written = 0U;
    (void)lora_mac_v2_up_event_serialize(&up_evt, pt, sizeof(pt), &pt_written);

    uint8_t ct[11];
    uint8_t ccm_tag[8];
    esp_err_t enc_err = lora_mac_crypto_encrypt_up_event(cfg->k_session_up,
                                                         nonce,
                                                         raw_hdr, sizeof(raw_hdr),
                                                         pt, sizeof(pt),
                                                         ct, ccm_tag);
    lora_mac_crypto_zeroize(pt, sizeof(pt));
    if (enc_err != ESP_OK) {
        ESP_LOGE(TAG, "UP_EVENT encryption failed: %s", esp_err_to_name(enc_err));
        return enc_err;
    }

    uint8_t wire_tx[26];
    (void)memcpy(&wire_tx[0], raw_hdr, 7);
    (void)memcpy(&wire_tx[7], ct, 11);
    (void)memcpy(&wire_tx[18], ccm_tag, 8);

    /* 2. Intra-session Stop-and-Wait ARQ loop */
    uint8_t tx_retries = 0U;
    const uint8_t tx_max = NODE_ARQ_MAX_RETRIES;

    while (node_arq_should_retry(tx_retries, tx_max)) {
        ESP_LOGI(TAG, "--- ARQ Transmission Attempt #%u/%u (Event Ref=%" PRIu32 ") ---",
                 (unsigned int)(tx_retries + 1U), (unsigned int)tx_max, event_item.event_ref);

        /* 2a. CAD with exponential random backoff (ADR-0004: up to MAX_CAD_RETRIES=5) */
        bool channel_clear = false;
        for (uint8_t attempt = 1; attempt <= NODE_CAD_MAX_RETRIES; attempt++) {
            bool activity = false;
            esp_err_t cad_err = sx1276_cad(&activity, pdMS_TO_TICKS(50));
            if (cad_err == ESP_OK && !activity) {
                channel_clear = true;
                ESP_LOGI(TAG, "[CAD] Channel CLEAR on attempt #%u/%u (Freq=920.250 MHz CH0)",
                         attempt, NODE_CAD_MAX_RETRIES);
                break;
            }

            uint32_t cw_k = node_get_cad_contention_window_ms(attempt);
            (void)cw_k;
            uint32_t backoff_ms = node_calculate_cad_backoff_ms(attempt);
            ESP_LOGW(TAG, "[CAD] Channel BUSY on attempt #%u/%u (CW_k=%" PRIu32 " ms), backing off %" PRIu32 " ms...",
                     attempt, NODE_CAD_MAX_RETRIES, cw_k, backoff_ms);
            (void)node_smart_backoff(backoff_ms);
        }

        if (!channel_clear) {
            ESP_LOGE(TAG, "[CAD] Channel persistently busy after %u retries (activity detected); aborting TX session",
                     NODE_CAD_MAX_RETRIES);
            (void)node_event_fifo_record_retry(fifo, event_item.event_ref);
            ESP_LOGW(TAG, "Event Ref #%" PRIu32 " preserved in FIFO for retry", event_item.event_ref);
            (void)sx1276_sleep();
            return ESP_ERR_TIMEOUT;
        }

        /* 2b. Transmit UP_EVENT */
        ESP_LOGI(TAG, "[EVENT TX] Transmitting UP_EVENT (26B, Node #%u, Ctr=%" PRIu32 ", Attempt #%u/%u) on 920.250 MHz...",
                 hdr.node_id, uplink_counter, (unsigned int)(tx_retries + 1U), (unsigned int)tx_max);
        esp_err_t tx_err = sx1276_tx(wire_tx, sizeof(wire_tx), pdMS_TO_TICKS(600));
        if (tx_err != ESP_OK) {
            ESP_LOGE(TAG, "[EVENT TX] Transmission failed: %s", esp_err_to_name(tx_err));
            tx_retries++;
            if (node_arq_should_retry(tx_retries, tx_max)) {
                (void)node_reset_sx1276_fifo_tx_ptr();
                uint32_t retry_backoff = node_calculate_arq_backoff_ms();
                (void)node_smart_backoff(retry_backoff);
                continue;
            } else {
                break;
            }
        }
        ESP_LOGI(TAG, "[EVENT TX] Transmitted UP_EVENT successfully. Listening for DOWN_EVENT_ACK...");

        /* 2c. Open RX window to wait for DOWN_EVENT_ACK (timeout: 800 ms) */
        (void)node_radio_hal_rx_single(800);
        uint8_t ack_buf[64];
        size_t ack_len = 0U;
        esp_err_t ack_rx_err = node_radio_hal_read_frame(ack_buf, &ack_len, 800);
        (void)sx1276_standby();

        bool ack_valid = false;
        if (ack_rx_err == ESP_OK && ack_len >= LORA_MAC_V2_LEN_DOWN_EVENT_ACK) {
            lora_mac_v2_header_t ack_hdr;
            if (lora_mac_v2_header_parse(ack_buf, ack_len, &ack_hdr) == ESP_OK &&
                ack_hdr.node_id == cfg->node_id) {

                uint8_t dl_nonce[13];
                (void)lora_mac_v2_build_nonce(cfg->session_nonce_prefix,
                                              LORA_MAC_V2_DIR_DOWNLINK,
                                              ack_hdr.frame_counter,
                                              dl_nonce);

                if (ack_hdr.ver_type == LORA_MAC_V2_TYPE_DOWN_REVOKE) {
                    uint8_t dl_pt[4];
                    if (lora_mac_crypto_decrypt_down_revoke(cfg->k_session_down,
                                                            dl_nonce,
                                                            ack_buf, 7U,
                                                            &ack_buf[7], 4U,
                                                            &ack_buf[11],
                                                            dl_pt) == ESP_OK) {
                        lora_mac_crypto_zeroize(dl_pt, sizeof(dl_pt));
                        ESP_LOGI(TAG, "DOWN_REVOKE received during event ACK window");
                        return ESP_ERR_INVALID_STATE;
                    } else {
                        ESP_LOGW(TAG, "DOWN_REVOKE decryption/MIC check failed");
                    }
                } else if (ack_hdr.ver_type == LORA_MAC_V2_TYPE_DOWN_EVENT_ACK) {
                    uint8_t dl_pt[4];
                    if (lora_mac_crypto_decrypt_down_ack(cfg->k_session_down,
                                                         dl_nonce,
                                                         ack_buf, 7U,
                                                         &ack_buf[7], 4U,
                                                         &ack_buf[11],
                                                         dl_pt) == ESP_OK) {
                        lora_mac_v2_down_event_ack_t ack_payload;
                        if (lora_mac_v2_down_event_ack_deserialize(dl_pt, 4U, &ack_payload) == ESP_OK &&
                            ack_payload.event_ref == event_item.event_ref) {
                            ack_valid = true;
                            ESP_LOGI(TAG, "==================================================");
                            ESP_LOGI(TAG, ">>> DOWN_EVENT_ACK RECEIVED & VERIFIED! <<< (Ref: %" PRIu32 ")",
                                     ack_payload.event_ref);
                            ESP_LOGI(TAG, "==================================================");
                        } else {
                            ESP_LOGW(TAG, "ACK event_ref mismatch (received %" PRIu32 ", expected %" PRIu32 ")",
                                     ack_payload.event_ref, event_item.event_ref);
                        }
                        lora_mac_crypto_zeroize(dl_pt, sizeof(dl_pt));
                    } else {
                        ESP_LOGW(TAG, "DOWN_EVENT_ACK decryption/MIC check failed");
                    }
                } else {
                    ESP_LOGW(TAG, "Unexpected downlink message type: 0x%02X", ack_hdr.ver_type);
                }
            } else {
                ESP_LOGW(TAG, "Corrupted ACK header received");
            }
        } else {
            ESP_LOGW(TAG, "ACK timeout or missing (err: %s, len: %zu)", esp_err_to_name(ack_rx_err), ack_len);
        }

        /* 2d. Evaluate ACK */
        if (ack_valid) {
            esp_err_t fifo_ack_err = node_event_fifo_ack(fifo, event_item.event_ref);
            if (fifo_ack_err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to dequeue ACKed event Ref #%" PRIu32 " from FIFO: %s",
                         event_item.event_ref, esp_err_to_name(fifo_ack_err));
                *out_event_acked = false;
                return fifo_ack_err;
            }
            *out_event_acked = true;
            tx_retries = 0U;
            ESP_LOGI(TAG, "Event Ref #%" PRIu32 " ACKed and removed from FIFO. Remaining pending: %zu",
                     event_item.event_ref, node_event_fifo_get_pending_count(fifo));
            return ESP_OK;
        }

        /* 2e. Prepare for ARQ retransmission */
        tx_retries++;
        if (node_arq_should_retry(tx_retries, tx_max)) {
            ESP_LOGW(TAG, "[ARQ] Retrying transmission: tx_retries=%u < tx_max=%u. Resetting FIFO pointer & backing off...",
                     (unsigned int)tx_retries, (unsigned int)tx_max);
            (void)node_reset_sx1276_fifo_tx_ptr();
            uint32_t arq_backoff_ms = node_calculate_arq_backoff_ms();
            ESP_LOGI(TAG, "[ARQ] Smart backoff %" PRIu32 " ms before next CAD & TX attempt", arq_backoff_ms);
            (void)node_smart_backoff(arq_backoff_ms);
        } else {
            ESP_LOGE(TAG, "[ARQ] Reached tx_max (%u attempts) without receiving valid ACK", (unsigned int)tx_max);
            break;
        }
    }

    /* 3. Retries exhausted without valid ACK: record retry in FIFO and end session */
    (void)node_event_fifo_record_retry(fifo, event_item.event_ref);
    ESP_LOGW(TAG, "Event Ref #%" PRIu32 " preserved in FIFO for retry in next wake cycle", event_item.event_ref);
    return ESP_ERR_TIMEOUT;
}

esp_err_t node_send_heartbeat_ack(uint8_t node_id, uint16_t seq)
{
    uint8_t ack_pkt[8];
    ack_pkt[0] = LORA_MAC_V2_TYPE_UP_HEARTBEAT_ACK;
    ack_pkt[1] = node_id;
    ack_pkt[2] = (uint8_t)(seq & 0xFF);
    ack_pkt[3] = (uint8_t)((seq >> 8) & 0xFF);
    /* 4-byte response auth token matching Gateway probe expectations */
    ack_pkt[4] = 0x55;
    ack_pkt[5] = 0xAA;
    ack_pkt[6] = (uint8_t)(seq & 0xFF);
    ack_pkt[7] = (uint8_t)((seq >> 8) & 0xFF);

    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, ">>> LORA UP_HEARTBEAT_ACK TRANSMISSION <<<");
    ESP_LOGI(TAG, "Node ID: #%u | Seq: %u | Length: 8 Bytes | Freq: 920.250 MHz", node_id, seq);
    ESP_LOGI(TAG, "==================================================");

    return sx1276_tx(ack_pkt, sizeof(ack_pkt), pdMS_TO_TICKS(100));
}

esp_err_t node_listen_downlink_revoke(const node_mac_config_t *cfg, uint32_t wait_ms, bool *out_revoked)
{
    if (out_revoked != NULL) {
        *out_revoked = false;
    }
    if (cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    (void)node_radio_hal_rx_single(wait_ms);
    uint8_t dl_buf[64];
    size_t dl_len = 0U;
    esp_err_t dl_rx_err = node_radio_hal_read_frame(dl_buf, &dl_len, wait_ms);
    (void)sx1276_standby();

    if (dl_rx_err == ESP_OK && dl_len >= LORA_MAC_V2_LEN_DOWN_REVOKE) {
        lora_mac_v2_header_t dl_hdr;
        if (lora_mac_v2_header_parse(dl_buf, dl_len, &dl_hdr) == ESP_OK &&
            dl_hdr.ver_type == LORA_MAC_V2_TYPE_DOWN_REVOKE &&
            dl_hdr.node_id == cfg->node_id) {

            uint8_t dl_nonce[13];
            (void)lora_mac_v2_build_nonce(cfg->session_nonce_prefix,
                                          LORA_MAC_V2_DIR_DOWNLINK,
                                          dl_hdr.frame_counter,
                                          dl_nonce);
            uint8_t dl_pt[4];
            if (lora_mac_crypto_decrypt_down_revoke(cfg->k_session_down,
                                                    dl_nonce,
                                                    dl_buf, 7U,
                                                    &dl_buf[7], 4U,
                                                    &dl_buf[11],
                                                    dl_pt) == ESP_OK) {
                lora_mac_crypto_zeroize(dl_pt, sizeof(dl_pt));
                if (out_revoked != NULL) {
                    *out_revoked = true;
                }
                return ESP_OK;
            } else {
                ESP_LOGW(TAG, "DOWN_REVOKE decryption/MIC check failed");
            }
        }
    }
    return dl_rx_err;
}

esp_err_t node_listen_and_respond_probe(const node_mac_config_t *cfg, uint32_t wait_ms)
{
    if (cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    (void)node_radio_hal_rx_single(wait_ms);
    uint8_t rx_buf[64];
    size_t rx_len = 0U;
    esp_err_t err = node_radio_hal_read_frame(rx_buf, &rx_len, wait_ms);
    (void)sx1276_standby();

    if (err == ESP_OK && rx_len >= 7 && rx_buf[0] == LORA_MAC_V2_TYPE_DOWN_HEARTBEAT_PROBE) {
        uint16_t probe_seq = (uint16_t)rx_buf[1] | ((uint16_t)rx_buf[2] << 8);
        ESP_LOGI(TAG, "==================================================");
        ESP_LOGI(TAG, ">>> DOWN_HEARTBEAT_PROBE RECEIVED! <<< (Seq: %u)", probe_seq);
        ESP_LOGI(TAG, "==================================================");

        /* Slotted delay to prevent channel collision: Node_ID * 40ms */
        uint32_t slot_delay_ms = (uint32_t)cfg->node_id * 40U;
        ESP_LOGI(TAG, "[HEARTBEAT] Applying slotted backoff: %" PRIu32 " ms before ACK...", slot_delay_ms);
        if (slot_delay_ms > 0) {
            (void)node_smart_backoff(slot_delay_ms);
        }

        esp_err_t ack_err = node_send_heartbeat_ack(cfg->node_id, probe_seq);
        bool revoked = false;
        (void)node_listen_downlink_revoke(cfg, 400, &revoked);
        if (revoked) {
            return ESP_ERR_INVALID_STATE;
        }
        return ack_err;
    }
    return err;
}
