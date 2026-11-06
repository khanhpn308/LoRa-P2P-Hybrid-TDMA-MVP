#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file airtime_policy.h
 * @brief Pre-Transmit Local Duty Cycle & Airtime Enforcement Policy.
 *
 * Reference: contracts/radio-mac/specification.md Section 4.
 * Authority: ADR-0003, C Coding Standard v2, Issue #10.
 *
 * Applies to all radio emissions (BEACON, DATA, ACK, PRIORITY_ALERT, JOIN).
 * Emergency frames MAY NEVER bypass applicable regulatory TX limits.
 */

#define AIRTIME_POLICY_WINDOW_MS          (3600000U)  /**< 1-hour tracking window (ms) */
#define AIRTIME_POLICY_DEFAULT_PERMILLE   (10U)       /**< 1.0% default regulatory limit */

/**
 * @brief Initialize or reconfigure the local airtime policy limiter.
 *
 * @param max_permille Maximum duty cycle permitted in permille (e.g. 10 = 1.0%, 100 = 10.0%).
 *                     Valid range: 1..1000.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on out-of-range value.
 */
esp_err_t airtime_policy_init(uint16_t max_permille);

/**
 * @brief Pre-transmit safety check: verify if emitting a packet of duration toa_ms
 *        is permitted under the current accumulated airtime budget.
 *
 * @param packet_toa_ms Time on Air of the planned transmission in milliseconds.
 * @return ESP_OK if within budget, ESP_ERR_INVALID_STATE if duty limit would be violated.
 */
esp_err_t airtime_policy_check(uint32_t packet_toa_ms);

/**
 * @brief Record an actual completed RF transmission.
 *
 * @param packet_toa_ms Actual Time on Air in milliseconds.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on invalid value.
 */
esp_err_t airtime_policy_record_tx(uint32_t packet_toa_ms);

/**
 * @brief Get remaining airtime budget in milliseconds for the current window.
 *
 * @return Milliseconds of TX airtime remaining before reaching duty cycle limit.
 */
uint32_t airtime_policy_get_remaining_budget_ms(void);

/**
 * @brief Get accumulated transmission duration in milliseconds in current window.
 *
 * @return Total accumulated TX duration in milliseconds.
 */
uint32_t airtime_policy_get_accumulated_tx_ms(void);

/**
 * @brief Reset accumulated airtime counter (e.g. at window boundary or test reset).
 */
void airtime_policy_reset(void);

#ifdef __cplusplus
}
#endif
