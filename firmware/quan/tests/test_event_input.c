#include "event_input.h"
#include <assert.h>
#include <stdio.h>

static void event_input_test_queue_boundaries(void)
{
    event_input_t storage[2];
    event_input_queue_t queue = {0};
    event_input_t event = {.sequence = 1, .created_ms = 17};
    event_input_t out = {.sequence = 99};
    assert(event_input_init_queue(NULL, storage, 2) == EVENT_INPUT_INVALID);
    assert(event_input_init_queue(&queue, NULL, 2) == EVENT_INPUT_INVALID);
    assert(event_input_init_queue(&queue, storage, 0) == EVENT_INPUT_INVALID);
    assert(event_input_init_queue(&queue, storage, SIZE_MAX) == EVENT_INPUT_INVALID);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_INVALID);
    assert(event_input_init_queue(&queue, storage, 2) == EVENT_INPUT_OK);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_EMPTY);
    assert(out.sequence == 99);
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_OK);
    event.sequence = 2;
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_OK);
    event.sequence = 3;
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_FULL);
    assert(queue.dropped == 1);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_OK && out.sequence == 1);
    assert(out.created_ms == 17);
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_OK);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_OK && out.sequence == 2);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_OK && out.sequence == 3);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_EMPTY);
    assert(event_input_push_event(&queue, NULL) == EVENT_INPUT_INVALID);
    assert(event_input_pop_event(&queue, NULL) == EVENT_INPUT_INVALID);
    queue.head = queue.capacity;
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_INVALID);
    assert(event_input_init_queue(&queue, storage, 1) == EVENT_INPUT_OK);
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_OK);
    queue.dropped = UINT32_MAX;
    assert(event_input_push_event(&queue, &event) == EVENT_INPUT_FULL);
    assert(queue.dropped == UINT32_MAX);
    assert(event_input_pop_event(&queue, &out) == EVENT_INPUT_OK);
    assert(queue.head == 0);
}

static void event_input_test_button_edges(void)
{
    event_input_button_t button = {0};
    bool edge = true;
    assert(event_input_init_button(NULL, 10) == EVENT_INPUT_INVALID);
    assert(event_input_init_button(&button, 0) == EVENT_INPUT_INVALID);
    assert(event_input_sample_button(&button, false, 0, &edge) == EVENT_INPUT_INVALID);
    assert(!edge);
    assert(event_input_init_button(&button, 10) == EVENT_INPUT_OK);
    assert(event_input_sample_button(&button, true, 0, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, 100, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, false, 101, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, false, 111, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, 120, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, false, 125, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, 126, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, 135, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, 136, &edge) == EVENT_INPUT_OK && edge);
    assert(event_input_sample_button(&button, true, 200, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, false, 199, &edge) == EVENT_INPUT_CLOCK_REVERSED && !edge);
    assert(button.last_sample_ms == 200 && button.stable_pressed);
    assert(event_input_sample_button(&button, false, 201, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, false, 211, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, UINT64_MAX - 10, &edge) == EVENT_INPUT_OK && !edge);
    assert(event_input_sample_button(&button, true, UINT64_MAX, &edge) == EVENT_INPUT_OK && edge);
    assert(event_input_sample_button(&button, true, 0, NULL) == EVENT_INPUT_INVALID);
}

int main(void)
{
    event_input_test_queue_boundaries();
    event_input_test_button_edges();
    puts("PASS: queue boundaries/FIFO/overflow; debounce/bounce/hold/clock boundaries");
    return 0;
}
