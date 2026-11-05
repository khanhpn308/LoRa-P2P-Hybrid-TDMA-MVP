# SX1276 Driver Operations Guide


## 1. Physical Hardware Interface and Strapping Pins (HW-001)

The SX1276 communicates with the ESP32-WROOM-32E host through an SPI bus, an active-low reset line, and a single interrupt line (DIO0):

| Signal | ESP32 GPIO | Pin Type | Notes & Operational Constraints |
|---|---|---|---|
| `SCK` | **GPIO5** | ESP32 Output | Max frequency: $10\text{ MHz}$. **Caution:** ESP32 strapping pin. Must idle LOW in SPI Mode 0 and not force an invalid strapping state during ESP32 reset. |
| `MISO` | **GPIO19** | ESP32 Input | High-impedance when NSS is high. Data changes on falling edge of SCK. |
| `MOSI` | **GPIO27** | ESP32 Output | Master changes data on falling edge; SX1276 samples on rising edge. |
| `NSS` (`CS`) | **GPIO18** | ESP32 Output | Active-low chip select. Asserted for duration of SPI transaction. |
| `RESET` | **GPIO23** | ESP32 Output | Active-low hardware reset. Configure as open-drain output. |
| `DIO0` | **GPIO26** | ESP32 Input | Configured as edge-triggered interrupt. Maps to `TxDone`, `RxDone`, or `CadDone`. |
| `DIO1`–`DIO5` | **NOT_CONNECTED** | — | Unrouted on PCB. Signals mapped to DIO1–DIO5 (including `RxTimeout`) **cannot** generate hardware interrupts on the ESP32. |

---

## 2. SPI Protocol and Transaction Framing


### Protocol Parameters
- **SPI Mode:** Mode 0 (**CPOL = 0, CPHA = 0**). SCK idles low. MOSI changes on falling edge and is sampled on rising edge.
- **Maximum Clock Speed:** $F_{SCK} \le 10\text{ MHz}$. (Recommended driver speed: 4 to 8 MHz).
- **Address Byte Format:** Every SPI transaction begins with an 8-bit command byte shifted MSB first:
  - Bit 7 (`wnr`): Write / not-Read bit. `1` indicates write access; `0` indicates read access.
  - Bits 6:0: 7-bit register address (`0x00` to `0x7F`).
- **Read-during-Write Response:** During any write transaction, the byte shifted out on MISO while the address byte is being clocked in contains the existing (prior) value of that register.

### Transaction Types
1. **Single Register Access:**
   - Assert NSS low $\to$ Send Address (`wnr | Addr`) $\to$ Read or write single data byte $\to$ De-assert NSS high.
2. **Burst Register Access (Non-FIFO):**
   - Assert NSS low $\to$ Send Address $\to$ Stream multiple bytes while holding NSS low $\to$ De-assert NSS high.
   - The SX1276 internal address pointer automatically increments after each byte transferred.
3. **FIFO Burst Access (`Address = 0x00`):**
   - Assert NSS low $\to$ Send Address `0x00` (or `0x80` for write) $\to$ Stream payload bytes $\to$ De-assert NSS high.
   - The internal address pointer **remains held at `0x00`** and does not auto-increment, allowing rapid bulk transfer of packet payloads into/out of the 256-byte FIFO RAM buffer.

### Reset Timing Limits
- MOSI setup time: $\ge 30\text{ ns}$ before rising SCK edge.
- MOSI hold time: $\ge 20\text{ ns}$ after rising SCK edge.
- NSS setup time: $\ge 30\text{ ns}$ from falling NSS to first rising SCK edge.
- NSS hold time: $\ge 100\text{ ns}$ from last falling SCK edge to rising NSS edge.
- NSS high idle time between transactions: $\ge 20\text{ ns}$.

---

## 3. Reset Dynamics and Chip Health Verification


### Hardware Reset Procedures
1. **Power-On Reset (POR):**
   - Occurs automatically at initial power application. If $V_{DD}$ was disconnected, wait **at least 10 ms** before starting SPI communication. `NRESET` must remain floating during POR.
2. **Manual Hardware Reset (GPIO23):**
   - Pull GPIO23 low for a **minimum of 100 microseconds ($\ge 100\text{ }\mu\text{s}$)**.
   - Release GPIO23 to floating/high-impedance.
   - Wait a **minimum of 5 milliseconds ($\ge 5\text{ ms}$)** before initiating SPI transactions. (Recommended driver delay: 10 ms).
   - *Current Transient:* While `NRESET` is low, supply current may increase by up to 1 mA.

### Chip Health Check
Immediately after reset recovery, the driver must verify SPI communication by reading `RegVersion` (`0x42`):
- Expected value: **`0x12`** (bits 7:4 revision code `0x1`, bits 3:0 mask revision `0x2`).
- If read value is `0x00`, `0xFF`, or anything other than `0x12`, the SPI bus is broken or unpowered. The driver must fail initialization and enter safe fault recovery.

---

## 4. Operating Modes and State Machine Transitions


