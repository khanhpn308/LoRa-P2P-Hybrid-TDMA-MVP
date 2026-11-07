#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "node_event_fifo.h"
#include "lora_mac.h"
#include "node_crypto.h"

#ifdef __cplusplus
extern "C" {
#endif

#define NODE_TDMA_W_MS                     (500U)    /**< Usable Event+ACK window (DEC-127-03) */
#define NODE_TDMA_GUARD_MS                 (50U)     /**< Leading & trailing guard each side */
#define NODE_TDMA_SLOT_PERIOD_MS           (600U)    /**< Full slot duration: 500 + 2*50 */
#define NODE_TDMA_BEACON_WINDOW_MS         (250U)    /**< Nominal beacon broadcast window */
#define NODE_TDMA_ACK_TIMEOUT_MS           (200U)    /**< In-slot ACK reception timeout */
#define NODE_TDMA_NOMINAL_TOA_MS           (60U)     /**< Nominal Time-on-Air for 26B UP_EVENT */
#define NODE_TDMA_MAX_MISSED_BEACONS       (3U)      /**< Consecutive miss threshold before DISCONNECTED */
#define NODE_TDMA_DEFAULT_DRIFT_PPM        (20U)     /**< Crystal oscillator tolerance */
#define NODE_TDMA_MAX_HOLD_DRIFT_MS        (50U)     /**< Holdover drift guard limit */

/**
 * @brief Node TDMA Slot Client State Machine States
 */
typedef enum {
    NODE_TDMA_STATE_IDLE = 0,
    NODE_TDMA_STATE_WAKE_CHECK,
    NODE_TDMA_STATE_FIFO_EVAL,
    NODE_TDMA_STATE_BEACON_SYNC,
    NODE_TDMA_STATE_SLOT_SCHEDULER,
    NODE_TDMA_STATE_AIRTIME_CHECK,
    NODE_TDMA_STATE_EVENT_TX,
    NODE_TDMA_STATE_ACK_RX,
    NODE_TDMA_STATE_ACK_EVAL,
    NODE_TDMA_STATE_REARM_SLEEP,
    NODE_TDMA_STATE_DISCONNECTED,
} node_tdma_state_t;

/**
 * @brief Radio and Timing Abstraction Layer for Node TDMA Client
 */
typedef struct {
    esp_err_t (*radio_tx)(const uint8_t *payload, uint8_t length, uint32_t timeout_ms);
    esp_err_t (*radio_rx_single)(uint32_t timeout_ms);
    esp_err_t (*radio_read_frame)(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms);
    esp_err_t (*radio_sleep)(void);
    esp_err_t (*radio_standby)(void);
    uint32_t (*get_time_ms)(void);
    void (*delay_ms)(uint32_t ms);
} node_tdma_radio_hal_t;

/**
 * @brief Provisioned Configuration Parameters for Node TDMA Slot Client
 */
typedef struct {
    uint8_t node_id;                                /**< 1..15: Node ID == Static DATA slot index */
    uint8_t gw_id;                                  /**< 1..254: Expected Gateway ID */
    uint8_t session_sel;                            /**< 0 or 1: Session key selector */
    uint8_t beacon_key_id;                          /**< Expected K_BEACON key identifier */
    uint8_t k_beacon[32];                           /**< 256-bit provisioned Beacon HMAC key */
    uint8_t k_session_up[16];                       /**< 128-bit Uplink session key */
    uint8_t k_session_down[16];                     /**< 128-bit Downlink session key */
    uint8_t session_nonce_prefix[8];                /**< 8-byte session nonce prefix */
    uint32_t beacon_window_ms;                      /**< Duration of Beacon reception window */
    uint32_t slot_duration_ms;                      /**< 600 ms full slot */
    uint32_t slot_guard_ms;                         /**< 50 ms guard */
    uint32_t ack_timeout_ms;                        /**< Timeout waiting for ACK within slot */
    uint32_t clock_drift_ppm;                       /**< Crystal drift in PPM */
    uint32_t packet_toa_ms;                         /**< Estimated ToA for 26B UP_EVENT */
} node_tdma_client_config_t;

/**
 * @brief Persistent RTC State for Node TDMA Slot Client (Preserved across Deep-Sleep)
 */
typedef struct {
    uint32_t uplink_frame_counter;                  /**< Monotonic 32-bit uplink frame counter */
    uint32_t last_sf_seq;                           /**< Last validated Beacon superframe sequence */
    uint32_t last_beacon_sync_time_ms;              /**< Timestamp of last valid Beacon sync */
    uint32_t n_missed_beacons;                      /**< Consecutive missed Beacon counter */
    node_tdma_state_t state;                        /**< Current or last state machine state */
    bool is_synchronized;                           /**< True if synchronized with Gateway Beacon */
    bool is_disconnected;                           /**< True if n_missed_beacons > 3 */
} node_tdma_client_state_t;

/**
 * @brief Populate default configuration matching project V2 specifications.
 */
esp_err_t node_tdma_client_get_default_config(node_tdma_client_config_t *out_cfg);

/**
 * @brief Initialize persistent TDMA state structure.
 */
esp_err_t node_tdma_client_init(const node_tdma_client_config_t *cfg,
                                node_tdma_client_state_t *state);

/**
 * @brief Calculate assigned static TDMA slot timing boundaries for a given node.
 *
 * Formula:
 *   reserved_start = beacon_arrival + beacon_window + (node_id - 1) * slot_duration
 *   usable_start   = reserved_start + slot_guard
 *   usable_end     = usable_start + (slot_duration - 2 * slot_guard)
 *   reserved_end   = reserved_start + slot_duration
 *
 * @param cfg               Pointer to configuration.
 * @param beacon_arrival_ms Timestamp of beacon arrival.
 * @param[out] out_usable_start Usable slot start timestamp.
 * @param[out] out_usable_end   Usable slot end timestamp.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG on invalid parameters.
 */
esp_err_t node_tdma_compute_slot_boundaries(const node_tdma_client_config_t *cfg,
                                            uint32_t beacon_arrival_ms,
                                            uint32_t *out_usable_start,
                                            uint32_t *out_usable_end);

/**
 * @brief Execute a single TDMA slot client cycle:
 *   Check FIFO -> Beacon Sync -> Slot Boundary Align -> Airtime Check ->
 *   UP_EVENT TX -> ACK RX -> Evaluation (Pop/Retry) -> Sleep Prepare.
 *
 * Adheres strictly to:
 * - MAC-001 (V2 framing & validation)
 * - MAC-002 (Slot boundary adherence, zero out-of-slot RF transmission)
 * - RAD-001 (Airtime check before TX)
 * - RAD-002 (Fail-closed on radio error)
 * - SEC-001 / SEC-004 / SEC-005 (Safe keys, unique nonce, memory zeroization)
 * - MEM-001 / MEM-002 / MEM-005 (Zero heap, bounded buffers, zeroized memory)
 *
 * @param cfg    Node configuration.
 * @param hal    Radio and time HAL callbacks.
 * @param state  Persistent TDMA state.
 * @param fifo   Persistent event FIFO.
 * @return ESP_OK if execution cycle completed (even if transmission was skipped safely).
 */
esp_err_t node_tdma_client_run_cycle(const node_tdma_client_config_t *cfg,
                                     const node_tdma_radio_hal_t *hal,
                                     node_tdma_client_state_t *state,
                                     node_event_fifo_t *fifo);

/**
 * @brief Convert state enum to human-readable string for logging.
 */
const char *node_tdma_state_to_str(node_tdma_state_t state);

#ifdef __cplusplus
}
#endif
