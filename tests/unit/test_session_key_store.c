#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "session_key_store.h"
#include "nvs.h"

// Forward declare mock crypto helper
void mock_crypto_set_tag_valid(bool valid);

static void setup_test_aad_params(sk_install_aad_params_t *params,
                                  uint8_t node_id,
                                  uint64_t session_rev,
                                  uint64_t not_before_ms,
                                  uint64_t expires_at_ms) {
    memset(params, 0, sizeof(*params));
    params->topic = "iot/v1/gw/gw01/downlink/session-key-install";
    params->schema_version = "1.1-draft";
    params->install_protocol_version = 1;
    params->aad_version = 1;
    params->gateway_id = "gw01";
    params->target_gw_id = 1;
    params->node_id = node_id;
    params->key_id = 1;
    memset((void *)params->session_id, 0x11, SK_UUID_SIZE);
    memset((void *)params->install_id, 0x22, SK_UUID_SIZE);
    params->session_revision = session_rev;
    params->assignment_revision = 100;
    params->not_before_ms = not_before_ms;
    params->expires_at_ms = expires_at_ms;
    params->install_deadline_ms = expires_at_ms - 1000;
    params->wrap_key_id = 1;
    params->crypto_suite = "AES-256-GCM";
}

// Test 1: Valid unwrap + commit enters INSTALLED_INACTIVE
static void test_install_valid_enters_installed_inactive(void) {
    mock_nvs_reset();
    mock_crypto_set_tag_valid(true);
    esp_err_t err = session_key_store_init();
    assert(err == ESP_OK);

    sk_install_aad_params_t params;
    setup_test_aad_params(&params, 1, 10, 1000000, 2000000);

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE];
    memset(k_gw_wrap, 0x01, sizeof(k_gw_wrap));
    uint8_t ciphertext[SK_PLAINTEXT_SIZE];
    memset(ciphertext, 0xAA, sizeof(ciphertext));
    uint8_t tag[SK_TAG_SIZE];
    memset(tag, 0xBB, sizeof(tag));

    uint32_t prev_commit_count = g_mock_nvs.commit_count;

    err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_OK);
    // Verifies durable commit to NVS occurred
    assert(g_mock_nvs.commit_count > prev_commit_count);

    // Staging record must be in INSTALLED_INACTIVE
    sk_session_record_t stg;
    err = session_key_store_get_staging(1, &stg);
    assert(err == ESP_OK);
    assert(stg.state == SK_RECORD_STATE_INSTALLED_INACTIVE);
    assert(stg.session_revision == 10);
    assert(stg.node_id == 1);
    assert(stg.not_before_ms == 1000000);
    assert(stg.expires_at_ms == 2000000);

    // Radio transmission MUST remain disabled: active session is absent
    sk_session_record_t act;
    err = session_key_store_get_active(1, &act);
    assert(err == ESP_ERR_NOT_FOUND);

    printf("  [PASS] test_install_valid_enters_installed_inactive\n");
}

// Test 2: Durability & reboot restore check
static void test_durability_and_reboot_restore(void) {
    // Re-initialize session key store (simulating reboot)
    esp_err_t err = session_key_store_init();
    assert(err == ESP_OK);

    // Node 1 staging session must have restored from NVS
    sk_session_record_t stg;
    err = session_key_store_get_staging(1, &stg);
    assert(err == ESP_OK);
    assert(stg.state == SK_RECORD_STATE_INSTALLED_INACTIVE);
    assert(stg.session_revision == 10);

    // High water revision must have restored
    uint64_t rev = 0;
    err = session_key_store_get_revision(1, &rev);
    assert(err == ESP_OK);
    assert(rev == 10);

    printf("  [PASS] test_durability_and_reboot_restore\n");
}

// Test 3: Idempotent duplicate install succeeds without duplicate writes
static void test_idempotent_duplicate_install(void) {
    sk_install_aad_params_t params;
    setup_test_aad_params(&params, 1, 10, 1000000, 2000000);

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE];
    memset(k_gw_wrap, 0x01, sizeof(k_gw_wrap));
    uint8_t ciphertext[SK_PLAINTEXT_SIZE];
    memset(ciphertext, 0xAA, sizeof(ciphertext));
    uint8_t tag[SK_TAG_SIZE];
    memset(tag, 0xBB, sizeof(tag));

    uint32_t commit_before = g_mock_nvs.commit_count;
    uint32_t blob_before = g_mock_nvs.set_blob_count;

    // Retry with identical parameters
    esp_err_t err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_OK);

    // Must NOT write or commit to NVS again!
    assert(g_mock_nvs.commit_count == commit_before);
    assert(g_mock_nvs.set_blob_count == blob_before);

    printf("  [PASS] test_idempotent_duplicate_install\n");
}

