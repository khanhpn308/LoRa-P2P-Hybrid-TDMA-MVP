idf_component_register(
    SRCS "src/sx1276_hal.c"
         "src/sx1276_config.c"
         "src/sx1276_owner.c"
         "src/sx1276_driver.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "src"
    REQUIRES esp_driver_gpio esp_driver_spi freertos esp_timer log
)
