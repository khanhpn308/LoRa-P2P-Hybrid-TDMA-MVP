# LP2P V2 Join, Session Key & READY Security Test Matrix

**Document ID:** `DOC-VERIF-V2-JOIN-CRYPTO-TEST-001`  
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`  
**Parent Tracking:** Issue #182 (Agent 3 Work Package), Parent Issue #127 (Migration Integration Gate), Umbrella Issue #125, Architecture Child Issue #126.  
**Companion Dossier:** [V2 Join & Session Key Compatibility Decisions](v2-join-session-key-compatibility-decisions.md).  
**Related Test Documents:**
- [V2 Post-Join Activation Test Matrix (Issue #136)](join-v2-ready-tdma-activation-test-matrix.md)
- [V2 Maintenance SF & Health Test Matrix (Issue #178)](v2-maintenance-beacon-health-test-matrix.md)
- [V2 Event DATA & ACK Test Matrix (Issue #177)](v2-event-ack-negative-test-matrix.md)
- [Harness Quality Gates Reference](../development/harness-quality-gates.md)
- [Acceptance Gates Reference](acceptance-gates.md)

---

## 1. Verification Strategy, Authority & Evidence Classes

### 1.1 Policy & Authority
In strict adherence to **Owner Decision #137 (2026-11-04)** and project [AGENTS.md](../../AGENTS.md):
1. **Mandatory `NOT_RUN` Initial State:** Every test case specified in this security matrix holds the initial status **`NOT_RUN`**. The creation of this documentation, test scenario schemas, or synthetic mock vectors does not constitute cryptographic verification or physical RF validation.
2. **Delta Security Focus:** Issue #136 delivered a comprehensive test matrix (`join-v2-ready-tdma-activation-test-matrix.md`, scenarios `TM-01` through `TM-25`) addressing nominal state transitions, general $3 \to 2 \to 1$ countdown mechanics, and basic radio timing. **This document does not duplicate those generic lifecycle tests.** Instead, it specifies the **targeted cryptographic delta**, focusing on adversarial attacks, edge-compromise resistance, zero-knowledge boundaries, X25519 degenerate point defenses, MQTT principal authorization, and NVS fault tolerance.
3. **Strict Downstream Binding:** Verification execution is bound directly to three independent downstream verification packages:
   - **Issue #173:** Cross-language Go ↔ ESP-IDF mbedTLS cryptographic golden vectors for HKDF, HMAC, and X25519.
   - **Issue #174:** Real Mosquitto 2.0 MQTT 5.0 broker integration verifying mTLS per-principal ACLs and topic authorization.
   - **Issue #175:** Real ESP32 Gateway NVS power-loss fault-injection HIL proving atomic key slot transitions.

---

### 1.2 Evidence Classification Hierarchy

| Class | Tag | Scope & Verification Environment |
|:---|:---:|:---|
| **Static Code Inspection** | `STATIC` | Clang-tidy, Go vet/golangci-lint, Ruff, constant-time comparison checks (`mbedtls_ct_memcmp`, `crypto/subtle`). |
| **Contract & Schema** | `CONTRACT` | Structural JSON schema validation (Draft 2020-12), binary wire field bounds, and bitfield assertions. |
| **Protocol Simulation** | `SIM` | Multi-node Python/Go discrete-event protocol testbed evaluating adversarial message injection and drop scenarios. |
| **Integration Testing** | `INT` | Multi-process containerized testbed (Go Modular Monolith + Mosquitto Broker + synthetic Gateway edge runners). |
| **Hardware-in-the-Loop** | `HIL` | Physical ESP32-WROOM-32E + SX1276 bench with automated power interruption and logic analyzer verification. |
| **RF Physical Bench** | `RF` | Over-the-air RF testbench in RF shielded chamber measuring spectrum, spurious emission, and physical preamble timing. |
| **Security Cryptanalysis** | `SEC` | Formal cryptographic proof verification, entropy assessment, side-channel analysis, and known-answer tests (KAT). |

---

## 2. Test Execution Preconditions & Profile Defaults

Unless otherwise specified, all test scenarios assume the approved MVP system profile:
- **RF PHY Profile:** Custom LoRa P2P, Center Freq 921.4 MHz, BW 125 kHz, SF7, CR 4/5, Preamble 8 symbols.
- **Node Hardware:** ESP32-WROOM-32E, ESP-IDF v6.1, FreeRTOS, hardware cryptographic accelerator (AES/SHA), secure eFuse MAC.
- **Gateway Edge:** ESP32-WROOM-32E / Linux Host with single SX1276 radio owner, serialized SPI driver.
- **Backend Stack:** Go Modular Monolith, PostgreSQL 16, Mosquitto 2.0 MQTT 5.0 broker with TLS 1.3 and mTLS principal certificates.
- **Cryptographic Root:** Unique 32-byte $K_{\text{JOIN}}$ per device registered in Backend Key Store, burned to encrypted NVS/eFuse on Node.
- **Clock Drift Assumption:** Max crystal drift $\le \pm 30\text{ ppm}$; guard interval lead $T_{\text{guard\_lead}} = 25\text{ ms}$.

---

## 3. Targeted Cryptographic Security Test Matrix (22 Scenarios)

```
+-------------------------------------------------------------------------------------------------------+
|                                10 TARGETED SECURITY VERIFICATION DIMENSIONS                           |
+-------------------------------------------------------------------------------------------------------+
| Dimension 1: Forged Gateway Attacks (SEC-TM-01 .. 03)    | Dimension 6: Key Desynchronization (SEC-TM-13..14)|
| Dimension 2: Lost Handshake Downlink (SEC-TM-04 .. 05)   | Dimension 7: Nonce & Rollback (SEC-TM-15 .. 16)   |
| Dimension 3: Replayed READY Attacks (SEC-TM-06 .. 07)    | Dimension 8: Early DATA Violations (SEC-TM-17..18)|
| Dimension 4: Identity & Generation (SEC-TM-08 .. 10)     | Dimension 9: Expired Grants/Leases (SEC-TM-19..20)|
| Dimension 5: ECDH All-Zero Points (SEC-TM-11 .. 12)      | Dimension 10: Forged MQTT Payloads (SEC-TM-21..22)|
+-------------------------------------------------------------------------------------------------------+
```

---

### Dimension 1: Forged Gateway Attacks

#### `SEC-TM-01`: Rogue Gateway Injects Fabricated `UP_JOIN_READY` Uplink over MQTT
- **Security Dimension:** Gateway Edge Compromise / Untrusted Gateway Boundary.
- **Threat Vector:** An attacker gains root access to Gateway edge hardware and captures ephemeral session keys ($Z, K_{\text{KC\_UP}}$). The attacker attempts to forge an `uplink/join-ready` message to trick the Backend into admitting an unauthorized Node or allocating a TDMA slot.
- **Preconditions:** Node handshake reached `UP_JOIN_KEY_CONFIRM`. Gateway holds $Z$ and derives valid `GW_READY_TAG8`. Gateway DOES NOT possess $K_{\text{JOIN}}$ or $K_{\text{JREADY}}$.
- **Stimulus:** Rogue Gateway generates candidate `UP_JOIN_READY` (0x49) frame with valid `READY_PREFIX7` and valid `GW_READY_TAG8`, but calculates `BACKEND_READY_PROOF16` using an arbitrary key or random bytes. Rogue Gateway publishes frame via MQTT to `iot/v1/gw/gw01/uplink/join-ready`.
- **Expected System Behavior & Safe State:**
  1. Backend Join Service extracts `BACKEND_READY_PROOF16` from bytes 15..30.
  2. Backend derives authentic $K_{\text{JREADY}}$ from device's provisioned $K_{\text{JOIN}}$.
  3. Constant-time HMAC comparison fails (`mismatch`).
  4. Backend **MUST NOT** transition Node to `NODE_READY_PENDING_SCHEDULE`.
  5. Backend emits a high-priority `SECURITY_ALERT` logging `REASON_INVALID_BACKEND_PROOF` with Gateway principal identity.
  6. Transaction is permanently aborted; Node remains unadmitted.
- **Traceability:** Decision `DEC-SEC-03`, `DEC-SEC-04` · Downstream: Issue #174.
- **Primary Owner:** Backend Go / Security Reviewer.
- **Evidence Class:** `INT` / `SEC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-02`: Rogue Gateway Injects Fabricated `DOWN_JOIN_GRANT` on RF
- **Security Dimension:** Downlink MITM / Unauthenticated Gateway Grant Injection.
- **Threat Vector:** Rogue transmitter emits a forged `DOWN_JOIN_GRANT` (0x46, 66B) containing an attacker-controlled ephemeral public key `GW_X25519_PUB` to establish a bogus session.
- **Preconditions:** Node has transmitted valid `UP_JOIN_HELLO` (0x45) and is listening during $T_{\text{grant\_listen}}$ window.
- **Stimulus:** Attacker transmits forged 66-byte frame on 921.4 MHz with matching `JOIN_COUNTER`, attacker `GW_X25519_PUB`, and forged `GRANT_PROOF16`.
- **Expected System Behavior & Safe State:**
  1. Node radio MAC parses frame; checks `VER_TYPE == 0x46` and `JOIN_COUNTER`.
  2. Node computes authentic $K_{\text{JGRANT}}$ using local $K_{\text{JOIN}}$ and provisioned generation.
  3. Node computes expected `GRANT_PROOF` over `M_GRANT` (137 bytes).
  4. Constant-time comparison detects tag mismatch.
  5. Node immediately discards the frame; **MUST NOT** execute X25519 scalar multiplication with attacker's public key; remains in `NODE_JOINING`.
- **Traceability:** Decision `DEC-SEC-01` · Downstream: Issue #173.
- **Primary Owner:** Node Firmware / Security Reviewer.
- **Evidence Class:** `HIL` / `SEC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-03`: Rogue Gateway Dispatches Fabricated `DOWN_JOIN_FINISH` on RF
- **Security Dimension:** Handshake Finalization Spoofing.
- **Threat Vector:** Rogue Gateway with valid $K_{\text{KC\_DOWN}}$ (derived from local ECDH) attempts to complete the handshake without Backend authorization by forging `DOWN_JOIN_FINISH` (0x48).
- **Preconditions:** Node transmitted `UP_JOIN_KEY_CONFIRM` and is waiting for Finish.
- **Stimulus:** Rogue Gateway sends 31-byte frame with valid `GW_FINISH_TAG8` (computed under $K_{\text{KC\_DOWN}}$), but forged or blank `BACKEND_FINISH_PROOF16`.
- **Expected System Behavior & Safe State:**
  1. Node verifies `GW_FINISH_TAG8` (evaluates TRUE).
  2. Node verifies `BACKEND_FINISH_PROOF16` using $K_{\text{JFINISH}}$ derived from $K_{\text{JOIN}}$ (evaluates FALSE).
  3. Node detects Backend proof failure; fails closed.
  4. Node wipes ephemeral keys, discards session, transitions to `NODE_UNJOINED` (or initiates fresh Join with incremented counter).
  5. Zero session keys committed to NVS.
- **Traceability:** Decision `DEC-SEC-04`, `DEC-SEC-05`.
- **Primary Owner:** Node Firmware / Security Reviewer.
- **Evidence Class:** `HIL` / `SEC`.
- **Status:** `NOT_RUN`.

---

### Dimension 2: Lost Handshake Downlink & Recovery

#### `SEC-TM-04`: RF Loss of `DOWN_JOIN_FINISH` (0x48) & Idempotent Confirm Retransmission
- **Security Dimension:** Delivery Uncertainty & Handshake State Reconciliation.
- **Threat Vector:** LoRa RF packet loss drops `DOWN_JOIN_FINISH` in transit. Node must safely retry without desynchronizing state, leaking keys, or reusing nonces.
- **Preconditions:** Backend issued valid Finish; Gateway transmitted on RF; packet lost due to channel fading.
- **Stimulus:**
  1. Node timeout $T_{\text{finish\_listen}}$ expires without receiving Finish.
  2. Node retransmits byte-identical `UP_JOIN_KEY_CONFIRM` (0x47, 31B) with identical nonces, counters, and tags within authorized retry window.
  3. Gateway receives duplicate Confirm; forwards to Backend.
- **Expected System Behavior & Safe State:**
  1. Backend detects duplicate Confirm matching active pending Join transaction (`JOIN_COUNTER`, $TH$).
  2. Backend DOES NOT re-plan or rotate keys; idempotently fetches previously generated Finish from transactional outbox.
  3. Gateway retransmits byte-identical `DOWN_JOIN_FINISH` (0x48) on RF.
  4. Node receives Finish; verifies dual tags; transitions to `SESSION_READY_NOT_ACTIVE`.
- **Traceability:** Decision `DEC-SEC-04` · Issue #136 (`TM-24` Delta).
- **Primary Owner:** Backend Go / Gateway Firmware.
- **Evidence Class:** `INT` / `SIM`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-05`: Node Power Loss / Watchdog Reset During Handshake Recovery
- **Security Dimension:** Volatile Memory Loss / Crash Recovery Integrity.
- **Threat Vector:** Node experiences a brownout or watchdog hardware reset after sending `UP_JOIN_KEY_CONFIRM` but before processing `DOWN_JOIN_FINISH`.
- **Preconditions:** Node RAM contains ephemeral private key $\text{priv}_{\text{node}}$ and temporary session derivations.
- **Stimulus:** Trigger hardware reset line on ESP32 while awaiting Finish. Node reboots.
- **Expected System Behavior & Safe State:**
  1. Node wakes up in `NODE_UNJOINED`. RAM is zeroized.
  2. Node inspects NVS; sees no active committed session.
  3. Node **MUST NOT** attempt to resume the interrupted transaction (ephemeral key is permanently lost).
  4. Node reads persistent `JOIN_COUNTER` from NVS, strictly increments it: $\text{counter}_{\text{new}} = \text{counter}_{\text{prev}} + 1$, and generates a fresh ephemeral keypair.
  5. Any late-arriving `DOWN_JOIN_FINISH` from the old transaction is rejected due to mismatched counter and unknown public key.
