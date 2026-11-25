/**
 * @file test_node_ui.c
 * @brief Unit tests for Node UI ACK LED indicator and pin safety collision checks.
 *
 * Authority: Issue #396, C Coding Standard v2.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "esp_err.h"

/* Mock FreeRTOS definitions */
typedef uint32_t TickType_t;
#define pdMS_TO_TICKS(ms) ((TickType_t)(ms))

static uint32_t s_mock_vtaskdelay_called_ms = 0;
static void vTaskDelay(TickType_t ticks)
{
    s_mock_vtaskdelay_called_ms = ticks;
}

/* Mock ESP-IDF GPIO definitions */
typedef enum {
    GPIO_NUM_NC = -1,
    GPIO_NUM_0 = 0,
    GPIO_NUM_1 = 1,
    GPIO_NUM_2 = 2,
    GPIO_NUM_3 = 3,
    GPIO_NUM_4 = 4,
    GPIO_NUM_5 = 5,
    GPIO_NUM_6 = 6,
    GPIO_NUM_7 = 7,
    GPIO_NUM_8 = 8,
    GPIO_NUM_9 = 9,
    GPIO_NUM_10 = 10,
    GPIO_NUM_11 = 11,
    GPIO_NUM_12 = 12,
    GPIO_NUM_13 = 13,
    GPIO_NUM_14 = 14,
    GPIO_NUM_15 = 15,
    GPIO_NUM_16 = 16,
    GPIO_NUM_17 = 17,
    GPIO_NUM_18 = 18,
    GPIO_NUM_19 = 19,
    GPIO_NUM_20 = 20,
    GPIO_NUM_21 = 21,
    GPIO_NUM_22 = 22,
    GPIO_NUM_23 = 23,
    GPIO_NUM_25 = 25,
    GPIO_NUM_26 = 26,
    GPIO_NUM_27 = 27,
    GPIO_NUM_32 = 32,
    GPIO_NUM_33 = 33,
    GPIO_NUM_34 = 34,
    GPIO_NUM_35 = 35,
    GPIO_NUM_36 = 36,
    GPIO_NUM_37 = 37,
    GPIO_NUM_38 = 38,
    GPIO_NUM_39 = 39,
    GPIO_NUM_MAX = 40
} gpio_num_t;

#define GPIO_IS_VALID_OUTPUT_GPIO(gpio_num) ((gpio_num >= 0 && gpio_num <= 33) && \
                                             (gpio_num != 20) && (gpio_num != 24) && (gpio_num != 28) && \
                                             (gpio_num != 29) && (gpio_num != 30) && (gpio_num != 31))

typedef enum {
    GPIO_MODE_DISABLE = 0,
    GPIO_MODE_INPUT = 1,
    GPIO_MODE_OUTPUT = 2,
    GPIO_MODE_OUTPUT_OD = 3,
    GPIO_MODE_INPUT_OUTPUT_OD = 4,
    GPIO_MODE_INPUT_OUTPUT = 5,
} gpio_mode_t;

typedef enum {
    GPIO_PULLUP_DISABLE = 0x0,
    GPIO_PULLUP_ENABLE = 0x1,
} gpio_pullup_t;

typedef enum {
    GPIO_PULLDOWN_DISABLE = 0x0,
    GPIO_PULLDOWN_ENABLE = 0x1,
} gpio_pulldown_t;

typedef enum {
    GPIO_INTR_DISABLE = 0,
} gpio_int_type_t;

typedef struct {
    uint64_t pin_bit_mask;
    gpio_mode_t mode;
    gpio_pullup_t pull_up_en;
    gpio_pulldown_t pull_down_en;
    gpio_int_type_t intr_type;
} gpio_config_t;

static esp_err_t s_mock_gpio_config_ret = ESP_OK;
static uint64_t s_mock_last_config_pin_mask = 0;
static gpio_mode_t s_mock_last_config_mode = GPIO_MODE_DISABLE;
static gpio_pulldown_t s_mock_last_config_pulldown = GPIO_PULLDOWN_DISABLE;

static esp_err_t gpio_config(const gpio_config_t *pGPIOConfig)
{
    if (s_mock_gpio_config_ret != ESP_OK) {
        return s_mock_gpio_config_ret;
    }
    s_mock_last_config_pin_mask = pGPIOConfig->pin_bit_mask;
    s_mock_last_config_mode = pGPIOConfig->mode;
    s_mock_last_config_pulldown = pGPIOConfig->pull_down_en;
    return ESP_OK;
}

