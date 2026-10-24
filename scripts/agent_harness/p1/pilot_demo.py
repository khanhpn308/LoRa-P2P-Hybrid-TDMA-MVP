"""Local harmless pilot with fake Worker, fake Host checks and fake AGY Auditor.

Demonstrates one failed verification, bounded repair, audit and SQLite states.
NEVER connects to model providers or flashes any device.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

if __package__ in ("", None):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from p1.state import Journal
from p1.worktrees import make_plan, prepare
from p1.pilot import run_simulated_cycle, CheckOutcome, PilotLedger


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args],
                   check=True, capture_output=True, timeout=20)


def demo() -> dict:
    with tempfile.TemporaryDirectory(prefix="lora-harness-sim-") as tmp:
        root = pathlib.Path(tmp)
        repo = root / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "fixture@example.invalid")
        git(repo, "config", "user.name", "Harness Demo")
        (repo / "firmware").mkdir()
        (repo / "firmware" / "esp-idf-version.txt").write_text("v6.1\n")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "fixture")
        run_id = "c" * 32
        plan = make_plan(repo, 34, run_id)
        prepare(plan)
        journal_path = root / "host" / "runs.sqlite"
        with Journal(journal_path) as host:
            host.plan(run_id=run_id, issue=34, source_sha=plan.base_sha,
                      issue_sha="d" * 64, branch=plan.branch, worktree=plan.target,
                      scope=("tests/agent_harness/",))
            host.transition(run_id, expected="PLANNED", next_state="PREPARING")
            host.transition(run_id, expected="PREPARING", next_state="PREPARED")

            def worker(attempt, feedback):
                f = plan.target / "tests" / "agent_harness" / "example.py"
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text("def value():\n    return " + str(attempt) + "\n")

            hits = []

            def check(candidate):
                hits.append(True)
                return (CheckOutcome("FAIL", 1, ("SIMULATED_COMPILER_FAILURE",))
                        if len(hits) == 1
                        else CheckOutcome("PASS", 0, ("SIMULATED_BUILD_PASS",)))

            def audit(candidate, checks):
                return {"status": "PASS", "findings": [], "limitations": [],
                        "reviewed_scope": candidate["paths"]}

            result = run_simulated_cycle(
                host, run_id, worker=worker, checker=check, auditor=audit)
            result["history"] = [e["status"] for e in PilotLedger(host).events(run_id)]
            return result


if __name__ == "__main__":
    print(json.dumps(demo(), indent=2))
