#pragma once

#include "sx1276_types.h"
#include "sx1276_regs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file sx1276_driver.h
 * @brief Public Interface for Semtech SX1276 Non-blocking Shared Driver.
 *
 * Designed for ESP32-WROOM-32E + SX1276 (PCB HW-001) under FreeRTOS / ESP-IDF v6.1.
 * Governed by C Coding Standard v2, ADR-0003, and Owner SX1276 Active Profile.
 */

/**
 * @brief Populate default hardware configuration matching PCB HW-001.
 */
esp_err_t sx1276_get_default_hw_config(sx1276_hw_config_t *out_hw);

/**
 * @brief Populate default PHY configuration matching SX1276_TEST_PROFILE_V1.
 */
esp_err_t sx1276_get_default_phy_config(sx1276_phy_config_t *out_phy);

/**
 * @brief Initialize SPI bus, GPIOs, Radio Owner task, and apply PHY configuration.
 *
 * @param hw_conf Hardware pinout configuration (or NULL to use Kconfig defaults).
 * @param phy_conf PHY parameters configuration (or NULL to use Kconfig defaults).
 * @return ESP_OK on success, or ESP_ERR_* error code.
 */
esp_err_t sx1276_init(const sx1276_hw_config_t *hw_conf,
                      const sx1276_phy_config_t *phy_conf);

/**
 * @brief Safely reinitialize transceiver after ESP32 deep-sleep wake cycle.
 *
 * Asserts reset pulse, checks RegVersion, and re-applies validated configuration
 * without re-creating tasks or queues.
 * @return ESP_OK on success, or ESP_ERR_* error code.
 */
esp_err_t sx1276_reinit_after_wake(void);

/**
 * @brief Transition radio into low-power SLEEP mode.
 */
esp_err_t sx1276_sleep(void);

/**
 * @brief Transition radio into STANDBY mode.
 */
esp_err_t sx1276_standby(void);

/**
 * @brief Transmit a packet over RF.
 *
 * Enforces fail-closed safety gate: transmission is rejected if PA_PATH is UNKNOWN
 * or if RF transmission is disabled in configuration.
 *
 * @param payload Pointer to payload buffer.
 * @param length Byte length (1 to 255).
 * @param timeout_ticks Maximum FreeRTOS ticks to wait for TxDone.
 * @return ESP_OK on success, ESP_ERR_NOT_SUPPORTED if TX disabled/fail-closed,
 *         ESP_ERR_TIMEOUT if transmission timed out, or ESP_ERR_INVALID_ARG.
 */
esp_err_t sx1276_tx(const uint8_t *payload, uint8_t length, TickType_t timeout_ticks);

/**
 * @brief Enter single-packet receive mode (RxSingle) with two-stage host supervision.
 *
 * Used by Node during bounded ACK reception window and Maintenance slots.
 * Automatically returns to STANDBY upon RxDone or timeout.
 *
 * @param timeout_ticks Search supervision timeout ticks.
 * @return ESP_OK on command dispatch.
 */
esp_err_t sx1276_start_rx_single(TickType_t timeout_ticks);

/**
 * @brief Enter continuous receive mode (RxContinuous).
 *
 * Used by Gateway during timed receive phases.
 * @return ESP_OK on success.
 */
esp_err_t sx1276_start_rx_continuous(void);

/**
 * @brief Abort any active receive mode and return transceiver to STANDBY.
 */
esp_err_t sx1276_stop_rx(void);

/**
 * @brief Perform Channel Activity Detection (CAD).
 *
 * Samples channel for 1 symbol duration and returns whether activity was detected.
 *
 * @param[out] out_cad_detected Pointer to boolean receiving CAD detection result.
 * @param timeout_ticks Maximum wait ticks.
 * @return ESP_OK on success, or ESP_ERR_TIMEOUT.
 */
esp_err_t sx1276_cad(bool *out_cad_detected, TickType_t timeout_ticks);

/**
 * @brief Tune carrier frequency to specified VN920_V1 channel (0 to 10).
 *
 * @param channel_idx Channel index (0 = 920.250 MHz, 10 = 922.750 MHz).
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if out of bounds.
 */
esp_err_t sx1276_set_channel(uint8_t channel_idx);

/**
 * @brief Read an extracted and verified frame from the driver RX queue.
 *
 * @param[out] out_frame Pointer to structure receiving frame data.
 * @param wait_ticks Maximum ticks to wait for frame arrival.
 * @return ESP_OK if frame retrieved, or ESP_ERR_TIMEOUT.
 */
esp_err_t sx1276_read_frame(sx1276_rx_frame_t *out_frame, TickType_t wait_ticks);

/**
 * @brief Retrieve diagnostic metrics and error counters.
 */
esp_err_t sx1276_get_diagnostics(sx1276_diagnostics_t *out_diag);

/**
 * @brief Validate typed PHY configuration against silicon and project constraints.
 */
esp_err_t sx1276_config_validate(const sx1276_phy_config_t *conf);

/**
 * @brief Programmatically build register plan from validated configuration.
 */
esp_err_t sx1276_register_plan_build(const sx1276_phy_config_t *conf,
                                     sx1276_register_plan_t *out_plan);

/**
 * @brief Calculate exact Time-on-Air (ToA) in microseconds for candidate payload.
 */
esp_err_t sx1276_calculate_toa_us(const sx1276_phy_config_t *conf,
                                  uint8_t payload_len,
                                  uint32_t *out_toa_us);

#ifdef __cplusplus
}
#endif
