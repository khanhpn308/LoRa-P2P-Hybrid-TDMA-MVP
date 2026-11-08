/*
 * SPDX-License-Identifier: MIT
 *
 * SSD1306 0.96-inch OLED Display Component Implementation for ESP32 / ESP-IDF v6.1.
 * Authority: Issue #271, C Coding Standard v2 (GOV-001..010, C-001..020, MEM-001..008, ERR-001..007, RTOS-003).
 */

#include "oled_ssd1306.h"
#include "oled_font.h"
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
#include "esp_log.h"
#include "sdkconfig.h"

static const char *TAG = "oled_ssd1306";

/* Control bytes for SSD1306 I2C communication (Co = 0) */
#define SSD1306_I2C_CMD_STREAM  0x00U
#define SSD1306_I2C_DATA_STREAM 0x40U

/* Standard SSD1306 initialization command sequence (128x64 display) */
static const uint8_t SSD1306_INIT_CMDS[] = {
    0xAEU,        /* Display OFF (sleep mode) */
    0xD5U, 0x80U, /* Set display clock divide ratio / oscillator frequency */
    0xA8U, 0x3FU, /* Set multiplex ratio (64 MUX) */
    0xD3U, 0x00U, /* Set display offset (0 = no vertical shift) */
    0x40U,        /* Set display start line (line 0) */
    0x8DU, 0x14U, /* Enable internal DC-DC charge pump (7.5V) */
    0x20U, 0x02U, /* Set memory addressing mode: Page Addressing Mode */
    0xA1U,        /* Set segment re-map: column 127 is SEG0 */
    0xC8U,        /* Set COM output scan direction: remapped (COM63 to COM0) */
    0xDAU, 0x12U, /* Set COM pins hardware config: alternative configuration */
    0x81U, 0x7FU, /* Set contrast control: 0x7F */
    0xD9U, 0xF1U, /* Set pre-charge period: Phase 1=1 DCLK, Phase 2=15 DCLK */
    0xDBU, 0x40U, /* Set VCOMH deselect level: ~0.77 x VCC */
    0xA4U,        /* Entire display ON: output follows RAM content */
    0xA6U,        /* Set normal display mode: 1 = pixel ON, 0 = pixel OFF */
    0xAFU         /* Display ON in normal mode */
};

