#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_CRYPTO_CCM_TAG_LEN   8U
#define NODE_CRYPTO_CCM_NONCE_LEN 13U
#define NODE_CRYPTO_HMAC_TAG_LEN  16U

/**
 * @brief Initialize node cryptographic subsystem.
 */
esp_err_t node_crypto_init(void);

/**
 * @brief Securely zeroize sensitive memory buffer.
 */
void node_crypto_zeroize(void *buf, size_t len);

/**
 * @brief Compute and verify Beacon HMAC-SHA256-128 tag in constant time.
 *
 * @param k_beacon 32-byte provisioned Beacon key.
 * @param header 16-byte Beacon header transcript.
 * @param header_len Length of header (16).
 * @param expected_tag 16-byte expected HMAC tag.
 * @return ESP_OK if tag matches, ESP_ERR_INVALID_CRC if mismatch, ESP_ERR_INVALID_ARG on NULL.
 */
esp_err_t node_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                        const uint8_t *header,
                                        size_t header_len,
                                        const uint8_t *expected_tag);

/**
 * @brief Compute Beacon HMAC-SHA256-128 tag (for test generation and validation).
 */
esp_err_t node_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                         const uint8_t *header,
                                         size_t header_len,
                                         uint8_t out_tag[NODE_CRYPTO_HMAC_TAG_LEN]);

/**
 * @brief Encrypt UP_EVENT payload (11B) with AES-128-CCM-8.
 *
 * @param k_session_up 16-byte uplink session key.
 * @param nonce 13-byte standard V2 uplink nonce.
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param plaintext 11-byte UP_EVENT plaintext.
 * @param pt_len Length of plaintext (11).
 * @param out_ciphertext Destination buffer for 11-byte ciphertext.
 * @param out_tag Destination buffer for 8-byte CCM tag.
 * @return ESP_OK on success, ESP_ERR_* on error.
 */
esp_err_t node_crypto_encrypt_up_event(const uint8_t *k_session_up,
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
 * @param k_session_down 16-byte downlink session key.
 * @param nonce 13-byte standard V2 downlink nonce.
 * @param aad 7-byte V2 unicast header.
 * @param aad_len Length of AAD (7).
 * @param ciphertext 4-byte DOWN_EVENT_ACK ciphertext.
 * @param ct_len Length of ciphertext (4).
 * @param tag 8-byte received CCM tag.
 * @param out_plaintext Destination buffer for 4-byte decrypted plaintext.
 * @return ESP_OK on valid tag and decryption, ESP_ERR_INVALID_CRC if tag invalid.
 */
esp_err_t node_crypto_decrypt_down_ack(const uint8_t *k_session_down,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *ciphertext,
                                       size_t ct_len,
                                       const uint8_t *tag,
                                       uint8_t *out_plaintext);

/**
 * @brief Encrypt DOWN_EVENT_ACK payload (4B) with AES-128-CCM-8 (for test and simulator use).
 */
esp_err_t node_crypto_encrypt_down_ack(const uint8_t *k_session_down,
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
