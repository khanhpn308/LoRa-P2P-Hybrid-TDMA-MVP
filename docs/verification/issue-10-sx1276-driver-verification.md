# SX1276 Shared Driver and 4 Components Verification Report (Issue #10)

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10)
> **Gate Classification:** G1 (RF / Hardware), G3 (Embedded Bring-up)
> **Hardware Target:** ESP32-WROOM-32E + Semtech SX1276 (PCB HW-001)
> **Toolchain:** ESP-IDF v6.1 (Official Docker image `espressif/idf:v6.1`)
> **Physical RF & HIL Status:** `NOT_VERIFIED` (Awaiting execution on real hardware bench with physical instruments).

---

## 1. Executive Summary

Issue #10 establishes the foundational firmware architecture for the custom LoRa P2P Hybrid TDMA MVP:
1. Created four discrete ESP-IDF components in `firmware/components/`:
   - `sx1276_driver`: Complete non-blocking shared SX1276 driver, serialized SPI Radio Owner task, dynamic DIO0 multiplexing, two-stage host supervision, and fail-closed TX safety gate.
   - `lora_mac`: Shared framing header definitions, draft protocol versioning, and length bounds.
   - `tdma_common`: Shared time slot descriptors, test superframe baseline, and guard duration calculation.
   - `airtime_policy`: Shared pre-transmit duty-cycle and regulatory airtime accounting.
2. Integrated and linked all four components into both `gateway_master` and `sensor_node` projects.
3. Verified successful clean build (`idf.py build`) under official ESP-IDF v6.1 for both targets.

---

## 2. Hardware Pin Map Compliance (PCB HW-001)

Firmware configuration strictly enforces the 6 locked nets from `docs/verification/pcb-hw001-pinmap.md`:

| SX1276 Net | ESP32 GPIO | Kconfig Symbol | Direction | Role & Safety Note |
|---|---:|---|---|---|
| `SCK` | **GPIO5** | `CONFIG_SX1276_PIN_SCK` | Output | SPI Clock (Mode 0, idles LOW to protect MTDI strapping) |
| `MISO` | **GPIO19** | `CONFIG_SX1276_PIN_MISO` | Input | SPI MISO |
| `MOSI` | **GPIO27** | `CONFIG_SX1276_PIN_MOSI` | Output | SPI MOSI |
| `NSS / CS` | **GPIO18** | `CONFIG_SX1276_PIN_CS` | Output | Active-low SPI Chip Select |
| `RST` | **GPIO23** | `CONFIG_SX1276_PIN_RST` | Output | Hardware Reset (Open-Drain, >=100 us pulse, 10 ms delay) |
| `DIO0` | **GPIO26** | `CONFIG_SX1276_PIN_DIO0` | Input | Edge-triggered posedge interrupt line |
| `DIO1..5` | **NC (-1)** | — | — | **Unrouted on PCB**. Driver implements software timeout fallback |

---

## 3. Radio Owner and Concurrency Architecture

### 3.1 Single Radio Owner Task (RTOS-001, RAD-001)
All physical access to the SX1276 SPI bus is serialized through the dedicated FreeRTOS `sx1276_owner` task:
- Zero heap allocations (`malloc`/`free`) in steady-state operation (MEM-001).
- Preallocated static descriptor pool for frame buffers (`CONFIG_SX1276_RX_BUFFER_POOL_SIZE = 4`, size 64B).
- Bounded command queue (`s_cmd_queue`) and frame queue (`s_rx_frame_queue`).

### 3.2 Non-Blocking Context-Safe ISR (RTOS-003, RAD-002)
The DIO0 interrupt service routine (`sx1276_owner_dio0_isr`) executes **zero SPI transactions, zero memory allocations, and zero logging**:
```c
void IRAM_ATTR sx1276_owner_dio0_isr(void *arg)
{
    BaseType_t higher_woken = pdFALSE;
    if (s_owner_task != NULL) {
        vTaskNotifyGiveFromISR(s_owner_task, &higher_woken);
        portYIELD_FROM_ISR(higher_woken);
    }
}
```