- **Traceability:** Decision `DEC-SEC-05`, `DEC-SEC-06`.
- **Primary Owner:** Node Firmware / Embedded HIL.
- **Evidence Class:** `HIL`.
- **Status:** `NOT_RUN`.

---

### Dimension 3: Replayed READY Transmissions

#### `SEC-TM-06`: Sniffed `UP_JOIN_READY` Replay in Subsequent Session
- **Security Dimension:** Anti-Replay Protection & Transcript Freshness.
- **Threat Vector:** Passive adversary records a valid `UP_JOIN_READY` (0x49) packet transmitted over the air. In a subsequent session (after Node re-joined or rotated keys), the adversary replays the old packet.
- **Preconditions:** Session $N$ completed successfully. Node subsequently performed a fresh Join, establishing Session $N+1$ with new ephemeral keys and $\text{JOIN\_COUNTER}_{N+1} > \text{JOIN\_COUNTER}_N$.
- **Stimulus:** Adversary transmits the recorded 0x49 frame from Session $N$ during the Subframe 4 `CTRL_WINDOW` of Session $N+1$.
- **Expected System Behavior & Safe State:**
  1. Gateway checks `GW_READY_TAG8` using current $K_{\text{KC\_UP}}$:
     - Tag verification fails immediately because $K_{\text{KC\_UP}}$ is derived from fresh ephemeral secret $Z_{N+1}$ and fresh transcript $TH_{N+1}$.
  2. Gateway drops packet at baseband; emits `LOG_SEC_TAG_MISMATCH`.
  3. If injected directly via MQTT, Backend checks `JOIN_COUNTER` against high-water mark:
     - Detects $\text{JOIN\_COUNTER}_N < \text{active\_counter}$; rejects with `STALE_COUNTER_REPLAY`.
