/*
 * SPDX-License-Identifier: MIT
 * Minimal host mock for esp_log.h.
 */
#pragma once
#include <stdio.h>

#define ESP_LOGI(tag, fmt, ...) do { (void)(tag); } while (0)
#define ESP_LOGW(tag, fmt, ...) do { (void)(tag); } while (0)
#define ESP_LOGE(tag, fmt, ...) do { (void)(tag); } while (0)
