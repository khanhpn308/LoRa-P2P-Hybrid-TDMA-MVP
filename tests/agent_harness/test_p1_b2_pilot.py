"""End-to-end fake Worker/Host/Auditor tests over real local Git worktrees."""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1.state import Journal
from p1.worktrees import make_plan, prepare
from p1.pilot import (CheckOutcome, PilotBlocked, PilotLedger,
                      run_simulated_cycle)


def git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                   text=True, check=True, timeout=20)


class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = pathlib.Path(self.tmp.name)
        self.source = self.dir / "source"
        self.source.mkdir()
        git(self.source, "init", "-q")
        git(self.source, "config", "user.email", "fixture@example.invalid")
        git(self.source, "config", "user.name", "Pilot Fixture")
        (self.source / "firmware").mkdir()
        (self.source / "firmware" / "esp-idf-version.txt").write_text("v6.1\n")
        git(self.source, "add", ".")
        git(self.source, "commit", "-qm", "fixture")
        plan = make_plan(self.source, 34, "b" * 32)
        prepare(plan)
        self.worktree = plan.target
        self.run_id = "b" * 32
        self.db = self.dir / "journal" / "state.sqlite"
        self.host = Journal(self.db)
        self.addCleanup(self.host.close)
        self.host.plan(run_id=self.run_id, issue=34, source_sha=plan.base_sha,
                       issue_sha="d" * 64, branch=plan.branch, worktree=plan.target,
                       scope=("tests/agent_harness/",))
        self.host.transition(self.run_id, expected="PLANNED", next_state="PREPARING")
        self.host.transition(self.run_id, expected="PREPARING", next_state="PREPARED")

    def worker(self, iteration: int, feedback: str) -> None:
        path = self.worktree / "tests" / "agent_harness" / "generated.py"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"def sample():\n    return {iteration}\n")

    @staticmethod
    def good_check(candidate):
        return CheckOutcome("PASS", 0, ("simulated_gateway_build", "simulated_node_build"))

    @staticmethod
    def pass_audit(candidate, checks):
        return {"status": "PASS", "findings": [], "limitations": [],
                "reviewed_scope": candidate["paths"]}

    def cycle(self, **overrides):
        callbacks = {"worker": self.worker, "checker": self.good_check,
                     "auditor": self.pass_audit, "max_repairs": 2}
        callbacks.update(overrides)
        return run_simulated_cycle(self.host, self.run_id, **callbacks)

    def test_one_round_all_gates_simulated(self):
        r = self.cycle()
        self.assertEqual(r["status"], "SIMULATED_AWAIT_HUMAN")
        self.assertEqual(r["attempts"], 1)
        self.assertEqual(r["build"], "NOT_VERIFIED")
        self.assertEqual(r["audit"], "NOT_VERIFIED")
        history = [x["status"] for x in PilotLedger(self.host).events(self.run_id)]
        self.assertEqual(history, ["READY", "WORKER_RUNNING", "VERIFYING",
                                   "AUDITING", "AWAIT_HUMAN"])

    def test_bounded_check_fail_then_repair_success(self):
        counter = []

        def check(candidate):
            counter.append(1)
            if len(counter) == 1:
                return CheckOutcome("FAIL", 1, ("simulated_failed_build",))
            return self.good_check(candidate)

        result = self.cycle(checker=check)
        self.assertEqual(result["status"], "SIMULATED_AWAIT_HUMAN")
        self.assertEqual(result["attempts"], 2)
        events = [e["status"] for e in PilotLedger(self.host).events(self.run_id)]
        self.assertEqual(events.count("REPAIR_REQUIRED"), 1)

    def test_auditor_fail_then_repair_success(self):
        counter = []

        def audit(candidate, checks):
            counter.append(1)
            if len(counter) == 1:
                return {
                    "status": "FAIL", "limitations": [],
                    "reviewed_scope": candidate["paths"],
                    "findings": [{"severity": "HIGH", "file": candidate["paths"][0],
                                  "line": 1, "rule": "RAD-01",
                                  "explanation": "simulated bad data", "fix": "update stub"}],
                }
            return self.pass_audit(candidate, checks)

        result = self.cycle(auditor=audit)
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(PilotLedger(self.host).get(self.run_id)["status"], "AWAIT_HUMAN")

    def test_stalled_worker_is_blocked_no_infinite_retry(self):
        def same_worker(attempt, feedback):
            target = self.worktree / "tests" / "agent_harness" / "x.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("same content forever\n")

        def fail(candidate):
            return CheckOutcome("FAIL", 1, ("mock",))

        result = self.cycle(worker=same_worker, checker=fail)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("did not alter", result["reason"])

    def test_budget_exhaustion_blocks(self):
        result = self.cycle(max_repairs=0,
                            checker=lambda x: CheckOutcome("FAIL", 1, ("mock",)))
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 1)

    def test_worker_crash_requires_manual_recovery(self):
        def crash(a, b):
            raise TimeoutError("No credentials stored in ledger")

        result = self.cycle(worker=crash)
        self.assertEqual(result["status"], "RECOVERY_REQUIRED")
        self.assertTrue(all("No credentials" not in str(x)
                            for x in PilotLedger(self.host).events(self.run_id)))

    def test_out_of_scope_change_blocks(self):
        def unsafe_worker(a, b):
            f = self.worktree / "contracts" / "radio-mac" / "hijack.c"
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("oops")

        result = self.cycle(worker=unsafe_worker)
        self.assertEqual(result["status"], "BLOCKED")

    def test_audit_missing_changed_path_blocks(self):
        result = self.cycle(auditor=lambda c, x: {
            "status": "PASS", "findings": [], "limitations": [],
            "reviewed_scope": [],
        })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("Invalid audit", result["reason"])

    def test_check_cannot_forge_success(self):
        result = self.cycle(checker=lambda x: CheckOutcome("PASS", 99, ("mock",)))
        self.assertEqual(result["status"], "BLOCKED")

    def test_auditor_mutation_detected_after_review(self):
        def audit(c, checks):
            (self.worktree / c["paths"][0]).write_text("unexpected change\n")
            return self.pass_audit(c, checks)

        result = self.cycle(auditor=audit)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("changed during", result["reason"])

    def test_duplicate_pilot_run_id_refused(self):
        self.cycle()
        with self.assertRaises(PilotBlocked):
            self.cycle()

    def test_unknown_prepared_job_cannot_start(self):
        with self.assertRaises(Exception):
            run_simulated_cycle(self.host, "unknown", worker=self.worker,
                                checker=self.good_check, auditor=self.pass_audit)

    def test_interruption_marking_and_no_resume(self):
        ledger = PilotLedger(self.host)
        ledger.begin(self.run_id)
        ledger.transition(self.run_id, "READY", "WORKER_RUNNING", attempt=1)
        self.assertTrue(ledger.mark_interrupted(self.run_id))
        self.assertEqual(ledger.get(self.run_id)["status"], "RECOVERY_REQUIRED")
        self.assertFalse(ledger.mark_interrupted(self.run_id))
        with self.assertRaises(PilotBlocked):
            ledger.transition(self.run_id, "RECOVERY_REQUIRED", "AWAIT_HUMAN",
                              attempt=1)

    def test_malformed_outcome_audit_stops_without_retry(self):
        result = self.cycle(auditor=lambda c, checks: {
            "status": "PASS", "findings": ["string is not an audit finding"],
            "limitations": [], "reviewed_scope": c["paths"],
        })
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 1)


    def test_audit_extra_reviewed_path_blocks_without_repair(self):
        def audit(candidate, checks):
            return {"status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": list(candidate["paths"]) + ["unreviewed.py"]}
        result = self.cycle(auditor=audit)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 1)
        self.assertIn("Invalid audit", result["reason"])

    def test_audit_duplicate_path_blocks_without_repair(self):
        def audit(candidate, checks):
            paths = list(candidate["paths"])
            return {"status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": paths + paths}
        result = self.cycle(auditor=audit)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 1)

    def test_audit_unknown_root_key_blocks_without_repair(self):
        def audit(candidate, checks):
            return {"status": "PASS", "findings": [], "limitations": [],
                    "reviewed_scope": candidate["paths"], "ignored": True}
        result = self.cycle(auditor=audit)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["attempts"], 1)




class PilotDemoSmokeTests(unittest.TestCase):
    def test_offline_pilot_demo_marks_everything_simulated(self):
        """Exercise the real local demo entrypoint, never a model/provider."""
        from p1.pilot_demo import demo

        result = demo()
        self.assertEqual(result["status"], "SIMULATED_AWAIT_HUMAN")
        self.assertEqual(result["evidence_level"], "SIMULATED")
        self.assertEqual(result["attempts"], 2)
        self.assertIn("REPAIR_REQUIRED", result["history"])
        for dimension in ("build", "audit", "hil", "rf"):
            self.assertEqual(result[dimension], "NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
