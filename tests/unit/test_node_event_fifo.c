/**
 * @file test_node_event_fifo.c
 * @brief Unit tests for Node Persistent Event FIFO and Bounded Buffer Policy.
 *
 * Authority: C Coding Standard v2, Issue #131, DEC-127-04.
 * Policy: Capacity 16, RING_BUFFER_DROP_OLDEST on overflow, observable dropped_event_count.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>

#include "node_event_fifo.h"

#define TEST_RUN(name) do { \
    printf("Running %s ... ", #name); \
    if (name() == 0) { \
        printf("PASSED\n"); \
    } else { \
        printf("FAILED\n"); \
        failures++; \
    } \
} while (0)

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "\nAssertion failed: %s at %s:%d\n", #cond, __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_INT(expected, actual) do { \
    if ((int)(expected) != (int)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %d, got %d) at %s:%d\n", \
                #expected, #actual, (int)(expected), (int)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_U32(expected, actual) do { \
    if ((uint32_t)(expected) != (uint32_t)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %u, got %u) at %s:%d\n", \
                #expected, #actual, (uint32_t)(expected), (uint32_t)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

static int test_fifo_init(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 5U, 100U));
    ASSERT_EQUAL_U32(5U, node_event_fifo_get_dropped_count(&fifo));
    ASSERT_EQUAL_INT(0, (int)node_event_fifo_get_pending_count(&fifo));

    /* NULL check */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_event_fifo_init(NULL, 0, 0));

    return 0;
}

static int test_fifo_push_and_peek(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));

    uint32_t ref1 = 0, ref2 = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 1000, 1, 250, &ref1));
    ASSERT_EQUAL_U32(1U, ref1);
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 1005, 2, 300, &ref2));
    ASSERT_EQUAL_U32(2U, ref2);
    ASSERT_EQUAL_INT(2, (int)node_event_fifo_get_pending_count(&fifo));

    node_event_fifo_item_t peek_item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &peek_item));
    ASSERT_EQUAL_U32(ref1, peek_item.event_ref);
    ASSERT_EQUAL_U32(1000U, peek_item.event_time);
    ASSERT_EQUAL_INT(1, peek_item.event_code);
    ASSERT_EQUAL_INT(250, peek_item.event_value);
    ASSERT_EQUAL_INT(0, peek_item.retry_count);
    ASSERT_TRUE(!peek_item.acked);

    return 0;
}

static int test_fifo_ack_in_order(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));

    uint32_t ref1 = 0, ref2 = 0;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 1000, 1, 100, &ref1));
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, 1010, 2, 200, &ref2));
    ASSERT_EQUAL_INT(2, (int)node_event_fifo_get_pending_count(&fifo));

    /* ACK first event */
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_ack(&fifo, ref1));
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    /* Peek should now return ref2 */
    node_event_fifo_item_t item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_U32(ref2, item.event_ref);

    /* ACK second event */
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_ack(&fifo, ref2));
    ASSERT_EQUAL_INT(0, (int)node_event_fifo_get_pending_count(&fifo));
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, node_event_fifo_peek_pending(&fifo, &item));

    return 0;
}

static int test_fifo_ack_out_of_order(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 10));

    uint32_t ref1 = 0, ref2 = 0, ref3 = 0;
    (void)node_event_fifo_push(&fifo, 100, 1, 10, &ref1);
    (void)node_event_fifo_push(&fifo, 200, 2, 20, &ref2);
    (void)node_event_fifo_push(&fifo, 300, 3, 30, &ref3);
    ASSERT_EQUAL_INT(3, (int)node_event_fifo_get_pending_count(&fifo));

    /* ACK ref2 out of order (e.g. retransmit received ack) */
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_ack(&fifo, ref2));
    ASSERT_EQUAL_INT(2, (int)node_event_fifo_get_pending_count(&fifo));

    /* Peek should still return ref1 */
    node_event_fifo_item_t item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_U32(ref1, item.event_ref);

    /* Now ACK ref1: head should cascade past ref1 and ref2, leaving ref3 */
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_ack(&fifo, ref1));
    ASSERT_EQUAL_INT(1, (int)node_event_fifo_get_pending_count(&fifo));

    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_U32(ref3, item.event_ref);

    return 0;
}

static int test_fifo_overflow_drop_oldest(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));

    uint32_t refs[NODE_EVENT_FIFO_CAPACITY + 5];

    for (size_t i = 0; i < NODE_EVENT_FIFO_CAPACITY + 5; i++) {
        ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_push(&fifo, (uint32_t)(1000 + i), 1, (int16_t)i, &refs[i]));
    }

    /* We pushed 16 + 5 = 21 items. Dropped count must be 5 (DEC-127-04) */
    ASSERT_EQUAL_U32(5U, node_event_fifo_get_dropped_count(&fifo));
    ASSERT_EQUAL_INT(NODE_EVENT_FIFO_CAPACITY, (int)node_event_fifo_get_pending_count(&fifo));

    /* The oldest remaining item should be index 5 */
    node_event_fifo_item_t item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_U32(refs[5], item.event_ref);
    ASSERT_EQUAL_INT(5, item.event_value);

    return 0;
}

static int test_fifo_retry_count(void)
{
    node_event_fifo_t fifo;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_init(&fifo, 0, 1));

    uint32_t ref = 0;
    (void)node_event_fifo_push(&fifo, 1000, 1, 100, &ref);

    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_record_retry(&fifo, ref));
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_record_retry(&fifo, ref));

    node_event_fifo_item_t item;
    ASSERT_EQUAL_INT(ESP_OK, node_event_fifo_peek_pending(&fifo, &item));
    ASSERT_EQUAL_INT(2, item.retry_count);

    /* Unknown ref */
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, node_event_fifo_record_retry(&fifo, 999U));

    return 0;
}

static int test_fifo_negative_and_bounds(void)
{
    node_event_fifo_item_t item;
    node_event_fifo_t fifo;
    (void)node_event_fifo_init(&fifo, 0, 1);

    /* Peek empty */
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, node_event_fifo_peek_pending(&fifo, &item));

    /* Ack empty */
    ASSERT_EQUAL_INT(ESP_ERR_NOT_FOUND, node_event_fifo_ack(&fifo, 1U));

    /* NULL args */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_event_fifo_peek_pending(NULL, &item));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_event_fifo_peek_pending(&fifo, NULL));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, node_event_fifo_push(NULL, 1, 1, 1, NULL));

    return 0;
}

int main(void)
{
    int failures = 0;
    printf("--- Node Event FIFO Unit Tests ---\n");

    TEST_RUN(test_fifo_init);
    TEST_RUN(test_fifo_push_and_peek);
    TEST_RUN(test_fifo_ack_in_order);
    TEST_RUN(test_fifo_ack_out_of_order);
    TEST_RUN(test_fifo_overflow_drop_oldest);
    TEST_RUN(test_fifo_retry_count);
    TEST_RUN(test_fifo_negative_and_bounds);

    if (failures == 0) {
        printf("All Node Event FIFO unit tests PASSED successfully!\n");
        return 0;
    }

    fprintf(stderr, "%d test(s) FAILED.\n", failures);
    return 1;
}

