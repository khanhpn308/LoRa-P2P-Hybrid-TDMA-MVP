#include "node_app.h"

#include <inttypes.h>
#include <string.h>
#include "esp_log.h"
#include "esp_sleep.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_mac.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "sx1276_driver.h"
#include "lora_mac.h"
#include "lora_mac_crypto.h"
#include "node_event_fifo.h"
#include "button_driver.h"
#include "airtime_policy.h"
#include "node_v2_join.h"
#include "node_ui.h"
#include "node_smart_backoff.h"
#include "node_cad_backoff.h"
#include "node_radio_hal.h"
#include "node_arq.h"
#include "node_event_tx.h"
#include "sdkconfig.h"

static const char *TAG = "sensor_node";

static const uint8_t DEFAULT_NONCE_PREFIX[8] = {
    0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57
};

/* Persistent RTC memory variables preserved across Deep-Sleep */
RTC_DATA_ATTR static node_event_fifo_t s_event_fifo;
RTC_DATA_ATTR static uint32_t s_uplink_frame_counter = 0;
RTC_DATA_ATTR static node_v2_join_context_t s_join_ctx;
RTC_DATA_ATTR static uint32_t s_boot_count = 0;
RTC_DATA_ATTR static uint32_t s_button_events = 0;
RTC_DATA_ATTR static bool s_fifo_initialized = false;
RTC_DATA_ATTR static bool s_join_initialized = false;

#ifndef CONFIG_NODE_STRICT_PROVISIONING
#define CONFIG_NODE_STRICT_PROVISIONING 1
#endif

static button_driver_t s_btn_driver;

/**
 * @brief Checks if buffer contains all zeros.
 */
static bool is_all_zeros(const uint8_t *buf, size_t len)
{
    if (buf == NULL || len == 0U) {
        return true;
    }
    for (size_t i = 0; i < len; i++) {
        if (buf[i] != 0U) {
            return false;
        }
    }
    return true;
}

static void node_handle_revoke_and_sleep(button_driver_t *btn_driver)
{
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, ">>> DOWN_REVOKE RECEIVED & VERIFIED! <<<");
    ESP_LOGI(TAG, "Erasing session NVS, putting radio to SLEEP, entering indefinite Deep-Sleep.");
    ESP_LOGI(TAG, "==================================================");

    /* 1. Update OLED if configured */
    (void)node_ui_show_unjoined();

    /* 2. Erase session from NVS and transition state */
    (void)node_v2_join_erase_session(&s_join_ctx);
    s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;

    /* 3. Put radio completely to sleep */
    (void)sx1276_sleep();

    /* 4. Disable timer wakeup explicitly to prevent periodic wakes */
    (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);

    /* 5. Arm EXT0 wakeup on button GPIO only */
    if (btn_driver != NULL && btn_driver->is_initialized) {
        (void)button_driver_arm_sleep(btn_driver);
    }

    ESP_LOGI(TAG, "Revoked: Entering Deep-Sleep mode. Press button on GPIO %d to request new join...",
             CONFIG_NODE_BUTTON_GPIO);
    esp_deep_sleep_start();
    vTaskSuspend(NULL);
}

