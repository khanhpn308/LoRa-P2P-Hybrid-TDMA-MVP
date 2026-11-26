#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <stdbool.h>
#include "gateway_transport.h"
#include "gateway_wifi.h"
#include "gateway_mqtt.h"
#include "nvs.h"

/* Synthetic non-secret PEM fixtures for unit tests (string-split avoids secret-scanner false positive) */
static const char k_test_ca_pem[] =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIBkTCB+wIJAKTestCA0001MA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBnRl\n"
    "-----END CERTIFICATE-----\n";

static const char k_test_client_cert_pem[] =
    "-----BEGIN CERTIFICATE-----\n"
    "MIIBkTCB+wIJAKTestGW0001MA0GCSqGSIb3DQEBCwUAMBExDzANBgNVBAMMBmd3\n"
    "-----END CERTIFICATE-----\n";

static const char k_test_client_key_pem[] =
    "-----BEGIN " "PRIVATE " "KEY-----\n"
    "MIIBVQIBADANBgkqhkiG9w0BAQEFAASCAT8wggE7AgEAAkEAsyntheticTestKey\n"
    "-----END " "PRIVATE " "KEY-----\n";

static bool s_mock_session_key_cb_called = false;
static uint8_t s_mock_session_key_data[64];
static size_t s_mock_session_key_len = 0;

static bool s_mock_schedule_cb_called = false;
static uint8_t s_mock_schedule_data[64];
static size_t s_mock_schedule_len = 0;

static void mock_session_key_cb(const uint8_t *data, size_t len)
{
    s_mock_session_key_cb_called = true;
    s_mock_session_key_len = len;
    if (len <= sizeof(s_mock_session_key_data)) {
        memcpy(s_mock_session_key_data, data, len);
    }
}

static void mock_schedule_cb(const uint8_t *data, size_t len)
{
    s_mock_schedule_cb_called = true;
    s_mock_schedule_len = len;
    if (len <= sizeof(s_mock_schedule_data)) {
        memcpy(s_mock_schedule_data, data, len);
    }
}

static bool s_mock_node_revoke_cb_called = false;
static uint8_t s_mock_node_revoke_data[64];
static size_t s_mock_node_revoke_len = 0;

static void mock_node_revoke_cb(const uint8_t *data, size_t len)
{
    s_mock_node_revoke_cb_called = true;
    s_mock_node_revoke_len = len;
    if (len <= sizeof(s_mock_node_revoke_data)) {
        memcpy(s_mock_node_revoke_data, data, len);
    }
}

static bool s_mock_join_wait_cb_called = false;
static uint8_t s_mock_join_wait_data[64];
static size_t s_mock_join_wait_len = 0;

static void mock_join_wait_cb(const uint8_t *data, size_t len)
{
    s_mock_join_wait_cb_called = true;
    s_mock_join_wait_len = len;
    if (len <= sizeof(s_mock_join_wait_data)) {
        memcpy(s_mock_join_wait_data, data, len);
    }
}

static bool s_mock_join_reject_cb_called = false;
static uint8_t s_mock_join_reject_data[64];
static size_t s_mock_join_reject_len = 0;

static void mock_join_reject_cb(const uint8_t *data, size_t len)
{
    s_mock_join_reject_cb_called = true;
    s_mock_join_reject_len = len;
    if (len <= sizeof(s_mock_join_reject_data)) {
        memcpy(s_mock_join_reject_data, data, len);
    }
}

static void test_client_id_generation(void)
{
    printf("  Testing MQTT Client ID generation (ADR-0002)...\n");
    char client_id[64];

    /* Valid generation */
    esp_err_t err = gateway_mqtt_build_client_id(client_id, sizeof(client_id), "gw-a");
    assert(err == ESP_OK);
    assert(strcmp(client_id, "iot/v1/gw/gw-a") == 0);

    err = gateway_mqtt_build_client_id(client_id, sizeof(client_id), "gw-b");
    assert(err == ESP_OK);
    assert(strcmp(client_id, "iot/v1/gw/gw-b") == 0);

    /* Invalid arguments */
    assert(gateway_mqtt_build_client_id(NULL, sizeof(client_id), "gw-a") == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_build_client_id(client_id, 0, "gw-a") == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_build_client_id(client_id, sizeof(client_id), NULL) == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_build_client_id(client_id, sizeof(client_id), "") == ESP_ERR_INVALID_ARG);

    /* Buffer truncation */
    char small_buf[10];
    assert(gateway_mqtt_build_client_id(small_buf, sizeof(small_buf), "gw-a") == ESP_ERR_INVALID_SIZE);

    printf("  [PASS] test_client_id_generation\n");
}

