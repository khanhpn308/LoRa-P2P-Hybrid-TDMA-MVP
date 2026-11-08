#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "lora_mac.h"
#include "sx1276_driver.h"
#include "session_key_store.h"
#include "gateway_transport.h"
#include "gateway_v2_join.h"
#include "sdkconfig.h"
#include "airtime_policy.h"
#include "gateway_tdma_master.h"

static const char *TAG = "gateway_master";
static gateway_v2_join_engine_t s_join_engine;

static void on_downlink_session_key(const uint8_t *data, size_t len)
{
    ESP_LOGI(TAG, "Downlink session-key-install received (%zu bytes)", len);
}

static void on_downlink_schedule(const uint8_t *data, size_t len)
{
    ESP_LOGI(TAG, "Downlink schedule received (%zu bytes)", len);
}

static gateway_tdma_engine_t s_tdma_engine;
static TaskHandle_t s_tdma_task_handle = NULL;
static esp_timer_handle_t s_epoch_timer = NULL;

#define GATEWAY_TASK_STACK_SIZE_BYTES (12288U)
static StackType_t s_gateway_task_stack[GATEWAY_TASK_STACK_SIZE_BYTES];
static StaticTask_t s_gateway_task_tcb;

/* Hardware and Radio HAL Callbacks */

static esp_err_t hal_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    TickType_t ticks = pdMS_TO_TICKS(timeout_ms);
    return sx1276_tx(payload, length, ticks);
}

static esp_err_t hal_radio_rx_start(void)
{
    return sx1276_start_rx_continuous();
}

static esp_err_t hal_radio_rx_stop(void)
{
    return sx1276_stop_rx();
}

static esp_err_t hal_radio_read_frame(uint8_t *out_buf, size_t *out_len, int16_t *out_rssi, int8_t *out_snr, uint32_t timeout_ms)
{
    sx1276_rx_frame_t frame;
    TickType_t ticks = pdMS_TO_TICKS(timeout_ms);
    esp_err_t err = sx1276_read_frame(&frame, ticks);
    if (err == ESP_OK) {
        if (out_buf != NULL && frame.length <= 128U) {
            (void)memcpy(out_buf, frame.payload, frame.length);
        }
        if (out_len != NULL) {
            *out_len = frame.length;
        }
        if (out_rssi != NULL) {
            *out_rssi = frame.rssi_dbm;
        }
        if (out_snr != NULL) {
            *out_snr = frame.snr_db_quarter;
        }
        return ESP_OK;
    }
    return err;
}

static esp_err_t hal_radio_standby(void)
{
    return sx1276_standby();
}

static esp_err_t hal_radio_sleep(void)
{
    return sx1276_sleep();
}

static uint32_t hal_get_time_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000ULL);
}

static void hal_delay_ms(uint32_t ms)
{
    if (ms > 0U) {
        vTaskDelay(pdMS_TO_TICKS(ms));
    }
}

static esp_err_t hal_session_key_lookup(uint8_t node_id,
                                        uint8_t *out_session_sel,
                                        uint8_t out_k_session_up[16],
                                        uint8_t out_k_session_dl[16],
                                        uint8_t out_nonce_prefix[8])
{
    sk_session_record_t rec;
    esp_err_t err = session_key_store_get_active(node_id, &rec);
    if (err != ESP_OK) {
        return err;
    }
    if (out_session_sel != NULL) {
        *out_session_sel = rec.key_id & 1U;
    }
    if (out_k_session_up != NULL) {
        (void)memcpy(out_k_session_up, rec.k_session_up, 16);
    }
    if (out_k_session_dl != NULL) {
        (void)memcpy(out_k_session_dl, rec.k_session_dl, 16);
    }
    if (out_nonce_prefix != NULL) {
        (void)memcpy(out_nonce_prefix, rec.session_id, 8);
    }
    return ESP_OK;
}

static void gateway_epoch_timer_cb(void *arg)
{
    (void)arg;
    if (s_tdma_task_handle != NULL) {
        /* Non-blocking notification to worker task per RTOS-001 / RTOS-005 */
        vTaskNotifyGiveFromISR(s_tdma_task_handle, NULL);
    }
}

