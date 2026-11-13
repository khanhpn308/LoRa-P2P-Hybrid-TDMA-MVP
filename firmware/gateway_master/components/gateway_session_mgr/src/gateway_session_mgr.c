#include "gateway_session_mgr.h"

#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "session_key_store.h"

static const char *TAG = "gateway_master";

const uint8_t DEFAULT_NONCE_PREFIX[8] = {
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57
};

static gateway_v2_join_engine_t *s_join_engine_ptr = NULL;
static approved_node_entry_t s_approved_nodes[MAX_APPROVED_NODES];
static size_t s_approved_count = 0;
static gateway_revoked_node_info_t s_revoked_nodes[MAX_REVOKED_NODES];

esp_err_t gateway_session_mgr_init(gateway_v2_join_engine_t *join_engine)
{
    s_join_engine_ptr = join_engine;
    return ESP_OK;
}

approved_node_entry_t *find_or_create_node_entry(const uint8_t mac[6])
{
    approved_node_entry_t *reusable_entry = NULL;
    static const uint8_t s_zero_mac[6] = {0};

    for (size_t i = 0; i < s_approved_count; i++) {
        if (memcmp(s_approved_nodes[i].mac, mac, 6) == 0) {
            return &s_approved_nodes[i];
        }
        if (reusable_entry == NULL && memcmp(s_approved_nodes[i].mac, s_zero_mac, 6) == 0 && s_approved_nodes[i].node_id == 0) {
            reusable_entry = &s_approved_nodes[i];
        }
    }
    if (reusable_entry != NULL) {
        memset(reusable_entry, 0, sizeof(*reusable_entry));
        memcpy(reusable_entry->mac, mac, 6);
        return reusable_entry;
    }
    if (s_approved_count < MAX_APPROVED_NODES) {
        approved_node_entry_t *entry = &s_approved_nodes[s_approved_count++];
        memset(entry, 0, sizeof(*entry));
        memcpy(entry->mac, mac, 6);
        return entry;
    }
    return NULL;
}

