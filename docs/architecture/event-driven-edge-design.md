# Event-Driven Edge Trigger, Hysteresis, Latch/Clear, and Recovery Design (V2)

> **Document Status:** `PROPOSED_DESIGN / NOT_IMPLEMENTED / RF_HIL_NOT_VERIFIED`  
> **Authority / Provenance:** Successor to Issue #77 (closed `not_planned/SUPERSEDED` under #199 backlog rebaseline); parent architecture #125, #126, merged PR #133.  
> **Interface Dependencies:** Radio MAC V2 (`contracts/radio-mac/specification.md` v0.2.0-DRAFT, #127, PR #198, PR #202, #201 corrective), TDMA Schedule (`contracts/radio-mac/tdma-schedule.md`), MQTT 5.0 contract (`contracts/mqtt/topics.md`), and `contracts/OPEN_DECISIONS.md`.  
> **Allowed Implementation Path:** `docs/architecture/event-driven-edge-design.md` only. All code, wire formats, contracts, and firmware implementations are out of scope.  
> **Numerical Values Invariant:** All numerical thresholds, debounce durations, hysteresis bands, and sampling intervals are strictly **`TBD` pending Owner physical calibration and real-hardware measurement (#169)**.

---

## 1. Executive Summary & Architectural Scope

This design document specifies a bounded, deterministic, Node-local edge event trigger algorithm for sensor threshold evaluation, noise suppression (hysteresis and debounce), latching/clear transitions, and power-loss recovery on the ESP32-WROOM-32E + SX1276 Sensor Node.

Under the approved V2 architecture (#125, #127, PR #133), the system enforces:
1. **Local Alarm Autonomy:** When a sensor violation is qualified, the Node immediately triggers local physical actuators (buzzer, warning LED, relay) without awaiting RF transmission, TDMA slot arrival, Gateway acknowledgment, or Backend permission.
2. **Event-Only RF Data Plane:** Continuous periodic application telemetry (`DATA_TELEMETRY`) is completely abolished. The SX1276 radio transmits application data **only** when a discrete, qualified Event occurs (`UP_EVENT`, opcode `0x41`, 26 octets).
3. **Static DATA Slot Execution:** Normal application Event transmissions occur **exclusively** within the Node's pre-assigned Static TDMA DATA slot via the durable Event queue (#131). There is **no contention access**, no priority contention backoff (no PCSS/CAD application data access), and no unscheduled transmission.
4. **Boundary Separation:** The Node generates a local monotonic `EVENT_REF` (4-byte unsigned integer). The Gateway and Backend originate the canonical, network-wide business `event_id`. RF hop acknowledgment (`DOWN_EVENT_ACK`, opcode `0x42`) strictly represents single-hop RF delivery to the Gateway's local persistent WAL/SQLite buffer; it **does not represent a Backend PostgreSQL database commit or human operator acknowledgment**.

```
[ Sensor Input ] 
       │ (ADC / I2C / SPI samples)
       ▼
┌────────────────────────────────────────────────────────┐
│  Node Edge Trigger Engine (This Document - Issue #203) │
│  - Validity checking & noise filtering                │
│  - Hysteresis band & time-window debounce             │
│  - One-event-per-transition latching & clear logic    │
│  - Reset / power-loss state consistency               │
└──────────────┬──────────────────────────┬──────────────┘
               │ (Immediate)              │ (Local Event Intent)
               ▼                          ▼
      ┌─────────────────┐       ┌────────────────────────────────┐
      │   Local Alarm   │       │   Durable Event FIFO (#131)    │
      │   Autonomy      │       │   - RING_BUFFER_DROP_OLDEST    │
      │ (Buzzer/LED/IO) │       │   - Persistent DROPPED_COUNT   │
      └─────────────────┘       └──────────────┬─────────────────┘
                                               │ (Own Static Slot)
                                               ▼
                                ┌────────────────────────────────┐
                                │   SX1276 Radio Owner (TDMA)    │
                                │   - UP_EVENT (0x41) 26B TX     │
                                │   - DOWN_EVENT_ACK (0x42) RX   │
                                └────────────────────────────────┘
```

---

## 2. Trust Boundaries, Identities, and the Four-Layer Confirmation Model

### 2.1 Identity Hierarchy and Trust Boundaries

| Level | Component | Identity Generated | Durability Scope | Trust Boundary |
|---|---|---|---|---|
| **Local Trigger** | Edge Trigger Engine | `INTENT_LOCAL_ID` | In-memory RAM; transient across warm sampling loops | Local to Node CPU task; non-authoritative |
| **Node Firmware** | NVS Event Queue (#131) | `EVENT_REF` (uint32 BE) | Persisted in NVS Flash; strictly monotonic increment | Edge device boundary; encrypted with $K_{\text{SESSION\_UP}}$ |
| **Gateway RF** | Gateway Radio Owner | `RF_ACK` (`DOWN_EVENT_ACK`) | Committed to Gateway local WAL/SQLite before ACK TX | Radio link hop boundary; confirms radio reception only |
| **Backend / DB** | Go Backend Monolith | Canonical `event_id` | Committed to PostgreSQL via `(gateway_id, event_id)` | Enterprise business authority; originates global identity |

### 2.2 The Four-Layer Confirmation Model (Non-Equivalence)

In accordance with `contracts/mqtt/topics.md` §9 and `contracts/radio-mac/specification.md` §1:
1. **Layer 1: RF Hop Acknowledgment (`DOWN_EVENT_ACK 0x42`):** Acknowledges that the Gateway received and authenticated the 26-byte `UP_EVENT` frame and staged it locally. Upon receiving this, the Node removes the event from its unacknowledged retry list or marks it latched.
2. **Layer 2: MQTT Transport Acknowledgment (`PUBACK`):** Mosquitto broker acknowledges receipt of the MQTT QoS 1 publish packet from the Gateway. This guarantees broker transit only; it does **not** prove Backend database ingestion.
3. **Layer 3: Backend Database Persistence (`DB Commit`):** The Go Backend verifies deduplication via `UNIQUE(gateway_id, event_id)` in PostgreSQL and commits the record. The event is now officially part of the durable system state.
4. **Layer 4: UI Operator Acknowledgment (`API Acknowledge`):** A human operator calls `POST /api/v1/alerts/{id}/acknowledge` from the Next.js Web or Android client. **This layer never triggers a Downlink RF frame to the Node.**

> [!IMPORTANT]
> The Node must never assume that an RF ACK indicates backend persistence, nor wait for a backend response before asserting its local hardware alarm.

---

## 3. Sensor Sampling Input & Threshold Specification

### 3.1 Input Interface Definition

The Edge Trigger Engine accepts discrete sensor readings from hardware drivers (ADC, I2C, SPI) formatted as a structured sample record:

```c
typedef struct {
    uint32_t sample_seq;       /* Monotonic sample sequence number since boot */
    uint64_t sample_mono_us;   /* Monotonic host timer (esp_timer_get_time) in microseconds */
    int16_t  raw_value;        /* Calibrated sensor measurement in standard units */
    uint8_t  channel_id;       /* Physical sensor channel identifier */
    uint8_t  quality_flags;    /* Bitmask: VALID, CLIPPED, NOISE_GLITCH, BUS_ERROR */
} sensor_sample_t;
```

#### Quality Flags Bitmask:
- `SAMPLE_FLAG_VALID` (`0x01`): Reading passed hardware CRC, sanity bounds, and electrical checks.
- `SAMPLE_FLAG_CLIPPED` (`0x02`): Reading reached hardware ADC/sensor rail saturation.
- `SAMPLE_FLAG_DEGRADED` (`0x04`): Transient bus re-try succeeded; data usable with caution.
- `SAMPLE_FLAG_INVALID` (`0x80`): Hardware communication failure, sensor disconnected, or CRC error.

### 3.2 Parameter Units and Fixed-Point Representation

To avoid non-deterministic floating-point operations in ISR/FreeRTOS embedded tasks and ensure bit-exact cross-platform behavior:
- **Temperature:** Signed 16-bit integer, unit: centi-degrees Celsius ($0.01^\circ\text{C}$). Range: $-4000$ to $+12500$ ($-40.00^\circ\text{C}$ to $+125.00^\circ\text{C}$).
- **Relative Humidity:** Unsigned 16-bit integer, unit: centi-percent RH ($0.01\%\text{ RH}$). Range: $0$ to $10000$ ($0.00\%$ to $100.00\%$).
- **Gas / Smoke Concentration:** Unsigned 16-bit integer, unit: parts per million (ppm) or scaled ADC raw millivolts.
- **Physical Button / Discrete Switch:** Boolean state (`0 = INACTIVE`, `1 = ACTIVE`), owned separately under #149.

### 3.3 Threshold Versioning and Ownership

- **Configuration Owner:** The Backend Go Monolith owns sensor policy profiles (upper/lower thresholds, hysteresis bands, debounce parameters).
- **Distribution Mechanism:** Configuration updates are delivered via authorized Maintenance Downlink management frames (or initial factory provisioning).
- **Version Tracking:** The Node maintains a 16-bit configuration generation counter (`CONFIG_GENERATION`). Every evaluated sample is stamped with the active `CONFIG_GENERATION`. If the Node detects an unverified or corrupt configuration in NVS, it reverts to factory fail-closed safe defaults and flags a configuration fault.

### 3.4 Numerical Parameters Invariant (`TBD`)

All numerical operational values are strictly **`TBD`** pending empirical testing on hardware revision HW-001 (Issue #169). No hardcoded constant in this design shall be construed as approved for production:
- Sampling period: $T_{\text{sample}} = \text{TBD ms}$ (trade-off between battery life and detection latency).
- Upper violation threshold: $T_{\text{upper}} = \text{TBD}$ (engineering units).
- Hysteresis release threshold: $T_{\text{lower}} = T_{\text{upper}} - \Delta H = \text{TBD}$.
- Violation debounce duration: $t_{\text{debounce\_violation}} = \text{TBD ms}$ ($N_{\text{debounce\_violation}}$ samples).
- Clear debounce duration: $t_{\text{debounce\_clear}} = \text{TBD ms}$ ($N_{\text{debounce\_clear}}$ samples).
- Fault sample limit: $K_{\text{fault\_limit}} = \text{TBD consecutive samples}$.

---

## 4. Algorithm Requirements & Invariants

### 4.1 Mandatory Invariants

1. **INV-01 (One-Event-Per-Transition):** Exactly one `EVENT_VIOLATION` intent is handed to the durable queue upon entering the qualified violation state. The Node **must not** emit repeated event intents while the sensor sample continuously remains above the threshold.
2. **INV-02 (Local Alarm Autonomy):** Local alarm GPIO pins (buzzer, warning LED) are driven high immediately upon qualifying the threshold transition, with latency $\le 10\text{ ms}$ from the qualifying sample, irrespective of LoRa radio status or TDMA slot timing.
3. **INV-03 (Noise Immunity / Hysteresis):** Once a violation is triggered, the state remains `LATCHED` until the physical sensor reading drops strictly below the lower release threshold $T_{\text{lower}} = T_{\text{upper}} - \Delta H$ and remains there for the full clear debounce period $t_{\text{debounce\_clear}}$.
4. **INV-04 (Zero Duplicate Intent Across Reboot):** If the Node experiences a warm or cold reset while a violation condition persists:
   - The Node reconstructs its latched state from NVS.
   - If the previous event was already committed to the durable queue (#131), the Node **must not** generate a duplicate event intent.
   - If the previous event was in volatile debounce RAM and not yet qualified, the debounce timer restarts cleanly from zero in the `ARMED` state.
5. **INV-05 (Bounded Memory & Static Allocation):** The Edge Trigger Engine operates entirely within static memory structures. No dynamic heap allocation (`malloc`, `free`) is permitted during runtime sampling.
6. **INV-06 (Fail-Closed on Sensor Loss):** If $K_{\text{fault\_limit}}$ consecutive samples return `SAMPLE_FLAG_INVALID`, the engine enters `STATE_ERROR`, deactivates the threshold evaluator, sets a local hardware fault indicator, and does not emit spurious violation events.
7. **INV-07 (No Unscheduled RF Access):** The Edge Trigger Engine never commands the SX1276 radio. It only submits structured intents into the durable queue (#131). The radio schedule is strictly governed by the TDMA scheduler.

---

## 5. Candidate Algorithms & Trade-Off Comparison

To ensure an optimal balance between false alarm rejection, detection latency, power consumption, and Flash endurance, three algorithmic candidates were evaluated:

### 5.1 Evaluated Candidates

#### Candidate A: Dual-Threshold Hysteresis with Consecutive-Sample Time-Window Debounce (Proposed Candidate)
- **Mechanism:** Maintains an upper threshold $T_{\text{upper}}$ and lower threshold $T_{\text{lower}}$ forming a deadband $\Delta H$. When $S \ge T_{\text{upper}}$, a debounce counter $C_{\text{violation}}$ increments. If $C_{\text{violation}} \ge N_{\text{violation}}$, the engine transitions to `LATCHED` and fires the event intent. Clearing requires $S \le T_{\text{lower}}$ continuously for $N_{\text{clear}}$ samples.
- **Characteristics:** Minimal RAM footprint (12 bytes context), zero floating-point math, deterministic state transitions, highly resistant to thermal drift oscillation.

#### Candidate B: Exponential Moving Average (EMA) Low-Pass Filter with Single Threshold
- **Mechanism:** Computes $\bar{S}_k = \alpha S_k + (1-\alpha) \bar{S}_{k-1}$ using fixed-point integer arithmetic. Triggers when $\bar{S}_k \ge T_{\text{threshold}}$.
- **Characteristics:** Smooths high-frequency Gaussian noise, but introduces an asymmetric phase lag proportional to $\frac{1}{\alpha}$, potentially delaying rapid fire or shock detection. Susceptible to lingering near threshold during slow ramps.

#### Candidate C: Median-of-5 Sliding Window with Latch State Machine
- **Mechanism:** Stores the last 5 samples in a ring buffer, sorts them to obtain the median value $S_{\text{med}}$, and evaluates $S_{\text{med}}$ against a threshold with an immediate latch.
- **Characteristics:** Exceptional immunity against single-sample spike outliers (e.g. electrical motor noise on ADC line), but requires buffer shifting and branch-heavy sorting on every sample, increasing CPU active time and battery drain.

### 5.2 Comparative Analysis Matrix

| Evaluation Criterion | Candidate A: Dual-Threshold Hysteresis + Debounce (Proposed) | Candidate B: EMA Low-Pass Filter | Candidate C: Median-of-5 Window |
|---|---|---|---|
| **Oscillation Immunity** | **Superior:** Hysteresis band $\Delta H$ mathematically eliminates limit-cycle oscillation at the threshold boundary. | **Moderate:** High-frequency noise reduced, but slow baseline drift still causes edge oscillations without deadband. | **Moderate:** Eliminates isolated spikes; vulnerable to sustained noisy transitions near threshold. |
| **Missed Event Risk** | **Low:** Deterministic count window guarantees capture of sustained signals $\ge t_{\text{debounce}}$. | **Medium:** Fast, high-amplitude transient pulses may be damped out below threshold. | **Low:** Captures multi-sample steps reliably. |
| **Detection Latency** | Bounded exactly to $N_{\text{violation}} \times T_{\text{sample}}$. | Variable; depends on pulse amplitude relative to filter step response ($3$ to $5 \times \tau$). | Fixed lag of $\lfloor W/2 \rfloor \times T_{\text{sample}}$ samples. |
| **CPU & Energy Budget** | **Optimal:** 2 integer comparisons and 1 increment per sample. Minimal active time for ESP32 deep-sleep cycling. | Low: Fixed-point MAC instructions, but requires multiply/shift operations. | Medium: Sorting 5 values incurs branch mispredictions and memory swaps per sample. |
| **Flash Endurance Impact** | **Optimal:** Strictly enforces one-event-per-transition; zero duplicate writes during persistent violation. | Low: Requires additional hysteresis logic to prevent repeated writes during boundary hover. | Low: Same as A if combined with latch. |
| **Failure Modes** | Missing/invalid sample resets pending debounce count cleanly; no filter state contamination. | Invalid sample contaminates filter history for multiple sampling cycles ($\sim 5\tau$). | Corrupt sample persists in buffer for $W$ cycles until shifted out. |
| **Formal Recommendation** | **PROPOSED CANDIDATE for V2 MVP.** | Rejected for MVP (phase lag and filter contamination risks). | Rejected for MVP (unnecessary CPU sorting overhead on battery). |

---

## 6. Deterministic State Machine & Pseudocode

### 6.1 State Definitions

```
                     ┌──────────────────┐
                     │  UNINITIALIZED   │
                     └────────┬─────────┘
                              │ Init & Self-Test OK
                              ▼
                     ┌──────────────────┐
        ┌───────────►│      ARMED       │◄───────────┐
        │            └────────┬─────────┘            │
        │                     │ S >= T_upper         │
        │ Clear Debounce      ▼                      │ Violation Debounce
        │ Expired     ┌──────────────────┐           │ Canceled (S < T_upper)
        │             │VIOLATION_PENDING ├───────────┘
        │             └───────┬──────────┘
        │                     │ S >= T_upper for N_viol samples
        │                     ▼
        │             ┌──────────────────┐
        │             │     LATCHED      │ (Local Alarm ON, Event Intent Dispatched)
        │             └───────┬──────────┘
        │                     │ S <= T_lower
        │                     ▼
        │             ┌──────────────────┐
        └─────────────┤  CLEAR_PENDING   │
                      └───────┬──────────┘
                              │ S > T_lower (Re-trigger)
                              ▼
                         (To LATCHED)
```

1. **`STATE_UNINITIALIZED`:** System boot or hard reset. NVS state is loaded; hardware sensors are validated. Transitions to `ARMED` once configuration is verified.
2. **`STATE_ARMED`:** Monitoring baseline. Sensor reading is within normal operating limits ($S < T_{\text{upper}}$). Local alarm is OFF.
3. **`STATE_VIOLATION_PENDING`:** Sensor reading has met or exceeded $T_{\text{upper}}$. The debounce timer is active. If the reading drops below $T_{\text{upper}}$ before $N_{\text{violation}}$ samples, the state reverts to `ARMED` without generating an event.
4. **`STATE_LATCHED`:** Qualified violation state. Entered when $S \ge T_{\text{upper}}$ for $N_{\text{violation}}$ consecutive samples.
   - **Immediate Actions:** Drive local alarm GPIO active; generate a single `EVENT_INTENT` with local timestamp and enqueue to #131 NVS FIFO; persist `LATCHED` bit in NVS.
5. **`STATE_CLEAR_PENDING`:** Sensor reading has dropped below $T_{\text{lower}}$. Clear debounce timer is running. If reading spikes back above $T_{\text{lower}}$, returns to `LATCHED`.
6. **`STATE_ERROR`:** Sensor hardware fault, bus timeout, or invalid sample limit reached. Local trouble indicator set; threshold evaluation halted.

### 6.2 State Transition Matrix

| Current State | Trigger / Condition | Next State | Actions Executed |
|---|---|---|---|
| `UNINITIALIZED` | Self-test PASS, Config valid, NVS latch clean | `ARMED` | Reset debounce counters, de-assert local alarms. |
| `UNINITIALIZED` | Self-test PASS, Config valid, NVS latch SET | `LATCHED` | Restore local alarm, restore latched state, DO NOT re-emit event intent. |
| `ARMED` | Valid sample $S \ge T_{\text{upper}}$ | `VIOLATION_PENDING` | Start violation debounce counter: $C_{\text{viol}} \leftarrow 1$. |
| `ARMED` | Valid sample $S < T_{\text{upper}}$ | `ARMED` | Reset counters: $C_{\text{viol}} \leftarrow 0$. |
| `VIOLATION_PENDING` | Valid sample $S \ge T_{\text{upper}}$ and $C_{\text{viol}} + 1 < N_{\text{viol}}$ | `VIOLATION_PENDING` | Increment counter: $C_{\text{viol}} \leftarrow C_{\text{viol}} + 1$. |
| `VIOLATION_PENDING` | Valid sample $S \ge T_{\text{upper}}$ and $C_{\text{viol}} + 1 \ge N_{\text{viol}}$ | `LATCHED` | 1. Assert local alarm GPIO (buzzer/LED);<br>2. Generate local `EVENT_INTENT`;<br>3. Commit `EVENT_INTENT` to #131 NVS FIFO;<br>4. Mark NVS latch state = `ACTIVE`;<br>5. Reset $C_{\text{viol}} \leftarrow 0$. |
| `VIOLATION_PENDING` | Valid sample $S < T_{\text{upper}}$ | `ARMED` | Debounce cancelled. Reset $C_{\text{viol}} \leftarrow 0$. |
| `LATCHED` | Valid sample $S > T_{\text{lower}}$ | `LATCHED` | Maintain alarm; suppress all RF intents (INV-01). |
| `LATCHED` | Valid sample $S \le T_{\text{lower}}$ | `CLEAR_PENDING` | Start clear debounce counter: $C_{\text{clear}} \leftarrow 1$. |
| `CLEAR_PENDING` | Valid sample $S \le T_{\text{lower}}$ and $C_{\text{clear}} + 1 < N_{\text{clear}}$ | `CLEAR_PENDING` | Increment counter: $C_{\text{clear}} \leftarrow C_{\text{clear}} + 1$. |
| `CLEAR_PENDING` | Valid sample $S \le T_{\text{lower}}$ and $C_{\text{clear}} + 1 \ge N_{\text{clear}}$ | `ARMED` | 1. De-assert local alarm (or set to clear mode);<br>2. Clear NVS latch state;<br>3. Optional: dispatch local `EVENT_CLEAR` intent (see Open Decisions);<br>4. Reset $C_{\text{clear}} \leftarrow 0$. |
| `CLEAR_PENDING` | Valid sample $S > T_{\text{lower}}$ | `LATCHED` | Clear debounce aborted. Reset $C_{\text{clear}} \leftarrow 0$. |
| Any State | Consecutive invalid samples $\ge K_{\text{fault\_limit}}$ | `STATE_ERROR` | Set hardware trouble pin; log internal diagnostic; stop alarm trigger. |
| `STATE_ERROR` | Valid sample received and self-test PASS | `ARMED` | Clear error pin; reset state context to initial `ARMED`. |

### 6.3 Algorithmic Pseudocode

```c
/*
 * Event-Driven Edge Trigger Engine - Candidate Algorithm A
 * Note: Pure design pseudocode. Constants are marked TBD.
 */

#define TBD_UPPER_THRESHOLD       /* TBD: e.g. 5500 (55.00 deg C) */
#define TBD_HYSTERESIS_BAND       /* TBD: e.g. 500  (5.00 deg C)   */
#define TBD_N_VIOLATION_SAMPLES   /* TBD: e.g. 3 consecutive samples */
#define TBD_N_CLEAR_SAMPLES       /* TBD: e.g. 5 consecutive samples */
#define TBD_MAX_FAULT_SAMPLES     /* TBD: e.g. 4 consecutive samples */

typedef enum {
    TRIGGER_STATE_UNINITIALIZED = 0,
    TRIGGER_STATE_ARMED,
    TRIGGER_STATE_VIOLATION_PENDING,
    TRIGGER_STATE_LATCHED,
    TRIGGER_STATE_CLEAR_PENDING,
    TRIGGER_STATE_ERROR
} trigger_state_t;

typedef struct {
    trigger_state_t state;
    int16_t  threshold_upper;
    int16_t  threshold_lower;
    uint16_t n_violation_target;
    uint16_t n_clear_target;
    uint16_t count_violation;
    uint16_t count_clear;
    uint16_t count_fault;
    uint16_t config_generation;
    bool     nvs_latched;
} trigger_context_t;

static trigger_context_t g_trigger_ctx;

void Trigger_Init(const trigger_config_t *config, bool nvs_was_latched) {
    g_trigger_ctx.threshold_upper = config->upper_threshold;   /* TBD */
    g_trigger_ctx.threshold_lower = config->upper_threshold - config->hysteresis_delta; /* TBD */
    g_trigger_ctx.n_violation_target = config->n_violation_samples; /* TBD */
    g_trigger_ctx.n_clear_target = config->n_clear_samples;         /* TBD */
    g_trigger_ctx.config_generation = config->config_generation;
    g_trigger_ctx.count_violation = 0;
    g_trigger_ctx.count_clear = 0;
    g_trigger_ctx.count_fault = 0;
    g_trigger_ctx.nvs_latched = nvs_was_latched;

    if (nvs_was_latched) {
        /* Device rebooted while violation was active */
        g_trigger_ctx.state = TRIGGER_STATE_LATCHED;
        Hardware_SetLocalAlarm(true);
        /* Invariant INV-04: DO NOT generate duplicate event intent into #131 */
    } else {
        g_trigger_ctx.state = TRIGGER_STATE_ARMED;
        Hardware_SetLocalAlarm(false);
    }
}

void Trigger_ProcessSample(const sensor_sample_t *sample) {
    /* 1. Validate sample integrity */
    if (!(sample->quality_flags & SAMPLE_FLAG_VALID) || 
         (sample->quality_flags & SAMPLE_FLAG_INVALID)) {
        g_trigger_ctx.count_fault++;
        if (g_trigger_ctx.count_fault >= TBD_MAX_FAULT_SAMPLES) {
            g_trigger_ctx.state = TRIGGER_STATE_ERROR;
            Hardware_SetFaultIndicator(true);
        }
        return;
    }
    g_trigger_ctx.count_fault = 0;

    /* 2. Execute deterministic state machine */
    switch (g_trigger_ctx.state) {
    case TRIGGER_STATE_ARMED:
        if (sample->raw_value >= g_trigger_ctx.threshold_upper) {
            g_trigger_ctx.count_violation = 1;
            g_trigger_ctx.state = TRIGGER_STATE_VIOLATION_PENDING;
        }
        break;

    case TRIGGER_STATE_VIOLATION_PENDING:
        if (sample->raw_value >= g_trigger_ctx.threshold_upper) {
            g_trigger_ctx.count_violation++;
            if (g_trigger_ctx.count_violation >= g_trigger_ctx.n_violation_target) {
                /* Threshold qualified: Transition to LATCHED */
                g_trigger_ctx.state = TRIGGER_STATE_LATCHED;
                g_trigger_ctx.nvs_latched = true;
                g_trigger_ctx.count_violation = 0;

                /* Execute Invariant INV-02: Immediate Local Alarm */
                Hardware_SetLocalAlarm(true);

                /* Execute Invariant INV-01: One-Event-Per-Transition Intent */
                event_intent_t intent = {
                    .event_code = EVENT_CODE_SENSOR_THRESHOLD_EXCEEDED,
                    .sample_value = sample->raw_value,
                    .sample_time = sample->sample_mono_us,
                    .config_gen = g_trigger_ctx.config_generation
                };
                
                /* Hand off to #131 Persistent FIFO */
                NVS_PersistLatchState(true);
                Queue_HandoffEventIntent(&intent);
            }
        } else {
            /* Noise glitch: Reading dropped below threshold before debounce expired */
            g_trigger_ctx.count_violation = 0;
            g_trigger_ctx.state = TRIGGER_STATE_ARMED;
        }
        break;

    case TRIGGER_STATE_LATCHED:
        /* Reading remains above clear threshold: suppress all duplicate intents */
        if (sample->raw_value <= g_trigger_ctx.threshold_lower) {
            g_trigger_ctx.count_clear = 1;
            g_trigger_ctx.state = TRIGGER_STATE_CLEAR_PENDING;
        }
        break;

    case TRIGGER_STATE_CLEAR_PENDING:
        if (sample->raw_value <= g_trigger_ctx.threshold_lower) {
            g_trigger_ctx.count_clear++;
            if (g_trigger_ctx.count_clear >= g_trigger_ctx.n_clear_target) {
                /* Sustained clear qualified: Re-arm engine */
                g_trigger_ctx.state = TRIGGER_STATE_ARMED;
                g_trigger_ctx.nvs_latched = false;
                g_trigger_ctx.count_clear = 0;

                Hardware_SetLocalAlarm(false);
                NVS_PersistLatchState(false);

                /* Optional: Emit CLEAR event intent if required by policy */
                Trigger_HandleClearNotification(sample);
            }
        } else {
            /* Reading rose back above lower threshold: abort clear debounce */
            g_trigger_ctx.count_clear = 0;
            g_trigger_ctx.state = TRIGGER_STATE_LATCHED;
        }
        break;

    case TRIGGER_STATE_ERROR:
        /* Sensor recovery check */
        Hardware_SetFaultIndicator(false);
        g_trigger_ctx.state = TRIGGER_STATE_ARMED;
        break;

    default:
        g_trigger_ctx.state = TRIGGER_STATE_ERROR;
        break;
    }
}
```

---

## 7. Sample Traces & Boundary Scenarios

### Trace 1: Clean Threshold Crossing & Qualified Latch
- **Setup:** Upper threshold $T_{\text{upper}} = 50.0^\circ\text{C}$, Debounce $N_{\text{viol}} = 3$ samples. $T_{\text{sample}} = 1000\text{ ms}$.
- **Events & State Flow:**

| Step | Sample Time ($t$) | Value ($S$) | State | Counter | Local Alarm | Event Intent Created | Comments |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| 1 | $10.0\text{ s}$ | $48.2^\circ\text{C}$ | `ARMED` | 0 | OFF | None | Normal baseline operation. |
| 2 | $11.0\text{ s}$ | $50.5^\circ\text{C}$ | `VIOLATION_PENDING` | 1 | OFF | None | First threshold crossing ($S \ge T_{\text{upper}}$). |
| 3 | $12.0\text{ s}$ | $51.2^\circ\text{C}$ | `VIOLATION_PENDING` | 2 | OFF | None | Second consecutive sample. |
| 4 | $13.0\text{ s}$ | $52.0^\circ\text{C}$ | `LATCHED` | 0 | **ON** | **1 Intent** | **Qualified!** Alarm activated; intent sent to #131. |
| 5 | $14.0\text{ s}$ | $52.5^\circ\text{C}$ | `LATCHED` | 0 | ON | None | Violation continues; duplicate suppressed (INV-01). |

---

### Trace 2: High-Frequency Noise & Oscillation Rejection
- **Setup:** $T_{\text{upper}} = 50.0^\circ\text{C}$, Lower $T_{\text{lower}} = 45.0^\circ\text{C}$ ($\Delta H = 5.0^\circ\text{C}$). Debounce $N = 3$.
- **Demonstration:** Sensor hovers rapidly around $50^\circ\text{C}$ due to electrical pickup.

| Step | Sample Time ($t$) | Value ($S$) | State | Counter | Local Alarm | Event Intent Created | Comments |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| 1 | $20.0\text{ s}$ | $50.2^\circ\text{C}$ | `VIOLATION_PENDING` | 1 | OFF | None | Spike above threshold. |
| 2 | $21.0\text{ s}$ | $49.8^\circ\text{C}$ | `ARMED` | 0 | OFF | None | Drops below threshold; debounce canceled immediately. |
| 3 | $22.0\text{ s}$ | $50.3^\circ\text{C}$ | `VIOLATION_PENDING` | 1 | OFF | None | Second spike; debounce starts anew. |
| 4 | $23.0\text{ s}$ | $49.9^\circ\text{C}$ | `ARMED` | 0 | OFF | None | Glitch cancels debounce; zero false alarms emitted. |
| 5 | $24.0\text{ s}$ | $48.5^\circ\text{C}$ | `ARMED` | 0 | OFF | None | Noise suppressed completely without RF impact. |

---

### Trace 3: Sustained Violation, Recovery, and Clear Latch
- **Setup:** $T_{\text{upper}} = 50.0^\circ\text{C}$, $T_{\text{lower}} = 45.0^\circ\text{C}$ ($\Delta H = 5.0^\circ\text{C}$). Clear Debounce $N_{\text{clear}} = 3$.

| Step | Sample Time ($t$) | Value ($S$) | State | Counter | Local Alarm | Event Intent Created | Comments |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---|
| 1 | $30.0\text{ s}$ | $51.0^\circ\text{C}$ | `LATCHED` | 0 | ON | None | System is latched in active alarm. |
| 2 | $31.0\text{ s}$ | $47.0^\circ\text{C}$ | `LATCHED` | 0 | ON | None | Below $T_{\text{upper}}$, but above $T_{\text{lower}}$: **Hysteresis holds latch**. |
| 3 | $32.0\text{ s}$ | $44.5^\circ\text{C}$ | `CLEAR_PENDING` | 1 | ON | None | Reading drops strictly below $T_{\text{lower}}$ ($45.0^\circ\text{C}$). |
| 4 | $33.0\text{ s}$ | $44.0^\circ\text{C}$ | `CLEAR_PENDING` | 2 | ON | None | Second clear sample. |
| 5 | $34.0\text{ s}$ | $43.8^\circ\text{C}$ | `ARMED` | 0 | **OFF** | Optional Clear | **Clear qualified!** Local alarm cleared; re-armed. |

---

### Trace 4: Sudden Reboot / Power Loss During Violation
- **Scenario:** Node loses power at $t = 13.5\text{ s}$ while in `STATE_LATCHED` with the initial event committed to NVS FIFO.
- **Recovery Behavior:**
  1. At power restoration ($t = 15.0\text{ s}$), `Trigger_Init()` inspects the NVS latch record.
  2. Finds `nvs_was_latched == true`.
  3. Transitions directly to `STATE_LATCHED` and drives local alarm ON immediately.
  4. **Strictly suppresses creating a new event intent** (INV-04), because the event already exists in the #131 NVS FIFO waiting for the next assigned static TDMA DATA slot.
  5. Gateway receives the original un-ACKed `UP_EVENT` frame without duplicate event generation.

---

### Trace 5: Sensor Disconnection / CRC Bus Failure
- **Scenario:** I2C pull-up resistor fails or cable disconnects; readings return `SAMPLE_FLAG_INVALID`.
- **Fault Handling:**
  1. First invalid sample: Engine increments `count_fault = 1`. Active violation debounce is suspended.
  2. Successive invalid samples accumulate up to $K_{\text{fault\_limit}} = 4$.
  3. Upon reaching $K_{\text{fault\_limit}}$, the engine transitions to `STATE_ERROR`.
  4. Local trouble indicator is set; no spurious `UP_EVENT` violation frame is transmitted over LoRa RF.

---

## 8. Queue-Full & Persistence Handoff Policy (#131 & DEC-127-04)

When a qualified threshold violation occurs, the Edge Trigger Engine hands off an `event_intent_t` to the persistent queue module (#131).

```
   ┌────────────────────────────────────────────────────────┐
   │         Edge Trigger Engine: Event Intent             │
   └──────────────────────────┬─────────────────────────────┘
                              │ Enqueue Intent
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │         Persistent NVS Event FIFO Queue (#131)         │
   │  Capacity: N_MAX_EVENTS (e.g. 16 or 32 records)        │
   │  Policy: RING_BUFFER_DROP_OLDEST (DEC-127-04)          │
   ├────────────────────────────────────────────────────────┤
   │  If Queue is FULL when new Event arrives:              │
   │  1. Discard oldest untransmitted event record          │
   │  2. Atomically increment DROPPED_EVENT_COUNT in NVS    │
   │  3. Insert new Event Intent at tail of FIFO            │
   └──────────────────────────┬─────────────────────────────┘
                              │ Report via Diagnostics
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │  UP_DIAG_METRICS (0x4A, 23B) via Maintenance Slot      │
   │  (DEC-MH-08 / #204 - Distinct from Health 0x44)        │
   └────────────────────────────────────────────────────────┘
```

1. **Queue Capacity Limit:** The NVS FIFO queue holds a bounded number of events ($N_{\text{max\_events}} = \text{TBD}$, e.g. 16 to 32 slots).
2. **Buffer Full Policy (`DEC-127-04`):** If the queue is saturated due to extended gateway outage or radio jamming, the queue driver executes **`RING_BUFFER_DROP_OLDEST`**:
   - The oldest unacknowledged event is dropped from Flash to ensure the most recent emergency alert is preserved.
   - The 32-bit monotonic counter `DROPPED_EVENT_COUNT` is committed in NVS.
3. **Observability:** `DROPPED_EVENT_COUNT` is later reported out-of-band via `UP_DIAG_METRICS` (`0x4A`, 23 octets) during authorized maintenance slots, keeping data loss visible to the backend.

---

## 9. Composition Model with #149 (GPIO Button Trigger)

The system supports two distinct physical trigger domains that operate concurrently on the Sensor Node:
- **Domain A (This Document - Issue #203):** Continuous or sampled analog/digital sensor threshold monitoring (temperature, gas, smoke).
- **Domain B (Issue #149):** Physical push-button interrupt and deep-sleep wake-up GPIO.

```
┌─────────────────────────────────┐       ┌─────────────────────────────────┐
│     Sensor Threshold Trigger    │       │     GPIO Button Wake Trigger    │
│     (Issue #203 - This Spec)    │       │     (Issue #149 - Separate)     │
│  - Hysteresis & Debounce        │       │  - Mechanical Debounce          │
│  - Local Alarm Autonomy         │       │  - Deep-Sleep Wake Source       │
│  - State Machine (ARMED/LATCH)  │       │  - Button Click Qualification   │
└────────────────┬────────────────┘       └────────────────┬────────────────┘
                 │ Event Intent                            │ Event Intent
                 │ (Code: SENSOR_ALARM)                    │ (Code: BUTTON_PRESS)
                 ▼                                         ▼
         ┌─────────────────────────────────────────────────────────┐
         │         Shared Durable Event Queue FIFO (#131)          │
         │  - Strict Arrival-Time Sequencing (FIFO)                │
         │  - Atomic NVS Enqueue                                   │
         │  - RING_BUFFER_DROP_OLDEST Overflow                     │
         └────────────────────────────┬────────────────────────────┘
                                      │ Single Channel Output
                                      ▼
         ┌─────────────────────────────────────────────────────────┐
         │    SX1276 Radio Owner (Static TDMA DATA Slot Only)      │
         │    - Transmits 1 UP_EVENT (0x41) per assigned slot      │
         │    - No preemption, no out-of-slot priority CAD         │
         └─────────────────────────────────────────────────────────┘
```

### 9.1 Rules of Composition

1. **Independent Sensing & Autonomous Actuation:**
   - The button handler (#149) operates via GPIO edge interrupts and deep-sleep RTC wake.
   - The sensor engine (#203) runs in a scheduled periodic sampling task or ADC conversion callback.
   - A button press does **not** alter the internal state machine of the sensor threshold engine (it does not clear a latched temperature alarm unless an explicit operator re-arm procedure is approved).
2. **Unified Queue Multiplexing into #131:**
   - Both domains produce standardized `event_intent_t` packets.
   - Intents are enqueued into the shared #131 NVS FIFO on a first-come, first-served basis.
3. **No RF Preemption or Out-of-Slot Transmission:**
   - Neither the button press nor the sensor threshold trigger possesses an "urgent RF bypass" capability.
   - Under V2 MAC, **all** application frames are transmitted strictly within the Node's allocated Static DATA Slot. Unscheduled contention transmission (PCSS/CAD) for normal alerts is strictly prohibited.

---

## 10. Test & Verification Matrix (Unit, Simulation, HIL)

> **Verification Notice:** All test items below represent design specifications and verification plans. In compliance with project governance, all items remain **`NOT_RUN / NOT_VERIFIED`** until verified on real hardware with documented execution receipts.

| Test ID | Test Category | Target Component | Scenario Description | Expected Outcome | Verification Status |
|---|---|---|---|---|:---:|
| **TC-EDGE-01** | Unit (Mocked) | State Machine | Clean single step above $T_{\text{upper}}$ sustained for $N_{\text{viol}}$ samples. | Exactly 1 `EVENT_INTENT` created; local alarm pin goes HIGH on $N$-th sample. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-02** | Unit (Mocked) | State Machine | Glitch spike above $T_{\text{upper}}$ for $N-1$ samples followed by drop. | Counter resets to 0; 0 intents created; local alarm remains LOW. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-03** | Unit (Mocked) | Hysteresis | Sustained value hovering between $T_{\text{lower}}$ and $T_{\text{upper}}$ after latch. | State remains `LATCHED`; local alarm stays HIGH; 0 duplicate intents. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-04** | Unit (Mocked) | Clear Logic | Value strictly below $T_{\text{lower}}$ for $N_{\text{clear}}$ consecutive samples. | State transitions to `ARMED`; local alarm pin returns to LOW. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-05** | Unit / NVS Mock | Recovery | Simulated power cut in `LATCHED` state, followed by reboot with active reading. | State resumes as `LATCHED`; alarm immediately ON; 0 new intents enqueued. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-06** | Unit (Fault) | Sensor Driver | Inject $K_{\text{fault}}$ consecutive `SAMPLE_FLAG_INVALID` readings. | Enters `STATE_ERROR`; fault pin asserted; 0 false alarm events generated. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-07** | Integration | Queue Handoff | Trigger event when #131 FIFO is at full capacity ($N_{\text{max}}$). | Oldest event evicted; `DROPPED_EVENT_COUNT` incremented; new intent saved. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-08** | Physical HIL | Hardware HW-001 | Real ESP32-WROOM-32E thermal chamber ramp test with buzzer output (#169). | Buzzer activates within $10\text{ ms}$ of qualified threshold sample. | `NOT_RUN / NOT_VERIFIED` |
| **TC-EDGE-09** | Physical HIL | Hardware HW-001 | Concurrent button press (#149) and thermal trip during single TDMA cycle. | Both events stored in FIFO; transmitted in successive TDMA slots without loss. | `NOT_RUN / NOT_VERIFIED` |

---

## 11. Traceability & Open Decisions

### 11.1 Source Traceability Matrix

| Requirement / Decision | Governing Authority | Location / Artifact Reference | Architectural Compliance |
|---|---|---|---|
| **Event-Only Data Plane** | Owner Architecture Approval | Issue #125, #126, merged PR #133 | Fully compliant; continuous telemetry eliminated. |
| **Local Alarm Autonomy** | Owner Architecture Approval | PR #133, `contracts/radio-mac/specification.md` §1 | Fully compliant; hardware alarms assert independently of RF. |
| **Static DATA Slot Only** | V2 Radio MAC Specification | `contracts/radio-mac/specification.md` §3, PR #198 | Fully compliant; no PCSS/CAD application data transmission. |
| **Queue Overflow Policy** | Owner Decision `DEC-127-04` | `contracts/OPEN_DECISIONS.md` | Fully compliant; `RING_BUFFER_DROP_OLDEST` specified. |
| **Four-Layer Confirmation** | MQTT & Architecture Spec | `contracts/mqtt/topics.md` §9 | Fully compliant; RF ACK decoupled from Backend DB commit. |
| **Button Separation** | Hardware & Wake Scope | Issue #149 | Fully compliant; GPIO wake owned under #149, composition defined. |
| **Timing & Physical Profile** | Physical RF Timing Verification | Issue #169, #201 corrective | Compliant; all numerical parameters left strictly as `TBD`. |

### 11.2 Open Decisions Pending Owner Disposition

| Decision ID | Summary of Issue | Alternative Options | Impact / Recommendation | Status |
|---|---|---|---|:---:|
| **OD-EDGE-01** | **Clear Event RF Transmission:** Should the return-to-normal transition (`STATE_CLEAR_PENDING` $\to$ `ARMED`) generate an over-the-air `UP_EVENT`? | **Option 1:** Yes, send a clear event (`EVENT_CODE_CLEAR`) via TDMA.<br>**Option 2:** No, clear state is purely local; remote status is inferred from subsequent Health replies (`0x44`). | Option 1 is recommended for safety-critical monitoring, but consumes 1 TDMA DATA slot airtime. | `OPEN_DECISION` |
| **OD-EDGE-02** | **Sampling Cadence vs Battery Life:** Balance between sampling interval $T_{\text{sample}}$ and ESP32 power consumption. | **Option 1:** Fast sampling ($100\text{ ms}$) with higher active CPU power.<br>**Option 2:** Duty-cycled ULP coprocessor / timer wake ($1000\text{ ms}$) for multi-year battery operation. | Pending real physical board power measurements under #169. | `OPEN_DECISION` |
| **OD-EDGE-03** | **Dynamic Threshold Reconfiguration:** Can thresholds be modified during runtime without full device re-provisioning? | **Option 1:** Fixed compile-time / provisioning-time NVS configuration only.<br>**Option 2:** Authorized Downlink Maintenance command to update `threshold_upper` and increment `CONFIG_GENERATION`. | Option 2 is architecturally supported via `CONFIG_GENERATION`, awaiting management contract. | `OPEN_DECISION` |

---

## 12. Human Review Sign-Off & Handoff

This document is submitted as an architectural design proposal for Issue #203. Before any firmware coding begins under Wave 2 implementation issues, formal cross-functional technical human review is required:

| Reviewing Discipline | Role / Scope of Review | Required Verifications | Human Review Disposition |
|---|---|---|:---:|
| **Node Firmware Lead** | Embedded state machine, memory bounds, FreeRTOS task safety, and NVS endurance. | Verify static memory allocation, absence of heap malloc in sampling path, and NVS write frequency bounds. | `PENDING_HUMAN_REVIEW` |
| **Radio MAC / TDMA Lead** | Conformance with V2 TDMA schedule and queue handoff to #131. | Confirm no contention or unscheduled RF transmission; verify slot handoff rules. | `PENDING_HUMAN_REVIEW` |
| **Backend & Security Lead** | Identity separation (`EVENT_REF` vs `event_id`) and four-layer confirmation model. | Verify that Gateway originates business `event_id` and Backend DB commit semantics are preserved. | `PENDING_HUMAN_REVIEW` |
| **QA / Test Lead** | Testability of state machine, simulation vectors, and boundary traces. | Verify test matrix completeness and feasibility of physical HIL testing under #169. | `PENDING_HUMAN_REVIEW` |
