"""P1-B2 deterministic pilot coordinator with injected, EXTERNAL execution callbacks.

No real Codex/AGY/ESP-IDF subprocess invocation or GitHub write is authorized here.
The included demo and tests use mock callbacks; evidence is always SIMULATED.
Production callbacks MUST be deployed in a separately approved isolated runtime.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from typing import Callable, Any

from .state import Journal, StateConflict
from .verify import VerificationBlocked, verify_candidate
from adapters.antigravity import check_report, AuditError

TRANSITIONS = {
    "READY": {"WORKER_RUNNING", "BLOCKED"},
    "WORKER_RUNNING": {"VERIFYING", "BLOCKED", "RECOVERY_REQUIRED"},
    "VERIFYING": {"AUDITING", "REPAIR_REQUIRED", "BLOCKED", "RECOVERY_REQUIRED"},
    "AUDITING": {"REPAIR_REQUIRED", "AWAIT_HUMAN", "BLOCKED", "RECOVERY_REQUIRED"},
    "REPAIR_REQUIRED": {"WORKER_RUNNING", "BLOCKED"},
    "AWAIT_HUMAN": set(),
    "BLOCKED": set(),
    "RECOVERY_REQUIRED": {"BLOCKED"},
}
ACTIVE = frozenset({"WORKER_RUNNING", "VERIFYING", "AUDITING"})


class PilotBlocked(RuntimeError):
    """A deterministic or trust-boundary gate blocked the pilot."""


@dataclass(frozen=True)
class CheckOutcome:
    """Created from trusted Host tool receipts, never from model prose."""
    status: str
    exit_code: int
    checks: tuple[str, ...]

    def valid(self) -> bool:
        return (self.status in ("PASS", "FAIL")
                and isinstance(self.exit_code, int)
                and not isinstance(self.exit_code, bool)
                and bool(self.checks)
                and all(isinstance(c, str) and c for c in self.checks)
                and ((self.status == "PASS" and self.exit_code == 0)
                     or (self.status == "FAIL" and self.exit_code != 0)))


def fingerprint(candidate: dict) -> str:
    # Both diff and untracked file hashes MUST be covered.
    keys = {k: candidate[k] for k in ("base_sha", "branch", "paths",
                                      "files_sha256", "tracked_diff_sha256")}
    return hashlib.sha256(json.dumps(keys, sort_keys=True).encode()).hexdigest()


class PilotLedger:
    """SQLite CAS journal; durable checkpoints but NO automatic crash resume."""
    def __init__(self, host: Journal):
        self.host = host
        self.db = host.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS pilot_runs (
              run_id TEXT PRIMARY KEY,
              status TEXT NOT NULL,
              attempt INTEGER NOT NULL DEFAULT 0,
              fingerprint TEXT,
              updated TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            CREATE TABLE IF NOT EXISTS pilot_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              run_id TEXT NOT NULL,
              previous TEXT,
              status TEXT NOT NULL,
              attempt INTEGER NOT NULL,
              evidence_sha256 TEXT,
              created TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
        """)

    def begin(self, run_id: str) -> None:
        if self.host.get(run_id)["state"] != "PREPARED":
            raise PilotBlocked("Only a PREPARED P1-A job may start a pilot")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("INSERT INTO pilot_runs(run_id,status) VALUES (?,?)",
                            (run_id, "READY"))
            self.db.execute("INSERT INTO pilot_events(run_id,status,attempt) VALUES (?,?,?)",
                            (run_id, "READY", 0))
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self.db.execute("ROLLBACK")
            raise PilotBlocked("Pilot already initialized: cannot repeat a run ID") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def get(self, run_id: str) -> dict:
        row = self.db.execute("SELECT * FROM pilot_runs WHERE run_id=?",
                              (run_id,)).fetchone()
        if row is None:
            raise PilotBlocked("Unknown pilot run")
        return dict(row)

    def events(self, run_id: str) -> list[dict]:
        self.get(run_id)
        return [dict(x) for x in self.db.execute(
            "SELECT status,attempt,evidence_sha256 FROM pilot_events "
            "WHERE run_id=? ORDER BY id", (run_id,))]

    def transition(self, run_id: str, expected: str, next_state: str,
                   *, attempt: int, evidence: dict | None = None,
                   candidate_hash: str | None = None) -> None:
        if next_state not in TRANSITIONS.get(expected, set()):
            raise PilotBlocked("Forbidden pilot state transition")
        if attempt < 0 or attempt > 3:
            raise PilotBlocked("Invalid attempt index")
        digest = (hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()
                  if evidence is not None else None)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            update = self.db.execute(
                "UPDATE pilot_runs SET status=?, attempt=?, "
                "fingerprint=COALESCE(?,fingerprint), "
                "updated=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                "WHERE run_id=? AND status=? AND attempt<=?",
                (next_state, attempt, candidate_hash, run_id, expected, attempt))
            if update.rowcount != 1:
                raise PilotBlocked("Pilot CAS conflict or attempt rollback")
            self.db.execute(
                "INSERT INTO pilot_events(run_id,previous,status,attempt,evidence_sha256) "
                "VALUES (?,?,?,?,?)",
                (run_id, expected, next_state, attempt, digest))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def mark_interrupted(self, run_id: str) -> bool:
        record = self.get(run_id)
        if record["status"] not in ACTIVE:
            return False
        self.transition(run_id, record["status"], "RECOVERY_REQUIRED",
                        attempt=record["attempt"])
        return True


