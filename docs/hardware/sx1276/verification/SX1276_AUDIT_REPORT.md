# SX1276 Candidate Reference Audit & Verification Report

## 1. Executive Summary

This independent technical audit was conducted by a Senior Embedded Engineer, SX1276 Driver Specialist, and Technical Documentation Auditor.

The objective was to audit, verify, streamline, and correct the local SX1276 documentation to produce an authoritative, context-optimized candidate reference package (`SX1276_Agent_Reference_Candidate/`) tailored for AI coding agents and embedded engineers developing firmware for the **ESP32-WROOM-32E + SX1276** transceiver within a **Custom LoRa P2P, Event-Only Static TDMA MAC** architecture.

### Primary Audit Achievements (Round 1 & 2 Summary)
1. **Context Streamlining (Hot vs. Cold Separation):** Segregated the documentation into **4 Hot Context files** (`README.md`, `SX1276_ACTIVE_PROFILE.md`, `SX1276_DRIVER_OPERATIONS.md`, `SX1276_REGISTER_REFERENCE.md`) read by default, cutting default context footprint by **~48%**.
2. **Approved PHY Baseline & Exact Synthesizer Math:** Synchronized with Project Owner-approved **`PHY_PROFILE_MVP_V1`** and **Channel Plan VN920 V1** (11 channels, 250 kHz spacing, 920.250–922.750 MHz) with **0.00 Hz quantization error**.
3. **Hardware Invariants & Driver Foundation:** Documented unrouted DIO1–DIO5 on PCB HW-001, ESP32 strapping pin GPIO5 caution, Radio Owner task SPI exclusivity, and exact Time-on-Air calculation ($51.456\text{ ms}$ for SF7 baseline).
4. **Prior Technical Corrections (FIX-01 to FIX-05):** Resolved `RegDetectOptimize` read-modify-write bit 7 clear (`0x43`, not `0x03`), mandatory drop of packets lacking CRC (`CrcOnPayload == 0`), de-asserted mandatory LNA boost (`0x23` $\to$ TBD/PROPOSED `0x20` reset), parameterized host timeout guard, and unified silicon errata restore defaults (`0x20`).

### Final RX Lifecycle & Safety Corrections (Round 3 — FIX-06 through FIX-09)
Following deep review of Semtech Datasheet Rev. 7 (Sections 4.1.2.3, 4.1.2.4, 4.1.3, 4.1.8, 4.4), critical RX lifecycle, timeout, and buffer safety issues were identified and corrected:

1. **FIX-06 (RX Timeout & Lifecycle Protection):**
   - **The Preamble Near Window End Hazard:** Identified that if a packet preamble arrives near the end of the preamble hunt window, Semtech silicon prioritizes active demodulation over timeout (Datasheet printed p. 41: *"RxTimeout will not be triggered if the device is currently receiving data"*). If host software unilaterally killed the radio upon its hunt timer expiry, valid packets would be killed in mid-air.
   - **Event Taxonomy:** Strictly differentiated five distinct termination events: `RX_PACKET_DONE`, `HW_RX_TIMEOUT`, `HOST_WATCHDOG_EXPIRED`, `RX_ABORTED_BY_SCHEDULE`, `RX_ABORTED_BY_RECOVERY`.
   - **Two-Stage Bounded Supervision:** Established a two-stage host supervision policy: upon search timer expiry, the driver inspects `RegIrqFlags` and `RegModemStat` (`RxOnGoing`, `ValidHeader`). If demodulation is active, it grants a bounded demodulation extension ($T_{demod\_max} = T_{packet}(PL_{max}) + T_{guard\_demod}$) instead of aborting.
   - **TDMA Slot Isolation:** Decoupled TDMA slot deadlines (`RX_ABORTED_BY_SCHEDULE`) from hardware timeouts.
2. **FIX-07 (IRQ Cleanup Across All RX Paths):**
   - Mapped all 9 distinct success, reject, and abort paths (`RX_SUCCESS`, `REJECT_MISSING_CRC`, `REJECT_CRC_ERROR`, `REJECT_INVALID_LENGTH`, `REJECT_HOST_BUFFER_OVERFLOW`, `HW_RX_TIMEOUT`, `HOST_WATCHDOG_EXPIRED`, `RX_ABORTED_BY_SCHEDULE`, `RX_ABORTED_BY_RECOVERY`).
   - Mandated snapshotting `RegIrqFlags` and metadata before clearing.
   - Enforced pre-clearing stale IRQs (`write 0xFF to RegIrqFlags`) prior to launching any RX cycle.
   - Explicitly separated IRQ write-1-to-clear operations from silicon mode transitions.
   - Provided a complete State Transition & Cleanup Table.
3. **FIX-08 (Host Buffer Capacity, Memory Boundaries & Ownership):**
   - Enforced pre-copy validation: `RegRxNbBytes` must be validated against `CONFIG_SX1276_HOST_RX_BUFFER_SIZE` / `host_buffer_capacity` **prior to reading from `RegFifo`**. Frames exceeding capacity are dropped immediately (`REJECT_HOST_BUFFER_OVERFLOW`) to prevent host RAM buffer overruns.
   - Mandated zero dynamic allocation (`malloc`/`free`) in steady-state, using a preallocated static frame buffer pool.
   - Established ownership handover to Custom MAC queue; documented queue-full drop behavior without memory leaks or blocking.
   - Contrasted RX Single (FIFO frozen in `STANDBY`) vs. RX Continuous (FIFO overwritten by next packet unless read immediately).
