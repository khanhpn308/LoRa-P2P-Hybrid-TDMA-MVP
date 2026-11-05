# SX1276 Active PHY Profile — PHY_PROFILE_MVP_V1

Source: Project Owner Approved PHY Specification & Semtech SX1276 Datasheet Rev. 7 (May 2020), Sections 3.3.3, 4.1.1, 4.4; Printed pp. 26–31, 36, 82, 108–115 / PDF pp. 27–32, 37, 83, 109–116.

## 1. Approved PHY Parameters Summary

This document specifies the authoritative physical layer configuration for the **MVP V1 Custom LoRa P2P** network. Every field marked `PROJECT_APPROVED` represents an engineering baseline approved by the Project Owner.

| Parameter | Approved Value | Silicon Mapping / Setting | Verification Status |
|---|---|---|---|
| **Transceiver** | Semtech SX1276 | LoRa Mode (`LongRangeMode = 1` in `RegOpMode`) | PDF_VERIFIED |
| **Network Architecture** | Custom LoRa P2P | Event-only Static TDMA (Gateway-controlled) | PROJECT_APPROVED |
| **PHY Profile Name** | `PHY_PROFILE_MVP_V1` | Firmware profile identifier | PROJECT_APPROVED |
| **RF Operating Band** | 920.0–923.0 MHz | High-Frequency (HF) port ($> 525\text{ MHz}$) | PROJECT_APPROVED |
| **Channel Plan** | VN920 V1 (11 channels) | Spacing: 250 kHz (920.250–922.750 MHz) | PROJECT_APPROVED |
| **Active Channel** | **TBD** (Runtime assigned) | Selected via Backend PostgreSQL authorization | PROJECT_APPROVED |
| **Spreading Factor** | **SF7** | `SpreadingFactor = 0b0111` in `RegModemConfig2` | PDF_VERIFIED |
| **Bandwidth (BW)** | **125,000 Hz** (125 kHz) | `Bw = 0b0111` in `RegModemConfig1` | PDF_VERIFIED |
| **Coding Rate (CR)** | **4/5** ($CR=1$) | `CodingRate = 0b001` in `RegModemConfig1` | PDF_VERIFIED |
| **Payload CRC** | **ON** | `RxPayloadCrcOn = 1` in `RegModemConfig2` | PDF_VERIFIED |
| **Header Mode** | **Explicit Header** | `ImplicitHeaderModeOn = 0` in `RegModemConfig1` | PDF_VERIFIED |
| **LoRa Sync Word** | **`0x12`** | `SyncWord = 0x12` in `RegSyncWord` (`0x39`) | PDF_VERIFIED |
| **Low Data Rate Optimize** | **OFF** ($DE = 0$) | `LowDataRateOptimize = 0` in `RegModemConfig3` | PDF_VERIFIED |
| **Frequency Hopping** | **DISABLED** | `FreqHoppingPeriod = 0x00` in `RegHopPeriod` | PDF_VERIFIED |
| **Preamble Length** | **TBD** | Standard calculation assumes 8 symbols | NOT_VERIFIED |
| **TX Output Power** | **TBD** | Subject to link-budget & battery life freeze | NOT_VERIFIED |
| **PA Path** | **TBD** (`RFO` vs `PA_BOOST`) | Dependent on board RF matching circuitry | NOT_VERIFIED |

> [!CAUTION]
> **No Guessing of TBD Fields:**
> Firmware must **never** hardcode assumptions for parameters marked `TBD`. Preamble length, TX output power code, and PA pin selection will be provided in an upcoming hardware revision freeze.

---

## 2. Channel Plan VN920 V1 (11 Discrete Channels)

The project utilizes 11 discrete RF channels with a constant **250 kHz channel spacing**:

### Synthesizer Step and Quantization Precision

Source: Datasheet Section 3.3.3 and Section 4.1.4 (Printed pp. 36, 82 / PDF pp. 37, 83).

The RF carrier synthesizer step for the specified $F_{XOSC} = 32.000\text{ MHz}$ crystal is:

$$F_{step} = \frac{F_{XOSC}}{2^{19}} = \frac{32,000,000\text{ Hz}}{524288} = 61.03515625\text{ Hz}$$

The 24-bit frequency register word `Frf[23:0]` is:

$$Frf = \text{round}\left( \frac{F_{target}}{F_{step}} \right) = \text{round}\left( \frac{F_{target} \times 2^{19}}{32 \times 10^6} \right)$$

Because $250,000\text{ Hz} / 61.03515625\text{ Hz} = 4096 = 0x1000$ exactly, every 250 kHz channel hop corresponds to an increment of exactly `0x1000` in `Frf`. Consequently, the synthesizer quantization error is **0.00 Hz** across all 11 channels.

### Channel Allocation Table