- **Traceability:** Decision `DEC-SEC-03`, `DEC-SEC-06`.
- **Primary Owner:** Gateway Firmware / Backend Go.
- **Evidence Class:** `INT` / `SEC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-07`: Delayed / Out-of-Window `UP_JOIN_READY` Arrival
- **Security Dimension:** Half-Duplex Window Isolation & Timeout Fencing.
- **Threat Vector:** A Node transmits `UP_JOIN_READY` outside the designated Subframe 4 `CTRL_WINDOW`, or after Gateway's $T_{\text{await\_ready}}$ timer has expired.
- **Preconditions:** Gateway transmitted Finish; timer $T_{\text{await\_ready}} = 5{,}000\text{ ms}$ expired; Gateway purged staging context.
- **Stimulus:** Delayed `UP_JOIN_READY` arrives at Gateway radio receiver.
- **Expected System Behavior & Safe State:**
  1. Gateway checks active join transaction registry.
  2. Finds no pending transaction matching `(GW_ID, NODE_ID, JOIN_COUNTER)`.
  3. Gateway drops packet immediately; does not forward to Backend; does not arm TDMA engine.
- **Traceability:** Decision `DEC-SEC-03` · Issue #136 (`TM-20` Delta).
- **Primary Owner:** Gateway Firmware.
- **Evidence Class:** `SIM` / `HIL`.
- **Status:** `NOT_RUN`.

