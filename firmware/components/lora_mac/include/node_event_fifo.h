
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#define NODE_EVENT_FIFO_CAPACITY 16U

typedef struct {
    uint32_t event_ref;
    uint32_t event_time;
    uint8_t event_code;
    int16_t event_value;
    uint8_t retry_count;
    bool acked;
} node_event_fifo_item_t;

typedef struct {
    node_event_fifo_item_t items[NODE_EVENT_FIFO_CAPACITY];
    size_t head;
    size_t tail;
    size_t count;
    uint32_t dropped_event_count;
    uint32_t next_event_ref;
} node_event_fifo_t;

esp_err_t node_event_fifo_init(node_event_fifo_t *fifo, uint32_t dropped_count, uint32_t next_ref);
esp_err_t node_event_fifo_push(node_event_fifo_t *fifo, uint32_t event_time, uint8_t event_code, int16_t event_value, uint32_t *out_ref);
esp_err_t node_event_fifo_peek_pending(const node_event_fifo_t *fifo, node_event_fifo_item_t *out_item);
esp_err_t node_event_fifo_ack(node_event_fifo_t *fifo, uint32_t event_ref);
esp_err_t node_event_fifo_record_retry(node_event_fifo_t *fifo, uint32_t event_ref);
size_t node_event_fifo_get_pending_count(const node_event_fifo_t *fifo);
uint32_t node_event_fifo_get_dropped_count(const node_event_fifo_t *fifo);
