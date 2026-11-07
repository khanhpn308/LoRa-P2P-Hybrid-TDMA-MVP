#include "gateway_mqtt.h"
#include <stdio.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "esp_log.h"
#include "mqtt_client.h"
#include "mqtt5_client.h"
#endif

#ifndef ESP_PLATFORM
#include "esp_log.h"
#endif

static const char *TAG __attribute__((unused)) = "gateway_mqtt";

static gateway_mqtt_config_t s_config;
static bool s_initialized = false;
static bool s_running = false;
static bool s_connected = false;

#ifdef ESP_PLATFORM
static esp_mqtt_client_handle_t s_mqtt_client = NULL;
static char s_client_id[64];
static char s_sub_topic_session_key[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_sub_topic_schedule[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_pub_topic_status[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_will_msg[128];
static char s_birth_msg[128];

static void mqtt5_event_handler(void *handler_args, esp_event_base_t base,
                                int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    esp_mqtt_client_handle_t client = event->client;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT 5.0 client connected successfully");
        s_connected = true;

        /* Subscribe to downlink topics with QoS 1 */
        int sub_id1 = esp_mqtt_client_subscribe(client, s_sub_topic_session_key, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_session_key, sub_id1);

        int sub_id2 = esp_mqtt_client_subscribe(client, s_sub_topic_schedule, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_schedule, sub_id2);

        /* Publish retained birth/online status */
        int pub_id = esp_mqtt_client_publish(client, s_pub_topic_status,
                                            s_birth_msg, (int)strlen(s_birth_msg),
                                            1, 1);
        ESP_LOGI(TAG, "Published birth status to %s (msg_id=%d)", s_pub_topic_status, pub_id);

        if (s_config.status_cb) {
            s_config.status_cb(true);
        }
        break;

    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT client disconnected");
        s_connected = false;
        if (s_config.status_cb) {
            s_config.status_cb(false);
        }
        break;

    case MQTT_EVENT_SUBSCRIBED:
        ESP_LOGI(TAG, "MQTT_EVENT_SUBSCRIBED (msg_id=%d)", event->msg_id);
        break;

    case MQTT_EVENT_UNSUBSCRIBED:
        ESP_LOGI(TAG, "MQTT_EVENT_UNSUBSCRIBED (msg_id=%d)", event->msg_id);
        break;

    case MQTT_EVENT_PUBLISHED:
        ESP_LOGD(TAG, "MQTT_EVENT_PUBLISHED (msg_id=%d)", event->msg_id);
        break;

    case MQTT_EVENT_DATA:
        ESP_LOGI(TAG, "MQTT_EVENT_DATA received: topic_len=%d, data_len=%d",
                 event->topic_len, event->data_len);
        if (s_config.downlink_cb && event->topic_len > 0 && event->data_len >= 0) {
            s_config.downlink_cb(event->topic, (size_t)event->topic_len,
                                 (const uint8_t *)event->data, (size_t)event->data_len);
        }
        break;

    case MQTT_EVENT_ERROR:
        ESP_LOGE(TAG, "MQTT_EVENT_ERROR occurred");
        if (event->error_handle) {
            ESP_LOGE(TAG, "Connect return code: %d, error type: %d",
                     event->error_handle->connect_return_code,
                     event->error_handle->error_type);
        }
        break;

    default:
        ESP_LOGD(TAG, "Unhandled MQTT event id:%d", event->event_id);
        break;
    }
}
#endif /* ESP_PLATFORM */

esp_err_t gateway_mqtt_build_client_id(char *out, size_t max_len, const char *gw_id)
{
    if (out == NULL || max_len == 0 || gw_id == NULL || gw_id[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }
    int ret = snprintf(out, max_len, "iot/v1/gw/%s", gw_id);
    if (ret < 0 || (size_t)ret >= max_len) {
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

esp_err_t gateway_mqtt_build_topic(char *out, size_t max_len, const char *gw_id, const char *suffix)
{
    if (out == NULL || max_len == 0 || gw_id == NULL || suffix == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    int ret = snprintf(out, max_len, "iot/v1/gw/%s/%s", gw_id, suffix);
    if (ret < 0 || (size_t)ret >= max_len) {
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

esp_err_t gateway_mqtt_init(const gateway_mqtt_config_t *config)
{
    if (config == NULL || config->gateway_id[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_initialized) {
        return ESP_OK;
    }

    memset(&s_config, 0, sizeof(s_config));
    strncpy(s_config.gateway_id, config->gateway_id, sizeof(s_config.gateway_id) - 1);
    if (config->broker_uri[0] != '\0') {
        strncpy(s_config.broker_uri, config->broker_uri, sizeof(s_config.broker_uri) - 1);
    } else {
        snprintf(s_config.broker_uri, sizeof(s_config.broker_uri), "mqtts://192.168.1.10:8883");
    }
    s_config.broker_ca_cert = config->broker_ca_cert;
    s_config.client_cert = config->client_cert;
    s_config.client_key = config->client_key;
    s_config.status_cb = config->status_cb;
    s_config.downlink_cb = config->downlink_cb;

    s_connected = false;

#ifdef ESP_PLATFORM
    esp_err_t err;

    err = gateway_mqtt_build_client_id(s_client_id, sizeof(s_client_id), s_config.gateway_id);
    if (err != ESP_OK) {
        return err;
    }

    err = gateway_mqtt_build_topic(s_sub_topic_session_key, sizeof(s_sub_topic_session_key),
                                   s_config.gateway_id, "downlink/session-key-install");
    if (err != ESP_OK) return err;

    err = gateway_mqtt_build_topic(s_sub_topic_schedule, sizeof(s_sub_topic_schedule),
                                   s_config.gateway_id, "downlink/schedule");
    if (err != ESP_OK) return err;

    err = gateway_mqtt_build_topic(s_pub_topic_status, sizeof(s_pub_topic_status),
                                   s_config.gateway_id, "uplink/status");
    if (err != ESP_OK) return err;

    snprintf(s_will_msg, sizeof(s_will_msg),
             "{\"gateway_id\":\"%s\",\"status\":\"offline\",\"schema_version\":\"1.0-draft\"}",
             s_config.gateway_id);

    snprintf(s_birth_msg, sizeof(s_birth_msg),
             "{\"gateway_id\":\"%s\",\"status\":\"online\",\"schema_version\":\"1.0-draft\"}",
             s_config.gateway_id);

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker = {
            .address.uri = s_config.broker_uri,
            .verification.certificate = s_config.broker_ca_cert,
        },
        .credentials = {
            .client_id = s_client_id,
            .authentication = {
                .certificate = s_config.client_cert,
                .key = s_config.client_key,
            },
        },
        .session = {
            .protocol_ver = MQTT_PROTOCOL_V_5,
            .disable_clean_session = false, /* Clean Start = 1 per ADR-0002 */
            .last_will = {
                .topic = s_pub_topic_status,
                .msg = s_will_msg,
                .msg_len = (int)strlen(s_will_msg),
                .qos = 1,
                .retain = true,
            },
        },
        .network = {
            .timeout_ms = 10000,
            .reconnect_timeout_ms = 5000,
        },
    };

    s_mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    if (s_mqtt_client == NULL) {
        ESP_LOGE(TAG, "Failed to initialize ESP-MQTT client");
        return ESP_FAIL;
    }

    /* Configure ADR-0002 protocol invariants: Session Expiry Interval = 0 */
    esp_mqtt5_connection_property_config_t connect_property = {
        .session_expiry_interval = 0,
    };
    esp_mqtt5_client_set_connect_property(s_mqtt_client, &connect_property);

    err = esp_mqtt_client_register_event(s_mqtt_client, ESP_EVENT_ANY_ID, mqtt5_event_handler, NULL);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to register MQTT event handler: %s", esp_err_to_name(err));
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
        return err;
    }
#endif /* ESP_PLATFORM */

    s_initialized = true;
    return ESP_OK;
}

esp_err_t gateway_mqtt_start(void)
{
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }

    s_running = true;

#ifdef ESP_PLATFORM
    if (s_mqtt_client) {
        esp_err_t err = esp_mqtt_client_start(s_mqtt_client);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_mqtt_client_start failed: %s", esp_err_to_name(err));
            s_running = false;
            return err;
        }
    }
#endif

    return ESP_OK;
}

esp_err_t gateway_mqtt_stop(void)
{
    if (!s_initialized || !s_running) {
        return ESP_OK;
    }

    s_running = false;
    s_connected = false;

#ifdef ESP_PLATFORM
    if (s_mqtt_client) {
        /* Clean socket shutdown on reconnect / stop (ERR-003) */
        esp_mqtt_client_stop(s_mqtt_client);
    }
#endif

    return ESP_OK;
}

esp_err_t gateway_mqtt_deinit(void)
{
    if (!s_initialized) {
        return ESP_OK;
    }

    gateway_mqtt_stop();

#ifdef ESP_PLATFORM
    if (s_mqtt_client) {
        esp_mqtt_client_destroy(s_mqtt_client);
        s_mqtt_client = NULL;
    }
#endif

    s_initialized = false;
    return ESP_OK;
}

bool gateway_mqtt_is_connected(void)
{
    return s_connected;
}

esp_err_t gateway_mqtt_publish(const char *topic, const uint8_t *payload, size_t len, int qos, int retain)
{
    if (topic == NULL || payload == NULL || len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    if (!s_connected) {
        return ESP_ERR_INVALID_STATE;
    }

#ifdef ESP_PLATFORM
    if (s_mqtt_client == NULL) {
        return ESP_ERR_INVALID_STATE;
    }

    int msg_id = esp_mqtt_client_publish(s_mqtt_client, topic,
                                         (const char *)payload, (int)len,
                                         qos, retain);
    if (msg_id < 0) {
        ESP_LOGE(TAG, "esp_mqtt_client_publish failed to topic: %s", topic);
        return ESP_FAIL;
    }
    ESP_LOGD(TAG, "Published %zu bytes to %s (msg_id=%d)", len, topic, msg_id);
    return ESP_OK;
#else
    (void)topic;
    (void)payload;
    (void)len;
    (void)qos;
    (void)retain;
    return ESP_OK;
#endif
}
