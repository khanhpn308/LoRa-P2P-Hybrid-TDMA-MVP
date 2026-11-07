#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "esp_system.h"
#include "session_key_crypto.h"

// Test vectors generated deterministically and shared with Go test suite
static const uint8_t K_GW_WRAP[32] = {
    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
    0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f, 0x10,
    0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17, 0x18,
    0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20
};

static const uint8_t K_SESSION_UP[32] = {
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16, 0x17,
    0x18, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f,
    0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
    0x28, 0x29, 0x2a, 0x2b, 0x2c, 0x2d, 0x2e, 0x2f
};

static const uint8_t K_SESSION_DL[32] = {
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
    0x38, 0x39, 0x3a, 0x3b, 0x3c, 0x3d, 0x3e, 0x3f,
    0x40, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47,
    0x48, 0x49, 0x4a, 0x4b, 0x4c, 0x4d, 0x4e, 0x4f
};

static const uint8_t NONCE[12] = {
    0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01
};

static const uint8_t DEVICE_MAC[6] = {0x24, 0x6f, 0x28, 0x12, 0x34, 0x56};
static const uint8_t SESSION_ID[16] = {
    0x55, 0x0e, 0x84, 0x00, 0xe2, 0x9b, 0x41, 0xd4,
    0xa7, 0x16, 0x44, 0x66, 0x55, 0x44, 0x00, 0x00
};
static const uint8_t INSTALL_ID[16] = {
    0xf4, 0x7a, 0xc1, 0x0b, 0x58, 0xcc, 0x43, 0x72,
    0xa5, 0x67, 0x0e, 0x02, 0xb2, 0xc3, 0xd4, 0x79
};

// SHA256("TEST_SESSION_CONTEXT_32_BYTES_01")
static const uint8_t SESSION_CONTEXT_HASH[32] = {
    0x93, 0x83, 0xd9, 0xef, 0x80, 0xa1, 0x18, 0x0a,
    0x55, 0xa1, 0x98, 0x7f, 0xdf, 0x96, 0x74, 0x86,
    0xa6, 0xda, 0xd8, 0x7f, 0x47, 0x4f, 0xd4, 0x51,
    0x37, 0x60, 0x72, 0x22, 0x6c, 0x08, 0x6e, 0x6f
};

