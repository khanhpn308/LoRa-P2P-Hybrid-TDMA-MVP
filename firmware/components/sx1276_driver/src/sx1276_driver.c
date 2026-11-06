#include "sx1276_driver.h"
#include "sx1276_hal.h"
#include "sx1276_config.h"
#include "sx1276_owner.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "sx1276_driver";

// ISR callback declared in sx1276_owner.h

esp_err_t sx1276_init(const sx1276_hw_config_t *hw_conf,
                      const sx1276_phy_config_t *phy_conf)
{
    sx1276_hw_config_t hw;
    if (hw_conf != NULL) {
        hw = *hw_conf;
    } else {
        esp_err_t err = sx1276_get_default_hw_config(&hw);
        if (err != ESP_OK) return err;
    }

    sx1276_phy_config_t phy;
    if (phy_conf != NULL) {
        phy = *phy_conf;
    } else {
        esp_err_t err = sx1276_get_default_phy_config(&phy);
        if (err != ESP_OK) return err;
    }

    ESP_LOGI(TAG, "Initializing SX1276 driver: SCK=%d MISO=%d MOSI=%d CS=%d RST=%d DIO0=%d",
             hw.pin_sck, hw.pin_miso, hw.pin_mosi, hw.pin_cs, hw.pin_rst, hw.pin_dio0);
    ESP_LOGI(TAG, "PHY config: SF=%d BW=%d CR=%d Preamble=%d Channel=%d Freq=%lu Hz",
             phy.sf, phy.bw, phy.cr, phy.preamble_len, phy.channel_idx, (unsigned long)phy.frequency_hz);
    ESP_LOGI(TAG, "Safety status: PA_PATH=%d, RF_TX_ENABLE=%d (Fail-closed if PA_PATH==UNKNOWN)",
             phy.pa_path, phy.rf_tx_enabled);

    // 1. Initialize HAL and register DIO0 ISR
    esp_err_t err = sx1276_hal_init(&hw, sx1276_owner_dio0_isr, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "sx1276_hal_init failed: %s", esp_err_to_name(err));
        return err;
    }

    // 2. Perform hardware reset pulse
    err = sx1276_hal_reset();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "sx1276_hal_reset failed: %s", esp_err_to_name(err));
        sx1276_hal_deinit();
        return err;
    }

    // 3. Verify silicon presence and version
    err = sx1276_hal_verify_version();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "sx1276_hal_verify_version failed: %s", esp_err_to_name(err));
        sx1276_hal_deinit();
        return err;
    }

    // 4. Initialize Radio Owner task
    err = sx1276_owner_init(&phy);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "sx1276_owner_init failed: %s", esp_err_to_name(err));
        sx1276_hal_deinit();
        return err;
    }

    ESP_LOGI(TAG, "SX1276 Driver successfully initialized and standing by");
    return ESP_OK;
}

esp_err_t sx1276_reinit_after_wake(void)
{
    ESP_LOGI(TAG, "Reinitializing SX1276 after ESP32 deep-sleep wake");
    return sx1276_owner_reinit_after_wake();
}

esp_err_t sx1276_sleep(void)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_SLEEP,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(500));
}

esp_err_t sx1276_standby(void)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_STANDBY,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(500));
}

esp_err_t sx1276_tx(const uint8_t *payload, uint8_t length, TickType_t timeout_ticks)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_TX,
        .params.tx = {
            .payload = payload,
            .length = length,
            .timeout_ticks = timeout_ticks,
        },
    };
    return sx1276_owner_send_cmd(&cmd, timeout_ticks + pdMS_TO_TICKS(500));
}

esp_err_t sx1276_start_rx_single(TickType_t timeout_ticks)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_START_RX_SINGLE,
        .params.rx_single = {
            .timeout_ticks = timeout_ticks,
        },
    };
    return sx1276_owner_send_cmd(&cmd, timeout_ticks + pdMS_TO_TICKS(500));
}

esp_err_t sx1276_start_rx_continuous(void)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_START_RX_CONT,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(500));
}

esp_err_t sx1276_stop_rx(void)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_STOP_RX,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(500));
}

esp_err_t sx1276_cad(bool *out_cad_detected, TickType_t timeout_ticks)
{
    if (out_cad_detected == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_CAD,
        .params.cad = {
            .out_detected = out_cad_detected,
            .timeout_ticks = timeout_ticks,
        },
    };
    return sx1276_owner_send_cmd(&cmd, timeout_ticks + pdMS_TO_TICKS(500));
}

esp_err_t sx1276_set_channel(uint8_t channel_idx)
{
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_SET_CHANNEL,
        .params.set_chan = {
            .channel_idx = channel_idx,
        },
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(500));
}

esp_err_t sx1276_read_frame(sx1276_rx_frame_t *out_frame, TickType_t wait_ticks)
{
    return sx1276_owner_pop_rx_frame(out_frame, wait_ticks);
}

esp_err_t sx1276_get_diagnostics(sx1276_diagnostics_t *out_diag)
{
    return sx1276_owner_get_diagnostics(out_diag);
}