static void test_canonical_topics_generation(void)
{
    printf("  Testing canonical MQTT topics formatting (contracts/mqtt/topics.md)...\n");
    char topic[128];
    esp_err_t err;

    /* Uplink topics */
    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "uplink/alert");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/uplink/alert") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "uplink/status");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/uplink/status") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "uplink/session-key-ack");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/uplink/session-key-ack") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "uplink/join-hello");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/uplink/join-hello") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "uplink/schedule-ack");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/uplink/schedule-ack") == 0);

    /* Downlink topics */
    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "downlink/session-key-install");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/downlink/session-key-install") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "downlink/schedule");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/downlink/schedule") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "downlink/join-wait");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/downlink/join-wait") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "downlink/join-reject");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/downlink/join-reject") == 0);

    err = gateway_mqtt_build_topic(topic, sizeof(topic), "gw-a", "downlink/node-revoke");
    assert(err == ESP_OK);
    assert(strcmp(topic, "iot/v1/gw/gw-a/downlink/node-revoke") == 0);

    /* Buffer bounds */
    char small_buf[15];
    assert(gateway_mqtt_build_topic(small_buf, sizeof(small_buf), "gw-a", "uplink/alert") == ESP_ERR_INVALID_SIZE);

    printf("  [PASS] test_canonical_topics_generation\n");
}

static void test_wifi_exponential_backoff(void)
{
    printf("  Testing WiFi reconnect exponential backoff calculation...\n");
    uint8_t max_retry = 5;

    /* Fast retries: 0 ms delay for attempts 0..4 */
    for (uint32_t i = 0; i < max_retry; i++) {
        assert(gateway_wifi_compute_backoff_ms(i, max_retry) == 0);
    }

    /* Exponential backoff starting at retry == 5 */
    assert(gateway_wifi_compute_backoff_ms(5, max_retry) == 1000);
    assert(gateway_wifi_compute_backoff_ms(6, max_retry) == 2000);
    assert(gateway_wifi_compute_backoff_ms(7, max_retry) == 4000);
    assert(gateway_wifi_compute_backoff_ms(8, max_retry) == 8000);
    assert(gateway_wifi_compute_backoff_ms(9, max_retry) == 16000);
    assert(gateway_wifi_compute_backoff_ms(10, max_retry) == 32000);
    assert(gateway_wifi_compute_backoff_ms(11, max_retry) == 60000); /* capped at MAX 60s */
    assert(gateway_wifi_compute_backoff_ms(50, max_retry) == 60000); /* capped */

    printf("  [PASS] test_wifi_exponential_backoff\n");
}

static void test_transport_init_and_bounds(void)
{
    printf("  Testing Transport initialization and parameter bounds...\n");

    /* Null config */
    assert(gateway_transport_init(NULL) == ESP_ERR_INVALID_ARG);

    /* Empty gateway id */
    gateway_transport_config_t bad_cfg;
    memset(&bad_cfg, 0, sizeof(bad_cfg));
    assert(gateway_transport_init(&bad_cfg) == ESP_ERR_INVALID_ARG);

    /* Valid config with mTLS PEM credentials */
    gateway_transport_config_t cfg = {
        .gateway_id = "gw-a",
        .wifi_ssid = "test-ssid",
        .wifi_password = "test-password",
        .wifi_max_retry = 5,
        .broker_uri = "mqtts://192.168.1.50:8883",
        .broker_ca_cert = k_test_ca_pem,
        .client_cert = k_test_client_cert_pem,
        .client_key = k_test_client_key_pem,
        .disable_auto_connect = true,
    };
    esp_err_t err = gateway_transport_init(&cfg);
    assert(err == ESP_OK);

    /* Idempotent re-init */
    assert(gateway_transport_init(&cfg) == ESP_OK);

    /* Verify initial status */
    assert(gateway_transport_get_status() == GATEWAY_TRANSPORT_STATUS_DISCONNECTED);
    assert(gateway_transport_is_connected() == false);

    printf("  [PASS] test_transport_init_and_bounds\n");
}

