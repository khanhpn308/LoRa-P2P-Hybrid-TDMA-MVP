idf_component_register(
    SRCS "src/node_ui.c"
    INCLUDE_DIRS "include"
    REQUIRES oled_ssd1306 esp_driver_gpio freertos
)
