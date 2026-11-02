#!/usr/bin/env python3
"""PROPOSED J01/J02 Python reference only. No Owner approval, C↔Go, HIL or G2 PASS.

python3 -m unittest discover -s tests/contract -p 'test_bootstrap_join_j02_proposed.py' -v
"""
import hashlib
import hmac
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "contracts/radio-mac/test-vectors/bootstrap-join-j02-proposed.json"


def hmac16(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()[:16]


def expand32(prk: bytes, info: bytes) -> bytes:
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


class ProposedJ01J02Reference(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.i = {k: (v.encode("ascii") if k == "RF_PLAN_ID" else bytes.fromhex(v))
                 for k, v in cls.f["input"].items()}
        cls.e = {k: bytes.fromhex(v) for k, v in cls.f["expected"].items()}

    def test_not_approved(self):
        self.assertIn("PROPOSED_ONLY", self.f["status"])
        self.assertIn("C_GO_NOT_VERIFIED", self.f["status"])
        self.assertEqual(len(self.f["negative_cases"]), 7)

    def test_target_request_accept_confirm(self):
        i, expected = self.i, self.e
        self.assertEqual(i["RELAY_GW_ID"], i["TARGET_GW_ID"])
        mac, counter, random, plan = (i[k] for k in
                                     ("DEVICE_MAC", "JOIN_COUNTER_BE", "JOIN_RANDOM", "RF_PLAN_ID"))
        prk = hmac.new(b"LP2P/JOIN/V1/SALT", i["K_JOIN"], hashlib.sha256).digest()
        req_key = expand32(prk, b"LP2P/JOIN/V1/K-REQ" + mac)
        dl_key = expand32(prk, b"LP2P/JOIN/V1/K-ASN-DL" + mac)
        req_prefix = b"\x22" + mac + counter + random
        m_up = b"LP2P/JOIN/V1/M-REQ" + req_prefix + i["RELAY_GW_ID"] + plan
        req = req_prefix + hmac16(req_key, m_up)
        self.assertEqual(req[0], 0x22)

        accept_head = (b"\x24" + random[:2] + i["TARGET_GW_ID"]
                       + i["NODE_ID"] + i["KEY_ID"])
        m_accept = (b"LP2P/JOIN/V1/M-ACCEPT" + accept_head + mac + counter
                    + random + i["RELAY_GW_ID"] + plan)
        accept_tag = hmac16(dl_key, m_accept)
        accept = accept_head + accept_tag

        context = (mac + i["TARGET_GW_ID"] + i["NODE_ID"] + i["KEY_ID"] +
                   counter + random + plan)
        session_up = expand32(prk, b"LP2P/JOIN/V1/SESSION-UP" + context)
        session_dl = expand32(prk, b"LP2P/JOIN/V1/SESSION-DL" + context)
        confirm_key = expand32(prk, b"LP2P/JOIN/V1/SESSION-CONFIRM" + context)
        confirm_prefix = b"\x25" + i["NODE_ID"] + i["KEY_ID"]
        m_confirm = b"LP2P/JOIN/V1/M-CONFIRM" + confirm_prefix + context + accept
        confirm = confirm_prefix + hmac16(confirm_key, m_confirm)
        outputs = {
            "PRK": prk, "K_JOIN_REQ": req_key, "K_JOIN_ASSIGN_DL": dl_key,
            "M_UP": m_up, "JOIN_PROOF": req[-16:], "UP_JOIN_REQUEST": req,
            "ACCEPT_HEAD": accept_head, "M_ACCEPT": m_accept,
            "AUTH_TAG": accept_tag, "DOWN_JOIN_ACCEPT": accept,
            "SESSION_CONTEXT": context, "K_SESSION_UP": session_up,
            "K_SESSION_DL": session_dl, "K_JOIN_CONFIRM": confirm_key,
            "M_CONFIRM": m_confirm, "UP_JOIN_CONFIRM": confirm
        }
        for field, value in outputs.items():
            with self.subTest(field=field):
                self.assertEqual(value, expected[field])
        for key, size in (
            ("M_UP", 49), ("UP_JOIN_REQUEST", 35), ("ACCEPT_HEAD", 6),
            ("M_ACCEPT", 57), ("DOWN_JOIN_ACCEPT", 22),
            ("SESSION_CONTEXT", 32), ("M_CONFIRM", 79), ("UP_JOIN_CONFIRM", 19)
        ):
            self.assertEqual(len(outputs[key]), size, key)

    def test_auth_tampering_and_wrong_gateway(self):
        i, e = self.i, self.e
        good = e["M_ACCEPT"]
        good_tag = e["AUTH_TAG"]
        key = e["K_JOIN_ASSIGN_DL"]
        self.assertTrue(hmac.compare_digest(hmac16(key, good), good_tag))
        for idx in (0, 21, 21 + 4, len(good) - 12):
            altered = bytearray(good)
            altered[idx] ^= 1
            self.assertFalse(hmac.compare_digest(hmac16(key, altered), good_tag))
        wrong_relay = (b"LP2P/JOIN/V1/M-ACCEPT" + e["ACCEPT_HEAD"]
                       + i["DEVICE_MAC"] + i["JOIN_COUNTER_BE"]
                       + i["JOIN_RANDOM"] + b"\x07" + i["RF_PLAN_ID"])
        self.assertFalse(hmac.compare_digest(hmac16(key, wrong_relay), good_tag))

        # Backend expects authenticated raw 22B Accept exactly in Confirm transcript.
        original_confirm_mac = hmac16(e["K_JOIN_CONFIRM"], e["M_CONFIRM"])
        tampered = e["M_CONFIRM"][:-1] + bytes([e["M_CONFIRM"][-1] ^ 1])
        self.assertNotEqual(original_confirm_mac, hmac16(e["K_JOIN_CONFIRM"], tampered))

    def test_replay_requires_state_not_vector(self):
        state_only = [case for case in self.f["negative_cases"]
                      if "BACKEND_STATE" in case["expected"] or "DENY_TX" in case["expected"]]
        self.assertEqual(len(state_only), 2)
        self.assertTrue(all(len(case["test"]) > 10 for case in state_only))


if __name__ == "__main__":
    unittest.main()
