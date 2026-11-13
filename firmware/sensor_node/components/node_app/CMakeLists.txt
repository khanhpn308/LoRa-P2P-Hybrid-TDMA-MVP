idf_component_register(
    SRCS "src/node_app.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "../../main"
    REQUIRES
        lora_mac
        node_v2_join
        node_smart_backoff
        node_arq
        sx1276_driver
        button_driver
        airtime_policy
        nvs_flash
        mbedtls
        node_ui
)
