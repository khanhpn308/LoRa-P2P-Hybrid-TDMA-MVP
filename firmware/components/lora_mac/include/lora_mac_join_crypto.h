#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "lora_mac.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LORA_MAC_X25519_KEY_LEN     (32U)
#define LORA_MAC_SHA256_HASH_LEN    (32U)
#define LORA_MAC_HMAC_PROOF_LEN     (16U)
#define LORA_MAC_HMAC_TAG_LEN       (8U)

typedef struct {
    uint8_t k_jreq[32];
    uint8_t k_jgrant[32];
    uint8_t k_jconf[32];
    uint8_t k_jfinish[32];
    uint8_t k_jready[32];
} lora_mac_k_join_expanded_keys_t;

typedef struct {
    uint8_t prk_session[32];
    uint8_t k_kc_up[32];
    uint8_t k_kc_down[32];
    uint8_t k_session_root[32];
    uint8_t k_session_up[32];
    uint8_t k_session_dl[32];
} lora_mac_session_keys_t;

/**
 * @brief Zeroize a memory buffer securely (MEM-005, SEC-005).
 */
void lora_mac_crypto_zeroize(void *buf, size_t len);

/**
 * @brief Constant-time buffer comparison.
 *
 * @return 0 if buffers are equal, -1 if different.
 */
int lora_mac_crypto_constant_time_memcmp(const void *a, const void *b, size_t len);

/**
 * @brief Check if a buffer is all zeros in constant time.
 *
 * @return true if all bytes are 0x00, false otherwise.
 */
bool lora_mac_crypto_is_all_zero(const uint8_t *buf, size_t len);

/**
 * @brief Generate ephemeral X25519 keypair.
 *
 * @param[out] out_priv 32-byte private key.
 * @param[out] out_pub  32-byte public key.
 * @return ESP_OK on success, ESP_ERR_* on failure.
 */
esp_err_t lora_mac_crypto_x25519_keypair(uint8_t out_priv[32], uint8_t out_pub[32]);

/**
 * @brief Perform RFC 7748 X25519 Diffie-Hellman scalar multiplication with fail-closed check (DEC-SEC-07).
 *
 * If the resulting shared secret is all zeros (Z == 0^32) or peer_pub is all zeros,
 * immediately zeroizes out_shared and returns ESP_ERR_INVALID_RESPONSE.
 *
 * @param[in]  priv        32-byte local private key.
 * @param[in]  peer_pub    32-byte peer public key.
 * @param[out] out_shared  32-byte computed shared secret Z.
 * @return ESP_OK on success, ESP_ERR_INVALID_RESPONSE on all-zero point abort, ESP_ERR_INVALID_ARG on NULL.
 */
esp_err_t lora_mac_crypto_x25519_ecdh(const uint8_t priv[32],
                                      const uint8_t peer_pub[32],
                                      uint8_t out_shared[32]);

#if !defined(ESP_PLATFORM)
/**
 * @brief Test hook to simulate RFC 7748 all-zeros shared secret abort on host.
 */
void lora_mac_crypto_mock_set_force_zero_shared(bool force_zero);
#endif

/**
 * @brief Compute SHA-256 digest.
 */
esp_err_t lora_mac_crypto_sha256(const uint8_t *data, size_t len, uint8_t out_hash[32]);

/**
 * @brief Compute HMAC-SHA256 tag.
 */
esp_err_t lora_mac_crypto_hmac_sha256(const uint8_t *key, size_t key_len,
                                      const uint8_t *data, size_t data_len,
                                      uint8_t out_tag[32]);

/**
 * @brief HKDF-Extract using SHA-256.
 */
esp_err_t lora_mac_crypto_hkdf_extract(const uint8_t *salt, size_t salt_len,
                                       const uint8_t *ikm, size_t ikm_len,
                                       uint8_t out_prk[32]);

/**
 * @brief HKDF-Expand using SHA-256.
 */
esp_err_t lora_mac_crypto_hkdf_expand(const uint8_t *prk, size_t prk_len,
                                      const uint8_t *info, size_t info_len,
                                      uint8_t *out_okm, size_t okm_len);

