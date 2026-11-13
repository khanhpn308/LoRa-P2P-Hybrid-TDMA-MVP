#pragma once

#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
#include "node_v2_join.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Populate node_v2_join_radio_hal_t callback structure with production Radio HAL implementations.
 *
 * @param[out] out_hal Pointer to node_v2_join_radio_hal_t structure to fill.
 * @return esp_err_t ESP_OK on success, ESP_ERR_INVALID_ARG if out_hal is NULL.
 */
esp_err_t node_radio_hal_get_join_hal(node_v2_join_radio_hal_t *out_hal);

/**
 * @brief Put radio in continuous RX mode after draining any stale frames from the RX FIFO/queue.
 *
 * @param timeout_ms Listen timeout parameter (unused in continuous RX transition).
 * @return esp_err_t Result from sx1276_start_rx_continuous().
 */
esp_err_t node_radio_hal_rx_single(uint32_t timeout_ms);

/**
 * @brief Read a received frame from the radio RX queue within the specified timeout.
 *
 * @param[out] out_buf Destination buffer for frame payload.
 * @param[out] out_len Pointer to store length of received payload.
 * @param wait_ms Maximum time to wait in milliseconds.
 * @return esp_err_t ESP_OK if frame received, ESP_ERR_INVALID_ARG if args NULL, or timeout/error.
 */
esp_err_t node_radio_hal_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms);

#ifdef __cplusplus
}
#endif
