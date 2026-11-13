#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Main entrypoint for sensor node application orchestration.
 *        Dispatches cold-boot vs Deep Sleep wake, join, event FIFO, and sleep arming.
 */
void node_app_run(void);

#ifdef __cplusplus
}
#endif
