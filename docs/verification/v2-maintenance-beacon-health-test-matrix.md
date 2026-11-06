# LP2P V2 Maintenance SF, SYNC_BEACON & HEALTH_REPLY Test Matrix

**Document ID:** `DOC-VERIF-V2-MAINT-BCN-HEALTH-002`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent Tracking:** Issue #178 (Agent 2 Work Package), Parent Issue #127, Umbrella Issue #125, Architecture Child Issue #126.
**Related Documents:** [Compatibility Dossier](v2-maintenance-beacon-health-compatibility.md), [Acceptance Gates](acceptance-gates.md), [Harness Quality Gates](../development/harness-quality-gates.md), [Post-Join Activation Test Matrix](join-v2-ready-tdma-activation-test-matrix.md), [RF Timing Methodology](rf-timing-methodology-and-harness.md).

---

## 1. Verification Strategy, Evidence Classes & Execution Policy

### 1.1 Verification Strategy
The LP2P Radio MAC V2 introduces critical architectural enhancements: asymmetric Ed25519 Gateway beacon signing, pairwise AES-128-CCM node health telemetry, and strict half-duplex TDMA scheduling. Because this protocol operates under lossy, half-duplex RF conditions on constrained microcontrollers (ESP32-WROOM-32E + SX1276), verification must span multiple independent tiers of evidence.

### 1.2 Evidence Classification Hierarchy
Every test scenario in this matrix is classified into one of seven distinct verification tiers:

| Evidence Tier | Code | Execution Environment | Tools & Instrumentation | Scope & Capabilities |
|:---|:---:|:---|:---|:---|
| **Static Analysis** | `STATIC` | Host Linux CI | `clang-tidy`, `cppcheck`, `ruff`, compiler warnings | Code safety, integer bounds, null checks, unused variables. |
| **Contract Schema** | `CONTRACT`| Host Python / Go | `pytest`, `pydantic`, `test_vectors.py`, Go unit tests | Structural binary wire codec encoding/decoding, field widths. |
| **Simulation** | `SIM` | Headless Linux Host| Multi-node discrete event simulator (`SimPy` / Go runner) | Protocol state machine logic, schedule countdowns, retransmissions. |
| **Integration** | `INT` | Containerized Bed | Docker Compose, Mosquitto 2.0 MQTT 5.0, Go Backend | End-to-end MQTT schedule dispatch, health ingestion, leases. |
| **Hardware-in-Loop**| `HIL` | Physical Bench | ESP32-WROOM-32E + SX1276, Logic Analyzer, Oscilloscope | Interrupt latency, FreeRTOS jitter, SPI bus turnaround. |
| **RF Physical** | `RF` | RF Shielded Range | Spectrum Analyzer, Coaxial Attenuators, Power Meter | On-air Time-on-Air (ToA), receiver sensitivity, clock drift. |
| **Security Audit** | `SEC` | Security Sandbox | Fuzzers, Cryptographic Test Vector Suite, Tamper Bed | Cryptographic boundary validation, replay, tag forgery. |

