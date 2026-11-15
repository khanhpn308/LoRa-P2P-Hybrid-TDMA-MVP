#include "sx1276_owner.h"
#include "sx1276_driver.h"
#include "sx1276_hal.h"
#include "sx1276_config.h"
#include "esp_timer.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "sx1276_owner";

#define SX1276_CMD_QUEUE_LEN 8U

static TaskHandle_t         s_owner_task = NULL;
static QueueHandle_t        s_cmd_queue = NULL;
static QueueHandle_t        s_rx_frame_queue = NULL;

static sx1276_phy_config_t  s_phy_conf;
static sx1276_register_plan_t s_reg_plan;
static sx1276_diagnostics_t s_diag;
static sx1276_radio_mode_t  s_current_mode = SX1276_MODE_STANDBY;

// Static preallocated frame descriptor pool (zero dynamic allocation in steady state)
static sx1276_rx_frame_t    s_frame_pool[CONFIG_SX1276_RX_BUFFER_POOL_SIZE];
static uint8_t              s_pool_head = 0;

void IRAM_ATTR sx1276_owner_dio0_isr(void *arg)
{
    BaseType_t higher_woken = pdFALSE;
    if (s_owner_task != NULL) {
        vTaskNotifyGiveFromISR(s_owner_task, &higher_woken);
        portYIELD_FROM_ISR(higher_woken);
    }
}

static esp_err_t apply_register_plan(const sx1276_register_plan_t *plan)
{
    esp_err_t err;

    // 1. Put transceiver into SLEEP to modify LongRangeMode
    err = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_SLEEP);
    if (err != ESP_OK) return err;

    // 2. Transition to STANDBY
    err = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
    if (err != ESP_OK) return err;

    // 3. Carrier Frequency
    sx1276_hal_write_reg(SX1276_REG_FR_MSB, plan->reg_fr_msb);
    sx1276_hal_write_reg(SX1276_REG_FR_MID, plan->reg_fr_mid);
    sx1276_hal_write_reg(SX1276_REG_FR_LSB, plan->reg_fr_lsb);

    // 4. PA, OCP & PA_DAC
    sx1276_hal_write_reg(SX1276_REG_PA_CONFIG, plan->reg_pa_config);
    sx1276_hal_write_reg(SX1276_REG_PA_RAMP, plan->reg_pa_ramp);
    sx1276_hal_write_reg(SX1276_REG_OCP, plan->reg_ocp);
    if (plan->reg_pa_dac != 0x00U) {
        sx1276_hal_write_reg(SX1276_REG_PA_DAC, plan->reg_pa_dac);
    }

    // 5. LNA
    sx1276_hal_write_reg(SX1276_REG_LNA, plan->reg_lna);

    // 6. Modem Configuration 1, 2, 3
    sx1276_hal_write_reg(SX1276_REG_MODEM_CONFIG_1, plan->reg_modem_config_1);
    sx1276_hal_write_reg(SX1276_REG_MODEM_CONFIG_2, plan->reg_modem_config_2);
    sx1276_hal_write_reg(SX1276_REG_MODEM_CONFIG_3, plan->reg_modem_config_3);

    // 7. Timeout & Preamble
    sx1276_hal_write_reg(SX1276_REG_SYMB_TIMEOUT_LSB, plan->reg_symb_timeout_lsb);
    sx1276_hal_write_reg(SX1276_REG_PREAMBLE_MSB, plan->reg_preamble_msb);
    sx1276_hal_write_reg(SX1276_REG_PREAMBLE_LSB, plan->reg_preamble_lsb);

    // 8. Sync Word
    sx1276_hal_write_reg(SX1276_REG_SYNC_WORD, plan->reg_sync_word);

    // 9. Errata & Threshold
    sx1276_hal_read_modify_write(SX1276_REG_DETECT_OPTIMIZE, 0x80U, 0x00U);
    sx1276_hal_write_reg(SX1276_REG_DETECTION_THRESHOLD, plan->reg_detection_threshold);

    // 10. FIFO Base Addresses
    sx1276_hal_write_reg(SX1276_REG_FIFO_TX_BASE_ADDR, 0x80U);
    sx1276_hal_write_reg(SX1276_REG_FIFO_RX_BASE_ADDR, 0x00U);

    s_current_mode = SX1276_MODE_STANDBY;
    return ESP_OK;
}

