#include "quan_event.h"

static bool quan_event_is_queue_valid(const quan_event_queue_t *queue)
{
    return queue != NULL && queue->storage != NULL && queue->capacity > 0 &&
           queue->capacity <= SIZE_MAX / sizeof(quan_event_t) &&
           queue->head < queue->capacity && queue->count <= queue->capacity;
}

quan_event_status_t quan_event_init_queue(quan_event_queue_t *queue,
                                        quan_event_t *storage, size_t capacity)
{
    if (queue == NULL || storage == NULL || capacity == 0 ||
        capacity > SIZE_MAX / sizeof(quan_event_t)) {
        return QUAN_EVENT_INVALID;
    }
    *queue = (quan_event_queue_t){.storage = storage, .capacity = capacity};
    return QUAN_EVENT_OK;
}

quan_event_status_t quan_event_push_event(quan_event_queue_t *queue,
                                        const quan_event_t *event)
{
    size_t tail;
    if (!quan_event_is_queue_valid(queue) || event == NULL) {
        return QUAN_EVENT_INVALID;
    }
    if (queue->count == queue->capacity) {
        if (queue->dropped < UINT32_MAX) {
            ++queue->dropped;
        }
        return QUAN_EVENT_FULL;
    }
    /* Avoid overflow of head + count even for caller-supplied capacities. */
    tail = queue->count >= queue->capacity - queue->head
               ? queue->count - (queue->capacity - queue->head)
               : queue->head + queue->count;
    queue->storage[tail] = *event;
    ++queue->count;
    return QUAN_EVENT_OK;
}

quan_event_status_t quan_event_pop_event(quan_event_queue_t *queue,
                                       quan_event_t *event)
{
    if (!quan_event_is_queue_valid(queue) || event == NULL) {
        return QUAN_EVENT_INVALID;
    }
    if (queue->count == 0) {
        return QUAN_EVENT_EMPTY;
    }
    *event = queue->storage[queue->head];
    queue->head = queue->head == queue->capacity - 1 ? 0 : queue->head + 1;
    --queue->count;
    return QUAN_EVENT_OK;
}

quan_event_status_t quan_event_init_button(quan_event_button_t *button,
                                         uint64_t debounce_ms)
{
    if (button == NULL || debounce_ms == 0) {
        return QUAN_EVENT_INVALID;
    }
    *button = (quan_event_button_t){.debounce_ms = debounce_ms};
    return QUAN_EVENT_OK;
}

quan_event_status_t quan_event_sample_button(quan_event_button_t *button,
                                           bool pressed, uint64_t now_ms,
                                           bool *press_edge)
{
    if (press_edge == NULL) {
        return QUAN_EVENT_INVALID;
    }
    *press_edge = false;
    if (button == NULL || button->debounce_ms == 0) {
        return QUAN_EVENT_INVALID;
    }
    if (!button->initialized) {
        button->initialized = true;
        button->candidate_pressed = pressed;
        button->stable_pressed = pressed;
        button->candidate_since_ms = now_ms;
        button->last_sample_ms = now_ms;
        return QUAN_EVENT_OK;
    }
    if (now_ms < button->last_sample_ms) {
        return QUAN_EVENT_CLOCK_REVERSED;
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
    return QUAN_EVENT_OK;
}
