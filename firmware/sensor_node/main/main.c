#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"
#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "node_event_fifo.h"
#include "button_driver.h"
#include "airtime_policy.h"
#include "node_v2_join.h"
#include "oled_ssd1306.h"
#include "node_smart_backoff.h"
#include "node_cad_backoff.h"
#include "node_arq.h"
#include "sdkconfig.h"

static const char *TAG = "sensor_node";

static const uint8_t DEFAULT_NONCE_PREFIX[8] = {
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57
};

/* Persistent RTC memory variables preserved across Deep-Sleep */
RTC_DATA_ATTR static node_event_fifo_t s_event_fifo;
RTC_DATA_ATTR static uint32_t s_uplink_frame_counter = 0;
RTC_DATA_ATTR static node_v2_join_context_t s_join_ctx;
RTC_DATA_ATTR static uint32_t s_boot_count = 0;
RTC_DATA_ATTR static uint32_t s_button_events = 0;
RTC_DATA_ATTR static bool s_fifo_initialized = false;
RTC_DATA_ATTR static bool s_join_initialized = false;

/* Node MAC Configuration structure for Pure CAD CSMA/CA */
typedef struct {
    uint8_t node_id;
    uint8_t gw_id;
    uint8_t session_sel;
    uint8_t session_nonce_prefix[8];
    uint8_t k_session_up[16];
    uint8_t k_session_down[16];
} node_mac_config_t;

#ifndef CONFIG_NODE_STRICT_PROVISIONING
#define CONFIG_NODE_STRICT_PROVISIONING 1
#endif

static button_driver_t s_btn_driver;

static void node_update_oled_unjoined(void);
static void node_handle_revoke_and_sleep(button_driver_t *btn_driver);

/**
 * @brief Checks if buffer contains all zeros.
 */
static bool is_all_zeros(const uint8_t *buf, size_t len)
{
    if (buf == NULL || len == 0U) {
        return true;
    }
    for (size_t i = 0; i < len; i++) {
        if (buf[i] != 0U) {
            return false;
        }
    }
    return true;
}

/* Production SX1276 & FreeRTOS Radio HAL Callbacks */
static esp_err_t prod_radio_cad(bool *out_activity_detected)
{
    return sx1276_cad(out_activity_detected, pdMS_TO_TICKS(100));
}

static esp_err_t prod_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    return sx1276_tx(payload, length, pdMS_TO_TICKS(timeout_ms));
}

static esp_err_t prod_radio_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    /* Purge any stale frames from the RX queue before opening the reception window */
    sx1276_rx_frame_t stale;
    while (sx1276_read_frame(&stale, 0) == ESP_OK) {
        /* drain */
    }
    return sx1276_start_rx_continuous();
}

static esp_err_t prod_radio_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    if (out_buf == NULL || out_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sx1276_rx_frame_t frame;
    esp_err_t err = sx1276_read_frame(&frame, pdMS_TO_TICKS(wait_ms));
    if (err == ESP_OK) {
        *out_len = frame.length;
        (void)memcpy(out_buf, frame.payload, frame.length);
    }
    return err;
}

static esp_err_t prod_radio_sleep(void)
{
    return sx1276_sleep();
}

static esp_err_t prod_radio_standby(void)
{
    return sx1276_standby();
}

static uint32_t prod_get_time_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000ULL);
}

static void prod_delay_ms(uint32_t ms)
{
    (void)node_smart_backoff(ms);
}

