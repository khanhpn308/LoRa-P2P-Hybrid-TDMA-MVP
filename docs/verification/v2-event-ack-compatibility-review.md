# LP2P V2 Event DATA & Durable ACK: Compatibility Review, Protocol Invariants & Cryptographic Dossier

**Document ID:** `DOC-VERIF-V2-EVENT-ACK-001`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent / Tracking:** Issue #177 (Agent 1), Umbrella #125, Child Architecture #126, Integration Gate #127.
**Related Documents:** [ADR-0001 (Hybrid TDMA)](../adr/0001-hybrid-tdma.md), [ADR-0002 (MQTT 5.0)](../adr/0002-mqtt-5.md), [ADR-0003 (ESP-IDF v6.1)](../adr/0003-esp-idf-v6-1.md), [ADR-0004 (Timing Budget)](../adr/0004-theoretical-timing-guard-budget.md), [Radio MAC Specification](../../contracts/radio-mac/specification.md), [TDMA Schedule Contract](../../contracts/radio-mac/tdma-schedule.md), [Open Decisions](../../contracts/OPEN_DECISIONS.md), [MQTT Topics](../../contracts/mqtt/topics.md), [MQTT Semantic Rules](../../contracts/mqtt/semantic-rules.md), [Session Key Security](../../contracts/mqtt/session-key-security.md), [RF Timing Methodology](rf-timing-methodology-and-harness.md), [Join V2 Ready Activation](join-v2-ready-tdma-activation-design.md).

---

## 1. Executive Summary & Purpose

In accordance with Owner Decision #137 and the approved architectural transition (#125, #126), the LoRa-P2P-Hybrid-TDMA-MVP system has transitioned from a legacy continuous telemetry and contention-based alert architecture to a deterministic **Local Alarm + Event-Only Remote Logging + Static DATA TDMA + Maintenance Superframe** operational model.

Under this architecture:
1. **Local Alarm Autonomy:** Sensor violation detection triggers immediate, autonomous local alarm actuation (buzzer, LED, siren, relay) on the ESP32 Node without awaiting LoRa RF availability or TDMA slot boundaries.
2. **Event-Only RF Plane:** The radio sub-system transmits application data strictly when an authenticated event occurs. Periodic application telemetry (`UP_TELEMETRY`, periodic reporting mode `SET_PERIODIC_MODE`) is completely superseded.
3. **Static DATA TDMA Plane:** Event transmission occurs strictly within the Node's exclusively allocated static DATA slot in the TDMA superframe. Priority contention sub-slots (PCSS), CAD-based channel contention, and ad-hoc priority interrupts are retired as primary access paths.
4. **Durable In-Slot ACK & Bounded Retries:** Transmission follows a strict `Node Event TX → Gateway Durable Acceptance → Authenticated ACK RX` sequence within the assigned slot. Unacknowledged events retry exclusively in the Node's own subsequent assigned static DATA slot.
5. **Decoupled Event Identity:** The Gateway is the sole authoritative source of globally unique business `event_id` values published to Backend MQTT. The Node maintains an internal, durable, monotonic `EVENT_REF` within its local FIFO for retry correlation and local acknowledgment tracking, but does not assert global event IDs.

```
+----------------------------------------------------------------------------------------------------+
|                                      EVENT LIFECYCLE FLOW                                          |
|                                                                                                    |
|  [ Sensor Violation ]                                                                              |
|           │                                                                                        |
|           ├───► (Immediate Autonomous Local Alarm: GPIO / Buzzer / LED)                            |
|           │                                                                                        |
|           ▼                                                                                        |
|  [ Push to Persistent Bounded NVS FIFO ] (Assigns Node-Local EVENT_REF)                            |
|           │                                                                                        |
|           ▼                                                                                        |
|  [ Await Assigned Static DATA Slot ] ──► Evaluate 8-Fold Fail-Closed DATA TX Guards                |
|           │                                                                                        |
|           ▼ (All Guards PASS)                                                                      |
|  [ Transmit Candidate UP_EVENT (0x41) ] ───────────────► [ Gateway SX1276 RX ]                    |
|                                                                  │                                 |
|                                                                  ▼                                 |
|                                                     [ Verify AES-CCM-8 & Replay ]                  |
|                                                                  │                                 |
|                                                                  ▼                                 |
|                                                     [ Durable Dedup Check ]                        |
|                                                     - New: Persist WAL -> Mint event_id            |
|                                                     - Duplicate: Skip Mint -> Idempotent ACK       |
|                                                                  │                                 |
|                                                                  ▼                                 |
|  [ Receive Candidate DOWN_EVENT_ACK (0x42) ] ◄────────── [ Transmit In-Slot ACK ]                  |
|           │                                                                                        |
|           ├──► ACK Validated: Pop/Commit FIFO Head                                                 |
|           └──► ACK Lost/Corrupted: Retain in FIFO -> Retry in Next Own Slot (Up to Max Retries)    |
+----------------------------------------------------------------------------------------------------+
```

> [!IMPORTANT]
> This document represents a **design dossier and compatibility review** delivered by Agent 1 under Issue #177 (linked to Parent #127). It does NOT constitute authorization to modify production wire schemas, database structures, or firmware implementations without subsequent approved follow-up PRs. V2 codepoints, byte layouts, and cryptographic primitives remain `CANDIDATE` / `OPEN_DECISION` until formal Owner and cross-functional sign-off.

---

## 2. V1 vs V2 Event/ACK Compatibility Registry

### 2.1 Protocol Registry & Authority Classification

