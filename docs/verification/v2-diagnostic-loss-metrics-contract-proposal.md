# LP2P V2 Diagnostic Loss Metrics & Management Message Design Proposal

**Document ID:** `DOC-VERIF-V2-DIAG-METRICS-001`  
**Status:** `DESIGN_PROPOSED / OWNER_WIRE_APPROVAL_PENDING` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`  
**Owner Decision Reference:** `DEC-MH-08` (Approved Technical Direction / Planned Not Implemented)  
**Parent Tracking:** Issue #204 (V2 Diagnostic Loss Metrics Design)  
**Cross-Issue References:** #127 (G2 Radio MAC Contract Gate), #201 / Merged PR #202 (Timing & Health Consistency Disposition), #128 (MQTT/API Contracts), #131 (Node/Gateway Firmware Execution), #18 / #132 (Backend Go Storage & Ingest), #130 (Simulator & Test Automation), #169 (Physical RF Timing & HIL Measurement Sign-off), #117 (Cross-Layer Verification)  
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
- **Uncompromised `UP_HEALTH_REPLY` (0x44):** The 21-byte layout of `UP_HEALTH_REPLY` remains frozen. No fields are redefined, truncated, or overloaded.
- **Strict Data Semantics:** `PENDING_COUNT` is volatile queue depth; `DROPPED_EVENT_COUNT` is durable cumulative dropped event count maintained in NVS flash.
- **Separate Versioned Message:** Diagnostic metrics must be carried in a separately versioned management message.
- **Candidate Status of `0x4A`:** Codepoint `0x4A` (symbolically designated `UP_DIAG_METRICS`) is strictly a **proposal candidate**, pending Owner wire approval.
- **Zero RF Chaos:** No unscheduled transmissions, no priority contention (PCSS), no CAD backoff, and no periodic application business telemetry are permitted.
- **All Numeric Timing is Symbolic:** All slot durations, guard intervals, holdover limits, and cadence periods are non-normative engineering targets, blocked on physical Hardware-in-the-Loop (HIL) sign-off under **Issue #169**.

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
| **REQ-DIAG-08** | RF Regulatory | Total RF transmission time for diagnostic reporting must respect the VN920 duty cycle limit ($\le 1.0\%$ for nodes) and $+14\text{ dBm}$ EIRP limit (`D03 §1`). | Gate G1 / RF Regulation |
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
                          --> DROPPED_EVENT_COUNT = DROPPED_EVENT_COUNT + 1 (Durable commit)
  +-----------------------------------------------------------------------------------+
```

#### Counter Width Evaluation (u16 vs u24 vs u32)
1. **Candidate 16-Bit Unsigned Integer (`uint16_t`, 2 Bytes):**
   - Maximum representable value: $65,535$.
   - **Overflow Analysis:** In an industrial monitoring facility experiencing sustained RF interference or gateway hardware failure, a vibration/thermal sensor generating an alert every 2 seconds will generate 43,200 events in 24 hours. A 16-bit counter will rollover within **36.4 hours** ($1.5$ days).
   - **Assessment:** High risk of undetected multi-rollover during prolonged outages.
2. **Candidate 24-Bit Unsigned Integer (`uint24_t`, 3 Bytes):**
   - Maximum representable value: $16,777,215$.
   - **Overflow Analysis:** At 1 event per second, rollover occurs after **194.1 days**.
   - **Assessment:** Sufficient headroom, but awkward alignment on 32-bit MCU architectures (ESP32 Xtensa LX6).
3. **Candidate 32-Bit Unsigned Integer (`uint32_t`, 4 Bytes):**
   - Maximum representable value: $4,294,967,295$.
   - **Overflow Analysis:** At 10 events per second continuous, rollover occurs after **13.6 years** (exceeding typical 10-year device field lifetime).
   - **Alignment & Microcontroller Cost:** Native 32-bit register on ESP32; zero byte-packing penalty in RAM/NVS; natural alignment for big-endian wire serialisation.
   - **Byte Cost Delta:** Only 2 bytes more than `uint16_t`.

