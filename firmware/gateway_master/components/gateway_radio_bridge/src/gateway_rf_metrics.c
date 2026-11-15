#include "gateway_rf_metrics.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "gateway_transport.h"
#include "sx1276_driver.h"

static const char *TAG = "gateway_rf_metrics";

static char s_gateway_id[32] = "gw-a";
static char s_gateway_epoch[37] = {0};
static uint64_t s_sample_seq_counter = 0;

static gateway_rf_node_cache_entry_t s_node_cache[GATEWAY_RF_METRICS_MAX_NODES + 1][GATEWAY_RF_METRICS_MAX_CHANNELS];
static gateway_rf_channel_cache_entry_t s_channel_cache[GATEWAY_RF_METRICS_MAX_CHANNELS];

#ifdef ESP_PLATFORM
static SemaphoreHandle_t s_rf_mutex = NULL;
static StaticSemaphore_t s_rf_mutex_buffer;
#endif

static bool is_valid_uuid(const char *uuid)
{
    if (uuid == NULL) {
        return false;
    }
    if (strlen(uuid) != 36) {
        return false;
    }
    for (size_t i = 0; i < 36; i++) {
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (uuid[i] != '-') {
                return false;
            }
        } else {
            char c = uuid[i];
            if (!((c >= '0' && c <= '9') ||
                  (c >= 'a' && c <= 'f') ||
                  (c >= 'A' && c <= 'F'))) {
                return false;
            }
        }
    }
    return true;
}

static void lock_rf(void)
{
#ifdef ESP_PLATFORM
    if (s_rf_mutex != NULL) {
        (void)xSemaphoreTake(s_rf_mutex, portMAX_DELAY);
    }
#endif
}

static void unlock_rf(void)
{
#ifdef ESP_PLATFORM
    if (s_rf_mutex != NULL) {
        (void)xSemaphoreGive(s_rf_mutex);
    }
#endif
}

esp_err_t gateway_rf_metrics_init(const char *gateway_id, const char *gateway_epoch)
{
    if (gateway_id == NULL || strlen(gateway_id) == 0) {
        ESP_LOGE(TAG, "RF Metrics init failed: gateway_id is NULL or empty");
        return ESP_ERR_INVALID_ARG;
    }
    if (!is_valid_uuid(gateway_epoch)) {
        ESP_LOGE(TAG, "RF Metrics init failed: invalid or missing gateway_epoch UUID: %s",
                 gateway_epoch ? gateway_epoch : "NULL");
        return ESP_ERR_INVALID_ARG;
    }

#ifdef ESP_PLATFORM
    if (s_rf_mutex == NULL) {
        s_rf_mutex = xSemaphoreCreateMutexStatic(&s_rf_mutex_buffer);
    }
#endif

    lock_rf();
    strncpy(s_gateway_id, gateway_id, sizeof(s_gateway_id) - 1);
    s_gateway_id[sizeof(s_gateway_id) - 1] = '\0';

    strncpy(s_gateway_epoch, gateway_epoch, sizeof(s_gateway_epoch) - 1);
    s_gateway_epoch[sizeof(s_gateway_epoch) - 1] = '\0';

    memset(s_node_cache, 0, sizeof(s_node_cache));
    memset(s_channel_cache, 0, sizeof(s_channel_cache));
    s_sample_seq_counter = 0;
    unlock_rf();

    ESP_LOGI(TAG, "RF Metrics initialized: GW=%s Epoch=%s", s_gateway_id, s_gateway_epoch);
    return ESP_OK;
}

const char *gateway_rf_metrics_get_epoch(void)
{
    return s_gateway_epoch;
}

uint64_t gateway_rf_metrics_next_seq(void)
{
    uint64_t seq;
    lock_rf();
    seq = ++s_sample_seq_counter;
    unlock_rf();
    return seq;
}

