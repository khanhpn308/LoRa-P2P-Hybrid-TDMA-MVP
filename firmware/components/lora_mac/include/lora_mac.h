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
 * @brief Custom LoRa P2P Radio MAC Framing Definitions & Codecs.
 *
 * Reference: contracts/radio-mac/specification.md (Revision 0.3.0-draft).
 * Authority: ADR-0003, C Coding Standard v2, Issue #127, Issue #131.
 * Owner-Approved Decisions: DEC-127-01, DEC-127-02, DEC-MH-01, DEC-MH-02, DEC-MH-08, DEC-SEC-01..07.
 *
 * NOTE: Security, authentication, and wire layout adhere to V2 Owner MVP Baseline.
 * Unicast Header: 7 octets (AAD).
 * AEAD: AES-128-CCM with 8-byte tag (CCM-8, M=8) and 13-byte nonce (L=2).
 */

/* =========================================================================
 * V2 SECURE MAC PROTOCOL (Normative Specification per contracts/radio-mac)
 * ========================================================================= */

#define LORA_MAC_V2_PROTOCOL_VERSION        (2U)      /**< 3-bit version: 010b = 2 */
#define LORA_MAC_V2_HEADER_LEN             (7U)      /**< 7 octets unencrypted AAD */
#define LORA_MAC_V2_CCM_TAG_LEN            (8U)      /**< AES-128-CCM tag: 8 octets (M=8, DEC-127-02) */
#define LORA_MAC_V2_CCM_NONCE_LEN          (13U)     /**< AES-128-CCM nonce: 13 octets (L=2) */
#define LORA_MAC_V2_MAX_PAYLOAD_LEN        (48U)     /**< Maximum payload length */

/**
 * @brief V2 Message Type Identifiers (Table 3.2, contracts/radio-mac/specification.md)
 */
typedef enum {
    LORA_MAC_V2_TYPE_UP_EVENT          = 0x41,  /**< Node -> GW: Alarm event violation (26B total) */
    LORA_MAC_V2_TYPE_DOWN_EVENT_ACK    = 0x42,  /**< GW -> Node: Immediate event acknowledgment (19B total) */
    LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON  = 0x43,  /**< GW -> Bcast: Maintenance superframe sync (32B total, HMAC) */
    LORA_MAC_V2_TYPE_UP_HEALTH_REPLY   = 0x44,  /**< Node -> GW: Scheduled health telemetry (21B total) */
    LORA_MAC_V2_TYPE_UP_JOIN_HELLO     = 0x45,  /**< Node -> GW: Asynchronous CAD join hello (68B total) */
    LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT   = 0x46,  /**< GW -> Node: Join grant with backend ticket (66B total) */
    LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF  = 0x47,  /**< Node -> GW: Join key confirmation (31B/39B) */
    LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH  = 0x48,  /**< GW -> Node: Join finish (31B/39B) */
    LORA_MAC_V2_TYPE_UP_JOIN_READY     = 0x49,  /**< Node -> GW: Join ready with backend proof (31B/39B) */
    LORA_MAC_V2_TYPE_UP_DIAG_METRICS   = 0x4A,  /**< Node -> GW: Diagnostic loss metrics (23B total, DEC-MH-08) */
    LORA_MAC_V2_TYPE_DOWN_SCHED_PREP   = 0x4B,  /**< GW -> Bcast: Schedule prepare (80B, Backend Ed25519) */
    LORA_MAC_V2_TYPE_UP_SCHED_READY    = 0x4C,  /**< Node -> GW: Migration ready per node (41B total) */
    LORA_MAC_V2_TYPE_DOWN_SCHED_DEC    = 0x4D,  /**< GW -> Bcast: Schedule decision commit/abort (80B) */
} lora_mac_v2_msg_type_t;

/**
 * @brief Direction byte in CCM Nonce construction (contracts/radio-mac/specification.md Section 4)
 */
#define LORA_MAC_V2_DIR_UPLINK             (0x01U)   /**< Node -> Gateway (0x01 per Section 4 item 4) */
#define LORA_MAC_V2_DIR_DOWNLINK           (0x02U)   /**< Gateway -> Node (0x02 per Section 4 item 4) */

/**
 * @brief Total wire frame lengths for V2 fixed-size messages
 */
#define LORA_MAC_V2_LEN_UP_EVENT           (26U)     /**< 7B header + 11B cipher + 8B tag */
#define LORA_MAC_V2_LEN_DOWN_EVENT_ACK     (19U)     /**< 7B header + 4B cipher + 8B tag */
#define LORA_MAC_V2_LEN_DOWN_SYNC_BEACON   (32U)     /**< 16B header + 16B HMAC tag */
#define LORA_MAC_V2_LEN_UP_HEALTH_REPLY    (21U)     /**< 7B header + 6B cipher + 8B tag */
#define LORA_MAC_V2_LEN_UP_DIAG_METRICS    (23U)     /**< 7B header + 8B cipher + 8B tag */

