idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES
        node_tdma_client
        node_v2_join
        sx1276_driver
        lora_mac
        button_driver
        tdma_common
        airtime_policy
        nvs_flash
        mbedtls
)
