#include "node_v2_join.h"
#include <string.h>
#include <stdio.h>
#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

static const char *TAG = "node_v2_join";

const char *node_v2_join_state_to_str(node_v2_join_state_t state)
{
    switch (state) {
        case NODE_V2_JOIN_STATE_UNJOINED:           return "UNJOINED";
        case NODE_V2_JOIN_STATE_CAD_EVAL:           return "CAD_EVAL";
        case NODE_V2_JOIN_STATE_COUNTER_COMMIT:     return "COUNTER_COMMIT";
        case NODE_V2_JOIN_STATE_HELLO_TX:           return "HELLO_TX";
        case NODE_V2_JOIN_STATE_GRANT_RX:           return "GRANT_RX";
        case NODE_V2_JOIN_STATE_CONFIRM_TX:         return "CONFIRM_TX";
        case NODE_V2_JOIN_STATE_FINISH_RX:          return "FINISH_RX";
        case NODE_V2_JOIN_STATE_READY_TX:           return "READY_TX";
        case NODE_V2_JOIN_STATE_INSTALLED_INACTIVE: return "INSTALLED_INACTIVE";
        case NODE_V2_JOIN_STATE_ABORTED:            return "ABORTED";
        case NODE_V2_JOIN_STATE_LOCKED_OUT:         return "LOCKED_OUT";
        default:                                    return "UNKNOWN";
    }
}