static int run_all_tests(void) {
    int passed = 0;
    int failed = 0;

    printf("\n=== RUNNING ESP-IDF MBEDTLS SESSION KEY INTEROP TESTS ===\n");

    sk_status_t status = sk_crypto_init();
    if (status != SK_OK) {
        printf("FAILED: sk_crypto_init returned %d\n", status);
        return 1;
    }
    printf("INIT: PSA Crypto initialized successfully\n");

    // 1. Build Install AAD
    sk_install_aad_params_t aad_params = {
        .topic = "iot/v1/gw/gw01/downlink/session-key-install",
        .schema_version = "1.1-draft",
        .install_protocol_version = 1,
        .aad_version = 1,
        .gateway_id = "gw01",
        .target_gw_id = 1,
        .node_id = 14,
        .key_id = 1,
        .session_revision = 7,
        .assignment_revision = 3,
        .not_before_ms = 1793592000000ULL, // 2026-11-02T04:00:00Z
        .expires_at_ms = 1793678400000ULL, // 2026-11-03T04:00:00Z
        .install_deadline_ms = 1793592300000ULL, // 2026-11-02T04:05:00Z
        .wrap_key_id = 1,
        .crypto_suite = "AES-256-GCM",
    };
    memcpy((void *)aad_params.device_mac, DEVICE_MAC, 6);
    memcpy((void *)aad_params.session_id, SESSION_ID, 16);
    memcpy((void *)aad_params.install_id, INSTALL_ID, 16);
    memcpy((void *)aad_params.session_context_hash, SESSION_CONTEXT_HASH, 32);
    memcpy((void *)aad_params.nonce, NONCE, 12);

    uint8_t aad[512];
    size_t aad_len = 0;
    status = sk_build_install_aad(&aad_params, aad, sizeof(aad), &aad_len);
    if (status == SK_OK && aad_len == 232) {
        printf("TEST 1: sk_build_install_aad length=232 ... PASSED\n");
        passed++;
    } else {
        printf("TEST 1: sk_build_install_aad ... FAILED (status=%d, len=%zu)\n", status, aad_len);
        failed++;
    }

    // 2. Wrap session keys (Backend producer test)
    uint8_t ciphertext[64];
    uint8_t tag[16];
    status = sk_wrap_session_keys(K_GW_WRAP, NONCE, K_SESSION_UP, K_SESSION_DL, aad, aad_len, ciphertext, tag);
    if (status == SK_OK) {
        printf("TEST 2: sk_wrap_session_keys ... PASSED\n");
        passed++;
    } else {
        printf("TEST 2: sk_wrap_session_keys ... FAILED (status=%d)\n", status);
        failed++;
    }

    // 3. Unwrap session keys (Gateway consumer test)
    uint8_t unwrapped_up[32];
    uint8_t unwrapped_dl[32];
    status = sk_unwrap_session_keys(K_GW_WRAP, NONCE, ciphertext, tag, aad, aad_len, unwrapped_up, unwrapped_dl);
    if (status == SK_OK &&
        memcmp(unwrapped_up, K_SESSION_UP, 32) == 0 &&
        memcmp(unwrapped_dl, K_SESSION_DL, 32) == 0) {
        printf("TEST 3: sk_unwrap_session_keys round-trip ... PASSED\n");
        passed++;
    } else {
        printf("TEST 3: sk_unwrap_session_keys ... FAILED (status=%d)\n", status);
        failed++;
    }

    // 4. Derive K_ACK
    uint8_t k_ack[32];
    status = sk_derive_k_ack(K_GW_WRAP, 1, "gw01", k_ack);
    if (status == SK_OK) {
        printf("TEST 4: sk_derive_k_ack HKDF-SHA256 ... PASSED\n");
        passed++;
    } else {
        printf("TEST 4: sk_derive_k_ack ... FAILED (status=%d)\n", status);
        failed++;
    }

    // 5. Build ACK transcript (INSTALLED)
    sk_ack_transcript_params_t ack_params = {
        .topic = "iot/v1/gw/gw01/uplink/session-key-ack",
        .schema_version = "1.1-draft",
        .ack_protocol_version = 1,
        .gateway_id = "gw01",
        .session_revision = 7,
        .wrap_key_id = 1,
        .status = "INSTALLED",
        .reason_code = "NONE",
    };
    memcpy((void *)ack_params.install_id, INSTALL_ID, 16);
    memcpy((void *)ack_params.session_id, SESSION_ID, 16);

    uint8_t m_ack[512];
    size_t m_ack_len = 0;
    status = sk_build_ack_transcript(&ack_params, m_ack, sizeof(m_ack), &m_ack_len);
    if (status == SK_OK && m_ack_len == 138) {
        printf("TEST 5: sk_build_ack_transcript length=138 ... PASSED\n");
        passed++;
    } else {
        printf("TEST 5: sk_build_ack_transcript ... FAILED (status=%d, len=%zu)\n", status, m_ack_len);
        failed++;
    }

    // 6. Compute & verify ACK tag (INSTALLED)
    uint8_t ack_tag[16];
    status = sk_compute_ack_tag(k_ack, m_ack, m_ack_len, ack_tag);
    sk_status_t v_status = sk_verify_ack_tag(k_ack, m_ack, m_ack_len, ack_tag);
    if (status == SK_OK && v_status == SK_OK) {
        printf("TEST 6: sk_compute_ack_tag and verify (INSTALLED) ... PASSED\n");
        passed++;
    } else {
        printf("TEST 6: ACK tag compute/verify ... FAILED (c_status=%d, v_status=%d)\n", status, v_status);
        failed++;
    }

    // 7. Negative: Tampered ciphertext must fail GCM unwrap
    uint8_t bad_ct[64];
    memcpy(bad_ct, ciphertext, 64);
    bad_ct[0] ^= 0x01;
    status = sk_unwrap_session_keys(K_GW_WRAP, NONCE, bad_ct, tag, aad, aad_len, unwrapped_up, unwrapped_dl);
    if (status == SK_ERR_GCM_AUTH_FAILED) {
        printf("TEST 7: Negative tampered ciphertext rejected fail-closed ... PASSED\n");
        passed++;
    } else {
        printf("TEST 7: Negative tampered ciphertext ... FAILED (expected %d, got %d)\n", SK_ERR_GCM_AUTH_FAILED, status);
        failed++;
    }

    // 8. Negative: Tampered tag must fail GCM unwrap
    uint8_t bad_tag[16];
    memcpy(bad_tag, tag, 16);
    bad_tag[15] ^= 0x01;
    status = sk_unwrap_session_keys(K_GW_WRAP, NONCE, ciphertext, bad_tag, aad, aad_len, unwrapped_up, unwrapped_dl);
    if (status == SK_ERR_GCM_AUTH_FAILED) {
        printf("TEST 8: Negative tampered tag rejected fail-closed ... PASSED\n");
        passed++;
    } else {
        printf("TEST 8: Negative tampered tag ... FAILED (expected %d, got %d)\n", SK_ERR_GCM_AUTH_FAILED, status);
        failed++;
    }

    // 9. Negative: Tampered AAD must fail GCM unwrap
    uint8_t bad_aad[512];
    memcpy(bad_aad, aad, aad_len);
    bad_aad[aad_len - 1] ^= 0x01;
    status = sk_unwrap_session_keys(K_GW_WRAP, NONCE, ciphertext, tag, bad_aad, aad_len, unwrapped_up, unwrapped_dl);
    if (status == SK_ERR_GCM_AUTH_FAILED) {
        printf("TEST 9: Negative tampered AAD rejected fail-closed ... PASSED\n");
        passed++;
    } else {
        printf("TEST 9: Negative tampered AAD ... FAILED (expected %d, got %d)\n", SK_ERR_GCM_AUTH_FAILED, status);
        failed++;
    }

    // 10. Negative: Tampered ACK tag must fail HMAC verification
    uint8_t bad_ack_tag[16];
    memcpy(bad_ack_tag, ack_tag, 16);
    bad_ack_tag[0] ^= 0x01;
    status = sk_verify_ack_tag(k_ack, m_ack, m_ack_len, bad_ack_tag);
    if (status == SK_ERR_TAG_MISMATCH) {
        printf("TEST 10: Negative tampered ACK tag rejected fail-closed ... PASSED\n");
        passed++;
    } else {
        printf("TEST 10: Negative tampered ACK tag ... FAILED (expected %d, got %d)\n", SK_ERR_TAG_MISMATCH, status);
        failed++;
    }

    printf("\n=== SUMMARY: %d passed, %d failed ===\n", passed, failed);
    return (failed == 0) ? 0 : 1;
}

void app_main(void) {
    int rc = run_all_tests();
    if (rc == 0) {
        printf("=== ESP32 MBEDTLS ALL TESTS PASSED ===\n");
    } else {
        printf("=== ESP32 MBEDTLS TESTS FAILED ===\n");
    }
    fflush(stdout);
    // Restart to trigger QEMU exit with -no-reboot
    esp_restart();
}
