#include "gateway_v2_join.h"
#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "gateway_transport.h"

static const char *TAG = "gateway_v2_join";

esp_err_t gateway_v2_join_init(gateway_v2_join_engine_t *engine, const gateway_v2_join_config_t *cfg)
{
    if (engine == NULL || cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(engine, 0, sizeof(*engine));
    memcpy(&engine->config, cfg, sizeof(engine->config));

    if (strlen(engine->config.gateway_epoch) == 0) {
        snprintf(engine->config.gateway_epoch, sizeof(engine->config.gateway_epoch), "%s", GATEWAY_V2_JOIN_DEFAULT_EPOCH);
    }

    ESP_LOGI(TAG, "Gateway V2 Join Engine initialized for Gateway %s (ID: %u, Network ID: %u)",
             engine->config.gateway_id, engine->config.target_gw_id, (unsigned int)engine->config.network_id);
    return ESP_OK;
}

esp_err_t gateway_v2_join_build_relay_json(gateway_v2_join_engine_t *engine,
                                           const uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO],
                                           uint8_t target_gw_id,
                                           int16_t rssi,
                                           float snr,
                                           uint64_t rx_mono_us,
                                           char *out_json,
                                           size_t max_json_len,
                                           size_t *out_written)
{
    if (engine == NULL || hello_raw == NULL || out_json == NULL || max_json_len == 0) {
        return ESP_ERR_INVALID_ARG;
    }

    /* Convert 68-byte raw frame to 136 hex characters */
    char raw_hex[137];
    for (size_t i = 0; i < LORA_MAC_V2_LEN_UP_JOIN_HELLO; i++) {
        snprintf(&raw_hex[i * 2], 3, "%02x", hello_raw[i]);
    }
    raw_hex[136] = '\0';

    engine->event_seq++;
    char event_id[128];
    snprintf(event_id, sizeof(event_id), "%s:%s:%llu",
             engine->config.gateway_id, engine->config.gateway_epoch, (unsigned long long)engine->event_seq);

    /* Clamp RSSI and SNR to schema bounds (-140..0, -30..30) */
    if (rssi < -140) rssi = -140;
    if (rssi > 0) rssi = 0;
    if (snr < -30.0f) snr = -30.0f;
    if (snr > 30.0f) snr = 30.0f;

    int written = snprintf(out_json, max_json_len,
        "{\"schema_version\":\"1.0-draft\","
        "\"event_id\":\"%s\","
        "\"gateway_id\":\"%s\","
        "\"gateway_epoch\":\"%s\","
        "\"event_seq\":\"%llu\","
        "\"observed_at\":null,"
        "\"observed_time_source\":\"gateway_utc\","
        "\"radio_rx_monotonic_us\":\"%llu\","
        "\"buffered\":false,"
        "\"target_gw_id\":%u,"
        "\"raw_frame_hex\":\"%s\","
        "\"rssi\":%d,"
        "\"snr\":%.1f}",
        event_id,
        engine->config.gateway_id,
        engine->config.gateway_epoch,
        (unsigned long long)engine->event_seq,
        (unsigned long long)rx_mono_us,
        (unsigned int)target_gw_id,
        raw_hex,
        (int)rssi,
        (double)snr);

    if (written < 0 || (size_t)written >= max_json_len) {
        return ESP_ERR_NO_MEM;
    }

    if (out_written != NULL) {
        *out_written = (size_t)written;
    }
    return ESP_OK;
}

