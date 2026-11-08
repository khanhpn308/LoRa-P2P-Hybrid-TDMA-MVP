#include "gateway_wal.h"
#include <string.h>

esp_err_t gateway_wal_init(gateway_wal_t *wal)
{
    if (wal == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    (void)memset(wal, 0, sizeof(*wal));
    return ESP_OK;
}

esp_err_t gateway_wal_push(gateway_wal_t *wal, const gateway_wal_event_t *event)
{
    if (wal == NULL || event == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (wal->count == GATEWAY_WAL_CAPACITY) {
        /* Buffer is full: apply DROP_OLDEST policy per DEC-127-04 / D12 §6.3 */
        wal->tail = (wal->tail + 1U) % GATEWAY_WAL_CAPACITY;
        wal->overflow_dropped_count++;
        /* wal->count remains at GATEWAY_WAL_CAPACITY */
    } else {
        wal->count++;
    }

    wal->entries[wal->head] = *event;
    wal->head = (wal->head + 1U) % GATEWAY_WAL_CAPACITY;

    return ESP_OK;
}

esp_err_t gateway_wal_pop(gateway_wal_t *wal, gateway_wal_event_t *out_event)
{
    if (wal == NULL || out_event == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (wal->count == 0U) {
        return ESP_ERR_NOT_FOUND;
    }

    *out_event = wal->entries[wal->tail];
    (void)memset(&wal->entries[wal->tail], 0, sizeof(gateway_wal_event_t));

    wal->tail = (wal->tail + 1U) % GATEWAY_WAL_CAPACITY;
    wal->count--;

    return ESP_OK;
}

esp_err_t gateway_wal_peek(const gateway_wal_t *wal, gateway_wal_event_t *out_event)
{
    if (wal == NULL || out_event == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (wal->count == 0U) {
        return ESP_ERR_NOT_FOUND;
    }

    *out_event = wal->entries[wal->tail];
    return ESP_OK;
}

size_t gateway_wal_count(const gateway_wal_t *wal)
{
    if (wal == NULL) {
        return 0U;
    }
    return wal->count;
}

uint32_t gateway_wal_get_dropped_count(const gateway_wal_t *wal)
{
    if (wal == NULL) {
        return 0U;
    }
    return wal->overflow_dropped_count;
}

bool gateway_wal_is_full(const gateway_wal_t *wal)
{
    if (wal == NULL) {
        return false;
    }
    return (wal->count >= GATEWAY_WAL_CAPACITY);
}

void gateway_wal_clear(gateway_wal_t *wal)
{
    if (wal != NULL) {
        (void)memset(wal, 0, sizeof(*wal));
    }
}
