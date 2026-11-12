#include <inttypes.h>
#include <string.h>
#include <stdlib.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "sx1276_driver.h"
#include "session_key_store.h"
#include "gateway_transport.h"
#include "gateway_v2_join.h"
#include "gateway_wal.h"
#include "sdkconfig.h"
#include "airtime_policy.h"

static const char *TAG = "gateway_master";
static char s_gateway_id[32] = "gw-a";
static const uint8_t DEFAULT_NONCE_PREFIX[8] = {
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57
};
static gateway_v2_join_engine_t s_join_engine;

typedef struct {
    uint8_t mac[6];
    uint8_t node_id;
    bool approved;
    bool has_cached_hello;
    uint8_t cached_hello[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    int16_t cached_rssi;
    int8_t cached_snr;
} approved_node_entry_t;

#define MAX_APPROVED_NODES 32
static approved_node_entry_t s_approved_nodes[MAX_APPROVED_NODES];
static size_t s_approved_count = 0;

static approved_node_entry_t *find_or_create_node_entry(const uint8_t mac[6])
{
    for (size_t i = 0; i < s_approved_count; i++) {
        if (memcmp(s_approved_nodes[i].mac, mac, 6) == 0) {
            return &s_approved_nodes[i];
        }
    }
    if (s_approved_count < MAX_APPROVED_NODES) {
        approved_node_entry_t *entry = &s_approved_nodes[s_approved_count++];
        memset(entry, 0, sizeof(*entry));
        memcpy(entry->mac, mac, 6);
        return entry;
    }
    return NULL;
}

static esp_err_t gateway_save_node_session(uint8_t node_id);
static void gateway_restore_sessions_from_nvs(void);
static esp_err_t gateway_erase_node_session(uint8_t node_id);

static void on_downlink_session_key(const uint8_t *data, size_t len)
{
    ESP_LOGI(TAG, "Downlink session-key-install received (%zu bytes)", len);
}

static void on_downlink_schedule(const uint8_t *data, size_t len)
{
    ESP_LOGI(TAG, "Downlink schedule received (%zu bytes)", len);
}

static void on_downlink_join_grant(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) return;
    char buf[256];
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, data, len);
    buf[len] = '\0';
    ESP_LOGI(TAG, "[DOWNLINK JOIN_GRANT] Received from Backend: %s", buf);

    /* Parse device_mac */
    const char *mac_ptr = strstr(buf, "\"device_mac\":\"");
    if (!mac_ptr) return;
    mac_ptr += 14;
    uint8_t mac[6];
    for (int i = 0; i < 6; i++) {
        unsigned int byte_val = 0;
        if (sscanf(mac_ptr + (i * 2), "%02x", &byte_val) != 1) {
            return;
        }
        mac[i] = (uint8_t)byte_val;
    }

    /* Parse node_id */
    const char *id_ptr = strstr(buf, "\"node_id\":");
    if (!id_ptr) return;
    id_ptr += 10;
    int assigned_id = atoi(id_ptr);
    if (assigned_id <= 0 || assigned_id > 254) return;

    approved_node_entry_t *entry = find_or_create_node_entry(mac);
    if (entry) {
        entry->node_id = (uint8_t)assigned_id;
        entry->approved = true;
        ESP_LOGI(TAG, "[APPROVED] Node %02X:%02X:%02X:%02X:%02X:%02X approved by User! Assigned Node ID #%u",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], entry->node_id);

        /* If we have a cached hello frame waiting, send grant now! */
        if (entry->has_cached_hello) {
            uint8_t grant_buf[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
            size_t grant_len = 0;
            uint64_t now_us = (uint64_t)esp_timer_get_time();
            float snr_f = (float)entry->cached_snr / 4.0f;

            esp_err_t h_err = gateway_v2_join_handle_hello_with_id(
                &s_join_engine,
                entry->cached_hello,
                LORA_MAC_V2_LEN_UP_JOIN_HELLO,
                entry->cached_rssi,
                snr_f,
                now_us,
                NULL,
                entry->node_id,
                grant_buf,
                &grant_len
            );
            if (h_err == ESP_OK) {
                (void)gateway_save_node_session(entry->node_id);
                vTaskDelay(pdMS_TO_TICKS(40));
                ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_GRANT (%zu bytes) to Node #%u...", grant_len, entry->node_id);
                esp_err_t tx_err = sx1276_tx(grant_buf, (uint8_t)grant_len, pdMS_TO_TICKS(300));
                if (tx_err == ESP_OK) {
                    ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_GRANT transmitted successfully for Node #%u", entry->node_id);
                } else {
                    ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_GRANT: %s", esp_err_to_name(tx_err));
                }
            }
            entry->has_cached_hello = false;
        }

        /* Re-enable 24/7 continuous RX on Gateway to receive retries or subsequent frames */
        (void)sx1276_start_rx_continuous();
    }
}

