idf_component_register(
    SRCS "src/gateway_radio_bridge.c" "src/gateway_rf_metrics.c"
    INCLUDE_DIRS "include"
    REQUIRES
        gateway_session_mgr
        gateway_liveness
        gateway_wal
        gateway_v2_join
        gateway_transport
        sx1276_driver
        lora_mac
        esp_timer
        freertos
)
