#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "sdkconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifdef CONFIG_NODE_CAD_CW_MIN_MS
#define NODE_CAD_CW_MIN_MS         ((uint32_t)CONFIG_NODE_CAD_CW_MIN_MS)
#else
#define NODE_CAD_CW_MIN_MS         16U
#endif

#ifdef CONFIG_NODE_CAD_CW_MAX_MS
#define NODE_CAD_CW_MAX_MS         ((uint32_t)CONFIG_NODE_CAD_CW_MAX_MS)
#else
#define NODE_CAD_CW_MAX_MS         256U
#endif

#ifdef CONFIG_NODE_CAD_MAX_RETRIES
#define NODE_CAD_MAX_RETRIES       ((uint8_t)CONFIG_NODE_CAD_MAX_RETRIES)
#else
#define NODE_CAD_MAX_RETRIES       5U
#endif

/**
 * @brief Calculate the contention window CW_k in milliseconds at attempt k.
 *
 * Implements ADR-0004 (Section 2.2, Item 3):
 * CW_k = min(CW_max, CW_min * 2^(k-1)) for attempt k in 1..NODE_CAD_MAX_RETRIES.
 *
 * For default parameters (CW_min=16ms, CW_max=256ms):
 * - Attempt 1 (k=1): min(256, 16 * 1) = 16 ms
 * - Attempt 2 (k=2): min(256, 16 * 2) = 32 ms
 * - Attempt 3 (k=3): min(256, 16 * 4) = 64 ms
 * - Attempt 4 (k=4): min(256, 16 * 8) = 128 ms
 * - Attempt 5 (k=5): min(256, 16 * 16) = 256 ms
 *
 * @param attempt Attempt index (1-based; attempt 0 is treated as 1).
 * @return Contention window in milliseconds.
 */
uint32_t node_get_cad_contention_window_ms(uint8_t attempt);

/**
 * @brief Calculate exponential random backoff time in milliseconds for CAD CSMA/CA.
 *
 * Implements ADR-0004 (Section 2.2, Item 3):
 * Backoff_Time = random_uniform(0, CW_k) ms = esp_random() % (CW_k + 1).
 *
 * @param attempt Attempt index (1-based; attempt 0 is treated as 1).
 * @return Random backoff duration in milliseconds within [0, CW_k].
 */
uint32_t node_calculate_cad_backoff_ms(uint8_t attempt);

#ifdef __cplusplus
}
#endif