### 3.2 Retry Statistics Semantics
Industrial link degradation often causes packet drops before FIFO exhaustion. Capturing retry behavior enables predictive link maintenance:
- **`TX_ATTEMPT_COUNT` (16-bit or 8-bit):** Total number of RF transmission bursts attempted by the MAC layer.
- **`TX_FAIL_COUNT` (8-bit or 16-bit):** Number of events that reached the maximum MAC retry limit without receiving a `DOWN_EVENT_ACK` (if the node implements drop-after-retry).
- **Semantics Distinction:** In the current V2 baseline, events remain in the FIFO until acknowledged or overwritten by `RING_BUFFER_DROP_OLDEST`. Therefore, tracking transmission retries per epoch indicates channel contention or fading margin.

### 3.3 Battery Metrics Semantics
- **`BATTERY_MV` (16-bit unsigned, millivolts):** Direct ADC calibrated voltage ($0..5000\text{ mV}$).
  - *Advantage:* Absolute physical measurement; immune to battery discharge curve interpretation errors on edge nodes; allows Backend to apply chemistry-specific state-of-charge (SoC) curves (e.g. LiSOCl2 vs LiFePO4).
- **`BATTERY_PCT_RAW` (8-bit compressed):** Linear encoding $V_{\text{mv}} = 1800 + (\text{val} \times 10)$ covering $1.80\text{V} - 4.35\text{V}$ in $10\text{ mV}$ steps.
  - *Advantage:* Saves 1 byte over the air.
  - *Disadvantage:* Loss of sub-10mV resolution; requires non-standard decompression logic in Gateway/Backend.

### 3.4 Counter Rollover, Reset, and Persistence Lifecycle
The relationship between volatile memory, NVS flash, reboots, and Join sessions governs data integrity:

```
+---------------------------------------------------------------------------------------------------+
|                                 NODE COUNTER LIFECYCLE STATE MACHINE                              |
+---------------------------------------------------------------------------------------------------+

     [Factory Provision]  --> NVS DROPPED_EVENT_COUNT = 0
                                     │
                                     ▼
        +---------------------------------------------------------+
        |                 ACTIVE RUNTIME OPERATION                |
        | - RAM: High-speed cached drop counter                   |
        | - Event dropped -> Increment RAM counter                |
        | - Periodic / Event-driven flush -> Commit to NVS Flash  |
        +---------------------------------------------------------+
                    │                                 │
     (Power Loss / Reboot)               (Session Re-Join / ECDH)
                    │                                 │
                    ▼                                 ▼
        +-----------------------+         +-------------------------------+
        |   CRASH RECOVERY      |         |      SESSION ROTATION         |
        | - Read NVS counter    |         | - Derive new K_SESSION_UP     |
        | - Resume without reset|         | - Reset FRAME_COUNTER = 0     |
        | - Monotonicity PRESERVED|       | - DROPPED_EVENT_COUNT persists|
        +-----------------------+         +-------------------------------+
```

1. **NVS Wear-Leveling Strategy:**
   - ESP32 SPI NOR flash allows $\sim 100,000$ write/erase cycles per sector. Committing `DROPPED_EVENT_COUNT` synchronously on every single event drop during an avalanche could wear out flash sectors rapidly.
   - **Recommended Rule:** Implement a **batched dirty-commit policy**: Maintain `DROPPED_EVENT_COUNT` in RAM; commit to NVS upon:
     - (a) A fixed drop increment threshold (e.g., every 16 dropped events), OR
     - (b) Immediately prior to entering Deep Sleep between TDMA frames, OR
     - (c) Right before constructing a diagnostic uplink frame, OR
     - (d) Brownout detector interrupt (ESP32 RTC brownout ISR).
2. **Persistence Across Reboots:**
   - `DROPPED_EVENT_COUNT` is a **device-lifetime cumulative metric**. It **must NOT** reset to zero upon software reset, watchdog reset, or battery brownout.
3. **Behavior Across Session Re-Joins:**
   - Re-running the Join protocol (`0x45`..`0x48`) rotates ephemeral keys ($Z \to K_{\text{SESSION\_UP}}$) and resets `FRAME_COUNTER` to $0$.
   - `DROPPED_EVENT_COUNT` **must remain continuous across Join sessions**. The Backend detects session changes via `SESSION_SEL` and maintains both cumulative device loss and session-specific loss.

