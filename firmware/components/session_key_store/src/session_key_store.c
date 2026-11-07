#include "session_key_store.h"
#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "mbedtls/platform_util.h"

static const char *TAG = "sk_store";

typedef struct {
    sk_session_record_t staging;
    sk_session_record_t active;
    uint64_t high_water_revision;
    bool initialized;
} sk_node_slot_t;

// Static bounded slot allocation (MEM-001: zero dynamic heap allocation)
static sk_node_slot_t s_node_slots[SK_STORE_MAX_NODES];
static nvs_handle_t s_nvs_handle = 0;
static bool s_is_initialized = false;

static inline bool is_valid_node_id(uint8_t node_id) {
    return (node_id >= 1 && node_id <= SK_STORE_MAX_NODES);
}

static inline size_t node_to_index(uint8_t node_id) {
    return (size_t)(node_id - 1);
}

static void make_nvs_key(char *buf, size_t buf_len, const char *prefix, uint8_t node_id) {
    snprintf(buf, buf_len, "%s_%u", prefix, (unsigned int)node_id);
}

esp_err_t session_key_store_init(void) {
    // Clear in-memory state
    session_key_store_clear();

    sk_status_t c_ret = sk_crypto_init();
    if (c_ret != SK_OK) {
        ESP_LOGE(TAG, "PSA crypto init failed: %d", c_ret);
        return ESP_FAIL;
    }

    esp_err_t err = nvs_open(SK_STORE_NVS_NAMESPACE, NVS_READWRITE, &s_nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace %s: %s", SK_STORE_NVS_NAMESPACE, esp_err_to_name(err));
        return err;
    }

    // Restore state from NVS for each node slot
    for (uint8_t node_id = 1; node_id <= SK_STORE_MAX_NODES; node_id++) {
        size_t idx = node_to_index(node_id);
        char key[16];

        // 1. Restore revision high-water mark
        make_nvs_key(key, sizeof(key), "rev", node_id);
        uint64_t rev = 0;
        err = nvs_get_u64(s_nvs_handle, key, &rev);
        if (err == ESP_OK) {
            s_node_slots[idx].high_water_revision = rev;
        } else if (err != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGW(TAG, "NVS error reading %s: %s", key, esp_err_to_name(err));
        }

        // 2. Restore staging slot
        make_nvs_key(key, sizeof(key), "stg", node_id);
        size_t len = sizeof(sk_session_record_t);
        err = nvs_get_blob(s_nvs_handle, key, &s_node_slots[idx].staging, &len);
        if (err == ESP_OK && len == sizeof(sk_session_record_t)) {
            if (s_node_slots[idx].staging.state == SK_RECORD_STATE_INSTALLED_INACTIVE ||
                s_node_slots[idx].staging.state == SK_RECORD_STATE_WAIT_TDMA) {
                ESP_LOGI(TAG, "Restored staging session for node %u (rev %llu)",
                         node_id, (unsigned long long)s_node_slots[idx].staging.session_revision);
            } else {
                mbedtls_platform_zeroize(&s_node_slots[idx].staging, sizeof(sk_session_record_t));
            }
        } else {
            mbedtls_platform_zeroize(&s_node_slots[idx].staging, sizeof(sk_session_record_t));
        }

        // 3. Restore active slot
        make_nvs_key(key, sizeof(key), "act", node_id);
        len = sizeof(sk_session_record_t);
        err = nvs_get_blob(s_nvs_handle, key, &s_node_slots[idx].active, &len);
        if (err == ESP_OK && len == sizeof(sk_session_record_t)) {
            if (s_node_slots[idx].active.state == SK_RECORD_STATE_ACTIVE) {
                ESP_LOGI(TAG, "Restored active session for node %u (rev %llu)",
                         node_id, (unsigned long long)s_node_slots[idx].active.session_revision);
            } else {
                mbedtls_platform_zeroize(&s_node_slots[idx].active, sizeof(sk_session_record_t));
            }
        } else {
            mbedtls_platform_zeroize(&s_node_slots[idx].active, sizeof(sk_session_record_t));
        }

        s_node_slots[idx].initialized = true;
    }

    s_is_initialized = true;
    ESP_LOGI(TAG, "Session key store initialized successfully (15 node slots bounded)");
    return ESP_OK;
}

