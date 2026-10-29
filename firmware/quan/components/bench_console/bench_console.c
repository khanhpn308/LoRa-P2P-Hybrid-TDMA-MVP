#include "bench_console.h"
#include "event_input.h"
#include "sdkconfig.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include <inttypes.h>
#include <stdio.h>
#ifdef EVENT_BENCH_LINK_SHARED_DRIVER
#include "sx1276_driver.h"
#endif

static const char *const bench_console_tag = "event_bench";

void bench_console_run_bench(bool gateway)
{
    /* One pending event is intentional bench backpressure, not a production
     * queue budget. Owned exclusively by app_main for this function lifetime. */
    event_input_t storage[1];
    event_input_queue_t queue;
    event_input_button_t button;
    uint32_t sequence = 0;
    bool pressed = false;
    bool sequence_exhausted = false;
    bool initial_edge = false;

    if (event_input_init_queue(&queue, storage, 1) != EVENT_INPUT_OK ||
        event_input_init_button(&button, CONFIG_BENCH_CONSOLE_DEBOUNCE_MS) != EVENT_INPUT_OK) {
        ESP_LOGE(bench_console_tag, "Local state initialization failed");
        return;
    }
    /* UART logical button starts released, even if p was already buffered. */
    if (event_input_sample_button(&button, false, 0, &initial_edge) != EVENT_INPUT_OK) {
        ESP_LOGE(bench_console_tag, "Button baseline initialization failed");
        return;
    }
#ifdef EVENT_BENCH_LINK_SHARED_DRIVER
    ESP_LOGI(bench_console_tag, "Linked shared component: %s (not started)",
             sx1276_driver_component_name());
#endif
    ESP_LOGI(bench_console_tag, "%s LOCAL BENCH; no radio transport",
             gateway ? "Gateway" : "Node");
    ESP_LOGI(bench_console_tag, "Commands: p=press r=release i=local ingress(gateway) d=drain s=status");
    for (;;) {
        int command = getchar();
        int64_t now_us = esp_timer_get_time();
        uint64_t now_ms;
        bool edge = false;
        bool create_event;
        event_input_status_t status;
        if (now_us < 0) {
            ESP_LOGE(bench_console_tag, "Clock invalid; stopping bench");
            return;
        }
        now_ms = (uint64_t)now_us / UINT64_C(1000);
        if (command == EOF) {
            clearerr(stdin);
        } else if (command == 'p') {
            pressed = true;
        } else if (command == 'r') {
            pressed = false;
        }
        status = event_input_sample_button(&button, pressed, now_ms, &edge);
        if (status != EVENT_INPUT_OK) {
            ESP_LOGE(bench_console_tag, "Button rejected sample: %d", (int)status);
            return;
        }
        create_event = gateway ? command == 'i' : edge;
        if (create_event && !sequence_exhausted) {
            event_input_t event = {.sequence = sequence, .created_ms = now_ms};
            status = event_input_push_event(&queue, &event);
            ESP_LOGI(bench_console_tag, "Local event=%" PRIu32 " enqueue_status=%d",
                     sequence, (int)status);
            if (sequence == UINT32_MAX) {
                sequence_exhausted = true;
            } else {
                ++sequence;
            }
        } else if (create_event) {
            ESP_LOGW(bench_console_tag, "Local sequence exhausted; event rejected");
        }
        if (command == 'd') {
            event_input_t event;
            status = event_input_pop_event(&queue, &event);
            if (status == EVENT_INPUT_OK) {
                ESP_LOGI(bench_console_tag, "Drained local event=%" PRIu32 " created_ms=%" PRIu64,
                         event.sequence, event.created_ms);
            } else {
                ESP_LOGI(bench_console_tag, "Drain status=%d", (int)status);
            }
        } else if (command == 's') {
            ESP_LOGI(bench_console_tag, "pending=%u dropped=%" PRIu32,
                     (unsigned)queue.count, queue.dropped);
        }
        vTaskDelay(1);
    }
}