static esp_err_t process_join_packet(const uint8_t *payload, size_t length, int16_t rssi, int8_t snr)
{
    if (payload == NULL || length == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t msg_type = payload[0];
    uint64_t now_us = (uint64_t)esp_timer_get_time();
    float snr_f = (float)snr / 4.0f;

    switch (msg_type) {
        case LORA_MAC_V2_TYPE_UP_JOIN_HELLO: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_HELLO (68B): MAC=%02X:%02X:%02X:%02X:%02X:%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[1], payload[2], payload[3], payload[4], payload[5], payload[6],
                         rssi, (double)snr_f);
                uint8_t grant_buf[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
                size_t grant_len = 0;
                esp_err_t h_err = gateway_v2_join_handle_hello(
                    &s_join_engine,
                    payload,
                    length,
                    rssi,
                    snr_f,
                    now_us,
                    NULL, /* edge grant (no backend proof in MVP) */
                    grant_buf,
                    &grant_len
                );
                if (h_err == ESP_OK) {
                    /* Allow Node time to switch from TX to RXSINGLE (RF turnaround margin) */
                    vTaskDelay(pdMS_TO_TICKS(40));
                    ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_GRANT (%zu bytes) to Node on 920.250 MHz (CH0)...", grant_len);
                    esp_err_t tx_err = sx1276_tx(grant_buf, (uint8_t)grant_len, pdMS_TO_TICKS(300));
                    if (tx_err == ESP_OK) {
                        ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_GRANT transmitted successfully");
                    } else {
                        ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_GRANT: %s", esp_err_to_name(tx_err));
                    }
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_HELLO: %s", esp_err_to_name(h_err));
                }
                return h_err;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_KEY_CONFIRM (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                uint8_t finish_buf[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
                size_t finish_len = 0;
                esp_err_t c_err = gateway_v2_join_handle_confirm(
                    &s_join_engine,
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
            if (length == LORA_MAC_V2_LEN_UP_JOIN_READY) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_READY (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                esp_err_t r_err = gateway_v2_join_handle_ready(
                    &s_join_engine,
                    payload,
                    length
                );
                if (r_err == ESP_OK) {
                    ESP_LOGI(TAG, "[JOIN SUCCESS] Node #%u Join complete! Session committed in INSTALLED_INACTIVE state.", payload[2]);
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_READY: %s", esp_err_to_name(r_err));
                }
                return r_err;
            }
            break;
        }

        default:
            ESP_LOGD(TAG, "[RF RX] Non-join frame: type=0x%02X, len=%zu", msg_type, length);
            break;
    }
    return ESP_OK;
}

static void gateway_tdma_master_task(void *pvParameters)
{
    (void)pvParameters;
    ESP_LOGI(TAG, "Gateway TDMA Master Task running (Continuous RX active on 920.250 MHz CH0)");

    /* Start in continuous RX to listen for OTA join handshakes */
    (void)sx1276_start_rx_continuous();

    while (1) {
        /* Check if epoch timer triggered a superframe */
        uint32_t notified = ulTaskNotifyTake(pdTRUE, 0);
        if (notified > 0) {
            /* Superframe epoch reached: Stop continuous RX and run TDMA superframe */
            (void)sx1276_stop_rx();

            ESP_LOGI(TAG, "Starting Superframe sequence #%" PRIu32 " (Broadcasting DOWN_SYNC_BEACON on 920.250 MHz CH0)",
                     s_tdma_engine.superframe_seq);
            esp_err_t err = gateway_tdma_run_superframe(&s_tdma_engine);
            if (err != ESP_OK) {
                ESP_LOGW(TAG, "Superframe cycle returned warning: %s", esp_err_to_name(err));
            }

            /* Superframe completed: return to continuous RX for OTA Join */
            (void)sx1276_start_rx_continuous();
            continue;
        }

        /* Check for incoming LoRa packet with 20ms wait */
        sx1276_rx_frame_t rx_frame;
        esp_err_t rx_err = sx1276_read_frame(&rx_frame, pdMS_TO_TICKS(20));
        if (rx_err == ESP_OK && rx_frame.length > 0) {
            ESP_LOGI(TAG, "[RF RX IDLE] Frame received: len=%u B, Type=0x%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                     rx_frame.length, rx_frame.payload[0], rx_frame.rssi_dbm, (float)rx_frame.snr_db_quarter / 4.0f);
            (void)process_join_packet(rx_frame.payload, rx_frame.length, rx_frame.rssi_dbm, rx_frame.snr_db_quarter);
            (void)sx1276_start_rx_continuous();
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "Starting Gateway Master (ESP-IDF v6.1 / SX1276 MVP)");

    // Initialize NVS flash for durable session key storage
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Initialize Session Key Store & restore durable slots from NVS
    ret = session_key_store_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize session key store: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Session key store initialized successfully");
    }

    // Initialize Gateway Transport (WiFi Station & MQTT 5.0 mTLS)
    gateway_transport_config_t transport_cfg = {
#ifdef CONFIG_GATEWAY_ID
        .gateway_id = CONFIG_GATEWAY_ID,
#else
        .gateway_id = "gw-a",
#endif
#ifdef CONFIG_GATEWAY_WIFI_SSID
        .wifi_ssid = CONFIG_GATEWAY_WIFI_SSID,
#else
        .wifi_ssid = "myssid",
#endif
#ifdef CONFIG_GATEWAY_WIFI_PASSWORD
        .wifi_password = CONFIG_GATEWAY_WIFI_PASSWORD,
#else
        .wifi_password = "mypassword",
#endif
#ifdef CONFIG_GATEWAY_WIFI_MAX_RETRY
        .wifi_max_retry = CONFIG_GATEWAY_WIFI_MAX_RETRY,
#else
        .wifi_max_retry = 5,
#endif
#ifdef CONFIG_GATEWAY_BROKER_URI
        .broker_uri = CONFIG_GATEWAY_BROKER_URI,
#else
        .broker_uri = "",
#endif
        .disable_auto_connect = false,
    };

    ret = gateway_transport_init(&transport_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway transport: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway transport initialized successfully");
        gateway_transport_register_session_key_callback(&on_downlink_session_key);
        gateway_transport_register_schedule_callback(&on_downlink_schedule);
    }

    // Initialize Gateway V2 Join Relay Engine
    gateway_v2_join_config_t join_cfg = {
#ifdef CONFIG_GATEWAY_TARGET_GW_ID
        .target_gw_id = (uint8_t)CONFIG_GATEWAY_TARGET_GW_ID,
#else
        .target_gw_id = 1,
#endif
        .network_id = 100,
    };
    snprintf(join_cfg.gateway_id, sizeof(join_cfg.gateway_id), "%s", transport_cfg.gateway_id);
    snprintf(join_cfg.gateway_epoch, sizeof(join_cfg.gateway_epoch), "%s", GATEWAY_V2_JOIN_DEFAULT_EPOCH);
    ret = gateway_v2_join_init(&s_join_engine, &join_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize Gateway V2 Join Engine: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway V2 Join Engine initialized successfully");
    }

    // Initialize Gateway SX1276 radio transceiver
    ret = sx1276_init(NULL, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SX1276 driver: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "SX1276 radio initialized in STANDBY mode");
    }

    // Configure Gateway TDMA Master Engine
    gateway_tdma_config_t cfg;
    ESP_ERROR_CHECK(gateway_tdma_get_default_config(&cfg));
#ifdef CONFIG_GATEWAY_TARGET_GW_ID
    cfg.gw_id = (uint8_t)CONFIG_GATEWAY_TARGET_GW_ID;
#endif
    cfg.key_lookup_fn = hal_session_key_lookup;
    cfg.join_frame_fn = process_join_packet;

    gateway_tdma_radio_hal_t hal = {
        .radio_tx = hal_radio_tx,
        .radio_rx_start = hal_radio_rx_start,
        .radio_rx_stop = hal_radio_rx_stop,
        .radio_read_frame = hal_radio_read_frame,
        .radio_standby = hal_radio_standby,
        .radio_sleep = hal_radio_sleep,
        .get_time_ms = hal_get_time_ms,
        .delay_ms = hal_delay_ms,
    };

    ESP_ERROR_CHECK(gateway_tdma_init(&s_tdma_engine, &cfg, &hal));
    ESP_LOGI(TAG, "Gateway TDMA Master Engine initialized");

    // Create static FreeRTOS task per RTOS-005
    s_tdma_task_handle = xTaskCreateStatic(
        gateway_tdma_master_task,
        "gw_tdma_master",
        GATEWAY_TASK_STACK_SIZE_BYTES,
        NULL,
        5, /* Priority */
        s_gateway_task_stack,
        &s_gateway_task_tcb
    );

    // Initialize high-resolution hardware periodic timer (esp_timer) for 10-second epoch loop
    const esp_timer_create_args_t timer_args = {
        .callback = &gateway_epoch_timer_cb,
        .arg = NULL,
        .name = "tdma_epoch_timer"
    };
    ret = esp_timer_create(&timer_args, &s_epoch_timer);
    if (ret == ESP_OK) {
        ESP_ERROR_CHECK(esp_timer_start_periodic(s_epoch_timer, 10000000ULL)); /* 10 seconds */
        ESP_LOGI(TAG, "High-resolution hardware timer active (10s period)");
    } else {
        ESP_LOGE(TAG, "Failed to create esp_timer: %s", esp_err_to_name(ret));
    }

    ESP_LOGI(TAG, "Gateway Master active and operational with V2 Join relay initialized");
}
