idf_component_register(
    SRCS "session_key_crypto.c" "test_main.c"
    INCLUDE_DIRS "."
    REQUIRES mbedtls esp_system
)
