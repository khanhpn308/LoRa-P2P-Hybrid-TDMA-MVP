#include "gateway_crypto.h"
#include <string.h>

#if defined(ESP_PLATFORM)
#include "psa/crypto.h"
#include "mbedtls/platform_util.h"
#endif

void gateway_crypto_zeroize(void *buf, size_t len)
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

static int constant_time_compare(const uint8_t *a, const uint8_t *b, size_t len)
{
    uint8_t diff = 0U;
    for (size_t i = 0; i < len; i++) {
        diff |= (a[i] ^ b[i]);
    }
    return (diff == 0U) ? 0 : -1;
}

#if defined(ESP_PLATFORM)

static bool s_psa_initialized = false;

esp_err_t gateway_crypto_init(void)
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

esp_err_t gateway_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                             const uint8_t *header,
                                             size_t header_len,
                                             uint8_t out_tag[GATEWAY_CRYPTO_HMAC_TAG_LEN])
{
    if (k_beacon == NULL || header == NULL || out_tag == NULL || header_len == 0U) {
        return ESP_ERR_INVALID_ARG;
    }
    esp_err_t init_err = gateway_crypto_init();
    if (init_err != ESP_OK) {
        return init_err;
    }

    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_SIGN_MESSAGE);
    psa_set_key_algorithm(&attr, PSA_ALG_HMAC(PSA_ALG_SHA_256));
    psa_set_key_type(&attr, PSA_KEY_TYPE_HMAC);
    psa_set_key_bits(&attr, 256);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, k_beacon, 32, &key_id);
    psa_reset_key_attributes(&attr);
    if (status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    uint8_t full_mac[32];
    size_t mac_len = 0;
    status = psa_mac_compute(key_id, PSA_ALG_HMAC(PSA_ALG_SHA_256),
                            header, header_len,
                            full_mac, sizeof(full_mac), &mac_len);
    psa_destroy_key(key_id);

    if (status != PSA_SUCCESS || mac_len < GATEWAY_CRYPTO_HMAC_TAG_LEN) {
        gateway_crypto_zeroize(full_mac, sizeof(full_mac));
        return ESP_FAIL;
    }

    (void)memcpy(out_tag, full_mac, GATEWAY_CRYPTO_HMAC_TAG_LEN);
    gateway_crypto_zeroize(full_mac, sizeof(full_mac));
    return ESP_OK;
}

esp_err_t gateway_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                            const uint8_t *header,
                                            size_t header_len,
                                            const uint8_t *expected_tag)
{
    if (k_beacon == NULL || header == NULL || expected_tag == NULL || header_len == 0U) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t computed_tag[GATEWAY_CRYPTO_HMAC_TAG_LEN];
    esp_err_t err = gateway_crypto_compute_beacon_hmac(k_beacon, header, header_len, computed_tag);
    if (err != ESP_OK) {
        return err;
    }

    int match = constant_time_compare(computed_tag, expected_tag, GATEWAY_CRYPTO_HMAC_TAG_LEN);
    gateway_crypto_zeroize(computed_tag, sizeof(computed_tag));
    return (match == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}

static esp_err_t psa_ccm_encrypt(const uint8_t *key_bytes,
                                 const uint8_t *nonce,
                                 const uint8_t *aad, size_t aad_len,
                                 const uint8_t *plaintext, size_t pt_len,
                                 uint8_t *out_ciphertext, uint8_t *out_tag)
{
    esp_err_t init_err = gateway_crypto_init();
    if (init_err != ESP_OK) {
        return init_err;
    }

    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_ENCRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_CCM, GATEWAY_CRYPTO_CCM_TAG_LEN));
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 128);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, key_bytes, 16, &key_id);
    psa_reset_key_attributes(&attr);
    if (status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    uint8_t temp_out[64];
    size_t out_len = 0;
    status = psa_aead_encrypt(key_id,
                              PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_CCM, GATEWAY_CRYPTO_CCM_TAG_LEN),
                              nonce, GATEWAY_CRYPTO_CCM_NONCE_LEN,
                              aad, aad_len,
                              plaintext, pt_len,
                              temp_out, sizeof(temp_out),
                              &out_len);
    psa_destroy_key(key_id);

    if (status != PSA_SUCCESS || out_len != (pt_len + GATEWAY_CRYPTO_CCM_TAG_LEN)) {
        gateway_crypto_zeroize(temp_out, sizeof(temp_out));
        return ESP_FAIL;
    }

    (void)memcpy(out_ciphertext, temp_out, pt_len);
    (void)memcpy(out_tag, temp_out + pt_len, GATEWAY_CRYPTO_CCM_TAG_LEN);
    gateway_crypto_zeroize(temp_out, sizeof(temp_out));
    return ESP_OK;
}

