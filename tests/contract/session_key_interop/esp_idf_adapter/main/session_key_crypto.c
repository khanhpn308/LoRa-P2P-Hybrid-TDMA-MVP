#include "session_key_crypto.h"
#include <string.h>
#include "psa/crypto.h"

static void put_u16_be(uint8_t *buf, uint16_t val) {
    buf[0] = (uint8_t)((val >> 8) & 0xFF);
    buf[1] = (uint8_t)(val & 0xFF);
}

static void put_u32_be(uint8_t *buf, uint32_t val) {
    buf[0] = (uint8_t)((val >> 24) & 0xFF);
    buf[1] = (uint8_t)((val >> 16) & 0xFF);
    buf[2] = (uint8_t)((val >> 8) & 0xFF);
    buf[3] = (uint8_t)(val & 0xFF);
}

static void put_u64_be(uint8_t *buf, uint64_t val) {
    buf[0] = (uint8_t)((val >> 56) & 0xFF);
    buf[1] = (uint8_t)((val >> 48) & 0xFF);
    buf[2] = (uint8_t)((val >> 40) & 0xFF);
    buf[3] = (uint8_t)((val >> 32) & 0xFF);
    buf[4] = (uint8_t)((val >> 24) & 0xFF);
    buf[5] = (uint8_t)((val >> 16) & 0xFF);
    buf[6] = (uint8_t)((val >> 8) & 0xFF);
    buf[7] = (uint8_t)(val & 0xFF);
}

static sk_status_t append_lp(uint8_t *buf, size_t max_len, size_t *offset, const char *str) {
    if (!str) return SK_ERR_INVALID_PARAM;
    size_t s_len = strlen(str);
    if (s_len > 65535) return SK_ERR_INVALID_PARAM;
    if (*offset + 2 + s_len > max_len) return SK_ERR_BUFFER_TOO_SMALL;

    put_u16_be(buf + *offset, (uint16_t)s_len);
    *offset += 2;
    memcpy(buf + *offset, str, s_len);
    *offset += s_len;
    return SK_OK;
}

static sk_status_t append_bytes(uint8_t *buf, size_t max_len, size_t *offset, const uint8_t *data, size_t len) {
    if (!data) return SK_ERR_INVALID_PARAM;
    if (*offset + len > max_len) return SK_ERR_BUFFER_TOO_SMALL;
    memcpy(buf + *offset, data, len);
    *offset += len;
    return SK_OK;
}

sk_status_t sk_crypto_init(void) {
    psa_status_t status = psa_crypto_init();
    return (status == PSA_SUCCESS) ? SK_OK : SK_ERR_CRYPTO_INIT;
}