esp_err_t session_key_store_install(const sk_install_aad_params_t *params,
                                   const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                   const uint8_t ciphertext[SK_PLAINTEXT_SIZE],
                                   const uint8_t tag[SK_TAG_SIZE],
                                   uint64_t now_ms) {
    if (!s_is_initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    if (!params || !k_gw_wrap || !ciphertext || !tag) {
        return ESP_ERR_INVALID_ARG;
    }
    if (!is_valid_node_id(params->node_id)) {
        return ESP_ERR_INVALID_ARG;
    }
    if (params->session_revision == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (params->not_before_ms >= params->expires_at_ms) {
        return ESP_ERR_INVALID_ARG;
    }
    if (params->install_deadline_ms > params->expires_at_ms) {
        return ESP_ERR_INVALID_ARG;
    }
    if (now_ms > 0 && params->install_deadline_ms > 0 && now_ms > params->install_deadline_ms) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t idx = node_to_index(params->node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    // Check for idempotent retry:
    // If install_id and session_id and session_revision match already committed INSTALLED_INACTIVE, return ESP_OK
    if (slot->staging.state == SK_RECORD_STATE_INSTALLED_INACTIVE &&
        slot->staging.session_revision == params->session_revision &&
        memcmp(slot->staging.install_id, params->install_id, SK_UUID_SIZE) == 0 &&
        memcmp(slot->staging.session_id, params->session_id, SK_UUID_SIZE) == 0) {
        ESP_LOGI(TAG, "Idempotent duplicate install detected for node %u, session %llu",
                 params->node_id, (unsigned long long)params->session_revision);
        return ESP_OK;
    }

    // Anti-replay / anti-rollback check (SK-09)
    if (params->session_revision <= slot->high_water_revision) {
        ESP_LOGW(TAG, "Anti-rollback rejection: node %u rev %llu <= committed rev %llu",
                 params->node_id, (unsigned long long)params->session_revision,
                 (unsigned long long)slot->high_water_revision);
        return ESP_ERR_INVALID_VERSION;
    }

    // Step 1: Reconstruct canonical Install AAD V1
    uint8_t aad_buf[512];
    size_t aad_len = 0;
    sk_status_t sk_rc = sk_build_install_aad(params, aad_buf, sizeof(aad_buf), &aad_len);
    if (sk_rc != SK_OK) {
        ESP_LOGE(TAG, "Failed to build Install AAD: %d", sk_rc);
        return ESP_ERR_INVALID_ARG;
    }

    // Step 2: Unwrap session keys (AES-256-GCM) into temporary stack buffers
    uint8_t k_session_up[SK_SESSION_KEY_SIZE];
    uint8_t k_session_dl[SK_SESSION_KEY_SIZE];
    sk_rc = sk_unwrap_session_keys(k_gw_wrap,
                                   params->nonce,
                                   ciphertext,
                                   tag,
                                   aad_buf,
                                   aad_len,
                                   k_session_up,
                                   k_session_dl);
    mbedtls_platform_zeroize(aad_buf, sizeof(aad_buf));

    if (sk_rc != SK_OK) {
        // Tag authentication failure: MUST abort before modifying NVS or slot state!
        mbedtls_platform_zeroize(k_session_up, sizeof(k_session_up));
        mbedtls_platform_zeroize(k_session_dl, sizeof(k_session_dl));
        ESP_LOGW(TAG, "Unwrap auth failed for node %u: %d", params->node_id, sk_rc);
        return ESP_ERR_INVALID_CRC;
    }

    // Step 3: Prepare staging record (INSTALLED_INACTIVE)
    sk_session_record_t staging_rec;
    memset(&staging_rec, 0, sizeof(staging_rec));
    memcpy(staging_rec.session_id, params->session_id, SK_UUID_SIZE);
    memcpy(staging_rec.install_id, params->install_id, SK_UUID_SIZE);
    staging_rec.node_id = params->node_id;
    staging_rec.key_id = params->key_id;
    staging_rec.session_revision = params->session_revision;
    staging_rec.assignment_revision = params->assignment_revision;
    memcpy(staging_rec.k_session_up, k_session_up, SK_SESSION_KEY_SIZE);
    memcpy(staging_rec.k_session_dl, k_session_dl, SK_SESSION_KEY_SIZE);
    staging_rec.not_before_ms = params->not_before_ms;
    staging_rec.expires_at_ms = params->expires_at_ms;
    staging_rec.state = SK_RECORD_STATE_INSTALLED_INACTIVE;

    // Clean up unwrapped keys from temporary stack buffers immediately
    mbedtls_platform_zeroize(k_session_up, sizeof(k_session_up));
    mbedtls_platform_zeroize(k_session_dl, sizeof(k_session_dl));

    // Step 4: Durable NVS commit before ACK (SK-10)
    char rev_key[16];
    char stg_key[16];
    make_nvs_key(rev_key, sizeof(rev_key), "rev", params->node_id);
    make_nvs_key(stg_key, sizeof(stg_key), "stg", params->node_id);

    esp_err_t err = nvs_set_u64(s_nvs_handle, rev_key, params->session_revision);
    if (err != ESP_OK) {
        mbedtls_platform_zeroize(&staging_rec, sizeof(staging_rec));
        ESP_LOGE(TAG, "NVS set rev failed: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_set_blob(s_nvs_handle, stg_key, &staging_rec, sizeof(staging_rec));
    if (err != ESP_OK) {
        mbedtls_platform_zeroize(&staging_rec, sizeof(staging_rec));
        ESP_LOGE(TAG, "NVS set blob failed: %s", esp_err_to_name(err));
        return err;
    }

    err = nvs_commit(s_nvs_handle);
    if (err != ESP_OK) {
        mbedtls_platform_zeroize(&staging_rec, sizeof(staging_rec));
        ESP_LOGE(TAG, "NVS commit failed: %s", esp_err_to_name(err));
        return err;
    }

    // Step 5: Commit to RAM slot only after successful flash commit
    slot->staging = staging_rec;
    slot->high_water_revision = params->session_revision;
    mbedtls_platform_zeroize(&staging_rec, sizeof(staging_rec));

    ESP_LOGI(TAG, "Session key installed durably in INSTALLED_INACTIVE: node %u rev %llu",
             params->node_id, (unsigned long long)params->session_revision);
    return ESP_OK;
}

esp_err_t session_key_store_stage_wait_tdma(uint8_t node_id) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id)) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    if (slot->staging.state != SK_RECORD_STATE_INSTALLED_INACTIVE) {
        return ESP_ERR_INVALID_STATE;
    }

    slot->staging.state = SK_RECORD_STATE_WAIT_TDMA;

    // Update NVS staging record
    char stg_key[16];
    make_nvs_key(stg_key, sizeof(stg_key), "stg", node_id);
    esp_err_t err = nvs_set_blob(s_nvs_handle, stg_key, &slot->staging, sizeof(sk_session_record_t));
    if (err == ESP_OK) {
        nvs_commit(s_nvs_handle);
    }
    return err;
}

esp_err_t session_key_store_promote(uint8_t node_id, uint64_t now_ms) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id)) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    if (slot->staging.state != SK_RECORD_STATE_INSTALLED_INACTIVE &&
        slot->staging.state != SK_RECORD_STATE_WAIT_TDMA) {
        return ESP_ERR_INVALID_STATE;
    }

    // Verify time validity window (SK-04)
    if (now_ms > 0) {
        if (now_ms < slot->staging.not_before_ms || now_ms >= slot->staging.expires_at_ms) {
            ESP_LOGW(TAG, "Promotion guard rejected: now %llu outside [%llu, %llu)",
                     (unsigned long long)now_ms,
                     (unsigned long long)slot->staging.not_before_ms,
                     (unsigned long long)slot->staging.expires_at_ms);
            return ESP_ERR_INVALID_ARG;
        }
    }

    // Prepare new active record
    sk_session_record_t new_active = slot->staging;
    new_active.state = SK_RECORD_STATE_ACTIVE;

    char act_key[16];
    char stg_key[16];
    make_nvs_key(act_key, sizeof(act_key), "act", node_id);
    make_nvs_key(stg_key, sizeof(stg_key), "stg", node_id);

    // Commit new active record to NVS and erase staging
    esp_err_t err = nvs_set_blob(s_nvs_handle, act_key, &new_active, sizeof(new_active));
    if (err != ESP_OK) {
        mbedtls_platform_zeroize(&new_active, sizeof(new_active));
        return err;
    }

    nvs_erase_key(s_nvs_handle, stg_key);
    err = nvs_commit(s_nvs_handle);
    if (err != ESP_OK) {
        mbedtls_platform_zeroize(&new_active, sizeof(new_active));
        return err;
    }

    // Update in-memory slots: zeroize old active and clear staging
    mbedtls_platform_zeroize(&slot->active, sizeof(slot->active));
    slot->active = new_active;
    mbedtls_platform_zeroize(&new_active, sizeof(new_active));

    mbedtls_platform_zeroize(&slot->staging, sizeof(slot->staging));
    slot->staging.state = SK_RECORD_STATE_FREE;

    ESP_LOGI(TAG, "Session promoted to ACTIVE: node %u rev %llu",
             node_id, (unsigned long long)slot->active.session_revision);
    return ESP_OK;
}