---

### Dimension 4: Identity, Principal & Generation Mismatches

#### `SEC-TM-08`: Cross-Gateway Principal Spoofing (RF `GW_ID` vs MQTT Client Cert)
- **Security Dimension:** Multi-Gateway Isolation & mTLS ACL Enforcement.
- **Threat Vector:** Gateway `gw02` attempts to publish join/ready events claiming to be `gw01`, or relays an RF packet where `TARGET_GW_ID == 0x01` through its own MQTT uplink.
- **Preconditions:** Gateway `gw02` has valid mTLS cert for `gw02` topic namespace; RF frame captured has `GW_ID = 0x01`.
- **Stimulus:** Gateway `gw02` publishes to `iot/v1/gw/gw01/uplink/join-ready` OR publishes to its own topic `iot/v1/gw/gw02/uplink/join-ready` with payload specifying `gateway_id = "gw01"` or `target_gw_id = 1`.
- **Expected System Behavior & Safe State:**
  1. If publishing to `gw01` topic: Mosquitto broker mTLS ACL rejects PUBLISH immediately with MQTT Reason Code `0x87 (Not authorized)`.
  2. If publishing to `gw02` topic with spoofed payload: Backend cross-checks TLS client principal identity (`gw02`) against payload (`gw01`):
     - Backend detects mismatch; rejects message with `PRINCIPAL_SPOOFING_REJECTED`.
     - Transaction aborted.
- **Traceability:** Decision `DEC-SEC-02` · Downstream: Issue #174.
- **Primary Owner:** Mosquitto Infra / Backend Go.
- **Evidence Class:** `INT` / `SEC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-09`: `DEVICE_GENERATION` Stale Session Injection
- **Security Dimension:** Technician Key Reprovisioning & Generation Fencing.
- **Threat Vector:** Technician executed an exceptional security reprovisioning of a compromised node: incremented `DEVICE_GENERATION` from 1 to 2 in Backend and burned new $K_{\text{JOIN\_GEN2}}$. An attacker replays an old Hello or attempts handshake using Generation 1 material.
- **Preconditions:** Backend registry active generation is 2.
- **Stimulus:** Attacker or stale node transmits `UP_JOIN_HELLO` with implicit Generation 1 KDF parameters, or receives `DOWN_JOIN_GRANT` with `DEVICE_GENERATION = 1`.
- **Expected System Behavior & Safe State:**
  1. Backend computes `PRK_JOIN` using active Generation 2:
     - `JOIN_PROOF` verification fails; Backend drops Hello.
  2. If Node receives Grant with `DEVICE_GENERATION == 1`:
     - Node checks local generation (2); detects mismatch (`1 != 2`); drops Grant immediately without processing.
