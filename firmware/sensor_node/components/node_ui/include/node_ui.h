#pragma once

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Display unjoined / revoked status screen on local OLED.
 *
 * If CONFIG_OLED_SSD1306_ENABLE is enabled, initializes SSD1306 OLED,
 * displays "STATUS: UNJOINED" and "NODE REVOKED", refreshes display RAM,
 * and deinits the OLED driver.
 * If CONFIG_OLED_SSD1306_ENABLE is disabled (0), this function is a no-op returning ESP_OK.
 *
 * @return esp_err_t ESP_OK on success or when OLED is disabled, or driver error code.
 */
esp_err_t node_ui_show_unjoined(void);

/**
 * @brief Display confirmed sensor event metrics on local OLED.
 *
 * If CONFIG_OLED_SSD1306_ENABLE is enabled, initializes SSD1306 OLED,
 * displays formatted event lines (event value, relative boot time, total events count),
 * refreshes display RAM, and deinits the OLED driver.
 * If CONFIG_OLED_SSD1306_ENABLE is disabled (0), this function is a no-op returning ESP_OK.
 *
 * @param value Confirmed sensor event value.
 * @param rel_time_sec Relative time in seconds since boot.
 * @param total_events Cumulative button events count.
 * @return esp_err_t ESP_OK on success or when OLED is disabled, or driver error code.
 */
esp_err_t node_ui_show_event(int16_t value, uint32_t rel_time_sec, uint32_t total_events);

/**
 * @brief Pulse GPIO LED once to indicate verified DOWN_EVENT_ACK delivery.
 *
 * If CONFIG_NODE_ACK_LED_ENABLE is enabled (1), initializes the configured GPIO
 * (CONFIG_NODE_ACK_LED_GPIO) as active-high output with safe pin collision checks,
 * drives it HIGH for CONFIG_NODE_ACK_LED_PULSE_MS ms using a bounded FreeRTOS task delay,
 * and then drives it LOW.
 *
 * If CONFIG_NODE_ACK_LED_ENABLE is disabled (0), this function is an immediate no-op
 * returning ESP_OK without configuring GPIO or delaying the wake session.
 *
 * @return esp_err_t ESP_OK on success or when LED feedback is disabled,
 *         ESP_ERR_INVALID_ARG if configured GPIO conflicts with reserved hardware pins,
 *         or driver error code on GPIO operation failure.
 */
esp_err_t node_ui_blink_event_ack(void);

#ifdef __cplusplus
}
#endif
