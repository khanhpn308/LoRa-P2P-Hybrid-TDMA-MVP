idf_component_register(
    SRCS "src/oled_ssd1306.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_i2c esp_timer log
)
