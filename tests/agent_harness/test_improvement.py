"""Tests for P08-D Controlled Harness Meta-Improvement Experiment Loop (OD-10)."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))

import improvement as imp
from observability import query_signals, record_process_signal
from orchestrator import RoleAccessDenied
from p1.state import Journal, StateConflict


def _init_git_repo(repo_dir: pathlib.Path) -> str:
    repo_dir.mkdir(parents=True, exist_ok=True)
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.name", "P08D Test"],
        ["git", "config", "user.email", "p08d-test@example.invalid"],
    ):
        subprocess.run(cmd, cwd=repo_dir, check=True, capture_output=True, timeout=15)
    (repo_dir / "AGENTS.md").write_text("# Test AGENTS\n- Follow OD-10.\n", encoding="utf-8")
    (repo_dir / "docs").mkdir(exist_ok=True)
    (repo_dir / "docs" / "routing_note.md").write_text("# Routing\n- Noise line\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True, timeout=15)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=repo_dir, check=True, capture_output=True, timeout=15)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_dir, check=True, capture_output=True, text=True, timeout=15
    ).stdout.strip()


class ImprovementProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / "repo"
        self.base_sha = _init_git_repo(self.repo)
        self.journal = self.root / "state" / "journal.sqlite"
        self.ev_dir = self.root / "evidence"
        self.ws_root = self.root / "workspaces"

    def test_od10_protocol_validation_and_maker_isolation(self):
        with self.assertRaises(imp.ProtocolError):
            imp.validate_experiment_scope(["AGENTS.md"])
        with self.assertRaises(imp.ProtocolError):
            imp.validate_experiment_scope(["scripts/agent_harness/quality_gates.py"])
        with self.assertRaises(imp.ProtocolError):
            imp.validate_experiment_scope(["docs/*.md"])
        with self.assertRaises(imp.ProtocolError):
            imp.validate_experiment_scope(["../escape.md"])
        with self.assertRaises(imp.ProtocolError):
            imp.build_experiment_plan(
                experiment_id="EXP-BAD-01",
                hypothesis="",
                one_change_summary="change",
                attributed_subsystem="instructions",
                attributed_failure={},
                target_metric="instruction_snr",
                direction="higher_is_better",
                min_delta=0.1,
                baseline_revision=self.base_sha,
                allowed_paths=("docs/routing_note.md",),
            )

        plan = imp.build_experiment_plan(
            experiment_id="EXP-PROTO-01",
            hypothesis="One change raises SNR",
            one_change_summary="Refine docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={"owning_domain": "harness"},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.15,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            holdout_spec={"cases": [{"id": "HO-1", "secret_answer": "do-not-leak-to-maker"}]},
        )
        self.assertNotIn("holdout_spec", plan["maker_view"])
        self.assertNotIn("negative_controls_spec", plan["maker_view"])
        self.assertNotIn("oracle_spec", plan["maker_view"])
        self.assertEqual(len(plan["plan_sha256"]), 64)
        self.assertEqual(len(plan["holdout_sha256"]), 64)

    def test_controlled_demo_keep_reject_gaming_and_cli_verify(self):
        summary = imp.run_controlled_experiment_demo(
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
        )
        self.assertEqual(summary["mode"], "CONTROLLED_FIXTURE")
        self.assertFalse(summary["real_productivity_gain_claimed"])
        self.assertEqual(summary["live_provider_evaluation"], "NOT_VERIFIED")
        self.assertEqual(summary["human_rubric_calibration"], "NOT_VERIFIED")

        by_id = {row["experiment_id"]: row for row in summary["experiments"]}
        self.assertEqual(by_id["EXP-DEMO-KEEP-001"]["decision"], "KEEP")
        self.assertEqual(by_id["EXP-DEMO-KEEP-001"]["promotion_status"], "FIXTURE_ONLY_NOT_PROMOTABLE")
        self.assertTrue(by_id["EXP-DEMO-KEEP-001"]["workspaces_cleaned"])

        self.assertEqual(by_id["EXP-DEMO-REJECT-002"]["decision"], "REJECT")
        self.assertEqual(by_id["EXP-DEMO-REJECT-002"]["reason_code"], "INSUFFICIENT_IMPROVEMENT_OR_REGRESSION")
        self.assertTrue(by_id["EXP-DEMO-REJECT-002"]["workspaces_cleaned"])

        self.assertEqual(by_id["EXP-DEMO-GAMING-003"]["decision"], "REJECT")
        self.assertEqual(by_id["EXP-DEMO-GAMING-003"]["reason_code"], "TAMPERING_OR_METRIC_GAMING")
        self.assertTrue(by_id["EXP-DEMO-GAMING-003"]["workspaces_cleaned"])

        for exp_id in ("EXP-DEMO-KEEP-001", "EXP-DEMO-REJECT-002", "EXP-DEMO-GAMING-003"):
            ver = imp.verify_experiment_evidence(journal_path=self.journal, experiment_id=exp_id)
            self.assertEqual(ver["status"], "PASS")

        # Verify CLI status & verify commands work cleanly.
        cli_path = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness" / "improvement.py"
        proc = subprocess.run(
            [sys.executable, str(cli_path), "verify", "--journal", str(self.journal), "--experiment-id", "EXP-DEMO-KEEP-001"],
            text=True, capture_output=True, check=False, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "PASS")

    def test_safe_discard_refuses_unowned_and_preserves_user_work(self):
        unowned_dir = self.ws_root / "user-work-preserve"
        unowned_dir.mkdir(parents=True)
        (unowned_dir / "notes.txt").write_text("do not delete", encoding="utf-8")

        with self.assertRaises(imp.WorkspaceIsolationError):
            imp.discard_disposable_workspace(
                workspace_info={
                    "experiment_id": "EXP-UNOWNED",
                    "role": "candidate",
                    "workspace_path": str(unowned_dir),
                },
                workspace_root=self.ws_root,
            )
        self.assertTrue((unowned_dir / "notes.txt").is_file())

        # Symlink target must be rejected
        ws_info = imp.create_disposable_workspace(
            source_repo=self.repo,
            workspace_root=self.ws_root,
            experiment_id="EXP-SYM-TEST",
            role="candidate",
            baseline_revision=self.base_sha,
        )
        ws_path = pathlib.Path(ws_info["workspace_path"])
        import shutil
        shutil.rmtree(ws_path)
        ws_path.symlink_to(unowned_dir)
        with self.assertRaises(imp.WorkspaceIsolationError):
            imp.discard_disposable_workspace(workspace_info=ws_info, workspace_root=self.ws_root)
        self.assertTrue((unowned_dir / "notes.txt").is_file())

    def test_tampered_stale_and_replayed_evidence_rejected(self):
        imp.run_controlled_experiment_demo(
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
        )
        keep_ev = self.ev_dir / "EXP-DEMO-KEEP-001"
        rej_ev = self.ev_dir / "EXP-DEMO-REJECT-002"

        # 1. Tampered artifact hash mismatch
        cand_file = keep_ev / "candidate_eval.json"
        orig_cand = cand_file.read_bytes()
        tampered = json.loads(orig_cand.decode("utf-8"))
        tampered["metrics"]["instruction_snr"] = 0.99
        cand_file.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaises(imp.TamperingError):
            imp.verify_experiment_evidence(journal_path=self.journal, experiment_id="EXP-DEMO-KEEP-001")
        cand_file.write_bytes(orig_cand)

        # 2. Replayed artifact from another experiment (even if receipt hash updated in SQLite, anti-replay catches ID)
        rej_cand_bytes = (rej_ev / "candidate_eval.json").read_bytes()
        cand_file.write_bytes(rej_cand_bytes)
        with self.assertRaises(imp.TamperingError):
            imp.verify_experiment_evidence(journal_path=self.journal, experiment_id="EXP-DEMO-KEEP-001")
        cand_file.write_bytes(orig_cand)

        # 3. Stale/forged decision mismatch caught by re-evaluating artifacts
        dec_file = rej_ev / "decision_record.json"
        dec_data = json.loads(dec_file.read_text(encoding="utf-8"))
        dec_data["decision"] = "KEEP"
        forged_bytes = (json.dumps(dec_data, indent=2, sort_keys=True) + "\n").encode("utf-8")
        forged_sha = imp._bytes_sha256(forged_bytes)
        dec_file.write_bytes(forged_bytes)
        with Journal(self.journal) as j:
            row = j.get_experiment("EXP-DEMO-REJECT-002")
            receipts = dict(row["receipts"])
            receipts["decision_record.json"] = forged_sha
            j.db.execute(
                "UPDATE improvement_experiments SET decision='KEEP', receipts_json=?, decision_record_sha256=? WHERE experiment_id=?",
                (json.dumps(receipts, sort_keys=True), forged_sha, "EXP-DEMO-REJECT-002"),
            )
        with self.assertRaises(imp.TamperingError):
            imp.verify_experiment_evidence(journal_path=self.journal, experiment_id="EXP-DEMO-REJECT-002")

    def test_unauthorized_promotion_blocked_and_owner_representative_allowed_pr_only(self):
        imp.run_controlled_experiment_demo(
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
        )
        # Missing owner
        with self.assertRaises(imp.UnauthorizedPromotionError):
            imp.attempt_promotion(journal_path=self.journal, experiment_id="EXP-DEMO-KEEP-001", approved_by="")
        # Fixture cannot be promoted even with owner
        with self.assertRaises(imp.UnauthorizedPromotionError):
            imp.attempt_promotion(journal_path=self.journal, experiment_id="EXP-DEMO-KEEP-001", approved_by="owner:khanhpn308")
        # REJECT cannot be promoted
        with self.assertRaises(imp.UnauthorizedPromotionError):
            imp.attempt_promotion(journal_path=self.journal, experiment_id="EXP-DEMO-REJECT-002", approved_by="owner:khanhpn308")
        # Direct merge to main forbidden
        with self.assertRaises(imp.UnauthorizedPromotionError):
            imp.attempt_promotion(
                journal_path=self.journal,
                experiment_id="EXP-DEMO-KEEP-001",
                approved_by="owner:khanhpn308",
                target_branch="main",
            )

        # Representative task with OWNER_APPROVED threshold -> authorized for Owner PR only (never auto_merged)
        plan = imp.build_experiment_plan(
            experiment_id="EXP-REP-KEEP-01",
            hypothesis="Representative task raises SNR",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={"owning_domain": "harness"},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.2,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="REPRESENTATIVE_TASK",
            threshold_approval={"status": "OWNER_APPROVED", "approved_by": "owner:khanhpn308"},
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        promo = imp.attempt_promotion(
            journal_path=self.journal,
            experiment_id="EXP-REP-KEEP-01",
            approved_by="owner:khanhpn308",
            target_branch="feature/owner-review-pr",
        )
        self.assertEqual(promo["status"], "AUTHORIZED_FOR_OWNER_PR_ONLY")
        self.assertFalse(promo["auto_merged"])

    def test_budget_exhaustion_unavailable_metering_and_negative_controls(self):
        # 1. Required token metering unavailable -> REJECT (METERING_UNAVAILABLE)
        plan_meter = imp.build_experiment_plan(
            experiment_id="EXP-METER-FAIL",
            hypothesis="Test unavailable metering fail-closed",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            budget=imp.ExperimentBudget(max_wall_seconds=30.0, max_rounds=1, max_tokens=1000, require_token_budget=True),
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        res_meter = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_meter,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        self.assertEqual(res_meter["decision_record"]["decision"], "REJECT")
        self.assertEqual(res_meter["decision_record"]["reason_code"], "METERING_UNAVAILABLE")

        # 2. Missing holdout -> REJECT (HOLDOUT_FAILED_OR_MISSING)
        plan_no_ho = imp.build_experiment_plan(
            experiment_id="EXP-NO-HOLDOUT",
            hypothesis="Test missing holdout fails closed",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            holdout_spec={},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        res_no_ho = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_no_ho,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
        )
        self.assertEqual(res_no_ho["decision_record"]["decision"], "REJECT")
        self.assertEqual(res_no_ho["decision_record"]["reason_code"], "HOLDOUT_FAILED_OR_MISSING")

        # 3. Oracle drift mid-run -> ABORTED & workspace safely cleaned
        plan_drift = imp.build_experiment_plan(
            experiment_id="EXP-ORACLE-DRIFT",
            hypothesis="Test oracle tampering mid-run aborts safely",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="security",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )

        def _gaming_maker(ws: pathlib.Path, _mv: dict) -> dict:
            # Mutate the in-memory oracle_spec to simulate oracle drift attempt
            plan_drift["oracle_spec"]["hard_gates"] = []
            (ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8")
            return {}

        res_drift = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_drift,
            maker_fn=_gaming_maker,
            evaluator_fn=lambda _ws, _p, _r: {"mandatory_passed": True, "metrics": {"instruction_snr": 0.9}},
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        self.assertEqual(res_drift["decision_record"]["decision"], "ABORTED")
        self.assertEqual(res_drift["experiment"]["state"], "RECOVERED")
        self.assertTrue(all(not w["exists_after"] for w in res_drift["recovery_receipt"]["workspaces_discarded"]))

        # 4. Representative task without OWNER_APPROVED threshold -> REJECT
        plan_pending = imp.build_experiment_plan(
            experiment_id="EXP-PENDING-OWNER",
            hypothesis="Representative task without owner threshold approval",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="REPRESENTATIVE_TASK",
            threshold_approval={"status": "PENDING_OWNER_APPROVAL"},
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        res_pending = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_pending,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        self.assertEqual(res_pending["decision_record"]["decision"], "REJECT")
        self.assertEqual(res_pending["decision_record"]["reason_code"], "THRESHOLD_PENDING_OWNER_APPROVAL")

    def test_failure_attribution_and_bounded_observability_signal(self):
        fake_secret = "ghp_" + "A" * 24
        record_process_signal(
            journal_path=self.journal,
            category="check",
            owning_domain="harness",
            status="FAIL",
            issue=443,
            check_id="snr-check",
            finding=f"Instruction SNR below target; token={fake_secret}",
        )
        attr = imp.attribute_failure_from_journal(self.journal, issue=443)
        self.assertEqual(attr["owning_domain"], "harness")
        self.assertEqual(attr["check_id"], "snr-check")
        self.assertNotIn(fake_secret, attr["finding"])

        plan = imp.build_experiment_plan(
            experiment_id="EXP-ATTR-01",
            issue=443,
            hypothesis="Address attributed snr-check failure",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem=attr["owning_domain"],
            attributed_failure=attr,
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.2,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        sigs = query_signals(self.journal, issue=443, category="experiment")
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0]["check_id"], "EXP-ATTR-01")
        self.assertEqual(sigs[0]["status"], "PASS")

    def test_p1_cli_experiment_and_wall_timeout_and_failing_negative_control(self):
        p1_cli = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness" / "p1" / "cli.py"
        cli_journal = self.root / "cli_state" / "state.sqlite"
        cli_ev = self.root / "cli_ev"
        cli_ws = self.root / "cli_ws"
        proc = subprocess.run(
            [
                sys.executable,
                str(p1_cli),
                "experiment",
                "--action",
                "demo",
                "--state",
                str(cli_journal),
                "--evidence-dir",
                str(cli_ev),
                "--workspace-root",
                str(cli_ws),
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        demo_out = json.loads(proc.stdout)
        self.assertEqual(len(demo_out["experiments"]), 3)

        proc_ver = subprocess.run(
            [
                sys.executable,
                str(p1_cli),
                "experiment",
                "--action",
                "verify",
                "--state",
                str(cli_journal),
                "--experiment-id",
                "EXP-DEMO-KEEP-001",
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        self.assertEqual(proc_ver.returncode, 0, proc_ver.stdout + proc_ver.stderr)
        self.assertEqual(json.loads(proc_ver.stdout)["status"], "PASS")

        # Wall-time timeout budget exhaustion
        plan_timeout = imp.build_experiment_plan(
            experiment_id="EXP-WALL-TIMEOUT",
            hypothesis="Command timeout exhausts budget and forces REJECT",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="harness",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            budget=imp.ExperimentBudget(max_wall_seconds=0.15, max_rounds=1),
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={
                "commands": [[sys.executable, "-c", "import time; time.sleep(1.0)"]],
                "run_quality_gates": False,
            },
        )
        res_to = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_timeout,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda _ws, _p, _r: {"mandatory_passed": True, "metrics": {"instruction_snr": 0.9}},
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
        )
        self.assertEqual(res_to["decision_record"]["decision"], "REJECT")
        self.assertEqual(res_to["decision_record"]["reason_code"], "BUDGET_EXHAUSTED")

        # Failing negative control -> REJECT
        plan_nc = imp.build_experiment_plan(
            experiment_id="EXP-NC-FAIL",
            hypothesis="Failing negative control blocks KEEP even with metric gain",
            one_change_summary="Update docs/routing_note.md",
            attributed_subsystem="security",
            attributed_failure={},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.1,
            baseline_revision=self.base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            holdout_spec={"cases": [{"id": "HO-1"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        res_nc = imp.run_improvement_experiment(
            source_repo=self.repo,
            journal_path=self.journal,
            evidence_dir=self.ev_dir,
            workspace_root=self.ws_root,
            plan=plan_nc,
            maker_fn=lambda ws, _mv: ((ws / "docs" / "routing_note.md").write_text("# Routing\n- Focused\n", encoding="utf-8") and {}) or {},
            evaluator_fn=lambda ws, _p, _r: {
                "mandatory_passed": True,
                "metrics": {"instruction_snr": 0.9 if "Focused" in (ws / "docs" / "routing_note.md").read_text(encoding="utf-8") else 0.5},
            },
            holdout_fn=lambda _ws, _p: {"cases": [{"case_id": "HO-1", "passed": True}]},
            negative_control_fn=lambda _ws, _p: {"controls": [{"id": "NC-OUT-OF-SCOPE", "rejected_as_expected": False}]},
        )
        self.assertEqual(res_nc["decision_record"]["decision"], "REJECT")
        self.assertEqual(res_nc["decision_record"]["reason_code"], "NEGATIVE_CONTROL_FAILED")


if __name__ == "__main__":
    unittest.main()
