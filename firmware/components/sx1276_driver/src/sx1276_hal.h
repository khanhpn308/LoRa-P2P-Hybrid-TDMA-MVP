#pragma once

#include "sx1276_types.h"
#include "sx1276_regs.h"
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef void (*sx1276_dio0_isr_cb_t)(void *arg);

esp_err_t sx1276_hal_init(const sx1276_hw_config_t *hw, sx1276_dio0_isr_cb_t isr_cb, void *isr_arg);
esp_err_t sx1276_hal_deinit(void);

esp_err_t sx1276_hal_reset(void);
esp_err_t sx1276_hal_verify_version(void);

esp_err_t sx1276_hal_read_reg(uint8_t addr, uint8_t *out_val);
esp_err_t sx1276_hal_write_reg(uint8_t addr, uint8_t val);
esp_err_t sx1276_hal_burst_read(uint8_t addr, uint8_t *buffer, size_t len);
esp_err_t sx1276_hal_burst_write(uint8_t addr, const uint8_t *buffer, size_t len);
esp_err_t sx1276_hal_read_modify_write(uint8_t addr, uint8_t mask, uint8_t val);

#ifdef __cplusplus
}
#endif
