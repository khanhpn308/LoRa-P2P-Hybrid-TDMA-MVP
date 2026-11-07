idf_component_register(
    SRCS "main.c" "gateway_wal.c" "gateway_crypto.c" "gateway_tdma_master.c" "gateway_v2_join.c"
    INCLUDE_DIRS "."
    REQUIRES session_key_store nvs_flash sx1276_driver lora_mac tdma_common airtime_policy mbedtls esp_timer gateway_transport
)
