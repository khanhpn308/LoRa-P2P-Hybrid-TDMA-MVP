# Source Traceability and Verification Matrix

Source: Semtech SX1276/77/78/79 Datasheet Rev. 7 (May 2020), Semtech Errata Note (Rev. 1.1), and Project Owner HW-001 / VN920 V1 Baseline.

## 1. Traceability Matrix

| Subject / Topic | Candidate Document & Section | Source Document | Section | Printed Page / PDF Page | Verification Status | Verification Evidence / Rationale |
|---|---|---|---|---|---|---|
| **Authoritative Scope** | [`README.md`](../README.md) §1 | Datasheet Rev. 7 | 1, 4.1 | Printed pp. 9, 25–26 / PDF pp. 9, 26–27 | PDF_VERIFIED | Confirmed product family, transceiver features, and LoRa capabilities. |
| **HW-001 Pinout** | [`README.md`](../README.md) §3, [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §1 | HW-001 Design | Board Spec | n/a | PROJECT_APPROVED | Owner-confirmed mapping: SCK=5, MISO=19, MOSI=27, NSS=18, RESET=23, DIO0=26. DIO1–5 unrouted. |
| **Strapping Pin GPIO5** | [`README.md`](../README.md) §3, [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §1 | ESP32 Datasheet | Strapping | n/a | PROJECT_APPROVED | Verified GPIO5 is sampled during reset for SDIO slave timing; must idle LOW in SPI Mode 0. |
| **Approved PHY Profile** | [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) §1 | Project Baseline | Contract | n/a | PROJECT_APPROVED | SF7, BW 125k, CR 4/5, Payload CRC ON, Explicit Header, SyncWord 0x12, LDRO OFF. |
| **Channel Plan VN920 V1**| [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) §2 | Project Baseline | Contract | n/a | PROJECT_APPROVED | 11 discrete channels, 250 kHz spacing from 920.250 to 922.750 MHz. |
| **Carrier Synthesizer Step**| [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) §2 | Datasheet Rev. 7 | 3.3.3, 4.1.4 | Printed pp. 36, 82 / PDF pp. 37, 83 | PDF_VERIFIED | $F_{step} = 32\text{ MHz} / 2^{19} = 61.03515625\text{ Hz}$. 250 kHz hop = exactly 4096 steps (0.00 Hz quantization error). |
| **Modem Config Registers**| [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) §3 | Datasheet Rev. 7 | 4.4, Table 41 | Printed pp. 113–114 / PDF pp. 114–115 | PDF_VERIFIED | `RegModemConfig1 = 0x72`, `RegModemConfig2` SF7/CRC bits, `RegModemConfig3` LDRO=0. |
| **LoRa Sync Word** | [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) §3 | Datasheet Rev. 7 | 4.4, Table 41 | Printed p. 115 / PDF p. 116 | PDF_VERIFIED | `RegSyncWord` (`0x39`) = `0x12` (private network default; 0x34 reserved for LoRaWAN). |
| **SPI Slave Protocol** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §2 | Datasheet Rev. 7 | 2.2, Table 11 | Printed pp. 22, 80 / PDF pp. 22, 81 | PDF_VERIFIED | CPOL=0, CPHA=0, $F_{SCK} \le 10\text{ MHz}$, burst auto-increment, FIFO burst address held at 0x00. |
| **Reset Dynamics** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §3 | Datasheet Rev. 7 | 5.2, 7.2 | Printed pp. 116–117 / PDF pp. 117–118 | PDF_VERIFIED | POR 10 ms wait (NRESET floating); manual reset $\ge 100\text{ }\mu\text{s}$ low pulse, $\ge 5\text{ ms}$ recovery wait. |
| **Chip Version Check** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §3 | Datasheet Rev. 7 | 4.2, Table 42 | Printed p. 105 / PDF p. 106 | PDF_VERIFIED | `RegVersion` (`0x42`) readback value is `0x12`. |
| **Operating Modes & State**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §4 | Datasheet Rev. 7 | 4.1.2, 4.1.3 | Printed pp. 34–35, 38–41 / PDF pp. 35–36, 39–42 | PDF_VERIFIED | LoRa mode switchable only in SLEEP; FIFO wiped in SLEEP; automatic return to STDBY after TX/RXSingle/CAD. |
| **Radio Owner & Mutex** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §5 | Driver Architecture | Design Spec | n/a | PROJECT_PROPOSED | Single Radio Owner task, mutex-guarded SPI, ISR notifies task without SPI or blocking calls. |
| **DIO0 Reconfiguration** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §5 | Datasheet Rev. 7 | 4.1.7, Table 18 | Printed p. 45 / PDF p. 46 | PDF_VERIFIED | 01=TxDone, 00=RxDone, 10=CadDone. Verified Table 18 for all mappings. |
| **Interrupt Clear Semantics**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §5, §7.4 | Datasheet Rev. 7 | 4.1.2.4, Table 41 | Printed pp. 35, 110–111 / PDF pp. 36, 111–112 | PDF_VERIFIED | Write 1 to clear (`RegIrqFlags` 0x12). Writing 0 has no effect. Pre-clear stale IRQs before entering RX. |
| **TX Sequence** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §6 | Datasheet Rev. 7 | 4.1.3 | Printed p. 39 / PDF p. 40 | PDF_VERIFIED | Write payload to FIFO, set length, mode=TX, wait for `TxDone`, clear flag. |
| **RX Preamble Priority** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.2 | Datasheet Rev. 7 | 4.1.3 | Printed p. 41 / PDF p. 41 | PDF_VERIFIED | In RxSingle, `RxTimeout` is inhibited if radio is actively receiving data; reception takes priority over timeout. |
| **Modem Status Indicators**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.3 | Datasheet Rev. 7 | 4.1.8, Table 41 | Printed pp. 46, 111 / PDF pp. 47, 112 | PDF_VERIFIED | `RegModemStat` (`0x18`): bit 0 `SignalDetected`, bit 1 `SignalSynchronized`, bit 2 `RxOnGoing`, bit 3 `HeaderInfoValid`. |
| **Two-Stage Host Supervision**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.3 | Driver Architecture | Design Spec | n/a | PROJECT_PROPOSED | Preamble search timer + bounded demodulation extension on `RxOnGoing`/`ValidHeader`; avoids killing valid packets. |
| **RX Event Taxonomy** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.1 | Driver Architecture | Design Spec | n/a | PROJECT_PROPOSED | Distinctly classifies `RX_PACKET_DONE`, `HW_RX_TIMEOUT`, `HOST_WATCHDOG_EXPIRED`, `RX_ABORTED_BY_SCHEDULE`, `RX_ABORTED_BY_RECOVERY`. |
| **RX Single & CRC Check** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.4 | Datasheet Rev. 7 | 4.1.3, Table 41 | Printed pp. 39–42, 112 / PDF pp. 40–43, 113 | PDF_VERIFIED | Must inspect `RegHopChannel.CrcOnPayload` (0x1C[6]) and reject if 0 before checking `PayloadCrcError` (0x12[5]). Discard missing CRC frames before MAC handoff. |
| **Host Buffer Bounds & Own**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §8 | Driver Architecture | Design Spec | n/a | PROJECT_PROPOSED | Check `RegRxNbBytes <= host_buffer_capacity` before `RegFifo` copy; static preallocated buffer pool; zero steady-state `malloc`. |
| **Host RX Timeout Guard** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.3 | System Architecture | Design Spec | n/a | NOT_VERIFIED | DIO1 unrouted; $T_{host\_timeout} = T_{symb\_timeout} + T_{guard}$. $T_{guard}$ is an uncalibrated TBD parameter; no static +20 ms constant is assumed. |
| **FIFO Boundaries** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §8 | Datasheet Rev. 7 | 4.1.2.3, Table 41 | Printed pp. 34–35, 114 / PDF pp. 35–36, 115 | PDF_VERIFIED | 256-byte dual-port RAM. `RegMaxPayloadLength` forces header CRC error to prevent overflow. |
| **ToA Formula & Vectors**| [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §9 | Datasheet Rev. 7 | 4.1.1.7 | Printed p. 31 / PDF p. 31 | PDF_VERIFIED | Correct formula: $N_{payload}=38$, $T_{preamble}=12.544\text{ ms}$. Vectors: 16B = **51.456 ms**, 64B = **118.016 ms**, 255B = **399.616 ms**. |
| **RX Race Arbitration & Residual Race (FIX-10)** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.3 | Datasheet Rev. 7 | 4.1.2.3, 4.1.3 | Printed pp. 39–41 / PDF pp. 40–42 | PROJECT_PROPOSED | Pre-abort re-read of `RegIrqFlags`; 6-scenario arbitration table; explicit residual race window disclaimer; forced TDMA slot abort classified as `RX_ABORTED_BY_SCHEDULE`. |
| **RX Continuous Targeted Cleanup (FIX-11)** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §7.5 | Datasheet Rev. 7 | 4.1.2.4, 4.1.3 | Printed pp. 35, 41 / PDF pp. 36, 41 | PDF_VERIFIED | Targeted write-1-to-clear `snapshot & 0x70`. Prohibits solitary `0x40` (leaves stale CRC/header flags) and unconditional `0xFF` (wipes incoming frame flags). |
| **Deep-Sleep Recovery** | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) §10 | Driver Architecture | Design Spec | n/a | PROJECT_APPROVED | Full hardware reset and register reconfiguration required on ESP32 wake. |
| **Lean Register Map** | [`SX1276_REGISTER_REFERENCE.md`](../SX1276_REGISTER_REFERENCE.md) | Datasheet Rev. 7 | 4.2, 4.4 | Printed pp. 105, 108–115 / PDF pp. 106, 109–116 | PDF_VERIFIED | 37 active registers/bitfields verified against Table 41 and Table 42. |
| **RegLna Configuration** | [`SX1276_REGISTER_REFERENCE.md`](../SX1276_REGISTER_REFERENCE.md) | Datasheet Rev. 7 | 4.4, Table 41 | Printed p. 110 / PDF p. 111 | NOT_VERIFIED | Reset default `0x20`. Boost value `0x23` is PROPOSED for link budget but unfrozen/TBD pending RF bench test; overridden if `AgcAutoOn=1`. |
| **Secondary SF/BW/CR Modes**| [`reference/SX1276_OTHER_MODES.md`](SX1276_OTHER_MODES.md) | Datasheet Rev. 7 | 4.1.1, Table 41 | Printed pp. 27–31, 113 / PDF pp. 28–32, 114 | PDF_VERIFIED | Preserved non-MVP modes (SF6 special settings, SF8–SF12, BW, CR, implicit header). |
| **Errata: AutomaticIFOn** | [`reference/SX1276_ERRATA.md`](SX1276_ERRATA.md) §2, [`SX1276_REGISTER_REFERENCE.md`](../SX1276_REGISTER_REFERENCE.md) | Datasheet Rev. 7 | 4.4, Table 41 | Printed p. 115 / PDF p. 116 | PDF_VERIFIED | Table 41 states bit 7 must be cleared to 0 after reset. Read-modify-write `reg & ~0x80` yields `0x43` from reset `0xC3`; hardcoding `0x03` is forbidden. |
| **Errata: 500k Optimization**| [`reference/SX1276_ERRATA.md`](SX1276_ERRATA.md) §3 | Errata Note 1.1 | 2.1 | n/a | ERRATA_REVIEW_NOT_VERIFIED | Register 0x36/0x3A presence verified in PDF; workaround values derived from driver code. Verified reset default to restore on $\le 250\text{ kHz}$ is 0x20. |
| **Errata: Spurious IF** | [`reference/SX1276_ERRATA.md`](SX1276_ERRATA.md) §4 | Errata Note 1.1 | 2.2 / 2.3 | n/a | ERRATA_REVIEW_NOT_VERIFIED | Registers 0x2F/0x30 verified in PDF; workaround derived from driver code. |

---

## 2. Verification Taxonomy Definitions

1. **`PDF_VERIFIED`:**
   - The technical assertion, register address, bitfield layout, reset value, equation, or silicon timing constraint was directly read, compared, and confirmed in the Semtech SX1276 Datasheet Rev. 7 (May 2020) PDF.
2. **`PROJECT_APPROVED`:**
   - The parameter represents an intentional design decision approved by the Project Owner for this target system (e.g., custom LoRa P2P MAC, Static TDMA scheduling, HW-001 GPIO mapping, Channel Plan VN920 V1).
3. **`PROJECT_PROPOSED`:**
   - A driver implementation state machine, buffer management protocol, or software supervision architecture formulated to safely control the transceiver. While grounded in datasheet hardware facts, the software sequence itself is a driver design policy and must not be conflated with silicon-verified facts.
4. **`NOT_VERIFIED`:**
   - A hardware property or parameter that is unrouted, unmeasured on physical boards, or intentionally pending system freeze (e.g., Preamble Length, TX Output Power, PCB Deep-sleep rail retention). No default value is guessed.
5. **`ERRATA_REVIEW_NOT_VERIFIED`:**
   - A silicon errata workaround whose register address is cited in the datasheet, but whose exact numerical workaround values originate from secondary driver source code and await physical inspection of the standalone errata document `SX1276_77_8_ErrataNote_1.1_STD.pdf`.
6. **`CONFLICT`:**
   - An unresolved discrepancy between documentation sources requiring engineering intervention.
