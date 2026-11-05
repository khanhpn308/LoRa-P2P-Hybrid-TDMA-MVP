# SX1276 Lean Register Reference (MVP Profile)


## Scope and Design Rules

This register reference is strictly pruned to the registers and bitfields required by the **MVP V1 LoRa Driver** on ESP32-WROOM-32E. Non-MVP modes (FSK/OOK, SF6, SF8–SF12, BW other than 125 kHz, frequency hopping, and fast hopping) are segregated into [`reference/SX1276_OTHER_MODES.md`](reference/SX1276_OTHER_MODES.md).

### Core Silicon Access Rules
1. **LoRa Mode Selection:** `LongRangeMode` (bit 7 of `RegOpMode`) **can only be modified in SLEEP mode**. Writes in any other mode are ignored.
2. **Access Shared Registers:** `AccessSharedReg` (bit 6 of `RegOpMode`) must remain `0` so that addresses `0x0D`–`0x3F` map to LoRa baseband registers.
3. **Interrupt Flags Clear:** Flags in `RegIrqFlags` (`0x12`) are cleared by **writing a `1`**. Writing `0` leaves them unchanged.
4. **FIFO Memory:** Inaccessible and wiped in `SLEEP` mode. Retained across `STDBY`, `TX`, `RX`, and `CAD`.

---

## Active Register Map