- **Traceability:** Decision `DEC-SEC-06` · Issue #127 ([Comment 6629863066](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6629863066)).
- **Primary Owner:** Backend Go / Node Firmware.
- **Evidence Class:** `INT` / `CONTRACT`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-10`: `SESSION_SEL` Collision & Stale Slot Hijacking Attempt
- **Security Dimension:** Unicast Frame Disambiguation.
- **Threat Vector:** A Node transmits an application frame using a stale `SESSION_SEL` value from a prior session, or an adversary guesses the 1-byte selector.
- **Preconditions:** Node has active Session with `SESSION_SEL = 0x02`.
- **Stimulus:** Node or attacker emits frame with `SESSION_SEL = 0x01` during allocated slot.
- **Expected System Behavior & Safe State:**
  1. Gateway checks session selector table for `(NODE_ID, SESSION_SEL)`.
  2. Gateway detects selector `0x01` is retired/inactive.
  3. Packet dropped immediately; AES-CCM decryption not executed; error logged.
- **Traceability:** Decision `DEC-SEC-05`.
- **Primary Owner:** Gateway Firmware.
- **Evidence Class:** `CONTRACT` / `SIM`.
- **Status:** `NOT_RUN`.

---

### Dimension 5: ECDH All-Zero & Degenerate Point Attacks

#### `SEC-TM-11`: Malicious Node Injects All-Zero / Degenerate Point Public Key in Hello
- **Security Dimension:** Small-Subgroup & Curve25519 Degenerate Point Mitigation.
- **Threat Vector:** Rogue node sends an invalid X25519 public key in `UP_JOIN_HELLO` (e.g. all-zero $0^{32}$, order-8 twist points, or points of low order per RFC 7748 Section 6.1) to force shared secret $Z = 0^{32}$.
- **Preconditions:** Gateway has received Hello frame; relayed to Backend; Backend approved; Gateway ready to compute $Z$.
- **Stimulus:** Injected `NODE_X25519_PUB` consists of 32 bytes of `0x00` (or low-order hex `e0eb0100...`).
- **Expected System Behavior & Safe State:**
  1. Gateway executes `mbedtls_ecdh_compute_shared()`.
  2. Gateway inspects resulting shared secret $Z$.
  3. Gateway executes constant-time check: `all_zero = constant_time_is_zero(Z, 32)`.
  4. Gateway detects all-zero output point:
     - **MUST IMMEDIATELY ABORT HANDSHAKE.**
     - **MUST NOT** proceed to `HKDF-Extract`.
     - Zeroizes temporary buffers; logs `ERR_CRYPTO_ECDH_DEGENERATE_POINT`.
     - Fails closed; sends no Grant.
- **Traceability:** Decision `DEC-SEC-07` · RFC 7748 Section 6.1 · Issue #127 ([Comment 6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)).
- **Primary Owner:** Gateway Firmware / Crypto Reviewer.
- **Evidence Class:** `SEC` / `STATIC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-12`: Rogue Gateway Injects All-Zero / Degenerate Public Key in Grant
- **Security Dimension:** Node-Side Degenerate Point Mitigation.
- **Threat Vector:** Malicious or faulty Gateway sends all-zero `GW_X25519_PUB` in `DOWN_JOIN_GRANT`.
- **Preconditions:** Node received Grant; verified `GRANT_PROOF` (or tested in negative driver fixture).
- **Stimulus:** Node executes `X25519(priv_node, pub_gw)` where `pub_gw == 0^{32}`.
- **Expected System Behavior & Safe State:**
  1. Node detects $Z == 0^{32}$.
  2. Node aborts handshake immediately; zeroizes $\text{priv}_{\text{node}}$.
  3. Transitions to `NODE_UNJOINED`; logs security fault.
- **Traceability:** Decision `DEC-SEC-07`.
- **Primary Owner:** Node Firmware / Crypto Reviewer.
- **Evidence Class:** `HIL` / `SEC`.
- **Status:** `NOT_RUN`.

---

### Dimension 6: Key Material Desynchronization & Mismatches

#### `SEC-TM-13`: Transcript Hash $TH$ Bit-Flip & Desynchronization
- **Security Dimension:** Cryptographic Transcript Integrity.
- **Threat Vector:** A single-bit channel error or malicious alteration corrupts the ephemeral public key in transit between Node and Gateway, causing $TH$ to diverge.
- **Preconditions:** Node and Gateway computed different $TH$ values ($TH_{\text{node}} \ne TH_{\text{gw}}$).
- **Stimulus:** Node transmits `UP_JOIN_KEY_CONFIRM` (0x47).
- **Expected System Behavior & Safe State:**
  1. Gateway verifies `GW_KC_TAG8` using its local $K_{\text{KC\_UP}}$ and local $TH_{\text{gw}}$.
  2. Because $TH$ diverged, both $K_{\text{KC\_UP}}$ (derived with salt $TH$) and the tag MAC calculation fail.
  3. Gateway drops frame; does not forward to Backend; handshake terminates.
- **Traceability:** Decision `DEC-SEC-01`, `DEC-SEC-03`.
- **Primary Owner:** Node Firmware / Gateway Firmware.
- **Evidence Class:** `SIM` / `INT`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-14`: Desynchronized Session Key Generation at Cutover (Slot Mismatch)
- **Security Dimension:** State Cutover Synchronization.
- **Threat Vector:** Gateway commits session keys to active slot, but Node's schedule activation fails (e.g. missed Beacon countdown).
- **Preconditions:** Gateway is in `ACTIVE_SCHEDULE` (version 2); Node remains in `SCHEDULE_STAGED` or `RECOVERY_HOLD`.
- **Stimulus:** Node transmits in old slot or fails to transmit in new slot.
- **Expected System Behavior & Safe State:**
  1. Gateway detects slot transmission violation or empty slot.
  2. Gateway does not send ACK; registers missing transmission.
  3. Node 8-fold guard detects un-synchronized schedule; inhibits RF transmission; prevents collisions with other nodes.
