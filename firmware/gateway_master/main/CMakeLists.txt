idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        gateway_tdma_master
        gateway_v2_join
        gateway_transport
        session_key_store
        sx1276_driver
        lora_mac
        tdma_common
        airtime_policy
        nvs_flash
        mbedtls
        esp_timer
)
