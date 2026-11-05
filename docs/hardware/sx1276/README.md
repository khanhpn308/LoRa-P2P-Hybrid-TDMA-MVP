# SX1276 Agent Reference

## 1. Overview and Engineering Scope

This project reference provides a streamlined, context-optimized technical guide for developing the **SX1276 LoRa transceiver driver** on an **ESP32-WROOM-32E** microcontroller using **ESP-IDF v6.1** and **FreeRTOS / C**.

It is tailored for AI coding assistants (Gemini / Codex) and embedded software engineers implementing **Issue #10 (SX1276 Driver Foundation)** within a **Custom LoRa P2P, Event-Only Static TDMA MAC** architecture.

> [!IMPORTANT]
> **Context-Optimization Rule for AI Agents:**
> To conserve prompt context and prevent hallucination from unused silicon features, **AI Agents must by default read ONLY the 4 Hot Context files** in the root directory.
> Secondary modes, errata workarounds, and traceability matrices are segregated into the `reference/` and `verification/` subdirectories and should only be consulted on demand.

---

## 2. Document Navigation and Context Hierarchy

```text
docs/hardware/sx1276/
├── README.md                      <-- [HOT 1] Master index, context rules, hardware and configuration boundaries
├── SX1276_ACTIVE_PROFILE.md       <-- [HOT 2] Approved PHY profile (SF7/BW125k), 11-channel plan, MVP registers
├── SX1276_DRIVER_OPERATIONS.md    <-- [HOT 3] SPI, reset, TX/RX sequences, FIFO, IRQ/DIO0, ToA, recovery
├── SX1276_REGISTER_REFERENCE.md   <-- [HOT 4] Lean register reference strictly for MVP firmware
│
├── reference/                     <-- [COLD] Consulted only when handling non-MVP modes or deep audits
│   ├── SX1276_OTHER_MODES.md      <-- Non-MVP SF/BW/CR, FSK/OOK, FHSS, sequencers, non-MVP registers
│   ├── SX1276_ERRATA.md           <-- Silicon errata analysis (AutomaticIFOn, 500k opt, IF shifts)
│   └── SX1276_SOURCE_TRACEABILITY.md <-- Source section/page citations for all technical assertions
│
└── verification/                  <-- [AUDIT] Verification reports and automated validation
    ├── SX1276_AUDIT_REPORT.md     <-- Corrective audit v2 report, Quality Gates G1-G6 evaluation
    └── tests/                     <-- Automated test suite (Python unittest)
        └── test_candidate_reference.py
```

### Context Selection Rules for Agents

| Task Description | Minimum Required Files |
|---|---|
| **Implementing SX1276 Driver Initialization & Reset** | [`README.md`](README.md), [`SX1276_ACTIVE_PROFILE.md`](SX1276_ACTIVE_PROFILE.md), [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md), [`SX1276_REGISTER_REFERENCE.md`](SX1276_REGISTER_REFERENCE.md) |
| **Implementing Radio TX / RX / IRQ State Machine** | [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md), [`SX1276_REGISTER_REFERENCE.md`](SX1276_REGISTER_REFERENCE.md) |
| **Channel Tuning and Frequency Configuration** | [`SX1276_ACTIVE_PROFILE.md`](SX1276_ACTIVE_PROFILE.md), [`SX1276_REGISTER_REFERENCE.md`](SX1276_REGISTER_REFERENCE.md) |
| **Calculating Packet Time-on-Air (ToA)** | [`SX1276_ACTIVE_PROFILE.md`](SX1276_ACTIVE_PROFILE.md), [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md) |
| **Auditing Silicon Errata & Workarounds** | [`reference/SX1276_ERRATA.md`](reference/SX1276_ERRATA.md) |
| **Adding Future Non-MVP Modes (SF8–SF12, FSK)** | [`reference/SX1276_OTHER_MODES.md`](reference/SX1276_OTHER_MODES.md) |
| **Auditing Verification & Citations** | [`reference/SX1276_SOURCE_TRACEABILITY.md`](reference/SX1276_SOURCE_TRACEABILITY.md), [`verification/SX1276_AUDIT_REPORT.md`](verification/SX1276_AUDIT_REPORT.md) |

---

## 3. Project Hardware Context (HW-001)

The approved hardware design connects the SX1276 transceiver to the ESP32-WROOM-32E host as follows:

