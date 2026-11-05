cmake_minimum_required(VERSION 3.22)

# Timing test harness Node application for Issue #11
# Isolated test-only ESP-IDF project
set(EXTRA_COMPONENT_DIRS "../common")
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(node_timing_harness)
