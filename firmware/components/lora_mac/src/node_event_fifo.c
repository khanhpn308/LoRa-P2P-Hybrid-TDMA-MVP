
#include "node_event_fifo.h"
#include <string.h>

esp_err_t node_event_fifo_init(node_event_fifo_t *fifo, uint32_t dropped_count, uint32_t next_ref) {
    if (!fifo) return ESP_ERR_INVALID_ARG;
    (void)memset(fifo, 0, sizeof(*fifo));
    fifo->dropped_event_count = dropped_count;
    fifo->next_event_ref = (next_ref == 0U) ? 1U : next_ref;
    return ESP_OK;
}
esp_err_t node_event_fifo_push(node_event_fifo_t *fifo, uint32_t event_time, uint8_t event_code, int16_t event_value, uint32_t *out_ref) {
    if (!fifo) return ESP_ERR_INVALID_ARG;
    uint32_t ref = fifo->next_event_ref++;
    if (fifo->next_event_ref == 0U) fifo->next_event_ref = 1U;
    if (fifo->count >= NODE_EVENT_FIFO_CAPACITY) {
        fifo->head = (fifo->head + 1U) % NODE_EVENT_FIFO_CAPACITY;
        fifo->dropped_event_count++;
    } else {
        fifo->count++;
    }
    node_event_fifo_item_t *slot = &fifo->items[fifo->tail];
    slot->event_ref = ref;
    slot->event_time = event_time;
    slot->event_code = event_code;
    slot->event_value = event_value;
    slot->retry_count = 0U;
    slot->acked = false;
    fifo->tail = (fifo->tail + 1U) % NODE_EVENT_FIFO_CAPACITY;
    if (out_ref) *out_ref = ref;
    return ESP_OK;
}
esp_err_t node_event_fifo_peek_pending(const node_event_fifo_t *fifo, node_event_fifo_item_t *out_item) {
    if (!fifo || !out_item) return ESP_ERR_INVALID_ARG;
    if (fifo->count == 0U) return ESP_ERR_NOT_FOUND;
    for (size_t i = 0; i < fifo->count; i++) {
        size_t idx = (fifo->head + i) % NODE_EVENT_FIFO_CAPACITY;
        if (!fifo->items[idx].acked) {
            *out_item = fifo->items[idx];
            return ESP_OK;
        }
    }
    return ESP_ERR_NOT_FOUND;
}
esp_err_t node_event_fifo_ack(node_event_fifo_t *fifo, uint32_t event_ref) {
    if (!fifo || fifo->count == 0U) return ESP_ERR_NOT_FOUND;
    bool found = false;
    for (size_t i = 0; i < fifo->count; i++) {
        size_t idx = (fifo->head + i) % NODE_EVENT_FIFO_CAPACITY;
        if (fifo->items[idx].event_ref == event_ref) {
            fifo->items[idx].acked = true;
            found = true;
            break;
        }
    }
    if (!found) return ESP_ERR_NOT_FOUND;
    while (fifo->count > 0U && fifo->items[fifo->head].acked) {
        fifo->head = (fifo->head + 1U) % NODE_EVENT_FIFO_CAPACITY;
        fifo->count--;
    }
    return ESP_OK;
}
esp_err_t node_event_fifo_record_retry(node_event_fifo_t *fifo, uint32_t event_ref) {
    if (!fifo || fifo->count == 0U) return ESP_ERR_NOT_FOUND;
    for (size_t i = 0; i < fifo->count; i++) {
        size_t idx = (fifo->head + i) % NODE_EVENT_FIFO_CAPACITY;
        if (fifo->items[idx].event_ref == event_ref) {
            if (fifo->items[idx].retry_count < 255U) fifo->items[idx].retry_count++;
            return ESP_OK;
        }
    }
    return ESP_ERR_NOT_FOUND;
}
size_t node_event_fifo_get_pending_count(const node_event_fifo_t *fifo) {
    if (!fifo || fifo->count == 0U) return 0U;
    size_t pending = 0U;
    for (size_t i = 0; i < fifo->count; i++) {
        size_t idx = (fifo->head + i) % NODE_EVENT_FIFO_CAPACITY;
        if (!fifo->items[idx].acked) pending++;
    }
    return pending;
}
uint32_t node_event_fifo_get_dropped_count(const node_event_fifo_t *fifo) {
    return fifo ? fifo->dropped_event_count : 0U;
}
