#ifndef SESSION_KEY_CRYPTO_H
#define SESSION_KEY_CRYPTO_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#define SK_KEY_WRAP_SIZE 32
#define SK_NONCE_SIZE 12
#define SK_SESSION_KEY_SIZE 32
#define SK_PLAINTEXT_SIZE 64
#define SK_TAG_SIZE 16
#define SK_ACK_TAG_SIZE 16
#define SK_UUID_SIZE 16
#define SK_MAC_SIZE 6
#define SK_SHA256_SIZE 32

typedef struct {
    const char *topic;
    const char *schema_version;
    uint8_t install_protocol_version;
    uint8_t aad_version;
    const char *gateway_id;
    uint8_t target_gw_id;
    const uint8_t device_mac[SK_MAC_SIZE];
    uint8_t node_id;
    uint8_t key_id;
    const uint8_t session_id[SK_UUID_SIZE];
    const uint8_t install_id[SK_UUID_SIZE];
    uint64_t session_revision;
    uint64_t assignment_revision;
    const uint8_t session_context_hash[SK_SHA256_SIZE];
    uint64_t not_before_ms;
    uint64_t expires_at_ms;
    uint64_t install_deadline_ms;
    uint32_t wrap_key_id;
    const char *crypto_suite;
    const uint8_t nonce[SK_NONCE_SIZE];
} sk_install_aad_params_t;

typedef struct {
    const char *topic;
    const char *schema_version;
    uint8_t ack_protocol_version;
    const char *gateway_id;
    const uint8_t install_id[SK_UUID_SIZE];
    const uint8_t session_id[SK_UUID_SIZE];
    uint64_t session_revision;
    uint32_t wrap_key_id;
    const char *status;
    const char *reason_code;
} sk_ack_transcript_params_t;

typedef enum {
    SK_OK = 0,
    SK_ERR_INVALID_PARAM = -1,
    SK_ERR_BUFFER_TOO_SMALL = -2,
    SK_ERR_CRYPTO_INIT = -3,
    SK_ERR_GCM_AUTH_FAILED = -4,
    SK_ERR_HMAC_FAILED = -5,
    SK_ERR_TAG_MISMATCH = -6,
} sk_status_t;

// Initialize crypto subsystem (calls psa_crypto_init)
sk_status_t sk_crypto_init(void);

// Build canonical binary Install AAD V1
sk_status_t sk_build_install_aad(const sk_install_aad_params_t *params,
                                 uint8_t *out_buf,
                                 size_t max_out_len,
                                 size_t *out_len);

// AES-256-GCM Unwrap (Gateway Consumer role)
sk_status_t sk_unwrap_session_keys(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                   const uint8_t nonce[SK_NONCE_SIZE],
                                   const uint8_t ciphertext[SK_PLAINTEXT_SIZE],
                                   const uint8_t tag[SK_TAG_SIZE],
                                   const uint8_t *aad,
                                   size_t aad_len,
                                   uint8_t out_k_session_up[SK_SESSION_KEY_SIZE],
                                   uint8_t out_k_session_dl[SK_SESSION_KEY_SIZE]);

// AES-256-GCM Wrap (Backend Producer role)
sk_status_t sk_wrap_session_keys(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                 const uint8_t nonce[SK_NONCE_SIZE],
                                 const uint8_t k_session_up[SK_SESSION_KEY_SIZE],
                                 const uint8_t k_session_dl[SK_SESSION_KEY_SIZE],
                                 const uint8_t *aad,
                                 size_t aad_len,
                                 uint8_t out_ciphertext[SK_PLAINTEXT_SIZE],
                                 uint8_t out_tag[SK_TAG_SIZE]);

// Derive K_ACK via HKDF-SHA256
sk_status_t sk_derive_k_ack(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                            uint32_t wrap_key_id,
                            const char *gateway_id,
                            uint8_t out_k_ack[32]);

// Build canonical binary ACK transcript M_ACK V1
sk_status_t sk_build_ack_transcript(const sk_ack_transcript_params_t *params,
                                    uint8_t *out_buf,
                                    size_t max_out_len,
                                    size_t *out_len);

// Compute 16-byte HMAC-SHA256 tag over M_ACK
sk_status_t sk_compute_ack_tag(const uint8_t k_ack[32],
                               const uint8_t *m_ack,
                               size_t m_ack_len,
                               uint8_t out_tag[SK_ACK_TAG_SIZE]);

// Constant-time verify 16-byte HMAC tag
sk_status_t sk_verify_ack_tag(const uint8_t k_ack[32],
                              const uint8_t *m_ack,
                              size_t m_ack_len,
                              const uint8_t expected_tag[SK_ACK_TAG_SIZE]);

#endif // SESSION_KEY_CRYPTO_H