### 3.5 Reporting & Idempotency Semantics
- **At Gateway:** The Gateway receives the diagnostic frame, validates the AES-128-CCM tag and monotonic `FRAME_COUNTER`, extracts the plaintext loss metrics, and forwards them to Backend via MQTT topic `iot/v1/gw/{gateway_id}/uplink/diagnostics` (or extended status).
- **At Backend:**
  - Duplicate MQTT deliveries (due to QoS 1 retries) are de-duplicated via `event_id = gateway_id:gateway_epoch:event_seq`.
  - For storage in PostgreSQL, the backend compares received `dropped_event_count` ($C_{\text{curr}}$) with the previous recorded value ($C_{\text{prev}}$):
    $$\Delta_{\text{loss}} = \begin{cases} C_{\text{curr}} - C_{\text{prev}}, & \text{if } C_{\text{curr}} \ge C_{\text{prev}} \\ C_{\text{curr}}, & \text{if } C_{\text{curr}} < C_{\text{prev}} \text{ (Anomaly: Flash Wiped / Rollover)} \end{cases}$$
  - This guarantees that metric rates (drops/hour) remain mathematically accurate even when packets are delayed or delivered out of order.

---

## 4. Candidate Design Proposals (Deliverable 2)

We propose three distinct candidate designs representing different architectural trade-offs:
- **Candidate 1 (Compact 23-Byte):** Minimal airtime overhead, optimal for low-duty industrial nodes.
- **Candidate 2 (Extended 29-Byte):** Comprehensive metrics, full 32-bit precision, optimal for predictive maintenance.
- **Candidate 3 (TLV Multiplexed 27-Byte):** Future-proof modularity, extensible sub-typing.

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
|      DROPPED_EVENT_COUNT      | TX_FAIL_COUNT |  BATTERY_RAW  |
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
| 13 | `TX_FAIL_COUNT` | 1B | `uint8_t` | MAC transmission failure count in current epoch ($0..255$). |
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
|       TX_ATTEMPT_COUNT        | TX_FAIL_COUNT |  DIAG_FLAGS   |
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
| 17 | `TX_FAIL_COUNT` | 1B | `uint8_t` | Total unacknowledged events discarded after retry exhaustion ($0..255$). |
| 18 | `DIAG_FLAGS` | 1B | `uint8_t` bitmask | Bit 0: NVS Wear Warning.<br>Bit 1: RTC Drift Warning.<br>Bit 2: Brownout Detected.<br>Bit 3: Sensor Comm Failure.<br>Bits 4..7: Reserved (`0`). |
| 19..20 | `BATTERY_MV` | 2B | `uint16_t` BE | Direct ADC millivolt reading ($0..5000\text{ mV}$). |
| **21..28**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM-8 authentication tag ($M=8, L=2$).** |

---

### 4.3 Candidate 3: TLV-Multiplexed Management Frame (`UP_MGMT_TLV`)

#### Wire Format Overview (27 Bytes Nominal)
Consists of standard 7-byte Unicast Header, 12-byte encrypted TLV payload, and 8-byte AES-128-CCM authentication tag.