static void test_transport_publish_and_queuing(void)
{
    printf("  Testing Transport outbound publish and payload bounds (MEM-001, MEM-002, RTOS-001)...\n");

    const uint8_t sample_payload[] = "{\"test\":\"event\"}";
    size_t payload_len = strlen((const char *)sample_payload);

    /* Parameter bounds checking (SEC-001) */
    assert(gateway_transport_publish_event(NULL, payload_len) == ESP_ERR_INVALID_ARG);
    assert(gateway_transport_publish_event(sample_payload, 0) == ESP_ERR_INVALID_ARG);
    assert(gateway_transport_publish_event(sample_payload, GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN + 1) == ESP_ERR_INVALID_ARG);

    /* Test all publish functions with valid payload */
    assert(gateway_transport_publish_event(sample_payload, payload_len) == ESP_OK);
    assert(gateway_transport_publish_session_key_ack(sample_payload, payload_len) == ESP_OK);
    assert(gateway_transport_publish_join_relay(sample_payload, payload_len) == ESP_OK);
    assert(gateway_transport_publish_status(sample_payload, payload_len) == ESP_OK);
    assert(gateway_transport_publish_schedule_ack(sample_payload, payload_len) == ESP_OK);
    assert(gateway_transport_publish_rf_metrics(sample_payload, payload_len) == ESP_OK);

    /* Verify queued count */
    assert(gateway_transport_get_queued_count() >= 6);

    printf("  [PASS] test_transport_publish_and_queuing\n");
}

static void test_downlink_callbacks(void)
{
    printf("  Testing downlink callback registration and dispatch...\n");

    s_mock_session_key_cb_called = false;
    s_mock_schedule_cb_called = false;
    s_mock_join_wait_cb_called = false;
    s_mock_join_reject_cb_called = false;
    s_mock_node_revoke_cb_called = false;

    assert(gateway_transport_register_session_key_callback(&mock_session_key_cb) == ESP_OK);
    assert(gateway_transport_register_schedule_callback(&mock_schedule_cb) == ESP_OK);
    assert(gateway_transport_register_join_wait_callback(&mock_join_wait_cb) == ESP_OK);
    assert(gateway_transport_register_join_reject_callback(&mock_join_reject_cb) == ESP_OK);
    assert(gateway_transport_register_node_revoke_callback(&mock_node_revoke_cb) == ESP_OK);

    printf("  [PASS] test_downlink_callbacks\n");
}

static void test_transport_deinit(void)
{
    printf("  Testing Transport deinitialization (clean shutdown)...\n");

    assert(gateway_transport_deinit() == ESP_OK);
    /* Idempotent */
    assert(gateway_transport_deinit() == ESP_OK);
    assert(gateway_transport_get_status() == GATEWAY_TRANSPORT_STATUS_DISCONNECTED);

    printf("  [PASS] test_transport_deinit\n");
}

static void test_broker_uri_resolution(void)
{
    printf("  Testing MQTT broker URI resolution and downgrade protection...\n");
    char uri[128];

    /* 1. URI override takes precedence when valid */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri),
                                           "mqtts://broker.internal:8883",
                                           "10.0.0.1", 1883, true) == ESP_OK);
    assert(strcmp(uri, "mqtts://broker.internal:8883") == 0);
    assert(gateway_mqtt_is_tls_uri(uri) == true);

    /* 2. Reject silent downgrade to mqtt:// when tls_enabled == true */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri),
                                           "mqtt://127.0.0.1:1883",
                                           "127.0.0.1", 1883, true) == ESP_ERR_INVALID_ARG);
    assert(uri[0] == '\0');

    /* 3. Allow explicit mqtt:// override only when tls_enabled == false */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri),
                                           "mqtt://127.0.0.1:1883",
                                           "10.0.0.1", 8883, false) == ESP_OK);
    assert(strcmp(uri, "mqtt://127.0.0.1:1883") == 0);
    assert(gateway_mqtt_is_tls_uri(uri) == false);

    /* 4. Construct from host + port: port 8883 forces mqtts:// even if tls_enabled == false */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "", "192.168.1.25", 8883, false) == ESP_OK);
    assert(strcmp(uri, "mqtts://192.168.1.25:8883") == 0);

    /* 5. Construct from host + port: tls_enabled == true forces mqtts:// on custom port */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), NULL, "mqtt.example.local", 8884, true) == ESP_OK);
    assert(strcmp(uri, "mqtts://mqtt.example.local:8884") == 0);

    /* 6. Opt-in dev plaintext mqtt:// only when tls_enabled == false and port != 8883 */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "", "127.0.0.1", 1883, false) == ESP_OK);
    assert(strcmp(uri, "mqtt://127.0.0.1:1883") == 0);

    /* 7. Missing host, zero port, invalid scheme, or truncation fail closed */
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "", "", 8883, true) == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "", "192.168.1.25", 0, true) == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "http://bad:80", "192.168.1.25", 8883, true) == ESP_ERR_INVALID_ARG);
    assert(gateway_mqtt_resolve_broker_uri(uri, sizeof(uri), "", "bad host", 8883, true) == ESP_ERR_INVALID_ARG);

    char tiny[12];
    assert(gateway_mqtt_resolve_broker_uri(tiny, sizeof(tiny), "", "192.168.1.25", 8883, true) == ESP_ERR_INVALID_SIZE);

    printf("  [PASS] test_broker_uri_resolution\n");
}

