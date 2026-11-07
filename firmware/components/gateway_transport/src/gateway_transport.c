#include "gateway_transport.h"
#include "gateway_wifi.h"
#include "gateway_mqtt.h"
#include <string.h>

#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#endif

#ifndef ESP_PLATFORM
#include "esp_log.h"
#endif

static const char *TAG __attribute__((unused)) = "gateway_transport";

typedef struct {
    gateway_msg_type_t type;
    uint16_t len;
    uint8_t payload[GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN];
} gateway_outbound_msg_t;

static gateway_transport_config_t s_config;
static bool s_initialized = false;
static gateway_transport_status_t s_status = GATEWAY_TRANSPORT_STATUS_DISCONNECTED;

static gateway_downlink_session_key_cb_t s_session_key_cb = NULL;
static gateway_downlink_schedule_cb_t s_schedule_cb = NULL;

static uint32_t s_dropped_events = 0;
static uint32_t s_published_events = 0;
static uint32_t s_queued_events = 0;

#ifdef ESP_PLATFORM
static QueueHandle_t s_outbound_queue = NULL;
static TaskHandle_t s_transport_task_handle = NULL;
static SemaphoreHandle_t s_state_mutex = NULL;
static volatile bool s_task_running = false;

static void transport_task(void *pvParameters)
{
    (void)pvParameters;
    gateway_outbound_msg_t msg;
    char topic[GATEWAY_MQTT_TOPIC_MAX_LEN];

    ESP_LOGI(TAG, "Gateway transport worker task started");

    while (s_task_running) {
        if (!gateway_mqtt_is_connected()) {
            /* While disconnected, hold messages in queue up to capacity (MEM-002) */
            vTaskDelay(pdMS_TO_TICKS(50));
            continue;
        }

        if (xQueueReceive(s_outbound_queue, &msg, pdMS_TO_TICKS(100)) == pdTRUE) {
            const char *suffix = NULL;
            int retain = 0;

            switch (msg.type) {
            case GATEWAY_MSG_TYPE_EVENT:
                suffix = "uplink/alert";
                retain = 0;
                break;
            case GATEWAY_MSG_TYPE_SESSION_KEY_ACK:
                suffix = "uplink/session-key-ack";
                retain = 0;
                break;
            case GATEWAY_MSG_TYPE_JOIN_RELAY:
                suffix = "uplink/join-hello";
                retain = 0;
                break;
            case GATEWAY_MSG_TYPE_STATUS:
                suffix = "uplink/status";
                retain = 1; /* Status is retained per contract */
                break;
            case GATEWAY_MSG_TYPE_SCHEDULE_ACK:
                suffix = "uplink/schedule-ack";
                retain = 0;
                break;
            default:
                suffix = "uplink/unknown";
                break;
            }

            esp_err_t err = gateway_mqtt_build_topic(topic, sizeof(topic),
                                                     s_config.gateway_id, suffix);
            if (err == ESP_OK) {
                err = gateway_mqtt_publish(topic, msg.payload, msg.len, 1, retain);
                if (err == ESP_OK) {
                    s_published_events++;
                } else {
                    s_dropped_events++;
                    ESP_LOGW(TAG, "Failed to publish message: %s", esp_err_to_name(err));
                }
            } else {
                s_dropped_events++;
            }

            /* Zeroize sensitive temporary buffer (SEC-005) */
            memset(&msg, 0, sizeof(msg));
        }
    }

    ESP_LOGI(TAG, "Gateway transport worker task terminating");
    vTaskDelete(NULL);
}
#endif /* ESP_PLATFORM */

static void on_wifi_event(bool connected, bool got_ip)
{
    ESP_LOGI(TAG, "WiFi event notification: connected=%d, got_ip=%d", connected, got_ip);
    if (connected && got_ip) {
        s_status = GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTED;
        ESP_LOGI(TAG, "WiFi ready, starting MQTT client...");
        s_status = GATEWAY_TRANSPORT_STATUS_MQTT_CONNECTING;
        gateway_mqtt_start();
    } else {
        s_status = GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTING;
        gateway_mqtt_stop();
    }
}

