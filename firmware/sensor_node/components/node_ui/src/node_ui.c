#include "node_ui.h"
#include "sdkconfig.h"
#include "esp_err.h"
#include "esp_log.h"
#include "oled_ssd1306.h"

#if CONFIG_NODE_ACK_LED_ENABLE
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

static const char *TAG = "node_ui";

#if CONFIG_NODE_ACK_LED_ENABLE
static bool is_pin_prohibited(gpio_num_t pin)
{
    /* Must be a valid output GPIO on ESP32 */
    if (!GPIO_IS_VALID_OUTPUT_GPIO(pin)) {
        return true;
    }
    /* Input-only pins on ESP32 (GPIO 34..39) */
    if (pin >= GPIO_NUM_34 && pin <= GPIO_NUM_39) {
        return true;
    }
    /* SPI flash pins (GPIO 6..11) */
    if (pin >= GPIO_NUM_6 && pin <= GPIO_NUM_11) {
        return true;
    }
    /* SX1276 HW-001 reserved radio pins: SCK(5), CS(18), MISO(19), RST(23), DIO0(26), MOSI(27) */
    if (pin == GPIO_NUM_5 || pin == GPIO_NUM_18 || pin == GPIO_NUM_19 ||
        pin == GPIO_NUM_23 || pin == GPIO_NUM_26 || pin == GPIO_NUM_27) {
        return true;
    }
    /* UART console pins: TX(1), RX(3) */
    if (pin == GPIO_NUM_1 || pin == GPIO_NUM_3) {
        return true;
    }
    /* Strapping pins: GPIO 0, 2, 15 (GPIO 12 is permitted for active-high ACK LED) */
    if (pin == GPIO_NUM_0 || pin == GPIO_NUM_2 || pin == GPIO_NUM_15) {
        return true;
    }
    /* Configured wakeup button GPIO */
#ifdef CONFIG_NODE_BUTTON_GPIO
    if (pin == (gpio_num_t)CONFIG_NODE_BUTTON_GPIO) {
        return true;
    }
#endif
    /* Configured OLED I2C pins if OLED is enabled */
#if CONFIG_OLED_SSD1306_ENABLE
    if (pin == (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SDA_GPIO ||
        pin == (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SCL_GPIO) {
        return true;
    }
#endif

    return false;
}
#endif

esp_err_t node_ui_show_unjoined(void)
{
#if CONFIG_OLED_SSD1306_ENABLE
    oled_ssd1306_dev_t oled_dev;
    oled_ssd1306_config_t oled_cfg;
    esp_err_t err = oled_ssd1306_get_default_config(&oled_cfg);
    if (err == ESP_OK) {
        oled_cfg.button_gpio = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO;
        err = oled_ssd1306_init(&oled_dev, &oled_cfg);
        if (err == ESP_OK) {
            (void)oled_ssd1306_clear(&oled_dev);
            (void)oled_ssd1306_draw_string(&oled_dev, 8, 2, "STATUS: UNJOINED");
            (void)oled_ssd1306_draw_string(&oled_dev, 8, 4, "NODE REVOKED");
            (void)oled_ssd1306_refresh(&oled_dev);
            (void)oled_ssd1306_deinit(&oled_dev);
        }
    }
    return err;
#else
    return ESP_OK;
#endif
}

esp_err_t node_ui_show_event(int16_t value, uint32_t rel_time_sec, uint32_t total_events)
{
#if CONFIG_OLED_SSD1306_ENABLE
    oled_ssd1306_dev_t oled_dev;
    oled_ssd1306_config_t oled_cfg;
    (void)oled_ssd1306_get_default_config(&oled_cfg);
    oled_cfg.button_gpio = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO;
    esp_err_t oled_err = oled_ssd1306_init(&oled_dev, &oled_cfg);
    if (oled_err == ESP_OK) {
        oled_err = oled_ssd1306_display_event(&oled_dev, value, rel_time_sec, total_events);
        if (oled_err != ESP_OK) {
            ESP_LOGW(TAG, "OLED display event failed: %s", esp_err_to_name(oled_err));
        }
        (void)oled_ssd1306_deinit(&oled_dev);
    } else {
        ESP_LOGW(TAG, "OLED init failed: %s (non-fatal, continuing event flow)", esp_err_to_name(oled_err));
    }
    return oled_err;
#else
    (void)value;
    (void)rel_time_sec;
    (void)total_events;
    return ESP_OK;
#endif
}

esp_err_t node_ui_blink_event_ack(void)
{
#if CONFIG_NODE_ACK_LED_ENABLE
    gpio_num_t pin = (gpio_num_t)CONFIG_NODE_ACK_LED_GPIO;
    if (is_pin_prohibited(pin)) {
        ESP_LOGE(TAG, "Configured ACK LED GPIO %d is prohibited or conflicts with reserved pins", (int)pin);
        return ESP_ERR_INVALID_ARG;
    }

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << pin),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&io_conf);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to configure ACK LED GPIO %d: %s", (int)pin, esp_err_to_name(err));
        return err;
    }

    /* Drive HIGH for pulse duration */
    (void)gpio_set_level(pin, 1);
    uint32_t pulse_ms = (uint32_t)CONFIG_NODE_ACK_LED_PULSE_MS;
    if (pulse_ms < 50U) {
        pulse_ms = 50U;
    } else if (pulse_ms > 1000U) {
        pulse_ms = 1000U;
    }
    vTaskDelay(pdMS_TO_TICKS(pulse_ms));

    /* Return to LOW before entering sleep */
    (void)gpio_set_level(pin, 0);
    return ESP_OK;
#else
    return ESP_OK;
#endif
}