| SX1276 Signal | ESP32 GPIO | Direction | Bus / Role |
|---|---|---|---|
| `SCK` | **GPIO5** | ESP32 $\to$ SX1276 | SPI Clock ($F_{SCK} \le 10\text{ MHz}$, SPI Mode 0) |
| `MISO` | **GPIO19** | SX1276 $\to$ ESP32 | SPI Master-In Slave-Out |
| `MOSI` | **GPIO27** | ESP32 $\to$ SX1276 | SPI Master-Out Slave-In |
| `NSS` (`CS`) | **GPIO18** | ESP32 $\to$ SX1276 | Active-Low SPI Chip Select |
| `RESET` (`NRESET`)| **GPIO23** | ESP32 $\to$ SX1276 | Active-Low Reset (Open-Drain, $\ge 100\text{ }\mu\text{s}$ low pulse) |
| `DIO0` | **GPIO26** | SX1276 $\to$ ESP32 | Multi-purpose interrupt (`TxDone`, `RxDone`, `CadDone`) |
| `DIO1`–`DIO5` | **NOT_CONNECTED**| — | Unrouted on PCB HW-001 |

### Hardware Boundary Warnings
1. **DIO1 is NOT connected:** `RxTimeout` cannot generate a physical hardware interrupt on the ESP32. Receiver timeout must be detected by polling `RegIrqFlags` (`0x12`, bit 7) or by arming a host FreeRTOS software timer.
2. **GPIO5 Strapping Pin Caution:** GPIO5 is an ESP32 strapping pin sampled during reset (SDIO slave timing). The driver and board circuitry must ensure that SCK idles LOW and does not force an invalid strapping state during chip reset.
3. **Button Wake-Up GPIO:** The external wake-up button is handled entirely by the ESP32 RTC controller and is **not connected to the SX1276**.
4. **Deep-Sleep Power Domain:** It is unverified whether the SX1276 $V_{DD}$ rail remains powered during ESP32 Deep-sleep. Therefore, the driver must perform a complete hardware reset and register reconfiguration upon every ESP32 wake-up.
5. **No Autonomous Button Transmissions:** Under the project's Static TDMA architecture, nodes never transmit spontaneously upon wake-up; transmissions occur strictly within gateway-assigned TDMA slots.

---

## 4. Summary of Approved PHY & Channel Design (VN920 V1)

- **RF Band:** 920.0–923.0 MHz.
- **Channel Plan:** 11 discrete channels (`CH00` to `CH10`), spaced at **250 kHz intervals** from 920.250 MHz to 922.750 MHz.
- **Synthesizer Step:** With $F_{XOSC} = 32.0\text{ MHz}$, $F_{step} = 61.03515625\text{ Hz}$. A 250 kHz hop equals exactly $4096$ (`0x1000`) steps, resulting in **0.00 Hz quantization error**.
- **Modulation Settings:** $SF=7$, $BW=125,000\text{ Hz}$, $CR=4/5$ ($CR=1$), Payload CRC = `ON`, Header = `Explicit`, Sync Word = `0x12`, LowDataRateOptimize = `OFF` ($T_s = 1.024\text{ ms} \le 16\text{ ms}$).
- **Single Active Channel:** A Gateway registers and operates on strictly one channel at a time via PostgreSQL Backend authorization (Issue #154). The SX1276 is half-duplex and cannot monitor multiple channels concurrently.
- **`CH05` is NOT a default channel:** Active channel is authorized at runtime by the backend.

---

## 5. Explicit List of Pending / Unresolved Parameters (TBD)

The following parameters are intentionally marked **`TBD`** and must not be fabricated by AI coding agents:
1. **Preamble Length (`TBD`):** Standard default is 8 symbols for calculation, but official project preamble length is pending system timing freeze.
2. **TX Output Power (`TBD`):** Nominal dBm setting is subject to link budget and battery life targets.
3. **PA Path (`TBD`):** Selection between `RFO` (up to +14 dBm) and `PA_BOOST` (up to +20 dBm) depends on PCB RF matching and regulatory limits.
4. **Active Channel (`TBD`):** Runtime channel is dynamically assigned by the Gateway / Backend controller.
5. **RegLna Gain & HF Boost (`TBD` / `PROPOSED`):** Reset default is `0x20`. Setting `0x23` (HF Boost on, +150% LNA current) is proposed for link budget optimization but unfrozen pending RF bench validation, and overridden if `RegModemConfig3.AgcAutoOn = 1`.
6. **Host RX Timeout Guard Margins (`TBD`):** $T_{guard\_search}$ and $T_{guard\_demod}$ (`CONFIG_SX1276_RX_SEARCH_GUARD_MS`, `CONFIG_SX1276_RX_DEMOD_GUARD_MS`) are uncalibrated host software margins; no fixed arithmetic constant is assumed as a production default.

---

## 6. Technical Sources and Boundaries

- Manufacturer register and radio behavior: Semtech SX1276/77/78/79 Datasheet Rev. 7 (May 2020); see [`reference/SX1276_SOURCE_TRACEABILITY.md`](reference/SX1276_SOURCE_TRACEABILITY.md) for section/page references.
- Implement the active settings and operations in the Hot files. Consult `reference/` only for a specific non-MVP mode or erratum. Do not apply BW500 workarounds to the active BW125 profile.
- Do not substitute example values for `TBD` fields. An approved reference is not proof of PCB behavior, RF emissions compliance, or measured TDMA timing.
