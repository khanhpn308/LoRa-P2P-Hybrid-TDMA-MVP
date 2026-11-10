# node_smart_backoff

Tiered smart backoff mechanism for ESP32 Sensor Node (Issue #313, part of #312).

## Features
- **Tiered Execution**:
  - `ms == 0`: Instant return with `ESP_OK`.
  - `0 < ms < 10`: Standard FreeRTOS `vTaskDelay` (minimum 1 tick) to avoid PLL relock jitter and energy overhead.
  - `ms >= 10`: SX1276 preserved in `STANDBY` mode, timer wakeup configured with 1.5ms overhead latency compensation, and ESP32 enters Light-sleep (~1mA power consumption).
- **Radio Integrity**: Guarantees SX1276 radio is kept in `STANDBY` mode (never `SLEEP`) to preserve FIFO packet buffers.