esp_err_t gateway_rf_metrics_record_and_publish_node(uint8_t node_id,
                                                    uint8_t channel_idx,
                                                    int16_t rssi_dbm,
                                                    int8_t snr_db_quarter,
                                                    uint64_t rx_monotonic_us,
                                                    const char *source,
                                                    bool is_mic_verified,
                                                    uint64_t *out_sample_seq)
{
    if (source == NULL || channel_idx >= GATEWAY_RF_METRICS_MAX_CHANNELS) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_gateway_epoch[0] == '\0') {
        ESP_LOGE(TAG, "RF Metrics not initialized with valid epoch");
        return ESP_ERR_INVALID_STATE;
    }

    uint64_t seq = gateway_rf_metrics_next_seq();
    if (out_sample_seq != NULL) {
        *out_sample_seq = seq;
    }

    const char *validation_str = is_mic_verified ? "VERIFIED" : "UNVERIFIED";
    const char *auth_prov_str = is_mic_verified ? "MIC_VERIFIED" : "UNVERIFIED_CRC_ONLY";
    float snr_db = (float)snr_db_quarter / 4.0f;

    /* Update thread-safe bounded cache */
    lock_rf();
    if (node_id <= GATEWAY_RF_METRICS_MAX_NODES) {
        gateway_rf_node_cache_entry_t *entry = &s_node_cache[node_id][channel_idx];
        entry->valid = true;
        entry->node_id = node_id;
        entry->channel_idx = channel_idx;
        entry->rssi_dbm = rssi_dbm;
        entry->snr_db_quarter = snr_db_quarter;
        entry->sample_seq = seq;
        entry->rx_monotonic_us = rx_monotonic_us;
        strncpy(entry->source, source, sizeof(entry->source) - 1);
        entry->source[sizeof(entry->source) - 1] = '\0';
        strncpy(entry->validation, validation_str, sizeof(entry->validation) - 1);
        entry->validation[sizeof(entry->validation) - 1] = '\0';
        strncpy(entry->auth_provenance, auth_prov_str, sizeof(entry->auth_provenance) - 1);
        entry->auth_provenance[sizeof(entry->auth_provenance) - 1] = '\0';
    }
    unlock_rf();

    /* Compute age at publish time */
    uint64_t now_us = (uint64_t)esp_timer_get_time();
    uint32_t age_ms = 0;
    if (now_us > rx_monotonic_us) {
        age_ms = (uint32_t)((now_us - rx_monotonic_us) / 1000ULL);
    }

    /* Build and validate strict JSON payload */
    char rf_json[GATEWAY_RF_JSON_MAX_LEN];
    int len = snprintf(rf_json, sizeof(rf_json),
        "{\"schema_version\":\"1.0-draft\","
        "\"gateway_id\":\"%s\","
        "\"gateway_epoch\":\"%s\","
        "\"sample_seq\":\"%" PRIu64 "\","
        "\"sample_monotonic_us\":\"%" PRIu64 "\","
        "\"age_ms\":%" PRIu32 ","
        "\"kind\":\"NODE_UPLINK\","
        "\"channel_idx\":%u,"
        "\"node_id\":%u,"
        "\"rssi_dbm\":%d,"
        "\"snr_db\":%.2f,"
        "\"source\":\"%s\","
        "\"validation\":\"%s\","
        "\"auth_provenance\":\"%s\"}",
        s_gateway_id,
        s_gateway_epoch,
        seq,
        rx_monotonic_us,
        age_ms,
        channel_idx,
        node_id,
        rssi_dbm,
        (double)snr_db,
        source,
        validation_str,
        auth_prov_str);

    if (len < 0 || (size_t)len >= sizeof(rf_json)) {
        ESP_LOGE(TAG, "Payload truncated or format error: len=%d", len);
        return ESP_ERR_INVALID_SIZE;
    }

    esp_err_t pub_err = gateway_transport_publish_rf_metrics((const uint8_t *)rf_json, (size_t)len);
    if (pub_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish NODE_UPLINK rf-metrics: %s", esp_err_to_name(pub_err));
        return pub_err;
    }

    ESP_LOGD(TAG, "[RF METRICS] Published NODE_UPLINK: Node=%u RSSI=%d dBm SNR=%.2f dB (%s)",
             node_id, rssi_dbm, (double)snr_db, auth_prov_str);
    return ESP_OK;
}

