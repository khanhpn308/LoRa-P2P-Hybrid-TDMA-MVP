#include "event_input.h"

static bool event_input_is_queue_valid(const event_input_queue_t *queue)
{
    return queue != NULL && queue->storage != NULL && queue->capacity > 0 &&
           queue->capacity <= SIZE_MAX / sizeof(event_input_t) &&
           queue->head < queue->capacity && queue->count <= queue->capacity;
}

event_input_status_t event_input_init_queue(event_input_queue_t *queue,
                                        event_input_t *storage, size_t capacity)
{
    if (queue == NULL || storage == NULL || capacity == 0 ||
        capacity > SIZE_MAX / sizeof(event_input_t)) {
        return EVENT_INPUT_INVALID;
    }
    *queue = (event_input_queue_t){.storage = storage, .capacity = capacity};
    return EVENT_INPUT_OK;
}

event_input_status_t event_input_push_event(event_input_queue_t *queue,
                                        const event_input_t *event)
{
    size_t tail;
    if (!event_input_is_queue_valid(queue) || event == NULL) {
        return EVENT_INPUT_INVALID;
    }
    if (queue->count == queue->capacity) {
        if (queue->dropped < UINT32_MAX) {
            ++queue->dropped;
        }
        return EVENT_INPUT_FULL;
    }
    /* Avoid overflow of head + count even for caller-supplied capacities. */
    tail = queue->count >= queue->capacity - queue->head
               ? queue->count - (queue->capacity - queue->head)
               : queue->head + queue->count;
    queue->storage[tail] = *event;
    ++queue->count;
    return EVENT_INPUT_OK;
}

event_input_status_t event_input_pop_event(event_input_queue_t *queue,
                                       event_input_t *event)
{
    if (!event_input_is_queue_valid(queue) || event == NULL) {
        return EVENT_INPUT_INVALID;
    }
    if (queue->count == 0) {
        return EVENT_INPUT_EMPTY;
    }
    *event = queue->storage[queue->head];
    queue->head = queue->head == queue->capacity - 1 ? 0 : queue->head + 1;
    --queue->count;
    return EVENT_INPUT_OK;
}

event_input_status_t event_input_init_button(event_input_button_t *button,
                                         uint64_t debounce_ms)
{
    if (button == NULL || debounce_ms == 0) {
        return EVENT_INPUT_INVALID;
    }
    *button = (event_input_button_t){.debounce_ms = debounce_ms};
    return EVENT_INPUT_OK;
}

event_input_status_t event_input_sample_button(event_input_button_t *button,
                                           bool pressed, uint64_t now_ms,
                                           bool *press_edge)
{
    if (press_edge == NULL) {
        return EVENT_INPUT_INVALID;
    }
    *press_edge = false;
    if (button == NULL || button->debounce_ms == 0) {
        return EVENT_INPUT_INVALID;
    }
    if (!button->initialized) {
        button->initialized = true;
        button->candidate_pressed = pressed;
        button->stable_pressed = pressed;
        button->candidate_since_ms = now_ms;
        button->last_sample_ms = now_ms;
        return EVENT_INPUT_OK;
    }
    if (now_ms < button->last_sample_ms) {
        return EVENT_INPUT_CLOCK_REVERSED;
    }
    button->last_sample_ms = now_ms;
    if (pressed != button->candidate_pressed) {
        button->candidate_pressed = pressed;
        button->candidate_since_ms = now_ms;
    }
    if (pressed != button->stable_pressed &&
        now_ms - button->candidate_since_ms >= button->debounce_ms) {
        button->stable_pressed = pressed;
        *press_edge = pressed;
    }
    return EVENT_INPUT_OK;
}