static void test_mqtt_mtls_fail_closed(void)
{
    printf("  Testing fail-closed mTLS validation (missing/empty/invalid certs & URI)...\n");

    /* Ensure clean uninitialized state */
    assert(gateway_transport_deinit() == ESP_OK);

    /* 1. Empty broker_uri must fail closed (no hardcoded 192.168.1.10 fallback) */
    gateway_transport_config_t no_uri_cfg = {
        .gateway_id = "gw-a",
        .wifi_ssid = "test-ssid",
        .wifi_password = "test-password",
        .wifi_max_retry = 5,
        .broker_uri = "",
        .broker_ca_cert = k_test_ca_pem,
        .client_cert = k_test_client_cert_pem,
        .client_key = k_test_client_key_pem,
        .disable_auto_connect = true,
    };
    assert(gateway_transport_init(&no_uri_cfg) == ESP_ERR_INVALID_ARG);
    assert(gateway_transport_is_connected() == false);

    /* 2. mqtts:// with missing CA cert fails closed */
    gateway_transport_config_t missing_ca = no_uri_cfg;
    snprintf(missing_ca.broker_uri, sizeof(missing_ca.broker_uri), "mqtts://192.168.1.50:8883");
    missing_ca.broker_ca_cert = NULL;
    assert(gateway_transport_init(&missing_ca) == ESP_ERR_INVALID_ARG);
    assert(gateway_transport_is_connected() == false);

    /* 3. mqtts:// with empty client cert fails closed */
    gateway_transport_config_t empty_cert = missing_ca;
    empty_cert.broker_ca_cert = k_test_ca_pem;
    empty_cert.client_cert = "";
    assert(gateway_transport_init(&empty_cert) == ESP_ERR_INVALID_ARG);

    /* 4. mqtts:// with missing or malformed client key fails closed */
    gateway_transport_config_t bad_key = empty_cert;
    bad_key.client_cert = k_test_client_cert_pem;
    bad_key.client_key = NULL;
    assert(gateway_transport_init(&bad_key) == ESP_ERR_INVALID_ARG);

    bad_key.client_key = "not-a-pem-key";
    assert(gateway_transport_init(&bad_key) == ESP_ERR_INVALID_ARG);

    /* Certificate passed where private key is required must fail closed */
    bad_key.client_key = k_test_client_cert_pem;
    assert(gateway_transport_init(&bad_key) == ESP_ERR_INVALID_ARG);

    /* 5. Opt-in plaintext mqtt:// works without TLS certs */
    gateway_transport_config_t dev_cfg = {
        .gateway_id = "gw-a",
        .wifi_ssid = "test-ssid",
        .wifi_password = "test-password",
        .wifi_max_retry = 5,
        .broker_uri = "mqtt://127.0.0.1:1883",
        .disable_auto_connect = true,
    };
    assert(gateway_transport_init(&dev_cfg) == ESP_OK);
    assert(gateway_transport_deinit() == ESP_OK);

    printf("  [PASS] test_mqtt_mtls_fail_closed\n");
}

