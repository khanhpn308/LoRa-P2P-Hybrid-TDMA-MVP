#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "gateway_v2_join.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t gateway_downlink_init(gateway_v2_join_engine_t *join_engine);
void gateway_downlink_register_callbacks(void);

void on_downlink_session_key(const uint8_t *data, size_t len);
void on_downlink_schedule(const uint8_t *data, size_t len);
void on_downlink_join_grant(const uint8_t *data, size_t len);
void on_downlink_join_wait(const uint8_t *data, size_t len);
void on_downlink_join_reject(const uint8_t *data, size_t len);
void on_downlink_node_revoke(const uint8_t *data, size_t len);

#ifdef __cplusplus
}
#endif
