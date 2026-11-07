#pragma once

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
#include "esp_err.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef uint32_t nvs_handle_t;

typedef enum {
    NVS_READONLY,
    NVS_READWRITE
} nvs_open_mode_t;

#define MOCK_NVS_MAX_ENTRIES 64
#define MOCK_NVS_MAX_KEY_LEN 16
#define MOCK_NVS_MAX_BLOB_SIZE 256

typedef struct {
    char key[MOCK_NVS_MAX_KEY_LEN];
    bool is_u64;
    uint64_t u64_val;
    uint8_t blob_val[MOCK_NVS_MAX_BLOB_SIZE];
    size_t blob_len;
    bool in_use;
} mock_nvs_entry_t;

typedef struct {
    mock_nvs_entry_t entries[MOCK_NVS_MAX_ENTRIES];
    uint32_t commit_count;
    uint32_t set_blob_count;
    uint32_t set_u64_count;
    uint32_t erase_count;
    esp_err_t commit_err_injection;
} mock_nvs_state_t;

extern mock_nvs_state_t g_mock_nvs;

void mock_nvs_reset(void);

esp_err_t nvs_open(const char* name, nvs_open_mode_t open_mode, nvs_handle_t *out_handle);
void nvs_close(nvs_handle_t handle);

esp_err_t nvs_get_u64(nvs_handle_t handle, const char* key, uint64_t *out_value);
esp_err_t nvs_set_u64(nvs_handle_t handle, const char* key, uint64_t value);

esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out_value, size_t* length);
esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* value, size_t length);

esp_err_t nvs_erase_key(nvs_handle_t handle, const char* key);
esp_err_t nvs_commit(nvs_handle_t handle);

#ifdef __cplusplus
}
#endif