| Operating Mode | Mode Code (`RegOpMode[2:0]`) | Oscillator & PLL | RF / PA Block | FIFO RAM Status | Permitted Operations |
|---|---|---|---|---|---|
| **SLEEP** | `000` | OFF (lowest power) | OFF | **Cleared & inaccessible** | **Only mode where `LongRangeMode` (LoRa/FSK switch) can be changed.** Registers writable. |
| **STDBY** | `001` | Crystal ON; PLL OFF | OFF | Retained & accessible | Normal staging mode. Registers and FIFO accessible. |
| **FSTX** | `010` | Crystal ON; PLL locked (TX) | OFF | Retained | Synthesizer tune; usually automated via TX. |
| **TX** | `011` | Crystal ON; PLL locked (TX) | PA active | Retained | Transmits packet. **Automatically returns to STDBY upon `TxDone`.** |
| **FSRX** | `100` | Crystal ON; PLL locked (RX) | OFF | Retained | Synthesizer tune; usually automated via RX. |
| **RXCONTINUOUS**| `101` | Crystal ON; PLL locked (RX) | Demodulator ON | Retained; writes RX data | Continuously listens. Does not time out. Does not return to STDBY. |
| **RXSINGLE** | `110` | Crystal ON; PLL locked (RX) | Demodulator ON | Retained; writes RX data | Listens for `SymbTimeout`. **Automatically returns to STDBY on `RxDone` or `RxTimeout`.** |
| **CAD** | `111` | Crystal ON; PLL locked | Demodulator ON | Retained | Samples channel for 1 symbol. **Automatically returns to STDBY upon `CadDone`.** |