esp_err_t gateway_rf_metrics_format_alert_block(char *buf,
                                               size_t buf_size,
                                               uint64_t sample_seq,
                                               uint64_t rx_monotonic_us,
                                               uint8_t channel_idx,
                                               int16_t rssi_dbm,
                                               int8_t snr_db_quarter)
{
    if (buf == NULL || buf_size == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_gateway_epoch[0] == '\0') {
        return ESP_ERR_INVALID_STATE;
    }

    float snr_db = (float)snr_db_quarter / 4.0f;
    int len = snprintf(buf, buf_size,
        "\"rf\":{\"rssi_dbm\":%d,\"snr_db\":%.2f,\"channel_idx\":%u,\"rx_monotonic_us\":\"%" PRIu64 "\",\"gateway_epoch\":\"%s\",\"sample_seq\":\"%" PRIu64 "\"}",
        rssi_dbm, (double)snr_db, channel_idx, rx_monotonic_us, s_gateway_epoch, sample_seq);

    if (len < 0 || (size_t)len >= buf_size) {
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

esp_err_t gateway_rf_metrics_sample_and_publish_channel(void)
{
    if (s_gateway_epoch[0] == '\0') {
        return ESP_ERR_INVALID_STATE;
    }

    int16_t channel_rssi = 0;
    sx1276_channel_sample_context_t ctx = SX1276_CHANNEL_SAMPLE_IDLE;

    esp_err_t err = sx1276_read_channel_rssi(&channel_rssi, &ctx);
    if (err != ESP_OK) {
        /* Not in valid receive mode or SPI failure; fail closed */
        return err;
    }

    uint64_t seq = gateway_rf_metrics_next_seq();
    uint64_t sample_us = (uint64_t)esp_timer_get_time();
    const char *ctx_str = (ctx == SX1276_CHANNEL_SAMPLE_ACTIVE) ? "RX_ACTIVE" : "RX_IDLE";
    uint8_t channel_idx = 0; /* Gateway operates on CH0 (VN920 920.250 MHz) */

    /* Update cache */
    lock_rf();
    if (channel_idx < GATEWAY_RF_METRICS_MAX_CHANNELS) {
        gateway_rf_channel_cache_entry_t *entry = &s_channel_cache[channel_idx];
        entry->valid = true;
        entry->channel_idx = channel_idx;
        entry->channel_rssi_dbm = channel_rssi;
        entry->sample_seq = seq;
        entry->sample_monotonic_us = sample_us;
        strncpy(entry->sample_context, ctx_str, sizeof(entry->sample_context) - 1);
        entry->sample_context[sizeof(entry->sample_context) - 1] = '\0';
    }
    unlock_rf();

    char rf_json[GATEWAY_RF_JSON_MAX_LEN];
    int len = snprintf(rf_json, sizeof(rf_json),
        "{\"schema_version\":\"1.0-draft\","
        "\"gateway_id\":\"%s\","
        "\"gateway_epoch\":\"%s\","
        "\"sample_seq\":\"%" PRIu64 "\","
        "\"sample_monotonic_us\":\"%" PRIu64 "\","
        "\"age_ms\":0,"
        "\"kind\":\"CHANNEL\","
        "\"channel_idx\":%u,"
        "\"channel_rssi_dbm\":%d,"
        "\"sample_context\":\"%s\"}",
        s_gateway_id,
        s_gateway_epoch,
        seq,
        sample_us,
        channel_idx,
        channel_rssi,
        ctx_str);

    if (len < 0 || (size_t)len >= sizeof(rf_json)) {
        ESP_LOGE(TAG, "Channel payload format error or truncation: len=%d", len);
        return ESP_ERR_INVALID_SIZE;
    }

    esp_err_t pub_err = gateway_transport_publish_rf_metrics((const uint8_t *)rf_json, (size_t)len);
    if (pub_err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to publish CHANNEL rf-metrics: %s", esp_err_to_name(pub_err));
        return pub_err;
    }

    ESP_LOGD(TAG, "[RF METRICS] Published CHANNEL: RSSI=%d dBm, Context=%s", channel_rssi, ctx_str);
    return ESP_OK;
}

esp_err_t gateway_rf_metrics_get_node_cache(uint8_t node_id,
                                            uint8_t channel_idx,
                                            gateway_rf_node_cache_entry_t *out_entry)
{
    if (out_entry == NULL || node_id > GATEWAY_RF_METRICS_MAX_NODES ||
        channel_idx >= GATEWAY_RF_METRICS_MAX_CHANNELS) {
        return ESP_ERR_INVALID_ARG;
    }

    lock_rf();
    if (!s_node_cache[node_id][channel_idx].valid) {
        unlock_rf();
        return ESP_ERR_NOT_FOUND;
    }
    *out_entry = s_node_cache[node_id][channel_idx];
    unlock_rf();
    return ESP_OK;
}

esp_err_t gateway_rf_metrics_get_channel_cache(uint8_t channel_idx,
                                               gateway_rf_channel_cache_entry_t *out_entry)
{
    if (out_entry == NULL || channel_idx >= GATEWAY_RF_METRICS_MAX_CHANNELS) {
        return ESP_ERR_INVALID_ARG;
    }

    lock_rf();
    if (!s_channel_cache[channel_idx].valid) {
        unlock_rf();
        return ESP_ERR_NOT_FOUND;
    }
    *out_entry = s_channel_cache[channel_idx];
    unlock_rf();
    return ESP_OK;
}
