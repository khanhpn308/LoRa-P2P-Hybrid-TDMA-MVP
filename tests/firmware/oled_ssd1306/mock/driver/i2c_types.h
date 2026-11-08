/*
 * SPDX-License-Identifier: MIT
 * Minimal host mock for driver/i2c_types.h.
 */
#pragma once
#include <stdint.h>
#include <stddef.h>

#define SOC_I2C_NUM 2
#define I2C_ADDR_BIT_LEN_7 0
#define I2C_CLK_SRC_DEFAULT 0

typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
