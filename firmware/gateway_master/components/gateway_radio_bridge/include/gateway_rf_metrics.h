#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "sx1276_types.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_RF_METRICS_MAX_NODES    (32U)
#define GATEWAY_RF_METRICS_MAX_CHANNELS (11U)
#define GATEWAY_RF_JSON_MAX_LEN         (384U)

typedef struct {
    bool     valid;
    uint8_t  node_id;
    uint8_t  channel_idx;
    int16_t  rssi_dbm;
    int8_t   snr_db_quarter;
    uint64_t sample_seq;
    uint64_t rx_monotonic_us;
    char     source[20];
    char     validation[24];
    char     auth_provenance[24];
} gateway_rf_node_cache_entry_t;

typedef struct {
    bool     valid;
    uint8_t  channel_idx;
    int16_t  channel_rssi_dbm;
    uint64_t sample_seq;
    uint64_t sample_monotonic_us;
    char     sample_context[16];
} gateway_rf_channel_cache_entry_t;

/**
 * @brief Initialize Gateway RF metrics subsystem with gateway ID and boot epoch.
 *
 * @param gateway_id Gateway identity string.
 * @param gateway_epoch Unique boot epoch UUID string.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on NULL.
 */
esp_err_t gateway_rf_metrics_init(const char *gateway_id, const char *gateway_epoch);

/**
 * @brief Get the current gateway epoch UUID string.
 */
const char *gateway_rf_metrics_get_epoch(void);

/**
 * @brief Allocate next monotonic sample sequence number.
 */
uint64_t gateway_rf_metrics_next_seq(void);

/**
 * @brief Record node uplink RF observation in thread-safe bounded cache and publish to MQTT.
 *
 * @param node_id Transmitting node ID (1..32).
 * @param channel_idx VN920 channel index (0..10).
 * @param rssi_dbm Packet RSSI with HF correction and nearest-integer rounding.
 * @param snr_db_quarter Signed raw RegPktSnrValue (0.25 dB / LSB).
 * @param rx_monotonic_us ESP32 monotonic microsecond latch at RxDone.
 * @param source Packet type ("UP_EVENT" or "UP_HEARTBEAT_ACK").
 * @param is_mic_verified True if authenticated with MIC, false if unauthenticated/CRC only.
 * @param[out] out_sample_seq Sequence number assigned to this measurement identity.
 * @return ESP_OK on success.
 */
esp_err_t gateway_rf_metrics_record_and_publish_node(uint8_t node_id,
                                                    uint8_t channel_idx,
                                                    int16_t rssi_dbm,
                                                    int8_t snr_db_quarter,
                                                    uint64_t rx_monotonic_us,
                                                    const char *source,
                                                    bool is_mic_verified,
                                                    uint64_t *out_sample_seq);

/**
 * @brief Format optional 'rf' JSON block for embedding in alert payload.
 *
 * @param buf Output buffer.
 * @param buf_size Size of output buffer.
 * @param sample_seq Monotonic sample sequence number.
 * @param rx_monotonic_us Monotonic microsecond latch.
 * @param channel_idx Operating channel index.
 * @param rssi_dbm Packet RSSI.
 * @param snr_db_quarter Raw quarter-dB SNR.
 * @return ESP_OK on success, ESP_ERR_NO_MEM / ESP_ERR_INVALID_SIZE on truncation.
 */
esp_err_t gateway_rf_metrics_format_alert_block(char *buf,
                                               size_t buf_size,
                                               uint64_t sample_seq,
                                               uint64_t rx_monotonic_us,
                                               uint8_t channel_idx,
                                               int16_t rssi_dbm,
                                               int8_t snr_db_quarter);

/**
 * @brief Sample instantaneous channel RSSI via serialized Radio Owner and publish to MQTT.
 *
 * Enforces task context execution (never direct SPI from ISR/timer).
 *
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE if radio is not in valid RX mode.
 */
esp_err_t gateway_rf_metrics_sample_and_publish_channel(void);

/**
 * @brief Retrieve cached latest observation for a specific node and channel.
 */
esp_err_t gateway_rf_metrics_get_node_cache(uint8_t node_id,
                                            uint8_t channel_idx,
                                            gateway_rf_node_cache_entry_t *out_entry);

/**
 * @brief Retrieve cached latest channel RSSI sample for a specific channel.
 */
esp_err_t gateway_rf_metrics_get_channel_cache(uint8_t channel_idx,
                                               gateway_rf_channel_cache_entry_t *out_entry);

#ifdef __cplusplus
}
#endif
