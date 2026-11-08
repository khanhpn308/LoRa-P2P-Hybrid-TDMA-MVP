#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "sdkconfig.h"

#ifdef __cplusplus
extern "C" {
#endif

#ifndef CONFIG_SX1276_HOST_RX_BUFFER_SIZE
#define CONFIG_SX1276_HOST_RX_BUFFER_SIZE 128U
#endif

#ifndef CONFIG_SX1276_RX_BUFFER_POOL_SIZE
#define CONFIG_SX1276_RX_BUFFER_POOL_SIZE 4U
#endif

#define SX1276_VN920_CHANNEL_COUNT 11U

typedef enum {
    SX1276_SF_7  = 7,
    SX1276_SF_8  = 8,
    SX1276_SF_9  = 9,
    SX1276_SF_10 = 10,
    SX1276_SF_11 = 11,
    SX1276_SF_12 = 12,
} sx1276_sf_t;

typedef enum {
    SX1276_BW_125K = 0x07, // 0111b
    SX1276_BW_250K = 0x08, // 1000b
    SX1276_BW_500K = 0x09, // 1001b
} sx1276_bw_t;

typedef enum {
    SX1276_CR_4_5 = 0x01, // 001b
    SX1276_CR_4_6 = 0x02, // 010b
    SX1276_CR_4_7 = 0x03, // 011b
    SX1276_CR_4_8 = 0x04, // 100b
} sx1276_cr_t;

typedef enum {
    SX1276_PA_PATH_UNKNOWN = 0, // Unverified - fail closed
    SX1276_PA_PATH_RFO     = 1, // RFO_HF port
    SX1276_PA_PATH_BOOST   = 2, // PA_BOOST pin
} sx1276_pa_path_t;

typedef enum {
    SX1276_LDRO_AUTO       = 0, // Enable if symbol duration > 16ms
    SX1276_LDRO_FORCE_ON   = 1,
    SX1276_LDRO_FORCE_OFF  = 2,
} sx1276_ldro_mode_t;

typedef enum {
    SX1276_MODE_SLEEP      = 0,
    SX1276_MODE_STANDBY    = 1,
    SX1276_MODE_TX         = 2,
    SX1276_MODE_RXSINGLE   = 3,
    SX1276_MODE_RXCONT     = 4,
    SX1276_MODE_CAD        = 5,
} sx1276_radio_mode_t;

typedef enum {
    SX1276_RX_STATUS_PACKET_DONE             = 0,
    SX1276_RX_STATUS_HW_TIMEOUT              = 1,
    SX1276_RX_STATUS_HOST_WATCHDOG_EXPIRED   = 2,
    SX1276_RX_STATUS_ABORTED_BY_HOST         = 3,
    SX1276_RX_STATUS_ABORTED_BY_RECOVERY     = 4,
    SX1276_RX_STATUS_REJECT_MISSING_CRC      = 5,
    SX1276_RX_STATUS_REJECT_CRC_ERROR        = 6,
    SX1276_RX_STATUS_REJECT_INVALID_LENGTH   = 7,
    SX1276_RX_STATUS_REJECT_BUFFER_OVERFLOW  = 8,
} sx1276_rx_status_t;

typedef struct {
    uint32_t           frequency_hz;
    uint8_t            channel_idx;
    sx1276_sf_t        sf;
    sx1276_bw_t        bw;
    sx1276_cr_t        cr;
    uint16_t           preamble_len;
    uint8_t            sync_word;
    bool               payload_crc_on;
    bool               explicit_header;
    sx1276_ldro_mode_t ldro_mode;
    sx1276_pa_path_t   pa_path;
    int8_t             tx_power_dbm;
    uint16_t           pa_ramp_us;
    bool               ocp_enabled;
    uint8_t            ocp_current_limit_ma;
    bool               agc_auto_on;
    bool               lna_boost_hf;
    uint8_t            lna_gain_manual; // 1-6, only active when agc_auto_on is false
    bool               rf_tx_enabled;   // Safety gate: false by default
} sx1276_phy_config_t;

typedef struct {
    gpio_num_t         pin_sck;
    gpio_num_t         pin_miso;
    gpio_num_t         pin_mosi;
    gpio_num_t         pin_cs;
    gpio_num_t         pin_rst;
    gpio_num_t         pin_dio0;
    spi_host_device_t  spi_host;
    int                spi_clock_speed_hz;
} sx1276_hw_config_t;

typedef struct {
    uint8_t reg_op_mode;
    uint8_t reg_fr_msb;
    uint8_t reg_fr_mid;
    uint8_t reg_fr_lsb;
    uint8_t reg_pa_config;
    uint8_t reg_pa_ramp;
    uint8_t reg_ocp;
    uint8_t reg_lna;
    uint8_t reg_modem_config_1;
    uint8_t reg_modem_config_2;
    uint8_t reg_modem_config_3;
    uint8_t reg_symb_timeout_lsb;
    uint8_t reg_preamble_msb;
    uint8_t reg_preamble_lsb;
    uint8_t reg_sync_word;
    uint8_t reg_detect_optimize;
    uint8_t reg_detection_threshold;
} sx1276_register_plan_t;

typedef struct {
    uint8_t  payload[CONFIG_SX1276_HOST_RX_BUFFER_SIZE];
    uint8_t  length;
    int8_t   snr_db_quarter; // Signed 2's complement from RegPktSnrValue
    int16_t  rssi_dbm;       // Calculated packet RSSI in dBm
    uint8_t  channel_idx;    // Operating channel index (0-10)
    uint32_t timestamp_us;   // ESP32 monotonic microsecond latch at RxDone
} sx1276_rx_frame_t;

typedef struct {
    uint32_t tx_packets_sent;
    uint32_t tx_fail_closed_blocked;
    uint32_t rx_packets_received;
    uint32_t rx_crc_errors;
    uint32_t rx_missing_crc_dropped;
    uint32_t rx_invalid_length_dropped;
    uint32_t rx_host_buffer_overflow_dropped;
    uint32_t rx_hw_timeouts;
    uint32_t rx_host_watchdog_expired;
    uint32_t rx_aborted_by_host;
    uint32_t rx_aborted_by_recovery;
    uint32_t cad_detected_count;
    uint32_t cad_clear_count;
    uint32_t spi_failures;
} sx1276_diagnostics_t;

#ifdef __cplusplus
}
#endif