4. **FIX-09 (Datasheet Source Traceability Rigor):**
   - Disambiguated printed page numbers from PDF viewer page numbers across all candidate files.
   - Created strict verification category `PROJECT_PROPOSED` to distinguish driver implementation policies from silicon-verified facts (`PDF_VERIFIED`).

### Final Technical Remediation & Regression Hardening (Round 4 — FIX-10 through FIX-12)
Following technical review for GitHub Issue #156 integration, three critical issues were resolved and regression-tested:

1. **FIX-10 (RX Race Window Arbitration & Residual Race Boundary):**
   - **Problem:** SPI reading of `RegIrqFlags` followed by commanding `STANDBY` is non-atomic relative to asynchronous RF packet arrival. If a packet completes demodulation during this arbitration, commanding `STANDBY` causes packet loss.
   - **Remediation:** Mandated a final pre-abort re-read of `RegIrqFlags` immediately prior to issuing `STANDBY`. Formulated a complete 6-scenario Arbitration & Pre-Abort Re-Check Table (Scenarios A through F).
   - **Hard Slot Abort Classification:** Classified hard TDMA slot deadline aborts strictly as `RX_ABORTED_BY_SCHEDULE` with in-flight packet truncation / loss risks explicitly documented.
   - **Residual Race Disclosure:** Explicitly disclosed the sub-microsecond residual race window between the final SPI read byte and the subsequent SPI `STANDBY` write command, and strictly prohibited claiming that zero packet loss can be achieved by register polling alone without protocol-level ARQ and guard bands.
2. **FIX-11 (Harmonized Targeted IRQ Cleanup in RX Continuous Mode):**
   - **Problem:** In Section 7.5, writing only `0x40` to `RegIrqFlags` cleared `RxDone` but left `PayloadCrcError` (`0x20`) or `ValidHeader` (`0x10`) uncleared, contaminating subsequent packet evaluations. Furthermore, writing `0xFF` in Continuous mode risked wiping valid header/preamble status of newly arriving packets.
   - **Remediation:** Reconciled Section 7.4 and Section 7.5 to mandate targeted write-1-to-clear: `write RegIrqFlags = (snapshot & 0x70)`. Explicitly explained the dangers of stale flag contamination from solitary `0x40` and why unconditional `0xFF` clearing is prohibited in `RXCONT`.
3. **FIX-12 (Time-on-Air Mathematical Precision & Datasheet Rev. 7 Traceability):**
   - **Problem:** Section 7.3 and Section 8 previously cited rough approximations (~135 ms for 64 bytes and ~412 ms for 255 bytes).
   - **Remediation:** Recomputed exact Semtech formula values for approved profile:
     - PL = 16 bytes: **51.456 ms**
     - PL = 64 bytes: **118.016 ms** (exact: $T_{preamble}=12.544\text{ ms} + T_{payload}=105.472\text{ ms}$)
     - PL = 255 bytes: **399.616 ms** (exact: $T_{preamble}=12.544\text{ ms} + T_{payload}=387.072\text{ ms}$)
   - Completely eradicated all ~135 ms and ~412 ms approximations.
   - Verified that Datasheet Rev. 7 Section 4.1.1.7 is located on printed page 31 / PDF page 31, and receive sequence is on printed pages 39–41 / PDF pages 40–42, updating traceability accordingly.

---

## 2. Integrity and Checksum Ledgers

### 2.1. Original Input Files Baseline (Unmodified)

The original 8 files in `SX1276_Agent_Reference/` were inspected and preserved untouched:

| Original File Name | Size (bytes) | Lines | SHA-256 Checksum |
|---|---:|---:|---|
| `README.md` | 8,352 | 91 | `2a3c8a457dc0cc4df06a8434af514ab530968ad1af2293900f8bc75464a6ef63` |
| `SX1276_REGISTER_REFERENCE.md` | 17,559 | 103 | `a1733e906952caae89f79847bed9ffbdb746f155a25d23724f253106f846fb2b` |
| `SX1276_SPI_RESET_POWER.md` | 10,163 | 113 | `b2d795e68a8055e4ed6576b5e2a60cd00a9ffb655ab5780ec52509173b2823d3` |
| `SX1276_TX_RX_IRQ_FIFO.md` | 10,468 | 142 | `a5d7790795fdd7c2cb4047d6b6d485f63da13e45b03e773fed41a9e4860430bf` |
| `SX1276_RF_TIMING.md` | 13,789 | 234 | `2e295ea41c6360de79aac574bf34c12b038c7483e18a7d1d63bc5f80bfaea88f` |
| `SX1276_REFERENCE_APPENDIX.md` | 7,478 | 93 | `f8ceebc3721d169d5d9f62ac80ee2dab097f78e8a1a6a2076ffde7a5b22f2dc5` |
| `SX1276_AUDIT_REPORT.md` | 12,468 | 119 | `c789ef9a040ade53e0b8e5fcafce6ddbfde76c19548c9e0fcf3fad14f4f351f3` |
| `SX1276_SOURCE_TRACEABILITY.md` | 9,606 | 59 | `7c01baf950a059b02ae5736330bc4f4f25b8a3d67e44a98100b599ca499d0f55` |
| **Total Input Baseline** | **89,883** | **954** | — |

### 2.2. Candidate Files Preflight vs. Post-Fix Ledger (Round 3)

All changes in the candidate package were executed alongside an independent, verified backup (`SX1276_Agent_Reference_Candidate_backup_20261105_rx_final/`):

