# SX1276 Non-MVP Modes and Auxiliary Registers

> [!NOTE]
> **Classification: `NON_MVP_REFERENCE`**
> The contents of this document are preserved for engineering completeness and future migration paths.
> **They are NOT active configurations for the current MVP V1 firmware.** AI agents developing the active P2P driver must not load these settings into the active PHY configuration.

Source: Semtech SX1276/77/78/79 Datasheet Rev. 7 (May 2020), Sections 2.1, 4.1.1, 4.1.4–4.1.6, 4.2, 5.3, 6.2, and Table 41; PDF pages 27–32, 36–37, 46–107, 108–115.

---

## 1. Alternate Spreading Factors (SF6, SF8–SF12)

### Spreading Factor 6 Special Configuration
Operating at SF6 achieves the fastest LoRa chirps (64 chips/symbol) but imposes strict silicon constraints:
- **Implicit Header Required:** SF6 **cannot** operate with an explicit header ($IH = 1$ is mandatory).
- **Detection Optimize:** Bitfield `DetectionOptimize` in `RegDetectOptimize` (`0x31`, bits 2:0) must be set to `0x05` (instead of standard `0x03`).
- **Detection Threshold:** `RegDetectionThreshold` (`0x37`) must be set to `0x0C` (instead of standard `0x0A`).
- When returning to SF7–SF12, these registers must be restored to `0x03` and `0x0A` respectively.

### Spreading Factors 8 through 12 and LDRO Rules
- **SF8–SF10:** Standard explicit header, `DetectionOptimize = 0x03`, `DetectionThreshold = 0x0A`.
- **SF11–SF12 at 125 kHz BW:** Symbol duration exceeds 16 ms ($T_s = 16.384\text{ ms}$ for SF11; $T_s = 32.768\text{ ms}$ for SF12). **LowDataRateOptimize (`DE = 1` in `RegModemConfig3`) is MANDATORY.** Both transmitter and receiver must agree, or the symbol count mismatch prevents frame demodulation.

---

## 2. Alternate Signal Bandwidths and Coding Rates

### Signal Bandwidths (Table in `RegModemConfig1[7:4]`)
- `0000`: 7.8 kHz
- `0001`: 10.4 kHz
- `0010`: 15.6 kHz
- `0011`: 20.8 kHz
- `0100`: 31.25 kHz
- `0101`: 41.7 kHz
- `0110`: 62.5 kHz
- `0111`: 125 kHz (Active MVP Profile)
- `1000`: 250 kHz
- `1001`: 500 kHz (Requires high-bandwidth errata optimization)
- *Band Restriction:* In the lower frequency band (169 MHz), bandwidths 250 kHz and 500 kHz are **not supported**.

### Coding Rates (Table in `RegModemConfig1[3:1]`)
- `001`: 4/5 ($CR=1$) (Active MVP Profile)
- `010`: 4/6 ($CR=2$)
- `011`: 4/7 ($CR=3$)
- `100`: 4/8 ($CR=4$)
- All other bit patterns are reserved.

---

## 3. Secondary Known-Answer Time-on-Air Test Vectors

The following vectors provide independent theoretical validation of the ToA equation across non-MVP operating modes:

| Vector ID | Profile Details | $T_s$ | $N_{preamble}$ | $T_{preamble}$ | Numerator / Denom | Ceil | $N_{payload}$ | $T_{payload}$ | Total ToA ($T_{packet}$) | Verification Status |
|---|---|---|---|---|---|---|---|---|---|---|
| **V1 (Mid-SF)** | SF10, BW125k, CR 4/5, PL 32, IH 0, CRC 1, DE 0 | 8.192 ms | 8 | 100.352 ms | 260 / 40 | 7 | 43 | 352.256 ms | **452.608 ms** | PDF_VERIFIED |
| **V2 (High-SF LDRO)**| SF12, BW125k, CR 4/8, PL 64, IH 0, CRC 1, DE 1 | 32.768 ms | 8 | 401.408 ms | 508 / 40 | 13 | 112 | 3670.016 ms | **4071.424 ms** | PDF_VERIFIED |
| **V3 (Wideband Imp)** | SF8, BW500k, CR 4/6, PL 10, IH 1, CRC 0, DE 0 | 0.512 ms | 12 | 8.320 ms | 56 / 32 | 2 | 20 | 10.240 ms | **18.560 ms** | PDF_VERIFIED |
| **V4 (Boundary SF11)**| SF11, BW125k, CR 4/5, PL 20, IH 0, CRC 1, DE 1 | 16.384 ms | 8 | 200.704 ms | 160 / 36 | 5 | 33 | 540.672 ms | **741.376 ms** | PDF_VERIFIED |