### Transition Invariants
1. Changing between LoRa and FSK/OOK (`LongRangeMode`, bit 7 of `RegOpMode`) is **only allowed in SLEEP mode**. Attempts to write bit 7 in STDBY, TX, or RX are silently ignored.
2. Entering SLEEP mode **wipes the FIFO RAM**. Never stage TX data in FIFO and then enter SLEEP.
3. The silicon automatically reverts to `STDBY` after TX, RX Single, or CAD operations. Driver state machines must mirror this automatic transition.
4. **TDMA Network Role Policies & Mode Lifecycles:**
   - **Node Lifecycle:**
     - Baseline state is ESP32 Deep-sleep / radio low power (#149).
     - Event detection (button/sensor) triggers local alarm and stages durable pending Event; **no immediate RF TX on event**.
     - In authorized own DATA slot (#125/#131): Wake $\to$ `STDBY` $\to$ `TX` (Event frame) $\to$ automatically reverts to `STDBY` upon `TxDone` $\to$ configure `RegDioMapping1` for `RxDone` $\to$ enter `RXSINGLE` during bounded ACK window $\to$ upon authenticated ACK, return to Deep-sleep. If ACK missing or invalid, preserve the pending Event and retry only in a subsequent authorized own DATA slot; do not switch to unrestricted continuous listening.
     - Scheduled Maintenance: Wake before scheduled Maintenance reception slot $\to$ enter `RXSINGLE` to receive Gateway `SYNC_BEACON` $\to$ transition to `STDBY` $\to$ `TX` (`HEALTH_REPLY` in Node's permitted response slot) $\to$ return to Deep-sleep. Maintenance is not RX-only; no DATA/Maintenance/ACK overlap.
   - **Gateway Lifecycle:**
     - Baseline state is `RXCONTINUOUS` during scheduled receive phases (including DATA RX windows).
     - Half-duplex radio transitions: To transmit an authenticated Event ACK or scheduled `SYNC_BEACON`, Gateway Radio Owner executes: `RXCONTINUOUS` $\to$ `STDBY` $\to$ stage payload in FIFO $\to$ configure DIO0 for `TxDone` $\to$ `TX` $\to$ wait `TxDone` (reverts to `STDBY`) $\to$ reconfigure DIO0 for `RxDone` $\to$ return to `RXCONTINUOUS`. The Gateway cannot receive while transmitting its own packets.

---

## 5. Radio Owner Task and Interrupt Architecture

### Concurrency and Mutex Policy
All physical access to the SX1276 SPI bus must be serialized through a single FreeRTOS **Radio Owner Task**:
- A dedicated FreeRTOS mutex guards the SPI bus peripheral.
- Interrupt Service Routines (ISRs) on GPIO26 (DIO0) **must never** execute SPI transactions, heap allocations, or blocking FreeRTOS calls.
- The DIO0 ISR simply issues a direct-to-task notification (`vTaskNotifyGiveFromISR`) to the Radio Owner Task and yields if a higher-priority task wakes (`portYIELD_FROM_ISR`).

### DIO0 Pin Multiplexing (`RegDioMapping1` at `0x40`)
Because DIO1–DIO5 are not connected, the driver must dynamically reconfigure DIO0 for the desired event prior to entering an operational mode:

| Desired Event | `Dio0Mapping` Bits (`0x40[7:6]`) | Mode Code in `RegOpMode` | Expected Interrupt Flag |
|---|---|---|---|
| **Transmit Done** | `01` | `011` (`TX`) | `TxDone` (`RegIrqFlags[3]`) |
| **Receive Done** | `00` | `110` (`RXSINGLE`) or `101` (`RXCONT`) | `RxDone` (`RegIrqFlags[6]`) |
| **CAD Complete** | `10` | `111` (`CAD`) | `CadDone` (`RegIrqFlags[2]`) |

### Interrupt Flag Clearing Semantics
Flags in `RegIrqFlags` (`0x12`) are **cleared by writing a `1`** to the corresponding bit. Writing a `0` has no effect. Setting a bit to `1` in `RegIrqFlagsMask` (`0x11`) prevents the event from driving the DIO pin, but the flag will still set in `RegIrqFlags`.

---

## 6. Packet Transmission (TX) Sequence


```text
[STANDBY] ──> Set FifoAddrPtr = FifoTxBaseAddr (0x80)
          ──> Burst-write payload into RegFifo (0x00)
          ──> Write payload byte length into RegPayloadLength (0x22)
          ──> Configure DIO0 = 01 (TxDone) in RegDioMapping1 (0x40)
          ──> Set Mode = TX (0x83) in RegOpMode (0x01)
          ──> [Radio transmits over air; PA ramps down; asserts TxDone]
          ──> Radio automatically reverts to STANDBY
          ──> DIO0 pulses high ──> ISR notifies Radio Owner Task
          ──> Radio Owner Task clears TxDone flag (write 0x08 to RegIrqFlags)
```

**Driver Rule:** Never access `RegFifo` or modify modem registers while `Mode == TX`.

---

## 7. Packet Reception (RX) Lifecycle, Timeout, and IRQ Architecture


### 7.1. RX Event & Termination Taxonomy

To ensure deterministic firmware state machine transitions, the driver distinguishes five mutually exclusive event categories:

1. **`RX_PACKET_DONE`:**
   - Physical packet demodulation completed successfully.
   - Asserted by the SX1276 via `RxDone` (`RegIrqFlags[6]`) on the physical DIO0 interrupt line.
2. **`HW_RX_TIMEOUT`:**
   - Hardware-level preamble hunt timeout asserted by the SX1276 (`RegIrqFlags[7] == 1`).
   - In `RxSingle` mode, this occurs when no valid preamble is detected within the programmed `RegSymbTimeout` window (or when carrier lock is lost due to severe RF perturbation). The transceiver autonomously returns to `STANDBY`.
3. **`HOST_WATCHDOG_EXPIRED`:**
   - An ESP32 FreeRTOS software supervision timer expired without a hardware interrupt or observable demodulation activity.
   - Requires explicit driver arbitration to verify whether the transceiver stalled or is actively receiving.
4. **`RX_ABORTED_BY_SCHEDULE`:**
   - The upper-layer MAC scheduler (e.g., Static TDMA slot deadline) commands the driver to terminate the RX session because the allocated time slot has elapsed.
   - **Crucial Rule:** TDMA slot expiration is an architectural schedule abort, **never to be conflated with a silicon `HW_RX_TIMEOUT`**.
5. **`RX_ABORTED_BY_RECOVERY`:**
   - Fail-safe abort triggered by driver fault-handling policies (e.g., SPI communication failure, demodulator lockup beyond maximum theoretical packet duration, or invalid register state).

---

### 7.2. Silicon Demodulator Behavior in RX Single Mode

**RX Single hardware behavior:** `RxTimeout` is suppressed while SX1276 is receiving packet data. If demodulation loses track of the packet, SX1276 raises `RxTimeout` and returns to `STDBY`. Reception takes priority over the preamble-search timeout.

#### The "Preamble Near Window End" Hazard & Host Supervision Rule
- In `RxSingle` mode, `RegSymbTimeout` defines the time window to search for a preamble:
  $$T_{search} = \text{SymbTimeout} \times T_s$$
- If a transmitter begins sending a packet near the end of this search window (e.g., at symbol 9.5 of a 10-symbol hunt window), the SX1276 hardware detects the preamble, sets `RegModemStat[0]` (`SignalDetected`) and `RegModemStat[1]` (`SignalSynchronized`), raises `ValidHeader` (`RegIrqFlags[4]`), and continues receiving payload data.
- **The hardware `RxTimeout` interrupt is inhibited while demodulation is in progress.**
- Total physical packet duration $T_{packet} = (N_{preamble} + 4.25 + N_{payload}) \times T_s$ ($51.456\text{ ms}$ for SF7/BW125k/PL16, $118.016\text{ ms}$ for 64B, or up to $399.616\text{ ms}$ for max payload of 255B).
- Because DIO1 (`RxTimeout`) is **`NOT_CONNECTED`** on HW-001, the ESP32 host must run a software supervision timer.
- **DANGER:** If the host watchdog was set only to $T_{search} + T_{guard}$, the host timer would expire while the radio is actively demodulating a valid packet. **Forcibly writing `Mode = STANDBY` upon host timer expiry would kill a valid packet in mid-air.**

---

### 7.3. Two-Stage Bounded Host Supervision Policy

To avoid killing valid packets while maintaining bounded execution and preventing infinite lockup, the Radio Owner task implements a two-stage supervision algorithm:

```text
[Host Starts RX Single]
        │
        ├──> Pre-clear stale IRQs (write 0xFF to RegIrqFlags)
        ├──> Enter RXSINGLE (RegOpMode = 0x86)
        └──> Arm Stage 1 Host Search Timer:
             T_host_search = T_symb_timeout + T_guard_search
                    │
                    ▼
    Wait for DIO0 (RxDone) or Host Timer Expiry
                    │
       ┌────────────┴──────────────────────────┐
       ▼                                       ▼
[DIO0 Asserted (RxDone)]              [Host Search Timer Expired]
       │                                       │
       ▼                                       ▼
Execute Strict RX Validation Pipeline      Read Snapshot: RegIrqFlags (0x12)
(Check CrcOnPayload, PayloadCrcError,                     RegModemStat (0x18)
 Bounds, FIFO copy, MAC delivery)              │
                                               ├─> Priority 1: RxDone == 1?
                                               │   └── Packet arrived at timer expiry (Race).
                                               │       Process as RX_PACKET_DONE!
                                               │
                                               ├─> Priority 2: RxTimeout == 1?
                                               │   └── Silicon confirmed timeout; radio in STANDBY.
                                               │       Clear flag (write 0x80).
                                               │       Emit HW_RX_TIMEOUT.
                                               │
                                               ├─> Priority 3: Active Demodulation in Progress?
                                               │   (ValidHeader == 1 OR RxOnGoing == 1 OR
                                               │    [SignalSynchronized == 1 AND HeaderInfoValid == 1])
                                               │   └── DO NOT ABORT! DO NOT FORCE STANDBY!
                                               │       Grant Bounded Demodulation Extension:
                                               │       T_demod_max = T_packet(PL_max) + T_guard_demod
                                               │       Wait on DIO0 until T_demod_max expires.
                                               │       ├─> RxDone asserted -> RX_PACKET_DONE.
                                               │       └─> Expired -> Fail-safe abort (RX_ABORTED_BY_RECOVERY).
                                               │
                                               └─> Priority 4: Inactive / Unresponsive
                                                   (RxDone==0, RxTimeout==0, RxOnGoing==0)
                                                   └── Transceiver idle without IRQ latch.
                                                       Perform Pre-Abort Re-check:
                                                       Re-read RegIrqFlags (0x12) immediately prior to abort.
                                                       ├─> RxDone latched -> Divert to RX_PACKET_DONE.
                                                       └─> Otherwise -> Force STANDBY (RegOpMode = 0x81).
                                                           Clear all IRQs (write 0xFF).
                                                           Emit HOST_WATCHDOG_EXPIRED.
```

#### Timing Parameter Governance:
- $T_{symb\_timeout} = \text{SymbTimeout} \times T_s$ ($T_s = 1.024\text{ ms}$ for SF7/BW125k).
- $T_{guard\_search}$ (`CONFIG_SX1276_RX_SEARCH_GUARD_MS`): Host FreeRTOS tick & task switch margin (**`TBD / NOT_VERIFIED`**).
- $T_{packet}(PL_{max})$: Maximum theoretical Time-on-Air for approved profile at maximum payload length ($51.456\text{ ms}$ for 16B; $118.016\text{ ms}$ for 64B; $399.616\text{ ms}$ for 255B).
- $T_{guard\_demod}$ (`CONFIG_SX1276_RX_DEMOD_GUARD_MS`): Demodulation margin accounting for crystal frequency drift (**`TBD / NOT_VERIFIED`**).

#### Arbitration & Pre-Abort Re-Check Policy (FIX-10)

Because asynchronous RF packet arrival over the air is inherently concurrent with synchronous host SPI bus execution, the Radio Owner task implements a strict arbitration policy to resolve contention between host abort decisions and late packet completion:

| Scenario | Radio Owner Action / Decision Point | Silicon Register Snapshot (`RegIrqFlags`, `RegModemStat`) | Arbitration Resolution | Final Radio Mode | IRQ / Driver Action | Resulting Event / Classification |
|---|---|---|---|---|---|---|
| **Scenario A: Normal or Late Arrival** | Host search timer expires or DIO0 asserts | `RxDone == 1` (Bit 6 asserted) | **Packet takes priority over timer.** Immediate packet acceptance; do NOT abort. | Auto `STANDBY` (`0x81`) | Execute strict validation pipeline; targeted clear (`snapshot & 0x70`). | `RX_PACKET_DONE` |
| **Scenario B: Packet In-Flight at Deadline** | Host search timer expires or TDMA slot boundary reached | `RxDone == 0`, but `RxOnGoing == 1` or `ValidHeader == 1` (Demodulator active) | **Check Slot Flexibility:**<br>1. *Flexible Slot:* Grant bounded extension $T_{packet}(PL_{max}) + T_{guard}$ to allow packet to finish.<br>2. *Hard Slot Deadline:* Bounded extension not permitted. Must abort. | If flexible: remain `RXSINGLE`.<br>If hard deadline: force `STANDBY` (`0x81`). | If flexible: await DIO0.<br>If hard deadline: clear all IRQs (`0xFF`), log in-flight packet truncation. | If flexible: `EXTENDED_DECODING`.<br>If hard deadline: `RX_ABORTED_BY_SCHEDULE`. |
| **Scenario C: Definite Timeout / Idle** | Host timer expires | `RxDone == 0`, `RxTimeout == 1` (or `ModemStat` completely idle: `0x00`) | **Definite expiration.** Silicon has timed out and automatically transitioned to `STANDBY`, or channel is completely idle. | Auto `STANDBY` (`0x81`) (or verified idle). | Clear `RxTimeout` (`write 0x80`) or clean IRQs. | `HW_RX_TIMEOUT` (if bit 7) or `HOST_WATCHDOG_EXPIRED`. |
| **Scenario D: Pre-Abort Re-Check Latch** | Host preparing to write `STANDBY` on watchdog or schedule abort | First read showed `RxDone == 0`, but **Pre-Abort Re-read** of `RegIrqFlags` reveals `RxDone == 1` | **Abort cancelled.** The packet finished arriving while the host was arbitrating the decision. Divert immediately to packet processing. | Auto `STANDBY` (`0x81`) | Cancel `STANDBY` write; execute strict validation pipeline; targeted clear (`snapshot & 0x70`). | `RX_PACKET_DONE` |
| **Scenario E: DIO0 ISR Interrupt Preemption** | Host preparing abort sequence | DIO0 interrupt fires on ESP32 while host task is preparing abort | **Hardware ISR takes precedence.** Abort sequence is cancelled. Host wakes on task notification and services `RxDone`. | Auto `STANDBY` (`0x81`) | Discard pending abort; process packet through validation pipeline; targeted clear (`snapshot & 0x70`). | `RX_PACKET_DONE` |
| **Scenario F: Residual Race Window (Hardware Boundary)** | Host issues SPI write `RegOpMode = STANDBY` | Packet finishes on silicon in the sub-microsecond gap *after* the pre-abort SPI read but *before* the SPI write byte takes effect | **Hardware Race Boundary.** The silicon receives the `STANDBY` command and aborts internal demodulation / resets state machine. | Force `STANDBY` (`0x81`) | The in-flight frame or late arriving packet is truncated or lost. | `RX_ABORTED_BY_SCHEDULE` / `HOST_WATCHDOG_EXPIRED` (with packet loss). |

> [!CAUTION]
> **Residual Race Boundary and Zero-Packet-Loss Limitations:**
> Because the SX1276 SPI bus transaction is discrete and non-atomic relative to continuous, asynchronous RF energy arriving over the air, there is an unavoidable hardware residual race condition between the final SPI byte of the pre-abort `RegIrqFlags` read and the first clock cycle of the SPI write putting the radio into `STANDBY`. If RF packet reception finishes inside this narrow window, the frame will be discarded when `STANDBY` is commanded.
> **Firmware developers and system architects are strictly prohibited from claiming that zero packet loss can be achieved by register polling or software supervision alone.** In half-duplex packet radio systems, eliminating residual packet loss at slot boundaries requires protocol-level synchronization (TDMA guard bands) and MAC-layer retransmissions (ARQ).

> [!WARNING]
> **TDMA Slot Deadline Abort & In-Flight Truncation Risk:**
> When a hard TDMA time slot deadline is reached, the Radio Owner task must abort the reception and return the transceiver to `STANDBY` to protect subsequent slot transmissions. This forced abort must be classified and logged as `RX_ABORTED_BY_SCHEDULE` (never disguised as `HW_RX_TIMEOUT`). If a packet was in-flight (`RxOnGoing == 1`), forcing `STANDBY` truncates the frame in mid-air, causing a known and expected packet loss at the PHY boundary.

---

### 7.4. IRQ Cleanup Architecture Across All RX Paths

The SX1276 interrupt architecture relies on strict hardware invariants:
1. **Radio Owner Task Exclusivity:** The Radio Owner task is the **sole task** permitted to execute SPI transactions and alter SX1276 registers.
2. **DIO0 ISR Role:** The DIO0 interrupt service routine performs a **notification only** (e.g., `vTaskNotifyGiveFromISR()`). **Zero SPI transactions are executed in ISR context.**
3. **Pre-Clear Stale IRQs:** Before entering any RX state (`RXSINGLE` or `RXCONT`), the driver writes `0xFF` to `RegIrqFlags` (`0x12`) to purge any lingering flags from prior activity.
4. **Snapshot Before Clear:** The driver reads `RegIrqFlags` (`0x12`), `RegModemStat` (`0x18`), `RegHopChannel` (`0x1C`), and `RegRxNbBytes` (`0x13`) into a local snapshot before issuing clear commands.
5. **Write-1-to-Clear Semantics:** Writing a `1` bit to `RegIrqFlags` clears that specific interrupt. Writing a `0` bit leaves it unchanged.
6. **Mode Transition Separation:**
   - In `RxSingle`, the SX1276 silicon automatically transitions to `STANDBY` upon `RxDone` or `RxTimeout`. Clearing `RegIrqFlags` does **not** alter radio mode.
   - In `RxContinuous`, the SX1276 remains in `RXCONT` across packets. The driver must clear `RxDone` while remaining in `RXCONT`.

#### Strict RX Validation & MAC Delivery Pipeline
When `RxDone` asserts on DIO0, the driver processes the packet through a strict gating pipeline before MAC handover:
```text
RxDone (DIO0 interrupt snapshot)
  │
  ├──> 1. Read RegIrqFlags (0x12) & RegHopChannel (0x1C)
  │
  ├──> 2. Inspect RegHopChannel.CrcOnPayload (0x1C[6])
  │         └── If CrcOnPayload == 0: REJECT & DISCARD (Missing Payload CRC)
  │
  ├──> 3. Inspect RegIrqFlags.PayloadCrcError (0x12[5])
  │         └── If PayloadCrcError == 1: REJECT & DISCARD (CRC Mismatch)
  │
  ├──> 4. Read RegRxNbBytes (0x13) & Validate Host Buffer Bounds
  │         └── If Length == 0 or Length > CONFIG_SX1276_HOST_RX_BUFFER_SIZE: REJECT & DISCARD
  │
  ├──> 5. Read Payload Data from RegFifo (0x00)
  │         └── Set RegFifoAddrPtr = RegFifoRxCurrentAddr (0x10)
  │         └── Burst-read RegRxNbBytes into host buffer
  │
  ├──> 6. Deliver to Custom MAC Validation Layer
  │         └── Hand off clean frame for MAC frame counter, session, and HMAC/MIC checks
  │
  └──> 7. Clear IRQ Flags in RegIrqFlags (0x12)
            └── Write 1 to clear asserted bits (write 0x70: RxDone, PayloadCrcError, ValidHeader)
```

> [!IMPORTANT]
> **Reject if CRC Absent:** Under the Owner-approved `PHY_PROFILE_MVP_V1` contract (`Payload CRC = ON`), a packet received without CRC (`CrcOnPayload == 0`) is strictly non-compliant and **must be rejected immediately**, even though `PayloadCrcError` will read 0. Do not deliver unverified packets to the MAC layer.

#### State Transition & Cleanup Table

| Current State | Event / Trigger | Condition / Snapshot | Next State | Radio Mode | IRQ Cleanup Action | Telemetry / Return Code |
|---|---|---|---|---|---|---|
| `RX_STANDBY` | `CMD_START_RX_SINGLE` | Valid config, BaseAddr set | `RX_SINGLE_SEARCH` | `RXSINGLE` (`0x86`) | Pre-clear stale IRQs (`write 0xFF`) | `OK` |
| `RX_SINGLE_SEARCH` | DIO0 High (`RxDone`) | `CrcOnPayload=1`, `PayloadCrcError=0`, Length valid | `RX_COMPLETED` | Auto `STANDBY` (`0x81`) | Snapshot, copy FIFO, clear `0x70` | `RX_PACKET_DONE` |
| `RX_SINGLE_SEARCH` | DIO0 High (`RxDone`) | `CrcOnPayload=0` (Missing mandatory CRC) | `RX_STANDBY` | Auto `STANDBY` (`0x81`) | Snapshot, discard FIFO, clear `0x70` | `REJECT_MISSING_CRC` |
| `RX_SINGLE_SEARCH` | DIO0 High (`RxDone`) | `PayloadCrcError=1` (Corrupted CRC) | `RX_STANDBY` | Auto `STANDBY` (`0x81`) | Snapshot, discard FIFO, clear `0x70` | `REJECT_CRC_ERROR` |
| `RX_SINGLE_SEARCH` | DIO0 High (`RxDone`) | Length == 0 or Length < MAC_MIN | `RX_STANDBY` | Auto `STANDBY` (`0x81`) | Snapshot, discard FIFO, clear `0x70` | `REJECT_INVALID_LENGTH` |
| `RX_SINGLE_SEARCH` | DIO0 High (`RxDone`) | Length > host buffer capacity | `RX_STANDBY` | Auto `STANDBY` (`0x81`) | Snapshot, discard FIFO, clear `0x70`, increment overflow metric | `REJECT_HOST_BUFFER_OVERFLOW` |
| `RX_SINGLE_SEARCH` | Host Search Timer Expired | `RegIrqFlags[7] (RxTimeout) == 1` | `RX_STANDBY` | Auto `STANDBY` (`0x81`) | Clear `0x80` (`RxTimeout`) | `HW_RX_TIMEOUT` |
| `RX_SINGLE_SEARCH` | Host Search Timer Expired | `ValidHeader=1` or `RxOnGoing=1` | `RX_SINGLE_DECODING`| `RXSINGLE` (`0x86`) | None (Arm bounded demodulation timer) | `EXTENDED_DECODING` |
| `RX_SINGLE_SEARCH` | Host Search Timer Expired | `RxDone=0`, `RxTimeout=0`, `RxOnGoing=0` | `RX_STANDBY` | Force `STANDBY` (`0x81`) | Clear all IRQs (`write 0xFF`) | `HOST_WATCHDOG_EXPIRED` |
| `RX_SINGLE_DECODING`| DIO0 High (`RxDone`) | Full CRC and length validation | `RX_COMPLETED` | Auto `STANDBY` (`0x81`) | Snapshot, copy FIFO, clear `0x70` | `RX_PACKET_DONE` |
| `RX_SINGLE_DECODING`| Extended Timer Expired | Still no `RxDone` / demodulator stalled | `RX_STANDBY` | Force `STANDBY` (`0x81`) | Clear all IRQs (`write 0xFF`), increment recovery metric | `RX_ABORTED_BY_RECOVERY` |
| Any RX State | `CMD_ABORT_SCHEDULE` | TDMA time slot deadline reached | `RX_STANDBY` | Force `STANDBY` (`0x81`) | Clear all IRQs (`write 0xFF`), record MAC slot end | `RX_ABORTED_BY_SCHEDULE` |
| Any RX State | `FATAL_SPI_ERROR` | SPI failure / unresponsive hardware | `RX_RECOVERY` | Hardware Pin Reset (GPIO23) | Re-initialize via Section 10 checklist | `RX_ABORTED_BY_RECOVERY` |

---

### 7.5. RX Continuous Mode Sequence
- Initiate by writing `Mode = 101` in `RegOpMode` (`0x85`).
- The radio never times out autonomously and remains in RX mode across multiple packets.
- On each `RxDone` interrupt:
  1. Radio Owner task reads snapshot (`RegIrqFlags`, `RegHopChannel`, `RegRxNbBytes`).
  2. Executes the strict RX Validation Pipeline.
  3. **Immediate FIFO extraction:** Because the receiver remains in `RXCONT`, incoming RF energy from a subsequent packet will begin writing to the circular FIFO immediately. The host must extract payload bytes before the FIFO pointer wraps around or before the next packet arrives.
  4. **Targeted IRQ Clearing (`snapshot & 0x70`):** The driver clears only the processed flags by executing a targeted write-1-to-clear with `RegIrqFlags = (snapshot & 0x70)` (specifically clearing `RxDone` `[bit 6]`, `PayloadCrcError` `[bit 5]`, and `ValidHeader` `[bit 4]` if asserted for this frame). The radio continues receiving seamlessly.
- **Gateway Half-Duplex Transmission Transition:** When the Gateway needs to transmit (e.g., sending an Event ACK or Maintenance `SYNC_BEACON`), the Radio Owner task must explicitly transition from `RXCONT` to `STDBY`, stage the payload into `RegFifo`, set DIO0 to `TxDone` (`0x40`), and enter `TX`. After `TxDone` asserts (automatically reverting the transceiver to `STDBY`), the task reconfigures DIO0 to `RxDone` (`0x00`) and transitions back to `RXCONT`. The Gateway cannot receive while transmitting its own packets.

> [!WARNING]
> **Prohibition of Solitary `0x40` Clearing in Continuous Mode:**
> Drivers must NOT clear only `0x40` (`RxDone`). If a corrupted frame or valid header asserted `PayloadCrcError` (`0x20`) or `ValidHeader` (`0x10`), writing `0x40` leaves those bits asserted in `RegIrqFlags`. This stale CRC error or header flag contaminates subsequent packet evaluations, causing spurious CRC error rejections on perfectly valid subsequent frames. Handled flags must always be cleared using targeted clearing: `write RegIrqFlags = (snapshot & 0x70)`.

> [!CAUTION]
> **Strict Prohibition of Unconditional `0xFF` Clearing in Continuous Mode:**
> Drivers must NEVER write `0xFF` to `RegIrqFlags` while operating in `RXCONT` mode. Unlike `RxSingle` mode where the radio automatically idles into `STANDBY`, the transceiver in `RXCONT` immediately begins searching for and locking onto subsequent RF signals. By the time the host completes FIFO readout and issues an SPI clear command, the modem may already have detected a preamble or latched a valid header for the next incoming frame. Writing `0xFF` unconditionally clears all active flags, destroying the header/preamble tracking state of the newly arriving frame and causing reception failure or packet loss.

---

## 8. FIFO Memory Management, Host Buffer Capacity, and Ownership


### 8.1. Pre-Copy Validation Checklist

Before a single byte is read from `RegFifo` (`0x00`), the Radio Owner task must execute a mandatory six-step safety check:

```c
// 1. Read packet payload byte length
uint8_t nb_bytes = sx1276_read(REG_RX_NB_BYTES); // Address 0x13

// 2. Reject zero or sub-minimum MAC frames
if (nb_bytes < CONFIG_CUSTOM_MAC_MIN_FRAME_LEN) {
    sx1276_write(REG_IRQ_FLAGS, 0x70); // Clear RxDone, PayloadCrcError, ValidHeader
    return REJECT_INVALID_LENGTH;
}

// 3. Reject frames exceeding transceiver register ceiling
uint8_t max_payload = sx1276_read(REG_MAX_PAYLOAD_LENGTH); // Address 0x23
if (nb_bytes > max_payload) {
    sx1276_write(REG_IRQ_FLAGS, 0x70);
    return REJECT_INVALID_LENGTH;
}

// 4. MANDATORY: Check against actual host RX buffer capacity
if (nb_bytes > CONFIG_SX1276_HOST_RX_BUFFER_SIZE) {
    // CRITICAL: Reject before copying to prevent RAM buffer overflow!
    sx1276_write(REG_IRQ_FLAGS, 0x70);
    driver_stats.rx_host_buffer_overflow_dropped++;
    return REJECT_HOST_BUFFER_OVERFLOW;
}

// 5. Verify FIFO pointer arithmetic and boundary alignment
uint8_t current_addr = sx1276_read(REG_FIFO_RX_CURRENT_ADDR); // Address 0x10
sx1276_write(REG_FIFO_ADDR_PTR, current_addr);                // Set SPI pointer to start of packet

// 6. Burst-read verified payload into preallocated host buffer
sx1276_burst_read(REG_FIFO, host_frame->payload, nb_bytes);
host_frame->length = nb_bytes;
```

---

### 8.2. Buffer Allocation and Ownership Protocol

To guarantee real-time predictability and prevent heap exhaustion:

1. **Zero Dynamic Allocation Rule:**
   - Steady-state driver operation **strictly prohibits `malloc()` and `free()`**.
   - All RX buffers are statically allocated in a preallocated ring or descriptor pool at startup:
     ```c
     #define CONFIG_SX1276_HOST_RX_BUFFER_SIZE 64U // Must accommodate max project MAC PDU
     #define CONFIG_SX1276_RX_BUFFER_POOL_SIZE 4U

     typedef struct {
         uint8_t  payload[CONFIG_SX1276_HOST_RX_BUFFER_SIZE];
         uint8_t  length;
         int8_t   snr_db_quarter; // Signed 2's complement from RegPktSnrValue
         int16_t  rssi_dbm;       // Calculated packet RSSI in dBm
         uint8_t  channel_idx;    // Operating channel (00-10)
         uint32_t timestamp_us;   // ESP32 timer latch at RxDone
     } sx1276_rx_frame_t;
     ```
2. **Ownership Handover Protocol:**
   - **Phase 1 (Driver Exclusive):** While extracting from `RegFifo`, the Radio Owner task has exclusive ownership of the current frame buffer.
   - **Phase 2 (Handover to MAC):** Once payload is completely extracted, tagged with SNR/RSSI/timestamp, and validated, the Radio Owner task transfers ownership to the Custom MAC queue:
     ```c
     BaseType_t status = xQueueSend(xMacRxQueue, &p_frame, 0);
     ```
3. **Queue Full & Buffer Unavailable Policy:**
   - If `xMacRxQueue` is full or no free buffer descriptors remain in the pool:
     - The frame is **immediately dropped**.
     - `driver_stats.rx_queue_overflow_dropped` is incremented.
     - The Radio Owner task **never blocks indefinitely** waiting for the queue to drain.
     - The buffer descriptor is immediately reclaimed for the next reception.
     - **No invalid ownership transfer or memory leak occurs.**
4. **Architectural Differences: RX Single vs. RX Continuous:**
   - **In RX Single:** Upon `RxDone`, the radio automatically reverts to `STANDBY`. The 256-byte dual-port RAM cannot be overwritten by incoming RF signals. The host may read FIFO data at any time before initiating the next RX/TX cycle.
   - **In RX Continuous:** The transceiver remains active in `RXCONT`. The next packet will begin writing to the FIFO immediately. The host driver must complete burst FIFO extraction immediately to prevent FIFO overwrite.

---

---

## 9. Time-on-Air (ToA) Formulation and Static TDMA Guard Times


The total packet transmission duration is:

$$T_{packet} = T_{preamble} + T_{payload}$$

$$T_{preamble} = (N_{preamble} + 4.25) \times \frac{2^{SF}}{BW}$$

$$N_{payload} = 8 + \max\left( \left\lceil \frac{8PL - 4SF + 28 + 16CRC - 20IH}{4(SF - 2DE)} \right\rceil (CR + 4), 0 \right)$$

$$T_{payload} = N_{payload} \times \frac{2^{SF}}{BW}$$

### Approved Active Profile Baseline Calculation & Mathematical Test Vectors
- Profile Parameters: $BW = 125,000\text{ Hz}$, $SF = 7$, $CR = 1$ (4/5), $IH = 0$, $CRC = 1$, $DE = 0$, $N_{preamble} = 8$:
  - $T_s = 2^7 / 125000 = \mathbf{1.024\text{ ms}}$.
  - $T_{preamble} = (8 + 4.25) \times 1.024\text{ ms} = \mathbf{12.544\text{ ms}}$.

- **16-byte Payload (Baseline):**
  - $\text{Numerator} = 8(16) - 4(7) + 28 + 16(1) - 0 = 144$.
  - $\text{Denominator} = 4(7 - 0) = 28$.
  - $\text{Ceil term} = \lceil 144 / 28 \rceil = 6$.
  - $N_{payload} = 8 + 6 \times (1 + 4) = 8 + 30 = \mathbf{38\text{ symbols}}$.
  - $T_{payload} = 38 \times 1.024\text{ ms} = \mathbf{38.912\text{ ms}}$.
  - $T_{packet} = 12.544\text{ ms} + 38.912\text{ ms} = \mathbf{51.456\text{ ms}}$.

- **64-byte Payload:**
  - $\text{Numerator} = 8(64) - 4(7) + 28 + 16(1) - 0 = 528$.
  - $\text{Denominator} = 4(7 - 0) = 28$.
  - $\text{Ceil term} = \lceil 528 / 28 \rceil = 19$.
  - $N_{payload} = 8 + 19 \times (1 + 4) = 8 + 95 = \mathbf{103\text{ symbols}}$.
  - $T_{payload} = 103 \times 1.024\text{ ms} = \mathbf{105.472\text{ ms}}$.
  - $T_{packet} = 12.544\text{ ms} + 105.472\text{ ms} = \mathbf{118.016\text{ ms}}$.

- **255-byte Payload (Transceiver Maximum Capacity):**
  - $\text{Numerator} = 8(255) - 4(7) + 28 + 16(1) - 0 = 2056$.
  - $\text{Denominator} = 4(7 - 0) = 28$.
  - $\text{Ceil term} = \lceil 2056 / 28 \rceil = 74$.
  - $N_{payload} = 8 + 74 \times (1 + 4) = 8 + 370 = \mathbf{378\text{ symbols}}$.
  - $T_{payload} = 378 \times 1.024\text{ ms} = \mathbf{387.072\text{ ms}}$.
  - $T_{packet} = 12.544\text{ ms} + 387.072\text{ ms} = \mathbf{399.616\text{ ms}}$.

> [!CAUTION]
> **TDMA Slot Budgeting Rule:**
> Physical Time-on-Air ($51.456\text{ ms}$) is **strictly RF channel occupancy**.
> A complete TDMA time slot must include:
> 1. Host SPI transfer overhead: Burst write time at SPI clock frequency.
> 2. PLL lock time: $t_{FS} \approx 60\text{ }\mu\text{s}$.
> 3. PA ramp time: $t_{ramp} \approx 40\text{ }\mu\text{s}$.
> 4. Receiver lock time: Minimum 4 preamble symbols.
> 5. Interrupt processing & FreeRTOS task scheduling latency.
> 6. Reference crystal drift margin across operating temperature.

---

## 10. Radio Initialization Sequence after ESP32 Wake-Up

Because ESP32 Deep-sleep may disconnect or reset the SX1276 power domain, firmware must reinitialize the transceiver on every wake cycle using the validated configuration plan derived from `sx1276_phy_config_t`:

1. Configure ESP32 GPIOs: NSS (GPIO18) high, SCK/MOSI low, RESET (GPIO23) floating, DIO0 (GPIO26) input.
2. Assert manual reset: Drive GPIO23 low for $\ge 100\text{ }\mu\text{s}$ (recommended $150\text{ }\mu\text{s}$), release to open-drain, delay $10\text{ ms}$.
3. Read `RegVersion` (`0x42`): Assert error if readback is not `0x12`.
4. Put radio in `SLEEP` (`RegOpMode = 0x00`), then select LoRa (`RegOpMode = 0x80`).
5. Switch to `STDBY` (`RegOpMode = 0x81`).
6. Apply silicon errata fix: Read-modify-write `RegDetectOptimize` (`0x31`): clear bit 7 (`reg & ~0x80`), yielding `0x43` if reset value is `0xC3`. Never hardcode `0x03` as this corrupts reserved bits.
7. Program carrier frequency (`RegFrMsb/Mid/Lsb`) for the Backend-authorized channel (e.g., `0xE61000` for CH00).
8. Program modem parameters derived from typed configuration (`sx1276_register_plan_build`):
   - `RegModemConfig1`: write computed byte (`0x72` for BW125/CR4/5/Explicit).
   - `RegModemConfig2`: set SF7 (`0x70`) and `RxPayloadCrcOn` (`0x04`) while preserving `SymbTimeout[9:8]`.
   - `RegModemConfig3`: set `LowDataRateOptimize = 0` and `AgcAutoOn = 1` (`0x04`).
9. Program preamble length: write configured preamble symbols (`0x0008` for 8-symbol test preset in `RegPreambleMsb/Lsb`).
10. Program PA ramp and OCP: write `0x09` to `RegPaRamp` (40 µs ramp) and `0x2B` to `RegOcp` (100 mA limit).
11. Program LNA: write `0x20` to `RegLna` (HF Boost OFF, default current; gain controlled by AGC).
12. Program sync word: write `0x12` to `RegSyncWord` (`0x39`).
13. Set FIFO base addresses: `RegFifoTxBaseAddr = 0x80`, `RegFifoRxBaseAddr = 0x00`.
14. Route DIO0 to `TxDone` (`0x40`) or `RxDone` (`0x00`) depending on scheduled role.
15. Ready in `STDBY` mode.

*(Note: Register byte values in the checklist illustrate the compiled output for `PHY_PROFILE_MVP_V1` and `SX1276_TEST_PROFILE_V1`. The driver logic uses bitfield encoders and validation rather than fixed magic numbers).*
