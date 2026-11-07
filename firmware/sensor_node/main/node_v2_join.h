#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "lora_mac.h"
#include "lora_mac_join_crypto.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_V2_JOIN_MAX_CAD_RETRIES       (3U)
#define NODE_V2_JOIN_DEFAULT_BACKOFF_MS    (50U)
#define NODE_V2_JOIN_GRANT_TIMEOUT_MS      (1000U)
#define NODE_V2_JOIN_FINISH_TIMEOUT_MS     (1000U)
#define NODE_V2_JOIN_NVS_NAMESPACE         "node_join"
#define NODE_V2_JOIN_NVS_KEY_COUNTER       "join_ctr"

typedef enum {
    NODE_V2_JOIN_STATE_UNJOINED = 0,
    NODE_V2_JOIN_STATE_CAD_EVAL,
    NODE_V2_JOIN_STATE_COUNTER_COMMIT,
    NODE_V2_JOIN_STATE_HELLO_TX,
    NODE_V2_JOIN_STATE_GRANT_RX,
    NODE_V2_JOIN_STATE_CONFIRM_TX,
    NODE_V2_JOIN_STATE_FINISH_RX,
    NODE_V2_JOIN_STATE_READY_TX,
    NODE_V2_JOIN_STATE_INSTALLED_INACTIVE,
    NODE_V2_JOIN_STATE_ABORTED,
    NODE_V2_JOIN_STATE_LOCKED_OUT,
} node_v2_join_state_t;

typedef struct {
    esp_err_t (*radio_cad)(bool *out_activity_detected);
    esp_err_t (*radio_tx)(const uint8_t *payload, uint8_t length, uint32_t timeout_ms);
    esp_err_t (*radio_rx_single)(uint32_t timeout_ms);
    esp_err_t (*radio_read_frame)(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms);
    esp_err_t (*radio_sleep)(void);
    esp_err_t (*radio_standby)(void);
    uint32_t (*get_time_ms)(void);
    void (*delay_ms)(uint32_t ms);
} node_v2_join_radio_hal_t;

typedef struct {
    uint32_t network_id;
    uint16_t device_generation;
    uint8_t  device_mac[6];
    uint8_t  target_gw_id;
    uint8_t  k_join[32];
    uint8_t  max_cad_retries;
    uint32_t cad_backoff_base_ms;
    uint32_t grant_listen_timeout_ms;
    uint32_t finish_listen_timeout_ms;
} node_v2_join_config_t;

typedef struct {
    node_v2_join_state_t state;
    uint8_t assigned_node_id;
    uint32_t committed_join_counter;
    uint8_t last_finish31[31];
    lora_mac_session_keys_t session_keys;
    bool radio_permanently_locked;
} node_v2_join_context_t;

/**
 * @brief Get default configuration for Node V2 Join.
 */
esp_err_t node_v2_join_get_default_config(node_v2_join_config_t *cfg);

/**
 * @brief Initialize Node V2 Join context.
 */
esp_err_t node_v2_join_init(node_v2_join_context_t *ctx);

/**
 * @brief Commit incremented monotonic counter into NVS flash before RF transmission (DEC-SEC-06).
 *
 * If rollback is detected (read counter < previously committed) or NVS read/write fails,
 * sets radio_permanently_locked = true and returns ESP_ERR_INVALID_STATE.
 *
 * @param[in,out] ctx  Join context.
 * @param[out]    out_counter  Committed counter value.
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE on rollback or lock, or NVS error.
 */
esp_err_t node_v2_join_commit_counter(node_v2_join_context_t *ctx, uint32_t *out_counter);

/**
 * @brief Execute complete Over-the-Air V2 Join handshake campaign.
 *
 * Steps:
 * 1. CAD on channel (up to max_cad_retries, exponential backoff). If 3 consecutive busy detects -> sleep.
 * 2. Monotonic NVS counter commit before emission (DEC-SEC-06).
 * 3. Phase 1: Generate ephemeral X25519 keypair and transmit UP_JOIN_HELLO (0x45, 68B).
 * 4. Phase 2: Receive DOWN_JOIN_GRANT (0x46, 66B). Verify GRANT_PROOF.
 *             Compute Z = X25519(priv_node, pub_gw). DEC-SEC-07: check Z != 0^32.
 *             Derive operational session keys. Zeroize priv_node and Z immediately (MEM-005).
 * 5. Phase 3: Transmit UP_JOIN_KEY_CONFIRM (0x47, 31B).
 * 6. Phase 4a: Receive DOWN_JOIN_FINISH (0x48, 31B). Verify GW_FINISH_TAG and BACKEND_FINISH_PROOF.
 * 7. Phase 4b: Transmit UP_JOIN_READY (0x49, 31B) with dual verification tags binding FINISH31.
 *              Transition session to INSTALLED_INACTIVE (DEC-SEC-05).
 *
 * @param[in]     cfg  Configuration parameters.
 * @param[in]     hal  Radio and timer HAL callbacks.
 * @param[in,out] ctx  Join state context.
 * @return ESP_OK on complete successful handshake, or esp_err_t failure code.
 */
esp_err_t node_v2_join_run(const node_v2_join_config_t *cfg,
                           const node_v2_join_radio_hal_t *hal,
                           node_v2_join_context_t *ctx);

/**
 * @brief Convert node join state to string for logging and verification.
 */
const char *node_v2_join_state_to_str(node_v2_join_state_t state);

#ifdef __cplusplus
}
#endif
