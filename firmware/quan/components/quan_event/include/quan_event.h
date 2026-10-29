#ifndef QUAN_EVENT_H
#define QUAN_EVENT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Local application data only: never serialize this struct as an RF frame.
 * sequence is process-local, not a durable identity or replay counter. */
typedef struct {
    uint32_t sequence;
    uint64_t created_ms;
} quan_event_t;

typedef enum {
    QUAN_EVENT_OK = 0,
    QUAN_EVENT_INVALID,
    QUAN_EVENT_FULL,
    QUAN_EVENT_EMPTY,
    QUAN_EVENT_CLOCK_REVERSED
} quan_event_status_t;

/* Caller-owned storage; exactly one task owns each object. No ISR use,
 * synchronization, allocation or asynchronous retained event pointers. */
typedef struct {
    quan_event_t *storage;
    size_t capacity;
    size_t head;
    size_t count;
    uint32_t dropped;
} quan_event_queue_t;

typedef struct {
    bool initialized;
    bool candidate_pressed;
    bool stable_pressed;
    uint64_t candidate_since_ms;
    uint64_t last_sample_ms;
    uint64_t debounce_ms;
} quan_event_button_t;

/* storage must remain valid and unmodified for queue lifetime, with capacity
 * elements (capacity > 0). Reset is permitted only with no users pending.
 * Returns INVALID for null pointers/zero capacity/size overflow. */
quan_event_status_t quan_event_init_queue(quan_event_queue_t *queue,
                                        quan_event_t *storage, size_t capacity);
/* Copies one event. FULL drops newest and saturates dropped at UINT32_MAX.
 * INVALID for null/invalid state. Event pointer is borrowed only until return. */
quan_event_status_t quan_event_push_event(quan_event_queue_t *queue,
                                        const quan_event_t *event);
/* Copies/removes oldest event; EMPTY leaves output unchanged. INVALID on null
 * or invalid state. Output belongs to caller and has no queue lifetime tie. */
quan_event_status_t quan_event_pop_event(quan_event_queue_t *queue,
                                       quan_event_t *event);
/* Configurable nonzero debounce in ms; no platform/pin defaults. INVALID on
 * null or zero debounce. Initializes released; first sample establishes
 * baseline, so a button held at startup does not create an event. */
quan_event_status_t quan_event_init_button(quan_event_button_t *button,
                                         uint64_t debounce_ms);
/* Task-context sample of logical pressed state at monotonically increasing
 * milliseconds. Sets press_edge only after stable released -> pressed.
 * Repeated hold never emits more edges. CLOCK_REVERSED preserves state and
 * sets edge false; caller must reinitialize after clock reset. INVALID for
 * null/uninitialized config. No borrowed pointer survives this call. */
quan_event_status_t quan_event_sample_button(quan_event_button_t *button,
                                           bool pressed, uint64_t now_ms,
                                           bool *press_edge);

#endif
