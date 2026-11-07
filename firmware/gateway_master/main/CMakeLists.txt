idf_component_register(
    SRCS "main.c" "gateway_v2_join.c"
    INCLUDE_DIRS "."
    REQUIRES session_key_store nvs_flash gateway_transport lora_mac sx1276_driver mbedtls
)
