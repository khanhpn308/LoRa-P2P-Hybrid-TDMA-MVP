#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"
#include "node_event_fifo.h"
#include "button_driver.h"
#include "airtime_policy.h"
#include "tdma_common.h"
#include "node_crypto.h"
#include "node_tdma_client.h"
#include "node_v2_join.h"
#include "sdkconfig.h"

static const char *TAG = "sensor_node";

/* Persistent RTC memory variables preserved across Deep-Sleep */
RTC_DATA_ATTR static node_event_fifo_t s_event_fifo;
RTC_DATA_ATTR static node_tdma_client_state_t s_tdma_state;
RTC_DATA_ATTR static node_v2_join_context_t s_join_ctx;
RTC_DATA_ATTR static uint32_t s_boot_count = 0;
RTC_DATA_ATTR static uint32_t s_button_events = 0;
RTC_DATA_ATTR static bool s_fifo_initialized = false;
RTC_DATA_ATTR static bool s_tdma_initialized = false;
RTC_DATA_ATTR static bool s_join_initialized = false;

/* Production SX1276 & FreeRTOS Radio HAL Callbacks */
static esp_err_t prod_radio_cad(bool *out_activity_detected)
{
    return sx1276_cad(out_activity_detected, pdMS_TO_TICKS(100));
}

static esp_err_t prod_radio_tx(const uint8_t *payload, uint8_t length, uint32_t timeout_ms)
{
    return sx1276_tx(payload, length, pdMS_TO_TICKS(timeout_ms));
}

static esp_err_t prod_radio_rx_single(uint32_t timeout_ms)
{
    return sx1276_start_rx_single(pdMS_TO_TICKS(timeout_ms));
}