static esp_err_t process_rx_packet(void)
{
    uint8_t irq_flags = 0;
    uint8_t hop_channel = 0;
    uint8_t nb_bytes = 0;
    uint8_t current_addr = 0;
    uint8_t snr_raw = 0;
    uint8_t rssi_raw = 0;
    esp_err_t err = ESP_OK;

    err = sx1276_hal_read_reg(SX1276_REG_IRQ_FLAGS, &irq_flags);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }
    err = sx1276_hal_read_reg(SX1276_REG_HOP_CHANNEL, &hop_channel);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }
    err = sx1276_hal_read_reg(SX1276_REG_RX_NB_BYTES, &nb_bytes);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }
    err = sx1276_hal_read_reg(SX1276_REG_PKT_SNR_VALUE, &snr_raw);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }
    err = sx1276_hal_read_reg(SX1276_REG_PKT_RSSI_VALUE, &rssi_raw);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }

    // 1. Mandatory Payload CRC verification (per PHY_PROFILE_MVP_V1)
    if ((hop_channel & SX1276_HOPCHANNEL_CRCONPAYLOAD) == 0) {
        ESP_LOGW(TAG, "Reject packet: Missing mandatory Payload CRC");
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
        s_diag.rx_missing_crc_dropped++;
        return ESP_ERR_INVALID_CRC;
    }

    if ((irq_flags & SX1276_IRQ_PAYLOADCRCERROR) != 0) {
        ESP_LOGW(TAG, "Reject packet: Payload CRC Mismatch");
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
        s_diag.rx_crc_errors++;
        return ESP_ERR_INVALID_CRC;
    }

    // 2. Validate Length against host buffer bounds
    if (nb_bytes == 0) {
        ESP_LOGW(TAG, "Reject packet: Zero length");
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
        s_diag.rx_invalid_length_dropped++;
        return ESP_ERR_INVALID_SIZE;
    }

    if (nb_bytes > CONFIG_SX1276_HOST_RX_BUFFER_SIZE) {
        ESP_LOGE(TAG, "Reject packet: Exceeds host buffer size %u (got %u)",
                 CONFIG_SX1276_HOST_RX_BUFFER_SIZE, nb_bytes);
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
        s_diag.rx_host_buffer_overflow_dropped++;
        return ESP_ERR_INVALID_SIZE;
    }

    // 3. Extract Payload from RegFifo
    sx1276_hal_read_reg(SX1276_REG_FIFO_RX_CURRENT_ADDR, &current_addr);
    sx1276_hal_write_reg(SX1276_REG_FIFO_ADDR_PTR, current_addr);

    // Acquire next slot in preallocated static descriptor pool
    sx1276_rx_frame_t *frame = &s_frame_pool[s_pool_head];
    s_pool_head = (s_pool_head + 1) % CONFIG_SX1276_RX_BUFFER_POOL_SIZE;

    err = sx1276_hal_burst_read(SX1276_REG_FIFO, frame->payload, nb_bytes);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
        return err;
    }
    frame->length = nb_bytes;

    // 4. Calculate SNR & RSSI (HF port > 525 MHz per Semtech SX1276 Rev 7 §5.5.5)
    int8_t snr = (int8_t)snr_raw;
    frame->snr_db_quarter = snr;
    if (snr >= 0) {
        frame->rssi_dbm = -157 + (int16_t)rssi_raw;
    } else {
        /* Raw SNR is signed 2's complement representing 0.25 dB per LSB (snr / 4.0 dB).
         * For negative SNR: Packet RSSI = -157 + PacketRssi + SNR_dB.
         * Symmetric nearest-integer rounding for negative division: (snr - 2) / 4 */
        int16_t snr_correction = (int16_t)((snr - 2) / 4);
        frame->rssi_dbm = -157 + (int16_t)rssi_raw + snr_correction;
    }
    frame->channel_idx = s_phy_conf.channel_idx;
    frame->timestamp_us = (uint64_t)esp_timer_get_time();

    // 5. Targeted IRQ clear: write-1-to-clear only processed flags (0x70)
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);

    // 6. Enqueue frame into RX queue
    if (xQueueSend(s_rx_frame_queue, &frame, 0) != pdTRUE) {
        ESP_LOGW(TAG, "RX queue full: Frame dropped");
        s_diag.rx_host_buffer_overflow_dropped++;
        return ESP_ERR_NO_MEM;
    }

    s_diag.rx_packets_received++;
    return ESP_OK;
}