esp_err_t session_key_store_revoke(uint8_t node_id) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id)) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    // Zeroize sensitive keys in memory
    mbedtls_platform_zeroize(&slot->active, sizeof(slot->active));
    slot->active.state = SK_RECORD_STATE_REVOKED;

    mbedtls_platform_zeroize(&slot->staging, sizeof(slot->staging));
    slot->staging.state = SK_RECORD_STATE_REVOKED;

    // Erase active and staging from NVS, but KEEP high_water_revision!
    char act_key[16];
    char stg_key[16];
    make_nvs_key(act_key, sizeof(act_key), "act", node_id);
    make_nvs_key(stg_key, sizeof(stg_key), "stg", node_id);

    nvs_erase_key(s_nvs_handle, act_key);
    nvs_erase_key(s_nvs_handle, stg_key);
    esp_err_t err = nvs_commit(s_nvs_handle);

    ESP_LOGI(TAG, "Revoked sessions for node %u (retained high water rev %llu)",
             node_id, (unsigned long long)slot->high_water_revision);
    return err;
}

esp_err_t session_key_store_expire(uint8_t node_id, uint64_t now_ms) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id)) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    if (slot->active.state == SK_RECORD_STATE_ACTIVE && now_ms >= slot->active.expires_at_ms) {
        mbedtls_platform_zeroize(&slot->active, sizeof(slot->active));
        slot->active.state = SK_RECORD_STATE_EXPIRED;

        char act_key[16];
        make_nvs_key(act_key, sizeof(act_key), "act", node_id);
        nvs_erase_key(s_nvs_handle, act_key);
        nvs_commit(s_nvs_handle);

        ESP_LOGI(TAG, "Active session expired for node %u at %llu",
                 node_id, (unsigned long long)now_ms);
    }

    if ((slot->staging.state == SK_RECORD_STATE_INSTALLED_INACTIVE ||
         slot->staging.state == SK_RECORD_STATE_WAIT_TDMA) &&
        now_ms >= slot->staging.expires_at_ms) {
        mbedtls_platform_zeroize(&slot->staging, sizeof(slot->staging));
        slot->staging.state = SK_RECORD_STATE_EXPIRED;

        char stg_key[16];
        make_nvs_key(stg_key, sizeof(stg_key), "stg", node_id);
        nvs_erase_key(s_nvs_handle, stg_key);
        nvs_commit(s_nvs_handle);

        ESP_LOGI(TAG, "Staging session expired for node %u at %llu",
                 node_id, (unsigned long long)now_ms);
    }

    return ESP_OK;
}

