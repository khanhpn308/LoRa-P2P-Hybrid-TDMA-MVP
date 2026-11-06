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
- **Strict Data Semantics:** `PENDING_COUNT` is volatile queue depth; `DROPPED_EVENT_COUNT` is durable cumulative dropped event count maintained in NVS flash, with actual durability guarantees subject to verification.
- **Separate Versioned Message:** Diagnostic metrics must be carried in a separately versioned management message.
- **Owner-approved MVP diagnostic field scope (2026-11-07; FIELD_SELECTION_APPROVED / WIRE_NOT_APPROVED):** Retain exactly these application diagnostic fields: `MAINT_SEQ` (Maintenance sequence echo), `DROPPED_EVENT_COUNT` (cumulative FIFO-overwrite loss), `DIAG_FLAGS` (Node diagnostic status bitmask) and `BATTERY_MV` (Node battery/supply voltage in millivolts). **Exclude `TX_ATTEMPT_COUNT` and `TX_UNACKED_COUNT`** from the on-air Diagnostic MVP payload; ACK/retry logic for `UP_EVENT` and `DOWN_EVENT_ACK` is unchanged. The field set is approved by the Owner; candidate packet type `0x4A`, 26B wire length/offsets, exact flag bit assignments, voltage sensing point, validity rules, nonce/security and TDMA opportunity remain `PROPOSED / OPEN_DECISION / NOT_APPROVED_WIRE`. Historical 23B/29B/33B alternatives are retained for comparison only.
- **Candidate Status of `0x4A`:** Codepoint `0x4A` (symbolically designated `UP_DIAG_METRICS`) is strictly `NOT_APPROVED_WIRE` (candidate packet type only), pending Owner wire approval.
- **Zero RF Chaos:** No unscheduled transmissions, no priority contention (PCSS), no CAD backoff, and no periodic application business telemetry are permitted.
- **All Numeric Timing is Symbolic & Unverified:** All slot durations (400 ms candidate example), guard intervals, holdover limits, and cadence periods are non-normative engineering targets, qualified as `THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY` and blocked on physical Hardware-in-the-Loop (HIL) sign-off under **Issue #169**.

---

## 2. Source-Bound Design Requirements

| Requirement ID | Domain | Requirement Statement & Authority Source | Verification Gate |
|:---|:---|:---|:---|
| **REQ-DIAG-01** | Semantics | Node must maintain `DROPPED_EVENT_COUNT` as a durable cumulative counter incremented strictly upon FIFO drop events (`RING_BUFFER_DROP_OLDEST` under `DEC-127-04`). Crash durability remains `NOT_VERIFIED` pending **Node FIFO** fault injection; #175 targets **Gateway key slots**, not Node FIFO. | Firmware #131 / Node-specific HIL (to scope) |
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

### 3.2 Event ACK / Retry Semantics (Retained MAC Behavior; Excluded from Diagnostic MVP Payload)
Under the approved architecture ([ADR-0001](../adr/0001-hybrid-tdma.md), `DEC-127-04`, and `specification.md` Section 5.2):
- **Event Retention Guarantee:** Sensor events are **retained in the FIFO until acknowledged** by `DOWN_EVENT_ACK` (0x42) or overwritten when the FIFO is 100% full (`RING_BUFFER_DROP_OLDEST`).
- **No Discard on Retry Exhaustion:** There is **no** MAC policy where an event is discarded simply because a retry attempt counter expired. Such an event remains in the FIFO and is retransmitted in subsequent assigned static DATA slots.
- **Field Semantics:**
  - `TX_ATTEMPT_COUNT` (16-bit unsigned, BE): Cumulative count of physical LoRa transmission bursts initiated by the MAC layer for application data events.
  - `TX_UNACKED_COUNT` (8-bit or 16-bit unsigned): Count of transmission cycles that concluded without receiving a valid `DOWN_EVENT_ACK` within the slot turnaround window. This directly measures channel loss and RF fading without implying event deletion.
  - Event loss is **exclusively** tracked by `DROPPED_EVENT_COUNT` when buffer saturation occurs.
  - **Owner field-scope direction:** `TX_ATTEMPT_COUNT` and `TX_UNACKED_COUNT` may remain internal MAC debugging concepts, but **neither is included in the proposed Diagnostic MVP on-air payload**. They do not count lost Events. Earlier candidate layouts that include them are retained solely for comparison. This does not alter authorized event ACK or retry behavior.

### 3.3 Battery Metrics Semantics
- **`BATTERY_MV` (16-bit unsigned, millivolts):** Direct ADC calibrated voltage ($0..5000\text{ mV}$).
  - *Advantage:* Absolute physical measurement; immune to battery discharge curve interpretation errors on edge nodes; allows Backend to apply chemistry-specific state-of-charge (SoC) curves (e.g. LiSOCl2 vs LiFePO4).
- **`BATTERY_RAW` (8-bit compressed):** Linear encoding $V_{\text{mv}} = 1800 + (\text{val} \times 10)$ covering $1.80\text{V} - 4.35\text{V}$ in $10\text{ mV}$ steps.
  - *Advantage:* Saves 1 byte over the air.
  - *Disadvantage:* Loss of sub-10mV resolution; requires non-standard decompression logic in Gateway/Backend.

### 3.4 NVS Counter / FIFO Crash Consistency & Transaction Atomicity Analysis

#### Technical Analysis of Flash Writes and Brownout Prohibition
> [!CAUTION]
> **Prohibition of Flash Commits in Brownout ISR:** Proposing synchronous NOR flash writes inside a brownout interrupt service routine (ISR) without dedicated hardware energy storage is **strictly rejected**.
> - In ESP-IDF, SPI NOR flash programming/erase operations require multi-millisecond hold times ($T_{\text{prog}} \sim 0.5 - 3.0\text{ ms}$, $T_{\text{erase}} \sim 20 - 100\text{ ms}$) and draw peak currents of $30 - 50\text{ mA}$.
> - During a brownout event on typical decoupled power rails ($C_{\text{decouple}} \le 100\text{ }\mu\text{F}$), the rail voltage collapses within tens to hundreds of microseconds.
> - Attempting flash writes when $V_{\text{DD}}$ drops below the flash chip minimum operating voltage ($2.7\text{ V}$) results in partial bit programming, sector corruption, or unrecoverable NVS filesystem panics. Furthermore, ESP-IDF SPI flash drivers disable the cache and use mutexes that cannot be executed from an ISR context.
> - Consequently, flash writes in a brownout ISR are **forbidden** unless backed by empirical hardware bench evidence with calibrated supercapacitors and power-fail early-warning circuitry.

#### Power Failure at Transaction Boundaries
A naive three-step mutation sequence:
$$\text{Step 1: Commit } \text{DROPPED\_EVENT\_COUNT} \to \text{Step 2: Advance FIFO drop pointer} \to \text{Step 3: Insert new Event}$$
exhibits critical failure modes when power collapses across boundaries:

```
  +-------------------------------------------------------------------------------------------------+
  |                             TRANSACTION BOUNDARY FAILURE ANALYSIS                               |
  +-------------------------------------------------------------------------------------------------+

  Boundary 0 -> 1: Power loss during Step 1 (SPI Flash write of DROPPED_EVENT_COUNT)
    - Flash State: In-flight NVS record has invalid CRC; discarded on next boot.
    - FIFO State: Unmodified. Oldest event retained.
    - Result: Clean rollback to previous committed counter value.

  Boundary 1 -> 2: Power loss AFTER Step 1 finishes, BEFORE Step 2 advances FIFO drop pointer
    - Flash State: DROPPED_EVENT_COUNT committed as (C_prev + 1).
    - FIFO State: Drop pointer NOT advanced; oldest event remains in FIFO.
    - Result: PHANTOM DROP INCREMENT. The durable drop counter incremented, but no event was dropped
      from the queue. Upon reboot, the old event might trigger another drop attempt, double-counting.

  Boundary 2 -> 3: Power loss AFTER Step 2 finishes, BEFORE Step 3 inserts new replacement Event
    - Flash State: DROPPED_EVENT_COUNT committed as (C_prev + 1).
    - FIFO State: Oldest event dropped; new event lost before commit.
    - Result: Queue depth drops from 255 to 254; new alarm lost without queue preservation.

  Reverse Order (Step 2 before Step 1: Advance FIFO drop pointer before NVS Commit):
    - Power loss between Step 2 and Step 1: Event was dropped from FIFO, but NVS counter was NOT updated.
    - Result: UNACCOUNTED EVENT DROP. Actual event was permanently discarded without loss recording.
```

#### Evaluation of Crash-Consistent Transaction Options
To avoid phantom increments or uncounted drops without introducing unreviewed flash partition architectures:

1. **Volatile RAM Queue vs Durable Flash FIFO:**
   - *Volatile RAM Queue:* If the event FIFO is maintained in volatile SRAM, any power loss completely clears all pending queue items. Persisting `DROPPED_EVENT_COUNT` in NVS preserves cumulative historical drops, but cannot reconcile uncommitted RAM states across power cycles.
   - *Durable Flash FIFO:* If the FIFO itself resides in flash storage, the drop pointer and the cumulative drop counter exist in separate storage structures. Achieving atomicity across them requires a coordinated recovery protocol.
