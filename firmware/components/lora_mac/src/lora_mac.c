#include "lora_mac.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "lora_mac";

esp_err_t lora_mac_init(void)
{
    ESP_LOGI(TAG, "Initialized shared lora_mac component (candidate draft v0.1.0)");
    return ESP_OK;
}

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
