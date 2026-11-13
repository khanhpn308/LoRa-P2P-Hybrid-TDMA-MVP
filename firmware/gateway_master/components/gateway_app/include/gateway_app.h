#pragma once

#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t gateway_app_init(void);
void gateway_app_run(void);

#ifdef __cplusplus
}
#endif
