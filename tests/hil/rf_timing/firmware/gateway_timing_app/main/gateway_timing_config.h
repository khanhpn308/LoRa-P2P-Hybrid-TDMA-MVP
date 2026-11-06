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

/* Normative V2 Packet Payload Lengths (PR #202 / Issue #169) */
#define GATEWAY_BEACON_INTERVAL_MS     10000U /* 10s test beacon cycle */
#define GATEWAY_BEACON_PAYLOAD_LEN     80U    /* V2 DOWN_SYNC_BEACON (0x43): 16B header + 64B Ed25519 sig */
#define GATEWAY_ACK_PAYLOAD_LEN        19U    /* V2 DOWN_EVENT_ACK (0x42): 7B header + 4B payload + 8B CCM */
#define GATEWAY_EVENT_PAYLOAD_LEN      26U    /* V2 UP_EVENT (0x41): 7B header + 11B payload + 8B CCM */
#define GATEWAY_HEALTH_PAYLOAD_LEN     21U    /* V2 UP_HEALTH_REPLY (0x44): 7B header + 6B payload + 8B CCM */

/* RF Safety defaults */
#define GATEWAY_DEFAULT_RF_TX_ENABLED  false  /* Fail-closed safety gate */
#define GATEWAY_DEFAULT_PA_VERIFIED    false  /* Fail-closed safety gate */

/* FreeRTOS task sizing */
#define GATEWAY_RUNNER_STACK_SIZE      4096U
#define GATEWAY_LOGGER_STACK_SIZE      4096U
#define GATEWAY_RUNNER_TASK_PRIO       5U
#define GATEWAY_LOGGER_TASK_PRIO       2U

#endif /* GATEWAY_TIMING_CONFIG_H */
