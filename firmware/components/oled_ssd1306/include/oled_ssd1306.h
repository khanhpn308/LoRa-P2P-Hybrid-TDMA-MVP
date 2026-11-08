/*
 * SPDX-License-Identifier: MIT
 *
 * SSD1306 0.96-inch OLED Display Component Header for ESP32 / ESP-IDF v6.1.
 * Authority: Issue #271, C Coding Standard v2 (GOV-001..010, C-001..020, MEM-001..008, ERR-001..007).
 */

#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "hal/gpio_types.h"
#include "driver/i2c_types.h"
#include "driver/i2c_master.h"

#ifdef __cplusplus
extern "C" {
#endif

#define OLED_SSD1306_WIDTH          128U
#define OLED_SSD1306_HEIGHT         64U
#define OLED_SSD1306_PAGES          (OLED_SSD1306_HEIGHT / 8U)       /* 8 pages */
#define OLED_SSD1306_BUFFER_SIZE    (OLED_SSD1306_WIDTH * OLED_SSD1306_PAGES) /* 1024 bytes */

#define OLED_SSD1306_DEFAULT_SDA    GPIO_NUM_21
#define OLED_SSD1306_DEFAULT_SCL    GPIO_NUM_22
#define OLED_SSD1306_DEFAULT_ADDR   0x3CU
#define OLED_SSD1306_ALT_ADDR       0x3DU
#define OLED_SSD1306_DEFAULT_PORT   0
#define OLED_SSD1306_DEFAULT_SPEED  400000U /* 400 kHz fast mode */
#define OLED_SSD1306_DEFAULT_TIMEOUT_MS 100U /* 100 ms */

/**
 * @brief SSD1306 Configuration structure.
 */
typedef struct {
    gpio_num_t sda_gpio;         /*!< I2C SDA GPIO number (default GPIO 21) */
    gpio_num_t scl_gpio;         /*!< I2C SCL GPIO number (default GPIO 22) */
    gpio_num_t button_gpio;      /*!< Active button GPIO to check against pin conflict (e.g. GPIO 4) */
    int i2c_port;                /*!< I2C controller port index (0 or 1) */
    uint16_t dev_addr;           /*!< 7-bit I2C slave address (0x3C or 0x3D) */
    uint32_t clk_speed_hz;       /*!< SCL clock speed in Hz (100000..400000) */
    uint32_t timeout_ms;         /*!< Transfer timeout in ms (10..1000) */
} oled_ssd1306_config_t;

/**
 * @brief SSD1306 Device handle structure.
 * Statically allocated by caller, zero heap allocation required (MEM-002).
 */
typedef struct {
    oled_ssd1306_config_t config;
    i2c_master_bus_handle_t bus_handle;
    i2c_master_dev_handle_t dev_handle;
    bool is_initialized;
    bool owns_bus;
    uint8_t buffer[OLED_SSD1306_BUFFER_SIZE];
} oled_ssd1306_dev_t;

/**
 * @brief Fill configuration structure with menuconfig / safe defaults.
 * @param[out] out_config Pointer to configuration struct.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if out_config is NULL.
 */
esp_err_t oled_ssd1306_get_default_config(oled_ssd1306_config_t *out_config);

/**
 * @brief Validate GPIO pin selections against hardware restrictions and conflicts.
 * Checks for SPI flash (6..11), SX1276 HW-001 (5, 18, 19, 23, 26, 27),
 * UART0 console (1, 3), input-only pins (34..39), button pin conflict, and SDA==SCL.
 *
 * @param sda_gpio Selected SDA GPIO number.
 * @param scl_gpio Selected SCL GPIO number.
 * @param button_gpio Selected button GPIO number (-1 if unassigned).
 * @return ESP_OK if valid and free of conflicts, ESP_ERR_INVALID_ARG otherwise.
 */
esp_err_t oled_ssd1306_validate_gpio(gpio_num_t sda_gpio, gpio_num_t scl_gpio, gpio_num_t button_gpio);

/**
 * @brief Validate complete device configuration structure.
 * @param config Pointer to configuration struct.
 * @return ESP_OK if valid, ESP_ERR_INVALID_ARG otherwise.
 */
esp_err_t oled_ssd1306_validate_config(const oled_ssd1306_config_t *config);

/**
 * @brief Initialize I2C master bus, register device, and power up SSD1306 controller.
 *
 * Execution Context: FreeRTOS Task context only (C-004, RTOS-003). MUST NOT be called from ISR.
 *
 * @param[in,out] dev Pointer to device structure.
 * @param[in] config Pointer to configuration structure.
 * @return ESP_OK on success, appropriate esp_err_t on error.
 */
esp_err_t oled_ssd1306_init(oled_ssd1306_dev_t *dev, const oled_ssd1306_config_t *config);

/**
 * @brief Deinitialize SSD1306 device, release I2C handles.
 *
 * @param[in,out] dev Pointer to initialized device structure.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if dev is NULL or uninitialized.
 */
esp_err_t oled_ssd1306_deinit(oled_ssd1306_dev_t *dev);

/**
 * @brief Query initialization status of SSD1306 device.
 * @param dev Pointer to device structure.
 * @return true if initialized, false otherwise.
 */
bool oled_ssd1306_is_initialized(const oled_ssd1306_dev_t *dev);

/**
 * @brief Clear local framebuffer to all black (0x00).
 * Does not transmit to screen until oled_ssd1306_refresh is called.
 *
 * @param[in,out] dev Pointer to device structure.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if dev is NULL.
 */
esp_err_t oled_ssd1306_clear(oled_ssd1306_dev_t *dev);

/**
 * @brief Draw single ASCII character at specified column and page.
 * Uses 6x8 font (5x7 glyph + 1 pixel column spacing).
 *
 * @param[in,out] dev Pointer to device structure.
 * @param x Horizontal pixel column (0..127).
 * @param page Vertical page index (0..7, each page is 8 pixels high).
 * @param c ASCII character to draw (32..126).
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on out of bounds.
 */
esp_err_t oled_ssd1306_draw_char(oled_ssd1306_dev_t *dev, uint8_t x, uint8_t page, char c);

/**
 * @brief Draw null-terminated ASCII string at specified column and page.
 * Truncates gracefully at right edge (x >= 128) without buffer overflow (MEM-004).
 *
 * @param[in,out] dev Pointer to device structure.
 * @param x Horizontal start pixel column (0..127).
 * @param page Vertical page index (0..7).
 * @param str Null-terminated ASCII string.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if parameters invalid.
 */
esp_err_t oled_ssd1306_draw_string(oled_ssd1306_dev_t *dev, uint8_t x, uint8_t page, const char *str);

/**
 * @brief Transmit complete 1024-byte framebuffer to SSD1306 GDDRAM page by page.
 * Uses bounded I2C transactions with configured timeout (ERR-002).
 *
 * @param[in,out] dev Pointer to device structure.
 * @return ESP_OK on success, I2C driver error code on failure.
 */
esp_err_t oled_ssd1306_refresh(oled_ssd1306_dev_t *dev);

/**
 * @brief Format event text lines into preallocated character arrays.
 * Pure formatting helper testable on host without hardware dependencies.
 *
 * @param rand_val Generated random value (80..100).
 * @param rel_time_sec Relative time in seconds since boot/wake.
 * @param total_events Cumulative button event count.
 * @param[out] line_val Buffer of at least 22 bytes for value text.
 * @param[out] line_time Buffer of at least 22 bytes for relative time text.
 * @param[out] line_total Buffer of at least 22 bytes for total events text.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if any buffer is NULL.
 */
esp_err_t oled_ssd1306_format_event_lines(int16_t rand_val,
                                         uint32_t rel_time_sec,
                                         uint32_t total_events,
                                         char line_val[22],
                                         char line_time[22],
                                         char line_total[22]);

/**
 * @brief Render confirmed button event information to display and refresh.
 *
 * Displays:
 * - Line 0: Header "== NODE EVENT =="
 * - Line 2: "Value: <rand_val>" (exact 80..100 generated value)
 * - Line 4: "Rel: <rel_time_sec>s" (explicitly marked as relative time since boot/wake)
 * - Line 6: "Count: <total_events>" (cumulative event counter)
 *
 * @param[in,out] dev Pointer to initialized device structure.
 * @param rand_val Random value (80..100) from confirmed button event.
 * @param rel_time_sec Relative timestamp in seconds since node boot/wake.
 * @param total_events Total confirmed button events recorded.
 * @return ESP_OK on success, error code on I2C failure.
 */
esp_err_t oled_ssd1306_display_event(oled_ssd1306_dev_t *dev,
                                    int16_t rand_val,
                                    uint32_t rel_time_sec,
                                    uint32_t total_events);

#ifdef __cplusplus
}
#endif
