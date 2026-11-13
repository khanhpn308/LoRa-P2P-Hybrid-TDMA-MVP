idf_component_register(
    SRCS "src/gateway_session_mgr.c"
    INCLUDE_DIRS "include"
    REQUIRES
        nvs_flash
        session_key_store
        gateway_v2_join
        lora_mac
)