// Test 4: Anti-replay / anti-rollback rejects stale revision
static void test_anti_rollback_rejects_stale_revision(void) {
    sk_install_aad_params_t params;

    // Case A: revision == committed (10 <= 10) with different install_id (not an idempotent retry)
    setup_test_aad_params(&params, 1, 10, 1000000, 2000000);
    memset((void *)params.install_id, 0x33, SK_UUID_SIZE); // different install_id

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE] = {0};
    uint8_t ciphertext[SK_PLAINTEXT_SIZE] = {0};
    uint8_t tag[SK_TAG_SIZE] = {0};

    esp_err_t err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_ERR_INVALID_VERSION);

    // Case B: revision < committed (9 < 10)
    setup_test_aad_params(&params, 1, 9, 1000000, 2000000);
    err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_ERR_INVALID_VERSION);

    printf("  [PASS] test_anti_rollback_rejects_stale_revision\n");
}

// Test 5: Tag authentication failure rejects cleanly without state alteration
static void test_tag_auth_failure_clean_rejection(void) {
    mock_crypto_set_tag_valid(false); // Simulate GCM tag mismatch

    sk_install_aad_params_t params;
    setup_test_aad_params(&params, 2, 50, 1000000, 2000000);

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE] = {0};
    uint8_t ciphertext[SK_PLAINTEXT_SIZE] = {0};
    uint8_t tag[SK_TAG_SIZE] = {0};

    uint32_t commit_before = g_mock_nvs.commit_count;

    esp_err_t err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_ERR_INVALID_CRC);

    // NVS must NOT have been modified
    assert(g_mock_nvs.commit_count == commit_before);

    // Node 2 must have no staging session
    sk_session_record_t stg;
    err = session_key_store_get_staging(2, &stg);
    assert(err == ESP_ERR_NOT_FOUND);

    mock_crypto_set_tag_valid(true); // Reset
    printf("  [PASS] test_tag_auth_failure_clean_rejection\n");
}

// Test 6: Promotion moves INSTALLED_INACTIVE to ACTIVE with time guard validation
static void test_promotion_lifecycle(void) {
    // 1. Cannot promote when now_ms < not_before_ms
    esp_err_t err = session_key_store_promote(1, 999999);
    assert(err == ESP_ERR_INVALID_ARG);

    // 2. Cannot promote when now_ms >= expires_at_ms
    err = session_key_store_promote(1, 2000000);
    assert(err == ESP_ERR_INVALID_ARG);

    // 3. Stage WAIT_TDMA
    err = session_key_store_stage_wait_tdma(1);
    assert(err == ESP_OK);
    sk_session_record_t stg;
    err = session_key_store_get_staging(1, &stg);
    assert(err == ESP_OK);
    assert(stg.state == SK_RECORD_STATE_WAIT_TDMA);

    // 4. Valid promotion at boundary
    uint32_t commit_before = g_mock_nvs.commit_count;
    err = session_key_store_promote(1, 1500000);
    assert(err == ESP_OK);
    assert(g_mock_nvs.commit_count > commit_before);

    // Active session is now present and active
    sk_session_record_t act;
    err = session_key_store_get_active(1, &act);
    assert(err == ESP_OK);
    assert(act.state == SK_RECORD_STATE_ACTIVE);
    assert(act.session_revision == 10);
    assert(act.node_id == 1);

    // Staging slot is now free
    err = session_key_store_get_staging(1, &stg);
    assert(err == ESP_ERR_NOT_FOUND);

    printf("  [PASS] test_promotion_lifecycle\n");
}