static esp_err_t node_cad_event_tx_and_ack(const node_mac_config_t *cfg,
                                           node_event_fifo_t *fifo)
{
    if (cfg == NULL || fifo == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

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
    uint32_t uplink_counter = ++s_uplink_frame_counter;
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
        esp_err_t tx_err = sx1276_tx(wire_tx, sizeof(wire_tx), pdMS_TO_TICKS(150));
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

        /* 2c. Open RX window to wait for DOWN_EVENT_ACK (timeout: 400 ms) */
        (void)prod_radio_rx_single(400);
        uint8_t ack_buf[64];
        size_t ack_len = 0U;
        esp_err_t ack_rx_err = prod_radio_read_frame(ack_buf, &ack_len, 400);
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
                        node_handle_revoke_and_sleep(&s_btn_driver);
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
            (void)node_event_fifo_ack(fifo, event_item.event_ref);
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

static void node_update_oled_unjoined(void)
{
#if CONFIG_OLED_SSD1306_ENABLE
    oled_ssd1306_dev_t oled_dev;
    oled_ssd1306_config_t oled_cfg;
    if (oled_ssd1306_get_default_config(&oled_cfg) == ESP_OK) {
        oled_cfg.button_gpio = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO;
        if (oled_ssd1306_init(&oled_dev, &oled_cfg) == ESP_OK) {
            (void)oled_ssd1306_clear(&oled_dev);
            (void)oled_ssd1306_draw_string(&oled_dev, 8, 2, "STATUS: UNJOINED");
            (void)oled_ssd1306_draw_string(&oled_dev, 8, 4, "NODE REVOKED");
            (void)oled_ssd1306_refresh(&oled_dev);
            (void)oled_ssd1306_deinit(&oled_dev);
        }
    }
#endif
}

static void node_handle_revoke_and_sleep(button_driver_t *btn_driver)
{
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, ">>> DOWN_REVOKE RECEIVED & VERIFIED! <<<");
    ESP_LOGI(TAG, "Erasing session NVS, putting radio to SLEEP, entering indefinite Deep-Sleep.");
    ESP_LOGI(TAG, "==================================================");

    /* 1. Update OLED if configured */
    node_update_oled_unjoined();

    /* 2. Erase session from NVS and transition state */
    (void)node_v2_join_erase_session(&s_join_ctx);
    s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;

    /* 3. Put radio completely to sleep */
    (void)sx1276_sleep();

    /* 4. Disable timer wakeup explicitly to prevent periodic wakes */
    (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);

    /* 5. Arm EXT0 wakeup on button GPIO only */
    if (btn_driver != NULL && btn_driver->is_initialized) {
        (void)button_driver_arm_sleep(btn_driver);
    }

    ESP_LOGI(TAG, "Revoked: Entering Deep-Sleep mode. Press button on GPIO %d to request new join...",
             CONFIG_NODE_BUTTON_GPIO);
    esp_deep_sleep_start();
    vTaskSuspend(NULL);
}

static void node_listen_downlink_revoke(const node_mac_config_t *cfg, uint32_t wait_ms)
{
    if (cfg == NULL) {
        return;
    }
    (void)prod_radio_rx_single(wait_ms);
    uint8_t dl_buf[64];
    size_t dl_len = 0U;
    esp_err_t dl_rx_err = prod_radio_read_frame(dl_buf, &dl_len, wait_ms);
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
                node_handle_revoke_and_sleep(&s_btn_driver);
            } else {
                ESP_LOGW(TAG, "DOWN_REVOKE decryption/MIC check failed");
            }
        }
    }
}

static esp_err_t node_send_heartbeat_ack(uint8_t node_id, uint16_t seq)
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

static esp_err_t node_listen_and_respond_probe(const node_mac_config_t *cfg, uint32_t wait_ms)
{
    if (cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    (void)prod_radio_rx_single(wait_ms);
    uint8_t rx_buf[64];
    size_t rx_len = 0U;
    esp_err_t err = prod_radio_read_frame(rx_buf, &rx_len, wait_ms);
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
        node_listen_downlink_revoke(cfg, 400);
        return ack_err;
    }
    return err;
}

