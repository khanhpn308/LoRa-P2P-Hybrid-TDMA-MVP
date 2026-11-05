# SX1276 Silicon Errata & Workaround Analysis

Source: Semtech SX1276/77/78/79 Datasheet Rev. 7 (May 2020), Section 4.4, Table 41 (PDF pages 114–115); Semtech SX1276/77/78 Errata Note (Rev. 1.1).

## 1. Overview and Engineering Policy

The Semtech SX1276 transceiver silicon contains known hardware exceptions that require software-level workarounds during driver initialization and channel switching.

> [!WARNING]
> **Errata Verification Boundaries:**
> 1. `AutomaticIFOn` behavior follows Semtech Datasheet Rev. 7 and must be handled in the active profile.
> 2. Do not enable 500 kHz and spurious-IF workarounds in the active BW125 profile. Their numeric values are derived from secondary driver examples and require direct review of the standalone Semtech Errata Note before use.
> 3. **Bandwidth Isolation Rule:** Workarounds specific to 500 kHz bandwidth **MUST NOT** be applied to the project's 125 kHz active profile.

---

## 2. Erratum 1: Automatic Intermediate Frequency (`AutomaticIFOn`)

- **Affected Register:** `RegDetectOptimize` (`0x31`), bit 7 (`AutomaticIFOn`).
- **Datasheet Citation:** Datasheet Table 41 (PDF page 115).
- **Datasheet Text:** *"Should be set to 0x0 after each reset (POR or manual). See errata note for more information."*
- **Reset Default:** Hardware resets bit 7 to `0x1`.
- **Applicability to MVP Profile (125 kHz):** **MANDATORY.**


### Erratum 1 Mechanism and Problem Description
When `AutomaticIFOn = 1`, the internal receiver demodulator dynamically shifts intermediate frequency (IF) settings during signal acquisition. Under narrow and medium bandwidths (including 125 kHz), this dynamic adjustment causes frequency-tracking loop instability, premature preamble drops, and reduced link sensitivity.

### Required Driver Implementation
The driver **must explicitly clear bit 7 to `0`** using read-modify-write after every Power-On Reset (POR) or manual pin reset:
```c
// Mandatory errata workaround for all LoRa modes
uint8_t detect_opt = sx1276_read(REG_DETECT_OPTIMIZE); // Address 0x31 (reset default 0xC3)
detect_opt &= (uint8_t)~0x80U;                         // Clear AutomaticIFOn (bit 7 = 0, result 0x43)
sx1276_write(REG_DETECT_OPTIMIZE, detect_opt);
```

> [!IMPORTANT]
> **Read-Modify-Write Mandatory:** The hardware reset default of `RegDetectOptimize` is `0xC3` (`AutomaticIFOn=1`, `Reserved=0x40`, `DetectionOptimize=0x03`). Clearing bit 7 (`detect_opt &= ~0x80U`) evaluates to `0x43`. Drivers **must never overwrite the register with a hardcoded whole-byte `0x03`**, as doing so corrupts the factory-reserved bits.

---

## 3. Erratum 2: Sensitivity Optimization for 500 kHz Bandwidth

- **Affected Registers:**
  - `RegHighBWOptimize1` (`0x36`, reset `0x20`).
  - `RegHighBWOptimize2` (`0x3A`, reset `0x20`).
- **Datasheet Citation:** Datasheet Table 41 (PDF page 115).
- **Datasheet Annotation:** *"Optimization for 500 kHz bandwidth. See errata note."*
- **Applicability to MVP Profile (125 kHz):** **NOT APPLICABLE (Do not apply).**
- **Verification Status:**
  - Register presence/annotation: documented in the Semtech datasheet.
  - Workaround hex values: not authorized for the active BW125 profile; validate against standalone errata before use.

### Erratum 2 Mechanism and Problem Description
At 500 kHz bandwidth, internal analog filter gain peaking degrades the receiver noise figure and reduces sensitivity by several dB unless non-default calibration values are injected.

### Workaround Values (For 500 kHz reference only)
In driver stacks operating at $BW = 500\text{ kHz}$ (reference-only values requiring standalone errata review before use):
- Write `0x02` to `RegHighBWOptimize1` (`0x36`).
- Write `0x64` (for High-Band $F_{RF} > 525\text{ MHz}$) or `0x7F` (for Low-Band $F_{RF} < 525\text{ MHz}$) to `RegHighBWOptimize2` (`0x3A`).
- When returning to $BW \le 250\text{ kHz}$ (such as the active MVP 125 kHz profile), restore the verified datasheet reset default values: **`0x20`** for `RegHighBWOptimize1` (`0x36`) and **`0x20`** for `RegHighBWOptimize2` (`0x3A`). Legacy driver snippets mentioning `0x03` for `0x36` contradict the datasheet Table 41 reset default (`0x20`) and must not be used.

> [!CAUTION]
> Applying `0x02` / `0x64` to `RegHighBWOptimize` on a 125 kHz profile impairs demodulation performance. Firmware must keep these registers at their verified reset defaults (`0x20`) for `PHY_PROFILE_MVP_V1`.

---

## 4. Erratum 3: Receiver Spurious Reception / IF Settings

- **Affected Registers:**
  - `IfFreq2` (`0x2F`, reset `0x20`).
  - `IfFreq1` (`0x30`, reset `0x00`).
- **Datasheet Citation:** Datasheet Table 41 (PDF pages 114–115).
- **Datasheet Annotation:** *"See errata note."*
- **Applicability to MVP Profile (125 kHz):** Deferred / Default retained.


### Erratum 3 Mechanism and Problem Description
Under certain narrow bandwidths ($BW < 500\text{ kHz}$), internal synthesizer mixing harmonics can fold into the receiver baseband, creating false preamble detection triggers (spurious packet reception).

### Workaround Summary
Semtech reference implementations (`LoRaMac-node`) optionally adjust `IfFreq1` and offset the RF carrier frequency slightly to steer harmonic spurs outside the receiver channel filter. For the active MVP P2P network operating in a clean RF environment with explicit header verification, default IF settings (`0x20` and `0x00`) are maintained pending RF bench validation.

---

## 5. Summary of Errata Workarounds for Driver Implementers

| Erratum | Target Registers | Action in Active 125 kHz MVP Driver | Action in 500 kHz Mode |
|---|---|---|---|
| **`AutomaticIFOn`** | `0x31[7]` | **MUST CLEAR TO 0** after every reset | **MUST CLEAR TO 0** after every reset |
| **500 kHz Optimization** | `0x36`, `0x3A` | **RETAIN DEFAULT (`0x20`)** | Write `0x02` to 0x36, `0x64`/`0x7F` to 0x3A |
| **Spurious IF Shift** | `0x2F`, `0x30` | **RETAIN DEFAULT (`0x20`, `0x00`)** | Retain default |
