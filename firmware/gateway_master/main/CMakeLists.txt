idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        gateway_wal
        gateway_v2_join
        gateway_transport
        session_key_store
        sx1276_driver
        lora_mac
        airtime_policy
        nvs_flash
        mbedtls
        esp_timer
)
