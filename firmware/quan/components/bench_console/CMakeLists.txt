idf_component_register(SRCS "bench_console.c" INCLUDE_DIRS "include"
    PRIV_REQUIRES event_input esp_timer freertos log)
if(EVENT_BENCH_LINK_SHARED_DRIVER)
    # Project CMake options are not visible during IDF early requirements
    # expansion. The explicit extra directory makes this optional component
    # available; use the v6.1 late optional dependency API for its include/link.
    idf_component_optional_requires(PRIVATE sx1276_driver)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE EVENT_BENCH_LINK_SHARED_DRIVER=1)
endif()
