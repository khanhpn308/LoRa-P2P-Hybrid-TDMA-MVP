idf_component_register(
    SRCS "src/node_radio_hal.c"
    INCLUDE_DIRS "include"
    REQUIRES sx1276_driver node_smart_backoff node_v2_join esp_timer
)