sk_status_t sk_build_install_aad(const sk_install_aad_params_t *params,
                                 uint8_t *out_buf,
                                 size_t max_out_len,
                                 size_t *out_len) {
    if (!params || !out_buf || !out_len) return SK_ERR_INVALID_PARAM;

    size_t off = 0;
    sk_status_t ret;

    // 1. LP("LP2P/MQTT/V1/KEY-INSTALL")
    ret = append_lp(out_buf, max_out_len, &off, "LP2P/MQTT/V1/KEY-INSTALL");
    if (ret != SK_OK) return ret;

    // 2. LP(topic)
    ret = append_lp(out_buf, max_out_len, &off, params->topic);
    if (ret != SK_OK) return ret;

    // 3. LP(schema_version)
    ret = append_lp(out_buf, max_out_len, &off, params->schema_version);
    if (ret != SK_OK) return ret;

    // 4. U8(install_protocol_version)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->install_protocol_version;

    // 5. U8(aad_version)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->aad_version;

    // 6. LP(gateway_id)
    ret = append_lp(out_buf, max_out_len, &off, params->gateway_id);
    if (ret != SK_OK) return ret;

    // 7. U8(target_gw_id)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->target_gw_id;

    // 8. MAC(device_mac) (6B)
    ret = append_bytes(out_buf, max_out_len, &off, params->device_mac, SK_MAC_SIZE);
    if (ret != SK_OK) return ret;

    // 9. U8(node_id)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->node_id;

    // 10. U8(key_id)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->key_id;

    // 11. UUID(session_id) (16B)
    ret = append_bytes(out_buf, max_out_len, &off, params->session_id, SK_UUID_SIZE);
    if (ret != SK_OK) return ret;

    // 12. UUID(install_id) (16B)
    ret = append_bytes(out_buf, max_out_len, &off, params->install_id, SK_UUID_SIZE);
    if (ret != SK_OK) return ret;

    // 13. U64(session_revision) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->session_revision);
    off += 8;

    // 14. U64(assignment_revision) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->assignment_revision);
    off += 8;

    // 15. SHA(session_context_hash) (32B)
    ret = append_bytes(out_buf, max_out_len, &off, params->session_context_hash, SK_SHA256_SIZE);
    if (ret != SK_OK) return ret;

    // 16. TIME(not_before) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->not_before_ms);
    off += 8;

    // 17. TIME(expires_at) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->expires_at_ms);
    off += 8;

    // 18. TIME(install_deadline) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->install_deadline_ms);
    off += 8;

    // 19. U32(wrap_key_id) (4B)
    if (off + 4 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u32_be(out_buf + off, params->wrap_key_id);
    off += 4;

    // 20. LP(crypto_suite)
    ret = append_lp(out_buf, max_out_len, &off, params->crypto_suite);
    if (ret != SK_OK) return ret;

    // 21. B64(nonce) (12B)
    ret = append_bytes(out_buf, max_out_len, &off, params->nonce, SK_NONCE_SIZE);
    if (ret != SK_OK) return ret;

    *out_len = off;
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
    if (!k_gw_wrap || !nonce || !ciphertext || !tag || !aad || !out_k_session_up || !out_k_session_dl) {
        return SK_ERR_INVALID_PARAM;
    }

    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_DECRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_GCM);
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 256);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, k_gw_wrap, SK_KEY_WRAP_SIZE, &key_id);
    if (status != PSA_SUCCESS) {
        return SK_ERR_CRYPTO_INIT;
    }

    uint8_t input_buf[SK_PLAINTEXT_SIZE + SK_TAG_SIZE];
    memcpy(input_buf, ciphertext, SK_PLAINTEXT_SIZE);
    memcpy(input_buf + SK_PLAINTEXT_SIZE, tag, SK_TAG_SIZE);

    uint8_t plaintext[SK_PLAINTEXT_SIZE];
    size_t plaintext_len = 0;

    status = psa_aead_decrypt(key_id,
                              PSA_ALG_GCM,
                              nonce, SK_NONCE_SIZE,
                              aad, aad_len,
                              input_buf, sizeof(input_buf),
                              plaintext, sizeof(plaintext),
                              &plaintext_len);

    psa_destroy_key(key_id);
    memset(input_buf, 0, sizeof(input_buf));

    if (status != PSA_SUCCESS) {
        memset(plaintext, 0, sizeof(plaintext));
        return SK_ERR_GCM_AUTH_FAILED;
    }

    if (plaintext_len != SK_PLAINTEXT_SIZE) {
        memset(plaintext, 0, sizeof(plaintext));
        return SK_ERR_INVALID_PARAM;
    }

    memcpy(out_k_session_up, plaintext, SK_SESSION_KEY_SIZE);
    memcpy(out_k_session_dl, plaintext + SK_SESSION_KEY_SIZE, SK_SESSION_KEY_SIZE);
    memset(plaintext, 0, sizeof(plaintext));

    return SK_OK;
}

