#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file gateway_crypto.h
 * @brief Cryptographic subsystem for Gateway Master TDMA Engine.
 *
 * Authority: DEC-127-01, DEC-127-02, DEC-MH-01, DEC-MH-07, DEC-MH-08,
 *            C Coding Standard v2 (SEC-001, SEC-004, SEC-005, MEM-001).
 * Supports:
 * - HMAC-SHA256-128 tag generation and verification for Beacon 0x43 (DEC-MH-01).
 * - AES-128-CCM-8 decryption and verification for UP_EVENT 0x41 (DEC-127-01 / DEC-127-02).
 * - AES-128-CCM-8 encryption for DOWN_EVENT_ACK 0x42 with downlink nonce (dir=0x02).
 * - AES-128-CCM-8 decryption for Maintenance UP_HEALTH_REPLY 0x44 and UP_DIAG_METRICS 0x4A.
 * Dual-backend: PSA Crypto on ESP-IDF v6.1; portable RFC 3610 / FIPS 180-4 for host unit testing.
 */

#define GATEWAY_CRYPTO_CCM_TAG_LEN    (8U)
#define GATEWAY_CRYPTO_CCM_NONCE_LEN  (13U)
#define GATEWAY_CRYPTO_HMAC_TAG_LEN   (16U)
#define GATEWAY_CRYPTO_KEY_LEN        (16U)
#define GATEWAY_CRYPTO_BEACON_KEY_LEN (32U)

/**
 * @brief Initialize cryptographic subsystem (initializes PSA Crypto on ESP32).
 */
esp_err_t gateway_crypto_init(void);

/**
 * @brief Securely zeroize sensitive memory buffer (SEC-005).
 */
void gateway_crypto_zeroize(void *buf, size_t len);

/**
 * @brief Compute Beacon HMAC-SHA256-128 tag (16 octets) over 16-byte header transcript.
 *
 * @param k_beacon 32-byte provisioned Beacon key.
 * @param header 16-byte Beacon header transcript.
 * @param header_len Length of header (16).
 * @param out_tag Output destination for 16-byte HMAC tag.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on invalid arguments.
 */
esp_err_t gateway_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                             const uint8_t *header,
                                             size_t header_len,
                                             uint8_t out_tag[GATEWAY_CRYPTO_HMAC_TAG_LEN]);

/**
 * @brief Constant-time verification of Beacon HMAC-SHA256-128 tag.
 *
 * @param k_beacon 32-byte provisioned Beacon key.
 * @param header 16-byte Beacon header transcript.
 * @param header_len Length of header (16).
 * @param expected_tag 16-byte received HMAC tag.
 * @return ESP_OK if valid, ESP_ERR_INVALID_CRC if mismatch, ESP_ERR_INVALID_ARG on NULL.
 */
esp_err_t gateway_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                            const uint8_t *header,
                                            size_t header_len,
                                            const uint8_t *expected_tag);

/**
 * @brief Decrypt UP_EVENT payload (11B) and verify AES-128-CCM-8 tag.
 *
 * @param k_session_up 16-byte uplink session key.
 * @param nonce 13-byte standard V2 uplink nonce.
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param ciphertext 11-byte UP_EVENT ciphertext.
 * @param ct_len Length of ciphertext (11).
 * @param tag 8-byte received CCM-8 tag.
 * @param out_plaintext Destination buffer for 11-byte decrypted plaintext.
 * @return ESP_OK on valid tag and decryption, ESP_ERR_INVALID_CRC if tag mismatch,
 *         ESP_ERR_INVALID_ARG on parameter bounds error.
 */
esp_err_t gateway_crypto_decrypt_up_event(const uint8_t *k_session_up,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *ciphertext,
                                          size_t ct_len,
                                          const uint8_t *tag,
                                          uint8_t *out_plaintext);

/**
 * @brief Encrypt DOWN_EVENT_ACK payload (4B) with AES-128-CCM-8.
 *
 * @param k_session_dl 16-byte downlink session key.
 * @param nonce 13-byte standard V2 downlink nonce (dir=0x02).
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param plaintext 4-byte DOWN_EVENT_ACK plaintext.
 * @param pt_len Length of plaintext (4).
 * @param out_ciphertext Destination buffer for 4-byte ciphertext.
 * @param out_tag Destination buffer for 8-byte CCM-8 tag.
 * @return ESP_OK on success, ESP_ERR_* on error.
 */
esp_err_t gateway_crypto_encrypt_down_ack(const uint8_t *k_session_dl,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *plaintext,
                                          size_t pt_len,
                                          uint8_t *out_ciphertext,
                                          uint8_t *out_tag);

/**
 * @brief Decrypt DOWN_EVENT_ACK payload (4B) and verify AES-128-CCM-8 tag.
 */
esp_err_t gateway_crypto_decrypt_down_ack(const uint8_t *k_session_dl,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *ciphertext,
                                          size_t ct_len,
                                          const uint8_t *tag,
                                          uint8_t *out_plaintext);

/**
 * @brief Decrypt UP_HEALTH_REPLY payload (6B) and verify AES-128-CCM-8 tag.
 */
esp_err_t gateway_crypto_decrypt_up_health(const uint8_t *k_session_up,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *ciphertext,
                                           size_t ct_len,
                                           const uint8_t *tag,
                                           uint8_t *out_plaintext);

/**
 * @brief Decrypt UP_DIAG_METRICS payload (8B) and verify AES-128-CCM-8 tag (DEC-MH-08).
 */
esp_err_t gateway_crypto_decrypt_up_diag(const uint8_t *k_session_up,
                                         const uint8_t *nonce,
                                         const uint8_t *aad,
                                         size_t aad_len,
                                         const uint8_t *ciphertext,
                                         size_t ct_len,
                                         const uint8_t *tag,
                                         uint8_t *out_plaintext);

/* Test & Simulator helpers for generating verified packets in unit tests */
esp_err_t gateway_crypto_encrypt_up_event(const uint8_t *k_session_up,
                                          const uint8_t *nonce,
                                          const uint8_t *aad,
                                          size_t aad_len,
                                          const uint8_t *plaintext,
                                          size_t pt_len,
                                          uint8_t *out_ciphertext,
                                          uint8_t *out_tag);

esp_err_t gateway_crypto_encrypt_up_health(const uint8_t *k_session_up,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *plaintext,
                                           size_t pt_len,
                                           uint8_t *out_ciphertext,
                                           uint8_t *out_tag);

esp_err_t gateway_crypto_encrypt_up_diag(const uint8_t *k_session_up,
                                         const uint8_t *nonce,
                                         const uint8_t *aad,
                                         size_t aad_len,
                                         const uint8_t *plaintext,
                                         size_t pt_len,
                                         uint8_t *out_ciphertext,
                                         uint8_t *out_tag);

#ifdef __cplusplus
}
#endif
