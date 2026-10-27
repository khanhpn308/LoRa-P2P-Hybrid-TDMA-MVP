"""Operator-signed Issue-grant tests; local synthetic fixtures, no root or live GitHub."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/agent_harness"))
from mcp_approval import ApprovalAuthority, _ACTIONS, canonical, _strict_json
try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
except ImportError:
    Ed25519PrivateKey = None
    serialization = None


@unittest.skipIf(Ed25519PrivateKey is None, "MCP signer cryptography SDK not installed in core test environment")
class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "authority"
        self.root.mkdir(mode=0o755)
        self.grants = self.root / "approvals"
        self.grants.mkdir(mode=0o755)
        self.key = Ed25519PrivateKey.generate()
        pub = self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        (self.root/"public.pem").write_bytes(pub)
        (self.root/"public.pem").chmod(0o644)
        self.auth = ApprovalAuthority(self.root, test_owner=os.getuid())
        self.base = "a"*40
        self.body = hashlib.sha256(b"Issue acceptance criteria").hexdigest()
        self.scope = ["docs/development/sample.md"]
        now = int(time.time())
        self.grant = {"version": 1, "grant_id": uuid.uuid4().hex, "issue": 83,
                      "base_sha": self.base, "issue_sha256": self.body,
                      "scope": self.scope[:], "issued_at": now,
                      "expires_at": now + 1800, "actions": list(_ACTIONS)}
        self.path = self.grants / "issue-83.json"
        self.write()

    def write(self):
        envelope = {"grant": self.grant, "signature": self.key.sign(canonical(self.grant)).hex()}
        self.path.write_bytes(canonical(envelope))
        self.path.chmod(0o644)

    def valid(self, **kw):
        params = dict(issue=83, base_sha=self.base, issue_sha256=self.body,
                      scope=self.scope, action="prepare")
        params.update(kw)
        return self.auth.verify(**params)

    def test_exact_signature_and_pins(self):
        value = self.valid()
        self.assertEqual(value["issue"], 83)
        self.assertEqual(value["grant_id"], self.grant["grant_id"])

    def test_invalid_issue_source_hash_scope_and_id(self):
        for modified in (dict(issue=84), dict(base_sha="b"*40),
                         dict(issue_sha256="b"*64), dict(scope=["firmware/"]),
                         dict(expected_id="0"*32)):
            with self.assertRaises(ValueError):
                self.valid(**modified)

    def test_tampered_valid_json_invalidates_signature(self):
        envelope = json.loads(self.path.read_text())
        envelope["grant"]["issue"] = 84
        self.path.write_text(json.dumps(envelope))
        with self.assertRaises(ValueError):
            self.valid()

    def test_expired_and_overlong_grants_fail(self):
        self.grant["expires_at"] = int(time.time()) - 1
        self.write()
        with self.assertRaises(ValueError):
            self.valid()
        self.grant["expires_at"] = int(time.time()) + 9*3600
        self.write()
        with self.assertRaises(ValueError):
            self.valid()

    def test_duplicate_json_keys_and_nan_fail(self):
        for raw in (b'{"grant":{},"grant":{},"signature":""}',
                    b'{"grant":NaN,"signature":""}'):
            with self.assertRaises(ValueError):
                _strict_json(raw)

    def test_missing_grant_has_validation_error_not_uncaught_file_not_found(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "Required approval path unavailable"):
            self.valid()

    def test_grant_symlink_rejected(self):
        self.path.unlink()
        self.path.symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.valid()

    def test_wrong_owner_or_writable_modes_fail(self):
        self.path.chmod(0o666)
        with self.assertRaises(ValueError):
            self.valid()
        self.path.chmod(0o644)
        self.grants.chmod(0o777)
        with self.assertRaises(ValueError):
            self.valid()

    def test_unsigned_or_different_key_rejected(self):
        other = Ed25519PrivateKey.generate()
        self.path.write_bytes(canonical({"grant": self.grant,
                                         "signature": other.sign(canonical(self.grant)).hex()}))
        with self.assertRaises(ValueError):
            self.valid()

    def test_bad_contract_action_and_no_permission_hint(self):
        for extra in ({"actions": ["prepare"]}, {"version": 9}, {"grant_id": "bad"}):
            self.grant.update(extra)
            self.write()
            with self.assertRaises(ValueError):
                self.valid()
        self.assertNotIn("LORA_HARNESS_MUTATIONS", self.grant)


if __name__ == "__main__":
    unittest.main()
