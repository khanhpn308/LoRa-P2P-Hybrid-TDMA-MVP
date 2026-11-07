#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file tdma_common.h
 * @brief Shared TDMA Timing & Slot Layout Definitions (Profile P-10S-15 Baseline).
 *
 * Reference: contracts/radio-mac/tdma-schedule.md.
 * Authority: ADR-0003, C Coding Standard v2, Issue #10 / #14.
 *
 * NOTE: Timings are a baseline for mock/simulator bring-up (Gate G1/G2/G3: NOT_VERIFIED).
 * The driver does not execute schedule state machines or time individual slots.
 */

#define TDMA_SUPERFRAME_MS              (10000U)  /**< 10-second superframe */
#define TDMA_SUBFRAME_COUNT             (5U)      /**< 5 subframes per superframe */
#define TDMA_SUBFRAME_MS                (2000U)   /**< 2000 ms per subframe */
#define TDMA_DATA_SLOTS_PER_SUBFRAME    (3U)      /**< 3 dedicated DATA slots per subframe */
#define TDMA_TOTAL_DATA_SLOTS           (15U)     /**< 15 total dedicated DATA slots (#1..#15) */
#define TDMA_SLOT_DURATION_MS           (400U)    /**< 400 ms slot duration */

/* Subframe Timing Windows (ms from subframe start) */
#define TDMA_BCN_DL_WINDOW_START_MS     (0U)
#define TDMA_BCN_DL_WINDOW_END_MS       (250U)    /**< 0..250ms: Beacon (SF0) or Downlink (SF1..4) */

#define TDMA_PCSS_WINDOW_START_MS       (250U)
#define TDMA_PCSS_WINDOW_END_MS         (650U)    /**< 250..650ms: Priority Contention Slot (PCSS) */

#define TDMA_DATA_SECTION_START_MS      (650U)    /**< 650..1850ms: 3 x 400ms DATA slots */

/* Intra-Slot Partitioning (400 ms total) */
#define TDMA_SLOT_LEADING_GUARD_MS      (25U)     /**< 0..25ms: Leading guard */
#define TDMA_SLOT_TX_BUDGET_MS          (100U)    /**< 25..125ms: Node transmission window */
#define TDMA_SLOT_TURNAROUND_MS         (20U)     /**< 125..145ms: Radio turnaround / RX setup */
#define TDMA_SLOT_ACK_BUDGET_MS         (100U)    /**< 145..245ms: Gateway ACK window */
#define TDMA_SLOT_TRAILING_GUARD_MS     (155U)    /**< 245..400ms: Trailing guard & margin */

/**
 * @brief TDMA Slot Types
 */
typedef enum {
    TDMA_SLOT_TYPE_BEACON      = 0,
    TDMA_SLOT_TYPE_DOWNLINK    = 1,
    TDMA_SLOT_TYPE_PCSS        = 2,
    TDMA_SLOT_TYPE_DATA        = 3,
    TDMA_SLOT_TYPE_JOIN        = 4,
    TDMA_SLOT_TYPE_IDLE        = 5,
} tdma_slot_type_t;

/**
 * @brief Initialize the shared tdma_common component.
 *
 * @return ESP_OK on success.
 */
esp_err_t tdma_common_init(void);

/**
 * @brief Verify if slot index is within the valid data slot range (#1..#15).
 *
 * @param slot_id Slot index to check (1-based).
 * @return true if 1 <= slot_id <= 15, false otherwise.
 */
bool tdma_is_valid_slot_id(uint8_t slot_id);

/**
 * @brief Calculate the start offset in milliseconds within the 10-second superframe.
 *
 * Formula: subframe_idx = (slot_id - 1) / 3; slot_in_subframe = (slot_id - 1) % 3;
 *          offset = 2000 * subframe_idx + 650 + 400 * slot_in_subframe.
 *
 * @param slot_id Slot index (1..15).
 * @param[out] out_offset_ms Pointer to store offset in milliseconds.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if slot_id invalid or out_offset_ms NULL.
 */
esp_err_t tdma_get_slot_start_offset_ms(uint8_t slot_id, uint32_t *out_offset_ms);

/**
 * @brief Compute dynamic clock drift guard in milliseconds.
 *
 * @param clock_drift_ppm Crystal oscillator drift in PPM (e.g. 20 for ±20ppm).
 * @param interval_s      Time elapsed since last beacon sync in seconds.
 * @return Guard time in milliseconds (drift * 2 for bilateral + baseline margin).
 */
uint32_t tdma_calculate_drift_guard_ms(uint32_t clock_drift_ppm, uint32_t interval_s);

/* =========================================================================
 * V2 STATIC TDMA DEFINITIONS (DEC-127-03, DEC-127-06, DEC-MH-03)
 * ========================================================================= */
#define TDMA_V2_DATA_SLOTS_COUNT        (15U)     /**< 15 dedicated static DATA slots (#1..#15) */
#define TDMA_V2_SLOT_USABLE_MS          (500U)    /**< W_MS = 500ms usable window per DEC-127-03 */
#define TDMA_V2_SLOT_GUARD_MS           (50U)     /**< G_MS = 50ms guard on each side per DEC-127-03 */
#define TDMA_V2_SLOT_DURATION_MS        (600U)    /**< 500ms + 2*50ms = 600ms full slot duration */
#define TDMA_V2_BEACON_WINDOW_MS        (250U)    /**< Slot 0 nominal Beacon Window */
#define TDMA_V2_SUPERFRAME_MS           (10000U)  /**< 10-second superframe */
#define TDMA_V2_MAINTENANCE_CADENCE_MS  (300000U) /**< ~300s Maintenance cadence per DEC-MH-03 */

/**
 * @brief Calculate V2 Static TDMA slot timing offsets within a superframe.
 *
 * @param slot_id Slot index (1..15).
 * @param[out] out_slot_start_ms Slot start offset (slot_id * 600ms).
 * @param[out] out_usable_start_ms Usable window start (slot_start + 50ms).
 * @param[out] out_usable_end_ms Usable window end (usable_start + 500ms).
 * @param[out] out_slot_end_ms Slot trailing boundary (slot_start + 600ms).
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG if slot_id is invalid or pointers NULL.
 */
esp_err_t tdma_v2_get_slot_timing(uint8_t slot_id,
                                  uint32_t *out_slot_start_ms,
                                  uint32_t *out_usable_start_ms,
                                  uint32_t *out_usable_end_ms,
                                  uint32_t *out_slot_end_ms);

#ifdef __cplusplus
}
#endif
