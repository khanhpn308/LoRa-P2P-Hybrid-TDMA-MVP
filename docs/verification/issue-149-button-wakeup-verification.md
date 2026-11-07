# Issue #149: Sensor Node Deep-Sleep Button Wakeup & Debounce Verification Dossier

- **Document ID:** `VERIFY-ISSUE-149-BUTTON-WAKEUP`
- **Issue Reference:** [#149: [Firmware][Node] Button Wake-up, Debounce and Event Trigger](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149)
- **Status:** `IMPLEMENTATION_COMPLETE / HIL_UNIT_VERIFIED / READY_FOR_HARDWARE_BENCH`
- **Component Target:** `firmware/sensor_node/`
- **ESP-IDF Target:** `ESP-IDF v6.1`
- **Target Silicon:** `ESP32-WROOM-32E (Revision v3.0) + Semtech SX1276`

---

## 1. Overview and Architecture

In accordance with Owner architecture decisions for the Event-Only Hybrid TDMA system (Refs #125, #131), the Sensor Node defaults to **Deep-Sleep mode** to maximize energy efficiency and preserve battery life.

Physical push button activation serves as a manual alarm / external trigger to wake the ESP32 from Deep-Sleep, qualify the electrical signal, filter mechanical contact bouncing, push an event intent into the persistent event FIFO (`node_event_fifo`), and return safely to sleep without transmitting unauthorized, out-of-schedule RF packets.

---

## 2. Pinout Safety & HW-001 Pinmap Protection

To prevent bus contention and hardware strapping failures:
1. **Radio Pin Protection:** The button driver explicitly validates and rejects any GPIO belonging to the locked HW-001 SX1276 interface ([`pcb-hw001-pinmap.md`](docs/verification/pcb-hw001-pinmap.md)):
   - `SCK = GPIO 5`
   - `MISO = GPIO 19`
   - `MOSI = GPIO 27`
   - `CS = GPIO 18`
   - `RST = GPIO 23`
   - `DIO0 = GPIO 26`
2. **UART Console Protection:** UART TX (`GPIO 1`) and RX (`GPIO 3`) are strictly prohibited.
3. **RTC GPIO Requirement:** Deep-sleep `EXT0` wakeup requires the pin to reside within the ESP32 RTC power domain (GPIO 0, 2, 4, 12-15, 25-27, 32-39). The driver strictly checks `is_rtc_gpio()` during initialization.

---

## 3. Kconfig Menuconfig Configuration

User-configurable options are exposed via `firmware/sensor_node/main/Kconfig.projbuild`:

| Kconfig Symbol | Default | Range / Type | Description |
|---|---|---|---|
| `CONFIG_NODE_BUTTON_GPIO` | `4` | 0 – 39 (int) | GPIO connected to the external push button. |
| `CONFIG_NODE_BUTTON_ACTIVE_LEVEL` | `0` | 0 or 1 (int) | `0` = Active Low (shorts to GND, internal pull-up). `1` = Active High (shorts to 3.3V, internal pull-down). |
| `CONFIG_NODE_BUTTON_DEBOUNCE_MS` | `50` | 5 – 500 ms (int) | Software debounce duration to qualify stable asserted level. |
| `CONFIG_NODE_BUTTON_HOLD_TIME_MS` | `20` | 5 – 200 ms (int) | Minimum press hold time. |
| `CONFIG_NODE_DEEP_SLEEP_TIMEOUT_SEC` | `0` | 0 – 86400 s (int) | Optional periodic fallback wakeup timer (0 = disabled, button wakeup only). |

---

## 4. Debounce State Machine & Anti-Storm Loop Protection

Mechanical push buttons introduce switch contact bounce lasting 5–30 ms. If unmitigated, bouncing triggers repeated wakeups and event storms.

### 4.1 Qualification Process
1. **Immediate Inspection:** At wakeup, `button_driver_qualify_press()` reads `gpio_get_level()`. If the signal is not at `active_level`, it is dismissed as a transient spike.
2. **Debounce Time Window:** The driver samples the pin level every 5 ms across the configured `debounce_ms` window. If the level drops to inactive at any point, the press is rejected.
3. **Release & Stuck-Button Protection:** Before re-entering Deep-Sleep, the driver monitors the pin until the button is released. If held down continuously (> 3000 ms), it logs a warning and arms sleep only after release or release timeout, preventing immediate wake storms.

---

## 5. Persistent Event FIFO Handoff

Upon qualifying a valid button press:
- An event with `event_code = 0x01` (Manual Button Alarm), `event_value = 1`, and the current timestamp is pushed into `s_event_fifo` using `node_event_fifo_push()`.
- `s_event_fifo` is allocated with `RTC_DATA_ATTR`, ensuring event queue state and sequence numbers persist across Deep-Sleep cycles.
- Radio RF transmission is **NOT** executed immediately (fail-closed); transmission occurs strictly when authorized within the assigned TDMA DATA slot.

---

## 6. How to Configure and Test on Hardware

### 6.1 Configure via Menuconfig
From the sensor node directory:
```bash
cd firmware/sensor_node
idf.py menuconfig
```
Navigate to:
> `Sensor Node Button Wakeup and Power Configuration`
> - Set `Wakeup Button GPIO Pin` (e.g. `4` for external button, or `0` for BOOT button).
> - Set `Button Active Trigger Level` (`0` for button to GND, `1` for button to 3.3V).
> - Set `Software Debounce Duration (ms)` (default 50 ms).

Save and exit.

### 6.2 Build and Flash
```bash
idf.py build flash monitor
```

### 6.3 Expected Terminal Behavior
1. **Initial Boot:**
   ```text
   Starting Sensor Node Boot #1 (ESP-IDF v6.1 / HW-001)
   Persistent Node Event FIFO initialized (capacity: 16 items)
   Button driver initialized on GPIO 4 (Active Level: 0, Debounce: 50 ms)
   [WAKE CAUSE] Power-On Reset or Software Restart
   SX1276 initialized successfully in STANDBY mode
   FIFO State: Pending Events = 0, Dropped Events = 0
   Armed Deep-Sleep EXT0 wakeup on GPIO 4 (Trigger Level: 0)
   Entering Deep-Sleep mode. Press button on GPIO 4 to wake up...
   ```
2. **Pressing Button:**
   ```text
   Starting Sensor Node Boot #2 (ESP-IDF v6.1 / HW-001)
   [WAKE CAUSE] EXT0 Button Wakeup detected on GPIO 4
   Button press verified: stable asserted level for 50 ms
   Button released after 120 ms. Re-armed.
   >>> EVENT ENQUEUED <<< Ref: 1, Total button events: 1
   FIFO State: Pending Events = 1, Dropped Events = 0
   Armed Deep-Sleep EXT0 wakeup on GPIO 4 (Trigger Level: 0)
   Entering Deep-Sleep mode. Press button on GPIO 4 to wake up...
   ```
3. **Contact Bounce / Noise Pulse:**
   ```text
   Starting Sensor Node Boot #3 (ESP-IDF v6.1 / HW-001)
   [WAKE CAUSE] EXT0 Button Wakeup detected on GPIO 4
   Button bounced inactive after 15 ms: rejected
   Transient wake without qualified button press (bounce/noise filtered)
   FIFO State: Pending Events = 1, Dropped Events = 0
   ...
   ```

---

## 7. Verification Evidence Summary

- **Firmware Build:** PASS (`ESP-IDF v6.1`, `sensor_node.bin` size: 0x31d10 bytes, 81% flash free).
- **HIL & State Machine Unit Tests:** PASS (`tests/hil/test_node_button_hil.py` - 6/6 tests OK).
- **Quality Gates:** Zero out-of-scope modifications outside `firmware/sensor_node/`, `tests/hil/`, and `docs/verification/`.
