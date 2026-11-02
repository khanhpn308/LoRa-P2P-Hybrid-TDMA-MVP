#!/usr/bin/env python3
"""Design-to-Contract structural checks for RF Bootstrap Join v1.

Run: python3 -m unittest discover -s tests/contract -p 'test_bootstrap_join_contract.py' -v
No external packages required. Not a crypto Golden Vector or G2/HIL verification.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "contracts" / "radio-mac" / "test-vectors" / "bootstrap-join-structural.json"


def classify(frame, sample):
    data = bytes.fromhex(sample)
    if len(data) != frame["size"]:
        return "REJECT_BAD_LENGTH"
    proto_ver = data[0] >> 5
    packet_type = data[0] & 0x1F
    if proto_ver != 1:
        return "REJECT_BAD_VERSION"
    if packet_type in (0, 31):
        return "REJECT_RESERVED_TYPE"
    if data[0] != int(frame["type_byte"], 16):
        return "REJECT_WRONG_TYPE"
    return "HEADER_OK_AUTH_UNVERIFIED"


class BootstrapJoinContractStructuralTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(PATH.read_text(encoding="utf-8"))
        cls.frames = {f["name"]: f for f in cls.doc["frames"]}

    def test_frame_offsets_and_lengths(self):
        for frame in self.frames.values():
            with self.subTest(frame=frame["name"]):
                offset = 0
                for field_name, declared_offset, width in frame["fields"]:
                    self.assertEqual(declared_offset, offset, field_name)
                    self.assertGreater(width, 0)
                    offset += width
                self.assertEqual(offset, frame["size"])
                self.assertEqual(frame["fields"][0][0], "VER_TYPE")
                self.assertEqual(frame["fields"][-1][2], 16)

    def test_owner_approval_not_inferred_for_join_request(self):
        self.assertEqual(self.frames["UP_JOIN_REQUEST"]["status"], "CANDIDATE")
        for name in ("DOWN_JOIN_ASSIGNMENT", "DOWN_JOIN_ACCEPT", "UP_JOIN_CONFIRM"):
            self.assertEqual(self.frames[name]["status"], "OWNER_APPROVED_DESIGN")

    def test_exact_static_frame_cases(self):
        self.assertEqual(len(self.doc["cases"]), 8)
        for case in self.doc["cases"]:
            with self.subTest(case=case["case_id"]):
                self.assertEqual(classify(self.frames[case["frame"]], case["wire_hex"]),
                                 case["expected_static"])
                self.assertEqual(len(case["wire_hex"]) % 2, 0)

    def test_request_ref_and_frequency_offset(self):
        f = self.doc["fixture_values"]
        self.assertEqual(f["join_random"][:4], f["request_ref"])
        self.assertEqual(920000000 + 1000 * int(f["freq_offset_khz_be"], 16),
                         921400000)
        self.assertEqual(int(f["join_counter_be"], 16), 0x0123)

    def test_session_context_exactly_32_bytes(self):
        f = self.doc["fixture_values"]
        expected = (f["device_mac"] + f["target_gw_id"] + f["node_id"]
                    + f["key_id"] + f["join_counter_be"] + f["join_random"]
                    + f["rf_plan_ascii_hex"])
        self.assertEqual(f["session_context_hex"], expected)
        self.assertEqual(bytes.fromhex(expected)[-11:], b"RF-VN920-V1")
        self.assertEqual(len(bytes.fromhex(expected)), 32)

    def test_not_cryptographically_verified(self):
        self.assertIn("NOT_IMPLEMENTATION_READY", self.doc["contract_status"])
        for case in self.doc["cases"]:
            self.assertNotEqual(case["expected_static"], "AUTH_ACCEPT")
            if case["expected_static"] == "HEADER_OK_AUTH_UNVERIFIED":
                self.assertTrue(case["wire_hex"].endswith("00" * 16),
                                "Placeholder tag must never be mistaken for valid HMAC")


if __name__ == "__main__":
    unittest.main()
