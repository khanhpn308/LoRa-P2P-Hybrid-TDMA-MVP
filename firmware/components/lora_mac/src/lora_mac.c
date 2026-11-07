#include "lora_mac.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "lora_mac";

esp_err_t lora_mac_init(void)
{
    ESP_LOGI(TAG, "Initialized shared lora_mac component (V2 baseline + candidate draft v0.1.0)");
    return ESP_OK;
}

/* =========================================================================
 * V2 SECURE MAC CODECS (DEC-127-01, DEC-127-02, DEC-MH-01, DEC-MH-08)
 * ========================================================================= */

esp_err_t lora_mac_v2_header_parse(const uint8_t *raw_buf, size_t len, lora_mac_v2_header_t *out_hdr)
{
    if (raw_buf == NULL || out_hdr == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < LORA_MAC_V2_HEADER_LEN) {
        return ESP_ERR_INVALID_SIZE;
    }

    uint8_t ver_type = raw_buf[0];
    uint8_t version = (uint8_t)((ver_type >> 5) & 0x07U);

    if (version != LORA_MAC_V2_PROTOCOL_VERSION) {
        ESP_LOGD(TAG, "Unsupported V2 MAC protocol version: %u", version);
        return ESP_ERR_INVALID_VERSION;
    }

    /* Valid V2 msg_type is in range 0x40..0x5F */
    if (ver_type < 0x40U || ver_type > 0x5FU) {
        ESP_LOGD(TAG, "Invalid V2 msg_type: 0x%02X", ver_type);
        return ESP_ERR_INVALID_VERSION;
    }

    out_hdr->ver_type = ver_type;
    out_hdr->node_id = raw_buf[1];
    out_hdr->session_sel = raw_buf[2];
    out_hdr->frame_counter = ((uint32_t)raw_buf[3] << 24) |
                             ((uint32_t)raw_buf[4] << 16) |
                             ((uint32_t)raw_buf[5] << 8) |
                             (uint32_t)raw_buf[6];

    return ESP_OK;
}

