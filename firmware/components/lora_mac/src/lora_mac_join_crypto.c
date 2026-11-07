#include "lora_mac_join_crypto.h"
#include <string.h>

#if defined(ESP_PLATFORM)
#include "psa/crypto.h"
#include "mbedtls/platform_util.h"
#include "esp_random.h"
#include "esp_log.h"
#endif

void lora_mac_crypto_zeroize(void *buf, size_t len)
{
    if (buf == NULL || len == 0U) {
        return;
    }
#if defined(ESP_PLATFORM)
    mbedtls_platform_zeroize(buf, len);
#else
    volatile uint8_t *p = (volatile uint8_t *)buf;
    while (len--) {
        *p++ = 0U;
    }
#endif
}

int lora_mac_crypto_constant_time_memcmp(const void *a, const void *b, size_t len)
{
    if (a == NULL || b == NULL) {
        return -1;
    }
    const uint8_t *pa = (const uint8_t *)a;
    const uint8_t *pb = (const uint8_t *)b;
    uint8_t diff = 0U;
    for (size_t i = 0; i < len; i++) {
        diff |= (pa[i] ^ pb[i]);
    }
    return (diff == 0U) ? 0 : -1;
}

bool lora_mac_crypto_is_all_zero(const uint8_t *buf, size_t len)
{
    if (buf == NULL) {
        return true;
    }
    uint8_t acc = 0U;
    for (size_t i = 0; i < len; i++) {
        acc |= buf[i];
    }
    return (acc == 0U);
}

/* =========================================================================
 * SHA-256 and HMAC-SHA256 (FIPS 180-4 portable implementation)
 * ========================================================================= */

typedef struct {
    uint32_t state[8];
    uint64_t count;
    uint8_t buffer[64];
} sw_sha256_ctx_t;

static inline uint32_t rotr32(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32U - n));
}

#define CH(x, y, z)  (((x) & (y)) ^ (~(x) & (z)))
#define MAJ(x, y, z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define EP0(x)       (rotr32((x), 2) ^ rotr32((x), 13) ^ rotr32((x), 22))
#define EP1(x)       (rotr32((x), 6) ^ rotr32((x), 11) ^ rotr32((x), 25))
#define SIG0(x)      (rotr32((x), 7) ^ rotr32((x), 18) ^ ((x) >> 3))
#define SIG1(x)      (rotr32((x), 17) ^ rotr32((x), 19) ^ ((x) >> 10))

static const uint32_t K[64] = {
    0x428a2f98U, 0x71374491U, 0xb5c0fbcfU, 0xe9b5dba5U, 0x3956c25bU, 0x59f111f1U, 0x923f82a4U, 0xab1c5ed5U,
    0xd807aa98U, 0x12835b01U, 0x243185beU, 0x550c7dc3U, 0x72be5d74U, 0x80deb1feU, 0x9bdc06a7U, 0xc19bf174U,
    0xe49b69c1U, 0xefbe4786U, 0x0fc19dc6U, 0x240ca1ccU, 0x2de92c6fU, 0x4a7484aaU, 0x5cb0a9dcU, 0x76f988daU,
    0x983e5152U, 0xa831c66dU, 0xb00327c8U, 0xbf597fc7U, 0xc6e00bf3U, 0xd5a79147U, 0x06ca6351U, 0x14292967U,
    0x27b70a85U, 0x2e1b2138U, 0x4d2c6dfcU, 0x53380d13U, 0x650a7354U, 0x766a0abbU, 0x81c2c92eU, 0x92722c85U,
    0xa2bfe8a1U, 0xa81a664bU, 0xc24b8b70U, 0xc76c51a3U, 0xd192e819U, 0xd6990624U, 0xf40e3585U, 0x106aa070U,
    0x19a4c116U, 0x1e376c08U, 0x2748774cU, 0x34b0bcb5U, 0x391c0cb3U, 0x4ed8aa4aU, 0x5b9cca4fU, 0x682e6ff3U,
    0x748f82eeU, 0x78a5636fU, 0x84c87814U, 0x8cc70208U, 0x90befffaU, 0xa4506cebU, 0xbef9a3f7U, 0xc67178f2U
};

