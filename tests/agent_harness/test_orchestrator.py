"""Unit and integration tests for P08-A Role & Control-Plane Integration."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))

import feature_state
import orchestrator
import run as harness_run
from p1 import cli as p1_cli
from p1.state import Journal, StateConflict
from snapshot import REFERENCES as SNAPSHOT_REFERENCES


def _git(repo: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=20,
    )
    return proc.stdout.strip()


class OrchestratorControlPlaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base_dir = pathlib.Path(self.tmp.name)
        self.repo = self.base_dir / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.name", "Harness Test")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        (self.repo / "AGENTS.md").write_text("# Test AGENTS\n- Follow P08-A invariants.\n", encoding="utf-8")
        (self.repo / "README.md").write_text("before\n", encoding="utf-8")
        for ref in SNAPSHOT_REFERENCES:
            p = self.repo / ref
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("Read-only fixture reference.\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "base fixture")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")
        _git(self.repo, "checkout", "-qb", "feature/437-fixture")
        self.journal_path = self.base_dir / "host" / "state.sqlite"
        self.evidence_dir = self.base_dir / "evidence"
        self.issue_data = {
            "state": "OPEN",
            "title": "Fixture P08-A Issue",
            "body": "## Target Directories (allowed paths)\n- `README.md`\n",
        }
        self.approval = {
            "status": "SUPERVISED_ISSUE_OPEN",
            "isolated_pilot_attested": True,
        }

    def _admit(self, **overrides):
        kwargs = {
            "repo": self.repo,
            "issue": 437,
            "journal_path": self.journal_path,
            "base_sha": self.base_sha,
            "issue_data": self.issue_data,
            "approval": self.approval,
            "maker_provider": "fixture",
            "checker_provider": "fixture",
            "capability_overrides": {"fixture_maker": True, "fixture_checker": True},
            "require_isolated_worktree": False,
        }
        kwargs.update(overrides)
        return orchestrator.admit_run(**kwargs)

    def _make_linked_worktree(self, *, issue: int = 437, suffix: str = "wt") -> pathlib.Path:
        wt_path = self.base_dir / f"linked-{issue}-{suffix}"
        branch = f"feature/{issue}-{suffix}"
        _git(self.repo, "worktree", "add", "-b", branch, str(wt_path), self.base_sha)
        return wt_path

    def _seed_harness_files(self, repo_path: pathlib.Path) -> None:
        (repo_path / ".agent-harness").mkdir(exist_ok=True)
        (repo_path / ".agent-harness" / "worker.md").write_text("Worker rules\n", encoding="utf-8")
        (repo_path / ".agent-harness" / "auditor.md").write_text("Auditor rules\n", encoding="utf-8")
        (repo_path / "scripts" / "agent_harness" / "adapters").mkdir(parents=True, exist_ok=True)
        (repo_path / "scripts" / "agent_harness" / "adapters" / "audit.schema.json").write_text("{}\n", encoding="utf-8")
        (repo_path / "scripts" / "verify_structure.py").write_text("print('OK')\n", encoding="utf-8")
        _git(repo_path, "add", ".")
        _git(repo_path, "commit", "-qm", "harness fixture files")

    def _make_pass_evidence(
        self,
        round_label: str,
        *,
        admitted: dict,
        candidate_sha256: str = "a" * 64,
        diff_sha256: str = "b" * 64,
        decision: str = "ACCEPT",
        hard_gate_passed: bool = True,
        checks_status: str = "PASS",
        audit_status: str = "PASS",
    ) -> dict:
        ev_root = self.base_dir / "pass_ev" / admitted["run"]["run_id"]
        round_rel = round_label
        round_dir = ev_root / round_rel
        checks_doc = {
            "status": checks_status,
            "candidate_sha256": candidate_sha256,
            "diff_sha256": diff_sha256,
            "source_sha": admitted["run"]["source_sha"],
        }
        checks_sha = orchestrator.write_immutable_json(round_dir / "checks_summary.json", checks_doc)
        ev_refs = [{"receipt_path": f"{round_rel}/checks_summary.json", "receipt_sha256": checks_sha}]
        rubric = orchestrator.build_rubric_report(
            decision=decision, hard_gate_passed=hard_gate_passed, evidence_refs=ev_refs
        )
        audit_doc = {
            "status": audit_status,
            "findings": [],
            "limitations": [],
            "reviewed_scope": list(admitted["admission"]["scope"]),
            "selection_sha256": admitted["selection"]["selection_sha256"],
            "rule_results": [],
            "rubric": rubric,
        }
        audit_sha = orchestrator.write_immutable_json(round_dir / "audit_report.json", audit_doc)
        return {
            "candidate_sha256": candidate_sha256,
            "diff_sha256": diff_sha256,
            "policy_sha256": admitted["policy"]["policy_sha256"],
            "check_plan_sha256": admitted["check_plan"]["plan_sha256"],
            "selection_sha256": admitted["selection"]["selection_sha256"],
            "checks_summary_sha256": checks_sha,
            "auditor_report_sha256": audit_sha,
            "evidence_dir": ev_root,
            "evidence_refs": {
                "round_dir": round_rel,
                "checks_summary": f"{round_rel}/checks_summary.json",
                "auditor_report": f"{round_rel}/audit_report.json",
            },
            "rubric": rubric,
        }

    def test_admission_happy_path_and_frozen_policy_pending_approval(self):
        res = self._admit()
        run = res["run"]
        self.assertEqual(run["state"], "ADMITTED")
        self.assertEqual(run["issue"], 437)
        self.assertEqual(run["policy"]["consecutive_passes_required"], 1)
        self.assertEqual(run["policy"]["max_rounds"], 1)
        self.assertEqual(run["policy"]["wip_limit"], 1)
        self.assertTrue(run["policy"]["sequential_only"])
        self.assertEqual(run["policy"]["owner_approval_status"], "PENDING_OWNER_APPROVAL")
        self.assertEqual(run["policy"]["metric_availability"]["tokens"], "UNAVAILABLE")
        self.assertEqual(run["policy"]["metric_availability"]["cost_usd"], "UNAVAILABLE")
        self.assertEqual(run["policy"]["metric_availability"]["wall_seconds"], "AVAILABLE")
        self.assertTrue(res["check_plan"]["plan_sha256"])
        self.assertFalse(res["capabilities"]["isolation_disclosure"]["os_process_sandbox_for_native_ui"])

    def test_admission_blocks_missing_approval_closed_issue_main_branch_and_dirty_g0(self):
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit(approval=None)
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit(approval={"status": "MISSING"})
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit(issue_data={"state": "CLOSED", "body": self.issue_data["body"]})
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit(
                issue_data={
                    "state": "OPEN",
                    "body": "## Target Directories (allowed paths)\n- `contracts/radio-mac/spec.md`\n",
                },
                require_protected_approval=True,
            )

        # Dirty AGENTS.md blocks G0
        (self.repo / "AGENTS.md").write_text("tampered\n", encoding="utf-8")
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit()
        _git(self.repo, "checkout", "--", "AGENTS.md")

        # Main branch is forbidden
        _git(self.repo, "checkout", "-qb", "main")
        with self.assertRaises(orchestrator.AdmissionError):
            self._admit()

    def test_capability_and_budget_policy_fail_closed(self):
        with self.assertRaises(orchestrator.CapabilityError):
            self._admit(
                maker_provider="codex",
                capability_overrides={"codex_path": None, "agy_path": "/usr/bin/agy"},
            )
        with self.assertRaises(orchestrator.CapabilityError):
            self._admit(
                checker_provider="agy",
                capability_overrides={"codex_path": "/usr/bin/codex", "agy_path": None},
            )
        with self.assertRaises(orchestrator.PolicyError):
            orchestrator.build_run_policy(require_token_budget=True, max_tokens=1000, token_metering_available=False)
        with self.assertRaises(orchestrator.PolicyError):
            orchestrator.build_run_policy(require_cost_budget=True, max_cost_usd=1.0, cost_metering_available=False)
        with self.assertRaises(orchestrator.PolicyError):
            orchestrator.build_run_policy(wip_limit=2)
        with self.assertRaises(orchestrator.PolicyError):
            orchestrator.build_run_policy(sequential_only=False)

    def test_role_acl_separates_planner_orchestrator_maker_host_checker_owner(self):
        for role, action in (
            ("orchestrator", "approve_scope"),
            ("orchestrator", "approve_policy"),
            ("orchestrator", "certify_pass"),
            ("orchestrator", "write_host_receipt"),
            ("orchestrator", "edit_candidate"),
            ("orchestrator", "merge_pr"),
            ("planner", "approve_scope"),
            ("planner", "transition_unit_passing"),
            ("maker", "certify_pass"),
            ("maker", "modify_verification_defs"),
            ("maker", "transition_unit_passing"),
            ("checker", "edit_candidate"),
            ("checker", "mutate_evidence"),
            ("checker", "dispatch_role"),
            ("checker", "merge_pr"),
            ("host", "approve_scope"),
            ("host", "merge_pr"),
        ):
            with self.subTest(role=role, action=action):
                with self.assertRaises(orchestrator.RoleAccessDenied):
                    orchestrator.authorize_role_action(role, action)

        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.authorize_role_action(
                "maker", "edit_candidate", target_path="contracts/secret.md", repo=self.repo, approved_scope=("README.md",)
            )
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.authorize_role_action("host", "write_host_receipt", model_output_as_evidence=True)

        ok = orchestrator.authorize_role_action(
            "maker", "edit_candidate", target_path="README.md", repo=self.repo, approved_scope=("README.md",)
        )
        self.assertTrue(ok["allowed"])
        self.assertFalse(ok["os_sandbox_enforced"])

    def test_wip_one_duplicate_dispatch_and_invalid_transitions_rejected(self):
        admitted = self._admit()
        run_id = admitted["run"]["run_id"]

        # Sequential WIP=1 rejects second concurrent run on same Issue
        with self.assertRaises(StateConflict):
            self._admit()

        # Sequential WIP=1 also rejects a concurrent run on a different Issue #438 sharing the Journal
        repo2 = self.base_dir / "repo438"
        shutil.copytree(self.repo, repo2)
        _git(repo2, "checkout", "-qb", "feature/438-fixture")
        with self.assertRaises(StateConflict):
            self._admit(
                repo=repo2,
                issue=438,
                issue_data={"state": "OPEN", "body": self.issue_data["body"]},
            )

        # Invalid transition ADMITTED -> MAKER_RUNNING or READY_FOR_HUMAN_REVIEW
        with self.assertRaises(StateConflict):
            orchestrator.transition_state(
                journal_path=self.journal_path,
                run_id=run_id,
                expected="ADMITTED",
                next_state="MAKER_RUNNING",
            )
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.transition_state(
                journal_path=self.journal_path,
                run_id=run_id,
                expected="ADMITTED",
                next_state="READY_FOR_HUMAN_REVIEW",
            )

        # Duplicate dispatch while active lease exists is rejected
        dispatched = orchestrator.dispatch_role(
            repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="maker"
        )
        self.assertTrue(dispatched["dispatch_token"])
        with self.assertRaises(orchestrator.DuplicateDispatchError):
            orchestrator.dispatch_role(
                repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker"
            )

        # Cannot record PASS without Host + Checker PASS
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=dispatched["dispatch_token"],
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=False,
            )

    def test_cancellation_preserves_worktree_and_blocks_subsequent_dispatch(self):
        (self.repo / "README.md").write_text("uncommitted work\n", encoding="utf-8")
        admitted = self._admit()
        run_id = admitted["run"]["run_id"]
        cancelled = orchestrator.cancel_run(
            journal_path=self.journal_path, run_id=run_id, requested_by="owner", reason="Operator stop"
        )
        self.assertEqual(cancelled["state"], "CANCELLED")
        self.assertTrue(cancelled["cancel_requested"])
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "uncommitted work\n")
        with self.assertRaises(orchestrator.ControlPlaneError):
            orchestrator.dispatch_role(
                repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="maker"
            )

    def test_no_progress_wall_budget_and_consecutive_passes_policy(self):
        # 1. No-progress threshold escalates after repeated identical failures
        pol = orchestrator.build_run_policy(
            consecutive_passes_required=1, max_rounds=4, max_wall_seconds=120, no_progress_threshold=2
        )
        run1 = self._admit(policy=pol)["run"]["run_id"]
        d1 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run1, role="maker")
        r1 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run1,
            dispatch_token=d1["dispatch_token"],
            outcome="FAIL",
            host_checks_passed=False,
            checker_passed=False,
            diff_sha256="a" * 64,
            failure_sig="err_same",
            wall_elapsed_s=5.0,
        )
        self.assertEqual(r1["state"], "REPAIR_REQUIRED")
        d2 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run1, role="maker")
        r2 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run1,
            dispatch_token=d2["dispatch_token"],
            outcome="FAIL",
            host_checks_passed=False,
            checker_passed=False,
            diff_sha256="a" * 64,
            failure_sig="err_same",
            wall_elapsed_s=5.0,
        )
        self.assertEqual(r2["state"], "ESCALATED")
        self.assertEqual(r2["no_progress_count"], 2)

        # 2. Wall-time budget exhaustion escalates and raises BudgetExhaustedError
        pol2 = orchestrator.build_run_policy(
            consecutive_passes_required=1, max_rounds=3, max_wall_seconds=10, no_progress_threshold=3
        )
        run2 = self._admit(policy=pol2)["run"]["run_id"]
        d3 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run2, role="maker")
        with self.assertRaises(orchestrator.BudgetExhaustedError):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run2,
                dispatch_token=d3["dispatch_token"],
                outcome="REVISE",
                host_checks_passed=True,
                checker_passed=False,
                wall_elapsed_s=15.0,
            )
        with Journal(self.journal_path) as journal:
            self.assertEqual(journal.get_control_run(run2)["state"], "ESCALATED")

        # 3. N consecutive passes required before READY_FOR_HUMAN_REVIEW
        pol3 = orchestrator.build_run_policy(
            consecutive_passes_required=2, max_rounds=3, max_wall_seconds=120, no_progress_threshold=3
        )
        adm3 = self._admit(policy=pol3)
        run3 = adm3["run"]["run_id"]
        d4 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run3, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path,
            run_id=run3,
            expected="DISPATCHED",
            next_state="CHECKING",
            actor_role="host",
            action="checker_started",
            dispatch_token=d4["dispatch_token"],
        )
        pass_ev1 = self._make_pass_evidence("round-01", admitted=adm3)
        r4 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run3,
            dispatch_token=d4["dispatch_token"],
            outcome="PASS",
            host_checks_passed=True,
            checker_passed=True,
            **pass_ev1,
        )
        self.assertEqual(r4["state"], "REPAIR_REQUIRED")
        self.assertEqual(r4["consecutive_passes"], 1)
        d5 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run3, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path,
            run_id=run3,
            expected="DISPATCHED",
            next_state="CHECKING",
            actor_role="host",
            action="checker_started",
            dispatch_token=d5["dispatch_token"],
        )
        pass_ev2 = self._make_pass_evidence("round-02", admitted=adm3)
        r5 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run3,
            dispatch_token=d5["dispatch_token"],
            outcome="PASS",
            host_checks_passed=True,
            checker_passed=True,
            confirming_pass=True,
            **pass_ev2,
        )
        self.assertEqual(r5["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(r5["consecutive_passes"], 2)

    def test_controlled_fixture_dispatch_produces_traceable_receipts_and_rejects_checker_mutation(self):
        def _maker(wt: pathlib.Path, _admitted: dict) -> dict:
            (wt / "README.md").write_text("after fixture\n", encoding="utf-8")
            return {"changed_path": "README.md"}

        summary = orchestrator.run_controlled_dispatch(
            repo=self.repo,
            issue=437,
            journal_path=self.journal_path,
            evidence_dir=self.evidence_dir,
            issue_data=self.issue_data,
            maker_fn=_maker,
            base_sha=self.base_sha,
        )
        self.assertEqual(summary["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertFalse(summary["ready_to_merge"])
        self.assertTrue(summary["human_approval_required"])
        self.assertEqual(summary["owner_approval_status"], "PENDING_OWNER_APPROVAL")
        for name in (
            "admission.json",
            "policy.json",
            "round-01/checks_summary.json",
            "round-01/audit_report.json",
            "control_plane_summary.json",
        ):
            self.assertTrue((self.evidence_dir / name).is_file(), name)
        r0 = summary["rounds"][0]
        self.assertEqual(r0["evidence_refs"]["checks_summary"], "round-01/checks_summary.json")
        self.assertEqual(r0["evidence_refs"]["auditor_report"], "round-01/audit_report.json")

        # Mutating snapshot inside Checker fails closed
        ev2 = self.base_dir / "evidence_mut"
        def _bad_checker(snapshot_dir: pathlib.Path, _ev: dict, _adm: dict) -> dict:
            (snapshot_dir / "changes.patch").chmod(0o644)
            (snapshot_dir / "changes.patch").write_text("tampered\n", encoding="utf-8")
            return {"status": "PASS", "findings": [], "limitations": [], "reviewed_scope": ["README.md"]}

        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.run_controlled_dispatch(
                repo=self.repo,
                issue=437,
                journal_path=self.journal_path,
                evidence_dir=ev2,
                issue_data=self.issue_data,
                maker_fn=_maker,
                checker_fn=_bad_checker,
                base_sha=self.base_sha,
            )

    def test_cli_integration_p1_cli_and_feature_state_resume(self):
        with patch.object(sys, "argv", ["cli.py", "capabilities"]), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p1_cli.main(), 0)
        caps = json.loads(out.getvalue())
        self.assertIn("isolation_disclosure", caps)

        # Fail closed without approval
        argv_no_app = [
            "cli.py", "admit", "--issue", "437", "--repo", str(self.repo),
            "--state", str(self.journal_path), "--base-sha", self.base_sha,
        ]
        with patch("orchestrator._fetch_live_issue", return_value=self.issue_data), \
             patch.object(sys, "argv", argv_no_app), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p1_cli.main(), 2)
        self.assertEqual(json.loads(out.getvalue())["state"], "BLOCKED")

        # Admit via p1/cli.py with real linked worktree and supervised attestation
        wt = self._make_linked_worktree(issue=437, suffix="cli")
        argv_ok = [
            "cli.py", "admit", "--issue", "437", "--repo", str(wt),
            "--state", str(self.journal_path), "--base-sha", self.base_sha,
            "--supervised-issue-open", "--maker-provider", "native_supervised", "--checker-provider", "native_subagent",
        ]
        with patch("orchestrator._fetch_live_issue", return_value=self.issue_data), \
             patch("shutil.which", return_value="/usr/bin/agy"), \
             patch.object(sys, "argv", argv_ok), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p1_cli.main(), 0)
        admitted = json.loads(out.getvalue())
        run_id = admitted["run"]["run_id"]

        resumed = feature_state.session_start(
            issue=437, repo=wt, state_db=self.journal_path, offline=True
        )
        self.assertIsNotNone(resumed["control_run"])
        self.assertEqual(resumed["control_run"]["run_id"], run_id)
        self.assertEqual(resumed["control_run"]["state"], "ADMITTED")

        # Cancel via p1/cli.py
        argv_can = [
            "cli.py", "cancel", "--run-id", run_id,
            "--source", str(wt), "--state", str(self.journal_path),
        ]
        with patch.object(sys, "argv", argv_can), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p1_cli.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "CANCELLED")

    def test_run_py_with_journal_persists_control_run_and_rejects_unavailable_token_budget(self):
        wt = self._make_linked_worktree(issue=437, suffix="run")
        self._seed_harness_files(wt)

        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        def _fake_worker(prompt, repo, timeout, **kwargs):
            (wt / "README.md").write_text("updated via run.py\n", encoding="utf-8")
            return {
                "exit_code": 0,
                "stdout_bytes": 0,
                "stderr_bytes": 0,
                "report": {
                    "status": "PASS",
                    "findings": [],
                    "limitations": [],
                    "reviewed_scope": ["README.md"],
                    "selection_sha256": kwargs["selection_sha256"],
                    "rule_results": [],
                },
            }

        def _fake_audit(prompt, snapshot, schema, timeout, required_paths, **kwargs):
            ev_refs = [
                {"receipt_path": k, "receipt_sha256": v}
                for k, v in sorted((kwargs.get("evidence_inventory") or {}).items())
            ]
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": kwargs["selection_sha256"],
                "rule_results": [],
                "rubric": orchestrator.build_rubric_report(
                    decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs
                ),
            }

        args = argparse.Namespace(
            issue=437,
            execute=True,
            accept_isolated_pilot=True,
            expected_idf_version=None,
            toolchain_mode="container_only",
            allow_native_fallback=False,
            timeout=30,
            max_repairs=0,
            check_profile="quick",
            max_wall_seconds=300,
            consecutive_passes=1,
            no_progress_threshold=2,
            require_token_budget=False,
            require_cost_budget=False,
            approved_by="",
            journal=self.journal_path,
            feature_file=None,
            unit_id=None,
            trusted_definitions=None,
        )
        stream = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fake_worker), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             contextlib.redirect_stdout(stream):
            rc = harness_run.run(args)
        manifest_path = pathlib.Path(stream.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, manifest_path.parent)
        self.assertEqual(rc, 0)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(manifest["owner_approval_status"], "PENDING_OWNER_APPROVAL")
        self.assertTrue((manifest_path.parent / "control-policy.json").is_file())
        with Journal(self.journal_path) as journal:
            ctrl = journal.get_control_run(manifest["run_id"])
            self.assertEqual(ctrl["state"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(ctrl["round_num"], 1)
            rounds = journal.list_control_rounds(manifest["run_id"])
            self.assertEqual(len(rounds), 1)
            self.assertEqual(rounds[0]["verdict"], "ACCEPT")
            self.assertEqual(rounds[0]["rubric_decision"], "ACCEPT")

        # Omitting --journal on --execute MUST fail closed (no no-Journal execute fallback)
        _git(wt, "checkout", "--", "README.md")
        args_no_journal = argparse.Namespace(**{**vars(args), "journal": None})
        stream_nj = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             contextlib.redirect_stdout(stream_nj):
            rc_nj = harness_run.run(args_no_journal)
        m_nj = pathlib.Path(stream_nj.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, m_nj.parent)
        self.assertEqual(rc_nj, 2)
        m_nj_doc = json.loads(m_nj.read_text(encoding="utf-8"))
        self.assertEqual(m_nj_doc["state"], "BLOCKED")
        self.assertIn("--journal is required", m_nj_doc["reason"])

        # Preflight/read-only without --journal remains compatible
        args_pre = argparse.Namespace(**{**vars(args), "execute": False, "journal": None})
        stream_pre = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             contextlib.redirect_stdout(stream_pre):
            rc_pre = harness_run.run(args_pre)
        m_pre = pathlib.Path(stream_pre.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, m_pre.parent)
        self.assertEqual(rc_pre, 0)
        self.assertEqual(json.loads(m_pre.read_text(encoding="utf-8"))["state"], "PREFLIGHT_ONLY")

        # Requiring unmeasurable token budget fails closed
        _git(wt, "checkout", "--", "README.md")
        args_tok = argparse.Namespace(**{**vars(args), "require_token_budget": True})
        stream2 = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             contextlib.redirect_stdout(stream2):
            rc2 = harness_run.run(args_tok)
        manifest_path2 = pathlib.Path(stream2.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, manifest_path2.parent)
        self.assertEqual(rc2, 2)
        self.assertEqual(json.loads(manifest_path2.read_text(encoding="utf-8"))["state"], "BLOCKED")

    def test_real_execution_enforces_isolated_worktree_and_protected_owner_approval(self):
        # 1. Primary checkout (not a linked git worktree) and FIXTURE_APPROVED fail closed by default
        with self.assertRaises(orchestrator.AdmissionError):
            orchestrator.admit_run(
                repo=self.repo,
                issue=437,
                journal_path=self.journal_path,
                base_sha=self.base_sha,
                issue_data=self.issue_data,
                approval=self.approval,
                maker_provider="fixture",
                checker_provider="fixture",
                capability_overrides={"fixture_maker": True, "fixture_checker": True},
            )
        wt = self._make_linked_worktree(issue=437, suffix="prot")
        with self.assertRaises(orchestrator.AdmissionError):
            orchestrator.admit_run(
                repo=wt,
                issue=437,
                journal_path=self.journal_path,
                base_sha=self.base_sha,
                issue_data=self.issue_data,
                approval={"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner"},
                maker_provider="fixture",
                checker_provider="fixture",
                capability_overrides={"fixture_maker": True, "fixture_checker": True},
            )
        # 2. Protected scope without Owner approval fails closed on admit_run & run.py
        protected_issue = {
            "state": "OPEN",
            "title": "Protected contract edit",
            "body": "## Target Directories (allowed paths)\n- `contracts/radio-mac/spec.md`\n",
        }
        with self.assertRaises(orchestrator.AdmissionError):
            orchestrator.admit_run(
                repo=wt,
                issue=437,
                journal_path=self.journal_path,
                base_sha=self.base_sha,
                issue_data=protected_issue,
                approval=self.approval,
                maker_provider="fixture",
                checker_provider="fixture",
                capability_overrides={"fixture_maker": True, "fixture_checker": True},
            )

        self._seed_harness_files(self.repo)
        self._seed_harness_files(wt)

        def _fake_tool_prot(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(protected_issue)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        # run.py on primary checkout fails closed
        args_base = argparse.Namespace(
            issue=437, execute=True, accept_isolated_pilot=True,
            expected_idf_version=None, toolchain_mode="container_only", allow_native_fallback=False,
            timeout=30, max_repairs=0, max_wall_seconds=300, consecutive_passes=1,
            no_progress_threshold=2, require_token_budget=False, require_cost_budget=False,
            approved_by="", journal=self.journal_path, feature_file=None, unit_id=None, trusted_definitions=None,
        )
        s_primary = io.StringIO()
        with patch.object(harness_run, "__file__", str(self.repo / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=lambda c, w, t: ({"tool": "gh", "command": c, "exit_code": 0, "output_sha256": "0"*64, "output_bytes": 10}, json.dumps(self.issue_data))), \
             contextlib.redirect_stdout(s_primary):
            rc_p = harness_run.run(args_base)
        p_manifest = pathlib.Path(s_primary.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, p_manifest.parent)
        self.assertEqual(rc_p, 2)
        self.assertEqual(json.loads(p_manifest.read_text(encoding="utf-8"))["state"], "BLOCKED")

        # run.py on protected scope without --approved-by fails closed
        s_prot = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool_prot), \
             contextlib.redirect_stdout(s_prot):
            rc_prot = harness_run.run(args_base)
        prot_manifest = pathlib.Path(s_prot.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, prot_manifest.parent)
        self.assertEqual(rc_prot, 2)
        self.assertEqual(json.loads(prot_manifest.read_text(encoding="utf-8"))["state"], "BLOCKED")

    def test_run_py_obeys_record_round_result_consecutive_passes_and_escalation(self):
        wt = self._make_linked_worktree(issue=437, suffix="consec")
        self._seed_harness_files(wt)
        worker_edit_round = {"n": 0}
        audit_round = {"n": 0}

        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        def _fake_worker(prompt, repo, timeout, **kwargs):
            if "Read-only final Worker report" not in prompt:
                worker_edit_round["n"] += 1
                (wt / "README.md").write_text(f"pass edit {worker_edit_round['n']}\n", encoding="utf-8")
            return {
                "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                "report": {
                    "status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": ["README.md"], "selection_sha256": kwargs["selection_sha256"], "rule_results": [],
                },
            }

        def _fake_audit(prompt, snapshot, schema, timeout, required_paths, **kwargs):
            audit_round["n"] += 1
            ev_refs = [
                {"receipt_path": k, "receipt_sha256": v}
                for k, v in sorted((kwargs.get("evidence_inventory") or {}).items())
            ]
            return {
                "status": "PASS", "findings": [], "limitations": [],
                "reviewed_scope": ["README.md"], "selection_sha256": kwargs["selection_sha256"], "rule_results": [],
                "rubric": orchestrator.build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs),
            }

        # Case A: consecutive_passes=2 with max_repairs=1 (max_rounds=2):
        # Round 1 edits once; Round 2 runs fresh Host verification + Checker WITHOUT Maker edit!
        args_2 = argparse.Namespace(
            issue=437, execute=True, accept_isolated_pilot=True,
            expected_idf_version=None, toolchain_mode="container_only", allow_native_fallback=False,
            timeout=30, max_repairs=1, check_profile="quick", max_wall_seconds=300, consecutive_passes=2,
            no_progress_threshold=3, require_token_budget=False, require_cost_budget=False,
            approved_by="", journal=self.journal_path, feature_file=None, unit_id=None, trusted_definitions=None,
        )
        s1 = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fake_worker), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             contextlib.redirect_stdout(s1):
            rc1 = harness_run.run(args_2)
        m1_path = pathlib.Path(s1.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, m1_path.parent)
        self.assertEqual(rc1, 0)
        self.assertEqual(worker_edit_round["n"], 1)
        self.assertEqual(audit_round["n"], 2)
        m1 = json.loads(m1_path.read_text(encoding="utf-8"))
        self.assertEqual(m1["state"], "READY_FOR_HUMAN_REVIEW")
        with Journal(self.journal_path) as journal:
            c1 = journal.get_control_run(m1["run_id"])
            self.assertEqual(c1["state"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(c1["consecutive_passes"], 2)
            rounds = journal.list_control_rounds(m1["run_id"])
            self.assertEqual(len(rounds), 2)
            self.assertTrue(rounds[0]["maker_dispatched"])
            self.assertFalse(rounds[0]["confirming_pass"])
            self.assertFalse(rounds[1]["maker_dispatched"])
            self.assertTrue(rounds[1]["confirming_pass"])
            self.assertEqual(rounds[0]["candidate_sha256"], rounds[1]["candidate_sha256"])

        # Case B: if record_round_result transitions to ESCALATED, run.py must NOT return READY_FOR_HUMAN_REVIEW
        _git(wt, "checkout", "--", "README.md")
        args_1 = argparse.Namespace(**{**vars(args_2), "max_repairs": 0, "consecutive_passes": 1})

        def _force_escalated(**kwargs):
            with Journal(kwargs["journal_path"]) as journal:
                return journal.transition_control_run(
                    kwargs["run_id"],
                    expected="CHECKING",
                    next_state="ESCALATED",
                    actor_role="host",
                    action="forced_escalation_test",
                    expected_dispatch_token=kwargs["dispatch_token"],
                    clear_dispatch=True,
                )

        s2 = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fake_worker), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             patch.object(harness_run, "record_round_result", side_effect=_force_escalated), \
             contextlib.redirect_stdout(s2):
            rc2 = harness_run.run(args_1)
        m2_path = pathlib.Path(s2.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, m2_path.parent)
        self.assertEqual(rc2, 4)
        self.assertEqual(json.loads(m2_path.read_text(encoding="utf-8"))["state"], "ESCALATED")

    def test_run_py_wall_time_budget_does_not_double_count_across_rounds(self):
        wt = self._make_linked_worktree(issue=437, suffix="wall")
        self._seed_harness_files(wt)
        clock = {"t": 0.0}

        def _fake_monotonic() -> float:
            return clock["t"]

        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        round_num = {"n": 0}

        def _fake_worker(prompt, repo, timeout, **kwargs):
            if "Read-only final Worker report" not in prompt:
                round_num["n"] += 1
                (wt / "README.md").write_text(f"wall edit {round_num['n']}\n", encoding="utf-8")
            return {
                "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                "report": {
                    "status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": ["README.md"], "selection_sha256": kwargs["selection_sha256"], "rule_results": [],
                },
            }

        def _fake_audit(prompt, snapshot, schema, timeout, required_paths, **kwargs):
            # Advance clock by 10s per round: 3 rounds = 30s total (not 10+20+30=60s!)
            clock["t"] += 10.0
            status = "FAIL" if round_num["n"] < 3 else "PASS"
            ev_refs = [
                {"receipt_path": k, "receipt_sha256": v}
                for k, v in sorted((kwargs.get("evidence_inventory") or {}).items())
            ]
            return {
                "status": status,
                "findings": [] if status == "PASS" else [{"severity": "MEDIUM", "file": "README.md", "line": 1, "rule": "TEST", "explanation": f"r{round_num['n']}", "fix": "retry"}],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": kwargs["selection_sha256"],
                "rule_results": [],
                "rubric": orchestrator.build_rubric_report(
                    decision="ACCEPT" if status == "PASS" else "REVISE",
                    hard_gate_passed=True,
                    evidence_refs=ev_refs,
                    findings_notes=None if status == "PASS" else {"correctness": [f"r{round_num['n']}"]},
                ),
            }

        args = argparse.Namespace(
            issue=437, execute=True, accept_isolated_pilot=True,
            expected_idf_version=None, toolchain_mode="container_only", allow_native_fallback=False,
            timeout=30, max_repairs=2, check_profile="quick", max_wall_seconds=35, consecutive_passes=1,
            no_progress_threshold=5, require_token_budget=False, require_cost_budget=False,
            approved_by="", journal=self.journal_path, feature_file=None, unit_id=None, trusted_definitions=None,
        )
        stream = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run.time, "monotonic", side_effect=_fake_monotonic), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fake_worker), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             contextlib.redirect_stdout(stream):
            rc = harness_run.run(args)
        manifest_path = pathlib.Path(stream.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, manifest_path.parent)
        self.assertEqual(rc, 0)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["state"], "READY_FOR_HUMAN_REVIEW")
        with Journal(self.journal_path) as journal:
            ctrl = journal.get_control_run(manifest["run_id"])
            self.assertEqual(ctrl["round_num"], 3)
            self.assertAlmostEqual(ctrl["budget_consumed"]["wall_seconds"], 30.0, places=3)
            self.assertEqual(len(journal.list_control_rounds(manifest["run_id"])), 3)

    def test_p08b_different_candidate_edits_cannot_accumulate_n_passes(self):
        pol = orchestrator.build_run_policy(
            consecutive_passes_required=2, max_rounds=3, max_wall_seconds=120, no_progress_threshold=3
        )
        adm = self._admit(policy=pol)
        run_id = adm["run"]["run_id"]
        # Round 1: Candidate A passes -> consecutive_passes = 1
        d1 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=run_id, expected="DISPATCHED",
            next_state="CHECKING", actor_role="host", action="checker_started", dispatch_token=d1["dispatch_token"],
        )
        ev1 = self._make_pass_evidence("round-01", admitted=adm, candidate_sha256="1" * 64, diff_sha256="2" * 64)
        r1 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d1["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            **ev1,
        )
        self.assertEqual(r1["consecutive_passes"], 1)
        self.assertEqual(r1["state"], "REPAIR_REQUIRED")

        # Maker dispatch while consecutive_passes > 0 is forbidden
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="maker")

        # Confirming pass where candidate drifted to B -> resets streak, NEVER accumulates to 2
        d2 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=run_id, expected="DISPATCHED",
            next_state="CHECKING", actor_role="host", action="checker_started", dispatch_token=d2["dispatch_token"],
        )
        ev2 = self._make_pass_evidence("round-02", admitted=adm, candidate_sha256="9" * 64, diff_sha256="8" * 64)
        r2 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d2["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            confirming_pass=True, **ev2,
        )
        self.assertEqual(r2["consecutive_passes"], 0)
        self.assertEqual(r2["state"], "REPAIR_REQUIRED")

        # Even non-confirming Maker edit to candidate C resets prior streak (starts at 1, not 2)
        d3 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=run_id, expected="DISPATCHED",
            next_state="CHECKING", actor_role="host", action="checker_started", dispatch_token=d3["dispatch_token"],
        )
        ev3 = self._make_pass_evidence("round-03", admitted=adm, candidate_sha256="7" * 64, diff_sha256="6" * 64)
        r3 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d3["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            confirming_pass=False, **ev3,
        )
        self.assertEqual(r3["consecutive_passes"], 1)
        self.assertEqual(r3["state"], "ESCALATED")

    def test_p08b_rejects_partial_checks_changed_candidate_waived_and_424_secret_scan(self):
        base_kw = {
            "approved_scope": ("README.md",),
            "expected_candidate_sha256": "a" * 64,
            "expected_diff_sha256": "b" * 64,
            "expected_source_sha": "c" * 40,
            "expected_planned_check_ids": ["verify-structure", "harness-unit"],
        }
        rubric_ok = orchestrator.build_rubric_report(decision="ACCEPT", hard_gate_passed=True)
        audit_ok = {"status": "PASS", "findings": [], "limitations": [], "rubric": rubric_ok}

        # 1. Changed candidate receipt
        res_cand = orchestrator.classify_round_outcome(
            **base_kw,
            checks_summary={
                "status": "PASS", "exit_code": 0,
                "candidate_sha256": "f" * 64, "diff_sha256": "b" * 64, "source_sha": "c" * 40,
                "results": [{"check_id": "verify-structure", "status": "PASS"}, {"check_id": "harness-unit", "status": "PASS"}],
                "quality_gates": {"auto_check": "AUTO_CHECK_PASS", "results": []},
            },
            audit_report=audit_ok,
        )
        self.assertEqual(res_cand["outcome"], "BLOCK")
        self.assertIn("candidate_receipt_mismatch", res_cand["failure_sig"])

        # 2. Partial check set (missing harness-unit)
        res_part = orchestrator.classify_round_outcome(
            **base_kw,
            checks_summary={
                "status": "PASS", "exit_code": 0,
                "candidate_sha256": "a" * 64, "diff_sha256": "b" * 64, "source_sha": "c" * 40,
                "results": [{"check_id": "verify-structure", "status": "PASS"}],
                "quality_gates": {"auto_check": "AUTO_CHECK_PASS", "results": []},
            },
            audit_report=audit_ok,
        )
        self.assertEqual(res_part["outcome"], "BLOCK")
        self.assertIn("partial_check_set", res_part["failure_sig"])

        # 3. Waived/NOT_VERIFIED check rejected
        res_waive = orchestrator.classify_round_outcome(
            **base_kw,
            checks_summary={
                "status": "PASS", "exit_code": 0,
                "candidate_sha256": "a" * 64, "diff_sha256": "b" * 64, "source_sha": "c" * 40,
                "results": [{"check_id": "verify-structure", "status": "PASS"}, {"check_id": "harness-unit", "status": "WAIVED_WITH_REASON"}],
                "quality_gates": {"auto_check": "AUTO_CHECK_PASS", "results": []},
            },
            audit_report=audit_ok,
        )
        self.assertEqual(res_waive["outcome"], "BLOCK")
        self.assertIn("unverified_checks", res_waive["failure_sig"])

        # 4. #424 SECRET-SCAN BLOCKED never produces fake ACCEPT
        res_424 = orchestrator.classify_round_outcome(
            **base_kw,
            checks_summary={
                "status": "FAIL", "exit_code": 1,
                "candidate_sha256": "a" * 64, "diff_sha256": "b" * 64, "source_sha": "c" * 40,
                "results": [{"check_id": "verify-structure", "status": "PASS"}, {"check_id": "harness-unit", "status": "PASS"}],
                "quality_gates": {"auto_check": "BLOCKED", "results": [{"rule_id": "SECRET-SCAN", "status": "FAIL"}]},
            },
            audit_report=audit_ok,
        )
        self.assertEqual(res_424["outcome"], "BLOCK")
        self.assertIn("secret_scan", res_424["failure_sig"])

        # 5. Out-of-scope finding -> impossible_scope BLOCK
        res_oos = orchestrator.classify_round_outcome(
            **base_kw,
            checks_summary={
                "status": "PASS", "exit_code": 0,
                "candidate_sha256": "a" * 64, "diff_sha256": "b" * 64, "source_sha": "c" * 40,
                "results": [{"check_id": "verify-structure", "status": "PASS"}, {"check_id": "harness-unit", "status": "PASS"}],
                "quality_gates": {"auto_check": "AUTO_CHECK_PASS", "results": []},
            },
            audit_report={
                "status": "FAIL",
                "findings": [{"severity": "HIGH", "file": "contracts/mqtt/topics.md", "line": 1, "rule": "SC-001", "explanation": "OOS", "fix": "edit"}],
                "limitations": [],
                "rubric": orchestrator.build_rubric_report(decision="REVISE", hard_gate_passed=True),
            },
        )
        self.assertEqual(res_oos["outcome"], "BLOCK")
        self.assertIn("impossible_scope", res_oos["failure_sig"])

    def test_p08b_pilot_scenarios_records_at_least_five_rounds_and_cli(self):
        pilot_ev = self.base_dir / "pilot_ev"
        pilot_db = self.base_dir / "pilot" / "state.sqlite"
        argv = ["orchestrator.py", "pilot", "--state", str(pilot_db), "--evidence-dir", str(pilot_ev)]
        out = io.StringIO()
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            rc = orchestrator.main()
        self.assertEqual(rc, 0)
        summary = json.loads(out.getvalue())
        self.assertGreaterEqual(summary["total_recorded_rounds"], 5)
        self.assertEqual(summary["mode"], "FIXTURE_CONTROLLED")
        self.assertEqual(summary["independent_provider_evaluation"], "NOT_VERIFIED")
        self.assertEqual(summary["human_rubric_calibration"], "NOT_VERIFIED")
        by_name = {s["scenario"]: s for s in summary["scenarios"]}
        self.assertEqual(by_name["seeded_fail_repair_accept"]["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(by_name["checker_revise_then_n2_same_candidate_accept"]["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(by_name["checker_revise_then_n2_same_candidate_accept"]["maker_invocations"], 2)
        self.assertEqual(by_name["repeated_failure_no_progress_escalated"]["state"], "ESCALATED")
        self.assertEqual(by_name["hard_gate_impossible_scope_blocked"]["state"], "BLOCKED")
        self.assertEqual(by_name["cancellation_preserves_work"]["state"], "CANCELLED")
        self.assertTrue(by_name["cancellation_preserves_work"]["worktree_preserved"])
        scenario_dirs = {
            "seeded_fail_repair_accept": pilot_ev / "scenario_1_seeded_fail_repair_accept",
            "checker_revise_then_n2_same_candidate_accept": pilot_ev / "scenario_2_revise_and_n2_same_candidate",
            "repeated_failure_no_progress_escalated": pilot_ev / "scenario_3_no_progress_escalated",
            "hard_gate_impossible_scope_blocked": pilot_ev / "scenario_4_hard_gate_block",
            "cancellation_preserves_work": pilot_ev / "scenario_5_cancellation",
        }
        with Journal(pilot_db) as journal:
            for sc in summary["scenarios"]:
                rounds = journal.list_control_rounds(sc["run_id"])
                self.assertEqual(len(rounds), sc["rounds"])
                ev_dir = scenario_dirs[sc["scenario"]]
                self.assertFalse((ev_dir / "audit_report.json").exists())
                for rnd in rounds:
                    refs = rnd["evidence_refs"]
                    expected_prefix = f"round-{rnd['round_num']:02d}/"
                    for hash_col, ref_key in (
                        ("checks_summary_sha256", "checks_summary"),
                        ("manifest_sha256", "manifest"),
                        ("auditor_report_sha256", "auditor_report"),
                    ):
                        digest_val = rnd[hash_col]
                        if digest_val:
                            self.assertIn(ref_key, refs)
                            self.assertTrue(refs[ref_key].startswith(expected_prefix))
                            artifact = ev_dir / refs[ref_key]
                            self.assertTrue(artifact.is_file(), refs[ref_key])
                            self.assertEqual(stat_mode := (artifact.stat().st_mode & 0o777), 0o444, (refs[ref_key], oct(stat_mode)))
                            self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(), digest_val)

    def test_p08b_record_round_result_rejects_boolean_only_and_incomplete_pass_evidence(self):
        adm = self._admit(
            policy=orchestrator.build_run_policy(
                consecutive_passes_required=1, max_rounds=8, max_wall_seconds=120, no_progress_threshold=8
            )
        )
        run_id = adm["run"]["run_id"]
        valid_ev = self._make_pass_evidence("round-good", admitted=adm)

        def _dispatch_to_checking() -> str:
            d = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
            orchestrator.transition_state(
                journal_path=self.journal_path,
                run_id=run_id,
                expected="DISPATCHED",
                next_state="CHECKING",
                actor_role="host",
                action="checker_started",
                dispatch_token=d["dispatch_token"],
            )
            return d["dispatch_token"]

        tok = _dispatch_to_checking()

        # 1. Self-declared booleans alone without receipts/bindings/rubric MUST fail closed
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
            )

        # 2. Missing explicit candidate/diff/selection/policy/check_plan binding MUST fail closed
        for drop_key in ("candidate_sha256", "diff_sha256", "policy_sha256", "check_plan_sha256", "selection_sha256"):
            partial = dict(valid_ev)
            partial[drop_key] = ""
            with self.subTest(missing_binding=drop_key):
                with self.assertRaises(orchestrator.RoleAccessDenied):
                    orchestrator.record_round_result(
                        journal_path=self.journal_path,
                        run_id=run_id,
                        dispatch_token=tok,
                        outcome="PASS",
                        host_checks_passed=True,
                        checker_passed=True,
                        **partial,
                    )

        # 3. Missing trusted receipt hashes or evidence_dir/evidence_refs MUST fail closed
        for drop_key in ("checks_summary_sha256", "auditor_report_sha256"):
            no_rec = dict(valid_ev)
            no_rec[drop_key] = ""
            with self.subTest(missing_receipt=drop_key):
                with self.assertRaises(orchestrator.RoleAccessDenied):
                    orchestrator.record_round_result(
                        journal_path=self.journal_path,
                        run_id=run_id,
                        dispatch_token=tok,
                        outcome="PASS",
                        host_checks_passed=True,
                        checker_passed=True,
                        **no_rec,
                    )

        no_dir = dict(valid_ev)
        no_dir["evidence_dir"] = None
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
                **no_dir,
            )

        # 4. Missing or non-ACCEPT / mismatched rubric MUST fail closed
        no_rubric = dict(valid_ev)
        no_rubric["rubric"] = None
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
                **no_rubric,
            )
        revise_ev = self._make_pass_evidence("round-revise", admitted=adm, decision="REVISE", audit_status="FAIL")
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
                **revise_ev,
            )

        # 5. Tampered / candidate-mismatched / non-PASS on-disk checks_summary MUST fail closed
        bad_checks_ev = self._make_pass_evidence("round-fail-checks", admitted=adm, checks_status="FAIL")
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
                **bad_checks_ev,
            )

        mismatch_ev = dict(valid_ev)
        mismatch_ev["checks_summary_sha256"] = "f" * 64
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path,
                run_id=run_id,
                dispatch_token=tok,
                outcome="PASS",
                host_checks_passed=True,
                checker_passed=True,
                **mismatch_ev,
            )

        # Journal state must remain CHECKING with 0 rounds after all rejected PASS attempts
        with Journal(self.journal_path) as journal:
            self.assertEqual(journal.get_control_run(run_id)["state"], "CHECKING")
            self.assertEqual(journal.list_control_rounds(run_id), [])

        # 6. Complete trusted receipts + candidate binding + ACCEPT rubric succeeds
        accepted = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run_id,
            dispatch_token=tok,
            outcome="PASS",
            host_checks_passed=True,
            checker_passed=True,
            **valid_ev,
        )
        self.assertEqual(accepted["state"], "READY_FOR_HUMAN_REVIEW")
        with Journal(self.journal_path) as journal:
            rounds = journal.list_control_rounds(run_id)
            self.assertEqual(len(rounds), 1)
            self.assertEqual(rounds[0]["checks_summary_sha256"], valid_ev["checks_summary_sha256"])
            self.assertEqual(rounds[0]["auditor_report_sha256"], valid_ev["auditor_report_sha256"])

    def test_p08b_immutable_per_round_evidence_never_overwritten_across_rounds(self):
        wt = self._make_linked_worktree(issue=437, suffix="immut")
        self._seed_harness_files(wt)

        # Direct write_immutable_artifact refusal on overwrite
        immut_file = self.base_dir / "immut_check.json"
        h0 = orchestrator.write_immutable_artifact(immut_file, b'{"round":1}\n')
        self.assertEqual(immut_file.stat().st_mode & 0o777, 0o444)
        self.assertEqual(hashlib.sha256(immut_file.read_bytes()).hexdigest(), h0)
        with self.assertRaises(orchestrator.ControlPlaneError):
            orchestrator.write_immutable_artifact(immut_file, b'{"round":2}\n')

        # Multi-round run.py execution (FAIL -> REVISE -> PASS) keeps distinct immutable per-round dirs
        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        round_n = {"n": 0}

        def _fake_worker(prompt, repo, timeout, **kwargs):
            if "Read-only final Worker report" not in prompt:
                round_n["n"] += 1
                (wt / "README.md").write_text(f"round {round_n['n']} edit\n", encoding="utf-8")
            return {
                "exit_code": 0, "stdout_bytes": 0, "stderr_bytes": 0,
                "report": {
                    "status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": ["README.md"], "selection_sha256": kwargs["selection_sha256"], "rule_results": [],
                },
            }

        def _fake_audit(prompt, snapshot, schema, timeout, required_paths, **kwargs):
            status = "FAIL" if round_n["n"] == 1 else "PASS"
            ev_refs = [
                {"receipt_path": k, "receipt_sha256": v}
                for k, v in sorted((kwargs.get("evidence_inventory") or {}).items())
            ]
            return {
                "status": status,
                "findings": [] if status == "PASS" else [{"severity": "MEDIUM", "file": "README.md", "line": 1, "rule": "DOC-001", "explanation": "revise", "fix": "edit"}],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": kwargs["selection_sha256"],
                "rule_results": [],
                "rubric": orchestrator.build_rubric_report(
                    decision="ACCEPT" if status == "PASS" else "REVISE",
                    hard_gate_passed=True,
                    evidence_refs=ev_refs,
                    findings_notes=None if status == "PASS" else {"correctness": ["revise"]},
                ),
            }

        args = argparse.Namespace(
            issue=437, execute=True, accept_isolated_pilot=True,
            expected_idf_version=None, toolchain_mode="container_only", allow_native_fallback=False,
            timeout=30, max_repairs=2, check_profile="quick", max_wall_seconds=300, consecutive_passes=2,
            no_progress_threshold=3, require_token_budget=False, require_cost_budget=False,
            approved_by="", journal=self.journal_path, feature_file=None, unit_id=None, trusted_definitions=None,
        )
        stream = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fake_worker), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             contextlib.redirect_stdout(stream):
            rc = harness_run.run(args)
        manifest_path = pathlib.Path(stream.getvalue().strip().split(": ", 1)[1])
        ev_root = manifest_path.parent
        self.addCleanup(shutil.rmtree, ev_root)
        self.assertEqual(rc, 0)
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(doc["state"], "READY_FOR_HUMAN_REVIEW")

        # No shared overwriting top-level per-round files
        for shared_name in ("auditor-report.json", "worker-report.json", "selected-rules.json", "checks.log", "quality-manifest.json"):
            self.assertFalse((ev_root / shared_name).exists(), shared_name)

        with Journal(self.journal_path) as journal:
            rounds = journal.list_control_rounds(doc["run_id"])
            self.assertEqual(len(rounds), 3)
            seen_audits: set[str] = set()
            for rnd in rounds:
                prefix = f"round-{rnd['round_num']:02d}/"
                refs = rnd["evidence_refs"]
                self.assertEqual(refs["round_dir"], f"round-{rnd['round_num']:02d}")
                for hash_col, ref_key in (
                    ("checks_summary_sha256", "checks_summary"),
                    ("manifest_sha256", "manifest"),
                    ("auditor_report_sha256", "auditor_report"),
                ):
                    h = rnd[hash_col]
                    self.assertTrue(h, (rnd["round_num"], hash_col))
                    rel = refs[ref_key]
                    self.assertTrue(rel.startswith(prefix), (rnd["round_num"], rel))
                    fpath = ev_root / rel
                    self.assertTrue(fpath.is_file(), rel)
                    self.assertEqual(fpath.stat().st_mode & 0o777, 0o444, rel)
                    self.assertEqual(hashlib.sha256(fpath.read_bytes()).hexdigest(), h)
                seen_audits.add(rnd["auditor_report_sha256"])
            # Each round preserves its own distinct immutable auditor report artifact
            self.assertEqual(len(seen_audits), 3)
            r1_audit = json.loads((ev_root / "round-01/auditor-report.json").read_text(encoding="utf-8"))
            r2_audit = json.loads((ev_root / "round-02/auditor-report.json").read_text(encoding="utf-8"))
            self.assertEqual(r1_audit["report"]["status"], "FAIL")
            self.assertEqual(r2_audit["report"]["status"], "PASS")

    def _spawn_and_kill_at_boundary(self, *, repo_path: pathlib.Path, journal_path: pathlib.Path, evidence_dir: pathlib.Path, boundary: str) -> str:
        """Spawn a real child process, hold/advance lease to target boundary, and SIGKILL it."""
        harness_dir = str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness")
        ready_file = evidence_dir.parent / f"ready_{boundary}_{time.time_ns()}.txt"
        child_script = f"""