Worker = Callable[[int, str], None]
Checker = Callable[[dict], CheckOutcome]
Auditor = Callable[[dict, CheckOutcome], dict]


def run_simulated_cycle(host: Journal, run_id: str, *,
                        worker: Worker, checker: Checker, auditor: Auditor,
                        max_repairs: int = 2) -> dict[str, Any]:
    """Test-only injected fake execution. Never call this with real CLI executors.

    The checked code must be different after each unsuccessful round; any
    crash/denial/malformed audit/scope violation terminates instead of retrying.
    """
    if not 0 <= max_repairs <= 2:
        raise PilotBlocked("Invalid repair limit")
    pilot = PilotLedger(host)
    pilot.begin(run_id)
    feedback = ""
    previous_hash = None

    def stop(state: str, attempt: int, why: str) -> dict:
        before = pilot.get(run_id)["status"]
        if state not in TRANSITIONS[before]:
            raise PilotBlocked("Unsafe stop transition")
        pilot.transition(run_id, before, state, attempt=attempt,
                         evidence={"stop_reason": why[:120]})
        return {"status": state, "reason": why[:200], "attempts": attempt,
                "evidence_level": "SIMULATED", "hil": "NOT_VERIFIED",
                "rf": "NOT_VERIFIED", "build": "NOT_VERIFIED"}

    for attempt in range(1, max_repairs + 2):
        before = pilot.get(run_id)["status"]
        pilot.transition(run_id, before, "WORKER_RUNNING", attempt=attempt)
        try:
            worker(attempt, feedback)
        except Exception as exc:
            # Unknown external executor failure requires manual investigation;
            # never automatically rerun a possibly partial Worker write.
            return stop("RECOVERY_REQUIRED", attempt,
                        "Worker interrupted: " + type(exc).__name__)
        try:
            candidate = verify_candidate(host, run_id)
            digest = fingerprint(candidate)
        except (VerificationBlocked, StateConflict) as exc:
            return stop("BLOCKED", attempt, "Candidate gate failed: " + str(exc)[:130])
        if digest == previous_hash:
            return stop("BLOCKED", attempt, "Worker did not alter failing candidate")
        pilot.transition(run_id, "WORKER_RUNNING", "VERIFYING",
                         attempt=attempt, candidate_hash=digest,
                         evidence={"candidate_sha256": digest})
        try:
            check = checker(candidate)
        except Exception as exc:
            return stop("RECOVERY_REQUIRED", attempt,
                        "Host checks interrupted: " + type(exc).__name__)
        if not isinstance(check, CheckOutcome) or not check.valid():
            return stop("BLOCKED", attempt, "Invalid Host check receipt")
        try:
            after_checks = fingerprint(verify_candidate(host, run_id))
        except (VerificationBlocked, StateConflict) as exc:
            return stop("BLOCKED", attempt, "Post-check scope violation: " + str(exc)[:120])
        if after_checks != digest:
            return stop("BLOCKED", attempt, "Candidate changed while running checks")
        if check.status == "FAIL":
            if attempt > max_repairs:
                return stop("BLOCKED", attempt, "Deterministic checks failed after budget")
            pilot.transition(run_id, "VERIFYING", "REPAIR_REQUIRED",
                             attempt=attempt, evidence={"checks": check.checks})
            previous_hash = digest
            feedback = "Host checks failed: " + ", ".join(check.checks)
            continue

        pilot.transition(run_id, "VERIFYING", "AUDITING", attempt=attempt,
                         evidence={"checked_candidate_sha256": digest,
                                   "exit_code": check.exit_code})
        try:
            review = check_report(auditor(candidate, check), set(candidate["paths"]))
        except (AuditError, ValueError, TypeError) as exc:
            return stop("BLOCKED", attempt, "Invalid audit receipt: " + type(exc).__name__)
        except Exception as exc:
            return stop("RECOVERY_REQUIRED", attempt,
                        "Auditor interrupted: " + type(exc).__name__)
        try:
            after_audit = fingerprint(verify_candidate(host, run_id))
        except (VerificationBlocked, StateConflict) as exc:
            return stop("BLOCKED", attempt, "Post-audit scope violation: " + str(exc)[:120])
        if after_audit != digest:
            return stop("BLOCKED", attempt, "Candidate changed during Auditor review")
        if review["status"] == "INCONCLUSIVE":
            return stop("BLOCKED", attempt, "Auditor was inconclusive")
        if review["status"] == "FAIL":
            if attempt > max_repairs:
                return stop("BLOCKED", attempt, "Auditor FAIL after repair budget")
            pilot.transition(run_id, "AUDITING", "REPAIR_REQUIRED",
                             attempt=attempt, evidence={"finding_count": len(review["findings"])})
            previous_hash = digest
            feedback = ("Audit FAIL, review findings; no protocol changes: "
                        + str(review["findings"])[:1100])
            continue
        pilot.transition(run_id, "AUDITING", "AWAIT_HUMAN", attempt=attempt,
                         evidence={"candidate_sha256": digest, "review": "SIMULATED_PASS",
                                   "check": "SIMULATED_PASS"})
        return {"status": "SIMULATED_AWAIT_HUMAN", "attempts": attempt,
                "candidate_sha256": digest, "evidence_level": "SIMULATED",
                "build": "NOT_VERIFIED", "audit": "NOT_VERIFIED",
                "hil": "NOT_VERIFIED", "rf": "NOT_VERIFIED"}
    raise PilotBlocked("Unreachable state")
