#include "tdma_common.h"
#include "esp_log.h"

static const char *TAG = "tdma_common";

esp_err_t tdma_common_init(void)
{
    ESP_LOGI(TAG, "Initialized shared tdma_common component (Profile P-10S-15 baseline)");
    return ESP_OK;
}

bool tdma_is_valid_slot_id(uint8_t slot_id)
{
    return (slot_id >= 1U && slot_id <= TDMA_TOTAL_DATA_SLOTS);
}

esp_err_t tdma_get_slot_start_offset_ms(uint8_t slot_id, uint32_t *out_offset_ms)
{
    if (!tdma_is_valid_slot_id(slot_id) || out_offset_ms == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t zero_indexed = (uint32_t)(slot_id - 1U);
    uint32_t subframe_idx = zero_indexed / TDMA_DATA_SLOTS_PER_SUBFRAME;
    uint32_t slot_in_subframe = zero_indexed % TDMA_DATA_SLOTS_PER_SUBFRAME;

    uint32_t offset = (subframe_idx * TDMA_SUBFRAME_MS) +
                      TDMA_DATA_SECTION_START_MS +
                      (slot_in_subframe * TDMA_SLOT_DURATION_MS);

    *out_offset_ms = offset;
    return ESP_OK;
}

uint32_t tdma_calculate_drift_guard_ms(uint32_t clock_drift_ppm, uint32_t interval_s)
{
    /* Bilateral clock drift in microseconds: 2 * drift_ppm * interval_s */
    uint32_t drift_us = 2U * clock_drift_ppm * interval_s;
    uint32_t drift_ms = (drift_us + 999U) / 1000U;

    /* Add minimum 5 ms base safety guard */
    return (drift_ms + 5U);
}