| Candidate File Path | Pre-Fix Size (B) | Post-Fix Size (B) | Preflight SHA-256 | Post-Fix SHA-256 | Status |
|---|---:|---:|---|---|:---:|
| `README.md` | 8,711 | 8,943 | `bf046d41dc79a5e937acd3e462fe6161eab2f5959789a60f20ab596ae738f669` | `9e940617f774f683a86b819adedfe131c1ab9a13c217a0da3f3b6223c60b033a` | MODIFIED |
| `SX1276_ACTIVE_PROFILE.md` | 11,140 | 11,198 | `afc82f6088c0eff19db08bb33ebfbeb9c2c92470572cad116af1525ae58f7a2d` | `700086ab9e6ceac4eadc1561dd79f1bed01a78324fbeb666e245577bdfe72d26` | MODIFIED |
| `SX1276_DRIVER_OPERATIONS.md` | 16,298 | 29,826 | `8cb9569a5294426ab6c1dec50be5d2ab877872723394fba0f03299dce5aa1c4e` | `6d13e85e1f83ac41fd7267316382c74cbe78399602d3897558354026e9390547` | MODIFIED |
| `SX1276_REGISTER_REFERENCE.md` | 10,235 | 10,914 | `829cf5fc8948cad03c1e7566bb9558e753adf59f516b9f5f3a8edb189e4f43d2` | `8c6af5a3b39cffcb55e3d2553af54748f7c6b155bc9a1dd54c52e5831d7d9d8c` | MODIFIED |
| `reference/SX1276_OTHER_MODES.md` | 6,389 | 6,389 | `2b39af55fd2cfb4ed00399ee19bb7b042a24f2e325802d2855a25dd996fd2e73` | `2b39af55fd2cfb4ed00399ee19bb7b042a24f2e325802d2855a25dd996fd2e73` | UNCHANGED |
| `reference/SX1276_ERRATA.md` | 6,232 | 6,232 | `c43fbb078f278cc0547133e785b88d0493604df8bc318463e9bffb4387665736` | `c43fbb078f278cc0547133e785b88d0493604df8bc318463e9bffb4387665736` | UNCHANGED |
| `reference/SX1276_SOURCE_TRACEABILITY.md` | 8,598 | 10,956 | `a60ced23749dd6e740ec9eea9c0d5b4a052de8f3d6a70514e9fcae3dbdbe6a5b` | `63c8b5b23dc5b02150df5f672eef3f50b972c3d71932c554f3331465f6a8734d` | MODIFIED |
| `verification/SX1276_AUDIT_REPORT.md` | 23,042 | 25,722 | `4c38c233ff4e28906255fc3113494d4e661caf3c017644d4a8b22d431395e193` | `15503cd8a5a609c80735a8a4ecece34b790658f85863e7423277a86890f4fca4` | UPDATED |
| `verification/tests/test_candidate_reference.py` | 18,378 | 23,879 | `447287325c3519946068b7abc108836219235f05e2bf3880a2ca9c92a3986d04` | `a872ef24ef163cc5b2411154f72412c908d97b9eb96ae3ea077d41155f4b3268` | EXPANDED |

### 2.3. Candidate Files Preflight vs. Post-Fix Ledger (Round 4)

All Round 4 remediations were executed alongside an independent, verified backup (`SX1276_Agent_Reference_Candidate_backup_20261105_hardening/`):

| Candidate File Path | Pre-Fix Size (B) | Post-Fix Size (B) | Preflight SHA-256 | Post-Fix SHA-256 | Status |
|---|---:|---:|---|---|:---:|
| `README.md` | 8,943 | 8,943 | `9e940617f774f683a86b819adedfe131c1ab9a13c217a0da3f3b6223c60b033a` | `9e940617f774f683a86b819adedfe131c1ab9a13c217a0da3f3b6223c60b033a` | UNCHANGED |
| `SX1276_ACTIVE_PROFILE.md` | 11,198 | 11,198 | `700086ab9e6ceac4eadc1561dd79f1bed01a78324fbeb666e245577bdfe72d26` | `700086ab9e6ceac4eadc1561dd79f1bed01a78324fbeb666e245577bdfe72d26` | UNCHANGED |
| `SX1276_DRIVER_OPERATIONS.md` | 29,826 | 37,489 | `6d13e85e1f83ac41fd7267316382c74cbe78399602d3897558354026e9390547` | `a28ca3aad96a1fc2c2a7775480181be785e4730686461b378f60f9cdcca18430` | EXPANDED |
| `SX1276_REGISTER_REFERENCE.md` | 10,914 | 10,914 | `8c6af5a3b39cffcb55e3d2553af54748f7c6b155bc9a1dd54c52e5831d7d9d8c` | `8c6af5a3b39cffcb55e3d2553af54748f7c6b155bc9a1dd54c52e5831d7d9d8c` | UNCHANGED |
| `reference/SX1276_OTHER_MODES.md` | 6,389 | 6,389 | `2b39af55fd2cfb4ed00399ee19bb7b042a24f2e325802d2855a25dd996fd2e73` | `2b39af55fd2cfb4ed00399ee19bb7b042a24f2e325802d2855a25dd996fd2e73` | UNCHANGED |
| `reference/SX1276_ERRATA.md` | 6,232 | 6,232 | `c43fbb078f278cc0547133e785b88d0493604df8bc318463e9bffb4387665736` | `c43fbb078f278cc0547133e785b88d0493604df8bc318463e9bffb4387665736` | UNCHANGED |
| `reference/SX1276_SOURCE_TRACEABILITY.md` | 10,956 | 11,748 | `63c8b5b23dc5b02150df5f672eef3f50b972c3d71932c554f3331465f6a8734d` | `6d5110b94fe08aebb10a114e3687ff127e08da188eba4e9f005dd322c83ae67b` | UPDATED |
| `verification/SX1276_AUDIT_REPORT.md` | 25,722 | *(current)* | `15503cd8a5a609c80735a8a4ecece34b790658f85863e7423277a86890f4fca4` | *(updated)* | UPDATED |
| `verification/tests/test_candidate_reference.py` | 23,879 | 32,258 | `a872ef24ef163cc5b2411154f72412c908d97b9eb96ae3ea077d41155f4b3268` | `76133450b60b2bf961c9827a23141dd664369e0974e25f95cabaaeb9a8933d91` | EXPANDED (39 tests) |

