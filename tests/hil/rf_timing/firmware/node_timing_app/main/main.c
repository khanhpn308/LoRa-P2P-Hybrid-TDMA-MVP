/**
 * @file main.c
 * @brief ESP-IDF Node Timing Instrumentation Application for Issue #11.
 *
 * Implements bounded test state machine to capture software timestamps and DIO0 IRQs.
 * Conforms to C Coding Standard v2, ADR-0003, and PCB HW-001 pin mapping.
 */

#include <stdio.h>
#include <string.h>
#include <inttypes.h>

#if defined(ESP_PLATFORM)
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/gpio.h"
#include "esp_timer.h"
#include "esp_log.h"
#endif

#include "timing_harness_types.h"
#include "timing_ring_buffer.h"
#include "radio_adapter_mock.h"
#include "node_timing_config.h"

static timing_ring_buffer_t s_ring_buffer;
static timing_diagnostics_t s_diagnostics;
#if defined(ESP_PLATFORM)
static TaskHandle_t s_runner_task_handle = NULL;
#endif

#if defined(ESP_PLATFORM)
/**
 * @brief Minimal, non-blocking ISR handler for DIO0 (GPIO26).
 * No SPI, no printf, no blocking memory allocations.
 */
static void IRAM_ATTR dio0_gpio_isr_handler(void *arg)
{
    (void)arg;
    int64_t now_us = esp_timer_get_time();
    s_diagnostics.irq_count++;

    /* Push latched event directly to ISR-safe ring buffer */
    timing_ring_buffer_push_isr(&s_ring_buffer, TIMING_EVT_DIO0_IRQ, now_us, 0U);

    /* Notify runner task */
    BaseType_t high_task_awoken = pdFALSE;
    if (s_runner_task_handle != NULL) {
        vTaskNotifyGiveFromISR(s_runner_task_handle, &high_task_awoken);
        portYIELD_FROM_ISR(high_task_awoken);
    }
}
#endif

static void log_event(uint8_t event_type, uint8_t pl_len, uint8_t channel, uint16_t status, uint32_t extra)
{
    timing_event_record_t rec;
    memset(&rec, 0, sizeof(rec));
    rec.timestamp_us = timing_get_time_us();
    rec.event_type = event_type;
    rec.role = (uint8_t)TIMING_ROLE_NODE;
    rec.payload_len = pl_len;
    rec.channel_idx = channel;
    rec.evidence_class = (uint8_t)EVIDENCE_SOFTWARE_TIMESTAMP;
    rec.status_code = status;
    rec.extra_info = extra;

    if (!timing_ring_buffer_push(&s_ring_buffer, &rec)) {
        s_diagnostics.events_dropped++;
    } else {
        s_diagnostics.events_recorded++;
    }
}

/**
 * @brief UART Logger Task: drains ring buffer and outputs structured JSONL lines.
 */
static void node_logger_task(void *pvParameters)
{
    (void)pvParameters;
    timing_event_record_t rec;

    while (1) {
        while (timing_ring_buffer_pop(&s_ring_buffer, &rec)) {
            const char *evt_str = "UNKNOWN";
            switch (rec.event_type) {
                case TIMING_EVT_INIT:       evt_str = "INIT"; break;
                case TIMING_EVT_TX_CMD:     evt_str = "TX_CMD"; break;
                case TIMING_EVT_TX_START:   evt_str = "TX_START"; break;
                case TIMING_EVT_DIO0_IRQ:   evt_str = "DIO0_IRQ"; break;
                case TIMING_EVT_TX_DONE:    evt_str = "TX_DONE"; break;
                case TIMING_EVT_RX_CMD:     evt_str = "RX_CMD"; break;
                case TIMING_EVT_RX_DONE:    evt_str = "RX_DONE"; break;
                case TIMING_EVT_RX_TIMEOUT: evt_str = "RX_TIMEOUT"; break;
                case TIMING_EVT_CAD_DONE:   evt_str = "CAD_DONE"; break;
                case TIMING_EVT_CLOCK_SYNC: evt_str = "CLOCK_SYNC"; break;
                case TIMING_EVT_OVERFLOW:   evt_str = "OVERFLOW"; break;
                default: break;
            }

            printf("{\"ver\":\"1.0.0\",\"seq\":%" PRIu32 ",\"role\":\"NODE\",\"dev_id\":\"%s\","
                   "\"evt\":\"%s\",\"ts_us\":%" PRId64 ",\"class\":\"SOFTWARE_TIMESTAMP\","
                   "\"pl_len\":%u,\"ch\":%u,\"status\":%u,\"extra\":%" PRIu32 "}\n",
                   rec.seq, NODE_DEVICE_ID, evt_str, rec.timestamp_us,
                   rec.payload_len, rec.channel_idx, rec.status_code, rec.extra_info);
        }

#if defined(ESP_PLATFORM)
        vTaskDelay(pdMS_TO_TICKS(10));
#else
        break;
#endif
    }
}

