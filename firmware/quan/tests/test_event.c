#include "quan_event.h"
#include <assert.h>
#include <stdio.h>

static void quan_test_queue_boundaries(void)
{
    quan_event_t storage[2];
    quan_event_queue_t queue = {0};
    quan_event_t event = {.sequence = 1, .created_ms = 17};
    quan_event_t out = {.sequence = 99};
    assert(quan_event_init_queue(NULL, storage, 2) == QUAN_EVENT_INVALID);
    assert(quan_event_init_queue(&queue, NULL, 2) == QUAN_EVENT_INVALID);
    assert(quan_event_init_queue(&queue, storage, 0) == QUAN_EVENT_INVALID);
    assert(quan_event_init_queue(&queue, storage, SIZE_MAX) == QUAN_EVENT_INVALID);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_INVALID);
    assert(quan_event_init_queue(&queue, storage, 2) == QUAN_EVENT_OK);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_EMPTY);
    assert(out.sequence == 99);
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_OK);
    event.sequence = 2;
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_OK);
    event.sequence = 3;
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_FULL);
    assert(queue.dropped == 1);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_OK && out.sequence == 1);
    assert(out.created_ms == 17);
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_OK);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_OK && out.sequence == 2);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_OK && out.sequence == 3);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_EMPTY);
    assert(quan_event_push_event(&queue, NULL) == QUAN_EVENT_INVALID);
    assert(quan_event_pop_event(&queue, NULL) == QUAN_EVENT_INVALID);
    queue.head = queue.capacity;
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_INVALID);
    assert(quan_event_init_queue(&queue, storage, 1) == QUAN_EVENT_OK);
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_OK);
    queue.dropped = UINT32_MAX;
    assert(quan_event_push_event(&queue, &event) == QUAN_EVENT_FULL);
    assert(queue.dropped == UINT32_MAX);
    assert(quan_event_pop_event(&queue, &out) == QUAN_EVENT_OK);
    assert(queue.head == 0);
}

static void quan_test_button_edges(void)
{
    quan_event_button_t button = {0};
    bool edge = true;
    assert(quan_event_init_button(NULL, 10) == QUAN_EVENT_INVALID);
    assert(quan_event_init_button(&button, 0) == QUAN_EVENT_INVALID);
    assert(quan_event_sample_button(&button, false, 0, &edge) == QUAN_EVENT_INVALID);
    assert(!edge);
    assert(quan_event_init_button(&button, 10) == QUAN_EVENT_OK);
    assert(quan_event_sample_button(&button, true, 0, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, 100, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, false, 101, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, false, 111, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, 120, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, false, 125, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, 126, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, 135, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, 136, &edge) == QUAN_EVENT_OK && edge);
    assert(quan_event_sample_button(&button, true, 200, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, false, 199, &edge) == QUAN_EVENT_CLOCK_REVERSED && !edge);
    assert(button.last_sample_ms == 200 && button.stable_pressed);
    assert(quan_event_sample_button(&button, false, 201, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, false, 211, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, UINT64_MAX - 10, &edge) == QUAN_EVENT_OK && !edge);
    assert(quan_event_sample_button(&button, true, UINT64_MAX, &edge) == QUAN_EVENT_OK && edge);
    assert(quan_event_sample_button(&button, true, 0, NULL) == QUAN_EVENT_INVALID);
}

int main(void)
{
    quan_test_queue_boundaries();
    quan_test_button_edges();
    puts("PASS: queue boundaries/FIFO/overflow; debounce/bounce/hold/clock boundaries");
    return 0;
}