- **Traceability:** Decision `DEC-SEC-05` · Issue #136 (`TM-12` Delta).
- **Primary Owner:** TDMA Scheduler / Node MAC.
- **Evidence Class:** `SIM`.
- **Status:** `NOT_RUN`.

---

### Dimension 7: Nonce Reuse & Counter Rollback

#### `SEC-TM-15`: `JOIN_COUNTER` Rollback Attack (Replayed Stale Hello)
- **Security Dimension:** Monotonicity Enforcement & Anti-Replay.
- **Threat Vector:** Attacker captures an old valid `UP_JOIN_HELLO` frame and replays it to force the Backend to accept a stale counter.
- **Preconditions:** Backend database records device high-water mark $\text{last\_join\_counter} = 15$.
- **Stimulus:** Replay Hello frame with $\text{JOIN\_COUNTER} \le 15$.
- **Expected System Behavior & Safe State:**
  1. Backend Join Service queries `devices` table: checks `JOIN_COUNTER <= last_join_counter`.
  2. Backend rejects frame immediately; emits `ALERT_COUNTER_ROLLBACK`.
  3. No Grant issued; transaction discarded.
- **Traceability:** Decision `DEC-SEC-06` · Issue #127 ([Comment 6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)).
- **Primary Owner:** Backend Go Join Service.
- **Evidence Class:** `INT` / `CONTRACT`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-16`: NVS Counter Corruption / Flash Wear on Node Boot
- **Security Dimension:** Hardware Fault Tolerance / Fail-Closed Storage.
- **Threat Vector:** Power loss during NVS write causes corrupted counter block or CRC mismatch on ESP32 reboot.
- **Preconditions:** ESP32 boots up; calls `nvs_get_u32("join_counter")`.
- **Stimulus:** Inject NVS CRC error or corrupted sector in flash.
- **Expected System Behavior & Safe State:**
  1. Node NVS driver returns `ESP_ERR_NVS_CORRUPT_KEY_SYSTEM` or CRC fail.
  2. Node **MUST NOT** default counter to 0 or arbitrary value.
  3. Node enters hard panic / unrecoverable fault state; halts radio initialization; turns on fault LED.
  4. Transmission is permanently inhibited until re-provisioned via technician UART tool.
- **Traceability:** Decision `DEC-SEC-06` · Downstream: Issue #175.
- **Primary Owner:** Node Firmware / Embedded HIL.
- **Evidence Class:** `HIL`.
- **Status:** `NOT_RUN`.

---

### Dimension 8: Early DATA Transmission Violations

#### `SEC-TM-17`: Node Attempts Early DATA TX in `SESSION_READY_NOT_ACTIVE`
- **Security Dimension:** Inactive Key Fencing Enforcement.
- **Threat Vector:** Faulty application task queues sensor event and attempts to key the SX1276 transmitter immediately after `DOWN_JOIN_FINISH` is processed, before TDMA schedule is received.
- **Preconditions:** Node state is `SESSION_READY_NOT_ACTIVE`. Keys derived in RAM.
- **Stimulus:** Application task calls `mac_send_event(payload)`.
- **Expected System Behavior & Safe State:**
  1. Radio MAC layer evaluates 8-fold DATA TX guard:
     - Guard G3 (`SCHEDULE_AUTHENTIC`) evaluates FALSE.
     - Guard G6 (`SLOT_OWNERSHIP_EXCLUSIVE`) evaluates FALSE.
  2. SX1276 power amplifier remains powered down.
  3. Function returns `ERR_MAC_TX_INHIBITED`.
  4. Event remains stored in local flash queue.
- **Traceability:** Decision `DEC-SEC-05` · Issue #136 Doc Section 6.
- **Primary Owner:** Node Firmware / Radio MAC.
- **Evidence Class:** `HIL` / `STATIC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-18`: Node Attempts Early DATA TX During $3 \to 2 \to 1$ Staging Horizon
- **Security Dimension:** Announcement Countdown Fence.
- **Threat Vector:** Node receives Downlink schedule with countdown = 2; attempts to transmit in allocated Slot $S$ before target boundary $K_{\text{target}}$ is reached.
- **Preconditions:** Node in `SCHEDULE_STAGED`; superframe sequence is $K_{\text{target}}-2$.
- **Stimulus:** Slot $S$ timer triggers.
- **Expected System Behavior & Safe State:**
  1. Guard evaluation checks active schedule version vs shadow version.
  2. Evaluates FALSE (active schedule version is still old or uncommitted).
  3. PA remains disabled; zero RF power output.
- **Traceability:** Decision `DEC-SEC-05`.
- **Primary Owner:** Node Firmware.
- **Evidence Class:** `HIL` / `SIM`.
- **Status:** `NOT_RUN`.

---

### Dimension 9: Expired Grants, Schedules & Leases

#### `SEC-TM-19`: Late `DOWN_JOIN_GRANT` Arrival (TTL / Window Expiration)
- **Security Dimension:** Handshake Temporal Bounds.
- **Threat Vector:** Delayed Grant packet arrives on RF after Node's $T_{\text{grant\_listen}}$ timer has elapsed.
- **Preconditions:** Node transmitted Hello; waited $T_{\text{grant\_listen}} = 4{,}000\text{ ms}$; timeout triggered; Node aborted transaction.
- **Stimulus:** Delayed `DOWN_JOIN_GRANT` arrives at SX1276 receiver.
- **Expected System Behavior & Safe State:**
  1. Node radio ISR discards packet because MAC state is `NODE_UNJOINED` (not `AWAIT_GRANT`).
  2. Packet dropped without cryptographic processing.
- **Traceability:** Decision `DEC-SEC-01`.
- **Primary Owner:** Node Firmware.
- **Evidence Class:** `SIM` / `HIL`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-20`: Active Session Lease Expiration During Operation
- **Security Dimension:** Session Lifetime Boundary & Re-Key Enforcement.
- **Threat Vector:** Active session lease expires without receiving a lease renewal in Maintenance Superframe.
- **Preconditions:** Node is in `ACTIVE_DATA_ELIGIBLE`; monotonic time passes $T_{\text{lease\_expiry}}$.
- **Stimulus:** Application queues new event for transmission.
- **Expected System Behavior & Safe State:**
  1. Guard G4 (`LEASE_ACTIVE`) evaluates FALSE ($T_{\text{now}} \ge T_{\text{lease\_expiry}}$).
  2. Node transitions to `NODE_RECOVERY_HOLD`.
  3. Transmission inhibited; Node waits for maintenance beacon or triggers re-join.
