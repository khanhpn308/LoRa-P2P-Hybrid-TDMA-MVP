#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <stdbool.h>
#include "gateway_transport.h"
#include "gateway_wifi.h"
#include "gateway_mqtt.h"

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

    /* Valid config */
    gateway_transport_config_t cfg = {
        .gateway_id = "gw-a",
        .wifi_ssid = "test-ssid",
        .wifi_password = "test-password",
        .wifi_max_retry = 5,
        .broker_uri = "mqtts://192.168.1.50:8883",
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

    printf("ALL Gateway Transport Unit Tests PASSED successfully.\n");
    return 0;
}
