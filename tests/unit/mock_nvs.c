#include "nvs.h"
#include "nvs_flash.h"
#include <string.h>

mock_nvs_state_t g_mock_nvs;

void mock_nvs_reset(void) {
    memset(&g_mock_nvs, 0, sizeof(g_mock_nvs));
}

esp_err_t nvs_flash_init(void) {
    return ESP_OK;
}

esp_err_t nvs_flash_erase(void) {
    mock_nvs_reset();
    return ESP_OK;
}

esp_err_t nvs_open(const char* name, nvs_open_mode_t open_mode, nvs_handle_t *out_handle) {
    (void)name;
    (void)open_mode;
    if (!out_handle) return ESP_ERR_INVALID_ARG;
    *out_handle = 1;
    return ESP_OK;
}

void nvs_close(nvs_handle_t handle) {
    (void)handle;
}

esp_err_t nvs_get_u64(nvs_handle_t handle, const char* key, uint64_t *out_value) {
    (void)handle;
    if (!key || !out_value) return ESP_ERR_INVALID_ARG;
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (g_mock_nvs.entries[i].in_use && g_mock_nvs.entries[i].is_u64) {
            if (strncmp(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN) == 0) {
                *out_value = g_mock_nvs.entries[i].u64_val;
                return ESP_OK;
            }
        }
    }
    return ESP_ERR_NVS_NOT_FOUND;
}

esp_err_t nvs_get_u32(nvs_handle_t handle, const char* key, uint32_t *out_value) {
    uint64_t val64 = 0;
    esp_err_t err = nvs_get_u64(handle, key, &val64);
    if (err == ESP_OK && out_value != NULL) {
        *out_value = (uint32_t)val64;
    }
    return err;
}

esp_err_t nvs_set_u64(nvs_handle_t handle, const char* key, uint64_t value) {
    (void)handle;
    if (!key) return ESP_ERR_INVALID_ARG;
    g_mock_nvs.set_u64_count++;

    // Find existing
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (g_mock_nvs.entries[i].in_use && strncmp(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN) == 0) {
            g_mock_nvs.entries[i].is_u64 = true;
            g_mock_nvs.entries[i].u64_val = value;
            return ESP_OK;
        }
    }

    // Allocate new
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (!g_mock_nvs.entries[i].in_use) {
            g_mock_nvs.entries[i].in_use = true;
            g_mock_nvs.entries[i].is_u64 = true;
            strncpy(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN - 1);
            g_mock_nvs.entries[i].key[MOCK_NVS_MAX_KEY_LEN - 1] = '\0';
            g_mock_nvs.entries[i].u64_val = value;
            return ESP_OK;
        }
    }

    return ESP_ERR_NO_MEM;
}

esp_err_t nvs_set_u32(nvs_handle_t handle, const char* key, uint32_t value) {
    return nvs_set_u64(handle, key, (uint64_t)value);
}

esp_err_t nvs_get_blob(nvs_handle_t handle, const char* key, void* out_value, size_t* length) {
    (void)handle;
    if (!key || !length) return ESP_ERR_INVALID_ARG;
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (g_mock_nvs.entries[i].in_use && !g_mock_nvs.entries[i].is_u64) {
            if (strncmp(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN) == 0) {
                if (!out_value) {
                    *length = g_mock_nvs.entries[i].blob_len;
                    return ESP_OK;
                }
                if (*length < g_mock_nvs.entries[i].blob_len) {
                    return ESP_ERR_INVALID_SIZE;
                }
                *length = g_mock_nvs.entries[i].blob_len;
                memcpy(out_value, g_mock_nvs.entries[i].blob_val, *length);
                return ESP_OK;
            }
        }
    }
    return ESP_ERR_NVS_NOT_FOUND;
}

esp_err_t nvs_set_blob(nvs_handle_t handle, const char* key, const void* value, size_t length) {
    (void)handle;
    if (!key || !value || length > MOCK_NVS_MAX_BLOB_SIZE) return ESP_ERR_INVALID_ARG;
    g_mock_nvs.set_blob_count++;

    // Find existing
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (g_mock_nvs.entries[i].in_use && strncmp(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN) == 0) {
            g_mock_nvs.entries[i].is_u64 = false;
            g_mock_nvs.entries[i].blob_len = length;
            memcpy(g_mock_nvs.entries[i].blob_val, value, length);
            return ESP_OK;
        }
    }

    // Allocate new
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (!g_mock_nvs.entries[i].in_use) {
            g_mock_nvs.entries[i].in_use = true;
            g_mock_nvs.entries[i].is_u64 = false;
            strncpy(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN - 1);
            g_mock_nvs.entries[i].key[MOCK_NVS_MAX_KEY_LEN - 1] = '\0';
            g_mock_nvs.entries[i].blob_len = length;
            memcpy(g_mock_nvs.entries[i].blob_val, value, length);
            return ESP_OK;
        }
    }

    return ESP_ERR_NO_MEM;
}

esp_err_t nvs_erase_key(nvs_handle_t handle, const char* key) {
    (void)handle;
    if (!key) return ESP_ERR_INVALID_ARG;
    g_mock_nvs.erase_count++;
    for (size_t i = 0; i < MOCK_NVS_MAX_ENTRIES; i++) {
        if (g_mock_nvs.entries[i].in_use && strncmp(g_mock_nvs.entries[i].key, key, MOCK_NVS_MAX_KEY_LEN) == 0) {
            memset(&g_mock_nvs.entries[i], 0, sizeof(mock_nvs_entry_t));
            return ESP_OK;
        }
    }
    return ESP_ERR_NVS_NOT_FOUND;
}

esp_err_t nvs_commit(nvs_handle_t handle) {
    (void)handle;
    if (g_mock_nvs.commit_err_injection != ESP_OK) {
        return g_mock_nvs.commit_err_injection;
    }
    g_mock_nvs.commit_count++;
    return ESP_OK;
}