esp_err_t gateway_save_node_session(uint8_t node_id)
{
    if (node_id < 1 || node_id > GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS || s_join_engine_ptr == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    size_t slot_idx = (size_t)(node_id - 1);
    gateway_v2_pending_join_t *pending = &s_join_engine_ptr->pending_joins[slot_idx];
    if (!pending->active) {
        return ESP_ERR_INVALID_STATE;
    }

    gw_persisted_session_t sess;
    memset(&sess, 0, sizeof(sess));
    sess.active = 1;
    sess.node_id = node_id;
    memcpy(sess.device_mac, pending->device_mac, 6);
    sess.join_counter = pending->join_counter;
    memcpy(sess.k_session_up, pending->session_keys.k_session_up, 16);
    memcpy(sess.k_session_dl, pending->session_keys.k_session_dl, 16);

    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open(GW_SESSION_NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace %s: %s", GW_SESSION_NVS_NAMESPACE, esp_err_to_name(err));
        return err;
    }

    char key[16];
    snprintf(key, sizeof(key), "node_%u", (unsigned int)node_id);
    err = nvs_set_blob(handle, key, &sess, sizeof(sess));
    if (err == ESP_OK) {
        err = nvs_commit(handle);
    }
    nvs_close(handle);

    if (err == ESP_OK) {
        ESP_LOGI(TAG, "[NVS SAVE] Persisted session keys for Node #%u to NVS flash", node_id);
    } else {
        ESP_LOGE(TAG, "[NVS SAVE] Failed to persist session keys for Node #%u: %s", node_id, esp_err_to_name(err));
    }
    return err;
}

void gateway_restore_sessions_from_nvs(void)
{
    if (s_join_engine_ptr == NULL) {
        return;
    }

    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open(GW_SESSION_NVS_NAMESPACE, NVS_READONLY, &handle);
    if (err != ESP_OK) {
        ESP_LOGI(TAG, "No persistent sessions in NVS namespace %s (%s)",
                 GW_SESSION_NVS_NAMESPACE, esp_err_to_name(err));
        return;
    }

    size_t restored_count = 0;
    for (uint8_t node_id = 1; node_id <= GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS; node_id++) {
        char key[16];
        snprintf(key, sizeof(key), "node_%u", (unsigned int)node_id);
        gw_persisted_session_t sess;
        size_t len = sizeof(sess);
        err = nvs_get_blob(handle, key, &sess, &len);
        if (err == ESP_OK && len == sizeof(sess) && sess.active == 1 && sess.node_id == node_id) {
            size_t slot_idx = (size_t)(node_id - 1);
            gateway_v2_pending_join_t *pending = &s_join_engine_ptr->pending_joins[slot_idx];
            memset(pending, 0, sizeof(*pending));
            pending->active = true;
            pending->assigned_node_id = sess.node_id;
            memcpy(pending->device_mac, sess.device_mac, 6);
            pending->join_counter = sess.join_counter;
            memcpy(pending->session_keys.k_session_up, sess.k_session_up, 16);
            memcpy(pending->session_keys.k_session_dl, sess.k_session_dl, 16);

            /* Also restore into approved nodes table without auto-approving (stateless bridge) */
            approved_node_entry_t *entry = find_or_create_node_entry(sess.device_mac);
            if (entry != NULL) {
                entry->node_id = sess.node_id;
                entry->approved = false;
                entry->has_cached_hello = false;
            }

            /* Mark node as known and not revoked */
            s_revoked_nodes[node_id].revoked = false;
            s_revoked_nodes[node_id].has_key = false;

            ESP_LOGI(TAG, "[NVS RESTORE] Restored persistent session for Node #%u (MAC %02X:%02X:%02X:%02X:%02X:%02X, Ctr: %u)",
                     node_id,
                     sess.device_mac[0], sess.device_mac[1], sess.device_mac[2],
                     sess.device_mac[3], sess.device_mac[4], sess.device_mac[5],
                     (unsigned int)sess.join_counter);
            restored_count++;
        }
    }
    nvs_close(handle);
    ESP_LOGI(TAG, "Gateway session restore completed: %zu active node sessions restored from NVS flash", restored_count);
}

esp_err_t gateway_erase_node_session(uint8_t node_id)
{
    nvs_handle_t handle = 0;
    esp_err_t err = nvs_open(GW_SESSION_NVS_NAMESPACE, NVS_READWRITE, &handle);
    if (err != ESP_OK) {
        return err;
    }
    char key[16];
    snprintf(key, sizeof(key), "node_%u", (unsigned int)node_id);
    (void)nvs_erase_key(handle, key);
    err = nvs_commit(handle);
    nvs_close(handle);
    ESP_LOGI(TAG, "[NVS ERASE] Erased session for Node #%u from NVS flash", node_id);
    return err;
}

gateway_revoked_node_info_t *gateway_session_mgr_get_revoked_info(uint8_t node_id)
{
    return &s_revoked_nodes[node_id];
}

bool gateway_session_mgr_is_node_revoked(uint8_t node_id)
{
    return s_revoked_nodes[node_id].revoked;
}

void gateway_session_mgr_clear_revocation(uint8_t node_id)
{
    s_revoked_nodes[node_id].revoked = false;
    s_revoked_nodes[node_id].has_key = false;
}

void gateway_session_mgr_revoke_node(uint8_t node_id)
{
    /* Lookup active session keys before revoking so we can authenticate DOWN_REVOKE */
    uint8_t k_session_up[16];
    uint8_t k_session_dl[16];
    uint8_t nonce_prefix[8];
    memcpy(nonce_prefix, DEFAULT_NONCE_PREFIX, sizeof(nonce_prefix));
    esp_err_t key_err = hal_session_key_lookup(node_id, NULL, k_session_up, k_session_dl, nonce_prefix);
    if (key_err != ESP_OK && s_join_engine_ptr != NULL) {
        size_t slot_idx = (size_t)(node_id - 1);
        if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS && s_join_engine_ptr->pending_joins[slot_idx].active) {
            memcpy(k_session_up, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_up, 16);
            memcpy(k_session_dl, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_dl, 16);
            key_err = ESP_OK;
        }
    }

    s_revoked_nodes[node_id].revoked = true;
    if (key_err == ESP_OK) {
        memcpy(s_revoked_nodes[node_id].k_session_dl, k_session_dl, 16);
        memcpy(s_revoked_nodes[node_id].nonce_prefix, nonce_prefix, 8);
        s_revoked_nodes[node_id].has_key = true;
    } else {
        s_revoked_nodes[node_id].has_key = false;
    }

    /* Release session keys in Session Key Store and pending joins */
    (void)session_key_store_revoke(node_id);
    (void)gateway_erase_node_session(node_id);
    if (s_join_engine_ptr != NULL) {
        size_t slot_idx = (size_t)(node_id - 1);
        if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
            memset(&s_join_engine_ptr->pending_joins[slot_idx], 0, sizeof(s_join_engine_ptr->pending_joins[slot_idx]));
        }
    }

    /* Clean up s_approved_nodes cache for this node_id */
    for (size_t i = 0; i < s_approved_count; i++) {
        if (s_approved_nodes[i].node_id == node_id) {
            memset(&s_approved_nodes[i], 0, sizeof(s_approved_nodes[i]));
            ESP_LOGI(TAG, "[REVOKE] Cleared s_approved_nodes cache for Node #%u", (unsigned int)node_id);
        }
    }

    ESP_LOGI(TAG, "[REVOKE] Node #%u added to revocation list (has_key=%d). Session keys evicted.",
             node_id, s_revoked_nodes[node_id].has_key ? 1 : 0);
}