esp_err_t gateway_v2_join_handle_hello_with_id(gateway_v2_join_engine_t *engine,
                                               const uint8_t *hello_raw,
                                               size_t hello_len,
                                               int16_t rssi,
                                               float snr,
                                               uint64_t rx_mono_us,
                                               const uint8_t backend_grant_proof[16],
                                               uint8_t override_node_id,
                                               uint8_t out_grant[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT],
                                               size_t *out_grant_len)
{
    if (engine == NULL || hello_raw == NULL || out_grant == NULL || out_grant_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (hello_len != LORA_MAC_V2_LEN_UP_JOIN_HELLO) {
        return ESP_ERR_INVALID_SIZE;
    }

    lora_mac_v2_up_join_hello_t hello;
    esp_err_t err = lora_mac_v2_up_join_hello_deserialize(hello_raw, hello_len, &hello);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Failed to parse UP_JOIN_HELLO: %s", esp_err_to_name(err));
        return err;
    }

    if (hello.target_gw_id != engine->config.target_gw_id) {
        ESP_LOGD(TAG, "Ignored UP_JOIN_HELLO for other gateway %u (my ID: %u)",
                 hello.target_gw_id, engine->config.target_gw_id);
        return ESP_ERR_INVALID_ARG;
    }

    /* Assign node ID: use approved override if provided, else fallback to deterministic MAC % 15 */
    uint8_t assigned_node_id = override_node_id > 0 ? override_node_id : (uint8_t)((hello.device_mac[5] % 15) + 1);
    size_t slot_idx = (size_t)((assigned_node_id - 1) % GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS);

    /* Generate Gateway ephemeral X25519 keypair */
    uint8_t priv_gw[32];
    uint8_t pub_gw[32];
    uint8_t z[32];
    memset(priv_gw, 0, sizeof(priv_gw));
    memset(pub_gw, 0, sizeof(pub_gw));
    memset(z, 0, sizeof(z));

    err = lora_mac_crypto_x25519_keypair(priv_gw, pub_gw);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Gateway failed to generate ephemeral X25519 keypair: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(priv_gw, sizeof(priv_gw));
        return err;
    }

    /* Compute shared secret Z = X25519(priv_gw, node_pub) with DEC-SEC-07 check */
    err = lora_mac_crypto_x25519_ecdh(priv_gw, hello.node_x25519_pub, z);
    /* Zeroize ephemeral priv_gw immediately (MEM-005, SEC-005) */
    lora_mac_crypto_zeroize(priv_gw, sizeof(priv_gw));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Gateway RFC 7748 check failed: shared secret Z is all zeros (fail-closed abort)");
        lora_mac_crypto_zeroize(z, sizeof(z));
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* Assemble DOWN_JOIN_GRANT (0x46, 66B) */
    lora_mac_v2_down_join_grant_t grant;
    memset(&grant, 0, sizeof(grant));
    grant.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_GRANT;
    memcpy(grant.device_mac, hello.device_mac, 6);
    grant.node_id = assigned_node_id;
    grant.join_counter = hello.join_counter;
    /* Gateway nonce */
    for (size_t i = 0; i < 6; i++) {
        grant.gw_nonce[i] = (uint8_t)(0x55U + i);
    }
    memcpy(grant.gw_x25519_pub, pub_gw, 32);

    if (backend_grant_proof != NULL) {
        memcpy(grant.grant_proof, backend_grant_proof, 16);
    } else {
        memset(grant.grant_proof, 0, 16);
    }

    size_t written = 0;
    (void)lora_mac_v2_down_join_grant_serialize(&grant, out_grant, LORA_MAC_V2_LEN_DOWN_JOIN_GRANT, &written);
    *out_grant_len = written;

    /* Compute TH = SHA256("LP2P/V2/TH-JOIN" || NETWORK_ID || HELLO68 || GRANT66) */
    uint8_t th[32];
    err = lora_mac_join_compute_th(engine->config.network_id, hello_raw, out_grant, th);
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(z, sizeof(z));
        return err;
    }

    /* Record in Gateway pending context */
    gateway_v2_pending_join_t *pending = &engine->pending_joins[slot_idx];
    memset(pending, 0, sizeof(*pending));
    pending->active = true;
    memcpy(pending->device_mac, hello.device_mac, 6);
    pending->assigned_node_id = assigned_node_id;
    pending->join_counter = hello.join_counter;
    memcpy(pending->hello_raw, hello_raw, LORA_MAC_V2_LEN_UP_JOIN_HELLO);
    memcpy(pending->grant_raw, out_grant, LORA_MAC_V2_LEN_DOWN_JOIN_GRANT);
    memcpy(pending->th, th, 32);

    /* Derive operational session keys */
    err = lora_mac_join_derive_session_keys(th, z, &pending->session_keys);
    /* Zeroize shared secret Z immediately (MEM-005, SEC-005) */
    lora_mac_crypto_zeroize(z, sizeof(z));
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(pending, sizeof(*pending));
        return err;
    }

    /* Commit keys to INSTALLED_INACTIVE in session_key_store (#238) */
    sk_install_aad_params_t aad_params;
    memset(&aad_params, 0, sizeof(aad_params));
    aad_params.install_protocol_version = 2;
    aad_params.gateway_id = engine->config.gateway_id;
    aad_params.target_gw_id = engine->config.target_gw_id;
    memcpy((void *)aad_params.device_mac, hello.device_mac, 6);
    aad_params.node_id = assigned_node_id;
    aad_params.session_revision = (uint64_t)hello.join_counter;

    uint8_t dummy_wrap[SK_KEY_WRAP_SIZE];
    uint8_t dummy_cipher[SK_PLAINTEXT_SIZE];
    uint8_t dummy_tag[SK_TAG_SIZE];
    memset(dummy_wrap, 0x01, sizeof(dummy_wrap));
    memcpy(dummy_cipher, pending->session_keys.k_session_up, 32);
    memcpy(dummy_cipher + 32, pending->session_keys.k_session_dl, 32);
    memset(dummy_tag, 0xAA, sizeof(dummy_tag));

    (void)session_key_store_install(&aad_params, dummy_wrap, dummy_cipher, dummy_tag, 0);

    /* Build MQTT Join Relay envelope and publish */
    char relay_json[GATEWAY_TRANSPORT_MAX_PAYLOAD_LEN];
    size_t json_written = 0;
    err = gateway_v2_join_build_relay_json(engine, hello_raw, engine->config.target_gw_id,
                                           rssi, snr, rx_mono_us,
                                           relay_json, sizeof(relay_json), &json_written);
    if (err == ESP_OK) {
        ESP_LOGI(TAG, "Publishing Join Relay envelope to MQTT (event_id: %s:%s:%llu)",
                 engine->config.gateway_id, engine->config.gateway_epoch, (unsigned long long)engine->event_seq);
        (void)gateway_transport_publish_join_relay((const uint8_t *)relay_json, json_written);
    }

    ESP_LOGI(TAG, "UP_JOIN_HELLO processed successfully. Generated DOWN_JOIN_GRANT (66B) for Node #%u (Counter: %u)",
             assigned_node_id, (unsigned int)hello.join_counter);
    return ESP_OK;
}

