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
        mbedtls
)

set(_gw_secrets_dir "${CMAKE_CURRENT_SOURCE_DIR}/../../secrets")
if(EXISTS "${_gw_secrets_dir}/ca.crt"
   AND EXISTS "${_gw_secrets_dir}/client.crt"
   AND EXISTS "${_gw_secrets_dir}/client.key")
    target_add_binary_data(${COMPONENT_LIB} "${_gw_secrets_dir}/ca.crt" TEXT)
    target_add_binary_data(${COMPONENT_LIB} "${_gw_secrets_dir}/client.crt" TEXT)
    target_add_binary_data(${COMPONENT_LIB} "${_gw_secrets_dir}/client.key" TEXT)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE GATEWAY_HAS_EMBEDDED_TLS_CERTS=1)
endif()