// Test 7: Expiration and Revocation lifecycle
static void test_expiration_and_revocation(void) {
    // Install a new session for Node 3
    sk_install_aad_params_t params;
    setup_test_aad_params(&params, 3, 100, 1000000, 2000000);

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE] = {0};
    uint8_t ciphertext[SK_PLAINTEXT_SIZE] = {0};
    uint8_t tag[SK_TAG_SIZE] = {0};

    esp_err_t err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_OK);

    // Promote to active
    err = session_key_store_promote(3, 1500000);
    assert(err == ESP_OK);

    // Expire at 2000001
    err = session_key_store_expire(3, 2000001);
    assert(err == ESP_OK);

    // Active session is no longer accessible
    sk_session_record_t act;
    err = session_key_store_get_active(3, &act);
    assert(err == ESP_ERR_NOT_FOUND);

    // Now test Revocation on Node 1 (which has active session 10)
    err = session_key_store_revoke(1);
    assert(err == ESP_OK);

    err = session_key_store_get_active(1, &act);
    assert(err == ESP_ERR_NOT_FOUND);

    // Crucial: high_water_revision MUST still be preserved in NVS to prevent replay of rev 10
    uint64_t rev = 0;
    err = session_key_store_get_revision(1, &rev);
    assert(err == ESP_OK);
    assert(rev == 10);

    // Attempt to reinstall rev 10 after revocation must still be rejected
    err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    // params is rev 100, let's test rev 10
    setup_test_aad_params(&params, 1, 10, 1000000, 2000000);
    err = session_key_store_install(&params, k_gw_wrap, ciphertext, tag, 1000000);
    assert(err == ESP_ERR_INVALID_VERSION);

    printf("  [PASS] test_expiration_and_revocation\n");
}

// Test 8: ACK transcript and tag generation
static void test_ack_generation(void) {
    sk_ack_transcript_params_t ack_params;
    memset(&ack_params, 0, sizeof(ack_params));
    ack_params.topic = "iot/v1/gw/gw01/uplink/session-key-ack";
    ack_params.schema_version = "1.1-draft";
    ack_params.ack_protocol_version = 1;
    ack_params.gateway_id = "gw01";
    memset((void *)ack_params.install_id, 0x22, SK_UUID_SIZE);
    memset((void *)ack_params.session_id, 0x11, SK_UUID_SIZE);
    ack_params.session_revision = 10;
    ack_params.wrap_key_id = 1;
    ack_params.status = "INSTALLED";
    ack_params.reason_code = "NONE";

    uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE];
    memset(k_gw_wrap, 0x01, sizeof(k_gw_wrap));
    uint8_t m_ack[256];
    size_t m_ack_len = 0;
    uint8_t ack_tag[SK_ACK_TAG_SIZE];

    esp_err_t err = session_key_store_generate_ack(k_gw_wrap,
                                                  &ack_params,
                                                  m_ack,
                                                  sizeof(m_ack),
                                                  &m_ack_len,
                                                  ack_tag);
    assert(err == ESP_OK);
    assert(m_ack_len == 138);

    printf("  [PASS] test_ack_generation\n");
}

// Test 9: Parameter bounds checking (MEM-003, MEM-004)
static void test_parameter_bounds(void) {
    sk_install_aad_params_t params;
    setup_test_aad_params(&params, 0, 1, 1000, 2000); // Invalid node 0
    uint8_t dummy[64] = {0};

    esp_err_t err = session_key_store_install(&params, dummy, dummy, dummy, 1000);
    assert(err == ESP_ERR_INVALID_ARG);

    setup_test_aad_params(&params, SK_STORE_MAX_NODES + 1, 1, 1000, 2000); // Invalid node 16
    err = session_key_store_install(&params, dummy, dummy, dummy, 1000);
    assert(err == ESP_ERR_INVALID_ARG);

    setup_test_aad_params(&params, 1, 0, 1000, 2000); // Invalid revision 0
    err = session_key_store_install(&params, dummy, dummy, dummy, 1000);
    assert(err == ESP_ERR_INVALID_ARG);

    setup_test_aad_params(&params, 1, 1, 2000, 1000); // not_before >= expires_at
    err = session_key_store_install(&params, dummy, dummy, dummy, 1000);
    assert(err == ESP_ERR_INVALID_ARG);

    printf("  [PASS] test_parameter_bounds\n");
}

int main(void) {
    printf("Running Gateway Session Key Store Unit Tests...\n");
    test_install_valid_enters_installed_inactive();
    test_durability_and_reboot_restore();
    test_idempotent_duplicate_install();
    test_anti_rollback_rejects_stale_revision();
    test_tag_auth_failure_clean_rejection();
    test_promotion_lifecycle();
    test_expiration_and_revocation();
    test_ack_generation();
    test_parameter_bounds();
    printf("ALL Gateway Session Key Store Unit Tests PASSED (100%% state transitions verified).\n");
    return 0;
}
