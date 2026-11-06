#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file lora_mac.h
 * @brief Custom LoRa P2P Radio MAC Framing Definitions & Candidate Envelope.
 *
 * Reference: contracts/radio-mac/specification.md (Revision 0.1.0-draft).
 * Authority: ADR-0003, C Coding Standard v2, Issue #10 / #12.
 *
 * NOTE: Security, authentication, and wire layout are DRAFT (Gate G2: NOT_VERIFIED).
 * Per Open Decisions D01 and D11, CRC16/PHY CRC only detect accidental bit flips.
 * Do not publish or use as frozen production codec until crypto review completes.
 */

#define LORA_MAC_MAGIC_BYTE            (0xA5U)
#define LORA_MAC_PROTOCOL_VERSION_DRAFT (0x01U)
#define LORA_MAC_MAX_PAYLOAD_LEN       (48U)
#define LORA_MAC_HEADER_LEN            (8U)

/**
 * @brief Candidate Message Types from contracts/radio-mac/specification.md
 */
typedef enum {
    LORA_MAC_TYPE_BEACON           = 0x01,  /**< GW -> Broadcast: Superframe sync & ACK bitmap */
    LORA_MAC_TYPE_SCHED_ANNOUNCE   = 0x02,  /**< GW -> Broadcast/Node: Slot allocation update */
    LORA_MAC_TYPE_DATA_TELEMETRY   = 0x03,  /**< Node -> GW: Periodic sensor payload */
    LORA_MAC_TYPE_PRIORITY_ALERT   = 0x04,  /**< Node -> GW: High-priority alarm event */
    LORA_MAC_TYPE_ACK_PACKET       = 0x05,  /**< GW -> Node: Frame acknowledgment */
    LORA_MAC_TYPE_CMD_DOWNLINK     = 0x06,  /**< GW -> Node: Downlink command from backend */
    LORA_MAC_TYPE_JOIN_SLOT_REQ    = 0x07,  /**< Node -> GW: Initial dynamic join request */
    LORA_MAC_TYPE_JOIN_SLOT_RSP    = 0x08,  /**< GW -> Node: Dynamic join response */
} lora_mac_msg_type_t;

/**
 * @brief Candidate Control Flag bitmasks (byte 2)
 */
#define LORA_MAC_FLAG_ACK_REQ          (1U << 5)  /**< Immediate acknowledgment requested */
#define LORA_MAC_FLAG_IS_RETRY         (1U << 4)  /**< Frame retransmission indicator */
#define LORA_MAC_FLAG_PENDING_SCHED    (1U << 3)  /**< Schedule update announcement pending */
#define LORA_MAC_FLAG_DUTY_LIMITED     (1U << 2)  /**< Node approaching local duty cycle limit */

/**
 * @brief Parsed Candidate MAC Header Representation (unpacked)
 */
typedef struct {
    uint8_t magic;          /**< Fixed sync/magic byte (0xA5) */
    uint8_t version;        /**< Protocol version (candidate 0x01) */
    uint8_t msg_type;       /**< Message type identifier (lora_mac_msg_type_t) */
    uint8_t flags;          /**< Control flags bitmask */
    uint8_t src_id;         /**< Source address (0x00=GW, 1..254=Node) */
    uint8_t dst_id;         /**< Destination address (0x00=GW, 1..254=Node, 0xFF=Broadcast) */
    uint8_t sched_ver;      /**< Schedule version tag */
    uint8_t seq_num;        /**< Sequence number (frame sequence, not crypto nonce) */
    uint8_t payload_len;    /**< Length of payload section (0..48 bytes) */
} lora_mac_header_t;

/**
 * @brief Initialize the shared lora_mac component.
 *
 * @return ESP_OK on success.
 */
esp_err_t lora_mac_init(void);

/**
 * @brief Parse candidate 8-byte MAC header from raw wire buffer.
 *
 * @param[in]  raw_buf  Pointer to received byte buffer.
 * @param[in]  len      Length of available received bytes (must be >= LORA_MAC_HEADER_LEN).
 * @param[out] out_hdr  Pointer to header struct to populate.
 * @return ESP_OK on valid header, ESP_ERR_INVALID_ARG on NULL/bounds, ESP_ERR_INVALID_VERSION
 *         on magic or unsupported version.
 */
esp_err_t lora_mac_header_parse(const uint8_t *raw_buf, size_t len, lora_mac_header_t *out_hdr);

/**
 * @brief Serialize candidate MAC header into target wire buffer.
 *
 * @param[in]  hdr          Pointer to header struct to encode.
 * @param[out] out_buf      Pointer to destination byte buffer.
 * @param[in]  buf_size     Available capacity in destination buffer.
 * @param[out] out_written  Number of bytes written (always 8 on success).
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG or ESP_ERR_NO_MEM if buffer too small.
 */
esp_err_t lora_mac_header_encode(const lora_mac_header_t *hdr,
                                 uint8_t *out_buf,
                                 size_t buf_size,
                                 size_t *out_written);

#ifdef __cplusplus
}
#endif
