#ifndef GATEWAY_TRANSPORT_H
#define GATEWAY_TRANSPORT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN 512
#define GATEWAY_TRANSPORT_QUEUE_CAPACITY  16
#define GATEWAY_ID_MAX_LEN                32

typedef enum {
    GATEWAY_TRANSPORT_STATUS_DISCONNECTED = 0,
    GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTING,
    GATEWAY_TRANSPORT_STATUS_WIFI_CONNECTED,
    GATEWAY_TRANSPORT_STATUS_MQTT_CONNECTING,
    GATEWAY_TRANSPORT_STATUS_MQTT_CONNECTED,
} gateway_transport_status_t;

typedef enum {
    GATEWAY_MSG_TYPE_EVENT = 0,       /* uplink/alert (V2 Event Plane) */
    GATEWAY_MSG_TYPE_SESSION_KEY_ACK, /* uplink/session-key-ack */
    GATEWAY_MSG_TYPE_JOIN_RELAY,      /* uplink/join-hello */
    GATEWAY_MSG_TYPE_STATUS,          /* uplink/status */
    GATEWAY_MSG_TYPE_SCHEDULE_ACK,    /* uplink/schedule-ack */
} gateway_msg_type_t;

typedef struct {
    char gateway_id[GATEWAY_ID_MAX_LEN];
    char wifi_ssid[32];
    char wifi_password[64];
    uint8_t wifi_max_retry;
    char broker_uri[128];
    const char *broker_ca_cert;     /* Broker CA cert in PEM format or NULL */
    const char *client_cert;        /* Device client cert in PEM format or NULL */
    const char *client_key;         /* Device private key in PEM format or NULL */
    bool disable_auto_connect;      /* Set to true to disable automatic WiFi/MQTT startup */
} gateway_transport_config_t;

/* Callback signatures for downlinks */
typedef void (*gateway_downlink_session_key_cb_t)(const uint8_t *data, size_t len);
typedef void (*gateway_downlink_schedule_cb_t)(const uint8_t *data, size_t len);

/**
 * @brief Initialize Gateway Transport subsystem (WiFi station, MQTT 5.0 client, queues, and worker task).
 *
 * @param cfg Configuration structure with credentials and endpoints.
 * @return ESP_OK on success, or an esp_err_t error code.
 */
esp_err_t gateway_transport_init(const gateway_transport_config_t *cfg);

/**
 * @brief Register callback for downlink session-key-install messages.
 *
 * @param cb Callback function.
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_register_session_key_callback(gateway_downlink_session_key_cb_t cb);

/**
 * @brief Register callback for downlink schedule messages.
 *
 * @param cb Callback function.
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_register_schedule_callback(gateway_downlink_schedule_cb_t cb);

/**
 * @brief Thread-safe non-blocking publish of an event alert to iot/v1/gw/{id}/uplink/alert.
 *
 * @param payload Raw JSON or serialized payload buffer.
 * @param len Payload length in bytes (must be <= GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN).
 * @return ESP_OK on success, ESP_ERR_NO_MEM if outbound queue full, ESP_ERR_INVALID_ARG on bad params.
 */
esp_err_t gateway_transport_publish_event(const uint8_t *payload, size_t len);

/**
 * @brief Thread-safe non-blocking publish of a session key ACK to iot/v1/gw/{id}/uplink/session-key-ack.
 *
 * @param payload Raw JSON or serialized payload buffer.
 * @param len Payload length in bytes.
 * @return ESP_OK on success, or error code.
 */
esp_err_t gateway_transport_publish_session_key_ack(const uint8_t *payload, size_t len);

/**
 * @brief Thread-safe non-blocking publish of a join relay (UP_JOIN_HELLO) to iot/v1/gw/{id}/uplink/join-hello.
 *
 * @param payload Raw JSON or serialized payload buffer.
 * @param len Payload length in bytes.
 * @return ESP_OK on success, or error code.
 */
esp_err_t gateway_transport_publish_join_relay(const uint8_t *payload, size_t len);

/**
 * @brief Thread-safe non-blocking publish of status snapshot to iot/v1/gw/{id}/uplink/status (retained).
 *
 * @param payload Raw JSON or serialized payload buffer.
 * @param len Payload length in bytes.
 * @return ESP_OK on success, or error code.
 */
esp_err_t gateway_transport_publish_status(const uint8_t *payload, size_t len);

/**
 * @brief Thread-safe non-blocking publish of schedule ACK to iot/v1/gw/{id}/uplink/schedule-ack.
 *
 * @param payload Raw JSON or serialized payload buffer.
 * @param len Payload length in bytes.
 * @return ESP_OK on success, or error code.
 */
esp_err_t gateway_transport_publish_schedule_ack(const uint8_t *payload, size_t len);

/**
 * @brief Get current transport connection status.
 */
gateway_transport_status_t gateway_transport_get_status(void);

/**
 * @brief Check if transport is fully connected (WiFi + MQTT 5.0 broker connected).
 */
bool gateway_transport_is_connected(void);

/**
 * @brief Get cumulative count of dropped events due to queue saturation or broker disconnect.
 */
uint32_t gateway_transport_get_dropped_events(void);

/**
 * @brief Get cumulative count of successfully published events.
 */
uint32_t gateway_transport_get_published_count(void);

/**
 * @brief Get current number of items buffered in outbound queue.
 */
uint32_t gateway_transport_get_queued_count(void);

/**
 * @brief Stop and deinitialize gateway transport subsystem, releasing resources cleanly.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_deinit(void);

#ifdef __cplusplus
}
#endif

#endif /* GATEWAY_TRANSPORT_H */
