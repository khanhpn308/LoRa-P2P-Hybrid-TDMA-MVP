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
    GATEWAY_MSG_TYPE_HEARTBEAT,       /* uplink/heartbeat (Binary Heartbeat Plane) */
} gateway_msg_type_t;

#define HEARTBEAT_TYPE_GATEWAY        (0x01)
#define HEARTBEAT_TYPE_NODES_BITMAP   (0x02)

typedef struct __attribute__((packed)) {
    uint8_t  type;             /* 0x01: HEARTBEAT_TYPE_GATEWAY */
    uint8_t  flags;            /* Bit 0: lora_ok, Bit 1: is_active */
    int8_t   wifi_rssi;        /* WiFi signal strength in dBm */
    uint8_t  reserved;         /* 0x00 */
    uint32_t uptime_s;         /* Uptime seconds */
    uint32_t free_heap_bytes;  /* Free RAM in bytes */
    uint32_t rx_events_count;  /* Total RX events */
} gateway_heartbeat_pkt_t;

typedef struct __attribute__((packed)) {
    uint8_t  type;             /* 0x02: HEARTBEAT_TYPE_NODES_BITMAP */
    uint8_t  node_count;       /* Total nodes tracked (e.g. 32) */
    uint8_t  bitmap[4];        /* Bitmap for 32 nodes (Bit k = Node k+1) */
    uint32_t timestamp;        /* Gateway timestamp */
} gateway_nodes_bitmap_pkt_t;

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
typedef void (*gateway_downlink_join_grant_cb_t)(const uint8_t *data, size_t len);
typedef void (*gateway_downlink_node_revoke_cb_t)(const uint8_t *data, size_t len);
typedef void (*gateway_transport_status_cb_t)(bool connected);

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
 * @brief Register callback for downlink join-grant messages from Backend.
 *
 * @param cb Callback function.
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_register_join_grant_callback(gateway_downlink_join_grant_cb_t cb);

/**
 * @brief Register callback for downlink node-revoke messages from Backend.
 *
 * @param cb Callback function.
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_register_node_revoke_callback(gateway_downlink_node_revoke_cb_t cb);

/**
 * @brief Register callback for transport connection status changes (WiFi + MQTT).
 *
 * @param cb Callback function.
 * @return ESP_OK on success.
 */
esp_err_t gateway_transport_register_status_callback(gateway_transport_status_cb_t cb);

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
 * @brief Thread-safe non-blocking publish of binary heartbeat to iot/v1/gw/{id}/uplink/heartbeat.
 *
 * @param payload Raw binary payload buffer.
 * @param len Payload length in bytes.
 * @return ESP_OK on success, or error code.
 */
esp_err_t gateway_transport_publish_heartbeat(const uint8_t *payload, size_t len);

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
 * @brief Get current WiFi RSSI in dBm.
 */
int8_t gateway_transport_get_wifi_rssi(void);

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