/**
 * @brief Derive Backend-bound keys from provisioned K_JOIN.
 *
 * SALT = "LP2P/V2/JOIN-ROOT" || NETWORK_ID_BE4 || DEVICE_MAC6 || DEVICE_GENERATION_BE2
 * PRK_JOIN = HKDF-Extract(salt=SALT, IKM=K_JOIN)
 * K_JREQ   = HKDF-Expand(PRK_JOIN, "LP2P/V2/JOIN-REQ", 32)
 * K_JGRANT = HKDF-Expand(PRK_JOIN, "LP2P/V2/JOIN-GRANT", 32)
 * K_JCONF  = HKDF-Expand(PRK_JOIN, "LP2P/V2/JOIN-CONF", 32)
 * K_JFINISH= HKDF-Expand(PRK_JOIN, "LP2P/V2/JOIN-FINISH", 32)
 * K_JREADY = HKDF-Expand(PRK_JOIN, "LP2P/V2/JOIN-READY", 32)
 */
esp_err_t lora_mac_join_derive_k_join_keys(uint32_t network_id,
                                           const uint8_t device_mac[6],
                                           uint16_t device_generation,
                                           const uint8_t k_join[32],
                                           lora_mac_k_join_expanded_keys_t *out_keys);

/**
 * @brief Compute 16-byte JOIN_PROOF for UP_JOIN_HELLO frame.
 *
 * M_HELLO = "LP2P/V2/M-HELLO" || NETWORK_ID_BE4 || HELLO[0..51]
 * JOIN_PROOF = HMAC-SHA256(K_JREQ, M_HELLO)[0..15]
 */
esp_err_t lora_mac_join_compute_hello_proof(uint32_t network_id,
                                            const uint8_t hello_prefix52[52],
                                            const uint8_t k_jreq[32],
                                            uint8_t out_proof[16]);

/**
 * @brief Verify 16-byte JOIN_PROOF for UP_JOIN_HELLO frame.
 */
esp_err_t lora_mac_join_verify_hello_proof(uint32_t network_id,
                                           const uint8_t hello_prefix52[52],
                                           const uint8_t k_jreq[32],
                                           const uint8_t expected_proof[16]);

/**
 * @brief Compute 16-byte GRANT_PROOF for DOWN_JOIN_GRANT frame.
 *
 * M_GRANT = "LP2P/V2/M-GRANT" || NETWORK_ID_BE4 || HELLO68 || GRANT[0..49] (137 bytes total)
 * GRANT_PROOF = HMAC-SHA256(K_JGRANT, M_GRANT)[0..15]
 */
esp_err_t lora_mac_join_compute_grant_proof(uint32_t network_id,
                                            const uint8_t hello68[68],
                                            const uint8_t grant_prefix50[50],
                                            const uint8_t k_jgrant[32],
                                            uint8_t out_proof[16]);

/**
 * @brief Verify 16-byte GRANT_PROOF for DOWN_JOIN_GRANT frame.
 */
esp_err_t lora_mac_join_verify_grant_proof(uint32_t network_id,
                                           const uint8_t hello68[68],
                                           const uint8_t grant_prefix50[50],
                                           const uint8_t k_jgrant[32],
                                           const uint8_t expected_proof[16]);

/**
 * @brief Compute Transcript Hash TH.
 *
 * TH = SHA256("LP2P/V2/TH-JOIN" || NETWORK_ID_BE4 || HELLO68 || GRANT66)
 */
esp_err_t lora_mac_join_compute_th(uint32_t network_id,
                                   const uint8_t hello68[68],
                                   const uint8_t grant66[66],
                                   uint8_t out_th[32]);

/**
 * @brief Derive operational session keys from TH and Z.
 *
 * PRK_SESSION    = HKDF-Extract(salt=TH, IKM=Z)
 * K_KC_UP        = HKDF-Expand(PRK_SESSION, "LP2P/V2/KC-UP", 32)
 * K_KC_DOWN      = HKDF-Expand(PRK_SESSION, "LP2P/V2/KC-DOWN", 32)
 * K_SESSION_ROOT = HKDF-Expand(PRK_SESSION, "LP2P/V2/SESSION-ROOT", 32)
 * K_SESSION_UP   = HKDF-Expand(K_SESSION_ROOT, "LP2P/V2/DATA-UP", 32)
 * K_SESSION_DL   = HKDF-Expand(K_SESSION_ROOT, "LP2P/V2/DATA-DOWN", 32)
 */
esp_err_t lora_mac_join_derive_session_keys(const uint8_t th[32],
                                            const uint8_t z[32],
                                            lora_mac_session_keys_t *out_keys);

