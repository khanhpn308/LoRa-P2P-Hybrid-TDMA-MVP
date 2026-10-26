"""MCP execution stage tests. No live model/GitHub/Docker, no repository changes."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/agent_harness"))
from mcp_execution import MCPExecution, _atomic_json
from mcp_host import HarnessMCPHost


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "main"
        self.repo.mkdir()
        self.host = HarnessMCPHost(self.repo)
        self.runner = MCPExecution(self.host)
        self.run_id = "a" * 32
        self.sha = "a" * 40
        self.issue_sha = "b" * 64

    def _prepared(self):
        evidence = self.runner._external(self.run_id, create=True)
        worktree = Path(self.tmp.name) / "candidate"
        file = worktree / "tests/agent_harness/fixtures/pilot/README.md"
        file.parent.mkdir(parents=True)
        file.write_text("# Fixture\n")
        _atomic_json(evidence / "run.json", {
            "issue": 85, "run_id": self.run_id, "base_sha": self.sha,
            "issue_sha256": self.issue_sha, "stage": "PREPARED",
            "worktree": str(worktree), "branch": "feature/85-agent-aaaaaaaa",
            "approved_scope": ["tests/agent_harness/fixtures/pilot/README.md"],
            "receipts": {},
        })
        return evidence, worktree

    def _mock_job(self):
        return {"state": "PREPARED", "worktree": str(Path(self.tmp.name)/"candidate"),
                "source_sha": self.sha}

    def _mock_scope(self):
        return {
            "status": "SCOPE_SCAN_PASS_ONLY", "paths": [
                "tests/agent_harness/fixtures/pilot/README.md"],
            "files_sha256": {"tests/agent_harness/fixtures/pilot/README.md": "b"*64},
            "tracked_diff_sha256": "c"*64, "changed_file_count": 1,
            "base_sha": self.sha, "build": "NOT_VERIFIED", "audit": "NOT_VERIFIED",
        }

    def test_default_disables_mutating_tools(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.runner.prepare(85, self.sha, self.issue_sha)["status"], "BLOCKED")
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.run_checks(self.run_id)["status"], "BLOCKED")

    def test_prepare_fails_closed_for_pins_without_host_apply(self):
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"}):
            with patch.object(self.host, "preflight",
                              return_value={"state": "PREFLIGHT_ONLY",
                                            "source_sha": self.sha,
                                            "issue_sha256": "0"*64}):
                with patch.object(self.host, "_run") as run:
                    self.assertEqual(self.runner.prepare(85, self.sha, self.issue_sha)["status"], "BLOCKED")
                    run.assert_not_called()

    def test_prepare_records_host_verified_run(self):
        preview = {"state": "PREFLIGHT_ONLY", "source_sha": self.sha, "issue_sha256": self.issue_sha}
        applied = {"state": "PREPARED", "run_id": self.run_id, "issue_sha256": self.issue_sha,
                   "source_sha": self.sha, "branch": "feature/85-agent-aaaaaaaa",
                   "worktree": str(Path(self.tmp.name)/"candidate"),
                   "approved_scope": ["tests/agent_harness/fixtures/pilot/README.md"]}
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"}):
            with patch.object(self.host, "preflight", return_value=preview):
                with patch.object(self.host, "_run", return_value=applied) as apply:
                    value = self.runner.prepare(85, self.sha, self.issue_sha)
        self.assertEqual(value["status"], "PREPARED")
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "PREPARED")
        self.assertIn("--apply", apply.call_args.args[1])

    def test_native_worker_handoff_and_gate(self):
        self._prepared()
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"}):
            with patch.object(self.runner, "_job", return_value=self._mock_job()):
                w = self.runner.worker_handoff(self.run_id)
            self.assertEqual(w["status"], "WORKER_HANDOFF")
            self.assertEqual(w["native_worker_provenance"], "NOT_VERIFIED")
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            with patch.object(self.runner, "_scope", return_value=self._mock_scope()):
                self.assertEqual(self.runner.verify_worker(self.run_id)["status"], "SCOPE_SCAN_PASS_ONLY")
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "SCOPE_VERIFIED")

    def test_checks_refuse_missing_image_pin(self):
        self._prepared()
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"},
                        clear=True):
            self.assertEqual(self.runner.run_checks(self.run_id)["status"], "BLOCKED")

    def test_firmware_copy_rejects_symlink_and_copies_allowlisted_source(self):
        base = Path(self.tmp.name) / "candidate"
        firmware = base / "firmware/gateway_master"
        firmware.mkdir(parents=True)
        (firmware/"main.c").write_text("void f(void) {}\n")
        (firmware/"secrets.txt").symlink_to("/etc/passwd")
        scratch = Path(self.tmp.name) / "scratch"
        with self.assertRaises(ValueError):
            self.runner._copy_firmware(base, scratch)
        (firmware/"secrets.txt").unlink()
        scratch2 = Path(self.tmp.name) / "scratch2"
        self.runner._copy_firmware(base, scratch2)
        self.assertTrue((scratch2/"firmware/gateway_master/main.c").exists())

    def test_native_report_validation_is_not_provenance(self):
        evidence, _ = self._prepared()
        state = json.loads((evidence / "run.json").read_text())
        state["stage"] = "AUDITOR_HANDOFF"
        _atomic_json(evidence / "run.json", state)
        snapshot = evidence / "snapshot"
        (snapshot/"source/tests/agent_harness/fixtures/pilot").mkdir(parents=True)
        f = snapshot/"source/tests/agent_harness/fixtures/pilot/README.md"
        f.write_text("# Fixture\n")
        schema = snapshot/"audit.schema.json"
        schema.write_text("{}\n")
        inv = {
            "status": "AUDITOR_HANDOFF", "run_id": self.run_id,
            "snapshot": str(snapshot), "candidate": self._mock_scope(),
            "snapshot_files_sha256": {
                "source/tests/agent_harness/fixtures/pilot/README.md": __import__("hashlib").sha256(f.read_bytes()).hexdigest(),
                "audit.schema.json": __import__("hashlib").sha256(schema.read_bytes()).hexdigest(),
            },
        }
        _atomic_json(evidence / "auditor_handoff.json", inv)
        good = {"status": "PASS", "findings": [], "limitations": [],
                "reviewed_scope": self._mock_scope()["paths"]}
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"}):
            with patch.object(self.runner, "_scope", return_value=self._mock_scope()):
                self.assertEqual(self.runner.submit_audit(self.run_id, {**good, "reviewed_scope": []})["status"], "BLOCKED")
                accepted = self.runner.submit_audit(self.run_id, good)
        self.assertEqual(accepted["status"], "AWAIT_HUMAN")
        self.assertEqual(accepted["native_auditor_provenance"], "NOT_VERIFIED")
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "AWAIT_HUMAN")


if __name__ == "__main__":
    unittest.main()
