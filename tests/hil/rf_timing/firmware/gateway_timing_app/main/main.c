/**
 * @file main.c
 * @brief ESP-IDF Gateway Timing Instrumentation Application for Issue #11.
 *
 * Implements bounded test state machine for Gateway role:
 * Beacon broadcast, continuous Uplink receive window, slotted ACK turnaround.
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
#include "gateway_timing_config.h"

static timing_ring_buffer_t s_gw_ring_buffer;
static timing_diagnostics_t s_gw_diagnostics;
#if defined(ESP_PLATFORM)
static TaskHandle_t s_gw_runner_task_handle = NULL;
#endif

#if defined(ESP_PLATFORM)
/**
 * @brief Non-blocking DIO0 ISR handler for Gateway (GPIO26).
 */
static void IRAM_ATTR gw_dio0_gpio_isr_handler(void *arg)
{
    (void)arg;
    int64_t now_us = esp_timer_get_time();
    s_gw_diagnostics.irq_count++;

    timing_ring_buffer_push_isr(&s_gw_ring_buffer, TIMING_EVT_DIO0_IRQ, now_us, 0U);

    BaseType_t high_task_awoken = pdFALSE;
    if (s_gw_runner_task_handle != NULL) {
        vTaskNotifyGiveFromISR(s_gw_runner_task_handle, &high_task_awoken);
        portYIELD_FROM_ISR(high_task_awoken);
    }
}
#endif

static void gw_log_event(uint8_t event_type, uint8_t pl_len, uint8_t channel, uint16_t status, uint32_t extra)
{
    timing_event_record_t rec;
    memset(&rec, 0, sizeof(rec));
    rec.timestamp_us = timing_get_time_us();
    rec.event_type = event_type;
    rec.role = (uint8_t)TIMING_ROLE_GATEWAY;
    rec.payload_len = pl_len;
    rec.channel_idx = channel;
    rec.evidence_class = (uint8_t)EVIDENCE_SOFTWARE_TIMESTAMP;
    rec.status_code = status;
    rec.extra_info = extra;

    if (!timing_ring_buffer_push(&s_gw_ring_buffer, &rec)) {
        s_gw_diagnostics.events_dropped++;
    } else {
        s_gw_diagnostics.events_recorded++;
    }
}

static void gw_logger_task(void *pvParameters)
{
    (void)pvParameters;
    timing_event_record_t rec;

    while (1) {
        while (timing_ring_buffer_pop(&s_gw_ring_buffer, &rec)) {
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

            printf("{\"ver\":\"1.0.0\",\"seq\":%" PRIu32 ",\"role\":\"GATEWAY\",\"dev_id\":\"%s\","
                   "\"evt\":\"%s\",\"ts_us\":%" PRId64 ",\"class\":\"SOFTWARE_TIMESTAMP\","
                   "\"pl_len\":%u,\"ch\":%u,\"status\":%u,\"extra\":%" PRIu32 "}\n",
                   rec.seq, GATEWAY_DEVICE_ID, evt_str, rec.timestamp_us,
                   rec.payload_len, rec.channel_idx, rec.status_code, rec.extra_info);
        }

#if defined(ESP_PLATFORM)
        vTaskDelay(pdMS_TO_TICKS(10));
#else
        break;
#endif
    }
}

