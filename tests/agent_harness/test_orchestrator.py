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
        run_id = self._admit(policy=pol)["run"]["run_id"]
        # Round 1: Candidate A passes -> consecutive_passes = 1
        d1 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=run_id, expected="DISPATCHED",
            next_state="CHECKING", actor_role="host", action="checker_started", dispatch_token=d1["dispatch_token"],
        )
        r1 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d1["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256="1" * 64, diff_sha256="2" * 64,
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
        r2 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d2["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256="9" * 64, diff_sha256="8" * 64, confirming_pass=True,
        )
        self.assertEqual(r2["consecutive_passes"], 0)
        self.assertEqual(r2["state"], "REPAIR_REQUIRED")

        # Even non-confirming Maker edit to candidate C resets prior streak (starts at 1, not 2)
        d3 = orchestrator.dispatch_role(repo=self.repo, journal_path=self.journal_path, run_id=run_id, role="checker")
        orchestrator.transition_state(
            journal_path=self.journal_path, run_id=run_id, expected="DISPATCHED",
            next_state="CHECKING", actor_role="host", action="checker_started", dispatch_token=d3["dispatch_token"],
        )
        r3 = orchestrator.record_round_result(
            journal_path=self.journal_path, run_id=run_id, dispatch_token=d3["dispatch_token"],
            outcome="PASS", host_checks_passed=True, checker_passed=True,
            candidate_sha256="7" * 64, diff_sha256="6" * 64, confirming_pass=False,
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
        with Journal(pilot_db) as journal:
            for sc in summary["scenarios"]:
                rounds = journal.list_control_rounds(sc["run_id"])
                self.assertEqual(len(rounds), sc["rounds"])


if __name__ == "__main__":
    unittest.main()
