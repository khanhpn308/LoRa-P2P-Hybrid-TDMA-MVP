"""CLI argument and fail-closed behavior tests with NO provider/network usage."""
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from adapters import antigravity, codex

FILES = {"firmware/components/sx1276_driver/sx1276.c"}
REPORT = {"status": "PASS", "findings": [], "limitations": [],
          "reviewed_scope": sorted(FILES)}


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
            self.assertEqual(args[:2], ["codex", "exec"])
            self.assertIn("workspace-write", args)
            self.assertIn("never", args)
            self.assertEqual(mocked.call_args.kwargs["input"], "write C")

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



if __name__ == "__main__":
    unittest.main()