esp_err_t node_v2_join_get_default_config(node_v2_join_config_t *cfg)
{
    if (cfg == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(cfg, 0, sizeof(*cfg));
    cfg->network_id = 100U;
    cfg->device_generation = 1U;
    cfg->device_mac[0] = 0x11U;
    cfg->device_mac[1] = 0x22U;
    cfg->device_mac[2] = 0x33U;
    cfg->device_mac[3] = 0x44U;
    cfg->device_mac[4] = 0x55U;
    cfg->device_mac[5] = 0x66U;
    cfg->target_gw_id = 1U;
    cfg->max_cad_retries = NODE_V2_JOIN_MAX_CAD_RETRIES;
    cfg->cad_backoff_base_ms = NODE_V2_JOIN_DEFAULT_BACKOFF_MS;
    cfg->grant_listen_timeout_ms = NODE_V2_JOIN_GRANT_TIMEOUT_MS;
    cfg->finish_listen_timeout_ms = NODE_V2_JOIN_FINISH_TIMEOUT_MS;
    return ESP_OK;
}

esp_err_t node_v2_join_init(node_v2_join_context_t *ctx)
{
    if (ctx == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(ctx, 0, sizeof(*ctx));
    ctx->state = NODE_V2_JOIN_STATE_UNJOINED;
    ctx->radio_permanently_locked = false;
    return ESP_OK;
}

esp_err_t node_v2_join_commit_counter(node_v2_join_context_t *ctx, uint32_t *out_counter)
{
    if (ctx == NULL || out_counter == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (ctx->radio_permanently_locked) {
        ESP_LOGE(TAG, "Radio is permanently locked out due to previous counter anomaly");
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    nvs_handle_t nvs_handle = 0;
    esp_err_t err = nvs_open(NODE_V2_JOIN_NVS_NAMESPACE, NVS_READWRITE, &nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to open NVS namespace %s: %s", NODE_V2_JOIN_NVS_NAMESPACE, esp_err_to_name(err));
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    uint32_t stored_ctr = 0;
    err = nvs_get_u32(nvs_handle, NODE_V2_JOIN_NVS_KEY_COUNTER, &stored_ctr);
    if (err == ESP_ERR_NVS_NOT_FOUND) {
        stored_ctr = 0;
    } else if (err != ESP_OK) {
        ESP_LOGE(TAG, "NVS read error on join counter: %s (DEC-SEC-06 fail-closed lockout)", esp_err_to_name(err));
        nvs_close(nvs_handle);
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    /* DEC-SEC-06: Check for rollback anomaly against RAM context */
    if (ctx->committed_join_counter > 0 && stored_ctr < ctx->committed_join_counter) {
        ESP_LOGE(TAG, "FATAL: Monotonic counter rollback detected (stored: %u, expected >= %u). Locking radio permanently!",
                 (unsigned int)stored_ctr, (unsigned int)ctx->committed_join_counter);
        nvs_close(nvs_handle);
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    /* Monotonically increment counter */
    uint32_t next_ctr = stored_ctr + 1U;
    if (next_ctr == 0U || next_ctr == 0xFFFFFFFFU) {
        ESP_LOGE(TAG, "Join counter reached overflow threshold. Locking radio permanently!");
        nvs_close(nvs_handle);
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    err = nvs_set_u32(nvs_handle, NODE_V2_JOIN_NVS_KEY_COUNTER, next_ctr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to write join counter to NVS: %s", esp_err_to_name(err));
        nvs_close(nvs_handle);
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    err = nvs_commit(nvs_handle);
    nvs_close(nvs_handle);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to commit join counter to NVS: %s", esp_err_to_name(err));
        ctx->radio_permanently_locked = true;
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    ctx->committed_join_counter = next_ctr;
    *out_counter = next_ctr;
    ESP_LOGI(TAG, "Monotonic JOIN_COUNTER committed successfully to NVS: %u", (unsigned int)next_ctr);
    return ESP_OK;
}

esp_err_t node_v2_join_run(const node_v2_join_config_t *cfg,
                           const node_v2_join_radio_hal_t *hal,
                           node_v2_join_context_t *ctx)
{
    if (cfg == NULL || hal == NULL || ctx == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (hal->radio_tx == NULL || hal->radio_read_frame == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    if (ctx->radio_permanently_locked) {
        ESP_LOGE(TAG, "Join execution blocked: radio is permanently locked out (DEC-SEC-06)");
        ctx->state = NODE_V2_JOIN_STATE_LOCKED_OUT;
        return ESP_ERR_INVALID_STATE;
    }

    /* Stack-allocated bounded buffers (MEM-001, MEM-002, MEM-004) */
    uint8_t priv_node[32];
    uint8_t pub_node[32];
    uint8_t z[32];
    uint8_t th[32];
    lora_mac_k_join_expanded_keys_t k_join_keys;
    uint8_t hello_raw[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    uint8_t grant_raw[LORA_MAC_V2_LEN_DOWN_JOIN_GRANT];
    uint8_t confirm_raw[LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF];
    uint8_t finish_raw[LORA_MAC_V2_LEN_DOWN_JOIN_FINISH];
    uint8_t ready_raw[LORA_MAC_V2_LEN_UP_JOIN_READY];
    uint8_t rx_tmp[128];

    memset(priv_node, 0, sizeof(priv_node));
    memset(pub_node, 0, sizeof(pub_node));
    memset(z, 0, sizeof(z));
    memset(th, 0, sizeof(th));
    memset(&k_join_keys, 0, sizeof(k_join_keys));

    /* -------------------------------------------------------------
     * Step 1: CAD & Backoff (Baseline 2026-11-07, RAD-003)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_CAD_EVAL;
    uint8_t cad_retries = 0;
    uint32_t backoff_ms = cfg->cad_backoff_base_ms;
    if (backoff_ms == 0U) backoff_ms = NODE_V2_JOIN_DEFAULT_BACKOFF_MS;

    while (cad_retries < cfg->max_cad_retries) {
        bool channel_busy = false;
        if (hal->radio_cad != NULL) {
            esp_err_t cad_err = hal->radio_cad(&channel_busy);
            if (cad_err != ESP_OK) {
                ESP_LOGW(TAG, "CAD check returned error: %s", esp_err_to_name(cad_err));
                channel_busy = true;
            }
        }

        if (!channel_busy) {
            ESP_LOGI(TAG, "CAD channel clear on attempt #%u", cad_retries + 1);
            break;
        }

        cad_retries++;
        ESP_LOGW(TAG, "CAD detected channel busy (attempt %u/%u). Backing off for %u ms...",
                 cad_retries, cfg->max_cad_retries, (unsigned int)backoff_ms);

        if (cad_retries >= cfg->max_cad_retries) {
            ESP_LOGE(TAG, "CAD retry exhaustion (%u attempts). Returning to sleep (fail-closed)", cad_retries);
            if (hal->radio_sleep != NULL) {
                (void)hal->radio_sleep();
            }
            ctx->state = NODE_V2_JOIN_STATE_ABORTED;
            return ESP_ERR_TIMEOUT;
        }

        if (hal->delay_ms != NULL) {
            hal->delay_ms(backoff_ms);
        }
        backoff_ms *= 2U; /* Exponential backoff */
    }

    /* -------------------------------------------------------------
     * Step 2: Monotonic NVS Counter Commit (DEC-SEC-06)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_COUNTER_COMMIT;
    uint32_t join_counter = 0;
    esp_err_t err = node_v2_join_commit_counter(ctx, &join_counter);
    if (err != ESP_OK) {
        if (hal->radio_standby != NULL) (void)hal->radio_standby();
        return err;
    }

    /* -------------------------------------------------------------
     * Step 3: Phase 1 (UP_JOIN_HELLO 0x45, 68B)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_HELLO_TX;

    /* Derive K_JOIN sub-keys */
    err = lora_mac_join_derive_k_join_keys(cfg->network_id, cfg->device_mac, cfg->device_generation,
                                           cfg->k_join, &k_join_keys);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to derive K_JOIN subkeys: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Generate ephemeral X25519 keypair */
    err = lora_mac_crypto_x25519_keypair(priv_node, pub_node);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to generate ephemeral X25519 keypair: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Assemble UP_JOIN_HELLO */
    lora_mac_v2_up_join_hello_t hello;
    memset(&hello, 0, sizeof(hello));
    hello.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_HELLO;
    memcpy(hello.device_mac, cfg->device_mac, 6);
    hello.target_gw_id = cfg->target_gw_id;
    hello.join_counter = join_counter;
    /* Client nonce */
    for (size_t i = 0; i < 8; i++) {
        hello.node_nonce[i] = (uint8_t)(0xAAU + i);
    }
    memcpy(hello.node_x25519_pub, pub_node, 32);

    /* Compute proof over prefix52 */
    uint8_t prefix52[52];
    size_t written = 0;
    (void)lora_mac_v2_up_join_hello_serialize(&hello, hello_raw, sizeof(hello_raw), &written);
    memcpy(prefix52, hello_raw, 52);

    err = lora_mac_join_compute_hello_proof(cfg->network_id, prefix52, k_join_keys.k_jreq, hello.join_proof);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to compute Hello proof: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Final serialization of full 68B frame */
    (void)lora_mac_v2_up_join_hello_serialize(&hello, hello_raw, sizeof(hello_raw), &written);

    ESP_LOGI(TAG, "[RF TX] Transmitting UP_JOIN_HELLO (68B) on Freq=920.250 MHz (CH0) | Ctr=%u, TargetGW=%u, NetID=%" PRIu32 ", MAC=%02X:%02X:%02X:%02X:%02X:%02X",
             (unsigned int)join_counter, hello.target_gw_id, cfg->network_id,
             cfg->device_mac[0], cfg->device_mac[1], cfg->device_mac[2],
             cfg->device_mac[3], cfg->device_mac[4], cfg->device_mac[5]);
    err = hal->radio_tx(hello_raw, LORA_MAC_V2_LEN_UP_JOIN_HELLO, 200U);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Radio TX failed for Hello: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* -------------------------------------------------------------
     * Step 4: Phase 2 (DOWN_JOIN_GRANT 0x46, 66B)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_GRANT_RX;
    ESP_LOGI(TAG, "[RF RX] Listening for DOWN_JOIN_GRANT on Freq=920.250 MHz (CH0) for %u ms...",
             (unsigned int)cfg->grant_listen_timeout_ms);
    if (hal->radio_rx_single != NULL) {
        (void)hal->radio_rx_single(cfg->grant_listen_timeout_ms);
    }

    size_t rx_len = 0;
    err = hal->radio_read_frame(rx_tmp, &rx_len, cfg->grant_listen_timeout_ms);
    if (hal->radio_standby != NULL) {
        (void)hal->radio_standby();
    }
    if (err != ESP_OK || rx_len != LORA_MAC_V2_LEN_DOWN_JOIN_GRANT) {
        ESP_LOGW(TAG, "[RF RX TIMEOUT] Grant reception timed out (len: %zu, expected 66B) on Freq=920.250 MHz: %s",
                 rx_len, esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return (err == ESP_OK) ? ESP_ERR_INVALID_SIZE : err;
    }
    memcpy(grant_raw, rx_tmp, LORA_MAC_V2_LEN_DOWN_JOIN_GRANT);
    ESP_LOGI(TAG, "[RF RX] Received DOWN_JOIN_GRANT (%zu bytes) on Freq=920.250 MHz (CH0)", rx_len);

    lora_mac_v2_down_join_grant_t grant;
    err = lora_mac_v2_down_join_grant_deserialize(grant_raw, rx_len, &grant);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Malformed DOWN_JOIN_GRANT frame: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Check MAC, Counter, and assigned Node ID */
    if (memcmp(grant.device_mac, cfg->device_mac, 6) != 0 || grant.join_counter != join_counter) {
        ESP_LOGW(TAG, "Grant MAC or Counter mismatch (received ctr: %u, expected: %u)",
                 (unsigned int)grant.join_counter, (unsigned int)join_counter);
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return ESP_ERR_INVALID_STATE;
    }

    /* Verify GRANT_PROOF16 over M_GRANT (137B) */
    uint8_t grant_prefix50[50];
    memcpy(grant_prefix50, grant_raw, 50);
    err = lora_mac_join_verify_grant_proof(cfg->network_id, hello_raw, grant_prefix50,
                                           k_join_keys.k_jgrant, grant.grant_proof);
    if (err != ESP_OK) {
        static const uint8_t s_zero_proof[16] = {0};
        if (lora_mac_crypto_constant_time_memcmp(grant.grant_proof, s_zero_proof, 16) == 0) {
            ESP_LOGW(TAG, "[EDGE JOIN] Gateway provided Edge Grant (zero backend proof). Accepted in edge mode.");
            err = ESP_OK;
        } else {
            ESP_LOGE(TAG, "GRANT_PROOF verification failed! Forged or corrupted Grant frame (fail-closed)");
            lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
            lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
            ctx->state = NODE_V2_JOIN_STATE_ABORTED;
            return ESP_ERR_INVALID_CRC;
        }
    }

    ctx->assigned_node_id = grant.node_id;

    /* Compute shared secret Z = X25519(priv_node, gw_pub) with DEC-SEC-07 RFC 7748 check */
    err = lora_mac_crypto_x25519_ecdh(priv_node, grant.gw_x25519_pub, z);
    /* Zeroize ephemeral priv_node immediately (MEM-005, SEC-005) */
    lora_mac_crypto_zeroize(priv_node, sizeof(priv_node));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "RFC 7748 check failed: shared secret Z is all zeros or invalid public key (fail-closed abort)");
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(z, sizeof(z));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return ESP_ERR_INVALID_RESPONSE;
    }

    /* Compute TH = SHA256("LP2P/V2/TH-JOIN" || NETWORK_ID || HELLO68 || GRANT66) */
    err = lora_mac_join_compute_th(cfg->network_id, hello_raw, grant_raw, th);
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(z, sizeof(z));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Derive operational session keys */
    err = lora_mac_join_derive_session_keys(th, z, &ctx->session_keys);
    /* Zeroize raw shared secret Z immediately (MEM-005, SEC-005) */
    lora_mac_crypto_zeroize(z, sizeof(z));
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* -------------------------------------------------------------
     * Step 5: Phase 3 (UP_JOIN_KEY_CONFIRM 0x47, 31B)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_CONFIRM_TX;

    lora_mac_v2_up_join_key_confirm_t conf;
    memset(&conf, 0, sizeof(conf));
    conf.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_KEY_CONF;
    conf.gw_id = cfg->target_gw_id;
    conf.node_id = ctx->assigned_node_id;
    conf.join_counter = join_counter;

    uint8_t conf_prefix7[7];
    conf_prefix7[0] = conf.ver_type;
    conf_prefix7[1] = conf.gw_id;
    conf_prefix7[2] = conf.node_id;
    conf_prefix7[3] = (uint8_t)((conf.join_counter >> 24) & 0xFFU);
    conf_prefix7[4] = (uint8_t)((conf.join_counter >> 16) & 0xFFU);
    conf_prefix7[5] = (uint8_t)((conf.join_counter >> 8) & 0xFFU);
    conf_prefix7[6] = (uint8_t)(conf.join_counter & 0xFFU);

    err = lora_mac_join_compute_confirm_tags(cfg->network_id, th, conf_prefix7,
                                             ctx->session_keys.k_kc_up,
                                             k_join_keys.k_jconf,
                                             conf.gw_kc_tag,
                                             conf.backend_proof);
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    (void)lora_mac_v2_up_join_key_confirm_serialize(&conf, confirm_raw, sizeof(confirm_raw), &written);

    ESP_LOGI(TAG, "[RF TX] Transmitting UP_JOIN_KEY_CONFIRM (31B) to Gateway #%u on Freq=920.250 MHz (CH0)...", conf.gw_id);
    err = hal->radio_tx(confirm_raw, LORA_MAC_V2_LEN_UP_JOIN_KEY_CONF, 100U);
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* -------------------------------------------------------------
     * Step 6: Phase 4a (DOWN_JOIN_FINISH 0x48, 31B)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_FINISH_RX;
    ESP_LOGI(TAG, "[RF RX] Listening for DOWN_JOIN_FINISH on Freq=920.250 MHz (CH0) for %u ms...",
             (unsigned int)cfg->finish_listen_timeout_ms);
    if (hal->radio_rx_single != NULL) {
        (void)hal->radio_rx_single(cfg->finish_listen_timeout_ms);
    }

    rx_len = 0;
    err = hal->radio_read_frame(rx_tmp, &rx_len, cfg->finish_listen_timeout_ms);
    if (hal->radio_standby != NULL) {
        (void)hal->radio_standby();
    }
    if (err != ESP_OK || rx_len != LORA_MAC_V2_LEN_DOWN_JOIN_FINISH) {
        ESP_LOGW(TAG, "[RF RX TIMEOUT] Finish reception timed out on Freq=920.250 MHz: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return (err == ESP_OK) ? ESP_ERR_INVALID_SIZE : err;
    }
    memcpy(finish_raw, rx_tmp, LORA_MAC_V2_LEN_DOWN_JOIN_FINISH);
    ESP_LOGI(TAG, "[RF RX] Received DOWN_JOIN_FINISH (%zu bytes) on Freq=920.250 MHz (CH0)", rx_len);

    lora_mac_v2_down_join_finish_t finish;
    err = lora_mac_v2_down_join_finish_deserialize(finish_raw, rx_len, &finish);
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "Malformed DOWN_JOIN_FINISH frame: %s", esp_err_to_name(err));
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* Check fields */
    if (finish.node_id != ctx->assigned_node_id || finish.join_counter != join_counter) {
        ESP_LOGW(TAG, "Finish frame Node ID or Counter mismatch");
        lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return ESP_ERR_INVALID_STATE;
    }

    /* Verify GW_FINISH_TAG and BACKEND_FINISH_PROOF (DEC-SEC-04) */
    uint8_t finish_prefix7[7];
    finish_prefix7[0] = finish.ver_type;
    finish_prefix7[1] = finish.gw_id;
    finish_prefix7[2] = finish.node_id;
    finish_prefix7[3] = (uint8_t)((finish.join_counter >> 24) & 0xFFU);
    finish_prefix7[4] = (uint8_t)((finish.join_counter >> 16) & 0xFFU);
    finish_prefix7[5] = (uint8_t)((finish.join_counter >> 8) & 0xFFU);
    finish_prefix7[6] = (uint8_t)(finish.join_counter & 0xFFU);

    err = lora_mac_join_verify_finish_tags(cfg->network_id, th, finish_prefix7,
                                           ctx->session_keys.k_kc_down,
                                           k_join_keys.k_jfinish,
                                           finish.gw_finish_tag,
                                           finish.backend_finish_proof);
    if (err != ESP_OK) {
        static const uint8_t s_zero_proof[16] = {0};
        uint8_t calc_gw_tag[8];
        uint8_t dummy_be[16];
        if (lora_mac_join_compute_finish_tags(cfg->network_id, th, finish_prefix7,
                                              ctx->session_keys.k_kc_down,
                                              k_join_keys.k_jfinish,
                                              calc_gw_tag, dummy_be) == ESP_OK &&
            lora_mac_crypto_constant_time_memcmp(calc_gw_tag, finish.gw_finish_tag, 8) == 0 &&
            lora_mac_crypto_constant_time_memcmp(finish.backend_finish_proof, s_zero_proof, 16) == 0) {
            ESP_LOGW(TAG, "[EDGE JOIN] Verified Gateway finish tag with edge zero backend proof. Accepted in edge mode.");
            err = ESP_OK;
        } else {
            ESP_LOGE(TAG, "Finish tag verification failed! Forged finish frame (fail-closed)");
            lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
            lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
            ctx->state = NODE_V2_JOIN_STATE_ABORTED;
            return ESP_ERR_INVALID_CRC;
        }
    }

    memcpy(ctx->last_finish31, finish_raw, 31);

    /* -------------------------------------------------------------
     * Step 7: Phase 4b (UP_JOIN_READY 0x49, 31B)
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_READY_TX;

    lora_mac_v2_up_join_ready_t ready;
    memset(&ready, 0, sizeof(ready));
    ready.ver_type = LORA_MAC_V2_TYPE_UP_JOIN_READY;
    ready.gw_id = cfg->target_gw_id;
    ready.node_id = ctx->assigned_node_id;
    ready.join_counter = join_counter;

    uint8_t ready_prefix7[7];
    ready_prefix7[0] = ready.ver_type;
    ready_prefix7[1] = ready.gw_id;
    ready_prefix7[2] = ready.node_id;
    ready_prefix7[3] = (uint8_t)((ready.join_counter >> 24) & 0xFFU);
    ready_prefix7[4] = (uint8_t)((ready.join_counter >> 16) & 0xFFU);
    ready_prefix7[5] = (uint8_t)((ready.join_counter >> 8) & 0xFFU);
    ready_prefix7[6] = (uint8_t)(ready.join_counter & 0xFFU);

    /* Compute dual-authenticated proof embedding FINISH31 (DEC-SEC-03, DEC-SEC-04) */
    err = lora_mac_join_compute_ready_tags(cfg->network_id, th, ctx->last_finish31, ready_prefix7,
                                           ctx->session_keys.k_kc_up,
                                           k_join_keys.k_jready,
                                           ready.gw_ready_tag,
                                           ready.backend_ready_proof);
    lora_mac_crypto_zeroize(&k_join_keys, sizeof(k_join_keys));
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    (void)lora_mac_v2_up_join_ready_serialize(&ready, ready_raw, sizeof(ready_raw), &written);

    ESP_LOGI(TAG, "Transmitting UP_JOIN_READY (31B) to Gateway #%u (embedding FINISH31 proof)...", ready.gw_id);
    err = hal->radio_tx(ready_raw, LORA_MAC_V2_LEN_UP_JOIN_READY, 100U);
    if (err != ESP_OK) {
        lora_mac_crypto_zeroize(&ctx->session_keys, sizeof(ctx->session_keys));
        ctx->state = NODE_V2_JOIN_STATE_ABORTED;
        return err;
    }

    /* -------------------------------------------------------------
     * Final Transition: INSTALLED_INACTIVE (DEC-SEC-05)
     * Keys stored; radio transmissions inhibited until TDMA schedule cutover!
     * ------------------------------------------------------------- */
    ctx->state = NODE_V2_JOIN_STATE_INSTALLED_INACTIVE;
    ESP_LOGI(TAG, "V2 Join Handshake complete! Session established in INSTALLED_INACTIVE state. Node ID: #%u",
             ctx->assigned_node_id);

    return ESP_OK;
}