static esp_err_t psa_ccm_decrypt(const uint8_t *key_bytes,
                                 const uint8_t *nonce,
                                 const uint8_t *aad, size_t aad_len,
                                 const uint8_t *ciphertext, size_t ct_len,
                                 const uint8_t *tag,
                                 uint8_t *out_plaintext)
{
    esp_err_t init_err = gateway_crypto_init();
    if (init_err != ESP_OK) {
        return init_err;
    }

    psa_key_attributes_t attr = psa_key_attributes_init();
    psa_set_key_usage_flags(&attr, PSA_KEY_USAGE_DECRYPT);
    psa_set_key_algorithm(&attr, PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_CCM, GATEWAY_CRYPTO_CCM_TAG_LEN));
    psa_set_key_type(&attr, PSA_KEY_TYPE_AES);
    psa_set_key_bits(&attr, 128);

    psa_key_id_t key_id = 0;
    psa_status_t status = psa_import_key(&attr, key_bytes, 16, &key_id);
    psa_reset_key_attributes(&attr);
    if (status != PSA_SUCCESS) {
        return ESP_FAIL;
    }

    uint8_t temp_in[64];
    (void)memcpy(temp_in, ciphertext, ct_len);
    (void)memcpy(temp_in + ct_len, tag, GATEWAY_CRYPTO_CCM_TAG_LEN);

    uint8_t temp_out[64];
    size_t out_len = 0;
    status = psa_aead_decrypt(key_id,
                              PSA_ALG_AEAD_WITH_SHORTENED_TAG(PSA_ALG_CCM, GATEWAY_CRYPTO_CCM_TAG_LEN),
                              nonce, GATEWAY_CRYPTO_CCM_NONCE_LEN,
                              aad, aad_len,
                              temp_in, ct_len + GATEWAY_CRYPTO_CCM_TAG_LEN,
                              temp_out, sizeof(temp_out),
                              &out_len);
    psa_destroy_key(key_id);
    gateway_crypto_zeroize(temp_in, sizeof(temp_in));

    if (status != PSA_SUCCESS || out_len != ct_len) {
        gateway_crypto_zeroize(temp_out, sizeof(temp_out));
        return ESP_ERR_INVALID_CRC;
    }

    (void)memcpy(out_plaintext, temp_out, ct_len);
    gateway_crypto_zeroize(temp_out, sizeof(temp_out));
    return ESP_OK;
}

#else /* Portable software implementation for Host unit tests */

/* --- SHA-256 (FIPS 180-4) --- */

typedef struct {
    uint32_t state[8];
    uint64_t count;
    uint8_t  buffer[64];
} sw_sha256_ctx_t;

#define CH(x,y,z)  (((x) & (y)) ^ (~(x) & (z)))
#define MAJ(x,y,z) (((x) & (y)) ^ ((x) & (z)) ^ ((y) & (z)))
#define ROTR(x,n)  (((x) >> (n)) | ((x) << (32 - (n))))
#define SIG0(x)    (ROTR(x, 2) ^ ROTR(x, 13) ^ ROTR(x, 22))
#define SIG1(x)    (ROTR(x, 6) ^ ROTR(x, 11) ^ ROTR(x, 25))
#define sig0(x)    (ROTR(x, 7) ^ ROTR(x, 18) ^ ((x) >> 3))
#define sig1(x)    (ROTR(x, 17) ^ ROTR(x, 19) ^ ((x) >> 10))

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

