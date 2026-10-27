"""Approval request creation tests: use mock live Host preflight; no Github/root access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/agent_harness"))

from mcp_approval import _read_untrusted_request, validate_request
from mcp_approval_request import ApprovalRequestMaker


class ApprovalRequestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name) / "approval-requests"
        self.host = Mock()
        self.preview = {
            "state": "PREFLIGHT_ONLY", "issue": 83,
            "source_sha": "a"*40, "issue_sha256": "b"*64,
            "approved_scope": ["docs/example.md", "tests/agent_harness/"],
        }
        self.host.preflight.return_value = self.preview
        self.maker = ApprovalRequestMaker(self.host, self.directory)

    def test_nonprivileged_request_has_exact_signed_grant_inputs(self):
        result = self.maker.create(83)
        self.assertEqual(result["status"], "APPROVAL_REQUIRED", result)
        path = Path(result["request_file"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.directory.stat().st_mode & 0o777, 0o700)
        payload = _read_untrusted_request(path)
        self.assertEqual(payload["issue"], 83)
        self.assertEqual(payload["base_sha"], "a"*40)
        self.assertEqual(payload["issue_sha256"], "b"*64)
        self.assertEqual(payload["scope"], self.preview["approved_scope"])
        self.assertEqual(payload["repository"], "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP")
        self.assertIn("approve --request ", result["operator_command"])
        self.assertNotIn("auth login", result["operator_command"])
        self.host.preflight.assert_called_once_with(83)

    def test_each_request_is_independent_and_never_overwrites_existing(self):
        a = self.maker.create(83)["request_file"]
        b = self.maker.create(83)["request_file"]
        self.assertNotEqual(a, b)
        self.assertTrue(Path(a).is_file())
        self.assertTrue(Path(b).is_file())

    def test_invalid_preflight_or_issue_cannot_create_request(self):
        for value in (True, 0, -1, "83", 2**40):
            self.assertEqual(self.maker.create(value)["status"], "BLOCKED")
        for preview in (
            {"state": "BLOCKED", "issue": 83},
            dict(self.preview, issue=82),
            dict(self.preview, source_sha="not-sha"),
            dict(self.preview, approved_scope=["../.ssh/"]),
        ):
            self.host.preflight.return_value = preview
            self.assertEqual(self.maker.create(83)["status"], "BLOCKED")
        self.assertFalse(self.directory.exists())

    def test_private_directory_symlink_and_unsafe_permissions_block(self):
        target = Path(self.tmp.name) / "real"
        target.mkdir(mode=0o700)
        self.directory.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.maker.create(83)["status"], "BLOCKED")
        self.directory.unlink()
        self.directory.mkdir(mode=0o777)
        self.directory.chmod(0o777)
        self.assertEqual(self.maker.create(83)["status"], "BLOCKED")

    def test_untrusted_request_file_symlink_and_duplicate_json_rejected(self):
        item = self.maker.create(83)
        path = Path(item["request_file"])
        fake = path.with_name("linked")
        fake.symlink_to(path)
        with self.assertRaises(ValueError):
            _read_untrusted_request(fake)
        path.write_text('{"issue":83,"issue":84}')
        with self.assertRaises(ValueError):
            _read_untrusted_request(path)

    def test_explicit_validation_disallows_extra_fields_and_scope_expansion(self):
        good = {
            "version": 1, "repository": "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP",
            "issue": 83, "base_sha": "a"*40, "issue_sha256": "b"*64,
            "scope": ["docs/example.md"],
        }
        self.assertEqual(validate_request(good), good)
        for invalid in (
            dict(good, token="secret"),
            dict(good, issue=True),
            dict(good, scope=["docs/example.md", "docs/example.md"]),
            dict(good, scope=["docs/../../secrets"]),
            dict(good, repository="evil/repo"),
        ):
            with self.assertRaises(ValueError):
                validate_request(invalid)


if __name__ == "__main__":
    unittest.main()
