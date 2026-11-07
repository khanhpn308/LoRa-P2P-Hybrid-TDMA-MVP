idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES sx1276_driver lora_mac button_driver
)
