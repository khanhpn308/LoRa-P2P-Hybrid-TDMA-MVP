#include "gateway_wifi.h"
#include <string.h>

#ifdef ESP_PLATFORM
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "esp_log.h"
#include "esp_timer.h"
#endif

#ifndef ESP_PLATFORM
#include "esp_log.h"
#endif

static const char *TAG __attribute__((unused)) = "gateway_wifi";

static gateway_wifi_config_t s_config;
static bool s_initialized = false;
static bool s_running = false;
static bool s_connected = false;
static bool s_got_ip = false;
static uint32_t s_retry_count = 0;
static uint32_t s_reconnect_attempts = 0;

#ifdef ESP_PLATFORM
static esp_netif_t *s_sta_netif = NULL;
static esp_event_handler_instance_t s_wifi_handler_instance = NULL;
static esp_event_handler_instance_t s_ip_handler_instance = NULL;
static esp_timer_handle_t s_reconnect_timer = NULL;

static void reconnect_timer_cb(void *arg)
{
    (void)arg;
    if (s_running && !s_connected) {
        ESP_LOGI(TAG, "Executing WiFi reconnect attempt #%" PRIu32, s_reconnect_attempts);
        esp_err_t err = esp_wifi_connect();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_wifi_connect failed: %s", esp_err_to_name(err));
        }
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        ESP_LOGI(TAG, "WiFi station started, connecting to %s...", s_config.ssid);
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        s_connected = false;
        s_got_ip = false;
        s_reconnect_attempts++;

        if (s_config.event_cb) {
            s_config.event_cb(false, false);
        }

        if (s_running) {
            uint32_t backoff_ms = gateway_wifi_compute_backoff_ms(s_retry_count, s_config.max_retry);
            s_retry_count++;
            ESP_LOGW(TAG, "WiFi disconnected. Next reconnect in %" PRIu32 " ms (retry %" PRIu32 ")",
                     backoff_ms, s_retry_count);

            if (backoff_ms == 0) {
                esp_wifi_connect();
            } else {
                /* Non-blocking timer dispatch (RTOS-001) */
                esp_timer_stop(s_reconnect_timer);
                esp_timer_start_once(s_reconnect_timer, (uint64_t)backoff_ms * 1000ULL);
            }
        }
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "WiFi station acquired IP: " IPSTR, IP2STR(&event->ip_info.ip));
        s_connected = true;
        s_got_ip = true;
        s_retry_count = 0;

        if (s_config.event_cb) {
            s_config.event_cb(true, true);
        }
    }
}
#endif /* ESP_PLATFORM */

uint32_t gateway_wifi_compute_backoff_ms(uint32_t retry_count, uint8_t max_retry)
{
    if (retry_count < (uint32_t)max_retry) {
        return 0;
    }

    uint32_t shift = retry_count - (uint32_t)max_retry;
    if (shift > 6) {
        shift = 6;
    }

    uint32_t backoff = GATEWAY_WIFI_BASE_BACKOFF_MS * (1U << shift);
    if (backoff > GATEWAY_WIFI_MAX_BACKOFF_MS) {
        backoff = GATEWAY_WIFI_MAX_BACKOFF_MS;
    }
    return backoff;
}

esp_err_t gateway_wifi_init(const gateway_wifi_config_t *config)
{
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_initialized) {
        return ESP_OK;
    }

    memset(&s_config, 0, sizeof(s_config));
    strncpy(s_config.ssid, config->ssid, sizeof(s_config.ssid) - 1);
    strncpy(s_config.password, config->password, sizeof(s_config.password) - 1);
    s_config.max_retry = (config->max_retry > 0) ? config->max_retry : 5;
    s_config.event_cb = config->event_cb;

    s_retry_count = 0;
    s_reconnect_attempts = 0;
    s_connected = false;
    s_got_ip = false;

#ifdef ESP_PLATFORM
    esp_err_t err;

    err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "esp_netif_init failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "esp_event_loop_create_default failed: %s", esp_err_to_name(err));
        return err;
    }

    s_sta_netif = esp_netif_create_default_wifi_sta();
    if (s_sta_netif == NULL) {
        ESP_LOGE(TAG, "esp_netif_create_default_wifi_sta failed");
        return ESP_FAIL;
    }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_init failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID,
                                              &wifi_event_handler, NULL,
                                              &s_wifi_handler_instance);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Register wifi event handler failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP,
                                              &wifi_event_handler, NULL,
                                              &s_ip_handler_instance);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Register ip event handler failed: %s", esp_err_to_name(err));
        return err;
    }

    wifi_config_t wifi_cfg;
    memset(&wifi_cfg, 0, sizeof(wifi_cfg));
    strncpy((char *)wifi_cfg.sta.ssid, s_config.ssid, sizeof(wifi_cfg.sta.ssid) - 1);
    strncpy((char *)wifi_cfg.sta.password, s_config.password, sizeof(wifi_cfg.sta.password) - 1);
    wifi_cfg.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_mode failed: %s", esp_err_to_name(err));
        return err;
    }

    err = esp_wifi_set_config(WIFI_IF_STA, &wifi_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_set_config failed: %s", esp_err_to_name(err));
        return err;
    }

    const esp_timer_create_args_t timer_args = {
        .callback = &reconnect_timer_cb,
        .name = "wifi_reconnect_tmr",
    };
    err = esp_timer_create(&timer_args, &s_reconnect_timer);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_timer_create failed: %s", esp_err_to_name(err));
        return err;
    }
#endif /* ESP_PLATFORM */

    s_initialized = true;
    return ESP_OK;
}

esp_err_t gateway_wifi_start(void)
{
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    s_running = true;

#ifdef ESP_PLATFORM
    esp_err_t err = esp_wifi_start();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_start failed: %s", esp_err_to_name(err));
        s_running = false;
        return err;
    }
#endif

    return ESP_OK;
}

esp_err_t gateway_wifi_stop(void)
{
    if (!s_initialized || !s_running) {
        return ESP_OK;
    }

    s_running = false;
    s_connected = false;
    s_got_ip = false;

#ifdef ESP_PLATFORM
    if (s_reconnect_timer) {
        esp_timer_stop(s_reconnect_timer);
    }
    esp_wifi_disconnect();
    esp_wifi_stop();
#endif

    return ESP_OK;
}

esp_err_t gateway_wifi_deinit(void)
{
    if (!s_initialized) {
        return ESP_OK;
    }

    gateway_wifi_stop();

#ifdef ESP_PLATFORM
    if (s_reconnect_timer) {
        esp_timer_delete(s_reconnect_timer);
        s_reconnect_timer = NULL;
    }

    if (s_wifi_handler_instance) {
        esp_event_handler_instance_unregister(WIFI_EVENT, ESP_EVENT_ANY_ID, s_wifi_handler_instance);
        s_wifi_handler_instance = NULL;
    }
    if (s_ip_handler_instance) {
        esp_event_handler_instance_unregister(IP_EVENT, IP_EVENT_STA_GOT_IP, s_ip_handler_instance);
        s_ip_handler_instance = NULL;
    }

    esp_wifi_deinit();
    if (s_sta_netif) {
        esp_netif_destroy_default_wifi(s_sta_netif);
        s_sta_netif = NULL;
    }
#endif

    s_initialized = false;
    return ESP_OK;
}

bool gateway_wifi_is_connected(void)
{
    return s_connected && s_got_ip;
}

uint32_t gateway_wifi_get_reconnect_attempts(void)
{
    return s_reconnect_attempts;
}
