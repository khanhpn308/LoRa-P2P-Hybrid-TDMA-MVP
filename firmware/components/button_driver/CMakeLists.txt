idf_component_register(
    SRCS "src/button_driver.c"
    INCLUDE_DIRS "include"
    REQUIRES esp_driver_gpio esp_timer freertos log esp_hw_support
)