esp_err_t lora_mac_v2_header_encode(const lora_mac_v2_header_t *hdr,
                                    uint8_t *out_buf,
                                    size_t buf_size,
                                    size_t *out_written)
{
    if (hdr == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < LORA_MAC_V2_HEADER_LEN) {
        return ESP_ERR_NO_MEM;
    }

    uint8_t version = (uint8_t)((hdr->ver_type >> 5) & 0x07U);
    if (version != LORA_MAC_V2_PROTOCOL_VERSION) {
        return ESP_ERR_INVALID_ARG;
    }

    out_buf[0] = hdr->ver_type;
    out_buf[1] = hdr->node_id;
    out_buf[2] = hdr->session_sel;
    out_buf[3] = (uint8_t)((hdr->frame_counter >> 24) & 0xFFU);
    out_buf[4] = (uint8_t)((hdr->frame_counter >> 16) & 0xFFU);
    out_buf[5] = (uint8_t)((hdr->frame_counter >> 8) & 0xFFU);
    out_buf[6] = (uint8_t)(hdr->frame_counter & 0xFFU);

    if (out_written != NULL) {
        *out_written = LORA_MAC_V2_HEADER_LEN;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_build_nonce(const uint8_t prefix[8],
                                  uint8_t direction,
                                  uint32_t frame_counter,
                                  uint8_t out_nonce[LORA_MAC_V2_CCM_NONCE_LEN])
{
    if (prefix == NULL || out_nonce == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (direction != LORA_MAC_V2_DIR_UPLINK && direction != LORA_MAC_V2_DIR_DOWNLINK) {
        return ESP_ERR_INVALID_ARG;
    }

    (void)memcpy(out_nonce, prefix, 8);
    out_nonce[8] = direction;
    out_nonce[9] = (uint8_t)((frame_counter >> 24) & 0xFFU);
    out_nonce[10] = (uint8_t)((frame_counter >> 16) & 0xFFU);
    out_nonce[11] = (uint8_t)((frame_counter >> 8) & 0xFFU);
    out_nonce[12] = (uint8_t)(frame_counter & 0xFFU);

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_event_serialize(const lora_mac_v2_up_event_t *event,
                                         uint8_t *out_buf,
                                         size_t buf_size,
                                         size_t *out_written)
{
    if (event == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < 11U) {
        return ESP_ERR_NO_MEM;
    }

    out_buf[0] = (uint8_t)((event->event_ref >> 24) & 0xFFU);
    out_buf[1] = (uint8_t)((event->event_ref >> 16) & 0xFFU);
    out_buf[2] = (uint8_t)((event->event_ref >> 8) & 0xFFU);
    out_buf[3] = (uint8_t)(event->event_ref & 0xFFU);

    out_buf[4] = (uint8_t)((event->event_time >> 24) & 0xFFU);
    out_buf[5] = (uint8_t)((event->event_time >> 16) & 0xFFU);
    out_buf[6] = (uint8_t)((event->event_time >> 8) & 0xFFU);
    out_buf[7] = (uint8_t)(event->event_time & 0xFFU);

    out_buf[8] = event->event_code;

    out_buf[9] = (uint8_t)(((uint16_t)event->event_value >> 8) & 0xFFU);
    out_buf[10] = (uint8_t)((uint16_t)event->event_value & 0xFFU);

    if (out_written != NULL) {
        *out_written = 11U;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_event_deserialize(const uint8_t *buf,
                                           size_t len,
                                           lora_mac_v2_up_event_t *out_event)
{
    if (buf == NULL || out_event == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < 11U) {
        return ESP_ERR_INVALID_SIZE;
    }

    out_event->event_ref = ((uint32_t)buf[0] << 24) |
                           ((uint32_t)buf[1] << 16) |
                           ((uint32_t)buf[2] << 8) |
                           (uint32_t)buf[3];

    out_event->event_time = ((uint32_t)buf[4] << 24) |
                            ((uint32_t)buf[5] << 16) |
                            ((uint32_t)buf[6] << 8) |
                            (uint32_t)buf[7];

    out_event->event_code = buf[8];

    out_event->event_value = (int16_t)(((uint16_t)buf[9] << 8) | (uint16_t)buf[10]);

    return ESP_OK;
}

esp_err_t lora_mac_v2_down_event_ack_serialize(const lora_mac_v2_down_event_ack_t *ack,
                                               uint8_t *out_buf,
                                               size_t buf_size,
                                               size_t *out_written)
{
    if (ack == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < 4U) {
        return ESP_ERR_NO_MEM;
    }

    out_buf[0] = (uint8_t)((ack->event_ref >> 24) & 0xFFU);
    out_buf[1] = (uint8_t)((ack->event_ref >> 16) & 0xFFU);
    out_buf[2] = (uint8_t)((ack->event_ref >> 8) & 0xFFU);
    out_buf[3] = (uint8_t)(ack->event_ref & 0xFFU);

    if (out_written != NULL) {
        *out_written = 4U;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_down_event_ack_deserialize(const uint8_t *buf,
                                                 size_t len,
                                                 lora_mac_v2_down_event_ack_t *out_ack)
{
    if (buf == NULL || out_ack == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < 4U) {
        return ESP_ERR_INVALID_SIZE;
    }

    out_ack->event_ref = ((uint32_t)buf[0] << 24) |
                         ((uint32_t)buf[1] << 16) |
                         ((uint32_t)buf[2] << 8) |
                         (uint32_t)buf[3];

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_health_reply_serialize(const lora_mac_v2_up_health_reply_t *health,
                                                uint8_t *out_buf,
                                                size_t buf_size,
                                                size_t *out_written)
{
    if (health == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < 6U) {
        return ESP_ERR_NO_MEM;
    }

    out_buf[0] = (uint8_t)((health->battery_mv >> 8) & 0xFFU);
    out_buf[1] = (uint8_t)(health->battery_mv & 0xFFU);

    out_buf[2] = (uint8_t)((health->uptime_sec >> 16) & 0xFFU);
    out_buf[3] = (uint8_t)((health->uptime_sec >> 8) & 0xFFU);
    out_buf[4] = (uint8_t)(health->uptime_sec & 0xFFU);

    out_buf[5] = health->pending_count;

    if (out_written != NULL) {
        *out_written = 6U;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_health_reply_deserialize(const uint8_t *buf,
                                                  size_t len,
                                                  lora_mac_v2_up_health_reply_t *out_health)
{
    if (buf == NULL || out_health == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < 6U) {
        return ESP_ERR_INVALID_SIZE;
    }

    out_health->battery_mv = (uint16_t)(((uint16_t)buf[0] << 8) | (uint16_t)buf[1]);
    out_health->uptime_sec = ((uint32_t)buf[2] << 16) |
                             ((uint32_t)buf[3] << 8) |
                             (uint32_t)buf[4];
    out_health->pending_count = buf[5];

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_diag_metrics_serialize(const lora_mac_v2_up_diag_metrics_t *diag,
                                                uint8_t *out_buf,
                                                size_t buf_size,
                                                size_t *out_written)
{
    if (diag == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < 8U) {
        return ESP_ERR_NO_MEM;
    }

    out_buf[0] = (uint8_t)((diag->dropped_event_count >> 24) & 0xFFU);
    out_buf[1] = (uint8_t)((diag->dropped_event_count >> 16) & 0xFFU);
    out_buf[2] = (uint8_t)((diag->dropped_event_count >> 8) & 0xFFU);
    out_buf[3] = (uint8_t)(diag->dropped_event_count & 0xFFU);

    out_buf[4] = (uint8_t)((diag->diag_seq >> 24) & 0xFFU);
    out_buf[5] = (uint8_t)((diag->diag_seq >> 16) & 0xFFU);
    out_buf[6] = (uint8_t)((diag->diag_seq >> 8) & 0xFFU);
    out_buf[7] = (uint8_t)(diag->diag_seq & 0xFFU);

    if (out_written != NULL) {
        *out_written = 8U;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_up_diag_metrics_deserialize(const uint8_t *buf,
                                                  size_t len,
                                                  lora_mac_v2_up_diag_metrics_t *out_diag)
{
    if (buf == NULL || out_diag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < 8U) {
        return ESP_ERR_INVALID_SIZE;
    }

    out_diag->dropped_event_count = ((uint32_t)buf[0] << 24) |
                                   ((uint32_t)buf[1] << 16) |
                                   ((uint32_t)buf[2] << 8) |
                                   (uint32_t)buf[3];

    out_diag->diag_seq = ((uint32_t)buf[4] << 24) |
                         ((uint32_t)buf[5] << 16) |
                         ((uint32_t)buf[6] << 8) |
                         (uint32_t)buf[7];

    return ESP_OK;
}

esp_err_t lora_mac_v2_beacon_serialize(const lora_mac_v2_beacon_t *bcn,
                                       uint8_t *out_buf,
                                       size_t buf_size,
                                       size_t *out_written)
{
    if (bcn == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < 32U) {
        return ESP_ERR_NO_MEM;
    }

    out_buf[0] = bcn->magic;
    out_buf[1] = bcn->gw_id;

    out_buf[2] = (uint8_t)((bcn->epoch_sec >> 24) & 0xFFU);
    out_buf[3] = (uint8_t)((bcn->epoch_sec >> 16) & 0xFFU);
    out_buf[4] = (uint8_t)((bcn->epoch_sec >> 8) & 0xFFU);
    out_buf[5] = (uint8_t)(bcn->epoch_sec & 0xFFU);

    out_buf[6] = (uint8_t)((bcn->sf_seq >> 24) & 0xFFU);
    out_buf[7] = (uint8_t)((bcn->sf_seq >> 16) & 0xFFU);
    out_buf[8] = (uint8_t)((bcn->sf_seq >> 8) & 0xFFU);
    out_buf[9] = (uint8_t)(bcn->sf_seq & 0xFFU);

    out_buf[10] = bcn->sched_ver;
    out_buf[11] = bcn->flags;
    out_buf[12] = bcn->key_id;

    out_buf[13] = 0U;
    out_buf[14] = 0U;
    out_buf[15] = 0U;

    (void)memcpy(&out_buf[16], bcn->hmac_tag, 16);

    if (out_written != NULL) {
        *out_written = 32U;
    }

    return ESP_OK;
}

esp_err_t lora_mac_v2_beacon_deserialize(const uint8_t *buf,
                                         size_t len,
                                         lora_mac_v2_beacon_t *out_bcn)
{
    if (buf == NULL || out_bcn == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < 32U) {
        return ESP_ERR_INVALID_SIZE;
    }

    if (buf[0] != LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON) {
        ESP_LOGD(TAG, "Beacon magic mismatch: 0x%02X (expected 0x%02X)", buf[0], LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON);
        return ESP_ERR_INVALID_VERSION;
    }

    out_bcn->magic = buf[0];
    out_bcn->gw_id = buf[1];

    out_bcn->epoch_sec = ((uint32_t)buf[2] << 24) |
                         ((uint32_t)buf[3] << 16) |
                         ((uint32_t)buf[4] << 8) |
                         (uint32_t)buf[5];

    out_bcn->sf_seq = ((uint32_t)buf[6] << 24) |
                      ((uint32_t)buf[7] << 16) |
                      ((uint32_t)buf[8] << 8) |
                      (uint32_t)buf[9];

    out_bcn->sched_ver = buf[10];
    out_bcn->flags = buf[11];
    out_bcn->key_id = buf[12];

    out_bcn->reserved[0] = buf[13];
    out_bcn->reserved[1] = buf[14];
    out_bcn->reserved[2] = buf[15];

    (void)memcpy(out_bcn->hmac_tag, &buf[16], 16);

    return ESP_OK;
}

/* =========================================================================
 * V1 CANDIDATE CODECS (HISTORICAL PROVENANCE ONLY — SUPERSEDED)
 * ========================================================================= */

esp_err_t lora_mac_header_parse(const uint8_t *raw_buf, size_t len, lora_mac_header_t *out_hdr)
{
    if (raw_buf == NULL || out_hdr == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len < LORA_MAC_HEADER_LEN) {
        return ESP_ERR_INVALID_SIZE;
    }

    if (raw_buf[0] != LORA_MAC_MAGIC_BYTE) {
        ESP_LOGD(TAG, "Magic mismatch: 0x%02X (expected 0x%02X)", raw_buf[0], LORA_MAC_MAGIC_BYTE);
        return ESP_ERR_INVALID_VERSION;
    }

    uint8_t ver_type = raw_buf[1];
    uint8_t version = (uint8_t)((ver_type >> 6) & 0x03U);
    uint8_t msg_type = (uint8_t)(ver_type & 0x3FU);

    if (version != LORA_MAC_PROTOCOL_VERSION_DRAFT && version != 0x00U) {
        ESP_LOGD(TAG, "Unsupported MAC protocol version: %u", version);
        return ESP_ERR_INVALID_VERSION;
    }

    out_hdr->magic = raw_buf[0];
    out_hdr->version = version;
    out_hdr->msg_type = msg_type;
    out_hdr->flags = raw_buf[2];
    out_hdr->src_id = raw_buf[3];
    out_hdr->dst_id = raw_buf[4];
    out_hdr->sched_ver = raw_buf[5];
    out_hdr->seq_num = raw_buf[6];
    out_hdr->payload_len = raw_buf[7];

    if (out_hdr->payload_len > LORA_MAC_MAX_PAYLOAD_LEN) {
        ESP_LOGD(TAG, "Payload length %u exceeds maximum candidate limit %u",
                 out_hdr->payload_len, LORA_MAC_MAX_PAYLOAD_LEN);
        return ESP_ERR_INVALID_SIZE;
    }

    return ESP_OK;
}

esp_err_t lora_mac_header_encode(const lora_mac_header_t *hdr,
                                 uint8_t *out_buf,
                                 size_t buf_size,
                                 size_t *out_written)
{
    if (hdr == NULL || out_buf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (buf_size < LORA_MAC_HEADER_LEN) {
        return ESP_ERR_NO_MEM;
    }
    if (hdr->payload_len > LORA_MAC_MAX_PAYLOAD_LEN) {
        return ESP_ERR_INVALID_SIZE;
    }

    out_buf[0] = LORA_MAC_MAGIC_BYTE;
    out_buf[1] = (uint8_t)(((hdr->version & 0x03U) << 6) | (hdr->msg_type & 0x3FU));
    out_buf[2] = hdr->flags;
    out_buf[3] = hdr->src_id;
    out_buf[4] = hdr->dst_id;
    out_buf[5] = hdr->sched_ver;
    out_buf[6] = hdr->seq_num;
    out_buf[7] = hdr->payload_len;

    if (out_written != NULL) {
        *out_written = LORA_MAC_HEADER_LEN;
    }

    return ESP_OK;
}