2. **Crash-Consistency Architectures (Candidate Design Options):**
   - *Option 1 (Compound Metadata Record, historical comparison):* Bundle FIFO pointers, generation and `DROPPED_EVENT_COUNT` into a metadata record. **CRC/`nvs_set_blob()` alone is insufficient to establish atomicity with Event records stored separately.** Requires a verified commit/recovery protocol.
   - *Option 2 (Intent Journal / WAL):* Log an intent record (`PENDING_DROP { old_event_ref, target_count }`) prior to queue pointer advancement, committing final state upon queue update completion.
   - *Option 3 (Recovery Reconciliation on Boot):* At boot initialization, scan the persistent FIFO sequence IDs (`EVENT_REF`) against the last committed `DROPPED_EVENT_COUNT` and unacknowledged transmit records to detect and reconcile any partial-transaction gaps.
3. **Formal Architectural Disposition — Owner-approved design direction (2026-11-07):**
   - **`DEC-DIAG-05 = OWNER_APPROVED_DIRECTION / IMPLEMENTATION_NOT_VERIFIED`:** Adopt **Copy-on-Write (CoW) Event staging + coordinated durable metadata commit + Boot Recovery** for the Node's approved persistent FIFO and cumulative `DROPPED_EVENT_COUNT`. This selects the *architecture*, not a specific ESP-IDF NVS API, Flash partition, journal encoding, bounded-wear algorithm or executable implementation.
   - A committed FIFO state must bind the queue's selected Event records and read/write pointers to the same committed `DROPPED_EVENT_COUNT` and generation. When the queue is full, a *committed transition* that logically evicts the oldest Event must increment the counter **exactly once**. A failed/uncommitted attempt must not create a phantom increment.
   - **Crash boundary:** A new Event staged but not yet durably committed is **not guaranteed preserved** across power loss. CoW/recovery aims to restore the previous or newly committed **valid queue snapshot** and avoid inconsistency; it is not a claim of zero data loss for all incoming real-world signals, nor a proof that every possible brownout can be recovered. Explicit status/failure evidence is required when recovery is ambiguous.
   - **No atomicity shortcut:** `nvs_set_blob()`, CRC or a standalone `nvs_commit()` call **do not by themselves prove atomic cross-record Event + metadata transactions**. Implementation must specify staging capacity, record validation, commit marker/generation, power-fail-safe switching and reclamation order; recoverability must be demonstrated. If Flash full or integrity cannot be established, fail safely rather than falsely increment/drop.
   - **Owner & HIL scope:** Firmware design/implementation belongs to **Issue #131** (Node Event FIFO). Node-specific power-loss HIL must be separately scoped there or in a dedicated Node HIL Issue. **Issue #175 is the Gateway `INSTALLED_INACTIVE` key-slot NVS fault-injection task, NOT Node FIFO validation.** It may share test methods but its PASS does not certify this decision.
   - **Boundary:** No firmware/schema/Flash layout/codepoint is authorized by this design document. `0x4A = NOT_APPROVED_WIRE`; `DEC-DIAG-01` wire approval, `DEC-DIAG-02/04/06`, physical HIL and G2 remain separately gated.

#### DEC-DIAG-05 Design Requirements — Pre-Implementation Gate