static esp_err_t execute_tx(const uint8_t *payload, uint8_t length, TickType_t timeout_ticks)
{
    // FAIL-CLOSED SAFETY GATE
    if (!s_phy_conf.rf_tx_enabled || s_phy_conf.pa_path == SX1276_PA_PATH_UNKNOWN) {
        ESP_LOGE(TAG, "RF TX BLOCKED fail-closed: rf_tx_enabled=%d, pa_path=%d",
                 s_phy_conf.rf_tx_enabled, s_phy_conf.pa_path);
        s_diag.tx_fail_closed_blocked++;
        return ESP_ERR_NOT_SUPPORTED;
    }

    if (payload == NULL || length == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    // 1. Switch to STANDBY
    sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);

    // 2. Set FIFO address pointer to TX base address (0x80)
    sx1276_hal_write_reg(SX1276_REG_FIFO_ADDR_PTR, 0x80U);

    // 3. Burst write payload into RegFifo
    esp_err_t err = sx1276_hal_burst_write(SX1276_REG_FIFO, payload, length);
    if (err != ESP_OK) {
        s_diag.spi_failures++;
        return err;
    }

    // 4. Set payload length
    sx1276_hal_write_reg(SX1276_REG_PAYLOAD_LENGTH, length);

    // 5. Configure DIO0 for TxDone (01b in RegDioMapping1)
    sx1276_hal_read_modify_write(SX1276_REG_DIO_MAPPING_1, SX1276_DIOMAPPING1_DIO0_MASK, SX1276_DIOMAPPING1_DIO0_TXDONE);

    // 6. Clear stale notifications
    ulTaskNotifyTake(pdTRUE, 0);

    // 7. Transition to TX mode (0x83)
    s_current_mode = SX1276_MODE_TX;
    sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_TX);

    // 8. Await TxDone notification from DIO0 ISR
    uint32_t notified = ulTaskNotifyTake(pdTRUE, timeout_ticks);
    s_current_mode = SX1276_MODE_STANDBY; // Silicon auto-reverts to STANDBY upon TxDone

    if (notified == 0) {
        ESP_LOGE(TAG, "TX timeout waiting for TxDone");
        // Force Standby and clear TxDone
        sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_TXDONE);
        return ESP_ERR_TIMEOUT;
    }

    // 9. Clear TxDone flag
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_TXDONE);
    s_diag.tx_packets_sent++;

    return ESP_OK;
}

