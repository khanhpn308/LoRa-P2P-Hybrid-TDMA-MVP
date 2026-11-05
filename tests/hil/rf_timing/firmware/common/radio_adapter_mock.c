/**
 * @file radio_adapter_mock.c
 * @brief Implementation of radio adapter abstraction boundary.
 */

#if !defined(ESP_PLATFORM)
#define _POSIX_C_SOURCE 200809L
#endif

#include "radio_adapter_mock.h"
#include <string.h>
#include <time.h>

#if defined(ESP_PLATFORM)
#include "esp_timer.h"
#include "esp_err.h"
#if defined(HIL_USE_REAL_RADIO_DRIVER)
#include "sx1276_driver.h"
#endif
#endif

static timing_radio_config_t s_config = {
    .sf = 7,
    .bw_hz = 125000,
    .cr = 1,
    .preamble_len = 8,
    .channel_idx = 0,
    .rf_tx_enabled = false,      /* Safety: disabled by default */
    .pa_path_verified = false,   /* Safety: fail closed */
    .tx_power_dbm = 2,
};

static bool s_initialized = false;
static bool s_rx_active = false;

int64_t timing_get_time_us(void)
{
#if defined(ESP_PLATFORM)
    return esp_timer_get_time();
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((int64_t)ts.tv_sec * 1000000LL) + (ts.tv_nsec / 1000LL);
#endif
}

int timing_radio_init(const timing_radio_config_t *conf)
{
    if (conf != NULL) {
        s_config = *conf;
    }
    s_initialized = true;
    s_rx_active = false;
    return 0;
}

int timing_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    (void)payload;
    (void)length;
    (void)timeout_ms;

    if (!s_initialized) {
        return -1;
    }

    /* FAIL-CLOSED RF SAFETY GATE:
     * Never transmit RF unless explicit authorization and verified PA path are set. */
    if (!s_config.rf_tx_enabled || !s_config.pa_path_verified) {
        return -100; /* BLOCKED: fail-closed safety gate */
    }

#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    return (int)sx1276_tx(payload, length, (TickType_t)(timeout_ms / portTICK_PERIOD_MS));
#else
    /* Mock transmission: return success */
    return 0;
#endif
}

int timing_radio_start_rx_single(uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (!s_initialized) {
        return -1;
    }
    s_rx_active = true;
#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    return (int)sx1276_start_rx_single((TickType_t)(timeout_ms / portTICK_PERIOD_MS));
#else
    return 0;
#endif
}

int timing_radio_start_rx_continuous(void)
{
    if (!s_initialized) {
        return -1;
    }
    s_rx_active = true;
#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    return (int)sx1276_start_rx_continuous();
#else
    return 0;
#endif
}

int timing_radio_stop_rx(void)
{
    if (!s_initialized) {
        return -1;
    }
    s_rx_active = false;
#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    return (int)sx1276_stop_rx();
#else
    return 0;
#endif
}

int timing_radio_cad(bool *out_cad_detected, uint32_t timeout_ms)
{
    (void)timeout_ms;
    if (!s_initialized || out_cad_detected == NULL) {
        return -1;
    }
#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    return (int)sx1276_cad(out_cad_detected, (TickType_t)(timeout_ms / portTICK_PERIOD_MS));
#else
    *out_cad_detected = false;
    return 0;
#endif
}

int timing_radio_read_frame(timing_rx_packet_t *out_pkt, uint32_t wait_ms)
{
    (void)wait_ms;
    if (!s_initialized || out_pkt == NULL) {
        return -1;
    }
#if defined(ESP_PLATFORM) && defined(HIL_USE_REAL_RADIO_DRIVER)
    sx1276_rx_frame_t frame;
    esp_err_t err = sx1276_read_frame(&frame, (TickType_t)(wait_ms / portTICK_PERIOD_MS));
    if (err == ESP_OK) {
        out_pkt->length = frame.length;
        memcpy(out_pkt->payload, frame.payload, frame.length);
        out_pkt->rssi_dbm = frame.rssi_dbm;
        out_pkt->snr_db = (int8_t)(frame.snr_db_quarter / 4);
        out_pkt->timestamp_us = frame.timestamp_us;
        return 0;
    }
    return (int)err;
#else
    /* Mock: no packet received unless injected */
    return -2; /* Timeout / empty */
#endif
}