| Channel | Center Frequency (MHz) | Target Frequency (Hz) | 24-bit `Frf` (dec) | 24-bit `Frf` (hex) | `RegFrMsb` (`0x06`) | `RegFrMid` (`0x07`) | `RegFrLsb` (`0x08`) | Actual Synth Freq (Hz) | Quant Error (Hz) |
|---|---:|---:|---:|---|---|---|---|---:|---:|
| **CH00** | 920.250 | 920,250,000 | 15,077,376 | `0xE61000` | `0xE6` | `0x10` | `0x00` | 920,250,000.00 | +0.00 |
| **CH01** | 920.500 | 920,500,000 | 15,081,472 | `0xE62000` | `0xE6` | `0x20` | `0x00` | 920,500,000.00 | +0.00 |
| **CH02** | 920.750 | 920,750,000 | 15,085,568 | `0xE63000` | `0xE6` | `0x30` | `0x00` | 920,750,000.00 | +0.00 |
| **CH03** | 921.000 | 921,000,000 | 15,089,664 | `0xE64000` | `0xE6` | `0x40` | `0x00` | 921,000,000.00 | +0.00 |
| **CH04** | 921.250 | 921,250,000 | 15,093,760 | `0xE65000` | `0xE6` | `0x50` | `0x00` | 921,250,000.00 | +0.00 |
| **CH05** | 921.500 | 921,500,000 | 15,097,856 | `0xE66000` | `0xE6` | `0x60` | `0x00` | 921,500,000.00 | +0.00 |
| **CH06** | 921.750 | 921,750,000 | 15,101,952 | `0xE67000` | `0xE6` | `0x70` | `0x00` | 921,750,000.00 | +0.00 |
| **CH07** | 922.000 | 922,000,000 | 15,106,048 | `0xE68000` | `0xE6` | `0x80` | `0x00` | 922,000,000.00 | +0.00 |
| **CH08** | 922.250 | 922,250,000 | 15,110,144 | `0xE69000` | `0xE6` | `0x90` | `0x00` | 922,250,000.00 | +0.00 |
| **CH09** | 922.500 | 922,500,000 | 15,114,240 | `0xE6A000` | `0xE6` | `0xA0` | `0x00` | 922,500,000.00 | +0.00 |
| **CH10** | 922.750 | 922,750,000 | 15,118,336 | `0xE6B000` | `0xE6` | `0xB0` | `0x00` | 922,750,000.00 | +0.00 |

### Channel Plan Operational Constraints

