idf_component_register(
    SRCS
        "main.c"
        "node_cad_backoff.c"
    INCLUDE_DIRS "."
    REQUIRES
        node_ui
        node_v2_join
        node_smart_backoff
        node_arq
        sx1276_driver
        lora_mac
        button_driver
        airtime_policy
        nvs_flash
        mbedtls
)
