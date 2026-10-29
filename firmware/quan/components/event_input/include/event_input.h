#ifndef EVENT_INPUT_H
#define EVENT_INPUT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Local application data only: never serialize this struct as an RF frame.
 * sequence is process-local, not a durable identity or replay counter. */
typedef struct {
    uint32_t sequence;
    uint64_t created_ms;
} event_input_t;

typedef enum {
    EVENT_INPUT_OK = 0,
    EVENT_INPUT_INVALID,
    EVENT_INPUT_FULL,
    EVENT_INPUT_EMPTY,
    EVENT_INPUT_CLOCK_REVERSED
} event_input_status_t;

/* Caller-owned storage; exactly one task owns each object. No ISR use,
 * synchronization, allocation or asynchronous retained event pointers. */
typedef struct {
    event_input_t *storage;
    size_t capacity;
    size_t head;
    size_t count;
    uint32_t dropped;
} event_input_queue_t;

typedef struct {
    bool initialized;
    bool candidate_pressed;
    bool stable_pressed;
    uint64_t candidate_since_ms;
    uint64_t last_sample_ms;
    uint64_t debounce_ms;
} event_input_button_t;

/* storage must remain valid and unmodified for queue lifetime, with capacity
 * elements (capacity > 0). Reset is permitted only with no users pending.
 * Returns INVALID for null pointers/zero capacity/size overflow. */
event_input_status_t event_input_init_queue(event_input_queue_t *queue,
                                        event_input_t *storage, size_t capacity);
/* Copies one event. FULL drops newest and saturates dropped at UINT32_MAX.
 * INVALID for null/invalid state. Event pointer is borrowed only until return. */
event_input_status_t event_input_push_event(event_input_queue_t *queue,
                                        const event_input_t *event);
/* Copies/removes oldest event; EMPTY leaves output unchanged. INVALID on null
 * or invalid state. Output belongs to caller and has no queue lifetime tie. */
event_input_status_t event_input_pop_event(event_input_queue_t *queue,
                                       event_input_t *event);
/* Configurable nonzero debounce in ms; no platform/pin defaults. INVALID on
 * null or zero debounce. Initializes released; first sample establishes
 * baseline, so a button held at startup does not create an event. */
event_input_status_t event_input_init_button(event_input_button_t *button,
                                         uint64_t debounce_ms);
/* Task-context sample of logical pressed state at monotonically increasing
 * milliseconds. Sets press_edge only after stable released -> pressed.
 * Repeated hold never emits more edges. CLOCK_REVERSED preserves state and
 * sets edge false; caller must reinitialize after clock reset. INVALID for
 * null/uninitialized config. No borrowed pointer survives this call. */
event_input_status_t event_input_sample_button(event_input_button_t *button,
                                           bool pressed, uint64_t now_ms,
                                           bool *press_edge);

#endif