static void on_mqtt_status(bool connected)
{
    ESP_LOGI(TAG, "MQTT status notification: connected=%d", connected);
    if (connected) {
        s_status = GATEWAY_TRANSPORT_STATUS_MQTT_CONNECTED;
    } else {
        if (gateway_wifi_is_connected()) {
            s_status = GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTED;
        } else {
            s_status = GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTING;
        }
    }
}

static void on_mqtt_downlink(const char *topic, size_t topic_len,
                             const uint8_t *data, size_t data_len)
{
    if (topic == NULL || topic_len == 0 || data == NULL) {
        return;
    }

    char topic_buf[GATEWAY_MQTT_TOPIC_MAX_LEN];
    if (topic_len >= sizeof(topic_buf)) {
        ESP_LOGE(TAG, "Downlink topic length exceeds buffer: %zu", topic_len);
        return;
    }
    memcpy(topic_buf, topic, topic_len);
    topic_buf[topic_len] = '\0';

    ESP_LOGI(TAG, "Processing downlink on topic: %s (%zu bytes)", topic_buf, data_len);

    if (strstr(topic_buf, "downlink/session-key-install") != NULL) {
        if (s_session_key_cb) {
            s_session_key_cb(data, data_len);
        }
    } else if (strstr(topic_buf, "downlink/schedule") != NULL) {
        if (s_schedule_cb) {
            s_schedule_cb(data, data_len);
        }
    } else {
        ESP_LOGW(TAG, "Unhandled downlink topic: %s", topic_buf);
    }
}

static esp_err_t enqueue_outbound(gateway_msg_type_t type, const uint8_t *payload, size_t len)
{
    if (payload == NULL || len == 0 || len > GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

#ifdef ESP_PLATFORM
    if (s_outbound_queue == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    gateway_outbound_msg_t msg;
    msg.type = type;
    msg.len = (uint16_t)len;
    memcpy(msg.payload, payload, len);

    /* Non-blocking queue send (timeout=0) to guarantee zero radio slot jitter (RTOS-001) */
    BaseType_t res = xQueueSend(s_outbound_queue, &msg, 0);
    if (res != pdTRUE) {
        s_dropped_events++;
        ESP_LOGW(TAG, "Outbound queue full (cap=%d), dropping event (total dropped=%" PRIu32 ")",
                 GATEWAY_TRANSPORT_QUEUE_CAPACITY, s_dropped_events);
        return ESP_ERR_NO_MEM;
    }

    s_queued_events++;
    return ESP_OK;
#else
    (void)type;
    (void)payload;
    (void)len;
    s_queued_events++;
    return ESP_OK;
#endif
}

esp_err_t gateway_transport_init(const gateway_transport_config_t *cfg)
{
    if (cfg == NULL || cfg->gateway_id[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_initialized) {
        return ESP_OK;
    }

    memset(&s_config, 0, sizeof(s_config));
    memcpy(&s_config, cfg, sizeof(gateway_transport_config_t));

    s_status = GATEWAY_TRANSPORT_STATUS_DISCONNECTED;
    s_dropped_events = 0;
    s_published_events = 0;
    s_queued_events = 0;

#ifdef ESP_PLATFORM
    s_state_mutex = xSemaphoreCreateMutex();
    if (s_state_mutex == NULL) {
        return ESP_ERR_NO_MEM;
    }

    s_outbound_queue = xQueueCreate(GATEWAY_TRANSPORT_QUEUE_CAPACITY,
                                    sizeof(gateway_outbound_msg_t));
    if (s_outbound_queue == NULL) {
        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;
        return ESP_ERR_NO_MEM;
    }

    s_task_running = true;
    BaseType_t task_ret = xTaskCreate(transport_task,
                                      "gw_transport",
                                      8192, /* Stack size 8KB per MEM-004 */
                                      NULL,
                                      4,    /* Priority 4, below high-res TDMA/ISR (RTOS-001) */
                                      &s_transport_task_handle);
    if (task_ret != pdPASS) {
        s_task_running = false;
        vQueueDelete(s_outbound_queue);
        s_outbound_queue = NULL;
        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;
        return ESP_ERR_NO_MEM;
    }
#endif

    gateway_mqtt_config_t mqtt_cfg = {
        .broker_ca_cert = cfg->broker_ca_cert,
        .client_cert = cfg->client_cert,
        .client_key = cfg->client_key,
        .status_cb = &on_mqtt_status,
        .downlink_cb = &on_mqtt_downlink,
    };
    strncpy(mqtt_cfg.gateway_id, cfg->gateway_id, sizeof(mqtt_cfg.gateway_id) - 1);
    strncpy(mqtt_cfg.broker_uri, cfg->broker_uri, sizeof(mqtt_cfg.broker_uri) - 1);

    esp_err_t err = gateway_mqtt_init(&mqtt_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "gateway_mqtt_init failed: %s", esp_err_to_name(err));
        return err;
    }

    gateway_wifi_config_t wifi_cfg = {
        .max_retry = cfg->wifi_max_retry,
        .event_cb = &on_wifi_event,
    };
    strncpy(wifi_cfg.ssid, cfg->wifi_ssid, sizeof(wifi_cfg.ssid) - 1);
    strncpy(wifi_cfg.password, cfg->wifi_password, sizeof(wifi_cfg.password) - 1);

    err = gateway_wifi_init(&wifi_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "gateway_wifi_init failed: %s", esp_err_to_name(err));
        gateway_mqtt_deinit();
        return err;
    }

    s_initialized = true;

    if (!cfg->disable_auto_connect) {
        s_status = GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTING;
        err = gateway_wifi_start();
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "gateway_wifi_start returned %s", esp_err_to_name(err));
        }
    }

    return ESP_OK;
}

