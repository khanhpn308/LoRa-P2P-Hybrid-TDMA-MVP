idf_component_register(
    SRCS "main.c" "node_tdma_client.c" "node_crypto.c" "node_v2_join.c"
    INCLUDE_DIRS "."
    REQUIRES sx1276_driver lora_mac button_driver tdma_common airtime_policy mbedtls nvs_flash
)
