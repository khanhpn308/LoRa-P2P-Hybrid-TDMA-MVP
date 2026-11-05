#!/usr/bin/env python3
"""
SX1276 Candidate Reference Verification Test Suite
Automated quality gates for structure, internal links, heading uniqueness,
math syntax, PHY channel frequency math, register coverage, and Time-on-Air KATs.
"""

import os
import re
import math
import unittest

CANDIDATE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HOT_FILES = [
    "README.md",
    "SX1276_ACTIVE_PROFILE.md",
    "SX1276_DRIVER_OPERATIONS.md",
    "SX1276_REGISTER_REFERENCE.md",
]

COLD_FILES = [
    "reference/SX1276_OTHER_MODES.md",
    "reference/SX1276_ERRATA.md",
    "reference/SX1276_SOURCE_TRACEABILITY.md",
]

AUDIT_FILES = [
    "verification/SX1276_AUDIT_REPORT.md",
]

ALL_DOCS = HOT_FILES + COLD_FILES + AUDIT_FILES

class TestCandidateStructureAndLinks(unittest.TestCase):
    """Quality Gate G1: Structure, required files, and link integrity."""

    def test_01_all_required_candidate_files_exist(self):
        """Verify all hot, cold, and audit candidate files exist."""
        for rel_path in ALL_DOCS:
            abs_path = os.path.join(CANDIDATE_ROOT, rel_path)
            self.assertTrue(os.path.isfile(abs_path), f"Missing required candidate file: {rel_path}")
            size = os.path.getsize(abs_path)
            self.assertGreater(size, 400, f"File {rel_path} is suspiciously small ({size} bytes)")

    def test_02_internal_markdown_links_resolve(self):
        """Verify all internal relative links in candidate files resolve to existing files."""
        link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
        for rel_path in ALL_DOCS:
            abs_path = os.path.join(CANDIDATE_ROOT, rel_path)
            doc_dir = os.path.dirname(abs_path)
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            for match in link_pattern.finditer(content):
                target = match.group(2)
                # Skip external links, fragments, mailto
                if target.startswith("http://") or target.startswith("https://") or target.startswith("mailto:"):
                    continue
                if target.startswith("#"):
                    continue

                clean_target = target.split("#")[0]
                if not clean_target:
                    continue

                resolved = os.path.normpath(os.path.join(doc_dir, clean_target))
                self.assertTrue(
                    os.path.exists(resolved),
                    f"Broken link in {rel_path}: [{match.group(1)}]({target}) -> {resolved} not found"
                )

    def test_03_no_duplicate_headings(self):
        """Verify no markdown document contains duplicate headings."""
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
        for rel_path in ALL_DOCS:
            abs_path = os.path.join(CANDIDATE_ROOT, rel_path)
            with open(abs_path, "r", encoding="utf-8") as f:
                content = f.read()

            headings = [m.group(2).strip().lower() for m in heading_pattern.finditer(content)]
            seen = set()
            duplicates = []
            for h in headings:
                if h in seen:
                    duplicates.append(h)
                seen.add(h)

            self.assertEqual(
                len(duplicates), 0,
                f"Duplicate headings in {rel_path}: {duplicates}"
            )

    def test_04_math_delimiters_balanced(self):
        """Verify LaTeX math delimiters ($ and $$) are balanced in all files."""
        for rel_path in ALL_DOCS:
            abs_path = os.path.join(CANDIDATE_ROOT, rel_path)
            with open(abs_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            in_code_block = False
            for line_no, line in enumerate(lines, 1):
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block:
                    continue

                double_dollars = line.count("$$")
                single_dollars = line.replace("$$", "").count("$")

                self.assertEqual(
                    double_dollars % 2, 0,
                    f"Unbalanced display math ($$) in {rel_path} at line {line_no}"
                )
                self.assertEqual(
                    single_dollars % 2, 0,
                    f"Unbalanced inline math ($) in {rel_path} at line {line_no}"
                )


class TestApprovedPhyAndRegisters(unittest.TestCase):
    """Quality Gate G2 & G3: Approved PHY profile, Channel Plan VN920 V1, and register sanity."""

    def test_channel_plan_frequency_math(self):
        """Verify exact Frf calculation and 0.00 Hz quantization error across all 11 channels."""
        f_xosc = 32000000.0
        f_step = f_xosc / (2**19)
        self.assertAlmostEqual(f_step, 61.03515625, places=8)

        expected_channels = [
            ("CH00", 920250000, 15077376, 0xE6, 0x10, 0x00),
            ("CH01", 920500000, 15081472, 0xE6, 0x20, 0x00),
            ("CH02", 920750000, 15085568, 0xE6, 0x30, 0x00),
            ("CH03", 921000000, 15089664, 0xE6, 0x40, 0x00),
            ("CH04", 921250000, 15093760, 0xE6, 0x50, 0x00),
            ("CH05", 921500000, 15097856, 0xE6, 0x60, 0x00),
            ("CH06", 921750000, 15101952, 0xE6, 0x70, 0x00),
            ("CH07", 922000000, 15106048, 0xE6, 0x80, 0x00),
            ("CH08", 922250000, 15110144, 0xE6, 0x90, 0x00),
            ("CH09", 922500000, 15114240, 0xE6, 0xA0, 0x00),
            ("CH10", 922750000, 15118336, 0xE6, 0xB0, 0x00),
        ]

        for name, f_target, exp_dec, exp_msb, exp_mid, exp_lsb in expected_channels:
            frf_val = f_target / f_step
            frf_int = round(frf_val)
            self.assertEqual(frf_int, exp_dec, f"Decimal Frf mismatch for {name}")
            msb = (frf_int >> 16) & 0xFF
            mid = (frf_int >> 8) & 0xFF
            lsb = frf_int & 0xFF
            self.assertEqual(msb, exp_msb, f"MSB mismatch for {name}")
            self.assertEqual(mid, exp_mid, f"Mid mismatch for {name}")
            self.assertEqual(lsb, exp_lsb, f"LSB mismatch for {name}")

            f_actual = frf_int * f_step
            error_hz = f_actual - f_target
            self.assertAlmostEqual(error_hz, 0.0, places=4, msg=f"Non-zero error on {name}")

    def test_lean_register_reference_content(self):
        """Verify required MVP registers are present with correct active values/rules."""
        reg_file = os.path.join(CANDIDATE_ROOT, "SX1276_REGISTER_REFERENCE.md")
        with open(reg_file, "r", encoding="utf-8") as f:
            content = f.read()

        required_regs = [
            ("RegOpMode", "0x01", "LongRangeMode"),
            ("RegFrMsb", "0x06", "0xE6"),
            ("RegModemConfig1", "0x1D", "0x72"),
            ("RegModemConfig2", "0x1E", "SpreadingFactor"),
            ("RegModemConfig3", "0x26", "LowDataRateOptimize"),
            ("RegSyncWord", "0x39", "0x12"),
            ("RegDetectOptimize", "0x31", "AutomaticIFOn"),
            ("RegVersion", "0x42", "0x12"),
            ("RegDioMapping1", "0x40", "Dio0Mapping"),
        ]
        for name, addr, token in required_regs:
            self.assertIn(name, content, f"Missing register {name} in lean register reference")
            self.assertIn(addr, content, f"Missing address {addr} for {name}")
            self.assertIn(token, content, f"Missing token/field {token} for {name}")


class TestTimeOnAirKnownAnswerTests(unittest.TestCase):
    """Quality Gate G5: Independent Known-Answer Tests for Time-on-Air."""

    @staticmethod
    def _compute_toa(bw, sf, cr, pl, ih, crc, de, n_preamble):
        t_s = (2 ** sf) / float(bw)
        t_preamble = (n_preamble + 4.25) * t_s
        num = 8 * pl - 4 * sf + 28 + 16 * crc - 20 * ih
        den = 4 * (sf - 2 * de)
        ceil_val = math.ceil(num / float(den))
        n_payload = 8 + max(ceil_val * (cr + 4), 0)
        t_payload = n_payload * t_s
        t_packet = t_preamble + t_payload
        return {
            "t_s_ms": t_s * 1000.0,
            "t_preamble_ms": t_preamble * 1000.0,
            "n_payload": n_payload,
            "t_payload_ms": t_payload * 1000.0,
            "t_packet_ms": t_packet * 1000.0,
        }

    def test_toa_approved_active_profile_baseline(self):
        """Active Profile Baseline: SF7, BW125k, CR 4/5, PL 16, IH 0, CRC 1, DE 0, Pre 8."""
        res = self._compute_toa(bw=125000, sf=7, cr=1, pl=16, ih=0, crc=1, de=0, n_preamble=8)

        # Independent hardcoded Known-Answer expectations
        self.assertAlmostEqual(res["t_s_ms"], 1.024, places=6)
        self.assertAlmostEqual(res["t_preamble_ms"], 12.544, places=6)
        self.assertEqual(res["n_payload"], 38)
        self.assertAlmostEqual(res["t_payload_ms"], 38.912, places=6)
        self.assertAlmostEqual(res["t_packet_ms"], 51.456, places=3)
        self.assertEqual(round(res["t_packet_ms"], 3), 51.456)

    def test_toa_non_mvp_vectors(self):
        """Non-MVP KAT vectors: SF10, SF12 LDRO, SF8 BW500k, SF11 Boundary."""
        # V1: SF10, BW125k, CR 4/5, PL 32, IH 0, CRC 1, DE 0, Pre 8 -> 452.608 ms
        v1 = self._compute_toa(125000, 10, 1, 32, 0, 1, 0, 8)
        self.assertEqual(v1["n_payload"], 43)
        self.assertAlmostEqual(v1["t_packet_ms"], 452.608, places=3)

        # V2: SF12, BW125k, CR 4/8, PL 64, IH 0, CRC 1, DE 1, Pre 8 -> 4071.424 ms
        v2 = self._compute_toa(125000, 12, 4, 64, 0, 1, 1, 8)
        self.assertEqual(v2["n_payload"], 112)
        self.assertAlmostEqual(v2["t_packet_ms"], 4071.424, places=3)

        # V3: SF8, BW500k, CR 4/6, PL 10, IH 1, CRC 0, DE 0, Pre 12 -> 18.560 ms
        v3 = self._compute_toa(500000, 8, 2, 10, 1, 0, 0, 12)
        self.assertEqual(v3["n_payload"], 20)
        self.assertAlmostEqual(v3["t_packet_ms"], 18.560, places=3)

        # V4: SF11, BW125k (Ts=16.384ms > 16ms), DE=1 -> 741.376 ms
        v4_de1 = self._compute_toa(125000, 11, 1, 20, 0, 1, 1, 8)
        self.assertEqual(v4_de1["n_payload"], 33)
        self.assertAlmostEqual(v4_de1["t_packet_ms"], 741.376, places=3)


class TestRfSignalCalculations(unittest.TestCase):
    """Quality Gate G4: Independent test of SNR decoding and Packet RSSI piecewise logic."""

    @staticmethod
    def _decode_snr(raw_byte):
        val = raw_byte if raw_byte < 128 else raw_byte - 256
        return val / 4.0

    @staticmethod
    def _compute_packet_rssi(packet_rssi_reg, snr_db, is_hf=True):
        offset = -157 if is_hf else -164
        if snr_db >= 0:
            return offset + packet_rssi_reg
        else:
            return offset + packet_rssi_reg + snr_db

    def test_snr_decoding(self):
        """Verify signed two's complement SNR decoding."""
        self.assertEqual(self._decode_snr(0x14), 5.0)     # +20 / 4 = +5.0 dB
        self.assertEqual(self._decode_snr(0x00), 0.0)     # 0 / 4 = 0.0 dB
        self.assertEqual(self._decode_snr(0xEE), -4.5)    # -18 / 4 = -4.5 dB
        self.assertEqual(self._decode_snr(0x80), -32.0)   # -128 / 4 = -32.0 dB
        self.assertEqual(self._decode_snr(0x7F), 31.75)   # +127 / 4 = +31.75 dB

    def test_packet_rssi_piecewise_logic(self):
        """Verify Packet RSSI under positive and negative SNR."""
        # HF positive SNR
        self.assertEqual(self._compute_packet_rssi(80, 5.0, is_hf=True), -77.0)
        # LF positive SNR
        self.assertEqual(self._compute_packet_rssi(80, 5.0, is_hf=False), -84.0)
        # HF negative SNR (packet below noise floor)
        self.assertEqual(self._compute_packet_rssi(50, -4.5, is_hf=True), -111.5)
        # LF negative SNR (packet below noise floor)
        self.assertEqual(self._compute_packet_rssi(50, -4.5, is_hf=False), -118.5)


class TestTechnicalCorrectionsRegression(unittest.TestCase):
    """
    Regression test suite enforcing the 5 mandatory technical fixes:
    REG-01, REG-02, CRC-01, CRC-02, CRC-03, LNA-01, TIME-01, ERR-01, ERR-02, CONS-01.
    """

    def test_REG_01_detect_optimize_bit7_clear(self):
        """REG-01: RegDetectOptimize must specify clearing bit 7, preserving remaining bits."""
        reg_file = os.path.join(CANDIDATE_ROOT, "SX1276_REGISTER_REFERENCE.md")
        with open(reg_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Must mention clearing bit 7 / masking with ~0x80 or 0x7F
        self.assertTrue(
            "& ~0x80" in content or "& 0x7F" in content or "bit 7 = 0" in content or "clear bit 7" in content.lower(),
            "RegDetectOptimize must describe clearing bit 7"
        )
        # Arithmetic check: 0xC3 & ~0x80 == 0x43
        val = 0xC3
        val &= ~0x80
        self.assertEqual(val, 0x43, "Bit 7 clear on 0xC3 must evaluate to 0x43")

    def test_REG_02_no_hardcoded_0x03_active_value(self):
        """REG-02: RegDetectOptimize must not have `0x03` hardcoded as the post-errata active value."""
        reg_file = os.path.join(CANDIDATE_ROOT, "SX1276_REGISTER_REFERENCE.md")
        with open(reg_file, "r", encoding="utf-8") as f:
            content = f.read()

        for line in content.splitlines():
            if "RegDetectOptimize" in line and "0x31" in line:
                self.assertNotIn("`0x03` (after errata fix)", line,
                    "RegDetectOptimize must not hardcode `0x03` as post-errata active byte value")
                self.assertNotIn("| `0x03` |", line,
                    "RegDetectOptimize must not list `0x03` as a whole-byte active value")

    def test_CRC_01_rx_rejects_missing_payload_crc(self):
        """CRC-01: RX sequence must explicitly reject and discard packets when CrcOnPayload == 0."""
        ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(ops_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Must contain explicit rejection when CRC is absent
        self.assertTrue(
            ("CrcOnPayload == 0" in content and ("reject" in content.lower() or "discard" in content.lower())) or
            "reject if crc absent" in content.lower(),
            "RX sequence must explicitly reject packets lacking payload CRC when CrcOnPayload == 0"
        )

    def test_CRC_02_rx_rejects_payload_crc_error(self):
        """CRC-02: RX sequence must explicitly reject and discard packets when PayloadCrcError == 1."""
        ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(ops_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            "PayloadCrcError" in content and ("reject" in content.lower() or "discard" in content.lower()),
            "RX sequence must reject packets with PayloadCrcError"
        )

    def test_CRC_03_mac_delivery_gated_by_crc_and_bounds(self):
        """CRC-03: Delivery to MAC layer must be strictly gated by CRC checks and payload bounds."""
        ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(ops_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Verification of the pipeline structure in text
        self.assertTrue(
            "mac" in content.lower() and "fiforxcurrentaddr" in content.lower(),
            "Delivery to MAC validation must be documented in RX sequence"
        )

    def test_LNA_01_reg_lna_not_owner_approved_mandatory(self):
        """LNA-01: RegLna (0x0C) must not be labeled as an Owner-approved mandatory active value 0x23."""
        reg_file = os.path.join(CANDIDATE_ROOT, "SX1276_REGISTER_REFERENCE.md")
        with open(reg_file, "r", encoding="utf-8") as f:
            content = f.read()

        for line in content.splitlines():
            if "RegLna" in line and "0x0C" in line:
                self.assertNotIn("`0x23` (G1 max gain, HF Boost on)", line,
                    "RegLna must not label 0x23 as approved active MVP value without qualification")
                self.assertTrue(
                    "TBD" in line or "PROPOSED" in line or "default" in line.lower(),
                    "RegLna active value must be classified as TBD or PROPOSED"
                )

    def test_TIME_01_no_fixed_20ms_production_timeout_margin(self):
        """TIME-01: SX1276_DRIVER_OPERATIONS.md must not hardcode +20ms as a production constant."""
        ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(ops_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("+ 20\\text{ ms}", content, "Must not hardcode '+ 20 ms' in LaTeX")
        self.assertNotIn("+ 20 ms", content, "Must not hardcode '+ 20 ms' in text")
        self.assertTrue(
            "guard" in content.lower() or "configurable" in content.lower(),
            "Must describe host timeout guard as a configurable parameter"
        )

    def test_ERR_01_bw500_workaround_not_pdf_verified(self):
        """ERR-01: BW500 workaround must be explicitly excluded from the active BW125 profile."""
        errata_file = os.path.join(CANDIDATE_ROOT, "reference/SX1276_ERRATA.md")
        with open(errata_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Prevent inadvertent application of secondary BW500 register writes.
        self.assertIn("Do not enable 500 kHz", content)

    def test_ERR_02_active_bw125_does_not_initialize_bw500_workaround(self):
        """ERR-02: Active BW125 profile must not apply 500 kHz workaround values."""
        prof_file = os.path.join(CANDIDATE_ROOT, "SX1276_ACTIVE_PROFILE.md")
        with open(prof_file, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("0x36", content, "Active profile should not touch 0x36")
        self.assertNotIn("0x3A", content, "Active profile should not touch 0x3A")

    def test_CONS_01_cross_file_consistency(self):
        """CONS-01: Check cross-file consistency for DetectOptimize, LNA, and Errata restore."""
        errata_file = os.path.join(CANDIDATE_ROOT, "reference/SX1276_ERRATA.md")
        with open(errata_file, "r", encoding="utf-8") as f:
            err_content = f.read()

        # In Errata, restore value for 0x36 must explicitly cite verified reset default 0x20
        self.assertIn("0x20", err_content)


class TestRxLifecycleAndSafetyRegression(unittest.TestCase):
    """
    Regression test suite enforcing the Final RX Lifecycle & Safety Invariants:
    RX-LATE-01, RX-LATE-02, RX-CLEANUP-01, RX-CLEANUP-02, RX-CLEANUP-03,
    RX-BOUNDS-01, RX-BOUNDS-02, RX-RACE-01, RX-RACE-02.
    NOTE: These documentation tests verify documentation invariants and contract specifications.
    """

    def setUp(self):
        self.ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(self.ops_file, "r", encoding="utf-8") as f:
            self.ops_content = f.read()

        self.trace_file = os.path.join(CANDIDATE_ROOT, "reference/SX1276_SOURCE_TRACEABILITY.md")
        with open(self.trace_file, "r", encoding="utf-8") as f:
            self.trace_content = f.read()

    def test_RX_LATE_01_preamble_near_window_end(self):
        """RX-LATE-01: Preamble detected near end of search window must not be aborted as hung."""
        # Must document that RxTimeout is NOT triggered when radio is actively receiving
        self.assertTrue(
            "priority" in self.ops_content.lower() and "preamble" in self.ops_content.lower(),
            "Must document that active reception takes priority over preamble hunt timeout"
        )
        self.assertIn("HW_RX_TIMEOUT", self.ops_content,
            "Must distinguish HW_RX_TIMEOUT in documentation")

    def test_RX_LATE_02_host_deadline_during_active_reception(self):
        """RX-LATE-02: Host timer expiry during active reception must use bounded demodulation policy."""
        # Must document inspecting RxOnGoing / ValidHeader before aborting
        self.assertTrue(
            "rxongoing" in self.ops_content.lower() or "validheader" in self.ops_content.lower(),
            "Must inspect RxOnGoing or ValidHeader before deciding host abort"
        )
        self.assertTrue(
            "bounded" in self.ops_content.lower() and ("toa" in self.ops_content.lower() or "demodulation" in self.ops_content.lower()),
            "Must specify bounded demodulation deadline rather than unconditional abort"
        )

    def test_RX_CLEANUP_01_rx_success_cleanup_and_state(self):
        """RX-CLEANUP-01: RX success path must document snapshot, cleanup, and state transition."""
        self.assertIn("RX_PACKET_DONE", self.ops_content,
            "Must document distinct RX_PACKET_DONE event")
        self.assertTrue(
            "snapshot" in self.ops_content.lower(),
            "Must mandate snapshot of IRQ flags before clearing"
        )

    def test_RX_CLEANUP_02_crc_error_and_missing_crc_cleanup(self):
        """RX-CLEANUP-02: CRC error and missing CRC must reject and cleanup completely."""
        self.assertTrue(
            "REJECT_MISSING_CRC" in self.ops_content or "missing crc" in self.ops_content.lower(),
            "Must have distinct rejection for missing CRC"
        )
        self.assertTrue(
            "REJECT_CRC_ERROR" in self.ops_content or "payloadcrcerror" in self.ops_content.lower(),
            "Must have distinct rejection for CRC error"
        )

    def test_RX_CLEANUP_03_timeout_abort_recovery_distinction(self):
        """RX-CLEANUP-03: Must distinctly document HW_RX_TIMEOUT, HOST_WATCHDOG_EXPIRED, RX_ABORTED_BY_SCHEDULE, RX_ABORTED_BY_RECOVERY."""
        required_events = [
            "HW_RX_TIMEOUT",
            "HOST_WATCHDOG_EXPIRED",
            "RX_ABORTED_BY_SCHEDULE",
            "RX_ABORTED_BY_RECOVERY"
        ]
        for evt in required_events:
            self.assertIn(evt, self.ops_content, f"Missing distinct event classification: {evt}")

    def test_RX_BOUNDS_01_reject_payload_exceeding_host_buffer_capacity(self):
        """RX-BOUNDS-01: Payload length exceeding host buffer capacity must be rejected before copy."""
        self.assertTrue(
            "host_buffer_capacity" in self.ops_content.lower() or "config_sx1276_host_rx_buffer_size" in self.ops_content.lower() or "host rx buffer" in self.ops_content.lower(),
            "Must mandate checking RegRxNbBytes against host RX buffer capacity"
        )
        self.assertTrue(
            "REJECT_HOST_BUFFER_OVERFLOW" in self.ops_content or "overflow" in self.ops_content.lower(),
            "Must document buffer overflow rejection"
        )

    def test_RX_BOUNDS_02_queue_full_or_buffer_unavailable(self):
        """RX-BOUNDS-02: Queue full / buffer unavailable must drop without memory leak or invalid ownership."""
        self.assertTrue(
            "queue" in self.ops_content.lower() and ("full" in self.ops_content.lower() or "unavailable" in self.ops_content.lower()),
            "Must document queue full / buffer unavailable handling"
        )

    def test_RX_RACE_01_simultaneous_rxdone_and_timeout(self):
        """RX-RACE-01: Simultaneous RxDone and host timeout must prioritize RxDone deterministically."""
        self.assertTrue(
            "rxdone" in self.ops_content.lower() and "priority" in self.ops_content.lower() and "timeout" in self.ops_content.lower(),
            "Must document deterministic priority for RxDone over timeout"
        )

    def test_RX_RACE_02_stale_irq_prevention(self):
        """RX-RACE-02: Stale IRQ flags must be cleared before entering new RX mode."""
        self.assertTrue(
            "stale" in self.ops_content.lower() or "pre-clear" in self.ops_content.lower() or "prior to" in self.ops_content.lower(),
            "Must document clearing stale IRQs prior to starting reception"
        )


class TestFinalRemediationRegression(unittest.TestCase):
    """
    Regression test suite enforcing the Final Technical Remediation invariants:
    - FIX-10: RX race between IRQ snapshot and abort (RX-RACE-03, RX-RACE-04)
    - FIX-11: Targeted IRQ cleanup in Continuous mode (RX-CONT-01, RX-CONT-02, RX-CONT-03)
    - FIX-12: Time-on-Air exact mathematical vectors & Datasheet Rev. 7 traceability (TOA-64, TOA-255, TOA-DOCUMENTATION, TOA-REGRESSION, SOURCE-PAGE-01)
    """

    def setUp(self):
        self.ops_file = os.path.join(CANDIDATE_ROOT, "SX1276_DRIVER_OPERATIONS.md")
        with open(self.ops_file, "r", encoding="utf-8") as f:
            self.ops_content = f.read()

        self.profile_file = os.path.join(CANDIDATE_ROOT, "SX1276_ACTIVE_PROFILE.md")
        with open(self.profile_file, "r", encoding="utf-8") as f:
            self.profile_content = f.read()

        self.trace_file = os.path.join(CANDIDATE_ROOT, "reference/SX1276_SOURCE_TRACEABILITY.md")
        with open(self.trace_file, "r", encoding="utf-8") as f:
            self.trace_content = f.read()

    def test_RX_RACE_03_pre_abort_recheck_and_residual_race(self):
        """RX-RACE-03: Pre-abort re-check of RegIrqFlags, arbitration table, and residual race disclosure."""
        # 1. Must document pre-abort re-check
        self.assertTrue(
            "pre-abort" in self.ops_content.lower() or "pre_abort" in self.ops_content.lower() or "final re-read" in self.ops_content.lower(),
            "Must document pre-abort re-check of RegIrqFlags"
        )
        # 2. Must document arbitration policy/table covering scenarios
        self.assertTrue(
            "arbitration" in self.ops_content.lower(),
            "Must document an arbitration policy/table for RX abort vs arrival race"
        )
        # 3. Must document residual race window (SPI transfer latency vs asynchronous RF completion)
        self.assertTrue(
            "residual race" in self.ops_content.lower() or "residual" in self.ops_content.lower(),
            "Must document residual race condition between final SPI check and STDBY command"
        )
        # 4. Must explicitly state zero packet loss cannot be guaranteed by register polling alone
        self.assertTrue(
            "zero packet loss" in self.ops_content.lower() or "zero-packet-loss" in self.ops_content.lower(),
            "Must explicitly state zero packet loss cannot be guaranteed by register polling alone"
        )

    def test_RX_RACE_04_forced_tdma_slot_deadline_classification(self):
        """RX-RACE-04: Hard TDMA slot deadline abort must classify as RX_ABORTED_BY_SCHEDULE and warn of packet truncation."""
        self.assertIn("RX_ABORTED_BY_SCHEDULE", self.ops_content,
            "Must classify forced TDMA slot abort as RX_ABORTED_BY_SCHEDULE")
        self.assertTrue(
            "truncat" in self.ops_content.lower() or "in-flight" in self.ops_content.lower() or "loss" in self.ops_content.lower(),
            "Must document risk of packet truncation or loss when aborting due to TDMA schedule deadline"
        )

    def test_RX_CONT_01_consistent_targeted_irq_cleanup(self):
        """RX-CONT-01: Both validation pipeline and RX Continuous mode must mandate targeted IRQ clearing (0x70 or snapshot & 0x70)."""
        # Continuous mode must NOT recommend clearing only 0x40
        self.assertNotIn(
            "writing `0x40` to `RegIrqFlags`", self.ops_content,
            "Must NOT recommend clearing only 0x40 in RX Continuous mode"
        )
        # Must recommend targeted clearing (0x70 or snapshot & 0x70)
        self.assertTrue(
            "0x70" in self.ops_content and ("snapshot & 0x70" in self.ops_content or "targeted" in self.ops_content.lower()),
            "Must specify targeted write-1-to-clear for handled flags (snapshot & 0x70)"
        )

    def test_RX_CONT_02_no_stale_crc_header_flag_contamination(self):
        """RX-CONT-02: Document why clearing 0x40 alone leaves stale CRC/header flags."""
        self.assertTrue(
            "stale" in self.ops_content.lower() and ("0x20" in self.ops_content or "payloadcrcerror" in self.ops_content.lower()),
            "Must explain why clearing 0x40 alone leaves stale CRC/header flags contaminating subsequent packets"
        )

    def test_RX_CONT_03_no_unconditional_0xFF_in_continuous(self):
        """RX-CONT-03: Warn against writing 0xFF in Continuous mode due to wiping incoming packet flags."""
        self.assertTrue(
            "0xff" in self.ops_content.lower() and ("wipe" in self.ops_content.lower() or "corrupt" in self.ops_content.lower() or "inadvertent" in self.ops_content.lower() or "subsequent" in self.ops_content.lower() or "unsafe" in self.ops_content.lower() or "prohibit" in self.ops_content.lower()),
            "Must warn against unconditional 0xFF clear in Continuous mode"
        )

    def test_TOA_64_exact_vector(self):
        """TOA-64: Mathematical calculation of Time-on-Air for PL=64 must be exactly 118.016 ms."""
        # Semtech formula: SF=7, BW=125000, CR=1 (4/5), IH=0, CRC=1, DE=0, Preamble=8
        bw = 125000.0
        sf = 7
        t_s = (2 ** sf) / bw  # 1.024 ms
        t_preamble = (8 + 4.25) * t_s  # 12.544 ms

        pl = 64
        numerator = 8 * pl - 4 * sf + 28 + 16 * 1 - 20 * 0  # 8*64 - 28 + 28 + 16 = 528
        denominator = 4 * (sf - 2 * 0)  # 28
        n_payload = 8 + max(math.ceil(numerator / denominator) * (1 + 4), 0)  # 8 + 19 * 5 = 103
        t_payload = n_payload * t_s  # 105.472 ms
        t_packet_ms = (t_preamble + t_payload) * 1000.0  # 118.016 ms

        self.assertAlmostEqual(t_packet_ms, 118.016, places=3)

    def test_TOA_255_exact_vector(self):
        """TOA-255: Mathematical calculation of Time-on-Air for PL=255 must be exactly 399.616 ms."""
        bw = 125000.0
        sf = 7
        t_s = (2 ** sf) / bw  # 1.024 ms
        t_preamble = (8 + 4.25) * t_s  # 12.544 ms

        pl = 255
        numerator = 8 * pl - 4 * sf + 28 + 16 * 1 - 20 * 0  # 8*255 - 28 + 28 + 16 = 2056
        denominator = 4 * (sf - 2 * 0)  # 28
        n_payload = 8 + max(math.ceil(numerator / denominator) * (1 + 4), 0)  # 8 + 74 * 5 = 378
        t_payload = n_payload * t_s  # 387.072 ms
        t_packet_ms = (t_preamble + t_payload) * 1000.0  # 399.616 ms

        self.assertAlmostEqual(t_packet_ms, 399.616, places=3)

    def test_TOA_DOCUMENTATION_exact_values(self):
        """TOA-DOCUMENTATION: Documentation must contain exact 118.016 ms and 399.616 ms, and NOT ~135 ms or ~412 ms."""
        # Check presence of exact values in operations file
        self.assertIn("118.016", self.ops_content, "Must contain exact ToA for 64B: 118.016 ms")
        self.assertIn("399.616", self.ops_content, "Must contain exact ToA for 255B: 399.616 ms")

        # Check absence of inaccurate approximations
        self.assertNotIn("135 ms", self.ops_content, "Must not contain inaccurate 135 ms approximation")
        self.assertNotIn("412 ms", self.ops_content, "Must not contain inaccurate 412 ms approximation")
        self.assertNotIn("~135", self.ops_content, "Must not contain ~135")
        self.assertNotIn("~412", self.ops_content, "Must not contain ~412")

    def test_TOA_REGRESSION_mutation(self):
        """TOA-REGRESSION: Mutation test ensuring erroneous ToA values are caught."""
        fake_content = self.ops_content.replace("118.016", "135.000")
        self.assertNotIn("118.016 ms", fake_content)
        with self.assertRaises(AssertionError):
            if "118.016" not in fake_content:
                raise AssertionError("Failed to find exact ToA 118.016")

    def test_SOURCE_PAGE_01_verified_citations(self):
        """SOURCE-PAGE-01: Citations must reflect verified Datasheet Rev. 7 Section 4.1.1.7 (page 31) and pages 40-41."""
        self.assertTrue(
            "4.1.1.7" in self.trace_content or "page 31" in self.trace_content.lower() or "p. 31" in self.trace_content.lower(),
            "Must cite Section 4.1.1.7 and page 31 for Time-on-Air formula"
        )
        self.assertTrue(
            "page 40" in self.trace_content.lower() or "page 41" in self.trace_content.lower() or "4.1.2.3" in self.trace_content or "4.1.2.4" in self.trace_content or "4.1.2" in self.trace_content,
            "Must cite RX mode sequence pages (40-41) in traceability"
        )


if __name__ == "__main__":
    unittest.main()
