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

    def test_legacy_journal_migrates_and_enforces_sqlite_wip_and_cas(self):
        import json
        import sqlite3

        # Simulate a pre-P04 SQLite journal containing only jobs and events.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.executescript("""
            CREATE TABLE jobs (
                run_id TEXT PRIMARY KEY,
                issue INTEGER NOT NULL,
                state TEXT NOT NULL,
                source_sha TEXT NOT NULL,
                issue_sha TEXT NOT NULL,
                branch TEXT NOT NULL,
                worktree TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            INSERT INTO jobs(run_id, issue, state, source_sha, issue_sha, branch, worktree, scope_json)
            VALUES ('legacyrun00000000000000000000001', 429, 'PREPARED', '0000000000000000000000000000000000000000',
                    '1111111111111111111111111111111111111111111111111111111111111111',
                    'feature/429-legacy', 'wt', '["scripts/agent_harness/"]');
        """)
        conn.commit()
        conn.close()

        with Journal(self.path) as state:
            job = state.active_job_for_issue(429)
            self.assertIsNotNone(job)
            self.assertEqual(job["run_id"], "legacyrun00000000000000000000001")

            units_active_two = [
                {"id": "U1", "state": "ACTIVE", "verification": {"definition_sha256": "a" * 64}},
                {"id": "U2", "state": "ACTIVE", "verification": {"definition_sha256": "b" * 64}},
            ]
            with self.assertRaises(StateConflict):
                state.save_feature_snapshot(
                    issue=429,
                    expected_revision=None,
                    revision=1,
                    doc_json=json.dumps({"issue": 429, "revision": 1, "units": units_active_two}),
                    units=units_active_two,
                    actor="coordinator",
                )

            units_ok = [
                {"id": "U1", "state": "ACTIVE", "verification": {"definition_sha256": "a" * 64}},
                {"id": "U2", "state": "PENDING", "verification": {"definition_sha256": "b" * 64}},
            ]
            state.save_feature_snapshot(
                issue=429,
                expected_revision=None,
                revision=1,
                doc_json=json.dumps({"issue": 429, "revision": 1, "units": units_ok}),
                units=units_ok,
                actor="coordinator",
            )
            with self.assertRaises(StateConflict):
                state.save_feature_snapshot(
                    issue=429,
                    expected_revision=99,
                    revision=2,
                    doc_json=json.dumps({"issue": 429, "revision": 2, "units": units_ok}),
                    units=units_ok,
                    actor="coordinator",
                )

            # Journal MUST reject PASSING without sealed HostVerificationProof
            units_fake_pass = [
                {
                    "id": "U1",
                    "state": "PASSING",
                    "verification": {"definition_sha256": "a" * 64},
                    "evidence": {
                        "verified_by": "host_verifier",
                        "status": "AUTO_CHECK_PASS",
                        "exit_code": 0,
                        "source_sha": "0" * 40,
                        "candidate_sha256": "c" * 64,
                        "verification_sha256": "a" * 64,
                        "receipt_path": "unit.log",
                        "receipt_sha256": "d" * 64,
                    },
                },
                {"id": "U2", "state": "PENDING", "verification": {"definition_sha256": "b" * 64}},
            ]
            with self.assertRaises(StateConflict):
                state.save_feature_snapshot(
                    issue=429,
                    expected_revision=1,
                    revision=2,
                    doc_json=json.dumps({"issue": 429, "revision": 2, "units": units_fake_pass}),
                    units=units_fake_pass,
                    actor="host_verifier",
                )

            # Journal MUST reject PENDING -> PASSING even with a HostVerificationProof
            from p1.state import issue_host_proof
            proof_u2 = issue_host_proof(
                issue=429,
                unit_id="U2",
                verification_sha256="b" * 64,
                source_sha="0" * 40,
                candidate_sha256="c" * 64,
                manifest_sha256="e" * 64,
                runner_sha256="f" * 64,
                receipt_path="unit.log",
                receipt_sha256="d" * 64,
                gate_rule_id="TOOLING-CHECK",
                auto_check="AUTO_CHECK_PASS",
            )
            units_skip = [
                {"id": "U1", "state": "ACTIVE", "verification": {"definition_sha256": "a" * 64}},
                {
                    "id": "U2",
                    "state": "PASSING",
                    "verification": {"definition_sha256": "b" * 64},
                    "evidence": {
                        "verified_by": "host_verifier",
                        "status": "AUTO_CHECK_PASS",
                        "exit_code": 0,
                        "source_sha": "0" * 40,
                        "candidate_sha256": "c" * 64,
                        "verification_sha256": "b" * 64,
                        "receipt_path": "unit.log",
                        "receipt_sha256": "d" * 64,
                    },
                },
            ]
            with self.assertRaises(StateConflict):
                state.save_feature_snapshot(
                    issue=429,
                    expected_revision=1,
                    revision=2,
                    doc_json=json.dumps({"issue": 429, "revision": 2, "units": units_skip}),
                    units=units_skip,
                    actor="host_verifier",
                    host_proofs={"U2": proof_u2},
                )

            # Atomic save_checkpoint_and_snapshot rejects CAS conflict without inserting checkpoint
            with self.assertRaises(StateConflict):
                state.save_checkpoint_and_snapshot(
                    issue=429,
                    run_id="legacyrun00000000000000000000001",
                    revision_sha="0" * 40,
                    candidate_sha256="c" * 64,
                    branch="feature/429-legacy",
                    worktree_rel=".",
                    active_unit="U1",
                    blocker="",
                    next_action="Should not persist",
                    decision_refs=["OD-02"],
                    issue_sha256="1" * 64,
                    handoff_json=json.dumps({"active_unit": "U1", "next_action": "Should not persist"}),
                    snapshot_args={
                        "issue": 429,
                        "expected_revision": 99,
                        "revision": 2,
                        "doc_json": json.dumps({"issue": 429, "revision": 2, "units": units_ok}),
                        "units": units_ok,
                        "actor": "coordinator",
                    },
                )
            self.assertIsNone(state.latest_checkpoint(429))

            ckpt_id = state.record_checkpoint(
                issue=429,
                run_id="legacyrun00000000000000000000001",
                revision_sha="0" * 40,
                candidate_sha256="c" * 64,
                branch="feature/429-legacy",
                worktree_rel=".",
                active_unit="U1",
                blocker="",
                next_action="Finish U1",
                decision_refs=["OD-02"],
                issue_sha256="1" * 64,
                handoff_json=json.dumps({"active_unit": "U1", "next_action": "Finish U1"}),
            )
            self.assertGreaterEqual(ckpt_id, 1)
            self.assertEqual(state.latest_checkpoint(429)["active_unit"], "U1")


if __name__ == "__main__":
    unittest.main()