---

## 4. Non-MVP Auxiliary Registers

The registers below are present in the SX1276 silicon but are **not used** by the active MVP V1 firmware:

| Register Name | Addr | Mode | Reset | Function & Notes |
|---|---|---|---|---|
| `RegRxHeaderCntValueMsb` | `0x14` | r | n/a | Number of valid headers received since last transition to RX (MSB). Cleared in Sleep. |
| `RegRxHeaderCntValueLsb` | `0x15` | r | n/a | Valid header counter LSB. Cleared in Sleep. |
| `RegRxPacketCntValueMsb` | `0x16` | rc | n/a | Number of valid packets received since last transition to RX (MSB). Cleared in Sleep. |
| `RegRxPacketCntValueLsb` | `0x17` | r | n/a | Valid packet counter LSB. Cleared in Sleep. |
| `RegHopPeriod` | `0x24` | rw | `0x00` | Frequency hopping symbol period. Disabled (`0x00`) in MVP. |
| `RegPpmCorrection` | `0x27` | rw | `0x00` | Baseband data rate offset value for software AFC ($0.95 \times F_{ErrPpm}$). |
| `RegFeiMsb` | `0x28` | r | `0x00` | Frequency Error Indicator MSB (bits 19:16). Part of 20-bit signed FEI estimator. |
| `RegFeiMid` | `0x29` | r | `0x00` | Frequency Error Indicator Middle byte (bits 15:8). |
| `RegFeiLsb` | `0x2A` | r | `0x00` | Frequency Error Indicator LSB (bits 7:0). $F_{ErrHz} = \frac{LoRaFeiValue \times 2^{24}}{32 \times 10^6} \times \frac{BW_{kHz}}{500}$. |
| `RegRssiWideband` | `0x2C` | r | n/a | Wideband RSSI measurement across receiver channel; used for random number generation. |
| `RegInvertIQ` | `0x33` | rw | `0x27` | I/Q signal inversion in RX (bit 6) and TX (bit 0). Used in LoRaWAN networks. |
| `RegHighBWOptimize1` | `0x36` | rw | `0x20` | Sensitivity optimization for 500 kHz bandwidth. (Errata note applies). |
| `RegHighBWOptimize2` | `0x3A` | rw | `0x20` | Sensitivity optimization for 500 kHz bandwidth. (Errata note applies). |
| `RegInvertIQ2` | `0x3B` | rw | `0x1D` | Complementary IQ inversion register. Set to `0x19` when inverted IQ is selected. |
| `RegPllHop` | `0x44` | rw | `0x2D` | Fast frequency hop control (`FastHopOn` bit 7). Bypasses normal synthesizer lock. |
| `RegTcxo` | `0x4B` | rw | `0x09` | External TCXO input enable (bit 4). Retain default crystal oscillator mode. |

---

## 5. Out-of-Scope Radio Architectures

1. **FSK / GFSK / MSK / GMSK / OOK Modulation:**
   - Full transceiver subsystem detailed in Sections 4.2 and 6.2 of the datasheet.
   - Utilizes separate registers, FIFOs, and packet handlers. Entirely out of scope for the P2P LoRa project.
2. **Frequency Hopping Spread Spectrum (FHSS):**
   - Retained in datasheet Section 4.1.1.8 for FCC dwell-time compliance. Not authorized for MVP.
3. **Top-Level Sequencer (Listen Mode):**
   - Autonomous wake-up engine exclusive to the FSK/OOK modem. Not available in LoRa mode.
4. **LoRaWAN Protocol Stack:**
   - Regional frequency plans, OTAA join handshakes, Adaptive Data Rate (ADR), and Class A/B/C state machines are not implemented. The project uses a custom deterministic TDMA MAC.