void node_app_run(void)
{
    s_boot_count++;
    ESP_LOGI(TAG, "==================================================");
    ESP_LOGI(TAG, "Starting Sensor Node Boot #%" PRIu32 " (ESP-IDF v6.1 / HW-001 Pure CAD CSMA)", s_boot_count);

    bool radio_initialized = false;

    /* 1. Initialize NVS flash for monotonic join counter and credentials storage */
    esp_err_t nvs_ret = nvs_flash_init();
    if (nvs_ret == ESP_ERR_NVS_NO_FREE_PAGES || nvs_ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        (void)nvs_flash_erase();
        nvs_ret = nvs_flash_init();
    }
    if (nvs_ret != ESP_OK) {
        ESP_LOGE(TAG, "NVS flash initialization failed: %s", esp_err_to_name(nvs_ret));
    }

    /* 2. Initialize persistent FIFO on first boot / cold start */
    if (!s_fifo_initialized) {
        esp_err_t fifo_err = node_event_fifo_init(&s_event_fifo, 0, 1);
        if (fifo_err == ESP_OK) {
            s_fifo_initialized = true;
            ESP_LOGI(TAG, "Persistent Node Event FIFO initialized (capacity: %u items)", NODE_EVENT_FIFO_CAPACITY);
        } else {
            ESP_LOGE(TAG, "Failed to initialize Node Event FIFO: %s", esp_err_to_name(fifo_err));
        }
    }

    /* 3. Configure Node MAC parameters from Kconfig / defaults */
    node_mac_config_t mac_cfg;
    (void)memset(&mac_cfg, 0, sizeof(mac_cfg));
#ifdef CONFIG_NODE_DEFAULT_NODE_ID
    mac_cfg.node_id = (uint8_t)CONFIG_NODE_DEFAULT_NODE_ID;
#else
    mac_cfg.node_id = 1;
#endif
#ifdef CONFIG_NODE_TARGET_GATEWAY_ID
    mac_cfg.gw_id = (uint8_t)CONFIG_NODE_TARGET_GATEWAY_ID;
#else
    mac_cfg.gw_id = 1;
#endif
    (void)memcpy(mac_cfg.session_nonce_prefix, DEFAULT_NONCE_PREFIX, 8);

    /* 4. Configure Node V2 Join subsystem */
    if (!s_join_initialized) {
        (void)node_v2_join_init(&s_join_ctx);
        s_join_initialized = true;
        ESP_LOGI(TAG, "Sensor Node V2 Join subsystem initialized (State: %s)",
                 node_v2_join_state_to_str(s_join_ctx.state));
    } else if (s_join_ctx.state == NODE_V2_JOIN_STATE_ABORTED && !s_join_ctx.radio_permanently_locked) {
        /* Allow retry on new boot / wake event */
        s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
        ESP_LOGI(TAG, "Join state reset from ABORTED to UNJOINED for retry");
    }

    /* Attempt to recover persistent session from NVS Flash across cold boots (Issue #322, #323) */
    if (s_join_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE && !s_join_ctx.radio_permanently_locked) {
        esp_err_t load_err = node_v2_join_load_session(&s_join_ctx);
        if (load_err == ESP_OK) {
            ESP_LOGI(TAG, "==================================================");
            ESP_LOGI(TAG, ">>> RESTORED PERSISTENT V2 JOIN SESSION FROM NVS <<<");
            ESP_LOGI(TAG, "Assigned Node ID: #%u | State: %s",
                     s_join_ctx.assigned_node_id, node_v2_join_state_to_str(s_join_ctx.state));
            ESP_LOGI(TAG, "==================================================");
            mac_cfg.node_id = s_join_ctx.assigned_node_id;
            (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
            (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
        } else {
            ESP_LOGI(TAG, "No valid persistent session in NVS Flash (%s). Node remains UNJOINED.",
                     esp_err_to_name(load_err));
        }
    } else if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        /* Session preserved in RTC RAM across deep-sleep wake */
        mac_cfg.node_id = s_join_ctx.assigned_node_id;
        (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
        (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
    }

    node_v2_join_config_t join_cfg;
    (void)node_v2_join_get_default_config(&join_cfg);
#ifdef CONFIG_NODE_JOIN_GRANT_TIMEOUT_MS
    join_cfg.grant_listen_timeout_ms = (uint32_t)CONFIG_NODE_JOIN_GRANT_TIMEOUT_MS;
#endif

    /* Read provisioned device MAC and credentials from nvs_sec if present */
    bool k_join_loaded = false;
    nvs_handle_t sec_handle;
    esp_err_t sec_err = nvs_open("nvs_sec", NVS_READONLY, &sec_handle);
    if (sec_err == ESP_OK) {
        size_t mac_len = sizeof(join_cfg.device_mac);
        esp_err_t mac_err = nvs_get_blob(sec_handle, "device_mac", join_cfg.device_mac, &mac_len);
        if (mac_err == ESP_OK && mac_len == sizeof(join_cfg.device_mac) &&
            !is_all_zeros(join_cfg.device_mac, sizeof(join_cfg.device_mac))) {
            ESP_LOGI(TAG, "Loaded provisioned device MAC: %02x%02x%02x%02x%02x%02x",
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        } else {
            (void)esp_read_mac(join_cfg.device_mac, ESP_MAC_WIFI_STA);
            ESP_LOGI(TAG, "Using factory Wi-Fi MAC: %02x%02x%02x%02x%02x%02x",
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        }

        size_t k_len = sizeof(join_cfg.k_join);
        esp_err_t k_err = nvs_get_blob(sec_handle, "k_join", join_cfg.k_join, &k_len);
        if (k_err == ESP_OK && k_len == sizeof(join_cfg.k_join)) {
            if (!is_all_zeros(join_cfg.k_join, sizeof(join_cfg.k_join))) {
                k_join_loaded = true;
                ESP_LOGI(TAG, "Loaded provisioned K_JOIN from nvs_sec");
            } else {
                ESP_LOGE(TAG, "Provisioned K_JOIN in nvs_sec is invalid (all zeros)");
            }
        } else {
            ESP_LOGW(TAG, "K_JOIN not found in nvs_sec: %s", esp_err_to_name(k_err));
        }

        uint32_t net_id = 0;
        if (nvs_get_u32(sec_handle, "network_id", &net_id) == ESP_OK) {
            join_cfg.network_id = net_id;
        }
        nvs_close(sec_handle);
    } else {
        (void)esp_read_mac(join_cfg.device_mac, ESP_MAC_WIFI_STA);
        ESP_LOGI(TAG, "Using factory Wi-Fi MAC: %02x%02x%02x%02x%02x%02x",
                 join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                 join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5]);
        ESP_LOGW(TAG, "Namespace nvs_sec not found: %s", esp_err_to_name(sec_err));
    }

    /* Bind established session keys if already joined */
    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        mac_cfg.node_id = s_join_ctx.assigned_node_id;
        (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
        (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);
    }

    node_v2_join_radio_hal_t join_hal;
    (void)node_radio_hal_get_join_hal(&join_hal);

    /* 5. Initialize Airtime Policy & Crypto subsystem */
#ifdef CONFIG_NODE_AIRTIME_PERMILLE
    (void)airtime_policy_init((uint16_t)CONFIG_NODE_AIRTIME_PERMILLE);
#else
    (void)airtime_policy_init(10U); /* 1.0% regulatory duty cycle */
#endif
    (void)lora_mac_crypto_init();

    /* 6. Initialize button driver from Kconfig settings */
    button_config_t btn_cfg = {
        .gpio_num = (gpio_num_t)CONFIG_NODE_BUTTON_GPIO,
        .active_level = CONFIG_NODE_BUTTON_ACTIVE_LEVEL,
        .debounce_ms = CONFIG_NODE_BUTTON_DEBOUNCE_MS,
        .hold_time_ms = CONFIG_NODE_BUTTON_HOLD_TIME_MS,
    };

    esp_err_t btn_err = button_driver_init(&s_btn_driver, &btn_cfg);
    if (btn_err != ESP_OK) {
        ESP_LOGE(TAG, "Button driver initialization failed: %s", esp_err_to_name(btn_err));
    }

    /* 7. Identify wake-up cause */
    button_wakeup_cause_t wake_cause = button_driver_get_wakeup_cause();

    /* =========================================================================
     * UNJOINED FLOW (Issue #340)
     * When unjoined, the node MUST NOT automatically transmit RF on cold boot / reset.
     * It immediately enters Deep Sleep and only initiates Join upon GPIO button press.
     * ========================================================================= */
    if (s_join_ctx.state != NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        if (wake_cause != BUTTON_CAUSE_EXT0_BUTTON) {
            ESP_LOGI(TAG, "[UNJOINED BOOT] Cold boot or non-button wake detected (cause=%d) while UNJOINED.", (int)wake_cause);
            ESP_LOGI(TAG, "[UNJOINED BOOT] Putting radio to SLEEP, arming button GPIO %d, entering Deep-Sleep immediately.",
                     CONFIG_NODE_BUTTON_GPIO);

            if (sx1276_init(NULL, NULL) == ESP_OK) {
                (void)sx1276_sleep();
            }
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            (void)node_ui_show_unjoined();
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }

        /* Wake cause is EXT0 physical button press while UNJOINED */
        ESP_LOGI(TAG, "[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO %d while UNJOINED", CONFIG_NODE_BUTTON_GPIO);
        bool button_qualified = false;
        esp_err_t q_err = button_driver_qualify_press(&s_btn_driver, &button_qualified);
        if (q_err != ESP_OK || !button_qualified) {
            ESP_LOGW(TAG, "Transient wake without qualified button press (bounce/noise filtered). Returning to Deep-Sleep.");
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }

        /* Strict Fail-Closed Provisioning Verification (DEC-SEC-01, DEC-SEC-06, Issue #324) */
#if CONFIG_NODE_STRICT_PROVISIONING
        if (!k_join_loaded) {
            ESP_LOGE(TAG, "[PROVISION ERROR] Missing provisioned K_JOIN in nvs_sec. Halting radio.");
            s_join_ctx.state = NODE_V2_JOIN_STATE_ABORTED;
            lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
            if (sx1276_init(NULL, NULL) == ESP_OK) {
                (void)sx1276_sleep();
            }
            if (s_btn_driver.is_initialized) {
                (void)button_driver_arm_sleep(&s_btn_driver);
            }
            esp_deep_sleep_start();
            vTaskSuspend(NULL);
            return;
        }
#else
        if (!k_join_loaded) {
            ESP_LOGW(TAG, "[PROVISION WARN] Missing provisioned K_JOIN in nvs_sec, but strict provisioning is disabled (lab test mode).");
        }
#endif

        /* Initialize SX1276 radio for OTA V2 Join Handshake */
        if (!radio_initialized) {
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err == ESP_OK) {
                radio_initialized = true;
            } else {
                ESP_LOGE(TAG, "SX1276 initialization failed for join: %s", esp_err_to_name(sx_err));
            }
        }

        if (radio_initialized) {
            ESP_LOGI(TAG, "==================================================");
            ESP_LOGI(TAG, "[JOIN TRIGGER] Physical button press qualified on GPIO %d. Starting OTA V2 Join!", CONFIG_NODE_BUTTON_GPIO);
            ESP_LOGI(TAG, "[RF PHY CONFIG] Freq: 920.250 MHz | Channel: 0 (VN920) | SF: 7 | BW: 125 kHz | CR: 4/5 | Preamble: 8 | SyncWord: 0x12 | PA: PA_BOOST (+14 dBm)");
            ESP_LOGI(TAG, "[RF IDENTITY] Node MAC: %02X:%02X:%02X:%02X:%02X:%02X | Target GW: %u | Network ID: %" PRIu32,
                     join_cfg.device_mac[0], join_cfg.device_mac[1], join_cfg.device_mac[2],
                     join_cfg.device_mac[3], join_cfg.device_mac[4], join_cfg.device_mac[5],
                     join_cfg.target_gw_id, join_cfg.network_id);
            ESP_LOGI(TAG, "==================================================");

            esp_err_t join_err = node_v2_join_run(&join_cfg, &join_hal, &s_join_ctx);
            if (join_err == ESP_OK && s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
                ESP_LOGI(TAG, "==================================================");
                ESP_LOGI(TAG, ">>> V2 JOIN HANDSHAKE SUCCESSFUL! <<<");
                ESP_LOGI(TAG, "Assigned Node ID: #%u | State: %s",
                         s_join_ctx.assigned_node_id, node_v2_join_state_to_str(s_join_ctx.state));
                ESP_LOGI(TAG, "==================================================");
                mac_cfg.node_id = s_join_ctx.assigned_node_id;
                (void)memcpy(mac_cfg.k_session_up, s_join_ctx.session_keys.k_session_up, 16);
                (void)memcpy(mac_cfg.k_session_down, s_join_ctx.session_keys.k_session_dl, 16);

                /* Verify NVS persistence integrity */
                node_v2_join_context_t verify_ctx;
                (void)node_v2_join_init(&verify_ctx);
                if (node_v2_join_load_session(&verify_ctx) == ESP_OK) {
                    ESP_LOGI(TAG, "NVS session persistence verified: Node ID #%u, joined=1, keys 16B",
                             verify_ctx.assigned_node_id);
                } else {
                    ESP_LOGW(TAG, "NVS session verification failed after join commit");
                }
                lora_mac_crypto_zeroize(&verify_ctx.session_keys, sizeof(verify_ctx.session_keys));

                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)sx1276_sleep();
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
                (void)esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
#endif
                ESP_LOGI(TAG, "Node is JOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            } else if (node_v2_join_is_rejected(&s_join_ctx)) {
                ESP_LOGW(TAG, "==================================================");
                ESP_LOGW(TAG, ">>> V2 JOIN REJECTED BY GATEWAY/BACKEND! <<<");
                ESP_LOGW(TAG, "Putting radio to SLEEP, arming button GPIO %d, entering Deep-Sleep.", CONFIG_NODE_BUTTON_GPIO);
                ESP_LOGW(TAG, "==================================================");
                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)node_v2_join_erase_session(&s_join_ctx);
                s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
                (void)sx1276_sleep();
                (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
                (void)node_ui_show_unjoined();
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            } else {
                ESP_LOGW(TAG, "[JOIN ATTEMPT FAILED] %s (State: %s). Entering Deep-Sleep ready for next button press.",
                         esp_err_to_name(join_err), node_v2_join_state_to_str(s_join_ctx.state));
                lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));
                (void)node_v2_join_erase_session(&s_join_ctx);
                s_join_ctx.state = NODE_V2_JOIN_STATE_UNJOINED;
                (void)sx1276_sleep();
                (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
                if (s_btn_driver.is_initialized) {
                    (void)button_driver_arm_sleep(&s_btn_driver);
                }
                (void)node_ui_show_unjoined();
                esp_deep_sleep_start();
                vTaskSuspend(NULL);
                return;
            }
        }
    }

    /* =========================================================================
     * JOINED FLOW (Node has active session in INSTALLED_INACTIVE)
     * ========================================================================= */
    switch (wake_cause) {
        case BUTTON_CAUSE_EXT0_BUTTON: {
            ESP_LOGI(TAG, "[WAKE CAUSE] EXT0 Button Wakeup detected on GPIO %d (JOINED Node)", CONFIG_NODE_BUTTON_GPIO);
            bool qualified = false;
            esp_err_t q_err = button_driver_qualify_press(&s_btn_driver, &qualified);
            if (q_err == ESP_OK && qualified) {
                s_button_events++;
                uint32_t event_ref = 0;
                uint32_t now_sec = (uint32_t)(esp_timer_get_time() / 1000000ULL);
                int16_t rand_val = (int16_t)(80 + (esp_random() % 21));

                /* Event Code 0x01 = Manual Button Trigger, Value = rand_val (80..100) */
                esp_err_t push_err = node_event_fifo_push(&s_event_fifo, now_sec, 0x01, rand_val, &event_ref);
                if (push_err == ESP_OK) {
                    ESP_LOGI(TAG, ">>> EVENT ENQUEUED <<< Ref: %" PRIu32 ", Value: %d, Total button events: %" PRIu32,
                             event_ref, (int)rand_val, s_button_events);
                } else {
                    ESP_LOGW(TAG, "Failed to enqueue event: %s (FIFO dropped count: %" PRIu32 ")",
                             esp_err_to_name(push_err), node_event_fifo_get_dropped_count(&s_event_fifo));
                }

                /* Local OLED display update for confirmed button event */
                (void)node_ui_show_event(rand_val, now_sec, s_button_events);
            } else {
                ESP_LOGW(TAG, "Transient wake without qualified button press (bounce/noise filtered)");
            }
            break;
        }
        case BUTTON_CAUSE_TIMER:
            ESP_LOGI(TAG, "[WAKE CAUSE] Periodic Timer Wakeup (5-10 min Node Liveness Heartbeat)");
            if (!radio_initialized) {
                esp_err_t sx_err = sx1276_init(NULL, NULL);
                if (sx_err == ESP_OK) {
                    radio_initialized = true;
                } else {
                    ESP_LOGW(TAG, "SX1276 init for timer wakeup failed: %s", esp_err_to_name(sx_err));
                }
            }
            if (radio_initialized) {
                uint32_t slot_delay_ms = (uint32_t)mac_cfg.node_id * 40U;
                if (slot_delay_ms > 0) {
                    (void)node_smart_backoff(slot_delay_ms);
                }
                uint16_t hb_seq = (uint16_t)(esp_timer_get_time() / 1000000ULL);
                (void)node_send_heartbeat_ack(mac_cfg.node_id, hb_seq);
                bool revoked = false;
                (void)node_listen_downlink_revoke(&mac_cfg, 400, &revoked);
                if (revoked) {
                    node_handle_revoke_and_sleep(&s_btn_driver);
                }
            }
            break;
        default:
            ESP_LOGI(TAG, "[WAKE CAUSE] Power-On Reset or Software Restart with active session");
            if (!radio_initialized) {
                esp_err_t sx_err = sx1276_init(NULL, NULL);
                if (sx_err == ESP_OK) {
                    radio_initialized = true;
                    (void)sx1276_sleep();
                    ESP_LOGI(TAG, "[COLD BOOT] Radio placed in SLEEP mode (Session restored from NVS)");
                } else {
                    ESP_LOGW(TAG, "SX1276 init returned: %s (safe sleep default)", esp_err_to_name(sx_err));
                }
            }
            break;
    }

    size_t pending_events = node_event_fifo_get_pending_count(&s_event_fifo);
    ESP_LOGI(TAG, "FIFO State: Pending Events = %zu, Dropped Events = %" PRIu32,
             pending_events, node_event_fifo_get_dropped_count(&s_event_fifo));

    /* 9. Execute CAD + Random Backoff Event Transmission if joined and pending events exist */
    bool event_acked = false;
    if (pending_events > 0U) {
        if (!radio_initialized) {
            ESP_LOGI(TAG, "Initializing SX1276 radio for Event transmission");
            esp_err_t sx_err = sx1276_init(NULL, NULL);
            if (sx_err != ESP_OK) {
                ESP_LOGE(TAG, "SX1276 initialization failed: %s", esp_err_to_name(sx_err));
            } else {
                radio_initialized = true;
            }
        }

        if (radio_initialized) {
            esp_err_t cycle_err = node_cad_event_tx_and_ack(&mac_cfg, &s_event_fifo, &s_uplink_frame_counter, &event_acked);
            ESP_LOGI(TAG, "CAD Event cycle finished (status: %s, acked: %s, remaining pending: %zu)",
                     esp_err_to_name(cycle_err),
                     event_acked ? "true" : "false",
                     node_event_fifo_get_pending_count(&s_event_fifo));
            if (cycle_err == ESP_ERR_INVALID_STATE) {
                node_handle_revoke_and_sleep(&s_btn_driver);
            }
        }
    }

    /* 9b. Briefly listen for Gateway DOWN_HEARTBEAT_PROBE (150ms window) on active wakeups */
    if (wake_cause != BUTTON_CAUSE_RESET_OR_OTHER && radio_initialized && pending_events == 0U) {
        esp_err_t probe_err = node_listen_and_respond_probe(&mac_cfg, 150);
        if (probe_err == ESP_ERR_INVALID_STATE) {
            node_handle_revoke_and_sleep(&s_btn_driver);
        }
    }

    /* Zeroize sensitive join key before entering sleep/suspend */
    lora_mac_crypto_zeroize(join_cfg.k_join, sizeof(join_cfg.k_join));

    /* 10. Ensure radio is sleeping before entering Deep-Sleep */
    if (radio_initialized) {
        (void)sx1276_sleep();
    }

    /* 10b. Local UI Delivery Feedback: Pulse LED once if event was confirmed by Gateway */
    if (event_acked) {
        esp_err_t ui_err = node_ui_blink_event_ack();
        if (ui_err != ESP_OK) {
            ESP_LOGW(TAG, "Event delivery feedback LED failed: %s (non-fatal, continuing to sleep)",
                     esp_err_to_name(ui_err));
        }
    }

    /* 11. Enter Deep-Sleep */
    if (s_btn_driver.is_initialized) {
        (void)button_driver_arm_sleep(&s_btn_driver);
    }

#if CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC > 0
    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        ESP_LOGI(TAG, "Enabling Timer Wakeup in %d seconds", CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC);
        (void)esp_sleep_enable_timer_wakeup((uint64_t)CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC * 1000000ULL);
    } else {
        (void)esp_sleep_disable_wakeup_source(ESP_SLEEP_WAKEUP_TIMER);
    }
#endif

    if (s_join_ctx.state == NODE_V2_JOIN_STATE_INSTALLED_INACTIVE) {
        ESP_LOGI(TAG, "Node is JOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    } else {
        ESP_LOGI(TAG, "Node is UNJOINED. Entering Deep-Sleep mode. Press button on GPIO %d to wake up...", CONFIG_NODE_BUTTON_GPIO);
    }
    ESP_LOGI(TAG, "==================================================");

    esp_deep_sleep_start();
}