esp_err_t hal_session_key_lookup(uint8_t node_id,
                                 uint8_t *out_session_sel,
                                 uint8_t out_k_session_up[16],
                                 uint8_t out_k_session_dl[16],
                                 uint8_t out_nonce_prefix[8])
{
    sk_session_record_t rec;
    esp_err_t err = session_key_store_get_active(node_id, &rec);
    if (err != ESP_OK) {
        err = session_key_store_get_staging(node_id, &rec);
    }
    if (err == ESP_OK) {
        if (out_session_sel != NULL) {
            *out_session_sel = rec.key_id & 1U;
        }
        if (out_k_session_up != NULL) {
            (void)memcpy(out_k_session_up, rec.k_session_up, 16);
        }
        if (out_k_session_dl != NULL) {
            (void)memcpy(out_k_session_dl, rec.k_session_dl, 16);
        }
        if (out_nonce_prefix != NULL) {
            static const uint8_t s_all_zeros[8] = {0};
            if (memcmp(rec.session_id, s_all_zeros, 8) == 0) {
                (void)memcpy(out_nonce_prefix, DEFAULT_NONCE_PREFIX, 8);
            } else {
                (void)memcpy(out_nonce_prefix, rec.session_id, 8);
            }
        }
        return ESP_OK;
    }

    /* Fallback directly to V2 Join pending_joins in s_join_engine */
    if (s_join_engine_ptr != NULL && node_id >= 1 && node_id <= GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        size_t slot_idx = (size_t)(node_id - 1);
        if (s_join_engine_ptr->pending_joins[slot_idx].active) {
            if (out_session_sel != NULL) {
                *out_session_sel = 0;
            }
            if (out_k_session_up != NULL) {
                memcpy(out_k_session_up, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_up, 16);
            }
            if (out_k_session_dl != NULL) {
                memcpy(out_k_session_dl, s_join_engine_ptr->pending_joins[slot_idx].session_keys.k_session_dl, 16);
            }
            if (out_nonce_prefix != NULL) {
                memcpy(out_nonce_prefix, DEFAULT_NONCE_PREFIX, 8);
            }
            return ESP_OK;
        }
    }

    return ESP_ERR_NOT_FOUND;
}
