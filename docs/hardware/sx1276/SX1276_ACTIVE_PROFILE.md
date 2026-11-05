# SX1276 Active PHY Profile — PHY_PROFILE_MVP_V1 & TEST_PROFILE_V1

## 1. Approved PHY Parameters Summary

This document specifies the authoritative physical layer configuration for the **MVP V1 Custom LoRa P2P** network. Operational values are **configurable presets** managed through ESP-IDF `menuconfig` and mapped to registers via a typed configuration pipeline; entries marked `TBD` or `UNKNOWN` remain unresolved and must not be hardcoded.

```text
idf.py menuconfig ──> sdkconfig.h ──> sx1276_phy_config_t ──> sx1276_config_validate() ──> sx1276_register_plan_build() ──> SPI Apply
```

### Approved Baseline Profile (`PHY_PROFILE_MVP_V1`) & Test Profile (`SX1276_TEST_PROFILE_V1`)

| Parameter | Preset / Value | Architectural Role & Silicon Setting |
|---|---|---|
| **Transceiver** | Semtech SX1276 | LoRa Mode (`LongRangeMode = 1` in `RegOpMode`, writable only in `SLEEP`) |
| **Network Architecture** | Custom LoRa P2P | Event-only Static TDMA (Gateway-controlled); **no LoRaWAN stack** |
| **PHY Profile Name** | `PHY_PROFILE_MVP_V1` | Approved baseline configuration preset |
| **Test Profile Name** | `SX1276_TEST_PROFILE_V1` | Two-board bench bring-up test preset |
| **RF Operating Band** | 920.0–923.0 MHz | High-Frequency (HF) port ($> 525\text{ MHz}$) |
| **Channel Plan** | VN920 V1 (11 channels) | Spacing: 250 kHz (920.250–922.750 MHz) |
| **Active Channel** | **Assigned at runtime** | Selected via Backend PostgreSQL authorization (#154); Kconfig provides test default only |
| **Spreading Factor** | **SF7** | `SpreadingFactor = 0b0111` in `RegModemConfig2` (selectable via Kconfig) |
| **Bandwidth (BW)** | **125,000 Hz** (125 kHz) | `Bw = 0b0111` in `RegModemConfig1` (selectable via Kconfig) |
| **Coding Rate (CR)** | **4/5** ($CR=1$) | `CodingRate = 0b001` in `RegModemConfig1` (selectable via Kconfig) |
| **Payload CRC** | **ON** | `RxPayloadCrcOn = 1` in `RegModemConfig2` (PHY CRC; does not authenticate MAC frames) |
| **Header Mode** | **Explicit Header** | `ImplicitHeaderModeOn = 0` in `RegModemConfig1` |
| **LoRa Sync Word** | **`0x12`** | `SyncWord = 0x12` in `RegSyncWord` (`0x39`); `0x34` (LoRaWAN) is prohibited |
| **Low Data Rate Optimize** | **OFF** ($DE = 0$) | `LowDataRateOptimize = 0` in `RegModemConfig3` (mandatory since $T_s = 1.024\text{ ms} \le 16\text{ ms}$) |
| **Frequency Hopping** | **DISABLED** | `FreqHoppingPeriod = 0x00` in `RegHopPeriod` |
| **Preamble Length** | **8 symbols** | `TEST_PROFILE_V1` selectable preset; not a measured production constant |
| **PA Ramp Time** | **40 µs** | `PaRamp[3:0] = 0x9` in `RegPaRamp` (`0x0A`); selectable Kconfig default |
| **Over-Current Protection** | **ON, 100 mA** | `OcpOn = 1`, `OcpTrim = 0x0B` (`RegOcp = 0x2B`); limits PA supply current |
| **AGC Loop** | **ON** | `AgcAutoOn = 1` in `RegModemConfig3[2]`; controls LNA gain automatically |
| **LNA HF Boost** | **OFF** | `LnaBoostHf[1:0] = 00b` in `RegLna[1:0]`; manual LNA gain is disabled while AGC is ON |
| **TX Output Power Target** | **+2 dBm** (target) | Selectable test default; optional alternate **+5 dBm** for supervised test only |
| **PA Path Selection** | **UNKNOWN / NOT_VERIFIED** | Module antenna pad is wired to `ANT`, but internal PA routing is unverified |
| **RF TX Default State** | **DISABLED / FAIL-CLOSED** | RF TX disabled until PA path, antenna matching, and regulatory safety are verified |

> [!CAUTION]
> **Fail-Closed RF Safety Gate:**
> Menuconfig selection of +2 dBm is an internal target power code, **not** an independently verified conducted or radiated EIRP measurement. Because the commercial 915-MHz module PA path (`RFO_HF` vs `PA_BOOST`) is unverified, **RF TX must remain disabled by default**. The driver must reject transmission requests fail-closed if the configured PA path is unknown or contradictory.

---

## 2. Channel Plan VN920 V1 (11 Discrete Channels)

The project utilizes 11 discrete RF channels with a constant **250 kHz channel spacing**:

### Synthesizer Step and Quantization Precision

The RF carrier synthesizer step for the specified $F_{XOSC} = 32.000\text{ MHz}$ crystal is:

$$F_{step} = \frac{F_{XOSC}}{2^{19}} = \frac{32,000,000\text{ Hz}}{524288} = 61.03515625\text{ Hz}$$

The 24-bit frequency register word `Frf[23:0]` is:

$$Frf = \text{round}\left( \frac{F_{target}}{F_{step}} \right) = \text{round}\left( \frac{F_{target} \times 2^{19}}{32 \times 10^6} \right)$$

Because $250,000\text{ Hz} / 61.03515625\text{ Hz} = 4096 = 0x1000$ exactly, every 250 kHz channel hop corresponds to an increment of exactly `0x1000` in `Frf`. Synthesizer quantization error is **0.00 Hz** across all 11 channels.

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

1. **One Channel per Gateway:** In the MVP deployment, each physical Gateway operates on strictly **one active channel** at any given time.
2. **Exclusive Registration:** Channel allocation is managed exclusively by Backend PostgreSQL schedule (#154).
3. **No Multi-Channel Reception:** SX1276 is a half-duplex single-carrier transceiver; it cannot listen to multiple channels concurrently.
4. **No Autonomous Frequency Hopping:** Frequency hopping is disabled. Nodes and Gateways remain on their assigned channel during active sessions.
5. **`CH05` is NOT Default:** `CH05` (921.500 MHz) is index 5 in the table; it is **not** an authorized default channel.
6. **Regulatory Status:** This plan is an internal engineering design. Channel allocation does **not** convey statutory RF compliance.

---

## 3. Register Encoding from Typed Configuration

Active register bytes are **derived programmatically** by driver encoding functions from typed configuration structures (`sx1276_phy_config_t`). Register bytes cited below represent the computed values for the approved presets:

### 1. `RegModemConfig1` (`0x1D`)
- **Field Definitions:**
  - `Bw[7:4]` = `0b0111` (125 kHz)
  - `CodingRate[3:1]` = `0b001` (CR 4/5)
  - `ImplicitHeaderModeOn[0]` = `0` (Explicit header mode)
- **Computed Value for `PHY_PROFILE_MVP_V1`:** `0b01110010` = **`0x72`**.
- **Driver Architecture:** The driver derives this value using bitfield encoders (`(bw << 4) | (cr << 1) | header_mode`), not raw literals.

### 2. `RegModemConfig2` (`0x1E`)
- **Field Definitions:**
  - `SpreadingFactor[7:4]` = `0b0111` (SF7)
  - `TxContinuousMode[3]` = `0` (Single packet transmission)
  - `RxPayloadCrcOn[2]` = `1` (Enable PHY CRC)
  - `SymbTimeout[9:8][1:0]` = Configurable RX timeout MSB
- **Driver Rule (Preserve `SymbTimeout`):**
  Bits 1:0 store the upper 2 bits of the 10-bit symbol timeout. Use read-modify-write:
  ```c
  uint8_t current_val = sx1276_read(REG_MODEM_CONFIG_2);
  uint8_t new_val = (current_val & 0x03) | (sf << 4) | (crc_en ? (1 << 2) : 0);
  sx1276_write(REG_MODEM_CONFIG_2, new_val);
  ```

### 3. `RegModemConfig3` (`0x26`)
- **Field Definitions:**
  - `LowDataRateOptimize[3]` = `0` (Disabled for SF7/BW125)
  - `AgcAutoOn[2]` = `1` (AGC loop enabled for `SX1276_TEST_PROFILE_V1`)
  - `Reserved[1:0]` = `0b00`
- **Computed Value for `SX1276_TEST_PROFILE_V1`:** `0b00000100` = **`0x04`**.
- **Driver Rule:** Preserve reserved bits and maintain AGC state when adjusting LDRO:
  ```c
  uint8_t reg3 = sx1276_read(REG_MODEM_CONFIG_3);
  reg3 = (reg3 & ~0x0C) | (ldro ? (1 << 3) : 0) | (agc_on ? (1 << 2) : 0);
  sx1276_write(REG_MODEM_CONFIG_3, reg3);
  ```

### 4. `RegPaConfig` (`0x09`) & `RegPaRamp` (`0x0A`)
- **Power Target:** +2 dBm initial test default (optional alternate +5 dBm).
- **Field Mapping:** Typed power encoder validates configured PA path and maps target dBm to `OutputPower[3:0]` and `MaxPower[6:4]`.
- **`RegPaRamp`:** `PaRamp[3:0] = 0x9` (40 µs ramp time).

### 5. `RegOcp` (`0x0B`)
- **Field Definitions:** `OcpOn[5] = 1`, `OcpTrim[4:0] = 11` (100 mA).
- **Computed Value for `SX1276_TEST_PROFILE_V1`:** `0x20 | 0x0B` = **`0x2B`**.
- **Driver Rule:** Encode limit via integer trim converter: $I_{max} = 45 + 5 \times Trim\text{ [mA]}$ (for $Trim \le 15$).

### 6. `RegLna` (`0x0C`)
- **Field Definitions:** `LnaGain[7:5]` (controlled by AGC when `AgcAutoOn=1`), `LnaBoostHf[1:0] = 00b` (HF Boost OFF).
- **Driver Rule:** When `AgcAutoOn=1`, manual LNA gain is inapplicable. Manual gain is selectable only with AGC OFF.

### 7. `RegSyncWord` (`0x39`)
- **Value:** **`0x12`** (private LoRa P2P sync word). Never use `0x34` (reserved for LoRaWAN).

### 8. `RegFrMsb/Mid/Lsb` (`0x06–0x08`)
- Programmed in `SLEEP` or `STDBY` mode. Write MSB (`0x06`), Mid (`0x07`), and LSB (`0x08`) in order. Writing `RegFrLsb` triggers synthesizer retuning.

---

## 4. Radio RX-Mode Policy & TDMA Roles

1. **Node Normal Event Flow:**
   - Default state is ESP32 Deep-sleep / radio low-power per #149.
   - Button/event detection sets local alarm and stages durable pending Event; **no immediate RF TX on event**.
   - At its assigned static DATA slot (#125/#131), Node transmits Event frame, then transitions to **`RxSingle` during bounded ACK window**.
   - If authenticated ACK is received, Node returns to Deep-sleep. If missing or invalid, retry only in a subsequent authorized own DATA slot.
2. **Node Scheduled Maintenance Flow:**
   - Node wakes before scheduled Maintenance reception window, enters **`RxSingle`** to receive authenticated Gateway `SYNC_BEACON`.
   - Node switches mode to transmit **`HEALTH_REPLY`** in its permitted Maintenance response slot. Maintenance is **not RX-only**; no DATA/Maintenance/ACK overlap.
3. **Gateway Continuous Receive Flow:**
   - Gateway operates in **`RxContinuous` during permitted receive phases** (including DATA RX windows).
   - Single half-duplex transceiver: Radio Owner coordinates transitions: `RxContinuous → Standby → TX (ACK or SYNC_BEACON) → RxContinuous`. The Gateway cannot receive while transmitting.

---

## 5. Runtime Configuration Checklist

When initializing into `PHY_PROFILE_MVP_V1` / `SX1276_TEST_PROFILE_V1`, the driver executes:

1. **Reset & Health Check:** Assert NRESET low $\ge 100\text{ }\mu\text{s}$, wait $10\text{ ms}$, read `RegVersion` (`0x42`) expecting `0x12`.
2. **Select LoRa Mode:** Enter `SLEEP` (`RegOpMode = 0x00`), then set `LongRangeMode = 1` (`RegOpMode = 0x80`).
3. **Transition to Standby:** Set `Mode = 001` (`RegOpMode = 0x81`).
4. **Silicon Errata Fix:** Clear `AutomaticIFOn` via read-modify-write: `sx1276_read(0x31) & ~0x80` (yielding `0x43` if reset is `0xC3`; never hardcode `0x03`).
5. **Tune RF Frequency:** Write `RegFrMsb`, `RegFrMid`, `RegFrLsb` for the Backend-authorized channel.
6. **Set Modem Config 1:** Write computed `0x72` (125 kHz BW, CR 4/5, Explicit header).
7. **Set Modem Config 2:** Set SF7 (`0x70`) and `RxPayloadCrcOn` (`0x04`) while preserving `SymbTimeout[9:8]`.
8. **Set Modem Config 3:** Ensure `LowDataRateOptimize = 0` and `AgcAutoOn = 1`.
9. **Set Preamble:** Write preamble length (8 symbols test preset: `0x0008` in `0x20`–`0x21`).
10. **Set PA Ramp & OCP:** Write `0x09` to `RegPaRamp` (40 µs) and `0x2B` to `RegOcp` (100 mA).
11. **Set LNA:** Write `0x20` to `RegLna` (HF Boost OFF, default current).
12. **Set Sync Word:** Write `0x12` to `RegSyncWord` (`0x39`).
13. **Set FIFO Pointers:** Write `0x80` to `RegFifoTxBaseAddr` and `0x00` to `RegFifoRxBaseAddr`.
14. **Configure DIO0:** Set `Dio0Mapping` in `RegDioMapping1` (`0x40`) appropriate to operation (`01` for TX, `00` for RX).

---

## 6. Physical Time-on-Air (ToA) for Active Profile

For active profile parameters ($BW = 125\text{ kHz}$, $SF = 7$, $CR = 1$, $IH = 0$, $CRC = 1$, $DE = 0$, $N_{preamble} = 8$):
- **Symbol Duration:** $T_s = \frac{2^7}{125000} = \mathbf{1.024\text{ ms}}$.
- **Preamble Duration:** $T_{preamble} = (8 + 4.25) \times 1.024\text{ ms} = \mathbf{12.544\text{ ms}}$.
- **Payload Symbol Count (for 16-byte payload):**
  $$N_{payload} = 8 + \max\left( \left\lceil \frac{8(16) - 4(7) + 28 + 16(1) - 0}{4(7 - 0)} \right\rceil (1 + 4), 0 \right) = 8 + \lceil 144 / 28 \rceil \times 5 = 8 + 30 = \mathbf{38\text{ symbols}}$$
- **Payload Duration:** $T_{payload} = 38 \times 1.024\text{ ms} = \mathbf{38.912\text{ ms}}$.
- **Total Time-on-Air:** $T_{packet} = 12.544\text{ ms} + 38.912\text{ ms} = \mathbf{51.456\text{ ms}}$.

*(Detailed operational transitions, IRQ cleanup, and TDMA guard timing budgets are documented in [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md)).*
