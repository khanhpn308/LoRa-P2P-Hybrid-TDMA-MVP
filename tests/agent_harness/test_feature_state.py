"""Regression tests for P04 Feature State & Session Continuity (H2-STA-01..06)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))

import feature_state as fs
from p1.state import Journal, StateConflict
from p1.worktrees import make_plan, prepare


def _git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True, capture_output=True, check=True, timeout=20,
    )
    return p.stdout.strip()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sample_units(scope: list[str] | None = None) -> list[dict]:
    sc = scope or ["scripts/agent_harness/"]
    return [
        {
            "id": "U-01",
            "behavior": "Define and validate feature schema",
            "verification": {
                "criteria": ["Schema and transitions pass unit tests"],
                "commands": ["python3 -m unittest tests/agent_harness/test_feature_state.py"],
            },
            "dependencies": [],
            "scope": sc,
            "state": "PENDING",
        },
        {
            "id": "U-02",
            "behavior": "Integrate session-start and checkpoint CLI",
            "verification": {
                "criteria": ["Session start resumes without chat history"],
                "commands": ["python3 -m unittest tests/agent_harness/test_feature_state.py"],
            },
            "dependencies": ["U-01"],
            "scope": sc,
            "state": "PENDING",
        },
    ]


class FeatureStateUnitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "feature/429-test")
        _git(self.repo, "config", "user.name", "Harness Test")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "AGENTS.md").write_text("# Agents\nTest instructions\n", encoding="utf-8")
        (self.repo / "scripts" / "agent_harness").mkdir(parents=True)
        (self.repo / "scripts" / "agent_harness" / "mod.py").write_text("X = 1\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "initial")
        self.snap = fs.compute_candidate_snapshot(self.repo)
        self.issue_body = "## Target Directories (allowed paths)\n- `scripts/agent_harness/`\n"
        self.issue_sha = _sha256(self.issue_body.encode("utf-8"))

    def _new_doc(self, issue: int = 429) -> dict:
        return fs.create_feature_doc(
            issue,
            units=_sample_units(),
            title="P04 test",
            issue_sha256=self.issue_sha,
            approved_scope=["scripts/agent_harness/"],
            base_sha=self.snap["base_sha"],
            head_sha=self.snap["source_sha"],
            branch=self.snap["branch"],
            candidate_sha256=self.snap["candidate_sha256"],
        )

    def _valid_receipt(self, doc: dict, unit_id: str) -> dict:
        unit = next(u for u in doc["units"] if u["id"] == unit_id)
        return {
            "verified_by": "host_verifier",
            "status": "AUTO_CHECK_PASS",
            "exit_code": 0,
            "checks_complete": True,
            "source_sha": doc["git"]["head_sha"],
            "candidate_sha256": doc["git"]["candidate_sha256"],
            "verification_sha256": unit["verification"]["definition_sha256"],
            "receipt_path": "evidence/checks.log",
            "receipt_sha256": "a" * 64,
        }

    def test_schema_validation_rejects_malformed_duplicate_cycle_and_hygiene_violations(self):
        doc = self._new_doc()
        self.assertEqual(doc["schema_version"], "1.0")
        self.assertEqual(fs.normalize_unit_state("in_progress"), "ACTIVE")

        # Duplicate ID
        dup = json.loads(json.dumps(doc))
        dup["units"].append(json.loads(json.dumps(dup["units"][0])))
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(dup)

        # Malformed ID
        bad_id = json.loads(json.dumps(doc))
        bad_id["units"][0]["id"] = "../bad"
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(bad_id)

        # Missing dependency
        miss_dep = json.loads(json.dumps(doc))
        miss_dep["units"][1]["dependencies"] = ["U-999"]
        with self.assertRaises(fs.DependencyBlocked):
            fs.validate_feature_doc(miss_dep)

        # Dependency cycle
        cyc = json.loads(json.dumps(doc))
        cyc["units"][0]["dependencies"] = ["U-02"]
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(cyc)

        # Scope outside Issue approved_scope
        oob = json.loads(json.dumps(doc))
        oob["units"][0]["scope"] = ["contracts/api/openapi.yaml"]
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(oob)

        # Unknown state synonym
        with self.assertRaises(fs.ValidationError):
            fs.normalize_unit_state("done_ish")

        # Absolute machine path rejected
        abs_doc = json.loads(json.dumps(doc))
        abs_doc["handoff"]["next_action"] = "Check /home/alice/repo/file.py"
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(abs_doc)

        # Secret signature rejected
        sec_doc = json.loads(json.dumps(doc))
        sec_doc["handoff"]["next_action"] = "Use ghp_" + "A" * 24
        with self.assertRaises(fs.ValidationError):
            fs.validate_feature_doc(sec_doc)

    def test_schema_file_exists_and_matches_exported_top_level_keys(self):
        schema_path = (
            pathlib.Path(__file__).resolve().parents[2]
            / "docs" / "harness" / "features" / "schema.json"
        )
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        doc = self._new_doc()
        self.assertEqual(set(schema["required"]), set(doc.keys()))
        self.assertEqual(set(schema["properties"]["handoff"]["required"]), set(doc["handoff"].keys()))

    def test_wip_one_and_dependencies_enforced(self):
        doc = self._new_doc()
        # Cannot activate U-02 before dependency U-01 is PASSING
        with self.assertRaises(fs.DependencyBlocked):
            fs.activate_unit(doc, "U-02", actor="coordinator")

        # Activate U-01
        doc = fs.activate_unit(doc, "U-01", actor="coordinator", expected_revision=1)
        self.assertEqual(doc["handoff"]["active_unit"], "U-01")

        # WIP=1 rejects second active unit even if independent
        doc_indep = fs.create_feature_doc(
            429,
            units=[
                *_sample_units()[:1],
                {
                    "id": "U-03",
                    "behavior": "Independent unit",
                    "verification": {"criteria": ["ok"], "commands": ["true"]},
                    "dependencies": [],
                    "scope": ["scripts/agent_harness/"],
                    "state": "PENDING",
                },
            ],
            approved_scope=["scripts/agent_harness/"],
        )
        doc_indep = fs.activate_unit(doc_indep, "U-01")
        with self.assertRaises(fs.WIPViolation):
            fs.activate_unit(doc_indep, "U-03")

        # Blocking U-01 with reason releases active slot
        doc_blocked = fs.block_unit(doc_indep, "U-01", reason="Waiting for owner decision")
        doc_blocked = fs.activate_unit(doc_blocked, "U-03")
        self.assertEqual(doc_blocked["handoff"]["active_unit"], "U-03")

        # Blocking without reason fails
        with self.assertRaises(fs.ValidationError):
            fs.block_unit(doc, "U-01", reason="   ")

    def test_worker_waiver_commit_stale_and_tamper_cannot_grant_passing(self):
        doc = fs.activate_unit(self._new_doc(), "U-01")
        receipt = self._valid_receipt(doc, "U-01")

        # Worker cannot mark PASSING
        with self.assertRaises(fs.UnauthorizedTransition):
            fs.verify_unit_passing(doc, "U-01", actor="worker", receipt=receipt)

        # Waiver / commit_only / scope-only cannot mark PASSING
        for bad_flag in ({"waived": True}, {"owner_waived": True}, {"commit_only": True}, {"status": "SCOPE_SCAN_PASS_ONLY"}):
            bad = {**receipt, **bad_flag}
            with self.assertRaises(fs.UnauthorizedTransition):
                fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt=bad)

        # Incomplete or nonzero receipt rejected
        with self.assertRaises(fs.ValidationError):
            fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt={**receipt, "exit_code": 1})
        with self.assertRaises(fs.ValidationError):
            fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt={**receipt, "checks_complete": False})

        # Stale candidate SHA rejected
        with self.assertRaises(fs.RevisionConflict):
            fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt={**receipt, "candidate_sha256": "b" * 64})

        # Tampered verification definition rejected
        with self.assertRaises(fs.VerificationTamperError):
            fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt={**receipt, "verification_sha256": "c" * 64})

        # Stale CAS revision rejected
        with self.assertRaises(fs.RevisionConflict):
            fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt=receipt, expected_revision=1)

        # Valid host_verifier transition succeeds
        passed = fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt=receipt, expected_revision=2)
        u1 = passed["units"][0]
        self.assertEqual(u1["state"], "PASSING")
        self.assertEqual(len(u1["evidence_history"]), 1)

        # Unauthorized modification of verification definition fails
        with self.assertRaises(fs.VerificationTamperError):
            fs.reconcile_revision_drift(
                passed,
                current_source_sha=self.snap["source_sha"],
                current_candidate_sha256=self.snap["candidate_sha256"],
                current_verifications={"U-01": {"criteria": ["weakened"], "commands": ["true"]}},
                allow_definition_change=False,
            )

    def test_revision_drift_invalidates_passing_while_preserving_historic_evidence(self):
        doc = fs.activate_unit(self._new_doc(), "U-01")
        doc = fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt=self._valid_receipt(doc, "U-01"))
        old_cand = doc["git"]["candidate_sha256"]

        # Modify tracked file in repo
        (self.repo / "scripts" / "agent_harness" / "mod.py").write_text("X = 2\n", encoding="utf-8")
        new_snap = fs.compute_candidate_snapshot(self.repo)
        self.assertNotEqual(new_snap["candidate_sha256"], old_cand)

        drifted, info = fs.reconcile_revision_drift(
            doc,
            current_source_sha=new_snap["source_sha"],
            current_candidate_sha256=new_snap["candidate_sha256"],
        )
        self.assertEqual(info["stale_units"], ["U-01"])
        u1 = drifted["units"][0]
        self.assertEqual(u1["state"], "STALE")
        self.assertIsNone(u1["evidence"])
        # Historic evidence + invalidation record preserved
        self.assertEqual(len(u1["evidence_history"]), 2)
        self.assertEqual(u1["evidence_history"][0]["candidate_sha256"], old_cand)
        self.assertEqual(u1["evidence_history"][1]["status"], "INVALIDATED")

    def test_interrupted_session_and_fresh_session_durable_export_import(self):
        db_a = self.root / "host_a" / "state.sqlite"
        db_b = self.root / "host_b" / "state.sqlite"
        export_path = self.root / "handoff" / "issue-429.json"

        doc = fs.activate_unit(self._new_doc(), "U-01")
        doc = fs.verify_unit_passing(doc, "U-01", actor="host_verifier", receipt=self._valid_receipt(doc, "U-01"))
        doc = fs.activate_unit(doc, "U-02")

        with Journal(db_a) as journal:
            journal.plan(
                run_id="a" * 32,
                issue=429,
                source_sha=self.snap["base_sha"],
                issue_sha=self.issue_sha,
                branch=self.snap["branch"],
                worktree=self.repo,
                scope=("scripts/agent_harness/",),
            )
            # Simulate crash mid-PREPARING
            journal.transition("a" * 32, expected="PLANNED", next_state="PREPARING")
            journal.save_feature_snapshot(
                issue=429,
                expected_revision=None,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="coordinator",
            )

        # Uncommitted unfinished work must be preserved
        unfinished = self.repo / "scripts" / "agent_harness" / "wip.py"
        unfinished.write_text("# unfinished work\n", encoding="utf-8")

        issue_data = {"title": "P04 test", "body": self.issue_body, "scope": ("scripts/agent_harness/",), "issue_sha256": self.issue_sha}
        res_recover = fs.session_start(issue=429, repo=self.repo, state_db=db_a, issue_data=issue_data)
        self.assertEqual(res_recover["status"], "RECOVERY_REQUIRED")
        self.assertTrue(res_recover["has_uncommitted_work"])
        self.assertTrue(unfinished.exists())
        # U-01 should have become STALE due to wip.py changing candidate_sha256
        self.assertIn("U-01", res_recover["drift"]["stale_units"])

        # Checkpoint & export portable handoff from Session A
        ckpt = fs.session_checkpoint(
            issue=429,
            repo=self.repo,
            state_db=db_a,
            next_action="Re-verify U-01 and finish U-02",
            export_path=export_path,
        )
        self.assertEqual(ckpt["status"], "CHECKPOINT_SAVED")
        exported_text = export_path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), exported_text)

        # Fresh Session B imports handoff into a new SQLite journal without prior chat
        argv_imp = ["feature_state.py", "import", "--feature-file", str(export_path), "--state", str(db_b), "--repo", str(self.repo)]
        with patch.object(sys, "argv", argv_imp), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fs.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "IMPORTED")

        # Cancel interrupted run in db_b (db_b has no job row, only imported feature state)
        res_b = fs.session_start(issue=429, repo=self.repo, state_db=db_b, issue_data=issue_data)
        self.assertEqual(res_b["status"], "READY_TO_RESUME")
        self.assertEqual(res_b["units"]["active"], ["U-02"])
        self.assertEqual(res_b["units"]["stale"], ["U-01"])
        self.assertIn("U-02", res_b["next_action"])

        # Live Issue scope drift blocks safely without touching wip.py
        drifted_issue = {**issue_data, "issue_sha256": "f" * 64}
        res_drift = fs.session_start(issue=429, repo=self.repo, state_db=db_b, issue_data=drifted_issue)
        self.assertEqual(res_drift["status"], "BLOCKED")
        self.assertTrue(unfinished.exists())

    def test_concurrent_isolated_worktrees_for_distinct_issues(self):
        p1 = make_plan(self.repo, 429, "1" * 32)
        p2 = make_plan(self.repo, 430, "2" * 32)
        prepare(p1)
        prepare(p2)
        db = self.root / "shared" / "state.sqlite"

        for issue, plan in ((429, p1), (430, p2)):
            snap = fs.compute_candidate_snapshot(plan.target)
            doc = fs.create_feature_doc(
                issue,
                units=_sample_units(),
                approved_scope=["scripts/agent_harness/"],
                base_sha=snap["base_sha"],
                head_sha=snap["source_sha"],
                branch=snap["branch"],
                candidate_sha256=snap["candidate_sha256"],
            )
            doc = fs.activate_unit(doc, "U-01")
            with Journal(db) as journal:
                journal.save_feature_snapshot(
                    issue=issue,
                    expected_revision=None,
                    revision=doc["revision"],
                    doc_json=json.dumps(doc, sort_keys=True),
                    units=doc["units"],
                    actor="coordinator",
                )
            ckpt = fs.session_checkpoint(
                issue=issue,
                repo=plan.target,
                state_db=db,
                next_action=f"Continue Issue #{issue}",
            )
            self.assertEqual(ckpt["active_unit"], "U-01")

        # Unrelated issues did not lock each other
        with Journal(db) as journal:
            self.assertEqual(journal.get_feature_snapshot(429)["doc"]["handoff"]["active_unit"], "U-01")
            self.assertEqual(journal.get_feature_snapshot(430)["doc"]["handoff"]["active_unit"], "U-01")

    def test_cli_lifecycle_init_activate_verify_unit_checkpoint_and_reject_worker(self):
        db = self.root / "cli_host" / "state.sqlite"
        units_file = self.root / "units.json"
        units_file.write_text(json.dumps(_sample_units()), encoding="utf-8")
        export_file = self.root / "export" / "issue-429.json"

        def run_cli(*argv: str) -> tuple[int, dict]:
            with patch.object(sys, "argv", ["feature_state.py", *argv]), \
                 contextlib.redirect_stdout(io.StringIO()) as out:
                rc = fs.main()
            return rc, json.loads(out.getvalue())

        rc, res = run_cli("init", "--issue", "429", "--repo", str(self.repo),
                          "--units-file", str(units_file), "--state", str(db), "--offline")
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "INITIALIZED")

        rc, res = run_cli("activate", "--issue", "429", "--unit-id", "U-01",
                          "--expected-revision", "1", "--state", str(db))
        self.assertEqual(rc, 0)
        self.assertEqual(res["revision"], 2)

        # Stale CAS fails
        rc, res = run_cli("activate", "--issue", "429", "--unit-id", "U-02",
                          "--expected-revision", "1", "--state", str(db))
        self.assertEqual(rc, 2)
        self.assertEqual(res["status"], "BLOCKED")

        # Worker cannot verify-unit via CLI
        with Journal(db) as journal:
            doc = journal.get_feature_snapshot(429)["doc"]
        receipt_file = self.root / "receipt.json"
        receipt_file.write_text(json.dumps(self._valid_receipt(doc, "U-01")), encoding="utf-8")

        rc, res = run_cli("verify-unit", "--issue", "429", "--unit-id", "U-01",
                          "--receipt", str(receipt_file), "--actor", "worker", "--state", str(db))
        self.assertEqual(rc, 2)
        self.assertEqual(res["status"], "BLOCKED")

        # Host verifier succeeds
        rc, res = run_cli("verify-unit", "--issue", "429", "--unit-id", "U-01",
                          "--receipt", str(receipt_file), "--actor", "host_verifier", "--state", str(db))
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "PASSING")

        # Checkpoint + export + validate
        rc, res = run_cli("checkpoint", "--issue", "429", "--repo", str(self.repo),
                          "--state", str(db), "--next-action", "Activate U-02",
                          "--export", str(export_file))
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "CHECKPOINT_SAVED")

        rc, res = run_cli("validate", "--feature-file", str(export_file))
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "VALID")

        rc, res = run_cli("session-start", "--issue", "429", "--repo", str(self.repo),
                          "--state", str(db), "--offline")
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "READY_TO_RESUME")
        self.assertEqual(res["units"]["passing"], ["U-01"])


if __name__ == "__main__":
    unittest.main()
