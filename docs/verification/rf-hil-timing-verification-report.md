# SX1276 Multi-Node TDMA HIL Verification & Calculated Timing Report (LAB-SCOPE V2)

## Document Metadata
- **Document Status:** `BENCH_PREPARATION_COMPLETE / LAB_HIL_NOT_RUN / RF_MEASURED_NOT_VERIFIED / READY_FOR_HUMAN_REVIEW`
- **Source Issue:** [Issue #169 (LAB-SCOPE V2)](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169)
- **Baseline Authority:** Merged PR #202 (Commit `5ce67822e82edc6582879081ea0bd6ea79104b68`)
- **Dependencies:** [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10), [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11), [#19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19), [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127), [#130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130), [#131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131), [#150](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/150), [#201](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/201), [#204](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/204)
- **Target Transceiver:** Semtech SX1276 (Datasheet Rev 7, March 2015 / May 2020)
- **Target Host MCU:** ESP32-WROOM-32E (ESP-IDF v6.1, ADR-0003)
- **Target Board Revision:** PCB HW-001 ([pcb-hw001-pinmap.md](pcb-hw001-pinmap.md))
- **Gate Classification:** Gate G1 (RF / Hardware), Gate G3 (Embedded Bring-up) — *LAB-Scope Verification only*

---

## 1. Executive Summary & LAB-SCOPE V2 Authority

On 2026-11-06, the Project Owner formally updated the scope and acceptance criteria of **Issue #169** to:
$$\mathbf{LAB\text{-}SCOPE\ V2:\ Multi\text{-}Node\ TDMA\ HIL\ +\ Calculated\ Timing}$$

### 1.1 Scope Adjustment Highlights
1. **Pragmatic Lab Verification:**
   Issue #169 is adjusted to match the actual lab equipment available to the project team:
   - Multiple custom PCB HW-001 boards (ESP32-WROOM-32E + SX1276).
   - USB Logic Analyzer (24 MHz / 8-Channel).
   - HABOTEST HT118E digital multimeter.
   - Nutatra 1505TD DC power supply.
   - PC Windows workstation running ESP-IDF v6.1, Python, and USB serial logging.
2. **De-scoping Specialized RF Instrumentation:**
   Purchasing or accessing a Spectrum Analyzer, RF Power Meter, high-bandwidth RF Oscilloscope, Vector Network Analyzer (VNA), or Temperature Chamber is **EXPLICITLY NOT REQUIRED** to complete the LAB acceptance criteria of Issue #169.
   Any parameter dependent on such instruments (conducted RF power, radiated emissions, antenna VSWR, thermal oscillator drift) is formally classified as **`DEFERRED / OUT_OF_SCOPE_FOR_LAB / NOT_VERIFIED`**.
3. **Fail-Closed Evidence Policy:**
   No physical test benches were connected during this execution turn (0 serial ports detected). In strict accordance with `AGENTS.md`:
   - Final status is `BENCH_PREPARATION_COMPLETE / LAB_HIL_NOT_RUN / RF_MEASURED_NOT_VERIFIED / READY_FOR_HUMAN_REVIEW`.
   - **Zero fabricated measurements or synthetic G1/RF PASS statuses are claimed.**
   - All theoretical formulas are tagged `CALCULATED_TOA`, and offline test fixtures are tagged `HOST_SYNTHETIC`.

---

## 2. Scope Change Reconciliation Matrix (`KEEP / CORRECT / REMOVE / DEFER / BLOCKED`)

Review of the 15 files changed in PR #207 against the updated Issue #169 LAB-SCOPE V2:

| # | File Path | Action | Technical Justification under LAB-SCOPE V2 |
|---|---|:---:|---|
| 1 | `docs/verification/rf-hil-bench-setup-and-procedure.md` | **CORRECT** | Replaced mandatory RF equipment with Owner lab inventory (HT118E, Nutatra 1505TD, 24 MHz Logic Analyzer). Fixed GPIO5/MTDI strapping error. Documented 24 MHz sampling limits. |
| 2 | `docs/verification/rf-hil-timing-verification-report.md` | **CORRECT** | Updated status to `BENCH_PREPARATION_COMPLETE / LAB_HIL_NOT_RUN / RF_MEASURED_NOT_VERIFIED`. Documented RX buffer blocker lines, candidate timing labels, and 10-step real HIL plan. |
| 3 | `docs/verification/pcb-hw001-pinmap.md` | **CORRECT** | Corrected strapping pin note: GPIO5 is SDIO slave timing strapping pin (NOT MTDI; MTDI is GPIO12). Disentangled SPI Mode 0 idle state from boot reset strapping. |
| 4 | `tests/hil/rf_timing/evidence_manifest_template.json` | **CORRECT** | Aligned manifest schema with lab equipment BOM; updated evidence classes to include `HARDWARE_DIGITAL_CAPTURE` and `ASSUMED_BOUND`. |
| 5 | `tests/hil/rf_timing/analysis/guard_budget_calculator.py` | **CORRECT** | Maintained parameterized inequality validators; ensured candidate profiles SF8-A (400ms) and SF8-B (450ms) are explicitly labeled `CANDIDATE`. |
| 6 | `tests/hil/rf_timing/analysis/test_timing_analysis.py` | **KEEP** | 16 unit tests verifying guard budget, candidate rebalanced profiles, and fail-closed bounds pass 100%. |
| 7 | `tests/hil/rf_timing/toa/matrix_profile_v2.json` | **KEEP** | Accurate Semtech SX1276 theoretical ToA for 19B, 21B, 26B, 80B at SF7 and SF8 (tagged `CALCULATED`). |
| 8 | `tests/hil/rf_timing/toa/matrix_profile_v2.csv` | **KEEP** | CSV export of V2 theoretical matrix matching JSON. |
| 9 | `tests/hil/rf_timing/toa/generate_matrix.py` | **KEEP** | Python generator creating both V1 (12/24/32/48B) and V2 (19/21/26/80B) profile matrices. |
| 10 | `tests/hil/rf_timing/toa/test_sx1276_toa.py` | **KEEP** | Unit tests for Semtech equations and V2 vectors pass 100%. |
| 11 | `tests/hil/rf_timing/firmware/common/radio_adapter_mock.h` | **KEEP** | `TIMING_MAX_PAYLOAD_LEN 128U` prevents buffer overflow on 80B Beacon reception. |
| 12 | `tests/hil/rf_timing/firmware/gateway_timing_app/main/gateway_timing_config.h` | **KEEP** | Configured V2 Beacon 80B, ACK 19B, Event 26B, Health 21B. |
| 13 | `tests/hil/rf_timing/firmware/node_timing_app/main/main.c` | **KEEP** | 128B dummy payload buffer and V2 ACK reception handling. |
| 14 | `tests/hil/rf_timing/firmware/node_timing_app/main/node_timing_config.h` | **KEEP** | Configured V2 payload suite (19B, 21B, 26B, 80B). |
| 15 | `tests/hil/rf_timing/host/fixtures/synthetic_v2_nominal_run.jsonl` | **KEEP** | Synthetic fixture for host collector stream testing (tagged `HOST_SYNTHETIC`). |
| 16 | `tests/hil/rf_timing/host/generate_fixtures.py` | **KEEP** | Generates synthetic test fixtures offline. |

---

## 3. Hardware & Pinmap Corrections (Remediation B)

### 3.1 Strapping Pin Disambiguation: GPIO5 vs MTDI (GPIO12)
- **The Error in Legacy Documentation:** Legacy documents and earlier drafts incorrectly stated:
  `LoRa_SCK = GPIO5 (Strapping Pin MTDI)`
- **The Datasheet Truth (ESP32-WROOM-32E Datasheet v2.1, Section 4 & Table 3):**
  - **`MTDI` is GPIO12.** `MTDI` controls the internal voltage regulator for SPI flash (`VDD_SDIO`: 0 for 3.3V, 1 for 1.8V). Pulling MTDI wrong can prevent flash access or cause a brownout.
  - **`GPIO5` is a strapping pin for SDIO Slave timing** (bit 1 of strapping vector, sampled at rising edge of `CHIP_PU`). It is **NOT MTDI**.
  - **SPI Mode 0 ($CPOL=0, CPHA=0$):** Defines that when the SPI master peripheral is *actively operating*, SCK idles LOW between bus frames. During chip reset, the SPI master peripheral has not yet initialized; the hardware bootloader evaluates GPIO5 according to its internal weak pull-up.
  - **Remediation:** Both [`docs/verification/pcb-hw001-pinmap.md`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/docs/verification/pcb-hw001-pinmap.md#L39) and [`docs/verification/rf-hil-bench-setup-and-procedure.md`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/docs/verification/rf-hil-bench-setup-and-procedure.md#L62) have been corrected to remove the false `MTDI` reference and clarify that external test instruments must not clamp or pull GPIO5 to an invalid level during reset.

### 3.2 24 MHz USB Logic Analyzer Sampling Limits vs SPI Clock
- **Nyquist-Shannon Constraint:** To accurately capture digital transitions, sampling frequency must be $\ge 4\times$ the clock frequency.
- **Analysis:**
  - In production, SPI operates at $10\text{ MHz}$ (or $8\text{ MHz}$). A 24 MS/s analyzer samples only $2.4\times$ per clock cycle, which causes significant clock pulse distortion and false protocol decode errors.
  - **Operational Rule:**
    1. For SPI byte/register decode debugging, SPI clock should be temporarily configured to $\le 4\text{ MHz}$ (e.g. 2 MHz or 4 MHz). Timing measurements under this reduced clock must be explicitly documented as debug profiles.
    2. In full-speed 10 MHz SPI operation, the 24 MHz analyzer must be used to observe macro digital events: `NSS` chip select envelope (duration tens of $\mu$s), `DIO0` interrupt edge, and GPIO debug strobes.
    3. The Logic Analyzer cannot observe RF waveforms, RF output power, or on-air spectral masks.

---

## 4. Critical Firmware Readiness Blocker: RX Buffer Overflow (Remediation C)

### 4.1 Exact Code Path Identification on `main`
In the shared SX1276 driver on `main`:
1. **Buffer Size Definition:**
   [`firmware/components/sx1276_driver/include/sx1276_types.h:16`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/components/sx1276_driver/include/sx1276_types.h#L16):
   ```c
   #ifndef CONFIG_SX1276_HOST_RX_BUFFER_SIZE
   #define CONFIG_SX1276_HOST_RX_BUFFER_SIZE 64U
   #endif
   ```
2. **Buffer Allocation in Frame Structure:**
   [`firmware/components/sx1276_driver/include/sx1276_types.h:134`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/components/sx1276_driver/include/sx1276_types.h#L134):
   ```c
   typedef struct {
       uint8_t payload[CONFIG_SX1276_HOST_RX_BUFFER_SIZE];
       uint8_t length;
       ...
   } sx1276_rx_frame_t;
   ```
3. **Execution Rejection Path:**
   [`firmware/components/sx1276_driver/src/sx1276_owner.c:96, 123-129`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/firmware/components/sx1276_driver/src/sx1276_owner.c#L96):
   ```c
   sx1276_hal_read_reg(SX1276_REG_RX_NB_BYTES, &nb_bytes); // Line 96
   ...
   if (nb_bytes > CONFIG_SX1276_HOST_RX_BUFFER_SIZE) {    // Line 123
       ESP_LOGE(TAG, "Reject packet: Exceeds host buffer size %u (got %u)",
                CONFIG_SX1276_HOST_RX_BUFFER_SIZE, nb_bytes);
       sx1276_hal_write_reg(SX1276_REG_IRQ_FLAGS, SX1276_IRQ_RX_TARGETED_CLEAR_MASK);
       s_diag.rx_host_buffer_overflow_dropped++;
       return ESP_ERR_INVALID_SIZE;
   }
   ```

### 4.2 Impact on V2 Architecture
Under V2 Normative MAC (`DEC-MH-01`), [`DOWN_SYNC_BEACON`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/contracts/radio-mac/specification.md#L91) (0x43) is **80 bytes** (16B header + 64B Ed25519 signature).
- When an 80B Beacon arrives, `nb_bytes` reads $80$.
- Because $80 > 64$, `sx1276_owner.c` logs `Reject packet: Exceeds host buffer size 64 (got 80)`, increments `rx_host_buffer_overflow_dropped`, and immediately discards the packet without reading the FIFO.
- **Result:** Sensor Nodes are completely unable to receive Beacons, leading to permanent clock desync, loss of holdover, and network failure.

### 4.3 Proposed Remediation & Evaluation
- **Scope Mandate:** PR #207 is strictly restricted to `tests/hil/rf_timing/**` and `docs/verification/**`. **Production driver files must NOT be edited in PR #207.**
- **Recommended Driver Modification:**
  Expand `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` in `Kconfig` and `sx1276_types.h` from $64\text{U}$ to **$128\text{U}$** (or $256\text{U}$ for SX1276 maximum FIFO limit).
- **RAM Impact Assessment:**
  The driver statically allocates a pool of 4 frame descriptors:
  $$\Delta \text{RAM} = 4 \times (128 - 64)\text{ bytes} = 256\text{ bytes}$$
  An increase of 256 bytes in static BSS is completely negligible on the ESP32 (which has 520 KB SRAM).
- **Handoff:** Formally assigned to [Issue #10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) (SX1276 Shared Driver) and [Issue #131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131) (Node TDMA Integration) for implementation.
- **Boundary Test Plan Required:**
  Before production adoption, the following boundary vectors must be verified:
  1. Exact 64B frame (boundary check).
  2. Exact 80B Beacon (normative target).
  3. 128B maximum capacity frame.
  4. Oversize frame (129B) rejection.
  5. Zero-byte frame rejection.

---

## 5. Timing Characterization & Parameterized Profile Validation (Remediation D)

### 5.1 Semtech SX1276 Rev. 7 Theoretical ToA (CALCULATED_TOA)
All values calculated via official Semtech Rev. 7 §4.1.1.7 formulas with VN920 default PHY tuple: BW = 125 kHz, CR = 4/5 ($CR=1$), Preamble = 8 symbols, Explicit Header, CRC ON ($CRC=1$), LDRO OFF ($DE=0$):

| Packet | Codepoint | Bytes | SF7 Payload Syms | SF7 ToA (ms) | SF8 Payload Syms | SF8 ToA (ms) | Provenance |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `UP_EVENT` | `0x41` | **26** | 48 | **61.696** | 43 | **113.152** | `CALCULATED_TOA` |
| `DOWN_EVENT_ACK` | `0x42` | **19** | 38 | **51.456** | 38 | **102.912** | `CALCULATED_TOA` |
| `DOWN_SYNC_BEACON` | `0x43` | **80** | 128 | **143.616** | 113 | **256.512** | `CALCULATED_TOA` |
| `UP_HEALTH_REPLY` | `0x44` | **21** | 43 | **56.576** | 38 | **102.912** | `CALCULATED_TOA` |

### 5.2 Strict Disambiguation of Timing Assumptions
In accordance with LAB-SCOPE V2, all candidate slot and guard durations must be explicitly labeled:

1. **400ms DATA Slot (`CANDIDATE`):** A candidate example demonstrating theoretical arithmetic feasibility; NOT an approved frozen standard constant.
2. **400ms Beacon Window (`CANDIDATE`):** Candidate window to accommodate 80B Beacon at SF8 ($256.512\text{ ms} + \text{guard}$); NOT approved as frozen.
3. **25ms Leading Guard ($W_{\text{lead}}$ — `ASSUMED_BOUND`):** Bound chosen to absorb maximum 300s holdover clock drift ($12.0\text{ ms}$) plus scheduler jitter ($5\text{ ms}$); pending multi-node physical verification.
4. **100ms Trailing Guard ($W_{\text{trail}}$ — `ASSUMED_BOUND`):** Candidate boundary guard for SF8 rebalanced slot ($155\text{ms}$ for SF7).
5. **Gateway Durable Acceptance ($\tau_{\text{accept}}$ — `ASSUMED_BOUND / NOT_VERIFIED`):** Assumed $15\text{ms}$ nominal (max bound $35\text{ms}$). Must be measured against actual ESP32 NVS flash commit / queue serialization.
6. **20ms Mode Turnaround ($\tau_{\text{turnaround}}$ — `ASSUMED_BOUND`):** Conservative engineering bound covering SX1276 synthesizer settling ($60\text{–}120\ \mu\text{s}$) plus FreeRTOS task scheduling.
7. **±20 PPM Clock Drift Scenario (`ASSUMED_SCENARIO`):** Scenario assuming commercial-grade crystals drift $\pm 20\text{ PPM}$. Requires installed oscillator BOM verification.

### 5.3 Candidate Profile Feasibility Matrix

| Profile Identifier | SF | BW | Slot Duration ($T_{\text{slot}}$) | Geometry $[W_{\text{lead}}, W_{\text{EVENT}}, W_{\text{GAP}}, W_{\text{ACK}}, W_{\text{trail}}]$ | Beacon Window | Theoretical Margin | Status & Evaluation |
|---|:---:|:---:|:---:|---|:---:|:---:|---|
| **`PROF_LEGACY_SF7`** | 7 | 125k | 400 ms | $[25, 100, 20, 100, 155]\text{ ms}$ | 250 ms | $+38.3\text{ms}$ (Event), $+48.5\text{ms}$ (ACK) | **FEASIBLE (THEORETICAL)** · Proven in #201 |
| **`PROF_LEGACY_SF8`** | 8 | 125k | 400 ms | $[25, 100, 20, 100, 155]\text{ ms}$ | 250 ms | $-13.2\text{ms}$ (Event), $-2.9\text{ms}$ (ACK) | **REJECTED (INFEASIBLE)** · Violates sub-windows |
| **`PROF_CANDIDATE_SF8_A`** | 8 | 125k | 400 ms | $[25, 125, 35, 115, 100]\text{ ms}$ | 400 ms | $+11.8\text{ms}$ (Event), $+12.1\text{ms}$ (ACK) | **CANDIDATE** · Tight margin; requires WAL $\le 15\text{ms}$ |
| **`PROF_CANDIDATE_SF8_B`** | 8 | 125k | 450 ms | $[30, 130, 45, 120, 125]\text{ ms}$ | 400 ms | $+16.8\text{ms}$ (Event), $+17.1\text{ms}$ (ACK) | **CANDIDATE** · Sums to 450ms; conservative slack |
| **`PROF_FALLBACK_HYBRID`** | 8/7 | 125k | 400 ms | DATA at SF8 (rebalanced), Beacon at SF7 | 250 ms | $+11.8\text{ms}$ (DATA), $+106.4\text{ms}$ (Beacon) | **CANDIDATE** · Dual-SF strategy |

> [!CAUTION]
> **Why Theoretical Margin $\ne$ Production PASS:**
> While Candidate SF8-A leaves $11.8\text{ms}$ of margin for `UP_EVENT` and $12.1\text{ms}$ for `DOWN_EVENT_ACK`, on real hardware this margin can be consumed by FreeRTOS task starvation or flash write tail latencies. A positive theoretical margin proves arithmetic possibility, but **CANNOT replace multi-node physical verification**.

---

## 6. Test Suite Execution & Host Verification Results

All tests have been executed locally within the isolated worktree `/tmp/lora-issue-169`:

1. **Python Unit & Contract Timing Tests:**
   - [`tests/contract/test_radio_mac_timing_consistency.py`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/tests/contract/test_radio_mac_timing_consistency.py): **12 passed** in 0.03s.
   - [`tests/hil/rf_timing/analysis/test_timing_analysis.py`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/tests/hil/rf_timing/analysis/test_timing_analysis.py): **16 passed** in 0.12s.
   - [`tests/hil/rf_timing/toa/test_sx1276_toa.py`](file:///home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/tests/hil/rf_timing/toa/test_sx1276_toa.py): **9 passed** in 0.06s.
   - **Total:** **37 passed in 0.11s**.
2. **C Firmware Toolchain Host Compilation & Execution:**
   - Compiled with strict warning flags: `gcc -Wall -Wextra -Werror -std=c11`.
   - Ring buffer unit tests: **PASS**.
   - Node timing application host compile: **PASS**.
   - Gateway timing application host compile: **PASS**.
3. **Stream Collector & Schema Validation:**
   - `HostCollector` processed `synthetic_v2_nominal_run.jsonl`: **251 valid records, 0 invalid, 0 dropped**.
4. **Harness PR Review (`pr_review.py`):**
   - **Verdict:** `🟢 READY FOR HUMAN REVIEW`
   - Scope compliance: **15 files changed, all within allowed paths**.
   - Secret scan: **Clean**.

---

## 7. Remaining Blockers & downstream Handoffs

### 7.1 Outstanding Blockers before Physical Multi-Node Execution
1. **Physical Board Access & Inventory Check:** Awaiting physical connection of PCB HW-001 boards to verify operational count (1 GW + 1/4/9/10–15 Nodes).
2. **Production Driver RX Buffer Capacity Blocker:** `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` must be updated from 64U to $\ge 128\text{U}$ under Issue #10.
3. **Module PA Path Identification:** Visual/schematic verification required to confirm `PA_BOOST` vs `RFO_HF` on physical boards.
4. **Human RF Safety Authorization:** Written sign-off required prior to enabling `rf_tx_enabled = true`.

### 7.2 Downstream Issue Handoffs
- **[Issue #10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) (Shared SX1276 Driver):** Remediate the 64U buffer blocker to allow 80B Beacon reception.
- **[Issue #127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127) (Radio MAC V2 Specification / Gate G2):** Maintain parameterized geometry equations instead of frozen numeric tables.
- **[Issue #19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19) (Go Backend TDMA Scheduler):** Implement versioned schedule models with dynamic sub-window parameters.
- **[Issue #130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130) (Gateway TDMA Implementation):** Implement symbolic schedule validation fail-closed checks on Gateway.
- **[Issue #131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131) (Node TDMA & Deep-Sleep):** Implement Fence 4 dynamic timing window checks using active schedule parameters.

---

## 8. Final Review Readiness & Conclusion

- **PR #207 Status:** Updated, pushed, and ready for human review.
- **Scope Compliance:** Strictly adheres to LAB-SCOPE V2. No production code, wire contracts, or ADRs were modified.
- **Final Disposition:**
  $$\mathbf{BENCH\_PREPARATION\_COMPLETE\ /\ LAB\_HIL\_NOT\_RUN\ /\ RF\_MEASURED\_NOT\_VERIFIED\ /\ READY\_FOR\_HUMAN\_REVIEW}$$