static esp_err_t prod_radio_read_frame(uint8_t *out_buf, size_t *out_len, uint32_t wait_ms)
{
    if (out_buf == NULL || out_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    sx1276_rx_frame_t frame;
    esp_err_t err = sx1276_read_frame(&frame, pdMS_TO_TICKS(wait_ms));
    if (err == ESP_OK) {
        *out_len = frame.length;
        (void)memcpy(out_buf, frame.payload, frame.length);
    }
    return err;
}

static esp_err_t prod_radio_sleep(void)
{
    return sx1276_sleep();
}

static esp_err_t prod_radio_standby(void)
{
    return sx1276_standby();
}

static uint32_t prod_get_time_ms(void)
{
    return (uint32_t)(esp_timer_get_time() / 1000ULL);
}

static void prod_delay_ms(uint32_t ms)
{
    if (ms > 0) {
        vTaskDelay(pdMS_TO_TICKS(ms));
    }
}

void app_main(void)
{
    s_boot_count++;
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "Starting Sensor Node Boot #%" PRIu32 " (ESP-IDF v6.1 / HW-001)", s_boot_count);

    /* 1. Initialize persistent FIFO on first boot / cold start */
    if (!s_fifo_initialized) {
        esp_err_t fifo_err = node_event_fifo_init(&s_event_fifo, 0, 1);
        if (fifo_err == ESP_OK) {
            s_fifo_initialized = true;
            ESP_LOGI(TAG, "Persistent Node Event FIFO initialized (capacity: %u items)", NODE_EVENT_FIFO_CAPACITY);
        } else {
            ESP_LOGE(TAG, "Failed to initialize Node Event FIFO: %s", esp_err_to_name(fifo_err));
        }
    }

    /* 2. Configure TDMA Client parameters from Kconfig / defaults */
    node_tdma_client_config_t tdma_cfg;
    (void)node_tdma_client_get_default_config(&tdma_cfg);
#ifdef CONFIG_NODE_TDMA_NODE_ID
    tdma_cfg.node_id = (uint8_t)CONFIG_NODE_TDMA_NODE_ID;
#endif
#ifdef CONFIG_NODE_TDMA_GATEWAY_ID
    tdma_cfg.gw_id = (uint8_t)CONFIG_NODE_TDMA_GATEWAY_ID;
#endif
#ifdef CONFIG_NODE_TDMA_BEACON_TIMEOUT_MS
    tdma_cfg.beacon_window_ms = (uint32_t)CONFIG_NODE_TDMA_BEACON_TIMEOUT_MS;
#endif
#ifdef CONFIG_NODE_TDMA_CLOCK_DRIFT_PPM
    tdma_cfg.clock_drift_ppm = (uint32_t)CONFIG_NODE_TDMA_CLOCK_DRIFT_PPM;
#endif

    if (!s_tdma_initialized) {
        esp_err_t tdma_init_err = node_tdma_client_init(&tdma_cfg, &s_tdma_state);
        if (tdma_init_err == ESP_OK) {
            s_tdma_initialized = true;
            ESP_LOGI(TAG, "Node TDMA Client initialized for Node ID #%u (Slot #%u)",
                     tdma_cfg.node_id, tdma_cfg.node_id);
        } else {
            ESP_LOGE(TAG, "Failed to initialize TDMA Client state: %s", esp_err_to_name(tdma_init_err));
        }
    }

    if (!s_join_initialized) {
        (void)node_v2_join_init(&s_join_ctx);
        s_join_initialized = true;
        ESP_LOGI(TAG, "Sensor Node V2 Join subsystem initialized (State: %s)",
                 node_v2_join_state_to_str(s_join_ctx.state));
    }

    node_v2_join_radio_hal_t join_hal = {
        .radio_cad = prod_radio_cad,
        .radio_tx = prod_radio_tx,
        .radio_rx_single = prod_radio_rx_single,
        .radio_read_frame = prod_radio_read_frame,
        .radio_sleep = prod_radio_sleep,
        .radio_standby = prod_radio_standby,
        .get_time_ms = prod_get_time_ms,
        .delay_ms = prod_delay_ms,
    };
    (void)join_hal;

    /* 3. Initialize Airtime Policy & Crypto subsystem */
#ifdef CONFIG_NODE_TDMA_AIRTIME_PERMILLE
    (void)airtime_policy_init((uint16_t)CONFIG_NODE_TDMA_AIRTIME_PERMILLE);
#else
    (void)airtime_policy_init(10U); /* 1.0% regulatory duty cycle */
#endif
    (void)node_crypto_init();

    /* 4. Initialize button driver from Kconfig settings */
    button_driver_t btn_driver;
    button_config_t btn_cfg = {
        .gpio_num = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO,
        .active_level = CONFIG_NODE_BUTTON_ACTIVE_LEVEL,
        .debounce_ms = CONFIG_NODE_BUTTON_DEBOUNCE_MS,
        .hold_time_ms = CONFIG_NODE_BUTTON_HOLD_TIME_MS,
    };

    esp_err_t btn_err = button_driver_init(&btn_driver, &btn_cfg);
    if (btn_err != ESP_OK) {
        ESP_LOGE(TAG, "Button driver initialization failed: %s", esp_err_to_name(btn_err));
    }

    /* 5. Identify wake-up cause and service button events */
    button_wakeup_cause_t wake_cause = button_driver_get_wakeup_cause();
    switch (wake_cause) {
        case BUTTON_CAUSE_EXT0_BUTTON: {
            ESP_LOGI(TAG, "[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO %d", CONFIG_NODE_BUTTON_GPIO);
            bool qualified = false;
            esp_err_t q_err = button_driver_qualify_press(&btn_driver, &qualified);
            if (q_err == ESP_OK && qualified) {
                s_button_events++;
                uint32_t event_ref = 0;
                uint32_t now_sec = (uint32_t)(esp_timer_get_time() / 1000000ULL);

                /* Event Code 0x01 = Manual Button Trigger, Value 1 = Pressed */
                esp_err_t push_err = node_event_fifo_push(&s_event_fifo, now_sec, 0x01, 1, &event_ref);
                if (push_err == ESP_OK) {
                    ESP_LOGI(TAG, ">>> EVENT ENQUEUED <<< Ref: %" PRIu32 ", Total button events: %" PRIu32,
                             event_ref, s_button_events);
                } else {
                    ESP_LOGW(TAG, "Failed to enqueue event: %s (FIFO dropped count: %" PRIu32 ")",
                             esp_err_to_name(push_err), node_event_fifo_get_dropped_count(&s_event_fifo));
                }
            } else {
                ESP_LOGW(TAG, "Transient wake without qualified button press (bounce/noise filtered)");
            }
            /* Re-initialize SX1276 after sleep wake */
            esp_err_t reinit_err = sx1276_reinit_after_wake();
            if (reinit_err != ESP_OK) {
                ESP_LOGW(TAG, "Radio reinit after wake returned: %s", esp_err_to_name(reinit_err));
            }
            break;
        }
        case BUTTON_CAUSE_TIMER:
            ESP_LOGI(TAG, "[WAKE CAUSE] Periodic Timer Wakeup (Maintenance/Sync Check)");
            (void)sx1276_reinit_after_wake();
            break;
        default:
            ESP_LOGI(TAG, "[WAKE CAUSE] Power-On Reset or Software Restart");
            /* Cold boot: initialize SX1276 radio into STANDBY (Fail-closed RF) */
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err != ESP_OK) {
                ESP_LOGW(TAG, "SX1276 init returned: %s (safe standby default)", esp_err_to_name(sx_err));
            } else {
                ESP_LOGI(TAG, "SX1276 initialized successfully in STANDBY mode");
            }
            break;
    }

    size_t pending_events = node_event_fifo_get_pending_count(&s_event_fifo);
    ESP_LOGI(TAG, "FIFO State: Pending Events = %zu, Dropped Events = %" PRIu32,
             pending_events, node_event_fifo_get_dropped_count(&s_event_fifo));

    /* 6. Execute TDMA Slot Client cycle if pending events exist */
    if (pending_events > 0U) {
        node_tdma_radio_hal_t hal = {
            .radio_tx = prod_radio_tx,
            .radio_rx_single = prod_radio_rx_single,
            .radio_read_frame = prod_radio_read_frame,
            .radio_sleep = prod_radio_sleep,
            .radio_standby = prod_radio_standby,
            .get_time_ms = prod_get_time_ms,
            .delay_ms = prod_delay_ms,
        };

        ESP_LOGI(TAG, "Executing TDMA transmission cycle for %zu pending event(s)...", pending_events);
        esp_err_t cycle_err = node_tdma_client_run_cycle(&tdma_cfg, &hal, &s_tdma_state, &s_event_fifo);
        ESP_LOGI(TAG, "TDMA cycle completed (status: %s, client state: %s, remaining pending: %zu)",
                 esp_err_to_name(cycle_err),
                 node_tdma_state_to_str(s_tdma_state.state),
                 node_event_fifo_get_pending_count(&s_event_fifo));
    } else {
        /* No pending events: ensure radio is put to sleep */
        (void)sx1276_sleep();
    }

    /* 7. Prepare for Deep-Sleep */
    if (btn_driver.is_initialized) {
        button_driver_arm_sleep(&btn_driver);
    }

#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
    ESP_LOGI(TAG, "Enabling Timer Wakeup in %d seconds", CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC);
    esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
#endif

    ESP_LOGI(TAG, "Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    ESP_LOGI(TAG, "==================================================");

    esp_deep_sleep_start();
}
