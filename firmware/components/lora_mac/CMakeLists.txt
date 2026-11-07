idf_component_register(
    SRCS "src/lora_mac.c" "src/node_event_fifo.c"
    INCLUDE_DIRS "include"
    REQUIRES log
)