static void sw_sha256_transform(sw_sha256_ctx_t *ctx, const uint8_t data[64])
{
    uint32_t a = ctx->state[0], b = ctx->state[1], c = ctx->state[2], d = ctx->state[3];
    uint32_t e = ctx->state[4], f = ctx->state[5], g = ctx->state[6], h = ctx->state[7];
    uint32_t w[64];

    for (size_t i = 0, j = 0; i < 16; ++i, j += 4) {
        w[i] = ((uint32_t)data[j] << 24) | ((uint32_t)data[j + 1] << 16) |
               ((uint32_t)data[j + 2] << 8) | ((uint32_t)data[j + 3]);
    }
    for (size_t i = 16; i < 64; ++i) {
        w[i] = sig1(w[i - 2]) + w[i - 7] + sig0(w[i - 15]) + w[i - 16];
    }
    for (size_t i = 0; i < 64; ++i) {
        uint32_t t1 = h + SIG1(e) + CH(e, f, g) + K[i] + w[i];
        uint32_t t2 = SIG0(a) + MAJ(a, b, c);
        h = g; g = f; f = e; e = d + t1;
        d = c; c = b; a = t1 + t2;
    }
    ctx->state[0] += a; ctx->state[1] += b; ctx->state[2] += c; ctx->state[3] += d;
    ctx->state[4] += e; ctx->state[5] += f; ctx->state[6] += g; ctx->state[7] += h;
}

static void sw_sha256_init(sw_sha256_ctx_t *ctx)
{
    ctx->count = 0;
    ctx->state[0] = 0x6a09e667U; ctx->state[1] = 0xbb67ae85U;
    ctx->state[2] = 0x3c6ef372U; ctx->state[3] = 0xa54ff53aU;
    ctx->state[4] = 0x510e527fU; ctx->state[5] = 0x9b05688cU;
    ctx->state[6] = 0x1f83d9abU; ctx->state[7] = 0x5be0cd19U;
}

static void sw_sha256_update(sw_sha256_ctx_t *ctx, const uint8_t *data, size_t len)
{
    size_t i = (size_t)(ctx->count & 63);
    ctx->count += len;
    size_t fill = 64 - i;
    if (i > 0 && len >= fill) {
        (void)memcpy(ctx->buffer + i, data, fill);
        sw_sha256_transform(ctx, ctx->buffer);
        data += fill;
        len -= fill;
        i = 0;
    }
    while (len >= 64) {
        sw_sha256_transform(ctx, data);
        data += 64;
        len -= 64;
    }
    if (len > 0) {
        (void)memcpy(ctx->buffer + i, data, len);
    }
}

static void sw_sha256_final(sw_sha256_ctx_t *ctx, uint8_t digest[32])
{
    uint8_t final_count[8];
    uint64_t bits = ctx->count * 8ULL;
    for (int i = 7; i >= 0; i--) {
        final_count[i] = (uint8_t)(bits & 0xFFULL);
        bits >>= 8;
    }
    uint8_t pad = 0x80;
    sw_sha256_update(ctx, &pad, 1);
    uint8_t zero = 0;
    while ((ctx->count & 63) != 56) {
        sw_sha256_update(ctx, &zero, 1);
    }
    sw_sha256_update(ctx, final_count, 8);
    for (size_t j = 0, k = 0; j < 8; ++j, k += 4) {
        digest[k] = (uint8_t)((ctx->state[j] >> 24) & 0xFFU);
        digest[k + 1] = (uint8_t)((ctx->state[j] >> 16) & 0xFFU);
        digest[k + 2] = (uint8_t)((ctx->state[j] >> 8) & 0xFFU);
        digest[k + 3] = (uint8_t)(ctx->state[j] & 0xFFU);
    }
    gateway_crypto_zeroize(ctx, sizeof(*ctx));
}

esp_err_t gateway_crypto_init(void)
{
    return ESP_OK;
}