```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Unicast Header (7B)         | MAINT_SEQ (4B)                |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Tag: 0x01 | Len: 4 | DROPPED_EVENT_COUNT (4B, uint32 BE)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Tag: 0x02 | Len: 2 | BATTERY_MV (2B) | CCM Tag (8B)           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

- Tag `0x01` (Loss Metrics): Length 4B (`DROPPED_EVENT_COUNT:4B`).
- Tag `0x02` (Battery Metrics): Length 2B (`BATTERY_MV:2B`).
- Tag `0x03` (Retry Metrics): Length 2B (`TX_ATTEMPT:1B`, `TX_FAIL:1B`).
- *Trade-off:* High extensibility; however, parser complexity increases firmware code size on microcontrollers and introduces malformed length parsing attack surfaces.

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

#### Exact Physical ToA Comparison Table
| Message Profile | Total Wire Bytes | SF7 ToA (ms) | SF8 ToA (ms) | Delta vs Health 21B (SF7) | Delta vs Health 21B (SF8) |
|:---|:---:|:---:|:---:|:---:|:---:|
| `UP_HEALTH_REPLY` (Baseline, 0x44) | **21 B** | **56.576 ms** | **102.912 ms** | Baseline ($0.0\text{ ms}$) | Baseline ($0.0\text{ ms}$) |
| **Candidate 1 (Compact)** | **23 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ ($+9.0\%$) | $+10.240\text{ ms}$ ($+9.9\%$) |
| **Candidate 3 (TLV Nominal)** | **27 B** | **66.816 ms** | **123.392 ms** | $+10.240\text{ ms}$ ($+18.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| **Candidate 2 (Extended)** | **29 B** | **71.936 ms** | **123.392 ms** | $+15.360\text{ ms}$ ($+27.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| `UP_EVENT` (Reference, 0x41) | **26 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ | $+10.240\text{ ms}$ |

> [!NOTE]
> At SF8, Candidate 2 (29B) and Candidate 3 (27B) produce identical ToA ($123.392\text{ ms}$) because LoRa symbol block quantization rounds up both payload lengths into the exact same 4-symbol codeword boundary.

### 5.2 Slot Budget & Feasibility Analysis within TDMA Slot
Under `DEC-127-06` (parameterized slot geometry, candidate example 400 ms slot), we evaluate whether Candidate 1 (23B) and Candidate 2 (29B) can fit safely within a single uplink transmission window:

$$\text{Margin} = T_{\text{SLOT}} - T_{\text{LEAD\_GUARD}} - \text{ToA}_{\text{DIAG}} - T_{\text{TRAILING\_GUARD}}$$

Assuming candidate symbolic guards ($T_{\text{LEAD\_GUARD}} = 25\text{ ms}$, $T_{\text{TRAILING\_GUARD}} = 50\text{ ms}$):
- **Candidate 1 at SF7:** $400 - 25 - 61.696 - 50 = 263.304\text{ ms}$ available margin.
- **Candidate 1 at SF8:** $400 - 25 - 113.152 - 50 = 211.848\text{ ms}$ available margin.
- **Candidate 2 at SF7:** $400 - 25 - 71.936 - 50 = 253.064\text{ ms}$ available margin.
- **Candidate 2 at SF8:** $400 - 25 - 123.392 - 50 = 201.608\text{ ms}$ available margin.

**Conclusion:** Both Candidate 1 and Candidate 2 easily fit within the candidate 400 ms slot envelope with $>200\text{ ms}$ of idle headroom. Neither causes transceiver overlap or slot boundary violation.

### 5.3 Comparative Trade-Off Matrix

| Evaluation Dimension | Candidate 1 (Compact 23B) | Candidate 2 (Extended 29B) | Candidate 3 (TLV 27B) | Architectural Recommendation |
|:---|:---|:---|:---|:---|
| **Wire Size** | **23 Bytes** | 29 Bytes | 27 Bytes | Candidate 1 is most compact. |
| **ToA at SF7** | **61.696 ms** | 71.936 ms | 66.816 ms | Candidate 1 saves 10.2 ms airtime. |
| **ToA at SF8** | **113.152 ms** | 123.392 ms | 123.392 ms | Candidate 1 saves 10.2 ms airtime. |
| **Counter Range** | 16-bit ($65,535$) | **32-bit ($4.29\times 10^9$)** | 32-bit ($4.29\times 10^9$) | **Candidate 2 eliminates rollover risk.** |
| **Battery Accuracy** | 8-bit ($10\text{ mV}$ step) | **16-bit ($1\text{ mV}$ direct ADC)**| 16-bit ($1\text{ mV}$ direct ADC)| Candidate 2 provides true physical ADC value. |
| **Link Telemetry** | Fail count only | **Attempts + Fails + Flags**| Optional sub-tags | Candidate 2 enables predictive diagnostics. |
| **Parser Complexity** | Fixed offset (O(1)) | Fixed offset (O(1)) | Dynamic Loop (O(N)) | Candidate 1 and 2 avoid parsing bugs. |
| **Extensibility** | Low | Moderate | **High** | Candidate 3 is most extensible. |

---

## 6. Security and Replay Analysis (Deliverable 5)

### 6.1 Cryptographic Trust Boundaries (`DEC-SEC-01` .. `DEC-SEC-07`)
The proposed diagnostic message maintains strict fidelity to the approved V2 security architecture:
1. **Zero-Knowledge Backend (`DEC-SEC-01`):** The Backend Go server does not know or receive the ephemeral shared secret $Z$ or session keys $K_{\text{SESSION\_UP}}$. AES-128-CCM verification is terminated exclusively at the Gateway edge.
2. **Session Key Derivation:** The message is authenticated using the pairwise directional session key $K_{\text{SESSION\_UP}}$ derived from the V2 Ephemeral X25519 ECDH handshake (`0x45`..`0x48`).
3. **Cipher Suite:** AES-128-CCM according to NIST SP 800-38C and RFC 3610:
   - Cipher: AES with 128-bit key.
   - Authentication Tag Length ($M$): **8 Bytes** (64 bits), providing $2^{-64}$ forgery resistance (`DEC-127-02`).
   - Length Field Size ($L$): **2 Bytes** (sufficient for payloads $\le 65,535$ bytes).
   - Nonce Size ($N$): **13 Bytes** ($15 - L = 13$).

### 6.2 Nonce Construction & Frame Counter Domain Architecture
In accordance with RFC 3610 Section 2.3, a key-nonce pair $(K, N)$ must **never** be used more than once.

$$N = \text{SESSION\_NONCE\_PREFIX}_{\text{UP}}[0..7] \parallel 0\text{x}01 \parallel \text{FRAME\_COUNTER}[0..3]$$
- $\text{SESSION\_NONCE\_PREFIX}_{\text{UP}}$: 8 bytes derived from $Z$ via HKDF during Join.
- Direction byte: $0\text{x}01$ explicitly designates **UPLINK**.
- `FRAME_COUNTER`: 4-byte big-endian unsigned integer.

#### Nonce Reuse Prevention: Shared vs Dedicated Frame Counter
We evaluate two alternative counter domain models:

```
Option A: Unified Frame Counter Domain (Recommended)
  K_SESSION_UP:
     UP_EVENT (0x41)        --> Uses FRAME_COUNTER = k
     UP_HEALTH_REPLY (0x44) --> Uses FRAME_COUNTER = k + 1
     UP_DIAG_METRICS (0x4A) --> Uses FRAME_COUNTER = k + 2
  --> Single monotonic counter per session. Nonce reuse mathematically impossible.

