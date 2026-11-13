#include "gateway_app.h"

#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "sdkconfig.h"

#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "sx1276_driver.h"
#include "session_key_store.h"
#include "gateway_transport.h"
#include "gateway_v2_join.h"
#include "gateway_wal.h"
#include "airtime_policy.h"

#include "gateway_session_mgr.h"
#include "gateway_downlink.h"
#include "gateway_liveness.h"
#include "gateway_radio_bridge.h"

static const char *TAG = "gateway_master";

static gateway_wal_t s_gateway_wal;
static gateway_v2_join_engine_t s_join_engine;

esp_err_t gateway_app_init(void)
{
    ESP_LOGI(TAG, "Starting Gateway Master (ESP-IDF v6.1 / SX1276 MVP Continuous RX)");

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

    // Initialize Gateway WAL
    ret = gateway_wal_init(&s_gateway_wal);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway WAL: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway WAL initialized successfully");
    }

    // Initialize Crypto Subsystem
    ret = lora_mac_crypto_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize lora_mac crypto: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "LoRa MAC crypto initialized successfully");
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
        gateway_downlink_register_callbacks();
        gateway_transport_register_status_callback(&gateway_liveness_on_transport_connection_status);
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
        gateway_session_mgr_init(&s_join_engine);
        /* Restore persistent joined node sessions from NVS flash */
        gateway_restore_sessions_from_nvs();
    }

    gateway_downlink_init(&s_join_engine);

    // Initialize Gateway SX1276 radio transceiver
    ret = sx1276_init(NULL, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SX1276 driver: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "SX1276 radio initialized in STANDBY mode");
    }

    // Create static FreeRTOS task for 24/7 Continuous RX per RTOS-005
    gateway_radio_bridge_config_t bridge_cfg = {
        .join_engine = &s_join_engine,
        .wal = &s_gateway_wal,
        .gateway_id = transport_cfg.gateway_id,
    };
    ret = gateway_radio_bridge_init(&bridge_cfg);
    if (ret == ESP_OK) {
        (void)gateway_radio_bridge_start();
    }

    // Initialize and start Heartbeat and Liveness timers
    (void)gateway_liveness_init();
    (void)gateway_liveness_start_timers();

    ESP_LOGI(TAG, "Gateway Master active and operational in 24/7 Continuous RX mode");
    return ESP_OK;
}

void gateway_app_run(void)
{
    (void)gateway_app_init();
}