static void on_downlink_join_wait(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) return;
    char buf[256];
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, data, len);
    buf[len] = '\0';
    ESP_LOGI(TAG, "[DOWNLINK JOIN_WAIT] Received from Backend: %s", buf);

    /* Parse device_mac */
    const char *mac_ptr = strstr(buf, "\"device_mac\":\"");
    if (!mac_ptr) return;
    mac_ptr += 14;
    uint8_t mac[6];
    for (int i = 0; i < 6; i++) {
        unsigned int byte_val = 0;
        if (sscanf(mac_ptr + (i * 2), "%02x", &byte_val) != 1) {
            return;
        }
        mac[i] = (uint8_t)byte_val;
    }

    /* Optional auth_tag parsing */
    uint8_t auth_tag[8];
    bool has_auth_tag = false;
    const char *tag_ptr = strstr(buf, "\"auth_tag\":\"");
    if (tag_ptr) {
        tag_ptr += 12;
        int parsed = 0;
        for (int i = 0; i < 8; i++) {
            unsigned int byte_val = 0;
            if (sscanf(tag_ptr + (i * 2), "%02x", &byte_val) == 1) {
                auth_tag[i] = (uint8_t)byte_val;
                parsed++;
            }
        }
        if (parsed == 8) {
            has_auth_tag = true;
        }
    }

    approved_node_entry_t *entry = find_or_create_node_entry(mac);
    if (entry && entry->has_cached_hello) {
        uint8_t wait_buf[LORA_MAC_V2_LEN_DOWN_JOIN_WAIT];
        size_t wait_len = 0;

        esp_err_t b_err = gateway_v2_join_build_wait(
            &s_join_engine,
            entry->cached_hello,
            LORA_MAC_V2_LEN_UP_JOIN_HELLO,
            has_auth_tag ? auth_tag : NULL,
            wait_buf,
            &wait_len
        );
        if (b_err == ESP_OK) {
            /* Allow Node time to switch from TX to RX (RF turnaround margin) */
            vTaskDelay(pdMS_TO_TICKS(40));
            ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_WAIT (%zu bytes) to MAC %02X:%02X:%02X:%02X:%02X:%02X...",
                     wait_len, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            esp_err_t tx_err = sx1276_tx(wait_buf, (uint8_t)wait_len, pdMS_TO_TICKS(300));
            if (tx_err == ESP_OK) {
                ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_WAIT transmitted successfully for MAC %02X:%02X:%02X:%02X:%02X:%02X",
                         mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            } else {
                ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_WAIT: %s", esp_err_to_name(tx_err));
            }
        } else {
            ESP_LOGE(TAG, "[JOIN TX] Failed to build DOWN_JOIN_WAIT: %s", esp_err_to_name(b_err));
        }
    } else {
        ESP_LOGW(TAG, "[JOIN TX] No cached UP_JOIN_HELLO for MAC %02X:%02X:%02X:%02X:%02X:%02X, cannot send DOWN_JOIN_WAIT",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }

    /* Re-enable 24/7 continuous RX on Gateway immediately (stateless radio bridge) */
    (void)sx1276_start_rx_continuous();
}

static void on_downlink_join_reject(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) return;
    char buf[256];
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, data, len);
    buf[len] = '\0';
    ESP_LOGI(TAG, "[DOWNLINK JOIN_REJECT] Received from Backend: %s", buf);

    /* Parse device_mac */
    const char *mac_ptr = strstr(buf, "\"device_mac\":\"");
    if (!mac_ptr) return;
    mac_ptr += 14;
    uint8_t mac[6];
    for (int i = 0; i < 6; i++) {
        unsigned int byte_val = 0;
        if (sscanf(mac_ptr + (i * 2), "%02x", &byte_val) != 1) {
            return;
        }
        mac[i] = (uint8_t)byte_val;
    }

    /* Optional auth_tag parsing */
    uint8_t auth_tag[8];
    bool has_auth_tag = false;
    const char *tag_ptr = strstr(buf, "\"auth_tag\":\"");
    if (tag_ptr) {
        tag_ptr += 12;
        int parsed = 0;
        for (int i = 0; i < 8; i++) {
            unsigned int byte_val = 0;
            if (sscanf(tag_ptr + (i * 2), "%02x", &byte_val) == 1) {
                auth_tag[i] = (uint8_t)byte_val;
                parsed++;
            }
        }
        if (parsed == 8) {
            has_auth_tag = true;
        }
    }

    approved_node_entry_t *entry = find_or_create_node_entry(mac);
    if (entry && entry->has_cached_hello) {
        uint8_t reject_buf[LORA_MAC_V2_LEN_DOWN_JOIN_REJECT];
        size_t reject_len = 0;

        esp_err_t b_err = gateway_v2_join_build_reject(
            &s_join_engine,
            entry->cached_hello,
            LORA_MAC_V2_LEN_UP_JOIN_HELLO,
            has_auth_tag ? auth_tag : NULL,
            reject_buf,
            &reject_len
        );
        if (b_err == ESP_OK) {
            /* Allow Node time to switch from TX to RX (RF turnaround margin) */
            vTaskDelay(pdMS_TO_TICKS(40));
            ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_REJECT (%zu bytes) to MAC %02X:%02X:%02X:%02X:%02X:%02X...",
                     reject_len, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            esp_err_t tx_err = sx1276_tx(reject_buf, (uint8_t)reject_len, pdMS_TO_TICKS(300));
            if (tx_err == ESP_OK) {
                ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_REJECT transmitted successfully for MAC %02X:%02X:%02X:%02X:%02X:%02X",
                         mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
            } else {
                ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_REJECT: %s", esp_err_to_name(tx_err));
            }
        } else {
            ESP_LOGE(TAG, "[JOIN TX] Failed to build DOWN_JOIN_REJECT: %s", esp_err_to_name(b_err));
        }
        /* Clear cached hello and approval on reject */
        entry->has_cached_hello = false;
        entry->approved = false;
    } else {
        ESP_LOGW(TAG, "[JOIN TX] No cached UP_JOIN_HELLO for MAC %02X:%02X:%02X:%02X:%02X:%02X, cannot send DOWN_JOIN_REJECT",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }

    /* Re-enable 24/7 continuous RX on Gateway immediately (stateless radio bridge) */
    (void)sx1276_start_rx_continuous();
}

static gateway_wal_t s_gateway_wal;
static uint32_t s_downlink_frame_counter = 0;
static TaskHandle_t s_gateway_rx_task_handle = NULL;
static esp_timer_handle_t s_gw_heartbeat_timer = NULL;
static esp_timer_handle_t s_nodes_liveness_timer = NULL;

#define MAX_LORA_TRACKED_NODES (32)
static bool s_node_alive[MAX_LORA_TRACKED_NODES + 1] = {false};
static uint32_t s_node_last_seen_s[MAX_LORA_TRACKED_NODES + 1] = {0};
static uint32_t s_rx_events_total = 0;

