#include "button_driver.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"

static const char *TAG = "button_driver";

// Pins reserved by SX1276 HW-001 pinmap (pcb-hw001-pinmap.md)
static const int s_reserved_sx1276_pins[] = {5, 18, 19, 23, 26, 27};
#define NUM_RESERVED_PINS (sizeof(s_reserved_sx1276_pins) / sizeof(s_reserved_sx1276_pins[0]))

static bool is_pin_reserved(gpio_num_t pin)
{
    for (size_t i = 0; i < NUM_RESERVED_PINS; i++) {
        if ((int)pin == s_reserved_sx1276_pins[i]) {
            return true;
        }
    }
    // UART console pins
    if (pin == GPIO_NUM_1 || pin == GPIO_NUM_3) {
        return true;
    }
    return false;
}

static bool is_rtc_gpio(gpio_num_t pin)
{
    // On ESP32, RTC GPIOs are: 0, 2, 4, 12, 13, 14, 15, 25, 26, 27, 32, 33, 34, 35, 36, 37, 38, 39
    switch (pin) {
        case GPIO_NUM_0:
        case GPIO_NUM_2:
        case GPIO_NUM_4:
        case GPIO_NUM_12:
        case GPIO_NUM_13:
        case GPIO_NUM_14:
        case GPIO_NUM_15:
        case GPIO_NUM_25:
        case GPIO_NUM_26:
        case GPIO_NUM_27:
        case GPIO_NUM_32:
        case GPIO_NUM_33:
        case GPIO_NUM_34:
        case GPIO_NUM_35:
        case GPIO_NUM_36:
        case GPIO_NUM_37:
        case GPIO_NUM_38:
        case GPIO_NUM_39:
            return true;
        default:
            return false;
    }
}

esp_err_t button_driver_init(button_driver_t *driver, const button_config_t *config)
{
    if (driver == NULL || config == NULL) {
        ESP_LOGE(TAG, "Invalid argument: driver or config is NULL");
        return ESP_ERR_INVALID_ARG;
    }

    if (is_pin_reserved(config->gpio_num)) {
        ESP_LOGE(TAG, "GPIO %d conflicts with SX1276 HW-001 or UART console! Rejected.", config->gpio_num);
        return ESP_ERR_INVALID_ARG;
    }

    if (!is_rtc_gpio(config->gpio_num)) {
        ESP_LOGE(TAG, "GPIO %d is NOT an RTC GPIO! Deep-Sleep EXT0 wake requires RTC GPIO.", config->gpio_num);
        return ESP_ERR_INVALID_ARG;
    }

    driver->config = *config;
    driver->is_initialized = true;

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << config->gpio_num),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = (config->active_level == 0 && config->gpio_num < GPIO_NUM_34) ? GPIO_PULLUP_ENABLE : GPIO_PULLUP_DISABLE,
        .pull_down_en = (config->active_level == 1 && config->gpio_num < GPIO_NUM_34) ? GPIO_PULLDOWN_ENABLE : GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };

    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to configure GPIO %d: %s", config->gpio_num, esp_err_to_name(err));
        driver->is_initialized = false;
        return err;
    }

    if (config->gpio_num >= GPIO_NUM_34) {
        ESP_LOGW(TAG, "GPIO %d is input-only without internal pull resistors. External resistor required.", config->gpio_num);
    }

    ESP_LOGI(TAG, "Button driver initialized on GPIO %d (Active Level: %d, Debounce: %" PRIu32 " ms)",
             config->gpio_num, config->active_level, config->debounce_ms);
    return ESP_OK;
}

button_wakeup_cause_t button_driver_get_wakeup_cause(void)
{
    uint32_t causes = esp_sleep_get_wakeup_causes();
    if (causes & (BIT(ESP_SLEEP_WAKEUP_EXT0) | BIT(ESP_SLEEP_WAKEUP_EXT1) | BIT(ESP_SLEEP_WAKEUP_GPIO))) {
        return BUTTON_CAUSE_EXT0_BUTTON;
    }
    if (causes & BIT(ESP_SLEEP_WAKEUP_TIMER)) {
        return BUTTON_CAUSE_TIMER;
    }
    return BUTTON_CAUSE_RESET_OR_OTHER;
}

esp_err_t button_driver_qualify_press(button_driver_t *driver, bool *out_qualified)
{
    if (driver == NULL || out_qualified == NULL || !driver->is_initialized) {
        return ESP_ERR_INVALID_ARG;
    }

    *out_qualified = false;
    const gpio_num_t pin = driver->config.gpio_num;
    const int active_lvl = driver->config.active_level;
    const uint32_t debounce_ms = driver->config.debounce_ms;

    // Check immediate level
    int current_level = gpio_get_level(pin);
    if (current_level != active_lvl) {
        ESP_LOGW(TAG, "Button not asserted at wake inspection (level=%d, expected=%d): transient noise pulse",
                 current_level, active_lvl);
        return ESP_OK;
    }

    // Debounce sampling: sample across debounce_ms in slices of 5ms
    uint32_t step_ms = 5;
    uint32_t elapsed_ms = 0;
    while (elapsed_ms < debounce_ms) {
        vTaskDelay(pdMS_TO_TICKS(step_ms));
        elapsed_ms += step_ms;
        if (gpio_get_level(pin) != active_lvl) {
            ESP_LOGW(TAG, "Button bounced inactive after %" PRIu32 " ms: rejected", elapsed_ms);
            return ESP_OK;
        }
    }

    // Button remained steadily asserted throughout debounce window
    *out_qualified = true;
    ESP_LOGI(TAG, "Button press verified: stable asserted level for %" PRIu32 " ms", elapsed_ms);

    // Release and re-arm handling: wait for release or maximum hold limit to prevent re-sleep immediate wake loop
    uint32_t hold_timeout_ms = 3000; // max 3 seconds wait for release
    uint32_t hold_elapsed_ms = 0;
    while (gpio_get_level(pin) == active_lvl && hold_elapsed_ms < hold_timeout_ms) {
        vTaskDelay(pdMS_TO_TICKS(20));
        hold_elapsed_ms += 20;
    }

    if (hold_elapsed_ms >= hold_timeout_ms) {
        ESP_LOGW(TAG, "Button stuck/held down > %" PRIu32 " ms. Continuing with 1 qualified event.", hold_timeout_ms);
    } else {
        ESP_LOGI(TAG, "Button released after %" PRIu32 " ms. Re-armed.", hold_elapsed_ms);
        vTaskDelay(pdMS_TO_TICKS(10)); // small release settling delay
    }

    return ESP_OK;
}

esp_err_t button_driver_arm_sleep(button_driver_t *driver)
{
    if (driver == NULL || !driver->is_initialized) {
        return ESP_ERR_INVALID_ARG;
    }

    // If button is currently still held, wait for release to avoid immediate wake storm
    int retry = 0;
    while (gpio_get_level(driver->config.gpio_num) == driver->config.active_level && retry < 50) {
        vTaskDelay(pdMS_TO_TICKS(20));
        retry++;
    }

    esp_err_t err = esp_sleep_enable_ext0_wakeup(driver->config.gpio_num, driver->config.active_level);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to arm EXT0 wakeup on GPIO %d: %s", driver->config.gpio_num, esp_err_to_name(err));
        return err;
    }

    ESP_LOGI(TAG, "Armed Deep-Sleep EXT0 wakeup on GPIO %d (Trigger Level: %d)",
             driver->config.gpio_num, driver->config.active_level);
    return ESP_OK;
}
