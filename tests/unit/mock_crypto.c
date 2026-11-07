#include "session_key_crypto.h"
#include <string.h>

static bool s_tag_valid = true;
static bool s_zeroize_check_failed = false;

void mock_crypto_set_tag_valid(bool valid) {
    s_tag_valid = valid;
}

bool mock_crypto_get_zeroize_status(void) {
    return !s_zeroize_check_failed;
}

sk_status_t sk_crypto_init(void) {
    return SK_OK;
}

sk_status_t sk_build_install_aad(const sk_install_aad_params_t *params,
                                 uint8_t *out_buf,
                                 size_t max_out_len,
                                 size_t *out_len) {
    if (!params || !out_buf || !out_len) return SK_ERR_INVALID_PARAM;
    if (max_out_len < 232) return SK_ERR_BUFFER_TOO_SMALL;
    // Fill dummy AAD with non-zero deterministic bytes
    memset(out_buf, 0xAA, 232);
    *out_len = 232;
    return SK_OK;
}

sk_status_t sk_unwrap_session_keys(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                   const uint8_t nonce[SK_NONCE_SIZE],
                                   const uint8_t ciphertext[SK_PLAINTEXT_SIZE],
                                   const uint8_t tag[SK_TAG_SIZE],
                                   const uint8_t *aad,
                                   size_t aad_len,
                                   uint8_t out_k_session_up[SK_SESSION_KEY_SIZE],
                                   uint8_t out_k_session_dl[SK_SESSION_KEY_SIZE]) {
    (void)k_gw_wrap;
    (void)nonce;
    (void)aad;
    (void)aad_len;

    if (!k_gw_wrap || !nonce || !ciphertext || !tag || !aad || !out_k_session_up || !out_k_session_dl) {
        return SK_ERR_INVALID_PARAM;
    }

    if (!s_tag_valid) {
        return SK_ERR_GCM_AUTH_FAILED;
    }

    // For mock testing: synthesize deterministic unwrapped keys from ciphertext
    memcpy(out_k_session_up, ciphertext, SK_SESSION_KEY_SIZE);
    memcpy(out_k_session_dl, ciphertext + SK_SESSION_KEY_SIZE, SK_SESSION_KEY_SIZE);
    return SK_OK;
}

sk_status_t sk_derive_k_ack(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                            uint32_t wrap_key_id,
                            const char *gateway_id,
                            uint8_t out_k_ack[32]) {
    (void)wrap_key_id;
    (void)gateway_id;
    if (!k_gw_wrap || !out_k_ack) return SK_ERR_INVALID_PARAM;
    memset(out_k_ack, 0x42, 32);
    return SK_OK;
}

sk_status_t sk_build_ack_transcript(const sk_ack_transcript_params_t *params,
                                    uint8_t *out_buf,
                                    size_t max_out_len,
                                    size_t *out_len) {
    if (!params || !out_buf || !out_len) return SK_ERR_INVALID_PARAM;
    if (max_out_len < 138) return SK_ERR_BUFFER_TOO_SMALL;
    memset(out_buf, 0x55, 138);
    *out_len = 138;
    return SK_OK;
}

sk_status_t sk_compute_ack_tag(const uint8_t k_ack[32],
                               const uint8_t *m_ack,
                               size_t m_ack_len,
                               uint8_t out_tag[SK_ACK_TAG_SIZE]) {
    (void)k_ack;
    (void)m_ack;
    (void)m_ack_len;
    if (!out_tag) return SK_ERR_INVALID_PARAM;
    memset(out_tag, 0x77, SK_ACK_TAG_SIZE);
    return SK_OK;
}

sk_status_t sk_verify_ack_tag(const uint8_t k_ack[32],
                              const uint8_t *m_ack,
                              size_t m_ack_len,
                              const uint8_t expected_tag[SK_ACK_TAG_SIZE]) {
    (void)k_ack;
    (void)m_ack;
    (void)m_ack_len;
    if (!expected_tag) return SK_ERR_INVALID_PARAM;
    return SK_OK;
}