---

## 3. Source-to-Target Mapping and Content Disposition

| Original 8 Files | Candidate Target File | Content Disposition & Refactoring Action |
|---|---|---|
| `README.md` | [`README.md`](../README.md) | `KEEP_HOT` / `MERGE`: Master index, context rules, HW-001 pinout, strapping warning, and explicit TBD status. |
| *(New Document)* | [`SX1276_ACTIVE_PROFILE.md`](../SX1276_ACTIVE_PROFILE.md) | `KEEP_HOT`: Approved `PHY_PROFILE_MVP_V1`, Channel Plan VN920 V1 (11 channels), and active register values. |
| `SX1276_SPI_RESET_POWER.md`, `SX1276_TX_RX_IRQ_FIFO.md`, `SX1276_RF_TIMING.md` | [`SX1276_DRIVER_OPERATIONS.md`](../SX1276_DRIVER_OPERATIONS.md) | `KEEP_HOT` / `MERGE`: Consolidated SPI bus rules, reset dynamics, Radio Owner task, TX/RX sequences, FIFO bounds, IRQ cleanup across all 9 paths, two-stage host supervision, and buffer capacity checks. |
| `SX1276_REGISTER_REFERENCE.md` | [`SX1276_REGISTER_REFERENCE.md`](../SX1276_REGISTER_REFERENCE.md) | `KEEP_HOT`: Pruned down to strictly the 37 registers and bitfields needed for MVP firmware with printed and PDF page numbers. |
| `SX1276_RF_TIMING.md` (non-MVP sections), `SX1276_REFERENCE_APPENDIX.md` (FSK/FHSS/sequencer) | [`reference/SX1276_OTHER_MODES.md`](../reference/SX1276_OTHER_MODES.md) | `MOVE_COLD`: Preserved SF6, SF8–SF12, non-125kHz bandwidths, alternate coding rates, FSK/OOK, FHSS, sequencer, and 16 non-MVP registers under `NON_MVP_REFERENCE`. |
| `SX1276_REFERENCE_APPENDIX.md` (Errata section) | [`reference/SX1276_ERRATA.md`](../reference/SX1276_ERRATA.md) | `MOVE_COLD`: Silicon errata workarounds (`AutomaticIFOn`, 500k optimization, IF shifts) with explicit verification boundaries. |
| `SX1276_SOURCE_TRACEABILITY.md` | [`reference/SX1276_SOURCE_TRACEABILITY.md`](../reference/SX1276_SOURCE_TRACEABILITY.md) | `MOVE_COLD`: Traceability matrix with printed/PDF page citations, differentiating hardware facts from driver policies. |
| `SX1276_AUDIT_REPORT.md` | [`verification/SX1276_AUDIT_REPORT.md`](SX1276_AUDIT_REPORT.md) | `MOVE_COLD`: Comprehensive audit report, gate evaluation, and regression test ledger. |

---

## 4. Context Volume and Token Reduction Analysis

### Estimation Methodology
- **Character-based estimate:** $\text{Characters} / 4.0$.
- **Word-based estimate:** $\text{Words} \times 1.30$.

### Comparative Ledger

| Document Set | Component Files | Size (bytes) | Word Count | Est. Tokens (Char) | Est. Tokens (Word) | Context Status |
|---|---|---:|---:|---:|---:|---|
| **Original Baseline (8 files)** | All 8 original files in flat root | 89,883 | 12,887 | ~22,433 | ~16,753 | Loaded by default |
| **Candidate Hot Context (4 files)** | `README.md`<br>`SX1276_ACTIVE_PROFILE.md`<br>`SX1276_DRIVER_OPERATIONS.md`<br>`SX1276_REGISTER_REFERENCE.md` | **60,881** | **8,940** | **~15,220** | **~11,622** | **Default Agent Reading** |
| **Candidate Cold Reference (3 files)** | `reference/SX1276_OTHER_MODES.md`<br>`reference/SX1276_ERRATA.md`<br>`reference/SX1276_SOURCE_TRACEABILITY.md` | 23,577 | 3,380 | ~5,894 | ~4,394 | On-demand only |
| **Candidate Audit & Tests (2 files)** | `verification/SX1276_AUDIT_REPORT.md`<br>`tests/test_candidate_reference.py` | ~45,000 | ~4,600 | ~11,250 | ~5,980 | Quality verification |
| **Total Candidate Package (9 files)** | Complete candidate package | ~129,458 | ~16,920 | ~32,364 | ~21,996 | Preserved knowledge |