static esp_err_t execute_rx_single(TickType_t timeout_ticks)
{
    // 1. Pre-clear stale IRQs
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, 0xFFU);

    // 2. Route DIO0 to RxDone (00b)
    sx1276_hal_read_modify_write(SX1276_REG_DIO_MAPPING_1, SX1276_DIOMAPPING1_DIO0_MASK, SX1276_DIOMAPPING1_DIO0_RXDONE);

    // 3. Clear stale notifications
    ulTaskNotifyTake(pdTRUE, 0);

    // 4. Enter RXSINGLE mode (0x86)
    s_current_mode = SX1276_MODE_RXSINGLE;
    sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_RXSINGLE);

    // 5. Stage 1 Search wait
    uint32_t notified = ulTaskNotifyTake(pdTRUE, timeout_ticks);
    s_current_mode = SX1276_MODE_STANDBY; // Reverts to STANDBY upon RxDone or timeout

    if (notified > 0) {
        return process_rx_packet();
    }

    // Stage 1 Search Expired: Read snapshot
    uint8_t irq_flags = 0;
    uint8_t modem_stat = 0;
    sx1276_hal_read_reg(SX1276_REG_IRQ_FLAGS, &irq_flags);
    sx1276_hal_read_reg(SX1276_REG_MODEM_STAT, &modem_stat);

    // Priority 1: RxDone race at timer expiry
    if ((irq_flags & SX1276_IRQ_RXDONE) != 0) {
        return process_rx_packet();
    }

    // Priority 2: Silicon confirmed RxTimeout
    if ((irq_flags & SX1276_IRQ_RXTIMEOUT) != 0) {
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RXTIMEOUT);
        s_diag.rx_hw_timeouts++;
        return ESP_ERR_TIMEOUT;
    }

    // Priority 3: Active in-flight demodulation
    if ((modem_stat & SX1276_MODEMSTAT_RXONGOING) != 0 ||
        (irq_flags & SX1276_IRQ_VALIDHEADER) != 0) {
        // Grant Stage 2 Bounded Demodulation Extension (up to 400 ms + margin)
        TickType_t demod_margin = pdMS_TO_TICKS(CONFIG_SX1276_RX_DEMOD_MARGIN_MS + 400);
        notified = ulTaskNotifyTake(pdTRUE, demod_margin);
        if (notified > 0) {
            return process_rx_packet();
        }
        // Demodulator stalled
        sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, 0xFFU);
        s_diag.rx_aborted_by_recovery++;
        return ESP_ERR_TIMEOUT;
    }

    // Priority 4: Pre-abort re-check
    sx1276_hal_read_reg(SX1276_REG_IRQ_FLAGS, &irq_flags);
    if ((irq_flags & SX1276_IRQ_RXDONE) != 0) {
        return process_rx_packet();
    }

    // Idle: force Standby and clear IRQs
    sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, 0xFFU);
    s_diag.rx_host_watchdog_expired++;
    return ESP_ERR_TIMEOUT;
}

static esp_err_t execute_cad(bool *out_detected, TickType_t timeout_ticks)
{
    if (out_detected == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    // 1. Pre-clear CadDone and CadDetected
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_CADDONE | SX1276_IRQ_CADDETECTED);

    // 2. Route DIO0 to CadDone (10b in RegDioMapping1)
    sx1276_hal_read_modify_write(SX1276_REG_DIO_MAPPING_1, SX1276_DIOMAPPING1_DIO0_MASK, SX1276_DIOMAPPING1_DIO0_CADDONE);

    // 3. Clear prior notifications
    ulTaskNotifyTake(pdTRUE, 0);

    // 4. Enter CAD mode (0x87)
    s_current_mode = SX1276_MODE_CAD;
    sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_CAD);

    // 5. Await CadDone notification
    uint32_t notified = ulTaskNotifyTake(pdTRUE, timeout_ticks);
    s_current_mode = SX1276_MODE_STANDBY; // Reverts to STANDBY upon CadDone

    if (notified == 0) {
        sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
        sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_CADDONE | SX1276_IRQ_CADDETECTED);
        return ESP_ERR_TIMEOUT;
    }

    uint8_t flags = 0;
    sx1276_hal_read_reg(SX1276_REG_IRQ_FLAGS, &flags);
    bool detected = (flags & SX1276_IRQ_CADDETECTED) != 0;
    *out_detected = detected;

    // Clear CAD flags
    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_CADDONE | SX1276_IRQ_CADDETECTED);

    if (detected) {
        s_diag.cad_detected_count++;
    } else {
        s_diag.cad_clear_count++;
    }

    return ESP_OK;
}

