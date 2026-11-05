/**
 * @file gateway_timing_config.h
 * @brief Static configuration for ESP32 Gateway timing test application.
 */

#ifndef GATEWAY_TIMING_CONFIG_H
#define GATEWAY_TIMING_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

#define GATEWAY_DEVICE_ID              "GATEWAY_HIL_01"
#define GATEWAY_TIMING_CYCLES          50U
#define GATEWAY_SUPPORTED_NODES        15U

/* Beacon period and timing */
#define GATEWAY_BEACON_INTERVAL_MS     10000U /* 10s test beacon cycle */
#define GATEWAY_BEACON_PAYLOAD_LEN     16U
#define GATEWAY_ACK_PAYLOAD_LEN        8U

/* RF Safety defaults */
#define GATEWAY_DEFAULT_RF_TX_ENABLED  false  /* Fail-closed safety gate */
#define GATEWAY_DEFAULT_PA_VERIFIED    false  /* Fail-closed safety gate */

/* FreeRTOS task sizing */
#define GATEWAY_RUNNER_STACK_SIZE      4096U
#define GATEWAY_LOGGER_STACK_SIZE      4096U
#define GATEWAY_RUNNER_TASK_PRIO       5U
#define GATEWAY_LOGGER_TASK_PRIO       2U

#endif /* GATEWAY_TIMING_CONFIG_H */