Option B: Split Subkey / Independent Counter Domain
  K_SESSION_UP (Data):      --> UP_EVENT (0x41)        [DATA_FRAME_COUNTER]
  K_SESSION_DIAG (Derived): --> UP_DIAG_METRICS (0x4A) [DIAG_FRAME_COUNTER]
  --> Requires secondary HKDF expansion and double tracking in Gateway state table.
```

- **Analysis & Decision:** **Option A (Unified Frame Counter Domain)** is strongly recommended.
  - Sharing `FRAME_COUNTER` across all uplink message types (`UP_EVENT`, `UP_HEALTH_REPLY`, and `UP_DIAG_METRICS`) under $K_{\text{SESSION\_UP}}$ strictly guarantees nonce uniqueness without requiring extra key derivation, extra state machines, or extra NVS storage slots.
  - The Gateway maintains a single `LAST_RX_FRAME_COUNTER[NODE_ID]` high-water mark. Any received frame with `FRAME_COUNTER` $\le \text{LAST\_RX}$ is immediately rejected.

### 6.3 Epoch-Binding & Replay Defense
To prevent delayed replay attacks (where an adversary records an authentic diagnostic frame and replays it hours or days later):
1. **Primary Defense (`FRAME_COUNTER`):** Replayed frames are discarded by Gateway sliding high-water mark verification.
2. **Secondary Defense (`MAINT_SEQ` Echo):** The plaintext payload carries the 4-byte `MAINT_SEQ` echoed from the current Maintenance Superframe Beacon. If the received `MAINT_SEQ` does not match the active maintenance sequence counter within acceptable drift ($\pm 1$), the Gateway flags a freshness violation.

---

## 7. RF and TDMA Integration (Analysis C)

### 7.1 Transmission Opportunity Models within TDMA Superframe
We evaluate four architectural opportunities for scheduling diagnostic message transmissions:

```
+---------------------------------------------------------------------------------------------------+
|                            TDMA DIAGNOSTIC TRANSMISSION OPPORTUNITIES                             |
+---------------------------------------------------------------------------------------------------+