static void sx1276_owner_task(void *pvParameters)
{
    ESP_LOGI(TAG, "Radio Owner Task started (serialized SPI + state controller)");

    while (1) {
        sx1276_owner_cmd_t cmd;
        TickType_t wait_ticks = (s_current_mode == SX1276_MODE_RXCONT) ? pdMS_TO_TICKS(10) : portMAX_DELAY;

        BaseType_t ret = xQueueReceive(s_cmd_queue, &cmd, wait_ticks);
        if (ret == pdTRUE) {
            esp_err_t res = ESP_OK;
            switch (cmd.type) {
                case SX1276_CMD_APPLY_PLAN:
                    res = apply_register_plan(&s_reg_plan);
                    break;
                case SX1276_CMD_SLEEP:
                    res = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_SLEEP);
                    if (res == ESP_OK) s_current_mode = SX1276_MODE_SLEEP;
                    break;
                case SX1276_CMD_STANDBY:
                    res = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
                    if (res == ESP_OK) s_current_mode = SX1276_MODE_STANDBY;
                    break;
                case SX1276_CMD_TX:
                    res = execute_tx(cmd.params.tx.payload, cmd.params.tx.length, cmd.params.tx.timeout_ticks);
                    break;
                case SX1276_CMD_START_RX_SINGLE:
                    res = execute_rx_single(cmd.params.rx_single.timeout_ticks);
                    break;
                case SX1276_CMD_START_RX_CONT:
                    if (s_current_mode == SX1276_MODE_RXCONT) {
                        /* Already operating in RXCONT; do not write 0xFF to RegIrqFlags or drop DIO0 IRQ notifications. */
                        res = ESP_OK;
                        break;
                    }
                    sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, 0xFFU);
                    sx1276_hal_read_modify_write(SX1276_REG_DIO_MAPPING_1, SX1276_DIOMAPPING1_DIO0_MASK, SX1276_DIOMAPPING1_DIO0_RXDONE);
                    ulTaskNotifyTake(pdTRUE, 0);
                    res = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_RXCONTINUOUS);
                    if (res == ESP_OK) s_current_mode = SX1276_MODE_RXCONT;
                    break;
                case SX1276_CMD_STOP_RX:
                    res = sx1276_hal_write_reg(SX1276_REG_OP_MODE, SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY);
                    s_current_mode = SX1276_MODE_STANDBY;
                    s_diag.rx_aborted_by_host++;
                    break;
                case SX1276_CMD_CAD:
                    res = execute_cad(cmd.params.cad.out_detected, cmd.params.cad.timeout_ticks);
                    break;
                case SX1276_CMD_SET_CHANNEL: {
                    uint32_t freq_hz = 0;
                    res = sx1276_channel_to_frequency(cmd.params.set_chan.channel_idx, &freq_hz);
                    if (res == ESP_OK) {
                        s_phy_conf.channel_idx = cmd.params.set_chan.channel_idx;
                        s_phy_conf.frequency_hz = freq_hz;
                        sx1276_register_plan_build(&s_phy_conf, &s_reg_plan);
                        res = apply_register_plan(&s_reg_plan);
                    }
                    break;
                }
                case SX1276_CMD_READ_CHANNEL_RSSI: {
                    if (s_current_mode != SX1276_MODE_RXCONT && s_current_mode != SX1276_MODE_RXSINGLE) {
                        res = ESP_ERR_INVALID_STATE;
                        break;
                    }
                    uint8_t modem_stat = 0;
                    uint8_t rssi_raw = 0;
                    res = sx1276_hal_read_reg(SX1276_REG_MODEM_STAT, &modem_stat);
                    if (res != ESP_OK) {
                        s_diag.spi_failures++;
                        break;
                    }
                    res = sx1276_hal_read_reg(SX1276_REG_RSSI_VALUE, &rssi_raw);
                    if (res != ESP_OK) {
                        s_diag.spi_failures++;
                        break;
                    }
                    if (cmd.params.read_rssi.out_rssi_dbm != NULL) {
                        *cmd.params.read_rssi.out_rssi_dbm = -157 + (int16_t)rssi_raw;
                    }
                    if (cmd.params.read_rssi.out_context != NULL) {
                        *cmd.params.read_rssi.out_context = ((modem_stat & SX1276_MODEMSTAT_RXONGOING) != 0)
                                                                ? SX1276_CHANNEL_SAMPLE_ACTIVE
                                                                : SX1276_CHANNEL_SAMPLE_IDLE;
                    }
                    break;
                }
                default:
                    res = ESP_ERR_INVALID_ARG;
                    break;
            }

            if (cmd.out_result != NULL) {
                *cmd.out_result = res;
            }
            if (cmd.caller_task != NULL) {
                xTaskNotifyGive(cmd.caller_task);
            }
        }

        // If in Continuous RX mode, service any packet arrivals signaled by DIO0 ISR
        if (s_current_mode == SX1276_MODE_RXCONT) {
            uint32_t notified = ulTaskNotifyTake(pdTRUE, 0);
            if (notified > 0) {
                process_rx_packet();
            }
        }
    }
}