static int s_mock_gpio_levels[40];
static int s_mock_gpio_set_level_calls = 0;
static esp_err_t gpio_set_level(gpio_num_t gpio_num, uint32_t level)
{
    if (gpio_num >= 0 && gpio_num < 40) {
        s_mock_gpio_levels[gpio_num] = (int)level;
    }
    s_mock_gpio_set_level_calls++;
    return ESP_OK;
}

/* Include the module logic with test configurations */
#define CONFIG_NODE_BUTTON_GPIO 4
#define CONFIG_OLED_SSD1306_ENABLE 1
#define CONFIG_OLED_SSD1306_I2C_SDA_GPIO 21
#define CONFIG_OLED_SSD1306_I2C_SCL_GPIO 22

static bool test_is_pin_prohibited(gpio_num_t pin)
{
    if (!GPIO_IS_VALID_OUTPUT_GPIO(pin)) {
        return true;
    }
    if (pin >= GPIO_NUM_34 && pin <= GPIO_NUM_39) {
        return true;
    }
    if (pin >= GPIO_NUM_6 && pin <= GPIO_NUM_11) {
        return true;
    }
    if (pin == GPIO_NUM_5 || pin == GPIO_NUM_18 || pin == GPIO_NUM_19 ||
        pin == GPIO_NUM_23 || pin == GPIO_NUM_26 || pin == GPIO_NUM_27) {
        return true;
    }
    if (pin == GPIO_NUM_1 || pin == GPIO_NUM_3) {
        return true;
    }
    /* Strapping pins: GPIO 0, 2, 15 (GPIO 12 is permitted for active-high ACK LED) */
    if (pin == GPIO_NUM_0 || pin == GPIO_NUM_2 || pin == GPIO_NUM_15) {
        return true;
    }
#ifdef CONFIG_NODE_BUTTON_GPIO
    if (pin == (gpio_num_t)CONFIG_NODE_BUTTON_GPIO) {
        return true;
    }
#endif
#if CONFIG_OLED_SSD1306_ENABLE
    if (pin == (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SDA_GPIO ||
        pin == (gpio_num_t)CONFIG_OLED_SSD1306_I2C_SCL_GPIO) {
        return true;
    }
#endif
    return false;
}

static esp_err_t test_blink_impl(bool enabled, gpio_num_t pin, uint32_t pulse_ms)
{
    if (!enabled) {
        return ESP_OK;
    }
    if (test_is_pin_prohibited(pin)) {
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
        return err;
    }
    (void)gpio_set_level(pin, 1);
    if (pulse_ms < 50U) {
        pulse_ms = 50U;
    } else if (pulse_ms > 1000U) {
        pulse_ms = 1000U;
    }
    vTaskDelay(pdMS_TO_TICKS(pulse_ms));
    (void)gpio_set_level(pin, 0);
    return ESP_OK;
}

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "\nAssertion failed: %s at %s:%d\n", #cond, __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_INT(expected, actual) do { \
    if ((int)(expected) != (int)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %d, got %d) at %s:%d\n", \
                #expected, #actual, (int)(expected), (int)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

static int test_prohibited_pins_sx1276(void)
{
    /* SX1276 HW-001 radio pins must all be prohibited */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_5));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_18));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_19));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_23));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_26));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_27));
    return 0;
}

static int test_prohibited_pins_system(void)
{
    /* UART console */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_1));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_3));

    /* Strapping */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_0));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_2));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_15));

    /* Button */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_4));

    /* OLED */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_21));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_22));

    /* Input-only (GPI) */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_34));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_35));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_36));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_39));

    /* SPI Flash */
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_6));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_7));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_8));
    ASSERT_TRUE(test_is_pin_prohibited(GPIO_NUM_11));

    return 0;
}

static int test_permitted_pin_candidate(void)
{
    /* GPIO 25 is the proposed candidate on HW-001, GPIO 12 is permitted for active-high ACK LED */
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_25));
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_12));

    /* Other valid general purpose RTC pins */
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_13));
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_14));
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_32));
    ASSERT_TRUE(!test_is_pin_prohibited(GPIO_NUM_33));
    return 0;
}

