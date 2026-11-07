#include <inttypes.h>
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "sx1276_driver.h"
#include "node_event_fifo.h"
#include "button_driver.h"
#include "sdkconfig.h"

static const char *TAG = "sensor_node";

// Persistent RTC memory variables preserved across Deep-Sleep
RTC_DATA_ATTR static node_event_fifo_t s_event_fifo;
RTC_DATA_ATTR static uint32_t s_boot_count = 0;
RTC_DATA_ATTR static uint32_t s_button_events = 0;
RTC_DATA_ATTR static bool s_fifo_initialized = false;

void app_main(void)
{
    s_boot_count++;
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "Starting Sensor Node Boot #%" PRIu32 " (ESP-IDF v6.1 / HW-001)", s_boot_count);

    // Initialize persistent FIFO on first boot / cold start
    if (!s_fifo_initialized) {
        esp_err_t fifo_err = node_event_fifo_init(&s_event_fifo, 0, 1);
        if (fifo_err == ESP_OK) {
            s_fifo_initialized = true;
            ESP_LOGI(TAG, "Persistent Node Event FIFO initialized (capacity: %u items)", NODE_EVENT_FIFO_CAPACITY);
        } else {
            ESP_LOGE(TAG, "Failed to initialize Node Event FIFO: %s", esp_err_to_name(fifo_err));
        }
    }

    // Initialize button driver from Kconfig settings
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

    // Identify wake-up cause
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

                // Event Code 0x01 = Manual Button Trigger, Value 1 = Pressed
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
            break;
        }
        case BUTTON_CAUSE_TIMER:
            ESP_LOGI(TAG, "[WAKE CAUSE] Periodic Timer Wakeup (Maintenance/Sync Check)");
            break;
        default:
            ESP_LOGI(TAG, "[WAKE CAUSE] Power-On Reset or Software Restart");
            // Cold boot: initialize SX1276 radio into STANDBY (Fail-closed RF)
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err != ESP_OK) {
                ESP_LOGW(TAG, "SX1276 init returned: %s (safe standby default)", esp_err_to_name(sx_err));
            } else {
                ESP_LOGI(TAG, "SX1276 initialized successfully in STANDBY mode");
            }
            break;
    }

    ESP_LOGI(TAG, "FIFO State: Pending Events = %zu, Dropped Events = %" PRIu32,
             node_event_fifo_get_pending_count(&s_event_fifo),
             node_event_fifo_get_dropped_count(&s_event_fifo));

    // Prepare for Deep-Sleep
    // Arm EXT0 wakeup on button GPIO
    if (btn_driver.is_initialized) {
        button_driver_arm_sleep(&btn_driver);
    }

    // Optional timer fallback
#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
    ESP_LOGI(TAG, "Enabling Timer Wakeup in %d seconds", CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC);
    esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
#endif

    ESP_LOGI(TAG, "Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    ESP_LOGI(TAG, "==================================================");

    esp_deep_sleep_start();
}
