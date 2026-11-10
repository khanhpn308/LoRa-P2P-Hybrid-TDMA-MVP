#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "sdkconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifdef CONFIG_NODE_ARQ_MAX_RETRIES
#define NODE_ARQ_MAX_RETRIES       ((uint8_t)CONFIG_NODE_ARQ_MAX_RETRIES)
#else
#define NODE_ARQ_MAX_RETRIES       3U
#endif

#ifdef CONFIG_NODE_ARQ_BACKOFF_MIN_MS
#define NODE_ARQ_BACKOFF_MIN_MS    ((uint32_t)CONFIG_NODE_ARQ_BACKOFF_MIN_MS)
#else
#define NODE_ARQ_BACKOFF_MIN_MS    50U
#endif

#ifdef CONFIG_NODE_ARQ_BACKOFF_MAX_MS
#define NODE_ARQ_BACKOFF_MAX_MS    ((uint32_t)CONFIG_NODE_ARQ_BACKOFF_MAX_MS)
#else
#define NODE_ARQ_BACKOFF_MAX_MS    200U
#endif

/**
 * @brief Calculate random backoff time in milliseconds for Intra-session Stop-and-Wait ARQ.
 *
 * Implements Issue #316:
 * Generates a uniform random backoff in [NODE_ARQ_BACKOFF_MIN_MS, NODE_ARQ_BACKOFF_MAX_MS]
 * (default: 50ms - 200ms) before attempting immediate retransmission after ACK loss.
 *
 * @return Random backoff duration in milliseconds.
 */
uint32_t node_calculate_arq_backoff_ms(void);

/**
 * @brief Check if another retransmission attempt is permitted under ARQ policy.
 *
 * @param tx_retries Current retry count.
 * @param tx_max Maximum allowed retries (threshold).
 * @return true if tx_retries < tx_max, false otherwise.
 */
bool node_arq_should_retry(uint8_t tx_retries, uint8_t tx_max);

/**
 * @brief Reset SX1276 FIFO pointer to TX base address (FifoTxBaseAddr = 0x80).
 *
 * Transitions the transceiver into STANDBY mode via Radio Owner, guaranteeing
 * that subsequent sx1276_tx sets RegFifoAddrPtr to RegFifoTxBaseAddr (0x80)
 * before writing the payload, avoiding corrupted/stale offsets from previous RX windows.
 *
 * Authority: Semtech SX1276 Datasheet & docs/hardware/sx1276/SX1276_DRIVER_OPERATIONS.md.
 *
 * @return ESP_OK on success, or ESP-IDF error code from driver.
 */
esp_err_t node_reset_sx1276_fifo_tx_ptr(void);

#ifdef __cplusplus
}
#endif
