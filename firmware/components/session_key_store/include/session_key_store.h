#ifndef SESSION_KEY_STORE_H
#define SESSION_KEY_STORE_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include "esp_err.h"
#include "session_key_crypto.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SK_STORE_MAX_NODES 15
#define SK_STORE_NVS_NAMESPACE "sk_store"

typedef enum {
    SK_RECORD_STATE_FREE = 0,
    SK_RECORD_STATE_INSTALL_PENDING = 1,
    SK_RECORD_STATE_INSTALLED_INACTIVE = 2,
    SK_RECORD_STATE_WAIT_TDMA = 3,
    SK_RECORD_STATE_ACTIVE = 4,
    SK_RECORD_STATE_REVOKED = 5,
    SK_RECORD_STATE_EXPIRED = 6
} sk_record_state_t;

typedef struct {
    uint8_t session_id[SK_UUID_SIZE];
    uint8_t install_id[SK_UUID_SIZE];
    uint8_t node_id;
    uint8_t key_id;
    uint64_t session_revision;
    uint64_t assignment_revision;
    uint8_t k_session_up[SK_SESSION_KEY_SIZE];
    uint8_t k_session_dl[SK_SESSION_KEY_SIZE];
    uint64_t not_before_ms;
    uint64_t expires_at_ms;
    sk_record_state_t state;
} sk_session_record_t;

/**
 * @brief Initialize the session key store subsystem and restore records from NVS.
 *
 * @return ESP_OK on success, or an esp_err_t failure code.
 */
esp_err_t session_key_store_init(void);

/**
 * @brief Unwrap and durably persist an incoming SESSION_KEY_INSTALL envelope into INSTALLED_INACTIVE.
 *
 * Enforces:
 * - Anti-replay / anti-rollback: session_revision > current_committed_revision.
 * - Idempotency: identical install_id & session_id in INSTALLED_INACTIVE returns ESP_OK without re-writing NVS.
 * - GCM tag authentication: failure aborts before modifying NVS or slot state.
 * - Durable NVS commit before returning success.
 * - Radio transmission rights remain strictly disabled in INSTALLED_INACTIVE.
 *
 * @param params Parsed AAD parameters for canonical binary reconstruction.
 * @param k_gw_wrap 32-byte Gateway wrapping key.
 * @param ciphertext 64-byte AES-256-GCM ciphertext.
 * @param tag 16-byte AES-256-GCM authentication tag.
 * @param now_ms Current UTC timestamp in milliseconds (0 if untrusted/unchecked).
 * @return ESP_OK on success, ESP_ERR_INVALID_VERSION on rollback attempt, ESP_ERR_INVALID_CRC on tag failure.
 */
esp_err_t session_key_store_install(const sk_install_aad_params_t *params,
                                   const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                   const uint8_t ciphertext[SK_PLAINTEXT_SIZE],
                                   const uint8_t tag[SK_TAG_SIZE],
                                   uint64_t now_ms);

/**
 * @brief Transition a staged session from INSTALLED_INACTIVE to WAIT_TDMA.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @return ESP_OK on success, or error code.
 */
esp_err_t session_key_store_stage_wait_tdma(uint8_t node_id);

/**
 * @brief Atomically promote a staged session (INSTALLED_INACTIVE or WAIT_TDMA) to ACTIVE.
 *
 * Checks time validity (now_ms >= not_before && now_ms < expires_at).
 * Durably commits the new ACTIVE record and cleans the staging slot in NVS and RAM.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @param now_ms Current UTC timestamp in milliseconds.
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE if no staged session, ESP_ERR_INVALID_ARG if expired/not-yet-valid.
 */
esp_err_t session_key_store_promote(uint8_t node_id, uint64_t now_ms);

/**
 * @brief Revoke any active or staged keys for a node, zeroizing sensitive buffers and updating NVS.
 *
 * Retains high_water_revision in NVS to prevent replay of revoked revisions.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @return ESP_OK on success, or error code.
 */
esp_err_t session_key_store_revoke(uint8_t node_id);

/**
 * @brief Expire an active session if now_ms >= expires_at_ms, zeroizing keys.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @param now_ms Current UTC timestamp in milliseconds.
 * @return ESP_OK on success, or error code.
 */
esp_err_t session_key_store_expire(uint8_t node_id, uint64_t now_ms);

/**
 * @brief Retrieve a copy of the ACTIVE session record for a node.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @param out_record Output record destination.
 * @return ESP_OK on success, ESP_ERR_NOT_FOUND if no active session.
 */
esp_err_t session_key_store_get_active(uint8_t node_id, sk_session_record_t *out_record);

/**
 * @brief Retrieve a copy of the staged session record for a node.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @param out_record Output record destination.
 * @return ESP_OK on success, ESP_ERR_NOT_FOUND if no staged session.
 */
esp_err_t session_key_store_get_staging(uint8_t node_id, sk_session_record_t *out_record);

/**
 * @brief Retrieve the monotonic high-water mark revision for a node.
 *
 * @param node_id Target node ID (1..SK_STORE_MAX_NODES).
 * @param out_rev Output revision pointer.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if invalid node.
 */
esp_err_t session_key_store_get_revision(uint8_t node_id, uint64_t *out_rev);

/**
 * @brief Generate authenticated ACK transcript and HMAC-SHA256 tag.
 *
 * @param k_gw_wrap Gateway wrapping key.
 * @param ack_params ACK parameters.
 * @param out_m_ack Output buffer for M_ACK binary transcript.
 * @param max_m_ack_len Capacity of out_m_ack.
 * @param out_m_ack_len Number of bytes written to out_m_ack.
 * @param out_ack_tag Output 16-byte HMAC tag.
 * @return ESP_OK on success, or error code.
 */
esp_err_t session_key_store_generate_ack(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                        const sk_ack_transcript_params_t *ack_params,
                                        uint8_t *out_m_ack,
                                        size_t max_m_ack_len,
                                        size_t *out_m_ack_len,
                                        uint8_t out_ack_tag[SK_ACK_TAG_SIZE]);

/**
 * @brief Clear and zeroize all in-memory slots.
 */
void session_key_store_clear(void);

#ifdef __cplusplus
}
#endif

#endif // SESSION_KEY_STORE_H
