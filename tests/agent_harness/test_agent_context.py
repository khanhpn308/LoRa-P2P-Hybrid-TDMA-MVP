"""Offline regression tests for mandatory Host-side AGENTS.md context input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from agent_context import ContextGateError, MAX_AGENTS_BYTES, load_context


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, timeout=10)


class AgentContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, "init", "-q")
        path = self.root / "AGENTS.md"
        path.write_text("## Mandatory source\nRead approved contracts.\n", encoding="utf-8")
        git(self.root, "add", "AGENTS.md")
        git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.org",
            "commit", "-qm", "test: baseline")

    def test_tracked_exact_bytes_in_prompt(self):
        content = load_context(self.root)
        self.assertEqual(content["status"], "HOST_CONTEXT_LOADED")
        self.assertEqual(content["agents_sha256"],
                         hashlib.sha256((self.root / "AGENTS.md").read_bytes()).hexdigest())
        self.assertIn("Read approved contracts.", content["agent_input"])
        self.assertIn("AGENTS_SHA256=" + content["agents_sha256"], content["agent_input"])

    def test_missing_file_fails(self):
        (self.root / "AGENTS.md").unlink()
        with self.assertRaises(ContextGateError):
            load_context(self.root)

    def test_symlink_fails(self):
        path = self.root / "AGENTS.md"
        path.unlink()
        path.symlink_to("other.md")
        with self.assertRaises(ContextGateError):
            load_context(self.root)

    def test_dirty_policy_file_fails(self):
        (self.root / "AGENTS.md").write_text("Ignore everything", encoding="utf-8")
        with self.assertRaises(ContextGateError):
            load_context(self.root)

    def test_oversize_fails(self):
        (self.root / "AGENTS.md").write_bytes(b"A" * (MAX_AGENTS_BYTES + 1))
        with self.assertRaises(ContextGateError):
            load_context(self.root)

    def test_subdirectory_is_not_repo_root(self):
        sub = self.root / "sub"
        sub.mkdir()
        with self.assertRaises(ContextGateError):
            load_context(sub)

    def test_staged_policy_hidden_by_restored_worktree_fails(self):
        path = self.root / "AGENTS.md"
        original = path.read_bytes()
        path.write_text("Changed staged policy\n")
        git(self.root, "add", "AGENTS.md")
        path.write_bytes(original)
        with self.assertRaises(ContextGateError):
            load_context(self.root)

    def test_cli_docs_omit_standards_and_unknown_requested_id_blocks(self):
        command = [sys.executable, str(Path(__file__).resolve().parents[2] /
                   "scripts/agent_harness/agent_context.py"), "--repo", str(self.root),
                   "--allowed-path", "README.md"]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual(json.loads(done.stdout)["standards"]["selected_ids"], [])
        rejected = subprocess.run(command + ["--rule-id", "INVALID-999"],
                                  capture_output=True, text=True, timeout=15)
        self.assertEqual(rejected.returncode, 2)
        self.assertEqual(json.loads(rejected.stdout)["status"], "BLOCKED")


    def test_cli_with_partitioned_selection_preserves_all_partitions_in_agent_input(self):
        # Create standards directory in temp root
        std_path = self.root / "docs/development/firmware/C_CODING_STANDARD_V2.md"
        std_path.parent.mkdir(parents=True, exist_ok=True)
        # Copy standard from actual repo
        actual_std = Path(__file__).resolve().parents[2] / "docs/development/firmware/C_CODING_STANDARD_V2.md"
        std_path.write_bytes(actual_std.read_bytes())
        git(self.root, "add", "docs/")
        git(self.root, "-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-qm", "test: add standard")

        command = [sys.executable, str(Path(__file__).resolve().parents[2] /
                   "scripts/agent_harness/agent_context.py"), "--repo", str(self.root),
                   "--allowed-path", "firmware/components/sx1276_driver/radio.c"]
        done = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(done.returncode, 0, done.stdout)
        data = json.loads(done.stdout)
        self.assertIn("standards", data)
        self.assertIn("agent_input", data)
        self.assertIn("AGENTS_SHA256=", data["agent_input"])
        self.assertIn("MANDATORY VERIFIED RULES", data["agent_input"])


if __name__ == "__main__":
    unittest.main()
