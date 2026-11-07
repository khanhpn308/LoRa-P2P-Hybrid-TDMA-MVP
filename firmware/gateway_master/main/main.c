#include "esp_log.h"
#include "nvs_flash.h"
#include "session_key_store.h"
#include "gateway_transport.h"
#include "gateway_v2_join.h"
#include "sdkconfig.h"

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
        .target_gw_id = 1,
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

    ESP_LOGI(TAG, "Gateway Master active with session key store, transport, and V2 Join relay initialized");
}