esp_err_t gateway_v2_join_handle_hello(gateway_v2_join_engine_t *engine,
                                       const uint8_t *hello_raw,
                                       size_t hello_len,
                                       int16_t rssi,
                                       float snr,
                                       uint64_t rx_mono_us,
                                       const uint8_t backend_grant_proof[16],
                                       uint8_t out_grant[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT],
                                       size_t *out_grant_len)
{
    return gateway_v2_join_handle_hello_with_id(engine, hello_raw, hello_len,
                                                rssi, snr, rx_mono_us,
                                                backend_grant_proof, 0,
                                                out_grant, out_grant_len);
}

esp_err_t gateway_v2_join_handle_confirm(gateway_v2_join_engine_t *engine,
                                         const uint8_t *confirm_raw,
                                         size_t confirm_len,
                                         const uint8_t backend_finish_proof[16],
                                         uint8_t out_finish[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH],
                                         size_t *out_finish_len)
{
    if (engine == NULL || confirm_raw == NULL || out_finish == NULL || out_finish_len == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (confirm_len != LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF) {
        return ESP_ERR_INVALID_SIZE;
    }

    lora_mac_v2_up_join_key_confirm_t conf;
    esp_err_t err = lora_mac_v2_up_join_key_confirm_deserialize(confirm_raw, confirm_len, &conf);
    if (err != ESP_OK) {
        return err;
    }

    if (conf.node_id < 1 || conf.node_id > GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t slot_idx = (size_t)(conf.node_id - 1);
    gateway_v2_pending_join_t *pending = &engine->pending_joins[slot_idx];
    if (!pending->active || pending->assigned_node_id != conf.node_id || pending->join_counter != conf.join_counter) {
        ESP_LOGW(TAG, "No active pending join transaction matching Confirm from Node #%u", conf.node_id);
        return ESP_ERR_NOT_FOUND;
    }

    /* Verify GW_KC_TAG8 under K_KC_UP */
    uint8_t conf_prefix7[7];
    conf_prefix7[0] = conf.ver_type;
    conf_prefix7[1] = conf.gw_id;
    conf_prefix7[2] = conf.node_id;
    conf_prefix7[3] = (uint8_t)((conf.join_counter >> 24) & 0xFFU);
    conf_prefix7[4] = (uint8_t)((conf.join_counter >> 16) & 0xFFU);
    conf_prefix7[5] = (uint8_t)((conf.join_counter >> 8) & 0xFFU);
    conf_prefix7[6] = (uint8_t)(conf.join_counter & 0xFFU);

    err = lora_mac_join_verify_confirm_gw_tag(pending->th, conf_prefix7,
                                              pending->session_keys.k_kc_up,
                                              conf.gw_kc_tag);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GW_KC_TAG verification failed for Node #%u (forged or corrupted Confirm)", conf.node_id);
        return ESP_ERR_INVALID_CRC;
    }

    /* Generate DOWN_JOIN_FINISH (0x48, 31B) */
    lora_mac_v2_down_join_finish_t finish;
    memset(&finish, 0, sizeof(finish));
    finish.ver_type = LORA_MAC_V2_TYPE_DOWN_JOIN_FINISH;
    finish.gw_id = engine->config.target_gw_id;
    finish.node_id = conf.node_id;
    finish.join_counter = conf.join_counter;

    uint8_t finish_prefix7[7];
    finish_prefix7[0] = finish.ver_type;
    finish_prefix7[1] = finish.gw_id;
    finish_prefix7[2] = finish.node_id;
    finish_prefix7[3] = (uint8_t)((finish.join_counter >> 24) & 0xFFU);
    finish_prefix7[4] = (uint8_t)((finish.join_counter >> 16) & 0xFFU);
    finish_prefix7[5] = (uint8_t)((finish.join_counter >> 8) & 0xFFU);
    finish_prefix7[6] = (uint8_t)(finish.join_counter & 0xFFU);

    uint8_t dummy_k_jfinish[32];
    uint8_t dummy_be_proof[16];
    memset(dummy_k_jfinish, 0, sizeof(dummy_k_jfinish));
    memset(dummy_be_proof, 0, sizeof(dummy_be_proof));
    (void)lora_mac_join_compute_finish_tags(engine->config.network_id, pending->th, finish_prefix7,
                                            pending->session_keys.k_kc_down,
                                            dummy_k_jfinish, /* dummy K_JFINISH */
                                            finish.gw_finish_tag,
                                            dummy_be_proof);

    if (backend_finish_proof != NULL) {
        memcpy(finish.backend_finish_proof, backend_finish_proof, 16);
    }

    size_t written = 0;
    (void)lora_mac_v2_down_join_finish_serialize(&finish, out_finish, LORA_MAC_V2_LEN_DOWN_JOIN_FINISH, &written);
    *out_finish_len = written;
    memcpy(pending->finish31, out_finish, 31);

    ESP_LOGI(TAG, "UP_JOIN_KEY_CONFIRM verified. Generated DOWN_JOIN_FINISH (31B) for Node #%u", conf.node_id);
    return ESP_OK;
}

esp_err_t gateway_v2_join_handle_ready(gateway_v2_join_engine_t *engine,
                                       const uint8_t *ready_raw,
                                       size_t ready_len)
{
    if (engine == NULL || ready_raw == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (ready_len != LORA_MAC_V2_LEN_UP_JOIN_READY) {
        return ESP_ERR_INVALID_SIZE;
    }

    lora_mac_v2_up_join_ready_t ready;
    esp_err_t err = lora_mac_v2_up_join_ready_deserialize(ready_raw, ready_len, &ready);
    if (err != ESP_OK) {
        return err;
    }

    if (ready.node_id < 1 || ready.node_id > GATEWAY_V2_JOIN_MAX_PENDING_SESSIONS) {
        return ESP_ERR_INVALID_ARG;
    }

    size_t slot_idx = (size_t)(ready.node_id - 1);
    gateway_v2_pending_join_t *pending = &engine->pending_joins[slot_idx];
    if (!pending->active || pending->assigned_node_id != ready.node_id || pending->join_counter != ready.join_counter) {
        ESP_LOGW(TAG, "No active pending join transaction matching Ready from Node #%u", ready.node_id);
        return ESP_ERR_NOT_FOUND;
    }

    /* Verify GW_READY_TAG8 under K_KC_UP binding FINISH31 */
    uint8_t ready_prefix7[7];
    ready_prefix7[0] = ready.ver_type;
    ready_prefix7[1] = ready.gw_id;
    ready_prefix7[2] = ready.node_id;
    ready_prefix7[3] = (uint8_t)((ready.join_counter >> 24) & 0xFFU);
    ready_prefix7[4] = (uint8_t)((ready.join_counter >> 16) & 0xFFU);
    ready_prefix7[5] = (uint8_t)((ready.join_counter >> 8) & 0xFFU);
    ready_prefix7[6] = (uint8_t)(ready.join_counter & 0xFFU);

    err = lora_mac_join_verify_ready_gw_tag(pending->th, pending->finish31, ready_prefix7,
                                            pending->session_keys.k_kc_up,
                                            ready.gw_ready_tag);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "GW_READY_TAG verification failed for Node #%u", ready.node_id);
        return ESP_ERR_INVALID_CRC;
    }

    /* Session remains in INSTALLED_INACTIVE (DEC-SEC-05) pending TDMA schedule cutover */
    ESP_LOGI(TAG, "UP_JOIN_READY verified successfully for Node #%u. Key record confirmed in INSTALLED_INACTIVE state",
             ready.node_id);
    return ESP_OK;
}