static void sw_sha256_transform(sw_sha256_ctx_t *ctx, const uint8_t data[64]) {
    uint32_t a, b, c, d, e, f, g, h, t1, t2, m[64];
    for (size_t i = 0, j = 0; i < 16; ++i, j += 4) {
        m[i] = ((uint32_t)data[j] << 24) | ((uint32_t)data[j + 1] << 16) |
               ((uint32_t)data[j + 2] << 8) | ((uint32_t)data[j + 3]);
    }
    for (size_t i = 16; i < 64; ++i) {
        m[i] = SIG1(m[i - 2]) + m[i - 7] + SIG0(m[i - 15]) + m[i - 16];
    }
    a = ctx->state[0]; b = ctx->state[1]; c = ctx->state[2]; d = ctx->state[3];
    e = ctx->state[4]; f = ctx->state[5]; g = ctx->state[6]; h = ctx->state[7];

    for (size_t i = 0; i < 64; ++i) {
        t1 = h + EP1(e) + CH(e, f, g) + K[i] + m[i];
        t2 = EP0(a) + MAJ(a, b, c);
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; b = a; a = t1 + t2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sw_sha256_init(sw_sha256_ctx_t *ctx) {
    ctx->count = 0;
    ctx->state[0] = 0x6a09e667U; ctx->state[1] = 0xbb67ae85U;
    ctx->state[2] = 0x3c6ef372U; ctx->state[3] = 0xa54ff53aU;
    ctx->state[4] = 0x510e527fU; ctx->state[5] = 0x9b05688cU;
    ctx->state[6] = 0x1f83d9abU; ctx->state[7] = 0x5be0cd19U;
}

static void sw_sha256_update(sw_sha256_ctx_t *ctx, const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; ++i) {
        ctx->buffer[ctx->count % 64] = data[i];
        ctx->count++;
        if ((ctx->count % 64) == 0) {
            sw_sha256_transform(ctx, ctx->buffer);
        }
    }
}

static void sw_sha256_final(sw_sha256_ctx_t *ctx, uint8_t hash[32]) {
    uint64_t total_bits = ctx->count * 8ULL;
    sw_sha256_update(ctx, (const uint8_t *)"\x80", 1);
    while ((ctx->count % 64) != 56) {
        sw_sha256_update(ctx, (const uint8_t *)"\x00", 1);
    }
    for (int i = 7; i >= 0; --i) {
        uint8_t b = (uint8_t)((total_bits >> (i * 8)) & 0xFFU);
        sw_sha256_update(ctx, &b, 1);
    }
    for (size_t i = 0; i < 8; ++i) {
        hash[i * 4]     = (uint8_t)((ctx->state[i] >> 24) & 0xFFU);
        hash[i * 4 + 1] = (uint8_t)((ctx->state[i] >> 16) & 0xFFU);
        hash[i * 4 + 2] = (uint8_t)((ctx->state[i] >> 8) & 0xFFU);
        hash[i * 4 + 3] = (uint8_t)(ctx->state[i] & 0xFFU);
    }
}

esp_err_t lora_mac_crypto_sha256(const uint8_t *data, size_t len, uint8_t out_hash[32])
{
    if ((data == NULL && len > 0) || out_hash == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sw_sha256_ctx_t ctx;
    sw_sha256_init(&ctx);
    if (len > 0) {
        sw_sha256_update(&ctx, data, len);
    }
    sw_sha256_final(&ctx, out_hash);
    lora_mac_crypto_zeroize(&ctx, sizeof(ctx));
    return ESP_OK;
}

esp_err_t lora_mac_crypto_hmac_sha256(const uint8_t *key, size_t key_len,
                                      const uint8_t *data, size_t data_len,
                                      uint8_t out_tag[32])
{
    if ((key == NULL && key_len > 0) || (data == NULL && data_len > 0) || out_tag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t k[64];
    memset(k, 0, sizeof(k));
    if (key_len > 64) {
        lora_mac_crypto_sha256(key, key_len, k);
    } else if (key_len > 0) {
        memcpy(k, key, key_len);
    }

    uint8_t k_ipad[64];
    uint8_t k_opad[64];
    for (size_t i = 0; i < 64; ++i) {
        k_ipad[i] = k[i] ^ 0x36U;
        k_opad[i] = k[i] ^ 0x5cU;
    }

    sw_sha256_ctx_t ctx;
    uint8_t inner_hash[32];

    sw_sha256_init(&ctx);
    sw_sha256_update(&ctx, k_ipad, 64);
    if (data_len > 0) {
        sw_sha256_update(&ctx, data, data_len);
    }
    sw_sha256_final(&ctx, inner_hash);

    sw_sha256_init(&ctx);
    sw_sha256_update(&ctx, k_opad, 64);
    sw_sha256_update(&ctx, inner_hash, 32);
    sw_sha256_final(&ctx, out_tag);

    lora_mac_crypto_zeroize(k, sizeof(k));
    lora_mac_crypto_zeroize(k_ipad, sizeof(k_ipad));
    lora_mac_crypto_zeroize(k_opad, sizeof(k_opad));
    lora_mac_crypto_zeroize(inner_hash, sizeof(inner_hash));
    lora_mac_crypto_zeroize(&ctx, sizeof(ctx));
    return ESP_OK;
}

esp_err_t lora_mac_crypto_hkdf_extract(const uint8_t *salt, size_t salt_len,
                                       const uint8_t *ikm, size_t ikm_len,
                                       uint8_t out_prk[32])
{
    if ((ikm == NULL && ikm_len > 0) || out_prk == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t null_salt[32];
    memset(null_salt, 0, sizeof(null_salt));
    const uint8_t *actual_salt = salt;
    size_t actual_salt_len = salt_len;
    if (actual_salt == NULL || actual_salt_len == 0) {
        actual_salt = null_salt;
        actual_salt_len = 32;
    }
    return lora_mac_crypto_hmac_sha256(actual_salt, actual_salt_len, ikm, ikm_len, out_prk);
}

esp_err_t lora_mac_crypto_hkdf_expand(const uint8_t *prk, size_t prk_len,
                                      const uint8_t *info, size_t info_len,
                                      uint8_t *out_okm, size_t okm_len)
{
    if (prk == NULL || prk_len < 32 || out_okm == NULL || okm_len == 0 || okm_len > (255 * 32)) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t n = (okm_len + 31) / 32;
    uint8_t t[32];
    size_t t_len = 0;
    size_t out_offset = 0;

    for (size_t i = 1; i <= n; i++) {
        uint8_t counter = (uint8_t)i;
        uint8_t input_block[64 + 128]; // Max info len in our protocol is small
        size_t block_len = 0;

        if (t_len > 0) {
            memcpy(input_block + block_len, t, t_len);
            block_len += t_len;
        }
        if (info != NULL && info_len > 0) {
            memcpy(input_block + block_len, info, info_len);
            block_len += info_len;
        }
        input_block[block_len++] = counter;

        esp_err_t err = lora_mac_crypto_hmac_sha256(prk, 32, input_block, block_len, t);
        lora_mac_crypto_zeroize(input_block, sizeof(input_block));
        if (err != ESP_OK) {
            lora_mac_crypto_zeroize(t, sizeof(t));
            return err;
        }
        t_len = 32;

        size_t to_copy = (okm_len - out_offset > 32) ? 32 : (okm_len - out_offset);
        memcpy(out_okm + out_offset, t, to_copy);
        out_offset += to_copy;
    }

    lora_mac_crypto_zeroize(t, sizeof(t));
    return ESP_OK;
}

/* =========================================================================
 * X25519 ECDH & Keypair
 * ========================================================================= */

#if defined(ESP_PLATFORM)

static bool s_psa_initialized = false;

static esp_err_t ensure_psa_init(void)
{
    if (!s_psa_initialized) {
        psa_status_t status = psa_crypto_init();
        if (status != PSA_SUCCESS) {
            return ESP_FAIL;
        }
        s_psa_initialized = true;
    }
    return ESP_OK;
}

esp_err_t lora_mac_crypto_x25519_keypair(uint8_t out_priv[32], uint8_t out_pub[32])
{
    if (out_priv == NULL || out_pub == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t err = ensure_psa_init();
    if (err != ESP_OK) return err;

    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_DERIVE | PSA_KEY_USAGE_EXPORT);
    psa_set_key_algorithm(&attr, PSA_ALG_ECDH);
    psa_set_key_type(&attr, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_MONTGOMERY));
    psa_set_key_bits(&attr, 255);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_generate_key(&attr, &key_id);
    if (status != PSA_SUCCESS) {
        psa_reset_key_attributes(&attr);
        return ESP_FAIL;
    }

    size_t pub_len = 0;
    status = psa_export_public_key(key_id, out_pub, 32, &pub_len);
    if (status != PSA_SUCCESS || pub_len != 32) {
        psa_destroy_key(key_id);
        psa_reset_key_attributes(&attr);
        return ESP_FAIL;
    }

    size_t priv_len = 0;
    status = psa_export_key(key_id, out_priv, 32, &priv_len);
    psa_destroy_key(key_id);
    psa_reset_key_attributes(&attr);

    if (status != PSA_SUCCESS || priv_len != 32) {
        return ESP_FAIL;
    }
    return ESP_OK;
}

esp_err_t lora_mac_crypto_x25519_ecdh(const uint8_t priv[32],
                                      const uint8_t peer_pub[32],
                                      uint8_t out_shared[32])
{
    if (priv == NULL || peer_pub == NULL || out_shared == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* DEC-SEC-07: Reject all-zero public key immediately before crypto */
    if (lora_mac_crypto_is_all_zero(peer_pub, 32)) {
        lora_mac_crypto_zeroize(out_shared, 32);
        return ESP_ERR_INVALID_RESPONSE;
    }

    esp_err_t err = ensure_psa_init();
    if (err != ESP_OK) return err;

    psa_key_attributes_t attr = PSA_KEY_ATTRIBUTES_INIT;
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_DERIVE);
    psa_set_key_algorithm(&attr, PSA_ALG_ECDH);
    psa_set_key_type(&attr, PSA_KEY_TYPE_ECC_KEY_PAIR(PSA_ECC_FAMILY_MONTGOMERY));
    psa_set_key_bits(&attr, 255);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, priv, 32, &key_id);
    psa_reset_key_attributes(&attr);
    if (status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    size_t shared_len = 0;
    status = psa_raw_key_agreement(PSA_ALG_ECDH, key_id, peer_pub, 32, out_shared, 32, &shared_len);
    psa_destroy_key(key_id);

    if (status != PSA_SUCCESS || shared_len != 32) {
        lora_mac_crypto_zeroize(out_shared, 32);
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* DEC-SEC-07 & RFC 7748 §6.1 Check: If Z == 0^32, immediately abort */
    if (lora_mac_crypto_is_all_zero(out_shared, 32)) {
        lora_mac_crypto_zeroize(out_shared, 32);
        return ESP_ERR_INVALID_RESPONSE;
    }

    return ESP_OK;
}

#else /* Host test mock / simulator implementation */

static bool s_mock_force_all_zero_shared = false;

void lora_mac_crypto_mock_set_force_zero_shared(bool force_zero) {
    s_mock_force_all_zero_shared = force_zero;
}

esp_err_t lora_mac_crypto_x25519_keypair(uint8_t out_priv[32], uint8_t out_pub[32])
{
    if (out_priv == NULL || out_pub == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    /* Deterministic host mock keypair */
    for (size_t i = 0; i < 32; i++) {
        out_priv[i] = (uint8_t)(0x11U + i);
    }
    out_priv[0] &= 248U;
    out_priv[31] &= 127U;
    out_priv[31] |= 64U;

    for (size_t i = 0; i < 32; i++) {
        out_pub[i] = (uint8_t)(out_priv[i] ^ 0x5AU);
    }
    return ESP_OK;
}

esp_err_t lora_mac_crypto_x25519_ecdh(const uint8_t priv[32],
                                      const uint8_t peer_pub[32],
                                      uint8_t out_shared[32])
{
    if (priv == NULL || peer_pub == NULL || out_shared == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* DEC-SEC-07: Reject all-zero public key */
    if (lora_mac_crypto_is_all_zero(peer_pub, 32) || s_mock_force_all_zero_shared) {
        lora_mac_crypto_zeroize(out_shared, 32);
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* Deterministic mock ECDH derivation: SHA256(priv || peer_pub) */
    uint8_t combined[64];
    memcpy(combined, priv, 32);
    memcpy(combined + 32, peer_pub, 32);
    lora_mac_crypto_sha256(combined, 64, out_shared);
    lora_mac_crypto_zeroize(combined, sizeof(combined));

    /* Check all zeros */
    if (lora_mac_crypto_is_all_zero(out_shared, 32)) {
        lora_mac_crypto_zeroize(out_shared, 32);
        return ESP_ERR_INVALID_RESPONSE;
    }

    return ESP_OK;
}

#endif /* ESP_PLATFORM */

/* =========================================================================
 * V2 JOIN DOMAIN TRANSCRIPTS AND KEY DERIVATIONS
 * ========================================================================= */

esp_err_t lora_mac_join_derive_k_join_keys(uint32_t network_id,
                                           const uint8_t device_mac[6],
                                           uint16_t device_generation,
                                           const uint8_t k_join[32],
                                           lora_mac_k_join_expanded_keys_t *out_keys)
{
    if (device_mac == NULL || k_join == NULL || out_keys == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // SALT = "LP2P/V2/JOIN-ROOT" (17B) || NETWORK_ID_BE4 (4B) || DEVICE_MAC6 (6B) || DEVICE_GENERATION_BE2 (2B) = 29B
    uint8_t salt[29];
    const char *prefix = "LP2P/V2/JOIN-ROOT";
    memcpy(salt, prefix, 17);
    salt[17] = (uint8_t)((network_id >> 24) & 0xFFU);
    salt[18] = (uint8_t)((network_id >> 16) & 0xFFU);
    salt[19] = (uint8_t)((network_id >> 8) & 0xFFU);
    salt[20] = (uint8_t)(network_id & 0xFFU);
    memcpy(&salt[21], device_mac, 6);
    salt[27] = (uint8_t)((device_generation >> 8) & 0xFFU);
    salt[28] = (uint8_t)(device_generation & 0xFFU);

    uint8_t prk_join[32];
    esp_err_t err = lora_mac_crypto_hkdf_extract(salt, sizeof(salt), k_join, 32, prk_join);
    lora_mac_crypto_zeroize(salt, sizeof(salt));
    if (err != ESP_OK) return err;

    // Expand 5 keys
    err = lora_mac_crypto_hkdf_expand(prk_join, 32, (const uint8_t *)"LP2P/V2/JOIN-REQ", 16, out_keys->k_jreq, 32);
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(prk_join, 32, (const uint8_t *)"LP2P/V2/JOIN-GRANT", 18, out_keys->k_jgrant, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(prk_join, 32, (const uint8_t *)"LP2P/V2/JOIN-CONF", 17, out_keys->k_jconf, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(prk_join, 32, (const uint8_t *)"LP2P/V2/JOIN-FINISH", 19, out_keys->k_jfinish, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(prk_join, 32, (const uint8_t *)"LP2P/V2/JOIN-READY", 18, out_keys->k_jready, 32);
    }

    lora_mac_crypto_zeroize(prk_join, sizeof(prk_join));
    return err;
}

esp_err_t lora_mac_join_compute_hello_proof(uint32_t network_id,
                                            const uint8_t hello_prefix52[52],
                                            const uint8_t k_jreq[32],
                                            uint8_t out_proof[16])
{
    if (hello_prefix52 == NULL || k_jreq == NULL || out_proof == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // M_HELLO = "LP2P/V2/M-HELLO" (15B) || NETWORK_ID_BE4 (4B) || HELLO[0..51] (52B) = 71B
    uint8_t m_hello[71];
    memcpy(m_hello, "LP2P/V2/M-HELLO", 15);
    m_hello[15] = (uint8_t)((network_id >> 24) & 0xFFU);
    m_hello[16] = (uint8_t)((network_id >> 16) & 0xFFU);
    m_hello[17] = (uint8_t)((network_id >> 8) & 0xFFU);
    m_hello[18] = (uint8_t)(network_id & 0xFFU);
    memcpy(&m_hello[19], hello_prefix52, 52);

    uint8_t full_hmac[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_jreq, 32, m_hello, sizeof(m_hello), full_hmac);
    lora_mac_crypto_zeroize(m_hello, sizeof(m_hello));
    if (err == ESP_OK) {
        memcpy(out_proof, full_hmac, 16);
    }
    lora_mac_crypto_zeroize(full_hmac, sizeof(full_hmac));
    return err;
}

esp_err_t lora_mac_join_verify_hello_proof(uint32_t network_id,
                                           const uint8_t hello_prefix52[52],
                                           const uint8_t k_jreq[32],
                                           const uint8_t expected_proof[16])
{
    if (expected_proof == NULL) return ESP_ERR_INVALID_ARG;
    uint8_t calculated[16];
    esp_err_t err = lora_mac_join_compute_hello_proof(network_id, hello_prefix52, k_jreq, calculated);
    if (err != ESP_OK) return err;

    int cmp = lora_mac_crypto_constant_time_memcmp(calculated, expected_proof, 16);
    lora_mac_crypto_zeroize(calculated, sizeof(calculated));
    return (cmp == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}

esp_err_t lora_mac_join_compute_grant_proof(uint32_t network_id,
                                            const uint8_t hello68[68],
                                            const uint8_t grant_prefix50[50],
                                            const uint8_t k_jgrant[32],
                                            uint8_t out_proof[16])
{
    if (hello68 == NULL || grant_prefix50 == NULL || k_jgrant == NULL || out_proof == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // M_GRANT = "LP2P/V2/M-GRANT" (15B) || NETWORK_ID_BE4 (4B) || HELLO68 (68B) || GRANT[0..49] (50B) = 137B
    uint8_t m_grant[137];
    memcpy(m_grant, "LP2P/V2/M-GRANT", 15);
    m_grant[15] = (uint8_t)((network_id >> 24) & 0xFFU);
    m_grant[16] = (uint8_t)((network_id >> 16) & 0xFFU);
    m_grant[17] = (uint8_t)((network_id >> 8) & 0xFFU);
    m_grant[18] = (uint8_t)(network_id & 0xFFU);
    memcpy(&m_grant[19], hello68, 68);
    memcpy(&m_grant[87], grant_prefix50, 50);

    uint8_t full_hmac[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_jgrant, 32, m_grant, sizeof(m_grant), full_hmac);
    lora_mac_crypto_zeroize(m_grant, sizeof(m_grant));
    if (err == ESP_OK) {
        memcpy(out_proof, full_hmac, 16);
    }
    lora_mac_crypto_zeroize(full_hmac, sizeof(full_hmac));
    return err;
}

esp_err_t lora_mac_join_verify_grant_proof(uint32_t network_id,
                                           const uint8_t hello68[68],
                                           const uint8_t grant_prefix50[50],
                                           const uint8_t k_jgrant[32],
                                           const uint8_t expected_proof[16])
{
    if (expected_proof == NULL) return ESP_ERR_INVALID_ARG;
    uint8_t calculated[16];
    esp_err_t err = lora_mac_join_compute_grant_proof(network_id, hello68, grant_prefix50, k_jgrant, calculated);
    if (err != ESP_OK) return err;

    int cmp = lora_mac_crypto_constant_time_memcmp(calculated, expected_proof, 16);
    lora_mac_crypto_zeroize(calculated, sizeof(calculated));
    return (cmp == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}

esp_err_t lora_mac_join_compute_th(uint32_t network_id,
                                   const uint8_t hello68[68],
                                   const uint8_t grant66[66],
                                   uint8_t out_th[32])
{
    if (hello68 == NULL || grant66 == NULL || out_th == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // TH = SHA256("LP2P/V2/TH-JOIN" (16B) || NETWORK_ID_BE4 (4B) || HELLO68 (68B) || GRANT66 (66B)) = 154B
    uint8_t buf[154];
    memcpy(buf, "LP2P/V2/TH-JOIN", 16);
    buf[16] = (uint8_t)((network_id >> 24) & 0xFFU);
    buf[17] = (uint8_t)((network_id >> 16) & 0xFFU);
    buf[18] = (uint8_t)((network_id >> 8) & 0xFFU);
    buf[19] = (uint8_t)(network_id & 0xFFU);
    memcpy(&buf[20], hello68, 68);
    memcpy(&buf[88], grant66, 66);

    esp_err_t err = lora_mac_crypto_sha256(buf, sizeof(buf), out_th);
    lora_mac_crypto_zeroize(buf, sizeof(buf));
    return err;
}

esp_err_t lora_mac_join_derive_session_keys(const uint8_t th[32],
                                            const uint8_t z[32],
                                            lora_mac_session_keys_t *out_keys)
{
    if (th == NULL || z == NULL || out_keys == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    esp_err_t err = lora_mac_crypto_hkdf_extract(th, 32, z, 32, out_keys->prk_session);
    if (err != ESP_OK) return err;

    err = lora_mac_crypto_hkdf_expand(out_keys->prk_session, 32, (const uint8_t *)"LP2P/V2/KC-UP", 13, out_keys->k_kc_up, 32);
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(out_keys->prk_session, 32, (const uint8_t *)"LP2P/V2/KC-DOWN", 15, out_keys->k_kc_down, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(out_keys->prk_session, 32, (const uint8_t *)"LP2P/V2/SESSION-ROOT", 20, out_keys->k_session_root, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(out_keys->k_session_root, 32, (const uint8_t *)"LP2P/V2/DATA-UP", 15, out_keys->k_session_up, 32);
    }
    if (err == ESP_OK) {
        err = lora_mac_crypto_hkdf_expand(out_keys->k_session_root, 32, (const uint8_t *)"LP2P/V2/DATA-DOWN", 17, out_keys->k_session_dl, 32);
    }
    return err;
}

esp_err_t lora_mac_join_compute_confirm_tags(uint32_t network_id,
                                             const uint8_t th[32],
                                             const uint8_t confirm_prefix7[7],
                                             const uint8_t k_kc_up[32],
                                             const uint8_t k_jconf[32],
                                             uint8_t out_gw_kc_tag[8],
                                             uint8_t out_backend_proof[16])
{
    if (th == NULL || confirm_prefix7 == NULL || k_kc_up == NULL || k_jconf == NULL ||
        out_gw_kc_tag == NULL || out_backend_proof == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // M_GW_CONF = "LP2P/V2/M-GW-CONF" (17B) || TH (32B) || CONFIRM_PREFIX7 (7B) = 56B
    uint8_t m_gw[56];
    memcpy(m_gw, "LP2P/V2/M-GW-CONF", 17);
    memcpy(&m_gw[17], th, 32);
    memcpy(&m_gw[49], confirm_prefix7, 7);

    uint8_t hmac_gw[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_kc_up, 32, m_gw, sizeof(m_gw), hmac_gw);
    lora_mac_crypto_zeroize(m_gw, sizeof(m_gw));
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
        return err;
    }
    memcpy(out_gw_kc_tag, hmac_gw, 8);

    // M_BE_CONF = "LP2P/V2/M-BACKEND-CONF" (22B) || NETWORK_ID_BE4 (4B) || TH (32B) || CONFIRM_PREFIX7 (7B) || GW_KC_TAG8 (8B) = 73B
    uint8_t m_be[73];
    memcpy(m_be, "LP2P/V2/M-BACKEND-CONF", 22);
    m_be[22] = (uint8_t)((network_id >> 24) & 0xFFU);
    m_be[23] = (uint8_t)((network_id >> 16) & 0xFFU);
    m_be[24] = (uint8_t)((network_id >> 8) & 0xFFU);
    m_be[25] = (uint8_t)(network_id & 0xFFU);
    memcpy(&m_be[26], th, 32);
    memcpy(&m_be[58], confirm_prefix7, 7);
    memcpy(&m_be[65], out_gw_kc_tag, 8);

    uint8_t hmac_be[32];
    err = lora_mac_crypto_hmac_sha256(k_jconf, 32, m_be, sizeof(m_be), hmac_be);
    lora_mac_crypto_zeroize(m_be, sizeof(m_be));
    if (err == ESP_OK) {
        memcpy(out_backend_proof, hmac_be, 16);
    }
    lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
    lora_mac_crypto_zeroize(hmac_be, sizeof(hmac_be));
    return err;
}

esp_err_t lora_mac_join_verify_confirm_gw_tag(const uint8_t th[32],
                                              const uint8_t confirm_prefix7[7],
                                              const uint8_t k_kc_up[32],
                                              const uint8_t expected_tag[8])
{
    if (th == NULL || confirm_prefix7 == NULL || k_kc_up == NULL || expected_tag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t m_gw[56];
    memcpy(m_gw, "LP2P/V2/M-GW-CONF", 17);
    memcpy(&m_gw[17], th, 32);
    memcpy(&m_gw[49], confirm_prefix7, 7);

    uint8_t hmac_gw[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_kc_up, 32, m_gw, sizeof(m_gw), hmac_gw);
    lora_mac_crypto_zeroize(m_gw, sizeof(m_gw));
    if (err != ESP_OK) return err;

    int cmp = lora_mac_crypto_constant_time_memcmp(hmac_gw, expected_tag, 8);
    lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
    return (cmp == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}

esp_err_t lora_mac_join_compute_finish_tags(uint32_t network_id,
                                            const uint8_t th[32],
                                            const uint8_t finish_prefix7[7],
                                            const uint8_t k_kc_down[32],
                                            const uint8_t k_jfinish[32],
                                            uint8_t out_gw_finish_tag[8],
                                            uint8_t out_backend_finish_proof[16])
{
    if (th == NULL || finish_prefix7 == NULL || k_kc_down == NULL || k_jfinish == NULL ||
        out_gw_finish_tag == NULL || out_backend_finish_proof == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // M_GW_FINISH = "LP2P/V2/M-GW-FINISH" (19B) || TH (32B) || FINISH_PREFIX7 (7B) = 58B
    uint8_t m_gw[58];
    memcpy(m_gw, "LP2P/V2/M-GW-FINISH", 19);
    memcpy(&m_gw[19], th, 32);
    memcpy(&m_gw[51], finish_prefix7, 7);

    uint8_t hmac_gw[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_kc_down, 32, m_gw, sizeof(m_gw), hmac_gw);
    lora_mac_crypto_zeroize(m_gw, sizeof(m_gw));
    if (err != ESP_OK) return err;
    memcpy(out_gw_finish_tag, hmac_gw, 8);

    // M_BE_FINISH = "LP2P/V2/M-BACKEND-FINISH" (24B) || NETWORK_ID_BE4 (4B) || TH (32B) || FINISH_PREFIX7 (7B) || GW_FINISH_TAG8 (8B) = 75B
    uint8_t m_be[75];
    memcpy(m_be, "LP2P/V2/M-BACKEND-FINISH", 24);
    m_be[24] = (uint8_t)((network_id >> 24) & 0xFFU);
    m_be[25] = (uint8_t)((network_id >> 16) & 0xFFU);
    m_be[26] = (uint8_t)((network_id >> 8) & 0xFFU);
    m_be[27] = (uint8_t)(network_id & 0xFFU);
    memcpy(&m_be[28], th, 32);
    memcpy(&m_be[60], finish_prefix7, 7);
    memcpy(&m_be[67], out_gw_finish_tag, 8);

    uint8_t hmac_be[32];
    err = lora_mac_crypto_hmac_sha256(k_jfinish, 32, m_be, sizeof(m_be), hmac_be);
    lora_mac_crypto_zeroize(m_be, sizeof(m_be));
    if (err == ESP_OK) {
        memcpy(out_backend_finish_proof, hmac_be, 16);
    }
    lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
    lora_mac_crypto_zeroize(hmac_be, sizeof(hmac_be));
    return err;
}

esp_err_t lora_mac_join_verify_finish_tags(uint32_t network_id,
                                           const uint8_t th[32],
                                           const uint8_t finish_prefix7[7],
                                           const uint8_t k_kc_down[32],
                                           const uint8_t k_jfinish[32],
                                           const uint8_t expected_gw_tag[8],
                                           const uint8_t expected_be_proof[16])
{
    if (expected_gw_tag == NULL || expected_be_proof == NULL) return ESP_ERR_INVALID_ARG;
    uint8_t calc_gw[8];
    uint8_t calc_be[16];
    esp_err_t err = lora_mac_join_compute_finish_tags(network_id, th, finish_prefix7, k_kc_down, k_jfinish, calc_gw, calc_be);
    if (err != ESP_OK) return err;

    int cmp_gw = lora_mac_crypto_constant_time_memcmp(calc_gw, expected_gw_tag, 8);
    int cmp_be = lora_mac_crypto_constant_time_memcmp(calc_be, expected_be_proof, 16);
    lora_mac_crypto_zeroize(calc_gw, sizeof(calc_gw));
    lora_mac_crypto_zeroize(calc_be, sizeof(calc_be));

    if (cmp_gw != 0 || cmp_be != 0) {
        return ESP_ERR_INVALID_CRC;
    }
    return ESP_OK;
}

esp_err_t lora_mac_join_compute_ready_tags(uint32_t network_id,
                                           const uint8_t th[32],
                                           const uint8_t finish31[31],
                                           const uint8_t ready_prefix7[7],
                                           const uint8_t k_kc_up[32],
                                           const uint8_t k_jready[32],
                                           uint8_t out_gw_ready_tag[8],
                                           uint8_t out_backend_ready_proof[16])
{
    if (th == NULL || finish31 == NULL || ready_prefix7 == NULL || k_kc_up == NULL ||
        k_jready == NULL || out_gw_ready_tag == NULL || out_backend_ready_proof == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    // M_GW_READY = "LP2P/V2/M-GW-READY" (18B) || TH (32B) || FINISH31 (31B) || READY_PREFIX7 (7B) = 88B
    uint8_t m_gw[88];
    memcpy(m_gw, "LP2P/V2/M-GW-READY", 18);
    memcpy(&m_gw[18], th, 32);
    memcpy(&m_gw[50], finish31, 31);
    memcpy(&m_gw[81], ready_prefix7, 7);

    uint8_t hmac_gw[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_kc_up, 32, m_gw, sizeof(m_gw), hmac_gw);
    lora_mac_crypto_zeroize(m_gw, sizeof(m_gw));
    if (err != ESP_OK) return err;
    memcpy(out_gw_ready_tag, hmac_gw, 8);

    // M_BE_READY = "LP2P/V2/M-BACKEND-READY" (23B) || NETWORK_ID_BE4 (4B) || TH (32B) || FINISH31 (31B) || READY_PREFIX7 (7B) || GW_READY_TAG8 (8B) = 105B
    uint8_t m_be[105];
    memcpy(m_be, "LP2P/V2/M-BACKEND-READY", 23);
    m_be[23] = (uint8_t)((network_id >> 24) & 0xFFU);
    m_be[24] = (uint8_t)((network_id >> 16) & 0xFFU);
    m_be[25] = (uint8_t)((network_id >> 8) & 0xFFU);
    m_be[26] = (uint8_t)(network_id & 0xFFU);
    memcpy(&m_be[27], th, 32);
    memcpy(&m_be[59], finish31, 31);
    memcpy(&m_be[90], ready_prefix7, 7);
    memcpy(&m_be[97], out_gw_ready_tag, 8);

    uint8_t hmac_be[32];
    err = lora_mac_crypto_hmac_sha256(k_jready, 32, m_be, sizeof(m_be), hmac_be);
    lora_mac_crypto_zeroize(m_be, sizeof(m_be));
    if (err == ESP_OK) {
        memcpy(out_backend_ready_proof, hmac_be, 16);
    }
    lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
    lora_mac_crypto_zeroize(hmac_be, sizeof(hmac_be));
    return err;
}

esp_err_t lora_mac_join_verify_ready_gw_tag(const uint8_t th[32],
                                            const uint8_t finish31[31],
                                            const uint8_t ready_prefix7[7],
                                            const uint8_t k_kc_up[32],
                                            const uint8_t expected_tag[8])
{
    if (th == NULL || finish31 == NULL || ready_prefix7 == NULL || k_kc_up == NULL || expected_tag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    uint8_t m_gw[88];
    memcpy(m_gw, "LP2P/V2/M-GW-READY", 18);
    memcpy(&m_gw[18], th, 32);
    memcpy(&m_gw[50], finish31, 31);
    memcpy(&m_gw[81], ready_prefix7, 7);

    uint8_t hmac_gw[32];
    esp_err_t err = lora_mac_crypto_hmac_sha256(k_kc_up, 32, m_gw, sizeof(m_gw), hmac_gw);
    lora_mac_crypto_zeroize(m_gw, sizeof(m_gw));
    if (err != ESP_OK) return err;

    int cmp = lora_mac_crypto_constant_time_memcmp(hmac_gw, expected_tag, 8);
    lora_mac_crypto_zeroize(hmac_gw, sizeof(hmac_gw));
    return (cmp == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}
