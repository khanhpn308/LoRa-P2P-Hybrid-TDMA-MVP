/**
 * @file timing_ring_buffer.h
 * @brief Bounded, ISR-safe ring buffer for timing event records.
 *
 * Designed for ESP32 FreeRTOS environment. Zero dynamic memory allocation.
 * Conforms to C Coding Standard v2 (bounded capacity, explicit overflow tracking).
 */

#ifndef TIMING_RING_BUFFER_H
#define TIMING_RING_BUFFER_H

#include "timing_harness_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define TIMING_RING_BUFFER_CAPACITY 256U

typedef struct {
    timing_event_record_t buffer[TIMING_RING_BUFFER_CAPACITY];
    volatile uint32_t head;       /**< Write index */
    volatile uint32_t tail;       /**< Read index */
    volatile uint32_t drop_count; /**< Dropped records due to buffer full */
    volatile uint32_t seq_next;   /**< Monotonic sequence generator */
} timing_ring_buffer_t;

/**
 * @brief Initialize or reset ring buffer state.
 */
void timing_ring_buffer_init(timing_ring_buffer_t *rb);

/**
 * @brief Push a new event record into the ring buffer from task context.
 *
 * @param rb Pointer to ring buffer instance.
 * @param rec Pointer to event record data.
 * @return true if stored successfully, false if dropped due to buffer overflow.
 */
bool timing_ring_buffer_push(timing_ring_buffer_t *rb, const timing_event_record_t *rec);

/**
 * @brief Push a new event record into the ring buffer from ISR context.
 *
 * Minimal latency: only writes fields and increments head. No blocking.
 *
 * @param rb Pointer to ring buffer instance.
 * @param event_type Event code.
 * @param timestamp_us Microsecond timestamp latched in ISR.
 * @param extra_info Extra auxiliary context.
 * @return true if stored, false if dropped.
 */
bool timing_ring_buffer_push_isr(timing_ring_buffer_t *rb,
                                uint8_t event_type,
                                int64_t timestamp_us,
                                uint32_t extra_info);

/**
 * @brief Pop an event record from ring buffer in task context.
 *
 * @param rb Pointer to ring buffer instance.
 * @param[out] out_rec Pointer to destination structure.
 * @return true if a record was popped, false if buffer is empty.
 */
bool timing_ring_buffer_pop(timing_ring_buffer_t *rb, timing_event_record_t *out_rec);

/**
 * @brief Check current number of unread records in buffer.
 */
uint32_t timing_ring_buffer_count(const timing_ring_buffer_t *rb);

/**
 * @brief Retrieve total count of dropped records since initialization.
 */
uint32_t timing_ring_buffer_get_drops(const timing_ring_buffer_t *rb);

#ifdef __cplusplus
}
#endif

#endif /* TIMING_RING_BUFFER_H */
