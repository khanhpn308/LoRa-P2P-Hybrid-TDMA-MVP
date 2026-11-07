#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "esp_sleep.h"
#include "driver/gpio.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    BUTTON_CAUSE_NONE = 0,
    BUTTON_CAUSE_EXT0_BUTTON = 1,
    BUTTON_CAUSE_TIMER = 2,
    BUTTON_CAUSE_RESET_OR_OTHER = 3,
} button_wakeup_cause_t;

typedef struct {
    gpio_num_t gpio_num;
    int active_level;
    uint32_t debounce_ms;
    uint32_t hold_time_ms;
} button_config_t;

typedef struct {
    button_config_t config;
    bool is_initialized;
} button_driver_t;

/**
 * @brief Initialize button GPIO and configure electrical pull-up/pull-down.
 * @param driver Pointer to driver instance.
 * @param config Pointer to button configuration.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on invalid parameter.
 */
esp_err_t button_driver_init(button_driver_t *driver, const button_config_t *config);

/**
 * @brief Determine system wakeup cause.
 * @return Classified wakeup cause enum.
 */
button_wakeup_cause_t button_driver_get_wakeup_cause(void);

/**
 * @brief Qualify button state with software debounce.
 * @param driver Pointer to initialized button driver.
 * @param out_qualified Pointer to boolean receiving true if valid press, false if bounce/noise.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if parameters are NULL.
 */
esp_err_t button_driver_qualify_press(button_driver_t *driver, bool *out_qualified);

/**
 * @brief Arm Deep-Sleep EXT0 wakeup on configured button pin.
 * @param driver Pointer to initialized button driver.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if driver not initialized.
 */
esp_err_t button_driver_arm_sleep(button_driver_t *driver);

#ifdef __cplusplus
}
#endif