The table below reconciles historical V1 codepoints (PR #124, `contracts/radio-mac/specification.md`) with candidate V2 codepoints proposed under #127.

| Message Name | V1 Code | V1 Size | V2 Code | V2 Size | Direction | Authority / Status | Architectural Disposition |
|---|:---:|:---:|:---:|:---:|:---:|---|---|
| `BEACON` / `DOWN_SYNC_BEACON` | `0x01`/`0x21` | 14B / 28B | `0x43` | 80B | GW → Broadcast | `CANDIDATE` (Agent 2, #178) | V1 28B Group-HMAC Beacon with `ACK_BITMAP` superseded; V2 proposes 80B Ed25519 signed Beacon. |
| `SCHED_ANNOUNCE` / `DOWN_SCHED_CTRL` | `0x02`/`0x22` | Variable | `0x49` | TBD | GW → Node/BC | `OPEN_DECISION` | Sched distribution migrating to dedicated control frames; no silent byte reuse. |
| `DATA_TELEMETRY` | `0x03`/`0x23`/`0x26` | 22B / 12B | — | — | Node → GW | **`SUPERSEDED`** | **Retired.** Periodic reporting deleted from operational baseline. Codepoints preserved in archive. |
| `PRIORITY_ALERT` | `0x04`/`0x24` | 22B / 12B | — | — | Node → GW | **`SUPERSEDED`** | **Retired.** PCSS contention access eliminated; replaced by Local Alarm + static in-slot `UP_EVENT`. |
| `ACK_PACKET` / `DOWN_EVENT_ACK` | `0x05`/`0x25` | 10B / 12B | `0x42` | 19B | GW → Node | `CANDIDATE` (Agent 1, #177) | Unauthenticated V1 ACK retired; V2 introduces authenticated in-slot unicast ACK with AES-CCM-8. |
| `CMD_DOWNLINK` | `0x06`/`0x26` | Variable | `0x4B` | TBD | GW → Node | `OPEN_DECISION` | Retained under separate command security review. |
| `UP_JOIN_REQUEST` / `UP_JOIN_HELLO` | `0x07`/`0x27` | 35B | `0x45` | 68B | Node → GW | `OWNER_APPROVED_DESIGN` | V1 35B retired; V2 68B locked by Owner in #127 (Agent 3, #182). |
| `DOWN_JOIN_ACCEPT` / `DOWN_JOIN_GRANT` | `0x08`/`0x28` | 22B/57B | `0x46` | 66B | GW → Node | `OWNER_APPROVED_DESIGN` | V1 retired; V2 66B locked by Owner in #127 (Agent 3, #182). |
| `UP_JOIN_CONFIRM` / `UP_JOIN_KEY_CONFIRM`| `0x29` | 19B | `0x47` | 31B | Node → GW | `OWNER_APPROVED_DESIGN` | V1 19B retired; V2 31B locked by Owner in #127 (Agent 3, #182). |
| `DOWN_JOIN_FINISH` | — | — | `0x48` | 31B | GW → Node | `OWNER_APPROVED_DESIGN` | New in V2; locked by Owner in #127 (Agent 3, #182). |
| `UP_JOIN_READY` | `0x2A` | 19B | `0x49` (cand) | 31B | Node → GW | `CANDIDATE` (Agent 3, #136/#182) | Post-join activation trigger proposed in #136. |
| `UP_HEALTH_REPLY` | — | — | `0x44` | 21B | Node → GW | `CANDIDATE` (Agent 2, #178) | Periodic health reply within Maintenance Superframe (~300s). |
| `UP_EVENT` | — | — | `0x41` | 26B | Node → GW | `CANDIDATE` (Agent 1, #177) | Dedicated event transmission in assigned static DATA slot. |

> [!CAUTION]
> Historical V1 codepoints (`0x01`–`0x08` and `0x21`–`0x2C`) MUST NOT be silently reused or repurposed for V2. The V2 protocol uses a distinct version space (`VER_TYPE` high 3 bits = `2` $\to$ range `0x40`–`0x5F`).

---

### 2.2 Candidate V2 Unicast Common Header Layout (7 Bytes)

All V2 unicast frames (`UP_EVENT`, `DOWN_EVENT_ACK`, `UP_HEALTH_REPLY`) utilize an identical, authenticated 7-byte header serving as Additional Authenticated Data (AAD) for AES-128-CCM:

| Offset | Field | Type | Encoding | Description |
|:---:|---|:---:|:---:|---|
| 0 | `VER_TYPE` | `uint8_t` | Big-Endian | High 3 bits: Protocol Version (`010b` = 2). Low 5 bits: Packet Type (`0x01` $\to$ `0x41` for UP_EVENT; `0x02` $\to$ `0x42` for DOWN_EVENT_ACK). |
| 1 | `NODE_ID` | `uint8_t` | Big-Endian | Gateway-scoped Node identifier (`1`..`254`). `0x00` (Gateway) and `0xFF` (Broadcast) are invalid. |
| 2 | `SESSION_SEL` | `uint8_t` | Big-Endian | Session selector (`1`..`254`) identifying the active cryptographic session keypair. |
| 3–6 | `FRAME_COUNTER` | `uint32_t` | Big-Endian | Strictly monotonic frame counter per session. High bit reserved. Range: `1`..`0xFFFFFFFE`. |

#### Bitfield Layout of `VER_TYPE` (Byte 0)
```text
  7       6       5       4       3       2       1       0
+-------+-------+-------+-------+-------+-------+-------+-------+
|      VERSION (3 bits) |               TYPE (5 bits)           |
|      0       1       0|   0       0       0       0       1   |  --> 0x41 (UP_EVENT)
|      0       1       0|   0       0       0       1       0   |  --> 0x42 (DOWN_EVENT_ACK)
+-------+-------+-------+-------+-------+-------+-------+-------+
```

---

### 2.3 Candidate V2 `UP_EVENT` Frame Specification (26 Bytes)

- **Packet Type:** `0x41` (`UP_EVENT`)
- **Producer:** Sensor Node (ESP32-WROOM-32E)
- **Consumer:** Gateway Radio Host
- **Total Physical Length:** 26 octets (excluding LoRa preamble, explicit header, and PHY CRC)
- **Security Profile:** Authenticated & Encrypted via AES-128-CCM-8 (RFC 3610 / NIST SP 800-38C)

| Byte Offsets | Field Name | Width | Type / Endianness | Cryptographic Treatment | Constraints & Values |
|:---:|---|:---:|:---:|:---:|---|
| **0..6** | **Unicast Header** | **7B** | Struct | **AAD (Authenticated, Plaintext)** | `VER_TYPE=0x41`, assigned `NODE_ID`, active `SESSION_SEL`, monotonic `FRAME_COUNTER`. |
| 7..10 | `EVENT_REF` | 4B | `uint32_t` BE | Encrypted (AES-CTR) | Node-local persistent FIFO monotonic sequence number. Range: `1`..`0xFFFFFFFF`. |
| 11..14 | `EVENT_TIME` | 4B | `uint32_t` BE | Encrypted (AES-CTR) | Seconds since network epoch or relative time. Sentinel `0xFFFFFFFF` if clock unsynchronized. |
| 15 | `EVENT_CODE` | 1B | `uint8_t` | Encrypted (AES-CTR) | Application event type (`0x01` Door Open, `0x02` Tamper, `0x03` Vibration, `0x04` Smoke). |
| 16..17 | `EVENT_VALUE` | 2B | `int16_t` BE | Encrypted (AES-CTR) | Signed raw sensor reading / severity score / analog threshold. |
| **18..25** | **CCM Authentication Tag**| **8B** | Binary | **Integrity / Authenticity Tag** | Truncated CBC-MAC tag ($M=8$) covering AAD (bytes 0..6) and Plaintext (bytes 7..17). |

---

### 2.4 Candidate V2 `DOWN_EVENT_ACK` Frame Specification (19 Bytes)

- **Packet Type:** `0x42` (`DOWN_EVENT_ACK`)
- **Producer:** Gateway Radio Host
- **Consumer:** Sensor Node
- **Total Physical Length:** 19 octets (excluding LoRa preamble, explicit header, and PHY CRC)
- **Security Profile:** Authenticated & Encrypted via AES-128-CCM-8

| Byte Offsets | Field Name | Width | Type / Endianness | Cryptographic Treatment | Constraints & Values |
|:---:|---|:---:|:---:|:---:|---|
| **0..6** | **Unicast Header** | **7B** | Struct | **AAD (Authenticated, Plaintext)** | `VER_TYPE=0x42`, matching `NODE_ID`, matching `SESSION_SEL`, Gateway downlink `FRAME_COUNTER`. |
| 7..10 | `EVENT_REF` | 4B | `uint32_t` BE | Encrypted (AES-CTR) | Exact Node-local `EVENT_REF` being acknowledged. |
| **11..18** | **CCM Authentication Tag**| **8B** | Binary | **Integrity / Authenticity Tag** | Truncated CBC-MAC tag ($M=8$) covering AAD (bytes 0..6) and Plaintext (bytes 7..10). |

---

### 2.5 Theoretical Semtech SX1276 Time-on-Air (ToA) Calculations

Calculations adhere strictly to the Semtech SX1276 datasheet formula verified under [rf-timing-methodology-and-harness.md](rf-timing-methodology-and-harness.md):
- **RF Parameters:** $BW = 125\text{ kHz}$, Coding Rate $CR = 1$ ($4/5$), Preamble $N_{pre} = 8$, Header = Explicit ($H=0$), Payload CRC = Enabled ($CRC=1$). Low Data Rate Optimization $DE=1$ for $SF \ge 11$, else $DE=0$.

$$\text{ToA} = T_{preamble} + N_{payload} \times T_s$$

$$N_{payload} = 8 + \max\left( \left\lceil \frac{8 \cdot PL - 4 \cdot SF + 28 + 16 \cdot CRC - 20 \cdot H}{4 \cdot (SF - 2 \cdot DE)} \right\rceil \cdot (CR + 4),\, 0 \right)$$

| Packet Type | Length ($PL$) | SF | $T_s$ (ms) | $T_{preamble}$ (ms) | $N_{payload}$ (sym) | $T_{payload}$ (ms) | **Total ToA (ms)** | Total ToA (µs) |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **`UP_EVENT`** | **26 B** | **SF7** | 1.024 | 12.544 | 48 | 49.152 | **61.696** | 61,696 |
| `UP_EVENT` | 26 B | **SF8** | 2.048 | 25.088 | 43 | 88.064 | **113.152** | 113,152 |
| `UP_EVENT` | 26 B | **SF9** | 4.096 | 50.176 | 38 | 155.648 | **205.824** | 205,824 |
| `UP_EVENT` | 26 B | **SF10** | 8.192 | 100.352 | 38 | 311.296 | **411.648** | 411,648 |
| `UP_EVENT` | 26 B | **SF12** | 32.768 | 401.408 | 38 | 1245.184 | **1646.592** | 1,646,592 |
| **`DOWN_EVENT_ACK`**| **19 B** | **SF7** | 1.024 | 12.544 | 38 | 38.912 | **51.456** | 51,456 |
| `DOWN_EVENT_ACK`| 19 B | **SF8** | 2.048 | 25.088 | 38 | 77.824 | **102.912** | 102,912 |
| `DOWN_EVENT_ACK`| 19 B | **SF9** | 4.096 | 50.176 | 33 | 135.168 | **185.344** | 185,344 |
| `DOWN_EVENT_ACK`| 19 B | **SF10** | 8.192 | 100.352 | 28 | 229.376 | **329.728** | 329,728 |
| `DOWN_EVENT_ACK`| 19 B | **SF12** | 32.768 | 401.408 | 28 | 917.504 | **1318.912** | 1,318,912 |

---

### 2.6 Static DATA Slot Feasibility & Round-Trip Budget

In a static TDMA slot, the total slot duration $T_{slot}$ must accommodate leading guard, uplink transmission, transceiver turnaround, downlink ACK, and trailing guard:

$$T_{slot} \ge \tau_{lead} + \text{ToA}(UP\_EVENT) + \tau_{turnaround} + \text{ToA}(DOWN\_EVENT\_ACK) + \tau_{trail}$$

Assuming conservative MVP parameters: $\tau_{lead} = 25\text{ ms}$, $\tau_{turnaround} = 20\text{ ms}$ (SPI commands, radio state transition from TX to RX, PLL lock), $\tau_{trail} = 25\text{ ms}$:

1. **SF7 Profile ($125\text{ kHz}$):**
   $$T_{RT} = 25\text{ ms} + 61.696\text{ ms} + 20\text{ ms} + 51.456\text{ ms} + 25\text{ ms} = \mathbf{183.152\text{ ms}}$$
   *Evaluation:* Fits comfortably within the legacy 400 ms slot budget with $216.848\text{ ms}$ margin.
2. **SF8 Profile ($125\text{ kHz}$):**
   $$T_{RT} = 25\text{ ms} + 113.152\text{ ms} + 20\text{ ms} + 102.912\text{ ms} + 25\text{ ms} = \mathbf{286.064\text{ ms}}$$
   *Evaluation:* Fits within the 400 ms slot budget with $113.936\text{ ms}$ margin.
3. **SF9 Profile ($125\text{ kHz}$):**
   $$T_{RT} = 25\text{ ms} + 205.824\text{ ms} + 20\text{ ms} + 185.344\text{ ms} + 25\text{ ms} = \mathbf{441.168\text{ ms}}$$
   *Evaluation:* **EXCEEDS the 400 ms slot budget!**
4. **SF10 / SF12 Profile:**
   Exceeds 400 ms by an order of magnitude. Round-trip in-slot ACK at SF10 ($816.376\text{ ms}$) or SF12 ($3040.504\text{ ms}$) is physically impossible within a 400 ms slot.

> [!WARNING]
> **Blocking Timing Consequence for Parent #127 & RF Owner (#169):** Profile `P-10S-15`'s nominal 400 ms static slot duration is valid ONLY for SF7 and SF8. If SF9 or higher is required for link margin, the TDMA slot duration must be re-profiled (e.g. to 500–600 ms), or an asynchronous multi-superframe ACK mechanism must be standardized.

---

## 3. Sequence, State Invariants & Event Lifecycle

### 3.1 Persistent Bounded Node Event FIFO

The Sensor Node enforces a bounded, wear-leveled FIFO queue located in non-volatile storage (NVS / RTC slow memory):

1. **Capacity Limit:** Fixed capacity $N_{max}$ (MVP baseline: 64 records). Memory allocation is static; dynamic heap allocation during event insertion is strictly prohibited.
2. **Record Structure:**
   ```c
   typedef struct {
       uint32_t event_ref;      // Monotonic local reference (persisted high-water)
       uint32_t event_time;     // Timestamp or sentinel 0xFFFFFFFF
       uint8_t  event_code;     // Application event code
       int16_t  event_value;    // Sensor reading
       uint8_t  retry_count;    // Number of unacknowledged RF attempts
       uint8_t  state;          // PENDING_TX, AWAITING_ACK, ACKED, RECOVERY_HOLD
   } node_event_record_t;
   ```
3. **FIFO Insertion:** When a sensor violation occurs:
   - Local alarm actuation executes immediately in ISR / high-priority task.
   - An event record is committed to NVS with state `PENDING_TX`, incrementing the durable `EVENT_REF` counter.
   - If FIFO is full ($N == N_{max}$), the Node executes the **Fail-Closed Retention Policy**:
     - The event is quarantined, an internal error counter `err_fifo_overflow` is incremented.
     - New critical security events overwrite oldest non-critical records ONLY IF explicitly authorized; default policy is reject new insertion and maintain alarm latching.
4. **FIFO Consumption:** The head record is popped from the queue ONLY when a cryptographically validated `DOWN_EVENT_ACK` matching the head record's `EVENT_REF` is received.

---

### 3.2 Decoupled Identity & Gateway-Authoritative Dedup Map

A critical invariant approved in #125/#126 is the strict separation between the Node's local event reference and the Gateway's business event identity:
- **Node-Local Reference (`EVENT_REF`):** 32-bit unsigned integer allocated monotonically by the Node. It has NO global uniqueness guarantees across different nodes or across factory wipes.
- **Gateway Business Identity (`event_id`):** The globally authoritative identifier minted by the Gateway:
  $$\text{event\_id} = \langle \text{gateway\_id} \rangle : \langle \text{gateway\_epoch} \rangle : \langle \text{event\_seq} \rangle$$
  (where `gateway_epoch` is a UUID minted on Gateway boot, and `event_seq` is an unsigned 64-bit monotonic counter).

#### Gateway Durable Dedup Table
To prevent duplicate MQTT publication when an ACK is lost on the downlink RF path, the Gateway maintains a durable SQLite / WAL table:

```sql
CREATE TABLE gateway_event_dedup (
    node_id INTEGER NOT NULL,
    session_sel INTEGER NOT NULL,
    event_ref INTEGER NOT NULL,
    frame_counter INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    persisted_at TIMESTAMP NOT NULL,
    PRIMARY KEY (node_id, session_sel, event_ref)
);
```

#### Gateway Ingestion & Idempotent ACK Rules
When Gateway SX1276 receives a valid `UP_EVENT`:
1. **Validation:** Gateway verifies AES-CCM-8 tag and confirms `FRAME_COUNTER` is valid (not replayed).
2. **Lookup:** Gateway queries `gateway_event_dedup` for `(NODE_ID, SESSION_SEL, EVENT_REF)`.
3. **Branch A (New Event):**
   - Mint new `event_id` and assign `observed_at = NOW_UTC()`.
   - Atomically insert record into `gateway_event_dedup` and enqueue to local MQTT publish outbox.
   - Commit transaction to disk (fsync / WAL flush).
   - Formulate and transmit `DOWN_EVENT_ACK` carrying `EVENT_REF` within the slot ACK turnaround window.
4. **Branch B (Duplicate Retransmission):**
   - The lookup hits an existing record.
   - The Gateway **DOES NOT** mint a new `event_id` and **DOES NOT** publish a duplicate MQTT message.
   - The Gateway immediately formulates and transmits `DOWN_EVENT_ACK` using the matching `EVENT_REF`. This guarantees idempotent acknowledgment even under lossy downlink RF conditions.

```
+---------------+                                   +---------------+                                   +---------------+
|     NODE      |                                   |    GATEWAY    |                                   |  BACKEND DB   |
+---------------+                                   +---------------+                                   +---------------+
        |                                                   |                                                   |
        | [Assigned DATA Slot]                              |                                                   |
        | UP_EVENT(ref=101, cnt=1) ────────────────────────►|                                                   |
        |                                                   | [Verify CCM-8 & Counter]                          |
        |                                                   | [Atomic WAL Commit: mint event_id]                |
        |                                                   | [Enqueue MQTT Publish] ──────────────────────────►| (Single DB
        |                                                   |                                                   |  Ingest)
        |                    X [DOWN_EVENT_ACK Lost on RF] ─|                                                   |
        |                                                   |                                                   |
        | [Next Superframe: Retry in Own Slot]              |                                                   |
        | UP_EVENT(ref=101, cnt=2 or retry) ───────────────►|                                                   |
        |                                                   | [Hit Dedup Map: (node, sess, 101)]                |
        |                                                   | [DO NOT Publish to MQTT]                          |
        |                                                   | [Resend DOWN_EVENT_ACK(ref=101)]                  |
        |<──────────────────────────────────────────────────|                                                   |
        |                                                   |                                                   |
        | [Validate ACK -> Pop FIFO]                        |                                                   |
        ▼                                                   ▼                                                   ▼
```

---

### 3.3 Own-Slot Retry Protocol & Backoff Elimination

1. **No Ad-Hoc Backoff:** When `DOWN_EVENT_ACK` is not received, the Node MUST NOT execute exponential backoff, random channel hopping, or CAD-based contention.
2. **Own-Slot Retention:** The unacknowledged event remains at the head of the FIFO. The Node sleeps / enters low-power standby until its assigned static DATA slot in the subsequent TDMA superframe.
3. **Retry Counter (`retry_count`):**
   - Incremented by 1 for each failed transmission.
   - Maximum retries: $N_{retry\_max}$ (default: 5 attempts).
4. **Retry Exhaustion:**
   - When `retry_count == N_{retry\_max}`, the Node transitions the event to `RECOVERY_HOLD`.
   - The Node halts regular RF transmission for this event to preserve local airtime and battery budget.
   - The event is preserved in NVS; it is NEVER silently discarded. Recovery occurs during the next Maintenance Superframe or operator intervention.

---

### 3.4 Node Reboot & Rekey Reconciliation

1. **Volatile Key Loss:** On Node reset or brownout, volatile RAM holding ephemeral session keys (`K_SESSION_UP`, `K_SESSION_DOWN`) and ephemeral nonces is zeroized.
2. **FIFO Preservation:** The NVS FIFO remains intact, retaining pending `EVENT_REF` records.
3. **Mandatory Post-Reboot Join:** The Node cannot transmit pending events immediately. It must execute the complete V2 Join Handshake (`UP_JOIN_HELLO` 0x45 $\to$ `DOWN_JOIN_GRANT` 0x46 $\to$ `UP_JOIN_KEY_CONFIRM` 0x47 $\to$ `DOWN_JOIN_FINISH` 0x48), followed by `UP_JOIN_READY` (0x49) and TDMA schedule activation.
4. **New Session Binding:**
   - A new `SESSION_SEL` is assigned by Backend/Gateway.
   - `FRAME_COUNTER` starts freshly from 1 under new session keys.
   - When the Node reaches `NODE_ACTIVE_DATA_ELIGIBLE`, it resumes transmitting pending events from its FIFO.
   - Events are transmitted using the *new* `SESSION_SEL` and *new* `FRAME_COUNTER`, while preserving the original `EVENT_REF`, `EVENT_TIME`, `EVENT_CODE`, and `EVENT_VALUE`.
   - The Gateway dedup map indexes by `(NODE_ID, SESSION_SEL, EVENT_REF)`. Because `SESSION_SEL` is fresh, there is no collision with historical sessions.

---

## 4. Nonce Architecture & Cryptographic Security

### 4.1 AES-128-CCM Primitives & Constraints

V2 Unicast packets employ AES-128-CCM (Counter with CBC-MAC) specified in NIST SP 800-38C and RFC 3610:
- **Block Cipher:** AES-128 (16-byte block size).
- **Authentication Tag Length ($M$):** 8 octets (CCM-8). Provides $2^{-64}$ forgery protection, optimal for resource-constrained 125 kHz LoRa PHY.
- **Length Field Size ($L$):** 2 octets (accommodating payload lengths up to $2^{16}-1$ octets; actual payloads are $\le 26$ octets).
- **Nonce Length ($N = 15 - L$):** Exactly 13 octets.

---

### 4.2 Nonce Composition & Uniqueness Invariants

To guarantee absolute nonce uniqueness across all packets encrypted under the same session key, the 13-byte nonce is constructed deterministically:

| Offset | Component | Width | Source | Description |
|:---:|---|:---:|---|---|
| 0..7 | `SESSION_NONCE_PREFIX` | 8B | HKDF session derivation | Ephemeral pseudo-random salt derived during V2 Join key exchange. |
| 8 | `DIRECTION_BYTE` | 1B | Constant | `0x01` for Uplink (Node $\to$ Gateway); `0x02` for Downlink (Gateway $\to$ Node). |
| 9..12 | `FRAME_COUNTER` | 4B | Monotonic Counter | Big-Endian 32-bit integer matching header `FRAME_COUNTER`. |

```text
  0                   1                   2                   3
  0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |               SESSION_NONCE_PREFIX (Bytes 0..3)               |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |               SESSION_NONCE_PREFIX (Bytes 4..7)               |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 |   DIR (0x01)  |              FRAME_COUNTER (Bytes 0..2)       |
 +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
 | FRAME_CTR (3) |
 +-+-+-+-+-+-+-+-+
```

#### Nonce Security Rules:
1. **Direction Separation:** The `DIRECTION_BYTE` guarantees that a Gateway transmitting a downlink frame can NEVER reuse the same nonce as a Node transmitting an uplink frame, even if both devices coincidentally use the identical `FRAME_COUNTER` value.
2. **Strict Monotonicity:** Every new plaintext encryption MUST increment `FRAME_COUNTER` by at least 1.
3. **No Nonce Reuse:** Under NO circumstances may the same `(K_SESSION, NONCE)` tuple be used to encrypt different plaintexts.
4. **Retransmission Integrity:** When a Node retransmits an unacknowledged `UP_EVENT` within the same session, it transmits the **byte-identical cached ciphertext**. It DOES NOT generate new ciphertext with the same counter.

---

### 4.3 Counter Exhaustion & Rollback Mitigation

1. **Counter Bounds:** `FRAME_COUNTER` operates in the range $[1,\, 0\text{xFFFFFFFE}]$.
2. **Exhaustion Threshold:** If `FRAME_COUNTER >= 0xFFFFFF00` (within 256 packets of saturation), the Node flags `WARN_SESSION_COUNTER_EXHAUSTION` in subsequent health frames.
3. **Fail-Closed Saturation:** If `FRAME_COUNTER == 0xFFFFFFFE`, the session is irreversibly dead. The Node MUST fail closed: zeroize session keys, revoke DATA TX eligibility, and trigger a fresh V2 Join. It is strictly forbidden to wrap counter back to 0 under the active key.
4. **Anti-Rollback Persistence:** On clean sleep / deep sleep, the Node flushes its counter high-water mark to RTC memory / NVS. If a counter rollback is detected on boot (stored counter < previously observed counter), the Node panics, wipes session keys, and forces re-join.

---

### 4.4 Cryptographic Threat Matrix & Mitigations

| Threat ID | Threat Vector | Attack Scenario | Protocol Mitigation |
|---|---|---|---|
| **TH-01** | **Eavesdropping / Sniffing** | Attacker captures RF packets to inspect sensor data (`EVENT_CODE`, `EVENT_VALUE`). | Plaintext payload is encrypted with AES-128-CTR using session key $K_{SESSION\_UP}$. |
| **TH-02** | **Bit-Flipping / Tampering** | Attacker modifies `EVENT_CODE` or `EVENT_VALUE` in flight. | 8-byte CBC-MAC tag covers ciphertext and 7-byte header (AAD). Validation failure drops packet. |
| **TH-03** | **Replay Attack** | Attacker retransmits a captured valid `UP_EVENT` to trigger false alarms. | Gateway checks `FRAME_COUNTER` against high-water mark; counter $\le$ last_seen is dropped. |
| **TH-04** | **Replayed ACK Injection** | Attacker captures `DOWN_EVENT_ACK` and injects it to cause Node to drop events. | ACK is encrypted and authenticated with $K_{SESSION\_DOWN}$; binds matching `EVENT_REF` and monotonic downlink counter. |
| **TH-05** | **Rogue Gateway Impersonation** | Attacker attempts to acknowledge Node events without session keys. | Attacker lacks $K_{SESSION\_DOWN}$ (derived from ECDH shared secret $Z$); cannot compute valid CCM-8 tag. |
| **TH-06** | **Rogue Node Impersonation** | Attacker injects fraudulent events using a stolen `NODE_ID`. | Attacker lacks $K_{SESSION\_UP}$; Gateway drops frame on tag verification failure. |
| **TH-07** | **Direction Reflection** | Attacker reflects Node's `UP_EVENT` back to Node as a pseudo-downlink. | `DIRECTION_BYTE` (`0x01` vs `0x02`) causes nonce mismatch; decryption fails. |
| **TH-08** | **Cross-Session Replay** | Attacker replays frame from session $S_1$ during session $S_2$. | `SESSION_SEL` mismatch in header, and distinct session keys cause CCM tag failure. |

---

## 5. OWN-SLOT Acceptance Guards (8-Fold Fail-Closed Gate)

Before the SX1276 radio transitions from standby/sleep to transmit mode for an `UP_EVENT`, the firmware MUST evaluate eight mandatory guards. If ANY guard evaluates to `FALSE`, transmission is inhibited (`FAIL_CLOSED`), the failure reason code is logged, and the event remains queued in FIFO.

```text
+-----------------------------------------------------------------------------------+
|                     8-FOLD FAIL-CLOSED DATA TX GUARD PIPELINE                     |
|                                                                                   |
|  [ G1: JOIN_ACTIVE ]        Node has completed V2 Join & READY activation?        |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G2: SESSION_VALID ]      Session keys active, not expired, counter valid?      |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G3: SLOT_OWNERSHIP ]     Current slot S is assigned exclusively to this Node?  |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G4: TIMING_WINDOW ]      Current hardware timer within [T_start+lead, T_tx]?   |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G5: CLOCK_SYNC ]         Lost Beacons < 3, estimated drift <= 25 ms?           |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G6: AIRTIME_DUTY ]       Local 1.0% duty cycle token bucket >= Packet ToA?     |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G7: HALF_DUPLEX ]        SX1276 idle, no RX active, no Maintenance collision?  |
|            │                                                                      |
|            ▼ (TRUE)                                                               |
|  [ G8: RF_SAFETY ]          Physical RF sign-off (#169) complete & power valid?   |
|            │                                                                      |
|            ▼ (ALL TRUE)                                                           |
|       [ EXECUTE TX ] ──► Radio transitions to FSTX -> TX                          |
+-----------------------------------------------------------------------------------+
```

### Guard Detailed Specifications

1. **`GUARD_JOIN_ACTIVE` (Gate 1):**
   - *Condition:* `node_state == NODE_ACTIVE_DATA_ELIGIBLE`.
   - *Failure Code:* `ERR_GUARD_NOT_JOINED`.
   - *Behavior:* Inhibit TX. Node in `UNJOINED`, `JOINING`, or `SESSION_READY_NOT_ACTIVE` cannot transmit DATA.
2. **`GUARD_SESSION_VALID` (Gate 2):**
   - *Condition:* $K_{SESSION\_UP}$ loaded, session lease unexpired, `FRAME_COUNTER < 0xFFFFFFFE`.
   - *Failure Code:* `ERR_GUARD_SESSION_INVALID`.
   - *Behavior:* Inhibit TX. Trigger session renegotiation if counter saturated.
3. **`GUARD_SLOT_OWNERSHIP` (Gate 3):**
   - *Condition:* Active schedule table indicates `slot_map[current_slot] == local_node_id`.
   - *Failure Code:* `ERR_GUARD_UNASSIGNED_SLOT`.
   - *Behavior:* Inhibit TX. Node cannot transmit in unassigned slots or slots belonging to peers.
4. **`GUARD_TIMING_WINDOW` (Gate 4):**
   - *Condition:* Slot offset timer $t_{offset} \in [\tau_{lead},\, \tau_{lead} + \text{ToA}_{budget}]$. For 400 ms slot: $t_{offset} \in [25\text{ ms},\, 125\text{ ms}]$.
   - *Failure Code:* `ERR_GUARD_TIMING_WINDOW_VIOLATION`.
   - *Behavior:* Inhibit TX. If timer ISR jitter delays execution beyond 125 ms, abort transmission to prevent slot overlap.
5. **`GUARD_CLOCK_SYNC` (Gate 5):**
   - *Condition:* Consecutive lost Beacons $N_{lost} < 3$, and estimated cumulative drift $\tau_{drift} \le 25\text{ ms}$.
   - *Failure Code:* `ERR_GUARD_CLOCK_DESYNC`.
   - *Behavior:* Inhibit TX. Node transitions to `RECOVERY_HOLD`, listening for Beacon sync.
6. **`GUARD_AIRTIME_DUTY` (Gate 6):**
   - *Condition:* Local airtime accumulator verifies hourly duty cycle $\le 1.0\%$ (Node legal cap), and token bucket $\ge 61.696\text{ ms}$ (SF7 ToA).
   - *Failure Code:* `ERR_GUARD_AIRTIME_EXHAUSTED`.
   - *Behavior:* Inhibit TX. Retain event in FIFO until airtime budget replenishes.
7. **`GUARD_HALF_DUPLEX` (Gate 7):**
   - *Condition:* Radio state is `STANDBY` or `CAD_CLEAN`. Not actively receiving packet, not in Maintenance Superframe boundary.
   - *Failure Code:* `ERR_GUARD_HALF_DUPLEX_COLLISION`.
   - *Behavior:* Abort TX. Protect transceiver from switching while RX FIFO is filling.
8. **`GUARD_RF_SAFETY` (Gate 8):**
   - *Condition:* RF physical test sign-off flag active (`#169_RF_SIGNED_OFF == TRUE`), channel within VN920 regulatory plan (920.250–922.750 MHz), TX power $\le +14\text{ dBm}$.
   - *Failure Code:* `ERR_GUARD_RF_UNVERIFIED`.
   - *Behavior:* Inhibit TX in production builds until physical evidence exists.

---

## 6. Legacy V1 & PR #124 Conflict Reconciliation Matrix

The table below catalogs every historical conflict in PR #124 (`contracts/radio-mac/specification.md`, `tdma-schedule.md`, `docs/adr/0002-radio-mac-security-v1.md`) and defines the exact proposed amendment for Parent #127.

| Section / File in PR #124 | Legacy Wording / Concept | Conflict with #125/#126 Architecture | Proposed Replacement for Parent #127 |
|---|---|---|---|
| `contracts/radio-mac/specification.md` §2 | `DATA_TELEMETRY (0x03)` periodic 12B reporting. | Application telemetry is obsolete; system is Event-Only. | Mark `0x03`/`0x23` as `SUPERSEDED_HISTORICAL`. Add candidate `UP_EVENT (0x41)`. |
| `contracts/radio-mac/specification.md` §2 | `PRIORITY_ALERT (0x04)` in PCSS using CAD and backoff. | Contention access and CAD backoff eliminated; alarms are local, remote reporting is in-slot. | Mark `0x04`/`0x24` as `SUPERSEDED_HISTORICAL`. Document Local Alarm + static DATA slot model. |
| `contracts/radio-mac/specification.md` §2 | `ACK_BITMAP` (15 bits) in Beacon bytes 8–9. | Beacon does not acknowledge data; dedicated in-slot `DOWN_EVENT_ACK (0x42)` takes over. | Mark `ACK_BITMAP` as `SUPERSEDED`. Maintain historical Beacon record for V1 provenance. |
| `contracts/radio-mac/specification.md` §2 | Candidate 8B header + CRC16 without authentication. | Lacks authenticity and replay protection. | Replace candidate envelope with V2 7B Unicast Header + AES-128-CCM-8. |
| `contracts/radio-mac/tdma-schedule.md` §1 | Profile `P-10S-15` (5 subframes $\times$ 2000 ms, 400 ms PCSS each). | Subframe PCSS slots are obsolete; 400 ms slot invalid for SF9+. | Mark `P-10S-15` as `OBSOLETE_CANDIDATE`. Propose Event DATA + Maintenance SF profile pending #169. |
| `contracts/radio-mac/tdma-schedule.md` §1 | "ACK_BITMAP reflects previous cycle success". | Event ACK is immediate in-slot, not delayed bitmap in Beacon. | Remove `ACK_BITMAP` references from active schedule execution rules. |
| `docs/adr/0002-radio-mac-security-v1.md` | Group-HMAC 28B Beacon and V1 19B READY. | Group-HMAC lacks asymmetric Gateway authenticity; V2 uses Ed25519 or separate key. | Retain ADR-0002 as historical V1 design approval; create V2 security ADR under #127. |
| `contracts/radio-mac/bootstrap-join-v1.md` | 35B Join Request / 22B Accept. | V2 Join uses 68B Hello / 66B Grant / 31B Confirm / 31B Finish. | Retain as V1 Bootstrap archive; do not overwrite with V2 definitions. |
| `contracts/mqtt/semantic-rules.md` §2 | Ambiguous Node-origin vs Gateway-origin `event_id`. | Gateway is sole authoritative minter of `event_id`. | Formulate canonical rule: Gateway assigns `event_id`, Node carries `EVENT_REF`. |

---

## 7. Stable Cross-Agent Handshake & Interface Request Table

To ensure zero overlap and seamless integration across parallel child issues (#177, #178, #182) and Parent #127, the formal interface contracts are registered below:

| Decision ID | Target Agent | Scope | Candidate Version | Source / Authority | Producer | Consumer | Dependencies | Proposed Rule | Owner Decision Required | Test IDs |
|---|:---:|---|:---:|---|:---:|:---:|---|---|---|:---:|
| **IF-REQ-01** | **Agent 3 (#182)** | Session Key Material & Nonce Salt | V2 | #127, Comment 6628525270 | Agent 3 (Join) | Agent 1 (Data) | Join completion (`DOWN_JOIN_FINISH` 0x48) | Provide 16B $K_{SESSION\_UP}$, 16B $K_{SESSION\_DOWN}$, and 8B `SESSION_NONCE_PREFIX` upon activation. | Formal approval of HKDF expansion labels for unicast keys. | TM-EVT-16, TM-EVT-19 |
| **IF-REQ-02** | **Agent 3 (#182)** | Node Activation State Handoff | V2 | #136, #182 | Agent 3 (READY) | Agent 1 (Data) | Schedule Activation at Superframe $K_{target}$ | Transition Node to `NODE_ACTIVE_DATA_ELIGIBLE` and assign active `SESSION_SEL`. | Confirm 100%-READY countdown horizon $3 \to 2 \to 1$. | TM-EVT-01, TM-EVT-23 |
| **IF-REQ-03** | **Agent 2 (#178)** | Superframe Time & Clock Anchor | V2 | #127, Comment 6623475221 | Agent 2 (Beacon) | Agent 1 (Data) | Periodic `DOWN_SYNC_BEACON` (0x43) | Beacon provides authoritative network time anchor to calibrate local slot offset timer. | Approval of 80B Ed25519 signed Beacon vs alternative HMAC. | TM-EVT-27 |
| **IF-REQ-04** | **Agent 2 (#178)** | Maintenance SF Interval & Pending Count | V2 | #125, #178 | Agent 1 (Data) | Agent 2 (Health) | Health Reply (`UP_HEALTH_REPLY` 0x44) | Agent 1 exposes `fifo_pending_count` to Agent 2 for inclusion in `UP_HEALTH_REPLY`. | Confirm ~300s Maintenance superframe cadence. | TM-EVT-22 |
| **IF-REQ-05** | **Parent (#127)** | Codepoint Freeze & AES-CCM-8 Tag | V2 | #127, #177 | Agent 1 (Dossier) | Parent (#127) | Security Review & Cryptographic Sign-Off | Lock `0x41` (`UP_EVENT`) and `0x42` (`DOWN_EVENT_ACK`) with 8-byte tag. | Owner sign-off on 26B/19B wire frames and CCM-8. | TM-EVT-10, TM-EVT-11 |
| **IF-REQ-06** | **Parent (#127)** | Slot Timing Sign-off with #169 | V2 | #11, #169, #177 | Agent 1 (ToA) | Parent (#127) | Physical RF Bench Measurements (#169) | Reconcile 400 ms slot limit with SF9+ round-trip ToA requirement. | Sign-off on supported SF matrix (SF7–SF8 vs expanded slots). | TM-EVT-28 |

---

## 8. Open Decisions & Blocking Technical Item Inventory for Parent #127

The following items remain `OPEN_DECISION` or `BLOCKED_FOR_WIRE_IMPLEMENTATION` and MUST be resolved by Owner and cross-functional technical leads before normative contract freeze:

1. **DEC-127-01 (Wire Codepoint Lock):** Formal Owner design lock for `0x41` (`UP_EVENT`, 26B) and `0x42` (`DOWN_EVENT_ACK`, 19B). Currently classified as `CANDIDATE`.
2. **DEC-127-02 (CCM Tag Length vs Airtime):** Confirm whether 8-byte authentication tag ($M=8$) provides sufficient security margin for application data, or if 16-byte tag ($M=16$, adding 8B ToA) is required.
3. **DEC-127-03 (Static Slot Duration vs Spreading Factor):** Physical ToA calculations prove that 400 ms slots CANNOT support in-slot ACK at SF9 or higher. Owner must decide:
   - *Option A:* Restrict MVP operational deployment to SF7 and SF8 only.
   - *Option B:* Expand static DATA slot duration to 500–600 ms, reducing total slots per superframe.
   - *Option C:* Adopt asynchronous next-superframe ACK for SF9+.
4. **DEC-127-04 (FIFO Overflow Eviction Policy):** Under prolonged network outage, should the Node FIFO strictly reject new alarms (`FAIL_CLOSED_REJECT`), or evict oldest non-critical records (`RING_BUFFER_DROP_OLDEST`)?
5. **DEC-127-05 (Gateway WAL Persistence SLA):** Define minimum durable write latency for Gateway SQLite/WAL before issuing RF ACK to guarantee zero lost events under edge power loss.
