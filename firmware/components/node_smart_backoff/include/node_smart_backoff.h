#pragma once

#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Tiered smart backoff mechanism for ESP32 Sensor Node.
 *
 * Optimizes power consumption during CAD and ARQ backoff intervals:
 * - If ms == 0: Returns immediately with ESP_OK.
 * - If 0 < ms < 10: Uses FreeRTOS vTaskDelay (minimum 1 tick) to avoid PLL relock jitter and energy overhead.
 * - If ms >= 10: Ensures SX1276 radio is in STANDBY mode (never SLEEP, preserving FIFO contents),
 *   configures timer wakeup with 1.5ms (1500us) latency compensation,
 *   and enters ESP32 Light-sleep mode (~1mA vs ~30mA).
 *
 * FreeRTOS ticks and high-resolution timers are preserved across Light-sleep.
 *
 * Authority: Issue #313 (part of #312), ADR-0004.
 *
 * @param ms Backoff interval in milliseconds.
 * @return ESP_OK on success, or ESP-IDF error code.
 */
esp_err_t node_smart_backoff(uint32_t ms);

#ifdef __cplusplus
}
#endif
