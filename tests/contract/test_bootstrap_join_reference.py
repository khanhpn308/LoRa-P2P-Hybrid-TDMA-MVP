#!/usr/bin/env python3
"""Owner-approved HKDF/HMAC byte-transcript Python REFERENCE checks.

Run: python3 -m unittest discover -s tests/contract -p 'test_bootstrap_join_*.py' -v
This does NOT constitute independent C↔Go interoperability, M_ACCEPT completion, G2 security approval, or RF/HIL PASS.
Only synthetic K_JOIN 00..1f is used.
"""
import hashlib
import hmac
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "contracts" / "radio-mac" / "test-vectors" / "bootstrap-join-python-reference.json"


def raw(hexstr):
    return bytes.fromhex(hexstr)


def hkdf_expand32(prk, info):
    # RFC 5869 HKDF-Expand, L=32 <= hash length: one block, counter byte 0x01.
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()


def tag16(key, msg):
    return hmac.new(key, msg, hashlib.sha256).digest()[:16]


class BootstrapJoinPythonReferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.fields = cls.fixture["input"]
        cls.expected = cls.fixture["expected"]

    def test_reference_only_status(self):
        self.assertEqual(self.fixture["status"], "PYTHON_REFERENCE_ONLY_C_GO_NOT_VERIFIED")
        self.assertEqual(len(self.fixture["withheld"]), 2)

    def test_crypto_derived_bytes(self):
        f, exp = self.fields, self.expected
        device = raw(f["DEVICE_MAC"])
        ctr = raw(f["JOIN_COUNTER_BE"])
        rnd = raw(f["JOIN_RANDOM"])
        relay = raw(f["RELAY_GW_ID"])
        plan = f["RF_PLAN_ID_ASCII"].encode("ascii")
        prk = hmac.new(b"LP2P/JOIN/V1/SALT", raw(f["K_JOIN"]), hashlib.sha256).digest()
        req_key = hkdf_expand32(prk, b"LP2P/JOIN/V1/K-REQ" + device)
        dl_key = hkdf_expand32(prk, b"LP2P/JOIN/V1/K-ASN-DL" + device)
        context = (device + raw(f["TARGET_GW_ID"]) + raw(f["NODE_ID"]) +
                   raw(f["KEY_ID"]) + ctr + rnd + plan)
        m_up = b"LP2P/JOIN/V1/M-REQ" + b"\x22" + device + ctr + rnd + relay + plan
        asn_first7 = (b"\x23" + rnd[:2] + raw(f["TARGET_GW_ID"]) +
                      raw(f["FREQ_OFFSET_KHZ_BE"]) + raw(f["PHY_PROFILE_ID"]))
        m_dl = b"LP2P/JOIN/V1/M-ASN" + asn_first7 + device + ctr + rnd + relay + plan

        actual = {
            "PRK": prk, "K_JOIN_REQ": req_key, "K_JOIN_ASSIGN_DL": dl_key,
            "M_UP": m_up, "M_DL": m_dl, "JOIN_PROOF": tag16(req_key, m_up),
            "ASSIGNMENT_AUTH_TAG": tag16(dl_key, m_dl),
            "SESSION_CONTEXT": context,
            "K_SESSION_UP": hkdf_expand32(prk, b"LP2P/JOIN/V1/SESSION-UP" + context),
            "K_SESSION_DL": hkdf_expand32(prk, b"LP2P/JOIN/V1/SESSION-DL" + context),
            "K_JOIN_CONFIRM": hkdf_expand32(prk, b"LP2P/JOIN/V1/SESSION-CONFIRM" + context),
        }
        self.assertEqual(len(m_up), 49)
        self.assertEqual(len(m_dl), 55)
        self.assertEqual(len(context), 32)
        for name, val in actual.items():
            with self.subTest(field=name):
                self.assertEqual(val.hex(), exp[name])
        self.assertEqual((b"\x22" + device + ctr + rnd + actual["JOIN_PROOF"]).hex(),
                         self.fixture["examples"]["UP_JOIN_REQUEST_35B_CANDIDATE"])
        self.assertEqual((asn_first7 + actual["ASSIGNMENT_AUTH_TAG"]).hex(),
                         self.fixture["examples"]["DOWN_JOIN_ASSIGNMENT_23B_OWNER_APPROVED_DESIGN"])
        # Header mutation must change the authentication transcript and tag.
        mutated = m_up[:18] + b"\x23" + m_up[19:]
        self.assertNotEqual(tag16(req_key, mutated), actual["JOIN_PROOF"])


if __name__ == "__main__":
    unittest.main()
