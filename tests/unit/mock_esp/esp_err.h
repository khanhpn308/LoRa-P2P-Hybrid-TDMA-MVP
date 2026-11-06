/*
 * Minimal ESP-IDF error definitions for host unit tests.
 * Authority: ESP-IDF v6.1 esp_err.h
 */

#pragma once

#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int esp_err_t;

#define ESP_OK                  0       /*!< esp_err_t value indicating success (no error) */
#define ESP_FAIL               -1       /*!< Generic esp_err_t code indicating failure */

#define ESP_ERR_NO_MEM          0x101   /*!< Out of memory */
#define ESP_ERR_INVALID_ARG     0x102   /*!< Invalid argument */
#define ESP_ERR_INVALID_STATE   0x103   /*!< Invalid state */
#define ESP_ERR_INVALID_SIZE    0x104   /*!< Invalid size */
#define ESP_ERR_NOT_FOUND       0x105   /*!< Requested resource not found */
#define ESP_ERR_NOT_SUPPORTED   0x106   /*!< Operation or feature not supported */
#define ESP_ERR_TIMEOUT         0x107   /*!< Operation timed out */
#define ESP_ERR_INVALID_RESPONSE 0x108  /*!< Received response was invalid */
#define ESP_ERR_INVALID_CRC     0x109   /*!< CRC or checksum was invalid */
#define ESP_ERR_INVALID_VERSION 0x10A   /*!< Version was invalid */
#define ESP_ERR_INVALID_MAC     0x10B   /*!< MAC address was invalid */

#ifdef __cplusplus
}
#endif
