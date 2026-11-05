# ESP32-WROOM-32E + SX1276 PCB HW-001 Pin Map & Hardware Interface Specification

> **Document Status:** `CONFIRMED_IN_PRIOR_OWNER_HW-001_SOURCE` (for the 6 locked SX1276 nets); `OWNER_CONFIRMED_HARDWARE_DESIGN` (for DIO1–DIO5 unrouted); `PHYSICAL_BOARD_CONTINUITY/REVISION_NOT_VERIFIED` (for physical continuity, board revision, button GPIO/circuit, power rails, RTC wake).
> **Source Issue:** [#150](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/150)
> **Target Path:** `docs/verification/pcb-hw001-pinmap.md`
> **Gate Classification:** G1 (RF / Hardware), G3 (Embedded Bring-up)
> **Related Issues:** [#9](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/9) (Historical board bring-up), [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) (SX1276 shared driver), [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125) (Static TDMA), [#131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131) (Event-only deep-sleep integration), [#149](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149) (Deep-sleep GPIO button/debounce), [#156](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/156) (SX1276 agent reference docs).

---

## 1. Overview and Authority

This document formalizes the physical pin mapping, signal ownership, and hardware interface constraints for the **ESP32-WROOM-32E + Semtech SX1276** custom hardware revision **HW-001**.

### 1.1 Owner Provenance and Baseline Sources

The pin mapping defined herein originates from owner-confirmed baseline repositories and design assertions:
1. **Prior Baseline Repository (`khanhpn308/esp32e_sx1768-915Mhz`):**
   - [`AGENTS.md`](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/main/AGENTS.md): Confirmed owner HW-001 lock.
   - [`board_pins.h`](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/main/components/board_config/include/board_pins.h) (Git blob `dd282f240602f69d19f4f66eb998cb59f2f6b812`): Defines the six physical nets (`BOARD_LORA_*`).
   - [`docs/C_CODING_STANDARDS.md`](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/main/docs/C_CODING_STANDARDS.md): Confirms pin definitions and strapping pin constraints.
2. **Owner-Supplied Hardware Reference (2026-11-05):**
   - Photographic PCB pinout reference asserted by the Project Owner as the fixed physical pinout for the assembled HW-001 board.
3. **Owner Design Clarification (2026-11-05):**
   - Confirmation that SX1276 interrupt pins `DIO1` through `DIO5` are **NOT connected** to the ESP32 host on HW-001.

> [!WARNING]
> **Evidence Boundary:**
> A photographic reference or design assertion establishes design intent, **not** measured empirical proof. Physical board continuity, trace impedance, assembled board revisions, power rail stability, and boot strapping behavior remain `NOT_VERIFIED` until tested on physical hardware (HIL). Under no circumstance should AI coding agents or PR reviews treat documentation adoption alone as `HIL_PASS` or `RF_PASS`.

---

## 2. Source-Locked PCB HW-001 Pin Map

The following six nets form the locked physical interface between the ESP32-WROOM-32E host and the SX1276 transceiver:

| SX1276 Net | ESP32 GPIO | Firmware Symbol | Direction | Electrical / Functional Constraints | Disposition |
|---|---:|---|---|---|---|
| `LoRa_SCK` | **GPIO5** | `BOARD_LORA_SCK` | ESP32 $\rightarrow$ SX1276 | SPI Clock (Max 10 MHz). **Caution: ESP32 Strapping Pin (MTDI).** Must idle LOW in SPI Mode 0 and never bias strapping state during ESP32 reset. | **Locked HW-001** |
| `LoRa_MISO` | **GPIO19** | `BOARD_LORA_MISO` | SX1276 $\rightarrow$ ESP32 | SPI Master In / Slave Out. High-impedance when NSS is high. Data changes on falling edge of SCK. | **Locked HW-001** |
| `LoRa_MOSI` | **GPIO27** | `BOARD_LORA_MOSI` | ESP32 $\rightarrow$ SX1276 | SPI Master Out / Slave In. Master shifts data on falling edge; SX1276 samples on rising edge. | **Locked HW-001** |
| `LoRa_SS / CS / NSS`| **GPIO18** | `BOARD_LORA_CS` | ESP32 $\rightarrow$ SX1276 | Active-low SPI Chip Select. Held LOW exclusively during active SPI bus transaction. | **Locked HW-001** |
| `LoRa_RST` | **GPIO23** | `BOARD_LORA_RST` | ESP32 $\rightarrow$ SX1276 | Active-low Hardware Reset. Drive LOW $\ge 100\ \mu\text{s}$ (recommended $150\ \mu\text{s}$), then float/open-drain, delay $\ge 10\ \text{ms}$. | **Locked HW-001** |
| `LoRa_DIO0` | **GPIO26** | `BOARD_LORA_DIO0` | SX1276 $\rightarrow$ ESP32 | Edge-triggered Hardware Interrupt (posedge). Dynamically mapped via `RegDioMapping1` (`0x40`) to `TxDone`, `RxDone`, or `CadDone`. | **Locked HW-001** |

### 2.1 Critical Hardware and Strapping Pin Rules

1. **SCK and CS Must NOT Be Interchanged:**
   `SCK = GPIO5` and `CS = GPIO18`. Swapping these pins will cause bus failure and violate boot strapping conditions.
2. **Strapping Pin Vulnerability (GPIO5 / MTDI):**
   `GPIO5` is an ESP32 strapping pin that configures SDIO slave timing / boot voltage. The attached SX1276 clock line and pull resistors must not bias `GPIO5` during power-on or chip reset. Bus idling must be configured for SPI Mode 0 (CPOL=0, CPHA=0) where `SCK` idles LOW.
3. **No Pin Multiplexing / Peripheral Re-use:**
   None of these six GPIOs (`GPIO5`, `GPIO18`, `GPIO19`, `GPIO23`, `GPIO26`, `GPIO27`) may be shared or re-assigned to pushbuttons, LEDs, sensors, UART, or other external devices.
4. **SPI Host Controller Disambiguation:**
   The legacy firmware repository references `SPI2_HOST` (VSPI controller). While `SPI2_HOST` is the verified software host for these GPIO mappings, its configuration in new firmware must be validated against ESP-IDF v6.1 SPI master APIs without assuming unverified clock rates or DMA settings.

---

## 3. Disconnection of DIO1–DIO5 and Driver Architectural Impact

### 3.1 Hardware Status: `NOT_CONNECTED`
SX1276 interrupt pins `DIO1`, `DIO2`, `DIO3`, `DIO4`, and `DIO5` are **unrouted / NOT connected** to any ESP32 GPIO on the HW-001 PCB:

| SX1276 Pin | Routing Status | Impact on Firmware |
|---|---|---|
| `DIO1` | **NOT_CONNECTED** | Cannot generate hardware IRQ for `RxTimeout`, `FhssChangeChannel`, or `CadDetected`. |
| `DIO2` | **NOT_CONNECTED** | Cannot generate hardware IRQ for `FhssChangeChannel`. |
| `DIO3` | **NOT_CONNECTED** | Cannot generate hardware IRQ for `CadDone`, `ValidHeader`, or `PayloadCrcError`. |
| `DIO4` | **NOT_CONNECTED** | Cannot generate hardware IRQ for `CadDetected`, `PllLock`. |
| `DIO5` | **NOT_CONNECTED** | Cannot generate hardware IRQ for `ModeReady`, `ClkOut`. |

### 3.2 Firmware Constraints for Issue #10 (SX1276 Shared Driver)
Because only `DIO0` (`GPIO26`) is wired to the ESP32:
1. **Dynamic DIO0 Re-mapping:**
   The single Radio Owner task must dynamically multiplex `DIO0` via `RegDioMapping1` (`0x40`) prior to initiating operations:
   - For Transmit: write `Dio0Mapping = 01` (`TxDone`).
   - For Receive: write `Dio0Mapping = 00` (`RxDone`).
   - For CAD: write `Dio0Mapping = 10` (`CadDone`).
2. **Software-Enforced RX Timeout Fallback:**
   Because `DIO1` (`RxTimeout`) is not routed, the Radio Owner task cannot rely on an external pin interrupt to abort timed-out receptions. The driver must implement a bounded FreeRTOS host timer or task notification timeout matching the expected symbol duration / slot budget:
   $$\text{Timeout}_{\text{host}} = \text{SlotDuration} + \text{GuardBand}$$
3. **Targeted IRQ Clearing:**
   To prevent dropping race-condition interrupts during continuous receive (`RXCONT`), firmware must write-1-to-clear only the processed flags (e.g., `snapshot & 0x70` for `RxDone`, `PayloadCrcError`, `ValidHeader`), and **never write `0xFF` unconditionally** to `RegIrqFlags`.
4. **No Synthetic GPIO Definitions:**
   Firmware headers must define `BOARD_LORA_DIO1` through `BOARD_LORA_DIO5` as `GPIO_NUM_NC` (`-1`). Drivers must not simulate physical IRQ registrations on unrouted lines.

---

## 4. Conflict Analysis: Educational Module 04 vs. PCB HW-001

A significant conflict exists between the illustrative textbook example in `docs/Books/Module_04_Hardware_Design.md` §2.2.3 and the actual HW-001 physical PCB:

| Signal / Net | Educational Module 04 (§2.2.3) | Actual PCB HW-001 (Locked) | Conflict Nature & Risk |
|---|---|---|---|
| **SPI SCK** | `GPIO18` (VSPI CLK) | **GPIO5** | **Direct Swap:** Inverted with CS. Causes complete SPI communication failure and potentially violates ESP32 boot strapping. |
| **SPI NSS / CS** | `GPIO5` (VSPI CS0) | **GPIO18** | **Direct Swap:** Inverted with SCK. Transceiver CS will toggle inappropriately on clock cycles. |
| **Reset (RST)** | `GPIO14` | **GPIO23** | **Wrong Pin:** Transceiver reset line cannot be asserted; radio remains uninitialized or hung. |
| **DIO0** | `GPIO26` | `GPIO26` | Identical (both specify `GPIO26`). |
| **DIO1** | `GPIO33` | **NOT_CONNECTED** (`-1`) | **Phantom Connection:** Module 04 assumes `DIO1` routed to `GPIO33`. HW-001 does not route `DIO1`. |
| **BUSY / Transceiver** | `GPIO32` (SX1262) | **Not Applicable** (SX1276) | **Inapplicable Hardware:** Project uses Semtech SX1276; SX1262 `BUSY` pin logic does not apply. |

### 4.1 Directive for Firmware Implementation
- `docs/Books/Module_04_Hardware_Design.md` is strictly **illustrative and educational**. It is not an engineering specification.
- All firmware implementation in [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) and board configuration headers **must strictly use the HW-001 pin map** (`SCK=5`, `MISO=19`, `MOSI=27`, `CS=18`, `RST=23`, `DIO0=26`).
- Educational GPIO values (`SCK=18`, `CS=5`, `RST=14`, `DIO1=33`, `BUSY=32`) must be barred from all firmware headers, board configs, and test harnesses.

---

## 5. Deep-Sleep Button Wake-Up & Integration Requirements (#149, #125, #131)

### 5.1 Button GPIO Selection Status: `NOT_VERIFIED`
The physical push-button used to trigger event-driven sensor transmissions is currently under architectural evaluation in Issue [#149](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149).

> [!CAUTION]
> **Do Not Assume GPIO33:**
> Developers must **NOT** adopt `GPIO33` simply because educational Module 04 mentions it for `DIO1`. The button GPIO must be explicitly selected by the Project Owner based on RTC GPIO domain eligibility, hardware pull-up/down circuitry, and PCB trace routing.

### 5.2 Deep-Sleep RTC Wake Constraints
For the button to wake the ESP32-WROOM-32E from Deep-Sleep (`esp_sleep_enable_ext0_wakeup` or `esp_sleep_enable_ext1_wakeup`), the chosen GPIO **must belong to the RTC GPIO domain**:
- Valid RTC GPIOs on ESP32: `0, 2, 4, 12, 13, 14, 15, 25, 26, 27, 32, 33, 34, 35, 36, 37, 38, 39`.
- However, `GPIO26` (DIO0) and `GPIO27` (MOSI) are already dedicated to the SX1276 and cannot be reused.
- Pins `34, 35, 36, 39` are input-only and lack internal software-configurable pull-up/down resistors; if used, an external pull resistor network is mandatory.
- The button electrical circuit, active state (active-high vs. active-low), external filtering capacitor, hardware debounce latch, and RTC wake loop handling remain `NOT_VERIFIED`.

### 5.3 TDMA Transmission Protocol Invariant (#125, #131)
Under the Hybrid TDMA architecture:
1. **No Autonomous Radio Transmission on Wake:**
   Waking up via button press must **NEVER** trigger an immediate or unscheduled LoRa RF transmission.
2. **Event Queueing:**
   Upon waking from Deep-sleep via RTC button interrupt, the node firmware must:
   - Perform hardware debounce and button state validation.
   - Increment the local persistent event counter.
   - Enqueue the event payload into local memory/RTC storage.
   - Await the Gateway's next scheduled TDMA Beacon / Uplink Slot assigned to this Node, or use the contention-based CSMA/CA slot strictly according to TDMA protocol rules.
   - Unscheduled transmissions violate airtime budgets, cause packet collisions, and break deterministic TDMA scheduling.

---

## 6. Verification Status Checklist & Missing Data

The following checklist details the empirical and hardware verification required before production firmware sign-off on [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) and [#149](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149):

| Check Item | Description | Authority / Source | Current Verification Status |
|---|---|---|---|
| **Six Locked SX1276 Nets** | `SCK=5`, `MISO=19`, `MOSI=27`, `CS=18`, `RST=23`, `DIO0=26` | `khanhpn308/esp32e_sx1768-915Mhz` baseline + Owner image | `CONFIRMED_IN_PRIOR_OWNER_HW-001_SOURCE` |
| **DIO1–DIO5 Status** | Unrouted to ESP32 host (`NOT_CONNECTED`) | Owner conversation (2026-11-05) | `OWNER_CONFIRMED_HARDWARE_DESIGN` |
| **PCB Trace Continuity** | Physical multimeter / schematic netlist continuity test on assembled boards | Lab test | `NOT_VERIFIED` |
| **Board Revision ID** | Formal silkscreen / revision marking identifying HW-001 vs. other PCB revisions | Owner / Lab | `NOT_VERIFIED` |
| **Gateway vs Node Parity**| Confirmation whether Gateway and Node utilize identical PCB layout or distinct boards | Owner / Lab | `NOT_VERIFIED` |
| **GPIO5 Strapping Impact** | Verification that SX1276 SCK loading does not cause boot hang or flash voltage strapping faults | Lab scope measurement | `NOT_VERIFIED` |
| **DIO0 IRQ Latency** | Time from RF packet arrival to FreeRTOS Radio Owner task wake on GPIO26 posedge | HIL benchmark | `NOT_VERIFIED` |
| **Button GPIO Selection** | Assignment of dedicated RTC-capable GPIO for manual trigger button | Issue [#149](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149) | `NOT_VERIFIED` |
| **Button Electrical Circuit** | Pressed level, pull resistor, hold/release behavior, RC filter, debounce latch | Issue [#149](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/149) | `NOT_VERIFIED` |
| **Power Rails & Quiescent Load** | SX1276 and ESP32 3.3V rails, LDO quiescent current, deep-sleep current consumption | Bench measurement | `NOT_VERIFIED` |
| **SX1276 Wake / Back-power** | Transceiver state during ESP32 deep-sleep, SPI bus leakage prevention, safe re-init | Bench measurement | `NOT_VERIFIED` |
| **RF Compliance & Power** | Antenna matching, TX output power, harmonic suppression, 921.4 MHz regulatory check | RF Lab spectrum analyzer | `NOT_VERIFIED` |

---

## 7. Next Actions and Cross-Team Handoff

1. **Embedded / Firmware (#10):**
   Create `firmware/components/board_config/include/board_pins.h` adopting solely the six locked HW-001 pins and defining `BOARD_LORA_DIO1`..`5` as `-1` (`GPIO_NUM_NC`). Ensure SPI Mode 0 and proper reset timing.
2. **Deep-Sleep & Power Management (#149):**
   Conclude technical evaluation of the wake button GPIO, verify RTC domain compatibility, and record electrical debounce parameters without altering the six locked radio pins.
3. **TDMA Protocol Integration (#125, #131):**
   Verify that wake-up events enqueue packets into the TDMA frame buffer without causing out-of-schedule transmissions.
4. **Hardware Lab Bring-up:**
   Execute physical multimeter continuity check and strapping pin oscilloscope traces across both Gateway and Node boards to promote `PHYSICAL_BOARD_CONTINUITY/REVISION_NOT_VERIFIED` to verified status.