void app_main(void)
{
    s_boot_count++;
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "Starting Sensor Node Boot #%" PRIu32 " (ESP-IDF v6.1 / HW-001 Pure CAD CSMA)", s_boot_count);

    bool radio_initialized = false;

    /* 1. Initialize NVS flash for monotonic join counter and credentials storage */
    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        (void)nvs_flash_erase();
        nvs_ret = nvs_flash_init();
    }
    if (nvs_ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS flash initialization failed: %s", esp_err_to_name(nvs_ret));
    }

    /* 2. Initialize persistent FIFO on first boot / cold start */
    if (!s_fifo_initialized) {
        esp_err_t fifo_err = node_event_fifo_init(&s_event_fifo, 0, 1);
        if (fifo_err == ESP_OK) {
            s_fifo_initialized = true;
            ESP_LOGI(TAG, "Persistent Node Event FIFO initialized (capacity: %u items)", NODE_EVENT_FIFO_CAPACITY);
        } else {
            ESP_LOGE(TAG, "Failed to initialize Node Event FIFO: %s", esp_err_to_name(fifo_err));
        }
    }

    /* 3. Configure Node MAC parameters from Kconfig / defaults */
    node_mac_config_t mac_cfg;
    (void)memset(&mac_cfg, 0, sizeof(mac_cfg));
#ifdef CONFIG_NODE_DEFAULT_NODE_ID
    mac_cfg.node_id = (uint8_t)CONFIG_NODE_DEFAULT_NODE_ID;
#else
    mac_cfg.node_id = 1;
#endif
#ifdef CONFIG_NODE_TARGET_GATEWAY_ID
    mac_cfg.gw_id = (uint8_t)CONFIG_NODE_TARGET_GATEWAY_ID;
#else
    mac_cfg.gw_id = 1;
