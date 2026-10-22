"""P1 SQLite journal: atomic lifecycle, single active Issue, explicit recovery."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1.state import Journal, StateConflict


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = pathlib.Path(self.temp.name) / "hidden" / "state.sqlite"

    def add(self, store, run="a" * 32, issue=32):
        store.plan(run_id=run, issue=issue, source_sha="0" * 40, issue_sha="1" * 64,
                   branch="feature/32-agent-aaaaaaaa",
                   worktree=pathlib.Path(self.temp.name) / "worktree",
                   scope=("scripts/agent_harness/p1/",))

    def test_checkpoint_restart_and_event_log(self):
        with Journal(self.path) as state:
            self.add(state)
            state.transition("a" * 32, expected="PLANNED", next_state="PREPARING")
            state.transition("a" * 32, expected="PREPARING", next_state="PREPARED")
            self.assertEqual([x["to_state"] for x in state.events("a" * 32)],
                             ["PLANNED", "PREPARING", "PREPARED"])
        with Journal(self.path) as reopened:
            self.assertEqual(reopened.get("a" * 32)["state"], "PREPARED")

    def test_prevent_parallel_active_issue(self):
        with Journal(self.path) as state:
            self.add(state)
            with self.assertRaises(StateConflict):
                self.add(state, run="b" * 32)
            self.assertEqual(state.get("a" * 32)["state"], "PLANNED")

    def test_optimistic_concurrency_and_no_fabricated_pass(self):
        with Journal(self.path) as state:
            self.add(state)
            with self.assertRaises(StateConflict):
                state.transition("a" * 32, expected="PREPARING", next_state="PREPARED")
            with self.assertRaises(StateConflict):
                state.transition("a" * 32, expected="PLANNED", next_state="PREPARED")
            with self.assertRaises(StateConflict):
                state.transition("a" * 32, expected="PLANNED", next_state="RF_VERIFIED")
            self.assertEqual(len(state.events("a" * 32)), 1)

    def test_interrupted_preparation_is_not_auto_resumed(self):
        with Journal(self.path) as state:
            self.add(state)
            state.transition("a" * 32, expected="PLANNED", next_state="PREPARING")
            self.assertTrue(state.detect_interruption("a" * 32))
            self.assertEqual(state.get("a" * 32)["state"], "RECOVERY_REQUIRED")
            self.assertFalse(state.detect_interruption("a" * 32))
            with self.assertRaises(StateConflict):
                state.transition("a" * 32, expected="RECOVERY_REQUIRED",
                                 next_state="PREPARED")

    def test_db_is_private_and_symlinks_are_rejected(self):
        with Journal(self.path) as state:
            self.add(state)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        redirect = pathlib.Path(self.temp.name) / "alias.sqlite"
        redirect.symlink_to(self.path)
        with self.assertRaises(StateConflict):
            Journal(redirect)

    def test_unknown_run_id_fails(self):
        with Journal(self.path) as state:
            with self.assertRaises(StateConflict):
                state.get("unknown")


if __name__ == "__main__":
    unittest.main()