#define MAX_REVOKED_NODES (256)
typedef struct {
    bool revoked;
    uint8_t k_session_dl[16];
    uint8_t nonce_prefix[8];
    bool has_key;
} gateway_revoked_node_info_t;

static gateway_revoked_node_info_t s_revoked_nodes[MAX_REVOKED_NODES];

#define GATEWAY_TASK_STACK_SIZE_BYTES (16384U)
static StackType_t s_gateway_task_stack[GATEWAY_TASK_STACK_SIZE_BYTES];
static StaticTask_t s_gateway_task_tcb;

#define GW_SESSION_NVS_NAMESPACE "gw_session"

typedef struct {
    uint8_t  active;
    uint8_t  node_id;
    uint8_t  device_mac[6];
    uint32_t join_counter;
    uint8_t  k_session_up[16];
    uint8_t  k_session_dl[16];
} gw_persisted_session_t;

static esp_err_t gateway_save_node_session(uint8_t node_id)
{
    if (node_id < 1 || node_id > GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        return ESP_ERR_INVALID_ARG;
    }
    size_t slot_idx = (size_t)(node_id - 1);
    gateway_v2_pending_join_t *pending = &s_join_engine.pending_joins[slot_idx];
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

static void gateway_restore_sessions_from_nvs(void)
{
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
            gateway_v2_pending_join_t *pending = &s_join_engine.pending_joins[slot_idx];
            memset(pending, 0, sizeof(*pending));
            pending->active = true;
            pending->assigned_node_id = sess.node_id;
            memcpy(pending->device_mac, sess.device_mac, 6);
            pending->join_counter = sess.join_counter;
            memcpy(pending->session_keys.k_session_up, sess.k_session_up, 16);
            memcpy(pending->session_keys.k_session_dl, sess.k_session_dl, 16);

            /* Also restore into approved nodes table */
            approved_node_entry_t *entry = find_or_create_node_entry(sess.device_mac);
            if (entry != NULL) {
                entry->node_id = sess.node_id;
                entry->approved = true;
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

static esp_err_t gateway_erase_node_session(uint8_t node_id)
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

static esp_err_t hal_session_key_lookup(uint8_t node_id,
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
    if (node_id >= 1 && node_id <= GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        size_t slot_idx = (size_t)(node_id - 1);
        if (s_join_engine.pending_joins[slot_idx].active) {
            if (out_session_sel != NULL) {
                *out_session_sel = 0;
            }
            if (out_k_session_up != NULL) {
                memcpy(out_k_session_up, s_join_engine.pending_joins[slot_idx].session_keys.k_session_up, 16);
            }
            if (out_k_session_dl != NULL) {
                memcpy(out_k_session_dl, s_join_engine.pending_joins[slot_idx].session_keys.k_session_dl, 16);
            }
            if (out_nonce_prefix != NULL) {
                memcpy(out_nonce_prefix, DEFAULT_NONCE_PREFIX, 8);
            }
            return ESP_OK;
        }
    }

    return ESP_ERR_NOT_FOUND;
}

static void on_downlink_node_revoke(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0) return;
    char buf[256];
    if (len >= sizeof(buf)) len = sizeof(buf) - 1;
    memcpy(buf, data, len);
    buf[len] = '\0';
    ESP_LOGI(TAG, "[DOWNLINK NODE_REVOKE] Received from Backend: %s", buf);

    /* Parse node_id from {"node_id": X} */
    const char *id_ptr = strstr(buf, "\"node_id\":");
    if (!id_ptr) return;
    id_ptr += 10;
    while (*id_ptr == ' ' || *id_ptr == '\t') id_ptr++;
    int node_id_val = atoi(id_ptr);
    if (node_id_val <= 0 || node_id_val >= MAX_REVOKED_NODES) {
        ESP_LOGW(TAG, "[DOWNLINK NODE_REVOKE] Invalid node_id: %d", node_id_val);
        return;
    }
    uint8_t node_id = (uint8_t)node_id_val;

    /* Lookup active session keys before revoking so we can authenticate DOWN_REVOKE */
    uint8_t k_session_up[16];
    uint8_t k_session_dl[16];
    uint8_t nonce_prefix[8];
    memcpy(nonce_prefix, DEFAULT_NONCE_PREFIX, sizeof(nonce_prefix));
    esp_err_t key_err = hal_session_key_lookup(node_id, NULL, k_session_up, k_session_dl, nonce_prefix);
    if (key_err != ESP_OK) {
        size_t slot_idx = (size_t)(node_id - 1);
        if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS && s_join_engine.pending_joins[slot_idx].active) {
            memcpy(k_session_up, s_join_engine.pending_joins[slot_idx].session_keys.k_session_up, 16);
            memcpy(k_session_dl, s_join_engine.pending_joins[slot_idx].session_keys.k_session_dl, 16);
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
    size_t slot_idx = (size_t)(node_id - 1);
    if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        memset(&s_join_engine.pending_joins[slot_idx], 0, sizeof(s_join_engine.pending_joins[slot_idx]));
    }
    ESP_LOGI(TAG, "[REVOKE] Node #%u added to revocation list (has_key=%d). Session keys evicted.",
             node_id, s_revoked_nodes[node_id].has_key ? 1 : 0);
}

static void gateway_heartbeat_timer_cb(void *arg)
{
    (void)arg;
    if (!gateway_transport_is_connected()) {
        return;
    }

    gateway_heartbeat_pkt_t hb = {
        .type = HEARTBEAT_TYPE_GATEWAY,
        .flags = 0x01 | 0x02, /* bit 0: lora_ok, bit 1: is_active */
        .wifi_rssi = gateway_transport_get_wifi_rssi(),
        .reserved = 0x00,
        .uptime_s = (uint32_t)(esp_timer_get_time() / 1000000ULL),
        .free_heap_bytes = (uint32_t)esp_get_free_heap_size(),
        .rx_events_count = s_rx_events_total,
    };
    (void)gateway_transport_publish_heartbeat((const uint8_t *)&hb, sizeof(hb));
    ESP_LOGD(TAG, "[HEARTBEAT] Published Gateway Heartbeat (uptime=%" PRIu32 "s, heap=%" PRIu32 "B, rssi=%d)",
             hb.uptime_s, hb.free_heap_bytes, hb.wifi_rssi);
}

static void on_transport_connection_status(bool connected)
{
    if (connected) {
        ESP_LOGI(TAG, "[HEARTBEAT] Gateway transport connected to Backend! Sending immediate initial heartbeat (t=0)...");
        gateway_heartbeat_timer_cb(NULL);
    }
}

static void nodes_liveness_timer_cb(void *arg)
{
    (void)arg;
    if (!gateway_transport_is_connected()) {
        return;
    }

    /* 1. Broadcast DOWN_HEARTBEAT_PROBE to LoRa nodes */
    uint8_t probe_pkt[7] = {
        (uint8_t)LORA_MAC_V2_TYPE_DOWN_HEARTBEAT_PROBE,
        0x00, 0x01, /* sequence */
        0xAA, 0xBB, 0xCC, 0xDD /* auth/MIC */
    };
    (void)sx1276_tx(probe_pkt, sizeof(probe_pkt), pdMS_TO_TICKS(100));
    (void)sx1276_start_rx_continuous();

    /* 2. Build 32-node bitmap and publish to Backend */
    gateway_nodes_bitmap_pkt_t bmp_pkt = {
        .type = HEARTBEAT_TYPE_NODES_BITMAP,
        .node_count = MAX_LORA_TRACKED_NODES,
        .timestamp = (uint32_t)(esp_timer_get_time() / 1000000ULL),
    };
    memset(bmp_pkt.bitmap, 0, sizeof(bmp_pkt.bitmap));
    uint32_t now_s = bmp_pkt.timestamp;

    for (uint8_t i = 1; i <= MAX_LORA_TRACKED_NODES; i++) {
        if (s_node_alive[i] && (now_s - s_node_last_seen_s[i] < 600)) {
            uint8_t byte_idx = (i - 1) / 8;
            uint8_t bit_idx = (i - 1) % 8;
            bmp_pkt.bitmap[byte_idx] |= (1 << bit_idx);
        } else {
            s_node_alive[i] = false;
        }
    }

    (void)gateway_transport_publish_heartbeat((const uint8_t *)&bmp_pkt, sizeof(bmp_pkt));
    ESP_LOGI(TAG, "[BITMAP] Published Node Liveness Bitmap: [0x%02X 0x%02X 0x%02X 0x%02X] (N=%d)",
             bmp_pkt.bitmap[0], bmp_pkt.bitmap[1], bmp_pkt.bitmap[2], bmp_pkt.bitmap[3],
             MAX_LORA_TRACKED_NODES);
}

static esp_err_t process_join_packet(const uint8_t *payload, size_t length, int16_t rssi, int8_t snr)
{
    if (payload == NULL || length == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t msg_type = payload[0];
    uint64_t now_us = (uint64_t)esp_timer_get_time();
    float snr_f = (float)snr / 4.0f;

    switch (msg_type) {
        case LORA_MAC_V2_TYPE_UP_JOIN_HELLO: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_HELLO (68B): MAC=%02X:%02X:%02X:%02X:%02X:%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[1], payload[2], payload[3], payload[4], payload[5], payload[6],
                         rssi, (double)snr_f);

                /* Forward Join Request to Backend over MQTT for User Approval */
                char join_json[256];
                int join_len = snprintf(join_json, sizeof(join_json),
                    "{\"gateway_id\":\"%s\",\"device_mac\":\"%02x%02x%02x%02x%02x%02x\",\"rssi\":%d,\"snr\":%.1f}",
                    s_gateway_id,
                    payload[1], payload[2], payload[3], payload[4], payload[5], payload[6],
                    rssi, (double)snr_f);
                if (join_len > 0) {
                    (void)gateway_transport_publish_join_relay((const uint8_t *)join_json, (size_t)join_len);
                    ESP_LOGI(TAG, "[JOIN RELAY] Forwarded UP_JOIN_HELLO (MAC=%02X:%02X:%02X:%02X:%02X:%02X) to Backend MQTT for user approval",
                             payload[1], payload[2], payload[3], payload[4], payload[5], payload[6]);
                }

                uint8_t req_mac[6];
                memcpy(req_mac, &payload[1], 6);
                approved_node_entry_t *entry = find_or_create_node_entry(req_mac);
                if (entry) {
                    /* Cache this hello packet in case approval arrives while waiting */
                    memcpy(entry->cached_hello, payload, LORA_MAC_V2_LEN_UP_JOIN_HELLO);
                    entry->cached_rssi = rssi;
                    entry->cached_snr = snr;
                    entry->has_cached_hello = true;

                    if (!entry->approved) {
                        ESP_LOGI(TAG, "[JOIN PENDING] Node %02X:%02X:%02X:%02X:%02X:%02X is awaiting User Approval on Web Dashboard. No grant sent.",
                                 req_mac[0], req_mac[1], req_mac[2], req_mac[3], req_mac[4], req_mac[5]);
                        return ESP_OK;
                    }

                    /* Node IS approved by user! Send DOWN_JOIN_GRANT with assigned node_id */
                    uint8_t grant_buf[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
                    size_t grant_len = 0;
                    esp_err_t h_err = gateway_v2_join_handle_hello_with_id(
                        &s_join_engine,
                        payload,
                        length,
                        rssi,
                        snr_f,
                        now_us,
                        NULL,
                        entry->node_id,
                        grant_buf,
                        &grant_len
                    );
                    if (h_err == ESP_OK) {
                        /* Persist session to NVS immediately */
                        (void)gateway_save_node_session(entry->node_id);
                        /* Allow Node time to switch from TX to RXSINGLE (RF turnaround margin) */
                        vTaskDelay(pdMS_TO_TICKS(40));
                        ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_GRANT (%zu bytes) to Node #%u on 920.250 MHz (CH0)...", grant_len, entry->node_id);
                        esp_err_t tx_err = sx1276_tx(grant_buf, (uint8_t)grant_len, pdMS_TO_TICKS(300));
                        if (tx_err == ESP_OK) {
                            ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_GRANT transmitted successfully for Node #%u", entry->node_id);
                        } else {
                            ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_GRANT: %s", esp_err_to_name(tx_err));
                        }
                    } else {
                        ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_HELLO: %s", esp_err_to_name(h_err));
                    }
                    entry->has_cached_hello = false;
                    return h_err;
                }
                return ESP_OK;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_KEY_CONFIRM (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                uint8_t finish_buf[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
                size_t finish_len = 0;
                esp_err_t c_err = gateway_v2_join_handle_confirm(
                    &s_join_engine,
                    payload,
                    length,
                    NULL, /* edge finish */
                    finish_buf,
                    &finish_len
                );
                if (c_err == ESP_OK) {
                    /* Allow Node time to switch from TX to RXSINGLE (RF turnaround margin) */
                    vTaskDelay(pdMS_TO_TICKS(40));
                    ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_FINISH (%zu bytes) to Node #%u on 920.250 MHz (CH0)...", finish_len, payload[2]);
                    esp_err_t tx_err = sx1276_tx(finish_buf, (uint8_t)finish_len, pdMS_TO_TICKS(300));
                    if (tx_err == ESP_OK) {
                        ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_FINISH transmitted successfully");
                    } else {
                        ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_FINISH: %s", esp_err_to_name(tx_err));
                    }
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_KEY_CONFIRM: %s", esp_err_to_name(c_err));
                }
                return c_err;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_JOIN_READY: {
            if (length == LORA_MAC_V2_LEN_UP_JOIN_READY) {
                ESP_LOGI(TAG, "[JOIN RX] Received UP_JOIN_READY (31B) from Node #%u: RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                         payload[2], rssi, (double)snr_f);
                esp_err_t r_err = gateway_v2_join_handle_ready(
                    &s_join_engine,
                    payload,
                    length
                );
                if (r_err == ESP_OK) {
                    ESP_LOGI(TAG, "[JOIN SUCCESS] Node #%u Join complete! Session committed in INSTALLED_INACTIVE state.", payload[2]);
                    (void)gateway_save_node_session(payload[2]);
                    s_revoked_nodes[payload[2]].revoked = false;
                    s_revoked_nodes[payload[2]].has_key = false;
                } else {
                    ESP_LOGW(TAG, "[JOIN] Failed to handle UP_JOIN_READY: %s", esp_err_to_name(r_err));
                }
                return r_err;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_EVENT: {
            if (length == LORA_MAC_V2_LEN_UP_EVENT) {
                lora_mac_v2_header_t hdr;
                esp_err_t hdr_err = lora_mac_v2_header_parse(payload, length, &hdr);
                if (hdr_err != ESP_OK || hdr.ver_type != LORA_MAC_V2_TYPE_UP_EVENT) {
                    ESP_LOGW(TAG, "[EVENT RX] Invalid UP_EVENT header");
                    return ESP_ERR_INVALID_ARG;
                }

                if (hdr.node_id > 0 && s_revoked_nodes[hdr.node_id].revoked) {
                    ESP_LOGW(TAG, "[EVENT RX] Node #%u is REVOKED. Sending DOWN_REVOKE instead of ACK.", hdr.node_id);
                    vTaskDelay(pdMS_TO_TICKS(20));

                    uint8_t revoke_packet[19];
                    lora_mac_v2_header_t rev_hdr = {
                        .ver_type = LORA_MAC_V2_TYPE_DOWN_REVOKE,
                        .node_id = hdr.node_id,
                        .session_sel = hdr.session_sel,
                        .frame_counter = ++s_downlink_frame_counter,
                    };
                    size_t rev_hdr_written = 0;
                    (void)lora_mac_v2_header_encode(&rev_hdr, revoke_packet, 19U, &rev_hdr_written);

                    lora_mac_v2_down_revoke_t rev_payload = {
                        .revoke_reason = 0x01,
                    };
                    uint8_t rev_pt[4];
                    size_t pt_written = 0;
                    (void)lora_mac_v2_down_revoke_serialize(&rev_payload, rev_pt, 4U, &pt_written);

                    uint8_t dl_nonce[13];
                    (void)lora_mac_v2_build_nonce(s_revoked_nodes[hdr.node_id].nonce_prefix,
                                                  LORA_MAC_V2_DIR_DOWNLINK,
                                                  rev_hdr.frame_counter,
                                                  dl_nonce);

                    esp_err_t enc_err = lora_mac_crypto_encrypt_down_revoke(
                        s_revoked_nodes[hdr.node_id].k_session_dl,
                        dl_nonce,
                        revoke_packet, 7U,
                        rev_pt, 4U,
                        &revoke_packet[7],
                        &revoke_packet[11]);
                    if (enc_err == ESP_OK) {
                        ESP_LOGI(TAG, "[REVOKE TX] Sending DOWN_REVOKE (19B) to Node #%u...", hdr.node_id);
                        esp_err_t tx_err = sx1276_tx(revoke_packet, 19U, pdMS_TO_TICKS(100));
                        if (tx_err == ESP_OK) {
                            ESP_LOGI(TAG, "[REVOKE TX] DOWN_REVOKE transmitted successfully to Node #%u", hdr.node_id);
                        } else {
                            ESP_LOGE(TAG, "[REVOKE TX] Failed to transmit DOWN_REVOKE: %s", esp_err_to_name(tx_err));
                        }
                    }
                    return ESP_OK;
                }

                uint8_t k_session_up[16];
                uint8_t k_session_dl[16];
                uint8_t nonce_prefix[8];
                memcpy(nonce_prefix, DEFAULT_NONCE_PREFIX, sizeof(nonce_prefix));
                esp_err_t key_err = hal_session_key_lookup(hdr.node_id, NULL, k_session_up, k_session_dl, nonce_prefix);
                if (key_err != ESP_OK) {
                    /* Fallback to in-memory pending joins */
                    size_t slot_idx = (size_t)(hdr.node_id - 1);
                    if (slot_idx < GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS && s_join_engine.pending_joins[slot_idx].active) {
                        memcpy(k_session_up, s_join_engine.pending_joins[slot_idx].session_keys.k_session_up, 16);
                        memcpy(k_session_dl, s_join_engine.pending_joins[slot_idx].session_keys.k_session_dl, 16);
                        key_err = ESP_OK;
                    }
                }
                if (key_err != ESP_OK) {
                    ESP_LOGW(TAG, "[EVENT RX] Unknown keys for Node #%u", hdr.node_id);
                    return key_err;
                }

                uint8_t nonce[13];
                (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_UPLINK, hdr.frame_counter, nonce);

                uint8_t pt[11];
                esp_err_t dec_err = lora_mac_crypto_decrypt_up_event(k_session_up,
                                                                     nonce,
                                                                     payload, 7U,
                                                                     &payload[7], 11U,
                                                                     &payload[18],
                                                                     pt);
                if (dec_err != ESP_OK) {
                    ESP_LOGW(TAG, "[EVENT RX] Decryption/MIC verification failed for Node #%u", hdr.node_id);
                    return dec_err;
                }

                lora_mac_v2_up_event_t up_ev;
                (void)lora_mac_v2_up_event_deserialize(pt, 11U, &up_ev);
                ESP_LOGI(TAG, "==================================================");
                ESP_LOGI(TAG, ">>> VALID UP_EVENT RECEIVED! <<< Node #%u: Ref=%" PRIu32 ", Code=%u, Val=%d | RSSI=%d dBm, SNR=%.1f dB",
                         hdr.node_id, up_ev.event_ref, up_ev.event_code, up_ev.event_value, rssi, (double)snr_f);
                ESP_LOGI(TAG, "==================================================");

                /* Update node liveness tracking */
                s_rx_events_total++;
                if (hdr.node_id > 0 && hdr.node_id <= MAX_LORA_TRACKED_NODES) {
                    s_node_alive[hdr.node_id] = true;
                    s_node_last_seen_s[hdr.node_id] = (uint32_t)(esp_timer_get_time() / 1000000ULL);
                }

                /* Commit to WAL */
                gateway_wal_event_t wal_ev = {
                    .node_id = hdr.node_id,
                    .session_sel = hdr.session_sel,
                    .frame_counter = hdr.frame_counter,
                    .event_ref = up_ev.event_ref,
                    .event_time = up_ev.event_time,
                    .event_code = up_ev.event_code,
                    .event_value = up_ev.event_value,
                    .received_at_ms = (uint32_t)(esp_timer_get_time() / 1000ULL),
                    .rssi_dbm = rssi,
                    .snr_db_quarter = snr,
                };
                (void)gateway_wal_push(&s_gateway_wal, &wal_ev);

                /* Publish Event to Backend over MQTT for UI Charts */
                char alert_payload[384];
                int alert_len = snprintf(alert_payload, sizeof(alert_payload),
                    "{\"schema_version\":\"1.0-draft\",\"event_id\":\"%s:00000000-0000-0000-0000-000000000001:%" PRIu32 "\",\"gateway_id\":\"%s\",\"node_id\":%u,\"event_code\":%u,\"event_value\":%d,\"battery_mv\":3300,\"severity\":\"P3_NORMAL\",\"radio_ack_sent\":true,\"data\":{\"event_ref\":%" PRIu32 ",\"event_code\":%u,\"event_value\":%d}}",
                    s_gateway_id, (uint32_t)(esp_timer_get_time() / 1000ULL),
                    s_gateway_id,
                    hdr.node_id, up_ev.event_code, up_ev.event_value,
                    up_ev.event_ref, up_ev.event_code, up_ev.event_value);
                if (alert_len > 0) {
                    (void)gateway_transport_publish_event((const uint8_t *)alert_payload, (size_t)alert_len);
                    ESP_LOGI(TAG, "[EVENT TX] Published event to MQTT: Node #%u, Code=%u, Val=%d",
                             hdr.node_id, up_ev.event_code, up_ev.event_value);
                }

                /* Small turnaround delay before sending ACK */
                vTaskDelay(pdMS_TO_TICKS(20));

                uint8_t ack_packet[19];
                lora_mac_v2_header_t ack_hdr = {
                    .ver_type = LORA_MAC_V2_TYPE_DOWN_EVENT_ACK,
                    .node_id = hdr.node_id,
                    .session_sel = hdr.session_sel,
                    .frame_counter = ++s_downlink_frame_counter,
                };
                size_t ack_hdr_written = 0;
                (void)lora_mac_v2_header_encode(&ack_hdr, ack_packet, 19U, &ack_hdr_written);

                lora_mac_v2_down_event_ack_t ack_payload = {
                    .event_ref = up_ev.event_ref,
                };
                uint8_t ack_pt[4];
                size_t pt_written = 0;
                (void)lora_mac_v2_down_event_ack_serialize(&ack_payload, ack_pt, 4U, &pt_written);

                uint8_t dl_nonce[13];
                (void)lora_mac_v2_build_nonce(nonce_prefix, LORA_MAC_V2_DIR_DOWNLINK, ack_hdr.frame_counter, dl_nonce);

                esp_err_t enc_err = lora_mac_crypto_encrypt_down_ack(k_session_dl,
                                                                     dl_nonce,
                                                                     ack_packet, 7U,
                                                                     ack_pt, 4U,
                                                                     &ack_packet[7],
                                                                     &ack_packet[11]);
                if (enc_err == ESP_OK) {
                    ESP_LOGI(TAG, "[EVENT ACK TX] Sending DOWN_EVENT_ACK (19B) for Ref=%" PRIu32 " to Node #%u...",
                             up_ev.event_ref, hdr.node_id);
                    esp_err_t tx_ack_err = sx1276_tx(ack_packet, 19U, pdMS_TO_TICKS(100));
                    if (tx_ack_err == ESP_OK) {
                        ESP_LOGI(TAG, "[EVENT ACK TX] DOWN_EVENT_ACK transmitted successfully");
                    } else {
                        ESP_LOGE(TAG, "[EVENT ACK TX] Failed to transmit ACK: %s", esp_err_to_name(tx_ack_err));
                    }
                }
                return ESP_OK;
            }
            break;
        }

        case LORA_MAC_V2_TYPE_UP_HEARTBEAT_ACK: {
            if (length >= 2) {
                uint8_t ack_node_id = payload[1];
                if (ack_node_id > 0 && ack_node_id <= MAX_LORA_TRACKED_NODES) {
                    s_node_alive[ack_node_id] = true;
                    s_node_last_seen_s[ack_node_id] = (uint32_t)(esp_timer_get_time() / 1000000ULL);
                    ESP_LOGI(TAG, "[HEARTBEAT ACK] Node #%u confirmed ALIVE via LoRa (RSSI=%d dBm)",
                             ack_node_id, rssi);
                }
                if (ack_node_id > 0 && s_revoked_nodes[ack_node_id].revoked) {
                    ESP_LOGW(TAG, "[HEARTBEAT ACK] Node #%u is REVOKED. Sending DOWN_REVOKE in RX window.", ack_node_id);
                    vTaskDelay(pdMS_TO_TICKS(20));

                    uint8_t revoke_packet[19];
                    lora_mac_v2_header_t rev_hdr = {
                        .ver_type = LORA_MAC_V2_TYPE_DOWN_REVOKE,
                        .node_id = ack_node_id,
                        .session_sel = 0,
                        .frame_counter = ++s_downlink_frame_counter,
                    };
                    size_t rev_hdr_written = 0;
                    (void)lora_mac_v2_header_encode(&rev_hdr, revoke_packet, 19U, &rev_hdr_written);

                    lora_mac_v2_down_revoke_t rev_payload = {
                        .revoke_reason = 0x01,
                    };
                    uint8_t rev_pt[4];
                    size_t pt_written = 0;
                    (void)lora_mac_v2_down_revoke_serialize(&rev_payload, rev_pt, 4U, &pt_written);

                    uint8_t dl_nonce[13];
                    (void)lora_mac_v2_build_nonce(s_revoked_nodes[ack_node_id].nonce_prefix,
                                                  LORA_MAC_V2_DIR_DOWNLINK,
                                                  rev_hdr.frame_counter,
                                                  dl_nonce);

                    esp_err_t enc_err = lora_mac_crypto_encrypt_down_revoke(
                        s_revoked_nodes[ack_node_id].k_session_dl,
                        dl_nonce,
                        revoke_packet, 7U,
                        rev_pt, 4U,
                        &revoke_packet[7],
                        &revoke_packet[11]);
                    if (enc_err == ESP_OK) {
                        ESP_LOGI(TAG, "[HEARTBEAT REVOKE TX] Sending DOWN_REVOKE (19B) to Node #%u...", ack_node_id);
                        esp_err_t tx_err = sx1276_tx(revoke_packet, 19U, pdMS_TO_TICKS(100));
                        if (tx_err == ESP_OK) {
                            ESP_LOGI(TAG, "[HEARTBEAT REVOKE TX] DOWN_REVOKE transmitted successfully to Node #%u", ack_node_id);
                        } else {
                            ESP_LOGE(TAG, "[HEARTBEAT REVOKE TX] Failed to transmit DOWN_REVOKE: %s", esp_err_to_name(tx_err));
                        }
                    }
                    return ESP_OK;
                }
            }
            return ESP_OK;
        }

        default:
            ESP_LOGD(TAG, "[RF RX] Non-join frame: type=0x%02X, len=%zu", msg_type, length);
            break;
    }
    return ESP_OK;
}

static void gateway_radio_rx_task(void *pvParameters)
{
    (void)pvParameters;
    ESP_LOGI(TAG, "Gateway Continuous RX Task running (24/7 active on 920.250 MHz CH0)");

    /* Start in continuous RX to listen for OTA join handshakes and event uplinks */
    (void)sx1276_start_rx_continuous();

    while (1) {
        /* Check for incoming LoRa packet with 20ms wait */
        sx1276_rx_frame_t rx_frame;
        esp_err_t rx_err = sx1276_read_frame(&rx_frame, pdMS_TO_TICKS(20));
        if (rx_err == ESP_OK && rx_frame.length > 0) {
            ESP_LOGI(TAG, "[RF RX] Frame received: len=%u B, Type=0x%02X, RSSI=%d dBm, SNR=%.1f dB | Freq=920.250 MHz (CH0)",
                     rx_frame.length, rx_frame.payload[0], rx_frame.rssi_dbm, (float)rx_frame.snr_db_quarter / 4.0f);
            (void)process_join_packet(rx_frame.payload, rx_frame.length, rx_frame.rssi_dbm, rx_frame.snr_db_quarter);
            (void)sx1276_start_rx_continuous();
        }
    }
}

void app_main(void)
{
    ESP_LOGI(TAG, "Starting Gateway Master (ESP-IDF v6.1 / SX1276 MVP Continuous RX)");

    // Initialize NVS flash for durable session key storage
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // Initialize Session Key Store & restore durable slots from NVS
    ret = session_key_store_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize session key store: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Session key store initialized successfully");
    }

    // Initialize Gateway WAL
    ret = gateway_wal_init(&s_gateway_wal);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway WAL: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway WAL initialized successfully");
    }

    // Initialize Crypto Subsystem
    ret = lora_mac_crypto_init();
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize lora_mac crypto: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "LoRa MAC crypto initialized successfully");
    }

    // Initialize Gateway Transport (WiFi Station & MQTT 5.0 mTLS)
    gateway_transport_config_t transport_cfg = {
#ifdef CONFIG_GATEWAY_ID
        .gateway_id = CONFIG_GATEWAY_ID,
#else
        .gateway_id = "gw-a",
#endif
#ifdef CONFIG_GATEWAY_WIFI_SSID
        .wifi_ssid = CONFIG_GATEWAY_WIFI_SSID,
#else
        .wifi_ssid = "myssid",
#endif
#ifdef CONFIG_GATEWAY_WIFI_PASSWORD
        .wifi_password = CONFIG_GATEWAY_WIFI_PASSWORD,
#else
        .wifi_password = "mypassword",
#endif
#ifdef CONFIG_GATEWAY_WIFI_MAX_RETRY
        .wifi_max_retry = CONFIG_GATEWAY_WIFI_MAX_RETRY,
#else
        .wifi_max_retry = 5,
#endif
#ifdef CONFIG_GATEWAY_BROKER_URI
        .broker_uri = CONFIG_GATEWAY_BROKER_URI,
#else
        .broker_uri = "",
#endif
        .disable_auto_connect = false,
    };

    ret = gateway_transport_init(&transport_cfg);
    strncpy(s_gateway_id, transport_cfg.gateway_id, sizeof(s_gateway_id) - 1);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize gateway transport: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway transport initialized successfully");
        gateway_transport_register_session_key_callback(&on_downlink_session_key);
        gateway_transport_register_schedule_callback(&on_downlink_schedule);
        gateway_transport_register_join_grant_callback(&on_downlink_join_grant);
        gateway_transport_register_join_wait_callback(&on_downlink_join_wait);
        gateway_transport_register_join_reject_callback(&on_downlink_join_reject);
        gateway_transport_register_node_revoke_callback(&on_downlink_node_revoke);
        gateway_transport_register_status_callback(&on_transport_connection_status);
    }

    // Initialize Gateway V2 Join Relay Engine
    gateway_v2_join_config_t join_cfg = {
#ifdef CONFIG_GATEWAY_TARGET_GW_ID
        .target_gw_id = (uint8_t)CONFIG_GATEWAY_TARGET_GW_ID,
#else
        .target_gw_id = 1,
#endif
        .network_id = 100,
    };
    snprintf(join_cfg.gateway_id, sizeof(join_cfg.gateway_id), "%s", transport_cfg.gateway_id);
    snprintf(join_cfg.gateway_epoch, sizeof(join_cfg.gateway_epoch), "%s", GATEWAY_V2_JOIN_DEFAULT_EPOCH);
    ret = gateway_v2_join_init(&s_join_engine, &join_cfg);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize Gateway V2 Join Engine: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "Gateway V2 Join Engine initialized successfully");
        /* Restore persistent joined node sessions from NVS flash */
        gateway_restore_sessions_from_nvs();
    }

    // Initialize Gateway SX1276 radio transceiver
    ret = sx1276_init(NULL, NULL);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to initialize SX1276 driver: %s", esp_err_to_name(ret));
    } else {
        ESP_LOGI(TAG, "SX1276 radio initialized in STANDBY mode");
    }

    // Create static FreeRTOS task for 24/7 Continuous RX per RTOS-005
    s_gateway_rx_task_handle = xTaskCreateStatic(
        gateway_radio_rx_task,
        "gw_rx_task",
        GATEWAY_TASK_STACK_SIZE_BYTES,
        NULL,
        5, /* Priority */
        s_gateway_task_stack,
        &s_gateway_task_tcb
    );
    if (s_gateway_rx_task_handle == NULL) {
        ESP_LOGE(TAG, "Failed to create gateway radio RX task");
    }

    // 1. Gateway Binary Heartbeat: periodic 30-second cadence
    const esp_timer_create_args_t gw_hb_args = {
        .callback = &gateway_heartbeat_timer_cb,
        .arg = NULL,
        .name = "gw_heartbeat_timer"
    };
    if (esp_timer_create(&gw_hb_args, &s_gw_heartbeat_timer) == ESP_OK) {
        ESP_ERROR_CHECK(esp_timer_start_periodic(s_gw_heartbeat_timer, 30000000ULL)); /* 30 seconds */
        ESP_LOGI(TAG, "Gateway binary heartbeat timer started (30s cadence)");
    }

    // 2. Node Liveness Probe & Bitmap: periodic 5-minute cadence (300 seconds)
    const esp_timer_create_args_t nodes_live_args = {
        .callback = &nodes_liveness_timer_cb,
        .arg = NULL,
        .name = "nodes_liveness_timer"
    };
    if (esp_timer_create(&nodes_live_args, &s_nodes_liveness_timer) == ESP_OK) {
        ESP_ERROR_CHECK(esp_timer_start_periodic(s_nodes_liveness_timer, 300000000ULL)); /* 300 seconds = 5m */
        ESP_LOGI(TAG, "Node liveness probe and bitmap timer started (5m cadence)");
    }

    ESP_LOGI(TAG, "Gateway Master active and operational in 24/7 Continuous RX mode");
}
