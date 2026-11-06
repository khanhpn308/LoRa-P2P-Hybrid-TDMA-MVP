# LP2P V2 Event DATA & Durable ACK: Negative Verification & Test Matrix

**Document ID:** `DOC-VERIF-V2-EVENT-ACK-002`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent / Tracking:** Issue #177 (Agent 1), Umbrella #125, Child Architecture #126, Integration Gate #127.
**Related Documents:** [Compatibility Review & Protocol Invariants](v2-event-ack-compatibility-review.md), [Acceptance Gates](acceptance-gates.md), [Harness Quality Gates](../development/harness-quality-gates.md), [RF Timing Methodology](rf-timing-methodology-and-harness.md), [Join V2 Test Matrix](join-v2-ready-tdma-activation-test-matrix.md).

---

## 1. Verification Strategy & Evidence Hierarchy

To guarantee deterministic, fault-tolerant, and secure operation of the LP2P V2 Event-Only data plane, this document establishes an exhaustive verification and negative-test matrix. In strict adherence to Owner Decision #137 and `AGENTS.md`, verification must cross multiple independent validation layers rather than relying solely on synthetic or mock fixtures.

### Evidence Classification Hierarchy

| Evidence Class | Acronym | Description | Scope & Execution Environment |
|---|:---:|---|---|
| **Static Code Analysis** | `STATIC` | Clang-tidy, cppcheck, compiler bounds checks, Go linter. | Host CI / Local Toolchain. |
| **Contract & Codec** | `CONTRACT` | Binary serialization, byte offsets, endianness, AAD/tag generation. | Python / Go / C synthetic vectors. |
| **Protocol Simulation** | `SIM` | Discrete-event multi-node TDMA simulation, loss modeling, FIFO state. | Headless protocol runner (SimPy / Go). |
| **Host Integration** | `INT` | End-to-end software integration (Mosquitto + Go Backend + simulated radio). | Local Docker Compose testbed. |
| **Hardware-in-the-Loop** | `HIL` | Real ESP32-WROOM-32E + SX1276 hardware bench under logic analyzer. | Coaxial RF testbed, GPIO triggers. |
| **Physical RF & Airtime**| `RF` | Over-the-air spectrum verification, ToA timing, regulatory duty compliance. | Anechoic / RF lab (#169 sign-off). |
| **Security Audit** | `SEC` | Formal cryptographic audit, side-channel analysis, nonce evaluation. | Independent cryptographer review. |

> [!IMPORTANT]
> In accordance with project policy (Owner Decision #137 and AGENTS.md), **every test scenario in this matrix holds the initial verification status `NOT_RUN`**. Neither document creation, markdown approval, nor synthetic test vectors constitute verification of physical RF behavior or cross-language interoperability.

---

## 2. Test Execution Preconditions & Testbed Setup

All scenarios in this matrix operate under the following baseline configuration:
- **Radio MAC Version:** LP2P V2 Unicast Framing (`0x41` `UP_EVENT`, `0x42` `DOWN_EVENT_ACK`).
- **Cryptographic Suite:** AES-128-CCM with 8-byte authentication tag ($M=8$, $L=2$, $N=13$).
- **Node Hardware:** ESP32-WROOM-32E + Semtech SX1276 connected via SPI, ESP-IDF v6.1, FreeRTOS.
- **Gateway Hardware:** Linux host (or ESP32) + SX1276 radio owner, local SQLite / WAL persistent dedup store.
- **Backend Stack:** Go Modular Monolith, Mosquitto 2.0 MQTT 5.0 broker with TLS/ACL, PostgreSQL 16.
- **RF Parameters:** VN920 Band (920.250–922.750 MHz), $BW = 125\text{ kHz}$, $CR = 4/5$, Preamble = 8 symbols, Explicit Header with Payload CRC.
- **Nominal Profiles:** Spreading Factor 7 (SF7, $T_{slot} = 400\text{ ms}$, $T_{RT} = 183.152\text{ ms}$) and Spreading Factor 8 (SF8, $T_{slot} = 400\text{ ms}$, $T_{RT} = 286.064\text{ ms}$).

---

## 3. Comprehensive Verification Matrix (28 Scenarios)

### Group 1: Nominal Event Transmission & Durable In-Slot ACK

#### TM-EVT-01: Nominal Single Event In-Slot Happy Path
- **Description:** Verifies that an unacknowledged event in the Node's FIFO is transmitted during its assigned static DATA slot, durably accepted by the Gateway, acknowledged in-slot via `DOWN_EVENT_ACK`, and committed (popped) from the Node's FIFO.
- **Required Fixture:** Single Node (Node ID 7) + Gateway (GW ID 2) + Mosquitto broker + Go Backend.
- **Assumed Candidate Version:** Radio MAC V2 (`UP_EVENT` 0x41 26B, `DOWN_EVENT_ACK` 0x42 19B).
- **Preconditions:** Node has completed V2 Join and TDMA activation (`NODE_ACTIVE_DATA_ELIGIBLE`); assigned Slot #7 in active schedule $V=10$; session keys $K_{SESSION\_UP}$ and $K_{SESSION\_DOWN}$ active; `FRAME_COUNTER = 1`.
- **Stimulus:**
  1. Sensor violation occurs on Node; Node actuates local alarm immediately and commits event (`EVENT_REF = 101`, `EVENT_CODE = 0x01`, `EVENT_VALUE = 250`) to NVS FIFO.
  2. TDMA scheduler triggers at Slot #7 start boundary; Node evaluates 8-fold DATA TX guards (all PASS).
  3. Node transmits `UP_EVENT` (26B, `FRAME_COUNTER = 1`).
  4. Gateway SX1276 receives frame, verifies CCM-8 tag, persists event to local WAL, mints `event_id`, enqueues MQTT publish, and transmits `DOWN_EVENT_ACK` (19B, `EVENT_REF = 101`, `FRAME_COUNTER = 1`) within 20 ms turnaround window.
  5. Node SX1276 receives ACK, validates CCM-8 tag and matching `EVENT_REF = 101`.
- **Expected Outcome:**
  - Gateway publishes single event to Backend MQTT topic `iot/v1/gw/02/uplink/event`.
  - Node pops record 101 from FIFO head; FIFO pending count transitions from 1 to 0.
  - Node radio enters low-power standby before trailing guard expired.
- **Expected Accept / Drop / State:** `EVENT_ACCEPTED` / `ACK_COMMITTED` / `FIFO_EMPTY`.
- **Owner of Implementation:** Node Firmware (#131) + Gateway Radio (#131) + Backend Ingest (#132).
- **Test Layer:** `HIL` / `INT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-02: Sequential Multi-Event Transmission Across Superframes
- **Description:** Verifies that multiple sensor events accumulated in FIFO are transmitted sequentially—exactly one event per superframe assigned static slot.
- **Required Fixture:** Node 7 + Gateway 2 + Mosquitto + Backend.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node active in Slot #7. 3 events queued in FIFO (`EVENT_REF = 101, 102, 103`).
- **Stimulus:**
  1. Superframe $K$: Node transmits `EVENT_REF = 101`, receives ACK, pops 101.
  2. Superframe $K+1$: Node transmits `EVENT_REF = 102`, receives ACK, pops 102.
  3. Superframe $K+2$: Node transmits `EVENT_REF = 103`, receives ACK, pops 103.
- **Expected Outcome:**
  - Exactly 3 events published to Backend with distinct `event_id` and monotonic `FRAME_COUNTER` (1, 2, 3).
  - Node does NOT attempt multi-packet burst within a single 400 ms slot.
- **Expected Accept / Drop / State:** `SEQUENTIAL_ACCEPTED` / `FIFO_DRAINED`.
- **Owner of Implementation:** Node Firmware (#131) + Gateway Radio (#131).
- **Test Layer:** `SIM` / `INT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-03: Event Payload Boundary Values (Min/Max/Signed)
- **Description:** Verifies encryption, transmission, and backend parsing of boundary values for `EVENT_VALUE` (`-32768`, `0`, `+32767`) and application codes (`0x00`..`0xFF`).
- **Required Fixture:** Node + Gateway + Python codec validator.
- **Assumed Candidate Version:** Radio MAC V2 (26B).
- **Preconditions:** Active session; synthetic payload generator.
- **Stimulus:** Generate `UP_EVENT` frames with boundary values: $V_{min} = -32768$, $V_{zero} = 0$, $V_{max} = 32767$, $CODE = 0xFF$.
- **Expected Outcome:**
  - AES-CCM-8 encryption/decryption preserves sign and magnitude without integer truncation.
  - Gateway JSON serialization outputs raw signed integer without floating-point distortion.
- **Expected Accept / Drop / State:** `PARSE_SUCCESS` / `INTEGRITY_VERIFIED`.
- **Owner of Implementation:** Radio MAC Codec (#128) + Backend Ingest (#132).
- **Test Layer:** `CONTRACT` / `STATIC`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-04: Unsynchronized Clock Sentinel (`0xFFFFFFFF`)
- **Description:** Verifies behavior when an event occurs prior to clock synchronization, confirming sentinel `EVENT_TIME = 0xFFFFFFFF` is preserved and Backend populates `observed_at` using Gateway time.
- **Required Fixture:** Node + Gateway + Backend.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node has lost Beacon sync or has uninitialized RTC clock.
- **Stimulus:** Event fires; Node encodes `EVENT_TIME = 0xFFFFFFFF` in `UP_EVENT`.
- **Expected Outcome:**
  - Node successfully transmits frame.
  - Gateway recognizes sentinel `0xFFFFFFFF`, sets MQTT field `observed_time_source = "gateway_monotonic"`, and populates `observed_at` from trusted Gateway UTC.
- **Expected Accept / Drop / State:** `ACCEPTED_WITH_SENTINEL`.
- **Owner of Implementation:** Node Firmware (#131) + Backend Ingest (#132).
- **Test Layer:** `INT` / `CONTRACT`
- **Evidence Status:** `NOT_RUN`

---

### Group 2: Retransmission, Loss & Deduplication

#### TM-EVT-05: Uplink `UP_EVENT` Lost on RF Path
- **Description:** Verifies that when an uplink `UP_EVENT` is lost in transit due to RF attenuation, the Node does not receive an ACK, preserves the event in FIFO, and retries in its next assigned slot.
- **Required Fixture:** Node 7 + Gateway 2 + RF attenuator (set to -120 dBm during transmission).
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node active in Slot #7; 1 event queued (`EVENT_REF = 101`).
- **Stimulus:**
  1. Superframe $K$: Node transmits `UP_EVENT(ref=101)`. Packet is dropped by attenuator.
  2. Node opens RX window at $t = \tau_{turnaround}$; timeout expires with no ACK received.
  3. Superframe $K+1$: Node awakens at Slot #7 and retransmits `UP_EVENT(ref=101)`. Attenuator disabled.
  4. Gateway receives frame, persists, and transmits `DOWN_EVENT_ACK`.
- **Expected Outcome:**
  - Node increments `retry_count` from 0 to 1 after Superframe $K$.
  - Node DOES NOT transmit in Subframes 1..4 or in peers' slots.
  - Event 101 is accepted on Superframe $K+1$ and popped from FIFO.
- **Expected Accept / Drop / State:** `RETRY_SUCCESS_IN_OWN_SLOT`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL` / `SIM`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-06: Downlink `DOWN_EVENT_ACK` Lost on RF Path (Gateway Idempotent Dedup)
- **Description:** Verifies that when a Gateway receives and commits `UP_EVENT`, but the returned `DOWN_EVENT_ACK` is lost on RF, the Node's subsequent retransmission triggers an idempotent ACK without duplicate MQTT publication.
- **Required Fixture:** Node 7 + Gateway 2 + MQTT logger + Downlink RF drop filter.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node active in Slot #7; Gateway WAL initialized.
- **Stimulus:**
  1. Superframe $K$: Node transmits `UP_EVENT(ref=101)`.
  2. Gateway receives frame, persists to WAL, mints `event_id = "gw02:uuid:1"`, and transmits `DOWN_EVENT_ACK(ref=101)`.
  3. Downlink ACK is suppressed by test filter.
  4. Node timeout expires; event 101 retained in FIFO with `retry_count = 1`.
  5. Superframe $K+1$: Node retransmits `UP_EVENT(ref=101)`.
  6. Gateway receives retransmitted frame.
- **Expected Outcome:**
  - Gateway queries `gateway_event_dedup`, detects existing entry `(node=7, sess=1, ref=101)`.
  - Gateway **DOES NOT** mint a second `event_id` and **DOES NOT** publish a second message to MQTT.
  - Gateway immediately re-transmits `DOWN_EVENT_ACK(ref=101)`.
  - Node receives ACK and pops 101 from FIFO.
  - Total MQTT events received by Backend: exactly 1.
- **Expected Accept / Drop / State:** `IDEMPOTENT_DEDUP_ACK_EMITTED` / `ZERO_DUPLICATE_MQTT`.
- **Owner of Implementation:** Gateway Radio Host (#131) + Gateway Storage (#131).
- **Test Layer:** `INT` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-07: Corrupted / Bit-Flipped `DOWN_EVENT_ACK`
- **Description:** Verifies that an ACK corrupted by RF noise is rejected by the Node's CCM-8 integrity verification and treated as a lost ACK.
- **Required Fixture:** Node + Gateway + RF bit-error injector.
- **Assumed Candidate Version:** Radio MAC V2 (19B).
- **Preconditions:** Node awaiting ACK in Slot #7.
- **Stimulus:** Gateway transmits `DOWN_EVENT_ACK`; injector flips bit 12 (inside ciphertext).
- **Expected Outcome:**
  - Node AES-CCM-8 decryption fails tag verification.
  - Node increments `err_rx_tag_fail`, discards corrupted frame, and retains event in FIFO.
  - Node retransmits in next superframe.
- **Expected Accept / Drop / State:** `ACK_TAG_FAIL` / `DISCARDED` / `RETRY_QUEUED`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL` / `CONTRACT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-08: Retry Budget Exhaustion (`MAX_RETRIES` Reached)
- **Description:** Verifies that a Node experiencing persistent RF failure halts transmission after reaching $N_{max\_retries} = 5$, transitioning the event to `RECOVERY_HOLD` without dropping data.
- **Required Fixture:** Node with disconnected antenna / permanent RF block.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** 1 event in FIFO; $N_{max\_retries} = 5$.
- **Stimulus:** Node attempts transmission across 5 successive superframes; all ACKs fail.
- **Expected Outcome:**
  - For attempts 1..5: `retry_count` increments $1 \to 5$.
  - At attempt 5: Event transitions to `STATE_RECOVERY_HOLD`.
  - Superframe 6: Node evaluates guard, notes `RECOVERY_HOLD`, and **INHIBITS RF TX**.
  - Event remains durably in NVS FIFO; airtime is conserved.
- **Expected Accept / Drop / State:** `RETRY_EXHAUSTED` / `TX_HALTED` / `FIFO_PRESERVED`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `SIM` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-09: Late / Out-of-Window ACK Reception
- **Description:** Verifies that if an ACK arrives after the slot trailing guard boundary has elapsed, the Node radio is already in standby/sleep and does not process the packet.
- **Required Fixture:** Node + Delayed Gateway ACK simulator.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Slot duration 400 ms. Trailing guard expires at $t = 375\text{ ms}$.
- **Stimulus:** Gateway delays ACK transmission until $t = 390\text{ ms}$.
- **Expected Outcome:**
  - Node radio timer has already triggered `STANDBY` at $t = 375\text{ ms}$.
  - Node SX1276 ignores incoming RF energy; event is scheduled for retry in next superframe.
- **Expected Accept / Drop / State:** `WINDOW_EXPIRED` / `IGNORED`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL`
- **Evidence Status:** `NOT_RUN`

---

### Group 3: Cryptographic Integrity, Tampering & Replay Negative Scenarios

#### TM-EVT-10: Tampered Ciphertext in `UP_EVENT`
- **Description:** Verifies that single-bit tampering in the encrypted payload of `UP_EVENT` (bytes 7..17) causes CCM-8 tag verification failure at the Gateway.
- **Required Fixture:** Gateway Radio Host + Synthetic RF injector.
- **Assumed Candidate Version:** Radio MAC V2 (26B).
- **Preconditions:** Valid session established; Gateway listening in Slot #7.
- **Stimulus:** Inject valid `UP_EVENT` frame with bit 9 flipped (`EVENT_REF` altered from 101 to 103).
- **Expected Outcome:**
  - Gateway AES-CCM-8 decryption fails constant-time tag verification.
  - Gateway drops packet immediately; logs `ERR_CCM_TAG_MISMATCH`.
  - No database entry created; no ACK transmitted; no MQTT message published.
- **Expected Accept / Drop / State:** `DROP_CORRUPTED` / `ZERO_SIDE_EFFECT`.
- **Owner of Implementation:** Gateway Radio Host (#131).
- **Test Layer:** `CONTRACT` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-11: Tampered AAD / Unicast Header in `UP_EVENT`
- **Description:** Verifies that tampering with unencrypted header fields (`NODE_ID`, `SESSION_SEL`, `FRAME_COUNTER`) is detected because the header is authenticated as AAD.
- **Required Fixture:** Gateway Radio Host + Python codec test.
- **Assumed Candidate Version:** Radio MAC V2 (26B).
- **Preconditions:** Valid frame generated.
- **Stimulus:** Flip bit in Byte 1 (`NODE_ID` altered from 7 to 8) while leaving ciphertext and tag untouched.
- **Expected Outcome:**
  - AAD input to CBC-MAC changes; computed tag differs from received tag.
  - Gateway drops packet; logs `ERR_AAD_AUTH_FAIL`.
- **Expected Accept / Drop / State:** `DROP_TAMPERED_AAD`.
- **Owner of Implementation:** Radio MAC Codec (#128) + Gateway Radio (#131).
- **Test Layer:** `CONTRACT` / `STATIC`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-12: Replayed `UP_EVENT` with Stale Frame Counter
- **Description:** Verifies that an attacker sniffing a valid `UP_EVENT` and replaying it at a later time is rejected by the Gateway's monotonic frame counter filter.
- **Required Fixture:** Gateway + RF sniffer / replay injector.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node has successfully transmitted frame with `FRAME_COUNTER = 10`. Gateway high-water mark for Node 7 is `10`.
- **Stimulus:** Inject replayed frame from earlier session with `FRAME_COUNTER = 5`.
- **Expected Outcome:**
  - Gateway evaluates `FRAME_COUNTER <= last_seen_counter` ($5 \le 10$).
  - Gateway drops frame as duplicate/replay; logs `ERR_REPLAY_FRAME_COUNTER`.
  - No ACK emitted; no MQTT publish.
- **Expected Accept / Drop / State:** `DROP_REPLAY`.
- **Owner of Implementation:** Gateway Radio Host (#131).
- **Test Layer:** `INT` / `SEC`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-13: Replayed `DOWN_EVENT_ACK` Injection
- **Description:** Verifies that an attacker capturing a historical `DOWN_EVENT_ACK` and injecting it during a different transaction cannot trick the Node into prematurely popping an unconfirmed event.
- **Required Fixture:** Node + RF replay injector.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node has pending event `EVENT_REF = 205`. Historical ACK captured for `EVENT_REF = 101`.
- **Stimulus:** Inject historical ACK (`EVENT_REF = 101`) into Node's slot.
- **Expected Outcome:**
  - Node decrypts ACK and inspects `EVENT_REF`.
  - Reference mismatch ($101 \ne 205$); Node drops ACK.
  - Event 205 remains in FIFO head; retry executes as scheduled.
- **Expected Accept / Drop / State:** `DROP_MISMATCHED_ACK`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL` / `SEC`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-14: Frame Counter Rollback / Tamper Attempt
- **Description:** Verifies that if an attacker attempts to reset or decrement the `FRAME_COUNTER` under the same active session key, the transmission is fail-closed.
- **Required Fixture:** Synthetic test vector generator + Gateway validator.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Active session; high-water mark = 100.
- **Stimulus:** Transmit frame with `FRAME_COUNTER = 99`.
- **Expected Outcome:** Gateway rejects frame; counter rollback strictly denied.
- **Expected Accept / Drop / State:** `DROP_COUNTER_ROLLBACK`.
- **Owner of Implementation:** Gateway Radio Host (#131).
- **Test Layer:** `CONTRACT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-15: Frame Counter Exhaustion (`0xFFFFFFFE` Boundary)
- **Description:** Verifies that when `FRAME_COUNTER` reaches saturation, the Node inhibits further transmission, zeroizes session keys, and forces a complete re-join.
- **Required Fixture:** Node firmware bench with mocked counter.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node `FRAME_COUNTER = 0xFFFFFFFE`. 1 event in FIFO.
- **Stimulus:** TDMA slot fires; Node evaluates `GUARD_SESSION_VALID`.
- **Expected Outcome:**
  - Guard evaluates to `FALSE` due to counter saturation.
  - Radio TX is inhibited (`FAIL_CLOSED`).
  - Node zeroizes $K_{SESSION\_UP}$ and $K_{SESSION\_DOWN}$, transitions to `NODE_UNJOINED`, and initiates V2 Join handshake.
- **Expected Accept / Drop / State:** `FAIL_CLOSED_SATURATION` / `SESSION_PURGED` / `FORCE_REJOIN`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL` / `INT`
- **Evidence Status:** `NOT_RUN`

---

### Group 4: Session Rekey, Reboot & State Invariants

#### TM-EVT-16: Node Reboot with Pending FIFO Events
- **Description:** Verifies that after an abrupt power cut / reset, pending FIFO events are preserved in NVS, and upon completing a fresh V2 Join and schedule activation, the pending events are transmitted cleanly under the new session key.
- **Required Fixture:** Node with switched power supply + Gateway + Backend.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node has 2 events in NVS FIFO (`EVENT_REF = 50, 51`). Session 1 active.
- **Stimulus:**
  1. Trigger hardware reset line on ESP32 Node.
  2. Node reboots; volatile RAM zeroized; reads NVS FIFO and discovers 2 pending records.
  3. Node executes V2 Join handshake with Gateway/Backend $\to$ receives new `SESSION_SEL = 2`, new session keys, and TDMA schedule allocation.
  4. Node transitions to `NODE_ACTIVE_DATA_ELIGIBLE`.
  5. In assigned slot, Node transmits `UP_EVENT(ref=50)` using `SESSION_SEL = 2` and `FRAME_COUNTER = 1`.
- **Expected Outcome:**
  - Gateway accepts event under Session 2; mints `event_id`.
  - Node receives `DOWN_EVENT_ACK`, pops 50, and transmits 51 in the following superframe.
  - Zero events lost across reboot.
- **Expected Accept / Drop / State:** `REBOOT_RECOVERY_SUCCESS` / `ZERO_DATA_LOSS`.
- **Owner of Implementation:** Node Firmware (#131) + Gateway Radio (#131).
- **Test Layer:** `HIL` / `INT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-17: Gateway Crash During Durable WAL Acceptance
- **Description:** Verifies that if the Gateway crashes or loses power after receiving `UP_EVENT` but BEFORE the WAL transaction is committed, the event is safely recovered via Node retransmission upon Gateway reboot.
- **Required Fixture:** Gateway test host with power-cut relay + Node.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node transmits `UP_EVENT(ref=101)`.
- **Stimulus:** Gateway radio triggers crash/power-off immediately before SQLite WAL commit. No ACK sent. Gateway reboots. Node retries in next superframe.
- **Expected Outcome:**
  - Uncommitted WAL transaction is rolled back on Gateway startup.
  - Node retransmission in next superframe finds no prior dedup entry; accepted as fresh event.
  - Event committed to WAL; ACK returned; event published to MQTT.
- **Expected Accept / Drop / State:** `CRASH_RECOVERY_ACCEPTED`.
- **Owner of Implementation:** Gateway Storage & Radio (#131).
- **Test Layer:** `INT` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-18: Gateway Crash After WAL Commit But Before ACK Dispatch
- **Description:** Verifies that if the Gateway commits the event to WAL but crashes before RF ACK transmission, the Node's subsequent retry is idempotently acknowledged from the recovered WAL dedup table.
- **Required Fixture:** Gateway test host with programmable crash injection + Node.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node transmits `UP_EVENT(ref=101)`.
- **Stimulus:** Gateway commits to WAL, enqueues MQTT publish, then crashes before SX1276 transmits `DOWN_EVENT_ACK`. Gateway reboots. Node retries.
- **Expected Outcome:**
  - Gateway recovers SQLite WAL on startup; dedup record exists.
  - Node retransmission hits dedup map; Gateway resends ACK without duplicating MQTT publish.
  - Node pops 101 from FIFO.
- **Expected Accept / Drop / State:** `WAL_RECOVERED_DEDUP_ACK`.
- **Owner of Implementation:** Gateway Storage & Radio (#131).
- **Test Layer:** `INT`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-19: Cross-Session Transmission Rejection
- **Description:** Verifies that if a Node attempts transmission using an invalidated session selector (`SESSION_SEL = 1`) after the Gateway has rotated to `SESSION_SEL = 2`, the Gateway rejects the packet.
- **Required Fixture:** Gateway + Synthetic packet injector.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Gateway has retired Session 1.
- **Stimulus:** Transmit `UP_EVENT` with `SESSION_SEL = 1`.
- **Expected Outcome:**
  - Gateway detects unrecognized / expired `SESSION_SEL`.
  - Gateway drops packet; logs `ERR_EXPIRED_SESSION`.
- **Expected Accept / Drop / State:** `DROP_EXPIRED_SESSION`.
- **Owner of Implementation:** Gateway Radio Host (#131).
- **Test Layer:** `CONTRACT` / `SIM`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-20: Wrong Gateway Destination Rejection
- **Description:** Verifies that if a Node transmits an event targeting Gateway A, but the packet is received by Gateway B (e.g. cross-channel bleed or co-channel interference), Gateway B drops the frame.
- **Required Fixture:** Gateway B + Synthetic frame encoded with Gateway A's session keys.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Gateway B lacks Gateway A's session keys.
- **Stimulus:** Inject frame into Gateway B's receiver.
- **Expected Outcome:**
  - Decryption fails CCM-8 tag check on Gateway B.
  - Gateway B drops packet immediately; zero side-effects.
- **Expected Accept / Drop / State:** `DROP_WRONG_GATEWAY`.
- **Owner of Implementation:** Gateway Radio Host (#131).
- **Test Layer:** `INT`
- **Evidence Status:** `NOT_RUN`

---

### Group 5: TDMA Slot Ownership & Half-Duplex RF Guards

#### TM-EVT-21: Transmission Outside Assigned Slot (Guard 3 Failure)
- **Description:** Verifies that the Node's fail-closed guard inhibits transmission if the firmware attempts to trigger `UP_EVENT` outside its assigned static DATA slot.
- **Required Fixture:** Node firmware test harness.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node assigned Slot #7 (time offset 3450..3850 ms).
- **Stimulus:** Firmware timer erroneously attempts to trigger TX during Slot #3 (time offset 1450 ms).
- **Expected Outcome:**
  - Node evaluates `GUARD_SLOT_OWNERSHIP`: `slot_map[3] != local_node_id`.
  - Guard returns `FALSE`; radio remains in STANDBY; logs `ERR_GUARD_UNASSIGNED_SLOT`.
- **Expected Accept / Drop / State:** `TX_INHIBITED_SLOT_MISMATCH`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL` / `STATIC`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-22: Transmission During Maintenance Superframe Boundary
- **Description:** Verifies that during the Maintenance Superframe (~300s sync cadence), all DATA slot transmissions are inhibited.
- **Required Fixture:** Node + TDMA Scheduler simulator.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Active schedule transitions to Maintenance Superframe.
- **Stimulus:** Sensor event queued; slot timer reaches DATA slot offset.
- **Expected Outcome:**
  - Node evaluates `GUARD_HALF_DUPLEX` and `GUARD_SLOT_OWNERSHIP`: Maintenance superframe contains no active DATA slots.
  - TX is strictly inhibited; radio listens for `DOWN_SYNC_BEACON` (0x43).
- **Expected Accept / Drop / State:** `TX_INHIBITED_MAINTENANCE_SF`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `SIM` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-23: Transmission with Stale Schedule Version
- **Description:** Verifies that if the Node misses a schedule change announcement and the Beacon broadcasts a newer schedule version, the Node inhibits transmission.
- **Required Fixture:** Node + Gateway Beacon injector.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node operating on schedule version $V=10$.
- **Stimulus:** Gateway Beacon broadcasts active schedule version $V=11$. Node has not staged $V=11$.
- **Expected Outcome:**
  - Node detects schedule mismatch ($10 \ne 11$).
  - Node sets `schedule_valid = FALSE`, evaluates `GUARD_SLOT_OWNERSHIP` as `FALSE`.
  - Node inhibits DATA TX; transitions to `NODE_RECOVERY_HOLD`.
- **Expected Accept / Drop / State:** `TX_INHIBITED_STALE_SCHEDULE`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `SIM` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-24: Half-Duplex Radio Driver Collisions
- **Description:** Verifies that if the SX1276 transceiver is actively receiving a frame (e.g. background interference or late packet) when the slot TX timer fires, the driver aborts TX to avoid corrupting the SPI/FIFO state.
- **Required Fixture:** Node + RF continuous-wave / packet jammer.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Slot TX timer about to trigger.
- **Stimulus:** Inject RF packet so SX1276 enters `RX` with `RxOngoing = TRUE`.
- **Expected Outcome:**
  - Driver evaluates `GUARD_HALF_DUPLEX`: detects active RX.
  - Driver aborts transmission; logs `ERR_GUARD_HALF_DUPLEX_COLLISION`.
  - Radio returns to clean STANDBY.
- **Expected Accept / Drop / State:** `TX_ABORTED_HALF_DUPLEX`.
- **Owner of Implementation:** SX1276 Driver (#10) + Node Firmware (#131).
- **Test Layer:** `HIL`
- **Evidence Status:** `NOT_RUN`

---

### Group 6: Bounded FIFO Queue & Buffer Overflow Management

#### TM-EVT-25: Bounded FIFO Queue Saturation Under Prolonged Outage
- **Description:** Verifies that when an extended network outage occurs and 64 events accumulate in FIFO, new events are handled deterministically without memory corruption or crash.
- **Required Fixture:** Node firmware bench.
- **Assumed Candidate Version:** Radio MAC V2 ($N_{max} = 64$).
- **Preconditions:** Gateway disconnected; Node FIFO empty.
- **Stimulus:** Inject 70 consecutive sensor violation events.
- **Expected Outcome:**
  - Events 1..64 are committed to NVS FIFO with monotonic references $1..64$.
  - Events 65..70 trigger `ERR_FIFO_OVERFLOW`.
  - Under default fail-closed policy, new events are rejected; local alarms actuate; existing 64 records are preserved without heap exhaustion.
- **Expected Accept / Drop / State:** `FIFO_FULL_FAIL_CLOSED` / `ZERO_MEMORY_LEAK`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `STATIC` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-26: Concurrent Multi-Sensor Event Burst
- **Description:** Verifies that if multiple sensor interrupts (door open, tamper, vibration) fire within a 5 ms window, the Node's FIFO serializes them correctly with strictly increasing `EVENT_REF`.
- **Required Fixture:** Node with multi-GPIO test jig.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Node idle; interrupts enabled.
- **Stimulus:** Assert GPIO14 (tamper), GPIO27 (door), and GPIO32 (vibration) simultaneously.
- **Expected Outcome:**
  - ISRs post events to FreeRTOS queue without blocking or SPI contention.
  - NVS worker thread serializes commits: `EVENT_REF = 101, 102, 103`.
  - No race condition; FIFO integrity verified.
- **Expected Accept / Drop / State:** `SERIALIZATION_SUCCESS`.
- **Owner of Implementation:** Node Firmware (#131).
- **Test Layer:** `HIL`
- **Evidence Status:** `NOT_RUN`

---

### Group 7: Physical Timing, Clock Drift & Airtime Duty Cycle

#### TM-EVT-27: Cumulative Clock Drift Exceeding Guard Window
- **Description:** Verifies that when 3 consecutive Beacons are missed and cumulative crystal drift exceeds the 25 ms guard budget, the Node inhibits transmission to prevent slot overlap.
- **Required Fixture:** Node with mocked crystal offset (±50 ppm) + Beacon suppressor.
- **Assumed Candidate Version:** Radio MAC V2.
- **Preconditions:** Guard window $\tau_{guard} = 25\text{ ms}$.
- **Stimulus:** Suppress 3 consecutive Beacons ($3 \times 10\text{ s} = 30\text{ s}$). Cumulative drift reaches $30\text{ ms}$.
- **Expected Outcome:**
  - Node evaluates `GUARD_CLOCK_SYNC`: detects $N_{lost} \ge 3$ and $\tau_{drift} > \tau_{guard}$.
  - Guard returns `FALSE`; DATA TX is inhibited.
  - Node transitions to `NODE_RECOVERY_HOLD`.
- **Expected Accept / Drop / State:** `TX_INHIBITED_DRIFT_EXCEEDED`.
- **Owner of Implementation:** Node Firmware (#131) + RF Timing (#11/#169).
- **Test Layer:** `SIM` / `HIL`
- **Evidence Status:** `NOT_RUN`

#### TM-EVT-28: Airtime Duty Cycle Budget Depletion
- **Description:** Verifies that excessive retransmissions cannot violate the regulatory 1.0% Node duty cycle cap, with transmission blocked once the token bucket is exhausted.
- **Required Fixture:** Node firmware bench with token-bucket airtime tracker.
- **Assumed Candidate Version:** Radio MAC V2 (SF7 ToA = 61.696 ms).
- **Preconditions:** Token bucket capacity = 36,000 ms/hour (1.0% duty cycle). Mocked high burst of retransmissions.
- **Stimulus:** Node attempts retransmissions until remaining airtime tokens $< 61.696\text{ ms}$.
- **Expected Outcome:**
  - Node evaluates `GUARD_AIRTIME_DUTY`: detects insufficient tokens.
  - Guard returns `FALSE`; transmission is blocked; logs `ERR_GUARD_AIRTIME_EXHAUSTED`.
  - Node waits for token accumulation before next attempt.
- **Expected Accept / Drop / State:** `TX_BLOCKED_DUTY_LIMIT`.
- **Owner of Implementation:** Node Firmware (#131) + Airtime Policy (#179).
- **Test Layer:** `STATIC` / `HIL`
- **Evidence Status:** `NOT_RUN`

---

## 4. Summary & Verification Traceability Matrix

| Scenario ID | Test Name | Primary Layer | Primary Component | Invariant / Guard Tested | Verification Status |
|:---:|---|:---:|:---:|---|:---:|
| **TM-EVT-01** | Nominal Single Event Happy Path | `HIL` / `INT` | Node / GW / Backend | In-Slot ACK, FIFO Pop, MQTT Emit | `NOT_RUN` |
| **TM-EVT-02** | Sequential Multi-Event Processing | `SIM` / `INT` | Node Firmware | One Event per SF, No Bursting | `NOT_RUN` |
| **TM-EVT-03** | Event Payload Boundary Values | `CONTRACT` | Radio MAC Codec | Sign & Value Preservation | `NOT_RUN` |
| **TM-EVT-04** | Unsynchronized Clock Sentinel | `INT` | Gateway / Backend | Sentinel `0xFFFFFFFF` Provenance | `NOT_RUN` |
| **TM-EVT-05** | Uplink Lost on RF Path | `HIL` / `SIM` | Node Firmware | Own-Slot Retry, No PCSS Backoff | `NOT_RUN` |
| **TM-EVT-06** | Downlink ACK Lost on RF Path | `INT` / `HIL` | Gateway Radio / Store| Durable Dedup, Zero MQTT Dups | `NOT_RUN` |
| **TM-EVT-07** | Corrupted / Bit-Flipped ACK | `HIL` / `CONTRACT`| Node Firmware | CCM-8 Tag Validation Failure | `NOT_RUN` |
| **TM-EVT-08** | Retry Budget Exhaustion | `SIM` / `HIL` | Node Firmware | `MAX_RETRIES` Hold, No Flooding | `NOT_RUN` |
| **TM-EVT-09** | Out-of-Window ACK Reception | `HIL` | Node Firmware | Slot Trailing Guard Standby | `NOT_RUN` |
| **TM-EVT-10** | Tampered Ciphertext in Event | `CONTRACT` / `HIL`| Gateway Radio | AES-CCM-8 Tag Failure Drop | `NOT_RUN` |
| **TM-EVT-11** | Tampered AAD / Header in Event | `CONTRACT` | Radio MAC Codec | AAD Mismatch Drop | `NOT_RUN` |
| **TM-EVT-12** | Replayed Event with Stale Counter | `INT` / `SEC` | Gateway Radio | Monotonic High-Water Replay Drop | `NOT_RUN` |
| **TM-EVT-13** | Replayed ACK Injection | `HIL` / `SEC` | Node Firmware | Mismatched `EVENT_REF` Drop | `NOT_RUN` |
| **TM-EVT-14** | Frame Counter Rollback Attempt | `CONTRACT` | Gateway Radio | Counter Decrement Fail-Closed | `NOT_RUN` |
| **TM-EVT-15** | Frame Counter Exhaustion | `HIL` / `INT` | Node Firmware | Fail-Closed Saturation, Re-Join | `NOT_RUN` |
| **TM-EVT-16** | Node Reboot with Pending FIFO | `HIL` / `INT` | Node Firmware | NVS Retention, Re-Join & Send | `NOT_RUN` |
| **TM-EVT-17** | Gateway Crash Before WAL Commit | `INT` / `HIL` | Gateway Storage | Rollback on Boot, Retry Accept | `NOT_RUN` |
| **TM-EVT-18** | Gateway Crash After WAL Commit | `INT` | Gateway Storage | Dedup Recovery, Idempotent ACK | `NOT_RUN` |
| **TM-EVT-19** | Cross-Session Transmission | `CONTRACT` / `SIM`| Gateway Radio | Expired `SESSION_SEL` Drop | `NOT_RUN` |
| **TM-EVT-20** | Wrong Gateway Destination | `INT` | Gateway Radio | Key Mismatch Decryption Drop | `NOT_RUN` |
| **TM-EVT-21** | Transmission Outside Assigned Slot| `HIL` / `STATIC` | Node Firmware | `GUARD_SLOT_OWNERSHIP` Inhibit | `NOT_RUN` |
| **TM-EVT-22** | Transmission During Maintenance SF| `SIM` / `HIL` | Node Firmware | Maintenance Window Inhibit | `NOT_RUN` |
| **TM-EVT-23** | Stale Schedule Version | `SIM` / `HIL` | Node Firmware | Schedule Mismatch Inhibit | `NOT_RUN` |
| **TM-EVT-24** | Half-Duplex Radio Collision | `HIL` | SX1276 Driver | `RxOngoing` Abort | `NOT_RUN` |
| **TM-EVT-25** | Bounded FIFO Saturation | `STATIC` / `HIL` | Node Firmware | Fail-Closed Retention, Overflow Log| `NOT_RUN` |
| **TM-EVT-26** | Multi-Sensor Interrupt Burst | `HIL` | Node Firmware | FreeRTOS Queue Serialization | `NOT_RUN` |
| **TM-EVT-27** | Cumulative Clock Drift Exceeded | `SIM` / `HIL` | Node Firmware / RF | Drift $> 25\text{ ms}$ Inhibit | `NOT_RUN` |
| **TM-EVT-28** | Airtime Budget Depletion | `STATIC` / `HIL` | Airtime Policy (#179)| 1.0% Duty Cycle Token Block | `NOT_RUN` |