| ID | Required property | Verification criterion / owner |
|:---|:---|:---|
| `REQ-NVS-01` | Persistent FIFO as approved in `DEC-127-04` | Event and cumulative drop-count data survive reboot as specified; prohibit unapproved RAM-only fallback (#131) |
| `REQ-NVS-02` | Copy-on-Write before logical eviction | Stage and validate replacement Event without overwriting the only committed copy of the old FIFO head; reserve storage for staging/reclamation (#131) |
| `REQ-NVS-03` | Coherent durable commit boundary | One accepted generation binds queue pointers/records, `EVENT_REF` identity and `DROPPED_EVENT_COUNT`; atomicity must be **implemented and proven**, not inferred from one CRC-bearing blob (#131) |
| `REQ-NVS-04` | Exact drop accounting | Exactly one durable counter increment per **committed FIFO-full eviction**; no phantom increment if old snapshot remains authoritative; no uncounted committed eviction (#131/#130) |
| `REQ-NVS-05` | Boot recovery and fail-closed integrity | Select the newest internally consistent committed generation; reject partial/torn/incompatible records. On ambiguous/corrupt states: preserve evidence, signal error and avoid silently resetting count or destructive cleanup (#131) |
| `REQ-NVS-06` | ACK/pending coherence | Queue removal on an authenticated `DOWN_EVENT_ACK` is also crash-consistent; repeated ACK or retransmit must not delete another Event or double count loss (#131/#130) |
| `REQ-NVS-07` | Flash endurance and bounded resources | Size staging, NVS overhead, reclaim policy, wear and worst-case latency against expected Event rate; handle full NVS, commit failures and watchdog/queue bounds without unsafe TX (#131/#130) |
| `REQ-NVS-08` | Physical fault evidence | Test on real Node ESP32/actual Flash partition with controlled injection before/during/after Event staging and metadata commit and during reclamation; report actual coverage and unresolved failure windows (Node-specific HIL scope, **not** #175) |

**Additional clarification to historical candidate options above:** Option 1's description of `nvs_set_blob()` as automatically atomic across FIFO Event records and metadata was **overstated**; it is not accepted as sufficient proof. Option 2/3 are evaluated mechanisms rather than isolated alternative Owner choices: the Owner selected CoW + coordinated commit + recovery **together**, with precise implementation still subject to review.



---

### 3.5 Qualified Backend Ingest, Monotonic Deduplication & Rollover Handling

The Backend storage and ingest layer must handle duplicate packets, out-of-order deliveries, integer rollovers, node reboots, and session changes **without inventing lost-event totals or introducing phantom spikes**:

```
+---------------------------------------------------------------------------------------------------+
|                             BACKEND TIME-SERIES INGEST ARCHITECTURE                               |
+---------------------------------------------------------------------------------------------------+

  Incoming authenticated report --> Verify Node/session provenance at Gateway
                                      (rejoin/rekey history, key epoch, frame-counter domain)
                                      │
                                      ▼
                            Candidate Backend dedup identity (NOT approved SQL):
                            (gateway_id, node_id, authenticated_session_instance,
                             direction, frame_counter)
                            No verified non-reused session-instance binding?
                            --> QUARANTINE / SESSION_PROVENANCE_UNVERIFIED
                                      │
                                      ▼
                            Append-only reports with raw values and evidence
                                      │
                                      ▼
                            Evaluate ordering/deltas ONLY inside verified
                            identity/generation and durable-counter epoch
```

**Identity and ordering prerequisite — PROPOSED / OPEN_DECISION:** In the approved Radio MAC V2 specification, `SESSION_SEL` is a reusable key-slot selector (`0`/`1`), **not** a monotonic session-generation identifier. Its value can repeat after rejoin/rekey. The candidate dedup identity above requires a **non-reused, authenticated session-instance/key-generation binding** derived from authoritative Join/Gateway records. No such new RF field, approved Backend dedup schema or MQTT field is established by this document. `FRAME_COUNTER` is interpretable only within a verified cryptographic counter domain; `MAINT_SEQ` may wrap, and Gateway receive time alone is not proof of origin order. Do **not** sort by `(session_sel, frame_counter, maint_seq)` across sessions. If provenance or order is uncertain, preserve raw evidence and mark `UNKNOWN / SESSION_PROVENANCE_UNVERIFIED` (no synthetic delta). Coordinate #127/#128/#131/#117 approval before implementation.

#### Mathematically Defensible Modular Rollover Derivation
Let:
- $W \in \{2^{16}, 2^{32}\}$ be the counter modulus ($W = 65,536$ for 16-bit `uint16_t`, $W = 4,294,967,296$ for 32-bit `uint32_t`).
- $C_{\text{prev}} \in [0, W - 1]$ be the previous verified counter value observed at timestamp $t_{\text{prev}}$.
- $C_{\text{curr}} \in [0, W - 1]$ be the current received counter value observed at timestamp $t_{\text{curr}}$.
- $\Delta T = t_{\text{curr}} - t_{\text{prev}} > 0$ be the verified elapsed time in seconds between reports, established from an authoritative time source (Gateway UTC clock or Maintenance Superframe sequence cadence).
- $R_{\text{max}} > 0$ be the verified maximum possible physical drop rate (drops/second) that the sensor node hardware and firmware task queue can physically generate.

**Applicability:** The modulo calculation below applies only when both observations are proven to represent the same durable counter and a verified elapsed interval/order. A key-slot change neither proves nor disproves durable-counter continuity. On reset, unverified identity, reuse of an unknown session generation, counter epoch mismatch or uncertain time bounds, return `UNKNOWN / DISCONTINUITY_CAUSE_NOT_VERIFIED` instead of applying the congruence as if continuity were known.

The true physical drop increment $\Delta C \in \mathbb{Z}_{\ge 0}$ must simultaneously satisfy two constraints:

1. **Modular Congruence Constraint:**
   $$C_{\text{curr}} \equiv C_{\text{prev}} + \Delta C \pmod W \implies \Delta C = (C_{\text{curr}} - C_{\text{prev}}) + k \cdot W \quad \text{for } k \in \mathbb{Z}$$

2. **Physical Rate Bounding Constraint:**
   The increment cannot be negative, nor can it exceed the physical upper limit over elapsed time $\Delta T$:
   $$0 \le \Delta C \le R_{\text{max}} \times \Delta T$$

Substituting $\Delta C$:
$$0 \le (C_{\text{curr}} - C_{\text{prev}}) + k \cdot W \le R_{\text{max}} \times \Delta T$$

Solving for integer wrap count $k$:
$$k_{\text{min}} = \left\lceil \frac{C_{\text{prev}} - C_{\text{curr}}}{W} \right\rceil \le k \le \left\lfloor \frac{R_{\text{max}} \times \Delta T - (C_{\text{curr}} - C_{\text{prev}})}{W} \right\rfloor = k_{\text{max}}$$

Let $\mathcal{K} = \{ k \in \mathbb{Z} \mid k \ge 0 \text{ and } k_{\text{min}} \le k \le k_{\text{max}} \}$ be the set of physically and mathematically feasible wrap counts.

#### Formal Ingest Rules
- **Rule 1 (Unique Integer Solution, $|\mathcal{K}| = 1$):**
  Exactly one integer $k^* \in \mathcal{K}$ satisfies both modular congruence and physical rate limits:
  $$\Delta_{\text{loss}} = (C_{\text{curr}} - C_{\text{prev}}) + k^* \cdot W$$
  - If $k^* = 0$: Normal monotonic advance without rollover ($\Delta_{\text{loss}} = C_{\text{curr}} - C_{\text{prev}}$).
  - If $k^* = 1$: Unambiguous single rollover ($\Delta_{\text{loss}} = W - C_{\text{prev}} + C_{\text{curr}}$).
  - Definite loss delta is accepted and recorded.
- **Rule 2 (Ambiguous Multi-Wrap Solution, $|\mathcal{K}| > 1$):**
  Multiple integers $k \in \mathcal{K}$ are feasible (e.g., both $k=1$ and $k=2$ satisfy rate bounds because $\Delta T$ was too long).
  - **Strict Non-Invention Principle:** The Backend **must NOT assume $k=1$ or invent an arbitrary cumulative loss total**.
  - Action: Return `UNKNOWN / AMBIGUOUS_MULTI_WRAP`. Flag an audit warning. Establish $C_{\text{curr}}$ as the new reference baseline for subsequent intervals.
- **Rule 3 (Infeasible Under Model / Discontinuity, $|\mathcal{K}| = 0$):**
  No nonnegative $k$ satisfies the assumed modular congruence and rate/time bounds. This demonstrates **inconsistency with the model assumptions**, not a proven reset, flash wipe, reflash or identity collision.
  - Possible causes include source/epoch mismatch, counter reset or corruption, a wrong $R_{\text{max}}$, incorrect timestamps or ordering, or a broken counter persistence assumption; the cause remains **NOT_VERIFIED**.
  - Action: `DISCONTINUITY / CAUSE_NOT_VERIFIED`. Preserve the raw report and alert, set this interval's delta to `UNKNOWN`, and establish a fresh baseline only after identity and observation validation. Never synthesize a new loss total.
- **Rule 4 (Duplicates & Out-of-Order Handling):**
  - Duplicate detection needs the **same authenticated session instance and counter domain**, not merely matching `SESSION_SEL` and `FRAME_COUNTER`; conflicting authenticated content must be investigated. The candidate identity is **not an approved SQL UNIQUE constraint**. Equal counters across distinct sessions are not automatically duplicates.
  - Keep late/out-of-order reports as append-only evidence. Deltas can be computed only where identity, time and counter order are independently validated; any downstream recomputation must be idempotent, traceable and bounded. Where order is ambiguous, leave delta `UNKNOWN`.
- **Rule 5 (Key-Slot Reuse, Rejoin and Durable-Counter Continuity):**
  - `SESSION_SEL` (`0` or `1`) can be reused, does not encode a generation and is not a chronological ordering key. A flip of `SESSION_SEL` does **not** guarantee counter monotonicity, reset or a new generation.
  - A durable drop counter can decrease numerically due to a legitimate modulo rollover across sessions. A decrease can also indicate reset/corruption or an invalid identity binding. Apply Rules 1–2 only to a verified continuous counter and authorized identity; otherwise mark `UNKNOWN / SESSION_PROVENANCE_UNVERIFIED` or Rule 3. No new session field or wire behavior is approved by this design.
#### Mathematical Examples (Modulus $W = 65,536$, Verified $R_{\text{max}} = 5.0\text{ drops/s}$)

- **Example 1: Unambiguous Single Rollover ($|\mathcal{K}| = 1, k=1$):**
  - $C_{\text{prev}} = 65,500$, $C_{\text{curr}} = 120$, $\Delta T = 60\text{ s}$.
  - Upper rate bound: $R_{\text{max}} \times \Delta T = 5.0 \times 60 = 300\text{ drops}$.
  - Testing $k$:
    - For $k = 0$: $\Delta C = 120 - 65,500 = -65,380 < 0$ (infeasible).
    - For $k = 1$: $\Delta C = -65,380 + 65,536 = 156\text{ drops}$. Since $0 \le 156 \le 300$, $k=1$ is feasible.
    - For $k = 2$: $\Delta C = -65,380 + 131,072 = 65,692 > 300$ (infeasible).
  - Solution set: $\mathcal{K} = \{1\} \implies |\mathcal{K}| = 1$.
  - Result: $\Delta_{\text{loss}} = 156\text{ drops}$. Unambiguous rollover confirmed.

- **Example 2: Ambiguous Multi-Wrap ($|\mathcal{K}| > 1$):**
  - $C_{\text{prev}} = 65,500$, $C_{\text{curr}} = 120$, $\Delta T = 40,000\text{ s}$ ($\sim 11.1\text{ hours}$).
  - Upper rate bound: $R_{\text{max}} \times \Delta T = 5.0 \times 40,000 = 200,000\text{ drops}$.
  - Testing $k$:
    - For $k = 1$: $\Delta C = 156 \le 200,000$ (feasible).
    - For $k = 2$: $\Delta C = 65,692 \le 200,000$ (feasible).
    - For $k = 3$: $\Delta C = 131,228 \le 200,000$ (feasible).
  - Solution set: $\mathcal{K} = \{1, 2, 3\} \implies |\mathcal{K}| = 3 > 1$.
  - Result: Backend flags `AMBIGUOUS_MULTI_WRAP`. $\Delta_{\text{loss}} = \text{UNKNOWN}$. Zero synthetic loss invented.

- **Example 3: Out-of-Model Discontinuity (Cause Unverified, $|\mathcal{K}| = 0$):**
  - $C_{\text{prev}} = 50,000$, $C_{\text{curr}} = 100$, $\Delta T = 10\text{ s}$.
  - Upper rate bound: $R_{\text{max}} \times \Delta T = 5.0 \times 10 = 50\text{ drops}$.
  - Testing $k$:
    - For $k = 0$: $\Delta C = 100 - 50,000 = -49,900 < 0$ (infeasible).
    - For $k = 1$: $\Delta C = -49,900 + 65,536 = 15,636 > 50$ (infeasible).
    - For $k \ge 2$: $\Delta C > 15,636 > 50$ (infeasible).
  - Solution set: $\mathcal{K} = \emptyset \implies |\mathcal{K}| = 0$.
  - Result: Backend flags `DIAG_METRIC_DISCONTINUITY` with `CAUSE_NOT_VERIFIED`. The observations do not fit the assumed physical bounds, but **do not prove** a Node reset. $\Delta_{\text{loss}} = \text{UNKNOWN}$. Preserve evidence and establish $100$ as a new baseline only after source/provenance checks; no phantom drops are added.

> [!NOTE]
> This mathematical derivation governs design specifications for Issue #18 / #132. It is an analytical formulation and does **not** constitute proof that Backend logic has been implemented or tested.

---

## 4. Candidate Design Proposals (Deliverable 2)

Four layouts are compared. Candidates 1–3 were prepared before the Owner narrowed the **MVP Diagnostic payload**; they are retained as **comparison-only, not recommended for MVP wire implementation**:
- **Candidate 1 (Compact 23B, historical comparison):** Includes `TX_UNACKED_COUNT`; conflicts with the reduced MVP field set.
- **Candidate 2 (Extended 29B, historical comparison):** Includes `TX_ATTEMPT_COUNT` and `TX_UNACKED_COUNT`; **withdrawn as Proposed Primary**.
- **Candidate 3 (TLV 29B/33B, historical comparison):** The 33B option includes retry counters; retained for future design study only.
- **Candidate 4 (MVP Reduced Diagnostic, 26B, PROPOSED WIRE PRIMARY):** Owner-approved field selection retains `DROPPED_EVENT_COUNT`, `MAINT_SEQ`, `DIAG_FLAGS`, and `BATTERY_MV`, excluding both TX statistics fields. **Only field inclusion/exclusion is approved**; the 26B layout remains proposed. No codepoint allocation or wire freeze is granted.

### 4.1 Candidate 1: Compact Diagnostic Frame — Historical Comparison Only (`UP_DIAG_METRICS_COMPACT`)

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
| 11..12 | `DROPPED_EVENT_COUNT` | 2B | `uint16_t` BE | Cumulative dropped events count ($0..65535$). Subject to multi-wrap analysis. |
| 13 | `TX_UNACKED_COUNT` | 1B | `uint8_t` | MAC transmission attempts in DATA slots ending without ACK ($0..255$). |
| 14 | `BATTERY_RAW` | 1B | `uint8_t` | Compressed voltage: $V = 1800 + (\text{val} \times 10)\text{ mV}$ ($1.80\text{V} - 4.35\text{V}$). |
| **15..22**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM-8 authentication tag ($M=8, L=2$).** |

---

### 4.2 Candidate 2: Extended Diagnostic Frame — Historical Comparison Only (`UP_DIAG_METRICS_EXTENDED`)

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
| 11..14 | `DROPPED_EVENT_COUNT` | 4B | `uint32_t` BE | Full 32-bit cumulative dropped events count ($0..4,294,967,295$). Multi-year wrap immunity. |
| 15..16 | `TX_ATTEMPT_COUNT` | 2B | `uint16_t` BE | Total RF transmission attempts since session start ($0..65535$). |
| 17 | `TX_UNACKED_COUNT` | 1B | `uint8_t` | Total MAC slot transmissions ending without ACK ($0..255$). |
| 18 | `DIAG_FLAGS` | 1B | `uint8_t` bitmask | Bit 0: NVS Wear Warning.<br>Bit 1: RTC Drift Warning.<br>Bit 2: Brownout Detected.<br>Bit 3: Sensor Comm Failure.<br>Bits 4..7: Reserved (`0`). |
| 19..20 | `BATTERY_MV` | 2B | `uint16_t` BE | Direct ADC millivolt reading ($0..5000\text{ mV}$). |
| **21..28**| **CCM Tag** | **8B** | `byte[8]` | **AES-128-CCM-8 authentication tag ($M=8, L=2$).** |

---

### 4.3 Candidate 3: TLV-Multiplexed Management Frame — Historical Comparison Only (`UP_MGMT_TLV`)

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

### 4.4 Candidate 4: Reduced MVP Diagnostic Frame (26B) — PROPOSED PRIMARY / NOT_APPROVED_WIRE

**Purpose and flow:** In a separately authorized Maintenance TX opportunity, the **Node sends** a diagnostic observation over LoRa to the **Gateway**, which verifies the AES-128-CCM tag and (once a versioned MQTT contract is approved) may forward the interpreted fields to the Backend. This frame reports cumulative **FIFO event loss**, not RF ACK failure count. It is **not implemented**; `0x4A` remains a **candidate codepoint only**.

**Exact proposed envelope (26 bytes):**

```text
Byte offset    0        1         2        3..6
              VER_TYPE  NODE_ID  SESSION_SEL  FRAME_COUNTER    [7B AAD]
Byte offset   7..10       11..14          15          16..17  [11B encrypted]
              MAINT_SEQ   DROPPED_EVENT_COUNT DIAG_FLAGS  BATTERY_MV
Byte offset   18..25      AES-128-CCM-8 authentication tag    [8B tag]
```

| Offset | Field | Width | Producer and precise meaning | Consumer handling / remaining gate |
|:---|:---|:---:|:---|:---|
| 0 | `VER_TYPE` | 1B | Node; **candidate** `0x4A`, V2 diagnostic message type | Gateway must reject as unallocated until separately approved |
| 1 | `NODE_ID` | 1B | Node local identity on the radio network | Gateway resolves authorized Node; not an Event ID |
| 2 | `SESSION_SEL` | 1B | Key-slot selector `0` or `1` for the active uplink session | Gateway chooses the correct crypto context; **not** session-generation identity |
| 3..6 | `FRAME_COUNTER` | 4B | Network-order frame counter for AES-CCM nonce/replay domain | Gateway performs replay checks; shared counter-domain safety still `DEC-DIAG-03 OPEN_DECISION` |
| 7..10 | `MAINT_SEQ` | 4B | Node echoes the Maintenance superframe sequence to which this report is bound | Gateway checks freshness; **not** an occurrence timestamp for individual Event drops |
| 11..14 | `DROPPED_EVENT_COUNT` | 4B | Node cumulative count of Events actually overwritten from the durable FIFO by `RING_BUFFER_DROP_OLDEST` | Gateway/Backend preserves raw value; a new drop count requires trusted sequential observations and verified counter continuity; power-loss atomicity is `DEC-DIAG-05 OPEN_DECISION` |
| 15 | `DIAG_FLAGS` | 1B | Candidate bitmask: bit0 NVS warning; bit1 RTC drift; bit2 brownout; bit3 sensor communication error; bits4..7 reserved 0 | Detection, validity, latching and clearing semantics **require Owner review** |
| 16..17 | `BATTERY_MV` | 2B | Proposed calibrated supply/battery voltage in millivolts | Exact measurement point and valid/unsupported sentinel require platform/hardware review |
| 18..25 | `CCM_TAG` | 8B | AES-128-CCM-8 authentication tag on encrypted payload and header AAD | Gateway authenticates before parsing/forwarding; not a diagnostic metric |

**Accounting:** `7B Header + 11B Encrypted Payload (4+4+1+2) + 8B CCM Tag = 26B`.

**Explicit exclusions:** `TX_ATTEMPT_COUNT` and `TX_UNACKED_COUNT` are **not present** in this proposed 26B MVP layout, neither directly nor re-encoded in `DIAG_FLAGS`. Event retransmission and `DOWN_EVENT_ACK` are unaffected. A missing Event ACK is never equated with an Event deleted from FIFO.

**Example interpretation:** If report A contains `DROPPED_EVENT_COUNT=7` and a subsequent, proven-continuous report B contains `9`, Backend may derive **2 newly overwritten Events in the interval between these reports**. It cannot assign both losses to the second Maintenance cycle or identify exactly which timestamps/events were lost from a cumulative counter alone. On unverifiable reset, session identity or rollover, delta is `UNKNOWN`.

**Status:** `DEC-DIAG-01 = OWNER_APPROVED_FIELD_SELECTION / PROPOSED_26B_REDUCED_LAYOUT / OPEN_WIRE_DECISION`. The Owner explicitly retains `DROPPED_EVENT_COUNT`, `DIAG_FLAGS` and `BATTERY_MV`, with `MAINT_SEQ` as the sequence echo, and excludes both TX statistics fields. The **field set alone** is approved; frame length, byte offsets, codepoint, nonce/scheduling rules, flag bit semantics, voltage sampling/reference/validation, ADC mapping and wire activation **remain unapproved / NOT_VERIFIED**.

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
| **Candidate 4 (Reduced MVP; proposed primary)** | **26 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ ($+9.0\%$) | $+10.240\text{ ms}$ ($+9.9\%$) |
| **Candidate 2 (Extended; old comparison)** | **29 B** | **66.816 ms** | **123.392 ms** | $+10.240\text{ ms}$ ($+18.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| **Candidate 3A (Minimal TLV)** | **29 B** | **66.816 ms** | **123.392 ms** | $+10.240\text{ ms}$ ($+18.1\%$) | $+20.480\text{ ms}$ ($+19.9\%$) |
| **Candidate 3B (Full TLV)** | **33 B** | **71.936 ms** | **133.632 ms** | $+15.360\text{ ms}$ ($+27.1\%$) | $+30.720\text{ ms}$ ($+29.8\%$) |
| `UP_EVENT` (Reference, 0x41) | **26 B** | **61.696 ms** | **113.152 ms** | $+5.120\text{ ms}$ | $+10.240\text{ ms}$ |

> [!NOTE]
> LoRa symbol quantization: At SF7, payloads from 27B through 29B require exactly 53 symbols ($66.816\text{ ms}$). At SF8, payloads from 27B through 29B require 48 symbols ($123.392\text{ ms}$). The 26B Reduced MVP candidate requires the same symbol count and ToA as the 23B historical Compact candidate at SF7/SF8, while keeping the 32-bit drop counter and direct millivolts. All ToA values are theoretical only.

### 5.2 Theoretical Slot Budget & Qualification Statement
Under `DEC-127-06`, slot timing is parameterized. The candidate 400 ms slot profile is strictly a **non-normative theoretical example**.

> [!IMPORTANT]
> **Qualification of 400 ms Feasibility:**
> All headroom margins calculated below are **`THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY`**. They rely on unverified symbolic assumptions ($T_{\text{LEAD\_GUARD}} = 25\text{ ms}$, $T_{\text{TRAILING\_GUARD}} = 50\text{ ms}$) and are **`NOT_VERIFIED`** pending physical oscilloscope and HIL bench sign-off under **Issue #169**.

Under assumed theoretical guards:
- **Candidate 1 (23B) at SF7:** $400 - 25 - 61.696 - 50 = 263.304\text{ ms}$ (Theoretical Margin).
- **Candidate 1 (23B) at SF8:** $400 - 25 - 113.152 - 50 = 211.848\text{ ms}$ (Theoretical Margin).
- **Candidate 4 (26B Reduced MVP) at SF7:** $400 - 25 - 61.696 - 50 = 263.304\text{ ms}$ (Theoretical Margin).
- **Candidate 4 (26B Reduced MVP) at SF8:** $400 - 25 - 113.152 - 50 = 211.848\text{ ms}$ (Theoretical Margin).
- **Candidate 2 (29B) at SF7:** $400 - 25 - 66.816 - 50 = 258.184\text{ ms}$ (Theoretical Margin).
- **Candidate 2 (29B) at SF8:** $400 - 25 - 123.392 - 50 = 201.608\text{ ms}$ (Theoretical Margin).
- **Candidate 3B (33B) at SF7:** $400 - 25 - 71.936 - 50 = 253.064\text{ ms}$ (Theoretical Margin).
- **Candidate 3B (33B) at SF8:** $400 - 25 - 133.632 - 50 = 191.368\text{ ms}$ (Theoretical Margin).

### 5.3 Comparative Trade-Off Matrix
**Scope update:** The table below retains *historical three-candidate trade-offs* for auditability, but its old Candidate 2 recommendation is withdrawn. The preferred review target is **Candidate 4 Reduced 26B** with a 32-bit cumulative drop count, no TX statistics, 61.696ms (SF7) / 113.152ms (SF8). None is approved on wire.

| Evaluation Dimension | Candidate 1 (Compact 23B) | Candidate 2 (Extended 29B) | Candidate 3A (Min TLV 29B) | Candidate 3B (Full TLV 33B) | Architectural Assessment |
|:---|:---:|:---:|:---:|:---:|:---|
| **Wire Size** | **23 Bytes** | 29 Bytes | 29 Bytes | 33 Bytes | Candidate 1 is smallest. |
| **ToA SF7 (ms)** | **61.696 ms** | 66.816 ms | 66.816 ms | 71.936 ms | Candidate 1 saves 5.1 ms. |
| **ToA SF8 (ms)** | **113.152 ms** | 123.392 ms | 123.392 ms | 133.632 ms | Candidate 1 saves 10.2 ms. |
| **Counter Range** | 16-bit ($65,535$) | **32-bit ($4.29\times 10^9$)**| **32-bit ($4.29\times 10^9$)**| **32-bit ($4.29\times 10^9$)**| 32-bit eliminates rollover risk. |
| **Battery Field** | 8-bit ($10\text{ mV}$) | **16-bit ($1\text{ mV}$ direct)**| **16-bit ($1\text{ mV}$ direct)**| **16-bit ($1\text{ mV}$ direct)**| 16-bit avoids quantization. |
| **Link Metrics** | `TX_UNACKED` | `TX_ATTEMPT` + `UNACKED` | None | `TX_ATTEMPT` + `UNACKED` | Full telemetry on Cand 2/3B. |
| **Parser Overhead**| Fixed $O(1)$ | Fixed $O(1)$ | Dynamic loop $O(N)$ | Dynamic loop $O(N)$ | Fixed offset eliminates parser bugs. |
| **G2 Recommendation**| Historical comparison | **Former primary; withdrawn** | Historical comparison | Historical comparison | **Candidate 4 Reduced 26B is now proposed primary; Owner wire decision remains open.** |

---

## 6. Security and Replay Analysis (Deliverable 5)

### 6.1 Cryptographic Trust Boundaries (`DEC-SEC-01` .. `DEC-SEC-07`)
1. **Zero-Knowledge Backend (`DEC-SEC-01`):** The Backend Go server does not possess $Z$ or $K_{\text{SESSION\_UP}}$. AES-128-CCM verification terminates strictly at the Gateway edge.
2. **Session Key Derivation:** Authenticated and encrypted using $K_{\text{SESSION\_UP}}$ derived from the V2 Ephemeral X25519 ECDH handshake (`0x45`..`0x48`).
3. **Cipher Suite:** AES-128-CCM ($M=8$, $L=2$, $N=13$) per NIST SP 800-38C and RFC 3610.

### 6.2 Shared Uplink Frame Counter — Owner-Approved Design Direction / Implementation NOT_VERIFIED

**Owner direction (2026-11-07; `DEC-DIAG-03 Option A`):** Use a **shared `FRAME_COUNTER` namespace per authenticated **uplink session/key instance** for new `UP_EVENT` (0x41), `UP_HEALTH_REPLY` (0x44) and a separately approved future Diagnostic frame (candidate `0x4A`). This is **`OWNER_APPROVED_DIRECTION` ONLY**, not approval of any diagnostic wire codepoint, packet format, key derivation change, FreeRTOS API, firmware implementation or RF transmission. It does not change the existing downlink `K_SESSION_DOWN` counter domain or the current V2 registry.

**Responsibility:** MAC Security must serialize/reserve a unique counter and bind it to one authenticated `(session_key_instance, direction)` before AES-CCM encryption. Event/Health/Diagnostic producers submit bounded logical frame requests, never self-assign counters. The SX1276 Radio Owner already serializes radio operations, but its existence **does not prove** a MAC Security counter allocator has been implemented. The implementation owner (#131) must document exactly one allocator, ownership/locking, exhaustion handling, and rejoin lifecycle; #173/#130 supply contract/security tests and #169/#175 relevant HIL evidence.



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
> **DEC-DIAG-03 governance:** Option A is `OWNER_APPROVED_DIRECTION` (2026-11-07). **Implementation readiness remains `NOT_VERIFIED`**. Security review, code/contract inspection and the applicable tests below are mandatory before enabling Diagnostic TX. These tests do not authorize candidate `0x4A`; `DEC-DIAG-06` remains `NOT_APPROVED_WIRE`. Exact allocator algorithm, key/session lifecycle and verification evidence are **not yet approved/implemented**.

### 6.3 Shared-Counter Security Requirements & Evidence Gates (DESIGN ONLY)

| Requirement | Design rule / acceptance condition | Owner / evidence |
|:---|:---|:---|
| `SEC-DIAG-C01` — Single allocator | One logical MAC Security counter allocator per authenticated uplink key instance issues distinct values to **all new Event, Health and future Diagnostic frames**, including requests from concurrent FreeRTOS tasks. Only one authority may reserve/commit counters; no direct producer `++counter` path. | #131 implementation review; #130 concurrency test |
| `SEC-DIAG-C02` — Pair uniqueness | Every **new encryption of distinct plaintext/AAD under a given key** uses a previously unused CCM nonce. The nonce domain is `SESSION_NONCE_PREFIX[8] || 0x01 || FRAME_COUNTER[4]`. No per-packet-type reset or independent Event/Health/Diagnostic counter under `K_SESSION_UP`. Skipping a reserved counter is permitted; assigning it twice to different frames is not. | #173 crypto test and audit |
| `SEC-DIAG-C03` — Retry identity | Retry of an existing Event must transmit **byte-for-byte the same immutable authenticated frame**, with original counter/nonce; never change Event value, flags, AAD, payload, or CCM tag under that nonce. A genuinely new Event uses a fresh counter. The Diagnostic retransmission policy remains `DEC-DIAG-04 OPEN_DECISION`. | #131/#130 duplicate & ACK-loss tests |
| `SEC-DIAG-C04` — Reboot / brownout fail-closed | After reboot with lost volatile keys/counter, **do not transmit under the previous key**; perform fully authenticated new Join and verify fresh key/nonce-prefix binding before allocating a new counter. Do not assume a successful NVS/RTC write or fresh key without evidence. If the key/counter provenance is uncertain, block RF TX and rejoin/recover via approved design. | #131 implementation and #175 power-loss tests |
| `SEC-DIAG-C05` — Sleep / retained keys | The approved design keeps ephemeral session secrets in volatile ownership; **no new RTC-retained-key mode is authorized**. If a retained-key path is ever proposed, it requires a separate approved atomic key/counter epoch recovery protocol; simply persisting a counter in RTC RAM does not prove crash safety. | #127 security decision, #131/#175 tests |
| `SEC-DIAG-C06` — Exhaustion / rekey | Stop issuing counters before any reserved/forbidden value or 32-bit wrap in the active session; rekey by authenticated Join with verified fresh cryptographic context, or fail-closed. Adopt the exact allowed range from the versioned V2 contract after conflict check; do not silently freeze numeric rollover policy here. | #127/#173/#131 tests |
| `SEC-DIAG-C07` — Gateway session binding | Gateway replay state is scoped to authenticated **key/session instance, Node identity, direction** and the counter; `SESSION_SEL` (0/1) alone does **not** identify a globally unique session generation. A rejoin using the same selector must not reuse stale replay acceptance state or collide with an old session. Backend receives only verified provenance, never `K_SESSION_UP`. | #127/#128/#131 contract review |
| `SEC-DIAG-C08` — Lost ACK & duplicate delivery | Gateway must reject a duplicate as a *new Event* but preserve the approved **idempotent ACK recovery** path for an already durably accepted Event; otherwise ACK loss can trap an Event in Node FIFO. Treat exact ciphertext retry differently from fresh counter allocation. | #131/#130 integration tests |
| `SEC-DIAG-C09` — No early wire implementation | Current production registry remains `0x41..0x49`; `0x4A = NOT_APPROVED_WIRE`. Shared counter guidance applies to a **future approved** Diagnostic uplink only; no new parser, MQTT schema, DB key or RF scheduling is granted by this section. | #127 Gate G2 / #204 design review |

**Evidence standard:** Static reasoning, documentation and passing existing baseline contract tests alone do **not** establish nonce uniqueness under task races, brownout or reset. Record actual test commands, commit SHA, toolchain/configuration, failure injections and HIL evidence separately; until then `SECURITY_NOT_VERIFIED / G2_NOT_VERIFIED`.

---

## 7. RF and TDMA Integration (Analysis C)

### 7.1 Transmission Opportunities & Health Frequency Trade-Off
We evaluate four potential scheduling models for diagnostic metrics:

#### Rigorous Re-Evaluation of Opportunity 1 (Health Slot Interleaving)
Under Health Slot Interleaving, even Maintenance epochs transmit `UP_HEALTH_REPLY` (0x44) and odd epochs transmit `UP_DIAG_METRICS` (0x4A cand.):
- **Slot Allocation Count:** Unchanged. The schedule table allocates the same 1 slot per node in $SF_{\text{MAINT}}$.
- **Airtime Impact (reduced 26B candidate):** In odd epochs, theoretical airtime rises from 56.576ms (Health 21B) to 61.696ms at SF7 (+5.120ms, +9.0%) or from 102.912ms to 113.152ms at SF8 (+10.240ms, +9.9%). No extra slots are allocated, but diagnostic replaces a Health reply, so Health reporting is less frequent. All values are `CALCULATED_TOA / NOT_HIL_VERIFIED`.
- **Health Reporting Latency Penalty:** **Health reporting frequency is halved.** The interval between consecutive `UP_HEALTH_REPLY` transmissions increases from **~300 s to ~600 s** (nominal 10 minutes).
  - *Operational Consequence:* Critical health flags (`STATUS_FLAGS:1B` reporting hardware faults, low battery, or clock drift) and volatile queue depth (`PENDING_COUNT:1B`) are delayed by up to 10 minutes.
  - *Dynamic Health Override Mitigation:* If `STATUS_FLAGS != 0` or `PENDING_COUNT > 0`, the Node suppresses diagnostic transmission and forces `UP_HEALTH_REPLY` until healthy.

#### Comparative Opportunity Table
| Opportunity | Slot Allocation Count | Transmit Airtime Delta | Health Reporting Interval | Determinism | Status for Owner Review |
|:---|:---:|:---:|:---:|:---:|:---|
| **Opp 1: Health Interleaving** | **Unchanged (1 slot/node)** | $+5.12\text{ ms}$ (SF7 on odd, 26B) | **Doubled (~600 s)** | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 2: Expanded Maint SF** | Doubled ($+N$ slots) | $+5.12\text{ ms}$ per Diagnostic (SF7, 26B) | Unchanged (~300 s) | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 3: Multi-Epoch Diag SF** | Unchanged on normal | Normal SF unchanged | Unchanged (~300 s) | 100% Deterministic | `PROPOSED / OPEN_DECISION` |
| **Opp 4: Contention Slot N+1** | Unchanged | Variable contention | Unchanged (~300 s) | Non-Deterministic | **REJECTED (Violates V2)** |

### 7.2 Priority, Anti-Starvation & Regulatory Airtime Rules
1. **Absolute Event Priority:** Emergency events (`UP_EVENT` 0x41) strictly own DATA slots. Diagnostics are confined strictly to Maintenance Superframes and **never** consume or delay DATA slots.
2. **Best-Effort Zero-Retry Delivery:** Diagnostic frames are unacknowledged at the MAC layer. If a diagnostic frame is lost to RF fading, the Node **must not retry** in subsequent DATA slots, completely avoiding RF clutter.
3. **Qualified Regulatory Statement:** Per-packet ToA numbers do not constitute aggregate regulatory compliance. Full compliance with VN920 duty cycle ($\le 1.0\%$) and regional radio standards requires end-to-end schedule modeling under Issue #179, verified by conducted RF bench testing under Issue #169.

---

## 8. Cross-Layer Interface Impact Matrix (Deliverable 6)

> [!IMPORTANT]
> **Governance & Non-Authorization Boundary:**
> This matrix documents downstream technical coordination interfaces and planning dependencies only. **It does NOT authorize production implementation, code modifications, topic creation, database migrations, or RF frame transmission/reception.** All diagnostic wire codepoints, schemas, and firmware additions remain strictly `BLOCKED_ON_OWNER_WIRE_APPROVAL` and `NOT_IMPLEMENTED`.

| Target Component | Coordinating Reference | Current Layer | CURRENT_APPROVED_SCOPE (Baseline Merged) | Potential Implementation Impact — AFTER Owner-Approved Versioned Contract | Architectural Disposition |
|:---|:---|:---:|:---|:---|:---:|
| **Node Firmware** | Issue #131 | Embedded C | `UP_HEALTH_REPLY` (`0x44`, 21B); `PENDING_COUNT` reporting; `RING_BUFFER_DROP_OLDEST` in NVS. | Would incorporate a frame builder for an Owner-approved reduced diagnostic layout carrying cumulative FIFO drop count, hardware flags and calibrated voltage; would implement NVS persistence per `DEC-DIAG-05`. **No diagnostic TX-attempt/unacked fields.** | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Gateway Radio Engine** | Issue #131 | Embedded C / Go | Active codepoints `0x41`..`0x49`; AES-128-CCM verification; local TDMA execution. | Would add parser and validation logic for approved diagnostic opcode; would forward verified metrics to internal MQTT client. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **MQTT Contracts** | Issue #128 | Contract Schema | Topics in `contracts/mqtt/topics.md`; JSON Schemas for alert, status, schedule. | Would define versioned topic (e.g. `uplink/diagnostics`) and JSON Schema (`node-diagnostics.schema.json`) following Owner schema approval. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Backend Storage** | Issue #18 / #132 | Backend Go / SQL | PostgreSQL event deduplication; schedule planning; zero-knowledge session key handling. | Would prepare SQL migration for `node_loss_metrics` table; would implement sequence-anchored ledger ingest and qualified modular rollover disambiguation. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Simulator & QA** | Issue #130 | Test Automation | Event-only TDMA schedule simulation; join protocol test harnesses. | Would add simulation test cases for FIFO saturation, modular rollover disambiguation, multi-wrap detection, and crash recovery. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Physical RF & Timing** | Issue #169 | Hardware RF / HIL | Symbolic ToA models; unverified guard intervals; HIL measurement framework. | Would verify calculated ToA and hardware timing for **26B Reduced MVP** at SF7/SF8 using the lab-appropriate methods authorized in Issue #169; any specialized RF measurements remain deferred/unverified. Historical 23B/29B/33B profiles are comparison-only. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Radio MAC Authority** | Issue #127 | Governance Gate G2 | `contracts/radio-mac/specification.md` (v0.2.0-DRAFT); approved codepoints `0x41`..`0x49`. | Would integrate approved diagnostic wire layout into specification upon formal Owner decision. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |
| **Cross-Layer Alignment** | Issue #117 | Monorepo Sync | Architecture alignment across components; ensures contract traceability. | Would verify end-to-end trace from Node NVS counter $\to$ Gateway wire parser $\to$ MQTT payload $\to$ DB record after multi-team sign-off. | `BLOCKED_ON_OWNER_WIRE_APPROVAL`<br>`NOT_IMPLEMENTED`<br>`NOT_VERIFIED` |

---

## 9. Comprehensive Negative Test Matrix (Deliverable 7)

| Test ID | Test Category | Stimulus & Trigger Condition | Expected System Behavior & Invariant | Verification Tier | Tracking Owner |
|:---|:---|:---|:---|:---:|:---:|
| **TM-DIAG-01** | Counter Overflow & Wrap | Node FIFO saturated with $>65,535$ drops (Cand 1, 16-bit) or $>4.29\times 10^9$ (Cand 2, 32-bit). | Counter rolls over gracefully. Backend calculates wrapped delta only when elapsed time bounds rule out multi-wrap; otherwise flags `AMBIGUOUS_MULTI_WRAP`. | Unit / Sim | #130 / #131 |
| **TM-DIAG-02** | Crash & Reboot | Power cut to Node during active Event FIFO overflow, including before/after durable metadata commit. | Node selects the previous or next valid committed FIFO+counter snapshot; corruption/torn write is rejected; CRC alone is not an atomicity guarantee. | Node HIL / Fault Injection | #131 / dedicated Node HIL scope (**not #175**) |
| **TM-DIAG-03** | Duplicate Delivery | Gateway receives duplicate RF transmission (e.g. reflection or re-trigger) with identical `FRAME_COUNTER`. | Gateway rejects duplicate at MAC layer (`FRAME_COUNTER <= LAST_RX`). Zero redundant MQTT publishes. | Sim / Integration | #130 / #131 |
| **TM-DIAG-04** | Replay Attack | Malicious actor replays valid diagnostic packet from previous superframe. | Gateway detects expired `FRAME_COUNTER` and discards packet. Security log recorded. | Security / Sim | #182 / #130 |
| **TM-DIAG-05** | Stale Epoch Echo | Node transmits diagnostic packet echoing `MAINT_SEQ` from 10 cycles ago ($K-10$). | Gateway detects desynchronization / stale beacon echo; rejects packet or flags freshness anomaly to Backend. | Contract / Unit | #128 / #131 |
| **TM-DIAG-06** | Ciphertext Tampering | Adversary flips 1 bit in encrypted payload or alters `DROPPED_EVENT_COUNT` in transit. | AES-128-CCM tag verification fails ($M=8$). Gateway drops packet fail-closed. Zero data passed to MQTT. | Crypto Vector / Unit | #173 / #131 |
| **TM-DIAG-07** | Slot Intrusion | Node attempts to transmit diagnostic frame during normal DATA slot (Slot 1..15). | Gateway MAC rejects unexpected packet type in DATA slot. Node scheduler logic asserted fail-closed. | Sim / Firmware | #130 / #131 |
| **TM-DIAG-08** | Desync Lockout | Node misses $\ge 3$ consecutive Beacons; enters `HOLDOVER_DESYNCHRONIZED` state. | Node hard-locks RF transmitter. Zero diagnostic or health transmissions until valid Beacon re-acquired. | Firmware / HIL | #178 / #169 |
| **TM-DIAG-09** | Malformed Length | Received packet has `VER_TYPE=0x4A` but payload length is truncated (e.g. 18B) or oversized (e.g. 35B). | Gateway parser rejects invalid frame length fail-closed without buffer over-read. | Fuzzing / Unit | #130 / #131 |
| **TM-DIAG-10** | Unallocated Opcode | Node transmits candidate `0x4A` before Owner wire approval is activated. | Gateway rejects frame as unallocated codepoint. (Asserted active by `test_radio_mac_timing_consistency.py`). | Contract Test | #127 / #201 |
| **TM-DIAG-11** | Backend Idempotency | MQTT broker redelivers identical diagnostic JSON payload twice due to QoS 1 reconnect. | Backend Ingest deduplicates via `(gateway_id, event_id)` or unique constraint on `(node_id, observed_at)`. | Backend Test | #18 / #132 |
| **TM-DIAG-12** | Flash Saturation Stress| Model high-rate alert storm generating 100 drops/second for 10 minutes (stress case, not typical expected rate). | Measure/estimate Flash capacity, wear, write latency, staging bounds and reclaim success; fail safely on full/failed commit. Do not assume batching or NVS wear-leveling proves endurance or committed loss correctness. | Soak / Sim; physical follow-up | #130 / #131 |

### 9.1 DEC-DIAG-03 Mandatory Security Test Plan (NOT_EXECUTED)

| Test ID | Stimulus / failure injection | Expected invariant (PASS requires direct evidence) | Tier / owner |
|:---|:---|:---|:---|
| `TM-DIAG-13` | Dual-core FreeRTOS tasks concurrently enqueue Event, Health and candidate Diagnostic logical requests; force task preemption around counter reservation. | All *new* frames under the same `K_SESSION_UP` have unique nonces; one serialized allocator; zero race/counter duplicates. Current `0x4A` TX remains disabled. | Unit/Stress; #131/#130 |
| `TM-DIAG-14` | Event is transmitted, ACK lost; Node retries the same Event in a later authorized DATA slot. | Identical wire bytes and nonce reused **only for exact same frame**, Gateway dedupes the Event and can recover the ACK without double storage or FIFO deadlock. | Contract/Integration/HIL; #131/#130 |
| `TM-DIAG-15` | Power cut during counter reservation, frame creation, and immediately after TX; repeat with reboot. | No new distinct ciphertext is encrypted/transmitted under a previously used `(Key, Nonce)`; Node fails closed and rejoins when provenance is uncertain. | Fault injection/HIL; #175/#131 |
| `TM-DIAG-16` | Enter sleep/wake; separately attempt an unauthorized retention path with stale RTC counter and old key. | Approved volatile-key path requires safe fresh Join after key loss. Unsupported retained-key rollback cannot permit TX; no retention mechanism silently approved. | Firmware/HIL; #131/#175 |
| `TM-DIAG-17` | Exercise last allowed counter values, wrap attempt and failed rekey. | No counter wrap under a live key; rekey or radio TX lockout before a forbidden value; old session cannot be reused accidentally. | Crypto/Boundary; #173/#131 |
| `TM-DIAG-18` | Alternate `SESSION_SEL` 0/1, rejoin/rekey multiple times, reuse selector and present stale packet/counter from earlier key instance. | Gateway binds replay state to authenticated session instance, not bare selector; stale replay rejected, fresh authenticated session accepted. | Security/Integration; #127/#131 |
| `TM-DIAG-19` | Force allocator queue saturation, task cancellation, encryption failure, and delayed TX; inject a second packet type request. | Ownership is race-safe; no counter is reassigned to a different frame; correct fail-closed/error path; buffers remain bounded. | Unit/Fuzz/Stress; #131/#130 |
| `TM-DIAG-20` | Try to build/parse/transmit candidate `0x4A` before owner-approved versioned wire contract. | Active implementation rejects `0x4A` as unallocated; tests of logical counter scheduling use mocks only; G2 not promoted by test results. | Contract/Negative; #127/#130 |

**Required artifacts before implementation authorization:** Reviewed allocator/call graph; key/session lifecycle and immutable-retry specification; Golden Vectors showing nonce composition and cross-packet uniqueness; unit/contract/integration results for the above scenarios; brownout/sleep HIL data when corresponding implementation paths exist. All eight test cases are **DESIGNED / NOT_RUN** here.

### 9.2 DEC-DIAG-05 Node FIFO Crash-Consistency Test Plan (DESIGNED / NOT_RUN)

**Scope boundary:** These are **Node** FIFO and `DROPPED_EVENT_COUNT` test requirements for #131/#130 and separately scoped physical Node fault injection. **Issue #175 covers Gateway session key-slot NVS only.** No result here establishes an existing PASS.

| Test ID | Trigger / cut point | Expected recoverable invariant | Evidence tier |
|:---|:---|:---|:---|
| `TM-DIAG-21` | Saturate persistent FIFO; accept a replacement Event when capacity is exhausted. | A successful committed eviction replaces exactly the oldest pending Event and increments `DROPPED_EVENT_COUNT` **once**. | Unit / Node HIL |
| `TM-DIAG-22` | Power cut **before** replacement Event staging is durable. | Recover previous valid snapshot; drop counter unchanged. New uncommitted Event is **not guaranteed** preserved. | Fault injection / Node HIL |
| `TM-DIAG-23` | Power cut after staged Event write but **before** metadata commit. | Recover previous valid committed FIFO+counter; ignore uncommitted staging; no phantom drop. | Fault injection / Node HIL |
| `TM-DIAG-24` | Power cut during commit marker/metadata write and just after verified commit. | Recover **either old or new valid committed generation**, never a mixed head/tail/Event/count snapshot. Test torn writes and corruption. | Fault injection / Node HIL |
| `TM-DIAG-25` | Power cut during/after safe reclamation of obsolete Event storage. | Last committed FIFO remains recoverable; committed counter cannot roll back/double increment. | Fault injection / Node HIL |
| `TM-DIAG-26` | Inject NVS full, write/commit error, invalid checksum/generation, repeated reboot. | No silent counter reset, data overwrite or fabricated drop. Preserve evidence; degrade or fail-closed per reviewed design. | Negative / Node HIL |
| `TM-DIAG-27` | Power cut around authenticated `DOWN_EVENT_ACK`, queue-head removal and retry. | No unauthorized event deletion, no lost ACK-state consistency; duplicate event and ACK are idempotently handled. | Integration / Node HIL |
| `TM-DIAG-28` | Sustained bursts with wrap/reclaim, repeated reboot and finite storage. | Prove bounded queue/heap, worst-case commit latency, measured/estimated Flash wear and recovery in actual board/partition configuration; record unsupported windows. | Soak / Node HIL |

**Acceptance hold:** Before claiming `DEC-DIAG-05` implementation PASS, require reviewed `#131` design/code at a known SHA, explicit transaction state machine and generation scheme, Node Flash/NVS configuration, host tests, real-board power-cut logs with cut-point uncertainty, power/current conditions, and an independent Embedded/Hardware review. All `TM-DIAG-21..28` remain **`NOT_RUN / NOT_VERIFIED`** at document creation.

---

## 10. Open Decision Register for Owner Review (Deliverable 8)

**Owner-approved partial design choices (2026-11-07):** `DEC-DIAG-01 = OWNER_APPROVED_FIELD_SELECTION` (retain `DROPPED_EVENT_COUNT`, `DIAG_FLAGS`, `BATTERY_MV`, and `MAINT_SEQ`; exclude TX statistics), `DEC-DIAG-03 Option A = OWNER_APPROVED_DIRECTION` (shared uplink `FRAME_COUNTER`), and `DEC-DIAG-05 = OWNER_APPROVED_DIRECTION` (CoW + coordinated metadata commit + Boot Recovery). **All implementation verification and wire/codepoint decisions remain open**; especially `DEC-DIAG-01` 26B frame offsets and `DEC-DIAG-06` allocation. No wire allocation is made, `0x4A` remains `NOT_APPROVED_WIRE`, and `UP_HEALTH_REPLY` (0x44, 21B) remains frozen:

| Decision ID | Summary of Issue | Options Considered | Status & Proposed Disposition | Impacted Teams |
|:---|:---|:---|:---|:---|
| **DEC-DIAG-01** | Wire Layout Selection for Diagnostic Message | **Option A:** Candidate 1 Compact 23B (historical, includes TX_UNACKED).<br>**Option B:** Candidate 2 Extended 29B (historical, includes TX_ATTEMPT/TX_UNACKED).<br>**Option C:** Candidate 3 TLV 29B/33B (historical).<br>**Option D:** **Candidate 4 Reduced MVP 26B** (4B MAINT_SEQ, 4B DROPPED_EVENT_COUNT, 1B DIAG_FLAGS, 2B BATTERY_MV; no TX statistics). | `PROPOSED / OPEN_DECISION` — Owner **approves field inclusion** of `DROPPED_EVENT_COUNT`, `DIAG_FLAGS`, `BATTERY_MV` (plus `MAINT_SEQ` sequence echo) and **exclusion** of `TX_ATTEMPT_COUNT` / `TX_UNACKED_COUNT` from Diagnostic MVP; **Option D's 26B wire length, offsets, bit meanings and transport remain `PROPOSED / OPEN_WIRE_DECISION`**, requiring contract/security/hardware review before implementation. | MAC / Security / Firmware |
| **DEC-DIAG-02** | TDMA Transmission Opportunity | **Option 1:** Interleave with Health Reply (alternating cadence, ~600s health interval).<br>**Option 2:** Expand Maintenance Superframe ($+N$ slots).<br>**Option 3:** Low-frequency periodic diagnostic superframe (~3600s). | `PROPOSED / OPEN_DECISION` — Propose Option 1 with dynamic health override, balancing zero additional slot allocations against halved health frequency. | MAC Scheduler / Gateway |
| **DEC-DIAG-03** | Frame Counter Domain Binding | **Option A (OWNER SELECTED DESIGN DIRECTION):** Shared `FRAME_COUNTER` under $K_{\text{SESSION\_UP}}$ across newly encrypted Event, Health and future-approved Diagnostic frames, scoped to the authenticated uplink session/key instance.<br>**Option B (NOT SELECTED):** Dedicated derived subkey $K_{\text{DIAG\_UP}}$ with independent counter. | **`OWNER_APPROVED_DIRECTION` (2026-11-07) / `IMPLEMENTATION_NOT_VERIFIED`** — Option A selected; complete `SEC-DIAG-C01..C09` and `TM-DIAG-13..20` security evidence before implementation. No wire approval, no crypto/firmware contract change, `G2=NOT_VERIFIED`. | Security / Crypto / Firmware / HIL |
| **DEC-DIAG-04** | Retransmission Policy | **Option A:** Best-effort unacknowledged (zero MAC retries).<br>**Option B:** Bounded retry in next maintenance superframe.<br>**Option C:** Dedicated downlink diagnostic ACK. | `PROPOSED / OPEN_DECISION` — Propose Option A (Best-Effort Zero Retries) to eliminate RF clutter and preserve airtime margins. | Radio MAC / Firmware |
| **DEC-DIAG-05** | NVS Persistence Strategy & FIFO Atomicity | **OWNER-SELECTED COMBINED DIRECTION:** **Copy-on-Write Event staging + coherent durable metadata commit/generation + Boot Recovery**; preserve persistent NVS Event FIFO and `RING_BUFFER_DROP_OLDEST` counter invariant from `DEC-127-04`. Historical metadata-only / dirty-commit / recovery-only alternatives are not independent approvals. | **`OWNER_APPROVED_DIRECTION` (2026-11-07) / `IMPLEMENTATION_NOT_VERIFIED`**. `REQ-NVS-01..08`, `TM-DIAG-21..28`, storage layout and physical **Node** power-loss tests required before implementation acceptance. #175 is **Gateway key-slot HIL**, not Node FIFO evidence. Brownout ISR Flash writes prohibited. No wire/schema change authorized. | Node Firmware #131 / Node-specific HIL / #130 |
| **DEC-DIAG-06** | Wire Codepoint Assignment Boundary | **Option A:** Allocate candidate `0x4A` (`UP_DIAG_METRICS`) formally in Wire Registry.<br>**Option B:** Maintain `0x4A` as candidate; freeze wire allocation at Gate G2. | `PROPOSED / OPEN_DECISION` — Propose Option B (`NOT_APPROVED_WIRE`), strictly upholding `DEC-MH-08` policy until formal Owner wire allocation. | Project Owner / G2 Gate |

---

## 11. Traceability & Acceptance Disposition

### 11.1 Acceptance Criteria Traceability Matrix
- [x] **AC-1 (Source-Bound Boundaries):** Preserves `UP_HEALTH_REPLY` (0x44, 21B); defines `PENDING_COUNT` as volatile FIFO depth and `DROPPED_EVENT_COUNT` as cumulative loss counter in NVS, with atomicity qualified (Section 1 & 3).
- [x] **AC-2 (Candidate Designs):** Specifies at least two complete candidate designs with bitfields and wire diagrams (Candidate 1 historical 23B, Candidate 2 historical 29B, Candidate 3 historical TLV 29B/33B, Candidate 4 Reduced MVP proposed primary 26B (Section 4)).
- [x] **AC-3 (Trade-off & Airtime Analysis):** Compares physical LoRa ToA at SF7 and SF8, evaluates slot budget feasibility as `THEORETICAL_MODEL / ASSUMED_GUARDS_ONLY`, and analyzes byte efficiencies (Section 5).
- [x] **AC-4 (Field & Semantic Mapping):** Documents qualified rollover handling and Owner-selected CoW + coordinated metadata commit + Boot Recovery as a **design direction** (Section 3). Flash endurance, physical crash consistency, storage layout and runtime implementation are **NOT_VERIFIED**; batching is not presumed approved.
- [x] **AC-5 (Security & Replay Analysis):** Evaluates AES-128-CCM nonce uniqueness, shared frame counter domain failure modes, and epoch binding (Section 6). Owner approved `DEC-DIAG-03 Option A` **direction only**; the `SEC-DIAG-C01..C09` conditions and `TM-DIAG-13..20` tests are DESIGN / NOT_RUN and no implementation security acceptance is claimed.
- [x] **AC-6 (Cross-Layer Impact Matrix):** Produces non-authorizing cross-layer impact matrix distinguishing approved scope from future potential impact across #131, #128, #18/#132, #130, #169, #127, #117 (Section 8).
- [x] **AC-7 (Negative Test Matrix):** Formulates 12-case negative test suite covering overflow, replay, tampering, desync, and idempotency (Section 9).
- [x] **AC-8 (Open Decision Register):** Formulates 6 formal decision candidates marked `PROPOSED / OPEN_DECISION` (Section 10).
- [x] **AC-9 (Allowed Path Integrity):** Strictly confined to `docs/verification/v2-diagnostic-loss-metrics-contract-proposal.md`. Production contracts, ADRs, schemas, and code remain 100% read-only.

### 11.2 Status on Completion
In accordance with the Definition of Done:
- **Operational Status:** `DESIGN_REMEDIATED / READY_FOR_HUMAN_REVIEW / OWNER_WIRE_APPROVAL_PENDING` (`DEC-DIAG-03` and `DEC-DIAG-05` `OWNER_APPROVED_DIRECTION` only; security/Node FIFO implementation `NOT_VERIFIED`)
- **G2 Gate Status:** `NOT_VERIFIED` (pending physical HIL timing #169 and formal Owner wire allocation).
- **Existing Baseline Test Evidence:** Execution of `tests/contract/test_radio_mac_timing_consistency.py` verifies baseline contract invariants (0x41..0x49 active codepoints, 0x4A not implemented on wire, 21B budget saturated). It does **NOT** establish implementation PASS, RF/HIL PASS, or cross-layer integration PASS.