- **Traceability:** Decision `DEC-SEC-05` · Agent 2 Issue #178 Dossier.
- **Primary Owner:** Node Firmware / TDMA Engine.
- **Evidence Class:** `SIM` / `HIL`.
- **Status:** `NOT_RUN`.

---

### Dimension 10: Forged MQTT Payloads & Broker Tampering

#### `SEC-TM-21`: Unauthorized MQTT Client Attempts Publishing to Session Key Topics
- **Security Dimension:** MQTT Broker Access Control & Namespace Partitioning.
- **Threat Vector:** Compromised non-gateway MQTT client (e.g. web telemetry reader) connects with valid credentials and attempts to inject a forged `downlink/session-key-install` or `downlink/session-binding` payload.
- **Preconditions:** Mosquitto 2.0 broker configured with per-principal ACLs (PR #123 / Issue #174).
- **Stimulus:** Non-gateway client publishes to `iot/v1/gw/gw01/downlink/session-key-install`.
- **Expected System Behavior & Safe State:**
  1. Mosquitto ACL engine matches client principal against topic publish rules.
  2. Broker terminates publication with Reason Code `0x87 (Not authorized)`.
  3. Message is not delivered to Gateway subscriber; security audit log emitted.
- **Traceability:** Decision `DEC-SEC-02` · Downstream: Issue #174.
- **Primary Owner:** Infrastructure / Broker Admin.
- **Evidence Class:** `INT` / `SEC`.
- **Status:** `NOT_RUN`.

---

#### `SEC-TM-22`: Tampered AAD / Tag in MQTT V2 Session Binding Message
- **Security Dimension:** Alternative B Session Authorization Contract Integrity.
- **Threat Vector:** Man-in-the-middle or malfunctioning proxy tampers with `session_revision` or `transcript_hash_th` in V2 Session Binding message.
- **Preconditions:** Backend published V2 Session Binding Ticket; Gateway subscribed.
- **Stimulus:** Inject 1-bit alteration into `transcript_hash_th` field before delivery to Gateway.
- **Expected System Behavior & Safe State:**
  1. Gateway parses JSON; compares `transcript_hash_th` with local $TH$ computed from RF handshake.
  2. Gateway detects mismatch; rejects binding ticket.
  3. Locally derived keys in `INSTALLED_INACTIVE` are purged; Gateway publishes `VERIFY_NACK` with `REASON_TRANSCRIPT_MISMATCH`.
  4. Keys are never activated.
- **Traceability:** Decision `DEC-SEC-02`.
- **Primary Owner:** Gateway Firmware / Backend Go.
- **Evidence Class:** `CONTRACT` / `INT`.
- **Status:** `NOT_RUN`.

---

## 4. Traceability & Downstream Verification Mapping

This table binds each targeted security test case to its owning issue, primary verification environment, and downstream dependency.

| Test ID | Scenario Summary | Owning Authority | Evidence Tier | Status | Downstream Binding |
|:---|:---|:---:|:---:|:---:|:---:|
| `SEC-TM-01` | Rogue Gateway Injects Fabricated `UP_JOIN_READY` | Backend Go / Security | `INT` / `SEC` | `NOT_RUN` | Issue #174 (Broker) |
| `SEC-TM-02` | Rogue Gateway Injects Fabricated `DOWN_JOIN_GRANT` | Node Firmware / Crypto | `HIL` / `SEC` | `NOT_RUN` | Issue #173 (Vectors) |
| `SEC-TM-03` | Rogue Gateway Dispatches Fabricated `DOWN_JOIN_FINISH`| Node Firmware / Crypto | `HIL` / `SEC` | `NOT_RUN` | Issue #173 (Vectors) |
| `SEC-TM-04` | Lost `DOWN_JOIN_FINISH` & Idempotent Confirm Retransmit | Backend / Gateway | `INT` / `SIM` | `NOT_RUN` | Issue #136 (`TM-24`) |
| `SEC-TM-05` | Node Power Loss During Handshake Recovery | Node Firmware / HIL | `HIL` | `NOT_RUN` | Issue #175 (NVS HIL) |
| `SEC-TM-06` | Sniffed `UP_JOIN_READY` Cross-Session Replay | Gateway / Backend | `INT` / `SEC` | `NOT_RUN` | Issue #136 (`TM-05`) |
| `SEC-TM-07` | Delayed / Out-of-Window `UP_JOIN_READY` Arrival | Gateway Firmware | `SIM` / `HIL` | `NOT_RUN` | Issue #136 (`TM-20`) |
| `SEC-TM-08` | Cross-Gateway Principal Spoofing (RF vs MQTT) | Mosquitto / Backend | `INT` / `SEC` | `NOT_RUN` | Issue #174 (mTLS) |
| `SEC-TM-09` | `DEVICE_GENERATION` Stale Session Injection | Backend / Node | `INT` / `CONTRACT`| `NOT_RUN` | Issue #127 (C6629863066)|
| `SEC-TM-10` | `SESSION_SEL` Collision & Stale Slot Hijacking | Gateway Firmware | `CONTRACT` / `SIM`| `NOT_RUN` | Parent #127 |
| `SEC-TM-11` | Malicious Node Injects All-Zero X25519 Public Key | Gateway Crypto | `SEC` / `STATIC` | `NOT_RUN` | RFC 7748 / Issue #173 |
| `SEC-TM-12` | Rogue Gateway Injects All-Zero Public Key in Grant | Node Crypto | `HIL` / `SEC` | `NOT_RUN` | RFC 7748 / Issue #173 |
| `SEC-TM-13` | Transcript Hash $TH$ Bit-Flip Desynchronization | Node / Gateway Crypto | `SIM` / `INT` | `NOT_RUN` | Issue #173 (Vectors) |
| `SEC-TM-14` | Desynchronized Session Key Generation at Cutover | TDMA Engine / MAC | `SIM` | `NOT_RUN` | Issue #136 (`TM-12`) |
| `SEC-TM-15` | `JOIN_COUNTER` Rollback Attack on Hello | Backend Go Join | `INT` / `CONTRACT`| `NOT_RUN` | Issue #127 (C6628167582)|
| `SEC-TM-16` | NVS Counter Corruption / Flash Wear on Node Boot | Node Firmware / HIL | `HIL` | `NOT_RUN` | Issue #175 (NVS HIL) |
| `SEC-TM-17` | Node Attempts Early DATA TX in Inactive State | Node MAC Driver | `HIL` / `STATIC` | `NOT_RUN` | Issue #136 (Section 6)|
| `SEC-TM-18` | Node Attempts Early DATA TX During Staging Horizon | Node MAC Driver | `HIL` / `SIM` | `NOT_RUN` | Issue #136 (Section 5)|
| `SEC-TM-19` | Late `DOWN_JOIN_GRANT` Arrival (TTL Expiry) | Node Radio Driver | `SIM` / `HIL` | `NOT_RUN` | Parent #127 |
| `SEC-TM-20` | Active Session Lease Expiration During Operation | Node TDMA Engine | `SIM` / `HIL` | `NOT_RUN` | Issue #178 (Maint SF) |
| `SEC-TM-21` | Unauthorized MQTT Client Publishing to Key Topics | Infra / Mosquitto | `INT` / `SEC` | `NOT_RUN` | Issue #174 (ACLs) |
| `SEC-TM-22` | Tampered AAD / Tag in MQTT V2 Session Binding | Gateway / Backend | `CONTRACT` / `INT`| `NOT_RUN` | Issue #128 (Binding) |

---

## 5. Acceptance Sign-Off Checklist

- [x] Security test matrix covers all 10 mandatory dimensions: Forged Gateway, Lost Finish, Replayed READY, Wrong Tag/Principal/Generation, ECDH All-Zero, Key Mismatch, Nonce/Rollback, Early DATA, Expired Grant/Lease, Forged MQTT.
- [x] Every test case initialized to status `NOT_RUN` (zero false PASS claims).
- [x] Generic test cases from Issue #136 referenced rather than duplicated; focused delta specified.
- [x] Explicit downstream binding to #173, #174, #175 established.
- [x] Preconditions, stimulus, expected system behavior, and fail-closed states detailed for every scenario.
