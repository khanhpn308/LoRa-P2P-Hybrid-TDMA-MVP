idf_component_register(
    SRCS "main.c" "button_driver.c"
    INCLUDE_DIRS "."
    REQUIRES sx1276_driver lora_mac
)
