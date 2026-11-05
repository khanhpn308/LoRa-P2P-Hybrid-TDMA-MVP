/**
 * @file test_c_ring_buffer.c
 * @brief Host unit test runner for timing ring buffer and radio adapter safety gate.
 */

#include "timing_ring_buffer.h"
#include "radio_adapter_mock.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static void test_ring_buffer_basic(void)
{
    timing_ring_buffer_t rb;
    timing_ring_buffer_init(&rb);

    assert(timing_ring_buffer_count(&rb) == 0);
    assert(timing_ring_buffer_get_drops(&rb) == 0);

    timing_event_record_t rec1 = {
        .event_type = TIMING_EVT_TX_CMD,
        .timestamp_us = 1000000LL,
        .role = TIMING_ROLE_NODE,
        .payload_len = 24,
    };
    bool ok = timing_ring_buffer_push(&rb, &rec1);
    assert(ok);
    assert(timing_ring_buffer_count(&rb) == 1);

    timing_event_record_t popped;
    ok = timing_ring_buffer_pop(&rb, &popped);
    assert(ok);
    assert(popped.event_type == TIMING_EVT_TX_CMD);
    assert(popped.timestamp_us == 1000000LL);
    assert(popped.seq == 1);
    assert(timing_ring_buffer_count(&rb) == 0);

    /* Empty pop returns false */
    ok = timing_ring_buffer_pop(&rb, &popped);
    assert(!ok);
}

static void test_ring_buffer_overflow(void)
{
    timing_ring_buffer_t rb;
    timing_ring_buffer_init(&rb);

    /* Fill buffer to capacity - 1 */
    uint32_t capacity = TIMING_RING_BUFFER_CAPACITY;
    for (uint32_t i = 0; i < capacity - 1; i++) {
        timing_event_record_t rec = {
            .event_type = TIMING_EVT_DIO0_IRQ,
            .timestamp_us = (int64_t)(1000 + i),
        };
        bool ok = timing_ring_buffer_push(&rb, &rec);
        assert(ok);
    }
    assert(timing_ring_buffer_count(&rb) == capacity - 1);
    assert(timing_ring_buffer_get_drops(&rb) == 0);

    /* Attempt one more push -> should overflow and increment drop count */
    timing_event_record_t overflow_rec = {
        .event_type = TIMING_EVT_OVERFLOW,
        .timestamp_us = 999999LL,
    };
    bool ok = timing_ring_buffer_push(&rb, &overflow_rec);
    assert(!ok);
    assert(timing_ring_buffer_get_drops(&rb) == 1);

    /* ISR push when full also fails and increments drop count */
    ok = timing_ring_buffer_push_isr(&rb, TIMING_EVT_DIO0_IRQ, 1000000LL, 0);
    assert(!ok);
    assert(timing_ring_buffer_get_drops(&rb) == 2);
}

static void test_radio_safety_gate(void)
{
    timing_radio_config_t cfg = {
        .sf = 7,
        .bw_hz = 125000,
        .cr = 1,
        .rf_tx_enabled = false,      /* Disabled by default */
        .pa_path_verified = false,   /* Unverified fail-closed */
    };
    int err = timing_radio_init(&cfg);
    assert(err == 0);

    uint8_t dummy_payload[12] = {0};
    /* TX must be blocked fail-closed */
    int tx_res = timing_radio_tx(dummy_payload, sizeof(dummy_payload), 100);
    assert(tx_res == -100); /* TIMING_ERR_RF_TX_BLOCKED */
}

int main(void)
{
    printf("Running C firmware unit tests...\n");
    test_ring_buffer_basic();
    test_ring_buffer_overflow();
    test_radio_safety_gate();
    printf("All C firmware unit tests PASSED.\n");
    return 0;
}
