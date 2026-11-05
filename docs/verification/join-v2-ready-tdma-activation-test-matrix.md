# LP2P V2 Post-Join Activation: Verification & Test Matrix

**Document ID:** `DOC-JOIN-V2-READY-ACT-002`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent / Tracking:** Issue #136, Umbrella #125, G2 Compatibility #127.
**Related Documents:** [Activation Design](join-v2-ready-tdma-activation-design.md), [Acceptance Gates](acceptance-gates.md), [Harness Quality Gates](../development/harness-quality-gates.md).

---

## 1. Verification Strategy & Evidence Classes

To validate the V2 Post-Join Node READY $\to$ TDMA Schedule $\to$ Activation pipeline, tests must span multiple tiers of verification. Because this is a mission-critical RF MAC layer with strict security, timing, and half-duplex constraints, verification cannot rely solely on unit tests or synthetic fixtures.

### Evidence Classification Hierarchy

| Evidence Class | Acronym | Description | Scope & Execution Environment |
|---|---|---|---|
| **Static Analysis** | `STATIC` | Code inspection, compiler type checking, linters, bounds checkers. | CI Host (clang-tidy, golangci-lint, ruff). |
| **Contract Schema** | `CONTRACT` | Structural JSON schema validation and binary codec parsing tests. | Python / Go contract test harness. |
| **Simulation** | `SIM` | Discrete-event multi-node network simulation (SimPy / Go simulator). | Headless multi-node protocol runner. |
| **Integration** | `INT` | End-to-end software integration (Mosquitto broker + Go Backend + simulated nodes). | Local Docker Compose testbed. |
| **Hardware-in-the-Loop**| `HIL` | Real ESP32-WROOM-32E + SX1276 bench running under oscilloscope / logic analyzer. | Embedded test rack with RF coaxial cabling. |
| **RF / Physical** | `RF` | Over-the-air spectrum analysis, ToA verification, harmonic and airtime compliance. | Anechoic chamber / RF test range. |
| **Security Audit** | `SEC` | Formal cryptographic proof verification, tamper injection, replay evaluation. | Independent cryptographer / auditor review. |

