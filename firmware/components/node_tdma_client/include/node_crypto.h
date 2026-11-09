#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "lora_mac_crypto.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file node_crypto.h
 * @brief Legacy compatibility header forwarding to lora_mac_crypto.
 *
 * Authority: Issue #274, C Coding Standard v2.
 */

#define NODE_CRYPTO_CCM_TAG_LEN   LORA_MAC_CRYPTO_CCM_TAG_LEN
#define NODE_CRYPTO_CCM_NONCE_LEN LORA_MAC_CRYPTO_CCM_NONCE_LEN
#define NODE_CRYPTO_HMAC_TAG_LEN  LORA_MAC_CRYPTO_HMAC_TAG_LEN

esp_err_t node_crypto_init(void);

void node_crypto_zeroize(void *buf, size_t len);

esp_err_t node_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                         const uint8_t *header,
                                         size_t header_len,
                                         const uint8_t *expected_tag);

esp_err_t node_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                          const uint8_t *header,
                                          size_t header_len,
                                          uint8_t out_tag[NODE_CRYPTO_HMAC_TAG_LEN]);

esp_err_t node_crypto_encrypt_up_event(const uint8_t *k_session_up,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *plaintext,
                                       size_t pt_len,
                                       uint8_t *out_ciphertext,
                                       uint8_t *out_tag);

esp_err_t node_crypto_decrypt_down_ack(const uint8_t *k_session_down,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *ciphertext,
                                       size_t ct_len,
                                       const uint8_t *tag,
                                       uint8_t *out_plaintext);

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
