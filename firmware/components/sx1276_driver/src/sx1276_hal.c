#include "sx1276_hal.h"
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <string.h>

static const char *TAG = "sx1276_hal";

static spi_device_handle_t s_spi_dev = NULL;
static SemaphoreHandle_t   s_spi_mutex = NULL;
static sx1276_hw_config_t  s_hw_conf;
static bool                s_initialized = false;

esp_err_t sx1276_hal_init(const sx1276_hw_config_t *hw, sx1276_dio0_isr_cb_t isr_cb, void *isr_arg)
{
    if (hw == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_initialized) {
        return ESP_OK;
    }

    s_hw_conf = *hw;

    s_spi_mutex = xSemaphoreCreateMutex();
    if (s_spi_mutex == NULL) {
        ESP_LOGE(TAG, "Failed to allocate SPI mutex");
        return ESP_ERR_NO_MEM;
    }

    // 1. Configure RESET pin (GPIO23) as Open Drain with Pullup
    gpio_config_t rst_conf = {
        .pin_bit_mask = (1ULL << s_hw_conf.pin_rst),
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err = gpio_config(&rst_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to config RST pin %d: %s", s_hw_conf.pin_rst, esp_err_to_name(err));
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
        return err;
    }
    gpio_set_level(s_hw_conf.pin_rst, 1);

    // 2. Configure SPI Bus
    spi_bus_config_t buscfg = {
        .miso_io_num = s_hw_conf.pin_miso,
        .mosi_io_num = s_hw_conf.pin_mosi,
        .sclk_io_num = s_hw_conf.pin_sck,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 260,
    };

    err = spi_bus_initialize(s_hw_conf.spi_host, &buscfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        // ESP_ERR_INVALID_STATE means bus was already initialized by system/board
        ESP_LOGE(TAG, "spi_bus_initialize failed: %s", esp_err_to_name(err));
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
        return err;
    }

    // 3. Add SX1276 device to SPI Bus (Mode 0: CPOL=0, CPHA=0, SCK idles low)
    spi_device_interface_config_t devcfg = {
        .command_bits = 0,
        .address_bits = 0,
        .dummy_bits = 0,
        .mode = 0, // Mode 0 required for SCK idling low (HW-001 strapping safety)
        .clock_speed_hz = (s_hw_conf.spi_clock_speed_hz > 0) ? s_hw_conf.spi_clock_speed_hz : 8000000,
        .spics_io_num = s_hw_conf.pin_cs,
        .queue_size = 1,
    };

    err = spi_bus_add_device(s_hw_conf.spi_host, &devcfg, &s_spi_dev);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "spi_bus_add_device failed: %s", esp_err_to_name(err));
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
        return err;
    }

    // 4. Configure DIO0 pin (GPIO26) as input with posedge interrupt
    gpio_config_t dio0_conf = {
        .pin_bit_mask = (1ULL << s_hw_conf.pin_dio0),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_POSEDGE,
    };
    err = gpio_config(&dio0_conf);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "gpio_config DIO0 failed: %s", esp_err_to_name(err));
        spi_bus_remove_device(s_spi_dev);
        s_spi_dev = NULL;
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
        return err;
    }

    if (isr_cb != NULL) {
        gpio_install_isr_service(0);
        gpio_isr_handler_add(s_hw_conf.pin_dio0, isr_cb, isr_arg);
    }

    s_initialized = true;
    return ESP_OK;
}

esp_err_t sx1276_hal_deinit(void)
{
    if (!s_initialized) {
        return ESP_OK;
    }
    gpio_isr_handler_remove(s_hw_conf.pin_dio0);
    if (s_spi_dev != NULL) {
        spi_bus_remove_device(s_spi_dev);
        s_spi_dev = NULL;
    }
    if (s_spi_mutex != NULL) {
        vSemaphoreDelete(s_spi_mutex);
        s_spi_mutex = NULL;
    }
    s_initialized = false;
    return ESP_OK;
}

esp_err_t sx1276_hal_reset(void)
{
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    // Pull reset low for >= 100 us (recommended 150 us)
    gpio_set_level(s_hw_conf.pin_rst, 0);
    esp_rom_delay_us(150);
    // Release reset to open drain high
    gpio_set_level(s_hw_conf.pin_rst, 1);
    // Delay >= 5 ms (recommended 10 ms)
    vTaskDelay(pdMS_TO_TICKS(10));
    return ESP_OK;
}