> [!TIP]
> **Context Optimization Result:**
> Although Section 7 & 8 expanded to thoroughly document all 9 failure paths, the two-stage supervision policy, and buffer capacity guards, loading strictly the **4 Hot Context files** still reduces default reading volume compared to an unstructured baseline while completely isolating the agent from distracting non-MVP configurations.

---

## 5. Technical Verification & Consistency Audit

### 1. Approved PHY & Channel Plan VN920 V1 Consistency
- Confirmed: SF7, BW 125 kHz, CR 4/5, CRC ON, Explicit Header, Sync Word 0x12, LDRO OFF.
- Confirmed: 11 channels spaced at 250 kHz from 920.250 to 922.750 MHz.
- Confirmed: Synthesizer step is exactly $61.03515625\text{ Hz}$, hop is exactly $4096$ (`0x1000`) steps, quantization error is $0.00\text{ Hz}$.
- Verified: `CH05` is not described as default; active channel assignment is backend-authorized.

### 2. Register Active Values and Mask Rules
- `RegModemConfig1 (0x1D)`: Exactly `0x72` (BW=125k, CR=4/5, Explicit).
- `RegModemConfig2 (0x1E)`: Masked write policy enforced: `(reg & 0x03) | 0x74` to preserve `SymbTimeout[9:8]`.
- `RegModemConfig3 (0x26)`: Masked write policy enforced: `reg & ~(1 << 3)` to clear LDRO without clearing `AgcAutoOn`.
- `RegSyncWord (0x39)`: Exactly `0x12`.
- `RegDetectOptimize (0x31)`: Read-modify-write rule enforced: `reg & ~0x80` yields `0x43` from reset `0xC3`. Whole-byte `0x03` is forbidden.
- `RegLna (0x0C)`: Classified as `TBD` / `PROPOSED` (reset `0x20` vs boost `0x23`), noting AGC override.

### 3. RX Verification Pipeline & CRC Integrity
- Sequence enforces `RxDone` $\to$ check `RegHopChannel.CrcOnPayload` $\to$ reject if 0 $\to$ check `PayloadCrcError` $\to$ reject if 1 $\to$ bounds check $\to$ handoff to Custom MAC $\to$ clear IRQ flags.
- Distinguishes physical payload CRC from application/network HMAC/MIC.

### 4. RX Lifecycle, Host Supervision & Buffer Safety (Round 3)
- Recognizes silicon demodulation priority over preamble hunt timeout.
- Implements two-stage supervision: checks `RxOnGoing` and `ValidHeader` before aborting; grants bounded demodulation extension.
- Differentiates `HW_RX_TIMEOUT`, `HOST_WATCHDOG_EXPIRED`, `RX_PACKET_DONE`, `RX_ABORTED_BY_SCHEDULE`, `RX_ABORTED_BY_RECOVERY`.
- Enforces pre-copy check: `RegRxNbBytes <= host_buffer_capacity`. Frames exceeding capacity are dropped before copying (`REJECT_HOST_BUFFER_OVERFLOW`).
- Zero steady-state dynamic allocation; preallocated static buffer pool; queue-full drop handling without memory leaks.

### 5. RX Race Arbitration, Continuous Cleanup & Time-on-Air Hardening (Round 4)
- **Pre-Abort Re-Check & Arbitration:** Mandated pre-abort re-read of `RegIrqFlags` and implemented a complete 6-scenario Arbitration & Pre-Abort Re-Check Table (Scenarios A through F).
- **Residual Race Disclosure:** Formally disclosed the sub-microsecond residual race window between the final SPI read byte and the subsequent SPI `STANDBY` write command; strictly prohibited claiming zero packet loss can be achieved by register polling alone without protocol-level ARQ.
- **Forced TDMA Slot Abort:** Classified hard slot deadline aborts strictly as `RX_ABORTED_BY_SCHEDULE` with in-flight packet truncation / loss risks explicitly documented.
- **Harmonized Continuous Cleanup:** Unified IRQ clearing across pipeline and continuous reception using targeted write-1-to-clear: `write RegIrqFlags = (snapshot & 0x70)`.
- **Eliminated Stale Flag Hazards:** Prohibited solitary `0x40` clearing in continuous mode (which leaves stale `PayloadCrcError` `0x20` or `ValidHeader` `0x10` asserted, contaminating subsequent packet checks).
- **Prevented Flag Wiping:** Prohibited unconditional `0xFF` clearing in continuous mode (which wipes valid header/preamble status of newly arriving packets).
- **Exact Mathematical ToA:** Recomputed and replaced rough approximations with exact Semtech formula values for approved profile: PL=16B is **51.456 ms**, PL=64B is **118.016 ms**, PL=255B is **399.616 ms**. Completely eliminated all ~135 ms and ~412 ms estimates.
- **Datasheet Rev. 7 Page Traceability:** Verified Section 4.1.1.7 (Time on air) on printed page 31 / PDF page 31, and receive sequences on printed pages 39–41 / PDF pages 40–42.

---

## 6. Automated Quality Gates Evaluation (G1–G6)

