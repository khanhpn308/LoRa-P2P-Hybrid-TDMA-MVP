# LP2P V2 Diagnostic Loss Metrics & Management Message Design Proposal

**Document ID:** `DOC-VERIF-V2-DIAG-METRICS-001`  
**Status:** `DESIGN_PROPOSED / OWNER_WIRE_APPROVAL_PENDING` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`  
**Owner Decision Reference:** `DEC-MH-08` (Approved Technical Direction / Planned Not Implemented)  
**Parent Tracking:** Issue #204 (V2 Diagnostic Loss Metrics Design), PR #205  
**Cross-Issue References:** #127 (G2 Radio MAC Contract Gate), #201 / Merged PR #202 (Timing & Health Consistency Disposition), #128 (MQTT/API Contracts), #131 (Node/Gateway Firmware Execution), #18 / #132 (Backend Go Storage & Ingest), #130 (Simulator & Test Automation), #169 (Physical RF Timing & HIL Measurement Sign-off), #117 (Cross-Layer Verification), #175 (HIL Power-Loss Fault Injection), #179 (Airtime Policy & Regulatory Analysis)  
**Owning Authorities:** Radio MAC Architecture, Security Architecture, Gateway & Node Firmware, Backend Go Ingest  

---

## 1. Executive Summary & Source-Bound Governance Boundaries

### 1.1 Context & Problem Statement
Under the approved architecture of LoRa-P2P Hybrid TDMA MVP V2 ([ADR-0001](../adr/0001-hybrid-tdma.md), [ADR-0002](../adr/0002-mqtt-5.md), PR #133 under #125), the network operates in an **Event-Only Static TDMA** model supplemented by periodically interpolated **Maintenance Superframes** (~300 s nominal cadence).

In merged PR #190 / PR #198, the periodic node health message `UP_HEALTH_REPLY` (`0x44`, 21 octets) was approved under Owner Decision `DEC-MH-02`. During the audit of Issue #201 (reconciled in PR #202), two critical architectural truths were formally codified:
1. **Total Byte Budget Saturation:** The 21-byte frame budget of `UP_HEALTH_REPLY` is completely exhausted ($7\text{B Header} + 6\text{B Plaintext} + 8\text{B CCM Tag} = 21\text{B}$).
2. **Semantic Decoupling:** The field `PENDING_COUNT` (1B, uint8) represents exclusively the *instantaneous volatile queue depth* of unacknowledged events in the Node's FIFO ($0..255$). It **does not and cannot** represent cumulative dropped events.
3. **Queue Overflow Policy (`DEC-127-04`):** When a Node's NVS FIFO overflows during prolonged network disconnection or Gateway outage, the Node executes the approved `RING_BUFFER_DROP_OLDEST` policy, overwriting the oldest queued alarm to preserve fresher events while mandating the persistent increment of a durable `DROPPED_EVENT_COUNT` in non-volatile flash (NVS).

Under **Owner Decision `DEC-MH-08`** (ratified in Issue #201 / PR #202), the Project Owner directed:
> *"Preserve 100% of the active `UP_HEALTH_REPLY` (0x44, 21B) wire frame to protect the 56.6 ms (SF7) airtime budget. Approve the technical direction of utilizing a **separate versioned diagnostic/management message** to report durable loss metrics (`DROPPED_EVENT_COUNT`), retry statistics, and battery metrics. The identifier `0x4A` is strictly a candidate packet type (CANDIDATE_PACKET_TYPE_ONLY). Do not emit, assign, or commit wire formats in existing production contracts until formal design review is completed."*

### 1.2 Approved Design Boundaries (Strict Invariants)
In strict accordance with project authority (`AGENTS.md`, `contracts/OPEN_DECISIONS.md`, and Issue #204 acceptance criteria):
- **Design-Only Scope:** This document is an architectural and contract design proposal. It authorizes **zero** production code changes, **zero** modifications to frozen V2 Radio MAC contracts, and **zero** live RF transmissions.
- **Uncompromised `UP_HEALTH_REPLY` (0x44):** The 21-byte layout of `UP_HEALTH_REPLY` remains 100% frozen. No fields are redefined, truncated, or overloaded.
- **Strict Data Semantics:** `PENDING_COUNT` is volatile queue depth; `DROPPED_EVENT_COUNT` is durable cumulative dropped event count maintained in NVS flash.
- **Separate Versioned Message:** Diagnostic metrics must be carried in a separately versioned management message.
- **Candidate Status of `0x4A`:** Codepoint `0x4A` (symbolically designated `UP_DIAG_METRICS`) is strictly `NOT_APPROVED_WIRE` (candidate packet type only), pending Owner wire approval.
- **Zero RF Chaos:** No unscheduled transmissions, no priority contention (PCSS), no CAD backoff, and no periodic application business telemetry are permitted.
- **All Numeric Timing is Symbolic & Unverified:** All slot durations (400 ms candidate example), guard intervals, holdover limits, and cadence periods are non-normative engineering targets, qualified as `THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY` and blocked on physical Hardware-in-the-Loop (HIL) sign-off under **Issue #169**.

---

## 2. Source-Bound Design Requirements

| Requirement ID | Domain | Requirement Statement & Authority Source | Verification Gate |
|:---|:---|:---|:---|
| **REQ-DIAG-01** | Semantics | Node must maintain `DROPPED_EVENT_COUNT` as a durable cumulative counter incremented strictly upon FIFO drop events (`RING_BUFFER_DROP_OLDEST` under `DEC-127-04`). | Gate G2 / Firmware Unit |
| **REQ-DIAG-02** | Framing | `UP_HEALTH_REPLY` (0x44, 21B) must not be altered, expanded, or bit-stuffed (`DEC-MH-02`, `DEC-MH-08`). | Gate G2 / Contract Assert |
| **REQ-DIAG-03** | Framing | Diagnostic metrics must be encapsulated within a distinct, versioned Unicast uplink message following the standard V2 7-byte Unicast Header format (`DEC-127-01`, `DEC-SEC-01`). | Gate G2 / Wire Codec |
| **REQ-DIAG-04** | Security | Diagnostic uplinks must be authenticated and encrypted using AES-128-CCM ($M=8$, $L=2$, Nonce=13B) with the active session key $K_{\text{SESSION\_UP}}$ (`DEC-SEC-01`, `DEC-127-02`). | Gate G2 / Crypto Golden Vector |
| **REQ-DIAG-05** | Security | Nonce generation must guarantee strict uniqueness: $N = \text{SESSION\_NONCE\_PREFIX}_{\text{UP}}[0..7] \parallel 0\text{x}01 \parallel \text{FRAME\_COUNTER}[0..3]$ without nonce reuse across reboots or retries (`DEC-SEC-01`, RFC 3610). | Gate G2 / Security Audit |
| **REQ-DIAG-06** | TDMA Access | Diagnostic message transmission must occur exclusively within authorized, pre-scheduled TDMA opportunities (no unscheduled CAD/CSMA bursts) (`ADR-0001`, `DEC-127-03`). | Gate G1 / TDMA Schedule |
| **REQ-DIAG-07** | Priority | Event transmission (`UP_EVENT` 0x41) and health monitoring (`UP_HEALTH_REPLY` 0x44) have absolute priority over diagnostic reporting. Diagnostic reporting must never delay alarm delivery. | Gate G2 / Firmware Logic |
| **REQ-DIAG-08** | RF Regulatory | Diagnostic reporting must be designed to operate within regional duty-cycle limits ($\le 1.0\%$ for nodes under VN920, `D03 §1`). Per-packet ToA does not establish regulatory compliance; full scheduled airtime analysis across rolling 1-hour windows is required. | Gate G1 / RF Regulation (#179, #169) |
| **REQ-DIAG-09** | Idempotency | Gateway and Backend must handle duplicate or retransmitted diagnostic packets idempotently without double-counting drops or corrupting rate calculators (`ADR-0002`, `contracts/mqtt/topics.md`). | Gate G4 / Backend Ingest |
| **REQ-DIAG-10** | Timing Handoff | All slot allocations, guard times, and time-on-air boundaries are marked `PROPOSED / NOT_VERIFIED`, requiring empirical sign-off from Issue #169. | Gate G3 / HIL #169 |

---

## 3. Payload and Data Semantics Analysis (Analysis A)

### 3.1 Dropped Event Counter Semantics & Sizing

```
  Queue State Transition:
  +-----------------------------------------------------------------------------------+
  |                                LOCAL NVS FIFO QUEUE                               |
  +-----------------------------------------------------------------------------------+
  Normal Operation:       [Event #1] [Event #2] [Event #3] ... [Event #N]  (N < 255)
                          --> PENDING_COUNT = N, DROPPED_EVENT_COUNT = Unchanged

  Buffer Full (FIFO=255): [Event #1] [Event #2] ... [Event #254] [Event #255]
                          --> PENDING_COUNT = 255

  New Alert Arrives:      [Event #1] is DISCARDED (RING_BUFFER_DROP_OLDEST)
                          [Event #2] ... [Event #255] [Event #256] stored
                          --> PENDING_COUNT = 255 (Remains saturated)
                          --> DROPPED_EVENT_COUNT = DROPPED_EVENT_COUNT + 1 (NVS commit)
  +-----------------------------------------------------------------------------------+
```

#### Counter Width Evaluation (u16 vs u24 vs u32)
1. **Candidate 16-Bit Unsigned Integer (`uint16_t`, 2 Bytes):**
   - Maximum representable value: $65,535$.
   - **Overflow Analysis:** In an industrial monitoring facility experiencing sustained RF interference or gateway hardware failure, a vibration/thermal sensor generating an alert every 2 seconds will generate 43,200 events in 24 hours. A 16-bit counter will rollover within **36.4 hours** ($1.5$ days).
   - **Assessment:** High risk of undetected multi-rollover and ambiguity during prolonged outages.
2. **Candidate 24-Bit Unsigned Integer (`uint24_t`, 3 Bytes):**
   - Maximum representable value: $16,777,215$.
   - **Overflow Analysis:** At 1 event per second, rollover occurs after **194.1 days**.
   - **Assessment:** Sufficient headroom, but awkward non-power-of-two alignment on 32-bit MCU architectures (ESP32 Xtensa LX6).
3. **Candidate 32-Bit Unsigned Integer (`uint32_t`, 4 Bytes):**
   - Maximum representable value: $4,294,967,295$.
   - **Overflow Analysis:** At 10 events per second continuous, rollover occurs after **13.6 years** (exceeding typical 10-year device field lifetime).
   - **Alignment & Microcontroller Cost:** Native 32-bit register on ESP32; zero byte-packing penalty in RAM/NVS; natural big-endian wire alignment.
   - **Byte Cost Delta:** Only 2 bytes more than `uint16_t`.

### 3.2 Retry Statistics Semantics Reconciled with Event Retention
Under the approved architecture ([ADR-0001](../adr/0001-hybrid-tdma.md), `DEC-127-04`, and `specification.md` Section 5.2):
- **Event Retention Guarantee:** Sensor events are **retained in the FIFO until acknowledged** by `DOWN_EVENT_ACK` (0x42) or overwritten when the FIFO is 100% full (`RING_BUFFER_DROP_OLDEST`).
- **No Discard on Retry Exhaustion:** There is **no** MAC policy where an event is discarded simply because a retry attempt counter expired. Such an event remains in the FIFO and is retransmitted in subsequent assigned static DATA slots.
- **Field Semantics:**
  - `TX_ATTEMPT_COUNT` (16-bit unsigned, BE): Cumulative count of physical LoRa transmission bursts initiated by the MAC layer for application data events.
  - `TX_UNACKED_COUNT` (8-bit or 16-bit unsigned): Count of transmission cycles that concluded without receiving a valid `DOWN_EVENT_ACK` within the slot turnaround window. This directly measures channel loss and RF fading without implying event deletion.
  - Event loss is **exclusively** tracked by `DROPPED_EVENT_COUNT` when buffer saturation occurs.

### 3.3 Battery Metrics Semantics
- **`BATTERY_MV` (16-bit unsigned, millivolts):** Direct ADC calibrated voltage ($0..5000\text{ mV}$).
  - *Advantage:* Absolute physical measurement; immune to battery discharge curve interpretation errors on edge nodes; allows Backend to apply chemistry-specific state-of-charge (SoC) curves (e.g. LiSOCl2 vs LiFePO4).
- **`BATTERY_RAW` (8-bit compressed):** Linear encoding $V_{\text{mv}} = 1800 + (\text{val} \times 10)$ covering $1.80\text{V} - 4.35\text{V}$ in $10\text{ mV}$ steps.
  - *Advantage:* Saves 1 byte over the air.
  - *Disadvantage:* Loss of sub-10mV resolution; requires non-standard decompression logic in Gateway/Backend.

### 3.4 Counter Persistence, NVS Transaction Ordering & Power-Loss Windows

#### Technical Analysis of Flash Writes and Brownout Prohibition
> [!CAUTION]
> **Prohibition of Flash Commits in Brownout ISR:** Proposing synchronous NOR flash writes inside a brownout interrupt service routine (ISR) without dedicated hardware energy storage is **strictly rejected**.
> - In ESP-IDF, SPI NOR flash programming/erase operations require multi-millisecond hold times ($T_{\text{prog}} \sim 0.5 - 3.0\text{ ms}$, $T_{\text{erase}} \sim 20 - 100\text{ ms}$) and draw peak currents of $30 - 50\text{ mA}$.
> - During a brownout event on typical decoupled power rails ($C_{\text{decouple}} \le 100\text{ }\mu\text{F}$), the rail voltage collapses within tens to hundreds of microseconds.
> - Attempting flash writes when $V_{\text{DD}}$ drops below the flash chip minimum operating voltage ($2.7\text{ V}$) results in partial bit programming, sector corruption, or unrecoverable NVS filesystem panics. Furthermore, ESP-IDF SPI flash drivers disable the cache and use mutexes that cannot be executed from an ISR context.
> - Consequently, flash writes in a brownout ISR are **forbidden** unless backed by empirical hardware bench evidence with calibrated supercapacitors and power-fail early-warning circuitry.

```
+---------------------------------------------------------------------------------------------------+
|                        NVS TRANSACTION ORDERING & POWER-LOSS VULNERABILITY                        |
+---------------------------------------------------------------------------------------------------+

  Model A: Transaction-Ordered Synchronous Commit (NOT_VERIFIED pending HIL #175)
    FIFO Full Alert Arrives ---> Step 1: Execute NVS Write/Commit for DROPPED_EVENT_COUNT
                                 Step 2: On NVS Success, advance FIFO ring buffer drop pointer
                                 Step 3: Insert new event into FIFO
    - Note on Power Loss: Absolute zero-power-loss window cannot be guaranteed without HIL proof;
      if power fails mid-SPI transaction, in-flight NVS entry is invalidated by CRC, reverting
      counter to last fully committed state on reboot.
    - Trade-off: Flash write latency (~2-5ms) in event drop path; relies on ESP-IDF wear-leveling.

  Model B: Slot-Synchronized Flush (Bounded Vulnerability Window)
    Drops increment RAM counter ---> TDMA Slot Wake-up ---> Commit dirty counter to NVS ---> Sleep
    |<------------------- Bounded Vulnerability Window (T_batch) ------------------>|
    - If power collapses during T_batch, up to K uncommitted drops in RAM are lost.
    - Upon reboot, counter resumes from last committed NVS value without corruption.
```

#### Transaction Ordering & Atomicity Requirements
1. **Transaction Ordering Rule:** The increment of `DROPPED_EVENT_COUNT` in NVS must strictly precede the advancement of the FIFO tail pointer (`RING_BUFFER_DROP_OLDEST`). If the flash write fails, the drop must fail closed or record an uncommitted drop flag.
2. **Flash Wear Reality:** ESP-IDF NVS uses log-structured key-value append operations across pages. Writing a 32-bit integer appends a 32-byte record rather than erasing a sector. With typical 16–32 KB NVS partitions, thousands of writes are distributed across pages. Furthermore, FIFO saturation occurs only during prolonged network outages, not continuously in normal operation.
3. **Formal Gating Prerequisite:** Both Model A and Model B durability guarantees remain **`NOT_VERIFIED pending HIL power-loss fault-injection tests (Issue #175)`**.

### 3.5 Qualified Backend Ingest, Monotonic Deduplication & Rollover Handling

The Backend storage and ingest layer must handle duplicate packets, out-of-order deliveries, integer rollovers, node reboots, and session changes **without inventing lost-event totals or introducing phantom spikes**:

```
+---------------------------------------------------------------------------------------------------+
|                             BACKEND TIME-SERIES INGEST ARCHITECTURE                               |
+---------------------------------------------------------------------------------------------------+

  Incoming MQTT Packet ---> Ingest Deduplication:
                            UNIQUE (gateway_id, node_id, session_sel, frame_counter)
                            ON CONFLICT DO NOTHING
                                     │
                                     ▼
                            Append-Only Time-Series Ledger:
                            INSERT INTO node_diagnostic_reports (...)
                                     │
                                     ▼
                            Monotonic Sequence Alignment & Delta Evaluation:
                            Order reports by canonical sequence (session_sel, frame_counter, maint_seq)
```

#### Qualified Delta, Rollover & Discontinuity Rules
Let $R_k$ be the current report with counter $C_k$, and $R_{k-1}$ be the immediately preceding sequential report with counter $C_{k-1}$:

1. **Rule 1 (Monotonic Progress, $C_k \ge C_{k-1}$):**
   $$\Delta_{\text{loss}} = C_k - C_{k-1}$$
   Durable dropped event increment is recorded cleanly.
2. **Rule 2 (Qualified Integer Rollover):**
   If counter width is $W$ ($2^{16}$ for Candidate 1, $2^{32}$ for Candidate 2) and $C_k < C_{k-1}$:
   - **Candidate 2 (32-bit):** Rollover requires $4.29 \times 10^9$ drops ($\sim 13.6$ years at 10 drops/s continuous). A counter decrease in Candidate 2 is treated as an abnormal reset unless elapsed operating time and loss rates mathematically support multi-year rollover.
   - **Candidate 1 (16-bit):** Single rollover ($65,536$) occurs in 36.4 hours at 0.5 drops/s. Rollover delta $\Delta_{\text{loss}} = (W - C_{k-1}) + C_k$ is accepted **only if** elapsed offline time $\Delta T$ is bounded such that multi-wrap is mathematically impossible ($\Delta T < 2 \times T_{\text{min\_wrap}}$) AND $C_{k-1} > (W - \text{MARGIN}_{\text{wrap}})$.
   - **Multi-Wrap Ambiguity:** If the elapsed offline duration allows more than one possible wrap-around, calculating a single wrap would invent false totals. Under multi-wrap ambiguity, the system flags `AMBIGUOUS_MULTI_WRAP`, sets the delta to `UNKNOWN`, and establishes $C_k$ as the new baseline.
3. **Rule 3 (Counter Discontinuity / Reset / Flash Wipe / Identity Reuse):**
   If $C_k < C_{k-1}$ and rollover conditions are not met:
   - This indicates a hardware reset with flash wipe, firmware reflash, or node identity collision.
   - **Strict Non-Invention Principle:** The Backend **must NOT assume rollover or invent synthetic loss totals**.
   - Action: Flag a `DIAG_METRIC_DISCONTINUITY` audit record in the database. Establish $C_k$ as the new baseline ($C_{\text{baseline}} = C_k$). Mark the interval delta as `DISCONTINUOUS / UNVERIFIED`.
4. **Rule 4 (Out-of-Order Delivery & Offline Buffer Replay):**
   - Because all records are ingested into an append-only time-series ledger, out-of-order packets are placed in their proper sequential position by `(session_sel, frame_counter)`. Interval deltas are computed across the canonical sequence, completely preventing phantom spikes.
5. **Rule 5 (Session Change Handoff):**
   - When a Node re-joins (`SESSION_SEL` increments), `FRAME_COUNTER` resets to $0$.
   - Since `DROPPED_EVENT_COUNT` is a **device-lifetime durable counter** stored in NVS, $C_k$ remains monotonic across session changes ($C_{\text{new\_session}} \ge C_{\text{old\_session}}$).
   - If an NVS wipe accompanied the re-join, Rule 3 applies.

---

## 4. Candidate Design Proposals (Deliverable 2)

We propose three distinct candidate designs representing different architectural trade-offs:
- **Candidate 1 (Compact 23-Byte):** Minimal airtime overhead, optimal for low-duty industrial nodes.
- **Candidate 2 (Extended 29-Byte):** Comprehensive metrics, full 32-bit precision, optimal for predictive maintenance.
- **Candidate 3 (TLV Multiplexed 29-Byte / 33-Byte):** Future-proof modularity, extensible sub-typing.

### 4.1 Candidate 1: Compact Diagnostic Frame (`UP_DIAG_METRICS_COMPACT`)

#### Wire Format Overview (23 Bytes Fixed)
Consists of the standard 7-byte V2 Unicast Header (Plaintext AAD), an 8-byte encrypted payload, and an 8-byte AES-128-CCM authentication tag.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   VER_TYPE    |    NODE_ID    |  SESSION_SEL  |               |
|  (0x4A cand.) |   (1 Byte)    |   (1 Byte)    |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+               +
|                         FRAME_COUNTER                         |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           MAINT_SEQ                           |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      DROPPED_EVENT_COUNT      |TX_UNACKED_CNT |  BATTERY_RAW  |
|      (2 Bytes, uint16 BE)     |   (1 Byte)    |   (1 Byte)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
+                        AES-128-CCM TAG                        +
|                           (8 Bytes)                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### Field Specification Table (Candidate 1)
| Offset | Field Name | Width | Type / Encoding | Description & Validation Rule |
|:---:|:---|:---:|:---|:---|
| **0..6** | **Unicast Header (AAD)** | **7B** | **Plaintext** | **Standard V2 Unicast Header.** |
| 0 | `VER_TYPE` | 1B | `uint8` (`0x4A` cand.) | Protocol V2 (`0b010`), packet type candidate `UP_DIAG_METRICS` (`0b01010`). |
| 1 | `NODE_ID` | 1B | `uint8` | Unique node address (`0x01`..`0xFE`). |
| 2 | `SESSION_SEL` | 1B | `uint8` | Session key identifier matching $K_{\text{SESSION\_UP}}$. |
| 3..6 | `FRAME_COUNTER` | 4B | `uint32_t` BE | Strictly increasing per-session counter. Anti-replay protection. |
| **7..14**| **Encrypted Payload** | **8B** | **Ciphertext** | **AES-128-CTR encrypted plaintext payload.** |
| 7..10 | `MAINT_SEQ` | 4B | `uint32_t` BE | Echo of current Maintenance Superframe sequence counter from Beacon. |
| 11..12 | `DROPPED_EVENT_COUNT` | 2B | `uint16_t` BE | Cumulative dropped events count ($0..65535$). |
| 13 | `TX_UNACKED_COUNT` | 1B | `uint8_t` | MAC transmission attempts in DATA slots ending without ACK ($0..255$). |
| 14 | `BATTERY_RAW` | 1B | `uint8_t` | Compressed voltage: $V = 1800 + (\text{val} \times 10)\text{ mV}$ ($1.80\text{V} - 4.35\text{V}$). |
| **15..22**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM-8 authentication tag ($M=8, L=2$).** |

---

### 4.2 Candidate 2: Extended Diagnostic Frame (`UP_DIAG_METRICS_EXTENDED`)

#### Wire Format Overview (29 Bytes Fixed)
Consists of the standard 7-byte V2 Unicast Header, a 14-byte encrypted payload, and an 8-byte AES-128-CCM authentication tag.

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   VER_TYPE    |    NODE_ID    |  SESSION_SEL  |               |
|  (0x4A cand.) |   (1 Byte)    |   (1 Byte)    |               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+               +
|                         FRAME_COUNTER                         |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           MAINT_SEQ                           |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      DROPPED_EVENT_COUNT                      |
|                      (4 Bytes, uint32 BE)                     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|       TX_ATTEMPT_COUNT        |TX_UNACKED_CNT |  DIAG_FLAGS   |
|      (2 Bytes, uint16 BE)     |   (1 Byte)    |   (1 Byte)    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|          BATTERY_MV           |                               |
|      (2 Bytes, uint16 BE)     |                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+        AES-128-CCM TAG        +
|                                           (8 Bytes)           |
+                               +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### Field Specification Table (Candidate 2)
| Offset | Field Name | Width | Type / Encoding | Description & Validation Rule |
|:---:|:---|:---:|:---|:---|
| **0..6** | **Unicast Header (AAD)** | **7B** | **Plaintext** | **Standard V2 Unicast Header.** |
| 0 | `VER_TYPE` | 1B | `uint8` (`0x4A` cand.) | Protocol V2 (`0b010`), packet type candidate `UP_DIAG_METRICS` (`0b01010`). |
| 1 | `NODE_ID` | 1B | `uint8` | Unique node address (`0x01`..`0xFE`). |
| 2 | `SESSION_SEL` | 1B | `uint8` | Session key identifier matching $K_{\text{SESSION\_UP}}$. |
| 3..6 | `FRAME_COUNTER` | 4B | `uint32_t` BE | Strictly increasing per-session counter. Anti-replay protection. |
| **7..20**| **Encrypted Payload** | **14B** | **Ciphertext** | **AES-128-CTR encrypted plaintext payload.** |
| 7..10 | `MAINT_SEQ` | 4B | `uint32_t` BE | Echo of current Maintenance Superframe sequence counter from Beacon. |
| 11..14 | `DROPPED_EVENT_COUNT` | 4B | `uint32_t` BE | Full 32-bit cumulative dropped events count ($0..4,294,967,295$). |
| 15..16 | `TX_ATTEMPT_COUNT` | 2B | `uint16_t` BE | Total RF transmission attempts since session start ($0..65535$). |
| 17 | `TX_UNACKED_COUNT` | 1B | `uint8_t` | Total MAC slot transmissions ending without ACK ($0..255$). |
| 18 | `DIAG_FLAGS` | 1B | `uint8_t` bitmask | Bit 0: NVS Wear Warning.<br>Bit 1: RTC Drift Warning.<br>Bit 2: Brownout Detected.<br>Bit 3: Sensor Comm Failure.<br>Bits 4..7: Reserved (`0`). |
| 19..20 | `BATTERY_MV` | 2B | `uint16_t` BE | Direct ADC millivolt reading ($0..5000\text{ mV}$). |
| **21..28**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM-8 authentication tag ($M=8, L=2$).** |

---

### 4.3 Candidate 3: TLV-Multiplexed Management Frame (`UP_MGMT_TLV`)

#### Recalculated Wire Format Breakdown
A TLV architecture permits dynamic inclusion of metric blocks. Each TLV block consumes $1\text{B Tag} + 1\text{B Length} + V\text{ Bytes Value}$.

- **Common Header:** 7 Bytes (Plaintext AAD).
- **Mandatory Sequence Echo:** `MAINT_SEQ` (4 Bytes).
- **TLV Block 1 (Loss Metrics, Tag `0x01`):** Tag (1B) + Length (1B: `0x04`) + `DROPPED_EVENT_COUNT` (4B) = **6 Bytes**.
- **TLV Block 2 (Battery Metrics, Tag `0x02`):** Tag (1B) + Length (1B: `0x02`) + `BATTERY_MV` (2B) = **4 Bytes**.
- **Optional TLV Block 3 (Retry Metrics, Tag `0x03`):** Tag (1B) + Length (1B: `0x02`) + `TX_ATTEMPT` (1B) + `TX_UNACKED` (1B) = **4 Bytes**.
- **Authentication Tag:** AES-128-CCM Tag = **8 Bytes**.

```
Candidate 3A (Minimal TLV: Loss + Battery) — 29 Bytes Total:
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Unicast Header (7B)         | MAINT_SEQ (4B)                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Tag: 0x01 | Len: 4 | DROPPED_EVENT_COUNT (4B, uint32 BE)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Tag: 0x02 | Len: 2 | BATTERY_MV (2B) | CCM Tag (8B)           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
Total Plaintext = 4 (MAINT_SEQ) + 6 (TLV1) + 4 (TLV2) = 14 Bytes.
Total Wire = 7 (Header) + 14 (Plaintext) + 8 (Tag) = 29 Bytes.

Candidate 3B (Full TLV: Loss + Battery + Retries) — 33 Bytes Total:
Total Plaintext = 4 (MAINT_SEQ) + 6 (TLV1) + 4 (TLV2) + 4 (TLV3) = 18 Bytes.
Total Wire = 7 (Header) + 18 (Plaintext) + 8 (Tag) = 33 Bytes.
```

---

## 5. Trade-Off and Airtime Analysis (Deliverable 3)

### 5.1 Physical Layer Time-on-Air (ToA) Calculations
Calculated using the SX1276 LoRa PHY formula with standard VN920 parameters:
- **Bandwidth ($BW$):** $125\text{ kHz}$
- **Coding Rate ($CR$):** $4/5$ ($CR=1$)
- **Preamble Length:** $8\text{ symbols}$
- **Header:** Explicit mode ($IH=0$)
- **CRC:** Enabled on uplinks ($CRC=1$)
- **Low Data Rate Optimization ($DE$):** Off ($0$) for SF7 and SF8 at $125\text{ kHz}$.

$$\begin{aligned}
T_{\text{sym}} &= \frac{2^{\text{SF}}}{\text{BW}} \\
T_{\text{preamble}} &= (N_{\text{preamble}} + 4.25) \times T_{\text{sym}} \\
\text{PayloadSymbNb} &= 8 + \max\left( \left\lceil \frac{8 \cdot PL - 4 \cdot \text{SF} + 28 + 16 \cdot CRC - 20 \cdot IH}{4 \cdot (\text{SF} - 2 \cdot DE)} \right\rceil \times (CR + 4),\, 0 \right) \\
\text{ToA} &= T_{\text{preamble}} + (\text{PayloadSymbNb} \times T_{\text{sym}})
\end{aligned}$$

#### Recalculated Physical ToA Comparison Table
| Message Profile | Total Wire Bytes | SF7 ToA (ms) | SF8 ToA (ms) | Delta vs Health 21B (SF7) | Delta vs Health 21B (SF8) |
|:---|:---:|:---:|:---:|:---:|:---:|
| `UP_HEALTH_REPLY` (Baseline, 0x44) | **21 B** | **56.576 ms** | **102.912 ms** | Baseline ($0.0\text{ ms}$) | Baseline ($0.0\text{ ms}$) |
| **Candidate 1 (Compact)** | **23 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ ($+9.0\%$) | $+10.240\text{ ms}$ ($+9.9\%$) |
| **Candidate 2 (Extended)** | **29 B** | **66.816 ms** | **123.392 ms** | $+10.240\text{ ms}$ ($+18.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| **Candidate 3A (Minimal TLV)** | **29 B** | **66.816 ms** | **123.392 ms** | $+10.240\text{ ms}$ ($+18.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| **Candidate 3B (Full TLV)** | **33 B** | **71.936 ms** | **133.632 ms** | $+15.360\text{ ms}$ ($+27.1\%$) | $+30.720\text{ ms}$ ($+29.8\%$) |
| `UP_EVENT` (Reference, 0x41) | **26 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ | $+10.240\text{ ms}$ |

> [!NOTE]
> LoRa symbol quantization: At SF7, payloads from 27B through 29B require exactly 53 symbols ($66.816\text{ ms}$). At SF8, payloads from 27B through 29B require 48 symbols ($123.392\text{ ms}$). Thus, Candidate 2 (29B) achieves identical ToA to 27B while providing native 32-bit drop count and direct millivolts.

### 5.2 Theoretical Slot Budget & Qualification Statement
Under `DEC-127-06`, slot timing is parameterized. The candidate 400 ms slot profile is strictly a **non-normative theoretical example**.

> [!IMPORTANT]
> **Qualification of 400 ms Feasibility:**
> All headroom margins calculated below are **`THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY`**. They rely on unverified symbolic assumptions ($T_{\text{LEAD\_GUARD}} = 25\text{ ms}$, $T_{\text{TRAILING\_GUARD}} = 50\text{ ms}$) and are **`NOT_VERIFIED`** pending physical oscilloscope and HIL bench sign-off under **Issue #169**.

Under assumed theoretical guards:
- **Candidate 1 (23B) at SF7:** $400 - 25 - 61.696 - 50 = 263.304\text{ ms}$ (Theoretical Margin).
- **Candidate 1 (23B) at SF8:** $400 - 25 - 113.152 - 50 = 211.848\text{ ms}$ (Theoretical Margin).
- **Candidate 2 (29B) at SF7:** $400 - 25 - 66.816 - 50 = 258.184\text{ ms}$ (Theoretical Margin).
- **Candidate 2 (29B) at SF8:** $400 - 25 - 123.392 - 50 = 201.608\text{ ms}$ (Theoretical Margin).
- **Candidate 3B (33B) at SF7:** $400 - 25 - 71.936 - 50 = 253.064\text{ ms}$ (Theoretical Margin).
- **Candidate 3B (33B) at SF8:** $400 - 25 - 133.632 - 50 = 191.368\text{ ms}$ (Theoretical Margin).

### 5.3 Comparative Trade-Off Matrix

| Evaluation Dimension | Candidate 1 (Compact 23B) | Candidate 2 (Extended 29B) | Candidate 3A (Min TLV 29B) | Candidate 3B (Full TLV 33B) | Architectural Assessment |
|:---|:---:|:---:|:---:|:---:|:---|
| **Wire Size** | **23 Bytes** | 29 Bytes | 29 Bytes | 33 Bytes | Candidate 1 is smallest. |
| **ToA SF7 (ms)** | **61.696 ms** | 66.816 ms | 66.816 ms | 71.936 ms | Candidate 1 saves 5.1 ms. |
| **ToA SF8 (ms)** | **113.152 ms** | 123.392 ms | 123.392 ms | 133.632 ms | Candidate 1 saves 10.2 ms. |
| **Counter Range** | 16-bit ($65,535$) | **32-bit ($4.29\times 10^9$)**| **32-bit ($4.29\times 10^9$)**| **32-bit ($4.29\times 10^9$)**| 32-bit eliminates rollover risk. |
| **Battery Field** | 8-bit ($10\text{ mV}$) | **16-bit ($1\text{ mV}$ direct)**| **16-bit ($1\text{ mV}$ direct)**| **16-bit ($1\text{ mV}$ direct)**| 16-bit avoids quantization. |
| **Link Metrics** | `TX_UNACKED` | `TX_ATTEMPT` + `UNACKED` | None | `TX_ATTEMPT` + `UNACKED` | Full telemetry on Cand 2/3B. |
| **Parser Overhead**| Fixed $O(1)$ | Fixed $O(1)$ | Dynamic loop $O(N)$ | Dynamic loop $O(N)$ | Fixed offset eliminates parser bugs. |
| **G2 Recommendation**| Viable fallback | **Proposed Primary** | High complexity | Highest airtime penalty | Submit to Owner for decision. |

---

## 6. Security and Replay Analysis (Deliverable 5)

### 6.1 Cryptographic Trust Boundaries (`DEC-SEC-01` .. `DEC-SEC-07`)
1. **Zero-Knowledge Backend (`DEC-SEC-01`):** The Backend Go server does not possess $Z$ or $K_{\text{SESSION\_UP}}$. AES-128-CCM verification terminates strictly at the Gateway edge.
2. **Session Key Derivation:** Authenticated and encrypted using $K_{\text{SESSION\_UP}}$ derived from the V2 Ephemeral X25519 ECDH handshake (`0x45`..`0x48`).
3. **Cipher Suite:** AES-128-CCM ($M=8$, $L=2$, $N=13$) per NIST SP 800-38C and RFC 3610.

### 6.2 Frame Counter Domain Safety Analysis & OPEN_DECISION Status

$$N = \text{SESSION\_NONCE\_PREFIX}_{\text{UP}}[0..7] \parallel 0\text{x}01 \parallel \text{FRAME\_COUNTER}[0..3]$$

In accordance with RFC 3610, reusing a $(K, N)$ pair under AES-CCM destroys message confidentiality and authenticity. We evaluate the proposed **Unified Frame Counter Domain** across all critical operational failure modes:

1. **Failure Mode 1: Node Reboot & Power Loss:**
   - Under `DEC-SEC-01` and `DEC-SEC-05`, ephemeral session keys ($K_{\text{SESSION\_UP}}$) are held strictly in **volatile RAM**.
   - Upon reboot, volatile session keys are destroyed. The Node cannot transmit until executing a new V2 Join handshake (`0x45`..`0x48`), which derives a brand-new $K_{\text{SESSION\_UP}}$ from a new ECDH secret $Z$, increments persistent `JOIN_COUNTER` in NVS (`DEC-SEC-06`), and resets `FRAME_COUNTER` to $0$.
   - Under a new key, `FRAME_COUNTER = 0` is strictly safe.
   - *Residual Risk during Deep Sleep:* If session keys are preserved in RTC memory across Light/Deep Sleep to avoid re-joining, `FRAME_COUNTER` must also be preserved in RTC memory. An unhandled brownout resetting RTC memory without clearing session keys would create a catastrophic nonce reuse hazard.
2. **Failure Mode 2: Retransmission / Retry:**
   - For diagnostic frames, we propose a strict best-effort zero-retry policy.
   - If retries are ever enabled, RFC 3610 mandates that the node must re-transmit the **exact identical ciphertext and Nonce** buffered in memory. Re-encrypting mutated plaintext with the same `FRAME_COUNTER` is cryptographically fatal.
3. **Failure Mode 3: Concurrent Frame Creation (FreeRTOS Concurrency):**
   - On a dual-core ESP32, an Event Task (producing `UP_EVENT`) and a Telemetry Task (producing `UP_HEALTH_REPLY` or `UP_DIAG_METRICS`) could execute concurrently.
   - Grabbing `FRAME_COUNTER` without strict synchronization creates a race condition where two distinct messages could be encrypted with the identical Nonce.
   - Proving safety requires: (a) Single Radio Owner task architecture, or (b) Thread-safe atomic fetch-and-add (`atomic_fetch_add`) with mutex-serialized encryption.
4. **Failure Mode 4: Persistence Failure of Frame Counter:**
   - If `FRAME_COUNTER` is committed to flash/RTC and the write fails silently, counter rollbacks could occur upon subsequent wakes.

> [!WARNING]
> **Open Decision Disposition:** Because conclusive mathematical proof of frame counter safety under all concurrency, RTC sleep, and persistence failure paths requires verified firmware code and HIL bench testing, the Unified Frame Counter Domain cannot be declared unconditionally closed. It is formally classified as **`PROPOSED / OPEN_DECISION` (`DEC-DIAG-03`)** pending security review.

---

## 7. RF and TDMA Integration (Analysis C)

### 7.1 Transmission Opportunities & Health Frequency Trade-Off
We evaluate four potential scheduling models for diagnostic metrics:

#### Rigorous Re-Evaluation of Opportunity 1 (Health Slot Interleaving)
Under Health Slot Interleaving, even Maintenance epochs transmit `UP_HEALTH_REPLY` (0x44) and odd epochs transmit `UP_DIAG_METRICS` (0x4A cand.):
- **Slot Allocation Count:** Unchanged. The schedule table allocates the same 1 slot per node in $SF_{\text{MAINT}}$.
- **Airtime Impact:** In odd epochs, airtime increases from 56.576 ms (Health 21B) to 66.816 ms (Cand 2 29B) at SF7 ($+10.24\text{ ms}$, $+18.1\%$), and from 102.912 ms to 123.392 ms at SF8 ($+20.48\text{ ms}$, $+19.9\%$).
- **Health Reporting Latency Penalty:** **Health reporting frequency is halved.** The interval between consecutive `UP_HEALTH_REPLY` transmissions increases from **~300 s to ~600 s** (nominal 10 minutes).
  - *Operational Consequence:* Critical health flags (`STATUS_FLAGS:1B` reporting hardware faults, low battery, or clock drift) and volatile queue depth (`PENDING_COUNT:1B`) are delayed by up to 10 minutes.
  - *Dynamic Health Override Mitigation:* If `STATUS_FLAGS != 0` or `PENDING_COUNT > 0`, the Node suppresses diagnostic transmission and forces `UP_HEALTH_REPLY` until healthy.

#### Comparative Opportunity Table
| Opportunity | Slot Allocation Count | Transmit Airtime Delta | Health Reporting Interval | Determinism | Status for Owner Review |
|:---|:---:|:---:|:---:|:---:|:---|
| **Opp 1: Health Interleaving** | **Unchanged (1 slot/node)** | $+10.2\text{ ms}$ (SF7 on odd) | **Doubled (~600 s)** | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 2: Expanded Maint SF** | Doubled ($+N$ slots) | $+10.2\text{ ms}$ (every epoch) | Unchanged (~300 s) | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 3: Multi-Epoch Diag SF** | Unchanged on normal | Normal SF unchanged | Unchanged (~300 s) | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 4: Contention Slot N+1** | Unchanged | Variable contention | Unchanged (~300 s) | Non-Deterministic | **REJECTED (Violates V2)** |

### 7.2 Priority, Anti-Starvation & Regulatory Airtime Rules
1. **Absolute Event Priority:** Emergency events (`UP_EVENT` 0x41) strictly own DATA slots. Diagnostics are confined strictly to Maintenance Superframes and **never** consume or delay DATA slots.
2. **Best-Effort Zero-Retry Delivery:** Diagnostic frames are unacknowledged at the MAC layer. If a diagnostic frame is lost to RF fading, the Node **must not retry** in subsequent DATA slots, completely avoiding RF clutter.
3. **Qualified Regulatory Statement:** Per-packet ToA numbers do not constitute aggregate regulatory compliance. Full compliance with VN920 duty cycle ($\le 1.0\%$) and regional radio standards requires end-to-end schedule modeling under Issue #179, verified by conducted RF bench testing under Issue #169.

---

## 8. Cross-Layer Interface Impact Matrix (Deliverable 6)

| Target Component | Work Package / Issue | Layer | Specific Impact & Contract Changes | Prerequisites & Dependencies |
|:---|:---|:---|:---|:---|
| **Node Firmware** | Issue #131 | Embedded C | Implement NVS batched persistence for `DROPPED_EVENT_COUNT`; integrate retry and ADC battery drivers; implement frame builder for candidate 0x4A. | `RING_BUFFER_DROP_OLDEST` (#131), ADC driver. |
| **Gateway Radio Engine** | Issue #131 | Embedded C / Go | Add parser for candidate 0x4A; verify AES-128-CCM tag; extract loss metrics; dispatch to internal MQTT client. | Radio MAC codec, AES-CCM engine. |
| **MQTT Contracts** | Issue #128 | Contract / Schema | Add topic `iot/v1/gw/{gateway_id}/uplink/diagnostics` and corresponding JSON Schema `node-diagnostics.schema.json`; or extend `status.schema.json`. | Issue #128 schema baseline. |
| **Backend Storage** | Issue #18 / #132 | Backend Go | Create PostgreSQL migration for `node_loss_metrics` table; implement append-only time-series ledger with canonical sequence ordering and rollover disambiguation. | PostgreSQL migrations (#18). |
| **Simulator & QA** | Issue #130 | Test Automation | Develop Python simulation scenarios injecting buffer saturation, packet drops, multi-wrap ambiguity, and reboot sequences to verify loss reporting. | MAC specification baseline. |
| **HIL Timing Sign-off** | Issue #169 | Hardware RF | Measure physical ToA on calibrated oscilloscope for 23B/29B/33B at SF7/SF8; measure SPI FIFO transfer latency on ESP32-WROOM-32E. | Calibrated hardware bench (#169). |
| **Radio MAC Authority**| Issue #127 | Governance | Formally integrate approved candidate layout into `contracts/radio-mac/specification.md` upon Owner review. | Issue #204 Owner sign-off. |
| **Cross-Layer Sync** | Issue #117 | Architecture | Ensure end-to-end consistency from Node NVS counter $\to$ Gateway wire parser $\to$ MQTT payload $\to$ DB record. | Complete child package execution. |

---

## 9. Comprehensive Negative Test Matrix (Deliverable 7)

| Test ID | Test Category | Stimulus & Trigger Condition | Expected System Behavior & Invariant | Verification Tier | Tracking Owner |
|:---|:---|:---|:---|:---:|:---:|
| **TM-DIAG-01** | Counter Overflow & Wrap | Node FIFO saturated with $>65,535$ drops (Cand 1, 16-bit) or $>4.29\times 10^9$ (Cand 2, 32-bit). | Counter rolls over gracefully. Backend calculates wrapped delta only when elapsed time bounds rule out multi-wrap; otherwise flags `AMBIGUOUS_MULTI_WRAP`. | Unit / Sim | #130 / #131 |
| **TM-DIAG-02** | Crash & Reboot | Power cut to Node during active event dropping; Node restarts and re-reads NVS flash. | Node recovers last committed `DROPPED_EVENT_COUNT` from NVS. Incomplete write invalidated by CRC. Counter does not reset to zero. | HIL / Fault Injection | #175 / #131 |
| **TM-DIAG-03** | Duplicate Delivery | Gateway receives duplicate RF transmission (e.g. reflection or re-trigger) with identical `FRAME_COUNTER`. | Gateway rejects duplicate at MAC layer (`FRAME_COUNTER <= LAST_RX`). Zero redundant MQTT publishes. | Sim / Integration | #130 / #131 |
| **TM-DIAG-04** | Replay Attack | Malicious actor replays valid diagnostic packet from previous superframe. | Gateway detects expired `FRAME_COUNTER` and discards packet. Security log recorded. | Security / Sim | #182 / #130 |
| **TM-DIAG-05** | Stale Epoch Echo | Node transmits diagnostic packet echoing `MAINT_SEQ` from 10 cycles ago ($K-10$). | Gateway detects desynchronization / stale beacon echo; rejects packet or flags freshness anomaly to Backend. | Contract / Unit | #128 / #131 |
| **TM-DIAG-06** | Ciphertext Tampering | Adversary flips 1 bit in encrypted payload or alters `DROPPED_EVENT_COUNT` in transit. | AES-128-CCM tag verification fails ($M=8$). Gateway drops packet fail-closed. Zero data passed to MQTT. | Crypto Vector / Unit | #173 / #131 |
| **TM-DIAG-07** | Slot Intrusion | Node attempts to transmit diagnostic frame during normal DATA slot (Slot 1..15). | Gateway MAC rejects unexpected packet type in DATA slot. Node scheduler logic asserted fail-closed. | Sim / Firmware | #130 / #131 |
| **TM-DIAG-08** | Desync Lockout | Node misses $\ge 3$ consecutive Beacons; enters `HOLDOVER_DESYNCHRONIZED` state. | Node hard-locks RF transmitter. Zero diagnostic or health transmissions until valid Beacon re-acquired. | Firmware / HIL | #178 / #169 |
| **TM-DIAG-09** | Malformed Length | Received packet has `VER_TYPE=0x4A` but payload length is truncated (e.g. 18B) or oversized (e.g. 35B). | Gateway parser rejects invalid frame length fail-closed without buffer over-read. | Fuzzing / Unit | #130 / #131 |
| **TM-DIAG-10** | Unallocated Opcode | Node transmits candidate `0x4A` before Owner wire approval is activated. | Gateway rejects frame as unallocated codepoint. (Asserted active by `test_radio_mac_timing_consistency.py`). | Contract Test | #127 / #201 |
| **TM-DIAG-11** | Backend Idempotency | MQTT broker redelivers identical diagnostic JSON payload twice due to QoS 1 reconnect. | Backend Ingest deduplicates via `(gateway_id, event_id)` or unique constraint on `(node_id, observed_at)`. | Backend Test | #18 / #132 |
| **TM-DIAG-12** | Flash Saturation Stress| High-frequency alert storm generating 100 drops/second for 10 minutes. | Batched dirty-commit absorbs writes; NVS wear-leveling prevents sector exhaustion; MCU heap remains bounded. | Soak / Sim | #130 / #131 |

---

## 10. Open Decision Register for Owner Review (Deliverable 8)

All decisions below are formally submitted as **`PROPOSED / OPEN_DECISION`** for Project Owner review. No wire allocations are made, `0x4A` remains strictly `NOT_APPROVED_WIRE`, and the approved 21B `UP_HEALTH_REPLY` frame remains 100% frozen:

| Decision ID | Summary of Issue | Options Considered | Status & Proposed Disposition | Impacted Teams |
|:---|:---|:---|:---|:---|
| **DEC-DIAG-01** | Wire Layout Selection for Diagnostic Message | **Option A:** Candidate 1 Compact (23B, 16-bit drop counter, 61.7ms SF7).<br>**Option B:** Candidate 2 Extended (29B, 32-bit drop counter, 66.8ms SF7).<br>**Option C:** Candidate 3 TLV Multiplexed (29B/33B). | `PROPOSED / OPEN_DECISION` — Propose Option B (Candidate 2 Extended, 29B) due to 32-bit rollover immunity and direct ADC millivolts with only $+10.2\text{ ms}$ ToA delta at SF7. | MAC / Security / Firmware |
| **DEC-DIAG-02** | TDMA Transmission Opportunity | **Option 1:** Interleave with Health Reply (alternating cadence, ~600s health interval).<br>**Option 2:** Expand Maintenance Superframe ($+N$ slots).<br>**Option 3:** Low-frequency periodic diagnostic superframe (~3600s). | `PROPOSED / OPEN_DECISION` — Propose Option 1 with dynamic health override, balancing zero additional slot allocations against halved health frequency. | MAC Scheduler / Gateway |
| **DEC-DIAG-03** | Frame Counter Domain Binding | **Option A:** Shared `FRAME_COUNTER` under $K_{\text{SESSION\_UP}}$ across Event, Health, and Diag.<br>**Option B:** Dedicated derived subkey $K_{\text{DIAG\_UP}}$ with independent counter. | `PROPOSED / OPEN_DECISION` — Propose Option A subject to formal FreeRTOS concurrency mutex verification and RTC sleep persistence audit. | Security / Crypto |
| **DEC-DIAG-04** | Retransmission Policy | **Option A:** Best-effort unacknowledged (zero MAC retries).<br>**Option B:** Bounded retry in next maintenance superframe.<br>**Option C:** Dedicated downlink diagnostic ACK. | `PROPOSED / OPEN_DECISION` — Propose Option A (Best-Effort Zero Retries) to eliminate RF clutter and preserve airtime margins. | Radio MAC / Firmware |
| **DEC-DIAG-05** | NVS Persistence Strategy | **Option A:** Synchronous commit on every FIFO drop.<br>**Option B:** Batched dirty-commit with deterministic flush before TDMA sleep. (Brownout ISR flash write prohibited). | `PROPOSED / OPEN_DECISION` — Propose Option B to balance SPI NOR flash endurance against power-loss exposure window. (Durability remains `NOT_VERIFIED pending HIL #175`). | Node Firmware |
| **DEC-DIAG-06** | Wire Codepoint Assignment Boundary | **Option A:** Allocate candidate `0x4A` (`UP_DIAG_METRICS`) formally in Wire Registry.<br>**Option B:** Maintain `0x4A` as candidate; freeze wire allocation at Gate G2. | `PROPOSED / OPEN_DECISION` — Propose Option B (`NOT_APPROVED_WIRE`), strictly upholding `DEC-MH-08` policy until formal Owner wire allocation. | Project Owner / G2 Gate |

---

## 11. Traceability & Acceptance Disposition

### 11.1 Acceptance Criteria Traceability Matrix
- [x] **AC-1 (Source-Bound Boundaries):** Preserves `UP_HEALTH_REPLY` (0x44, 21B); defines `PENDING_COUNT` as volatile FIFO depth and `DROPPED_EVENT_COUNT` as durable cumulative loss counter in NVS (Section 1 & 3).
- [x] **AC-2 (Candidate Designs):** Specifies at least two complete candidate designs with bitfields and wire diagrams (Candidate 1 Compact 23B, Candidate 2 Extended 29B, Candidate 3 TLV 29B/33B, Section 4).
- [x] **AC-3 (Trade-off & Airtime Analysis):** Compares physical LoRa ToA at SF7 and SF8, evaluates slot budget feasibility as `THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY`, and analyzes byte efficiencies (Section 5).
- [x] **AC-4 (Field & Semantic Mapping):** Details counter rollover, reboot recovery, batching wear-leveling, and idempotency (Section 3).
- [x] **AC-5 (Security & Replay Analysis):** Evaluates AES-128-CCM nonce uniqueness, shared frame counter domain failure modes, and epoch binding (Section 6).
- [x] **AC-6 (Cross-Layer Impact Matrix):** Produces detailed cross-layer impact matrix spanning #131, #128, #18/#132, #130, #169, #127, #117 (Section 8).
- [x] **AC-7 (Negative Test Matrix):** Formulates 12-case negative test suite covering overflow, replay, tampering, desync, and idempotency (Section 9).
- [x] **AC-8 (Open Decision Register):** Formulates 6 formal decision candidates marked `PROPOSED / OPEN_DECISION` (Section 10).
- [x] **AC-9 (Allowed Path Integrity):** Strictly confined to `docs/verification/v2-diagnostic-loss-metrics-contract-proposal.md`. Production contracts, ADRs, schemas, and code remain 100% read-only.

### 11.2 Status on Completion
In accordance with the Definition of Done:
- **Operational Status:** `DESIGN_PROPOSED / OWNER_WIRE_APPROVAL_PENDING`
- **G2 Gate Status:** `NOT_VERIFIED` (pending physical HIL timing #169 and formal Owner wire allocation).
- **Existing Baseline Test Evidence:** Execution of `tests/contract/test_radio_mac_timing_consistency.py` verifies baseline contract invariants (0x41..0x49 active codepoints, 0x4A not implemented on wire, 21B budget saturated). It does **NOT** establish implementation PASS, RF/HIL PASS, or cross-layer integration PASS.
