#include "gateway_liveness.h"

#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "lora_mac.h"
#include "sx1276_driver.h"
#include "gateway_transport.h"

static const char *TAG = "gateway_master";

static esp_timer_handle_t s_gw_heartbeat_timer = NULL;
static esp_timer_handle_t s_nodes_liveness_timer = NULL;

static bool s_node_alive[MAX_LORA_TRACKED_NODES + 1] = {false};
static uint32_t s_node_last_seen_s[MAX_LORA_TRACKED_NODES + 1] = {0};
static uint32_t s_rx_events_total = 0;

esp_err_t gateway_liveness_init(void)
{
    memset(s_node_alive, 0, sizeof(s_node_alive));
    memset(s_node_last_seen_s, 0, sizeof(s_node_last_seen_s));
    s_rx_events_total = 0;
    return ESP_OK;
}

void gateway_liveness_record_event(uint8_t node_id)
{
    s_rx_events_total++;
    gateway_liveness_record_node_alive(node_id);
}

void gateway_liveness_record_node_alive(uint8_t node_id)
{
    if (node_id > 0 && node_id <= MAX_LORA_TRACKED_NODES) {
        s_node_alive[node_id] = true;
        s_node_last_seen_s[node_id] = (uint32_t)(esp_timer_get_time() / 1000000ULL);
    }
}

uint32_t gateway_liveness_get_rx_events_total(void)
{
    return s_rx_events_total;
}

void gateway_heartbeat_timer_cb(void *arg)
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

void gateway_liveness_on_transport_connection_status(bool connected)
{
    if (connected) {
        ESP_LOGI(TAG, "[HEARTBEAT] Gateway transport connected to Backend! Sending immediate initial heartbeat (t=0)...");
        gateway_heartbeat_timer_cb(NULL);
    }
}

void nodes_liveness_timer_cb(void *arg)
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

esp_err_t gateway_liveness_start_timers(void)
{
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

    return ESP_OK;
}