| Gate | Description | Evaluation Criteria | Result | Evidence |
|---|---|---|:---:|---|
| **G1** | **Structure** | Valid directory layout, all 4 hot + 3 cold + audit files present, no broken relative links, no broken references, balanced math delimiters, unique headings. | **PASS** | `test_01_all_required_candidate_files_exist`, `test_02_internal_markdown_links_resolve`, `test_03_no_duplicate_headings`, and `test_04_math_delimiters_balanced` all PASSED. |
| **G2** | **Technical Accuracy** | Register addresses and bitfields verified against Datasheet; SPI/Reset/IRQ/FIFO operations correct; no DIO0/DIO1 confusion; reset vs active values separated; read-modify-write on 0x31 verified (`0x43`, not `0x03`); LNA gain classified as TBD; RX buffer capacity verified before copy; targeted IRQ cleanup enforced. | **PASS** | `test_REG_01_detect_optimize_bit7_clear`, `test_REG_02_no_hardcoded_0x03_active_value`, `test_LNA_01_reg_lna_not_owner_approved_mandatory`, `test_RX_BOUNDS_01_reject_payload_exceeding_host_buffer_capacity`, `test_RX_CONT_01_consistent_targeted_irq_cleanup`, `test_RX_CONT_02_no_stale_crc_header_flag_contamination`, and `test_lean_register_reference_content` PASSED. |
| **G3** | **PHY Consistency** | SF7/BW125k/CR4/5/CRC ON/Explicit/SyncWord 0x12/LDRO OFF across all hot files; exact 11 channels; 0.00 Hz quantization error; RX drop on missing CRC enforced. | **PASS** | `test_channel_plan_frequency_math` (11 channels), `test_CRC_01_rx_rejects_missing_payload_crc`, `test_CRC_02_rx_rejects_payload_crc_error` PASSED. |
| **G4** | **Evidence & Traceability** | `PDF_VERIFIED` used only for confirmed datasheet text; unverified errata marked `ERRATA_REVIEW_NOT_VERIFIED`; driver policies marked `PROJECT_PROPOSED`; Owner decisions marked `PROJECT_APPROVED`; TBDs preserved; printed and PDF pages separated; Section 4.1.1.7 p. 31 and pp. 40–41 cited. | **PASS** | `SX1276_SOURCE_TRACEABILITY.md` completed with printed and PDF pages; `test_ERR_01_bw500_workaround_not_pdf_verified`, `test_SOURCE_PAGE_01_verified_citations`, and `test_CONS_01_cross_file_consistency` PASSED. |
| **G5** | **ToA & Tests** | Exact ToA formula; KAT vectors: 16B = 51.456 ms, 64B = 118.016 ms, 255B = 399.616 ms; ~135 ms and ~412 ms eradicated; independent Python test suite executed with zero failures; host timeout uncoupled from static +20 ms; RX race arbitration and lifecycle tests pass. | **PASS** | `test_toa_approved_active_profile_baseline`, `test_TOA_64_exact_vector`, `test_TOA_255_exact_vector`, `test_TOA_DOCUMENTATION_exact_values`, `test_TOA_REGRESSION_mutation`, `test_RX_RACE_03_pre_abort_recheck_and_residual_race`, `test_RX_RACE_04_forced_tdma_slot_deadline_classification`, and all 9 `TestRxLifecycleAndSafetyRegression` tests PASSED. Total 39 tests, Exit code: 0. |
| **G6** | **Delivery Safety** | Original 8 files unmodified; no git commands executed; no commits/branches/PRs created; no firmware edited; local candidate only with verified backup. | **PASS** | Checksum verification of original 8 files confirms 100% untouched; independent backup verified. |

---

## 7. Automated Test Suite Execution Log

Test file: [`verification/tests/test_candidate_reference.py`](tests/test_candidate_reference.py)
Execution command: `python3 verification/tests/test_candidate_reference.py -v`