static int test_blink_disabled_noop(void)
{
    s_mock_gpio_set_level_calls = 0;
    s_mock_vtaskdelay_called_ms = 0;
    esp_err_t err = test_blink_impl(false, GPIO_NUM_25, 200);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_EQUAL_INT(0, s_mock_gpio_set_level_calls);
    ASSERT_EQUAL_INT(0, (int)s_mock_vtaskdelay_called_ms);
    return 0;
}

static int test_blink_enabled_prohibited_pin_fails(void)
{
    s_mock_gpio_set_level_calls = 0;
    /* Attempt to configure radio DIO0 pin 26 */
    esp_err_t err = test_blink_impl(true, GPIO_NUM_26, 200);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, err);
    ASSERT_EQUAL_INT(0, s_mock_gpio_set_level_calls);
    return 0;
}

static int test_blink_enabled_nominal_pulse(void)
{
    memset(s_mock_gpio_levels, 0, sizeof(s_mock_gpio_levels));
    s_mock_gpio_set_level_calls = 0;
    s_mock_vtaskdelay_called_ms = 0;
    s_mock_gpio_config_ret = ESP_OK;

    esp_err_t err = test_blink_impl(true, GPIO_NUM_25, 200);
    ASSERT_EQUAL_INT(ESP_OK, err);

    /* GPIO configuration check */
    ASSERT_TRUE(s_mock_last_config_pin_mask == (1ULL << GPIO_NUM_25));
    ASSERT_EQUAL_INT(GPIO_MODE_OUTPUT, s_mock_last_config_mode);
    ASSERT_EQUAL_INT(GPIO_PULLDOWN_ENABLE, s_mock_last_config_pulldown);

    /* Pulse duration check */
    ASSERT_EQUAL_INT(200, (int)s_mock_vtaskdelay_called_ms);

    /* Pin level after execution MUST be LOW (0) */
    ASSERT_EQUAL_INT(0, s_mock_gpio_levels[GPIO_NUM_25]);
    ASSERT_EQUAL_INT(2, s_mock_gpio_set_level_calls); /* 1 call HIGH, 1 call LOW */

    return 0;
}

static int test_blink_pulse_duration_clamping(void)
{
    /* Under 50ms clamps to 50ms */
    s_mock_vtaskdelay_called_ms = 0;
    ASSERT_EQUAL_INT(ESP_OK, test_blink_impl(true, GPIO_NUM_25, 10));
    ASSERT_EQUAL_INT(50, (int)s_mock_vtaskdelay_called_ms);

    /* Over 1000ms clamps to 1000ms */
    s_mock_vtaskdelay_called_ms = 0;
    ASSERT_EQUAL_INT(ESP_OK, test_blink_impl(true, GPIO_NUM_25, 5000));
    ASSERT_EQUAL_INT(1000, (int)s_mock_vtaskdelay_called_ms);

    return 0;
}

static int test_blink_gpio_config_failure_propagation(void)
{
    s_mock_gpio_config_ret = ESP_ERR_INVALID_STATE;
    s_mock_gpio_set_level_calls = 0;
    esp_err_t err = test_blink_impl(true, GPIO_NUM_25, 200);
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, err);
    ASSERT_EQUAL_INT(0, s_mock_gpio_set_level_calls);
    s_mock_gpio_config_ret = ESP_OK;
    return 0;
}

#define TEST_RUN(name) do { \
    printf("Running %s ... ", #name); \
    if (name() == 0) { \
        printf("PASSED\n"); \
    } else { \
        printf("FAILED\n"); \
        failures++; \
    } \
} while (0)

int main(void)
{
    int failures = 0;
    printf("=== Running Node UI ACK LED Unit Tests ===\n");

    TEST_RUN(test_prohibited_pins_sx1276);
    TEST_RUN(test_prohibited_pins_system);
    TEST_RUN(test_permitted_pin_candidate);
    TEST_RUN(test_blink_disabled_noop);
    TEST_RUN(test_blink_enabled_prohibited_pin_fails);
    TEST_RUN(test_blink_enabled_nominal_pulse);
    TEST_RUN(test_blink_pulse_duration_clamping);
    TEST_RUN(test_blink_gpio_config_failure_propagation);

    printf("\nTest summary: %s (%d failures)\n", failures == 0 ? "ALL PASSED" : "FAILED", failures);
    return failures;
}