esp_err_t gateway_transport_register_session_key_callback(gateway_downlink_session_key_cb_t cb)
{
    s_session_key_cb = cb;
    return ESP_OK;
}

esp_err_t gateway_transport_register_schedule_callback(gateway_downlink_schedule_cb_t cb)
{
    s_schedule_cb = cb;
    return ESP_OK;
}

esp_err_t gateway_transport_publish_event(const uint8_t *payload, size_t len)
{
    return enqueue_outbound(GATEWAY_MSG_TYPE_EVENT, payload, len);
}

esp_err_t gateway_transport_publish_session_key_ack(const uint8_t *payload, size_t len)
{
    return enqueue_outbound(GATEWAY_MSG_TYPE_SESSION_KEY_ACK, payload, len);
}

esp_err_t gateway_transport_publish_join_relay(const uint8_t *payload, size_t len)
{
    return enqueue_outbound(GATEWAY_MSG_TYPE_JOIN_RELAY, payload, len);
}

esp_err_t gateway_transport_publish_status(const uint8_t *payload, size_t len)
{
    return enqueue_outbound(GATEWAY_MSG_TYPE_STATUS, payload, len);
}

esp_err_t gateway_transport_publish_schedule_ack(const uint8_t *payload, size_t len)
{
    return enqueue_outbound(GATEWAY_MSG_TYPE_SCHEDULE_ACK, payload, len);
}

gateway_transport_status_t gateway_transport_get_status(void)
{
    return s_status;
}

bool gateway_transport_is_connected(void)
{
    return (s_status == GATEWAY_TRANSPORT_STATUS_MQTT_CONNECTED);
}

uint32_t gateway_transport_get_dropped_events(void)
{
    return s_dropped_events;
}

uint32_t gateway_transport_get_published_count(void)
{
    return s_published_events;
}

uint32_t gateway_transport_get_queued_count(void)
{
    return s_queued_events;
}

esp_err_t gateway_transport_deinit(void)
{
    if (!s_initialized) {
        return ESP_OK;
    }

    gateway_wifi_stop();
    gateway_wifi_deinit();

    gateway_mqtt_stop();
    gateway_mqtt_deinit();

#ifdef ESP_PLATFORM
    s_task_running = false;
    if (s_transport_task_handle) {
        vTaskDelay(pdMS_TO_TICKS(150));
        s_transport_task_handle = NULL;
    }

    if (s_outbound_queue) {
        vQueueDelete(s_outbound_queue);
        s_outbound_queue = NULL;
    }

    if (s_state_mutex) {
        vSemaphoreDelete(s_state_mutex);
        s_state_mutex = NULL;
    }
#endif

    s_status = GATEWAY_TRANSPORT_STATUS_DISCONNECTED;
    s_initialized = false;
    return ESP_OK;
}
