#include "node_crypto.h"
#include "lora_mac_crypto.h"

#if !defined(ESP_PLATFORM)
/* For host unit tests that compile node_crypto.c standalone without lora_mac_crypto.c */
#include "../../lora_mac/src/lora_mac_crypto.c"
#endif

esp_err_t node_crypto_init(void)
{
    return lora_mac_crypto_init();
}

void node_crypto_zeroize(void *buf, size_t len)
{
    lora_mac_crypto_zeroize(buf, len);
}

esp_err_t node_crypto_compute_beacon_hmac(const uint8_t *k_beacon,
                                          const uint8_t *header,
                                          size_t header_len,
                                          uint8_t out_tag[NODE_CRYPTO_HMAC_TAG_LEN])
{
    return lora_mac_crypto_compute_beacon_hmac(k_beacon, header, header_len, out_tag);
}

esp_err_t node_crypto_verify_beacon_hmac(const uint8_t *k_beacon,
                                         const uint8_t *header,
                                         size_t header_len,
                                         const uint8_t *expected_tag)
{
    return lora_mac_crypto_verify_beacon_hmac(k_beacon, header, header_len, expected_tag);
}

esp_err_t node_crypto_encrypt_up_event(const uint8_t *k_session_up,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *plaintext,
                                       size_t pt_len,
                                       uint8_t *out_ciphertext,
                                       uint8_t *out_tag)
{
    return lora_mac_crypto_encrypt_up_event(k_session_up, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
}

esp_err_t node_crypto_decrypt_down_ack(const uint8_t *k_session_down,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *ciphertext,
                                       size_t ct_len,
                                       const uint8_t *tag,
                                       uint8_t *out_plaintext)
{
    return lora_mac_crypto_decrypt_down_ack(k_session_down, nonce, aad, aad_len, ciphertext, ct_len, tag, out_plaintext);
}

esp_err_t node_crypto_encrypt_down_ack(const uint8_t *k_session_down,
                                       const uint8_t *nonce,
                                       const uint8_t *aad,
                                       size_t aad_len,
                                       const uint8_t *plaintext,
                                       size_t pt_len,
                                       uint8_t *out_ciphertext,
                                       uint8_t *out_tag)
{
    return lora_mac_crypto_encrypt_down_ack(k_session_down, nonce, aad, aad_len, plaintext, pt_len, out_ciphertext, out_tag);
}
