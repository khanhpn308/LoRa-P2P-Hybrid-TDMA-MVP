#pragma once

#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gateway_v2_join.h"
#include "gateway_wal.h"
#include "sx1276_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_TASK_STACK_SIZE_BYTES (16384U)

typedef struct {
    gateway_v2_join_engine_t *join_engine;
    gateway_wal_t *wal;
    const char *gateway_id;
    const char *gateway_epoch;
} gateway_radio_bridge_config_t;

esp_err_t gateway_radio_bridge_init(const gateway_radio_bridge_config_t *cfg);
esp_err_t gateway_radio_bridge_start(void);

void gateway_radio_rx_task(void *pvParameters);
esp_err_t process_join_packet(const uint8_t *payload, size_t length, int16_t rssi, int8_t snr);
esp_err_t process_radio_frame(const sx1276_rx_frame_t *frame);

#ifdef __cplusplus
}
#endif