esp_err_t session_key_store_get_active(uint8_t node_id, sk_session_record_t *out_record) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id) || !out_record) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    if (slot->active.state != SK_RECORD_STATE_ACTIVE) {
        return ESP_ERR_NOT_FOUND;
    }

    *out_record = slot->active;
    return ESP_OK;
}

esp_err_t session_key_store_get_staging(uint8_t node_id, sk_session_record_t *out_record) {
    if (!s_is_initialized) return ESP_ERR_INVALID_STATE;
    if (!is_valid_node_id(node_id) || !out_record) return ESP_ERR_INVALID_ARG;

    size_t idx = node_to_index(node_id);
    sk_node_slot_t *slot = &s_node_slots[idx];

    if (slot->staging.state != SK_RECORD_STATE_INSTALLED_INACTIVE &&
        slot->staging.state != SK_RECORD_STATE_WAIT_TDMA) {
        return ESP_ERR_NOT_FOUND;
    }

    *out_record = slot->staging;
    return ESP_OK;
}

esp_err_t session_key_store_get_revision(uint8_t node_id, uint64_t *out_rev) {
    if (!is_valid_node_id(node_id) || !out_rev) return ESP_ERR_INVALID_ARG;
    size_t idx = node_to_index(node_id);
    *out_rev = s_node_slots[idx].high_water_revision;
    return ESP_OK;
}