import json, pathlib, sys, time
sys.path.insert(0, {harness_dir!r})
import orchestrator
from feature_state import compute_candidate_snapshot
from p1.state import Journal

repo = pathlib.Path({str(repo_path)!r})
journal_path = pathlib.Path({str(journal_path)!r})
ev_dir = pathlib.Path({str(evidence_dir)!r})
ev_dir.mkdir(parents=True, exist_ok=True)
boundary = {boundary!r}
issue_data = {{"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\\n- `README.md`\\n"}}
pol = orchestrator.build_run_policy(consecutive_passes_required=1, max_rounds=3, max_wall_seconds=60)
adm = orchestrator.admit_run(
    repo=repo, issue=4410, journal_path=journal_path,
    issue_data=issue_data,
    approval={{"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner"}},
    policy=pol, check_profile="quick",
    maker_provider="fixture", checker_provider="fixture",
    capability_overrides={{"fixture_maker": True, "fixture_checker": True}},
    require_isolated_worktree=False, require_protected_approval=False,
    allow_fixture_mode=True, evidence_dir=ev_dir,
)
rid = adm["run"]["run_id"]
(ev_dir / "frozen_check_plan.json").write_text(json.dumps(adm["check_plan"], indent=2, sort_keys=True), encoding="utf-8")
d_maker = orchestrator.dispatch_role(repo=repo, journal_path=journal_path, run_id=rid, role="maker", in_flight_round=1)
tok = d_maker["dispatch_token"]
if boundary == "maker_dispatch":
    pathlib.Path({str(ready_file)!r}).write_text(rid, encoding="utf-8")
    time.sleep(60)
