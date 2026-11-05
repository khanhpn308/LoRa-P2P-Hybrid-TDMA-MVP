/**
 * @file timing_harness_types.h
 * @brief Common types, event definitions, and hardware pinout for ESP32/SX1276 timing harness.
 *
 * Governed by C Coding Standard v2, ADR-0003, and PCB HW-001 pin mapping.
 * Test-only instrumentation for Issue #11 / handoff to #169.
 */

#ifndef TIMING_HARNESS_TYPES_H
#define TIMING_HARNESS_TYPES_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define TIMING_HARNESS_VERSION_MAJOR 1
#define TIMING_HARNESS_VERSION_MINOR 0
#define TIMING_HARNESS_VERSION_PATCH 0

/**
 * @brief Authoritative PCB HW-001 Pinout.
 * Note: Only DIO0 is physically connected to GPIO26. DIO1..DIO5 are NOT connected.
 */
#define HW001_PIN_SCK   5
#define HW001_PIN_MISO  19
#define HW001_PIN_MOSI  27
#define HW001_PIN_NSS   18
#define HW001_PIN_RST   23
#define HW001_PIN_DIO0  26

#define HW001_DIO1_CONNECTED 0
#define HW001_DIO2_CONNECTED 0
#define HW001_DIO3_CONNECTED 0
#define HW001_DIO4_CONNECTED 0
#define HW001_DIO5_CONNECTED 0

/**
 * @brief Device roles in TDMA network.
 */
typedef enum {
    TIMING_ROLE_UNSPECIFIED = 0,
    TIMING_ROLE_NODE        = 1,
    TIMING_ROLE_GATEWAY     = 2,
} timing_device_role_t;

/**
 * @brief Structured event codes latched during timing harness execution.
 */
typedef enum {
    TIMING_EVT_NONE             = 0x00,
    TIMING_EVT_INIT             = 0x01, /**< Harness & radio initialized */
    TIMING_EVT_TX_CMD           = 0x02, /**< Software scheduled / requested TX */
    TIMING_EVT_TX_START         = 0x03, /**< Radio TX command dispatched to SPI */
    TIMING_EVT_DIO0_IRQ         = 0x04, /**< DIO0 edge detected in ISR (TxDone/RxDone) */
    TIMING_EVT_TX_DONE          = 0x05, /**< Task finished handling TxDone */
    TIMING_EVT_RX_CMD           = 0x06, /**< Radio transitioned to RX mode (RxSingle/RxCont) */
    TIMING_EVT_RX_DONE          = 0x07, /**< Valid packet received and read */
    TIMING_EVT_RX_TIMEOUT       = 0x08, /**< RX window timed out without packet */
    TIMING_EVT_CAD_DONE         = 0x09, /**< Channel Activity Detection completed */
    TIMING_EVT_CLOCK_SYNC       = 0x0A, /**< Clock synchronization / Beacon reference event */
    TIMING_EVT_OVERFLOW         = 0x0B, /**< Internal ring buffer dropped samples */
    TIMING_EVT_ERROR            = 0x0C, /**< Runtime error or unexpected state */
} timing_event_type_t;

/**
 * @brief Evidence classification conforming to project data integrity policy.
 */
typedef enum {
    EVIDENCE_CALCULATED_TOA      = 0, /**< Mathematical model calculation */
    EVIDENCE_HOST_SYNTHETIC      = 1, /**< Generated synthetic fixture for unit test */
    EVIDENCE_SOFTWARE_TIMESTAMP  = 2, /**< ESP32 monotonic microsecond software latch */
    EVIDENCE_HARDWARE_CAPTURE    = 3, /**< Board-level logic analyzer / GPIO capture */
    EVIDENCE_EXTERNAL_RF_MEASURED= 4, /**< Calibrated bench oscilloscope / RF analyzer (#169) */
} timing_evidence_class_t;

/**
 * @brief Compact, fixed-size event record logged to bounded ring buffer.
 * Total size: 32 bytes (power-of-2 aligned, cache friendly, zero malloc).
 */
typedef struct {
    uint32_t seq;               /**< Monotonic sequence number */
    int64_t  timestamp_us;      /**< esp_timer_get_time() microsecond counter */
    uint8_t  event_type;        /**< timing_event_type_t */
    uint8_t  role;              /**< timing_device_role_t */
    uint8_t  payload_len;       /**< Packet payload length in bytes (0..255) */
    uint8_t  channel_idx;       /**< Operating channel index (0..10) */
    uint8_t  evidence_class;    /**< timing_evidence_class_t */
    uint8_t  reserved1;
    uint16_t status_code;       /**< ESP error code or custom status */
    uint32_t extra_info;        /**< Optional metric: latency_us, rssi/snr, drop count */
    uint32_t flags;             /**< Bitflags: 0x01=RF_TX_BLOCKED, 0x02=CRC_ERR */
} timing_event_record_t;

/**
 * @brief Aggregated diagnostics for harness run.
 */
typedef struct {
    uint32_t events_recorded;
    uint32_t events_dropped;
    uint32_t irq_count;
    uint32_t tx_cmd_count;
    uint32_t rx_cmd_count;
    uint32_t timeout_count;
    uint32_t crc_error_count;
    uint32_t fail_closed_tx_blocks;
} timing_diagnostics_t;

#ifdef __cplusplus
}
#endif

#endif /* TIMING_HARNESS_TYPES_H */
