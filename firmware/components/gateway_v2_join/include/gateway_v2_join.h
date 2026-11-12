#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "lora_mac.h"
#include "lora_mac_join_crypto.h"
#include "gateway_transport.h"
#include "session_key_store.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS  15
#define GATEWAY_V2_JOIN_DEFAULT_EPOCH         "01234567-89ab-cdef-0123-456789abcdef"

typedef struct {
    char gateway_id[GATEWAY_ID_MAX_LEN];
    char gateway_epoch[37];
    uint8_t target_gw_id;
    uint32_t network_id;
} gateway_v2_join_config_t;

typedef struct {
    bool active;
    uint8_t device_mac[6];
    uint8_t assigned_node_id;
    uint32_t join_counter;
    uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    uint8_t grant_raw[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
    uint8_t th[32];
    lora_mac_session_keys_t session_keys;
    uint8_t finish31[31];
} gateway_v2_pending_join_t;

typedef struct {
    gateway_v2_join_config_t config;
    uint64_t event_seq;
    gateway_v2_pending_join_t pending_joins[GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS];
} gateway_v2_join_engine_t;

/**
 * @brief Initialize Gateway V2 Join Relay Engine.
 */
esp_err_t gateway_v2_join_init(gateway_v2_join_engine_t *engine, const gateway_v2_join_config_t *cfg);

/**
 * @brief Build MQTT Join Relay JSON payload matching contracts/mqtt/schemas/join-hello.schema.json.
 *
 * @param[in]  engine        Engine instance.
 * @param[in]  hello_raw     68-byte UP_JOIN_HELLO frame.
 * @param[in]  target_gw_id  Target Gateway ID.
 * @param[in]  rssi          Received signal strength (-140..0).
 * @param[in]  snr           Signal-to-noise ratio (-30.0..30.0).
 * @param[in]  rx_mono_us    Gateway local monotonic microseconds.
 * @param[out] out_json      Destination buffer.
 * @param[in]  max_json_len  Size of destination buffer.
 * @param[out] out_written   Bytes written.
 * @return ESP_OK on success, ESP_ERR_NO_MEM if buffer too small, ESP_ERR_INVALID_ARG on bad params.
 */
esp_err_t gateway_v2_join_build_relay_json(gateway_v2_join_engine_t *engine,
                                           const uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO],
                                           uint8_t target_gw_id,
                                           int16_t rssi,
                                           float snr,
                                           uint64_t rx_mono_us,
                                           char *out_json,
                                           size_t max_json_len,
                                           size_t *out_written);

/**
 * @brief Process incoming UP_JOIN_HELLO (0x45, 68B) from LoRa RF.
 *
 * Steps:
 * 1. Validate framing, target_gw_id, MAC.
 * 2. Generate ephemeral X25519 keypair on Gateway.
 * 3. Compute shared secret Z = X25519(priv_gw, node_pub). Check RFC 7748 Z != 0^32.
 * 4. Assemble DOWN_JOIN_GRANT (0x46, 66B) with assigned Node ID (1..15).
 * 5. Compute TH and derive operational session keys.
 * 6. Commit derived session keys to INSTALLED_INACTIVE in session_key_store.
 * 7. Zeroize priv_gw and Z immediately.
 * 8. Build and publish MQTT Join Relay envelope to iot/v1/gw/{id}/uplink/join-hello.
 * 9. Output assembled DOWN_JOIN_GRANT frame for RF transmission.
 *
 * @param[in,out] engine       Engine instance.
 * @param[in]     hello_raw    68-byte UP_JOIN_HELLO frame.
 * @param[in]     hello_len    Length of frame (must be 68).
 * @param[in]     rssi         Measured RSSI.
 * @param[in]     snr          Measured SNR.
 * @param[in]     rx_mono_us   Monotonic arrival timestamp.
 * @param[in]     backend_grant_proof 16-byte Backend proof under K_JGRANT (or NULL for edge grant).
 * @param[out]    out_grant    Destination buffer for 66-byte DOWN_JOIN_GRANT.
 * @param[out]    out_grant_len Written grant length.
 * @return ESP_OK on success, or esp_err_t failure code.
 */
esp_err_t gateway_v2_join_handle_hello(gateway_v2_join_engine_t *engine,
                                       const uint8_t *hello_raw,
                                       size_t hello_len,
                                       int16_t rssi,
                                       float snr,
                                       uint64_t rx_mono_us,
                                       const uint8_t backend_grant_proof[16],
                                       uint8_t out_grant[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT],
                                       size_t *out_grant_len);

