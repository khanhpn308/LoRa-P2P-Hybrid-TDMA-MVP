idf_component_register(
    SRCS "src/lora_mac.c" "src/node_event_fifo.c" "src/lora_mac_join_crypto.c" "src/lora_mac_crypto.c"
    INCLUDE_DIRS "include"
    REQUIRES log mbedtls
)