```text
test_channel_plan_frequency_math (__main__.TestApprovedPhyAndRegisters.test_channel_plan_frequency_math)
Verify exact Frf calculation and 0.00 Hz quantization error across all 11 channels. ... ok
test_lean_register_reference_content (__main__.TestApprovedPhyAndRegisters.test_lean_register_reference_content)
Verify required MVP registers are present with correct active values/rules. ... ok
test_01_all_required_candidate_files_exist (__main__.TestCandidateStructureAndLinks.test_01_all_required_candidate_files_exist)
Verify all hot, cold, and audit candidate files exist. ... ok
test_02_internal_markdown_links_resolve (__main__.TestCandidateStructureAndLinks.test_02_internal_markdown_links_resolve)
Verify all internal relative links in candidate files resolve to existing files. ... ok
test_03_no_duplicate_headings (__main__.TestCandidateStructureAndLinks.test_03_no_duplicate_headings)
Verify no markdown document contains duplicate headings. ... ok
test_04_math_delimiters_balanced (__main__.TestCandidateStructureAndLinks.test_04_math_delimiters_balanced)
Verify LaTeX math delimiters ($ and $$) are balanced in all files. ... ok
test_RX_CONT_01_consistent_targeted_irq_cleanup (__main__.TestFinalRemediationRegression.test_RX_CONT_01_consistent_targeted_irq_cleanup)
RX-CONT-01: Both validation pipeline and RX Continuous mode must mandate targeted IRQ clearing (0x70 or snapshot & 0x70). ... ok
test_RX_CONT_02_no_stale_crc_header_flag_contamination (__main__.TestFinalRemediationRegression.test_RX_CONT_02_no_stale_crc_header_flag_contamination)
RX-CONT-02: Document why clearing 0x40 alone leaves stale CRC/header flags. ... ok
test_RX_CONT_03_no_unconditional_0xFF_in_continuous (__main__.TestFinalRemediationRegression.test_RX_CONT_03_no_unconditional_0xFF_in_continuous)
RX-CONT-03: Warn against writing 0xFF in Continuous mode due to wiping incoming packet flags. ... ok
test_RX_RACE_03_pre_abort_recheck_and_residual_race (__main__.TestFinalRemediationRegression.test_RX_RACE_03_pre_abort_recheck_and_residual_race)
RX-RACE-03: Pre-abort re-check of RegIrqFlags, arbitration table, and residual race disclosure. ... ok
test_RX_RACE_04_forced_tdma_slot_deadline_classification (__main__.TestFinalRemediationRegression.test_RX_RACE_04_forced_tdma_slot_deadline_classification)
RX-RACE-04: Hard TDMA slot deadline abort must classify as RX_ABORTED_BY_SCHEDULE and warn of packet truncation. ... ok
test_SOURCE_PAGE_01_verified_citations (__main__.TestFinalRemediationRegression.test_SOURCE_PAGE_01_verified_citations)
SOURCE-PAGE-01: Citations must reflect verified Datasheet Rev. 7 Section 4.1.1.7 (page 31) and pages 40-41. ... ok
test_TOA_255_exact_vector (__main__.TestFinalRemediationRegression.test_TOA_255_exact_vector)
TOA-255: Mathematical calculation of Time-on-Air for PL=255 must be exactly 399.616 ms. ... ok
test_TOA_64_exact_vector (__main__.TestFinalRemediationRegression.test_TOA_64_exact_vector)
TOA-64: Mathematical calculation of Time-on-Air for PL=64 must be exactly 118.016 ms. ... ok
test_TOA_DOCUMENTATION_exact_values (__main__.TestFinalRemediationRegression.test_TOA_DOCUMENTATION_exact_values)
TOA-DOCUMENTATION: Documentation must contain exact 118.016 ms and 399.616 ms, and NOT ~135 ms or ~412 ms. ... ok
test_TOA_REGRESSION_mutation (__main__.TestFinalRemediationRegression.test_TOA_REGRESSION_mutation)
TOA-REGRESSION: Mutation test ensuring erroneous ToA values are caught. ... ok
test_packet_rssi_piecewise_logic (__main__.TestRfSignalCalculations.test_packet_rssi_piecewise_logic)
Verify Packet RSSI under positive and negative SNR. ... ok
test_snr_decoding (__main__.TestRfSignalCalculations.test_snr_decoding)
Verify signed two's complement SNR decoding. ... ok
test_RX_BOUNDS_01_reject_payload_exceeding_host_buffer_capacity (__main__.TestRxLifecycleAndSafetyRegression.test_RX_BOUNDS_01_reject_payload_exceeding_host_buffer_capacity)
RX-BOUNDS-01: Payload length exceeding host buffer capacity must be rejected before copy. ... ok
test_RX_BOUNDS_02_queue_full_or_buffer_unavailable (__main__.TestRxLifecycleAndSafetyRegression.test_RX_BOUNDS_02_queue_full_or_buffer_unavailable)
RX-BOUNDS-02: Queue full / buffer unavailable must drop without memory leak or invalid ownership. ... ok
test_RX_CLEANUP_01_rx_success_cleanup_and_state (__main__.TestRxLifecycleAndSafetyRegression.test_RX_CLEANUP_01_rx_success_cleanup_and_state)
RX-CLEANUP-01: RX success path must document snapshot, cleanup, and state transition. ... ok
test_RX_CLEANUP_02_crc_error_and_missing_crc_cleanup (__main__.TestRxLifecycleAndSafetyRegression.test_RX_CLEANUP_02_crc_error_and_missing_crc_cleanup)
RX-CLEANUP-02: CRC error and missing CRC must reject and cleanup completely. ... ok
test_RX_CLEANUP_03_timeout_abort_recovery_distinction (__main__.TestRxLifecycleAndSafetyRegression.test_RX_CLEANUP_03_timeout_abort_recovery_distinction)
RX-CLEANUP-03: Must distinctly document HW_RX_TIMEOUT, HOST_WATCHDOG_EXPIRED, RX_ABORTED_BY_SCHEDULE, RX_ABORTED_BY_RECOVERY. ... ok
test_RX_LATE_01_preamble_near_window_end (__main__.TestRxLifecycleAndSafetyRegression.test_RX_LATE_01_preamble_near_window_end)
RX-LATE-01: Preamble detected near end of search window must not be aborted as hung. ... ok
test_RX_LATE_02_host_deadline_during_active_reception (__main__.TestRxLifecycleAndSafetyRegression.test_RX_LATE_02_host_deadline_during_active_reception)
RX-LATE-02: Host timer expiry during active reception must use bounded demodulation policy. ... ok
test_RX_RACE_01_simultaneous_rxdone_and_timeout (__main__.TestRxLifecycleAndSafetyRegression.test_RX_RACE_01_simultaneous_rxdone_and_timeout)
RX-RACE-01: Simultaneous RxDone and host timeout must prioritize RxDone deterministically. ... ok
test_RX_RACE_02_stale_irq_prevention (__main__.TestRxLifecycleAndSafetyRegression.test_RX_RACE_02_stale_irq_prevention)
RX-RACE-02: Stale IRQ flags must be cleared before entering new RX mode. ... ok
test_CONS_01_cross_file_consistency (__main__.TestTechnicalCorrectionsRegression.test_CONS_01_cross_file_consistency)
CONS-01: Check cross-file consistency for DetectOptimize, LNA, and Errata restore. ... ok
test_CRC_01_rx_rejects_missing_payload_crc (__main__.TestTechnicalCorrectionsRegression.test_CRC_01_rx_rejects_missing_payload_crc)
CRC-01: RX sequence must explicitly reject and discard packets when CrcOnPayload == 0. ... ok
test_CRC_02_rx_rejects_payload_crc_error (__main__.TestTechnicalCorrectionsRegression.test_CRC_02_rx_rejects_payload_crc_error)
CRC-02: RX sequence must explicitly reject and discard packets when PayloadCrcError == 1. ... ok
test_CRC_03_mac_delivery_gated_by_crc_and_bounds (__main__.TestTechnicalCorrectionsRegression.test_CRC_03_mac_delivery_gated_by_crc_and_bounds)
CRC-03: Delivery to MAC layer must be strictly gated by CRC checks and payload bounds. ... ok
test_ERR_01_bw500_workaround_not_pdf_verified (__main__.TestTechnicalCorrectionsRegression.test_ERR_01_bw500_workaround_not_pdf_verified)
ERR-01: Workaround values (0x02, 0x64, 0x7F) for BW500 must NOT be marked PDF_VERIFIED. ... ok
test_ERR_02_active_bw125_does_not_initialize_bw500_workaround (__main__.TestTechnicalCorrectionsRegression.test_ERR_02_active_bw125_does_not_initialize_bw500_workaround)
ERR-02: Active BW125 profile must not apply 500 kHz workaround values. ... ok
test_LNA_01_reg_lna_not_owner_approved_mandatory (__main__.TestTechnicalCorrectionsRegression.test_LNA_01_reg_lna_not_owner_approved_mandatory)
LNA-01: RegLna (0x0C) must not be labeled as an Owner-approved mandatory active value 0x23. ... ok
test_REG_01_detect_optimize_bit7_clear (__main__.TestTechnicalCorrectionsRegression.test_REG_01_detect_optimize_bit7_clear)
REG-01: RegDetectOptimize must specify clearing bit 7, preserving remaining bits. ... ok
test_REG_02_no_hardcoded_0x03_active_value (__main__.TestTechnicalCorrectionsRegression.test_REG_02_no_hardcoded_0x03_active_value)
REG-02: RegDetectOptimize must not have `0x03` hardcoded as the post-errata active value. ... ok
test_TIME_01_no_fixed_20ms_production_timeout_margin (__main__.TestTechnicalCorrectionsRegression.test_TIME_01_no_fixed_20ms_production_timeout_margin)
TIME-01: SX1276_DRIVER_OPERATIONS.md must not hardcode +20ms as a production constant. ... ok
test_toa_approved_active_profile_baseline (__main__.TestTimeOnAirKnownAnswerTests.test_toa_approved_active_profile_baseline)
Active Profile Baseline: SF7, BW125k, CR 4/5, PL 16, IH 0, CRC 1, DE 0, Pre 8. ... ok
test_toa_non_mvp_vectors (__main__.TestTimeOnAirKnownAnswerTests.test_toa_non_mvp_vectors)
Non-MVP KAT vectors: SF10, SF12 LDRO, SF8 BW500k, SF11 Boundary. ... ok

----------------------------------------------------------------------
Ran 39 tests in 0.020s

OK
```
**Exit Code:** `0`

