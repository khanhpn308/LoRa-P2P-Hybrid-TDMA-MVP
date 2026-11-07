#ifndef GATEWAY_WIFI_H
#define GATEWAY_WIFI_H

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_WIFI_BASE_BACKOFF_MS 1000
#define GATEWAY_WIFI_MAX_BACKOFF_MS  60000

typedef void (*gateway_wifi_event_cb_t)(bool connected, bool got_ip);

typedef struct {
    char ssid[32];
    char password[64];
    uint8_t max_retry;
    gateway_wifi_event_cb_t event_cb;
} gateway_wifi_config_t;

/**
 * @brief Initialize WiFi station driver and register default event handlers.
 *
 * @param config Pointer to WiFi configuration.
 * @return ESP_OK on success.
 */
esp_err_t gateway_wifi_init(const gateway_wifi_config_t *config);

/**
 * @brief Start WiFi station and initiate connection.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_wifi_start(void);

/**
 * @brief Stop WiFi station and disconnect.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_wifi_stop(void);

/**
 * @brief Deinitialize WiFi station driver.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_wifi_deinit(void);

/**
 * @brief Check if WiFi station is connected with an assigned IP.
 *
 * @return true if connected and IP obtained.
 */
bool gateway_wifi_is_connected(void);

/**
 * @brief Get cumulative number of WiFi reconnect attempts.
 *
 * @return Count of reconnect triggers.
 */
uint32_t gateway_wifi_get_reconnect_attempts(void);

/**
 * @brief Compute exponential backoff in milliseconds based on retry count.
 *
 * Pure function suitable for deterministic unit testing.
 *
 * @param retry_count Number of consecutive failed attempts.
 * @param max_retry Number of rapid retries before exponential backoff begins.
 * @return Backoff delay in milliseconds (capped at GATEWAY_WIFI_MAX_BACKOFF_MS).
 */
uint32_t gateway_wifi_compute_backoff_ms(uint32_t retry_count, uint8_t max_retry);

#ifdef __cplusplus
}
#endif

#endif /* GATEWAY_WIFI_H */
