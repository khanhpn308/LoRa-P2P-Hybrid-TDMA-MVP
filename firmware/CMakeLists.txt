cmake_minimum_required(VERSION 3.22)
project(lora_hybrid_tdma_firmware NONE)

# Umbrella CMake configuration providing targets for both Node and Gateway firmware builds.
# Under ESP-IDF, individual target firmware is built via `idf.py build`.

add_custom_target(gateway_master
    COMMAND idf.py -C "${CMAKE_CURRENT_SOURCE_DIR}/gateway_master" build
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/gateway_master"
    COMMENT "Building gateway_master ESP-IDF firmware"
)

add_custom_target(sensor_node
    COMMAND idf.py -C "${CMAKE_CURRENT_SOURCE_DIR}/sensor_node" build
    WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}/sensor_node"
    COMMENT "Building sensor_node ESP-IDF firmware"
)

add_custom_target(all_firmware ALL
    DEPENDS gateway_master sensor_node
    COMMENT "Building all firmware images (gateway_master & sensor_node)"
)
