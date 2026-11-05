/**
 * @file radio_adapter_mock.h
 * @brief Radio adapter abstraction boundary matching Issue #10 public driver interface.
 *
 * Provides both:
 * 1. Mock implementation with simulated timing callbacks for host testing and compilation isolation.
 * 2. Passthrough adapter to real #10 public APIs when compiled within ESP-IDF.
 *
 * RF_TX safety gate: transmissions are rejected fail-closed unless explicit authorization
 * is configured at runtime.
 */

#ifndef RADIO_ADAPTER_MOCK_H
#define RADIO_ADAPTER_MOCK_H

#include "timing_harness_types.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint8_t sf;
    uint32_t bw_hz;
    uint8_t cr;
    uint16_t preamble_len;
    uint8_t channel_idx;
    bool rf_tx_enabled;      /**< Safety gate: false by default */
    bool pa_path_verified;  /**< Safety gate: false by default */
    int8_t tx_power_dbm;    /**< Target: +2 dBm */
} timing_radio_config_t;

typedef struct {
    uint8_t payload[64];
    uint8_t length;
    int16_t rssi_dbm;
    int8_t snr_db;
    int64_t timestamp_us;
} timing_rx_packet_t;

/**
 * @brief Initialize radio adapter with specified configuration.
 */
int timing_radio_init(const timing_radio_config_t *conf);

/**
 * @brief Transmit packet buffer.
 * Enforces fail-closed RF safety gate: returns error code -100 (BLOCKED)
 * if rf_tx_enabled is false or pa_path_verified is false.
 */
int timing_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms);

/**
 * @brief Start single-packet reception.
 */
int timing_radio_start_rx_single(uint32_t timeout_ms);

/**
 * @brief Start continuous reception.
 */
int timing_radio_start_rx_continuous(void);

/**
 * @brief Stop active receive mode and return to standby.
 */
int timing_radio_stop_rx(void);

/**
 * @brief Channel activity detection.
 */
int timing_radio_cad(bool *out_cad_detected, uint32_t timeout_ms);

/**
 * @brief Read arrived frame from radio RX buffer.
 */
int timing_radio_read_frame(timing_rx_packet_t *out_pkt, uint32_t wait_ms);

/**
 * @brief Get high-resolution monotonic microsecond timestamp.
 */
int64_t timing_get_time_us(void);

#ifdef __cplusplus
}
#endif

#endif /* RADIO_ADAPTER_MOCK_H */
