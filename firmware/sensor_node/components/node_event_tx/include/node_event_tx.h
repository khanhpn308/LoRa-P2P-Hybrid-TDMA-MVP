#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include "esp_err.h"
#include "node_event_fifo.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Node MAC Configuration structure for Pure CAD CSMA/CA.
 */
typedef struct {
    uint8_t node_id;
    uint8_t gw_id;
    uint8_t session_sel;
    uint8_t session_nonce_prefix[8];
    uint8_t k_session_up[16];
    uint8_t k_session_down[16];
} node_mac_config_t;

/**
 * @brief Transmit pending event via CAD CSMA/CA and wait for DOWN_EVENT_ACK with Stop-and-Wait ARQ.
 *
 * Encapsulates UP_EVENT assembly, AES-CCM* encryption, exponential random CAD backoff,
 * transmission, and ACK reception / ARQ retry loop. If DOWN_REVOKE is received and verified,
 * returns ESP_ERR_INVALID_STATE.
 *
 * @param[in] cfg Pointer to node MAC configuration (non-NULL).
 * @param[in,out] fifo Pointer to persistent node event FIFO (non-NULL).
 * @param[in,out] inout_uplink_counter Pointer to uplink frame counter (non-NULL, incremented on TX).
 * @return ESP_OK on valid ACK received and event dequeued,
 *         ESP_ERR_INVALID_STATE if node was revoked via DOWN_REVOKE,
 *         ESP_ERR_TIMEOUT if CAD or ARQ retries exhausted without ACK,
 *         or error code on failure.
 */
esp_err_t node_cad_event_tx_and_ack(const node_mac_config_t *cfg,
                                    node_event_fifo_t *fifo,
                                    uint32_t *inout_uplink_counter);

/**
 * @brief Transmit UP_HEARTBEAT_ACK packet to Gateway.
 *
 * @param[in] node_id Sensor node ID.
 * @param[in] seq Heartbeat sequence number received or timestamp.
 * @return ESP_OK on success, or error code on radio TX failure.
 */
esp_err_t node_send_heartbeat_ack(uint8_t node_id, uint16_t seq);

/**
 * @brief Listen for Gateway DOWN_HEARTBEAT_PROBE and respond with UP_HEARTBEAT_ACK.
 *
 * If DOWN_HEARTBEAT_PROBE is received, delays for slotted backoff (node_id * 40 ms),
 * transmits UP_HEARTBEAT_ACK, and listens for DOWN_REVOKE (400 ms).
 *
 * @param[in] cfg Pointer to node MAC configuration (non-NULL).
 * @param[in] wait_ms Time to wait for probe in milliseconds.
 * @return ESP_OK on probe received and ACK sent,
 *         ESP_ERR_INVALID_STATE if node was revoked during revoke listen,
 *         ESP_ERR_TIMEOUT if no probe received within wait_ms,
 *         or error code on failure.
 */
esp_err_t node_listen_and_respond_probe(const node_mac_config_t *cfg, uint32_t wait_ms);

/**
 * @brief Open a single RX window to listen for DOWN_REVOKE message from Gateway.
 *
 * @param[in] cfg Pointer to node MAC configuration (non-NULL).
 * @param[in] wait_ms RX window timeout in milliseconds.
 * @param[out] out_revoked Set to true if DOWN_REVOKE was successfully decrypted and verified.
 * @return ESP_OK on check completion, or error code on invalid args / radio failure.
 */
esp_err_t node_listen_downlink_revoke(const node_mac_config_t *cfg, uint32_t wait_ms, bool *out_revoked);

#ifdef __cplusplus
}
#endif
