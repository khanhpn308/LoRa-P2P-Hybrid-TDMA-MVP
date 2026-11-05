idf_component_register(
    SRCS "main.c" "../../common/timing_ring_buffer.c" "../../common/radio_adapter_mock.c"
    INCLUDE_DIRS "." "../../common"
    REQUIRES esp_timer esp_driver_gpio driver freertos
)
