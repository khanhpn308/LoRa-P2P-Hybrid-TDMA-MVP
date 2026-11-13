idf_component_register(
    SRCS "src/node_event_tx.c"
    INCLUDE_DIRS "include"
    REQUIRES
        lora_mac
        node_arq
        node_smart_backoff
        node_cad_backoff
        node_radio_hal
        sx1276_driver
        airtime_policy
)
