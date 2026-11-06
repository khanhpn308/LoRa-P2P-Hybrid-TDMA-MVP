# ESP32-WROOM-32E + SX1276 TDMA HIL Bench Setup and Measurement Procedure (LAB-SCOPE V2)

## Document Metadata
- **Document Status:** `DRAFT_BENCH_PROCEDURE / LAB_SCOPE_V2 / PENDING_REVIEW`
- **Source Issue:** [Issue #169 (LAB-SCOPE V2)](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/169)
- **Baseline Authority:** Merged PR #202 (Commit `5ce67822e82edc6582879081ea0bd6ea79104b68`)
- **Dependencies:** [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10), [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11), [#19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19), [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127), [#130](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/130), [#131](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/131), [#150](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/150), [#201](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/201), [#204](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/204)
- **Target Hardware:** ESP32-WROOM-32E + Semtech SX1276 on PCB HW-001 ([pcb-hw001-pinmap.md](pcb-hw001-pinmap.md))
- **Gate Classification:** Gate G1 (RF / Hardware), Gate G3 (Embedded Bring-up) — *LAB-Scope Verification only*

---

## 1. Executive Summary & LAB-SCOPE V2 Mandate

Under **LAB-SCOPE V2** (Project Owner directive 2026-11-06), Issue #169 is rescoped to focus on **pragmatic small-lab multi-node TDMA functional HIL testing and calculated timing verification**.

### 1.1 Equipment Scope Rescoping
- **No Specialized RF Equipment Required for LAB Closure:**
  The acquisition or deployment of a Spectrum Analyzer, RF Power Meter, high-bandwidth RF Oscilloscope, VNA, or Temperature Chamber is **EXPLICITLY NOT REQUIRED** to complete the LAB acceptance criteria of Issue #169.
- **Specialized Equipment Status:**
  Any measurement requiring high-end RF instruments (radiated power, absolute frequency calibration, occupied bandwidth mask, harmonic emission, VSWR, and temperature chamber drift) is formally classified as **`DEFERRED / OUT_OF_SCOPE_FOR_LAB / NOT_VERIFIED`**.
- **Core Objective:**
  Demonstrate, using the actual hardware available in the lab, that the Gateway enforces schedule profiles and Sensor Nodes adhere to assigned TDMA slots without mutual transmission overlap in the DATA phase, and characterize observable software/digital latencies and synchronization holdover behavior.

---

## 2. Lab Hardware Bill of Materials & Equipment Constraints

Conforming to the equipment declared by the Project Owner:

| Equipment | Specification / State | Practical Lab Usage & Constraints |
|---|---|---|
| **Multiple PCB HW-001 Boards** | ESP32-WROOM-32E + SX1276 (mười mấy board) | Multi-node scaling: 1 Gateway + 1/4/9/10–15 Nodes. (Full 15 Nodes + 1 GW requires **16 functional boards**). |
| **USB Logic Analyzer** | 24 MHz / 8-Channel (Cypress FX2 compatible) | Digital signals only: SPI NSS envelope, DIO0 edge, GPIO debug strobes, task jitter. **Does NOT measure RF waveform, power, or spectrum.** |
| **Digital Multimeter** | HABOTEST HT118E | DC rail voltage verification ($3.30\text{ V}$), continuity, static DC current. **Cannot measure microsecond RF current transients.** |
| **DC Bench Power Supply** | Nutatra 1505TD | Regulated DC power. **Safety rule: Supply via board regulator input; NEVER connect unregulated 5V/15V directly to 3V3 rail!** |
| **Host Workstation** | PC Windows / ESP-IDF v6.1, Python, USB-UART | Firmware build/flashing, monitor, continuous JSONL UART stream capture, statistical analysis. |
| **Specialized RF Instruments** | Spectrum Analyzer, RF Meter, VNA, Temp Chamber | **NOT AVAILABLE / DEFERRED**. Unmeasured RF parameters remain `NOT_VERIFIED`. |

### 2.1 24 MHz Logic Analyzer Capabilities and Sampling Limits
- **Sampling Limit:** 24 MS/s nominal.
- **Nyquist-Shannon Constraint:** To reliably reconstruct digital clock transitions, sampling rate should be $4\times$ to $5\times$ the signal frequency. A 24 MS/s analyzer **CANNOT reliably decode a 10 MHz or 8 MHz SPI clock** (only 2.4 to 3 samples per clock cycle, leading to pulse jitter and decoding artifacts).
- **Measurement Strategy:**
  1. **Protocol / Register Debugging:** When SPI transaction byte decoding is required, temporarily configure SPI clock to $\le 4\text{ MHz}$ (e.g., 2 MHz or 4 MHz). The timing report MUST explicitly label these results as a reduced-clock debug profile.
  2. **Production 10 MHz SPI Envelope:** In standard 10 MHz operation, use the logic analyzer to sample **slower macro signals**: `NSS` chip select envelope (tens of $\mu$s), `DIO0` interrupt edge, and GPIO debug strobes.
  3. Under no circumstances should the Logic Analyzer be treated as a direct RF measurement tool.

---

## 3. PCB HW-001 Signal Map & Strapping Pin Rules

Conforming strictly to [pcb-hw001-pinmap.md](pcb-hw001-pinmap.md):

| SX1276 Net | ESP32 GPIO | Firmware Symbol | Direction | Electrical / Functional Constraints | Lab Attachment |
|---|---:|---|---|---|---|
| `LoRa_SCK` | **GPIO5** | `BOARD_LORA_SCK` | ESP32 $\rightarrow$ SX1276 | SPI Clock (Max 10 MHz). **Caution: Strapping Pin (SDIO Slave timing).** See §3.1. | Logic Ch 1 (Optional debug $\le 4\text{ MHz}$) |
| `LoRa_MISO` | **GPIO19** | `BOARD_LORA_MISO` | SX1276 $\rightarrow$ ESP32 | SPI MISO. High-impedance when NSS is HIGH. | Logic Ch 4 |
| `LoRa_MOSI` | **GPIO27** | `BOARD_LORA_MOSI` | ESP32 $\rightarrow$ SX1276 | SPI MOSI. Shifts data on SCK edge. | Logic Ch 3 |
| `LoRa_CS` | **GPIO18** | `BOARD_LORA_CS` | ESP32 $\rightarrow$ SX1276 | Active-low SPI NSS. Measures transaction envelope. | Logic Ch 2 |
| `LoRa_RST` | **GPIO23** | `BOARD_LORA_RST` | ESP32 $\rightarrow$ SX1276 | Active-low Reset pulse ($\ge 100\ \mu\text{s}$, hold $\ge 10\text{ ms}$). | Logic Ch 5 |
| `LoRa_DIO0` | **GPIO26** | `BOARD_LORA_DIO0` | SX1276 $\rightarrow$ ESP32 | Hardware IRQ: `TxDone`, `RxDone`, or `CadDone`. | Logic Ch 0 (Primary Trigger) |
| `DEBUG_MARKER_1` | **GPIO4** | N/A | ESP32 $\rightarrow$ Test | Software state toggle (dispatch start, ISR exit, durable commit). | Logic Ch 6 |
| `DEBUG_MARKER_2` | **GPIO16** | N/A | ESP32 $\rightarrow$ Test | Multi-node slot synchronization strobe / task wake marker. | Logic Ch 7 |

### 3.1 Strapping Pin Disambiguation (GPIO5 vs MTDI)
> [!IMPORTANT]
> **Correction of Legacy Documentation Error:**
> - `GPIO5` is an ESP32 strapping pin that sets the **SDIO slave timing** bit at chip reset. It is **NOT** `MTDI`. (MTDI is `GPIO12`, which sets the `VDD_SDIO` flash voltage).
> - Strapping pin states are sampled by the ESP32 hardware bootloader on the **rising edge of `CHIP_PU`** during power-on reset, long before FreeRTOS or the SPI master driver initializes.
> - SPI Mode 0 ($CPOL=0, CPHA=0$) defines that `SCK` idles LOW **only when the SPI master peripheral is actively controlling the bus**. Do NOT conflate SPI Mode 0 bus idling with a hardware boot strapping requirement.
> - Bench test fixtures and logic analyzer probe leads attached to `GPIO5` must have high input impedance and must not clamp or pull `GPIO5` to an invalid level during chip reset.

### 3.2 Unrouted DIO1–DIO5 Pins
- Pins `DIO1`, `DIO2`, `DIO3`, `DIO4`, and `DIO5` are **NOT routed** on PCB HW-001 (`GPIO_NUM_NC`).
- `DIO1` (`RxTimeout`) is unrouted: firmware MUST rely on software host FreeRTOS timers for receive timeout supervision.
- No test probes should be attached to floating or unrouted transceiver pads.

---

## 4. Evidence Classification Taxonomy

In compliance with project data integrity policies, all logged timing and test data must use the following mutually exclusive categories:

1. **`CALCULATED_TOA`:** Pure mathematical Time-on-Air derived from Semtech SX1276 Rev. 7 §4.1.1.7 equations via `tests/hil/rf_timing/toa/sx1276_toa.py`.
2. **`SOFTWARE_TIMESTAMP`:** Microsecond timestamp latched via `esp_timer_get_time()` on a single ESP32 microcontroller.
3. **`HARDWARE_DIGITAL_CAPTURE`:** Digital transition timestamps latched via the 24 MHz USB Logic Analyzer (e.g. `DIO0` rising edge, `NSS` chip select pulse, debug GPIO toggles).
4. **`ASSUMED_BOUND`:** Conservative engineering bounds for parameters not directly measured by lab instruments (e.g. assumed $\pm 20\text{ PPM}$ crystal scenario when installed crystal BOM is uncharacterized; assumed $20\text{ ms}$ turnaround bound; assumed $15\text{ ms}$ flash commit bound).
5. **`HOST_SYNTHETIC`:** Deterministic synthetic fixtures generated for offline unit testing and host parser validation.
6. **`RF_MEASURED`:** Calibrated external RF on-air waveform or power measurement. *(Currently classified as `NOT_VERIFIED` in this lab setup).*
7. **`NOT_VERIFIED`:** Any parameter requiring instruments absent from the lab (e.g. conducted RF power, harmonic emissions, occupied bandwidth mask, VSWR, thermal drift).

---

## 5. Gateway Durable Acceptance Semantics (ESP32 Reality vs Backend Architecture)

> [!IMPORTANT]
> **Durable Acceptance Disambiguation & Storage Tier Separation:**
> 1. **Volatile FreeRTOS Queue Serialization:** In-memory queueing (`xQueueSend`) between FreeRTOS tasks executes in RAM with minimal latency ($\le 100\ \mu\text{s}$). However, it is **strictly volatile** and provides zero durability across unexpected power loss or reset. FreeRTOS queue serialization **MUST NOT** be equated with durable acceptance.
> 2. **ESP32 Non-Volatile Flash Persistence (NVS / Raw Flash):** Non-volatile flash writes on ESP32 persist events across power cycles, but introduce wear-leveling overhead and erase/write tail latencies (typically $5\text{–}30\text{ ms}$). This mechanism is **NOT implemented** in current ESP32 Gateway firmware (`firmware/gateway_master/main/main.c`).
> 3. **Host / Linux Gateway Engine SQLite WAL:** Embedded SQLite in WAL mode on a Linux host engine or PostgreSQL on Backend Go Monolith can achieve durable commits with fsync/WAL checkpoints. However, SQLite does NOT run directly on the bare-metal ESP32 microcontroller.
> 4. **Contract vs Implementation Conflict (`CONTRACT_IMPLEMENTATION_CONFLICT / NOT_VERIFIED`):**
>    - `contracts/radio-mac/specification.md` line 20 and `DEC-127-05` require the Gateway to durably commit incoming `UP_EVENT` payloads before emitting `DOWN_EVENT_ACK` (0x42) over RF to ensure 0% data loss.
>    - Because current Gateway firmware is a scaffold with neither SQLite nor NVS persistence implemented before ACK, durable acceptance latency $\tau_{\text{accept}}$ cannot be assumed as $15\text{ms}$ or $35\text{ms}$ PASS.
>    - This architectural discrepancy is formally classified as **`CONTRACT_IMPLEMENTATION_CONFLICT / NOT_VERIFIED`** and handed off to downstream Issues #127 (Contract SLA / Slot Budget clarification) and #131 (Gateway firmware durable storage implementation). PR #207 does not alter the Radio MAC contract or invent an unverified storage architecture.

---

## 6. Ten-Step Transition Plan: From Mock to Multi-Node Real HIL

```text
 ┌────────────────────────────────────────────────────────────────────────┐
 │                   REAL HIL BRING-UP & EXECUTION PHASES                 │
 └────────────────────────────────────────────────────────────────────────┘

  [Phase 1: Hardware Preflight]
    Step 1: Visual & Power Inspection (HT118E, Nutatra 1505TD @ 3.3V)
    Step 2: SPI & RegVersion (0x12) Verification
    Step 3: Real Radio Driver Adapter Integration (#10 API)
    Step 4: RX Buffer Blocker Resolution (CONFIG_SX1276_HOST_RX_BUFFER_SIZE >= 128U)
    Step 5: PA Path Identification & Safety Gate (PA_PATH=UNKNOWN => TX=OFF)

  [Phase 2: Network Scaling & TDMA Scenarios]
    Step 6: Scenario 1 — 1 Gateway + 1 Node Point-to-Point Baseline
    Step 7: Scenario 2 — 1 Gateway + 4 Nodes Small Network Verification
    Step 8: Scenario 3 — 1 Gateway + 9 Nodes Medium Network Verification
    Step 9: Scenario 4 — 1 Gateway + 10-15 Nodes Full Network (when 16 boards available)

  [Phase 3: Edge Cases & Recovery]
    Step 10: Edge Cases — Simultaneous Alerts, Missed Beacons, Holdover, Reboot Recovery
```

### Step 1: Visual & Power Inspection per Board
1. Inspect PCB silkscreen for `HW-001`. Check solder joints on ESP32 module, SX1276, and 32 MHz crystal.
2. Measure $V_{\text{DD}}$ at SX1276 supply pins using the HABOTEST HT118E: verify $3.30\text{ V} \pm 0.05\text{ V}$.
3. Verify that `GPIO5` is not pulled to an invalid state by external fixture wiring during power-on reset.

### Step 2: SPI & RegVersion (0x12) Check
1. Connect ESP32 to PC via USB-UART.
2. Flash SPI test utility. Read register `0x42` (`RegVersion`).
3. Assert that `RegVersion == 0x12`. If readback is `0x00` or `0xFF`, check SPI bus wiring (SCK, MOSI, MISO, CS) and reset line (`GPIO23`).

### Step 3: Real Radio Driver Integration
1. Switch `tests/hil/rf_timing/firmware/common/radio_adapter_mock.c` from mock mode to calling real SX1276 driver APIs from Issue #10 (`sx1276_init`, `sx1276_tx`, `sx1276_start_rx_single`, `sx1276_read_frame`).
2. Log git commit SHA, build configuration, and board serial ID.

### Step 4: RX Buffer Blocker Resolution
1. Confirm that `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` is increased to $\ge 128\text{U}$ in firmware build configuration (see Blocker details in [rf-hil-timing-verification-report.md](rf-hil-timing-verification-report.md)).
2. Verify that 80-byte `DOWN_SYNC_BEACON` can be buffered without triggering `SX1276_RX_STATUS_REJECT_BUFFER_OVERFLOW`.

### Step 5: PA Path Identification & RF Safety Gate
1. **PA Trace Verification:** Inspect RF circuit traces from SX1276 silicon pads to determine whether `PA_BOOST` (Pin 27) or `RFO_HF` (Pin 28) is routed on PCB HW-001. If the PA routing is unverified, `rf_tx_enabled` must remain `false` (fail-closed).
2. **Matched Load / Attenuator Requirement:** A properly matched antenna or calibrated 50 $\Omega$ SMA RF dummy load / inline attenuator must be securely attached to the RF port before any transmission. Never key or enable the transmitter into an open or unterminated connector.
3. **Explicit Power and Channel Authorization:** Operating channel frequency (e.g. VN920 regulatory plan), transmit power level, and legal/regulatory compliance must be explicitly reviewed and authorized in writing by the Project Owner / RF Specialist.
4. **No Defaulted Values:** The bench procedure must **NOT** assume or default to $+2\text{ dBm}$ or 921.4 MHz (or any specific power/channel) as pre-approved for LAB execution. Transmit power and frequency parameters must be injected only from an authorized test configuration after written sign-off.

### Step 6: Scenario 1 — 1 Gateway + 1 Node Point-to-Point
1. Gateway broadcasts Beacon in Slot 0.
2. Node synchronizes, verifies Beacon Ed25519 signature / counter, and schedules `UP_EVENT` (26B) in Slot 1.
3. Gateway receives `UP_EVENT` and replies with slotted `DOWN_EVENT_ACK` (19B).
4. Capture `DIO0` rising edges on Logic Analyzer (Channels 0 and 4). Verify non-overlapping slot execution.

### Step 7: Scenario 2 — 1 Gateway + 4 Nodes
1. Configure 4 Nodes with slot indices 1, 2, 3, and 4.
2. Gateway transmits Beacon, then listens across 4 consecutive DATA slots.
3. Measure packet delivery ratio (PDR), roundtrip ACK latency, and assert zero observed slot overlap.

### Step 8: Scenario 3 — 1 Gateway + 9 Nodes
1. Scale network to 9 Nodes across 9 static DATA slots.
2. Monitor cumulative clock drift across 10s superframe cycles.
3. Verify that trailing guard bands prevent slot boundary collisions between adjacent nodes.

### Step 9: Scenario 4 — 1 Gateway + 10–15 Nodes (when 16 boards available)
1. Subject to physical board availability (requires 16 functional boards for 1 GW + 15 Nodes).
2. Measure total active superframe time against 10s nominal period and verify node airtime compliance ($\le 1.0\%$ duty cycle).

### Step 10: Edge Cases & Recovery Protocols
1. **Simultaneous Alert Events:** Trigger simultaneous alert inputs on multiple nodes; verify that each node transmits only within its assigned static slot without channel contention.
2. **Beacon Loss & Clock Holdover:** Inhibit Gateway Beacon transmission for 1, 2, and 3 cycles; verify that nodes maintain holdover timing for $N_{\text{MISSED}} \in \{1, 2\}$, and lock RF transmission fail-closed when $N_{\text{MISSED}} \ge 3$.
3. **Power Reset / Reboot Recovery:** Reset node mid-cycle; verify it waits for the next valid Beacon before attempting transmission.

---

## 7. Review and Approval Sign-Off (Human Engineers)

| Role | Name | Organization | Signature / Disposition | Date |
|---|---|---|---|---|
| **Hardware / RF Engineer** | TBD | Hardware Team | `PENDING_LAB_EXECUTION` | — |
| **Embedded Firmware Engineer** | TBD | Firmware Team | `PENDING_LAB_EXECUTION` | — |
| **System / Protocol Architect** | TBD | Architecture Team | `PENDING_LAB_EXECUTION` | — |
| **Project Owner** | TBD | Owner | `AUTHORIZATION_PENDING` | — |
