"""Isolated failure-path tests. No live MCP mutations, GitHub, Docker or models."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/agent_harness"))
import mcp_execution as execution
from mcp_execution import MCPExecution, _atomic_json, _sha
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
        self.issue_body = "fixture Issue AC"
        self.issue_sha = hashlib.sha256(self.issue_body.encode()).hexdigest()
        self.path = "tests/agent_harness/fixtures/pilot/README.md"

    def _prepared(self):
        evidence = self.runner._external(self.run_id, create=True)
        worktree = Path(self.tmp.name) / "candidate"
        file = worktree / self.path
        file.parent.mkdir(parents=True)
        file.write_text("# Fixture\n")
        _atomic_json(evidence / "run.json", {
            "issue": 85, "run_id": self.run_id, "base_sha": self.sha,
            "issue_sha256": self.issue_sha, "stage": "PREPARED",
            "worktree": str(worktree), "branch": "feature/85-agent-aaaaaaaa",
            "approved_scope": [self.path], "receipts": {},
        })
        self.host.state.parent.mkdir(mode=0o700)
        with sqlite3.connect(self.host.state) as db:
            db.execute("CREATE TABLE jobs(run_id TEXT PRIMARY KEY, issue_sha TEXT, scope_json TEXT)")
            db.execute("INSERT INTO jobs VALUES (?,?,?)",
                       (self.run_id, self.issue_sha, json.dumps([self.path])))
        self.host.state.chmod(0o600)
        return evidence, worktree

    def _job(self):
        return {"state": "PREPARED", "run_id": self.run_id, "issue": 85,
                "worktree": str(Path(self.tmp.name) / "candidate"),
                "branch": "feature/85-agent-aaaaaaaa", "source_sha": self.sha}

    def _scope(self, *_):
        return {"status": "SCOPE_SCAN_PASS_ONLY", "paths": [self.path],
                "files_sha256": {self.path: _sha(Path(self._job()["worktree"]) / self.path)},
                "tracked_diff_sha256": "c" * 64, "changed_file_count": 1,
                "base_sha": self.sha, "build": "NOT_VERIFIED", "audit": "NOT_VERIFIED"}

    def _to_scope(self):
        dest, tree = self._prepared()
        self.runner._receipt(self.run_id, "WORKER_HANDOFF", {"run_id": self.run_id})
        self.runner._receipt(self.run_id, "SCOPE_VERIFIED", self._scope())
        return dest, tree

    def _to_checks(self):
        dest, tree = self._to_scope()
        receipt = {"candidate": self._scope(), "tests": {}, "builds": {}}
        for section, key, name in (("tests", "structure", "structure.log"),
                                   ("tests", "harness_unit", "harness-unit.log"),
                                   ("builds", "gateway_master", "gateway_master.log"),
                                   ("builds", "sensor_node", "sensor_node.log")):
            file = dest / name
            file.write_bytes(b"fixture command receipt\n")
            file.chmod(0o600)
            receipt[section][key] = {"exit_code": 0, "log": name, "log_sha256": _sha(file)}
            if section == "builds":
                receipt[section][key].update(cleanup_verified=True, containers_seen=1)
        self.runner._receipt(self.run_id, "CHECKS_VERIFIED", receipt)
        return dest, tree

    def _to_audit(self):
        dest, tree = self._to_checks()
        for name in ("AGENTS.md", ".github/copilot-instructions.md",
                     "docs/development/agy-native-coordinator-sop.md"):
            file = tree / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("fixture policy\n")
        schema = self.repo / "scripts/agent_harness/adapters/audit.schema.json"
        schema.parent.mkdir(parents=True)
        schema.write_text("{}\n")
        result = subprocess.CompletedProcess([], 0, json.dumps(
            {"body": self.issue_body, "state": "OPEN"}).encode(), b"")
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(self.runner, "_scope", side_effect=self._scope), \
                patch.object(execution, "bounded_run", return_value=result):
            value = self.runner.auditor_handoff(self.run_id)
        self.assertEqual(value["status"], "AUDITOR_HANDOFF", value)
        return dest, tree

    def _report(self):
        return {"status": "PASS", "findings": [], "limitations": [], "reviewed_scope": [self.path]}

    def test_env_flag_cannot_authorize_mutation_without_signed_grant(self):
        with patch.dict(os.environ, {"LORA_HARNESS_MUTATIONS": "operator-enabled"}), \
                patch.object(self.host, "preflight", return_value={
                    "state": "PREFLIGHT_ONLY", "source_sha": self.sha,
                    "issue_sha256": self.issue_sha, "approved_scope": [self.path],
                }), \
                patch.object(self.host, "_run") as host:
            # No root-approved grant exists in this isolated test environment.
            self.assertEqual(self.runner.prepare(85, self.sha, self.issue_sha)["status"], "BLOCKED")
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.verify_worker(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.run_checks(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.auditor_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.submit_audit(self.run_id, self._report())["status"], "BLOCKED")
            host.assert_not_called()

    def test_missing_operator_grant_blocks_before_worktree_side_effects(self):
        preview = {"state": "PREFLIGHT_ONLY", "source_sha": self.sha,
                   "issue_sha256": self.issue_sha, "approved_scope": [self.path]}
        with patch.object(self.host, "preflight", return_value=preview), \
                patch.object(self.host, "_run") as host:
            self.assertEqual(self.runner.prepare(85, self.sha, self.issue_sha)["status"], "BLOCKED")
            host.assert_not_called()

    def test_pinned_issue_mismatch_cannot_consume_grant(self):
        preview = {"state": "PREFLIGHT_ONLY", "source_sha": self.sha,
                   "issue_sha256": "0"*64, "approved_scope": [self.path]}
        with patch.object(self.host, "preflight", return_value=preview), \
                patch.object(self.host, "_run") as host:
            self.assertEqual(self.runner.prepare(85, self.sha, self.issue_sha)["status"], "BLOCKED")
            host.assert_not_called()

    def test_signed_grant_is_consumed_only_once_before_host_apply(self):
        preview = {"state": "PREFLIGHT_ONLY", "source_sha": self.sha,
                   "issue_sha256": self.issue_sha, "approved_scope": [self.path]}
        verified = {"grant_id": "d"*32, "issue": 85}
        receipt = {"state": "PREPARED", "source_sha": self.sha,
                   "issue_sha256": self.issue_sha, "approved_scope": [self.path],
                   "run_id": self.run_id, "branch": "feature/85-agent-aaaaaaaa",
                   "worktree": str(Path(self.tmp.name) / "candidate")}
        with patch.object(self.host, "preflight", return_value=preview), \
                patch.object(execution, "ApprovalAuthority") as authority, \
                patch.object(self.host, "_run", return_value=receipt) as host:
            authority.return_value.verify.return_value = verified
            first = self.runner.prepare(85, self.sha, self.issue_sha)
            self.assertEqual(first["status"], "PREPARED", first)
            self.assertEqual(self.runner._state(self.run_id)[0]["approval_id"], verified["grant_id"])
            self.assertIn("--expected-issue-sha256", host.call_args.args[1])
            second = self.runner.prepare(85, self.sha, self.issue_sha)
            self.assertEqual(second["status"], "BLOCKED")
            self.assertEqual(host.call_count, 1)

    def test_fixture_handoff_and_scope_transition(self):
        self._prepared()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            handoff = self.runner.worker_handoff(self.run_id)
            self.assertEqual(handoff["native_worker_provenance"], "NOT_VERIFIED")
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.verify_worker(self.run_id)["status"], "SCOPE_SCAN_PASS_ONLY")
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "SCOPE_VERIFIED")

    def test_busy_operation_fails_without_waiting_or_side_effects(self):
        dest, _ = self._prepared()
        with (dest / ".lock").open("w") as lock, \
                patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_job") as job:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            start = time.monotonic()
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertLess(time.monotonic() - start, 1)
            job.assert_not_called()

    def test_concurrent_calls_cannot_both_perform_the_stage(self):
        self._prepared()
        entered, release = threading.Event(), threading.Event()
        values = []
        def slow_job(_):
            entered.set()
            self.assertTrue(release.wait(3))
            return self._job()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_job", side_effect=slow_job) as job:
            thread = threading.Thread(target=lambda: values.append(self.runner.worker_handoff(self.run_id)))
            thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            finally:
                release.set()
                thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(job.call_count, 1)
        self.assertEqual(values[0]["status"], "WORKER_HANDOFF")

    def test_failed_operation_requires_manual_recovery(self):
        self._prepared()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_job", side_effect=ValueError("fixture")) as job:
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(self.runner.worker_handoff(self.run_id)["status"], "BLOCKED")
            self.assertEqual(job.call_count, 1)

    def test_crash_between_receipt_and_state_blocks_replay(self):
        dest, _ = self._prepared()
        original = _atomic_json
        def fail_state(path, payload):
            if path.name == "run.json":
                raise OSError("fixture fsync failure")
            original(path, payload)
        with patch.object(execution, "_atomic_json", side_effect=fail_state):
            with self.assertRaises(OSError):
                self.runner._receipt(self.run_id, "WORKER_HANDOFF", {})
        self.assertTrue((dest / "worker_handoff.json").exists())
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)

    def test_receipt_hash_tampering_is_rejected(self):
        dest, _ = self._to_scope()
        (dest / "scope_verified.json").write_text('{"status":"PASS"}')
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)

    def test_checks_require_real_unchanged_logs(self):
        dest, _ = self._to_checks()
        (dest / "sensor_node.log").write_text("different")
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)

    def test_missing_receipt_cannot_gain_check_or_audit_status(self):
        dest, _ = self._prepared()
        state = json.loads((dest / "run.json").read_text())
        state["stage"] = "CHECKS_VERIFIED"
        _atomic_json(dest / "run.json", state)
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)

    def test_symlink_and_world_readable_evidence_are_rejected(self):
        dest, _ = self._prepared()
        (dest / "run.json").chmod(0o644)
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)
        (dest / "run.json").unlink()
        (dest / "run.json").symlink_to("/etc/passwd")
        with self.assertRaises(OSError):
            self.runner._state(self.run_id)
        dest.chmod(0o755)
        with self.assertRaises(ValueError):
            self.runner._external(self.run_id)

    def test_malformed_state_and_unsafe_scope_fail_closed(self):
        dest, _ = self._prepared()
        original = json.loads((dest / "run.json").read_text())
        for value in ({**original, "stage": "PASS"},
                      {**original, "approved_scope": ["../escape"]},
                      {**original, "receipts": {"WORKER_HANDOFF": {}}}):
            _atomic_json(dest / "run.json", value)
            with self.assertRaises(ValueError):
                self.runner._state(self.run_id)

    def test_journal_pin_mismatch_rejected(self):
        self._prepared()
        for field, value in (("source_sha", "c" * 40), ("worktree", "/tmp/elsewhere"),
                             ("issue", 86), ("branch", "main"), ("run_id", "b" * 32)):
            with patch.object(self.host, "status", return_value={**self._job(), field: value}):
                with self.assertRaises(ValueError):
                    self.runner._job(self.run_id)

    def test_journal_issue_hash_and_scope_must_match_actual_row(self):
        self._prepared()
        with patch.object(self.host, "status", return_value=self._job()):
            self.assertEqual(self.runner._job(self.run_id)["source_sha"], self.sha)
            for column, value in (("issue_sha", "0" * 64), ("scope_json", '["firmware/"]')):
                with sqlite3.connect(self.host.state) as db:
                    db.execute("UPDATE jobs SET " + column + "=?", (value,))
                with self.assertRaises(ValueError):
                    self.runner._job(self.run_id)
                with sqlite3.connect(self.host.state) as db:
                    db.execute("UPDATE jobs SET issue_sha=?, scope_json=?",
                               (self.issue_sha, json.dumps([self.path])))

    def test_scope_blocks_ignored_files_and_outside_approval(self):
        self._prepared()
        result = subprocess.CompletedProcess([], 0, b".env\0", b"")
        with patch.object(self.host, "verify_candidate", side_effect=self._scope), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(execution, "bounded_run", return_value=result):
            with self.assertRaises(ValueError):
                self.runner._scope(self.run_id)
        result.stdout = b""
        with patch.object(self.host, "verify_candidate", return_value={**self._scope(), "paths": ["backend-go/x.go"]}), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(execution, "bounded_run", return_value=result):
            with self.assertRaises(ValueError):
                self.runner._scope(self.run_id)

    def test_candidate_code_cannot_pass_trusted_source_tests(self):
        self._to_scope()
        candidate = {**self._scope(), "paths": ["scripts/agent_harness/mcp_server.py"]}
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.dict(os.environ, {"LORA_HARNESS_DOCKER_IMAGE_ID": "sha256:" + "1" * 64}), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(self.runner, "_scope", return_value=candidate), \
                patch.object(self.runner, "_command") as command:
            self.assertEqual(self.runner.run_checks(self.run_id)["status"], "BLOCKED")
            command.assert_not_called()

    def test_no_docker_without_daemon_cleanup_supervisor(self):
        self._to_scope()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.dict(os.environ, {"LORA_HARNESS_DOCKER_IMAGE_ID": "sha256:" + "1" * 64}), \
                patch.object(self.runner, "_job", return_value=self._job()), \
                patch.object(self.runner, "_scope", side_effect=self._scope), \
                patch.object(self.runner, "_command", return_value={"exit_code": 0}) as command:
            self.assertEqual(self.runner.run_checks(self.run_id)["status"], "BLOCKED")
            self.assertEqual(command.call_count, 2)
            for args in command.call_args_list:
                self.assertEqual(args.args[0][0], sys.executable)
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "SCOPE_VERIFIED")

    def test_firmware_copy_rejects_symlink_and_bounds_file_size(self):
        _, tree = self._prepared()
        firmware = tree / "firmware/gateway_master"
        firmware.mkdir(parents=True)
        (firmware / "main.c").write_text("void f(void) {}\n")
        link = firmware / "secrets.txt"
        link.symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.runner._copy_firmware(tree, Path(self.tmp.name) / "scratch")
        link.unlink()
        with patch.object(execution, "_MAX_SOURCE_FILE", 1):
            with self.assertRaises(ValueError):
                self.runner._copy_firmware(tree, Path(self.tmp.name) / "scratch2")

    def test_audit_pass_does_not_attest_native_provenance(self):
        self._to_audit()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            result = self.runner.submit_audit(self.run_id, self._report())
        self.assertEqual(result["status"], "AWAIT_HUMAN", result)
        self.assertEqual(result["native_auditor_provenance"], "NOT_VERIFIED")
        self.assertEqual(self.runner._state(self.run_id)[0]["stage"], "AWAIT_HUMAN")

    def test_audit_invalid_scope_is_rejected(self):
        self._to_audit()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            result = self.runner.submit_audit(self.run_id, {**self._report(), "reviewed_scope": []})
        self.assertEqual(result["status"], "BLOCKED")

    def test_snapshot_and_candidate_drift_are_rejected(self):
        dest, tree = self._to_audit()
        snapshot_file = dest / "snapshot/source" / self.path
        snapshot_file.chmod(0o600)
        snapshot_file.write_text("changed snapshot")
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            self.assertEqual(self.runner.submit_audit(self.run_id, self._report())["status"], "BLOCKED")

    def test_auditor_report_tampering_after_final_state_is_rejected(self):
        dest, _ = self._to_audit()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            result = self.runner.submit_audit(self.run_id, self._report())
        self.assertEqual(result["status"], "AWAIT_HUMAN")
        (dest / "auditor-report.json").write_text('{}')
        with self.assertRaises(ValueError):
            self.runner._state(self.run_id)


    def test_status_does_not_serve_final_disposition_for_changed_candidate(self):
        _, tree = self._to_audit()
        with patch.object(self.runner, "_enabled", return_value=True), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            result = self.runner.submit_audit(self.run_id, self._report())
        self.assertEqual(result["status"], "AWAIT_HUMAN")
        with patch.object(self.host, "status", return_value=self._job()), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            self.assertEqual(self.runner.status(self.run_id)["status"], "AWAIT_HUMAN")
        (tree / self.path).write_text("new candidate bytes")
        with patch.object(self.host, "status", return_value=self._job()), \
                patch.object(self.runner, "_scope", side_effect=self._scope):
            self.assertEqual(self.runner.status(self.run_id)["status"], "BLOCKED")

    def test_status_blocks_interrupted_stage(self):
        dest, _ = self._prepared()
        _atomic_json(dest / "operation.json", {"stage": "PREPARED"})
        with patch.object(self.host, "status", return_value=self._job()):
            self.assertEqual(self.runner.status(self.run_id)["status"], "BLOCKED")

    def test_snapshot_root_symlink_is_rejected(self):
        dest, _ = self._to_audit()
        snapshot = dest / "snapshot"
        snapshot.rename(dest / "original-snapshot")
        snapshot.symlink_to(dest / "original-snapshot", target_is_directory=True)
        self.assertEqual(self.runner.status(self.run_id)["status"], "BLOCKED")

    def test_duplicate_json_keys_and_nonfinite_constants_are_rejected(self):
        dest, _ = self._prepared()
        for value in ('{"run_id":"a","run_id":"b"}', '{"value":NaN}'):
            (dest / "run.json").write_text(value)
            with self.assertRaises(ValueError):
                self.runner._state(self.run_id)


class CommandReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runner = MCPExecution(HarnessMCPHost(self.root))
        self.log = self.root / "command.log"

    def command(self, code, timeout=2):
        return self.runner._command([sys.executable, "-c", code], self.root, self.log, timeout)

    def test_output_flood_retains_bounded_failure_receipt(self):
        with patch.object(execution, "_MAX_OUTPUT", 1024):
            result = self.command("import os\nwhile True: os.write(2,b'x'*4096)")
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(self.log.stat().st_size, 1024)
        self.assertEqual(result["log_sha256"], _sha(self.log))
        self.assertNotIn('xxx', json.dumps(result))

    def test_timeout_keeps_partial_log_and_never_reports_zero(self):
        result = self.command("import time; print('fixture',flush=True); time.sleep(10)", 0.1)
        self.assertIsNone(result["exit_code"])
        self.assertEqual(result["log_sha256"], _sha(self.log))
        self.assertEqual(self.log.read_text(), "fixture\n")

    def test_existing_logs_and_symlinks_are_never_overwritten(self):
        self.log.write_text("original")
        self.assertEqual(self.command("print('changed')")["status"], "BLOCKED")
        self.assertEqual(self.log.read_text(), "original")
        self.log.unlink()
        victim = self.root / "victim"
        victim.write_text("original")
        self.log.symlink_to(victim)
        self.assertEqual(self.command("print('changed')")["status"], "BLOCKED")
        self.assertEqual(victim.read_text(), "original")

    def test_command_receipt_uses_sanitized_environment(self):
        with patch.dict(os.environ, {"PR84_TEST_SECRET": "fixture-canary"}):
            result = self.command("import os; assert 'PR84_TEST_SECRET' not in os.environ; print('ok')")
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["log_sha256"], _sha(self.log))
        self.assertEqual(self.log.stat().st_mode & 0o777, 0o600)


async def sdk_readonly_smoke():
    """Run explicitly with the installed official SDK; never call mutation tools."""
    import importlib.metadata
    from mcp import Client, StdioServerParameters
    params = StdioServerParameters(command=sys.executable,
                                   args=[str(ROOT / "scripts/agent_harness/mcp_server.py")],
                                   env={"PATH": "/usr/bin:/bin", "HOME": "/tmp"}, cwd=str(ROOT))
    import asyncio
    async with asyncio.timeout(20):
        async with Client(params) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}
            expected = {"harness_preflight", "harness_status", "harness_verify_candidate",
                        "harness_prepare_issue", "harness_worker_handoff", "harness_verify_worker",
                        "harness_run_checks", "harness_auditor_handoff", "harness_submit_audit",
                        "harness_execution_status"}
            assert names == expected, names
            calls = {}
            for name, arguments in (("harness_preflight", {"issue_number": 0}),
                                    ("harness_status", {"run_id": "invalid"}),
                                    ("harness_verify_candidate", {"run_id": "invalid"}),
                                    ("harness_execution_status", {"run_id": "invalid"})):
                response = await client.call_tool(name, arguments)
                assert not response.is_error, response
                payload = response.structured_content
                if payload is None:
                    assert len(response.content) == 1 and response.content[0].type == "text", response
                    payload = json.loads(response.content[0].text)
                assert payload["status"] == "BLOCKED", response
                calls[name] = payload["status"]
    print(json.dumps({"sdk": importlib.metadata.version("mcp"), "transport": "stdio",
                      "tools": sorted(names), "readonly_calls": calls,
                      "mutating_calls": "NOT_RUN", "E2E": "NOT_VERIFIED"}, indent=2))


if __name__ == "__main__":
    unittest.main()
