cmake_minimum_required(VERSION 3.22)

# Shared components directory: firmware/components
# A directory is an ESP-IDF component only after it has a valid CMakeLists.txt and sources.
set(EXTRA_COMPONENT_DIRS "../components")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(sensor_node)
