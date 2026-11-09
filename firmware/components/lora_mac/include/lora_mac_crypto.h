#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file lora_mac_crypto.h
 * @brief Cryptographic subsystem for V2 LoRa MAC (AES-128-CCM-8 and Beacon HMAC).
 *
 * Authority: ADR-0003, ADR-0004, C Coding Standard v2 (SEC-001, SEC-004, SEC-005, MEM-001),
 *            contracts/radio-mac/specification.md (Revision 0.3.0-draft).
 * Owner Decisions: DEC-127-01, DEC-127-02, DEC-MH-01, DEC-MH-02, DEC-MH-08.
 *
 * Provides:
 * - Constant-time HMAC-SHA256-128 tag generation and verification for Beacon 0x43.
 * - AES-128-CCM-8 authenticated encryption and decryption for UP_EVENT 0x41.
 * - AES-128-CCM-8 authenticated encryption and decryption for DOWN_EVENT_ACK 0x42.
 * - Dual-backend: PSA Crypto on ESP-IDF v6.1; portable RFC 3610 / FIPS 180-4 for host unit testing.
 */

#define LORA_MAC_CRYPTO_CCM_TAG_LEN    (8U)
#define LORA_MAC_CRYPTO_CCM_NONCE_LEN  (13U)
#define LORA_MAC_CRYPTO_HMAC_TAG_LEN   (16U)
#define LORA_MAC_CRYPTO_KEY_LEN        (16U)
#define LORA_MAC_CRYPTO_BEACON_KEY_LEN (32U)

/* Backwards-compatibility aliases for legacy node_crypto callers */
#define NODE_CRYPTO_CCM_TAG_LEN        LORA_MAC_CRYPTO_CCM_TAG_LEN
#define NODE_CRYPTO_CCM_NONCE_LEN      LORA_MAC_CRYPTO_CCM_NONCE_LEN
#define NODE_CRYPTO_HMAC_TAG_LEN       LORA_MAC_CRYPTO_HMAC_TAG_LEN

/**
 * @brief Initialize cryptographic subsystem (initializes PSA Crypto on ESP-IDF).
 *
 * @return ESP_OK on success, ESP_FAIL on PSA crypto initialization failure.
 */
esp_err_t lora_mac_crypto_init(void);

/**
 * @brief Securely zeroize sensitive memory buffer (C Standard v2 SEC-005, MEM-005).
 *
 * @param buf Pointer to buffer to clear.
 * @param len Length in bytes.
 */
void lora_mac_crypto_zeroize(void *buf, size_t len);

/**
 * @brief Compute Beacon HMAC-SHA256-128 tag (16 octets) over header transcript.
 *
 * @param k_beacon 32-byte provisioned Beacon key.
 * @param header Beacon header transcript.
 * @param header_len Length of header transcript (typically 16).
 * @param out_tag Destination buffer for 16-byte HMAC tag.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on NULL pointers or zero length.
 */
esp_err_t lora_mac_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                              const uint8_t *header,
                                              size_t header_len,
                                              uint8_t out_tag[LORA_MAC_CRYPTO_HMAC_TAG_LEN]);

/**
 * @brief Verify Beacon HMAC-SHA256-128 tag in constant time (SEC-004).
 *
 * @param k_beacon 32-byte provisioned Beacon key.
 * @param header Beacon header transcript.
 * @param header_len Length of header transcript (typically 16).
 * @param expected_tag 16-byte received HMAC tag.
 * @return ESP_OK if valid, ESP_ERR_INVALID_CRC if mismatch, ESP_ERR_INVALID_ARG on NULL/zero length.
 */
esp_err_t lora_mac_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                             const uint8_t *header,
                                             size_t header_len,
                                             const uint8_t *expected_tag);

/**
 * @brief Encrypt UP_EVENT payload (11B) with AES-128-CCM-8.
 *
 * @param k_session_up 16-byte uplink session key.
 * @param nonce 13-byte standard V2 uplink nonce.
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param plaintext 11-byte UP_EVENT plaintext.
 * @param pt_len Length of plaintext (11).
 * @param out_ciphertext Destination buffer for ciphertext.
 * @param out_tag Destination buffer for 8-byte CCM tag.
 * @return ESP_OK on success, ESP_ERR_* on error.
 */
esp_err_t lora_mac_crypto_encrypt_up_event(const uint8_t *k_session_up,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *plaintext,
                                           size_t pt_len,
                                           uint8_t *out_ciphertext,
                                           uint8_t *out_tag);

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
 * @param out_plaintext Destination buffer for decrypted plaintext.
 * @return ESP_OK on valid tag and decryption, ESP_ERR_INVALID_CRC if tag mismatch,
 *         ESP_ERR_INVALID_ARG on parameter bounds error.
 */
esp_err_t lora_mac_crypto_decrypt_up_event(const uint8_t *k_session_up,
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
 * @param out_ciphertext Destination buffer for ciphertext.
 * @param out_tag Destination buffer for 8-byte CCM-8 tag.
 * @return ESP_OK on success, ESP_ERR_* on error.
 */
esp_err_t lora_mac_crypto_encrypt_down_ack(const uint8_t *k_session_dl,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *plaintext,
                                           size_t pt_len,
                                           uint8_t *out_ciphertext,
                                           uint8_t *out_tag);

/**
 * @brief Decrypt DOWN_EVENT_ACK payload (4B) and verify AES-128-CCM-8 tag.
 *
 * @param k_session_dl 16-byte downlink session key.
 * @param nonce 13-byte standard V2 downlink nonce.
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param ciphertext 4-byte DOWN_EVENT_ACK ciphertext.
 * @param ct_len Length of ciphertext (4).
 * @param tag 8-byte received CCM-8 tag.
 * @param out_plaintext Destination buffer for decrypted plaintext.
 * @return ESP_OK on valid tag and decryption, ESP_ERR_INVALID_CRC if tag mismatch,
 *         ESP_ERR_INVALID_ARG on parameter bounds error.
 */
esp_err_t lora_mac_crypto_decrypt_down_ack(const uint8_t *k_session_dl,
                                           const uint8_t *nonce,
                                           const uint8_t *aad,
                                           size_t aad_len,
                                           const uint8_t *ciphertext,
                                           size_t ct_len,
                                           const uint8_t *tag,
                                           uint8_t *out_plaintext);

/**
 * @brief Generic AES-128-CCM-8 encryption (M=8, L=2, Nonce=13).
 */
esp_err_t lora_mac_crypto_ccm_encrypt(const uint8_t key[16],
                                      const uint8_t nonce[13],
                                      const uint8_t *aad, size_t aad_len,
                                      const uint8_t *plaintext, size_t pt_len,
                                      uint8_t *out_ciphertext,
                                      uint8_t out_tag[8]);

/**
 * @brief Generic AES-128-CCM-8 decryption and authentication (M=8, L=2, Nonce=13).
 */
esp_err_t lora_mac_crypto_ccm_decrypt(const uint8_t key[16],
                                      const uint8_t nonce[13],
                                      const uint8_t *aad, size_t aad_len,
                                      const uint8_t *ciphertext, size_t ct_len,
                                      const uint8_t tag[8],
                                      uint8_t *out_plaintext);

#ifdef __cplusplus
}
#endif