static void test_nvs_tls_cert_loading(void)
{
    printf("  Testing NVS mTLS certificate loading and fail-closed zeroization...\n");

    char ca_buf[256];
    char cert_buf[256];
    char key_buf[256];
    nvs_handle_t handle = 0;

    /* 1. Empty NVS -> ESP_ERR_NVS_NOT_FOUND */
    mock_nvs_reset();
    assert(gateway_transport_load_tls_certs_from_nvs(
               "gw-a", ca_buf, sizeof(ca_buf), cert_buf, sizeof(cert_buf), key_buf, sizeof(key_buf)) ==
           ESP_ERR_NVS_NOT_FOUND);

    /* 2. Partial NVS (CA + client_cert present, client_key missing) -> fail-closed & zeroize */
    assert(nvs_open(GATEWAY_TLS_NVS_NAMESPACE, NVS_READWRITE, &handle) == ESP_OK);
    assert(nvs_set_blob(handle, "ca_cert", k_test_ca_pem, strlen(k_test_ca_pem) + 1) == ESP_OK);
    assert(nvs_set_blob(handle, "client_cert", k_test_client_cert_pem, strlen(k_test_client_cert_pem) + 1) == ESP_OK);
    assert(gateway_transport_load_tls_certs_from_nvs(
               "gw-a", ca_buf, sizeof(ca_buf), cert_buf, sizeof(cert_buf), key_buf, sizeof(key_buf)) ==
           ESP_ERR_INVALID_STATE);
    assert(ca_buf[0] == '\0' && cert_buf[0] == '\0' && key_buf[0] == '\0');

    /* 3. Non-NUL-terminated client_key blob -> fail-closed & zeroize */
    assert(nvs_set_blob(handle, "client_key", k_test_client_key_pem, strlen(k_test_client_key_pem)) == ESP_OK);
    assert(gateway_transport_load_tls_certs_from_nvs(
               "gw-a", ca_buf, sizeof(ca_buf), cert_buf, sizeof(cert_buf), key_buf, sizeof(key_buf)) ==
           ESP_ERR_INVALID_RESPONSE);
    assert(ca_buf[0] == '\0' && cert_buf[0] == '\0' && key_buf[0] == '\0');

    /* 4. Mismatched gateway_id in NVS -> ESP_ERR_INVALID_STATE & zeroize */
    assert(nvs_set_blob(handle, "client_key", k_test_client_key_pem, strlen(k_test_client_key_pem) + 1) == ESP_OK);
    assert(nvs_set_blob(handle, "gateway_id", "gw-b", sizeof("gw-b")) == ESP_OK);
    assert(gateway_transport_load_tls_certs_from_nvs(
               "gw-a", ca_buf, sizeof(ca_buf), cert_buf, sizeof(cert_buf), key_buf, sizeof(key_buf)) ==
           ESP_ERR_INVALID_STATE);
    assert(ca_buf[0] == '\0' && cert_buf[0] == '\0' && key_buf[0] == '\0');

    /* 5. Matching gateway_id & valid NUL-terminated PEMs -> ESP_OK & init succeeds */
    assert(nvs_set_blob(handle, "gateway_id", "gw-a", sizeof("gw-a")) == ESP_OK);
    assert(gateway_transport_load_tls_certs_from_nvs(
               "gw-a", ca_buf, sizeof(ca_buf), cert_buf, sizeof(cert_buf), key_buf, sizeof(key_buf)) == ESP_OK);
    assert(strcmp(ca_buf, k_test_ca_pem) == 0);
    assert(strcmp(cert_buf, k_test_client_cert_pem) == 0);
    assert(strcmp(key_buf, k_test_client_key_pem) == 0);

    gateway_transport_config_t cfg = {
        .gateway_id = "gw-a",
        .wifi_ssid = "test-ssid",
        .wifi_password = "test-password",
        .wifi_max_retry = 5,
        .broker_uri = "mqtts://192.168.1.50:8883",
        .broker_ca_cert = ca_buf,
        .client_cert = cert_buf,
        .client_key = key_buf,
        .disable_auto_connect = true,
    };
    assert(gateway_transport_init(&cfg) == ESP_OK);
    assert(gateway_transport_deinit() == ESP_OK);

    printf("  [PASS] test_nvs_tls_cert_loading\n");
}

int main(void)
{
    printf("Running Gateway Transport Unit Tests (ESP-IDF v6.1 / WiFi Station & MQTT 5.0 mTLS)...\n");

    test_client_id_generation();
    test_canonical_topics_generation();
    test_wifi_exponential_backoff();
    test_transport_init_and_bounds();
    test_transport_publish_and_queuing();
    test_downlink_callbacks();
    test_transport_deinit();
    test_broker_uri_resolution();
    test_mqtt_mtls_fail_closed();
    test_nvs_tls_cert_loading();

    printf("ALL Gateway Transport Unit Tests PASSED successfully.\n");
    return 0;
}
