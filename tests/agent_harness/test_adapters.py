"""CLI argument and fail-closed behavior tests with NO provider/network usage."""
import json
import pathlib
import subprocess
import sys
import tempfile
import copy
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from adapters import antigravity, codex

FILES = {"firmware/components/sx1276_driver/sx1276.c"}
REPORT = {"status": "PASS", "findings": [], "limitations": [],
          "reviewed_scope": sorted(FILES)}


class ScopedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.rules = [{"rule_id": "MEM-001", "rule_sha256": "a" * 64}]
        self.selection = "b" * 64
        self.report = dict(REPORT, status="INCONCLUSIVE", selection_sha256=self.selection,
                           rule_results=[{"rule_id": "MEM-001", "rule_sha256": "a" * 64,
                                          "status": "NOT_RUN", "evidence": [],
                                          "reason": "Host verification has not run yet."}])

    def invoke(self, payload, stderr=""):
        def provider(args, **kwargs):
            output = pathlib.Path(args[args.index("--output-last-message") + 1])
            if payload is not None:
                output.write_text(payload)
            self.assertIn("--output-schema", args)
            self.assertEqual(kwargs["input"], "scoped task")
            return subprocess.CompletedProcess(args, 0, "", stderr)
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.codex.subprocess.run", side_effect=provider):
            return codex.invoke("scoped task", pathlib.Path(directory), 120,
                                self.rules, self.selection, {})

    def test_structured_worker_report_preserved(self):
        result = self.invoke(json.dumps(self.report))
        self.assertEqual(result["report"], self.report)

    def test_missing_malformed_duplicate_stale_and_secret_reports_fail_closed(self):
        malformed = [None, "plain prose", "{" * 2000,
                     json.dumps(REPORT), json.dumps(dict(self.report, rule_results=[])),
                     json.dumps(dict(self.report, selection_sha256="c" * 64)),
                     '{"status":"PASS","status":"FAIL"}',
                     "x" * 160001]
        report = copy.deepcopy(self.report)
        report["rule_results"][0]["reason"] = "ghp_" + "A" * 30
        malformed.append(json.dumps(report))
        for payload in malformed:
            with self.subTest(size=len(payload or "")), self.assertRaises(codex.WorkerError):
                self.invoke(payload)

    def test_provider_secret_output_is_rejected_without_echo(self):
        secret = "ghp_" + "A" * 30
        with self.assertRaises(codex.WorkerError) as error:
            self.invoke(json.dumps(self.report), secret)
        self.assertNotIn(secret, str(error.exception))

    def test_scanner_source_literal_is_not_a_private_key_transcript(self):
        transcript = 'Source line: if b"PRIVATE KEY-----" in raw: reject()\n'
        self.assertEqual(self.invoke(json.dumps(self.report), transcript)["report"], self.report)
        pem = "-----BEGIN " + "PRIVATE KEY-----\nsynthetic material\n"
        with self.assertRaises(codex.WorkerError):
            self.invoke(json.dumps(self.report), pem)

    def test_soft_permission_denial_blocks_successful_worker_report(self):
        with self.assertRaises(codex.WorkerError):
            self.invoke(json.dumps(self.report), "approval required: run_command")

    def test_empty_rule_set_still_requires_scoped_report(self):
        self.rules = []
        self.report["rule_results"] = []
        self.assertEqual(self.invoke(json.dumps(self.report))["report"], self.report)

    def test_partial_scope_cannot_select_legacy_worker(self):
        with self.assertRaises(codex.WorkerError):
            codex.invoke("scoped task", pathlib.Path('/tmp'), 30, selection_sha256=self.selection)

    def test_real_provider_stream_is_bounded_before_decoding(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(antigravity.AuditError):
            antigravity.run_bounded(
                [sys.executable, "-c", "print('x' * 160001)"],
                cwd=pathlib.Path(directory), timeout=10)


class AdapterTests(unittest.TestCase):
    def test_agy_cli_requires_schema_and_sandbox(self):
        envelope = json.dumps({"status": "SUCCESS", "structured_output": REPORT})
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, envelope, "")) as mocked:
            base = pathlib.Path(directory)
            schema = base / "schema.json"
            schema.write_text("{}")
            answer = antigravity.invoke("Review data", base, schema, 120, FILES)
            self.assertEqual(answer["status"], "PASS")
            argv = mocked.call_args.args[0]
            self.assertEqual(argv[0], "agy")
            for flag in ("--sandbox", "--output-format", "--json-schema", "--print-timeout"):
                self.assertIn(flag, argv)
            self.assertNotIn("--dangerously-skip-permissions", argv)

    def test_agy_permission_denial_blocks_even_with_success_json(self):
        envelope = json.dumps({"status": "SUCCESS", "structured_output": REPORT})
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, envelope,
                    "approval required: run_command")):
            with self.assertRaises(antigravity.AuditError):
                antigravity.invoke("Review", pathlib.Path(directory),
                                   pathlib.Path(directory) / "schema.json", 120, FILES)

    def test_codex_worker_sandbox_and_no_approval(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.codex.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "edited", "")) as mocked:
            codex.invoke("write C", pathlib.Path(directory), 120)
            args = mocked.call_args.args[0]
            self.assertEqual(args[:4], ["codex", "--ask-for-approval", "never", "exec"])
            self.assertIn("workspace-write", args)
            self.assertIn("never", args)
            self.assertEqual(mocked.call_args.kwargs["input"], "write C")

    def test_codex_read_only_mode(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.codex.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, "read only", "")) as mocked:
            codex.invoke("read C", pathlib.Path(directory), 120, read_only=True)
            args = mocked.call_args.args[0]
            self.assertEqual(args[:4], ["codex", "--ask-for-approval", "never", "exec"])
            self.assertIn("read-only", args)
            self.assertNotIn("workspace-write", args)
            self.assertEqual(mocked.call_args.kwargs["input"], "read C")

    def test_adapter_rejects_more_than_128_rules(self):
        rules_129 = [{"rule_id": f"R-{n:03}", "rule_sha256": "a" * 64} for n in range(129)]
        with self.assertRaises(antigravity.AuditError):
            antigravity.scoped_schema(rules_129, "b" * 64)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(codex.WorkerError):
                codex.invoke("check", pathlib.Path(directory), 120, required_rules=rules_129, selection_sha256="b" * 64)

    def test_codex_nonzero_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.codex.subprocess.run",
                return_value=subprocess.CompletedProcess([], 2, "", "error")):
            with self.assertRaises(codex.WorkerError):
                codex.invoke("write", pathlib.Path(directory), 120)


    def test_agy_rejects_extra_scope_in_mocked_invoke(self):
        report = dict(REPORT, reviewed_scope=sorted(FILES) + ["unreviewed.py"])
        payload = json.dumps({"status": "SUCCESS", "structured_output": report})
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "")):
            with self.assertRaises(antigravity.AuditError):
                antigravity.invoke("Review", pathlib.Path(directory),
                                   pathlib.Path(directory) / "schema.json", 120, FILES)

    def test_agy_rejects_duplicate_raw_envelope_key(self):
        payload = '{"status":"SUCCESS","status":"SUCCESS","structured_output":{}}'
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "")):
            with self.assertRaises(antigravity.AuditError):
                antigravity.invoke("Review", pathlib.Path(directory),
                                   pathlib.Path(directory) / "schema.json", 120, FILES)

    def test_agy_rejects_extra_nested_audit_key(self):
        report = dict(REPORT, surprise="unexpected")
        payload = json.dumps({"status": "SUCCESS", "structured_output": report})
        with tempfile.TemporaryDirectory() as directory, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "")):
            with self.assertRaises(antigravity.AuditError):
                antigravity.invoke("Review", pathlib.Path(directory),
                                   pathlib.Path(directory) / "schema.json", 120, FILES)

    def test_adapters_reject_symlink_working_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            real_dir = root / "real"
            real_dir.mkdir()
            sym_dir = root / "link"
            sym_dir.symlink_to(real_dir, target_is_directory=True)
            with self.assertRaises(codex.WorkerError):
                codex.invoke("write", sym_dir, 60)
            with self.assertRaises(antigravity.AuditError):
                antigravity.invoke("review", sym_dir, real_dir / "schema.json", 60, FILES)


if __name__ == "__main__":
    unittest.main()
