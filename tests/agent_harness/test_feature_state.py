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
from p1.state import HostVerificationProof, Journal, StateConflict, issue_host_proof
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
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")
        (self.repo / "scripts" / "agent_harness" / "mod.py").write_text("X = 10\n", encoding="utf-8")
        _git(self.repo, "add", "scripts/agent_harness/mod.py")
        _git(self.repo, "commit", "-qm", "work on unit")
        self.snap = fs.compute_candidate_snapshot(self.repo, base_sha=self.base_sha)
        self.issue_body = "## Target Directories (allowed paths)\n- `scripts/agent_harness/`\n"
        self.issue_sha = _sha256(self.issue_body.encode("utf-8"))

    def _new_doc(self, issue: int = 429) -> dict:
        return fs.create_feature_doc(
            issue,
            units=_sample_units(),
            title="P04 test",
            issue_sha256=self.issue_sha,
            approved_scope=["scripts/agent_harness/"],
            base_sha=self.base_sha,
            head_sha=self.snap["source_sha"],
            branch=self.snap["branch"],
            candidate_sha256=self.snap["candidate_sha256"],
        )

    def _write_host_evidence(
        self,
        doc: dict,
        unit_id: str,
        *,
        dirname: str = "ev",
        command: list[str] | None = None,
        checks_complete: bool = True,
        exit_code: int = 0,
        tamper_receipt_sha: bool = False,
        extra_flags: dict | None = None,
    ) -> pathlib.Path:
        ev_dir = self.root / dirname
        ev_dir.mkdir(parents=True, exist_ok=True)
        log_path = ev_dir / "unit.log"
        log_bytes = b"Ran 1 test in 0.01s\nOK\n"
        log_path.write_bytes(log_bytes)
        log_sha = "f" * 64 if tamper_receipt_sha else _sha256(log_bytes)
        unit = next(u for u in doc["units"] if u["id"] == unit_id)
        cmd = command or ["python3", "-m", "unittest", "tests/agent_harness/test_feature_state.py"]
        entry = {
            "source_sha": doc["git"]["head_sha"],
            "candidate_sha256": doc["git"]["candidate_sha256"],
            "command": cmd,
            "exit_code": exit_code,
            "tool_version": "Python 3.12.3",
            "receipt_path": "unit.log",
            "receipt_sha256": log_sha,
            "observations": {
                "checks_complete": checks_complete,
                "verification_sha256": unit["verification"]["definition_sha256"],
            },
        }
        if extra_flags:
            entry.update(extra_flags)
        manifest = {"checks": {"TOOLING-CHECK": dict(entry), "SECURITY-CHECK": dict(entry)}}
        (ev_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return ev_dir

    def _verify_real(self, doc: dict, unit_id: str, *, dirname: str = "ev") -> tuple[dict, HostVerificationProof]:
        ev_dir = self._write_host_evidence(doc, unit_id, dirname=dirname)
        proof = fs.verify_host_gate_evidence(
            doc,
            unit_id,
            repo=self.repo,
            base_sha=doc["git"]["base_sha"],
            evidence_dir=ev_dir,
        )
        return fs.verify_unit_passing(doc, unit_id, proof=proof), proof

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

    def test_self_declared_receipt_actor_forged_proof_and_tamper_cannot_grant_passing(self):
        doc = fs.activate_unit(self._new_doc(), "U-01")

        # Raw dict / self-declared actor or receipt JSON rejected
        with self.assertRaises(fs.UnauthorizedTransition):
            fs.verify_unit_passing(doc, "U-01", proof={"verified_by": "host_verifier", "status": "PASS"})  # type: ignore[arg-type]

        # Forged HostVerificationProof with invalid seal rejected
        forged_proof = HostVerificationProof(
            issue=429,
            unit_id="U-01",
            verification_sha256=doc["units"][0]["verification"]["definition_sha256"],
            source_sha=doc["git"]["head_sha"],
            candidate_sha256=doc["git"]["candidate_sha256"],
            manifest_sha256="a" * 64,
            runner_sha256="b" * 64,
            receipt_path="unit.log",
            receipt_sha256="c" * 64,
            gate_rule_id="TOOLING-CHECK",
            auto_check="AUTO_CHECK_PASS",
            _seal=b"forged" * 5 + b"xx",
        )
        with self.assertRaises(StateConflict):
            fs.verify_unit_passing(doc, "U-01", proof=forged_proof)

        # Evidence inside candidate repo rejected
        inside_dir = self.repo / "inside_ev"
        inside_dir.mkdir()
        with self.assertRaises(fs.ValidationError):
            fs.verify_host_gate_evidence(
                doc, "U-01", repo=self.repo, base_sha=self.base_sha, evidence_dir=inside_dir
            )

        # Waiver / commit_only / nonzero exit / incomplete checks / tampered receipt hash rejected
        for kwargs in (
            {"dirname": "ev_waive", "extra_flags": {"waived": True}},
            {"dirname": "ev_owner", "extra_flags": {"owner_waived": True}},
            {"dirname": "ev_commit", "extra_flags": {"commit_only": True}},
            {"dirname": "ev_exit", "exit_code": 1},
            {"dirname": "ev_inc", "checks_complete": False},
            {"dirname": "ev_hash", "tamper_receipt_sha": True},
        ):
            ev = self._write_host_evidence(doc, "U-01", **kwargs)
            with self.assertRaises(fs.UnauthorizedTransition):
                fs.verify_host_gate_evidence(
                    doc, "U-01", repo=self.repo, base_sha=self.base_sha, evidence_dir=ev
                )

        # Unrelated command without matching verification definition rejected
        ev_wrong_cmd = self._write_host_evidence(doc, "U-01", dirname="ev_cmd", command=["echo", "fake"])
        manifest_obj = json.loads((ev_wrong_cmd / "manifest.json").read_text())
        for c in manifest_obj["checks"].values():
            c["observations"].pop("verification_sha256", None)
        (ev_wrong_cmd / "manifest.json").write_text(json.dumps(manifest_obj))
        with self.assertRaises(fs.ValidationError):
            fs.verify_host_gate_evidence(
                doc, "U-01", repo=self.repo, base_sha=self.base_sha, evidence_dir=ev_wrong_cmd
            )

        # Real trusted Host quality_gates evaluation succeeds
        ev_ok = self._write_host_evidence(doc, "U-01", dirname="ev_ok")
        proof = fs.verify_host_gate_evidence(
            doc, "U-01", repo=self.repo, base_sha=self.base_sha, evidence_dir=ev_ok
        )

        # Stale CAS revision rejected
        with self.assertRaises(fs.RevisionConflict):
            fs.verify_unit_passing(doc, "U-01", proof=proof, expected_revision=1)

        passed = fs.verify_unit_passing(doc, "U-01", proof=proof, expected_revision=2)
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
        doc, _ = self._verify_real(doc, "U-01")
        old_cand = doc["git"]["candidate_sha256"]

        # Modify tracked file in repo
        (self.repo / "scripts" / "agent_harness" / "mod.py").write_text("X = 2\n", encoding="utf-8")
        new_snap = fs.compute_candidate_snapshot(self.repo, base_sha=self.base_sha)
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
        db_c = self.root / "host_c" / "state.sqlite"
        export_path = self.root / "handoff" / "issue-429.json"

        doc0 = fs.activate_unit(self._new_doc(), "U-01")
        with Journal(db_a) as journal:
            journal.plan(
                run_id="a" * 32,
                issue=429,
                source_sha=self.base_sha,
                issue_sha=self.issue_sha,
                branch=self.snap["branch"],
                worktree=self.repo,
                scope=("scripts/agent_harness/",),
            )
            journal.save_feature_snapshot(
                issue=429,
                expected_revision=None,
                revision=doc0["revision"],
                doc_json=json.dumps(doc0, sort_keys=True),
                units=doc0["units"],
                actor="coordinator",
            )
            doc, proof = self._verify_real(doc0, "U-01")
            doc = fs.activate_unit(doc, "U-02")
            journal.save_feature_snapshot(
                issue=429,
                expected_revision=doc0["revision"],
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="host_verifier",
                host_proofs={"U-01": proof},
            )
            # Simulate crash mid-PREPARING
            journal.transition("a" * 32, expected="PLANNED", next_state="PREPARING")

        # Uncommitted unfinished work must be preserved
        unfinished = self.repo / "scripts" / "agent_harness" / "wip.py"
        unfinished.write_text("# unfinished work\n", encoding="utf-8")

        issue_data = {"title": "P04 test", "body": self.issue_body, "scope": ("scripts/agent_harness/",), "issue_sha256": self.issue_sha}
        res_recover = fs.session_start(issue=429, repo=self.repo, state_db=db_a, issue_data=issue_data)
        self.assertEqual(res_recover["status"], "RECOVERY_REQUIRED")
        self.assertTrue(res_recover["has_uncommitted_work"])
        self.assertTrue(unfinished.exists())
        self.assertIn("U-01", res_recover["drift"]["stale_units"])

        # Checkpoint & export portable handoff from Session A
        ckpt = fs.session_checkpoint(
            issue=429,
            repo=self.repo,
            state_db=db_a,
            next_action="Re-verify U-01 and finish U-02",
            export_path=export_path,
            base_sha=self.base_sha,
        )
        self.assertEqual(ckpt["status"], "CHECKPOINT_SAVED")
        exported_text = export_path.read_text(encoding="utf-8")
        self.assertNotIn(str(self.root), exported_text)

        # Forged PASSING in exported JSON CANNOT enter fresh Journal unverified on import
        hacked = json.loads(exported_text)
        hacked["units"][0]["state"] = "PASSING"
        hacked["units"][0]["evidence"] = {
            "verified_by": "host_verifier",
            "status": "AUTO_CHECK_PASS",
            "exit_code": 0,
            "source_sha": self.snap["source_sha"],
            "candidate_sha256": self.snap["candidate_sha256"],
            "verification_sha256": hacked["units"][0]["verification"]["definition_sha256"],
            "receipt_path": "fake.log",
            "receipt_sha256": "e" * 64,
        }
        hacked_path = self.root / "handoff" / "hacked.json"
        hacked_path.write_text(json.dumps(hacked), encoding="utf-8")

        argv_imp_hack = ["feature_state.py", "import", "--feature-file", str(hacked_path), "--state", str(db_c)]
        with patch.object(sys, "argv", argv_imp_hack), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fs.main(), 0)
        imp_hack_res = json.loads(out.getvalue())
        self.assertEqual(imp_hack_res["verified_passing"], [])
        self.assertIn("U-01", imp_hack_res["stale_units"])
        with Journal(db_c) as jc:
            self.assertEqual(jc.get_feature_snapshot(429)["doc"]["units"][0]["state"], "STALE")

        # Fresh Session B imports clean handoff into a new SQLite journal
        argv_imp = ["feature_state.py", "import", "--feature-file", str(export_path), "--state", str(db_b), "--repo", str(self.repo)]
        with patch.object(sys, "argv", argv_imp), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(fs.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["status"], "IMPORTED")

        res_b = fs.session_start(issue=429, repo=self.repo, state_db=db_b, issue_data=issue_data)
        self.assertEqual(res_b["status"], "READY_TO_RESUME")
        self.assertEqual(res_b["units"]["active"], ["U-02"])
        self.assertEqual(res_b["units"]["stale"], ["U-01"])

        # Live Issue scope drift blocks safely without touching wip.py
        drifted_issue = {**issue_data, "issue_sha256": "f" * 64}
        res_drift = fs.session_start(issue=429, repo=self.repo, state_db=db_b, issue_data=drifted_issue)
        self.assertEqual(res_drift["status"], "BLOCKED")
        self.assertTrue(unfinished.exists())

    def test_session_resume_restores_checkpoint_blocker_next_action_and_rejects_cas_or_branch_conflict(self):
        db = self.root / "resume_host" / "state.sqlite"
        doc = fs.activate_unit(self._new_doc(), "U-01")
        with Journal(db) as journal:
            journal.save_feature_snapshot(
                issue=429,
                expected_revision=None,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="coordinator",
            )

        # Save checkpoint with explicit blocker and next_action
        ckpt1 = fs.session_checkpoint(
            issue=429,
            repo=self.repo,
            state_db=db,
            next_action="Run RF bench check after owner approval",
            blocker="Pending RF PA_PATH decision",
            base_sha=self.base_sha,
            expected_revision=2,
            expected_branch=self.snap["branch"],
        )
        self.assertEqual(ckpt1["revision"], 3)

        # Resume must restore blocker, next_action, and saved_checkpoint metadata
        res1 = fs.session_start(
            issue=429, repo=self.repo, state_db=db, offline=True,
            expected_revision=3, expected_branch=self.snap["branch"],
        )
        self.assertEqual(res1["status"], "BLOCKED")
        self.assertEqual(res1["blocker"], "Pending RF PA_PATH decision")
        self.assertEqual(res1["next_action"], "Run RF bench check after owner approval")
        self.assertEqual(res1["saved_checkpoint"]["checkpoint_id"], ckpt1["checkpoint_id"])
        self.assertEqual(res1["saved_checkpoint"]["branch"], self.snap["branch"])
        self.assertEqual(res1["saved_checkpoint"]["revision_sha"], self.snap["source_sha"])

        # Clear blocker and record custom next_action
        ckpt2 = fs.session_checkpoint(
            issue=429,
            repo=self.repo,
            state_db=db,
            next_action="Execute unit test suite for U-01 step B",
            blocker="",
            base_sha=self.base_sha,
            expected_revision=3,
        )
        self.assertEqual(ckpt2["revision"], 4)
        res2 = fs.session_start(issue=429, repo=self.repo, state_db=db, offline=True)
        self.assertEqual(res2["status"], "READY_TO_RESUME")
        self.assertEqual(res2["blocker"], "")
        self.assertEqual(res2["next_action"], "Execute unit test suite for U-01 step B")

        # Stale CAS on checkpoint MUST fail and MUST NOT overwrite state or insert checkpoint
        with self.assertRaises(fs.RevisionConflict):
            fs.session_checkpoint(
                issue=429,
                repo=self.repo,
                state_db=db,
                next_action="Stale overwrite attempt",
                base_sha=self.base_sha,
                expected_revision=2,
            )
        with Journal(db) as journal:
            self.assertEqual(journal.get_feature_snapshot(429)["revision"], 4)
            self.assertEqual(len(journal.list_checkpoints(429)), 2)
            self.assertEqual(journal.latest_checkpoint(429)["next_action"], "Execute unit test suite for U-01 step B")

        # Stale CAS on session_start fails closed without mutating DB
        with self.assertRaises(fs.RevisionConflict):
            fs.session_start(issue=429, repo=self.repo, state_db=db, offline=True, expected_revision=2)

        # Concurrent DB update during session_start drift save does NOT overwrite newer state
        (self.repo / "scripts" / "agent_harness" / "mod.py").write_text("X = 99\n", encoding="utf-8")
        orig_reconcile = fs.reconcile_revision_drift

        def racing_reconcile(*args, **kwargs):
            with Journal(db) as j2:
                snap2 = j2.get_feature_snapshot(429)
                d2 = fs.block_unit(snap2["doc"], "U-01", reason="Concurrent block", expected_revision=snap2["revision"])
                j2.save_feature_snapshot(
                    issue=429,
                    expected_revision=snap2["revision"],
                    revision=d2["revision"],
                    doc_json=json.dumps(d2, sort_keys=True),
                    units=d2["units"],
                    actor="coordinator",
                )
            return orig_reconcile(*args, **kwargs)

        with patch.object(fs, "reconcile_revision_drift", side_effect=racing_reconcile):
            with self.assertRaises(fs.RevisionConflict):
                fs.session_start(issue=429, repo=self.repo, state_db=db, offline=True)
        with Journal(db) as journal:
            snap_after = journal.get_feature_snapshot(429)
            self.assertEqual(snap_after["revision"], 5)
            self.assertEqual(snap_after["doc"]["units"][0]["state"], "BLOCKED")
            self.assertEqual(snap_after["doc"]["units"][0]["blocker"], "Concurrent block")

        # Branch mismatch blocks resume and rejects checkpoint without overwriting
        _git(self.repo, "checkout", "-q", "-b", "feature/999-wrong")
        res_branch = fs.session_start(issue=429, repo=self.repo, state_db=db, offline=True)
        self.assertEqual(res_branch["status"], "BLOCKED")
        self.assertTrue(res_branch["drift"]["branch_mismatch"])
        with self.assertRaises(fs.RevisionConflict):
            fs.session_checkpoint(
                issue=429, repo=self.repo, state_db=db,
                next_action="Should fail on wrong branch", base_sha=self.base_sha,
            )

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
                          "--base-sha", self.base_sha, "--units-file", str(units_file),
                          "--state", str(db), "--offline")
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

        # Host quality_gates verification via CLI succeeds (no --actor or self-declared --receipt)
        with Journal(db) as journal:
            doc = journal.get_feature_snapshot(429)["doc"]
        ev_dir = self._write_host_evidence(doc, "U-01", dirname="cli_ev")

        rc, res = run_cli("verify-unit", "--issue", "429", "--unit-id", "U-01",
                          "--repo", str(self.repo), "--base-sha", self.base_sha,
                          "--evidence-dir", str(ev_dir), "--state", str(db))
        self.assertEqual(rc, 0)
        self.assertEqual(res["status"], "PASSING")

        # Checkpoint + export + validate
        rc, res = run_cli("checkpoint", "--issue", "429", "--repo", str(self.repo),
                          "--state", str(db), "--base-sha", self.base_sha,
                          "--expected-revision", "3", "--next-action", "Activate U-02",
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
        self.assertEqual(res["next_action"], "Activate U-02")


if __name__ == "__main__":
    unittest.main()
