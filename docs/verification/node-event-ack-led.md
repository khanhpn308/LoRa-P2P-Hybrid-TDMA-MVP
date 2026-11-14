# Local UI — Sensor Node Event Delivery Feedback LED Verification

- **Document ID:** `VERIFY-ISSUE-396-NODE-EVENT-ACK-LED`
- **Issue Reference:** [#396: [Firmware][Node][UI] Add GPIO LED blink on verified DOWN_EVENT_ACK](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/396)
- **Status:** `TEST_AND_BUILD_VERIFIED / HARDWARE_HIL_NOT_VERIFIED`
- **Component Targets:**
  - `firmware/sensor_node/components/node_ui/`
  - `firmware/sensor_node/components/node_event_tx/`
  - `firmware/sensor_node/components/node_app/`
  - `firmware/sensor_node/main/Kconfig.projbuild`
- **ESP-IDF Target:** `ESP-IDF v6.1` (Docker image `espressif/idf:v6.1`, digest `sha256:81893c71bb5e570088901f21def8684c25cd2a9020281bd01b843a7655edb18c`)
- **Target Silicon:** `ESP32-WROOM-32E + Semtech SX1276` (HW-001 Pure CAD CSMA/CA MAC)

---

## 1. Objective and Architectural Scope

This change provides **Local UI – Event Delivery Feedback** on the Sensor Node:
When the Node transmits an `UP_EVENT` and successfully receives and cryptographically validates a matching `DOWN_EVENT_ACK` from the Gateway, and subsequently dequeues that event from its persistent FIFO (`node_event_fifo`), it pulses a local GPIO LED once (active-high HIGH for 200 ms default), drives it LOW, and continues into Deep-Sleep.

### Crucial Boundaries & Invariants:
1. **Gateway Delivery Confirmation Only:** This signal confirms physical receipt and authentication of the event at the local Gateway master. It does **not** signify backend MQTT ingestion or PostgreSQL database persistence.
2. **Exclusion of Local Alarm Autonomy:** In accordance with #230, local alarm autonomy remains abolished. This LED is merely delivery feedback, not an autonomous alarm annunciator.
3. **No Unbounded Loops / Busy-Waiting:** Pulse timing is achieved via bounded FreeRTOS task delay (`vTaskDelay(pdMS_TO_TICKS(pulse_ms))`), avoiding CPU busy-waiting.
4. **Radio Lock Isolation:** The pulse is executed in the application task (`node_app`) **after** the SX1276 radio has completed its active session and has been transitioned to sleep (`sx1276_sleep()`). No radio mutex or SPI transaction lock is held while the LED is illuminated.
5. **Fail-Safe & Non-Fatal Lifecycle:** Any GPIO initialization or driver failure logs a warning and allows the node to proceed safely to Deep-Sleep. A UI failure never causes event retransmission, event loss, or a false node revocation.
6. **Multi-Event FIFO Precision:** An ACK for Ref=1 when Ref=2 is still pending pulses the LED exactly once for Ref=1, leaving Ref=2 queued in FIFO for its subsequent transmission cycle.

---

## 2. Hardware Constraints & Pin Collision Safety (HW-001)

### 2.1 Proposed Candidate: GPIO 25 (RTC GPIO)
- **Status:** `PROPOSED / NOT_VERIFIED` (pending physical continuity / schematic confirmation by hardware owner).
- **Drive Capability:** Configured as standard active-high push-pull digital output with internal pull-down enabled (`GPIO_PULLDOWN_ENABLE`) to prevent floating/high-Z illumination during boot or sleep transitions.

### 2.2 Electrical Circuit Diagram (Recommended)
```
  ESP32 GPIO 25 ────[ 330 Ω - 1 kΩ ]────( Anode >| Cathode )──── GND (Common)
```
- Current is limited to approximately 2–5 mA (well within ESP32 12 mA drive limit). Direct power driving from GPIO without a current-limiting resistor is strictly prohibited.

### 2.3 Prohibited Hardware Pin Mapping
To prevent hardware bus collisions, strapping faults, or flash corruption, `node_ui` executes compile-time and runtime validation rejecting:
- **SX1276 HW-001 Radio Pins:** SCK (`GPIO 5`), NSS/CS (`GPIO 18`), MISO (`GPIO 19`), RST (`GPIO 23`), DIO0 (`GPIO 26`), MOSI (`GPIO 27`).
- **UART Console Pins:** TX (`GPIO 1`), RX (`GPIO 3`).
- **ESP32 SPI Flash Pins:** `GPIO 6` through `GPIO 11`.
- **Strapping Pins:** `GPIO 0`, `GPIO 2`, `GPIO 12`, `GPIO 15`.
- **Input-Only Pins (GPI):** `GPIO 34`, `GPIO 35`, `GPIO 36`, `GPIO 37`, `GPIO 38`, `GPIO 39`.
- **Configured Push Button Pin:** `CONFIG_NODE_BUTTON_GPIO` (e.g. GPIO 4 or GPIO 0).
- **Configured OLED I2C Pins:** `CONFIG_OLED_SSD1306_I2C_SDA_GPIO` (GPIO 21), `CONFIG_OLED_SSD1306_I2C_SCL_GPIO` (GPIO 22).

---

## 3. Configuration & Kconfig Interface

Configured in `firmware/sensor_node/main/Kconfig.projbuild` under `menu "Local UI & Event Delivery Feedback"`:

| Kconfig Symbol | Type | Default | Range | Description |
|---|---|---|---|---|
| `CONFIG_NODE_ACK_LED_ENABLE` | `bool` | `n` (disabled) | `y/n` | Opt-in toggle. Default disabled until physical PCB pin is confirmed. When disabled, zero GPIO setup and zero wake delay occur. |
| `CONFIG_NODE_ACK_LED_GPIO` | `int` | `25` | 0 – 33 | Output GPIO pin connected to indicator LED. Enforces pin safety checks. |
| `CONFIG_NODE_ACK_LED_PULSE_MS` | `int` | `200` | 50 – 1000 | Active HIGH duration in milliseconds (clamped to 50–1000 ms). |

---

## 4. Software Implementation Details

### 4.1 `node_ui` Component (`node_ui.h`, `node_ui.c`)
- **API:** `esp_err_t node_ui_blink_event_ack(void)`
- **Behavior:**
  - If `CONFIG_NODE_ACK_LED_ENABLE` is disabled: immediately returns `ESP_OK`.
  - If enabled:
    - Validates pin against `is_pin_prohibited()`. Returns `ESP_ERR_INVALID_ARG` if prohibited.
    - Configures pin with `gpio_config()`.
    - Asserts HIGH, waits `CONFIG_NODE_ACK_LED_PULSE_MS` (bounded task delay), asserts LOW.
    - Leaves pin LOW before returning.

### 4.2 `node_event_tx` Component (`node_event_tx.h`, `node_event_tx.c`)
- **Updated API:**
  ```c
  esp_err_t node_cad_event_tx_and_ack(const node_mac_config_t *cfg,
                                      node_event_fifo_t *fifo,
                                      uint32_t *inout_uplink_counter,
                                      bool *out_event_acked);
  ```
- **Explicit Acknowledgment Separation:**
  - `*out_event_acked` is set to `false` at function entry.
  - Set to `true` **only** when `ack_valid == true` AND `node_event_fifo_ack(fifo, event_ref)` returns `ESP_OK`.
  - If `node_event_fifo_ack` returns an error, `*out_event_acked` remains `false`, an error is logged, and the function returns the FIFO error (not `ESP_ERR_INVALID_STATE`).
  - Empty FIFO returns `ESP_OK` with `*out_event_acked == false`.
  - `DOWN_REVOKE` returns `ESP_ERR_INVALID_STATE` with `*out_event_acked == false`.

### 4.3 `node_app` Component (`node_app.c`)
- Calls `node_cad_event_tx_and_ack(..., &event_acked)`.
- Radio is placed in sleep mode (`sx1276_sleep()`) prior to LED trigger.
- If `event_acked == true`, invokes `node_ui_blink_event_ack()`.
- Logs non-fatal warning on any UI error and proceeds cleanly to Deep-Sleep.

---

## 5. Verification & Test Evidence

### 5.1 Unit Tests (Host C11 `-Wall -Wextra -Werror -pedantic -std=c11`)

#### Suite 1: Node UI ACK LED & Pin Collision Suite (`test_node_ui.c`)
Command: `gcc -Wall -Wextra -Werror -pedantic -std=c11 -I tests/unit/mock_esp/ firmware/sensor_node/components/node_ui/test/test_node_ui.c -o /tmp/test_node_ui && /tmp/test_node_ui`
Output:
```
=== Running Node UI ACK LED Unit Tests ===
Running test_prohibited_pins_sx1276 ... PASSED
Running test_prohibited_pins_system ... PASSED
Running test_permitted_pin_candidate ... PASSED
Running test_blink_disabled_noop ... PASSED
Running test_blink_enabled_prohibited_pin_fails ... PASSED
Running test_blink_enabled_nominal_pulse ... PASSED
Running test_blink_pulse_duration_clamping ... PASSED
Running test_blink_gpio_config_failure_propagation ... PASSED

Test summary: ALL PASSED (0 failures)
```

#### Suite 2: Node Event TX & Explicit ACK Logic Suite (`test_node_event_tx.c`)
Command: `gcc -Wall -Wextra -Werror -pedantic -std=c11 ... firmware/sensor_node/components/node_event_tx/test/test_node_event_tx.c -o /tmp/test_node_event_tx && /tmp/test_node_event_tx`
Output:
```
=== Running Node Event TX Unit Tests ===
Running test_arg_validation ... PASSED
Running test_empty_fifo ... PASSED
Running test_cad_busy_timeout ... PASSED
Running test_tx_fail_timeout ... PASSED
Running test_down_revoke ... PASSED
Running test_successful_ack ... PASSED
Running test_multi_event_fifo_partial_ack ... PASSED
Running test_fifo_ack_failure_non_fatal ... PASSED
Running test_negative_ref_mismatch_no_ack ... PASSED
Running test_negative_corrupt_header_no_ack ... PASSED

Test summary: ALL PASSED (0 failures)
```

#### Suite 3: Repository Unit Regression Tests (`python3 -m unittest`)
Command: `python3 -m unittest discover -s tests/unit -p "test_*.py"`
Output:
```
Ran 30 tests in 1.767s
OK
```

### 5.2 Real ESP-IDF v6.1 Docker Compilation Verification

Both configurations were compiled against the official pinned ESP-IDF v6.1 Docker container (`espressif/idf:v6.1`):
1. **Default Configuration (`CONFIG_NODE_ACK_LED_ENABLE` disabled):**
   - Command: `docker run --rm --network=none -v $(pwd):/workspace -w /workspace/firmware/sensor_node espressif/idf:v6.1 idf.py build`
   - Result: Exit code `0` (Binary size: `0x50310` bytes, 69% free partition).
2. **Enabled Configuration (`CONFIG_NODE_ACK_LED_ENABLE=y`, GPIO 25, 200 ms):**
   - Command: `docker run --rm --network=none -v $(pwd):/workspace -w /workspace/firmware/sensor_node espressif/idf:v6.1 idf.py build`
   - Result: Exit code `0` (Binary size: `0x50510` bytes, 69% free partition).

---

## 6. Hardware Bench / HIL Verification Notice

- **Physical Pin Availability:** `NOT_VERIFIED` (pending physical bench wiring and oscilloscope / logic analyzer probe).
- **Pulse Duration Verification:** Software timing verified via task delay unit tests. Real physical rise/fall times and ±20 ms duration tolerance remain `NOT_VERIFIED` until hardware bench measurement.