Opportunity 1: Health Slot Interleaving (Recommended)
  Epoch K (Maint SF):   Slot 1: N1 HEALTH (0x44)  | Slot 2: N2 HEALTH (0x44)  | ...
  Epoch K+1 (Maint SF): Slot 1: N1 DIAG (0x4A)    | Slot 2: N2 DIAG (0x4A)    | ...
  --> Zero new RF slots; alternating reporting cadence (~600s interval).

Opportunity 2: Expanded Maintenance Superframe
  Epoch K (Maint SF):   Slot 1: N1 HEALTH (0x44)  | Slot 2: N1 DIAG (0x4A)    | Slot 3: N2 HEALTH ...
  --> Doubles Maintenance SF length; doubles Gateway RX active duty cycle.

Opportunity 3: Dedicated Low-Frequency Diagnostic Superframe
  Every 1 Hour:         Inject SF_DIAG carrying diagnostic slots for all nodes.
  --> Clean separation; requires Backend scheduler versioning complexity.

Opportunity 4: Contention Window Slot N+1
  Shared Access:        Nodes contend for Slot N+1 using slotted ALOHA.
  --> Violates zero-contention deterministic architecture; collision risk.
```

#### Detailed Comparison of Opportunities
| Transmission Opportunity | Airtime Overhead | Gateway RX Duty Cycle | Latency to Report Loss | Determinism | Recommended Disposition |
|:---|:---:|:---:|:---:|:---:|:---|
| **Opp 1: Health Slot Interleaving** | **None (0% increase)** | **Preserved** | ~600 seconds | **100% Deterministic** | **RECOMMENDED (Primary)** |
| **Opp 2: Expanded Maint SF** | High ($+100\%$ slots) | Doubled in Maint SF | ~300 seconds | 100% Deterministic | Viable Alternative |
| **Opp 3: Low-Freq Diag SF** | Low (amortized) | Negligible | ~3600 seconds | 100% Deterministic | Complex Scheduling |
| **Opp 4: Contention Slot N+1**| Unpredictable | Elevated | Variable | Non-Deterministic | **REJECTED (Violates V2)** |

### 7.2 Priority and Anti-Starvation Rules
1. **Absolute Event Priority:** Emergency events (`UP_EVENT` 0x41) use normal DATA superframes. Diagnostic reporting is confined strictly to Maintenance Superframes and **never** consumes or delays DATA slots.
2. **Health vs Diagnostic Priority in Interleaved Mode:** If a node experiences an active health warning (`STATUS_FLAGS != 0`), it may dynamically suppress diagnostic reporting and force transmission of `UP_HEALTH_REPLY` during its allocated slot until the health condition clears.
3. **Zero RF Spam / Best-Effort Delivery:** Diagnostic messages are unacknowledged at the MAC layer. If a diagnostic frame is lost to RF fading, the Node **must not retry** in subsequent DATA slots. It simply updates its local counters and transmits freshest metrics at the next scheduled diagnostic epoch.

---

## 8. Cross-Layer Interface Impact Matrix (Deliverable 6)

| Target Component | Work Package / Issue | Layer | Specific Impact & Contract Changes | Prerequisites & Dependencies |
|:---|:---|:---|:---|:---|
| **Node Firmware** | Issue #131 | Embedded C | Implement NVS batched persistence for `DROPPED_EVENT_COUNT`; integrate retry and ADC battery drivers; implement frame builder for candidate 0x4A. | `RING_BUFFER_DROP_OLDEST` (#131), ADC driver. |
| **Gateway Radio Engine** | Issue #131 | Embedded C / Go | Add parser for candidate 0x4A; verify AES-128-CCM tag; extract loss metrics; dispatch to internal MQTT client. | Radio MAC codec, AES-CCM engine. |
| **MQTT Contracts** | Issue #128 | Contract / Schema | Add topic `iot/v1/gw/{gateway_id}/uplink/diagnostics` and corresponding JSON Schema `node-diagnostics.schema.json`; or extend `status.schema.json`. | Issue #128 schema baseline. |
| **Backend Storage** | Issue #18 / #132 | Backend Go | Create PostgreSQL migration for `node_loss_metrics` table; implement idempotent deduplication by `(gateway_id, node_id, session_sel, frame_counter)`. | PostgreSQL migrations (#18). |
| **Simulator & QA** | Issue #130 | Test Automation | Develop Python simulation scenarios injecting buffer saturation, packet drops, and reboot sequences to verify loss reporting. | MAC specification baseline. |
| **HIL Timing Sign-off** | Issue #169 | Hardware RF | Measure physical ToA on calibrated oscilloscope for 23B/29B at SF7/SF8; measure SPI FIFO transfer latency on ESP32-WROOM-32E. | Calibrated hardware bench (#169). |
| **Radio MAC Authority**| Issue #127 | Governance | Formally integrate approved candidate layout into `contracts/radio-mac/specification.md` upon Owner review. | Issue #204 Owner sign-off. |
| **Cross-Layer Sync** | Issue #117 | Architecture | Ensure end-to-end consistency from Node NVS counter $\to$ Gateway wire parser $\to$ MQTT payload $\to$ DB record. | Complete child package execution. |

---

## 9. Comprehensive Negative Test Matrix (Deliverable 7)

| Test ID | Test Category | Stimulus & Trigger Condition | Expected System Behavior & Invariant | Verification Tier | Tracking Owner |
|:---|:---|:---|:---|:---:|:---:|
| **TM-DIAG-01** | Counter Overflow | Node FIFO saturated with $>65,535$ dropped events on Candidate 1 (16-bit) or $>4.29\times 10^9$ on Candidate 2 (32-bit). | Counter rolls over gracefully without firmware crash or integer trap. Backend detects rollover via delta heuristic without corrupting total loss ledger. | Unit / Sim | #130 / #131 |
| **TM-DIAG-02** | Crash & Reboot | Power cut to Node during active event dropping; Node restarts and re-reads NVS flash. | Node recovers last committed `DROPPED_EVENT_COUNT` from NVS. Counter does not reset to zero. Monotonicity preserved. | HIL / Fault Injection | #175 / #131 |
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

The following formal decision candidates are submitted for Project Owner consideration and direction under Issue #204:

| Decision ID | Summary of Issue | Options Considered | Recommended Technical Disposition | Impacted Teams |
|:---|:---|:---|:---|:---|
| **DEC-DIAG-01** | Wire Layout Selection for Diagnostic Message | **Option A:** Candidate 1 Compact (23B, 16-bit drop counter, 61.7ms SF7).<br>**Option B:** Candidate 2 Extended (29B, 32-bit drop counter, 71.9ms SF7).<br>**Option C:** Candidate 3 TLV Multiplexed (27B nominal). | **Adopt Option B (Candidate 2 Extended, 29B):** The 32-bit counter eliminates multi-day rollover risk during severe industrial outages. The $10.2\text{ ms}$ airtime difference is fully absorbed within the candidate 400 ms slot. | MAC / Security / Firmware |
| **DEC-DIAG-02** | TDMA Transmission Opportunity | **Option 1:** Interleave with Health Reply in Maintenance Superframe (alternating cadence, ~600s).<br>**Option 2:** Expand Maintenance Superframe with dedicated diagnostic slots.<br>**Option 3:** Periodic hourly diagnostic superframe. | **Adopt Option 1 (Interleaved Cadence):** Adds zero RF slots to the TDMA timeline; preserves the existing superframe duration; provides ample reporting frequency for slow-changing loss counters. | MAC Scheduler / Gateway |
| **DEC-DIAG-03** | Frame Counter Domain Binding | **Option A:** Shared `FRAME_COUNTER` under $K_{\text{SESSION\_UP}}$ across Event, Health, and Diag.<br>**Option B:** Dedicated derived subkey $K_{\text{DIAG\_UP}}$ with independent counter. | **Adopt Option A (Shared Counter Domain):** Strictly complies with NIST SP 800-38C nonce-uniqueness rules without key derivation or dual-state tracking overhead. | Security / Crypto |
| **DEC-DIAG-04** | Retransmission Policy | **Option A:** Best-effort unacknowledged (zero MAC retries).<br>**Option B:** Bounded retry in next maintenance superframe.<br>**Option C:** Dedicated downlink diagnostic ACK. | **Adopt Option A (Best-Effort Zero Retries):** Diagnostic metrics are cumulative and non-urgent. If a packet is lost, subsequent epochs carry latest totals without RF spam. | Radio MAC / Firmware |
| **DEC-DIAG-05** | NVS Persistence Strategy | **Option A:** Synchronous commit on every FIFO drop.<br>**Option B:** Batched dirty-commit to RAM with flush prior to deep sleep / transmission. | **Adopt Option B (Batched Dirty-Commit):** Protects SPI flash from premature wearout during event storms while guaranteeing persistence before radio sleep. | Node Firmware |
| **DEC-DIAG-06** | Wire Codepoint Assignment | **Option A:** Allocate candidate `0x4A` (`UP_DIAG_METRICS`) formally in Wire Registry.<br>**Option B:** Maintain `0x4A` as candidate; freeze wire allocation at Gate G2. | **Adopt Option B (Maintain Candidate Status):** Conforms strictly to `DEC-MH-08` policy until Owner formalizes multi-team wire approval. | Project Owner / G2 Gate |

---

## 11. Traceability & Acceptance Disposition

### 11.1 Acceptance Criteria Traceability Matrix
- [x] **AC-1 (Source-Bound Boundaries):** Preserves `UP_HEALTH_REPLY` (0x44, 21B); defines `PENDING_COUNT` as volatile FIFO depth and `DROPPED_EVENT_COUNT` as durable cumulative loss counter in NVS (Section 1 & 3).
- [x] **AC-2 (Candidate Designs):** Specifies at least two complete candidate designs with bitfields and wire diagrams (Candidate 1 Compact 23B and Candidate 2 Extended 29B, Section 4).
- [x] **AC-3 (Trade-off & Airtime Analysis):** Compares physical LoRa ToA at SF7 and SF8, evaluates slot budget feasibility, and analyzes byte efficiencies (Section 5).
- [x] **AC-4 (Field & Semantic Mapping):** Details counter rollover, reboot recovery, batching wear-leveling, and idempotency (Section 3).
- [x] **AC-5 (Security & Replay Analysis):** Evaluates AES-128-CCM nonce uniqueness, shared frame counter domain, and epoch binding (Section 6).
- [x] **AC-6 (Cross-Layer Impact Matrix):** Produces detailed cross-layer impact matrix spanning #131, #128, #18/#132, #130, #169, #127, #117 (Section 8).
- [x] **AC-7 (Negative Test Matrix):** Formulates 12-case negative test suite covering overflow, replay, tampering, desync, and idempotency (Section 9).
- [x] **AC-8 (Open Decision Register):** Formulates 6 formal decision candidates with options, trade-offs, and recommended technical dispositions (Section 10).
- [x] **AC-9 (Allowed Path Integrity):** Strictly confined to new document `docs/verification/v2-diagnostic-loss-metrics-contract-proposal.md`. Production contracts, ADRs, schemas, and code remain 100% read-only.

### 11.2 Status on Completion
In accordance with the Definition of Done:
- **Operational Status:** `DESIGN_PROPOSED / OWNER_WIRE_APPROVAL_PENDING`
- **G2 Gate Status:** `NOT_VERIFIED` (pending physical HIL timing #169 and formal Owner wire allocation).
