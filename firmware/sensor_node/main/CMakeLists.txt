idf_component_register(
    SRCS
        "main.c"
        "node_smart_backoff.c"
    INCLUDE_DIRS "."
    REQUIRES
        oled_ssd1306
        node_v2_join
        sx1276_driver
        lora_mac
        button_driver
        airtime_policy
        nvs_flash
        mbedtls
)
