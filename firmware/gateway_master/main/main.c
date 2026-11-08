#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

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

#define GATEWAY_TASK_STACK_WORDS (2048U)
static StackType_t s_gateway_task_stack[GATEWAY_TASK_STACK_WORDS];
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

static void gateway_tdma_master_task(void *pvParameters)
{
    (void)pvParameters;
    ESP_LOGI(TAG, "Gateway TDMA Master Task running");

    while (1) {
        /* Wait for superframe epoch notification or run periodically */
        (void)ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(10000));

        ESP_LOGI(TAG, "Starting Superframe sequence #%" PRIu32 " (Broadcasting DOWN_SYNC_BEACON 32B)",
                 s_tdma_engine.superframe_seq);
        esp_err_t err = gateway_tdma_run_superframe(&s_tdma_engine);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Superframe cycle returned warning: %s", esp_err_to_name(err));
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
        GATEWAY_TASK_STACK_WORDS,
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
