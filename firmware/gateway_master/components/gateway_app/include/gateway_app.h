#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t gateway_app_init(void);
void gateway_app_run(void);
const char *gateway_app_get_boot_epoch(void);

#ifdef __cplusplus
}
#endif
