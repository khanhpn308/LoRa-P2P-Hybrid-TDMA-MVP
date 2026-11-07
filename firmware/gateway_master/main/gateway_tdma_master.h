#pragma once

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "esp_err.h"
#include "lora_mac.h"
#include "gateway_wal.h"
#include "gateway_crypto.h"
#include "airtime_policy.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file gateway_tdma_master.h
 * @brief Gateway Master TDMA Engine Coordinator for Hybrid TDMA MVP V2.
 *
 * Authority: DEC-127-01, DEC-127-02, DEC-127-03, DEC-127-05, DEC-127-06,
 *            DEC-MH-01, DEC-MH-02, DEC-MH-03, DEC-MH-06, DEC-MH-07, DEC-MH-08,
 *            ADR-0003, C Coding Standard v2.
 */

#define GW_TDMA_MAX_DATA_SLOTS          (15U)     /**< Dedicated DATA slots (#1..#15) */
#define GW_TDMA_DEFAULT_W_MS            (500U)    /**< 500ms usable Event+ACK window (DEC-127-03) */
#define GW_TDMA_DEFAULT_GUARD_MS        (50U)     /**< 50ms guard on each side (DEC-127-03) */
#define GW_TDMA_DEFAULT_SLOT_DURATION_MS (600U)   /**< 600ms full slot duration (DEC-127-06) */
#define GW_TDMA_DEFAULT_BEACON_WINDOW_MS (250U)   /**< Slot 0 nominal Beacon broadcast window */
#define GW_TDMA_DEFAULT_TURNAROUND_MS   (20U)     /**< SX1276 half-duplex turnaround guard (DEC-MH-06) */
#define GW_TDMA_DEFAULT_SUPERFRAME_MS   (10000U)  /**< 10-second superframe epoch */
#define GW_TDMA_DEFAULT_MAINT_SF_INTERVAL (30U)   /**< Maintenance superframe every 30 SF (~300s, DEC-MH-03) */
#define GW_TDMA_DEFAULT_TOA_BEACON_MS   (60U)     /**< Estimated Beacon 32B Time-on-Air */
#define GW_TDMA_DEFAULT_TOA_ACK_MS      (50U)     /**< Estimated DOWN_EVENT_ACK 19B Time-on-Air */

/**
 * @brief Master TDMA Engine State Machine States
 */
typedef enum {
    GW_TDMA_STATE_IDLE = 0,
    GW_TDMA_STATE_BEACON_TX,
    GW_TDMA_STATE_BEACON_GUARD,
    GW_TDMA_STATE_SLOT_RX,
    GW_TDMA_STATE_SLOT_PROCESS,
    GW_TDMA_STATE_SLOT_ACK_TX,
    GW_TDMA_STATE_SUPERFRAME_COMPLETE,
} gateway_tdma_state_t;

/**
 * @brief Hardware and Timing Abstraction Layer for Gateway TDMA Master
 */
typedef struct {
    esp_err_t (*radio_tx)(const uint8_t *payload, uint8_t length, uint32_t timeout_ms);
    esp_err_t (*radio_rx_start)(void);
    esp_err_t (*radio_rx_stop)(void);
    esp_err_t (*radio_read_frame)(uint8_t *out_buf, size_t *out_len, int16_t *out_rssi, int8_t *out_snr, uint32_t timeout_ms);
    esp_err_t (*radio_standby)(void);
    esp_err_t (*radio_sleep)(void);
    uint32_t (*get_time_ms)(void);
    void (*delay_ms)(uint32_t ms);
} gateway_tdma_radio_hal_t;

/**
 * @brief Node session key configuration entry
 */
typedef struct {
    bool    is_active;
    uint8_t session_sel;
    uint8_t k_session_up[16];
    uint8_t k_session_dl[16];
    uint8_t session_nonce_prefix[8];
} gateway_node_key_entry_t;

/**
 * @brief Session key lookup callback type
 */
typedef esp_err_t (*gateway_tdma_key_lookup_fn)(uint8_t node_id,
                                                uint8_t *out_session_sel,
                                                uint8_t out_k_session_up[16],
                                                uint8_t out_k_session_dl[16],
                                                uint8_t out_nonce_prefix[8]);

/**
 * @brief Gateway TDMA Master Engine Configuration
 */