orchestrator.transition_state(
    journal_path=journal_path, run_id=rid, expected="DISPATCHED", next_state="MAKER_RUNNING",
    actor_role="host", action="maker_started", dispatch_token=tok,
)
(repo / "README.md").write_text("partial dirty maker work\\n", encoding="utf-8")
if boundary == "maker_running":
    pathlib.Path({str(ready_file)!r}).write_text(rid, encoding="utf-8")
    time.sleep(60)
snap = compute_candidate_snapshot(repo, base_sha=adm["run"]["base_sha"])
with Journal(journal_path) as j:
    j.record_control_progress(
        rid, expected_state="MAKER_RUNNING", actor_role="host", op="maker_completed",
        expected_dispatch_token=tok, wall_elapsed_delta_s=10.0,
        in_flight_round=1, candidate_sha256=snap["candidate_sha256"], last_diff_sha256=snap["diff_sha256"],
    )
orchestrator.transition_state(
    journal_path=journal_path, run_id=rid, expected="MAKER_RUNNING", next_state="VERIFYING",
    actor_role="host", action="host_verifying", dispatch_token=tok,
)
r1 = ev_dir / "round-01"
r1.mkdir(parents=True, exist_ok=True)
if boundary == "verifying":
    # Simulate interrupted partial/corrupt evidence write
    (r1 / "checks_summary.json").write_text('{{"truncated": true', encoding="utf-8")
    (r1 / ".staging.tmp").write_text("partial", encoding="utf-8")
    pathlib.Path({str(ready_file)!r}).write_text(rid, encoding="utf-8")
    time.sleep(60)