esp_err_t oled_ssd1306_get_default_config(oled_ssd1306_config_t *out_config)
{
    if (out_config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

#ifdef CONFIG_OLED_SSD1306_I2C_SDA_GPIO
    out_config->sda_gpio = (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SDA_GPIO;
#else
    out_config->sda_gpio = OLED_SSD1306_DEFAULT_SDA;
#endif

#ifdef CONFIG_OLED_SSD1306_I2C_SCL_GPIO
    out_config->scl_gpio = (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SCL_GPIO;
#else
    out_config->scl_gpio = OLED_SSD1306_DEFAULT_SCL;
#endif

#ifdef CONFIG_OLED_SSD1306_I2C_ADDRESS
    out_config->dev_addr = (uint16_t)CONFIG_OLED_SSD1306_I2C_ADDRESS;
#else
    out_config->dev_addr = OLED_SSD1306_DEFAULT_ADDR;
#endif

#ifdef CONFIG_OLED_SSD1306_I2C_PORT
    out_config->i2c_port = CONFIG_OLED_SSD1306_I2C_PORT;
#else
    out_config->i2c_port = OLED_SSD1306_DEFAULT_PORT;
#endif

#ifdef CONFIG_OLED_SSD1306_I2C_SPEED_HZ
    out_config->clk_speed_hz = (uint32_t)CONFIG_OLED_SSD1306_I2C_SPEED_HZ;
#else
    out_config->clk_speed_hz = OLED_SSD1306_DEFAULT_SPEED;
#endif

#ifdef CONFIG_OLED_SSD1306_I2C_TIMEOUT_MS
    out_config->timeout_ms = (uint32_t)CONFIG_OLED_SSD1306_I2C_TIMEOUT_MS;
#else
    out_config->timeout_ms = OLED_SSD1306_DEFAULT_TIMEOUT_MS;
#endif

    out_config->button_gpio = (gpio_num_t)-1;
    return ESP_OK;
}

static bool oled_is_pin_prohibited(gpio_num_t pin)
{
    /* ESP32 SPI Flash Pins: GPIO 6, 7, 8, 9, 10, 11 */
    if ((int)pin >= 6 && (int)pin <= 11) {
        return true;
    }
    /* ESP32 Input-Only Pins (GPI): GPIO 34, 35, 36, 37, 38, 39 */
    if ((int)pin >= 34 && (int)pin <= 39) {
        return true;
    }
    /* Console UART0 Pins: TX=1, RX=3 */
    if ((int)pin == 1 || (int)pin == 3) {
        return true;
    }
    /* SX1276 HW-001 Reserved Pins: SCK=5, CS=18, MISO=19, RST=23, DIO0=26, MOSI=27 */
    if ((int)pin == 5 || (int)pin == 18 || (int)pin == 19 ||
        (int)pin == 23 || (int)pin == 26 || (int)pin == 27) {
        return true;
    }
    /* Valid general range for bidirectional GPIOs on ESP32 is 0..33 */
    if ((int)pin < 0 || (int)pin > 33) {
        return true;
    }
    return false;
}

esp_err_t oled_ssd1306_validate_gpio(gpio_num_t sda_gpio, gpio_num_t scl_gpio, gpio_num_t button_gpio)
{
    if (sda_gpio == scl_gpio) {
        ESP_LOGE(TAG, "SDA and SCL cannot use the same GPIO (GPIO %d)", (int)sda_gpio);
        return ESP_ERR_INVALID_ARG;
    }

    if (oled_is_pin_prohibited(sda_gpio)) {
        ESP_LOGE(TAG, "SDA GPIO %d is prohibited (conflicts with flash, console, SX1276, or GPI-only)",
                 (int)sda_gpio);
        return ESP_ERR_INVALID_ARG;
    }

    if (oled_is_pin_prohibited(scl_gpio)) {
        ESP_LOGE(TAG, "SCL GPIO %d is prohibited (conflicts with flash, console, SX1276, or GPI-only)",
                 (int)scl_gpio);
        return ESP_ERR_INVALID_ARG;
    }

    if (button_gpio >= 0) {
        if (sda_gpio == button_gpio) {
            ESP_LOGE(TAG, "SDA GPIO %d conflicts with configured Button GPIO %d",
                     (int)sda_gpio, (int)button_gpio);
            return ESP_ERR_INVALID_ARG;
        }
        if (scl_gpio == button_gpio) {
            ESP_LOGE(TAG, "SCL GPIO %d conflicts with configured Button GPIO %d",
                     (int)scl_gpio, (int)button_gpio);
            return ESP_ERR_INVALID_ARG;
        }
    }

    return ESP_OK;
}

esp_err_t oled_ssd1306_validate_config(const oled_ssd1306_config_t *config)
{
    if (config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t gpio_err = oled_ssd1306_validate_gpio(config->sda_gpio, config->scl_gpio, config->button_gpio);
    if (gpio_err != ESP_OK) {
        return gpio_err;
    }

    if (config->i2c_port < 0 || config->i2c_port >= SOC_I2C_NUM) {
        ESP_LOGE(TAG, "Invalid I2C port %d (available: 0..%d)", config->i2c_port, SOC_I2C_NUM - 1);
        return ESP_ERR_INVALID_ARG;
    }

    /* Valid 7-bit slave address range is 0x08..0x77 */
    if (config->dev_addr < 0x08U || config->dev_addr > 0x77U) {
        ESP_LOGE(TAG, "Invalid I2C slave address 0x%02X (expected 0x3C or 0x3D)", config->dev_addr);
        return ESP_ERR_INVALID_ARG;
    }

    if (config->dev_addr != OLED_SSD1306_DEFAULT_ADDR && config->dev_addr != OLED_SSD1306_ALT_ADDR) {
        ESP_LOGW(TAG, "I2C address 0x%02X is non-standard for SSD1306 (usually 0x3C or 0x3D)", config->dev_addr);
    }

    if (config->clk_speed_hz < 100000U || config->clk_speed_hz > 400000U) {
        ESP_LOGE(TAG, "Invalid I2C clock speed %" PRIu32 " Hz (supported: 100000..400000)", config->clk_speed_hz);
        return ESP_ERR_INVALID_ARG;
    }

    if (config->timeout_ms < 10U || config->timeout_ms > 1000U) {
        ESP_LOGE(TAG, "Invalid I2C timeout %" PRIu32 " ms (supported: 10..1000)", config->timeout_ms);
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_OK;
}

esp_err_t oled_ssd1306_init(oled_ssd1306_dev_t *dev, const oled_ssd1306_config_t *config)
{
    if (dev == NULL || config == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t val_err = oled_ssd1306_validate_config(config);
    if (val_err != ESP_OK) {
        return val_err;
    }

    (void)memset(dev, 0, sizeof(*dev));
    dev->config = *config;

    /* 1. Configure and initialize I2C master bus (ESP-IDF v6.1 esp_driver_i2c) */
    i2c_master_bus_config_t bus_cfg = {
        .i2c_port = config->i2c_port,
        .sda_io_num = config->sda_gpio,
        .scl_io_num = config->scl_gpio,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .intr_priority = 0,
        .trans_queue_depth = 0,
        .flags = {
            .enable_internal_pullup = 1,
            .allow_pd = 0,
        },
    };

    esp_err_t bus_err = i2c_new_master_bus(&bus_cfg, &dev->bus_handle);
    if (bus_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to create I2C master bus: %s", esp_err_to_name(bus_err));
        return bus_err;
    }
    dev->owns_bus = true;

    /* 2. Probe device address on the bus */
    esp_err_t probe_err = i2c_master_probe(dev->bus_handle, config->dev_addr, (int)config->timeout_ms);
    if (probe_err != ESP_OK) {
        ESP_LOGW(TAG, "SSD1306 probe at address 0x%02X failed: %s (check wiring/power/address)",
                 config->dev_addr, esp_err_to_name(probe_err));
        (void)i2c_del_master_bus(dev->bus_handle);
        dev->bus_handle = NULL;
        dev->owns_bus = false;
        return probe_err;
    }

    /* 3. Register SSD1306 device on bus */
    i2c_device_config_t dev_cfg = {
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = config->dev_addr,
        .scl_speed_hz = config->clk_speed_hz,
        .scl_wait_us = 0,
        .flags = {
            .disable_ack_check = 0,
        },
    };

    esp_err_t dev_err = i2c_master_bus_add_device(dev->bus_handle, &dev_cfg, &dev->dev_handle);
    if (dev_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to add SSD1306 device to bus: %s", esp_err_to_name(dev_err));
        (void)i2c_del_master_bus(dev->bus_handle);
        dev->bus_handle = NULL;
        dev->owns_bus = false;
        return dev_err;
    }

    /* 4. Transmit initialization command sequence */
    uint8_t init_payload[sizeof(SSD1306_INIT_CMDS) + 1U];
    init_payload[0] = SSD1306_I2C_CMD_STREAM;
    (void)memcpy(&init_payload[1], SSD1306_INIT_CMDS, sizeof(SSD1306_INIT_CMDS));

    esp_err_t tx_err = i2c_master_transmit(dev->dev_handle,
                                          init_payload,
                                          sizeof(init_payload),
                                          (int)config->timeout_ms);
    if (tx_err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to send SSD1306 init commands: %s", esp_err_to_name(tx_err));
        (void)i2c_master_bus_rm_device(dev->dev_handle);
        dev->dev_handle = NULL;
        (void)i2c_del_master_bus(dev->bus_handle);
        dev->bus_handle = NULL;
        dev->owns_bus = false;
        return tx_err;
    }

    dev->is_initialized = true;

    /* 5. Clear display RAM */
    (void)oled_ssd1306_clear(dev);
    (void)oled_ssd1306_refresh(dev);

    ESP_LOGI(TAG, "SSD1306 OLED initialized at I2C port %d, addr 0x%02X (SDA=GPIO%d, SCL=GPIO%d, %" PRIu32 "Hz)",
             config->i2c_port, config->dev_addr, (int)config->sda_gpio, (int)config->scl_gpio, config->clk_speed_hz);
    return ESP_OK;
}

esp_err_t oled_ssd1306_deinit(oled_ssd1306_dev_t *dev)
{
    if (dev == NULL || !dev->is_initialized) {
        return ESP_ERR_INVALID_ARG;
    }

    if (dev->dev_handle != NULL) {
        (void)i2c_master_bus_rm_device(dev->dev_handle);
        dev->dev_handle = NULL;
    }

    if (dev->owns_bus && dev->bus_handle != NULL) {
        (void)i2c_del_master_bus(dev->bus_handle);
        dev->bus_handle = NULL;
        dev->owns_bus = false;
    }

    dev->is_initialized = false;
    return ESP_OK;
}

bool oled_ssd1306_is_initialized(const oled_ssd1306_dev_t *dev)
{
    return (dev != NULL && dev->is_initialized);
}

esp_err_t oled_ssd1306_clear(oled_ssd1306_dev_t *dev)
{
    if (dev == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    (void)memset(dev->buffer, 0x00, sizeof(dev->buffer));
    return ESP_OK;
}

esp_err_t oled_ssd1306_draw_char(oled_ssd1306_dev_t *dev, uint8_t x, uint8_t page, char c)
{
    if (dev == NULL || page >= OLED_SSD1306_PAGES || x >= OLED_SSD1306_WIDTH) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t glyph_idx;
    if (c >= OLED_FONT_FIRST_CHAR && c <= OLED_FONT_LAST_CHAR) {
        glyph_idx = (uint8_t)(c - OLED_FONT_FIRST_CHAR);
    } else {
        glyph_idx = 0; /* Space glyph fallback */
    }

    size_t base_offset = (size_t)page * OLED_SSD1306_WIDTH;
    const uint8_t *glyph = OLED_FONT_5X7[glyph_idx];

    for (uint8_t i = 0; i < OLED_FONT_GLYPH_WIDTH; i++) {
        uint8_t col = (uint8_t)(x + i);
        if (col < OLED_SSD1306_WIDTH) {
            dev->buffer[base_offset + col] = glyph[i];
        }
    }

    /* 1-pixel inter-character spacing column */
    uint8_t space_col = (uint8_t)(x + OLED_FONT_GLYPH_WIDTH);
    if (space_col < OLED_SSD1306_WIDTH) {
        dev->buffer[base_offset + space_col] = 0x00U;
    }

    return ESP_OK;
}

esp_err_t oled_ssd1306_draw_string(oled_ssd1306_dev_t *dev, uint8_t x, uint8_t page, const char *str)
{
    if (dev == NULL || str == NULL || page >= OLED_SSD1306_PAGES || x >= OLED_SSD1306_WIDTH) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t curr_x = x;
    while (*str != '\0' && curr_x < OLED_SSD1306_WIDTH) {
        (void)oled_ssd1306_draw_char(dev, curr_x, page, *str);
        curr_x = (uint8_t)(curr_x + OLED_FONT_CHAR_WIDTH);
        str++;
    }

    return ESP_OK;
}

esp_err_t oled_ssd1306_refresh(oled_ssd1306_dev_t *dev)
{
    if (dev == NULL || !dev->is_initialized || dev->dev_handle == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    uint8_t cmd_buf[4];
    uint8_t page_buf[OLED_SSD1306_WIDTH + 1U];
    page_buf[0] = SSD1306_I2C_DATA_STREAM;

    for (uint8_t page = 0; page < OLED_SSD1306_PAGES; page++) {
        /* Set page address and reset column pointer to 0 */
        cmd_buf[0] = SSD1306_I2C_CMD_STREAM;
        cmd_buf[1] = (uint8_t)(0xB0U | (page & 0x07U));
        cmd_buf[2] = 0x00U; /* Lower column start address 0 */
        cmd_buf[3] = 0x10U; /* Higher column start address 0 */

        esp_err_t err = i2c_master_transmit(dev->dev_handle,
                                            cmd_buf,
                                            sizeof(cmd_buf),
                                            (int)dev->config.timeout_ms);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to set page %u address: %s", page, esp_err_to_name(err));
            return err;
        }

        /* Copy 128 bytes of page data */
        size_t offset = (size_t)page * OLED_SSD1306_WIDTH;
        (void)memcpy(&page_buf[1], &dev->buffer[offset], OLED_SSD1306_WIDTH);

        err = i2c_master_transmit(dev->dev_handle,
                                  page_buf,
                                  sizeof(page_buf),
                                  (int)dev->config.timeout_ms);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "Failed to transmit page %u data: %s", page, esp_err_to_name(err));
            return err;
        }
    }

    return ESP_OK;
}

esp_err_t oled_ssd1306_format_event_lines(int16_t rand_val,
                                         uint32_t rel_time_sec,
                                         uint32_t total_events,
                                         char line_val[22],
                                         char line_time[22],
                                         char line_total[22])
{
    if (line_val == NULL || line_time == NULL || line_total == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    (void)snprintf(line_val, 22, "Val : %d", (int)rand_val);
    (void)snprintf(line_time, 22, "Rel : %" PRIu32 "s (boot)", rel_time_sec);
    (void)snprintf(line_total, 22, "Evts: %" PRIu32, total_events);

    return ESP_OK;
}

esp_err_t oled_ssd1306_display_event(oled_ssd1306_dev_t *dev,
                                    int16_t rand_val,
                                    uint32_t rel_time_sec,
                                    uint32_t total_events)
{
    if (dev == NULL || !dev->is_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    char line_val[22];
    char line_time[22];
    char line_total[22];

    esp_err_t fmt_err = oled_ssd1306_format_event_lines(rand_val, rel_time_sec, total_events,
                                                        line_val, line_time, line_total);
    if (fmt_err != ESP_OK) {
        return fmt_err;
    }

    (void)oled_ssd1306_clear(dev);

    /* Page 0: Header banner */
    (void)oled_ssd1306_draw_string(dev, 8, 0, "== SENSOR EVENT ==");

    /* Page 2: Confirmed random value (80..100) */
    (void)oled_ssd1306_draw_string(dev, 4, 2, line_val);

    /* Page 4: Relative time recorded at event */
    (void)oled_ssd1306_draw_string(dev, 4, 4, line_time);

    /* Page 6: Cumulative button events */
    (void)oled_ssd1306_draw_string(dev, 4, 6, line_total);

    return oled_ssd1306_refresh(dev);
}
