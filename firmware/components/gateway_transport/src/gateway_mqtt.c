#include "gateway_mqtt.h"
#include <stdio.h>
#include <string.h>

#ifdef ESP_PLATFORM
#include "esp_log.h"
#include "mbedtls/x509_crt.h"
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
static char s_sub_topic_join_grant[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_sub_topic_join_wait[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_sub_topic_join_reject[GATEWAY_MQTT_TOPIC_MAX_LEN];
static char s_sub_topic_node_revoke[GATEWAY_MQTT_TOPIC_MAX_LEN];
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

        int sub_id3 = esp_mqtt_client_subscribe(client, s_sub_topic_join_grant, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_join_grant, sub_id3);

        int sub_id4 = esp_mqtt_client_subscribe(client, s_sub_topic_join_wait, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_join_wait, sub_id4);

        int sub_id5 = esp_mqtt_client_subscribe(client, s_sub_topic_join_reject, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_join_reject, sub_id5);

        int sub_id6 = esp_mqtt_client_subscribe(client, s_sub_topic_node_revoke, 1);
        ESP_LOGI(TAG, "Subscribed to %s (msg_id=%d)", s_sub_topic_node_revoke, sub_id6);

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
            ESP_LOGE(TAG,
                     "Connect return code: %d, error type: %d, tls_esp_err: 0x%x, tls_stack_err: 0x%x, cert_flags: 0x%x, sock_errno: %d",
                     event->error_handle->connect_return_code,
                     event->error_handle->error_type,
                     (unsigned int)event->error_handle->esp_tls_last_esp_err,
                     event->error_handle->esp_tls_stack_err,
                     event->error_handle->esp_tls_cert_verify_flags,
                     event->error_handle->esp_transport_sock_errno);
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

static size_t bounded_strnlen(const char *s, size_t max_len)
{
    size_t len = 0;
    while (len < max_len && s[len] != '\0') {
        len++;
    }
    return len;
}

static bool has_valid_uri_host(const char *host)
{
    if (host == NULL || host[0] == '\0') {
        return false;
    }
    for (size_t i = 0; host[i] != '\0'; i++) {
        unsigned char c = (unsigned char)host[i];
        if (c <= 0x20U || c == '/' || c == '\\' || c == '?' || c == '#') {
            return false;
        }
    }
    if (strstr(host, "://") != NULL) {
        return false;
    }
    return true;
}

static bool is_supported_broker_uri(const char *uri, bool *out_is_tls)
{
    if (uri == NULL || uri[0] == '\0') {
        return false;
    }

    const char *rest = NULL;
    bool is_tls = false;
    if (strncmp(uri, "mqtts://", 8) == 0) {
        rest = uri + 8;
        is_tls = true;
    } else if (strncmp(uri, "ssl://", 6) == 0) {
        rest = uri + 6;
        is_tls = true;
    } else if (strncmp(uri, "mqtt://", 7) == 0) {
        rest = uri + 7;
        is_tls = false;
    } else {
        return false;
    }

    if (rest[0] == '\0') {
        return false;
    }

    for (size_t i = 0; rest[i] != '\0'; i++) {
        unsigned char c = (unsigned char)rest[i];
        if (c <= 0x20U || c == '\\') {
            return false;
        }
    }

    if (out_is_tls != NULL) {
        *out_is_tls = is_tls;
    }
    return true;
}

bool gateway_mqtt_is_tls_uri(const char *broker_uri)
{
    bool is_tls = false;
    if (!is_supported_broker_uri(broker_uri, &is_tls)) {
        return false;
    }
    return is_tls;
}

esp_err_t gateway_mqtt_validate_pem(const char *pem, size_t max_len, bool is_private_key)
{
    if (pem == NULL || max_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t len = bounded_strnlen(pem, max_len);
    if (len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    if (len >= max_len) {
        /* Not NUL-terminated within max_len */
        return ESP_ERR_INVALID_SIZE;
    }

    static const char k_begin_prefix[] = "-----BEGIN ";
    static const char k_end_prefix[] = "-----END ";
    static const char k_cert_suffix[] = "CERTIFICATE-----";
    static const char k_key_suffix[] = "PRIVATE KEY-----";
    const char *expected_suffix = is_private_key ? k_key_suffix : k_cert_suffix;

    const char *begin = strstr(pem, k_begin_prefix);
    if (begin == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *begin_line_end = strchr(begin, '\n');
    if (begin_line_end == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *begin_suffix = strstr(begin, expected_suffix);
    if (begin_suffix == NULL || begin_suffix > begin_line_end) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *end = strstr(begin_line_end + 1, k_end_prefix);
    if (end == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    const char *end_suffix = strstr(end, expected_suffix);
    if (end_suffix == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Require at least one non-whitespace Base64 body character between header and footer */
    bool has_body = false;
    for (const char *p = begin_line_end + 1; p < end; p++) {
        unsigned char c = (unsigned char)*p;
        if (c > 0x20U) {
            has_body = true;
            break;
        }
    }
    if (!has_body) {
        return ESP_ERR_INVALID_ARG;
    }

    return ESP_OK;
}

esp_err_t gateway_mqtt_resolve_broker_uri(char *out, size_t max_len,
                                          const char *uri_override,
                                          const char *host, uint16_t port,
                                          bool tls_enabled)
{
    if (out == NULL || max_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }
    out[0] = '\0';

    if (uri_override != NULL && uri_override[0] != '\0') {
        bool uri_is_tls = false;
        if (!is_supported_broker_uri(uri_override, &uri_is_tls)) {
            return ESP_ERR_INVALID_ARG;
        }
        if (tls_enabled && !uri_is_tls) {
            /* Fail closed: never allow silent cleartext downgrade when TLS is enabled */
            return ESP_ERR_INVALID_ARG;
        }
        int ret = snprintf(out, max_len, "%s", uri_override);
        if (ret < 0 || (size_t)ret >= max_len) {
            out[0] = '\0';
            return ESP_ERR_INVALID_SIZE;
        }
        return ESP_OK;
    }

    if (!has_valid_uri_host(host) || port == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    bool use_tls = tls_enabled || (port == 8883U);
    const char *scheme = use_tls ? "mqtts" : "mqtt";
    int ret = snprintf(out, max_len, "%s://%s:%u", scheme, host, (unsigned int)port);
    if (ret < 0 || (size_t)ret >= max_len) {
        out[0] = '\0';
        return ESP_ERR_INVALID_SIZE;
    }
    return ESP_OK;
}

#ifdef ESP_PLATFORM
static esp_err_t verify_x509_certs_and_identity(const char *ca_pem,
                                                const char *client_pem,
                                                const char *expected_gw_id)
{
    mbedtls_x509_crt ca_crt;
    mbedtls_x509_crt client_crt;
    mbedtls_x509_crt_init(&ca_crt);
    mbedtls_x509_crt_init(&client_crt);

    int ret = mbedtls_x509_crt_parse(&ca_crt,
                                     (const unsigned char *)ca_pem,
                                     strlen(ca_pem) + 1);
    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to parse broker CA X.509 certificate (mbedtls -0x%04x)", (unsigned int)(-ret));
        mbedtls_x509_crt_free(&ca_crt);
        mbedtls_x509_crt_free(&client_crt);
        return ESP_ERR_INVALID_ARG;
    }

    ret = mbedtls_x509_crt_parse(&client_crt,
                                 (const unsigned char *)client_pem,
                                 strlen(client_pem) + 1);
    if (ret != 0) {
        ESP_LOGE(TAG, "Failed to parse gateway client X.509 certificate (mbedtls -0x%04x)", (unsigned int)(-ret));
        mbedtls_x509_crt_free(&ca_crt);
        mbedtls_x509_crt_free(&client_crt);
        return ESP_ERR_INVALID_ARG;
    }

    /* Verify client certificate CN matches configured gateway_id (Mosquitto use_identity_as_username) */
    bool cn_found = false;
    bool cn_matched = false;
    size_t expected_len = strlen(expected_gw_id);
    static const unsigned char k_oid_at_cn[3] = {0x55U, 0x04U, 0x03U};
    for (const mbedtls_x509_name *name = &client_crt.subject; name != NULL; name = name->next) {
        if (name->oid.len == sizeof(k_oid_at_cn) &&
            memcmp(name->oid.p, k_oid_at_cn, sizeof(k_oid_at_cn)) == 0) {
            cn_found = true;
            if (name->val.len == expected_len &&
                memcmp(name->val.p, expected_gw_id, expected_len) == 0) {
                cn_matched = true;
                break;
            }
        }
    }

    mbedtls_x509_crt_free(&ca_crt);
    mbedtls_x509_crt_free(&client_crt);

    if (!cn_found || !cn_matched) {
        ESP_LOGE(TAG, "Client certificate CN does not match gateway_id '%s'", expected_gw_id);
        return ESP_ERR_INVALID_ARG;
    }
    return ESP_OK;
}
#endif

esp_err_t gateway_mqtt_init(const gateway_mqtt_config_t *config)
{
    if (config == NULL || config->gateway_id[0] == '\0') {
        return ESP_ERR_INVALID_ARG;
    }

    if (s_initialized) {
        return ESP_OK;
    }

    bool uri_is_tls = false;
    if (!is_supported_broker_uri(config->broker_uri, &uri_is_tls)) {
        ESP_LOGE(TAG, "Missing or invalid MQTT broker URI; refusing hardcoded fallback");
        return ESP_ERR_INVALID_ARG;
    }

    if (uri_is_tls) {
        if (gateway_mqtt_validate_pem(config->broker_ca_cert, GATEWAY_MQTT_PEM_MAX_LEN, false) != ESP_OK ||
            gateway_mqtt_validate_pem(config->client_cert, GATEWAY_MQTT_PEM_MAX_LEN, false) != ESP_OK ||
            gateway_mqtt_validate_pem(config->client_key, GATEWAY_MQTT_PEM_MAX_LEN, true) != ESP_OK) {
            ESP_LOGE(TAG, "Fail-closed: mqtts:// requires valid non-empty PEM CA cert, client cert, and client key");
            return ESP_ERR_INVALID_ARG;
        }
#ifdef ESP_PLATFORM
        esp_err_t x509_err = verify_x509_certs_and_identity(config->broker_ca_cert,
                                                            config->client_cert,
                                                            config->gateway_id);
        if (x509_err != ESP_OK) {
            return x509_err;
        }
#endif
    }

    memset(&s_config, 0, sizeof(s_config));
    strncpy(s_config.gateway_id, config->gateway_id, sizeof(s_config.gateway_id) - 1);
    strncpy(s_config.broker_uri, config->broker_uri, sizeof(s_config.broker_uri) - 1);
    s_config.broker_ca_cert = uri_is_tls ? config->broker_ca_cert : NULL;
    s_config.client_cert = uri_is_tls ? config->client_cert : NULL;
    s_config.client_key = uri_is_tls ? config->client_key : NULL;
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

    err = gateway_mqtt_build_topic(s_sub_topic_join_grant, sizeof(s_sub_topic_join_grant),
                                   s_config.gateway_id, "downlink/join-grant");
    if (err != ESP_OK) return err;

    err = gateway_mqtt_build_topic(s_sub_topic_join_wait, sizeof(s_sub_topic_join_wait),
                                   s_config.gateway_id, "downlink/join-wait");
    if (err != ESP_OK) return err;

    err = gateway_mqtt_build_topic(s_sub_topic_join_reject, sizeof(s_sub_topic_join_reject),
                                   s_config.gateway_id, "downlink/join-reject");
    if (err != ESP_OK) return err;

    err = gateway_mqtt_build_topic(s_sub_topic_node_revoke, sizeof(s_sub_topic_node_revoke),
                                   s_config.gateway_id, "downlink/node-revoke");
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