/**
 * @brief V2 Unicast Header (7 octets, unencrypted AAD)
 */
typedef struct {
    uint8_t ver_type;        /**< 3-bit version (010b = 2) | 5-bit msg_type (0x01..0x1F) -> 0x40..0x5F */
    uint8_t node_id;         /**< 1..254 (0x01..0xFE) */
    uint8_t session_sel;     /**< Session key index (0 or 1) */
    uint32_t frame_counter;  /**< Monotonic 32-bit big-endian frame counter */
} lora_mac_v2_header_t;

/**
 * @brief V2 UP_EVENT Plaintext Payload (11 octets)
 */
typedef struct {
    uint32_t event_ref;      /**< Monotonic local event reference (4B Big-Endian) */
    uint32_t event_time;     /**< Unix epoch timestamp or 0xFFFFFFFF (4B Big-Endian) */
    uint8_t  event_code;     /**< Violation/alarm category code (1B) */
    int16_t  event_value;    /**< Sensor measurement reading at violation (2B Big-Endian) */
} lora_mac_v2_up_event_t;

/**
 * @brief V2 DOWN_EVENT_ACK Plaintext Payload (4 octets)
 */
typedef struct {
    uint32_t event_ref;      /**< Echoed local event reference (4B Big-Endian) */
} lora_mac_v2_down_event_ack_t;

/**
 * @brief V2 UP_HEALTH_REPLY Plaintext Payload (6 octets)
 */
typedef struct {
    uint16_t battery_mv;     /**< Battery voltage in mV (2B Big-Endian) */
    uint32_t uptime_sec;     /**< Node uptime in seconds, 24-bit unsigned (3B Big-Endian) */
    uint8_t  pending_count;  /**< Current count of un-ACKed events in FIFO (1B) */
} lora_mac_v2_up_health_reply_t;

/**
 * @brief V2 UP_DIAG_METRICS Plaintext Payload (8 octets, DEC-MH-08)
 */
typedef struct {
    uint32_t dropped_event_count; /**< Cumulative dropped events due to buffer overflow (4B Big-Endian) */
    uint32_t diag_seq;            /**< Diagnostic sequence number (4B Big-Endian) */
} lora_mac_v2_up_diag_metrics_t;

/**
 * @brief V2 DOWN_SYNC_BEACON Wire Representation (32 octets, DEC-MH-01 / DEC-MH-07)
 */
typedef struct {
    uint8_t  magic;          /**< 0x43 (LORA_MAC_V2_TYPE_DOWN_SYNC_BEACON) */
    uint8_t  gw_id;          /**< Gateway network ID */
    uint32_t epoch_sec;      /**< Unix epoch seconds (4B Big-Endian) */
    uint32_t sf_seq;         /**< Superframe sequence counter (4B Big-Endian) */
    uint8_t  sched_ver;      /**< Current active schedule version tag */
    uint8_t  flags;          /**< Flags (bits 7:6 reserved=0, bit 5 emergency) */
    uint8_t  key_id;         /**< K_BEACON key identifier */
    uint8_t  reserved[3];    /**< Reserved, must be 0 */
    uint8_t  hmac_tag[16];   /**< HMAC-SHA256-128 tag */
} lora_mac_v2_beacon_t;

/* =========================================================================
 * V2 API FUNCTIONS
 * ========================================================================= */

/**
 * @brief Parse V2 7-byte Unicast Header from raw byte buffer.
 *
 * @param[in]  raw_buf  Pointer to buffer.
 * @param[in]  len      Buffer length (must be >= LORA_MAC_V2_HEADER_LEN).
 * @param[out] out_hdr  Pointer to header struct to populate.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on NULL/bounds, ESP_ERR_INVALID_VERSION
 *         if version is not V2 (0x02) or type is out of 0x40..0x5F range.
 */
esp_err_t lora_mac_v2_header_parse(const uint8_t *raw_buf, size_t len, lora_mac_v2_header_t *out_hdr);

/**
 * @brief Serialize V2 7-byte Unicast Header into target buffer.
 *
 * @param[in]  hdr          Pointer to header struct to encode.
 * @param[out] out_buf      Pointer to destination buffer.
 * @param[in]  buf_size     Available capacity in destination buffer.
 * @param[out] out_written  Number of bytes written (always 7 on success).
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG or ESP_ERR_NO_MEM if buffer too small.
 */
esp_err_t lora_mac_v2_header_encode(const lora_mac_v2_header_t *hdr,
                                    uint8_t *out_buf,
                                    size_t buf_size,
                                    size_t *out_written);

/**
 * @brief Build standard 13-byte AES-128-CCM nonce per specification.md Section 4.
 *
 * Nonce = SESSION_NONCE_PREFIX (8B) || DIRECTION (1B) || FRAME_COUNTER (4B BE)
 *
 * @param[in]  prefix         8-byte session nonce prefix.
 * @param[in]  direction      LORA_MAC_V2_DIR_UPLINK (0x01) or LORA_MAC_V2_DIR_DOWNLINK (0x02).
 * @param[in]  frame_counter  32-bit frame counter.
 * @param[out] out_nonce      13-byte destination buffer for nonce.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on NULL pointers or invalid direction.
 */
