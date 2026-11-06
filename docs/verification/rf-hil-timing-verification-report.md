# SX1276 Physical RF/HIL TDMA Timing Verification Report & Preparation Package

## Document Metadata
- **Document Status:** `BENCH_PREPARATION_COMPLETE / RF_HIL_NOT_VERIFIED`
- **Source Issue:** [Issue #169](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169)
- **Baseline Authority:** Merged PR #202 (Commit `5ce67822e82edc6582879081ea0bd6ea79104b68`)
- **Dependencies:** [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11), [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10), [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127), [#19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19), [#130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130), [#131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131)
- **Target Transceiver:** Semtech SX1276 (Datasheet Rev 7, March 2015)
- **Target Host MCU:** ESP32-WROOM-32E (ESP-IDF v6.1, ADR-0003)
- **Target Board Revision:** PCB HW-001 ([pcb-hw001-pinmap.md](pcb-hw001-pinmap.md))
- **Gate Classification:** Gate G1 (RF / Hardware), Gate G3 (Embedded Bring-up)

---

## 1. Executive Summary & Status Disposition

This document constitutes the authoritative preparation and verification report for **Issue #169: Physical SX1276 TDMA Timing Verification**.

Following the strict native execution rules of `AGENTS.md` and the fail-closed mandate:
- **No physical test benches or connected ESP32 hardware were accessible in this automated execution environment** (0 serial devices detected on `/dev/ttyUSB*` / `/dev/ttyACM*`, no calibrated RF instruments attached, no on-air transmission permitted).
- In accordance with the Issue #169 Definition of Done:
  $$\text{Final Disposition: } \mathbf{BENCH\_PREPARATION\_COMPLETE\ /\ RF\_HIL\_NOT\_VERIFIED}$$
- **Zero fabricated measurements or synthetic G1/RF PASS statuses are claimed.** All theoretical calculations are strictly tagged `CALCULATED`, and synthetic test fixtures are tagged `HOST_SYNTHETIC`.

This preparation package delivers:
1. Complete read-only preflight analysis of live `main` interfaces, contracts, and firmware readiness blockers.
2. Comprehensive, repeatable test plan covering exact V2 packet lengths (26B, 19B, 80B, 21B) at SF7 and SF8 across 9 distinct measurement scenarios (M1 through M9).
3. Statistical validation framework and parameterized inequality checker conforming to PR #202 (`DEC-127-06` and `DEC-MH-07`).
4. Operational bench procedure, evidence manifest schema, guard time recommendation, and human review handoff checklist.

---

## 2. Phase 1 — Read-Only Preflight Review & Readiness Findings

### 2.1 Live Main & Contract Baseline Review
- **Baseline Git SHA:** `5ce67822e82edc6582879081ea0bd6ea79104b68` (Merged PR #202 / Issue #201).
- **Contract Status:**
  - `contracts/radio-mac/specification.md` is **Revision 0.2.0-draft / Gate G2: NOT_VERIFIED**.
  - `contracts/radio-mac/tdma-schedule.md` is **Revision 0.2.0-draft / Gate G2: NOT_VERIFIED**.
  - `contracts/OPEN_DECISIONS.md` records `DEC-127-06` and `DEC-MH-07` as `OWNER_APPROVED_DIRECTION / NOT_HIL_VERIFIED`.

### 2.2 Transceiver Driver & Firmware Interface Review
- **Shared SX1276 Driver ([Issue #10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10)):**
  - Driver adheres to single Radio Owner pattern with FreeRTOS mutex serialization.
  - Pin assignments in `firmware/components/sx1276_driver/` match PCB HW-001: SCK=GPIO5, MISO=GPIO19, MOSI=GPIO27, CS=GPIO18, RST=GPIO23, DIO0=GPIO26.
  - Fail-closed RF safety gate implemented: `rf_tx_enabled` defaults to `false`; `pa_path` defaults to `SX1276_PA_PATH_UNKNOWN`. Transmissions return `-100 (BLOCKED)` if unauthorized.
  - Unrouted `DIO1` (RxTimeout) is handled via host software supervision timers.

> [!WARNING]
> **CRITICAL FIRMWARE READINESS FINDING (Blocker for 80B Beacon Reception):**
> In `firmware/components/sx1276_driver/include/sx1276_types.h` (Line 16), the driver buffer size is configured as:
> ```c
> #ifndef CONFIG_SX1276_HOST_RX_BUFFER_SIZE
> #define CONFIG_SX1276_HOST_RX_BUFFER_SIZE 64U
> #endif
> ```
> And `sx1276_rx_frame_t` allocates `payload[CONFIG_SX1276_HOST_RX_BUFFER_SIZE]`.
> However, under V2 Normative MAC (`DEC-MH-01`), the `DOWN_SYNC_BEACON` (0x43) is **80 bytes** (16B header + 64B Ed25519 signature).
> **Consequence:** If the SX1276 receives an 80-byte Beacon on physical hardware with default configuration, the driver will trigger `SX1276_RX_STATUS_REJECT_BUFFER_OVERFLOW` (Line 77) and increment `rx_host_buffer_overflow_dropped` (Line 149), dropping every Beacon!
> **Remediation Required:** `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` MUST be increased to $\ge 128\text{U}$ in production `Kconfig` before HIL Beacon tests can succeed on physical hardware. (In this test harness package, `TIMING_MAX_PAYLOAD_LEN` has been set to 128U).

### 2.3 Hardware Inventory & Physical Test Setup Readiness
| Item | Requirement | Actual Environment State | Disposition |
|---|---|---|---|
| Target MCU Boards | 2x ESP32-WROOM-32E (PCB HW-001) | 0 boards detected on `/dev/ttyUSB*` / `/dev/ttyACM*` | **MISSING / BLOCKED** |
| SX1276 Modules | 2x Semtech SX1276 connected via SPI | Not connected | **MISSING / BLOCKED** |
| Oscilloscope | $\ge 100\text{ MHz}$ 4-channel DSO | Not connected | **MISSING / BLOCKED** |
| Logic Analyzer | $\ge 100\text{ MS/s}$ 8-channel analyzer | Not connected | **MISSING / BLOCKED** |
| RF Attenuators | 2x 30 dB / 50 $\Omega$ coaxial attenuators | Not available | **MISSING / BLOCKED** |
| RF Authorization | Human Owner written approval | No transmission permitted | **FAIL_CLOSED / OFF** |

---

## 3. Phase 2 — Comprehensive HIL Test Plan

### 3.1 Exact V2 Packet Lengths Evaluated
Under documented VN920 default PHY settings (BW = 125 kHz, CR = 4/5, Preamble = 8 symbols, Explicit Header, CRC ON):

| Packet Identifier | Type Codepoint | Payload Size | SF7 Preamble / Payload / Total ToA | SF8 Preamble / Payload / Total ToA | Regulatory / Contract Classification |
|---|:---:|:---:|:---:|:---:|---|
| `UP_EVENT` | `0x41` | **26 Bytes** | 12.544ms / 49.152ms / **61.696 ms** | 25.088ms / 88.064ms / **113.152 ms** | `DEC-127-01` (AES-128-CCM 8B Tag) |
| `DOWN_EVENT_ACK` | `0x42` | **19 Bytes** | 12.544ms / 38.912ms / **51.456 ms** | 25.088ms / 77.824ms / **102.912 ms** | `DEC-127-01` (Instant slotted ACK) |
| `DOWN_SYNC_BEACON` | `0x43` | **80 Bytes** | 12.544ms / 131.072ms / **143.616 ms** | 25.088ms / 231.424ms / **256.512 ms** | `DEC-MH-01` (Ed25519 64B Signature) |
| `UP_HEALTH_REPLY` | `0x44` | **21 Bytes** | 12.544ms / 44.032ms / **56.576 ms** | 25.088ms / 77.824ms / **102.912 ms** | `DEC-MH-02` (Periodic health telemetry) |

### 3.2 Required Physical Measurement Scenarios (M1 to M9)

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      MEASUREMENT PROTOCOLS OVERVIEW                    │
 └────────────────────────────────────────────────────────────────────────┘

  M1: TX Command -> TxDone IRQ
      [ Host sx1276_tx() ] ──SPI──> [ SX1276 On-Air ] ──> [ DIO0 posedge ]
      Metrics: SPI command dispatch latency, on-air duration, IRQ delay.

  M2: RxDone IRQ -> Application Task Notification
      [ DIO0 posedge ] ──ISR──> [ xTaskNotifyFromISR ] ──> [ Task Run ]
      Metrics: FreeRTOS context switch, interrupt latency (target P99 < 50us).

  M3: Gateway Durable-Write Acceptance Latency (DEC-127-05)
      [ RxDone UP_EVENT ] ──> [ SQLite WAL / NVS Commit ] ──> [ Tx ACK ]
      Metrics: Flash commit duration (budget bound 15ms nominal, max 35ms).

  M4: Transceiver Mode Turnaround (RX <-> TX)
      [ RegOpMode = Standby/RX ] ──SPI──> [ PLL Lock & Synthesizer ] ──> [ TX Ramp ]
      Metrics: Hardware settling time (Semtech datasheet typical 60-120us).

  M5: SPI & Task Scheduling Latency
      [ CS Assert ] ──10MHz SPI──> [ 80B Payload FIFO Read ] ──> [ CS Deassert ]
      Metrics: Bus transaction time (64.8us @ 10MHz vs 648us @ 1MHz).

  M6: Node Deep-Sleep Wake-Up & Radio Initialization
      [ RTC Wake Event ] ──> [ ESP-IDF Boot ] ──> [ RST 150us ] ──> [ Standby ]
      Metrics: Cold start recovery time (~15-18ms).

  M7: Clock Drift & Beacon Holdover Tracking
      [ Gateway Time Reference ] <──Holdover 10s / 60s / 300s──> [ Node Drift ]
      Metrics: Empirical PPM offset (max allowed 20 PPM; 6.0ms @ 300s).

  M8: Guard Time Across Slot Boundaries
      [ Node 1 Slot Active ] ──Guard Lead/Trail──> [ Node 2 Slot Active ]
      Metrics: Non-overlapping boundary margin under worst-case jitter.

  M9: Maintenance SYNC & Health Sequence Execution
      [ 80B Beacon TX ] ──Sync Latch──> [ 21B Health Reply ] ──> [ Gateway Log ]
      Metrics: Full maintenance cycle time and holdover reset verification.
```

---

## 4. Phase 3 — Statistical Validation & Parameterized Inequality Checks

### 4.1 Parameterized Inequality System (PR #202 / DEC-127-06)
Under PR #202 and `contracts/radio-mac/tdma-schedule.md`, the Static DATA Slot timing budget is governed by the following mathematical system:

$$\begin{cases}
W_{\text{UP\_EVENT}} \ge \text{ToA}_{\text{UP\_EVENT}}(\text{SF}) + \tau_{\text{jitter\_Node}} \\
W_{\text{GAP}} \ge \tau_{\text{turnaround\_GW}} + \tau_{\text{WAL\_GW}} \\
W_{\text{DOWN\_ACK}} \ge \text{ToA}_{\text{DOWN\_ACK}}(\text{SF}) + \tau_{\text{jitter\_GW}} \\
W_{\text{lead}} + W_{\text{UP\_EVENT}} + W_{\text{GAP}} + W_{\text{DOWN\_ACK}} + W_{\text{trail}} \le T_{\text{slot}} \\
T_{\text{slot}} \ge W_{\text{lead}} + \text{ToA}_{\text{EVENT}} + \tau_{\text{turnaround\_GW}} + \tau_{\text{WAL\_GW}} + \text{ToA}_{\text{ACK}} + \tau_{\text{turnaround\_Node}} + W_{\text{trail}} + 2 \cdot \tau_{\text{drift\_max}}
\end{cases}$$

### 4.2 Fail-Closed Invariant Verification
1. **Unbounded Gateway WAL Latency ($\tau_{\text{WAL\_GW}}$):**
   - If $\tau_{\text{WAL\_GW}}$ is unknown or unbounded, the validator returns `FAIL_CLOSED`.
   - Reason: `DEC-127-05` requires proven 0% data loss; transmitting ACK before durable WAL write violates safety.
2. **Rejection of Legacy SF8 Sub-Windows (TIM-01):**
   - In legacy documentation, sub-windows were illustrated as $100\text{ms} / 20\text{ms} / 100\text{ms}$ inside a 220ms envelope $[25, 245)\text{ms}$.
   - At SF8: $\text{ToA}_{\text{UP\_EVENT}} = 113.152\text{ms} > 100.0\text{ms}$ (Overrun by $+13.152\text{ms}$).
   - $\text{ToA}_{\text{DOWN\_EVENT\_ACK}} = 102.912\text{ms} > 100.0\text{ms}$ (Overrun by $+2.912\text{ms}$).
   - Two-way on-air ToA alone is $113.152 + 102.912 = 216.064\text{ms}$. With minimal 20ms turnaround, total roundtrip is $236.064\text{ms} > 220.0\text{ms}$ (Overrun by $+16.064\text{ms}$).
   - **Verdict:** Legacy 100ms sub-windows and 220ms envelope are **STRICTLY REJECTED** for SF8.
3. **Rejection of Legacy 250ms Beacon Window at SF8 (TIM-02):**
   - $\text{ToA}_{\text{DOWN\_SYNC\_BEACON}}(\text{80B, SF8}) = 256.512\text{ms} > 250.0\text{ms}$ (Overrun by $+6.512\text{ms}$).
   - **Verdict:** Legacy 250ms Beacon window is **STRICTLY REJECTED** for SF8.

### 4.3 Why Candidate 400ms Timing Cannot Be Accepted Solely on Theoretical ToA
A common trap is assuming a 400ms slot duration is automatically feasible for SF8 simply because:
$$\text{ToA}_{\text{EVENT}} (113.152\text{ms}) + \text{ToA}_{\text{ACK}} (102.912\text{ms}) = 216.064\text{ms} < 400.0\text{ms}$$
This arithmetic leaves an apparent theoretical slack of $183.936\text{ms}$. However, on real embedded hardware, the remaining budget must simultaneously cover:
1. Leading guard band ($W_{\text{lead}} \ge 25\text{ ms}$).
2. Node FreeRTOS task scheduling jitter ($\tau_{\text{jitter\_Node}} \approx 2\text{–}5\text{ ms}$).
3. SX1276 mode turnaround from RX to TX and TX to RX ($\approx 2 \times 0.1\text{ ms}$).
4. Gateway durable SQLite WAL flush commit latency ($\tau_{\text{WAL\_GW}} \approx 10\text{–}35\text{ ms}$).
5. Trailing guard band ($W_{\text{trail}} \ge 100\text{ ms}$).
6. Maximum cumulative crystal clock drift ($2 \cdot \tau_{\text{drift\_max}} \le 12\text{ ms}$ over 300s holdover).

If measured Gateway flash latency exhibits tail latency outliers ($P99 > 35\text{ ms}$) or FreeRTOS task starvation delays dispatch by $> 15\text{ ms}$, the 400ms slot will experience boundary collisions and packet drops. **Physical measurement is mandatory prior to numerical freeze.**

---

## 5. Phase 4 — Candidate Profile Feasibility Matrix & Guard Recommendation

### 5.1 Profile Feasibility Matrix

| Profile Identifier | SF | BW (kHz) | Slot Duration ($T_{\text{slot}}$) | Sub-Window Geometry $[W_{\text{lead}}, W_{\text{EVENT}}, W_{\text{GAP}}, W_{\text{ACK}}, W_{\text{trail}}]$ | Beacon Window | Theoretical Margin | Hardware Feasibility Status |
|---|:---:|:---:|:---:|---|:---:|:---:|---|
| **`PROF_LEGACY_SF7`** | 7 | 125 | 400 ms | $[25, 100, 20, 100, 155]\text{ ms}$ | 250 ms | $+38.3\text{ms}$ (Event), $+48.5\text{ms}$ (ACK) | **FEASIBLE (THEORETICAL)** · Proven by #201 |
| **`PROF_LEGACY_SF8`** | 8 | 125 | 400 ms | $[25, 100, 20, 100, 155]\text{ ms}$ | 250 ms | $-13.2\text{ms}$ (Event), $-2.9\text{ms}$ (ACK) | **REJECTED (INFEASIBLE)** · Fails closed |
| **`PROF_CANDIDATE_SF8_A`** | 8 | 125 | 400 ms | $[25, 125, 35, 115, 100]\text{ ms}$ | 400 ms | $+11.8\text{ms}$ (Event), $+12.1\text{ms}$ (ACK) | **CANDIDATE ONLY** · Requires WAL $\le 15\text{ms}$ |
| **`PROF_CANDIDATE_SF8_B`** | 8 | 125 | 450 ms | $[30, 130, 45, 120, 125]\text{ ms}$ | 400 ms | $+16.8\text{ms}$ (Event), $+17.1\text{ms}$ (ACK) | **CANDIDATE ONLY** · Conservative margin |
| **`PROF_FALLBACK_HYBRID`** | 8/7 | 125 | 400 ms | DATA at SF8 (rebalanced), Beacon locked at SF7 | 250 ms | $+11.8\text{ms}$ (DATA), $+106.4\text{ms}$ (Beacon) | **CANDIDATE ONLY** · Dual-SF strategy |

### 5.2 Guard Time Budget Formulation (Non-Double-Counted)
Based on `tests/hil/rf_timing/analysis/guard_budget_calculator.py`:
$$\tau_{\text{drift}} = 2 \times \text{PPM}_{\text{crystal}} \times T_{\text{sync}} = 2 \times (20 \times 10^{-6}) \times 10.0\text{ s} = 400\ \mu\text{s} = 0.40\text{ ms}$$
$$\tau_{\text{prop}} = \frac{5.0\text{ km}}{299,792.458\text{ km/s}} \approx 16.7\ \mu\text{s} \approx 0.017\text{ ms}$$
$$\text{Base Guard} = \tau_{\text{drift}} + \tau_{\text{sync\_jitter}} (25\ \mu\text{s}) + \tau_{\text{task\_jitter}} (100\ \mu\text{s}) + \tau_{\text{rx\_turnaround}} (60\ \mu\text{s}) + \tau_{\text{prop}} \approx 0.602\text{ ms}$$
Applying conservative $1.25\times$ engineering safety multiplier yields a minimum physical boundary guard of $\mathbf{\approx 0.75\text{ ms}}$ for a 10s sync window.

For a 300s Maintenance holdover window ($N_{\text{MISSED}} \le 2$):
$$\tau_{\text{drift\_300s}} = 2 \times (20 \times 10^{-6}) \times 300\text{ s} = 12,000\ \mu\text{s} = 12.0\text{ ms}$$
$$\text{Total 300s Holdover Guard} \approx 12.0\text{ ms} + 0.2\text{ ms} \times 1.25 \approx \mathbf{15.25\text{ ms}} \le 25.0\text{ ms (Fence 5 Limit)}$$

**Recommendation:**
- Minimum leading guard ($W_{\text{lead}}$): **$25.0\text{ ms}$** (comfortably absorbs maximum 300s holdover drift).
- Minimum trailing guard ($W_{\text{trail}}$): **$100.0\text{ ms}$** for SF8 candidate rebalanced profile (or $155.0\text{ ms}$ for SF7).

---

## 6. Edge Conditions, Failure Modes & Environmental Limitations

1. **Extreme Temperature Drift:**
   - At $-10^\circ\text{C}$ or $+60^\circ\text{C}$, low-cost crystals can drift up to $\pm 30\text{ PPM}$. At 30 PPM over 300s, drift reaches $18\text{ ms}$. If combined with 10ms task jitter, timing crosses the 25ms holdover fence. Temperature testing in thermal chamber is recommended.
2. **FreeRTOS High-Load Starvation:**
   - If SQLite checkpointing or TLS crypto operations monopolize the Gateway CPU Core 0, ISR dispatch to the radio task can slip by $> 5\text{ ms}$. Radio Owner task MUST run at `configMAX_PRIORITIES - 2` with dedicated core pinning.
3. **Flash Write Wear & Garbage Collection:**
   - Raw NAND/NOR flash writes can exhibit latency spikes up to $50\text{–}100\text{ ms}$ during sector erase blocks. Gateway WAL database MUST reside on a high-end endurance-rated storage partition or NVS with pre-allocated wear-leveling pools to avoid blocking the RF ACK window.

---

## 7. Downstream Contract & Issue Handoffs

This verification package provides the necessary data-backed foundations for downstream tasks:

1. **Handoff to [Issue #127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127) / Gate G2:**
   - Formalizes that `contracts/radio-mac/tdma-schedule.md` and `specification.md` must maintain parameterized equations rather than fixed numeric tables.
   - Provides test vectors for SF7 and SF8 V2 packets.
2. **Handoff to [Issue #19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19) (TDMA Scheduling Engine in Go Backend):**
   - Backend scheduler must generate versioned JSON schedules containing explicit sub-window durations ($W_{\text{lead}}, W_{\text{EVENT}}, W_{\text{GAP}}, W_{\text{ACK}}, W_{\text{trail}}$).
   - Backend must not freeze single static numbers.
3. **Handoff to [Issue #130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130) (Gateway TDMA Implementation):**
   - Gateway must implement symbolic schedule validation on startup and fail-closed if received schedule violates measured bounds.
   - Gateway must measure and log actual WAL write durations.
4. **Handoff to [Issue #131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131) (Node TDMA & Deep-Sleep Integration):**
   - Node must enforce Fence 4 (`GUARD_TIMING_WINDOW`) using dynamic slot configuration received from Gateway.
   - Node must abort transmission fail-closed if wake-up or interrupt delay places current time past $W_{\text{lead}} + W_{\text{EVENT}}$.

---

## 8. Human Reviewer Acceptance Checklist

Before any numeric parameters can be approved in an ADR or merged into production contracts:

- [ ] **RF/Hardware Specialist:** Verified conducted RF setup, attenuator calibration, 50 $\Omega$ termination, and legal VN920 frequency compliance.
- [ ] **Embedded Systems Engineer:** Reviewed SPI transactions, ISR execution paths, FreeRTOS priority assignments, and verified that `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` is increased to $\ge 128\text{U}$ to support 80B Beacon reception.
- [ ] **MAC Protocol Specialist:** Verified non-overlapping slot boundaries, duty cycle limits ($\le 1.0\%$), and holdover drift models.
- [ ] **Project Owner:** Reviewed trial manifests, SHA256 hashes, and formally authorized candidate TDMA slot parameters.

---

## 9. Conclusion & Definition of Done Assessment

- **Artifacts Delivered:**
  - Complete, reproducible bench measurement procedure ([rf-hil-bench-setup-and-procedure.md](rf-hil-bench-setup-and-procedure.md)).
  - Comprehensive timing verification analysis and readiness report (this document).
  - Verifiable evidence manifest schema ([evidence_manifest_template.json](../../tests/hil/rf_timing/evidence_manifest_template.json)).
  - Versioned V2 profile matrix ([matrix_profile_v2.json](../../tests/hil/rf_timing/toa/matrix_profile_v2.json) and [matrix_profile_v2.csv](../../tests/hil/rf_timing/toa/matrix_profile_v2.csv)).
  - Extended C firmware test configuration supporting V2 frames (26B, 19B, 80B, 21B).
  - Parameterized budget validation unit tests (100% passing across toolchain).
- **Execution Safety Compliance:**
  - Zero RF transmissions performed.
  - Zero fabricated measurements claimed.
  - Fail-closed gates maintained.
- **Final Gate Status:**
  `BENCH_PREPARATION_COMPLETE / RF_HIL_NOT_VERIFIED`
