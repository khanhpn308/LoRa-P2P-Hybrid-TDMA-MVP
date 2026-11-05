# ESP-IDF Gateway Timing Instrumentation Application (Issue #11)

## Overview
Test-only firmware instrumentation running on Gateway ESP32-WROOM-32E + SX1276 (PCB HW-001).
Captures software timestamps for periodic beacon transmission, continuous uplink reception, and slotted ACK turnaround.

## HW-001 Pin Mapping
- SPI SCK: GPIO5
- SPI MISO: GPIO19
- SPI MOSI: GPIO27
- SPI CS: GPIO18
- SX1276 Reset: GPIO23
- DIO0 IRQ: GPIO26 (rising edge interrupt, minimal non-blocking ISR)
- DIO1–DIO5: NOT CONNECTED

## Fail-Closed RF Safety Gate
RF transmission is **disabled by default** (`GATEWAY_DEFAULT_RF_TX_ENABLED = false`).
Transmissions return `status = 100` (BLOCKED) unless explicit PA authorization is provided.

## Build Instructions (ESP-IDF v6.1)
```bash
cd tests/hil/rf_timing/firmware/gateway_timing_app
idf.py set-target esp32
idf.py build
```

## Host Test Build (Simulation / Regression)
```bash
gcc -Wall -Wextra -Werror -std=c11 \
    -I../common -Imain \
    ../common/timing_ring_buffer.c ../common/radio_adapter_mock.c main/main.c \
    -o gateway_timing_app_host
./gateway_timing_app_host
```
