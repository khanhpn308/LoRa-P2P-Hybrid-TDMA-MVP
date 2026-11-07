cmake_minimum_required(VERSION 3.22)

# Shared sibling directory: firmware/components/{sx1276_driver,lora_mac,tdma_common,airtime_policy,button_driver}
# A directory is an ESP-IDF component only after it has a valid CMakeLists.txt and sources.
set(EXTRA_COMPONENT_DIRS "../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(gateway_master)
