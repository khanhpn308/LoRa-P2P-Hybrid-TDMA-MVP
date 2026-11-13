idf_component_register(
    SRCS "src/gateway_liveness.c"
    INCLUDE_DIRS "include"
    REQUIRES
        esp_timer
        esp_system
        gateway_transport
        sx1276_driver
        lora_mac
        freertos
)