esp_err_t gateway_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                             const uint8_t *header,
                                             size_t header_len,
                                             uint8_t out_tag[GATEWAY_CRYPTO_HMAC_TAG_LEN])
{
    if (k_beacon == NULL || header == NULL || out_tag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t k_ipad[64];
    uint8_t k_opad[64];
    for (size_t i = 0; i < 32; i++) {
        k_ipad[i] = k_beacon[i] ^ 0x36U;
        k_opad[i] = k_beacon[i] ^ 0x5cU;
    }
    for (size_t i = 32; i < 64; i++) {
        k_ipad[i] = 0x36U;
        k_opad[i] = 0x5cU;
    }

    sw_sha256_ctx_t ctx;
    sw_sha256_init(&ctx);
    sw_sha256_update(&ctx, k_ipad, 64);
    sw_sha256_update(&ctx, header, header_len);
    uint8_t inner_hash[32];
    sw_sha256_final(&ctx, inner_hash);

    sw_sha256_init(&ctx);
    sw_sha256_update(&ctx, k_opad, 64);
    sw_sha256_update(&ctx, inner_hash, 32);
    uint8_t outer_hash[32];
    sw_sha256_final(&ctx, outer_hash);

    (void)memcpy(out_tag, outer_hash, GATEWAY_CRYPTO_HMAC_TAG_LEN);
    gateway_crypto_zeroize(k_ipad, sizeof(k_ipad));
    gateway_crypto_zeroize(k_opad, sizeof(k_opad));
    gateway_crypto_zeroize(inner_hash, sizeof(inner_hash));
    gateway_crypto_zeroize(outer_hash, sizeof(outer_hash));
    return ESP_OK;
}

esp_err_t gateway_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                            const uint8_t *header,
                                            size_t header_len,
                                            const uint8_t *expected_tag)
{
    if (k_beacon == NULL || header == NULL || expected_tag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t computed[GATEWAY_CRYPTO_HMAC_TAG_LEN];
    esp_err_t err = gateway_crypto_compute_beacon_hmac(k_beacon, header, header_len, computed);
    if (err != ESP_OK) {
        return err;
    }
    int cmp = constant_time_compare(computed, expected_tag, GATEWAY_CRYPTO_HMAC_TAG_LEN);
    gateway_crypto_zeroize(computed, sizeof(computed));
    return (cmp == 0) ? ESP_OK : ESP_ERR_INVALID_CRC;
}

/* --- AES-128 and AES-128-CCM (RFC 3610) --- */

static const uint8_t AES_SBOX[256] = {
    0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
    0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
    0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
    0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
    0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
    0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
    0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
    0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
    0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
    0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
    0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
    0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
    0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
    0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
    0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
    0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
};

static const uint8_t RCON[11] = {
    0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36
};

static void aes128_key_expansion(const uint8_t key[16], uint8_t round_keys[176])
{
    (void)memcpy(round_keys, key, 16);
    for (size_t i = 4; i < 44; i++) {
        uint8_t temp[4];
        (void)memcpy(temp, &round_keys[(i - 1) * 4], 4);
        if (i % 4 == 0) {
            uint8_t k0 = temp[0];
            temp[0] = AES_SBOX[temp[1]] ^ RCON[i / 4];
            temp[1] = AES_SBOX[temp[2]];
            temp[2] = AES_SBOX[temp[3]];
            temp[3] = AES_SBOX[k0];
        }
        for (size_t j = 0; j < 4; j++) {
            round_keys[i * 4 + j] = round_keys[(i - 4) * 4 + j] ^ temp[j];
        }
    }
}

static uint8_t xtime(uint8_t x)
{
    return ((x << 1) ^ ((x & 0x80) ? 0x1b : 0x00));
}

static void aes128_encrypt_block(const uint8_t round_keys[176], const uint8_t in[16], uint8_t out[16])
{
    uint8_t state[16];
    for (size_t i = 0; i < 16; i++) {
        state[i] = in[i] ^ round_keys[i];
    }
    for (size_t round = 1; round <= 10; round++) {
        uint8_t sub[16];
        for (size_t i = 0; i < 16; i++) {
            sub[i] = AES_SBOX[state[i]];
        }
        /* ShiftRows */
        state[0] = sub[0];   state[4] = sub[4];   state[8] = sub[8];   state[12] = sub[12];
        state[1] = sub[5];   state[5] = sub[9];   state[9] = sub[13];  state[13] = sub[1];
        state[2] = sub[10];  state[6] = sub[14];  state[10] = sub[2];  state[14] = sub[6];
        state[3] = sub[15];  state[7] = sub[3];   state[11] = sub[7];  state[15] = sub[11];

        if (round < 10) {
            /* MixColumns */
            for (size_t c = 0; c < 4; c++) {
                uint8_t a0 = state[c * 4];
                uint8_t a1 = state[c * 4 + 1];
                uint8_t a2 = state[c * 4 + 2];
                uint8_t a3 = state[c * 4 + 3];
                state[c * 4]     = xtime(a0 ^ a1) ^ a1 ^ a2 ^ a3;
                state[c * 4 + 1] = xtime(a1 ^ a2) ^ a2 ^ a3 ^ a0;
                state[c * 4 + 2] = xtime(a2 ^ a3) ^ a3 ^ a0 ^ a1;
                state[c * 4 + 3] = xtime(a3 ^ a0) ^ a0 ^ a1 ^ a2;
            }
        }
        const uint8_t *rk = &round_keys[round * 16];
        for (size_t i = 0; i < 16; i++) {
            state[i] ^= rk[i];
        }
    }
    (void)memcpy(out, state, 16);
    gateway_crypto_zeroize(state, sizeof(state));
}

static esp_err_t sw_aes128_ccm_encrypt(const uint8_t key[16],
                                       const uint8_t nonce[13],
                                       const uint8_t *aad, size_t aad_len,
                                       const uint8_t *pt, size_t pt_len,
                                       uint8_t *out_ct, uint8_t out_tag[8])
{
    uint8_t rkeys[176];
    aes128_key_expansion(key, rkeys);

    /* Build Block B_0: Flags (8B tag -> M=8 -> (8-2)/2=3; L=2 -> L-1=1; Adata=1 if aad_len>0) */
    uint8_t b0[16] = {0};
    b0[0] = (aad_len > 0 ? 0x40U : 0x00U) | (((GATEWAY_CRYPTO_CCM_TAG_LEN - 2U) / 2U) << 3U) | (2U - 1U);
    (void)memcpy(&b0[1], nonce, 13);
    b0[14] = (uint8_t)((pt_len >> 8) & 0xFFU);
    b0[15] = (uint8_t)(pt_len & 0xFFU);

    uint8_t mac[16];
    aes128_encrypt_block(rkeys, b0, mac);

    /* AAD blocks into CBC-MAC */
    if (aad_len > 0) {
        uint8_t aad_block[16] = {0};
        aad_block[0] = (uint8_t)((aad_len >> 8) & 0xFFU);
        aad_block[1] = (uint8_t)(aad_len & 0xFFU);
        size_t copy_first = (aad_len < 14) ? aad_len : 14;
        (void)memcpy(&aad_block[2], aad, copy_first);
        for (int i = 0; i < 16; i++) {
            mac[i] ^= aad_block[i];
        }
        aes128_encrypt_block(rkeys, mac, mac);
        if (aad_len > 14) {
            uint8_t rem_block[16] = {0};
            (void)memcpy(rem_block, aad + 14, aad_len - 14);
            for (int i = 0; i < 16; i++) {
                mac[i] ^= rem_block[i];
            }
            aes128_encrypt_block(rkeys, mac, mac);
        }
    }

    /* Plaintext blocks into CBC-MAC */
    if (pt_len > 0) {
        uint8_t pt_block[16] = {0};
        (void)memcpy(pt_block, pt, pt_len);
        for (int i = 0; i < 16; i++) {
            mac[i] ^= pt_block[i];
        }
        aes128_encrypt_block(rkeys, mac, mac);
    }

    /* CTR Mode: S_0 for Tag, S_1 for Payload */
    uint8_t a0[16] = {0};
    a0[0] = 0x01U; /* L - 1 */
    (void)memcpy(&a0[1], nonce, 13);
    a0[14] = 0U; a0[15] = 0U;
    uint8_t s0[16];
    aes128_encrypt_block(rkeys, a0, s0);
    for (int i = 0; i < 8; i++) {
        out_tag[i] = mac[i] ^ s0[i];
    }

    if (pt_len > 0) {
        uint8_t a1[16] = {0};
        a1[0] = 0x01U;
        (void)memcpy(&a1[1], nonce, 13);
        a1[14] = 0U; a1[15] = 1U;
        uint8_t s1[16];
        aes128_encrypt_block(rkeys, a1, s1);
        for (size_t i = 0; i < pt_len; i++) {
            out_ct[i] = pt[i] ^ s1[i];
        }
        gateway_crypto_zeroize(s1, sizeof(s1));
    }

    gateway_crypto_zeroize(rkeys, sizeof(rkeys));
    gateway_crypto_zeroize(mac, sizeof(mac));
    gateway_crypto_zeroize(s0, sizeof(s0));
    return ESP_OK;
}

static esp_err_t sw_aes128_ccm_decrypt(const uint8_t key[16],
                                       const uint8_t nonce[13],
                                       const uint8_t *aad, size_t aad_len,
                                       const uint8_t *ct, size_t ct_len,
                                       const uint8_t tag[8],
                                       uint8_t *out_pt)
{
    uint8_t rkeys[176];
    aes128_key_expansion(key, rkeys);

    /* Decrypt payload using CTR S_1 */
    if (ct_len > 0) {
        uint8_t a1[16] = {0};
        a1[0] = 0x01U;
        (void)memcpy(&a1[1], nonce, 13);
        a1[14] = 0U; a1[15] = 1U;
        uint8_t s1[16];
        aes128_encrypt_block(rkeys, a1, s1);
        for (size_t i = 0; i < ct_len; i++) {
            out_pt[i] = ct[i] ^ s1[i];
        }
        gateway_crypto_zeroize(s1, sizeof(s1));
    }

    /* Compute CBC-MAC over decrypted plaintext to verify tag */
    uint8_t b0[16] = {0};
    b0[0] = (aad_len > 0 ? 0x40U : 0x00U) | (((GATEWAY_CRYPTO_CCM_TAG_LEN - 2U) / 2U) << 3U) | (2U - 1U);
    (void)memcpy(&b0[1], nonce, 13);
    b0[14] = (uint8_t)((ct_len >> 8) & 0xFFU);
    b0[15] = (uint8_t)(ct_len & 0xFFU);

    uint8_t mac[16];
    aes128_encrypt_block(rkeys, b0, mac);

    if (aad_len > 0) {
        uint8_t aad_block[16] = {0};
        aad_block[0] = (uint8_t)((aad_len >> 8) & 0xFFU);
        aad_block[1] = (uint8_t)(aad_len & 0xFFU);
        size_t copy_first = (aad_len < 14) ? aad_len : 14;
        (void)memcpy(&aad_block[2], aad, copy_first);
        for (int i = 0; i < 16; i++) {
            mac[i] ^= aad_block[i];
        }
        aes128_encrypt_block(rkeys, mac, mac);
        if (aad_len > 14) {
            uint8_t rem_block[16] = {0};
            (void)memcpy(rem_block, aad + 14, aad_len - 14);
            for (int i = 0; i < 16; i++) {
                mac[i] ^= rem_block[i];
            }
            aes128_encrypt_block(rkeys, mac, mac);
        }
    }

    if (ct_len > 0) {
        uint8_t pt_block[16] = {0};
        (void)memcpy(pt_block, out_pt, ct_len);
        for (int i = 0; i < 16; i++) {
            mac[i] ^= pt_block[i];
        }
        aes128_encrypt_block(rkeys, mac, mac);
    }

    /* Verify tag */
    uint8_t a0[16] = {0};
    a0[0] = 0x01U;
    (void)memcpy(&a0[1], nonce, 13);
    a0[14] = 0U; a0[15] = 0U;
    uint8_t s0[16];
    aes128_encrypt_block(rkeys, a0, s0);
    uint8_t expected_tag[8];
    for (int i = 0; i < 8; i++) {
        expected_tag[i] = mac[i] ^ s0[i];
    }

    int match = constant_time_compare(expected_tag, tag, 8);
    gateway_crypto_zeroize(rkeys, sizeof(rkeys));
    gateway_crypto_zeroize(mac, sizeof(mac));
    gateway_crypto_zeroize(s0, sizeof(s0));
    gateway_crypto_zeroize(expected_tag, sizeof(expected_tag));

    if (match != 0) {
        gateway_crypto_zeroize(out_pt, ct_len);
        return ESP_ERR_INVALID_CRC;
    }
    return ESP_OK;
}

#endif /* ESP_PLATFORM vs HOST */

/* High-level Crypto Dispatchers */

esp_err_t gateway_crypto_decrypt_up_event(const uint8_t *k_session_up,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *ciphertext,
                                          size_t ct_len,
                                          const uint8_t *tag,
                                          uint8_t *out_plaintext)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || ciphertext == NULL ||
        tag == NULL || out_plaintext == NULL || ct_len != 11U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#else
    return sw_aes128_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#endif
}

