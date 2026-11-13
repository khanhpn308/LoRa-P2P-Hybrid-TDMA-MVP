#include "node_radio_hal.h"

#include <string.h>
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"
#include "node_smart_backoff.h"

static esp_err_t prod_radio_cad(bool *out_activity_detected)
{
    return sx1276_cad(out_activity_detected, pdMS_TO_TICKS(100));
}

static esp_err_t prod_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    return sx1276_tx(payload, length, pdMS_TO_TICKS(timeout_ms));
}

esp_err_t node_radio_hal_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    /* Purge any stale frames from the RX queue before opening the reception window */
    sx1276_rx_frame_t stale;
    while (sx1276_read_frame(&stale, 0) == ESP_OK) {
        /* drain */
    }
    return sx1276_start_rx_continuous();
}

esp_err_t node_radio_hal_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    if (out_buf == NULL || out_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sx1276_rx_frame_t frame;
    esp_err_t err = sx1276_read_frame(&frame, pdMS_TO_TICKS(wait_ms));
    if (err == ESP_OK) {
        *out_len = frame.length;
        (void)memcpy(out_buf, frame.payload, frame.length);
    }
    return err;
}

static esp_err_t prod_radio_sleep(void)
{
    return sx1276_sleep();
}

static esp_err_t prod_radio_standby(void)
{
    return sx1276_standby();
}

static uint32_t prod_get_time_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000ULL);
}

static void prod_delay_ms(uint32_t ms)
{
    (void)node_smart_backoff(ms);
}

esp_err_t node_radio_hal_get_join_hal(node_v2_join_radio_hal_t *out_hal)
{
    if (out_hal == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    out_hal->radio_cad = prod_radio_cad;
    out_hal->radio_tx = prod_radio_tx;
    out_hal->radio_rx_single = node_radio_hal_rx_single;
    out_hal->radio_read_frame = node_radio_hal_read_frame;
    out_hal->radio_sleep = prod_radio_sleep;
    out_hal->radio_standby = prod_radio_standby;
    out_hal->get_time_ms = prod_get_time_ms;
    out_hal->delay_ms = prod_delay_ms;
    return ESP_OK;
}