typedef struct {
    uint8_t  gw_id;                                  /**< Gateway ID (1..254) */
    uint8_t  sched_ver;                              /**< Current active schedule version */
    uint8_t  beacon_key_id;                          /**< K_BEACON key identifier */
    uint8_t  k_beacon[32];                           /**< 256-bit provisioned Beacon HMAC key */
    uint8_t  slot_count;                             /**< Total DATA slots (default: 15) */
    uint32_t slot_duration_ms;                       /**< Full slot duration (default: 600ms) */
    uint32_t slot_guard_ms;                          /**< Guard time each side (default: 50ms) */
    uint32_t slot_usable_ms;                         /**< Usable window (default: 500ms) */
    uint32_t beacon_window_ms;                       /**< Beacon window (default: 250ms) */
    uint32_t turnaround_guard_ms;                    /**< Half-duplex turnaround guard (default: 20ms) */
    uint32_t maintenance_interval_sf;               /**< Maintenance recurrence (default: 30 SFs) */
    uint32_t packet_toa_beacon_ms;                   /**< ToA budget for Beacon */
    uint32_t packet_toa_ack_ms;                      /**< ToA budget for ACK */
    gateway_node_key_entry_t static_keys[GW_TDMA_MAX_DATA_SLOTS + 1U]; /**< Node keys 1..15 */
    gateway_tdma_key_lookup_fn key_lookup_fn;        /**< Dynamic key lookup callback (optional) */
} gateway_tdma_config_t;

/**
 * @brief Gateway TDMA Master Engine State Context
 */
typedef struct {
    gateway_tdma_state_t state;
    uint32_t superframe_seq;
    uint32_t downlink_frame_counter;
    uint8_t  current_slot;
    bool     is_maintenance;
    uint32_t superframe_epoch_ms;

    /* Metrics & Diagnostics */
    uint32_t beacon_tx_count;
    uint32_t beacon_blocked_count;
    uint32_t up_event_received_count;
    uint32_t ack_sent_count;
    uint32_t airtime_blocked_ack_count;
    uint32_t slot_idle_count;
    uint32_t corrupted_packet_count;
    uint32_t corrupted_mic_count;
    uint32_t maintenance_health_count;
    uint32_t maintenance_diag_count;

    /* Anti-replay & diagnostic tracking per Node (1..15) */
    uint32_t node_last_frame_counter[GW_TDMA_MAX_DATA_SLOTS + 1U];
    uint32_t node_last_diag_seq[GW_TDMA_MAX_DATA_SLOTS + 1U];
    uint32_t node_last_dropped_event_count[GW_TDMA_MAX_DATA_SLOTS + 1U];

    /* In-memory Uplink WAL */
    gateway_wal_t wal;

    /* HAL & Config References */
    gateway_tdma_config_t cfg;
    gateway_tdma_radio_hal_t hal;
} gateway_tdma_engine_t;

/**
 * @brief Populate default Gateway configuration matching V2 specifications.
 */
esp_err_t gateway_tdma_get_default_config(gateway_tdma_config_t *out_cfg);

/**
 * @brief Initialize Gateway TDMA Master Engine.
 *
 * @param engine Pointer to engine state instance.
 * @param cfg Pointer to validated configuration.
 * @param hal Pointer to radio and time HAL callbacks.
 * @return ESP_OK on success, or ESP_ERR_INVALID_ARG on NULL.
 */
esp_err_t gateway_tdma_init(gateway_tdma_engine_t *engine,
                            const gateway_tdma_config_t *cfg,
                            const gateway_tdma_radio_hal_t *hal);

/**
 * @brief Run a complete deterministic TDMA superframe cycle:
 *   1. Superframe epoch trigger
 *   2. Slot 0 Beacon broadcast (HMAC-SHA256-128, airtime check, half-duplex turnaround guard)
 *   3. Slots 1..15 Static DATA reception & immediate in-slot ACK loop (or Maintenance evaluation)
 *   4. Bounded WAL commit on verified UP_EVENT
 *   5. Slot idle advancement with zero stray TX on timeout
 *   6. Superframe completion and metric recording.
 *
 * @param engine Pointer to initialized engine instance.
 * @return ESP_OK if superframe cycle completed cleanly.
 */
esp_err_t gateway_tdma_run_superframe(gateway_tdma_engine_t *engine);

/**
 * @brief Convert state enum to human-readable string for logging.
 */
const char *gateway_tdma_state_to_str(gateway_tdma_state_t state);

#ifdef __cplusplus
}
#endif
