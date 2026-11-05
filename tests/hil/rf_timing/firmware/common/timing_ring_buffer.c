/**
 * @file timing_ring_buffer.c
 * @brief Implementation of bounded, ISR-safe ring buffer for timing event records.
 */

#include "timing_ring_buffer.h"
#include <string.h>

void timing_ring_buffer_init(timing_ring_buffer_t *rb)
{
    if (rb == NULL) {
        return;
    }
    memset((void *)rb->buffer, 0, sizeof(rb->buffer));
    rb->head = 0U;
    rb->tail = 0U;
    rb->drop_count = 0U;
    rb->seq_next = 1U;
}

bool timing_ring_buffer_push(timing_ring_buffer_t *rb, const timing_event_record_t *rec)
{
    if (rb == NULL || rec == NULL) {
        return false;
    }

    uint32_t current_head = rb->head;
    uint32_t next_head = (current_head + 1U) % TIMING_RING_BUFFER_CAPACITY;

    if (next_head == rb->tail) {
        /* Buffer is full: record drop and fail */
        rb->drop_count++;
        return false;
    }

    timing_event_record_t entry = *rec;
    entry.seq = rb->seq_next++;
    rb->buffer[current_head] = entry;
    rb->head = next_head;
    return true;
}

bool timing_ring_buffer_push_isr(timing_ring_buffer_t *rb,
                                uint8_t event_type,
                                int64_t timestamp_us,
                                uint32_t extra_info)
{
    if (rb == NULL) {
        return false;
    }

    uint32_t current_head = rb->head;
    uint32_t next_head = (current_head + 1U) % TIMING_RING_BUFFER_CAPACITY;

    if (next_head == rb->tail) {
        rb->drop_count++;
        return false;
    }

    timing_event_record_t entry;
    memset(&entry, 0, sizeof(entry));
    entry.seq = rb->seq_next++;
    entry.timestamp_us = timestamp_us;
    entry.event_type = event_type;
    entry.evidence_class = (uint8_t)EVIDENCE_SOFTWARE_TIMESTAMP;
    entry.extra_info = extra_info;

    rb->buffer[current_head] = entry;
    rb->head = next_head;
    return true;
}

bool timing_ring_buffer_pop(timing_ring_buffer_t *rb, timing_event_record_t *out_rec)
{
    if (rb == NULL || out_rec == NULL) {
        return false;
    }

    uint32_t current_tail = rb->tail;
    if (current_tail == rb->head) {
        /* Buffer is empty */
        return false;
    }

    *out_rec = rb->buffer[current_tail];
    rb->tail = (current_tail + 1U) % TIMING_RING_BUFFER_CAPACITY;
    return true;
}

uint32_t timing_ring_buffer_count(const timing_ring_buffer_t *rb)
{
    if (rb == NULL) {
        return 0U;
    }
    uint32_t head = rb->head;
    uint32_t tail = rb->tail;
    if (head >= tail) {
        return head - tail;
    }
    return TIMING_RING_BUFFER_CAPACITY - (tail - head);
}

uint32_t timing_ring_buffer_get_drops(const timing_ring_buffer_t *rb)
{
    return rb ? rb->drop_count : 0U;
}