| Register Name | Addr | Mode | Reset Value | Active MVP Value / Runtime Policy | Relevant Bits & Field Definitions | Error / Operational Risk Notes |
|---|---|---|---|---|---|---|
| `RegFifo` | `0x00` | rw | `0x00` | Runtime burst buffer | `Fifo[7:0]`: SPI data input/output port. | Address pointer held at 0x00 during burst; inaccessible and cleared in SLEEP. |
| `RegOpMode` | `0x01` | rw / rwt | `0x09` | `0x80` (Sleep), `0x81` (Stdby), `0x83` (TX), `0x86` (RXSingle) | `LongRangeMode[7]` (1=LoRa); `AccessSharedReg[6]` (0=LoRa map); `LowFrequencyModeOn[3]` (0=HF band $>525$ MHz); `Mode[2:0]` (000=SLEEP, 001=STDBY, 011=TX, 101=RXCONT, 110=RXSINGLE, 111=CAD). | `LongRangeMode` writable **only in SLEEP**. Automatic transition to STDBY after TX, RXSingle, CAD. |
| `RegFrMsb` | `0x06` | rw | `0x6C` | `0xE6` | `Frf[23:16]`: Carrier frequency MSB. | Modify only in SLEEP or STDBY. |
| `RegFrMid` | `0x07` | rw | `0x80` | `0x10` to `0xB0` (per Channel Table) | `Frf[15:8]`: Carrier frequency Mid byte. | Increments by 0x10 for each 250 kHz channel step. |
| `RegFrLsb` | `0x08` | rwt | `0x00` | `0x00` | `Frf[7:0]`: Carrier frequency LSB. | **Writing `RegFrLsb` triggers synthesizer retuning.** |
| `RegPaConfig` | `0x09` | rw | `0x4F` | Runtime (TBD) | `PaSelect[7]` (0=RFO, 1=PA_BOOST); `MaxPower[6:4]`; `OutputPower[3:0]`. | Do not hardcode until PCB PA path and TX power are frozen. |
| `RegPaRamp` | `0x0A` | rw | `0x09` | `0x09` (40 $\mu$s) | `PaRamp[3:0]`: Rise/fall ramp time of PA (0000=3.4ms .. 1001=40us .. 1111=10us). | Shapes TX transient spectrum. |
| `RegOcp` | `0x0B` | rw | `0x2B` | `0x2B` (100 mA) | `OcpOn[5]` (1=enabled); `OcpTrim[4:0]` (0x0B = 100 mA current limit). | Protects battery/supply from overcurrent during TX. |
| `RegLna` | `0x0C` | rw | `0x20` | TBD / PROPOSED: `0x20` (default) or `0x23` (HF Boost) | `LnaGain[7:5]` (001=G1 max gain); `LnaBoostLf[4:3]`; `Reserved[2]`; `LnaBoostHf[1:0]` (00=default, 11=Boost on 150% current). | **Unfrozen / Subject to RF measurement:** Value `0x23` is PROPOSED for link budget but NOT an Owner-approved mandatory default. If `RegModemConfig3.AgcAutoOn = 1`, `LnaGain` bits 7:5 are dynamically overridden by the internal AGC loop. |
| `RegFifoAddrPtr` | `0x0D` | rw | `0x00` | Runtime dynamic pointer | `FifoAddrPtr[7:0]`: SPI interface address pointer into 256-byte FIFO RAM. | Automatically increments on each byte read/written through `RegFifo`. |
| `RegFifoTxBaseAddr` | `0x0E` | rw | `0x80` | `0x80` | `FifoTxBaseAddr[7:0]`: Start address in FIFO for TX buffer. | TX payload is written here prior to transmission. |
| `RegFifoRxBaseAddr` | `0x0F` | rw | `0x00` | `0x00` | `FifoRxBaseAddr[7:0]`: Start address in FIFO for RX buffer. | Demodulator writes incoming packet payloads starting here. |
| `RegFifoRxCurrentAddr`| `0x10` | r | n/a | Runtime latch | `FifoRxCurrentAddr[7:0]`: Start address in FIFO of the payload of the last received packet. | **Must copy this value to `RegFifoAddrPtr` before reading received packet from `RegFifo`.** |
| `RegIrqFlagsMask` | `0x11` | rw | `0x00` | `0x00` (or runtime mask) | Bits 7:0 mask corresponding IRQ flags: `RxTimeoutMask[7]`, `RxDoneMask[6]`, `PayloadCrcErrorMask[5]`, `ValidHeaderMask[4]`, `TxDoneMask[3]`, `CadDoneMask[2]`. | A bit set to `1` prevents the flag from driving the DIO pin. Does not prevent flag from setting in `RegIrqFlags`. |
| `RegIrqFlags` | `0x12` | rc | `0x00` | Runtime status / clear | Bits 7:0: `RxTimeout[7]`, `RxDone[6]`, `PayloadCrcError[5]`, `ValidHeader[4]`, `TxDone[3]`, `CadDone[2]`, `CadDetected[0]`. | **Write 1 to clear.** Writing 0 has no effect. |
| `RegRxNbBytes` | `0x13` | r | n/a | Runtime read | `FifoRxBytesNb[7:0]`: Number of payload bytes received in latest packet. | Read upon `RxDone` to know how many bytes to pull from FIFO. |
| `RegModemStat` | `0x18` | r | `0x10` | Diagnostic read | `RxCodingRate[7:5]`; `ModemStatus[4:0]` (bit 4: Modem clear, bit 3: Header info valid, bit 2: RX on-going, bit 1: Signal synced, bit 0: Signal detected). | Observable indicators: check `RxOnGoing` (bit 2) and `ValidHeader` before assuming timeout. |
| `RegPktSnrValue` | `0x19` | r | n/a | Runtime read | `PacketSnr[7:0]`: Signed 8-bit two's complement SNR divided by 4: $SNR [dB] = PacketSnr_{2's} / 4.0$. | Negative values mean signal received below thermal noise floor. |
| `RegPktRssiValue` | `0x1A` | r | n/a | Runtime read | `PacketRssi[7:0]`: Averaged packet RSSI. HF ($>525$ MHz): $-157 + Rssi$ (if $SNR \ge 0$) or $-157 + Rssi + SNR$ (if $SNR < 0$). | See [`SX1276_DRIVER_OPERATIONS.md`](SX1276_DRIVER_OPERATIONS.md) for high-signal linearity adjustment. |
| `RegRssiValue` | `0x1B` | r | n/a | Runtime read | `Rssi[7:0]`: Instantaneous RSSI: $-157 + Rssi$ (HF). | Can be sampled during payload reception between `ValidHeader` and `RxDone`. |
| `RegHopChannel` | `0x1C` | r | n/a | Runtime read | `PllTimeout[7]` (1=PLL did not lock); `CrcOnPayload[6]` (0=CRC off in header, 1=CRC on in header; explicit mode only). | **Must check bit 6 to confirm whether packet contained CRC before trusting `PayloadCrcError`.** |
| `RegModemConfig1` | `0x1D` | rw | `0x72` | `0x72` | `Bw[7:4]` = `0111` (125 kHz); `CodingRate[3:1]` = `001` (4/5); `ImplicitHeaderModeOn[0]` = `0` (Explicit). | Active MVP profile constant. |
| `RegModemConfig2` | `0x1E` | rw | `0x70` | Read-modify-write: `(reg & 0x03) \| 0x74` | `SpreadingFactor[7:4]` = `0111` (SF7); `TxContinuousMode[3]` = `0`; `RxPayloadCrcOn[2]` = `1`; `SymbTimeout[9:8][1:0]`. | **Do not write a static full byte without resolving `SymbTimeout` bits 1:0.** |
| `RegSymbTimeoutLsb` | `0x1F` | rw | `0x64` | Runtime timeout | `SymbTimeout[7:0]`: Combined 10-bit RX timeout LSB ($Timeout = SymbTimeout \times T_s$). | Range 4 to 1023 symbols. |
| `RegPreambleMsb` | `0x20` | rw | `0x00` | `0x00` | `PreambleLength[15:8]`: Programmed preamble length MSB. | Preamble length is currently TBD. Standard default is 8 symbols. |
| `RegPreambleLsb` | `0x21` | rw | `0x08` | `0x08` (TBD) | `PreambleLength[7:0]`: Programmed preamble length LSB. Transmitted duration is $(PreambleLength + 4.25) \times T_s$. | Preamble length is currently TBD. Standard default is 8 symbols. |
| `RegPayloadLength` | `0x22` | rw | `0x01` | Runtime frame length | `PayloadLength[7:0]`: Payload length in bytes (1 to 255). | Set to exact number of bytes loaded into FIFO before asserting TX. |
| `RegMaxPayloadLength`| `0x23` | rw | `0xFF` | Runtime max limit (e.g. 64) | `PayloadMaxLength[7:0]`: Maximum payload length in bytes. | Protects FIFO: generates header CRC error if incoming packet exceeds this value. |
| `RegFifoRxByteAddr` | `0x25` | r | n/a | Runtime read | `FifoRxByteAddrPtr[7:0]`: Address of last byte written + 1 by receiver. | Dynamic real-time pointer. |
| `RegModemConfig3` | `0x26` | rw | `0x00` | Read-modify-write: `reg & ~(1 << 3)` | `LowDataRateOptimize[3]` = `0`; `AgcAutoOn[2]` (1=enable AGC, 0=manual LNA); `Reserved[1:0]` = `00`. | **Do not clear `AgcAutoOn` (bit 2) when clearing `LowDataRateOptimize` (bit 3).** |
| `RegDetectOptimize` | `0x31` | rw | `0xC3` | Read-modify-write: `reg & ~0x80` (Result `0x43` if reset `0xC3`) | `AutomaticIFOn[7]` (1=reset default, **must clear to 0 per errata**); `Reserved[6:3]` (0xC); `DetectionOptimize[2:0]` (`0x03` for SF7..SF12). | **Errata requirement:** Must clear bit 7 (`AutomaticIFOn`) to 0 via read-modify-write. Preserves reserved bits 6:3 and SF7 detection code (`0x03`). If readback is reset default `0xC3`, cleared result is `0x43`, **never hardcode full byte `0x03`**. |
| `RegDetectionThreshold`| `0x37`| rw | `0x0A` | `0x0A` | `DetectionThreshold[7:0]`: Write `0x0A` for SF7..SF12. | Restores optimal preamble detection threshold for SF7. |
| `RegSyncWord` | `0x39` | rw | `0x12` | `0x12` | `SyncWord[7:0]`: LoRa sync word. Default `0x12` for private networks. | Value `0x34` is reserved for LoRaWAN and must not be used in this P2P project. |
| `RegDioMapping1` | `0x40` | rw | `0x00` | `0x40` (TX), `0x00` (RX), `0x80` (CAD) | `Dio0Mapping[7:6]` (00=RxDone, 01=TxDone, 10=CadDone); `Dio1..3Mapping` (bits 5:0). | Reconfigure DIO0 before each radio state transition. |
| `RegDioMapping2` | `0x41` | rw | `0x00` | `0x00` | `Dio4..5Mapping`; `MapPreambleDetect[0]`. | Retain default. |
| `RegVersion` | `0x42` | r | `0x12` | `0x12` (Health check) | `Version[7:0]`: Silicon revision identification byte. | **Must read `0x12` to verify SPI and power integrity after reset.** |
| `RegPaDac` | `0x4D` | rw | `0x84` | `0x84` (Default) | `reserved[7:3]` (0x10); `PaDac[2:0]` (0x04=default, 0x07=+20 dBm high power on PA_BOOST). | High-power mode (+20 dBm) requires strict 1% duty cycle. |