esp_err_t sx1276_hal_read_reg(uint8_t addr, uint8_t *out_val)
{
    if (!s_initialized || out_val == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t tx_buf[2] = { (uint8_t)(addr & 0x7FU), 0x00U };
    uint8_t rx_buf[2] = { 0 };

    spi_transaction_t t = {
        .length = 16,
        .tx_buffer = tx_buf,
        .rx_buffer = rx_buf,
    };

    if (xSemaphoreTake(s_spi_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t ret = spi_device_polling_transmit(s_spi_dev, &t);
    xSemaphoreGive(s_spi_mutex);

    if (ret == ESP_OK) {
        *out_val = rx_buf[1];
    }
    return ret;
}

esp_err_t sx1276_hal_write_reg(uint8_t addr, uint8_t val)
{
    if (!s_initialized) {
        return ESP_ERR_INVALID_STATE;
    }
    uint8_t tx_buf[2] = { (uint8_t)(addr | 0x80U), val };

    spi_transaction_t t = {
        .length = 16,
        .tx_buffer = tx_buf,
    };

    if (xSemaphoreTake(s_spi_mutex, pdMS_TO_TICKS(100)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t ret = spi_device_polling_transmit(s_spi_dev, &t);
    xSemaphoreGive(s_spi_mutex);
    return ret;
}

esp_err_t sx1276_hal_burst_read(uint8_t addr, uint8_t *buffer, size_t len)
{
    if (!s_initialized || buffer == NULL || len == 0 || len > 256) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t tx_buf[257];
    uint8_t rx_buf[257];
    memset(tx_buf, 0, len + 1);
    tx_buf[0] = (uint8_t)(addr & 0x7FU);

    spi_transaction_t t = {
        .length = (len + 1) * 8,
        .tx_buffer = tx_buf,
        .rx_buffer = rx_buf,
    };

    if (xSemaphoreTake(s_spi_mutex, pdMS_TO_TICKS(200)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t ret = spi_device_polling_transmit(s_spi_dev, &t);
    xSemaphoreGive(s_spi_mutex);

    if (ret == ESP_OK) {
        memcpy(buffer, &rx_buf[1], len);
    }
    return ret;
}

esp_err_t sx1276_hal_burst_write(uint8_t addr, const uint8_t *buffer, size_t len)
{
    if (!s_initialized || buffer == NULL || len == 0 || len > 256) {
        return ESP_ERR_INVALID_ARG;
    }
    uint8_t tx_buf[257];
    tx_buf[0] = (uint8_t)(addr | 0x80U);
    memcpy(&tx_buf[1], buffer, len);

    spi_transaction_t t = {
        .length = (len + 1) * 8,
        .tx_buffer = tx_buf,
    };

    if (xSemaphoreTake(s_spi_mutex, pdMS_TO_TICKS(200)) != pdTRUE) {
        return ESP_ERR_TIMEOUT;
    }
    esp_err_t ret = spi_device_polling_transmit(s_spi_dev, &t);
    xSemaphoreGive(s_spi_mutex);
    return ret;
}

esp_err_t sx1276_hal_read_modify_write(uint8_t addr, uint8_t mask, uint8_t val)
{
    uint8_t current = 0;
    esp_err_t ret = sx1276_hal_read_reg(addr, &current);
    if (ret != ESP_OK) {
        return ret;
    }
    uint8_t updated = (current & ~mask) | (val & mask);
    return sx1276_hal_write_reg(addr, updated);
}

esp_err_t sx1276_hal_verify_version(void)
{
    uint8_t version = 0;
    esp_err_t ret = sx1276_hal_read_reg(SX1276_REG_VERSION, &version);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "Failed to read RegVersion: %s", esp_err_to_name(ret));
        return ret;
    }
    if (version != SX1276_CHIP_VERSION_EXPECTED) {
        ESP_LOGE(TAG, "Invalid silicon version 0x%02X (expected 0x%02X)",
                 version, SX1276_CHIP_VERSION_EXPECTED);
        return ESP_ERR_INVALID_VERSION;
    }
    ESP_LOGI(TAG, "SX1276 silicon detected: RegVersion=0x%02X", version);
    return ESP_OK;
}
