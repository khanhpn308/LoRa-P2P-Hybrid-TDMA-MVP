#include "airtime_policy.h"
#include "esp_log.h"

static const char *TAG = "airtime_policy";

/* Bounded static state; zero dynamic allocation */
static uint16_t s_max_permille = AIRTIME_POLICY_DEFAULT_PERMILLE;
static uint32_t s_max_allowed_budget_ms = (AIRTIME_POLICY_WINDOW_MS * AIRTIME_POLICY_DEFAULT_PERMILLE) / 1000U;
static uint32_t s_accumulated_tx_ms = 0;

esp_err_t airtime_policy_init(uint16_t max_permille)
{
    if (max_permille == 0 || max_permille > 1000U) {
        return ESP_ERR_INVALID_ARG;
    }

    s_max_permille = max_permille;
    s_max_allowed_budget_ms = (uint32_t)(((uint64_t)AIRTIME_POLICY_WINDOW_MS * max_permille) / 1000U);
    s_accumulated_tx_ms = 0;

    ESP_LOGI(TAG, "Initialized airtime_policy: limit=%u permille (%lu ms per 1h window)",
             s_max_permille, (unsigned long)s_max_allowed_budget_ms);
    return ESP_OK;
}

esp_err_t airtime_policy_check(uint32_t packet_toa_ms)
{
    if (packet_toa_ms == 0) {
        return ESP_OK;
    }

    uint64_t projected = (uint64_t)s_accumulated_tx_ms + packet_toa_ms;
    if (projected > s_max_allowed_budget_ms) {
        ESP_LOGW(TAG, "TX DENIED by airtime policy: projected %llu ms > budget %lu ms (accumulated %lu ms)",
                 (unsigned long long)projected,
                 (unsigned long)s_max_allowed_budget_ms,
                 (unsigned long)s_accumulated_tx_ms);
        return ESP_ERR_INVALID_STATE;
    }

    return ESP_OK;
}

esp_err_t airtime_policy_record_tx(uint32_t packet_toa_ms)
{
    if (packet_toa_ms == 0) {
        return ESP_OK;
    }

    uint64_t sum = (uint64_t)s_accumulated_tx_ms + packet_toa_ms;
    if (sum > (uint64_t)UINT32_MAX) {
        s_accumulated_tx_ms = UINT32_MAX;
    } else {
        s_accumulated_tx_ms = (uint32_t)sum;
    }

    ESP_LOGD(TAG, "Recorded TX: +%lu ms -> total %lu/%lu ms",
             (unsigned long)packet_toa_ms,
             (unsigned long)s_accumulated_tx_ms,
             (unsigned long)s_max_allowed_budget_ms);
    return ESP_OK;
}

uint32_t airtime_policy_get_remaining_budget_ms(void)
{
    if (s_accumulated_tx_ms >= s_max_allowed_budget_ms) {
        return 0;
    }
    return (s_max_allowed_budget_ms - s_accumulated_tx_ms);
}

uint32_t airtime_policy_get_accumulated_tx_ms(void)
{
    return s_accumulated_tx_ms;
}

void airtime_policy_reset(void)
{
    s_accumulated_tx_ms = 0;
    ESP_LOGI(TAG, "Airtime policy budget reset");
}
