#include "node_arq.h"
#include "esp_random.h"
#include "esp_log.h"
#include "sx1276_driver.h"

static const char *TAG = "node_arq";

uint32_t node_calculate_arq_backoff_ms(void)
{
    if (NODE_ARQ_BACKOFF_MAX_MS <= NODE_ARQ_BACKOFF_MIN_MS) {
        return NODE_ARQ_BACKOFF_MIN_MS;
    }
    uint32_t range = NODE_ARQ_BACKOFF_MAX_MS - NODE_ARQ_BACKOFF_MIN_MS + 1U;
    return NODE_ARQ_BACKOFF_MIN_MS + (uint32_t)(esp_random() % range);
}

bool node_arq_should_retry(uint8_t tx_retries, uint8_t tx_max)
{
    return (tx_retries < tx_max);
}

esp_err_t node_reset_sx1276_fifo_tx_ptr(void)
{
    esp_err_t err = sx1276_standby();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to transition to STANDBY for FIFO reset: %s", esp_err_to_name(err));
        return err;
    }
    ESP_LOGI(TAG, "SX1276 FIFO pointer reset ready (FifoTxBaseAddr = 0x%02X)", SX1276_REG_FIFO_TX_BASE_ADDR);
    return ESP_OK;
}