sk_status_t sk_wrap_session_keys(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                 const uint8_t nonce[SK_NONCE_SIZE],
                                 const uint8_t k_session_up[SK_SESSION_KEY_SIZE],
                                 const uint8_t k_session_dl[SK_SESSION_KEY_SIZE],
                                 const uint8_t *aad,
                                 size_t aad_len,
                                 uint8_t out_ciphertext[SK_PLAINTEXT_SIZE],
                                 uint8_t out_tag[SK_TAG_SIZE]) {
    if (!k_gw_wrap || !nonce || !k_session_up || !k_session_dl || !aad || !out_ciphertext || !out_tag) {
        return SK_ERR_INVALID_PARAM;
    }

    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_GCM);
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 256);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, k_gw_wrap, SK_KEY_WRAP_SIZE, &key_id);
    if (status != PSA_SUCCESS) {
        return SK_ERR_CRYPTO_INIT;
    }

    uint8_t plaintext[SK_PLAINTEXT_SIZE];
    memcpy(plaintext, k_session_up, SK_SESSION_KEY_SIZE);
    memcpy(plaintext + SK_SESSION_KEY_SIZE, k_session_dl, SK_SESSION_KEY_SIZE);

    uint8_t output_buf[SK_PLAINTEXT_SIZE + SK_TAG_SIZE];
    size_t output_len = 0;

    status = psa_aead_encrypt(key_id,
                              PSA_ALG_GCM,
                              nonce, SK_NONCE_SIZE,
                              aad, aad_len,
                              plaintext, sizeof(plaintext),
                              output_buf, sizeof(output_buf),
                              &output_len);

    psa_destroy_key(key_id);
    memset(plaintext, 0, sizeof(plaintext));

    if (status != PSA_SUCCESS || output_len != sizeof(output_buf)) {
        return SK_ERR_GCM_AUTH_FAILED;
    }

    memcpy(out_ciphertext, output_buf, SK_PLAINTEXT_SIZE);
    memcpy(out_tag, output_buf + SK_PLAINTEXT_SIZE, SK_TAG_SIZE);
    memset(output_buf, 0, sizeof(output_buf));

    return SK_OK;
}

static sk_status_t hmac_sha256(const uint8_t *key, size_t key_len,
                              const uint8_t *data, size_t data_len,
                              uint8_t out_mac[32]) {
    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attr, PSA_ALG_HMAC(PSA_ALG_SHA_256));
    psa_set_key_type(&attr, PSA_KEY_TYPE_HMAC);
    psa_set_key_bits(&attr, key_len * 8);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, key, key_len, &key_id);
    if (status != PSA_SUCCESS) {
        return SK_ERR_CRYPTO_INIT;
    }

    size_t mac_len = 0;
    status = psa_mac_compute(key_id, PSA_ALG_HMAC(PSA_ALG_SHA_256),
                             data, data_len,
                             out_mac, 32, &mac_len);
    psa_destroy_key(key_id);

    return (status == PSA_SUCCESS && mac_len == 32) ? SK_OK : SK_ERR_HMAC_FAILED;
}

sk_status_t sk_derive_k_ack(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                            uint32_t wrap_key_id,
                            const char *gateway_id,
                            uint8_t out_k_ack[32]) {
    if (!k_gw_wrap || !gateway_id || !out_k_ack) return SK_ERR_INVALID_PARAM;

    // Step 1: ACK_PRK = HMAC-SHA256(salt="LP2P/MQTT/V1/ACK-SALT", IKM=K_GW_WRAP)
    const char *salt_str = "LP2P/MQTT/V1/ACK-SALT";
    uint8_t prk[32];
    sk_status_t ret = hmac_sha256((const uint8_t *)salt_str, strlen(salt_str),
                                  k_gw_wrap, SK_KEY_WRAP_SIZE, prk);
    if (ret != SK_OK) return ret;

    // Step 2: Build info = LP("LP2P/MQTT/V1/KEY-INSTALL-ACK") || U32(wrap_key_id) || LP(gateway_id)
    uint8_t info_buf[256];
    size_t off = 0;
    ret = append_lp(info_buf, sizeof(info_buf), &off, "LP2P/MQTT/V1/KEY-INSTALL-ACK");
    if (ret != SK_OK) return ret;

    if (off + 4 > sizeof(info_buf)) return SK_ERR_BUFFER_TOO_SMALL;
    put_u32_be(info_buf + off, wrap_key_id);
    off += 4;

    ret = append_lp(info_buf, sizeof(info_buf), &off, gateway_id);
    if (ret != SK_OK) return ret;

    // HKDF-Expand for 32 bytes: HMAC-SHA256(PRK, info || 0x01)
    if (off + 1 > sizeof(info_buf)) return SK_ERR_BUFFER_TOO_SMALL;
    info_buf[off++] = 0x01;

    ret = hmac_sha256(prk, 32, info_buf, off, out_k_ack);
    memset(prk, 0, sizeof(prk));
    memset(info_buf, 0, sizeof(info_buf));

    return ret;
}