#endif
    (void)memcpy(mac_cfg.session_nonce_prefix, DEFAULT_NONCE_PREFIX, 8);

    /* 4. Configure Node V2 Join subsystem */
    if (!s_join_initialized) {
        (void)node_v2_join_init(&s_join_ctx);
        s_join_initialized = true;
        ESP_LOGI(TAG, "Sensor Node V2 Join subsystem initialized (State: %s)",
                 node_v2_join_state_to_str(s_join_ctx.state));
    } else if (s_join_ctx.state == NODE_V2_JOIN_STATE_ABORTED && !s_join_ctx.radio_permanently_locked) {
        /* Allow retry on new boot / wake event */
        s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
        ESP_LOGI(TAG, "Join state reset from ABORTED to UNJOINED for retry");
    }

    /* Attempt to recover persistent session from NVS Flash across cold boots (Issue #322, #323) */
    if (s_join_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE && !s_join_ctx.radio_permanently_locked) {
        esp_err_t load_err = node_v2_join_load_session(&s_join_ctx);
        if (load_err == ESP_OK) {
            ESP_LOGI(TAG, "==================================================");
            ESP_LOGI(TAG, ">>> RESTORED PERSISTENT V2 JOIN SESSION FROM NVS <<<");
            ESP_LOGI(TAG, "Assigned Node ID: #%u | State: %s",
                     s_join_ctx.assigned_node_id, node_v2_join_state_to_str(s_join_ctx.state));
            ESP_LOGI(TAG, "==================================================");
            mac_cfg.node_id = s_join_ctx.assigned_node_id;
            (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
            (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
        } else {
            ESP_LOGI(TAG, "No valid persistent session in NVS Flash (%s). Node remains UNJOINED.",
                     esp_err_to_name(load_err));
        }
    } else if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        /* Session preserved in RTC RAM across deep-sleep wake */
        mac_cfg.node_id = s_join_ctx.assigned_node_id;
        (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
        (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
    }

    node_v2_join_config_t join_cfg;
    (void)node_v2_join_get_default_config(&join_cfg);
#ifdef CONFIG_NODE_JOIN_GRANT_TIMEOUT_MS
    join_cfg.grant_listen_timeout_ms = (uint32_t)CONFIG_NODE_JOIN_GRANT_TIMEOUT_MS;
#endif

    /* Read provisioned device MAC and credentials from nvs_sec if present */
    bool k_join_loaded = false;
    nvs_handle_t sec_handle;
    esp_err_t sec_err = nvs_open("nvs_sec", NVS_READONLY, &sec_handle);
    if (sec_err == ESP_OK) {
        size_t mac_len = sizeof(join_cfg.device_mac);
        esp_err_t mac_err = nvs_get_blob(sec_handle, "device_mac", join_cfg.device_mac, &mac_len);
        if (mac_err == ESP_OK && mac_len == sizeof(join_cfg.device_mac) &&
            !is_all_zeros(join_cfg.device_mac, sizeof(join_cfg.device_mac))) {
            ESP_LOGI(TAG, "Loaded provisioned device MAC: %02x%02x%02x%02x%02x%02x",
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        } else {
            (void)esp_read_mac(join_cfg.device_mac, ESP_MAC_WIFI_STA);
            ESP_LOGI(TAG, "Using factory Wi-Fi MAC: %02x%02x%02x%02x%02x%02x",
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        }

        size_t k_len = sizeof(join_cfg.k_join);
        esp_err_t k_err = nvs_get_blob(sec_handle, "k_join", join_cfg.k_join, &k_len);
        if (k_err == ESP_OK && k_len == sizeof(join_cfg.k_join)) {
            if (!is_all_zeros(join_cfg.k_join, sizeof(join_cfg.k_join))) {
                k_join_loaded = true;
                ESP_LOGI(TAG, "Loaded provisioned K_JOIN from nvs_sec");
            } else {
                ESP_LOGE(TAG, "Provisioned K_JOIN in nvs_sec is invalid (all zeros)");
            }
        } else {
            ESP_LOGW(TAG, "K_JOIN not found in nvs_sec: %s", esp_err_to_name(k_err));
        }

        uint32_t net_id = 0;
        if (nvs_get_u32(sec_handle, "network_id", &net_id) == ESP_OK) {
            join_cfg.network_id = net_id;
        }
        nvs_close(sec_handle);
    } else {
        (void)esp_read_mac(join_cfg.device_mac, ESP_MAC_WIFI_STA);
        ESP_LOGI(TAG, "Using factory Wi-Fi MAC: %02x%02x%02x%02x%02x%02x",
                 join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                 join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        ESP_LOGW(TAG, "Namespace nvs_sec not found: %s", esp_err_to_name(sec_err));
    }

    /* Bind established session keys if already joined */
    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        mac_cfg.node_id = s_join_ctx.assigned_node_id;
        (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
        (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
    }

    node_v2_join_radio_hal_t join_hal = {
        .radio_cad = prod_radio_cad,
        .radio_tx = prod_radio_tx,
        .radio_rx_single = prod_radio_rx_single,
        .radio_read_frame = prod_radio_read_frame,
        .radio_sleep = prod_radio_sleep,
        .radio_standby = prod_radio_standby,
        .get_time_ms = prod_get_time_ms,
        .delay_ms = prod_delay_ms,
    };

    /* 5. Initialize Airtime Policy & Crypto subsystem */
#ifdef CONFIG_NODE_AIRTIME_PERMILLE
    (void)airtime_policy_init((uint16_t)CONFIG_NODE_AIRTIME_PERMILLE);
#else
    (void)airtime_policy_init(10U); /* 1.0% regulatory duty cycle */
#endif
    (void)lora_mac_crypto_init();

    /* 6. Initialize button driver from Kconfig settings */
    button_config_t btn_cfg = {
        .gpio_num = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO,
        .active_level = CONFIG_NODE_BUTTON_ACTIVE_LEVEL,
        .debounce_ms = CONFIG_NODE_BUTTON_DEBOUNCE_MS,
        .hold_time_ms = CONFIG_NODE_BUTTON_HOLD_TIME_MS,
    };

    esp_err_t btn_err = button_driver_init(&s_btn_driver, &btn_cfg);
    if (btn_err != ESP_OK) {
        ESP_LOGE(TAG, "Button driver initialization failed: %s", esp_err_to_name(btn_err));
    }

    /* 7. Identify wake-up cause */
    button_wakeup_cause_t wake_cause = button_driver_get_wakeup_cause();

    /* =========================================================================
     * UNJOINED FLOW (Issue #340)
     * When unjoined, the node MUST NOT automatically transmit RF on cold boot / reset.
     * It immediately enters Deep Sleep and only initiates Join upon GPIO button press.
     * ========================================================================= */
    if (s_join_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        if (wake_cause != BUTTON_CAUSE_EXT0_BUTTON) {
            ESP_LOGI(TAG, "[UNJOINED BOOT] Cold boot or non-button wake detected (cause=%d) while UNJOINED.", (int)wake_cause);
            ESP_LOGI(TAG, "[UNJOINED BOOT] Putting radio to SLEEP, arming button GPIO %d, entering Deep-Sleep immediately.",
                     CONFIG_NODE_BUTTON_GPIO);

            if (sx1276_init(NULL, NULL) == ESP_OK) {
                (void)sx1276_sleep();
            }
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            node_update_oled_unjoined();
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }

        /* Wake cause is EXT0 physical button press while UNJOINED */
        ESP_LOGI(TAG, "[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO %d while UNJOINED", CONFIG_NODE_BUTTON_GPIO);
        bool button_qualified = false;
        esp_err_t q_err = button_driver_qualify_press(&s_btn_driver, &button_qualified);
        if (q_err != ESP_OK || !button_qualified) {
            ESP_LOGW(TAG, "Transient wake without qualified button press (bounce/noise filtered). Returning to Deep-Sleep.");
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }

        /* Strict Fail-Closed Provisioning Verification (DEC-SEC-01, DEC-SEC-06, Issue #324) */
#if CONFIG_NODE_STRICT_PROVISIONING
        if (!k_join_loaded) {
            ESP_LOGE(TAG, "[PROVISION ERROR] Missing provisioned K_JOIN in nvs_sec. Halting radio.");
            s_join_ctx.state = NODE_V2_JOIN_STATE_ABORTED;
            lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
            if (sx1276_init(NULL, NULL) == ESP_OK) {
                (void)sx1276_sleep();
            }
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }
#else
        if (!k_join_loaded) {
            ESP_LOGW(TAG, "[PROVISION WARN] Missing provisioned K_JOIN in nvs_sec, but strict provisioning is disabled (lab test mode).");
        }
#endif

        /* Initialize SX1276 radio for OTA V2 Join Handshake */
        if (!radio_initialized) {
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err == ESP_OK) {
                radio_initialized = true;
            } else {
                ESP_LOGE(TAG, "SX1276 initialization failed for join: %s", esp_err_to_name(sx_err));
            }
        }

        if (radio_initialized) {
            ESP_LOGI(TAG, "==================================================");
            ESP_LOGI(TAG, "[JOIN TRIGGER] Physical button press qualified on GPIO %d. Starting OTA V2 Join!", CONFIG_NODE_BUTTON_GPIO);
            ESP_LOGI(TAG, "[RF PHY CONFIG] Freq: 920.250 MHz | Channel: 0 (VN920) | SF: 7 | BW: 125 kHz | CR: 4/5 | Preamble: 8 | SyncWord: 0x12 | PA: PA_BOOST (+14 dBm)");
            ESP_LOGI(TAG, "[RF IDENTITY] Node MAC: %02X:%02X:%02X:%02X:%02X:%02X | Target GW: %u | Network ID: %" PRIu32,
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5],
                     join_cfg.target_gw_id, join_cfg.network_id);
            ESP_LOGI(TAG, "==================================================");

            esp_err_t join_err = node_v2_join_run(&join_cfg, &join_hal, &s_join_ctx);
            if (join_err == ESP_OK && s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
                ESP_LOGI(TAG, "==================================================");
                ESP_LOGI(TAG, ">>> V2 JOIN HANDSHAKE SUCCESSFUL! <<<");
                ESP_LOGI(TAG, "Assigned Node ID: #%u | State: %s",
                         s_join_ctx.assigned_node_id, node_v2_join_state_to_str(s_join_ctx.state));
                ESP_LOGI(TAG, "==================================================");
                mac_cfg.node_id = s_join_ctx.assigned_node_id;
                (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
                (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);

                /* Verify NVS persistence integrity */
                node_v2_join_context_t verify_ctx;
                (void)node_v2_join_init(&verify_ctx);
                if (node_v2_join_load_session(&verify_ctx) == ESP_OK) {
                    ESP_LOGI(TAG, "NVS session persistence verified: Node ID #%u, joined=1, keys 16B",
                             verify_ctx.assigned_node_id);
                } else {
                    ESP_LOGW(TAG, "NVS session verification failed after join commit");
                }
                lora_mac_crypto_zeroize(&verify_ctx.session_keys, sizeof(verify_ctx.session_keys));

                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)sx1276_sleep();
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
                (void)esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
#endif
                ESP_LOGI(TAG, "Node is JOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            } else if (node_v2_join_is_rejected(&s_join_ctx)) {
                ESP_LOGW(TAG, "==================================================");
                ESP_LOGW(TAG, ">>> V2 JOIN REJECTED BY GATEWAY/BACKEND! <<<");
                ESP_LOGW(TAG, "Putting radio to SLEEP, arming button GPIO %d, entering Deep-Sleep.", CONFIG_NODE_BUTTON_GPIO);
                ESP_LOGW(TAG, "==================================================");
                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)node_v2_join_erase_session(&s_join_ctx);
                s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
                (void)sx1276_sleep();
                (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
                node_update_oled_unjoined();
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            } else {
                ESP_LOGW(TAG, "[JOIN ATTEMPT FAILED] %s (State: %s). Entering Deep-Sleep ready for next button press.",
                         esp_err_to_name(join_err), node_v2_join_state_to_str(s_join_ctx.state));
                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)node_v2_join_erase_session(&s_join_ctx);
                s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
                (void)sx1276_sleep();
                (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
                node_update_oled_unjoined();
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            }
        }
    }

    /* =========================================================================
     * JOINED FLOW (Node has active session in INSTALLED_INACTIVE)
     * ========================================================================= */
    switch (wake_cause) {
        case BUTTON_CAUSE_EXT0_BUTTON: {
            ESP_LOGI(TAG, "[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO %d (JOINED Node)", CONFIG_NODE_BUTTON_GPIO);
            bool qualified = false;
            esp_err_t q_err = button_driver_qualify_press(&s_btn_driver, &qualified);
            if (q_err == ESP_OK && qualified) {
                s_button_events++;
                uint32_t event_ref = 0;
                uint32_t now_sec = (uint32_t)(esp_timer_get_time() / 1000000ULL);
                int16_t rand_val = (int16_t)(80 + (esp_random() % 21));

                /* Event Code 0x01 = Manual Button Trigger, Value = rand_val (80..100) */
                esp_err_t push_err = node_event_fifo_push(&s_event_fifo, now_sec, 0x01, rand_val, &event_ref);
                if (push_err == ESP_OK) {
                    ESP_LOGI(TAG, ">>> EVENT ENQUEUED <<< Ref: %" PRIu32 ", Value: %d, Total button events: %" PRIu32,
                             event_ref, (int)rand_val, s_button_events);
                } else {
                    ESP_LOGW(TAG, "Failed to enqueue event: %s (FIFO dropped count: %" PRIu32 ")",
                             esp_err_to_name(push_err), node_event_fifo_get_dropped_count(&s_event_fifo));
                }

                /* Local OLED display update for confirmed button event */
#if CONFIG_OLED_SSD1306_ENABLE
                oled_ssd1306_dev_t oled_dev;
                oled_ssd1306_config_t oled_cfg;
                (void)oled_ssd1306_get_default_config(&oled_cfg);
                oled_cfg.button_gpio = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO;
                esp_err_t oled_err = oled_ssd1306_init(&oled_dev, &oled_cfg);
                if (oled_err == ESP_OK) {
                    oled_err = oled_ssd1306_display_event(&oled_dev, rand_val, now_sec, s_button_events);
                    if (oled_err != ESP_OK) {
                        ESP_LOGW(TAG, "OLED display event failed: %s", esp_err_to_name(oled_err));
                    }
                    (void)oled_ssd1306_deinit(&oled_dev);
                } else {
                    ESP_LOGW(TAG, "OLED init failed: %s (non-fatal, continuing event flow)", esp_err_to_name(oled_err));
                }
#endif
            } else {
                ESP_LOGW(TAG, "Transient wake without qualified button press (bounce/noise filtered)");
            }
            break;
        }
        case BUTTON_CAUSE_TIMER:
            ESP_LOGI(TAG, "[WAKE CAUSE] Periodic Timer Wakeup (5-10 min Node Liveness Heartbeat)");
            if (!radio_initialized) {
                esp_err_t sx_err = sx1276_init(NULL, NULL);
                if (sx_err == ESP_OK) {
                    radio_initialized = true;
                } else {
                    ESP_LOGW(TAG, "SX1276 init for timer wakeup failed: %s", esp_err_to_name(sx_err));
                }
            }
            if (radio_initialized) {
                uint32_t slot_delay_ms = (uint32_t)mac_cfg.node_id * 40U;
                if (slot_delay_ms > 0) {
                    (void)node_smart_backoff(slot_delay_ms);
                }
                uint16_t hb_seq = (uint16_t)(esp_timer_get_time() / 1000000ULL);
                (void)node_send_heartbeat_ack(mac_cfg.node_id, hb_seq);
                node_listen_downlink_revoke(&mac_cfg, 400);
            }
            break;
        default:
            ESP_LOGI(TAG, "[WAKE CAUSE] Power-On Reset or Software Restart with active session");
            if (!radio_initialized) {
                esp_err_t sx_err = sx1276_init(NULL, NULL);
                if (sx_err == ESP_OK) {
                    radio_initialized = true;
                    (void)sx1276_sleep();
                    ESP_LOGI(TAG, "[COLD BOOT] Radio placed in SLEEP mode (Session restored from NVS)");
                } else {
                    ESP_LOGW(TAG, "SX1276 init returned: %s (safe sleep default)", esp_err_to_name(sx_err));
                }
            }
            break;
    }

    size_t pending_events = node_event_fifo_get_pending_count(&s_event_fifo);
    ESP_LOGI(TAG, "FIFO State: Pending Events = %zu, Dropped Events = %" PRIu32,
             pending_events, node_event_fifo_get_dropped_count(&s_event_fifo));

    /* 9. Execute CAD + Random Backoff Event Transmission if joined and pending events exist */
    if (pending_events > 0U) {
        if (!radio_initialized) {
            ESP_LOGI(TAG, "Initializing SX1276 radio for Event transmission");
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err != ESP_OK) {
                ESP_LOGE(TAG, "SX1276 initialization failed: %s", esp_err_to_name(sx_err));
            } else {
                radio_initialized = true;
            }
        }

        if (radio_initialized) {
            esp_err_t cycle_err = node_cad_event_tx_and_ack(&mac_cfg, &s_event_fifo);
            ESP_LOGI(TAG, "CAD Event cycle finished (status: %s, remaining pending: %zu)",
                     esp_err_to_name(cycle_err),
                     node_event_fifo_get_pending_count(&s_event_fifo));
        }
    }

    /* 9b. Briefly listen for Gateway DOWN_HEARTBEAT_PROBE (150ms window) on active wakeups */
    if (wake_cause != BUTTON_CAUSE_RESET_OR_OTHER && radio_initialized && pending_events == 0U) {
        (void)node_listen_and_respond_probe(&mac_cfg, 150);
    }

    /* Zeroize sensitive join key before entering sleep/suspend */
    lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));

    /* 10. Ensure radio is sleeping before entering Deep-Sleep */
    if (radio_initialized) {
        (void)sx1276_sleep();
    }

    /* 11. Enter Deep-Sleep */
    if (s_btn_driver.is_initialized) {
        (void)button_driver_arm_sleep(&s_btn_driver);
    }

#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        ESP_LOGI(TAG, "Enabling Timer Wakeup in %d seconds", CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC);
        (void)esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
    } else {
        (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
    }
#endif

    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        ESP_LOGI(TAG, "Node is JOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    } else {
        ESP_LOGI(TAG, "Node is UNJOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    }
    ESP_LOGI(TAG, "==================================================");

    esp_deep_sleep_start();
}