/**
 * @brief Node timing test state machine runner.
 */
static void node_runner_task(void *pvParameters)
{
    (void)pvParameters;
    uint8_t dummy_payload[64];
    memset(dummy_payload, 0xAA, sizeof(dummy_payload));

    /* Initialize radio configuration */
    timing_radio_config_t rcfg = {
        .sf = 7,
        .bw_hz = 125000,
        .cr = 1,
        .preamble_len = 8,
        .channel_idx = 0,
        .rf_tx_enabled = NODE_DEFAULT_RF_TX_ENABLED,
        .pa_path_verified = NODE_DEFAULT_PA_VERIFIED,
        .tx_power_dbm = 2,
    };
    timing_radio_init(&rcfg);
    log_event(TIMING_EVT_INIT, 0, 0, 0, 0);

    /* Run bounded sweeps across profile combinations */
    for (uint32_t iter = 0; iter < NODE_TIMING_ITERATIONS; iter++) {
        for (uint8_t sf_idx = 0; sf_idx < NODE_SF_COUNT; sf_idx++) {
            uint8_t sf = NODE_SF_MODES[sf_idx];
            rcfg.sf = sf;
            timing_radio_init(&rcfg);

            for (uint8_t pl_idx = 0; pl_idx < NODE_PAYLOAD_SIZE_COUNT; pl_idx++) {
                uint8_t pl_len = NODE_PAYLOAD_SIZES[pl_idx];

                /* 1. Schedule Uplink Event */
                log_event(TIMING_EVT_TX_CMD, pl_len, 0, 0, (uint32_t)sf);
                s_diagnostics.tx_cmd_count++;

                /* 2. Dispatch TX Command to radio adapter */
                log_event(TIMING_EVT_TX_START, pl_len, 0, 0, (uint32_t)sf);
                int tx_err = timing_radio_tx(dummy_payload, pl_len, 200U);
                if (tx_err == -100) {
                    /* Fail-closed safety gate blocked transmission */
                    s_diagnostics.fail_closed_tx_blocks++;
                    log_event(TIMING_EVT_TX_DONE, pl_len, 0, 100U /* BLOCKED */, 0U);
                } else {
                    log_event(TIMING_EVT_TX_DONE, pl_len, 0, 0U, 0U);
                }

                /* 3. Transition to RxSingle for slotted Gateway ACK */
                log_event(TIMING_EVT_RX_CMD, 8, 0, 0, 0);
                s_diagnostics.rx_cmd_count++;
                timing_rx_packet_t ack_pkt;
                int rx_err = timing_radio_read_frame(&ack_pkt, 50U);
                if (rx_err == 0) {
                    log_event(TIMING_EVT_RX_DONE, ack_pkt.length, 0, 0, (uint32_t)ack_pkt.rssi_dbm);
                } else {
                    s_diagnostics.timeout_count++;
                    log_event(TIMING_EVT_RX_TIMEOUT, 0, 0, (uint16_t)rx_err, 0);
                }

#if defined(ESP_PLATFORM)
                vTaskDelay(pdMS_TO_TICKS(50));
#endif
            }
        }
    }

    printf("# Node timing harness complete. Recorded: %" PRIu32 ", Dropped: %" PRIu32 ", Blocked: %" PRIu32 "\n",
           s_diagnostics.events_recorded, s_diagnostics.events_dropped, s_diagnostics.fail_closed_tx_blocks);

#if defined(ESP_PLATFORM)
    vTaskDelete(NULL);
#endif
}

void app_main(void)
{
    printf("=== Starting ESP32 SX1276 Node Timing Test Harness (Issue #11) ===\n");
    timing_ring_buffer_init(&s_ring_buffer);
    memset(&s_diagnostics, 0, sizeof(s_diagnostics));

#if defined(ESP_PLATFORM)
    /* Configure HW-001 GPIO26 for DIO0 input with rising edge interrupt */
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << HW001_PIN_DIO0),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    gpio_config(&io_conf);
    gpio_install_isr_service(0);
    gpio_isr_handler_add((gpio_num_t)HW001_PIN_DIO0, dio0_gpio_isr_handler, NULL);

    xTaskCreate(node_logger_task, "node_logger", NODE_LOGGER_STACK_SIZE, NULL, NODE_LOGGER_TASK_PRIO, NULL);
    xTaskCreate(node_runner_task, "node_runner", NODE_RUNNER_STACK_SIZE, NULL, NODE_RUNNER_TASK_PRIO, &s_runner_task_handle);
#else
    /* Host execution path */
    node_runner_task(NULL);
    node_logger_task(NULL);
#endif
}

#if !defined(ESP_PLATFORM)
int main(void)
{
    app_main();
    return 0;
}
#endif
