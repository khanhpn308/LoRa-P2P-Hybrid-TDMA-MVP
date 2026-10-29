# Include before project() from each personal firmware project.
set(EXTRA_COMPONENT_DIRS "${CMAKE_CURRENT_LIST_DIR}/components")
set(EVENT_BENCH_SHARED_COMPONENTS_DIR "${CMAKE_CURRENT_LIST_DIR}/../components"
    CACHE PATH "Explicit shared component source directory")
option(EVENT_BENCH_LINK_SHARED_DRIVER "Link reviewed shared SX1276 identity API; does not start radio" OFF)
if(EVENT_BENCH_LINK_SHARED_DRIVER)
    if(NOT EXISTS "${EVENT_BENCH_SHARED_COMPONENTS_DIR}/sx1276_driver/CMakeLists.txt")
        message(FATAL_ERROR "Shared sx1276_driver implementation missing. Supply reviewed EVENT_BENCH_SHARED_COMPONENTS_DIR or disable EVENT_BENCH_LINK_SHARED_DRIVER.")
    endif()
    list(APPEND EXTRA_COMPONENT_DIRS "${EVENT_BENCH_SHARED_COMPONENTS_DIR}")
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
if(NOT IDF_VERSION_MAJOR EQUAL 6 OR NOT IDF_VERSION_MINOR EQUAL 1 OR NOT IDF_VERSION_PATCH EQUAL 0)
    message(FATAL_ERROR "Event bench firmware requires ESP-IDF v6.1 (6.1.0).")
endif()
execute_process(COMMAND git -C "$ENV{IDF_PATH}" describe --tags --exact-match
    RESULT_VARIABLE event_bench_idf_tag_status OUTPUT_VARIABLE event_bench_idf_tag
    OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
if(NOT event_bench_idf_tag_status EQUAL 0 OR NOT event_bench_idf_tag STREQUAL "v6.1")
    message(FATAL_ERROR "Use the exact ESP-IDF Git tag v6.1, not a prerelease/dev checkout.")
endif()
