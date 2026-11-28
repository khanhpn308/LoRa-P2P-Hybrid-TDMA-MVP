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
                trusted_definition_sha256="b" * 64,
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

            # Journal doc and unit projection disagreement MUST fail closed
            state.db.execute("UPDATE feature_units SET state='PASSING' WHERE issue=429 AND unit_id='U1'")
            with self.assertRaises(StateConflict):
                state.get_feature_snapshot(429)

            # verify_host_proof rejects missing or mismatched trusted_definition_sha256
            proof_missing_td = issue_host_proof(
                issue=429,
                unit_id="U1",
                verification_sha256="a" * 64,
                source_sha="0" * 40,
                candidate_sha256="c" * 64,
                manifest_sha256="e" * 64,
                runner_sha256="f" * 64,
                receipt_path="unit.log",
                receipt_sha256="d" * 64,
                gate_rule_id="TOOLING-CHECK",
                auto_check="AUTO_CHECK_PASS",
            )
            unit_u1 = {
                "id": "U1",
                "verification": {"definition_sha256": "a" * 64},
                "evidence": {
                    "source_sha": "0" * 40,
                    "candidate_sha256": "c" * 64,
                    "receipt_path": "unit.log",
                    "receipt_sha256": "d" * 64,
                    "verification_sha256": "a" * 64,
                },
            }
            from p1.state import verify_host_proof
            with self.assertRaises(StateConflict):
                verify_host_proof(proof_missing_td, issue=429, unit=unit_u1)

    def test_p08b_control_rounds_persistence_and_legacy_streak_migration(self):
        import json
        import sqlite3

        # Simulate a P08-A journal without streak_* columns or control_rounds table.
        legacy_db = pathlib.Path(self.temp.name) / "legacy_p08a" / "state.sqlite"
        legacy_db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(legacy_db))
        conn.executescript("""
            CREATE TABLE control_runs (
                run_id TEXT PRIMARY KEY,
                issue INTEGER NOT NULL CHECK(issue > 0),
                state TEXT NOT NULL,
                active_role TEXT,
                dispatch_seq INTEGER NOT NULL DEFAULT 0,
                dispatch_token TEXT NOT NULL DEFAULT '',
                round_num INTEGER NOT NULL DEFAULT 0,
                consecutive_passes INTEGER NOT NULL DEFAULT 0,
                no_progress_count INTEGER NOT NULL DEFAULT 0,
                last_failure_sig TEXT NOT NULL DEFAULT '',
                last_diff_sha256 TEXT NOT NULL DEFAULT '',
                source_sha TEXT NOT NULL,
                base_sha TEXT NOT NULL,
                candidate_sha256 TEXT NOT NULL,
                branch TEXT NOT NULL,
                worktree TEXT NOT NULL,
                agents_sha256 TEXT NOT NULL,
                selection_sha256 TEXT NOT NULL,
                check_plan_sha256 TEXT NOT NULL,
                policy_sha256 TEXT NOT NULL,
                policy_json TEXT NOT NULL,
                admission_json TEXT NOT NULL,
                budget_consumed_json TEXT NOT NULL,
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                cancel_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE control_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                from_state TEXT,
                to_state TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                dispatch_token TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}',
                utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
        """)
        conn.commit()
        conn.close()

        with Journal(legacy_db) as state:
            cols = {r["name"] for r in state.db.execute("PRAGMA table_info(control_runs)").fetchall()}
            self.assertIn("streak_candidate_sha256", cols)
            self.assertIn("streak_policy_sha256", cols)
            run = state.create_control_run(
                run_id="run-p08b-mig",
                issue=439,
                source_sha="0" * 40,
                base_sha="0" * 40,
                candidate_sha256="1" * 64,
                branch="feature/439-mig",
                worktree="/tmp/wt",
                agents_sha256="2" * 64,
                selection_sha256="3" * 64,
                check_plan_sha256="4" * 64,
                policy_sha256="5" * 64,
                policy={"consecutive_passes_required": 2, "max_rounds": 3},
                admission={"issue": 439},
            )
            self.assertEqual(run["state"], "ADMITTED")
            d1 = state.acquire_dispatch(
                "run-p08b-mig", expected_state="ADMITTED", role="checker", actor_role="host", dispatch_token="tok-1"
            )
            self.assertEqual(d1["state"], "DISPATCHED")
            state.transition_control_run(
                "run-p08b-mig", expected="DISPATCHED", next_state="CHECKING", actor_role="host",
                action="checker_started", expected_dispatch_token="tok-1",
            )
            upd = state.transition_control_run(
                "run-p08b-mig", expected="CHECKING", next_state="REPAIR_REQUIRED", actor_role="host",
                action="await_next_consecutive_pass", expected_dispatch_token="tok-1", clear_dispatch=True,
                update_fields={
                    "round_num": 1,
                    "consecutive_passes": 1,
                    "streak_candidate_sha256": "1" * 64,
                    "streak_policy_sha256": "5" * 64,
                },
                round_record={
                    "round_num": 1,
                    "maker_dispatched": False,
                    "confirming_pass": False,
                    "outcome": "PASS",
                    "verdict": "ACCEPT",
                    "candidate_sha256": "1" * 64,
                    "policy_sha256": "5" * 64,
                    "evidence_refs": {
                        "round_dir": "round-01",
                        "checks_summary": "round-01/checks_summary.json",
                        "auditor_report": "round-01/audit_report.json",
                    },
                    "host_checks_passed": True,
                    "checker_passed": True,
                    "rubric_decision": "ACCEPT",
                    "rubric_total_score": 12,
                    "rubric_hard_gate_passed": True,
                    "findings": [],
                    "repair_scope": [],
                    "next_action": "Confirming pass",
                    "consecutive_passes": 1,
                },
            )
            self.assertEqual(upd["streak_candidate_sha256"], "1" * 64)
            # Confirming pass transition REPAIR_REQUIRED -> VERIFYING is allowed
            ver = state.transition_control_run(
                "run-p08b-mig", expected="REPAIR_REQUIRED", next_state="VERIFYING", actor_role="host",
                action="confirming_host_verifying",
            )
            self.assertEqual(ver["state"], "VERIFYING")
            rounds = state.list_control_rounds("run-p08b-mig")
            self.assertEqual(len(rounds), 1)
            self.assertEqual(rounds[0]["verdict"], "ACCEPT")
            self.assertEqual(rounds[0]["rubric_total_score"], 12)
            self.assertEqual(rounds[0]["evidence_refs"]["checks_summary"], "round-01/checks_summary.json")
            self.assertEqual(rounds[0]["evidence_refs"]["auditor_report"], "round-01/audit_report.json")
            self.assertEqual(json.loads(json.dumps(rounds[0]["findings"])), [])

    def test_p08c_durable_progress_lease_columns_and_signal_prune_separation(self):
        with Journal(self.path) as state:
            cols = {r["name"] for r in state.db.execute("PRAGMA table_info(control_runs)").fetchall()}
            for expected_col in (
                "evidence_dir",
                "frozen_plan_json",
                "lease_owner_pid",
                "lease_owner_start_ticks",
                "lease_owner_host",
                "in_flight_round",
                "last_completed_op",
                "completed_ops_json",
                "recovery_reason",
                "resume_phase",
                "next_action",
                "blocker",
            ):
                self.assertIn(expected_col, cols)

            run = state.create_control_run(
                run_id="run-p08c-prog",
                issue=441,
                source_sha="0" * 40,
                base_sha="0" * 40,
                candidate_sha256="1" * 64,
                branch="feature/441-prog",
                worktree="/tmp/wt441",
                agents_sha256="2" * 64,
                selection_sha256="3" * 64,
                check_plan_sha256="4" * 64,
                policy_sha256="5" * 64,
                policy={"max_rounds": 3, "max_wall_seconds": 60},
                admission={"issue": 441},
                evidence_dir="/tmp/ev441",
                frozen_plan={"plan_sha256": "4" * 64, "checks": []},
            )
            self.assertEqual(run["evidence_dir"], "/tmp/ev441")
            self.assertEqual(run["last_completed_op"], "admitted")
            self.assertEqual(run["resume_phase"], "")
            ev_run = state.record_control_event(
                "run-p08c-prog",
                expected_state="ADMITTED",
                actor_role="host",
                action="persist_resume_phase",
                resume_phase="VERIFY_AND_CHECK",
            )
            self.assertEqual(ev_run["resume_phase"], "VERIFY_AND_CHECK")

            d = state.acquire_dispatch(
                "run-p08c-prog",
                expected_state="ADMITTED",
                role="maker",
                actor_role="host",
                dispatch_token="tok-p08c",
                lease_owner_pid=12345,
                lease_owner_start_ticks="99999",
                lease_owner_host="host-a",
                in_flight_round=1,
            )
            self.assertEqual(d["lease_owner_pid"], 12345)
            self.assertEqual(d["lease_owner_start_ticks"], "99999")
            self.assertEqual(d["in_flight_round"], 1)

            state.transition_control_run(
                "run-p08c-prog",
                expected="DISPATCHED",
                next_state="MAKER_RUNNING",
                actor_role="host",
                action="maker_started",
                expected_dispatch_token="tok-p08c",
            )
            prog = state.record_control_progress(
                "run-p08c-prog",
                expected_state="MAKER_RUNNING",
                actor_role="host",
                op="maker_completed",
                expected_dispatch_token="tok-p08c",
                wall_elapsed_delta_s=12.5,
                in_flight_round=1,
                candidate_sha256="a" * 64,
            )
            self.assertEqual(prog["budget_consumed"]["wall_seconds"], 12.5)
            self.assertEqual(prog["last_completed_op"], "maker_completed")
            self.assertEqual(prog["candidate_sha256"], "a" * 64)

            with self.assertRaises(StateConflict):
                state.record_control_progress(
                    "run-p08c-prog",
                    expected_state="MAKER_RUNNING",
                    actor_role="host",
                    op="stale",
                    expected_dispatch_token="wrong-tok",
                    wall_elapsed_delta_s=5.0,
                )

            for idx in range(5):
                state.record_signal(
                    signal_type="process",
                    category="control_plane",
                    owning_domain="harness",
                    status="PASS",
                    captured=True,
                    issue=441,
                    run_id="run-p08c-prog",
                    check_id=f"sig-{idx}",
                )
            deleted = state.prune_signals(keep=2)
            self.assertEqual(deleted, 3)
            # Pruning telemetry NEVER removes control_runs or control_events
            self.assertEqual(state.get_control_run("run-p08c-prog")["run_id"], "run-p08c-prog")
            self.assertGreaterEqual(len(state.control_events("run-p08c-prog")), 3)

    def test_improvement_experiment_cas_immutability_and_redaction(self):
        fake_tok = "ghp_" + "B" * 24
        with Journal(self.path) as state:
            created = state.create_experiment(
                experiment_id="EXP-STATE-01",
                issue=443,
                mode="CONTROLLED_FIXTURE",
                hypothesis=f"Test experiment persistence token={fake_tok}",
                attributed_subsystem="instructions",
                target_metric="instruction_snr",
                baseline_revision="a" * 40,
                allowed_paths=["docs/routing_note.md"],
                plan_sha256="1" * 64,
                oracle_sha256="2" * 64,
                holdout_sha256="3" * 64,
                evaluator_sha256="4" * 64,
                policy_sha256="5" * 64,
                plan={"experiment_id": "EXP-STATE-01"},
                budget_limit={"max_wall_seconds": 30, "max_rounds": 1},
            )
            self.assertEqual(created["state"], "PLANNED")
            self.assertNotIn(fake_tok, created["hypothesis"])

            # Frozen digest columns cannot be overwritten after creation
            with self.assertRaises(StateConflict):
                state.update_experiment(
                    "EXP-STATE-01",
                    expected_state="PLANNED",
                    next_state="BASELINE_RUNNING",
                    actor_role="host",
                    action="tamper_oracle",
                    update_fields={"oracle_sha256": "9" * 64},
                )

            # CAS mismatch rejected
            with self.assertRaises(StateConflict):
                state.update_experiment(
                    "EXP-STATE-01",
                    expected_state="EVALUATING",
                    next_state="DECIDED",
                    actor_role="host",
                    action="bad_cas",
                )

            # Illegal transition rejected
            with self.assertRaises(StateConflict):
                state.update_experiment(
                    "EXP-STATE-01",
                    expected_state="PLANNED",
                    next_state="RECOVERED",
                    actor_role="host",
                    action="skip_steps",
                )

            state.update_experiment(
                "EXP-STATE-01",
                expected_state="PLANNED",
                next_state="DECIDED",
                actor_role="orchestrator",
                action="decide",
                update_fields={"decision": "REJECT", "decision_reason": "No gain"},
            )
            rec = state.update_experiment(
                "EXP-STATE-01",
                expected_state="DECIDED",
                next_state="RECOVERED",
                actor_role="host",
                action="recover",
            )
            self.assertEqual(rec["state"], "RECOVERED")
            self.assertEqual(rec["decision"], "REJECT")
            self.assertEqual(len(state.experiment_events("EXP-STATE-01")), 3)
            self.assertEqual(len(state.list_experiments(issue=443, decision="REJECT")), 1)


if __name__ == "__main__":
    unittest.main()
