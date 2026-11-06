# ESP32-WROOM-32E + SX1276 RF/HIL Timing Bench Setup and Measurement Procedure

## Document Metadata
- **Document Status:** `APPROVED_BENCH_PROCEDURE / PHYSICAL_EXECUTION_PENDING`
- **Source Issue:** [Issue #169](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169)
- **Baseline Authority:** Merged PR #202 (Commit `5ce67822e82edc6582879081ea0bd6ea79104b68`)
- **Dependencies:** [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11), [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10), [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127), [#19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19), [#130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130), [#131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131)
- **Architectural Authority:** [ADR-0001 (Hybrid TDMA)](../adr/0001-hybrid-tdma.md), [ADR-0003 (ESP-IDF v6.1)](../adr/0003-esp-idf-v6-1.md), [ADR-0004 (Timing Budget)](../adr/0004-theoretical-timing-guard-budget.md)
- **Target Hardware:** ESP32-WROOM-32E + Semtech SX1276 on PCB HW-001 ([pcb-hw001-pinmap.md](pcb-hw001-pinmap.md))
- **Gate Classification:** Gate G1 (RF / Hardware), Gate G3 (Embedded Bring-up)

---

## 1. Executive Summary & Purpose

This document provides the exhaustive, repeatable engineering procedure for conducting physical Hardware-in-the-Loop (HIL) timing measurements on the ESP32-WROOM-32E and Semtech SX1276 transceiver subsystem.

The objective is to gather empirical physical data required to resolve:
1. **`DEC-127-06` (TIM-01):** Validating whether parameterized sub-windows within a 400ms TDMA Static DATA slot can reliably accommodate SF7 and SF8 operations with empirical Gateway WAL write latency ($\tau_{\text{WAL\_GW}}$), transceiver mode turnaround ($\tau_{\text{turnaround}}$), interrupt jitter ($\tau_{\text{jitter}}$), and oscillator drift ($\tau_{\text{drift}}$).
2. **`DEC-MH-07` (TIM-02):** Validating whether the 80-byte Ed25519 `DOWN_SYNC_BEACON` can fit into a candidate 400ms Beacon window at SF8 or whether Beacon transmission must be restricted to SF7.
3. **`DEC-127-05`:** Measuring actual SQLite WAL flush / NVS durable write commit latency on the Gateway hardware.

> [!CAUTION]
> **RF Safety Gate & Legal Transmission Rules:**
> - Under no circumstances may RF power be transmitted on-air without written authorization from the Project Owner.
> - Bench tests MUST be conducted using direct coaxial cabling with a minimum 30 dB RF attenuator terminated into a 50 $\Omega$ dummy load, or inside a calibrated RF shielded enclosure (Faraday box).
> - Do not connect antennas during bench timing verification.
> - Operating channel MUST default to VN920 Channel 0 (920.250 MHz) with transmit power set to the minimum test level (+2 dBm).

---

## 2. Bench Hardware, Instrumentation & Cabling Architecture

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                           TEST BENCH TOPOLOGY                          │
 └────────────────────────────────────────────────────────────────────────┘

    [ Node ESP32 + SX1276 ]                       [ Gateway ESP32 + SX1276 ]
   (PCB HW-001 Node Device)                     (PCB HW-001 Gateway Device)
  ┌─────────────────────────┐                   ┌─────────────────────────┐
  │   ESP32-WROOM-32E       │                   │   ESP32-WROOM-32E       │
  │   SX1276 LoRa Radio     │                   │   SX1276 LoRa Radio     │
  │   RF Port: SMA Female   │                   │   RF Port: SMA Female   │
  └───────────┬─────────────┘                   └───────────┬─────────────┘
              │                                             │
              │ SMA Coax                                    │ SMA Coax
              ▼                                             ▼
       ┌──────────────┐                              ┌──────────────┐
       │ 30dB / 50Ω   │                              │ 30dB / 50Ω   │
       │ Attenuator   │                              │ Attenuator   │
       └──────┬───────┘                              └──────┬───────┘
              │                                             │
              └─────────────── Direct Coaxial ──────────────┘
                              (Conducted RF Link)

  [ Instrumented Logic Analyzer Probes (Saleae Logic Pro 8 @ 100 MS/s) ]
  ├── Probe 0: Node DIO0 (GPIO26)           ── Edge-triggered TxDone/RxDone
  ├── Probe 1: Node SPI SCK (GPIO5)          ── Bus clock activity
  ├── Probe 2: Node SPI CS/NSS (GPIO18)      ── SPI transaction envelope
  ├── Probe 3: Node Debug Marker (GPIO4)     ── Software timestamp latch marker
  ├── Probe 4: Gateway DIO0 (GPIO26)        ── Gateway TxDone/RxDone
  ├── Probe 5: Gateway SPI CS (GPIO18)       ── Gateway SPI transaction envelope
  ├── Probe 6: Gateway WAL Marker (GPIO4)    ── WAL commit start/finish toggle
  └── Probe 7: Shared Ref / Trigger (GPIO16) ── Cross-board sync reference
```

### 2.1 Hardware Bill of Materials
1. **Target Devices (2 units):** Custom PCB revision HW-001 with ESP32-WROOM-32E (16MB Flash) and Semtech SX1276.
2. **RF Cabling & Loads:**
   - 2x 50 $\Omega$ SMA male-to-male coaxial patch cables (RG-316 or RG-142, $\le 1\text{m}$).
   - 2x 30 dB / 2W / 50 $\Omega$ calibrated RF coaxial attenuators (DC–3 GHz).
   - 1x 50 $\Omega$ RF terminator / dummy load.
3. **Logic Analyzer:** Saleae Logic Pro 8 (or equivalent 8-channel analyzer capable of $\ge 100\text{ MS/s}$ with $\pm 2\text{ ppm}$ timebase accuracy).
4. **Oscilloscope:** 4-channel digital storage oscilloscope ($\ge 100\text{ MHz}$ bandwidth, e.g., Rigol DS1054Z or Rohde & Schwarz RTM3004) with $10\times$ passive probes.
5. **Power Supply:** Isolated dual-channel DC linear bench supply set to $3.30\text{ V} \pm 0.05\text{ V}$ with current limit set to $1.0\text{ A}$.
6. **Host Computer:** Linux workstation with dual dedicated USB-to-UART bridge connections for continuous telemetry logging.

---

## 3. PCB HW-001 Signal Map & Probe Attachment

Conforming strictly to [pcb-hw001-pinmap.md](pcb-hw001-pinmap.md):

| Signal Name | ESP32 GPIO | SX1276 Pin | Probe Assignment | Function & Timing Interest |
|---|---:|---|---|---|
| `LoRa_SCK` | **GPIO5** | SCK | Logic Ch 1 | SPI bus clock (10 MHz nominal). **Strapping pin MTDI: must idle LOW.** |
| `LoRa_MISO` | **GPIO19** | MISO | Scope Ch 2 | Data from SX1276 to ESP32. |
| `LoRa_MOSI` | **GPIO27** | MOSI | Scope Ch 3 | Data from ESP32 to SX1276. |
| `LoRa_CS` | **GPIO18** | NSS | Logic Ch 2 | Active-low SPI select envelope. Measures register write duration. |
| `LoRa_RST` | **GPIO23** | NRESET | Logic Ch 5 | Active-low reset pulse. Measures hardware reset recovery delay. |
| `LoRa_DIO0` | **GPIO26** | DIO0 | Logic Ch 0 (Trigger) | Hardware interrupt line: `TxDone`, `RxDone`, or `CadDone`. |
| `DEBUG_MARKER_1` | **GPIO4** | N/A | Logic Ch 3 / 6 | GPIO toggle in firmware at software dispatch, ISR enter, WAL commit. |
| `DEBUG_MARKER_2` | **GPIO16** | N/A | Logic Ch 7 | Cross-board frame boundary synchronization strobe. |

> [!IMPORTANT]
> **DIO1–DIO5 Disconnection Rule:**
> Pins `DIO1` through `DIO5` are **NOT routed** on HW-001. No probe should be attached to unrouted transceiver pads, and firmware must rely on software timer supervision for RX timeouts.

---

## 4. Pre-Test Safety & Authorization Checklist

Before powering on or uploading test firmware, the test operator MUST check each box:

- [ ] **A1. Visual Inspection:** Verify PCB silkscreen reads `HW-001`. Confirm soldering of SX1276 crystal oscillator (32 MHz) and decoupling capacitors.
- [ ] **A2. Strapping Pin Verification:** Verify with an oscilloscope that `GPIO5` is LOW ($< 0.4\text{ V}$) during ESP32 power-on reset. Ensure no external pull-up resistor is present on `GPIO5`.
- [ ] **A3. Power Rail Check:** Measure $V_{\text{DD}}$ at SX1276 pin 3 and 30 with digital multimeter: verify $3.30\text{ V} \pm 0.05\text{ V}$.
- [ ] **A4. RF Attenuator Continuity:** Verify 30 dB attenuator is securely fastened between SX1276 SMA and coaxial cable. Confirm 50 $\Omega$ impedance with DMM.
- [ ] **A5. PA Path Identification:** Inspect PCB routing from SX1276 RF output pins: confirm whether trace connects to `PA_BOOST` (Pin 27) or `RFO_HF` (Pin 28). If trace is `PA_BOOST`, transmit power must never be set above $+14\text{ dBm}$ (target test power: $+2\text{ dBm}$).
- [ ] **A6. Fail-Closed Default Configuration:** Ensure test configuration headers (`node_timing_config.h` and `gateway_timing_config.h`) have `rf_tx_enabled = false` until step-by-step authorization is complete.
- [ ] **A7. Legal RF Jurisdiction:** Verify operating frequency is within 920.250–922.250 MHz (VN920 Channel 0: 920.250 MHz).
- [ ] **A8. Human Authorization:** Project Owner signature obtained on test authorization record.

---

## 5. Step-by-Step Measurement Protocols (M1 through M9)

### 5.1 Protocol M1: TX Command Dispatch to TxDone IRQ
- **Objective:** Measure total delay from software calling `sx1276_tx()` to `DIO0` rising edge (`TxDone`).
- **Configuration:**
  - SF7 and SF8, BW 125 kHz, CR 4/5 ($CR=1$), Preamble 8 symbols, Explicit Header, CRC ON.
  - Payloads: 26B (`UP_EVENT`), 19B (`DOWN_EVENT_ACK`), 80B (`DOWN_SYNC_BEACON`), 21B (`UP_HEALTH_REPLY`).
- **Procedure:**
  1. Instrument Node firmware toggles `GPIO4` HIGH immediately before writing `RegOpMode = FSTX -> TX` via SPI.
  2. Logic analyzer triggers on rising edge of `GPIO4`.
  3. Latch timestamp of `GPIO4` rise ($T_{\text{cmd}}$), SPI CS falling/rising edge ($T_{\text{spi}}$), and `DIO0` rising edge ($T_{\text{irq}}$).
  4. Repeat for $N = 1000$ iterations per condition.
- **Derived Metrics:**
  - $\Delta T_{\text{spi\_dispatch}} = T_{\text{spi}} - T_{\text{cmd}}$
  - $\Delta T_{\text{total\_tx}} = T_{\text{irq}} - T_{\text{cmd}}$
  - $\Delta T_{\text{on\_air}} = T_{\text{irq}} - T_{\text{spi\_end}}$ (Compare against theoretical ToA).

### 5.2 Protocol M2: RxDone IRQ to Application Notification
- **Objective:** Measure latency from SX1276 asserting `DIO0` (`RxDone`) to the application FreeRTOS task unblocking and acquiring the payload buffer.
- **Procedure:**
  1. In `dio0_gpio_isr_handler()`, toggle `GPIO16` HIGH at entry.
  2. In `node_runner_task()`, toggle `GPIO16` LOW upon `xTaskNotifyWait()` unblocking.
  3. Logic analyzer records pulse width on `GPIO16`.
- **Target Bound:** $P99 < 50\ \mu\text{s}$.

### 5.3 Protocol M3: Gateway Durable-Write Acceptance Latency before ACK
- **Objective:** Measure real execution time of Gateway writing received `UP_EVENT` to SQLite WAL / NVS flash before dispatching `DOWN_EVENT_ACK`.
- **Procedure:**
  1. Gateway receives valid `UP_EVENT` via SX1276 driver.
  2. Gateway sets `GPIO4` HIGH immediately before starting SQLite WAL insert transaction (`BEGIN IMMEDIATE; INSERT INTO events ...; COMMIT;`).
  3. Gateway sets `GPIO4` LOW upon transaction completion.
  4. Run across 1000 event insertions under baseline system load (MQTT broker active, logging enabled).
- **Target Bound:** $\tau_{\text{WAL}} \le 15.0\text{ ms}$; reject if $> 35.0\text{ ms}$.

### 5.4 Protocol M4: Transceiver Mode Turnaround ($\text{RX} \leftrightarrow \text{TX}$)
- **Objective:** Measure SX1276 synthesizer settling and PLL lock time between Standby, RX, and TX modes.
- **Procedure:**
  1. Write `RegOpMode = STANDBY -> RXSINGLE` via SPI. Measure time until `RegOpMode` reads back active RX mode.
  2. Write `RegOpMode = RX -> TX`. Measure delay from CS rise to RF output power ramp detected on oscilloscope probe.
- **Target Bound:** $\tau_{\text{turnaround}} \le 20.0\text{ ms}$ (including FreeRTOS scheduling).

### 5.5 Protocol M5: SPI Transaction and Task Scheduling Latency
- **Objective:** Measure SPI transfer latency at 10 MHz vs 1 MHz for 80-byte Beacon read/write.
- **Procedure:**
  1. Logic analyzer measures `GPIO18` (CS) low duration during 80-byte FIFO burst read:
     $$T_{\text{burst\_80B}} = (1\text{ address byte} + 80\text{ data bytes}) \times \frac{8\text{ bits}}{10\text{ MHz}} \approx 64.8\ \mu\text{s}$$
  2. Measure FreeRTOS scheduler context switch jitter under varying CPU loads (0%, 50%, 90%).

### 5.6 Protocol M6: Node Wake-Up, Hardware Reset and Radio Initialization
- **Objective:** Measure latency from ESP32 deep-sleep RTC wake event to SX1276 entering active Standby mode.
- **Procedure:**
  1. Trigger Node wake-up via external button or RTC timer.
  2. Oscilloscope monitors:
     - Channel 1: ESP32 $V_{\text{DD33}}$ / boot strobe.
     - Channel 2: `GPIO23` (`LoRa_RST`) active-low pulse (asserted for $\ge 150\ \mu\text{s}$, followed by $\ge 10\text{ ms}$ hold).
     - Channel 3: `GPIO18` (CS) first configuration transaction.
     - Channel 4: `GPIO26` (DIO0).
- **Derived Metric:** Total boot wake-up latency $T_{\text{wake\_to\_standby}}$.

### 5.7 Protocol M7: Clock Drift and Beacon Synchronization
- **Objective:** Measure cumulative relative clock drift between Node and Gateway oscillators over holdover intervals of 10s, 60s, and 300s.
- **Procedure:**
  1. Both Node and Gateway connect to shared oscilloscope on `GPIO16` (pulse-per-second or pulse-at-slot-0).
  2. Measure time offset $\Delta t_{\text{offset}}$ between Node strobe and Gateway strobe at $t = 10\text{ s}$, $t = 60\text{ s}$, and $t = 300\text{ s}$.
  3. Calculate empirical PPM:
     $$\text{PPM} = \frac{\Delta t_{\text{offset}}(\mu\text{s})}{T_{\text{interval}}(\text{s})}$$
- **Pass Threshold:** Empirical drift $\le 20\text{ PPM}$ ($\le 6.0\text{ ms}$ over 300s holdover; well within the $25\text{ ms}$ holdover guard fence).

### 5.8 Protocol M8: Guard Time Across Slot Boundaries
- **Objective:** Verify empirical timing margins between consecutive Node DATA slots under maximum observed jitter and drift.
- **Procedure:**
  1. Run 2 Node boards transmitting in Slot 1 and Slot 2.
  2. Logic analyzer records RF activity window (DIO0 `TxDone` of Node 1 to `TxStart` of Node 2).
  3. Assert no overlap occurs under 1000 consecutive superframes.

### 5.9 Protocol M9: Full Maintenance SYNC & Health Sequence
- **Objective:** Execute full Maintenance Superframe: Gateway broadcasts 80B Beacon $\to$ Node synchronizes clock $\to$ Node transmits 21B Health Reply $\to$ Gateway receives Health Reply.
- **Procedure:**
  1. Configure Gateway to emit 80B Beacon at $t = 0$.
  2. Verify Node synchronizes within $[0, 400)\text{ms}$.
  3. In Slot 1, verify Node transmits 21B Health Reply within allocated window.
  4. Verify Gateway logs successful reception with valid CCM-8 tag.

---

## 6. Data Logging, Manifest Generation and Integrity Handoff

1. **Host Collector Execution:**
   ```bash
   python3 tests/hil/rf_timing/host/host_collector.py \
       --input /dev/ttyUSB0 \
       --output-manifest docs/verification/evidence/manifest_trial_001.json \
       --disallow-synthetic
   ```
2. **Statistical Analysis:**
   ```bash
   python3 tests/hil/rf_timing/analysis/timing_stats.py \
       --manifest docs/verification/evidence/manifest_trial_001.json
   ```
3. **Artifact Integrity:**
   - Every raw logic analyzer export (`.sal`), oscilloscope capture (`.csv` / `.wfm`), and UART stream (`.jsonl`) MUST have its SHA256 recorded in the manifest.
   - Raw binary captures $\ge 50\text{ MB}$ must be archived in designated project object storage and referenced by immutable URI and SHA256 checksum.

---

## 7. Review and Approval Sign-Off (Human Engineers)

| Role | Name | Organization / Team | Signature / Disposition | Date |
|---|---|---|---|---|
| **Hardware / RF Engineer** | TBD | HW Team | `PENDING_BENCH_TEST` | — |
| **Embedded Firmware Engineer** | TBD | Firmware Team | `PENDING_BENCH_TEST` | — |
| **System / Protocol Architect** | TBD | Systems Team | `PENDING_BENCH_TEST` | — |
| **Project Owner** | TBD | Owner | `AUTHORIZATION_PENDING` | — |
