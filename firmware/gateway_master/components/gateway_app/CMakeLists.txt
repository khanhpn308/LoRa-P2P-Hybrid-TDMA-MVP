idf_component_register(
    SRCS "src/gateway_app.c"
    INCLUDE_DIRS "include"
    REQUIRES
        gateway_radio_bridge
        gateway_downlink
        gateway_liveness
        gateway_session_mgr
        gateway_wal
        gateway_v2_join
        gateway_transport
        session_key_store
        sx1276_driver
        lora_mac
        airtime_policy
        nvs_flash
        esp_timer
)
