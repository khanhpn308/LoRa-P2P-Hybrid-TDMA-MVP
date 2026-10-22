"""P1 integration tests using disposable REAL Git repositories; no network."""
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
from p1.worktrees import WorktreeError, make_plan, prepare, git
from p1 import cli
from p1.state import Journal


def git_cmd(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True,
                   capture_output=True, text=True, timeout=20)


class WorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, timeout=20)
        git_cmd(self.repo, "config", "user.email", "tester@example.invalid")
        git_cmd(self.repo, "config", "user.name", "Test")
        (self.repo / "README.md").write_text("initial commit\n")
        git_cmd(self.repo, "add", "README.md")
        git_cmd(self.repo, "commit", "-qm", "initial")
        self.run_id = "a" * 32
        self.issue_data = {
            "title": "Test task",
            "body": "## Target Directories (allowed paths)\n- `scripts/agent_harness/p1/`\n",
            "scope": ("scripts/agent_harness/p1/",),
        }

    def test_git_worktree_verified_and_no_main_changes(self):
        p = make_plan(self.repo, 32, self.run_id)
        self.assertFalse(p.target.exists())
        prepare(p)
        self.assertEqual(git(p.target, "branch", "--show-current"), p.branch)
        self.assertEqual(git(p.target, "rev-parse", "HEAD"), p.base_sha)
        self.assertEqual(git(self.repo, "status", "--porcelain"), "")
        with self.assertRaises(WorktreeError):
            prepare(p)

    def test_dirty_source_blocked(self):
        (self.repo / "untracked.txt").write_text("dirty")
        with self.assertRaises(WorktreeError):
            make_plan(self.repo, 32, self.run_id)

    def test_symlink_parent_blocked(self):
        (self.root / ".lora-p1-worktrees").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(WorktreeError):
            make_plan(self.repo, 32, self.run_id)

    def test_duplicate_branch_blocked(self):
        git_cmd(self.repo, "branch", "feature/32-agent-aaaaaaaa")
        with self.assertRaises(WorktreeError):
            make_plan(self.repo, 32, self.run_id)

    def test_git_branch_lookup_failure_is_fail_closed(self):
        real_run = subprocess.run

        def fake_run(args, **kwargs):
            if "show-ref" in args:
                return subprocess.CompletedProcess(args, 128, "", "git database error")
            return real_run(args, **kwargs)

        with patch("p1.worktrees.subprocess.run", side_effect=fake_run):
            with self.assertRaises(WorktreeError):
                make_plan(self.repo, 32, self.run_id)

    def test_dry_run_has_no_mutations(self):
        db = self.root / "journal" / "state.sqlite"
        argv = ["cli.py", "prepare", "--issue", "32", "--source", str(self.repo),
                "--state", str(db)]
        with patch.object(cli, "issue_info", return_value=self.issue_data), \
             patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["state"], "PREFLIGHT_ONLY")
        self.assertFalse(db.exists())
        self.assertFalse(pathlib.Path(data["worktree"]).exists())

    def test_expected_source_sha_mismatch_blocks_before_mutation(self):
        db = self.root / "journal" / "state.sqlite"
        argv = ["cli.py", "prepare", "--issue", "32", "--source", str(self.repo),
                "--state", str(db), "--expected-base-sha", "0" * 40, "--apply"]
        with patch.object(cli, "issue_info", return_value=self.issue_data), \
             patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(), 2)
        self.assertEqual(json.loads(out.getvalue())["state"], "BLOCKED")
        self.assertFalse(db.exists())

    def test_apply_creates_journal_and_clean_worktree(self):
        db = self.root / "journal" / "state.sqlite"
        argv = ["cli.py", "prepare", "--issue", "32", "--source", str(self.repo),
                "--state", str(db), "--apply"]
        with patch.object(cli, "issue_info", return_value=self.issue_data), \
             patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result["state"], "PREPARED")
        with Journal(db) as journal:
            record = journal.get(result["run_id"])
            self.assertEqual(record["source_sha"], git(self.repo, "rev-parse", "HEAD"))
            self.assertEqual(len(journal.events(result["run_id"])), 3)

    def test_interrupted_git_add_requires_recovery(self):
        db = self.root / "journal" / "state.sqlite"
        argv = ["cli.py", "prepare", "--issue", "32", "--source", str(self.repo),
                "--state", str(db), "--apply"]
        with patch.object(cli, "issue_info", return_value=self.issue_data), \
             patch.object(cli, "prepare", side_effect=WorktreeError("simulated")), \
             patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(cli.main(), 2)
        self.assertEqual(json.loads(out.getvalue())["state"], "BLOCKED")
        with Journal(db) as journal:
            self.assertEqual(journal.db.execute("SELECT state FROM jobs").fetchone()["state"],
                             "RECOVERY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