sk_status_t sk_build_ack_transcript(const sk_ack_transcript_params_t *params,
                                    uint8_t *out_buf,
                                    size_t max_out_len,
                                    size_t *out_len) {
    if (!params || !out_buf || !out_len) return SK_ERR_INVALID_PARAM;

    size_t off = 0;
    sk_status_t ret;

    // 1. LP("LP2P/MQTT/V1/M-ACK")
    ret = append_lp(out_buf, max_out_len, &off, "LP2P/MQTT/V1/M-ACK");
    if (ret != SK_OK) return ret;

    // 2. LP(topic)
    ret = append_lp(out_buf, max_out_len, &off, params->topic);
    if (ret != SK_OK) return ret;

    // 3. LP(schema_version)
    ret = append_lp(out_buf, max_out_len, &off, params->schema_version);
    if (ret != SK_OK) return ret;

    // 4. U8(ack_protocol_version)
    if (off + 1 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    out_buf[off++] = params->ack_protocol_version;

    // 5. LP(gateway_id)
    ret = append_lp(out_buf, max_out_len, &off, params->gateway_id);
    if (ret != SK_OK) return ret;

    // 6. UUID(install_id) (16B)
    ret = append_bytes(out_buf, max_out_len, &off, params->install_id, SK_UUID_SIZE);
    if (ret != SK_OK) return ret;

    // 7. UUID(session_id) (16B)
    ret = append_bytes(out_buf, max_out_len, &off, params->session_id, SK_UUID_SIZE);
    if (ret != SK_OK) return ret;

    // 8. U64(session_revision) (8B)
    if (off + 8 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u64_be(out_buf + off, params->session_revision);
    off += 8;

    // 9. U32(wrap_key_id) (4B)
    if (off + 4 > max_out_len) return SK_ERR_BUFFER_TOO_SMALL;
    put_u32_be(out_buf + off, params->wrap_key_id);
    off += 4;

    // 10. LP(status)
    ret = append_lp(out_buf, max_out_len, &off, params->status);
    if (ret != SK_OK) return ret;

    // 11. LP(reason_code)
    ret = append_lp(out_buf, max_out_len, &off, params->reason_code);
    if (ret != SK_OK) return ret;

    *out_len = off;
    return SK_OK;
}

sk_status_t sk_compute_ack_tag(const uint8_t k_ack[32],
                               const uint8_t *m_ack,
                               size_t m_ack_len,
                               uint8_t out_tag[SK_ACK_TAG_SIZE]) {
    if (!k_ack || !m_ack || !out_tag) return SK_ERR_INVALID_PARAM;

    uint8_t full_mac[32];
    sk_status_t ret = hmac_sha256(k_ack, 32, m_ack, m_ack_len, full_mac);
    if (ret != SK_OK) return ret;

    memcpy(out_tag, full_mac, SK_ACK_TAG_SIZE);
    memset(full_mac, 0, sizeof(full_mac));
    return SK_OK;
}

sk_status_t sk_verify_ack_tag(const uint8_t k_ack[32],
                              const uint8_t *m_ack,
                              size_t m_ack_len,
                              const uint8_t expected_tag[SK_ACK_TAG_SIZE]) {
    if (!k_ack || !m_ack || !expected_tag) return SK_ERR_INVALID_PARAM;

    uint8_t computed[SK_ACK_TAG_SIZE];
    sk_status_t ret = sk_compute_ack_tag(k_ack, m_ack, m_ack_len, computed);
    if (ret != SK_OK) return ret;

    // Constant-time compare
    volatile uint8_t diff = 0;
    for (size_t i = 0; i < SK_ACK_TAG_SIZE; i++) {
        diff |= (computed[i] ^ expected_tag[i]);
    }
    memset(computed, 0, sizeof(computed));

    return (diff == 0) ? SK_OK : SK_ERR_TAG_MISMATCH;
}
