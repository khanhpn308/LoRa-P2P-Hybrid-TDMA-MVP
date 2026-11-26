#include "gateway_app.h"

#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "mbedtls/platform_util.h"
#include "sdkconfig.h"

#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "sx1276_driver.h"
#include "session_key_store.h"
#include "gateway_mqtt.h"
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
static char s_gateway_boot_epoch[37] = {0};

/* Static PEM buffers retained for ESP-MQTT reconnect lifecycle (MEM-001, MEM-002, MEM-005) */
static char s_tls_ca_cert[GATEWAY_TLS_PEM_MAX_LEN];
static char s_tls_client_cert[GATEWAY_TLS_PEM_MAX_LEN];
static char s_tls_client_key[GATEWAY_TLS_PEM_MAX_LEN];

#ifdef GATEWAY_HAS_EMBEDDED_TLS_CERTS
extern const char _binary_ca_crt_start[] asm("_binary_ca_crt_start");
extern const char _binary_client_crt_start[] asm("_binary_client_crt_start");
extern const char _binary_client_key_start[] asm("_binary_client_key_start");
#endif

static void gateway_app_init_boot_epoch(void)
{
    if (s_gateway_boot_epoch[0] != '\0') {
        return; /* Retain same epoch throughout boot, including MQTT reconnects */
    }
    uint8_t rand_bytes[16];
    esp_fill_random(rand_bytes, sizeof(rand_bytes));
    /* RFC 4122 UUID v4: set version to 4 (0100b) and variant to RFC 4122 (10b) */
    rand_bytes[6] = (uint8_t)((rand_bytes[6] & 0x0f) | 0x40);
    rand_bytes[8] = (uint8_t)((rand_bytes[8] & 0x3f) | 0x80);
    int written = snprintf(s_gateway_boot_epoch, sizeof(s_gateway_boot_epoch),
        "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
        rand_bytes[0], rand_bytes[1], rand_bytes[2], rand_bytes[3],
        rand_bytes[4], rand_bytes[5], rand_bytes[6], rand_bytes[7],
        rand_bytes[8], rand_bytes[9], rand_bytes[10], rand_bytes[11],
        rand_bytes[12], rand_bytes[13], rand_bytes[14], rand_bytes[15]);
    if (written != 36) {
        ESP_LOGE(TAG, "Failed to format gateway boot epoch UUID");
    } else {
        ESP_LOGI(TAG, "Gateway boot epoch initialized: %s", s_gateway_boot_epoch);
    }
}

const char *gateway_app_get_boot_epoch(void)
{
    if (s_gateway_boot_epoch[0] == '\0') {
        gateway_app_init_boot_epoch();
    }
    return s_gateway_boot_epoch;
}

esp_err_t gateway_app_init(void)
{
    ESP_LOGI(TAG, "Starting Gateway Master (ESP-IDF v6.1 / SX1276 MVP Continuous RX)");

    /* Initialize unique boot epoch UUID once at initialization */
    gateway_app_init_boot_epoch();

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
        .disable_auto_connect = false,
    };

#ifdef CONFIG_GATEWAY_BROKER_URI
    const char *broker_uri_override = CONFIG_GATEWAY_BROKER_URI;
#else
    const char *broker_uri_override = "";
#endif
#ifdef CONFIG_GATEWAY_BROKER_HOST
    const char *broker_host = CONFIG_GATEWAY_BROKER_HOST;
#else
    const char *broker_host = "";
#endif
#ifdef CONFIG_GATEWAY_BROKER_PORT
    uint16_t broker_port = (uint16_t)CONFIG_GATEWAY_BROKER_PORT;
#else
    uint16_t broker_port = 8883U;
#endif
#ifdef CONFIG_GATEWAY_MQTT_TLS_ENABLED
    bool tls_enabled = (CONFIG_GATEWAY_MQTT_TLS_ENABLED != 0);
#else
    bool tls_enabled = true;
