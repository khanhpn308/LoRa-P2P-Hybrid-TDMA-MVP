idf_component_register(
    SRCS "src/node_app.c"
    INCLUDE_DIRS "include"
    REQUIRES
        lora_mac
        node_v2_join
        node_smart_backoff
        node_cad_backoff
        node_radio_hal
        node_arq
        node_event_tx
        sx1276_driver
        button_driver
        airtime_policy
        nvs_flash
        mbedtls
        node_ui
)
