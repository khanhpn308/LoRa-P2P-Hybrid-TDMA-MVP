/*
 * SPDX-License-Identifier: MIT
 *
 * Host unit test suite for SSD1306 OLED driver component.
 * Authority: Issue #271, C Coding Standard v2 (GOV-001..010, C-001..020, MEM-001..008, ERR-001..007).
 */

#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include "oled_ssd1306.h"

/* Mock I2C state variables for hardware simulation */
static bool s_mock_probe_should_succeed = true;
static bool s_mock_tx_should_succeed = true;
static int s_mock_bus_count = 0;
static int s_mock_dev_count = 0;
static int s_mock_tx_count = 0;

esp_err_t i2c_new_master_bus(const i2c_master_bus_config_t *bus_config, i2c_master_bus_handle_t *ret_bus_handle)
{
    (void)bus_config;
    if (ret_bus_handle == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_mock_bus_count++;
    *ret_bus_handle = (i2c_master_bus_handle_t)(uintptr_t)0x1000;
    return ESP_OK;
}

esp_err_t i2c_master_probe(i2c_master_bus_handle_t bus_handle, uint16_t address, int xfer_timeout_ms)
{
    (void)bus_handle;
    (void)address;
    (void)xfer_timeout_ms;
    if (!s_mock_probe_should_succeed) {
        return ESP_ERR_NOT_FOUND;
    }
    return ESP_OK;
}

esp_err_t i2c_master_bus_add_device(i2c_master_bus_handle_t bus_handle, const i2c_device_config_t *dev_config, i2c_master_dev_handle_t *ret_handle)
{
    (void)bus_handle;
    (void)dev_config;
    if (ret_handle == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_mock_dev_count++;
    *ret_handle = (i2c_master_dev_handle_t)(uintptr_t)0x2000;
    return ESP_OK;
}

esp_err_t i2c_master_bus_rm_device(i2c_master_dev_handle_t handle)
{
    if (handle != NULL) {
        s_mock_dev_count--;
    }
    return ESP_OK;
}

esp_err_t i2c_del_master_bus(i2c_master_bus_handle_t bus_handle)
{
    if (bus_handle != NULL) {
        s_mock_bus_count--;
    }
    return ESP_OK;
}

esp_err_t i2c_master_transmit(i2c_master_dev_handle_t i2c_dev, const uint8_t *write_buffer, size_t write_size, int xfer_timeout_ms)
{
    (void)i2c_dev;
    (void)write_buffer;
    (void)write_size;
    (void)xfer_timeout_ms;
    if (!s_mock_tx_should_succeed) {
        return ESP_ERR_TIMEOUT;
    }
    s_mock_tx_count++;
    return ESP_OK;
}

static void test_default_config(void)
{
    printf("Running test_default_config...\n");
    oled_ssd1306_config_t cfg;
    assert(oled_ssd1306_get_default_config(NULL) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_get_default_config(&cfg) == ESP_OK);
    assert(cfg.sda_gpio == GPIO_NUM_21);
    assert(cfg.scl_gpio == GPIO_NUM_22);
    assert(cfg.dev_addr == 0x3C);
    assert(cfg.clk_speed_hz == 400000U);
    assert(cfg.timeout_ms == 100U);
    assert(oled_ssd1306_validate_config(&cfg) == ESP_OK);
    printf("PASS: test_default_config\n");
}

static void test_gpio_validation(void)
{
    printf("Running test_gpio_validation...\n");
    /* Valid configuration */
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, GPIO_NUM_22, GPIO_NUM_4) == ESP_OK);

    /* SDA == SCL */
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, GPIO_NUM_21, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);

    /* Button conflict */
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_4, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, GPIO_NUM_4, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);

    /* Flash pins (6..11) */
    for (int pin = 6; pin <= 11; pin++) {
        assert(oled_ssd1306_validate_gpio((gpio_num_t)pin, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
        assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, (gpio_num_t)pin, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    }

    /* Input-only GPI pins (34..39) */
    for (int pin = 34; pin <= 39; pin++) {
        assert(oled_ssd1306_validate_gpio((gpio_num_t)pin, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
        assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, (gpio_num_t)pin, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    }

    /* Console UART0 pins (1, 3) */
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_1, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_3, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);

    /* SX1276 HW-001 reserved pins (5, 18, 19, 23, 26, 27) */
    const gpio_num_t sx1276_pins[] = {GPIO_NUM_5, GPIO_NUM_18, GPIO_NUM_19, GPIO_NUM_23, GPIO_NUM_26, GPIO_NUM_27};
    for (size_t i = 0; i < sizeof(sx1276_pins)/sizeof(sx1276_pins[0]); i++) {
        assert(oled_ssd1306_validate_gpio(sx1276_pins[i], GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
        assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, sx1276_pins[i], GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    }

    /* Out of bounds negative / high GPIOs */
    assert(oled_ssd1306_validate_gpio((gpio_num_t)-2, GPIO_NUM_22, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_validate_gpio(GPIO_NUM_21, (gpio_num_t)45, GPIO_NUM_4) == ESP_ERR_INVALID_ARG);
    printf("PASS: test_gpio_validation\n");
}

static void test_config_validation(void)
{
    printf("Running test_config_validation...\n");
    oled_ssd1306_config_t cfg;
    (void)oled_ssd1306_get_default_config(&cfg);

    /* Null pointer */
    assert(oled_ssd1306_validate_config(NULL) == ESP_ERR_INVALID_ARG);

    /* Invalid I2C port */
    cfg.i2c_port = 2;
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.i2c_port = 0;

    /* Invalid addresses */
    cfg.dev_addr = 0x05; /* below 0x08 */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.dev_addr = 0x78; /* above 0x77 */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.dev_addr = 0x3C;
    assert(oled_ssd1306_validate_config(&cfg) == ESP_OK);
    cfg.dev_addr = 0x3D;
    assert(oled_ssd1306_validate_config(&cfg) == ESP_OK);

    /* Clock speed bounds */
    cfg.clk_speed_hz = 50000; /* too slow */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.clk_speed_hz = 1000000; /* too fast */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.clk_speed_hz = 400000;

    /* Timeout bounds */
    cfg.timeout_ms = 5; /* too short */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.timeout_ms = 2000; /* too long */
    assert(oled_ssd1306_validate_config(&cfg) == ESP_ERR_INVALID_ARG);
    cfg.timeout_ms = 100;
    assert(oled_ssd1306_validate_config(&cfg) == ESP_OK);
    printf("PASS: test_config_validation\n");
}

static void test_format_event_lines(void)
{
    printf("Running test_format_event_lines...\n");
    char l_val[22], l_time[22], l_total[22];

    assert(oled_ssd1306_format_event_lines(85, 12, 1, NULL, l_time, l_total) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_format_event_lines(85, 12, 1, l_val, NULL, l_total) == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_format_event_lines(85, 12, 1, l_val, l_time, NULL) == ESP_ERR_INVALID_ARG);

    assert(oled_ssd1306_format_event_lines(80, 0, 1, l_val, l_time, l_total) == ESP_OK);
    assert(strcmp(l_val, "Val : 80") == 0);
    assert(strcmp(l_time, "Rel : 0s (boot)") == 0);
    assert(strcmp(l_total, "Evts: 1") == 0);

    assert(oled_ssd1306_format_event_lines(100, 3600, 42, l_val, l_time, l_total) == ESP_OK);
    assert(strcmp(l_val, "Val : 100") == 0);
    assert(strcmp(l_time, "Rel : 3600s (boot)") == 0);
    assert(strcmp(l_total, "Evts: 42") == 0);
    printf("PASS: test_format_event_lines\n");
}

static void test_framebuffer_and_drawing(void)
{
    printf("Running test_framebuffer_and_drawing...\n");
    oled_ssd1306_dev_t dev;
    (void)memset(&dev, 0, sizeof(dev));

    /* Clear */
    dev.buffer[50] = 0xFF;
    assert(oled_ssd1306_clear(&dev) == ESP_OK);
    for (size_t i = 0; i < OLED_SSD1306_BUFFER_SIZE; i++) {
        assert(dev.buffer[i] == 0x00);
    }

    /* Draw char out of bounds */
    assert(oled_ssd1306_draw_char(&dev, 128, 0, 'A') == ESP_ERR_INVALID_ARG);
    assert(oled_ssd1306_draw_char(&dev, 0, 8, 'A') == ESP_ERR_INVALID_ARG);

    /* Draw 'A' at (0, 0) */
    assert(oled_ssd1306_draw_char(&dev, 0, 0, 'A') == ESP_OK);
    /* In font 5x7, 'A' has columns: 0x7E, 0x11, 0x11, 0x11, 0x7E, and column 5 is 0x00 */
    assert(dev.buffer[0] == 0x7E);
    assert(dev.buffer[1] == 0x11);
    assert(dev.buffer[2] == 0x11);
    assert(dev.buffer[3] == 0x11);
    assert(dev.buffer[4] == 0x7E);
    assert(dev.buffer[5] == 0x00);

    /* Draw string with truncation/clipping without buffer overflow */
    assert(oled_ssd1306_clear(&dev) == ESP_OK);
    assert(oled_ssd1306_draw_string(&dev, 120, 0, "ABCDEF") == ESP_OK);
    /* 'A' occupies 120..125, 'B' starts at 126 and clips at 127 */
    assert(dev.buffer[120] == 0x7E);
    /* Page 1 (offset 128) must not be corrupted */
    assert(dev.buffer[128] == 0x00);
    printf("PASS: test_framebuffer_and_drawing\n");
}

static void test_mock_hardware_lifecycle(void)
{
    printf("Running test_mock_hardware_lifecycle...\n");
    oled_ssd1306_dev_t dev;
    oled_ssd1306_config_t cfg;
    (void)oled_ssd1306_get_default_config(&cfg);

    /* 1. Probe failure simulation */
    s_mock_probe_should_succeed = false;
    assert(oled_ssd1306_init(&dev, &cfg) == ESP_ERR_NOT_FOUND);
    assert(!oled_ssd1306_is_initialized(&dev));
    assert(s_mock_bus_count == 0); /* Bus was cleaned up */

    /* 2. Successful initialization */
    s_mock_probe_should_succeed = true;
    s_mock_tx_should_succeed = true;
    s_mock_tx_count = 0;
    assert(oled_ssd1306_init(&dev, &cfg) == ESP_OK);
    assert(oled_ssd1306_is_initialized(&dev));
    assert(s_mock_bus_count == 1);
    assert(s_mock_dev_count == 1);

    /* 3. Refresh execution: 8 pages transmitted */
    s_mock_tx_count = 0;
    assert(oled_ssd1306_refresh(&dev) == ESP_OK);
    /* 8 pages * 2 transmissions (command + data) = 16 transmits */
    assert(s_mock_tx_count == 16);

    /* 4. Display event */
    assert(oled_ssd1306_display_event(&dev, 92, 45, 3) == ESP_OK);

    /* 5. Deinitialization */
    assert(oled_ssd1306_deinit(&dev) == ESP_OK);
    assert(!oled_ssd1306_is_initialized(&dev));
    assert(s_mock_bus_count == 0);
    assert(s_mock_dev_count == 0);
    printf("PASS: test_mock_hardware_lifecycle\n");
}

int main(void)
{
    printf("=========================================\n");
    printf("Starting SSD1306 Driver Host Unit Tests\n");
    printf("=========================================\n");

    test_default_config();
    test_gpio_validation();
    test_config_validation();
    test_format_event_lines();
    test_framebuffer_and_drawing();
    test_mock_hardware_lifecycle();

    printf("=========================================\n");
    printf("ALL SSD1306 UNIT TESTS PASSED SUCCESSFULLY!\n");
    printf("=========================================\n");
    return 0;
}