#endif

    bool transport_ready_to_init = true;
    ret = gateway_mqtt_resolve_broker_uri(transport_cfg.broker_uri,
                                          sizeof(transport_cfg.broker_uri),
                                          broker_uri_override,
                                          broker_host,
                                          broker_port,
                                          tls_enabled);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Fail-closed: failed to resolve MQTT broker URI (%s)", esp_err_to_name(ret));
        transport_ready_to_init = false;
    } else if (gateway_mqtt_is_tls_uri(transport_cfg.broker_uri)) {
        esp_err_t tls_err = gateway_transport_load_tls_certs_from_nvs(
            transport_cfg.gateway_id,
            s_tls_ca_cert, sizeof(s_tls_ca_cert),
            s_tls_client_cert, sizeof(s_tls_client_cert),
            s_tls_client_key, sizeof(s_tls_client_key));
        if (tls_err == ESP_OK) {
            transport_cfg.broker_ca_cert = s_tls_ca_cert;
            transport_cfg.client_cert = s_tls_client_cert;
            transport_cfg.client_key = s_tls_client_key;
            ESP_LOGI(TAG, "Loaded mTLS credentials from NVS namespace '%s' for gateway '%s'",
                     GATEWAY_TLS_NVS_NAMESPACE, transport_cfg.gateway_id);
        } else {
#ifdef GATEWAY_HAS_EMBEDDED_TLS_CERTS
            if (tls_err == ESP_ERR_NVS_NOT_FOUND) {
                ESP_LOGW(TAG, "NVS '%s' not provisioned; using gitignored embedded mTLS fallback",
                         GATEWAY_TLS_NVS_NAMESPACE);
                transport_cfg.broker_ca_cert = _binary_ca_crt_start;
                transport_cfg.client_cert = _binary_client_crt_start;
                transport_cfg.client_key = _binary_client_key_start;
            } else {
                ESP_LOGE(TAG, "Fail-closed: NVS mTLS credential error (%s); refusing MQTT connection",
                         esp_err_to_name(tls_err));
                transport_ready_to_init = false;
            }
#else
            ESP_LOGE(TAG, "Fail-closed: mTLS credentials missing/invalid in NVS '%s' (%s); refusing MQTT connection",
                     GATEWAY_TLS_NVS_NAMESPACE, esp_err_to_name(tls_err));
            transport_ready_to_init = false;
#endif
        }
    } else {
        ESP_LOGW(TAG, "Plaintext MQTT dev-insecure mode active (%s); mTLS disabled by configuration",
                 transport_cfg.broker_uri);
    }

    if (transport_ready_to_init) {
        ret = gateway_transport_init(&transport_cfg);
        if (ret != ESP_OK) {
            ESP_LOGE(TAG, "Failed to initialize gateway transport: %s", esp_err_to_name(ret));
            mbedtls_platform_zeroize(s_tls_ca_cert, sizeof(s_tls_ca_cert));
            mbedtls_platform_zeroize(s_tls_client_cert, sizeof(s_tls_client_cert));
            mbedtls_platform_zeroize(s_tls_client_key, sizeof(s_tls_client_key));
        } else {
            ESP_LOGI(TAG, "Gateway transport initialized successfully (%s)", transport_cfg.broker_uri);
            gateway_downlink_register_callbacks();
            gateway_transport_register_status_callback(&gateway_liveness_on_transport_connection_status);
        }
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
    snprintf(join_cfg.gateway_epoch, sizeof(join_cfg.gateway_epoch), "%s", s_gateway_boot_epoch);
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
        .gateway_epoch = s_gateway_boot_epoch,
    };
    ret = gateway_radio_bridge_init(&bridge_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway radio bridge: %s", esp_err_to_name(ret));
        return ret;
    }
    ret = gateway_radio_bridge_start();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start gateway radio bridge: %s", esp_err_to_name(ret));
        return ret;
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