1. **One Channel per Gateway:** In the MVP deployment, each physical Gateway is assigned and registers exactly **one active channel** at any given time.
2. **Exclusive Registration:** A given channel ID is registered to strictly one Gateway within the local cluster, managed by Backend PostgreSQL registration (Issue #154).
3. **No Multi-Channel Reception:** The SX1276 is a half-duplex single-carrier transceiver. It **cannot** listen to multiple channels simultaneously.
4. **No Autonomous Frequency Hopping:** Nodes and gateways remain on their assigned channel during active sessions. Frequency hopping is disabled.
5. **`CH05` is NOT Default:** `CH05` (921.500 MHz) is simply channel index 5; it is **not** an approved or hardcoded default channel.
6. **Regulatory Status:** This channel table represents an internal approved project engineering design. It is **not** an official statement of Vietnamese statutory radio regulations, and channel allocation does **not** convey RF transmission compliance.

---

## 3. Register Configuration for Active Profile

Source: Datasheet Section 4.4, Table 41 (PDF pages 108–115).

To guarantee protocol compliance, the driver must enforce the following register configurations:

### 1. `RegModemConfig1` (`0x1D`)
- **Field Definitions:**
  - `Bw[7:4]` = `0b0111` ($125\text{ kHz}$)
  - `CodingRate[3:1]` = `0b001` (CR 4/5)
  - `ImplicitHeaderModeOn[0]` = `0` (Explicit header mode)
- **Computed Byte Value:** `0b01110010` = **`0x72`**.
- **Driver Rule:** This full byte can be written directly during modem initialization.

### 2. `RegModemConfig2` (`0x1E`)
- **Field Definitions:**
  - `SpreadingFactor[7:4]` = `0b0111` ($SF7$)
  - `TxContinuousMode[3]` = `0` (Single packet transmission)
  - `RxPayloadCrcOn[2]` = `1` (Enable CRC generation on TX; CRC checked on RX)
  - `SymbTimeout[9:8][1:0]` = Configurable RX timeout MSB.
- **Driver Caution (Do NOT Overwrite `SymbTimeout`):**
  Bits 1:0 store the upper 2 bits of the 10-bit symbol timeout. Firmware must **not** blindly write a static constant (e.g., `0x74`) without resolving the timeout. Instead, use a read-modify-write sequence:
  ```c
  uint8_t current_val = sx1276_read(REG_MODEM_CONFIG_2);
  uint8_t new_val = (current_val & 0x03) | (0x07 << 4) | (1 << 2); // Keep bits 1:0, set SF7 and CRC
  sx1276_write(REG_MODEM_CONFIG_2, new_val);
  ```

### 3. `RegModemConfig3` (`0x26`)
- **Field Definitions:**
  - `Unused[7:4]` = `0b0000` (read-only)
  - `LowDataRateOptimize[3]` = `0` (Disabled, mandatory because $T_s = 1.024\text{ ms} \le 16\text{ ms}$)
  - `AgcAutoOn[2]` = `0` (Manual LNA gain) or `1` (Internal AGC loop). Default is `0`.
  - `Reserved[1:0]` = `0b00`.
- **Driver Caution (Do NOT Clear `AgcAutoOn`):**
  When configuring `LowDataRateOptimize = 0`, firmware must not inadvertently clear bit 2 (`AgcAutoOn`) if the AGC loop was enabled:
  ```c
  uint8_t reg3 = sx1276_read(REG_MODEM_CONFIG_3);
  reg3 &= ~(1 << 3); // Clear LowDataRateOptimize (bit 3 = 0)
  sx1276_write(REG_MODEM_CONFIG_3, reg3);
  ```

### 4. `RegSyncWord` (`0x39`)
- **Field Definitions:**
  - `SyncWord[7:0]` = **`0x12`** (LoRa private network sync word).
- **Driver Rule:** Value `0x34` is reserved for LoRaWAN public networks and must **not** be used in this P2P project.

### 5. `RegFrMsb/Mid/Lsb` (`0x06–0x08`)
- **Field Definitions:** 24-bit carrier frequency word programmed from the Channel Plan table above.
- **Driver Rule:** Always program MSB (`0x06`) first, Mid (`0x07`) second, and LSB (`0x08`) last, because writing `RegFrLsb` triggers the internal synthesizer retuning sequence. Must be performed in `SLEEP` or `STDBY` mode.

---

## 4. Runtime Configuration Checklist

When initializing the transceiver into `PHY_PROFILE_MVP_V1`, the driver must execute the following sequence:

1. **Reset & Health Check:** Assert NRESET low for $\ge 100\text{ }\mu\text{s}$, wait $10\text{ ms}$, read `RegVersion` (`0x42`) expecting `0x12`.
2. **Select LoRa Mode:** Put device into `SLEEP` mode (`RegOpMode = 0x00`), then set `LongRangeMode = 1` (`RegOpMode = 0x80`).
3. **Transition to Standby:** Set `Mode = 001` (`RegOpMode = 0x81`).
4. **Silicon Errata Fix:** Clear `AutomaticIFOn` via read-modify-write: `sx1276_read(0x31) & ~0x80` (bit 7 = 0; if reset value is `0xC3`, result is `0x43`, **never hardcode full byte `0x03`**).
5. **Tune RF Frequency:** Write `RegFrMsb`, `RegFrMid`, `RegFrLsb` corresponding to the backend-authorized channel.
6. **Set Modem Config 1:** Write `0x72` to `RegModemConfig1` (125 kHz BW, CR 4/5, Explicit header).
7. **Set Modem Config 2:** Set SF7 (`0x70`) and `RxPayloadCrcOn` (`0x04`) while preserving `SymbTimeout[9:8]`.
8. **Set Modem Config 3:** Ensure `LowDataRateOptimize = 0` while preserving `AgcAutoOn`.
9. **Set Sync Word:** Write `0x12` to `RegSyncWord` (`0x39`).
10. **Set FIFO Pointers:** Write `0x80` to `RegFifoTxBaseAddr` and `0x00` to `RegFifoRxBaseAddr`.
11. **Configure DIO0:** Set `Dio0Mapping` in `RegDioMapping1` (`0x40`) appropriate to next operation (`01` for TX, `00` for RX).

---

## 5. Physical Time-on-Air (ToA) for Active Profile

Source: Datasheet Section 4.1.1.7 (PDF page 31).

For the active profile parameters ($BW = 125\text{ kHz}$, $SF = 7$, $CR = 1$, $IH = 0$, $CRC = 1$, $DE = 0$, $N_{preamble} = 8$):
- **Symbol Duration:** $T_s = \frac{2^7}{125000} = \mathbf{1.024\text{ ms}}$.
- **Preamble Duration:** $T_{preamble} = (8 + 4.25) \times 1.024\text{ ms} = \mathbf{12.544\text{ ms}}$.
- **Payload Symbol Count (for 16-byte payload):**
  $$N_{payload} = 8 + \max\left( \left\lceil \frac{8(16) - 4(7) + 28 + 16(1) - 0}{4(7 - 0)} \right\rceil (1 + 4), 0 \right) = 8 + \lceil 144 / 28 \rceil \times 5 = 8 + 30 = \mathbf{38\text{ symbols}}$$
- **Payload Duration:** $T_{payload} = 38 \times 1.024\text{ ms} = \mathbf{38.912\text{ ms}}$.
- **Total Time-on-Air:** $T_{packet} = 12.544\text{ ms} + 38.912\text{ ms} = \mathbf{51.456\text{ ms}}$.

*(Detailed operational state transitions and TDMA guard timing budgets are documented in [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md)).*
