"""Unit and integration tests for P08-A Role & Control-Plane Integration."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
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
        run3 = self._admit(policy=pol3)["run"]["run_id"]
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
        r4 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run3,
            dispatch_token=d4["dispatch_token"],
            outcome="PASS",
            host_checks_passed=True,
            checker_passed=True,
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
        r5 = orchestrator.record_round_result(
            journal_path=self.journal_path,
            run_id=run3,
            dispatch_token=d5["dispatch_token"],
            outcome="PASS",
            host_checks_passed=True,
            checker_passed=True,
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
            "checks_summary.json",
            "audit_report.json",
            "control_plane_summary.json",
        ):
            self.assertTrue((self.evidence_dir / name).is_file(), name)

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

        # Admit via p1/cli.py with supervised attestation and resume via feature_state
        argv_ok = [
            "cli.py", "admit", "--issue", "437", "--repo", str(self.repo),
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
            issue=437, repo=self.repo, state_db=self.journal_path, offline=True
        )
        self.assertIsNotNone(resumed["control_run"])
        self.assertEqual(resumed["control_run"]["run_id"], run_id)
        self.assertEqual(resumed["control_run"]["state"], "ADMITTED")

        # Cancel via p1/cli.py
        argv_can = [
            "cli.py", "cancel", "--run-id", run_id,
            "--source", str(self.repo), "--state", str(self.journal_path),
        ]
        with patch.object(sys, "argv", argv_can), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(p1_cli.main(), 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "CANCELLED")

    def test_run_py_with_journal_persists_control_run_and_rejects_unavailable_token_budget(self):
        (self.repo / ".agent-harness").mkdir(exist_ok=True)
        (self.repo / ".agent-harness" / "worker.md").write_text("Worker rules\n", encoding="utf-8")
        (self.repo / ".agent-harness" / "auditor.md").write_text("Auditor rules\n", encoding="utf-8")
        (self.repo / "scripts" / "agent_harness" / "adapters").mkdir(parents=True, exist_ok=True)
        (self.repo / "scripts" / "agent_harness" / "adapters" / "audit.schema.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "scripts" / "verify_structure.py").write_text("print('OK')\n", encoding="utf-8")
        _git(self.repo, "add", ".")
        _git(self.repo, "commit", "-qm", "harness fixture files")

        def _fake_tool(cmd, cwd, timeout):
            if cmd[0] == "gh":
                return {"tool": "gh", "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 10}, json.dumps(self.issue_data)
            return {"tool": cmd[0], "command": cmd, "exit_code": 0, "output_sha256": "0" * 64, "output_bytes": 2}, "OK"

        def _fake_worker(prompt, repo, timeout, **kwargs):
            (self.repo / "README.md").write_text("updated via run.py\n", encoding="utf-8")
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
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": kwargs["selection_sha256"],
                "rule_results": [],
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
        with patch.object(harness_run, "__file__", str(self.repo / "scripts/agent_harness/run.py")), \
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

        # Requiring unmeasurable token budget fails closed
        _git(self.repo, "checkout", "--", "README.md")
        args_tok = argparse.Namespace(**{**vars(args), "require_token_budget": True})
        stream2 = io.StringIO()
        with patch.object(harness_run, "__file__", str(self.repo / "scripts/agent_harness/run.py")), \
             patch.object(harness_run.shutil, "which", return_value="fixture-bin"), \
             patch.object(harness_run, "tool", side_effect=_fake_tool), \
             contextlib.redirect_stdout(stream2):
            rc2 = harness_run.run(args_tok)
        manifest_path2 = pathlib.Path(stream2.getvalue().strip().split(": ", 1)[1])
        self.addCleanup(shutil.rmtree, manifest_path2.parent)
        self.assertEqual(rc2, 2)
        self.assertEqual(json.loads(manifest_path2.read_text(encoding="utf-8"))["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