> [!IMPORTANT]
> In accordance with project policy (Owner Decision #137 and AGENTS.md), **every test case in this matrix currently holds the verification status `NOT_RUN`**. Neither document creation, markdown approval, nor synthetic test vectors constitute verification of physical RF behavior or cross-language interoperability.

---

## 2. Test Execution Preconditions & Testbed Setup

All tests assume the standard MVP profile:
- **RF Channel Plan:** 920.0 MHz – 923.0 MHz (Profile `P-10S-15`).
- **Superframe Duration:** $T_{\text{SF}} = 10{,}000\text{ ms}$ (5 subframes $\times$ 2,000 ms).
- **Slot Allocation:** 15 Static DATA slots (400 ms each) per superframe.
- **Node Hardware:** ESP32-WROOM-32E + SX1276 connected via SPI, ESP-IDF v6.1, FreeRTOS.
- **Gateway Hardware:** ESP32 / Linux host + SX1276 radio owner.
- **Backend Stack:** Go Modular Monolith, Mosquitto 2.0 MQTT 5.0 broker with TLS and ACLs, PostgreSQL 16.
- **Node Identity:** Factory MAC from eFuse; 32-byte provisioned pre-shared key $K_{\text{JOIN}}$.

---

## 3. Comprehensive Verification Matrix (25 Scenarios)

### Group 1: Nominal Readiness & Activation Handshake

#### TM-01: Nominal 100%-READY Happy Path & Activation
- **Description:** Verifies that a Node completing V2 Join transitions through READY, stages the schedule, and activates exactly at the scheduled superframe boundary.
- **Preconditions:** Node has completed V2 Join handshake (processed valid `DOWN_JOIN_FINISH`); Gateway is online; Backend has available slot #7 in TDMA schedule.
- **Stimulus:**
  1. Node waits for CTRL window in Subframe 4 and transmits candidate `UP_JOIN_READY` (0x49).
  2. Gateway receives `UP_JOIN_READY`, validates `GW_READY_TAG`, and publishes `uplink/join-ready` to Backend.
  3. Backend verifies `BACKEND_READY_PROOF`, allocates Slot #7, and publishes `downlink/schedule` (version $V=10$, $H=3$).
  4. Gateway stages schedule, returns `STAGE_ACK` with $K_{\text{target}} = K_{\text{now}} + 3$, and broadcasts 3 Beacons with countdown $3 \to 2 \to 1$.
  5. Superframe sequence reaches $K_{\text{target}}$.
- **Expected Outcome:**
  - Node stages shadow schedule, evaluates all 8 DATA TX guards as TRUE at $K_{\text{target}}$, promotes schedule, and transmits DATA in Slot #7.
  - Gateway switches schedule at $K_{\text{target}}$ and emits `ACTIVE_REPORT`.
  - Backend marks Node and Schedule as ACTIVE.
- **TX Status:** Denied during staging; **Allowed** at $K_{\text{target}}$ in Slot #7.
- **Evidence Class:** `HIL` / `INT`
- **Verification Status:** `NOT_RUN`

#### TM-02: Single Node Missing READY in Multi-Node Network
- **Description:** 3 Nodes join simultaneously. Node 1 and Node 2 send valid `UP_JOIN_READY`; Node 3 loses power or RF packet is lost.
- **Preconditions:** Nodes 1, 2, 3 have received `DOWN_JOIN_FINISH`.
- **Stimulus:** Nodes 1 and 2 transmit `UP_JOIN_READY`. Node 3 remains silent. Timer $T_{\text{await\_ready}}$ expires at Backend.
- **Expected Outcome:**
  - Backend Planner generates schedule incorporating only Nodes 1 and 2.
  - Node 3 receives no assigned slot and remains in `SESSION_READY_NOT_ACTIVE`.
  - Node 3 evaluates Guard 6 (Slot Ownership) as FALSE and inhibits transmission.
- **TX Status:** Nodes 1 and 2: Allowed; **Node 3: Strictly Denied**.
- **Evidence Class:** `SIM` / `INT`
- **Verification Status:** `NOT_RUN`

---

### Group 2: Security, Replay & Cryptographic Negative Scenarios

#### TM-03: Malformed / Tampered Backend Proof in `UP_JOIN_READY`
- **Description:** An attacker or corrupted channel alters bits in `BACKEND_READY_PROOF` (bytes 15..30 of 0x49 frame).
- **Preconditions:** Node transmits candidate `UP_JOIN_READY`; byte 20 is bit-flipped in transit.
- **Stimulus:** Gateway receives frame. If `GW_READY_TAG` is intact, Gateway relays to Backend via `uplink/join-ready`.
- **Expected Outcome:**
  - Backend performs constant-time HMAC check against $K_{\text{JREADY}}$; validation fails.
  - Backend drops message, logs security event `ERR_BAD_READY_PROOF`, and does not allocate a slot.
  - Node never receives schedule allocation; fails closed.
- **TX Status:** **Denied**.
- **Evidence Class:** `SEC` / `CONTRACT`
- **Verification Status:** `NOT_RUN`

#### TM-04: Malformed / Tampered Gateway Tag in `UP_JOIN_READY`
- **Description:** Byte 10 (`GW_READY_TAG`) is corrupted or forged.
- **Preconditions:** Node transmits packet; RF bit error corrupts `GW_READY_TAG`.
- **Stimulus:** Gateway SX1276 receives packet in CTRL window and verifies `GW_READY_TAG` against $K_{\text{KC\_UP}}$.
- **Expected Outcome:**
  - Gateway detects invalid tag; immediately drops frame at radio driver layer.
  - Frame is NOT forwarded over MQTT; edge bandwidth is conserved.
- **TX Status:** **Denied**.
- **Evidence Class:** `HIL` / `SEC`
- **Verification Status:** `NOT_RUN`

#### TM-05: Replayed `UP_JOIN_READY` from Previous Session / Counter
- **Description:** Attacker captures a valid `UP_JOIN_READY` from session $N$ and replays it during session $N+1$.
- **Preconditions:** Node has rebooted and performed a fresh Join with `JOIN_COUNTER` incremented. Attacker transmits captured frame from previous counter.
- **Stimulus:** Replayed packet arrives at Gateway and Backend.
- **Expected Outcome:**
  - Gateway or Backend checks `JOIN_COUNTER` against current active session transaction.
  - Counter is strictly less than high-water mark; packet is rejected as `ERR_REPLAYED_COUNTER`.
- **TX Status:** **Denied**.
- **Evidence Class:** `SEC` / `INT`
- **Verification Status:** `NOT_RUN`

#### TM-06: Forged Schedule by Compromised Gateway
- **Description:** A compromised Gateway fabricates a TDMA schedule assigning a slot to an unauthorized Node without Backend approval.
- **Preconditions:** Rogue Gateway broadcasts Beacon with unapproved `schedule_version`.
- **Stimulus:** Sensor Node hears Beacon.
- **Expected Outcome:**
  - Node checks Schedule Authentication Tag / HMAC against Backend-derived credentials.
  - Verification fails; Node rejects schedule, evaluates Guard 3 as FALSE, and halts DATA TX.
- **TX Status:** **Denied**.
- **Evidence Class:** `SEC` / `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-07: Expired Lease Activation Attempt
- **Description:** A Node attempts to transmit DATA after its session lease $T_{\text{lease\_expiry}}$ has passed.
- **Preconditions:** Node was previously active; system clock advances beyond lease window without renewal.
- **Stimulus:** Application layer attempts to queue and transmit an event.
- **Expected Outcome:**
  - Node evaluates Guard 4 (`LEASE_ACTIVE`) as FALSE.
  - Transmission is inhibited; local event is queued; Node initiates lease renewal or re-join.
- **TX Status:** **Denied**.
- **Evidence Class:** `INT` / `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-08: Stale Session with `DEVICE_GENERATION` Rotation
- **Description:** Technician increments `DEVICE_GENERATION` in Backend registry (e.g. from 1 to 2) due to suspected key compromise.
- **Preconditions:** Node still holds keys derived from generation 1.
- **Stimulus:** Node attempts to transmit or stage schedule using old session keys.
- **Expected Outcome:**
  - Backend rejects any incoming uplink with `ERR_STALE_GENERATION`.
  - Node receives invalid tag on downlink; forces full re-provisioning / factory reset.
- **TX Status:** **Denied**.
- **Evidence Class:** `SEC` / `INT`
- **Verification Status:** `NOT_RUN`

---

### Group 3: MQTT Protocol & Timing Boundary Scenarios

#### TM-09: Duplicate / Reordered MQTT `downlink/schedule`
- **Description:** Network jitter causes Gateway to receive two copies of `downlink/schedule` with the same `request_id`, or an older version after a newer version.
- **Preconditions:** Gateway is online and staging schedule $V=5$.
- **Stimulus:** Broker delivers duplicate $V=5$, followed by out-of-order $V=4$.
- **Expected Outcome:**
  - Gateway recognizes duplicate $V=5$ by `request_id` and idempotent hash; ignores redundant processing.
  - Gateway rejects $V=4$ with `VERIFY_NACK` (`reason_code = STALE_VERSION`).
- **TX Status:** Active schedule unaffected.
- **Evidence Class:** `INT`
- **Verification Status:** `NOT_RUN`

#### TM-10: Stale Retained MQTT Schedule Handling
- **Description:** An improper publisher puts `retain=true` on `downlink/schedule`. Gateway reboots and reconnects.
- **Preconditions:** Broker holds retained schedule with past `expires_at`.
- **Stimulus:** Gateway connects to broker; receives retained message.
- **Expected Outcome:**
  - Gateway verifies `now >= expires_at`.
  - Gateway rejects message with `VERIFY_NACK` (`reason_code = RETAINED_STALE` or `EXPIRED`).
  - Stored NVS active schedule remains unchanged.
- **TX Status:** Maintained safe state.
- **Evidence Class:** `INT`
- **Verification Status:** `NOT_RUN`

#### TM-11: $3 \to 2 \to 1$ Horizon Partial Announcement Loss (Lost Beacon at $H=2$)
- **Description:** During the 3-superframe staging countdown, RF interference obliterates the Beacon at countdown 2.
- **Preconditions:** Gateway has staged schedule $V=10$ at $K$; broadcasts Beacon at $K$ ($H=3$), Beacon at $K+1$ ($H=2$) is lost, Beacon at $K+2$ ($H=1$) is received.
- **Stimulus:** Node receives Beacon $H=3$ and Beacon $H=1$, missing $H=2$.
- **Expected Outcome:**
  - Because Node received the schedule map at $H=3$ and observed $H=1$ confirming activation at $K+3$, Node safely activates at $K+3$.
  - All 8 guards pass.
- **TX Status:** **Allowed** at $K+3$.
- **Evidence Class:** `SIM` / `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-12: $3 \to 2 \to 1$ Horizon Complete Beacon Loss (Lost Beacons at $H=3, 2, 1$)
- **Description:** Node misses all three announcement Beacons due to severe jamming or deep fade.
- **Preconditions:** Gateway commits schedule $V=10$ at $K+3$.
- **Stimulus:** Superframe $K+3$ begins. Node has missed 3 consecutive Beacons.
- **Expected Outcome:**
  - Node evaluates Guard 5 (Timing & Drift Guard) as FALSE (3 lost beacons).
  - Node evaluates Guard 3 (Authentic Schedule) as FALSE (no knowledge of $V=10$).
  - Node strictly inhibits transmission; enters `RECOVERY_HOLD`.
- **TX Status:** **Strictly Denied**.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-13: Late Schedule Arrival at Gateway Mid-Superframe
- **Description:** Backend emits `downlink/schedule` that arrives at Gateway midway through superframe $K$ (e.g. at $t = 1500\text{ ms}$).
- **Preconditions:** Gateway superframe sequencer is running.
- **Stimulus:** MQTT message parsed at $t = 1500\text{ ms}$ of Subframe 0.
- **Expected Outcome:**
  - Gateway DOES NOT count the current incomplete superframe as an announcement cycle.
  - Gateway sets activation horizon $K_{\text{target}} = K_{\text{now}} + 1 + 3 = K_{\text{now}} + 4$.
  - Exactly 3 full, un-truncated superframes are used for broadcasting.
- **TX Status:** Staged safely; activation deferred to boundary $K+4$.
- **Evidence Class:** `HIL` / `INT`
- **Verification Status:** `NOT_RUN`

---

### Group 4: Hardware Faults, Power Loss & Clock Drift Scenarios

#### TM-14: Node Sudden Reboot in `SESSION_READY_NOT_ACTIVE`
- **Description:** Node suffers brownout or power cut immediately after sending `UP_JOIN_READY`.
- **Preconditions:** Node in `SESSION_READY_NOT_ACTIVE`; RAM keys present. Power dropped.
- **Stimulus:** Node reboots.
- **Expected Outcome:**
  - RAM is cleared. Ephemeral session keys are lost.
  - Node boots in `NODE_UNJOINED` state.
  - Node MUST NOT attempt to use old session; increments `JOIN_COUNTER` and initiates fresh Join.
- **TX Status:** **Denied** until new handshake completes.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-15: Node Sudden Reboot during Active DATA Slot
- **Description:** Node loses power while actively scheduled in Slot #4.
- **Preconditions:** Schedule is live; Node has transmitted multiple DATA frames. Power cycled.
- **Stimulus:** Node powers up midway through an ongoing superframe.
- **Expected Outcome:**
  - Node boots unjoined; does NOT transmit in Slot #4 even if slot time arrives.
  - Gateway detects silence in Slot #4; marks missing telemetry.
- **TX Status:** **Strictly Denied**.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-16: Gateway Sudden Reboot during STAGED Horizon
- **Description:** Gateway suffers power loss while broadcasting countdown ($H=2$).
- **Preconditions:** Gateway holds `SHADOW_SCHEDULE` in NVS. Power cycled.
- **Stimulus:** Gateway boots before $K_{\text{target}}$.
- **Expected Outcome:**
  - Gateway re-initializes; checks RTC. If RTC cannot be verified, Gateway purges shadow schedule.
  - Gateway emits retained status with new `gateway_epoch` UUID.
  - Gateway broadcasts prior active schedule or neutral beacon.
  - Nodes observing missing transition fail closed.
- **TX Status:** **Denied** for newly staged nodes.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-17: Gateway Sudden Reboot with Stored Active Schedule
- **Description:** Gateway boots with an established, validated `ACTIVE_SCHEDULE` in NVS.
- **Preconditions:** NVS contains valid active schedule; no backend connection yet.
- **Stimulus:** Gateway powers up in standalone mode.
- **Expected Outcome:**
  - Gateway validates integrity (CRC/HMAC) of active schedule in NVS.
  - Gateway starts local TDMA sequencer and broadcasts `SYNC_BEACON` with correct active version.
  - Active nodes continue transmitting in assigned slots.
- **TX Status:** **Allowed** for pre-existing active nodes.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-18: Excessive Clock Drift Beyond Leading Guard ($\tau_{\text{drift}} > T_{\text{guard}}$)
- **Description:** Node RTC crystal has severe frequency error (e.g. +100 ppm) or temperature gradient causes clock slip $> 25\text{ ms}$.
- **Preconditions:** Node missed 2 Beacons; drift estimator computes cumulative slip $= 28\text{ ms} > 25\text{ ms}$.
- **Stimulus:** Slot start interrupt fires.
- **Expected Outcome:**
  - Node evaluates Guard 5 (`TIMING_DRIFT_SAFE`) as FALSE.
  - Transmission is blocked to prevent clobbering preceding slot.
- **TX Status:** **Denied**.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-19: SX1276 Half-Duplex Overlap Prevention (TX vs RX Contention)
- **Description:** A firmware task attempts to initiate LoRa TX while SX1276 driver is in RX mode receiving Downlink CTRL or Beacon.
- **Preconditions:** SX1276 SPI owner mutex held by RX driver.
- **Stimulus:** Application layer fires urgent event TX.
- **Expected Outcome:**
  - Radio Owner driver returns `ERR_RADIO_BUSY_HALF_DUPLEX`.
  - Transmission is queued; RF registers are not overwritten; RX is not aborted.
- **TX Status:** **Denied / Deferred**.
- **Evidence Class:** `HIL` / `STATIC`
- **Verification Status:** `NOT_RUN`

---

### Group 5: Contention, Regulatory & Scale Boundaries

#### TM-20: Join / CTRL Contention Window Backoff & Collision
- **Description:** Two nodes transmit candidate `UP_JOIN_READY` simultaneously in the Subframe 4 CTRL window.
- **Preconditions:** Nodes A and B have both validated `DOWN_JOIN_FINISH`.
- **Stimulus:** Both transmit at the exact start of the CTRL window; LoRa packet collision occurs.
- **Expected Outcome:**
  - Gateway fails to decode payload due to CRC error; neither tag is verified.
  - Both nodes timeout on schedule receipt; apply randomized backoff before next attempt.
  - No active DATA slots are impacted.
- **TX Status:** Denied; re-attempt scheduled.
- **Evidence Class:** `SIM` / `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-21: Airtime Budget Exhaustion (1% Node Duty Cycle Denial)
- **Description:** Node generates high-frequency emergency event alerts; rolling 1-hour airtime accumulation reaches $36{,}000\text{ ms}$.
- **Preconditions:** Node has transmitted 360 packets of 100 ms ToA in the past 59 minutes.
- **Stimulus:** Next event arrives for transmission in assigned Slot #3.
- **Expected Outcome:**
  - Node evaluates Guard 7 (`REGULATORY_AIRTIME_BUDGET`) as FALSE.
  - Transmission is blocked; event is appended to durable flash queue.
- **TX Status:** **Strictly Denied**.
- **Evidence Class:** `HIL` / `CONTRACT`
- **Verification Status:** `NOT_RUN`

#### TM-22: Gateway Airtime Budget Exhaustion (10% Gateway Duty Cycle Denial)
- **Description:** Gateway downlink transmissions (Beacons + ACKs + Downlinks) approach 10.0% hourly cap ($360{,}000\text{ ms}$).
- **Preconditions:** Heavy traffic conditions; Gateway airtime accumulator $> 9.9\%$.
- **Stimulus:** Backend issues non-critical downlink command.
- **Expected Outcome:**
  - Gateway drops non-essential downlink; prioritizes `SYNC_BEACON` to preserve TDMA sync.
  - Emits telemetry alert `WARN_GW_AIRTIME_BUDGET`.
- **TX Status:** Non-essential DL Denied; Critical Beacon Preserved.
- **Evidence Class:** `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-23: Multi-Gateway Density Scale (15 Nodes/GW $\times$ 4 Gateways = 60 Nodes)
- **Description:** Network operates at full MVP capacity: 4 Gateways, each serving 15 active nodes across orthogonal RF channels or synchronized superframes.
- **Preconditions:** 60 nodes successfully completed V2 Join and activation.
- **Stimulus:** Continuous 24-hour traffic execution.
- **Expected Outcome:**
  - Zero inter-slot collisions within each Gateway domain.
  - All 60 nodes maintain valid Beacon sync and active leases.
  - Packet delivery ratio $> 98\%$ on nominal channels.
- **TX Status:** **Allowed** per assigned slots.
- **Evidence Class:** `SIM` / `HIL`
- **Verification Status:** `NOT_RUN`

#### TM-24: Lost `DOWN_JOIN_FINISH` on RF
- **Description:** Gateway transmits `DOWN_JOIN_FINISH` (0x48), but packet is lost due to RF attenuation.
- **Preconditions:** Node in `JOIN_AWAIT_FINISH`; Backend in `FINISH_ISSUED_AWAIT_NODE_READY`.
- **Stimulus:** RF packet dropped. Node timeout $T_{\text{finish\_timeout}}$ expires.
- **Expected Outcome:**
  - Node retransmits `UP_JOIN_KEY_CONFIRM` (using same counter and random bytes).
  - Gateway and Backend recognize retransmission of pending transaction; re-issue `DOWN_JOIN_FINISH`.
  - Node does NOT transmit DATA; no phantom slot created.
- **TX Status:** **Denied**.
- **Evidence Class:** `HIL` / `INT`
- **Verification Status:** `NOT_RUN`

#### TM-25: Lost `ACTIVE_REPORT` over MQTT / Network Partition
- **Description:** Gateway promotes schedule at $K_{\text{target}}$ and emits `ACTIVE_REPORT`, but cellular connection drops.
- **Preconditions:** Superframe boundary reached; Gateway local switch occurs; MQTT TCP connection severed.
- **Stimulus:** Internet outage lasts 120 seconds.
- **Expected Outcome:**
  - Gateway buffers `ACTIVE_REPORT` in offline queue with original `gateway_epoch` and `event_seq`.
  - Nodes continue transmitting in assigned slots according to valid local Beacon sync.
  - Upon reconnection, Gateway replays `ACTIVE_REPORT` with `buffered = true`.
  - Backend marks schedule ACTIVE retrospectively; no state desynchronization occurs.
- **TX Status:** **Allowed** on RF; buffered on MQTT.
- **Evidence Class:** `INT` / `HIL`
- **Verification Status:** `NOT_RUN`

---

## 4. Test Execution Ledger & Acceptance Criteria

| Scenario ID | Test Name | Primary Guard | Evidence Class | Interop Impact | Current Status |
|---|---|---|---|---|---|
| **TM-01** | Nominal 100%-READY Handshake | G1..G8 | `HIL` / `INT` | Node $\leftrightarrow$ GW $\leftrightarrow$ BE | `NOT_RUN` |
| **TM-02** | Single Node Missing READY | G6 | `SIM` / `INT` | BE Scheduler | `NOT_RUN` |
| **TM-03** | Tampered Backend Proof | G1, G2 | `SEC` / `CONTRACT` | Node $\leftrightarrow$ BE | `NOT_RUN` |
| **TM-04** | Tampered Gateway Tag | G1 | `HIL` / `SEC` | Node $\leftrightarrow$ GW | `NOT_RUN` |
| **TM-05** | Replayed `UP_JOIN_READY` | G8 | `SEC` / `INT` | Anti-Replay | `NOT_RUN` |
| **TM-06** | Forged Gateway Schedule | G3 | `SEC` / `HIL` | Rogue GW Defense | `NOT_RUN` |
| **TM-07** | Expired Lease Activation | G4 | `INT` / `HIL` | Lease Management | `NOT_RUN` |
| **TM-08** | Stale Session Key Generation | G2, G8 | `SEC` / `INT` | Key Revocation | `NOT_RUN` |
| **TM-09** | Duplicate / Reordered MQTT | G3 | `INT` | GW MQTT Ingest | `NOT_RUN` |
| **TM-10** | Retained Stale MQTT Schedule | G3 | `INT` | Broker Safety | `NOT_RUN` |
| **TM-11** | Partial Horizon Beacon Loss | G3, G5 | `SIM` / `HIL` | Robustness | `NOT_RUN` |
| **TM-12** | Complete Horizon Beacon Loss | G3, G5 | `HIL` | Fail-Closed Safety | `NOT_RUN` |
| **TM-13** | Late Mid-Superframe Schedule | G3 | `HIL` / `INT` | Horizon Guard | `NOT_RUN` |
| **TM-14** | Node Reboot in Ready State | G1, G2 | `HIL` | RAM Key Zeroization | `NOT_RUN` |
| **TM-15** | Node Reboot in Active Slot | G6 | `HIL` | State Cleanup | `NOT_RUN` |
| **TM-16** | GW Reboot in Staging State | G3 | `HIL` | NVS Re-eval | `NOT_RUN` |
| **TM-17** | GW Reboot with Active NVS | G3 | `HIL` | Standalone Run | `NOT_RUN` |
| **TM-18** | Excessive Clock Drift Slip | G5 | `HIL` | Drift Containment | `NOT_RUN` |
| **TM-19** | Half-Duplex TX/RX Contention | G6 | `HIL` / `STATIC` | Driver Mutex | `NOT_RUN` |
| **TM-20** | Join Contention Window Collision | G1 | `SIM` / `HIL` | Backoff Algorithm | `NOT_RUN` |
| **TM-21** | 1% Node Airtime Denial | G7 | `HIL` / `CONTRACT` | Legal Compliance | `NOT_RUN` |
| **TM-22** | 10% GW Airtime Denial | G7 | `HIL` | Legal Compliance | `NOT_RUN` |
| **TM-23** | 60-Node Density Scale | G1..G8 | `SIM` / `HIL` | System Capacity | `NOT_RUN` |
| **TM-24** | Lost `DOWN_JOIN_FINISH` | G1 | `HIL` / `INT` | Handshake Retry | `NOT_RUN` |
| **TM-25** | Lost `ACTIVE_REPORT` MQTT | G3 | `INT` / `HIL` | Network Partition | `NOT_RUN` |

---

## 5. Reviewer Sign-Off & Governance Requirements

Before any test in this matrix can be marked as `PASS`, the following stakeholders must execute formal sign-offs:

1. **RF & Regulatory Lead:** Review Profile `P-10S-15` calculated timings, guard bands (25 ms), turnaround latency (20 ms), and legal duty cycle verification (Vietnam 920-923 MHz band).
2. **Security & Cryptography Lead:** Formally inspect candidate `UP_JOIN_READY` (0x49) HKDF/HMAC transcript bindings, anti-replay high-water mark validation, and forward-secrecy properties.
3. **Firmware & Embedded Systems Lead:** Inspect SX1276 SPI serialized driver, FreeRTOS task priorities, half-duplex state machine, and NVS persistence failure recovery.
4. **Backend & Cloud Lead:** Validate MQTT 5.0 QoS 1 deduplication, Message Expiry, DB transaction locks, and scheduler staging horizons.
5. **Quality Assurance Lead:** Supervise automated HIL and simulation runs, collecting hardware oscilloscope traces and cryptographic test receipts.
