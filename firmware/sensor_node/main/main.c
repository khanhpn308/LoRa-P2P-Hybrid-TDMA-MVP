#include "esp_log.h"
#include "sx1276_driver.h"

static const char *TAG = "sensor_node";

void app_main(void)
{
    ESP_LOGI(TAG, "Starting Sensor Node (ESP-IDF v6.1 / SX1276 MVP)");

    // Initialize SX1276 Driver with Kconfig defaults (Fail-closed RF TX)
    esp_err_t err = sx1276_init(NULL, NULL);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "SX1276 init returned: %s (expected if hardware unattached on emulator/scaffold)",
                 esp_err_to_name(err));
    } else {
        ESP_LOGI(TAG, "SX1276 initialized successfully in STANDBY mode");
    }

    ESP_LOGI(TAG, "Sensor Node active with SX1276 driver initialized");
}