esp_err_t lora_mac_v2_build_nonce(const uint8_t prefix[8],
                                  uint8_t direction,
                                  uint32_t frame_counter,
                                  uint8_t out_nonce[LORA_MAC_V2_CCM_NONCE_LEN]);

/**
 * @brief Serialize UP_EVENT plaintext payload (11 octets).
 */
esp_err_t lora_mac_v2_up_event_serialize(const lora_mac_v2_up_event_t *event,
                                         uint8_t *out_buf,
                                         size_t buf_size,
                                         size_t *out_written);

/**
 * @brief Deserialize UP_EVENT plaintext payload (11 octets).
 */
esp_err_t lora_mac_v2_up_event_deserialize(const uint8_t *buf,
                                           size_t len,
                                           lora_mac_v2_up_event_t *out_event);

/**
 * @brief Serialize DOWN_EVENT_ACK plaintext payload (4 octets).
 */
esp_err_t lora_mac_v2_down_event_ack_serialize(const lora_mac_v2_down_event_ack_t *ack,
                                               uint8_t *out_buf,
                                               size_t buf_size,
                                               size_t *out_written);

/**
 * @brief Deserialize DOWN_EVENT_ACK plaintext payload (4 octets).
 */
esp_err_t lora_mac_v2_down_event_ack_deserialize(const uint8_t *buf,
                                                 size_t len,
                                                 lora_mac_v2_down_event_ack_t *out_ack);

/**
 * @brief Serialize UP_HEALTH_REPLY plaintext payload (6 octets).
 */
esp_err_t lora_mac_v2_up_health_reply_serialize(const lora_mac_v2_up_health_reply_t *health,
                                                uint8_t *out_buf,
                                                size_t buf_size,
                                                size_t *out_written);

/**
 * @brief Deserialize UP_HEALTH_REPLY plaintext payload (6 octets).
 */
esp_err_t lora_mac_v2_up_health_reply_deserialize(const uint8_t *buf,
                                                  size_t len,
                                                  lora_mac_v2_up_health_reply_t *out_health);

/**
 * @brief Serialize UP_DIAG_METRICS plaintext payload (8 octets, DEC-MH-08).
 */
esp_err_t lora_mac_v2_up_diag_metrics_serialize(const lora_mac_v2_up_diag_metrics_t *diag,
                                                uint8_t *out_buf,
                                                size_t buf_size,
                                                size_t *out_written);

/**
 * @brief Deserialize UP_DIAG_METRICS plaintext payload (8 octets, DEC-MH-08).
 */
esp_err_t lora_mac_v2_up_diag_metrics_deserialize(const uint8_t *buf,
                                                  size_t len,
                                                  lora_mac_v2_up_diag_metrics_t *out_diag);

/**
 * @brief Serialize DOWN_SYNC_BEACON frame (32 octets).
 */
esp_err_t lora_mac_v2_beacon_serialize(const lora_mac_v2_beacon_t *bcn,
                                       uint8_t *out_buf,
                                       size_t buf_size,
                                       size_t *out_written);

/**
 * @brief Deserialize DOWN_SYNC_BEACON frame (32 octets).
 */
esp_err_t lora_mac_v2_beacon_deserialize(const uint8_t *buf,
                                         size_t len,
                                         lora_mac_v2_beacon_t *out_bcn);

/* =========================================================================
 * V1 CANDIDATE DEFINITIONS (HISTORICAL PROVENANCE ONLY — SUPERSEDED)
 * ========================================================================= */

#define LORA_MAC_MAGIC_BYTE            (0xA5U)
#define LORA_MAC_PROTOCOL_VERSION_DRAFT (0x01U)
#define LORA_MAC_MAX_PAYLOAD_LEN       (48U)
#define LORA_MAC_HEADER_LEN            (8U)

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

#define LORA_MAC_FLAG_ACK_REQ          (1U << 5)
#define LORA_MAC_FLAG_IS_RETRY         (1U << 4)
#define LORA_MAC_FLAG_PENDING_SCHED    (1U << 3)
#define LORA_MAC_FLAG_DUTY_LIMITED     (1U << 2)

typedef struct {
    uint8_t magic;
    uint8_t version;
    uint8_t msg_type;
    uint8_t flags;
    uint8_t src_id;
    uint8_t dst_id;
    uint8_t sched_ver;
    uint8_t seq_num;
    uint8_t payload_len;
} lora_mac_header_t;

esp_err_t lora_mac_init(void);

esp_err_t lora_mac_header_parse(const uint8_t *raw_buf, size_t len, lora_mac_header_t *out_hdr);

esp_err_t lora_mac_header_encode(const lora_mac_header_t *hdr,
                                 uint8_t *out_buf,
                                 size_t buf_size,
                                 size_t *out_written);

#ifdef __cplusplus
}
#endif
