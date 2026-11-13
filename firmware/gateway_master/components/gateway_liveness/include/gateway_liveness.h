#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_LORA_TRACKED_NODES (32)

esp_err_t gateway_liveness_init(void);
esp_err_t gateway_liveness_start_timers(void);

void gateway_liveness_record_event(uint8_t node_id);
void gateway_liveness_record_node_alive(uint8_t node_id);
uint32_t gateway_liveness_get_rx_events_total(void);

void gateway_heartbeat_timer_cb(void *arg);
void nodes_liveness_timer_cb(void *arg);
void gateway_liveness_on_transport_connection_status(bool connected);

#ifdef __cplusplus
}
#endif