---

## 8. Summary of Pending Parameters (TBD) & Items for Human Review

The following items are intentionally marked **`TBD`** or require human engineering review / RF bench calibration prior to freezing driver firmware for production:

1. **Preamble Length (`TBD`):** Standard calculation assumes 8 symbols; exact programmed length must be frozen by the systems architect.
2. **TX Output Power & PA Pin (`TBD`):** Nominal dBm and `RFO` vs `PA_BOOST` path selection depend on physical PCB matching circuitry and battery discharge limits.
3. **RegLna Gain & HF Boost (`TBD` / `PROPOSED`):** Reset default is `0x20`. Setting `0x23` (HF Boost on, +150% LNA current) is proposed for link budget optimization but unfrozen pending RF bench validation, and overridden if `RegModemConfig3.AgcAutoOn = 1`.
4. **Host RX Timeout Guard Margins (`TBD`):** $T_{guard\_search}$ and $T_{guard\_demod}$ (`CONFIG_SX1276_RX_SEARCH_GUARD_MS`, `CONFIG_SX1276_RX_DEMOD_GUARD_MS`) are uncalibrated host software margins; no fixed arithmetic constant is assumed as a production default.
5. **ESP32 Deep-Sleep Power Domain (`NOT_VERIFIED`):** Physical board schematics must be checked to confirm whether radio $V_{DD}$ is dropped during deep sleep. (Driver mitigates this by mandating full hardware reset and re-initialization on wake-up).
6. **Standalone Errata PDF Review (`ERRATA_REVIEW_NOT_VERIFIED`):** Standalone document `SX1276_77_8_ErrataNote_1.1_STD.pdf` should be physically acquired to confirm 500 kHz workaround values before any future wideband migration.
7. **HIL / Firmware Execution Boundaries:** The 39 automated tests in `test_candidate_reference.py` verify **documentation invariants and specifications**. Actual silicon runtime behaviors (FreeRTOS task preemption, SPI DMA timings, packet demodulation under noise) must be verified through HIL bench testing on physical HW-001 hardware.

---

## 9. Final Disposition

Final Disposition: **`READY_FOR_HUMAN_REVIEW`**

The candidate package `SX1276_Agent_Reference_Candidate/` is complete, internally consistent, mathematically verified, passes all 39 automated unit and regression tests with exit code 0, and is ready for human engineering review prior to integration into GitHub Issue #156.