esp_err_t sx1276_owner_init(const sx1276_phy_config_t *initial_phy)
{
    if (initial_phy == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    s_phy_conf = *initial_phy;
    memset(&s_diag, 0, sizeof(sx1276_diagnostics_t));

    esp_err_t err = sx1276_register_plan_build(&s_phy_conf, &s_reg_plan);
    if (err != ESP_OK) {
        return err;
    }

    s_cmd_queue = xQueueCreate(SX1276_CMD_QUEUE_LEN, sizeof(sx1276_owner_cmd_t));
    if (s_cmd_queue == NULL) {
        return ESP_ERR_NO_MEM;
    }

    s_rx_frame_queue = xQueueCreate(CONFIG_SX1276_RX_BUFFER_POOL_SIZE, sizeof(sx1276_rx_frame_t *));
    if (s_rx_frame_queue == NULL) {
        vQueueDelete(s_cmd_queue);
        s_cmd_queue = NULL;
        return ESP_ERR_NO_MEM;
    }

    BaseType_t task_ret = xTaskCreatePinnedToCore(
        sx1276_owner_task,
        "sx1276_owner",
        4096,
        NULL,
        5,
        &s_owner_task,
        1
    );

    if (task_ret != pdPASS) {
        vQueueDelete(s_rx_frame_queue);
        s_rx_frame_queue = NULL;
        vQueueDelete(s_cmd_queue);
        s_cmd_queue = NULL;
        return ESP_ERR_NO_MEM;
    }

    // Apply register plan via owner command
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_APPLY_PLAN,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(1000));
}

esp_err_t sx1276_owner_deinit(void)
{
    if (s_owner_task != NULL) {
        vTaskDelete(s_owner_task);
        s_owner_task = NULL;
    }
    if (s_cmd_queue != NULL) {
        vQueueDelete(s_cmd_queue);
        s_cmd_queue = NULL;
    }
    if (s_rx_frame_queue != NULL) {
        vQueueDelete(s_rx_frame_queue);
        s_rx_frame_queue = NULL;
    }
    return ESP_OK;
}

esp_err_t sx1276_owner_send_cmd(sx1276_owner_cmd_t *cmd, TickType_t wait_ticks)
{
    if (cmd == NULL || s_cmd_queue == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    esp_err_t result = ESP_OK;
    cmd->out_result = &result;
    cmd->caller_task = xTaskGetCurrentTaskHandle();

    // Clear caller task notifications
    ulTaskNotifyTake(pdTRUE, 0);

    if (xQueueSend(s_cmd_queue, cmd, wait_ticks) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }

    // Await execution by Radio Owner
    if (ulTaskNotifyTake(pdTRUE, wait_ticks) == 0) {
        return ESP_ERR_TIMEOUT;
    }

    return result;
}

esp_err_t sx1276_owner_pop_rx_frame(sx1276_rx_frame_t *out_frame, TickType_t wait_ticks)
{
    if (out_frame == NULL || s_rx_frame_queue == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sx1276_rx_frame_t *p_frame = NULL;
    if (xQueueReceive(s_rx_frame_queue, &p_frame, wait_ticks) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    if (p_frame != NULL) {
        *out_frame = *p_frame;
    }
    return ESP_OK;
}

esp_err_t sx1276_owner_get_diagnostics(sx1276_diagnostics_t *out_diag)
{
    if (out_diag == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    *out_diag = s_diag;
    return ESP_OK;
}

esp_err_t sx1276_owner_reinit_after_wake(void)
{
    // Re-assert reset and verify version
    esp_err_t err = sx1276_hal_reset();
    if (err != ESP_OK) return err;

    err = sx1276_hal_verify_version();
    if (err != ESP_OK) return err;

    // Apply saved plan
    sx1276_owner_cmd_t cmd = {
        .type = SX1276_CMD_APPLY_PLAN,
    };
    return sx1276_owner_send_cmd(&cmd, pdMS_TO_TICKS(1000));
}
