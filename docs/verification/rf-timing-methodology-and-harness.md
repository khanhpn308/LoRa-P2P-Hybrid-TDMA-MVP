# SX1276 RF Timing Methodology, Test Harness, and Guard Time Model

## Document Metadata
- **Status:** APPROVED SOFTWARE METHODOLOGY / CONDITIONAL THEORETICAL MODEL
- **Issue Reference:** [Issue #11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11)
- **Handoff Target:** [Issue #169](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169) (Physical RF Measurements & Guard Time Sign-Off)
- **Architectural Authority:** [ADR-0001 (Hybrid TDMA)](../adr/0001-hybrid-tdma.md), [ADR-0003 (ESP-IDF v6.1)](../adr/0003-esp-idf-v6-1.md), [ADR-0004 (Timing Budget)](../adr/0004-theoretical-timing-guard-budget.md)
- **Transceiver Authority:** Semtech SX1276/77/78/79 Datasheet Rev 7 (March 2015)
- **Hardware Reference:** PCB HW-001 ([pcb-hw001-pinmap.md](pcb-hw001-pinmap.md))

---

## 1. Executive Summary & Responsibility Division
Issue #11 delivers the **software and theoretical toolchain** required to calculate, instrument, collect, and statistically analyze RF timing for the MVP V1 LoRa P2P Hybrid TDMA network.

```text
┌─────────────────────────────────────────────────────────────┐
│                       ISSUE #11 (Agent)                     │
│  - Theoretical Semtech SX1276 ToA Calculator                │
│  - Verified Profile Matrix (12/24/32/48 B, SF7/8, BW125k)   │
│  - Test-only ESP-IDF Node & Gateway Timing Harness Source   │
│  - Host Serial Collector, JSON Schema & Run Manifest        │
│  - Deterministic Synthetic Regression Fixtures              │
│  - Statistical Analyzer (P50/P90/P95/P99) & Provenance Check│
│  - Parameterized Guard Time & Slot Feasibility Calculator   │
└──────────────────────────────┬──────────────────────────────┘
                               │ Clean Handoff
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    ISSUE #169 (Hardware Owner)              │
│  - Bench Flashing & Integration with #10 SX1276 Driver       │
│  - Physical RF Transmission (Conducted / Radiated)          │
│  - Calibrated Oscilloscope & Logic Analyzer Capture         │
│  - Temperature / Holdover Crystal Drift Measurements        │
│  - Hardware Sample Count >= 1000 & Empirical Jitter         │
│  - Production Guard Time & Slot Duration Sign-Off           │
└─────────────────────────────────────────────────────────────┘
```

Closing Issue #11 **does not** authorize on-air transmission, certify Gate G1/G2 RF PASS, or approve production numerical timing constants. All numerical schedules generated herein are labeled `CALCULATED / SCENARIO`.

---

## 2. Theoretical PHY Time-on-Air (ToA) Formulation

### 2.1 Semtech SX1276 Silicon Airtime Equations
The Time-on-Air ($T_{packet}$) is the sum of the preamble duration ($T_{preamble}$) and the payload duration ($T_{payload}$):

$$T_{packet} = T_{preamble} + T_{payload}$$

#### Symbol Duration ($T_s$)
The symbol duration depends strictly on the Spreading Factor ($SF \in [6, 12]$) and Bandwidth ($BW\text{ Hz}$):

$$T_s = \frac{2^{SF}}{BW}$$

For MVP V1 ($BW = 125,000\text{ Hz}$):
- **SF7:** $T_s = \frac{128}{125000} = 0.001024\text{ s} = 1024.0\text{ µs} = 1.024\text{ ms}$
- **SF8:** $T_s = \frac{256}{125000} = 0.002048\text{ s} = 2048.0\text{ µs} = 2.048\text{ ms}$

#### Preamble Duration ($T_{preamble}$)
With programmed preamble symbol length $N_{preamble}$ (default 8 symbols) plus 4.25 synchronization symbols:

$$T_{preamble} = (N_{preamble} + 4.25) \times T_s = 12.25 \times T_s$$

- **SF7 ($125\text{ kHz}$):** $T_{preamble} = 12.25 \times 1024.0\text{ µs} = 12,544.0\text{ µs} = 12.544\text{ ms}$
- **SF8 ($125\text{ kHz}$):** $T_{preamble} = 12.25 \times 2048.0\text{ µs} = 25,088.0\text{ µs} = 25.088\text{ ms}$

#### Payload Symbol Count ($N_{payload}$)
For $SF \in [7, 12]$:

$$N_{payload} = 8 + \max\left( \left\lceil \frac{8 \cdot PL - 4 \cdot SF + 28 + 16 \cdot CRC - 20 \cdot H}{4 \cdot (SF - 2 \cdot DE)} \right\rceil \cdot (CR + 4),\, 0 \right)$$

Where:
- $PL$: Payload length in bytes ($0 \le PL \le 255$, SX1276 FIFO limit).
- $CRC$: $1$ if payload CRC is enabled, $0$ if disabled.
- $H$: $0$ for explicit header mode, $1$ for implicit header mode.
- $DE$: Low Data Rate Optimization ($DE=1$ if $T_s > 16\text{ ms}$, else $0$). For $BW=125\text{ kHz}$, $DE=0$ for $SF \le 10$, and $DE=1$ for $SF \in [11, 12]$.
- $CR$: Coding rate ($CR=1$ for $4/5$, $CR=2$ for $4/6$, $CR=3$ for $4/7$, $CR=4$ for $4/8$).

$$T_{payload} = N_{payload} \times T_s$$

---

### 2.2 Calculated Profile Matrix (MVP V1 & Test Profiles)
Generated deterministically via `tests/hil/rf_timing/toa/generate_matrix.py`:
- **Parameters:** $BW = 125\text{ kHz}$, $CR = 1$ ($4/5$), $N_{preamble} = 8$, Header = Explicit ($H=0$), CRC = ON ($CRC=1$), LDRO = OFF ($DE=0$), Sync Word = `0x12`.

| Profile Name | SF | BW (kHz) | Payload (Bytes) | Preamble (ms) | Payload Syms | Payload (ms) | Total ToA (ms) | Total ToA (µs) | Provenance |
|---|---|---|---|---|---|---|---|---|---|
| `PROF_SF7_PL12` | 7 | 125 | 12 | 12.544 | 28 | 28.672 | **41.216** | 41,216 | CALCULATED |
| `PROF_SF7_PL24` | 7 | 125 | 24 | 12.544 | 48 | 49.152 | **61.696** | 61,696 | CALCULATED |
| `PROF_SF7_PL32` | 7 | 125 | 32 | 12.544 | 58 | 59.392 | **71.936** | 71,936 | CALCULATED |
| `PROF_SF7_PL48` | 7 | 125 | 48 | 12.544 | 83 | 84.992 | **97.536** | 97,536 | CALCULATED |
| `PROF_SF8_PL12` | 8 | 125 | 12 | 25.088 | 28 | 57.344 | **82.432** | 82,432 | CALCULATED |
| `PROF_SF8_PL24` | 8 | 125 | 24 | 25.088 | 43 | 88.064 | **113.152** | 113,152 | CALCULATED |
| `PROF_SF8_PL32` | 8 | 125 | 32 | 25.088 | 53 | 108.544 | **133.632** | 133,632 | CALCULATED |
| `PROF_SF8_PL48` | 8 | 125 | 48 | 25.088 | 73 | 149.504 | **174.592** | 174,592 | CALCULATED |

Export artifacts:
- JSON: [`tests/hil/rf_timing/toa/matrix_profile_v1.json`](../../tests/hil/rf_timing/toa/matrix_profile_v1.json)
- CSV: [`tests/hil/rf_timing/toa/matrix_profile_v1.csv`](../../tests/hil/rf_timing/toa/matrix_profile_v1.csv)

---

## 3. Firmware Instrumentation Architecture & Pin Mapping

### 3.1 Hardware Pin Mapping (PCB HW-001)
The test firmware strictly conforms to the verified PCB pinout:
- **SPI SCK:** `GPIO5`
- **SPI MISO:** `GPIO19`
- **SPI MOSI:** `GPIO27`
- **SX1276 NSS / CS:** `GPIO18`
- **SX1276 Reset:** `GPIO23`
- **DIO0 IRQ:** `GPIO26` (Rising edge, mapped to `dio0_gpio_isr_handler`)
- **DIO1–DIO5:** `NOT CONNECTED`. Any software dependency on DIO1–DIO5 is strictly prohibited.

### 3.2 Non-Blocking ISR Latency Rules
In accordance with C Coding Standard v2:
1. `dio0_gpio_isr_handler` executes in IRAM (`IRAM_ATTR`).
2. Latching timestamp: Calls `esp_timer_get_time()` directly into an ISR-safe lock-free ring buffer.
3. No heap allocations (`malloc`/`free`), no floating-point math, no UART/`printf`, and no SPI bus transactions inside the ISR.
4. Task unblocking via `vTaskNotifyGiveFromISR()` and `portYIELD_FROM_ISR()`.

### 3.3 Fail-Closed RF Safety Gate
Because commercial module PA internal wiring (`RFO_HF` vs `PA_BOOST`) is unverified on physical hardware, `rf_tx_enabled` defaults to `false`.
- If a transmission is commanded while disabled, the radio adapter immediately rejects the call fail-closed (`status = 100` / `BLOCKED`).
- Flashing, key programming, or radiated RF emissions are disabled in Issue #11.

---

## 4. Host Collector & Log Schema

### 4.1 Log Record JSON Schema
Records emitted over UART follow the schema in `tests/hil/rf_timing/host/log_schema.json`:

```json
{
  "ver": "1.0.0",
  "seq": 4,
  "role": "NODE",
  "dev_id": "NODE_HIL_01",
  "evt": "TX_DONE",
  "ts_us": 137756695407,
  "class": "SOFTWARE_TIMESTAMP",
  "pl_len": 24,
  "ch": 0,
  "status": 0,
  "extra": 0
}
```

### 4.2 Sequence Continuity & Drop Detection
`HostCollector` verifies sequence continuity ($seq_i = seq_{i-1} + 1$).
- Sequence jumps increment `dropped_samples`.
- Buffer full conditions trigger an explicit `OVERFLOW` event record.
- Monotonic timestamp sanity checks reject backward jumps.

### 4.3 Run Manifest Specification
Every test run generates a SHA-256 digested manifest:
- Firmware git commit SHA
- UTC ISO 8601 timestamp
- Board hardware revision (`PCB-HW-001`)
- RF TX state (`rf_tx_enabled: false`)
- Sample count, invalid count, and dropped count
- Present evidence classes

---

## 5. Statistical Analysis & Conservative Guard Time Budget

### 5.1 Evidence Classification Policy
Data integrity mandates orthogonal classification:
- `CALCULATED_TOA`: Theoretical Semtech formula output.
- `HOST_SYNTHETIC`: Host-generated fixtures for CI/regression.
- `SOFTWARE_TIMESTAMP`: Microsecond monotonic latches on ESP32.
- `HARDWARE_CAPTURE`: External logic analyzer GPIO measurements.
- `EXTERNAL_RF_MEASURED`: Calibrated oscilloscope RF envelopes.

Attempts to represent `HOST_SYNTHETIC` or `SOFTWARE_TIMESTAMP` as `EXTERNAL_RF_MEASURED` are rejected fail-closed with `ProvenanceError`.

### 5.2 Guard Time Budget Formulation
The Guard Time ($T_{guard}$) ensures non-overlapping TDMA slots under worst-case clock drift, scheduling jitter, and transceiver turnaround:

$$T_{guard} = \left( T_{drift} + T_{sync\_uncertainty} + T_{task\_jitter} + T_{rx\_turnaround} + T_{prop} \right) \times M_{safety}$$

#### Component Breakdown:
1. **Clock Drift ($T_{drift}$):**
   $$T_{drift} = 2 \times \text{PPM}_{max} \times T_{sync\_window}$$
   With $\pm 20\text{ PPM}$ quartz crystals:
   - For $T_{sync} = 10\text{ s}$: $T_{drift} = 400.0\text{ µs} = 0.400\text{ ms}$.
   - For $T_{sync} = 300\text{ s}$: $T_{drift} = 12,000.0\text{ µs} = 12.000\text{ ms}$.
2. **Sync Timestamp Uncertainty ($T_{sync\_uncertainty}$):** $25.0\text{ µs}$.
3. **FreeRTOS Task Dispatch Jitter ($T_{task\_jitter}$):** $100.0\text{ µs}$.
4. **Transceiver Settling Turnaround ($T_{rx\_turnaround}$):** $60.0\text{ µs}$.
5. **Propagation Delay ($T_{prop}$):** $16.7\text{ µs}$ ($5\text{ km}$ link).
6. **Base Guard:** $400 + 25 + 100 + 60 + 16.7 = 601.7\text{ µs}$.
7. **Safety Margin ($M_{safety} = 1.25$):** $T_{guard} = 601.7 \times 1.25 = \mathbf{752.1\text{ µs}} \approx \mathbf{0.752\text{ ms}}$ (for $10\text{ s}$ holdover).

### 5.3 Feasibility Modeling for 10–15 Nodes
Superframe cycle ($T_{superframe} = 10.0\text{ s}$), SF7, BW 125 kHz, 24 B uplink, 8 B ACK:
- $\text{ToA}_{uplink} = 61.696\text{ ms}$
- $\text{ToA}_{ack} = 36.096\text{ ms}$
- $T_{guard} = 0.752\text{ ms}$
- **Slot Duration ($T_{slot}$):** $61.696 + 36.096 + 0.752 = \mathbf{98.544\text{ ms}}$

| Metric | 10 Nodes Scenario | 15 Nodes Scenario | Feasibility Constraint | Status |
|---|---|---|---|---|
| Beacon Slot Duration | 49.336 ms | 49.336 ms | Fits in superframe | OK |
| Total DATA Phase Duration | 985.440 ms | 1478.160 ms | $< 2.0\text{ s}$ | OK |
| Total Superframe Active Time | 1034.776 ms | 1527.496 ms | $\le 10,000\text{ ms}$ | **FEASIBLE** |
| Superframe Slack Margin | 8965.224 ms | 8472.504 ms | $> 8.0\text{ s}$ unallocated | **FEASIBLE** |
| Node Transmit Duty Cycle | 0.617% | 0.617% | $\le 1.000\%$ legal limit | **COMPLIANT** |

All schedule outputs are labeled `CALCULATED / SCENARIO`.

---

## 6. Risk Register

| Risk ID | Description | Severity | Software Mitigation (#11) | Hardware Resolution (#169) |
|---|---|---|---|---|---|
| **RSK-RF-01** | Unverified module PA path causes silicon latchup or damage upon TX | CRITICAL | RF TX disabled fail-closed (`status = 100`) | Conducted RF power meter & schematic verification |
| **RSK-RF-02** | Crystal thermal drift exceeds 20 PPM in field conditions | HIGH | Parameterized $T_{drift}$ equation with explicit PPM input | Bench temperature chamber measurement |
| **RSK-RF-03** | Ring buffer overflow drops critical timing events during burst | MEDIUM | Bounded static buffer with explicit drop counter & `OVERFLOW` event | Optimize UART logger baud rate / DMA transfer |
| **RSK-RF-04** | Floating-point math in ISR causes FreeRTOS context corruption | HIGH | Strictly forbidden in C code; only integer microsecond timestamps in ISR | Audited by C Standard v2 compliance gates |
| **RSK-RF-05** | False claim of RF compliance without bench data | HIGH | Schema rejects `EXTERNAL_RF_MEASURED` without cryptographic certificate | Sign-off reserved for human RF owner |

---

## 7. Clean Handoff Specification to Issue #169

### 7.1 What #169 Must Measure on Bench Hardware
The hardware owner executing Issue #169 must collect physical measurements to replace the theoretical quantities:
1. **Conducted PA Output Power:** Verify RF power at ANT pad matching +2 dBm target code.
2. **Physical Time-on-Air:** Using calibrated oscilloscope and RF sniffer, capture actual RF envelope duration from preamble start to last payload symbol.
3. **Transceiver Turnaround Latency:** Measure physical RF falling edge of TX to LNA activation in RX single mode.
4. **Crystal Drift Profile:** Measure oscillator drift across operating temperature range (-10°C to +60°C) over 10 s, 60 s, and 300 s holdover windows.
5. **Sample Count:** Acquire $\ge 1000$ empirical samples per profile combination.

### 7.2 Safety Stop Conditions for Hardware Operator
The operator must abort test runs immediately if:
- Module current consumption exceeds 100 mA (OCP trigger).
- Reflected power / VSWR indicates absent or mismatched antenna.
- Frequency counter indicates deviation $> 50\text{ kHz}$ from VN920 channel plan.

### 7.3 Handoff Artifact Checklist
- [x] Tested ToA calculator: `tests/hil/rf_timing/toa/sx1276_toa.py`
- [x] Versioned profile matrix: `tests/hil/rf_timing/toa/matrix_profile_v1.json`
- [x] Node instrumentation app: `tests/hil/rf_timing/firmware/node_timing_app/`
- [x] Gateway instrumentation app: `tests/hil/rf_timing/firmware/gateway_timing_app/`
- [x] Host collector tool: `tests/hil/rf_timing/host/host_collector.py`
- [x] Log schema & manifest validator: `tests/hil/rf_timing/host/log_schema.json`
- [x] Statistical analyzer & Guard model: `tests/hil/rf_timing/analysis/`
- [x] Unified test suite: `tests/hil/rf_timing/test_rf_timing_toolchain.py`
