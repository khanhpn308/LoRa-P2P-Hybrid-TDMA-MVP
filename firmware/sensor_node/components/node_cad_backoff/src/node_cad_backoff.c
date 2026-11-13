#include "node_cad_backoff.h"
#include "esp_random.h"

uint32_t node_get_cad_contention_window_ms(uint8_t attempt)
{
    uint8_t k = (attempt == 0U) ? 1U : attempt;
    if (k > NODE_CAD_MAX_RETRIES) {
        k = NODE_CAD_MAX_RETRIES;
    }

    uint8_t shift = k - 1U;
    if (shift >= 16U) {
        return NODE_CAD_CW_MAX_MS;
    }

    uint32_t exp_cw = NODE_CAD_CW_MIN_MS << shift;
    return (exp_cw < NODE_CAD_CW_MAX_MS) ? exp_cw : NODE_CAD_CW_MAX_MS;
}

uint32_t node_calculate_cad_backoff_ms(uint8_t attempt)
{
    uint32_t cw_k = node_get_cad_contention_window_ms(attempt);
    return (uint32_t)(esp_random() % (cw_k + 1U));
}