> [!IMPORTANT]
> **Strict Verification Policy (Owner Decision #137):**
> Every test scenario in this matrix currently holds the verification status **`NOT_RUN`**. Neither document creation, markdown approval, synthetic mock generation, nor local unit tests constitute verification of physical RF behavior or cross-platform interoperability. `NOT_RUN` must never be conflated with `PASS`.

---

## 2. Test Execution Preconditions & Baseline Configuration

### 2.1 Hardware & Firmware Baseline
- **Node Transceiver:** ESP32-WROOM-32E + Semtech SX1276 connected via locked SPI pinout (HW-001: SCK=GPIO5, MISO=GPIO19, MOSI=GPIO27, NSS=GPIO18, RST=GPIO23, DIO0=GPIO26). DIO1–DIO5 not routed.
- **Node Firmware:** C / FreeRTOS / ESP-IDF **v6.1** ([ADR-0003](../adr/0003-esp-idf-v6-1.md)). Single radio owner task.
- **Gateway Node:** ESP32-WROOM-32E / Linux Gateway host + SX1276 radio owner, Mosquitto 2.0 MQTT 5.0 client.
- **Backend Stack:** Go Modular Monolith, PostgreSQL 16, TLS 1.3 mutual authentication.

### 2.2 RF Physical Layer Profile (P-10S-15 Symbolic Baseline)
- **Frequency Band:** 920.0 MHz – 923.0 MHz (sub-band channel 921.4 MHz).
- **Modulation Parameters:** LoRa, Bandwidth $\text{BW} = 125\text{ kHz}$, Spreading Factor $\text{SF} = 7$, Coding Rate $\text{CR} = 4/5$.
- **Symbolic Timing:** Superframe duration $T_{\text{SF}} = 10{,}000\text{ ms}$; Maintenance interval $T_{\text{MAINT}} \approx 300\text{ s}$ ($M = 30$ superframes).
- **Physical Timing Dependency:** All slot widths ($T_{\text{SLOT}}$), guard intervals ($T_{\text{GUARD}}$), and timeout windows are **symbolic**, awaiting physical hardware-in-the-loop measurement under **Issue #169**.

---

## 3. Comprehensive Verification Matrix (24 Scenarios)

### Group 1: Nominal Maintenance Synchronization & Health Flow

#### TM-MH-01: Nominal Sync Beacon Reception & Clock Disciplining (Happy Path)
- **Target Specification:** Candidate V2 `DOWN_SYNC_BEACON` (0x43, 80B), Section 3.2.
- **Verification Tier & Owner:** `INT` / `HIL` · Gateway & Firmware Teams.
- **Preconditions:** Node is in `ACTIVATED` state; local clock drift is within $\pm 15\text{ ms}$; Gateway broadcasts valid 80-byte `DOWN_SYNC_BEACON` signed with $\text{SK}_{\text{GW}}$.
- **Stimulus:** Gateway transmits `DOWN_SYNC_BEACON` in Slot 0 at superframe boundary $t=0$. Node opens `RxSingle` window at $t = -15\text{ ms}$.
- **Expected Outcome:**
  - Node detects preamble, receives full 80-byte payload, and verifies Ed25519 signature against stored $\text{PK}_{\text{GW}}$.
  - Node updates $\text{MAINT\_SEQ}_{\text{HW}} \leftarrow \text{MAINT\_SEQ}$; disciplines local RTC to `NETWORK_TIME_MS`.
  - Node transitions to Low-Power Standby; $N_{\text{MISSED}}$ is reset to 0.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-02: Scheduled Health Reply Uplink (Happy Path)
- **Target Specification:** Candidate V2 `UP_HEALTH_REPLY` (0x44, 21B), Section 3.3.
- **Verification Tier & Owner:** `INT` / `HIL` · Gateway & Firmware Teams.
- **Preconditions:** Node successfully received Beacon `TM-MH-01` with $\text{MAINT\_SEQ} = 100$; Node is assigned Health Slot #3.
- **Stimulus:** At the scheduled onset of Slot #3, Node wakes from Standby, prepares 21-byte `UP_HEALTH_REPLY`, encrypts payload with AES-128-CCM ($K_{\text{SESSION\_UP}}$), and transmits frame.
- **Expected Outcome:**
  - Node transmits within Slot #3 boundary without overlapping Slot #2 or Slot #4.
  - Gateway receives frame in `RxContinuous` mode, validates 8-byte CCM tag, verifies $\text{MAINT\_SEQ} = 100$, and forwards health report via MQTT topic `uplink/health`.
  - Gateway logs receipt reason `HEALTH_ACCEPTED`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-03: Periodic Maintenance Cadence (~300 s Target Interval)
- **Target Specification:** Maintenance Calendar Interleaving, Section 4.1.
- **Verification Tier & Owner:** `SIM` / `INT` · Radio MAC & Backend Teams.
- **Preconditions:** Network operating with $M = 29$ DATA superframes ($T_{\text{SF}} = 10\text{ s}$) between Maintenance superframes.
- **Stimulus:** Run network simulation for 3,600 seconds (12 maintenance cycles).
- **Expected Outcome:**
  - Exactly 12 Maintenance Superframes occur at deterministic ~300 s intervals.
  - No DATA superframe is truncated or collided with by a Maintenance superframe.
  - Node clock drift remains bounded within the maximum guard budget across all cycles.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-04: Multi-Node Scheduled Health Non-Overlapping Execution
- **Target Specification:** Maintenance Slot Allocation, Section 4.2.
- **Verification Tier & Owner:** `SIM` / `HIL` · Firmware & Gateway Teams.
- **Preconditions:** 10 active Nodes ($N_1$..$N_{10}$) assigned consecutive Health slots 1..10 in Maintenance SF.
- **Stimulus:** All 10 nodes receive `DOWN_SYNC_BEACON` and transmit `UP_HEALTH_REPLY` in their respective slots.
- **Expected Outcome:**
  - Logic analyzer / RF capture confirms zero overlapping transmissions between adjacent nodes.
  - Inter-slot silence periods meet or exceed $T_{\text{GUARD}}$ between every transmission.
  - Gateway successfully decodes all 10 health packets without collision.
- **Verification Status:** `NOT_RUN`.

---

### Group 2: Sync Beacon Validation & Cryptographic Negative Tests

#### TM-MH-05: Sync Beacon Corrupted Payload / CRC Failure
- **Target Specification:** SX1276 PHY & Frame Integrity, Section 3.2.
- **Verification Tier & Owner:** `HIL` / `SEC` · Firmware Team.
- **Preconditions:** Node listening in Slot 0.
- **Stimulus:** RF noise generator injects burst interference during `DOWN_SYNC_BEACON` transmission, corrupting 3 bytes in the payload.
- **Expected Outcome:**
  - SX1276 hardware detects LoRa payload CRC error; `PayloadCrcError` flag asserted in `RegIrqFlags`.
  - Firmware discards packet immediately without invoking Ed25519 verification.
  - Node increments $N_{\text{MISSED}} \leftarrow 1$; local clock is not updated.
  - Log reason: `BAD_CRC`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-06: Sync Beacon Invalid Ed25519 Signature Rejection
- **Target Specification:** Ed25519 Verification, Section 3.2 & Threat 2.
- **Verification Tier & Owner:** `CONTRACT` / `SEC` · Security Team.
- **Preconditions:** Node listening in Slot 0 with provisioned Gateway public key $\text{PK}_{\text{GW}}$.
- **Stimulus:** Attacker broadcasts an 80-byte Beacon with valid fields and CRC, but signed with an unauthorized private key $\text{SK}_{\text{ATTACKER}}$.
- **Expected Outcome:**
  - Node firmware computes $M_{\text{BCN}}$ transcript and invokes `mbedtls_ed25519_verify`.
  - Signature verification returns non-zero error code.
  - Node rejects Beacon; does not update `MAINT_SEQ` or discipline clock.
  - Node increments $N_{\text{MISSED}}$; emits security audit log `BAD_AUTH`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-07: Sync Beacon Replay Attack Detection (Stale Sequence Counter)
- **Target Specification:** Monotonic Sequence Counter, Section 3.2 & Threat 2.
- **Verification Tier & Owner:** `SEC` / `CONTRACT` · Security Team.
- **Preconditions:** Node current high-water mark $\text{MAINT\_SEQ}_{\text{HW}} = 500$.
- **Stimulus:** Attacker captures authentic Beacon with $\text{MAINT\_SEQ} = 450$ and replays it over RF during Slot 0.
- **Expected Outcome:**
  - Signature is valid, but Node checks $\text{MAINT\_SEQ} \le \text{MAINT\_SEQ}_{\text{HW}}$ ($450 \le 500$).
  - Packet is immediately dropped as replay.
  - Clock and schedule state remain unchanged; $N_{\text{MISSED}}$ incremented.
  - Log reason: `REPLAY`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-08: Sync Beacon Network ID / Gateway ID Mismatch
- **Target Specification:** Multi-Gateway & Network Domain Isolation, Section 3.2.
- **Verification Tier & Owner:** `CONTRACT` / `SIM` · Radio MAC Team.
- **Preconditions:** Node provisioned for $\text{NETWORK\_ID} = 0\text{x}01020304$, associated with $\text{GW\_ID} = 0\text{x}02$.
- **Stimulus:** Neighboring network Gateway broadcasts valid Beacon with $\text{NETWORK\_ID} = 0\text{x}99887766$ and $\text{GW\_ID} = 0\text{x}05$.
- **Expected Outcome:**
  - Node checks `GW_ID` ($0\text{x}05 \neq 0\text{x}02$) and rejects packet before signature verification.
  - Transcript domain separator mismatch prevents signature verification even if `GW_ID` matched.
  - Log reason: `WRONG_DEST`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-09: Sync Beacon Expired / Drifted Network Time Rejection
- **Target Specification:** Sanity Time Bounds, Section 3.2 & Threat 5.
- **Verification Tier & Owner:** `SEC` / `HIL` · Firmware Team.
- **Preconditions:** Node local RTC reads $t_{\text{LOCAL}} = 1{,}700{,}000{,}000{,}000\text{ ms}$.
- **Stimulus:** Attacker broadcasts signed Beacon containing an anomalous timestamp $t_{\text{BCN}} = 1{,}700{,}100{,}000{,}000\text{ ms}$ ($\Delta t = 100\text{ s}$ discrepancy).
- **Expected Outcome:**
  - Node detects $|\Delta t| > \Delta T_{\text{SANITY}}$ ($60\text{ s}$).
  - Beacon rejected for clock disciplining; node flags RTC state as suspect (`RTC_SUSPECT`).
  - Log reason: `UNSYNCED`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-10: Unknown Signer ID / Revoked Gateway Key Rejection
- **Target Specification:** Public Key Provisioning & Revocation, Section 6.2 & Threat 3.
- **Verification Tier & Owner:** `SEC` / `CONTRACT` · Security Team.
- **Preconditions:** Node has $\text{SIGNER\_ID} = 0\text{x}01$ marked as revoked in NVS.
- **Stimulus:** Gateway transmits Beacon containing `SIGNER_ID = 0x01`.
- **Expected Outcome:**
  - Node inspects byte 15 (`SIGNER_ID`), detects revoked key status in keystore.
  - Beacon dropped without signature evaluation; node transitions toward Holdover.
  - Log reason: `BAD_AUTH`.
- **Verification Status:** `NOT_RUN`.

---

### Group 3: Node Health Reply & Access Control Negative Tests

#### TM-MH-11: Unscheduled Health Reply Attempt in DATA Slot (Enforced Rejection)
- **Target Specification:** Slot Isolation Policy, Section 4.2 & Deliverable 2.
- **Verification Tier & Owner:** `STATIC` / `HIL` · Firmware Team.
- **Preconditions:** Node assigned Slot #5 in normal DATA superframe.
- **Stimulus:** Software bug or errant task attempts to call `mac_tx_health_reply()` during a DATA superframe.
- **Expected Outcome:**
  - Firmware TDMA slot guard detects $SF_{\text{TYPE}} \neq SF_{\text{MAINT}}$.
  - MAC layer rejects transmission request locally; RF synthesizer remains in Sleep.
  - System error counter incremented; zero RF emitted into DATA slot.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-12: Health Reply CCM Tag Tampering / Wrong Session Key
- **Target Specification:** AES-128-CCM Tag Verification, Section 3.3 & Threat 4.
- **Verification Tier & Owner:** `SEC` / `CONTRACT` · Security Team.
- **Preconditions:** Gateway listening in Health Slot #3.
- **Stimulus:** Rogue device transmits 21-byte `UP_HEALTH_REPLY` using an expired or forged session key $K_{\text{FORGED}}$.
- **Expected Outcome:**
  - Gateway decrypts payload and validates 8-byte CCM tag against active session key $K_{\text{SESSION\_UP}}$.
  - Tag verification fails; Gateway drops packet immediately.
  - Gateway rejects MQTT publication; logs `BAD_AUTH`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-13: Health Reply Monotonic Counter Replay Detection
- **Target Specification:** Uplink Anti-Replay, Section 3.3 & Threat 4.
- **Verification Tier & Owner:** `SEC` / `INT` · Gateway & Security Teams.
- **Preconditions:** Gateway recorded highest uplink frame counter for Node #7 as $C_{\text{HW}} = 105$.
- **Stimulus:** Attacker replays valid past `UP_HEALTH_REPLY` from Node #7 with `FRAME_COUNTER` = 100.
- **Expected Outcome:**
  - Gateway header parser detects `FRAME_COUNTER` $\le C_{\text{HW}}$ ($100 \le 105$).
  - Packet dropped before decryption.
  - Log reason: `REPLAY`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-14: Unjoined / Inactive Node Health Transmission Prevention (Fail-Closed)
- **Target Specification:** Node Lifecycle Rights, Section 4.3.
- **Verification Tier & Owner:** `STATIC` / `HIL` · Firmware Team.
- **Preconditions:** Node is in `JOINING` or `SESSION_READY_NOT_ACTIVE` state.
- **Stimulus:** Firmware timer triggers health reporting callback.
- **Expected Outcome:**
  - State check verifies `NODE_STATE != ACTIVATED`.
  - Transmission blocked fail-closed; no packet emitted.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-15: Health Reply Pending Event Count Inconsistency Handling
- **Target Specification:** Backlog Reporting, Section 3.3.
- **Verification Tier & Owner:** `INT` · Backend Team.
- **Preconditions:** Node has 5 unacknowledged events in local FIFO (`PENDING_COUNT = 5`).
- **Stimulus:** Node transmits `UP_HEALTH_REPLY` with `PENDING_COUNT = 5`.
- **Expected Outcome:**
  - Gateway forwards report to Backend; Backend observes Node has high pending backlog without recent DATA uplinks.
  - Backend flags Node for diagnostic health alert.
- **Verification Status:** `NOT_RUN`.

---

### Group 4: Clock Drift, Holdover & Half-Duplex Physical Guard Tests

#### TM-MH-16: Single Missed Beacon Holdover Tolerance
- **Target Specification:** Holdover Mode, Section 5.2.
- **Verification Tier & Owner:** `HIL` · Firmware Team.
- **Preconditions:** Node in `ACTIVATED` state; $N_{\text{MISSED}} = 0$.
- **Stimulus:** Gateway RF suppressed for 1 maintenance superframe ($N_{\text{MISSED}} \to 1$). Node has pending event in subsequent DATA superframe.
- **Expected Outcome:**
  - Node detects Beacon timeout; increments $N_{\text{MISSED}} \leftarrow 1$.
  - Node remains in Holdover ($N \le 2$); timing uncertainty ($\pm 30\text{ ms}$) remains within $T_{\text{GUARD}}$.
  - Node successfully transmits pending `UP_EVENT` in its assigned DATA slot.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-17: Consecutive Missed Beacons ($N \ge 3$) Fail-Closed Lockout
- **Target Specification:** Desynchronization Lockout, Section 5.2 & Deliverable 3.
- **Verification Tier & Owner:** `HIL` · Firmware & Radio MAC Teams.
- **Preconditions:** Node has missed 2 consecutive beacons ($N_{\text{MISSED}} = 2$).
- **Stimulus:** Gateway RF suppressed for third consecutive maintenance cycle ($N_{\text{MISSED}} \to 3$). Node local event occurs.
- **Expected Outcome:**
  - Node increments $N_{\text{MISSED}} \leftarrow 3$; detects $N_{\text{MISSED}} \ge N_{\text{MAX\_HOLDOVER}}$.
  - Node transitions to `HOLDOVER_DESYNCHRONIZED` state.
  - Node logs event locally in durable NVS, but **locks RF transmission**.
  - No RF packet emitted in DATA slot; collision with adjacent slots prevented.
  - Log reason: `UNSYNCED`.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-18: Clock Recovery After Extended Holdover
- **Target Specification:** Clock Recovery, Section 5.2.
- **Verification Tier & Owner:** `HIL` · Firmware Team.
- **Preconditions:** Node in `HOLDOVER_DESYNCHRONIZED` state ($N_{\text{MISSED}} = 4$, DATA TX locked).
- **Stimulus:** Gateway RF restored. Node opens continuous RX in Slot 0; receives authentic `DOWN_SYNC_BEACON`.
- **Expected Outcome:**
  - Node validates signature, resets local RTC to `NETWORK_TIME_MS`, resets $N_{\text{MISSED}} \leftarrow 0$.
  - Node restores state to `ACTIVATED`; unlocks DATA transmission.
  - Backlogged events from NVS are transmitted in next assigned DATA slot.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-19: Half-Duplex Transceiver Mode Transition Guard (SX1276 Collision)
- **Target Specification:** Half-Duplex Transceiver Constraints, Section 4.4.
- **Verification Tier & Owner:** `HIL` · Firmware Team & Issue #169.
- **Preconditions:** Real ESP32-WROOM-32E + SX1276 test bench monitored by 4-channel oscilloscope on SPI lines and RF power detector.
- **Stimulus:** Execute transition from RX mode in Slot 0 to TX mode in Slot 1.
- **Expected Outcome:**
  - Firmware sequences SPI registers: `OpMode` $\to$ Standby ($5\text{ }\mu\text{s}$), PLL lock ($120\text{ }\mu\text{s}$), PA ramp.
  - RF output activates strictly after $T_{\text{GUARD}}$ silence.
  - No SPI bus contention; zero register corruption during mode switch.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-20: Worst-Case Drift Window Margin Verification (Pre-#169 Baseline)
- **Target Specification:** RxSingle Window Opening, Section 5.1.
- **Verification Tier & Owner:** `HIL` / `RF` · RF Team & Issue #169.
- **Preconditions:** Node subjected to thermal chamber temperature ramp from $-10^\circ\text{C}$ to $+60^\circ\text{C}$.
- **Stimulus:** Node operates over 300 s maintenance interval without intermediate sync.
- **Expected Outcome:**
  - Measure actual crystal frequency deviation (ppm).
  - Confirm widened `RxSingle` window ($T_{\text{RX\_OPEN}}$) captures Beacon preamble across full temperature range.
  - Log raw drift dataset for Issue #169 analysis.
- **Verification Status:** `NOT_RUN`.

---

### Group 5: Schedule Countdown & Maintenance Cutover

#### TM-MH-21: Schedule Announcement Countdown $3 \to 2 \to 1$ via Sync Beacon
- **Target Specification:** Schedule Countdown, Section 5.3.
- **Verification Tier & Owner:** `SIM` / `INT` · Backend & Gateway Teams.
- **Preconditions:** Backend stages schedule version $V=11$; Gateway prepares countdown $H=3$.
- **Stimulus:** Gateway broadcasts three consecutive Maintenance Beacons with countdown flags $3 \to 2 \to 1$.
- **Expected Outcome:**
  - All nodes decode countdown flags, stage shadow schedule, and arm cutover timer for $K_{\text{TARGET}} = K+3$.
  - Gateway and nodes execute simultaneous atomic schedule promotion at $K_{\text{TARGET}}$.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-22: Aborted Schedule Announcement Handling
- **Target Specification:** Schedule Abort, Section 5.3.
- **Verification Tier & Owner:** `SIM` / `INT` · Backend & Gateway Teams.
- **Preconditions:** Gateway broadcast Countdown = `3`; Backend detects missing 100%-READY confirmation from Node #4 and issues MQTT schedule abort.
- **Stimulus:** Gateway broadcasts next Beacon with Countdown Flag = `0` (cleared).
- **Expected Outcome:**
  - Nodes detect cleared countdown flag; discard staged shadow schedule.
  - Active schedule remains on version $V_{\text{CURR}}$; zero service disruption.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-23: Activation Boundary Cutover Synchronization Across Nodes
- **Target Specification:** Atomic Cutover, Section 5.3 & 5.4.
- **Verification Tier & Owner:** `HIL` / `INT` · Gateway & Firmware Teams.
- **Preconditions:** Multi-node testbed running countdown cutover from Schedule A (Node #1 in Slot #2) to Schedule B (Node #1 in Slot #5).
- **Stimulus:** Superframe sequence reaches $K_{\text{TARGET}}$.
- **Expected Outcome:**
  - Exactly at $K_{\text{TARGET}}$, Node #1 stops transmitting in Slot #2 and begins transmitting in Slot #5.
  - Gateway listens on Slot #5; zero ghost packets emitted in Slot #2.
- **Verification Status:** `NOT_RUN`.

#### TM-MH-24: Out-of-Sequence / Skipped Countdown Frame Rejection
- **Target Specification:** Countdown Validation, Section 5.3.
- **Verification Tier & Owner:** `SEC` / `SIM` · Security Team.
- **Preconditions:** Node received Countdown = `3`.
- **Stimulus:** Attacker injects fake Beacon claiming Countdown = `1` skipping countdown step `2`.
- **Expected Outcome:**
  - Node detects invalid countdown transition ($3 \to 1$ instead of $3 \to 2$).
  - Node rejects premature cutover; remains on active schedule until valid sequence completed.
- **Verification Status:** `NOT_RUN`.

---

## 4. Hardware-in-the-Loop (HIL) Handoff to Issue #169

In accordance with project separation of concerns, this dossier provides the formal measurement requirements for physical verification under **Issue #169**:

```
+---------------------------------------------------------------------------------------+
|                           ISSUE #178 -> ISSUE #169 HIL HANDOFF                        |
+---------------------------------------------------------------------------------------+
| Input Parameters & Hypotheses (Symbolic) | Physical Observables Required From #169    |
+------------------------------------------+--------------------------------------------+
| 1. DOWN_SYNC_BEACON Length: 80 Bytes     | - Measured RF on-air ToA (ms) via Analyzer |
|    (SF7, BW125kHz, CR4/5)                | - TxCommand -> TxDone IRQ Edge Latency     |
+------------------------------------------+--------------------------------------------+
| 2. Ed25519 Signature Verification Latency| - Measured CPU processing time on ESP32-S3 |
|    on ESP32 @ 160MHz                     |   / ESP32-WROOM-32E (P50, P95, Max ms)     |
+------------------------------------------+--------------------------------------------+
| 3. Node Clock Drift over 300 s Interval  | - Real quartz ppm variation (-10C to +60C) |
|    (Target Cadence)                      | - Max measured accumulated drift (ms)      |
+------------------------------------------+--------------------------------------------+
| 4. SX1276 Transceiver Mode Turnaround    | - Measured T_RX_TO_TX and T_TX_TO_RX (us)  |
|    (HW-001 SPI Pinout)                   | - Phase-lock loop (PLL) settling time      |
+------------------------------------------+--------------------------------------------+
| 5. Guard Interval Budget Validation      | - Data-backed recommendation for T_GUARD   |
|    (Absorb drift + turnaround + jitter)  |   (Verify whether 25ms / 35ms is valid)    |
+------------------------------------------+--------------------------------------------+
```

### Deliverable Artifacts Required From Issue #169 Before Normative Contract Freeze
1. Traceable raw logic analyzer / oscilloscope capture files with SHA-256 digests.
2. Statistical distribution (P50, P95, P99, Max) of Ed25519 verification latency on ESP-IDF v6.1.
3. Thermal drift measurements from a calibrated temperature chamber.
4. Formal recommendation for $T_{\text{GUARD}}$ and minimum slot duration $T_{\text{SLOT\_MIN}}$.

---

## 5. Traceability Matrix

| Requirement / Threat / AC | Description | Associated Verification Test IDs |
|:---|:---|:---|
| **AC-1** | Compatibility Matrix & Statuses | `TM-MH-01`, `TM-MH-02`, `TM-MH-05`, `TM-MH-06` |
| **AC-2** | Scheduling, Clock, 100%-READY, Half-Duplex | `TM-MH-03`, `TM-MH-04`, `TM-MH-16`, `TM-MH-17`, `TM-MH-19`, `TM-MH-20` |
| **AC-3** | Threat Model & Negative Tests | `TM-MH-06`, `TM-MH-07`, `TM-MH-08`, `TM-MH-09`, `TM-MH-10`, `TM-MH-12`, `TM-MH-13` |
| **AC-4** | Countdown & Cutover Synchronization | `TM-MH-21`, `TM-MH-22`, `TM-MH-23`, `TM-MH-24` |
| **AC-5** | HIL Handoff to Issue #169 | Section 4, `TM-MH-19`, `TM-MH-20` |
