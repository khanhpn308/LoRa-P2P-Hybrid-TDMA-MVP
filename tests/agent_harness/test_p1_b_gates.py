"""P1-B host-only gates with real disposable local Git worktrees; no providers."""
from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1.state import Journal
from p1.worktrees import make_plan, prepare
from p1.verify import verify_candidate, VerificationBlocked
from p1.runtime_boundary import BuildBoundary, BoundaryError, deny_model_execution_in_build_boundary
from p1 import host_gate


def git(repo, *argv):
    subprocess.run(["git", "-C", str(repo), *argv], check=True, capture_output=True, timeout=20)


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = pathlib.Path(self.temp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "Harness Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "firmware").mkdir()
        (self.repo / "firmware" / "esp-idf-version.txt").write_text("v6.1\n")
        git(self.repo, "add", "firmware/esp-idf-version.txt")
        git(self.repo, "commit", "-qm", "fixture")
        plan = make_plan(self.repo, 34, "a" * 32)
        prepare(plan)
        self.branch = plan.branch
        self.worktree = plan.target
        self.db = base / "host" / "state.sqlite"
        self.run_id = "a" * 32
        with Journal(self.db) as journal:
            journal.plan(run_id=self.run_id, issue=34, source_sha=plan.base_sha,
                         issue_sha="f" * 64, branch=plan.branch,
                         worktree=plan.target, scope=("tests/agent_harness/",))
            journal.transition(self.run_id, expected="PLANNED", next_state="PREPARING")
            journal.transition(self.run_id, expected="PREPARING", next_state="PREPARED")

    def candidate(self, path="tests/agent_harness/helper.py", value=b"def ok():\n    return 2\n"):
        dest = self.worktree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(value)
        return dest

    def verify(self):
        with Journal(self.db) as journal:
            return verify_candidate(journal, self.run_id)

    def test_prepared_candidate_untracked_file_is_in_receipt(self):
        self.candidate()
        receipt = self.verify()
        self.assertEqual(receipt["status"], "SCOPE_SCAN_PASS_ONLY")
        self.assertIn("tests/agent_harness/helper.py", receipt["paths"])
        self.assertRegex(receipt["files_sha256"]["tests/agent_harness/helper.py"], r"^[0-9a-f]{64}$")
        self.assertEqual(receipt["build"], "NOT_VERIFIED")
        self.assertEqual(receipt["audit"], "NOT_VERIFIED")

    def test_no_candidate_is_blocked(self):
        with self.assertRaises(VerificationBlocked):
            self.verify()

    def test_out_of_scope_change_is_blocked(self):
        self.candidate("contracts/radio-mac/contract.md", b"unauthorized\n")
        with self.assertRaises(VerificationBlocked):
            self.verify()

    def test_secret_like_token_is_blocked(self):
        self.candidate(value=b"key = 'sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ1234'\n")
        with self.assertRaises(VerificationBlocked):
            self.verify()

    def test_symlink_changed_file_is_blocked(self):
        file = self.candidate()
        file.unlink()
        file.symlink_to(self.repo / "firmware" / "esp-idf-version.txt")
        with self.assertRaises(VerificationBlocked):
            self.verify()

    def test_altered_base_sha_is_blocked(self):
        self.candidate()
        git(self.worktree, "config", "user.name", "Test")
        git(self.worktree, "config", "user.email", "test@example.invalid")
        git(self.worktree, "add", ".")
        git(self.worktree, "commit", "-qm", "unapproved commit")
        with self.assertRaises(VerificationBlocked):
            self.verify()

    def test_host_cli_read_only_and_version_pinned(self):
        self.candidate()
        with patch.object(sys, "argv", ["host_gate.py", "--run-id", self.run_id,
                                      "--state", str(self.db)]), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(host_gate.main(), 0)
        receipt = json.loads(buffer.getvalue())
        self.assertEqual(receipt["esp_idf"], "v6.1")
        self.assertEqual(receipt["status"], "SCOPE_SCAN_PASS_ONLY")
        self.assertNotIn("build_commands", receipt)

    def test_host_cli_rejects_unknown_job_without_creating_state(self):
        with patch.object(sys, "argv", ["host_gate.py", "--run-id", "unknown",
                                      "--state", str(self.db)]), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(host_gate.main(), 2)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "BLOCKED")


class BuildBoundaryTests(unittest.TestCase):
    def test_sha_pinned_offline_nonprivileged_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            c = BuildBoundary("sha256:" + "a" * 64).command(root, "gateway_master")
            self.assertIn("--network=none", c)
            self.assertIn("--read-only", c)
            self.assertIn("--cap-drop=ALL", c)
            self.assertIn("--security-opt=no-new-privileges", c)
            self.assertIn("--pull=never", c)
            self.assertEqual(c[-3:], ["sha256:" + "a" * 64, "idf.py", "build"])
            self.assertFalse(any("docker.sock" in x for x in c))
            self.assertFalse(any("HOME=/home/" in x for x in c))
            self.assertNotIn("--privileged", c)

    def test_reject_unpinned_image_and_unknown_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            with self.assertRaises(BoundaryError):
                BuildBoundary("espressif/idf:latest").command(root, "gateway_master")
            with self.assertRaises(BoundaryError):
                BuildBoundary("sha256:" + "a" * 64).command(root, "../unsafe")
        with self.assertRaises(BoundaryError):
            deny_model_execution_in_build_boundary("agy")


if __name__ == "__main__":
    unittest.main()
