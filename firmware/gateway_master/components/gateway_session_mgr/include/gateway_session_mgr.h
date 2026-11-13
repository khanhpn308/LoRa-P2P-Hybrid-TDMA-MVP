#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "esp_err.h"
#include "lora_mac.h"
#include "gateway_v2_join.h"

#ifdef __cplusplus
extern "C" {
#endif

#define MAX_APPROVED_NODES (32)
#define MAX_REVOKED_NODES  (256)
#define GW_SESSION_NVS_NAMESPACE "gw_session"

extern const uint8_t DEFAULT_NONCE_PREFIX[8];

typedef struct {
    uint8_t mac[6];
    uint8_t node_id;
    bool approved;
    bool has_cached_hello;
    uint8_t cached_hello[LORA_MAC_V2_LEN_UP_JOIN_HELLO];
    int16_t cached_rssi;
    int8_t cached_snr;
} approved_node_entry_t;

typedef struct {
    bool revoked;
    uint8_t k_session_dl[16];
    uint8_t nonce_prefix[8];
    bool has_key;
} gateway_revoked_node_info_t;

typedef struct {
    uint8_t  active;
    uint8_t  node_id;
    uint8_t  device_mac[6];
    uint32_t join_counter;
    uint8_t  k_session_up[16];
    uint8_t  k_session_dl[16];
} gw_persisted_session_t;

esp_err_t gateway_session_mgr_init(gateway_v2_join_engine_t *join_engine);

approved_node_entry_t *find_or_create_node_entry(const uint8_t mac[6]);

esp_err_t gateway_save_node_session(uint8_t node_id);
void gateway_restore_sessions_from_nvs(void);
esp_err_t gateway_erase_node_session(uint8_t node_id);

gateway_revoked_node_info_t *gateway_session_mgr_get_revoked_info(uint8_t node_id);
bool gateway_session_mgr_is_node_revoked(uint8_t node_id);
void gateway_session_mgr_clear_revocation(uint8_t node_id);
void gateway_session_mgr_revoke_node(uint8_t node_id);

esp_err_t hal_session_key_lookup(uint8_t node_id,
                                 uint8_t *out_session_sel,
                                 uint8_t out_k_session_up[16],
                                 uint8_t out_k_session_dl[16],
                                 uint8_t out_nonce_prefix[8]);

#ifdef __cplusplus
}
#endif
