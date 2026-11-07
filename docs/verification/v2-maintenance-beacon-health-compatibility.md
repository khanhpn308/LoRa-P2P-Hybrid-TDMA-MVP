# LP2P V2 Maintenance SF, SYNC_BEACON & HEALTH_REPLY Compatibility Dossier

**Document ID:** `DOC-VERIF-V2-MAINT-BCN-HEALTH-001`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent Tracking:** Issue #178 (Agent 2 Work Package), Parent Issue #127, Umbrella Issue #125, Architecture Child Issue #126.
**Parallel Work Packages:** Agent 1 (#177, V2 Event/ACK Compatibility), Agent 3 (#182, V2 Join/Session Keys/READY Security).
**Owning Authorities:** #19 (Backend Schedule Planner), #131 (Firmware Execution), #169 (Physical RF Timing & Measured Guard Time Sign-off).
**Related Documents:** [ADR-0001 (Hybrid TDMA)](../adr/0001-hybrid-tdma.md), [ADR-0002 (MQTT 5.0)](../adr/0002-mqtt-5.md), [Radio MAC Specification](../../contracts/radio-mac/specification.md), [TDMA Schedule Contract](../../contracts/radio-mac/tdma-schedule.md), [Open Decisions](../../contracts/OPEN_DECISIONS.md), [V2 Post-Join Activation Design](join-v2-ready-tdma-activation-design.md), [RF Timing Methodology & Harness](rf-timing-methodology-and-harness.md).

---

## 1. Governance, Authority & Scope Boundary

### 1.1 Authority & Project Policy
In accordance with **Owner Decision #137 (2026-11-04)** and project [AGENTS.md](../../AGENTS.md):
1. **Self-Contained Design Dossier:** This document constitutes a formal design and verification dossier for technical Owner, Radio MAC, Gateway, Node, Backend, and Security review. It does **not** authorize production firmware coding, live radio frequency (RF) transmissions, database migrations, or wire standard codepoint freezes.
2. **Symbolic Numeric Budgets:** All numeric time allocations (e.g., ~300 s maintenance interval, 10 s superframe duration, 400 ms slot lengths, 25 ms guard intervals) are strictly **symbolic engineering references**. Issue #11 owns theoretical Time-on-Air (ToA) tooling; **Issue #169** solely owns real physical hardware-in-the-loop (HIL) timing measurements, clock drift data, and measured Guard Time sign-off. No numeric timing parameters are frozen by this dossier.
3. **Zero In-Place Normative Overwrites:** Common normative contracts (`contracts/radio-mac/specification.md`, `contracts/radio-mac/tdma-schedule.md`, `contracts/OPEN_DECISIONS.md`) remain **read-only** for this child package. All contract modifications are handed off to parent Issue #127 for synchronized integration.
4. **V1 Provenance Protection:** Owner-approved V1 design artifacts in PR #124 (Bootstrap Join, 28B Group-HMAC Beacon, compact V1 READY, and historical Golden Vectors) remain preserved as historical audit provenance and are **not** repurposed, overwritten, or implicitly migrated.

### 1.2 Parallel Child Division of Labor (3 Agents)
Under parent #127 and umbrella #125, three disjoint child work packages execute concurrently:
- **Agent 1 (Issue #177):** V2 Event-only DATA slots, own-slot uplink retry, `DOWN_EVENT_ACK` (0x42) framing, persistent local `EVENT_REF` vs Gateway-origin `event_id`, and V1 periodic telemetry/ACK_BITMAP supersession.
- **Agent 2 (This Dossier, Issue #178):** V2 Maintenance Superframe (SF) interpolation, `DOWN_SYNC_BEACON` (0x43) candidate, `UP_HEALTH_REPLY` (0x44) candidate, half-duplex mode scheduling, 300 s calendar cadence, clock drift holdover, 100%-READY affected-node fence, and schedule synchronization (with legacy 3→2→1 countdown superseded per Owner Decision #208 / PR #206).
- **Agent 3 (Issue #182):** V2 Join cryptographic handshake (`0x45`..`0x48`), ephemeral X25519 ECDH key agreement, Backend `K_JOIN` verification, candidate `UP_JOIN_READY` (0x49), and Backend 64B Install vs V2 derivation reconciliation.

```
       +---------------------------------------------------------------------------------+
       |                           PARENT ISSUE #127 INTEGRATION GATE                    |
       |       Owns: contracts/radio-mac/specification.md, tdma-schedule.md, OPEN_DECISIONS |
       +---------------------------------------------------------------------------------+
                                 ▲                          ▲                          ▲
                                 │                          │                          │
        +------------------------+                          │                          +------------------------+
        │                                                   │                                                   │
+-------------------------------+       +---------------------------------------+       +-------------------------------+
|     AGENT 1 (ISSUE #177)      |       |         AGENT 2 (ISSUE #178)          |       |     AGENT 3 (ISSUE #182)      |
|  - UP_EVENT (0x41, 26B)       |       |  - DOWN_SYNC_BEACON (0x43, 80B)       |       |  - UP_JOIN_HELLO (0x45, 68B)  |
|  - DOWN_EVENT_ACK (0x42, 19B) |       |  - UP_HEALTH_REPLY (0x44, 21B)        |       |  - DOWN_JOIN_GRANT (0x46, 66B)|
|  - Local EVENT_REF mapping    |       |  - Maintenance SF (~300s cadence)     |       |  - UP_JOIN_CONFIRM (0x47, 31B)|
|  - Own-slot retry semantics   |       |  - Clock Drift / Holdover Lockout     |       |  - DOWN_JOIN_FINISH (0x48, 31B|
|  - Obsolete V1 Telemetry/ACK  |       |  - Half-Duplex SX1276 Scheduling      |       |  - UP_JOIN_READY (0x49 cand.) |
|  - Status: DESIGN CANDIDATE   |       |  - Status: DESIGN CANDIDATE           |       |  - Status: DESIGN CANDIDATE   |
+-------------------------------+       +---------------------------------------+       +-------------------------------+
```

---

## 2. Executive Summary & Purpose

### 2.1 The Architectural Transition from V1 to V2
Under approved architecture child **#126** (PR #133) and Umbrella **#125**, the LoRa-P2P network transitions from continuous periodic sensor polling to an **Event-Only Static TDMA + Maintenance Superframe** model:
- **Local Alarm Independence:** Nodes process local physical sensor inputs immediately; alert actuation is local and independent of RF connectivity.
- **Event-Only Static TDMA:** Sensor events are queued in a bounded local non-volatile FIFO and transmitted exclusively during the Node's pre-assigned static TDMA slot within normal DATA superframes.
- **Elimination of Continuous Telemetry:** Obsolete periodic uplink messages (`UP_TELEMETRY` 0x26), Contention Access Periods (CAP / C08), and piggybacked acknowledgment bitmaps (`ACK_BITMAP`) are eliminated.
- **The Role of Maintenance Superframes:** Normal DATA superframes contain static slots dedicated to low-latency event uplinks. However, sleeping and low-duty sensor nodes experience crystal drift, phase jitter, and lack of channel feedback. If no events occur for hours, the network would lose time synchronization, gateway connectivity awareness, and node liveness state.
- **Interpolated Maintenance Cadence:** Maintenance Superframes are interpolated among normal DATA superframes at a relaxed target interval of **~300 seconds** (symbolic target). The Maintenance Superframe executes two essential functions:
  1. **Broadcast Time & Schedule Synchronization:** Gateway broadcasts an authenticated `DOWN_SYNC_BEACON` carrying authoritative network time, epoch counters, and pending schedule countdowns.
  2. **Scheduled Node Liveness & Health Reporting:** Each authorized Node is allocated a dedicated, non-overlapping slot to transmit a lightweight, authenticated `UP_HEALTH_REPLY` reporting system status, battery condition, and unacknowledged event backlog.

---

## 3. Beacon & Health Compatibility Registry (Deliverable 1)

This section documents the formal registry comparing historical V1 provenance against candidate V2 formats. V1 and candidate V2 packet formats **must never be confused or merged**.

### 3.1 Historical V1 BEACON (0x21) — Provenance Only
The V1 Beacon is locked at the design level in PR #124 ([ADR-0002](../../docs/adr/0002-radio-mac-security-v1.md) and PR #116 Comment 6575398231). It represents historical provenance and is **superseded for V2 runtime**.

#### V1 Frame Layout (28 Bytes Fixed)
| Offset | Field Name | Width | Type / Encoding | Description / Rule |
|:---:|:---|:---:|:---|:---|
| 0 | `VER_TYPE` | 1B | `uint8` (`0x21`) | Protocol version 1 (`0x20`), packet type `BEACON` (`0x01`). Alias `DOWN_BEACON_ACK`. |
| 1 | `GW_ID` | 1B | `uint8` | Identity of broadcasting Gateway (`0x01`..`0xFE`; `0x00`/`0xFF` reserved). |
| 2..5 | `SF_EPOCH` | 4B | `uint32_t` BE | Superframe sequence counter / epoch timestamp. |
| 6..7 | `SCHED_VER` | 2B | `uint16_t` BE | Currently active TDMA schedule version identifier. |
| 8..9 | `ACK_BITMAP` | 2B | `uint16_t` BE | 16-bit acknowledgment bitmap for periodic telemetry slots 1..15. **Superseded in V2.** |
| 10 | `CTRL_FLAGS` | 1B | `uint8` | Control bits (e.g., Join open, schedule countdown active). |
| 11 | `BCN_KEY_ID` | 1B | `uint8` | Key selector index for provisioned group key `K_BEACON_GROUP`. |
| 12..27 | `BCN_AUTH_TAG` | 16B | `byte[16]` | Truncated tag: `first16(HMAC-SHA256(K_BEACON_GROUP, M_BCN_V1))`. |

#### V1 Security Trade-Off & Vulnerabilities
1. **Symmetric Group Key Possession $\neq$ Gateway Authentication:** Because `K_BEACON_GROUP` is shared across all nodes in the network, any physically compromised Node possessing `K_BEACON_GROUP` can extract the key from flash and forge valid Beacons. A valid HMAC tag proves group membership, not unique Gateway origin.
2. **Coupling to Periodic Telemetry:** Bytes 8..9 (`ACK_BITMAP`) assume nodes transmit periodic telemetry packets that are collectively acknowledged by the Gateway in the subsequent beacon. Under Event-only architecture (#126), this coupling is obsolete and wastes 16 bits of RF airtime.
3. **No Network Timestamp Anchor:** `SF_EPOCH` counts superframe increments rather than providing an absolute, high-precision network time anchor for real-time drift disciplining.

---

### 3.2 Candidate V2 DOWN_SYNC_BEACON (0x43) — Candidate Design
Introduced in parent #127 design sketch (`LP2P-V2-SKETCH-01`, Comment 6623475221). Status is **CANDIDATE_FOR_OWNER_REVIEW**.

#### V2 Frame Layout (80 Bytes Fixed)
The frame consists of 16 bytes of plaintext metadata followed by a 64-byte Ed25519 asymmetric signature:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   VER_TYPE    |     GW_ID     |           MAINT_SEQ           |
|    (0x43)     |    (1 Byte)   |           (4 Bytes,           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-------------------------------+
|      MAINT_SEQ (cont.)        |        NETWORK_TIME_MS        |
|          uint32 BE)           |       (6 Bytes, uint48 BE)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-------------------------------+
|                   NETWORK_TIME_MS (cont.)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           SCHED_VER           |     FLAGS     |   SIGNER_ID   |
|      (2 Bytes, uint16 BE)     |   (1 Byte)    |   (1 Byte)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                      ED25519 SIGNATURE                        +
|                     (64 Bytes, RFC 8032)                      |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Offset | Field Name | Width | Type / Constraint | Description & Validation Rule |
|:---:|:---|:---:|:---|:---|
| 0 | `VER_TYPE` | 1B | `uint8` (`0x43`) | Proto V2 (high 3 bits `0b010`), packet type `SYNC_BEACON` (low 5 bits `0b00011`). |
| 1 | `GW_ID` | 1B | `uint8` | Gateway Identifier (`0x01`..`0xFE`). Must match Node's associated Gateway. |
| 2..5 | `MAINT_SEQ` | 4B | `uint32_t` BE | Monotonic Maintenance Superframe Sequence Counter. Strictly increasing. |
| 6..11 | `NETWORK_TIME_MS` | 6B | `uint48_t` BE | Absolute Unix epoch time in milliseconds (valid through year 10889). |
| 12..13 | `SCHED_VER` | 2B | `uint16_t` BE | Active schedule version; or target version during countdown. |
| 14 | `FLAGS` | 1B | `uint8` bitmask | Bit 0: Countdown active (`1` = announcement in progress).<br>Bit 1: Maintenance-only window (`1` = no DATA superframes follow).<br>Bit 2: Join window open (`1` = contention slots permit `UP_JOIN_HELLO`).<br>Bits 3..7: Reserved (must be `0`). |
| 15 | `SIGNER_ID` | 1B | `uint8` | Key selector index referencing the Gateway's authorized Ed25519 public key. |
| 16..79 | `SIGNATURE` | 64B | `byte[64]` | Ed25519 signature over canonical transcript $M_{\text{BCN}}$. |

#### Cryptographic Canonical Transcript
The signature is computed over the domain-separated transcript $M_{\text{BCN}}$:
$$\text{Signature} = \text{Ed25519\_Sign}\left(\text{SK}_{\text{GW}},\, M_{\text{BCN}}\right)$$
Where:
$$M_{\text{BCN}} = \text{ASCII}(\text{"LP2P/V2/SYNC-BEACON"})\,\|\,\text{NETWORK\_ID}_{4}\,\|\,\text{FRAME}[0..15]$$
- $\text{ASCII}(\text{"LP2P/V2/SYNC-BEACON"})$: 19-byte ASCII domain separator.
- $\text{NETWORK\_ID}_{4}$: 4-byte provisioned network identifier (prevents cross-network beacon injection).
- $\text{FRAME}[0..15]$: The exact 16-byte plaintext header (`VER_TYPE` through `SIGNER_ID`).

#### Trust Model, Asymmetric Verification & Anti-Replay
1. **Asymmetric Origin Authentication:** The Gateway holds the private signing key $\text{SK}_{\text{GW}}$. Sensor nodes hold only the public verification key $\text{PK}_{\text{GW}}$ (provisioned during manufacturing or securely delivered via Backend-authorized activation). Node compromise reveals **only** $\text{PK}_{\text{GW}}$, preventing the compromised node from impersonating the Gateway or forging Beacons.
2. **Replay Rejection via High-Water Tracking:** Nodes maintain a durable in-memory high-water mark $\text{MAINT\_SEQ}_{\text{HW}}$. Any received Beacon with $\text{MAINT\_SEQ} \le \text{MAINT\_SEQ}_{\text{HW}}$ is immediately discarded as a replay.
3. **Network Time Bounding:** The node compares `NETWORK_TIME_MS` against its local clock adjusted for maximum drift. If the difference exceeds $\pm \Delta T_{\text{SANITY}}$ (e.g., 60 seconds), the Beacon is rejected for clock disciplining pending recovery.
4. **Airtime vs. Processing Trade-off:** At SF7/BW125, an 80-byte frame requires approximately 149 ms Time-on-Air (theoretical). Verifying an Ed25519 signature on an ESP32-WROOM-32E running at 160 MHz requires approximately 12–18 ms of CPU processing time (subject to physical HIL measurement under Issue #169).

---

### 3.3 Candidate V2 UP_HEALTH_REPLY (0x44) — Candidate Design
Introduced in parent #127 design sketch (`LP2P-V2-SKETCH-01`, Comment 6623475221). Status is **CANDIDATE_FOR_OWNER_REVIEW**.

#### V2 Frame Layout (21 Bytes Fixed)
The packet utilizes the standardized V2 7-byte Unicast Header, followed by 6 bytes of encrypted payload and an 8-byte AES-128-CCM authentication tag:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   VER_TYPE    |    NODE_ID    |  SESSION_SEL  |               |
|    (0x44)     |   (1 Byte)    |   (1 Byte)    |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+               +
|                         FRAME_COUNTER                         |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           MAINT_SEQ                           |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| STATUS_FLAGS  | PENDING_COUNT |                               |
|   (1 Byte)    |   (1 Byte)    |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+       AES-128-CCM TAG         +
|                                           (8 Bytes)           |
+                               +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Offset | Field Name | Width | Type / Constraint | Description & Security Policy |
|:---:|:---|:---:|:---|:---|
| **0..6** | **Unicast Header** | **7B** | **Plaintext (AAD)** | **Standardized V2 Unicast Header (Authenticated Additional Data).** |
| 0 | `VER_TYPE` | 1B | `uint8` (`0x44`) | Proto V2 (high 3 bits `0b010`), packet type `HEALTH_REPLY` (low 5 bits `0b00100`). |
| 1 | `NODE_ID` | 1B | `uint8` | Logical short identifier of reporting Node (`0x01`..`0xFE`). |
| 2 | `SESSION_SEL` | 1B | `uint8` | Active session index corresponding to pairwise key $K_{\text{SESSION\_UP}}$. |
| 3..6 | `FRAME_COUNTER` | 4B | `uint32_t` BE | Monotonic per-session uplink frame counter. Replay protection. |
| **7..12**| **Ciphertext** | **6B** | **Encrypted** | **AES-128-CTR encrypted payload bytes.** |
| 7..10 | `MAINT_SEQ` | 4B | `uint32_t` BE | Echo of the `MAINT_SEQ` from the received `DOWN_SYNC_BEACON`. |
| 11 | `STATUS_FLAGS` | 1B | `uint8` bitmask | Bit 0: Sensor HW OK (`1` = healthy, `0` = fault).<br>Bit 1: RTC Valid (`1` = clock disciplined, `0` = uncertain).<br>Bit 2: NVS Storage OK (`1` = flash healthy, `0` = flash fault).<br>Bit 3: Battery Low (`1` = voltage below threshold).<br>Bits 4..7: Reserved (`0`). |
| 12 | `PENDING_COUNT`| 1B | `uint8` | Number of unacknowledged events queued in local durable FIFO (`0`..`255`). |
| **13..20**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM authentication tag ($M=8$, $L=2$).** |

#### Encryption & Authentication Primitives
- **Authenticated Additional Data (AAD):** $\text{AAD} = \text{FRAME}[0..6]$ (the 7-byte Unicast Header).
- **Plaintext Payload ($P$):** $P = \text{MAINT\_SEQ}_{4}\,\|\,\text{STATUS\_FLAGS}_{1}\,\|\,\text{PENDING\_COUNT}_{1}$ (6 bytes).
- **13-Byte Nonce ($N$):** Formed from session-derived nonce prefix, direction byte, and frame counter:
  $$N = \text{NONCE\_PREFIX}_{\text{UP}}[0..7]\,\|\,0\text{x}01\,\|\,\text{FRAME\_COUNTER}[0..3]$$
  Where $0\text{x}01$ explicitly designates the **uplink** direction.
- **Key:** Pairwise dynamic key $K_{\text{SESSION\_UP}}$ derived from V2 Join ephemeral ECDH ($Z$) and authenticated by Backend.
- **Beacon Binding:** Including `MAINT_SEQ` inside the encrypted payload binds the Node's health response cryptographically to the specific Beacon of that superframe, completely preventing pre-computed or delayed replay attacks.

---

### 3.4 Comprehensive V1 vs V2 Compatibility Matrix Table

The following table provides the definitive provenance and architectural comparison required by parent #127:

| Technical Dimension | Historical V1 BEACON (`0x21`) | Candidate V2 SYNC_BEACON (`0x43`) | Candidate V2 HEALTH_REPLY (`0x44`) | Compatibility Status | Parent #127 Disposition |
|:---|:---|:---|:---|:---|:---|
| **Frame Length** | 28 Bytes fixed | 80 Bytes fixed | 21 Bytes fixed | **Incompatible** | V1 and V2 frames must never be parsed by same codec. |
| **Direction** | Gateway $\to$ Broadcast | Gateway $\to$ Broadcast | Node $\to$ Gateway (Unicast) | Compatible | Preserves broadcast sync + unicast uplink topology. |
| **Cryptographic Primitive**| HMAC-SHA256 (first 16B) | Ed25519 Signature (64B) | AES-128-CCM ($M=8, L=2$) | **Incompatible** | Upgrades group symmetric to asymmetric + pairwise session. |
| **Key Hierarchy** | Shared Group Key `K_BEACON_GROUP`| Gateway Asymmetric Private Key `SK_GW` | Pairwise Derived Key `K_SESSION_UP` | **Incompatible** | Node compromise does not compromise Gateway beacon. |
| **Identity Authentication**| Proves group key possession only | Authenticates unique Gateway origin | Authenticates unique Node origin | **Architectural Fix** | Solves J06 (untrusted Gateway / rogue node beacon forgery). |
| **Anti-Replay Mechanism** | `SF_EPOCH` (4B counter) | Monotonic `MAINT_SEQ` (4B) + Time | `FRAME_COUNTER` (4B) + `MAINT_SEQ` echo | **Enhanced** | Double-binding to maintenance sequence and frame counter. |
| **Time Synchronization** | Superframe counter only | `NETWORK_TIME_MS` (6B, ms anchor) | Echoes received `MAINT_SEQ` | **Enhanced** | Absolute ms anchor enables sub-millisecond disciplining. |
| **Event Acknowledgment** | `ACK_BITMAP` (bytes 8..9, 16 slots)| None (dedicated `DOWN_EVENT_ACK` 0x42)| `PENDING_COUNT` reports backlog | **Architectural Fix** | Decouples beacon from data; events ACKed in own slot. |
| **Schedule Countdown** | `CTRL_FLAGS` bitfield | `FLAGS` bitfield + `SCHED_VER` | None | Preserved | Preserves $3 \to 2 \to 1$ schedule announcement pipeline. |
| **Liveness Verification** | Inferred from lack of error | Inferred from Beacon broadcast | Direct cryptographic proof from Node | **Architectural Fix** | Gateway beacon alone does NOT establish Node alive. |
| **Authority Status** | `OWNER_APPROVED_DESIGN` (V1) | `CANDIDATE_FOR_OWNER_REVIEW` | `CANDIDATE_FOR_OWNER_REVIEW` | **Governance** | Historical V1 locked; V2 pending Owner decision. |

---

## 4. Maintenance Calendar & Superframe Access Policy (Deliverable 2)

### 4.1 Superframe Interleaving Architecture & Symbolic Cadence
To maintain deterministic low latency for Event-only alarms without continuous RF polling overhead, the network operates two distinct classes of superframes:
1. **DATA Superframes ($SF_{\text{DATA}}$):** Contain static TDMA slots 1..15 dedicated to Event-only uplinks (`UP_EVENT` 0x41) and immediate Gateway acknowledgments (`DOWN_EVENT_ACK` 0x42). No periodic telemetry occurs.
2. **Maintenance Superframes ($SF_{\text{MAINT}}$):** Interpolated periodically among DATA superframes to handle network-wide clock sync, gateway authentication, node health reporting, and schedule cutovers.

```
+-------------------------------------------------------------------------------------------------------+
|                                    LONG-TERM TDMA TIMELINE (~300s Cadence)                             |
+-------------------------------------------------------------------------------------------------------+

  SF_MAINT #K           SF_DATA #1            SF_DATA #2                 SF_DATA #M           SF_MAINT #K+1
+-------------+     +-------------+     +-------------+           +-------------+     +-------------+
| DOWN_SYNC_  |     | Slot 1: N1  |     | Slot 1: N1  |           | Slot 1: N1  |     | DOWN_SYNC_  |
| BEACON      |     | Slot 2: N2  |     | Slot 2: N2  |  . . .    | Slot 2: N2  |     | BEACON      |
| + Scheduled |     |   . . .     |     |   . . .     |           |   . . .     |     | + Scheduled |
| HEALTH Slots|     | Slot 15: N15|     | Slot 15: N15|           | Slot 15: N15|     | HEALTH Slots|
+-------------+     +-------------+     +-------------+           +-------------+     +-------------+
|<-- Tsf_m -->|     |<-- Tsf_d -->|     |<-- Tsf_d -->|           |<-- Tsf_d -->|     |<-- Tsf_m -->|
|                                                                                     |
+<----------------------------- TARGET CADENCE ~300 SECONDS ------------------------->+
```

> [!IMPORTANT]
> The target interval of **~300 seconds** (e.g., $M = 29$ DATA superframes of 10 seconds each, followed by 1 Maintenance superframe) is a **symbolic architectural target**. Exact values for $T_{\text{SF\_DATA}}$, $T_{\text{SF\_MAINT}}$, and $M$ remain subject to real physical HIL measurements under **Issue #169**.

### 4.2 Maintenance Superframe Internal Slot Allocation
The Maintenance Superframe is divided into four functional phases:

```
+-------------------------------------------------------------------------------------------------------+
|                                  MAINTENANCE SUPERFRAME INTERNAL STRUCTURE                             |
+-------------------------------------------------------------------------------------------------------+
|  Slot 0: SYNC_BEACON  |  Slots 1 .. N: Scheduled HEALTH  |  Slot N+1: CTRL / JOIN  | Guard Margin     |
|  GW TX -> Nodes RX    |  Assigned Node HEALTH_REPLY      |  Contention Access      | SX1276 Turnaround|
|  (Ed25519, 80 Bytes)  |  (AES-CCM, 21 Bytes each)        |  (UP_JOIN_HELLO, 68B)   | Boundary Buffer  |
+-------------------------------------------------------------------------------------------------------+
```

1. **Slot 0 (Gateway Synchronization Broadcast):**
   - Transceiver State: Gateway in **TX** mode; all synchronized Nodes in **RxSingle** mode.
   - Payload: `DOWN_SYNC_BEACON` (0x43, 80 bytes).
   - Function: Establishes the millisecond time base, confirms schedule version, and initiates countdowns.
2. **Slots 1..N (Dedicated Scheduled Node Health Windows):**
   - Transceiver State: Gateway in **RxContinuous** mode; assigned Node in **TX** mode; all other Nodes in **Sleep / Standby**.
   - Allocation: Nodes 1..N are allocated deterministic, non-overlapping time slices.
   - Payload: `UP_HEALTH_REPLY` (0x44, 21 bytes).
   - Collision-Free Guarantee: No contention occurs; each active node transmits strictly within its assigned health slot.
3. **Slot N+1 (Contention / Control Window):**
   - Transceiver State: Gateway in **RxContinuous** mode.
   - Allocation: Shared contention opportunity for unscheduled nodes.
   - Usage: Unjoined nodes transmit `UP_JOIN_HELLO` (0x45, 68B); joined-but-not-activated nodes transmit `UP_JOIN_READY` (0x49 candidate).
   - Protection: Contention traffic is strictly isolated to Slot N+1 and **never** enters DATA slots 1..15 or HEALTH slots 1..N.
4. **Inter-Slot Guard Margins ($T_{\text{GUARD}}$):**
   - Fixed silence periods inserted between every slot to absorb worst-case crystal drift and transceiver switching overhead.

### 4.3 Node Lifecycle Rights & Operating Modes
Node permissions to access RF slots vary strictly according to formal lifecycle states:

```
               +-----------------------------------------------------------+
               |                     UNPROVISIONED / NVS EMPTY             |
               +-----------------------------------------------------------+
                                             │ Provision K_JOIN, Network ID
                                             ▼
               +-----------------------------------------------------------+
               |                       1. INACTIVE                         |
               | - Radio in Deep Sleep / Standby                           |
               | - No RF transmission permitted anywhere                   |
               +-----------------------------------------------------------+
                                             │ Trigger Join Event
                                             ▼
               +-----------------------------------------------------------+
               |                       2. JOINING                          |
               | - Transmit UP_JOIN_HELLO strictly in Slot N+1 (CTRL)      |
               | - Strictly forbidden from DATA and HEALTH slots           |
               +-----------------------------------------------------------+
                                             │ Receive DOWN_JOIN_FINISH (0x48)
                                             ▼
               +-----------------------------------------------------------+
               |               3. SESSION_READY_NOT_ACTIVE                 |
               | - Pairwise session established; awaits Schedule Staging   |
               | - Transmit UP_JOIN_READY (0x49) in Slot N+1 (CTRL)        |
               | - Strictly forbidden from DATA and HEALTH slots           |
               +-----------------------------------------------------------+
                                             │ Schedule Activation Cutover (K_target)
                                             ▼
               +-----------------------------------------------------------+
               |                       4. ACTIVATED                        |
               | - Receive DOWN_SYNC_BEACON in Slot 0                      |
               | - Transmit UP_HEALTH_REPLY in assigned HEALTH Slot i      |
               | - Transmit UP_EVENT in assigned DATA Slot i               |
               | - Sleep during unassigned slots and idle DATA superframes |
               +-----------------------------------------------------------+
                                             │ >= 3 Consecutive Missed Beacons
                                             ▼
               +-----------------------------------------------------------+
               |                 5. HOLDOVER_DESYNCHRONIZED                |
               | - Clock uncertainty exceeds guard budget                  |
               | - FAIL-CLOSED: Lock DATA and HEALTH transmissions         |
               | - Continuous RX in Slot 0 until authentic Beacon acquired |
               +-----------------------------------------------------------+
```

### 4.4 SX1276 Physical Transceiver Constraints & Half-Duplex Scheduling
The Semtech SX1276 is a single-transceiver half-duplex chip. Firmware scheduling on both Gateway and Node must enforce strict hardware operating invariants:

1. **No Gateway Full-Duplex Fallacy:** The Gateway **cannot** receive uplinks while transmitting `DOWN_SYNC_BEACON`. Any firmware design that schedules Node uplinks during Gateway TX causes total packet loss.
2. **Mode Transition Timings:** Switching the SX1276 between operating modes requires deterministic hardware turnaround intervals:
   - Sleep $\to$ Standby / Synthesizer: $T_{\text{WAKE}} \approx 1.0\text{ ms}$
   - Standby $\to$ TX: $T_{\text{TX\_PREP}} \approx 120\text{ }\mu\text{s}$ (PLL lock + PA ramp)
   - TX $\to$ RX / Standby: $T_{\text{TX\_DONE}} \to \text{RxReady} \approx 50\text{ }\mu\text{s}$
   - RX $\to$ Standby: $T_{\text{RX\_STDBY}} \approx 5\text{ }\mu\text{s}$
3. **Timed Mode Sequencing:**
   - **Gateway Execution:** Enters `FSTX` (Frequency Synthesis TX) $5\text{ ms}$ before Slot 0 boundary; triggers TX at $t=0$; transitions immediately to `RXCONTINUOUS` upon `TxDone` interrupt; remains in RX throughout Slots 1..N+1.
   - **Node Execution:** Node RTC wakes core from Light/Deep Sleep $T_{\text{PRE\_WAKE}}$ before expected Beacon arrival; enters `RXSINGLE` mode; upon `PayloadReady` interrupt, verifies Beacon; transitions to Low Power Standby until its assigned Health slot $t_{\text{HEALTH\_i}}$; ramps to TX; transmits `UP_HEALTH_REPLY`; returns to Sleep.

---

## 5. Clock Synchronization, Drift Margins & Schedule Guards (Deliverable 3)

### 5.1 Drift Budget & Node RxSingle Window Widening
Sensor nodes rely on low-cost internal RC oscillators or quartz crystals for timekeeping between Maintenance Superframes:
- **Typical Quartz Crystal Stability:** $\pm 20\text{ ppm}$ to $\pm 50\text{ ppm}$ over industrial temperature ranges ($-40^\circ\text{C}$ to $+85^\circ\text{C}$).
- **Worst-Case Accumulated Drift Calculation:** Over the target interval $T_{\text{MAINT}} = 300\text{ s}$, a clock drift of $\delta = \pm 50\text{ ppm}$ accumulates a timing uncertainty $\Delta t_{\text{DRIFT}}$ of:
  $$\Delta t_{\text{DRIFT}} = T_{\text{MAINT}} \times \delta_{\text{MAX}} = 300\text{ s} \times \left(50 \times 10^{-6}\right) = \pm 15.0\text{ ms}$$
- **Node Rx Window Widening Requirement:** To guarantee reliable acquisition of `DOWN_SYNC_BEACON` in Slot 0, the Node's `RxSingle` window must open prior to the nominal slot start and remain open past the expected preamble:
  $$T_{\text{RX\_OPEN}} = t_{\text{NOMINAL}} - \Delta t_{\text{DRIFT}} - T_{\text{JITTER}}$$
  $$T_{\text{RX\_TIMEOUT}} = 2 \times \Delta t_{\text{DRIFT}} + T_{\text{PREAMBLE\_TOA}} + T_{\text{MARGIN}}$$
  Where $T_{\text{PREAMBLE\_TOA}}$ is the time required for the SX1276 to detect 8 LoRa preamble symbols ($8 \times \frac{2^{\text{SF}}}{\text{BW}} \approx 8.19\text{ ms}$ at SF7/125kHz), and $T_{\text{JITTER}}$ represents FreeRTOS task scheduling uncertainty.
- **Symbolic Nature:** The exact width of $T_{\text{RX\_TIMEOUT}}$ is symbolic pending real crystal measurement on the ESP32-WROOM-32E under **Issue #169**.

### 5.2 Missed Beacon Holdover & Fail-Closed Desynchronization Lockout
When RF interference, deep fading, or collision causes a Node to miss a `DOWN_SYNC_BEACON`, the Node enters **Holdover Mode**:

```
+-------------------------------------------------------------------------------------------------------+
|                                    MISSED BEACON HOLDOVER STATE MACHINE                               |
+-------------------------------------------------------------------------------------------------------+

        [Receive Valid Beacon]
                  │
                  ▼
        +-------------------+       Miss Beacon #1        +-------------------+
        |  SYNCHRONIZED     | ──────────────────────────> |   HOLDOVER (N=1)  |
        |  Drift <= 15 ms   | <────────────────────────── |   Drift <= 30 ms  |
        |  DATA TX: ALLOWED |    [Receive Valid Beacon]   |  DATA TX: ALLOWED |
        +-------------------+                             +-------------------+
                                                                    │
                                                                    │ Miss Beacon #2
                                                                    ▼
        +-------------------+       Miss Beacon #3        +-------------------+
        |  DESYNCHRONIZED   | <────────────────────────── |   HOLDOVER (N=2)  |
        |  Drift > 45 ms    |                             |   Drift <= 45 ms  |
        |  DATA TX: LOCKED  |                             |  DATA TX: ALLOWED |
        +-------------------+                             +-------------------+
```

1. **Consecutive Miss Counter ($N_{\text{MISSED}}$):** The Node increments $N_{\text{MISSED}}$ on each missed maintenance window.
2. **Tolerance Threshold ($N_{\text{MAX\_HOLDOVER}} = 2$):**
   - For $N_{\text{MISSED}} \le 2$ ($t \le 600\text{ s}$, drift $\le \pm 30\text{ ms}$), the Node remains in Holdover. Because the inter-slot guard interval $T_{\text{GUARD}}$ is designed to absorb up to $\pm 35\text{ ms}$ of skew, the Node is still permitted to transmit in its assigned DATA and HEALTH slots.
3. **Fail-Closed Desynchronization Lockout ($N_{\text{MISSED}} \ge 3$):**
   - When $N_{\text{MISSED}} \ge 3$ ($t \ge 900\text{ s}$, drift $> \pm 45\text{ ms}$), accumulated clock uncertainty risks spilling outside $T_{\text{GUARD}}$ and colliding with adjacent slots.
   - **Mandatory Fail-Closed Lockout:** The Node immediately enters `HOLDOVER_DESYNCHRONIZED` state. All DATA and HEALTH RF transmissions are strictly **locked**. Local event logging continues in durable NVS, but no RF packets are emitted.
4. **Clock Recovery Procedure:** To recover, the Node opens an extended, continuous RX window during subsequent maintenance intervals until an authentic, validated `DOWN_SYNC_BEACON` is acquired. Upon validation, the local clock is hard-reset to `NETWORK_TIME_MS`, $N_{\text{MISSED}}$ is zeroed, and transmissions are unlocked.

### 5.3 Schedule Migration Baseline (Supersedes 3→2→1 Countdown)

> [!IMPORTANT]
> **SUPERSEDED BY OWNER DECISION #208 / PR #206:** The historical `3→2→1` Beacon announcement countdown in `FLAGS[7:6]` has been formally abolished and set to `RESERVED=0`. Schedule migration is an on-demand, single-maintenance transaction: Backend-signed `DOWN_SCHED_PREPARE` (80B) $\to$ per-Node `UP_SCHED_READY` (41B, 0x4C) with 100% verified affected nodes $\to$ Backend-signed `DOWN_SCHED_DECISION` (80B) committing at common $K_{\text{TARGET}}$. Nodes missing COMMIT remain silent (`DATA_TX_DISABLED`) from $K_{\text{TARGET}}$.

1. **Staging & Transaction Reference:** The Backend issues a signed schedule update `DOWN_SCHED_PREPARE` (80B) with target activation superframe $K_{\text{TARGET}}$.
2. **Per-Node Readiness:** Each affected Node responds with `UP_SCHED_READY` (0x4C, 41B) within its designated management slot.
3. **Atomic Cutover at $K_{\text{TARGET}}$:** Upon receiving `DOWN_SCHED_DECISION` (80B) from Backend after 100% verification, Gateway and Nodes atomically commit the new schedule at $K_{\text{TARGET}}$. No 3-beacon countdown horizon is used.
4. **Anti-Confusion Guarantee:** A Node that misses the decision or commits inconsistently locks its DATA slot immediately from $K_{\text{TARGET}}$, preventing stale transmissions.

### 5.4 100%-READY Affected Nodes Policy
Before the Gateway initiates the $3 \to 2 \to 1$ countdown for a schedule modification affecting existing slots:
1. **Durable Proof Requirement:** Every Node whose slot assignment or timing profile changes must have submitted an authenticated `UP_JOIN_READY` (0x49 candidate) or `UP_SCHED_READY` (V1 provenance) acknowledging receipt of the shadow schedule.
2. **No Partial Cutovers:** If even one affected Node fails to confirm readiness (e.g., 9 out of 10 nodes ready), the Gateway **aborts** the countdown. Staging remains pending until Backend issues a timeout or revised schedule.
3. **Fence Superframe:** Nodes commit the target activation boundary to durable NVS before transmitting readiness, ensuring cutover state survives sudden power loss.

---

## 6. Comprehensive Threat Model & Trust Boundaries (Deliverable 4)

### 6.1 Architectural Trust Boundaries
The network security model partitions authority across three trust tiers:

```
+---------------------------------------------------------------------------------------+
|                                    CLOUD / BACKEND                                    |
| - Root of Trust: Secure Database & HSM                                                |
| - Holds master device pre-shared keys (K_JOIN)                                        |
| - Sole authority for TDMA schedule creation, slot assignment, and Gateway leases      |
+---------------------------------------------------------------------------------------+
                                           ▲
                                           │ TLS 1.3 / MQTT 5.0 Mutual Auth
                                           ▼
+---------------------------------------------------------------------------------------+
|                                    GATEWAY RELAY                                      |
| - Semi-trusted edge hardware located in potentially vulnerable physical sites         |
| - Holds Gateway Ed25519 Private Key (SK_GW) for Beacon signing                        |
| - Holds dynamic pairwise session keys (K_SESSION_GW)                                  |
| - DOES NOT hold K_JOIN; cannot forge Backend proofs or decrypt Node NVS               |
+---------------------------------------------------------------------------------------+
                                           ▲
                                           │ LoRa P2P RF (920 - 923 MHz)
                                           ▼
+---------------------------------------------------------------------------------------+
|                                    SENSOR NODE                                        |
| - Low-power edge sensor (ESP32-WROOM-32E)                                             |
| - Holds provisioned K_JOIN in encrypted flash NVS                                     |
| - Holds pinned Gateway Ed25519 Public Key (PK_GW)                                     |
| - Holds ephemeral/dynamic session keys (K_SESSION_UP / K_SESSION_DL)                   |
+---------------------------------------------------------------------------------------+
```

### 6.2 Threat Scenarios & Cryptographic Mitigations

#### Threat 1: Compromised Gateway Edge Hardware
- **Attack Vector:** An adversary physically captures or compromises a Gateway host and extracts all stored secrets (including $\text{SK}_{\text{GW}}$ and session keys).
- **Impact Analysis:** The attacker can broadcast valid `DOWN_SYNC_BEACON` frames and decrypt health replies for currently joined nodes.
- **Mitigation & Boundary Enforcement:**
  1. The Gateway **does not possess** $K_{\text{JOIN}}$. The attacker cannot forge Join handshakes, impersonate the Backend, or compromise root credentials.
  2. The Backend detects anomalous Gateway behavior via MQTT telemetry and revokes the Gateway's signing key identifier (`SIGNER_ID`).
  3. Nodes refuse Beacons with revoked `SIGNER_ID`. Schedule leases expire automatically, causing nodes to transition to fail-closed state.

#### Threat 2: Forged or Replayed SYNC_BEACON Broadcasts
- **Attack Vector:** An on-path RF adversary captures a valid `DOWN_SYNC_BEACON` and replays it at a later time to manipulate node clocks, induce slot collisions, or prevent sleep.
- **Cryptographic Mitigation:**
  1. **Monotonic Sequence Enforcement:** Every Node enforces a strictly monotonic sequence counter rule: $\text{MAINT\_SEQ}_{\text{RX}} > \text{MAINT\_SEQ}_{\text{HIGH\_WATER}}$. Any replayed packet with an equal or lower counter is immediately dropped.
  2. **Timestamp Window Verification:** Nodes verify that `NETWORK_TIME_MS` is reasonably consistent with local elapsed tick counters ($|\Delta t| < \text{TOLERANCE}$). Replays from past days or hours are rejected.
  3. **Ed25519 Signature:** Forged frames lacking a valid signature under $\text{PK}_{\text{GW}}$ fail cryptographic verification before any state machine change occurs.

#### Threat 3: Gateway Public Key Rollover & Key Substitution
- **Attack Vector:** An attacker broadcasts a Beacon containing an arbitrary public key and claims a key rollover.
- **Cryptographic Mitigation:** Nodes store $\text{PK}_{\text{GW}}$ in secure, write-locked NVS. Key rollover requires an authenticated Backend-signed Recovery Grant (`DOWN_AUTH_UPDATE` or V2 equivalent) containing a cryptographic proof derived from $K_{\text{JOIN}}$. A Beacon cannot update its own signing key.

#### Threat 4: Spoofed Node Health Replies
- **Attack Vector:** An attacker transmits rogue `UP_HEALTH_REPLY` frames to trick the Gateway into believing a failed or disconnected Node is healthy.
- **Cryptographic Mitigation:**
  1. **AES-128-CCM Authentication:** Every health reply is authenticated by an 8-byte CCM tag verified against the Node's pairwise $K_{\text{SESSION\_UP}}$.
  2. **Beacon Echo Binding:** The Node includes the current `MAINT_SEQ` in the encrypted payload. A captured health reply from a previous superframe fails the sequence match check at the Gateway.
  3. **Frame Counter Monotonicity:** Uplink frame counters increment monotonically; duplicate counters trigger immediate drop.

#### Threat 5: RF Delay & Relay Manipulation
- **Attack Vector:** An attacker intercepts `DOWN_SYNC_BEACON` over the air and re-transmits it after an intentional delay of several hundred milliseconds to desynchronize node slot timers.
- **Mitigation:** Nodes measure LoRa preamble detection time and enforce a tight `RxSingle` timeout. A Beacon arriving outside the bounded reception window ($T_{\text{RX\_OPEN}} \pm T_{\text{MARGIN}}$) is ignored.

#### Threat 6: RF Jamming & Denial-of-Service
- **Attack Vector:** Broadband RF jamming targeting Slot 0 to suppress `DOWN_SYNC_BEACON`.
- **Mitigation:** Nodes do not panic or transmit randomly. Nodes enter graceful Holdover mode ($N_{\text{MISSED}} = 1, 2$). If jamming persists ($N_{\text{MISSED}} \ge 3$), nodes enter fail-closed silent mode, preserving battery and preventing transmission anarchy.

---

## 7. Parent #127 Handoff & Interface Boundary

### 7.1 Decision Register Handoff Table
In accordance with parent #127 coordination requirements, the technical recommendations of this dossier are summarized below:

| Decision ID | Scope | Candidate Version | Source / Authority | Producer | Consumer | Dependencies | Proposed Rule | Owner Decision Required | Test IDs |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| **DEC-MH-01** | Wire Codepoint | `DOWN_SYNC_BEACON` (0x43, 80B) | Issue #127 (Sketch-01) | Gateway | All Nodes | Ed25519 on ESP-IDF v6.1 | Adopt 80B Ed25519 signed beacon for V2; deprecate V1 28B Group-HMAC. | Approve 80B wire layout and asymmetric signing model. | `TM-MH-01`, `TM-MH-06`, `TM-MH-07` |
| **DEC-MH-02** | Wire Codepoint | `UP_HEALTH_REPLY` (0x44, 21B) | Issue #127 (Sketch-01) | Active Node | Gateway / Backend | AES-128-CCM / Session Key | Adopt 21B AES-CCM health packet echoing `MAINT_SEQ`. | Approve 21B layout and `PENDING_COUNT` reporting. | `TM-MH-02`, `TM-MH-11`, `TM-MH-12` |
| **DEC-MH-03** | MAC Architecture| Maintenance SF Interleaving | Issue #126 / PR #133 | Gateway Scheduler | Node TDMA Engine | Symbolic 300s Cadence | Interpolate 1 Maintenance SF every ~300s among static DATA SFs. | Approve maintenance cadence and slot isolation policy. | `TM-MH-03`, `TM-MH-04`, `TM-MH-19` |
| **DEC-MH-04** | Security / Timing | Holdover Desync Lockout | Issue #178 Dossier | Node Clock Manager | Radio MAC Engine | Physical Drift Data (#169)| Lock DATA TX after $N \ge 3$ consecutive missed beacons. | Approve fail-closed 3-miss lockout threshold. | `TM-MH-16`, `TM-MH-17`, `TM-MH-18` |
| **DEC-MH-05** | Schedule Sync | Schedule Migration Baseline | Issue #208 / PR #206 | Backend / Gateway | Node TDMA Engine | 100%-READY Affected Nodes| Bãi bỏ countdown 3→2→1. Giao dịch PREPARE (80B) → 100% UP_SCHED_READY (41B, 0x4C) → DECISION (80B) COMMIT tại K_TARGET. | SUPERSEDED: Bãi bỏ 3→2→1 countdown; phê duyệt giao dịch 100% READY tại #208. | `TM-MH-21`, `TM-MH-22`, `TM-MH-23` |
| **DEC-MH-06** | Hardware / Timing | SX1276 Half-Duplex Guard | Issue #178 Dossier | Gateway / Node Radio | SX1276 SPI Driver | Physical Turnaround (#169)| Enforce explicit RX/TX turnaround guards; no GW RX during Beacon TX. | Formalize half-duplex slot scheduling constraints. | `TM-MH-19`, `TM-MH-20` |

### 7.2 Explicit Proposed Changes to Normative Parent Contracts
Upon Owner review and approval of this dossier, the following edits will be applied to the three parent #127 files:

1. **`contracts/radio-mac/specification.md`**:
   - Mark V1 `0x21 BEACON` (28B Group-HMAC) as `SUPERSEDED_FOR_V2 / HISTORICAL_PROVENANCE`.
   - Add V2 candidate specification for `0x43 DOWN_SYNC_BEACON` (80B Ed25519 signed).
   - Add V2 candidate specification for `0x44 UP_HEALTH_REPLY` (21B AES-128-CCM).
   - Clarify that `ACK_BITMAP` is obsolete; event acknowledgment is handled strictly by `0x42 DOWN_EVENT_ACK`.
2. **`contracts/radio-mac/tdma-schedule.md`**:
   - Define the structural split between DATA Superframes and Maintenance Superframes.
   - Specify Slot 0 (Beacon), Slots 1..N (Scheduled Health), and Slot N+1 (Contention/Join) structure.
   - Document the 3-miss beacon holdover policy and fail-closed transmission lockout.
3. **`contracts/OPEN_DECISIONS.md`**:
   - Update Decision registers for Beacon format, Ed25519 verification budget, and Maintenance superframe interval.
   - Reference Issue #169 as the blocking prerequisite for freezing numeric timing constants.

### 7.3 Immutability of PR #124 V1 Design Locks
This dossier affirms that all files locked under PR #124 (`contracts/radio-mac/bootstrap-join-v1.md`, `bootstrap-join-gates.md`, `test-vectors/*`, `docs/adr/0002-radio-mac-security-v1.md`) are **unmodified and preserved as historical provenance**. No retrofitting of V2 semantics into V1 contracts is permitted.

---

## 8. Appendix: Status Definitions & Traceability

### 8.1 Status Legend
- `HISTORICAL_PROVENANCE_ONLY`: Approved under prior V1 governance; preserved for auditability; invalid for active V2 runtime.
- `SUPERSEDED_FOR_V2`: Explicitly replaced by V2 architectural patterns (e.g., periodic telemetry, group-HMAC beacon, ACK bitmap).
- `CANDIDATE_FOR_OWNER_REVIEW`: Formally drafted V2 design option; pending Owner and cross-functional technical review.
- `OWNER_APPROVED_DESIGN`: Formally approved design specification; implementation and physical verification remain pending.
- `NOT_VERIFIED`: Design or test specification documented, but unexecuted on physical hardware or testbed.

### 8.2 Document Traceability Matrix
- **AC-1 (Compatibility Matrix & Statuses):** Fully satisfied in Section 3 and Section 3.4.
- **AC-2 (Scheduling, Clock, 100%-READY, Half-Duplex, #169 Dependency):** Fully satisfied in Sections 4, 5, and 1.1.
- **AC-3 (Threat Model & Security Trust Boundaries):** Fully satisfied in Section 6.
- **AC-4 (Parent Contract Changes & PR #124 Immutability):** Fully satisfied in Section 7.
- **AC-5 (Host G0, Independent Auditor, Human Review):** Addressed in accompanying PR and test matrix document.