esp_err_t gateway_crypto_encrypt_down_ack(const uint8_t *k_session_dl,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *plaintext,
                                          size_t pt_len,
                                          uint8_t *out_ciphertext,
                                          uint8_t *out_tag)
{
    if (k_session_dl == NULL || nonce == NULL || aad == NULL || plaintext == NULL ||
        out_ciphertext == NULL || out_tag == NULL || pt_len != 4U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_encrypt(k_session_dl, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#else
    return sw_aes128_ccm_encrypt(k_session_dl, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#endif
}

esp_err_t gateway_crypto_decrypt_down_ack(const uint8_t *k_session_dl,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *ciphertext,
                                          size_t ct_len,
                                          const uint8_t *tag,
                                          uint8_t *out_plaintext)
{
    if (k_session_dl == NULL || nonce == NULL || aad == NULL || ciphertext == NULL ||
        tag == NULL || out_plaintext == NULL || ct_len != 4U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_decrypt(k_session_dl, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#else
    return sw_aes128_ccm_decrypt(k_session_dl, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#endif
}

esp_err_t gateway_crypto_decrypt_up_health(const uint8_t *k_session_up,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *ciphertext,
                                           size_t ct_len,
                                           const uint8_t *tag,
                                           uint8_t *out_plaintext)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || ciphertext == NULL ||
        tag == NULL || out_plaintext == NULL || ct_len != 6U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#else
    return sw_aes128_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#endif
}

esp_err_t gateway_crypto_decrypt_up_diag(const uint8_t *k_session_up,
                                         const uint8_t *nonce,
                                         const uint8_t *aad,
                                         size_t aad_len,
                                         const uint8_t *ciphertext,
                                         size_t ct_len,
                                         const uint8_t *tag,
                                         uint8_t *out_plaintext)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || ciphertext == NULL ||
        tag == NULL || out_plaintext == NULL || ct_len != 8U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#else
    return sw_aes128_ccm_decrypt(k_session_up, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
#endif
}

/* Unit test / simulator encrypt helpers */

esp_err_t gateway_crypto_encrypt_up_event(const uint8_t *k_session_up,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *plaintext,
                                          size_t pt_len,
                                          uint8_t *out_ciphertext,
                                          uint8_t *out_tag)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || plaintext == NULL ||
        out_ciphertext == NULL || out_tag == NULL || pt_len != 11U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#else
    return sw_aes128_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#endif
}

esp_err_t gateway_crypto_encrypt_up_health(const uint8_t *k_session_up,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *plaintext,
                                           size_t pt_len,
                                           uint8_t *out_ciphertext,
                                           uint8_t *out_tag)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || plaintext == NULL ||
        out_ciphertext == NULL || out_tag == NULL || pt_len != 6U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#else
    return sw_aes128_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#endif
}

esp_err_t gateway_crypto_encrypt_up_diag(const uint8_t *k_session_up,
                                         const uint8_t *nonce,
                                         const uint8_t *aad,
                                         size_t aad_len,
                                         const uint8_t *plaintext,
                                         size_t pt_len,
                                         uint8_t *out_ciphertext,
                                         uint8_t *out_tag)
{
    if (k_session_up == NULL || nonce == NULL || aad == NULL || plaintext == NULL ||
        out_ciphertext == NULL || out_tag == NULL || pt_len != 8U) {
        return ESP_ERR_INVALID_ARG;
    }
#if defined(ESP_PLATFORM)
    return psa_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#else
    return sw_aes128_ccm_encrypt(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
#endif
}
