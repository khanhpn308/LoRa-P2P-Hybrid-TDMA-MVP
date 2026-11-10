#include "node_smart_backoff.h"

#include <inttypes.h>
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"

static const char *TAG = "smart_backoff";

#define NODE_SMART_BACKOFF_THRESHOLD_MS        10U
#define NODE_SMART_BACKOFF_WAKEUP_OVERHEAD_US  1500ULL

esp_err_t node_smart_backoff(uint32_t ms)
{
    if (ms == 0U) {
        return ESP_OK;
    }

    if (ms < NODE_SMART_BACKOFF_THRESHOLD_MS) {
        TickType_t ticks = pdMS_TO_TICKS(ms);
        vTaskDelay(ticks > 0U ? ticks : 1U);
        return ESP_OK;
    }

    /* Branch ms >= 10: Tiered Light-sleep with 1.5ms wakeup latency compensation */
    /* Ensure SX1276 radio is preserved in STANDBY mode (never SLEEP to retain FIFO contents) */
    esp_err_t radio_err = sx1276_standby();
    if (radio_err != ESP_OK && radio_err != ESP_ERR_INVALID_STATE) {
        ESP_LOGW(TAG, "sx1276_standby returned: %s", esp_err_to_name(radio_err));
    }

    uint64_t sleep_us = ((uint64_t)ms * 1000ULL) - NODE_SMART_BACKOFF_WAKEUP_OVERHEAD_US;

    esp_err_t err = esp_sleep_enable_timer_wakeup(sleep_us);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to enable timer wakeup: %s; falling back to vTaskDelay",
                 esp_err_to_name(err));
        TickType_t ticks = pdMS_TO_TICKS(ms);
        vTaskDelay(ticks > 0U ? ticks : 1U);
        return err;
    }

    ESP_LOGD(TAG, "Entering Light-sleep for %" PRIu64 " us (target=%" PRIu32 " ms)", sleep_us, ms);

    err = esp_light_sleep_start();
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_light_sleep_start returned: %s", esp_err_to_name(err));
    } else {
        uint32_t causes = esp_sleep_get_wakeup_causes();
        (void)causes;
        ESP_LOGD(TAG, "Woke up from Light-sleep (causes=0x%" PRIx32 ")", causes);
    }
    (void)TAG;

    return err;
}