/**
 * @brief Compute UP_JOIN_KEY_CONFIRM tags (GW_KC_TAG 8B and BACKEND_PROOF 16B).
 *
 * M_GW_CONF = "LP2P/V2/M-GW-CONF" || TH || CONFIRM_PREFIX7
 * GW_KC_TAG = HMAC(K_KC_UP, M_GW_CONF)[0..7]
 *
 * M_BE_CONF = "LP2P/V2/M-BACKEND-CONF" || NETWORK_ID_BE4 || TH || CONFIRM_PREFIX7 || GW_KC_TAG8
 * BACKEND_PROOF = HMAC(K_JCONF, M_BE_CONF)[0..15]
 */
esp_err_t lora_mac_join_compute_confirm_tags(uint32_t network_id,
                                             const uint8_t th[32],
                                             const uint8_t confirm_prefix7[7],
                                             const uint8_t k_kc_up[32],
                                             const uint8_t k_jconf[32],
                                             uint8_t out_gw_kc_tag[8],
                                             uint8_t out_backend_proof[16]);

/**
 * @brief Verify Gateway Confirm Tag (GW_KC_TAG 8B).
 */
esp_err_t lora_mac_join_verify_confirm_gw_tag(const uint8_t th[32],
                                              const uint8_t confirm_prefix7[7],
                                              const uint8_t k_kc_up[32],
                                              const uint8_t expected_tag[8]);

/**
 * @brief Compute DOWN_JOIN_FINISH tags (GW_FINISH_TAG 8B and BACKEND_FINISH_PROOF 16B).
 *
 * M_GW_FINISH = "LP2P/V2/M-GW-FINISH" || TH || FINISH_PREFIX7
 * GW_FINISH_TAG = HMAC(K_KC_DOWN, M_GW_FINISH)[0..7]
 *
 * M_BE_FINISH = "LP2P/V2/M-BACKEND-FINISH" || NETWORK_ID_BE4 || TH || FINISH_PREFIX7 || GW_FINISH_TAG8
 * BACKEND_FINISH_PROOF = HMAC(K_JFINISH, M_BE_FINISH)[0..15]
 */
esp_err_t lora_mac_join_compute_finish_tags(uint32_t network_id,
                                            const uint8_t th[32],
                                            const uint8_t finish_prefix7[7],
                                            const uint8_t k_kc_down[32],
                                            const uint8_t k_jfinish[32],
                                            uint8_t out_gw_finish_tag[8],
                                            uint8_t out_backend_finish_proof[16]);

/**
 * @brief Verify DOWN_JOIN_FINISH tags at Node.
 */
esp_err_t lora_mac_join_verify_finish_tags(uint32_t network_id,
                                           const uint8_t th[32],
                                           const uint8_t finish_prefix7[7],
                                           const uint8_t k_kc_down[32],
                                           const uint8_t k_jfinish[32],
                                           const uint8_t expected_gw_tag[8],
                                           const uint8_t expected_be_proof[16]);

/**
 * @brief Compute UP_JOIN_READY tags (GW_READY_TAG 8B and BACKEND_READY_PROOF 16B).
 *
 * M_GW_READY = "LP2P/V2/M-GW-READY" || TH || FINISH31 || READY_PREFIX7
 * GW_READY_TAG = HMAC(K_KC_UP, M_GW_READY)[0..7]
 *
 * M_BE_READY = "LP2P/V2/M-BACKEND-READY" || NETWORK_ID_BE4 || TH || FINISH31 || READY_PREFIX7 || GW_READY_TAG8
 * BACKEND_READY_PROOF = HMAC(K_JREADY, M_BE_READY)[0..15]
 */
esp_err_t lora_mac_join_compute_ready_tags(uint32_t network_id,
                                           const uint8_t th[32],
                                           const uint8_t finish31[31],
                                           const uint8_t ready_prefix7[7],
                                           const uint8_t k_kc_up[32],
                                           const uint8_t k_jready[32],
                                           uint8_t out_gw_ready_tag[8],
                                           uint8_t out_backend_ready_proof[16]);

/**
 * @brief Verify Gateway Ready Tag (GW_READY_TAG 8B) at Gateway.
 */
esp_err_t lora_mac_join_verify_ready_gw_tag(const uint8_t th[32],
                                            const uint8_t finish31[31],
                                            const uint8_t ready_prefix7[7],
                                            const uint8_t k_kc_up[32],
                                            const uint8_t expected_tag[8]);

#ifdef __cplusplus
}
#endif
