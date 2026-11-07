/*
 * Minimal ESP-IDF error definitions for host unit tests.
 * Authority: ESP-IDF v6.1 esp_err.h
 */

#pragma once

#include <stdint.h>
#include <stdio.h>
#include <assert.h>

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

#define ESP_ERR_NVS_BASE        0x1100  /*!< Starting number of NVS error codes */
#define ESP_ERR_NVS_NOT_FOUND   (ESP_ERR_NVS_BASE + 0x01)
#define ESP_ERR_NVS_NO_FREE_PAGES (ESP_ERR_NVS_BASE + 0x0d)
#define ESP_ERR_NVS_NEW_VERSION_FOUND (ESP_ERR_NVS_BASE + 0x10)

#define ESP_ERROR_CHECK(x) do {                                         \
        esp_err_t __err_rc = (x);                                       \
        (void)sizeof(__err_rc);                                         \
        assert(__err_rc == ESP_OK);                                     \
    } while(0)

static inline const char *esp_err_to_name(esp_err_t code) {
    switch (code) {
        case ESP_OK: return "ESP_OK";
        case ESP_FAIL: return "ESP_FAIL";
        case ESP_ERR_NO_MEM: return "ESP_ERR_NO_MEM";
        case ESP_ERR_INVALID_ARG: return "ESP_ERR_INVALID_ARG";
        case ESP_ERR_INVALID_STATE: return "ESP_ERR_INVALID_STATE";
        case ESP_ERR_INVALID_SIZE: return "ESP_ERR_INVALID_SIZE";
        case ESP_ERR_NOT_FOUND: return "ESP_ERR_NOT_FOUND";
        case ESP_ERR_NOT_SUPPORTED: return "ESP_ERR_NOT_SUPPORTED";
        case ESP_ERR_TIMEOUT: return "ESP_ERR_TIMEOUT";
        case ESP_ERR_INVALID_RESPONSE: return "ESP_ERR_INVALID_RESPONSE";
        case ESP_ERR_INVALID_CRC: return "ESP_ERR_INVALID_CRC";
        case ESP_ERR_INVALID_VERSION: return "ESP_ERR_INVALID_VERSION";
        case ESP_ERR_INVALID_MAC: return "ESP_ERR_INVALID_MAC";
        case ESP_ERR_NVS_NOT_FOUND: return "ESP_ERR_NVS_NOT_FOUND";
        case ESP_ERR_NVS_NO_FREE_PAGES: return "ESP_ERR_NVS_NO_FREE_PAGES";
        case ESP_ERR_NVS_NEW_VERSION_FOUND: return "ESP_ERR_NVS_NEW_VERSION_FOUND";
        default: return "ESP_ERR_UNKNOWN";
    }
}

#ifdef __cplusplus
}
#endif
