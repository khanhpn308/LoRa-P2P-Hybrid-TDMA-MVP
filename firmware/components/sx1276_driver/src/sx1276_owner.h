#pragma once

#include "sx1276_types.h"
#include "sx1276_regs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    SX1276_CMD_APPLY_PLAN,
    SX1276_CMD_SLEEP,
    SX1276_CMD_STANDBY,
    SX1276_CMD_TX,
    SX1276_CMD_START_RX_SINGLE,
    SX1276_CMD_START_RX_CONT,
    SX1276_CMD_STOP_RX,
    SX1276_CMD_CAD,
    SX1276_CMD_SET_CHANNEL,
} sx1276_owner_cmd_type_t;

typedef struct {
    sx1276_owner_cmd_type_t type;
    union {
        struct {
            const uint8_t *payload;
            uint8_t        length;
            TickType_t     timeout_ticks;
        } tx;
        struct {
            TickType_t     timeout_ticks;
        } rx_single;
        struct {
            bool          *out_detected;
            TickType_t     timeout_ticks;
        } cad;
        struct {
            uint8_t        channel_idx;
        } set_chan;
    } params;
    esp_err_t              *out_result;
    TaskHandle_t            caller_task;
} sx1276_owner_cmd_t;

esp_err_t sx1276_owner_init(const sx1276_phy_config_t *initial_phy);
esp_err_t sx1276_owner_deinit(void);

void sx1276_owner_dio0_isr(void *arg);

esp_err_t sx1276_owner_send_cmd(sx1276_owner_cmd_t *cmd, TickType_t wait_ticks);
esp_err_t sx1276_owner_pop_rx_frame(sx1276_rx_frame_t *out_frame, TickType_t wait_ticks);
esp_err_t sx1276_owner_get_diagnostics(sx1276_diagnostics_t *out_diag);
esp_err_t sx1276_owner_reinit_after_wake(void);

#ifdef __cplusplus
}
#endif
