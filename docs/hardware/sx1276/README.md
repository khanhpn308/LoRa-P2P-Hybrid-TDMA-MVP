# SX1276 Driver — Agent Reference (MVP V2)

Use this directory to implement the **SX1276 LoRa P2P radio driver** for **ESP32-WROOM-32E, ESP-IDF v6.1, FreeRTOS/C**. The system uses a Custom Binary MAC V2 (**Event-driven CAD + exponential random backoff CSMA/CA** and **Gateway Continuous RX 24/7** per [ADR-0004](../../adr/0004-pure-cad-csma-ca-mac.md), Owner #273), **not** superseded Hybrid TDMA or the LoRaWAN MAC stack.

## Read These Four Files

| File | Agent task |
|---|---|
| [`README.md`](README.md) | Entry point, architectural pipeline, hardware constraints, and role policies |
| [`SX1276_ACTIVE_PROFILE.md`](SX1276_ACTIVE_PROFILE.md) | Approved PHY presets, VN920 channel table, typed-config register mappings, and ToA formula |
| [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md) | SPI/reset, TX/RX/CAD lifecycles, FIFO, DIO0 IRQ, timeout, Radio Owner, recovery, and half-duplex transitions |
| [`SX1276_REGISTER_REFERENCE.md`](SX1276_REGISTER_REFERENCE.md) | Required register addresses, bitfields, reset values, write masks, and consolidated test-profile register semantics |

Read only the files relevant to the implementation task; start from the Active Profile and Operations Guide, then consult the Register Reference for exact SPI/register access. No additional SX1276 reference or audit files are required for the MVP.

## Configurable PHY Architecture & Approved Baseline Presets

Operational radio parameters are **not hardcoded constants** in the driver logic. The implementation follows an owner-approved pipeline separating build-time user choices, typed configuration, and register encoding:

```text
idf.py menuconfig (enumerated valid choices)
       │
       ▼
generated sdkconfig.h
       │
       ▼
typed sx1276_phy_config_t / sx1276_hw_config_t
       │
       ▼
sx1276_config_validate() (silicon + hardware + contract constraints)
       │
       ▼
sx1276_register_plan_build() (derive bitfields, masks, write sequences)
       │
       ▼
Radio Owner SPI Execution & Readback Validation
```

### Invariants vs Configurable Parameters
1. **Configurable via ESP-IDF `menuconfig`:** Discrete SF, BW, CR, preamble length, CRC enable, header mode (explicit/implicit), Sync Word, LDRO (AUTO/manual), test RF channel/frequency, TX PA path, TX target output power, PA ramp time, OCP enable/current limit, LNA gain / HF boost / AGC, RX symbol timeout, and wake/reinitialization options. Both Gateway and Node firmware expose these options with typed bounds.
2. **Silicon & Hardware Invariants (Code-Level Truth):** Register addresses, bitmask layouts, SPI Mode 0 timing constraints, HW-001 pin mapping, DIO0-only physical interrupt routing, `AutomaticIFOn` bit 7 clear (errata fix), `LongRangeMode` writable exclusively in SLEEP mode, and write-1-to-clear IRQ flag semantics are fixed properties of silicon and circuit design. They are never exposed as manual register byte inputs in `menuconfig`.
3. **Approved Baseline Preset (`PHY_PROFILE_MVP_V1`):**
   - Radio: SX1276 LoRa P2P. SF7, BW125 kHz, CR4/5, Explicit Header, Payload CRC ON, Sync Word `0x12`, LDRO OFF; frequency hopping disabled.
   - RF plan: 11 center frequencies CH00–CH10 (920.250–922.750 MHz in 250 kHz steps) per `VN920_V1`.
   - **Channel Authority:** Active operational channel (CH00–CH10, VN920) is assigned by Backend PostgreSQL (#154 / [ADR-0004](../../adr/0004-pure-cad-csma-ca-mac.md)). `menuconfig` supplies only boot/lab-test defaults; lab settings must not silently override production Backend channel configuration.
4. **Approved Test Preset (`SX1276_TEST_PROFILE_V1`):**
   - Preamble: **8 symbols** (selectable test preset default, not a measured production constant).
   - PA Ramp: **40 µs** (`RegPaRamp = 0x09`).
   - OCP: **Enabled, limit 100 mA** (`RegOcp = 0x2B`).
   - AGC: **ON** (`RegModemConfig3.AgcAutoOn = 1`). Manual LNA gain is inapplicable while AGC is active; manual gain is selectable only when AGC is OFF (manual gain level is not yet approved).
   - LNA HF Boost: **OFF** (`RegLna.LnaBoostHf = 00b`, default current).
   - TX Output Power Target: **+2 dBm** default selectable target; candidate alternate **+5 dBm** for subsequent supervised testing only.
   - **PA Path Unknown & TX Fail-Closed:** The installed commercial SX1276 915-MHz module has antenna soldered to `ANT`, but internal RF output topology (`RFO_HF` vs `PA_BOOST`) and 920–923 MHz matching are unverified (`PA_PATH = UNKNOWN / NOT_VERIFIED`). **RF TX is DISABLED by default.** Selecting a target power does not authorize RF transmission. TX must fail closed when PA path is unverified or contradictory.

## Hardware Interface & Radio Owner (HW-001)

- SX1276 / ESP32 HW-001 Pinout: SCK=GPIO5, MISO=GPIO19, MOSI=GPIO27, NSS=GPIO18, RESET=GPIO23, DIO0=GPIO26.
- **DIO1–DIO5 are NOT_CONNECTED.** Signals mapped to DIO1–DIO5 (including `RxTimeout`) cannot generate hardware interrupts. Detect `RxTimeout` through bounded Radio Owner task IRQ polling + host supervision timer, never an imagined DIO1 interrupt.
- SPI Mode 0; max clock 10 MHz. GPIO5 is an ESP32 strapping pin; ensure SCK idles low and does not pull up invalid bootstrap states during reset.
- A single FreeRTOS **Radio Owner task** serializes all SPI access. The DIO0 ISR issues task notifications only: **no SPI or blocking calls in ISR context**.
- For ESP32 wake-up from Deep-sleep, perform a full hardware reset (GPIO23 low $\ge 100\text{ }\mu\text{s}$) and complete register reconfiguration.

## Radio RX-Mode Policy & MAC V2 Roles (ADR-0004)

1. **Node Normal Event Flow:**
   - Baseline is ESP32 Deep-sleep / radio low-power per #149/#353.
   - Local physical button press (GPIO/EXT0, #149/#230) writes a durable pending `UP_EVENT` (`0x41`); local hardware alarms are abolished (#230).
   - Node executes SX1276 **CAD** (`RegOpMode = LORA_MODE_CAD`) and exponential random backoff (CSMA/CA) before transmitting `UP_EVENT`, then enters **`RxSingle` only during a bounded ACK receive window** (`DOWN_EVENT_ACK`, `0x42`).
   - Upon validating authenticated ACK, Node returns to sleep. If ACK is missing or invalid, preserve the pending Event in NVS/RTC FIFO and retry via bounded CAD/ARQ policy; do not switch to unrestricted continuous listening on battery Nodes.
2. **Gateway Baseline:**
   - Gateway operates in **`RxContinuous` 24/7** on its exclusive VN920 channel to receive Node packets.
   - Single half-duplex radio: Gateway Radio Owner explicitly executes state transitions: `RxContinuous → Standby → TX (ACK / Join response) → RxContinuous`. The Gateway cannot listen while transmitting. Gateway uses no LoRaWAN stack.
   - *(Historical provenance: Static DATA slots, `SYNC_BEACON`, and TDMA Maintenance Superframes from ADR-0001/#125 were superseded by ADR-0004 / Owner #273.)*

## Runtime Parameters Not Yet Frozen (TBD)

- **TBD:** Actual module PA path; RF output matching at 920–923 MHz; conducted/radiated power measurements; production TX power; RX Symbol Timeout; Host RX Timeout; ACK/Join receive windows; hardware mode turnaround and airtime budgets.
- Do not hardcode a TBD as an immutable project constant. Use explicit validation, fail-safe defaults, and report unresolved blockers.
- Only the BW125 MVP configuration is in scope. Do not apply BW500 or non-MVP errata workarounds. Preserve the mandatory `RegDetectOptimize` bit 7 read-modify-write rule.

## Scope Boundary

These files describe radio hardware control and driver register architecture, **not** a complete MAC wire contract. Follow versioned `contracts/radio-mac/` and approved architecture documents ([ADR-0004](../../adr/0004-pure-cad-csma-ca-mac.md)) for application integration. Documented calculations and test presets do not constitute measured RF, HIL, timing, or regulatory compliance results.
