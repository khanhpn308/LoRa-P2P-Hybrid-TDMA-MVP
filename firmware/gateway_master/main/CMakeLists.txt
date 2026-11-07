idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "."
    REQUIRES session_key_store nvs_flash
)
