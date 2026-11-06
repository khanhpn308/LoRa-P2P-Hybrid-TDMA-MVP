/**
 * @file node_timing_config.h
 * @brief Static configuration for ESP32 Node timing test application.
 */

#ifndef NODE_TIMING_CONFIG_H
#define NODE_TIMING_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

#define NODE_DEVICE_ID              "NODE_HIL_01"
#define NODE_TIMING_ITERATIONS      50U

/* Normative V2 Packet Payload Lengths (PR #202 / Issue #169) */
#define V2_LEN_DOWN_EVENT_ACK       19U
#define V2_LEN_UP_HEALTH_REPLY      21U
#define V2_LEN_UP_EVENT             26U
#define V2_LEN_DOWN_SYNC_BEACON     80U

/* Payload test suite sizes: exact V2 packet lengths */
#define NODE_PAYLOAD_SIZE_COUNT     4U
static const uint8_t NODE_PAYLOAD_SIZES[NODE_PAYLOAD_SIZE_COUNT] = {
    V2_LEN_DOWN_EVENT_ACK,   /* 19B */
    V2_LEN_UP_HEALTH_REPLY,  /* 21B */
    V2_LEN_UP_EVENT,         /* 26B */
    V2_LEN_DOWN_SYNC_BEACON  /* 80B */
};

/* Spreading Factors evaluated */
#define NODE_SF_COUNT               2U
static const uint8_t NODE_SF_MODES[NODE_SF_COUNT] = {7U, 8U};

/* RF Safety defaults */
#define NODE_DEFAULT_RF_TX_ENABLED  false  /* Fail-closed safety gate */
#define NODE_DEFAULT_PA_VERIFIED   false  /* Fail-closed safety gate */

/* FreeRTOS task sizing */
#define NODE_RUNNER_STACK_SIZE      4096U
#define NODE_LOGGER_STACK_SIZE      4096U
#define NODE_RUNNER_TASK_PRIO       5U
#define NODE_LOGGER_TASK_PRIO       2U

#endif /* NODE_TIMING_CONFIG_H */