esp_err_t session_key_store_generate_ack(const uint8_t k_gw_wrap[SK_KEY_WRAP_SIZE],
                                        const sk_ack_transcript_params_t *ack_params,
                                        uint8_t *out_m_ack,
                                        size_t max_m_ack_len,
                                        size_t *out_m_ack_len,
                                        uint8_t out_ack_tag[SK_ACK_TAG_SIZE]) {
    if (!k_gw_wrap || !ack_params || !out_m_ack || !out_m_ack_len || !out_ack_tag) {
        return ESP_ERR_INVALID_ARG;
    }

    // Derive K_ACK
    uint8_t k_ack[32];
    sk_status_t sk_rc = sk_derive_k_ack(k_gw_wrap, ack_params->wrap_key_id, ack_params->gateway_id, k_ack);
    if (sk_rc != SK_OK) {
        return ESP_FAIL;
    }

    // Build M_ACK transcript
    sk_rc = sk_build_ack_transcript(ack_params, out_m_ack, max_m_ack_len, out_m_ack_len);
    if (sk_rc != SK_OK) {
        mbedtls_platform_zeroize(k_ack, sizeof(k_ack));
        return ESP_ERR_INVALID_ARG;
    }

    // Compute ACK tag
    sk_rc = sk_compute_ack_tag(k_ack, out_m_ack, *out_m_ack_len, out_ack_tag);
    mbedtls_platform_zeroize(k_ack, sizeof(k_ack));

    return (sk_rc == SK_OK) ? ESP_OK : ESP_FAIL;
}

void session_key_store_clear(void) {
    for (size_t i = 0; i < SK_STORE_MAX_NODES; i++) {
        mbedtls_platform_zeroize(&s_node_slots[i].staging, sizeof(sk_session_record_t));
        mbedtls_platform_zeroize(&s_node_slots[i].active, sizeof(sk_session_record_t));
        s_node_slots[i].staging.state = SK_RECORD_STATE_FREE;
        s_node_slots[i].active.state = SK_RECORD_STATE_FREE;
        s_node_slots[i].high_water_revision = 0;
        s_node_slots[i].initialized = false;
    }
}
