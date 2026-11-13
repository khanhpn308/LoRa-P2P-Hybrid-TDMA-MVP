#include "gateway_downlink.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lora_mac.h"
#include "sx1276_driver.h"
#include "gateway_transport.h"
#include "gateway_session_mgr.h"

static const char *TAG = "gateway_master";

static gateway_v2_join_engine_t *s_join_engine_ptr = NULL;

esp_err_t gateway_downlink_init(gateway_v2_join_engine_t *join_engine)
{
    s_join_engine_ptr = join_engine;
    return ESP_OK;
}

void on_downlink_session_key(const uint8_t *data, size_t len)
{
    (void)data;
    ESP_LOGI(TAG, "Downlink session-key-install received (%zu bytes)", len);
}

void on_downlink_schedule(const uint8_t *data, size_t len)
{
    (void)data;
    ESP_LOGI(TAG, "Downlink schedule received (%zu bytes)", len);
}

void on_downlink_join_grant(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || s_join_engine_ptr == NULL) return;
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
        gateway_session_mgr_clear_revocation(entry->node_id);
        ESP_LOGI(TAG, "[APPROVED] Node %02X:%02X:%02X:%02X:%02X:%02X approved by User! Assigned Node ID #%u",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5], entry->node_id);

        /* If we have a cached hello frame waiting, send grant now! */
        if (entry->has_cached_hello) {
            uint8_t grant_buf[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
            size_t grant_len = 0;
            uint64_t now_us = (uint64_t)esp_timer_get_time();
            float snr_f = (float)entry->cached_snr / 4.0f;

            esp_err_t h_err = gateway_v2_join_handle_hello_with_id(
                s_join_engine_ptr,
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
                vTaskDelay(pdMS_TO_TICKS(40));
                ESP_LOGI(TAG, "[JOIN TX] Transmitting DOWN_JOIN_GRANT (%zu bytes) to Node #%u...", grant_len, entry->node_id);
                esp_err_t tx_err = sx1276_tx(grant_buf, (uint8_t)grant_len, pdMS_TO_TICKS(300));
                if (tx_err == ESP_OK) {
                    ESP_LOGI(TAG, "[JOIN TX] DOWN_JOIN_GRANT transmitted successfully for Node #%u", entry->node_id);
                } else {
                    ESP_LOGE(TAG, "[JOIN TX] Failed to transmit DOWN_JOIN_GRANT: %s", esp_err_to_name(tx_err));
                }
                (void)gateway_save_node_session(entry->node_id);
            } else {
                ESP_LOGE(TAG, "[JOIN TX] Failed to handle UP_JOIN_HELLO with ID: %s", esp_err_to_name(h_err));
            }
            entry->has_cached_hello = false;
        } else {
            ESP_LOGW(TAG, "[JOIN TX] No cached UP_JOIN_HELLO for MAC %02X:%02X:%02X:%02X:%02X:%02X, cannot send DOWN_JOIN_GRANT",
                     mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
        }

        /* Re-enable 24/7 continuous RX on Gateway to receive retries or subsequent frames */
        (void)sx1276_start_rx_continuous();
    }
}

void on_downlink_join_wait(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || s_join_engine_ptr == NULL) return;
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
            s_join_engine_ptr,
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

void on_downlink_join_reject(const uint8_t *data, size_t len)
{
    if (data == NULL || len == 0 || s_join_engine_ptr == NULL) return;
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
    if (entry) {
        if (entry->has_cached_hello) {
            uint8_t reject_buf[LORA_MAC_V2_LEN_DOWN_JOIN_REJECT];
            size_t reject_len = 0;

            esp_err_t b_err = gateway_v2_join_build_reject(
                s_join_engine_ptr,
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
            entry->has_cached_hello = false;
        } else {
            ESP_LOGW(TAG, "[JOIN TX] No cached UP_JOIN_HELLO for MAC %02X:%02X:%02X:%02X:%02X:%02X, cannot send DOWN_JOIN_REJECT",
                     mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
        }
        /* Clear cached hello and approval on reject */
        entry->approved = false;
    }

    /* Re-enable 24/7 continuous RX on Gateway immediately (stateless radio bridge) */
    (void)sx1276_start_rx_continuous();
}

void on_downlink_node_revoke(const uint8_t *data, size_t len)
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

    gateway_session_mgr_revoke_node(node_id);
}

void gateway_downlink_register_callbacks(void)
{
    gateway_transport_register_session_key_callback(&on_downlink_session_key);
    gateway_transport_register_schedule_callback(&on_downlink_schedule);
    gateway_transport_register_join_grant_callback(&on_downlink_join_grant);
    gateway_transport_register_join_wait_callback(&on_downlink_join_wait);
    gateway_transport_register_join_reject_callback(&on_downlink_join_reject);
    gateway_transport_register_node_revoke_callback(&on_downlink_node_revoke);
}
