#include "node_ui.h"
#include "sdkconfig.h"
#include "esp_err.h"
#include "esp_log.h"
#include "oled_ssd1306.h"

#if CONFIG_OLED_SSD1306_ENABLE
static const char *TAG = "sensor_node";
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
