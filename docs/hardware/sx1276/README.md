# SX1276 Driver — Agent Reference (MVP V1)

Use this directory to implement the **SX1276 LoRa P2P radio driver** for **ESP32-WROOM-32E, ESP-IDF v6.1, FreeRTOS/C**. The system uses a Custom Binary MAC and Event-only Static TDMA, **not** the LoRaWAN MAC stack.

## Read These Four Files

| File | Agent task |
|---|---|
| [`README.md`](README.md) | Entry point, scope and hardware constraints |
| [`SX1276_ACTIVE_PROFILE.md`](SX1276_ACTIVE_PROFILE.md) | Approved PHY settings, VN920 channel table and register values |
| [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md) | SPI/reset, TX/RX, FIFO, DIO0 IRQ, timeout, Radio Owner, recovery and ToA |
| [`SX1276_REGISTER_REFERENCE.md`](SX1276_REGISTER_REFERENCE.md) | Required register addresses, bitfields, reset values, write masks and operational constraints |

Read only the files relevant to the implementation task; start from the Active Profile and Operations Guide, then consult the Register Reference for exact SPI/register access. No additional SX1276 reference or audit files are required for the MVP.

## Fixed MVP Configuration

- Radio: SX1276 LoRa P2P. SF7, BW125 kHz, CR4/5, Explicit Header, Payload CRC ON, Sync Word `0x12`, LDRO OFF; frequency hopping disabled.
- RF plan: 11 center frequencies CH00–CH10 (920.250–922.750 MHz in 250 kHz steps). Select the authorized channel at runtime; **do not default to CH05**.
- SX1276 / ESP32 HW-001: SCK=GPIO5, MISO=GPIO19, MOSI=GPIO27, NSS=GPIO18, RESET=GPIO23, DIO0=GPIO26. **DIO1–DIO5 are NOT_CONNECTED**.
- SPI Mode 0; do not exceed SX1276 SPI timing limits. GPIO5 is an ESP32 boot-strapping pin; avoid unsafe SCK states during reset.
- One Radio Owner task owns SPI/radio state. DIO0 ISR sends notification only: **no SPI or blocking work in ISR**. Detect RxTimeout through task-level IRQ polling/host supervision, not a nonexistent DIO1 interrupt.
- For ESP32 wake-up, perform a full radio reset and register reconfiguration until the SX1276 power rail behavior is verified.
- Do not send Node packets outside the Gateway-authorized TDMA schedule. PHY CRC detects corruption; it does **not** authenticate MAC messages.

## Runtime Parameters Not Yet Frozen

- **TBD**: preamble length; TX output power; physical PA path (`RFO` versus `PA_BOOST`); LNA/HF boost and AGC policy; RX search/demod host guards; final TDMA slot/guard timing.
- The 8-symbol preamble used in theoretical ToA examples is **not** an approved production value.
- Do not silently hardcode a TBD as a project decision. Use explicit configuration/validation and report unresolved blockers at the point the feature needs them.
- Only the BW125 MVP configuration is in scope. Do not apply BW500 or other non-MVP silicon workarounds. Preserve the mandatory `RegDetectOptimize` bit-7 read-modify-write rule documented in the register/operations files.

## Scope Boundary

These files describe radio hardware control, **not** a complete MAC or TDMA wire contract. Follow the versioned `contracts/radio-mac/` and approved architecture documents for application integration. Do not treat documentary examples as proven RF, HIL, timing or legal-compliance results.