static void gw_runner_task(void *pvParameters)
{
    (void)pvParameters;
    uint8_t beacon_buf[GATEWAY_BEACON_PAYLOAD_LEN];
    memset(beacon_buf, 0xBB, sizeof(beacon_buf));

    uint8_t ack_buf[GATEWAY_ACK_PAYLOAD_LEN];
    memset(ack_buf, 0xCC, sizeof(ack_buf));

    timing_radio_config_t rcfg = {
        .sf = 7,
        .bw_hz = 125000,
        .cr = 1,
        .preamble_len = 8,
        .channel_idx = 0,
        .rf_tx_enabled = GATEWAY_DEFAULT_RF_TX_ENABLED,
        .pa_path_verified = GATEWAY_DEFAULT_PA_VERIFIED,
        .tx_power_dbm = 2,
    };
    timing_radio_init(&rcfg);
    gw_log_event(TIMING_EVT_INIT, 0, 0, 0, 0);

    for (uint32_t cycle = 0; cycle < GATEWAY_TIMING_CYCLES; cycle++) {
        /* 1. Transmit Superframe Beacon */
        gw_log_event(TIMING_EVT_CLOCK_SYNC, GATEWAY_BEACON_PAYLOAD_LEN, 0, 0, cycle);
        gw_log_event(TIMING_EVT_TX_CMD, GATEWAY_BEACON_PAYLOAD_LEN, 0, 0, 0);
        s_gw_diagnostics.tx_cmd_count++;

        gw_log_event(TIMING_EVT_TX_START, GATEWAY_BEACON_PAYLOAD_LEN, 0, 0, 0);
        int tx_res = timing_radio_tx(beacon_buf, sizeof(beacon_buf), 100U);
        if (tx_res == -100) {
            s_gw_diagnostics.fail_closed_tx_blocks++;
            gw_log_event(TIMING_EVT_TX_DONE, GATEWAY_BEACON_PAYLOAD_LEN, 0, 100U /* BLOCKED */, 0);
        } else {
            gw_log_event(TIMING_EVT_TX_DONE, GATEWAY_BEACON_PAYLOAD_LEN, 0, 0, 0);
        }

        /* 2. Transition to continuous RX for node uplink window */
        gw_log_event(TIMING_EVT_RX_CMD, 0, 0, 0, 0);
        s_gw_diagnostics.rx_cmd_count++;
        timing_radio_start_rx_continuous();

        /* Simulate node slot monitoring */
        for (uint8_t node = 0; node < 4; node++) {
            timing_rx_packet_t up_pkt;
            int rx_res = timing_radio_read_frame(&up_pkt, 20U);
            if (rx_res == 0) {
                gw_log_event(TIMING_EVT_RX_DONE, up_pkt.length, 0, 0, (uint32_t)node);

                /* Slotted ACK response */
                gw_log_event(TIMING_EVT_TX_CMD, sizeof(ack_buf), 0, 0, (uint32_t)node);
                timing_radio_tx(ack_buf, sizeof(ack_buf), 50U);
                gw_log_event(TIMING_EVT_TX_DONE, sizeof(ack_buf), 0, 0, 0);
            }
        }

        timing_radio_stop_rx();

#if defined(ESP_PLATFORM)
        vTaskDelay(pdMS_TO_TICKS(100));
#endif
    }

    printf("# Gateway timing harness complete. Recorded: %" PRIu32 ", Dropped: %" PRIu32 ", Blocked: %" PRIu32 "\n",
           s_gw_diagnostics.events_recorded, s_gw_diagnostics.events_dropped, s_gw_diagnostics.fail_closed_tx_blocks);

#if defined(ESP_PLATFORM)
    vTaskDelete(NULL);
#endif
}

void app_main(void)
{
    printf("=== Starting ESP32 SX1276 Gateway Timing Test Harness (Issue #11) ===\n");
    timing_ring_buffer_init(&s_gw_ring_buffer);
    memset(&s_gw_diagnostics, 0, sizeof(s_gw_diagnostics));

#if defined(ESP_PLATFORM)
    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << HW001_PIN_DIO0),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    gpio_config(&io_conf);
    gpio_install_isr_service(0);
    gpio_isr_handler_add((gpio_num_t)HW001_PIN_DIO0, gw_dio0_gpio_isr_handler, NULL);

    xTaskCreate(gw_logger_task, "gw_logger", GATEWAY_LOGGER_STACK_SIZE, NULL, GATEWAY_LOGGER_TASK_PRIO, NULL);
    xTaskCreate(gw_runner_task, "gw_runner", GATEWAY_RUNNER_STACK_SIZE, NULL, GATEWAY_RUNNER_TASK_PRIO, &s_gw_runner_task_handle);
#else
    gw_runner_task(NULL);
    gw_logger_task(NULL);
#endif
}

#if !defined(ESP_PLATFORM)
int main(void)
{
    app_main();
    return 0;
}
#endif
