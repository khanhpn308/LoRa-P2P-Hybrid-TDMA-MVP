"""No cloud credentials or model execution in P1-B supervision/publisher tests."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1.process import execute_checked, ProcessBlocked
from p1.draft_preview import preview, PublishingBlocked


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], check=True,
                       capture_output=True, text=True, timeout=20)
    return p.stdout.strip()


class ProcessTests(unittest.TestCase):
    def test_zero_exit_and_nonzero_do_not_forge_test_pass(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            good = execute_checked(["true"], root, timeout=5)
            self.assertEqual(good.status, "EXIT_SUCCESS")
            self.assertEqual(good.exit_code, 0)
            fail = execute_checked(["false"], root, timeout=5)
            self.assertEqual(fail.status, "EXIT_FAILURE")
            self.assertNotEqual(fail.exit_code, 0)
            self.assertEqual(len(fail.output_sha256), 64)

    def test_timeout_kills_process_group(self):
        with tempfile.TemporaryDirectory() as d:
            value = execute_checked(["sleep", "5"], pathlib.Path(d), timeout=1)
            self.assertEqual(value.status, "TIMEOUT")
            self.assertIsNone(value.exit_code)

    def test_invalid_timeout_and_agent_are_denied(self):
        with tempfile.TemporaryDirectory() as d:
            for tool in ("agy", "codex", "docker", "gh", "sudo"):
                with self.subTest(tool=tool), self.assertRaises(ProcessBlocked):
                    execute_checked([tool, "--help"], pathlib.Path(d), timeout=2)
            with self.assertRaises(ProcessBlocked):
                execute_checked(["true"], pathlib.Path(d), timeout=0)

    def test_execution_identity_and_cancellation_cleanup(self):
        from unittest.mock import patch, MagicMock
        with tempfile.TemporaryDirectory() as d:
            rec = execute_checked(["true"], pathlib.Path(d), timeout=5, execution_id="exec-427.1")
            self.assertEqual(rec.execution_id, "exec-427.1")
            with self.assertRaises(ProcessBlocked):
                execute_checked(["true"], pathlib.Path(d), timeout=5, execution_id="../bad")
            fake_proc = MagicMock()
            fake_proc.pid = 424242
            fake_proc.poll.return_value = None
            fake_proc.communicate.side_effect = [KeyboardInterrupt(), (b"", b"")]
            with patch("p1.process.subprocess.Popen", return_value=fake_proc), \
                 patch("p1.process._kill_process_group") as killer:
                with self.assertRaises(KeyboardInterrupt):
                    execute_checked(["sleep", "5"], pathlib.Path(d), timeout=5, execution_id="exec-cancel")
                killer.assert_called_once_with(424242)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = pathlib.Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, timeout=15)
        git(self.repo, "config", "user.name", "Harness Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "README.md").write_text("fixture\n")
        git(self.repo, "add", "README.md")
        git(self.repo, "commit", "-qm", "initial")
        git(self.repo, "checkout", "-qb", "feature/34-agent-aaaaaaaa")
        self.sha = git(self.repo, "rev-parse", "HEAD")

    def kwargs(self):
        return {"branch": "feature/34-agent-aaaaaaaa",
                "target_base": "chore/30-firmware-agent-harness",
                "expected_sha": self.sha, "issue": 34}

    def test_preview_does_not_publish(self):
        result = preview(self.repo, **self.kwargs())
        self.assertEqual(result["status"], "DRAFT_PR_PLAN_ONLY")
        self.assertEqual(result["commit"], self.sha)
        self.assertIn("--draft", result["example_command_not_executed"])

    def test_wrong_commit_or_base_is_blocked(self):
        with self.assertRaises(PublishingBlocked):
            preview(self.repo, **{**self.kwargs(), "expected_sha": "a"*40})
        with self.assertRaises(PublishingBlocked):
            preview(self.repo, **{**self.kwargs(), "target_base": "main"})

    def test_dirty_candidate_is_blocked(self):
        (self.repo / "untracked-secret-file.txt").write_text("untracked")
        with self.assertRaises(PublishingBlocked):
            preview(self.repo, **self.kwargs())


if __name__ == "__main__":
    unittest.main()
