#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file gateway_wal.h
 * @brief Bounded in-memory WAL buffer for decrypted uplink events awaiting backend dispatch.
 *
 * Authority: DEC-127-05, D12 §6.3, C Coding Standard v2 (MEM-001, MEM-002, MEM-005, SEC-005).
 * Enforces zero dynamic heap allocation and deterministic drop-oldest ring buffer semantics.
 */

#define GATEWAY_WAL_CAPACITY (64U) /**< Bounded queue depth per MEM-002, D12 §6.3 */

/**
 * @brief Verified and decrypted uplink event intent stored in WAL.
 */
typedef struct {
    uint8_t  node_id;        /**< Source Node ID (1..15) */
    uint8_t  session_sel;    /**< Active session index (0 or 1) */
    uint32_t frame_counter;  /**< Monotonic uplink frame counter */
    uint32_t event_ref;      /**< Node local event reference (4B) */
    uint32_t event_time;     /**< Unix timestamp or 0xFFFFFFFF (4B) */
    uint8_t  event_code;     /**< Violation/alarm category code (1B) */
    int16_t  event_value;    /**< Measurement reading at violation (2B) */
    uint32_t received_at_ms; /**< Local gateway monotonic reception timestamp (ms) */
    int16_t  rssi_dbm;       /**< Received packet RSSI */
    int8_t   snr_db_quarter; /**< Received packet SNR */
    uint8_t  channel_idx;    /**< Operating channel index (0..10) */
    uint64_t rx_monotonic_us;/**< Monotonic microsecond latch at RxDone */
    uint64_t sample_seq;     /**< Monotonic RF sample sequence (stable across replay) */
} gateway_wal_event_t;

/**
 * @brief Bounded in-memory event WAL structure.
 */
typedef struct {
    gateway_wal_event_t entries[GATEWAY_WAL_CAPACITY];
    size_t   head;                   /**< Write pointer */
    size_t   tail;                   /**< Read pointer */
    size_t   count;                  /**< Active pending event count */
    uint32_t overflow_dropped_count; /**< Monotonic overflow drop counter (D12 §6.3) */
} gateway_wal_t;

/**
 * @brief Initialize static WAL buffer and reset drop counter.
 *
 * @param wal Pointer to WAL instance.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if wal is NULL.
 */
esp_err_t gateway_wal_init(gateway_wal_t *wal);

/**
 * @brief Commit a verified event into bounded WAL (DEC-127-05 / D12 §6.3).
 *
 * If buffer is at capacity, drops the oldest pending event, increments
 * overflow_dropped_count, and overwrites with the newest verified event.
 *
 * @param wal Pointer to WAL instance.
 * @param event Pointer to validated event to enqueue.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on NULL pointer.
 */
esp_err_t gateway_wal_push(gateway_wal_t *wal, const gateway_wal_event_t *event);

/**
 * @brief Pop the oldest event from WAL buffer (e.g. after MQTT commit).
 *
 * @param wal Pointer to WAL instance.
 * @param out_event Destination buffer for popped event.
 * @return ESP_OK on success, ESP_ERR_NOT_FOUND if WAL is empty.
 */
esp_err_t gateway_wal_pop(gateway_wal_t *wal, gateway_wal_event_t *out_event);

/**
 * @brief Peek at the oldest event without advancing read pointer.
 *
 * @param wal Pointer to WAL instance.
 * @param out_event Destination buffer.
 * @return ESP_OK on success, ESP_ERR_NOT_FOUND if empty.
 */
esp_err_t gateway_wal_peek(const gateway_wal_t *wal, gateway_wal_event_t *out_event);

/**
 * @brief Get current number of stored events in WAL.
 */
size_t gateway_wal_count(const gateway_wal_t *wal);

/**
 * @brief Get monotonic cumulative count of dropped events due to overflow.
 */
uint32_t gateway_wal_get_dropped_count(const gateway_wal_t *wal);

/**
 * @brief Check if WAL is currently at maximum capacity.
 */
bool gateway_wal_is_full(const gateway_wal_t *wal);

/**
 * @brief Clear all WAL entries and zeroize memory (SEC-005).
 */
void gateway_wal_clear(gateway_wal_t *wal);

#ifdef __cplusplus
}
#endif