with Journal(journal_path) as j:
    j.transition_control_run(
        rid, expected="VERIFYING", next_state="REPAIR_REQUIRED", actor_role="host",
        action="maker_verified_ready_for_checker", expected_dispatch_token=tok, clear_dispatch=True,
        update_fields={{"candidate_sha256": snap["candidate_sha256"], "last_diff_sha256": snap["diff_sha256"]}},
    )
d_chk = orchestrator.dispatch_role(repo=repo, journal_path=journal_path, run_id=rid, role="checker", in_flight_round=1)
chk_tok = d_chk["dispatch_token"]
orchestrator.transition_state(
    journal_path=journal_path, run_id=rid, expected="DISPATCHED", next_state="CHECKING",
    actor_role="host", action="checker_started", dispatch_token=chk_tok,
)
(r1 / "audit_report.json").write_text('{{"partial_audit": ', encoding="utf-8")
pathlib.Path({str(ready_file)!r}).write_text(rid, encoding="utf-8")
time.sleep(60)
"""
        proc = subprocess.Popen([sys.executable, "-c", child_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 15.0
            while not ready_file.is_file():
                if proc.poll() is not None:
                    out, err = proc.communicate(timeout=5)
                    raise AssertionError(f"Child exited early ({proc.returncode}): {out.decode()} {err.decode()}")
                if time.monotonic() > deadline:
                    raise AssertionError(f"Timed out waiting for child boundary {boundary}")
                time.sleep(0.05)
            run_id = ready_file.read_text(encoding="utf-8").strip()
            # Verify live lease blocks concurrent reconcile/resume while child is alive!
            with self.assertRaises(orchestrator.DuplicateDispatchError):
                orchestrator.reconcile_run(
                    repo=repo_path,
                    journal_path=journal_path,
                    run_id=run_id,
                    evidence_dir=evidence_dir,
                    issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
                )
        finally:
            if proc.poll() is None:
                os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=10)
            if proc.stdout is not None:
                proc.stdout.close()
            if proc.stderr is not None:
                proc.stderr.close()
            if ready_file.exists():
                ready_file.unlink()
        return run_id

    def test_p08c_kill_restart_at_maker_verification_checker_and_commit_boundaries_fresh_process(self):
        # Ensure base repo fixture has scripts/verify_structure.py so profile="quick" check.run_checks passes
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "verify_structure.py").write_text("print('OK')\n", encoding="utf-8")
        _git(self.repo, "add", "scripts/verify_structure.py")
        _git(self.repo, "commit", "-qm", "add verify_structure fixture")

        # 1. Maker running boundary: SIGKILL -> fresh process refuses blind Maker re-exec & preserves dirty worktree
        r_maker = self.base_dir / "repo_maker"
        shutil.copytree(self.repo, r_maker)
        _git(r_maker, "checkout", "-q", "-B", "feature/4410-maker")
        j_maker = self.base_dir / "host" / "maker.sqlite"
        ev_maker = self.base_dir / "ev_maker"
        rid_maker = self._spawn_and_kill_at_boundary(
            repo_path=r_maker, journal_path=j_maker, evidence_dir=ev_maker, boundary="maker_running"
        )
        issue_4410 = {"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"}
        rec_maker = orchestrator.reconcile_run(
            repo=r_maker, journal_path=j_maker, run_id=rid_maker, evidence_dir=ev_maker, issue_data=issue_4410
        )
        self.assertEqual(rec_maker["status"], "BLOCKED")
        self.assertEqual(rec_maker["recovery_reason"], "interrupted_maker_preserved")
        self.assertFalse(rec_maker["can_resume"])
        self.assertEqual((r_maker / "README.md").read_text(encoding="utf-8"), "partial dirty maker work\n")

        # 2. Maker dispatch boundary (killed before MAKER_RUNNING): safe reconcile -> resume to READY_FOR_HUMAN_REVIEW
        r_disp = self.base_dir / "repo_disp"
        shutil.copytree(self.repo, r_disp)
        _git(r_disp, "checkout", "-q", "-B", "feature/4410-disp")
        j_disp = self.base_dir / "host" / "disp.sqlite"
        ev_disp = self.base_dir / "ev_disp"
        rid_disp = self._spawn_and_kill_at_boundary(
            repo_path=r_disp, journal_path=j_disp, evidence_dir=ev_disp, boundary="maker_dispatch"
        )
        resumed_disp = orchestrator.run_maker_checker_loop(
            repo=r_disp,
            issue=4410,
            journal_path=j_disp,
            evidence_dir=ev_disp,
            issue_data=issue_4410,
            maker_fn=lambda wt, _c: ((wt / "README.md").write_text("clean resumed maker\n", encoding="utf-8"), {"changed_path": "README.md"})[1],
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            resume_run_id=rid_disp,
        )
        self.assertEqual(resumed_disp["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertFalse(resumed_disp["ready_to_merge"])

        # 3. Verification boundary with interrupted partial evidence write -> quarantined, Maker NOT re-run
        r_ver = self.base_dir / "repo_ver"
        shutil.copytree(self.repo, r_ver)
        _git(r_ver, "checkout", "-q", "-B", "feature/4410-ver")
        j_ver = self.base_dir / "host" / "ver.sqlite"
        ev_ver = self.base_dir / "ev_ver"
        rid_ver = self._spawn_and_kill_at_boundary(
            repo_path=r_ver, journal_path=j_ver, evidence_dir=ev_ver, boundary="verifying"
        )
        maker_called_on_ver_resume = {"n": 0}
        resumed_ver = orchestrator.run_maker_checker_loop(
            repo=r_ver,
            issue=4410,
            journal_path=j_ver,
            evidence_dir=ev_ver,
            issue_data=issue_4410,
            maker_fn=lambda _wt, _c: (maker_called_on_ver_resume.__setitem__("n", maker_called_on_ver_resume["n"] + 1), {"changed_path": "README.md"})[1],
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            resume_run_id=rid_ver,
        )
        self.assertEqual(resumed_ver["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(maker_called_on_ver_resume["n"], 0)
        self.assertTrue((ev_ver / "interrupted").is_dir())
        with Journal(j_ver) as j:
            r_ver_run = j.get_control_run(rid_ver)
            # Persisted elapsed wall budget (10.0s flushed before kill) is preserved, never reset
            self.assertGreaterEqual(r_ver_run["budget_consumed"]["wall_seconds"], 10.0)

        # 4. Checker boundary with interrupted partial audit_report.json -> quarantined, Maker NOT re-run
        r_chk = self.base_dir / "repo_chk"
        shutil.copytree(self.repo, r_chk)
        _git(r_chk, "checkout", "-q", "-B", "feature/4410-chk")
        j_chk = self.base_dir / "host" / "chk.sqlite"
        ev_chk = self.base_dir / "ev_chk"
        rid_chk = self._spawn_and_kill_at_boundary(
            repo_path=r_chk, journal_path=j_chk, evidence_dir=ev_chk, boundary="checking"
        )
        maker_called_on_chk_resume = {"n": 0}
        resumed_chk = orchestrator.run_maker_checker_loop(
            repo=r_chk,
            issue=4410,
            journal_path=j_chk,
            evidence_dir=ev_chk,
            issue_data=issue_4410,
            maker_fn=lambda _wt, _c: (maker_called_on_chk_resume.__setitem__("n", maker_called_on_chk_resume["n"] + 1), {"changed_path": "README.md"})[1],
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            resume_run_id=rid_chk,
        )
        self.assertEqual(resumed_chk["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(maker_called_on_chk_resume["n"], 0)
        self.assertTrue((ev_chk / "interrupted").is_dir())

        # 5. Commit/checkpoint boundary between N=2 confirming passes -> resumes ONLY confirming pass
        r_ckpt = self.base_dir / "repo_ckpt"
        shutil.copytree(self.repo, r_ckpt)
        _git(r_ckpt, "checkout", "-q", "-B", "feature/4410-ckpt")
        j_ckpt = self.base_dir / "host" / "ckpt.sqlite"
        ev_ckpt = self.base_dir / "ev_ckpt"
        pol_n2 = orchestrator.build_run_policy(consecutive_passes_required=2, max_rounds=4, max_wall_seconds=120)
        round_1_done = orchestrator.run_maker_checker_loop(
            repo=r_ckpt,
            issue=4410,
            journal_path=j_ckpt,
            evidence_dir=ev_ckpt,
            issue_data=issue_4410,
            maker_fn=lambda wt, _c: ((wt / "README.md").write_text("n2 fixed\n", encoding="utf-8"), {"changed_path": "README.md"})[1],
            approval={"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner"},
            policy=pol_n2,
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            cancel_check=lambda rnd: rnd == 2,
        )
        self.assertEqual(round_1_done["state"], "CANCELLED")

        # Now test clean REPAIR_REQUIRED checkpoint resume before cancel
        r_ckpt2 = self.base_dir / "repo_ckpt2"
        shutil.copytree(self.repo, r_ckpt2)
        _git(r_ckpt2, "checkout", "-q", "-B", "feature/4410-ckpt2")
        j_ckpt2 = self.base_dir / "host" / "ckpt2.sqlite"
        ev_ckpt2 = self.base_dir / "ev_ckpt2"
        adm2 = orchestrator.admit_run(
            repo=r_ckpt2, issue=4410, journal_path=j_ckpt2, issue_data=issue_4410,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner"},
            policy=pol_n2, check_profile="quick",
            maker_provider="fixture", checker_provider="fixture",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False, require_protected_approval=False,
            allow_fixture_mode=True, evidence_dir=ev_ckpt2,
        )
        rid2 = adm2["run"]["run_id"]
        (ev_ckpt2 / "frozen_check_plan.json").write_text(json.dumps(adm2["check_plan"], indent=2, sort_keys=True), encoding="utf-8")
        # Complete round 1 PASS manually via run_checks + checker -> REPAIR_REQUIRED (consecutive_passes=1)
        d1 = orchestrator.dispatch_role(repo=r_ckpt2, journal_path=j_ckpt2, run_id=rid2, role="maker", in_flight_round=1)
        orchestrator.transition_state(
            journal_path=j_ckpt2, run_id=rid2, expected="DISPATCHED", next_state="MAKER_RUNNING",
            actor_role="host", action="maker_started", dispatch_token=d1["dispatch_token"],
        )
        (r_ckpt2 / "README.md").write_text("n2 clean edit\n", encoding="utf-8")
        snap2 = feature_state.compute_candidate_snapshot(r_ckpt2, base_sha=adm2["run"]["base_sha"])
        sel2 = orchestrator.select_rules(
            r_ckpt2,
            list(adm2["admission"]["scope"]),
            base=adm2["run"]["base_sha"],
            expected_source_sha=snap2["source_sha"],
        )
        orchestrator.transition_state(
            journal_path=j_ckpt2, run_id=rid2, expected="MAKER_RUNNING", next_state="VERIFYING",
            actor_role="host", action="host_verifying", dispatch_token=d1["dispatch_token"],
        )
        r1_dir = ev_ckpt2 / "round-01"
        r1_dir.mkdir(parents=True)
        cs1 = orchestrator.run_checks(
            r_ckpt2, base_sha=adm2["run"]["base_sha"], profile="quick",
            evidence_dir=r1_dir, frozen_plan_path=ev_ckpt2 / "frozen_check_plan.json",
            run_quality_gates=True, journal_path=j_ckpt2, issue=4410, run_id=rid2,
        )
        cs1_sha = hashlib.sha256((r1_dir / "checks_summary.json").read_bytes()).hexdigest()
        m1_sha = hashlib.sha256((r1_dir / "manifest.json").read_bytes()).hexdigest()
        with Journal(j_ckpt2) as j:
            j.transition_control_run(
                rid2, expected="VERIFYING", next_state="REPAIR_REQUIRED", actor_role="host",
                action="maker_verified_ready_for_checker", expected_dispatch_token=d1["dispatch_token"], clear_dispatch=True,
                update_fields={"candidate_sha256": snap2["candidate_sha256"], "last_diff_sha256": snap2["diff_sha256"]},
            )
        dc1 = orchestrator.dispatch_role(repo=r_ckpt2, journal_path=j_ckpt2, run_id=rid2, role="checker", in_flight_round=1)
        orchestrator.transition_state(
            journal_path=j_ckpt2, run_id=rid2, expected="DISPATCHED", next_state="CHECKING",
            actor_role="host", action="checker_started", dispatch_token=dc1["dispatch_token"],
        )
        ev_refs1 = [{"receipt_path": "checks_summary.json", "receipt_sha256": cs1_sha}]
        rub1 = orchestrator.build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs1)
        a1_sha = orchestrator.write_immutable_json(
            r1_dir / "audit_report.json",
            {
                "run_id": rid2, "round_num": 1, "source_sha": snap2["source_sha"],
                "candidate_sha256": snap2["candidate_sha256"], "diff_sha256": snap2["diff_sha256"],
                "selection_sha256": sel2["selection_sha256"],
                "report": {
                    "status": "PASS", "findings": [], "limitations": [], "reviewed_scope": ["README.md"],
                    "selection_sha256": sel2["selection_sha256"], "rule_results": [], "rubric": rub1,
                },
            },
        )
        orchestrator.record_round_result(
            journal_path=j_ckpt2, run_id=rid2, dispatch_token=dc1["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256=snap2["candidate_sha256"], diff_sha256=snap2["diff_sha256"],
            policy_sha256=adm2["policy"]["policy_sha256"], check_plan_sha256=adm2["check_plan"]["plan_sha256"],
            selection_sha256=sel2["selection_sha256"], selected_ids=sel2["selected_ids"],
            checks_summary_sha256=cs1_sha, manifest_sha256=m1_sha, auditor_report_sha256=a1_sha,
            evidence_dir=ev_ckpt2,
            evidence_refs={"round_dir": "round-01", "checks_summary": "round-01/checks_summary.json", "manifest": "round-01/manifest.json", "auditor_report": "round-01/audit_report.json"},
            rubric=rub1, wall_elapsed_s=4.0,
        )
        # Resume in a fresh call -> must run confirming pass ONLY (0 Maker calls) and reach READY_FOR_HUMAN_REVIEW
        ckpt_maker_calls = {"n": 0}
        resumed_ckpt2 = orchestrator.run_maker_checker_loop(
            repo=r_ckpt2,
            issue=4410,
            journal_path=j_ckpt2,
            evidence_dir=ev_ckpt2,
            issue_data=issue_4410,
            maker_fn=lambda _wt, _c: (ckpt_maker_calls.__setitem__("n", ckpt_maker_calls["n"] + 1), {"changed_path": "README.md"})[1],
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            resume_run_id=rid2,
        )
        self.assertEqual(resumed_ckpt2["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(resumed_ckpt2["consecutive_passes"], 2)
        self.assertEqual(ckpt_maker_calls["n"], 0)

    def test_p08c_ambiguous_ownership_cancel_persisted_budget_and_stale_n_pass_rejection(self):
        # 1. Ambiguous ownership (foreign host or missing PID) refused conservatively
        ev_amb = self.base_dir / "ev_amb"
        adm = self._admit(
            policy=orchestrator.build_run_policy(consecutive_passes_required=2, max_rounds=3, max_wall_seconds=20),
            evidence_dir=ev_amb,
        )
        rid = adm["run"]["run_id"]
        d = orchestrator.dispatch_role(
            repo=self.repo, journal_path=self.journal_path, run_id=rid, role="maker",
            lease_owner={"pid": 999999, "start_ticks": "123", "host": "remote-worker-host"},
        )
        rec_amb = orchestrator.reconcile_run(
            repo=self.repo, journal_path=self.journal_path, run_id=rid,
            evidence_dir=ev_amb, issue_data=self.issue_data,
        )
        self.assertEqual(rec_amb["decision"], "REFUSED_AMBIGUOUS_OWNERSHIP")
        self.assertFalse(rec_amb["can_resume"])
        self.assertEqual(rec_amb["status"], "DISPATCHED")

        # 2. Cancel + dead lease reconciles cleanly to CANCELLED preserving dirty worktree
        (self.repo / "README.md").write_text("dirty user work\n", encoding="utf-8")
        with Journal(self.journal_path) as j:
            j.db.execute("UPDATE control_runs SET lease_owner_host='', lease_owner_pid=99999999, cancel_requested=1, cancel_reason='user cancel' WHERE run_id=?", (rid,))
        rec_can = orchestrator.reconcile_run(
            repo=self.repo, journal_path=self.journal_path, run_id=rid,
            evidence_dir=ev_amb, issue_data=self.issue_data,
        )
        self.assertEqual(rec_can["status"], "CANCELLED")
        self.assertFalse(rec_can["can_resume"])
        self.assertEqual((self.repo / "README.md").read_text(encoding="utf-8"), "dirty user work\n")

        # 3. Persisted elapsed wall budget exhausted before restart -> immediately ESCALATED (no fresh retry budget)
        (self.repo / "README.md").write_text("before\n", encoding="utf-8")
        ev_bud = self.base_dir / "ev_bud"
        adm_b = self._admit(
            policy=orchestrator.build_run_policy(consecutive_passes_required=1, max_rounds=3, max_wall_seconds=15),
            evidence_dir=ev_bud,
        )
        rid_b = adm_b["run"]["run_id"]
        db = orchestrator.dispatch_role(
            repo=self.repo, journal_path=self.journal_path, run_id=rid_b, role="checker",
            lease_owner={"pid": 99999998, "start_ticks": "1", "host": os.uname().nodename},
        )
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=rid_b, expected="DISPATCHED", next_state="CHECKING",
            actor_role="host", action="checker_started", dispatch_token=db["dispatch_token"],
        )
        with Journal(self.journal_path) as j:
            j.record_control_progress(
                rid_b, expected_state="CHECKING", actor_role="host", op="budget_tick",
                expected_dispatch_token=db["dispatch_token"], wall_elapsed_delta_s=16.0,
            )
        rec_bud = orchestrator.reconcile_run(
            repo=self.repo, journal_path=self.journal_path, run_id=rid_b,
            evidence_dir=ev_bud, issue_data=self.issue_data,
        )
        self.assertEqual(rec_bud["status"], "ESCALATED")
        self.assertEqual(rec_bud["decision"], "ESCALATED_BUDGET_EXHAUSTED")
        self.assertFalse(rec_bud["can_resume"])

        # 4. Stale N=2 pass credit rejected if candidate drifts or prior evidence is tampered
        (self.repo / "README.md").write_text("before\n", encoding="utf-8")
        ev_n2 = self.base_dir / "ev_n2"
        adm_n2 = self._admit(
            policy=orchestrator.build_run_policy(consecutive_passes_required=2, max_rounds=3, max_wall_seconds=60),
            evidence_dir=ev_n2,
        )
        rid_n2 = adm_n2["run"]["run_id"]
        r1_n2 = ev_n2 / "round-01"
        r1_n2.mkdir(parents=True)
        dc_n2 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=rid_n2, role="checker", in_flight_round=1)
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=rid_n2, expected="DISPATCHED", next_state="CHECKING",
            actor_role="host", action="checker_started", dispatch_token=dc_n2["dispatch_token"],
        )
        snap_n2 = feature_state.compute_candidate_snapshot(self.repo, base_sha=adm_n2["run"]["base_sha"])
        cs_n2_sha = orchestrator.write_immutable_json(
            r1_n2 / "checks_summary.json",
            {
                "status": "PASS",
                "run_id": rid_n2, "round_num": 1, "source_sha": snap_n2["source_sha"],
                "candidate_sha256": snap_n2["candidate_sha256"], "diff_sha256": snap_n2["diff_sha256"],
                "checks_complete": True, "all_passed": True,
                "checks": [{"check_id": "verify-structure", "status": "PASS", "exit_code": 0}],
            },
        )
        rub_n2 = orchestrator.build_rubric_report(
            decision="ACCEPT", hard_gate_passed=True,
            evidence_refs=[{"receipt_path": "checks_summary.json", "receipt_sha256": cs_n2_sha}],
        )
        aud_n2_sha = orchestrator.write_immutable_json(
            r1_n2 / "audit_report.json",
            {
                "run_id": rid_n2, "round_num": 1, "source_sha": snap_n2["source_sha"],
                "candidate_sha256": snap_n2["candidate_sha256"], "diff_sha256": snap_n2["diff_sha256"],
                "selection_sha256": adm_n2["selection"]["selection_sha256"],
                "report": {
                    "status": "PASS", "findings": [], "limitations": [], "reviewed_scope": [],
                    "selection_sha256": adm_n2["selection"]["selection_sha256"], "rule_results": [], "rubric": rub_n2,
                },
            },
        )
        orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=rid_n2, dispatch_token=dc_n2["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256=snap_n2["candidate_sha256"], diff_sha256=snap_n2["diff_sha256"],
            policy_sha256=adm_n2["policy"]["policy_sha256"], check_plan_sha256=adm_n2["check_plan"]["plan_sha256"],
            selection_sha256=adm_n2["selection"]["selection_sha256"], selected_ids=adm_n2["selection"]["selected_ids"],
            checks_summary_sha256=cs_n2_sha, auditor_report_sha256=aud_n2_sha,
            evidence_dir=ev_n2,
            evidence_refs={"round_dir": "round-01", "checks_summary": "round-01/checks_summary.json", "auditor_report": "round-01/audit_report.json"},
            rubric=rub_n2, wall_elapsed_s=1.0,
        )
        (self.repo / "README.md").write_text("stale drift between passes\n", encoding="utf-8")
        rec_n2 = orchestrator.reconcile_run(
            repo=self.repo, journal_path=self.journal_path, run_id=rid_n2,
            evidence_dir=ev_n2, issue_data=self.issue_data,
        )
        self.assertEqual(rec_n2["status"], "BLOCKED")
        self.assertEqual(rec_n2["recovery_reason"], "confirming_pass_candidate_drift")
        self.assertFalse(rec_n2["can_resume"])
        self.assertEqual(rec_n2["acceptance_mode"], "FIXTURE_CONTROLLED_NOT_PRODUCTION_ACCEPTANCE")

    def test_p08c_deferred_p08b_real_evidence_validation_and_post_audit_integrity(self):
        # Real-mode run admission (codex + agy providers, non-fixture)
        wt = self._make_linked_worktree(issue=441, suffix="real-ev")
        self._seed_harness_files(wt)
        wt_base = _git(wt, "rev-parse", "HEAD")
        ev_real = self.base_dir / "ev_real"
        adm = orchestrator.admit_run(
            repo=wt,
            issue=441,
            journal_path=self.journal_path,
            base_sha=wt_base,
            issue_data={"state": "OPEN", "title": "Real Mode Validation", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            approval={"status": "SUPERVISED_ISSUE_OPEN", "isolated_pilot_attested": True},
            policy=orchestrator.build_run_policy(consecutive_passes_required=1, max_rounds=4, max_wall_seconds=120),
            check_profile="quick",
            maker_provider="codex",
            checker_provider="agy",
            capability_overrides={"codex_path": "/bin/true", "agy_path": "/bin/true"},
            evidence_dir=ev_real,
        )
        rid = adm["run"]["run_id"]
        (ev_real / "frozen_check_plan.json").write_text(json.dumps(adm["check_plan"], indent=2, sort_keys=True), encoding="utf-8")
        (wt / "README.md").write_text("real verified change\n", encoding="utf-8")
        snap = feature_state.compute_candidate_snapshot(wt, base_sha=adm["run"]["base_sha"])

        dc = orchestrator.dispatch_role(repo=wt, journal_path=self.journal_path, run_id=rid, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=rid, expected="DISPATCHED", next_state="CHECKING",
            actor_role="host", action="checker_started", dispatch_token=dc["dispatch_token"],
        )

        # Build complete real round-01 evidence using actual check.run_checks
        r1 = ev_real / "round-01"
        r1.mkdir()
        cs = orchestrator.run_checks(
            wt, base_sha=adm["run"]["base_sha"], profile="quick",
            evidence_dir=r1, frozen_plan_path=ev_real / "frozen_check_plan.json",
            run_quality_gates=True, journal_path=self.journal_path, issue=441, run_id=rid,
        )
        cs_sha = hashlib.sha256((r1 / "checks_summary.json").read_bytes()).hexdigest()
        m_sha = hashlib.sha256((r1 / "manifest.json").read_bytes()).hexdigest()
        ev_refs = [{"receipt_path": "checks_summary.json", "receipt_sha256": cs_sha}]
        rub = orchestrator.build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs)

        # 1. Swapped auditor report (wrong run_id) MUST fail closed
        swap_audit_sha = orchestrator.write_immutable_json(
            r1 / "swapped_audit.json",
            {"run_id": "other-run", "round_num": 1, "status": "PASS", "findings": [], "limitations": [], "rubric": rub},
        )
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path, run_id=rid, dispatch_token=dc["dispatch_token"],
                outcome="PASS", host_checks_passed=True, checker_passed=True,
                candidate_sha256=snap["candidate_sha256"], diff_sha256=snap["diff_sha256"],
                policy_sha256=adm["policy"]["policy_sha256"], check_plan_sha256=adm["check_plan"]["plan_sha256"],
                selection_sha256=adm["selection"]["selection_sha256"],
                checks_summary_sha256=cs_sha, manifest_sha256=m_sha, auditor_report_sha256=swap_audit_sha,
                evidence_dir=ev_real,
                evidence_refs={"round_dir": "round-01", "checks_summary": "round-01/checks_summary.json", "manifest": "round-01/manifest.json", "auditor_report": "round-01/swapped_audit.json"},
                rubric=rub,
            )

        # 2. Missing manifest in REAL mode MUST fail closed
        good_audit_sha = orchestrator.write_immutable_json(
            r1 / "audit_report.json",
            {
                "run_id": rid, "round_num": 1, "source_sha": snap["source_sha"],
                "candidate_sha256": snap["candidate_sha256"], "diff_sha256": snap["diff_sha256"],
                "selection_sha256": adm["selection"]["selection_sha256"],
                "report": {
                    "status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": ["README.md"], "selection_sha256": adm["selection"]["selection_sha256"],
                    "rule_results": [], "rubric": rub,
                },
            },
        )
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path, run_id=rid, dispatch_token=dc["dispatch_token"],
                outcome="PASS", host_checks_passed=True, checker_passed=True,
                candidate_sha256=snap["candidate_sha256"], diff_sha256=snap["diff_sha256"],
                policy_sha256=adm["policy"]["policy_sha256"], check_plan_sha256=adm["check_plan"]["plan_sha256"],
                selection_sha256=adm["selection"]["selection_sha256"],
                checks_summary_sha256=cs_sha, auditor_report_sha256=good_audit_sha,
                evidence_dir=ev_real,
                evidence_refs={"round_dir": "round-01", "checks_summary": "round-01/checks_summary.json", "auditor_report": "round-01/audit_report.json"},
                rubric=rub,
            )

        # 3. Waived summary MUST fail closed
        waived_cs = dict(cs, waived=True)
        waived_sha = orchestrator.write_immutable_json(r1 / "waived_cs.json", waived_cs)
        with self.assertRaises(orchestrator.RoleAccessDenied):
            orchestrator.record_round_result(
                journal_path=self.journal_path, run_id=rid, dispatch_token=dc["dispatch_token"],
                outcome="PASS", host_checks_passed=True, checker_passed=True,
                candidate_sha256=snap["candidate_sha256"], diff_sha256=snap["diff_sha256"],
                policy_sha256=adm["policy"]["policy_sha256"], check_plan_sha256=adm["check_plan"]["plan_sha256"],
                selection_sha256=adm["selection"]["selection_sha256"],
                checks_summary_sha256=waived_sha, manifest_sha256=m_sha, auditor_report_sha256=good_audit_sha,
                evidence_dir=ev_real,
                evidence_refs={"round_dir": "round-01", "checks_summary": "round-01/waived_cs.json", "manifest": "round-01/manifest.json", "auditor_report": "round-01/audit_report.json"},
                rubric=rub,
            )

        # 4. Complete real PASS evidence + post-audit-gates.json succeeds and distinguishes REAL_ACCEPTANCE_CANDIDATE
        pag_doc = orchestrator.evaluate_quality_gates(wt, adm["run"]["base_sha"], "manifest.json", r1)
        orchestrator.write_immutable_json(r1 / "post-audit-gates.json", pag_doc)
        accepted = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=rid, dispatch_token=dc["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256=snap["candidate_sha256"], diff_sha256=snap["diff_sha256"],
            policy_sha256=adm["policy"]["policy_sha256"], check_plan_sha256=adm["check_plan"]["plan_sha256"],
            selection_sha256=adm["selection"]["selection_sha256"],
            checks_summary_sha256=cs_sha, manifest_sha256=m_sha, auditor_report_sha256=good_audit_sha,
            evidence_dir=ev_real,
            evidence_refs={
                "round_dir": "round-01",
                "checks_summary": "round-01/checks_summary.json",
                "manifest": "round-01/manifest.json",
                "auditor_report": "round-01/audit_report.json",
                "post_audit_gates": "round-01/post-audit-gates.json",
            },
            rubric=rub,
        )
        self.assertEqual(accepted["state"], "READY_FOR_HUMAN_REVIEW")
        rec_ok = orchestrator.reconcile_run(
            repo=wt, journal_path=self.journal_path, run_id=rid,
            evidence_dir=ev_real,
            issue_data={"state": "OPEN", "title": "Real Mode Validation", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        self.assertEqual(rec_ok["decision"], "TERMINAL_PRESERVED")
        self.assertEqual(rec_ok["acceptance_mode"], "REAL_ACCEPTANCE_CANDIDATE")
        self.assertFalse(rec_ok["ready_to_merge"])

        # 5. Post-audit candidate drift MUST invalidate READY_FOR_HUMAN_REVIEW -> BLOCKED
        (wt / "README.md").write_text("mutated after audit!\n", encoding="utf-8")
        rec_drift = orchestrator.reconcile_run(
            repo=wt, journal_path=self.journal_path, run_id=rid,
            evidence_dir=ev_real,
            issue_data={"state": "OPEN", "title": "Real Mode Validation", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        self.assertEqual(rec_drift["status"], "BLOCKED")
        self.assertEqual(rec_drift["recovery_reason"], "post_audit_candidate_drift")

    def test_p08c_observability_status_resume_signals_redaction_and_g0_scope_drift(self):
        (self.repo / "scripts").mkdir(exist_ok=True)
        (self.repo / "scripts" / "verify_structure.py").write_text("print('OK')\n", encoding="utf-8")
        _git(self.repo, "add", "scripts/verify_structure.py")
        _git(self.repo, "commit", "-qm", "add verify_structure fixture for obs")
        obs_base = _git(self.repo, "rev-parse", "HEAD")

        ev_obs = self.base_dir / "ev_obs"
        res = orchestrator.run_maker_checker_loop(
            repo=self.repo,
            issue=437,
            journal_path=self.journal_path,
            evidence_dir=ev_obs,
            issue_data=self.issue_data,
            maker_fn=lambda wt, _c: ((wt / "README.md").write_text("obs ok\n", encoding="utf-8"), {"changed_path": "README.md"})[1],
            approval={"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner"},
            policy=orchestrator.build_run_policy(consecutive_passes_required=1, max_rounds=2, max_wall_seconds=120),
            base_sha=obs_base,
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
        )
        self.assertEqual(res["state"], "READY_FOR_HUMAN_REVIEW", res)
        rid = res["run_id"]

        # 1. p1/cli.py status, signals, resume, and orchestrator.py status/reconcile expose required fields & redact tokens
        with patch.object(sys, "argv", ["cli.py", "status", "--run-id", rid, "--state", str(self.journal_path)]), \
             contextlib.redirect_stdout(io.StringIO()) as out_st:
            self.assertEqual(p1_cli.main(), 0)
        st_doc = json.loads(out_st.getvalue())
        for req_key in ("run_id", "round_num", "phase", "lease", "receipt_refs", "recovery_reason", "decision", "blocker", "next_action", "recent_signals"):
            self.assertIn(req_key, st_doc)
        self.assertFalse(st_doc["ready_to_merge"])
        self.assertNotIn("dispatch_token", json.dumps(st_doc["lease"]))

        with patch.object(sys, "argv", ["cli.py", "signals", "--issue", "437", "--run-id", rid, "--state", str(self.journal_path)]), \
             contextlib.redirect_stdout(io.StringIO()) as out_sig:
            self.assertEqual(p1_cli.main(), 0)
        sig_doc = json.loads(out_sig.getvalue())
        self.assertIn("orchestration", sig_doc)
        self.assertEqual(sig_doc["orchestration"]["run_id"], rid)
        self.assertIn("receipt_refs", sig_doc["orchestration"])
        self.assertEqual(sig_doc["orchestration"]["acceptance_mode"], "FIXTURE_CONTROLLED_NOT_PRODUCTION_ACCEPTANCE")

        resumed_view = feature_state.session_start(
            issue=437, repo=self.repo, state_db=self.journal_path, offline=True,
            issue_data={**self.issue_data, "scope": ("README.md",), "issue_sha256": hashlib.sha256(self.issue_data["body"].encode()).hexdigest()},
        )
        self.assertIsNotNone(resumed_view["control_run"])
        self.assertEqual(resumed_view["control_run"]["run_id"], rid)
        self.assertIn("receipt_refs", resumed_view["control_run"])
        self.assertIn("lease", resumed_view["control_run"])

        # 2. Scope/G0 drift on reconcile blocks cleanly and preserves worktree
        (self.repo / "AGENTS.md").write_text("# Drifted AGENTS\n", encoding="utf-8")
        with patch.object(sys, "argv", ["orchestrator.py", "reconcile", "--run-id", rid, "--repo", str(self.repo), "--state", str(self.journal_path), "--offline"]), \
             contextlib.redirect_stdout(io.StringIO()) as out_rec:
            rc_rec = orchestrator.main()
        self.assertEqual(rc_rec, 2)
        rec_doc = json.loads(out_rec.getvalue())
        self.assertEqual(rec_doc["status"], "BLOCKED")
        self.assertEqual(rec_doc["recovery_reason"], "g0_gate_failed")

    def test_p08c_post_audit_gates_enforced_with_selected_rules(self):
        # Verify _post_audit_gates_passed accepts deferred STANDARDS-CHECK only when all other selected gates PASS,
        # and fails closed on any non-STANDARDS failure or STANDARDS FAIL/WAIVED.
        base_doc = {
            "auto_check": "BLOCKED",
            "mandatory_blockers": [],
            "standards": {"status": "NOT_VERIFIED", "selection_sha256": "a" * 64},
            "results": [
                {"rule_id": "SECRET-SCAN", "status": "PASS", "limitation": ""},
                {"rule_id": "DIFF-CHECK", "status": "PASS", "limitation": ""},
                {"rule_id": "BACKEND-CHECK", "status": "PASS", "limitation": ""},
                {"rule_id": "STANDARDS-CHECK", "status": "NOT_VERIFIED", "limitation": "Manifest lacks standards payload"},
                {"rule_id": "FIRMWARE-CHECK", "status": "NOT_RUN", "limitation": "Not selected by changed-file risk routing"},
            ],
        }
        self.assertTrue(
            orchestrator._post_audit_gates_passed(
                base_doc, selected_ids=["GO-ERR-01"], expected_selection_sha256="a" * 64
            )
        )
        self.assertFalse(
            orchestrator._post_audit_gates_passed(
                base_doc, selected_ids=(), expected_selection_sha256="a" * 64
            )
        )
        bad_secret = {**base_doc, "results": [{"rule_id": "SECRET-SCAN", "status": "FAIL", "limitation": "hit"}, *base_doc["results"][1:]]}
        self.assertFalse(
            orchestrator._post_audit_gates_passed(
                bad_secret, selected_ids=["GO-ERR-01"], expected_selection_sha256="a" * 64
            )
        )
        bad_std = {**base_doc, "standards": {"status": "FAIL", "selection_sha256": "a" * 64}}
        self.assertFalse(
            orchestrator._post_audit_gates_passed(
                bad_std, selected_ids=["GO-ERR-01"], expected_selection_sha256="a" * 64
            )
        )

        # Verify run_maker_checker_loop writes post-audit-gates.json even when selected_ids is non-empty,
        # so terminal reconcile_run(require_post_audit=True) succeeds cleanly.
        wt = self._make_linked_worktree(issue=441, suffix="sel-pag")
        self._seed_harness_files(wt)
        wt_base = _git(wt, "rev-parse", "HEAD")
        ev_sel = self.base_dir / "ev_sel_pag"
        sel_hash = "b" * 64
        stub_sel = {
            "selected_ids": ["DOC-001"],
            "selection_sha256": sel_hash,
            "agent_input_sha256": "c" * 64,
            "rules": [{"rule_id": "DOC-001", "rule_sha256": "d" * 64, "severity": "MUST"}],
        }

        def checker_with_sel(_wt, inv, _ctx):
            rub = orchestrator.build_rubric_report(
                decision="ACCEPT",
                hard_gate_passed=True,
                evidence_refs=[{"receipt_path": "checks_summary.json", "receipt_sha256": inv["checks_summary.json"]}],
            )
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": sel_hash,
                "rule_results": [
                    {
                        "rule_id": "DOC-001",
                        "rule_sha256": "d" * 64,
                        "status": "PASS",
                        "evidence": [{"receipt_path": "checks_summary.json", "receipt_sha256": inv["checks_summary.json"]}],
                        "reason": "Checked against receipts",
                    }
                ],
                "rubric": rub,
            }

        orig_eval_qg = orchestrator.evaluate_quality_gates

        def fake_eval_qg(repo_p, base_p, manifest_rel, ev_root):
            doc = orig_eval_qg(repo_p, base_p, manifest_rel, ev_root)
            return {**doc, "standards": {"status": "NOT_VERIFIED", "selection_sha256": sel_hash, "selected_ids": ["DOC-001"]}}

        with patch.object(orchestrator, "select_rules", return_value=stub_sel), \
             patch.object(orchestrator, "evaluate_quality_gates", side_effect=fake_eval_qg):
            res = orchestrator.run_maker_checker_loop(
                repo=wt,
                issue=441,
                journal_path=self.journal_path,
                evidence_dir=ev_sel,
                base_sha=wt_base,
                issue_data={"state": "OPEN", "title": "Selected IDs PAG", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
                maker_fn=lambda r, _c: ((r / "README.md").write_text("pag with sel\n", encoding="utf-8"), {"changed_path": "README.md"})[1],
                checker_fn=checker_with_sel,
                approval={"status": "SUPERVISED_ISSUE_OPEN", "isolated_pilot_attested": True},
                policy=orchestrator.build_run_policy(consecutive_passes_required=1, max_rounds=2, max_wall_seconds=120),
                check_profile="quick",
                maker_provider="codex",
                checker_provider="agy",
                capability_overrides={"codex_path": "/bin/true", "agy_path": "/bin/true"},
            )
            self.assertEqual(res["state"], "READY_FOR_HUMAN_REVIEW", res)
            self.assertIn("post_audit_gates", res["rounds"][0]["evidence_refs"])
            self.assertTrue((ev_sel / "round-01" / "post-audit-gates.json").is_file())
            rec = orchestrator.reconcile_run(
                repo=wt,
                journal_path=self.journal_path,
                run_id=res["run_id"],
                evidence_dir=ev_sel,
                issue_data={"state": "OPEN", "title": "Selected IDs PAG", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            )
            self.assertEqual(rec["decision"], "TERMINAL_PRESERVED")
            self.assertEqual(rec["acceptance_mode"], "REAL_ACCEPTANCE_CANDIDATE")

    def test_p08c_repeated_reconcile_persists_resume_phase_and_is_idempotent(self):
        wt = self._make_linked_worktree(issue=4410, suffix="idemp-rec")
        self._seed_harness_files(wt)
        wt_base = _git(wt, "rev-parse", "HEAD")
        ev_dir = self.base_dir / "ev_idemp_rec"

        # 1. Interrupted in VERIFYING -> reconcile 1 sets & persists VERIFY_AND_CHECK;
        #    reconcile 2 & 3 MUST keep VERIFY_AND_CHECK (never flip to MAKER!)
        rid = self._spawn_and_kill_at_boundary(
            repo_path=wt, journal_path=self.journal_path, evidence_dir=ev_dir, boundary="verifying"
        )
        rec1 = orchestrator.reconcile_run(
            repo=wt,
            journal_path=self.journal_path,
            run_id=rid,
            evidence_dir=ev_dir,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        self.assertEqual(rec1["status"], "REPAIR_REQUIRED")
        self.assertEqual(rec1["resume_phase"], "VERIFY_AND_CHECK")
        self.assertEqual(rec1["decision"], "RECONCILED_RESUME_SAFE")
        self.assertEqual(rec1["recovery_reason"], "interrupted_during_verification")
        with Journal(self.journal_path) as j:
            persisted = j.get_control_run(rid)
        self.assertEqual(persisted["resume_phase"], "VERIFY_AND_CHECK")

        rec2 = orchestrator.reconcile_run(
            repo=wt,
            journal_path=self.journal_path,
            run_id=rid,
            evidence_dir=ev_dir,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        rec3 = orchestrator.reconcile_run(
            repo=wt,
            journal_path=self.journal_path,
            run_id=rid,
            evidence_dir=ev_dir,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        for rec_n in (rec2, rec3):
            self.assertEqual(rec_n["status"], "REPAIR_REQUIRED")
            self.assertEqual(rec_n["resume_phase"], "VERIFY_AND_CHECK")
            self.assertEqual(rec_n["decision"], "RECONCILED_RESUME_SAFE")
            self.assertEqual(rec_n["recovery_reason"], "interrupted_during_verification")
            self.assertTrue(rec_n["can_resume"])
            self.assertGreater(rec_n["remaining_wall_seconds"], 0.0)

        # CLI status/resume/signals also surface persisted resume_phase and remaining_wall_seconds
        with patch.object(sys, "argv", ["cli.py", "resume", "--issue", "4410", "--run-id", rid, "--repo", str(wt), "--state", str(self.journal_path), "--offline"]), \
             contextlib.redirect_stdout(io.StringIO()) as out_cli_res:
            self.assertEqual(p1_cli.main(), 0)
        cli_res_doc = json.loads(out_cli_res.getvalue())
        self.assertEqual(cli_res_doc["resume_phase"], "VERIFY_AND_CHECK")
        self.assertEqual(cli_res_doc["reconciliation"]["resume_phase"], "VERIFY_AND_CHECK")
        self.assertEqual(cli_res_doc["control_run"]["resume_phase"], "VERIFY_AND_CHECK")

        # Subsequent loop resume AFTER repeated reconciles still skips Maker (0 calls)!
        maker_calls = {"n": 0}
        resumed = orchestrator.run_maker_checker_loop(
            repo=wt,
            issue=4410,
            journal_path=self.journal_path,
            evidence_dir=ev_dir,
            base_sha=wt_base,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=lambda _r, _c: (maker_calls.__setitem__("n", maker_calls["n"] + 1), {"changed_path": "README.md"})[1],
            check_profile="quick",
            allow_fixture_mode=True,
            require_isolated_worktree=False,
            require_protected_approval=False,
            resume_run_id=rid,
        )
        self.assertEqual(resumed["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(maker_calls["n"], 0)

        # 2. Candidate drift while paused in VERIFY_AND_CHECK still blocks conservatively on repeated reconcile
        wt_drift = self._make_linked_worktree(issue=4410, suffix="idemp-drift")
        self._seed_harness_files(wt_drift)
        j_drift = self.base_dir / "host" / "idemp_drift.sqlite"
        ev_drift = self.base_dir / "ev_idemp_drift"
        rid_d = self._spawn_and_kill_at_boundary(
            repo_path=wt_drift, journal_path=j_drift, evidence_dir=ev_drift, boundary="checking"
        )
        rec_d1 = orchestrator.reconcile_run(
            repo=wt_drift, journal_path=j_drift, run_id=rid_d, evidence_dir=ev_drift,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        self.assertEqual(rec_d1["resume_phase"], "VERIFY_AND_CHECK")
        (wt_drift / "README.md").write_text("tampered while paused!\n", encoding="utf-8")
        rec_d2 = orchestrator.reconcile_run(
            repo=wt_drift, journal_path=j_drift, run_id=rid_d, evidence_dir=ev_drift,
            issue_data={"state": "OPEN", "title": "Child Crash Fixture", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
        )
        self.assertEqual(rec_d2["status"], "BLOCKED")
        self.assertEqual(rec_d2["recovery_reason"], "candidate_drift_during_verify_or_check")
        self.assertFalse(rec_d2["can_resume"])

    def test_p08c_executable_resume_run_py_and_p1_cli_preserve_journal_policy_and_budget(self):
        wt = self._make_linked_worktree(issue=437, suffix="exec-res")
        self._seed_harness_files(wt)
        wt_base = _git(wt, "rev-parse", "HEAD")
        ev_exec = self.base_dir / "ev_exec_res"
        frozen_policy = orchestrator.build_run_policy(
            consecutive_passes_required=1,
            max_rounds=2,
            max_wall_seconds=100,
            no_progress_threshold=2,
        )
        adm = orchestrator.admit_run(
            repo=wt,
            issue=437,
            journal_path=self.journal_path,
            base_sha=wt_base,
            issue_data=self.issue_data,
            approval={"status": "SUPERVISED_ISSUE_OPEN", "isolated_pilot_attested": True},
            policy=frozen_policy,
            check_profile="quick",
            maker_provider="codex",
            checker_provider="agy",
            capability_overrides={"codex_path": "/bin/true", "agy_path": "/bin/true"},
            evidence_dir=ev_exec,
        )
        rid = adm["run"]["run_id"]
        (ev_exec / "frozen-check-plan.json").write_text(json.dumps(adm["check_plan"], indent=2, sort_keys=True), encoding="utf-8")

        # Simulate crash during CHECKING after Maker edited README.md and consumed 37.5s wall budget
        d_m = orchestrator.dispatch_role(repo=wt, journal_path=self.journal_path, run_id=rid, role="maker", in_flight_round=1)
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=rid, expected="DISPATCHED", next_state="MAKER_RUNNING",
            actor_role="host", action="maker_started", dispatch_token=d_m["dispatch_token"],
        )
        (wt / "README.md").write_text("edited before crash\n", encoding="utf-8")
        snap = feature_state.compute_candidate_snapshot(wt, base_sha=wt_base)
        with Journal(self.journal_path) as j:
            j.record_control_progress(
                rid, expected_state="MAKER_RUNNING", actor_role="host", op="maker_completed",
                expected_dispatch_token=d_m["dispatch_token"], wall_elapsed_delta_s=20.0,
                in_flight_round=1, candidate_sha256=snap["candidate_sha256"], last_diff_sha256=snap["diff_sha256"],
            )
            j.transition_control_run(
                rid, expected="MAKER_RUNNING", next_state="VERIFYING", actor_role="host",
                action="host_verifying", expected_dispatch_token=d_m["dispatch_token"],
            )
            j.transition_control_run(
                rid, expected="VERIFYING", next_state="REPAIR_REQUIRED", actor_role="host",
                action="host_checks_passed_prepare_checker", expected_dispatch_token=d_m["dispatch_token"],
                clear_dispatch=True,
            )
        d_c = orchestrator.dispatch_role(
            repo=wt, journal_path=self.journal_path, run_id=rid, role="checker", in_flight_round=1,
            lease_owner={"pid": 99999996, "start_ticks": "1", "host": os.uname().nodename},
        )
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=rid, expected="DISPATCHED", next_state="CHECKING",
            actor_role="host", action="checker_started", dispatch_token=d_c["dispatch_token"],
        )
        with Journal(self.journal_path) as j:
            j.record_control_progress(
                rid, expected_state="CHECKING", actor_role="host", op="checker_tick",
                expected_dispatch_token=d_c["dispatch_token"], wall_elapsed_delta_s=17.5, in_flight_round=1,
            )
        r1_partial = ev_exec / "round-01"
        r1_partial.mkdir(parents=True, exist_ok=True)
        (r1_partial / "audit_report.json").write_text("{partial", encoding="utf-8")

        # Execute executable resume via run.py with conflicting CLI policy flags (must be ignored in favor of frozen policy!)
        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        codex_calls = {"n": 0}
        audit_timeouts: list[int] = []

        def _fail_if_maker_called(*_args, **_kwargs):
            codex_calls["n"] += 1
            raise AssertionError("Maker codex.invoke must NOT execute on VERIFY_AND_CHECK resume!")

        def _fake_audit(prompt, snapshot, schema, timeout, required_paths, **kwargs):
            audit_timeouts.append(timeout)
            ev_refs = [
                {"receipt_path": k, "receipt_sha256": v}
                for k, v in sorted((kwargs.get("evidence_inventory") or {}).items())
            ]
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": kwargs["selection_sha256"],
                "rule_results": [],
                "rubric": orchestrator.build_rubric_report(
                    decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs
                ),
            }

        res_args = argparse.Namespace(
            issue=437,
            execute=True,
            accept_isolated_pilot=True,
            expected_idf_version=None,
            toolchain_mode="container_only",
            allow_native_fallback=False,
            timeout=300,
            max_repairs=9,
            check_profile="software",
            max_wall_seconds=9999,
            consecutive_passes=5,
            no_progress_threshold=9,
            require_token_budget=False,
            require_cost_budget=False,
            approved_by="",
            journal=self.journal_path,
            feature_file=None,
            unit_id=None,
            trusted_definitions=None,
            resume_run_id=rid,
            evidence_dir=None,
        )
        stream = io.StringIO()
        with patch.object(harness_run, "__file__", str(wt / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             patch.object(harness_run.codex, "invoke", side_effect=_fail_if_maker_called), \
             patch.object(harness_run.antigravity, "invoke", side_effect=_fake_audit), \
             contextlib.redirect_stdout(stream):
            rc = harness_run.run(res_args)
        self.assertEqual(rc, 0, stream.getvalue())
        out_manifest = pathlib.Path(stream.getvalue().strip().split(": ", 1)[1])
        self.assertEqual(out_manifest.parent.resolve(), ev_exec.resolve())
        doc_m = json.loads(out_manifest.read_text(encoding="utf-8"))
        self.assertEqual(doc_m["run_id"], rid)
        self.assertEqual(doc_m["state"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(doc_m["policy_sha256"], frozen_policy["policy_sha256"])
        self.assertEqual(codex_calls["n"], 0)
        # Auditor timeout MUST be bounded by remaining budget (<= 100 - 37.5 = 62.5s), never fresh 300s/9999s!
        self.assertTrue(audit_timeouts and audit_timeouts[0] <= 63, audit_timeouts)
        self.assertTrue((ev_exec / "interrupted").is_dir())
        with Journal(self.journal_path) as j:
            final_ctrl = j.get_control_run(rid)
            self.assertEqual(final_ctrl["state"], "READY_FOR_HUMAN_REVIEW")
            self.assertEqual(final_ctrl["policy"]["max_wall_seconds"], 100)
            self.assertEqual(final_ctrl["policy"]["max_rounds"], 2)
            self.assertGreaterEqual(final_ctrl["budget_consumed"]["wall_seconds"], 37.5)

        # Verify p1/cli.py resume --execute forwards exact --resume-run-id and --journal arguments
        with patch.object(p1_cli.subprocess, "run", return_value=argparse.Namespace(returncode=0)) as mock_sub, \
             patch.object(
                 sys,
                 "argv",
                 [
                     "cli.py",
                     "resume",
                     "--issue",
                     "437",
                     "--run-id",
                     rid,
                     "--repo",
                     str(wt),
                     "--state",
                     str(self.journal_path),
                     "--execute",
                     "--accept-isolated-pilot",
                 ],
             ):
            self.assertEqual(p1_cli.main(), 0)
        fwd_cmd = mock_sub.call_args[0][0]
        self.assertIn("--execute", fwd_cmd)
        self.assertIn("--accept-isolated-pilot", fwd_cmd)
        self.assertIn("--resume-run-id", fwd_cmd)
        self.assertIn(rid, fwd_cmd)
        self.assertIn(str(self.journal_path), fwd_cmd)



if __name__ == "__main__":
    unittest.main()