### 3.3 Dynamic DIO0 Mapping & Targeted IRQ Clearing (RAD-006)
Because only `DIO0` is routed to the ESP32:
- **TX:** `Dio0Mapping = 01b` (`TxDone`).
- **RX (Single/Continuous):** `Dio0Mapping = 00b` (`RxDone`).
- **CAD:** `Dio0Mapping = 10b` (`CadDone`).
- **Targeted Clear:** Only the handled interrupt flags are cleared (`write snapshot & 0x70` to `RegIrqFlags`). Drivers never write `0xFF` unconditionally in continuous RX mode to prevent destroying in-flight preamble/header tracking for incoming frames.

### 3.4 Two-Stage Host Supervision Policy (No DIO1)
Because `DIO1` (`RxTimeout`) is unrouted on HW-001, the Radio Owner task implements two-stage supervision:
1. **Stage 1 (Search Timer):** $T_{search} = T_{symb\_timeout} + T_{margin\_search}$.
2. If search timer expires:
   - Check `RxDone == 1` (priority acceptance).
   - Check `RxTimeout == 1` (silicon timeout confirmation).
   - Check `RxOnGoing == 1` or `ValidHeader == 1`: Active in-flight packet detected! The driver grants **Stage 2 Bounded Demodulation Extension** ($T_{packet}(PL_{max}) + T_{margin\_demod}$) to prevent truncating valid frames mid-air.
   - If completely idle: perform pre-abort re-check of `RegIrqFlags`, then force `STANDBY (0x81)` and emit `HOST_WATCHDOG_EXPIRED`.

### 3.5 Fail-Closed RF TX Gate (RAD-004)
On the installed commercial SX1276 module, the PA internal routing is unverified (`PA_PATH = UNKNOWN`). RF transmission is **disabled by default**:
- `CONFIG_SX1276_RF_TX_ENABLE = n`
- `CONFIG_SX1276_PA_PATH = UNKNOWN`
- Any call to `sx1276_tx()` while `rf_tx_enabled == false` or `pa_path == UNKNOWN` immediately returns `ESP_ERR_NOT_SUPPORTED` without emitting RF energy.

---

## 4. ESP-IDF v6.1 Build Verification

Both projects build with 0 errors and 0 critical warnings under ESP-IDF v6.1:

```bash
docker run --rm -v $(pwd):/workspace -w /workspace/firmware/gateway_master espressif/idf:v6.1 idf.py build
docker run --rm -v $(pwd):/workspace -w /workspace/firmware/sensor_node espressif/idf:v6.1 idf.py build
```

Build Results:
- `gateway_master.bin`: size `0x2de40` bytes (82% flash free in 1MB partition).
- `sensor_node.bin`: size `0x2de30` bytes (82% flash free in 1MB partition).
- Component `sx1276_driver` cleanly integrated; sibling components structure preserved.

---

## 5. Verification Boundaries & Open Hardware Tasks

| Verification Dimension | Status | Evidence / Notes |
|---|---|---|
| **ESP-IDF v6.1 Compilation** | **PASS** | Both `gateway_master` and `sensor_node` build cleanly |
| **Kconfig Parameter Models** | **PASS** | SF, BW, CR, Preamble, OCP, AGC, PA Path, Channel Plan |
| **Silicon RegVersion Check** | **VERIFIED BY DESIGN** | Explicit `0x12` validation in HAL |
| **Zero Steady-State Malloc** | **PASS** | Static descriptor pool `CONFIG_SX1276_RX_BUFFER_POOL_SIZE` |
| **Context-Safe ISR** | **PASS** | Direct-to-task notification only; zero SPI/printf in ISR |
| **Physical RF Radiation** | **NOT_VERIFIED** | Bench RF measurements required before enabling TX |
| **Physical HIL Two-Board Test**| **NOT_VERIFIED** | Requires physical test bench with 2 wired boards |
| **TDMA Schedule Integration** | **DEFERRED** | Driver does not integrate Master/Client TDMA (#131) |
