"""Unit and synthetic integration tests for P1-B3; NEVER call live AGY."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1 import auto_issue as job

MODEL = "gemini-test-model"
SHA = "a" * 64


def git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                       text=True, check=True, timeout=20)
    return p.stdout.strip()


class AutomationPolicyTests(unittest.TestCase):
    def test_consumer_login_never_authorized(self):
        valid = {"provider": "agy-enterprise-authorized",
                 "runner": "externally-isolated",
                 "approved": True, "evidence_id": "enterprise-review-001"}
        job.validate_entitlement(valid)
        for changed in (
            dict(valid, provider="agy-consumer"),
            dict(valid, provider="gemini-api"),
            dict(valid, approved=False),
            dict(valid, runner="personal-wsl2"),
            dict(valid, evidence_id=""),
            dict(valid, evidence_id="../../secret"),
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(job.PipelineBlocked):
                    job.validate_entitlement(changed)

    def test_model_subprocess_does_not_inherit_github_token(self):
        with patch.dict("os.environ", {"GH_TOKEN": "secret-placeholder",
                                        "GITHUB_TOKEN": "secret-placeholder",
                                        "OPENAI_API_KEY": "secret-placeholder",
                                        "PATH": "/usr/bin"}, clear=True):
            env = job._safe_env()
        self.assertNotIn("GH_TOKEN", env)
        self.assertNotIn("GITHUB_TOKEN", env)
        self.assertNotIn("OPENAI_API_KEY", env)
        self.assertEqual(env["PATH"], "/usr/bin")

    def test_agy_model_flags_and_soft_denial(self):
        result = json.dumps({"status": "SUCCESS", "response": "mock reply"})
        with tempfile.TemporaryDirectory() as d, patch.object(
                job, "exec_checked", return_value=(0, result, "")) as call:
            answer, _ = job._model("test", pathlib.Path(d), None, MODEL, 60)
            self.assertIn("SUCCESS", answer)
            args = call.call_args.args[0]
            self.assertEqual(args[:2], ["agy", "-p"])
            self.assertIn("--sandbox", args)
            self.assertNotIn("--dangerously-skip-permissions", args)
            self.assertNotIn("--continue", args)
            self.assertNotIn("GH_TOKEN", call.call_args.kwargs["env"])
        with tempfile.TemporaryDirectory() as d, patch.object(
                job, "exec_checked", return_value=(0, result, "permission denied")):
            with self.assertRaises(job.PipelineBlocked):
                job._model("test", pathlib.Path(d), None, MODEL, 60)

    def test_unknown_model_and_oversized_prompt(self):
        with self.assertRaises(job.PipelineBlocked):
            job._model("hello", pathlib.Path("."), None, "../ model", 60)
        with self.assertRaises(job.PipelineBlocked):
            job._model("x" * 100001, pathlib.Path("."), None, MODEL, 60)

    def test_issue_requires_approval_label_and_scope(self):
        body = "## Target Directories (allowed paths)\n- `tests/agent_harness/`\n"
        issue = {"number": 56, "state": "OPEN", "title": "fixture",
                 "body": body, "labels": [{"name": "harness:approved"}]}
        with patch.object(job.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(issue), "")):
            info = job.load_issue(56, pathlib.Path("."))
            self.assertEqual(info["scope"], ("tests/agent_harness/",))
        issue["labels"] = []
        with patch.object(job.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, json.dumps(issue), "")):
            with self.assertRaises(job.PipelineBlocked):
                job.load_issue(56, pathlib.Path("."))

    def test_no_execute_by_default(self):
        with patch.object(sys, "argv", ["auto_issue", "--issue", "56"]), patch.object(
                job, "load_issue", return_value={"number": 56, "body_sha256": "b" * 64,
                                                  "scope": ("tests/agent_harness/",)}), patch.object(
                job, "git", return_value="c" * 40):
            with patch("builtins.print") as out:
                self.assertEqual(job.main(), 0)
        self.assertIn("PREFLIGHT_ONLY", out.call_args.args[0])


class SyntheticFullCycleTests(unittest.TestCase):
    """Real temporary Git repo; synthetic AGY and Docker, no accounts/models."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "P1-B3 Test")
        (self.repo / "firmware").mkdir()
        (self.repo / "firmware" / "esp-idf-version.txt").write_text("v6.1\n")
        schema = self.repo / "scripts" / "agent_harness" / "adapters"
        schema.mkdir(parents=True)
        (schema / "audit.schema.json").write_text('{"type":"object"}')
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "fixture")
        self.issue = {"number": 56, "title": "make fixture",
                      "body_sha256": "b" * 64,
                      "body": "Create a harmless test fixture only.",
                      "scope": ("tests/agent_harness/",)}

    def _model(self, prompt, cwd, schema, model, timeout):
        if schema is None:
            file = cwd / "tests" / "agent_harness" / "example.txt"
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text("fixture\n")
            return json.dumps({"status": "SUCCESS"}), ""
        return json.dumps({"status": "SUCCESS", "structured_output": {
            "status": "PASS", "findings": [], "limitations": [],
            "reviewed_scope": ["tests/agent_harness/example.txt"],
        }}), ""

    def test_real_git_state_fake_worker_build_auditor(self):
        img = "sha256:" + SHA
        with patch.object(job, "_model", side_effect=self._model), patch.object(
                job, "exec_checked", return_value=(0, "fake tool output", "")), patch.object(
                job.shutil, "which", return_value="/usr/bin/fake"):
            result = job.run_pipeline(self.repo, self.issue, image_id=img, model=MODEL,
                                      max_repairs=0, timeout=60)
        self.assertEqual(result["status"], "AWAIT_HUMAN")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["rf"], "NOT_VERIFIED")
        self.assertEqual(result["hil"], "NOT_VERIFIED")
        self.assertEqual(len(result["build_receipts"]), 4)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")

    def test_modified_source_outside_scope_blocks(self):
        def worker_bad(prompt, cwd, schema, model, timeout):
            bad = cwd / "contracts" / "radio-mac" / "payload.c"
            bad.parent.mkdir(parents=True, exist_ok=True)
            bad.write_text("not allowed\n")
            return json.dumps({"status": "SUCCESS"}), ""
        with patch.object(job, "_model", side_effect=worker_bad), patch.object(
                job.shutil, "which", return_value="/usr/bin/fake"):
            with self.assertRaises(job.VerificationBlocked):
                job.run_pipeline(self.repo, self.issue,
                                 image_id="sha256:" + SHA, model=MODEL)

    def test_build_failure_never_reaches_auditor(self):
        calls = []
        def model(prompt, cwd, schema, name, timeout):
            calls.append(schema is not None)
            return self._model(prompt, cwd, schema, name, timeout)
        with patch.object(job, "_model", side_effect=model), patch.object(
                job, "exec_checked", return_value=(1, "mock failed", "")), patch.object(
                job.shutil, "which", return_value="/usr/bin/fake"):
            with self.assertRaises(job.PipelineBlocked):
                job.run_pipeline(self.repo, self.issue, image_id="sha256:" + SHA,
                                 model=MODEL, max_repairs=0)
        self.assertEqual(calls, [False])


if __name__ == "__main__":
    unittest.main()
