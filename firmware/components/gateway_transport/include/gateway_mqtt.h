#ifndef GATEWAY_MQTT_H
#define GATEWAY_MQTT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

#define GATEWAY_MQTT_TOPIC_MAX_LEN 128
#define GATEWAY_MQTT_PEM_MAX_LEN   4096U

typedef void (*gateway_mqtt_status_cb_t)(bool connected);
typedef void (*gateway_mqtt_downlink_cb_t)(const char *topic, size_t topic_len, const uint8_t *data, size_t data_len);

typedef struct {
    char gateway_id[32];
    char broker_uri[128];
    const char *broker_ca_cert;     /* Broker CA cert PEM */
    const char *client_cert;        /* Gateway Client cert PEM */
    const char *client_key;         /* Gateway Client private key PEM */
    gateway_mqtt_status_cb_t status_cb;
    gateway_mqtt_downlink_cb_t downlink_cb;
} gateway_mqtt_config_t;

/**
 * @brief Initialize MQTT 5.0 client over mTLS with ADR-0002 protocol invariants.
 *
 * Enforces:
 * - Clean Start = 1
 * - Session Expiry Interval = 0
 * - Protocol Version = MQTT_PROTOCOL_V_5
 * - Client ID = iot/v1/gw/{gateway_id}
 *
 * @param config Pointer to MQTT configuration.
 * @return ESP_OK on success.
 */
esp_err_t gateway_mqtt_init(const gateway_mqtt_config_t *config);

/**
 * @brief Start MQTT client background task and initiate connection.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_mqtt_start(void);

/**
 * @brief Stop MQTT client and disconnect cleanly (ERR-003).
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_mqtt_stop(void);

/**
 * @brief Deinitialize and destroy MQTT client handle.
 *
 * @return ESP_OK on success.
 */
esp_err_t gateway_mqtt_deinit(void);

/**
 * @brief Check if MQTT 5.0 client is actively connected and authenticated.
 *
 * @return true if connected.
 */
bool gateway_mqtt_is_connected(void);

/**
 * @brief Publish a payload to a specified topic with QoS and retain flags.
 *
 * @param topic Target MQTT topic.
 * @param payload Raw payload data.
 * @param len Payload length.
 * @param qos Quality of Service (0 or 1).
 * @param retain Retain flag.
 * @return ESP_OK on success, ESP_ERR_INVALID_STATE if disconnected, or failure code.
 */
esp_err_t gateway_mqtt_publish(const char *topic, const uint8_t *payload, size_t len, int qos, int retain);

/**
 * @brief Pure helper function to construct canonical ClientID: "iot/v1/gw/{gateway_id}".
 *
 * @param out Output buffer.
 * @param max_len Size of output buffer.
 * @param gw_id Gateway identity string.
 * @return ESP_OK on success, ESP_ERR_INVALID_SIZE if truncated.
 */
esp_err_t gateway_mqtt_build_client_id(char *out, size_t max_len, const char *gw_id);

/**
 * @brief Pure helper function to construct canonical topic: "iot/v1/gw/{gateway_id}/{suffix}".
 *
 * @param out Output buffer.
 * @param max_len Size of output buffer.
 * @param gw_id Gateway identity string.
 * @param suffix Topic suffix (e.g. "uplink/alert", "downlink/schedule").
 * @return ESP_OK on success, ESP_ERR_INVALID_SIZE if truncated.
 */
esp_err_t gateway_mqtt_build_topic(char *out, size_t max_len, const char *gw_id, const char *suffix);

/**
 * @brief Check whether a broker URI selects TLS transport ("mqtts://" or "ssl://").
 *
 * @param broker_uri Null-terminated broker URI string.
 * @return true if TLS scheme, false otherwise.
 */
bool gateway_mqtt_is_tls_uri(const char *broker_uri);

/**
 * @brief Validate a null-terminated PEM certificate or private key buffer.
 *
 * Checks non-NULL, non-empty, null-termination within max_len, and valid
 * PEM BEGIN/END markers with non-empty body. Does not allocate memory.
 *
 * @param pem Pointer to null-terminated PEM text (caller retains ownership).
 * @param max_len Maximum allowed buffer length including NUL terminator.
 * @param is_private_key true to validate a PRIVATE KEY block, false for CERTIFICATE.
 * @return ESP_OK if valid, ESP_ERR_INVALID_ARG or ESP_ERR_INVALID_SIZE otherwise.
 */
esp_err_t gateway_mqtt_validate_pem(const char *pem, size_t max_len, bool is_private_key);

/**
 * @brief Resolve the canonical MQTT broker URI from override or host/port/TLS settings.
 *
 * If uri_override is non-empty, validates scheme ("mqtts://" or "mqtt://"),
 * rejects cleartext "mqtt://" downgrade when tls_enabled is true, and copies to out.
 * Otherwise builds "<scheme>://<host>:<port>" using "mqtts" when tls_enabled is true
 * or port == 8883, and "mqtt" only when tls_enabled is false and port != 8883.
 *
 * @param out Destination URI buffer.
 * @param max_len Size of destination buffer in bytes.
 * @param uri_override Optional full URI override (may be NULL or empty).
 * @param host Broker hostname or IPv4 address.
 * @param port Broker TCP port (1..65535).
 * @param tls_enabled Enforce TLS scheme and block cleartext downgrade.
 * @return ESP_OK on success, ESP_ERR_INVALID_ARG or ESP_ERR_INVALID_SIZE on failure.
 */
esp_err_t gateway_mqtt_resolve_broker_uri(char *out, size_t max_len,
                                          const char *uri_override,
                                          const char *host, uint16_t port,
                                          bool tls_enabled);

#ifdef __cplusplus
}
#endif

#endif /* GATEWAY_MQTT_H */