/**
 * @brief Process incoming UP_JOIN_HELLO with an explicitly assigned node_id approved by Backend/User.
 */
esp_err_t gateway_v2_join_handle_hello_with_id(gateway_v2_join_engine_t *engine,
                                               const uint8_t *hello_raw,
                                               size_t hello_len,
                                               int16_t rssi,
                                               float snr,
                                               uint64_t rx_mono_us,
                                               const uint8_t backend_grant_proof[16],
                                               uint8_t override_node_id,
                                               uint8_t out_grant[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT],
                                               size_t *out_grant_len);

/**
 * @brief Process incoming UP_JOIN_KEY_CONFIRM (0x47, 31B) from LoRa RF.
 *
 * Verifies GW_KC_TAG8 under K_KC_UP, generates DOWN_JOIN_FINISH (0x48, 31B) with GW_FINISH_TAG8.
 *
 * @param[in,out] engine         Engine instance.
 * @param[in]     confirm_raw    31-byte UP_JOIN_KEY_CONFIRM frame.
 * @param[in]     confirm_len    Length (must be 31).
 * @param[in]     backend_finish_proof 16-byte Backend proof under K_JFINISH (or NULL).
 * @param[out]    out_finish     Destination buffer for 31-byte DOWN_JOIN_FINISH.
 * @param[out]    out_finish_len Written length.
 * @return ESP_OK on success, ESP_ERR_INVALID_CRC on tag failure.
 */
esp_err_t gateway_v2_join_handle_confirm(gateway_v2_join_engine_t *engine,
                                         const uint8_t *confirm_raw,
                                         size_t confirm_len,
                                         const uint8_t backend_finish_proof[16],
                                         uint8_t out_finish[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH],
                                         size_t *out_finish_len);

/**
 * @brief Process incoming UP_JOIN_READY (0x49, 31B) from LoRa RF.
 *
 * Verifies GW_READY_TAG8 under K_KC_UP. Preserves keys in INSTALLED_INACTIVE state (DEC-SEC-05)
 * without enabling DATA slot transmission prematurely.
 *
 * @param[in,out] engine     Engine instance.
 * @param[in]     ready_raw  31-byte UP_JOIN_READY frame.
 * @param[in]     ready_len  Length (must be 31).
 * @return ESP_OK on valid tag and session readiness, ESP_ERR_INVALID_CRC on tag mismatch.
 */
esp_err_t gateway_v2_join_handle_ready(gateway_v2_join_engine_t *engine,
                                       const uint8_t *ready_raw,
                                       size_t ready_len);

/**
 * @brief Build 20-byte DOWN_JOIN_WAIT (0x51) frame from cached UP_JOIN_HELLO.
 *
 * @param[in]  engine        Engine instance.
 * @param[in]  hello_raw     68-byte UP_JOIN_HELLO frame.
 * @param[in]  hello_len     Length of frame (must be 68).
 * @param[in]  auth_tag8     Optional 8-byte auth tag (or NULL for zeroed tag).
 * @param[out] out_wait      Destination buffer for 20-byte DOWN_JOIN_WAIT.
 * @param[out] out_wait_len  Written length.
 * @return ESP_OK on success, or esp_err_t failure code.
 */
esp_err_t gateway_v2_join_build_wait(gateway_v2_join_engine_t *engine,
                                     const uint8_t *hello_raw,
                                     size_t hello_len,
                                     const uint8_t auth_tag8[8],
                                     uint8_t out_wait[LORA_MAC_V2_LEN_DOWN_JOIN_WAIT],
                                     size_t *out_wait_len);

/**
 * @brief Build 20-byte DOWN_JOIN_REJECT (0x52) frame from cached UP_JOIN_HELLO.
 *
 * @param[in]  engine          Engine instance.
 * @param[in]  hello_raw       68-byte UP_JOIN_HELLO frame.
 * @param[in]  hello_len       Length of frame (must be 68).
 * @param[in]  auth_tag8       Optional 8-byte auth tag (or NULL for zeroed tag).
 * @param[out] out_reject      Destination buffer for 20-byte DOWN_JOIN_REJECT.
 * @param[out] out_reject_len  Written length.
 * @return ESP_OK on success, or esp_err_t failure code.
 */
esp_err_t gateway_v2_join_build_reject(gateway_v2_join_engine_t *engine,
                                       const uint8_t *hello_raw,
                                       size_t hello_len,
                                       const uint8_t auth_tag8[8],
                                       uint8_t out_reject[LORA_MAC_V2_LEN_DOWN_JOIN_REJECT],
                                       size_t *out_reject_len);

#ifdef __cplusplus
}
#endif
