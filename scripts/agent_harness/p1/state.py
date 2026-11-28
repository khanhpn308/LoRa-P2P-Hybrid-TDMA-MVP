"""SQLite journal for a single-issue, fail-closed firmware task.

It stores workflow metadata, never model credentials, shell output or source code.
SQLite is local Host state, NOT the application's PostgreSQL database.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

MAX_SIGNAL_ROWS = 500
MAX_QUERY_LIMIT = 200
MAX_FINDING_CHARS = 1000
MAX_EXCERPT_CHARS = 4000

_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----[\s\S]*?(?:-----END (?:[A-Z0-9]+ )*PRIVATE KEY-----|$)"
)
_GH_TOKEN_RE = re.compile(r"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}")
_AWS_KEY_RE = re.compile(r"AKIA[A-Z0-9]{16}")
_BEARER_RE = re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+|bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_URL_CRED_RE = re.compile(r"((?:postgres(?:ql)?|mqtts?|https?|redis)://[^:\s/@]+:)[^@\s/]+(@)")
_KV_SECRET_RE = re.compile(
    r"""(?im)(\b(?:POSTGRES_PASSWORD|MQTT_PASSWORD|password|passwd|api[_-]?key|access[_-]?token|auth[_-]?token|secret|private[_-]?key|authorization)\b\s*[:=]\s*)(["']?)([^"'\s\r\n#]+)\2"""
)
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_\-.])("
    r"pass(?:word|wd)?|pwd|secret(?:[_\-.]?key)?|"
    r"(?:api|access|private|signing|encryption|session|master|auth)[_\-.]?key|"
    r"client[_\-.]?secret|auth(?:orization)?|bearer|"
    r"(?:access|refresh|id|auth|csrf|session)?[_\-.]?token|"
    r"jwt|cookie|set[_\-.]?cookie|credentials?|k[_\-.]?join|"
    r"connection[_\-.]?string|dsn"
    r")(?:$|[_\-.])"
)
_SAFE_PLACEHOLDER_PREFIXES = ("$", "REPLACE_", "<", "[REDACTED")


def _is_safe_placeholder(value: str) -> bool:
    return not value or value.startswith(_SAFE_PLACEHOLDER_PREFIXES)


def _redact_signal_text(value: str, *, max_chars: int = MAX_EXCERPT_CHARS) -> str:
    """Redact credential signatures and bound string size before SQLite persistence."""
    if not value:
        return ""
    text = str(value)
    text = _PRIVATE_KEY_BLOCK_RE.sub("[REDACTED:PRIVATE_KEY]", text)
    text = _GH_TOKEN_RE.sub("[REDACTED:TOKEN]", text)
    text = _AWS_KEY_RE.sub("[REDACTED:AWS_KEY]", text)
    text = _BEARER_RE.sub(r"\1[REDACTED]", text)
    text = _URL_CRED_RE.sub(r"\1[REDACTED]\2", text)

    def _kv_sub(match: re.Match[str]) -> str:
        prefix, quote, secret_val = match.group(1), match.group(2), match.group(3)
        if _is_safe_placeholder(secret_val):
            return match.group(0)
        return f"{prefix}{quote}[REDACTED]{quote}"

    text = _KV_SECRET_RE.sub(_kv_sub, text)
    if len(text) > max_chars:
        suffix = "\n...[TRUNCATED]"
        keep = max(0, max_chars - len(suffix))
        text = text[:keep] + suffix
    return text


def _redact_json_value(
    obj: Any,
    *,
    max_chars: int = MAX_FINDING_CHARS,
    sensitive_context: bool = False,
) -> Any:
    if isinstance(obj, str):
        if sensitive_context and not _is_safe_placeholder(obj):
            return "[REDACTED]"
        return _redact_signal_text(obj, max_chars=max_chars)
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if sensitive_context:
            return "[REDACTED]"
        return obj
    if isinstance(obj, list):
        return [
            _redact_json_value(item, max_chars=max_chars, sensitive_context=sensitive_context)
            for item in obj[:100]
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in list(obj.items())[:50]:
            raw_key = str(k)
            safe_key = _redact_signal_text(raw_key, max_chars=max_chars)
            child_sensitive = sensitive_context or (_SENSITIVE_KEY_RE.search(raw_key) is not None)
            out[safe_key] = _redact_json_value(
                v,
                max_chars=max_chars,
                sensitive_context=child_sensitive,
            )
        return out
    return obj

_PROCESS_SEAL = os.urandom(32)


@dataclass(frozen=True)
class HostVerificationProof:
    """In-process sealed proof issued only after trusted Host gate verification.

    Note: An in-process HMAC seal is an API integrity/type guard, NOT independent
    cryptographic trust or OS process isolation under operator Full Access.
    """

    issue: int
    unit_id: str
    verification_sha256: str
    source_sha: str
    candidate_sha256: str
    manifest_sha256: str
    runner_sha256: str
    receipt_path: str
    receipt_sha256: str
    gate_rule_id: str
    auto_check: str
    _seal: bytes
    diff_sha256: str = ""
    command_receipts_sha256: str = ""
    tool_version: str = ""
    trusted_definition_sha256: str = ""


def _proof_mac(
    *,
    issue: int,
    unit_id: str,
    verification_sha256: str,
    source_sha: str,
    candidate_sha256: str,
    manifest_sha256: str,
    runner_sha256: str,
    receipt_path: str,
    receipt_sha256: str,
    gate_rule_id: str,
    auto_check: str,
    diff_sha256: str = "",
    command_receipts_sha256: str = "",
    tool_version: str = "",
    trusted_definition_sha256: str = "",
) -> bytes:
    payload = json.dumps(
        {
            "issue": issue,
            "unit_id": unit_id,
            "verification_sha256": verification_sha256,
            "source_sha": source_sha,
            "candidate_sha256": candidate_sha256,
            "manifest_sha256": manifest_sha256,
            "runner_sha256": runner_sha256,
            "receipt_path": receipt_path,
            "receipt_sha256": receipt_sha256,
            "gate_rule_id": gate_rule_id,
            "auto_check": auto_check,
            "diff_sha256": diff_sha256,
            "command_receipts_sha256": command_receipts_sha256,
            "tool_version": tool_version,
            "trusted_definition_sha256": trusted_definition_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(_PROCESS_SEAL, payload, hashlib.sha256).digest()


def issue_host_proof(
    *,
    issue: int,
    unit_id: str,
    verification_sha256: str,
    source_sha: str,
    candidate_sha256: str,
    manifest_sha256: str,
    runner_sha256: str,
    receipt_path: str,
    receipt_sha256: str,
    gate_rule_id: str,
    auto_check: str,
    diff_sha256: str = "",
    command_receipts_sha256: str = "",
    tool_version: str = "",
    trusted_definition_sha256: str = "",
) -> HostVerificationProof:
    if auto_check != "AUTO_CHECK_PASS":
        raise StateConflict("HostVerificationProof requires AUTO_CHECK_PASS")
    seal = _proof_mac(
        issue=issue,
        unit_id=unit_id,
        verification_sha256=verification_sha256,
        source_sha=source_sha,
        candidate_sha256=candidate_sha256,
        manifest_sha256=manifest_sha256,
        runner_sha256=runner_sha256,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        gate_rule_id=gate_rule_id,
        auto_check=auto_check,
        diff_sha256=diff_sha256,
        command_receipts_sha256=command_receipts_sha256,
        tool_version=tool_version,
        trusted_definition_sha256=trusted_definition_sha256,
    )
    return HostVerificationProof(
        issue=issue,
        unit_id=unit_id,
        verification_sha256=verification_sha256,
        source_sha=source_sha,
        candidate_sha256=candidate_sha256,
        manifest_sha256=manifest_sha256,
        runner_sha256=runner_sha256,
        receipt_path=receipt_path,
        receipt_sha256=receipt_sha256,
        gate_rule_id=gate_rule_id,
        auto_check=auto_check,
        _seal=seal,
        diff_sha256=diff_sha256,
        command_receipts_sha256=command_receipts_sha256,
        tool_version=tool_version,
        trusted_definition_sha256=trusted_definition_sha256,
    )


def verify_host_proof(
    proof: Any,
    *,
    issue: int,
    unit: dict[str, Any],
) -> None:
    if not isinstance(proof, HostVerificationProof):
        raise StateConflict("PASSING transition requires an in-process HostVerificationProof")
    if proof.auto_check != "AUTO_CHECK_PASS":
        raise StateConflict("HostVerificationProof did not pass AUTO_CHECK_PASS")
    if proof.issue != issue or proof.unit_id != unit["id"]:
        raise StateConflict("HostVerificationProof issue/unit mismatch")
    if proof.verification_sha256 != unit["verification"]["definition_sha256"]:
        raise StateConflict("HostVerificationProof verification_sha256 mismatch")
    if (
        not isinstance(proof.trusted_definition_sha256, str)
        or len(proof.trusted_definition_sha256) != 64
        or proof.trusted_definition_sha256 != proof.verification_sha256
    ):
        raise StateConflict("HostVerificationProof missing or mismatched frozen trusted_definition_sha256")
    ev = unit.get("evidence")
    if not isinstance(ev, dict):
        raise StateConflict("PASSING unit missing evidence dict")
    if (
        ev.get("source_sha") != proof.source_sha
        or ev.get("candidate_sha256") != proof.candidate_sha256
        or ev.get("receipt_path") != proof.receipt_path
        or ev.get("receipt_sha256") != proof.receipt_sha256
        or ev.get("verification_sha256") != proof.verification_sha256
        or ev.get("trusted_definition_sha256") != proof.trusted_definition_sha256
    ):
        raise StateConflict("HostVerificationProof does not match unit evidence")
    if proof.diff_sha256 and ev.get("diff_sha256") != proof.diff_sha256:
        raise StateConflict("HostVerificationProof diff_sha256 mismatch")
    if proof.command_receipts_sha256 and ev.get("command_receipts_sha256") != proof.command_receipts_sha256:
        raise StateConflict("HostVerificationProof command_receipts_sha256 mismatch")
    expected_seal = _proof_mac(
        issue=proof.issue,
        unit_id=proof.unit_id,
        verification_sha256=proof.verification_sha256,
        source_sha=proof.source_sha,
        candidate_sha256=proof.candidate_sha256,
        manifest_sha256=proof.manifest_sha256,
        runner_sha256=proof.runner_sha256,
        receipt_path=proof.receipt_path,
        receipt_sha256=proof.receipt_sha256,
        gate_rule_id=proof.gate_rule_id,
        auto_check=proof.auto_check,
        diff_sha256=proof.diff_sha256,
        command_receipts_sha256=proof.command_receipts_sha256,
        tool_version=proof.tool_version,
        trusted_definition_sha256=proof.trusted_definition_sha256,
    )
    if not hmac.compare_digest(proof._seal, expected_seal):
        raise StateConflict("HostVerificationProof seal verification failed")

STATES = frozenset({
    "PLANNED", "PREPARING", "PREPARED", "RECOVERY_REQUIRED",
    "BLOCKED", "CANCELLED",
})

CONTROL_STATES = frozenset({
    "ADMITTED",
    "DISPATCHED",
    "MAKER_RUNNING",
    "VERIFYING",
    "CHECKING",
    "REPAIR_REQUIRED",
    "READY_FOR_HUMAN_REVIEW",
    "BLOCKED",
    "ESCALATED",
    "CANCELLED",
})
ACTIVE_CONTROL_STATES = frozenset({
    "ADMITTED",
    "DISPATCHED",
    "MAKER_RUNNING",
    "VERIFYING",
    "CHECKING",
    "REPAIR_REQUIRED",
})
CONTROL_TRANSITIONS: dict[str, frozenset[str]] = {
    "ADMITTED": frozenset({"DISPATCHED", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "DISPATCHED": frozenset({"MAKER_RUNNING", "VERIFYING", "CHECKING", "REPAIR_REQUIRED", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "MAKER_RUNNING": frozenset({"VERIFYING", "REPAIR_REQUIRED", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "VERIFYING": frozenset({"CHECKING", "REPAIR_REQUIRED", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "CHECKING": frozenset({"READY_FOR_HUMAN_REVIEW", "REPAIR_REQUIRED", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "REPAIR_REQUIRED": frozenset({"DISPATCHED", "VERIFYING", "CANCELLED", "BLOCKED", "ESCALATED"}),
    "READY_FOR_HUMAN_REVIEW": frozenset({"CANCELLED", "BLOCKED"}),
    "BLOCKED": frozenset({"CANCELLED"}),
    "ESCALATED": frozenset({"CANCELLED"}),
    "CANCELLED": frozenset(),
}


class StateConflict(RuntimeError):
    """State did not match a compare-and-swap request."""


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise StateConflict("SQLite journal may not be a symlink")
        self.db = sqlite3.connect(str(path), timeout=15, isolation_level=None)
        self.path.chmod(0o600)  # Host-only state even under a permissive caller umask
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=15000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                run_id TEXT PRIMARY KEY,
                issue INTEGER NOT NULL CHECK(issue > 0),
                state TEXT NOT NULL,
                source_sha TEXT NOT NULL,
                issue_sha TEXT NOT NULL,
                branch TEXT NOT NULL,
                worktree TEXT NOT NULL,
                scope_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_issue
              ON jobs(issue) WHERE state IN (
                'PLANNED','PREPARING','PREPARED','RECOVERY_REQUIRED','BLOCKED');
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES jobs(run_id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS feature_docs (
                issue INTEGER PRIMARY KEY CHECK(issue > 0),
                revision INTEGER NOT NULL CHECK(revision >= 1),
                doc_json TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS feature_units (
                issue INTEGER NOT NULL CHECK(issue > 0),
                unit_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('PENDING','ACTIVE','BLOCKED','PASSING','STALE')),
                verification_sha256 TEXT NOT NULL,
                blocker TEXT NOT NULL DEFAULT '',
                evidence_json TEXT,
                updated_by TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                PRIMARY KEY (issue, unit_id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_unit_per_issue
              ON feature_units(issue) WHERE state = 'ACTIVE';
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue INTEGER NOT NULL CHECK(issue > 0),
                run_id TEXT,
                revision_sha TEXT NOT NULL,
                candidate_sha256 TEXT NOT NULL,
                branch TEXT NOT NULL,
                worktree_rel TEXT NOT NULL,
                active_unit TEXT,
                blocker TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL,
                decision_refs_json TEXT NOT NULL DEFAULT '[]',
                issue_sha256 TEXT NOT NULL DEFAULT '',
                handoff_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS signals (
                signal_id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue INTEGER,
                unit_id TEXT,
                run_id TEXT,
                signal_type TEXT NOT NULL CHECK(signal_type IN ('process', 'runtime')),
                category TEXT NOT NULL,
                owning_domain TEXT NOT NULL,
                check_id TEXT NOT NULL DEFAULT '',
                command_sha256 TEXT NOT NULL DEFAULT '',
                source_sha TEXT NOT NULL DEFAULT '',
                candidate_sha256 TEXT NOT NULL DEFAULT '',
                diff_sha256 TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL DEFAULT '',
                ended_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                duration_s REAL NOT NULL DEFAULT 0.0,
                exit_code INTEGER,
                status TEXT NOT NULL,
                captured INTEGER NOT NULL CHECK(captured IN (0, 1)),
                finding TEXT NOT NULL DEFAULT '',
                evidence_ref_json TEXT NOT NULL DEFAULT '{}',
                excerpt TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_signals_issue_id
              ON signals(issue, signal_id);
            CREATE TABLE IF NOT EXISTS control_runs (
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
                streak_candidate_sha256 TEXT NOT NULL DEFAULT '',
                streak_diff_sha256 TEXT NOT NULL DEFAULT '',
                streak_policy_sha256 TEXT NOT NULL DEFAULT '',
                streak_check_plan_sha256 TEXT NOT NULL DEFAULT '',
                streak_selection_sha256 TEXT NOT NULL DEFAULT '',
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
                evidence_dir TEXT NOT NULL DEFAULT '',
                frozen_plan_json TEXT NOT NULL DEFAULT '{}',
                lease_owner_pid INTEGER,
                lease_owner_start_ticks TEXT NOT NULL DEFAULT '',
                lease_owner_host TEXT NOT NULL DEFAULT '',
                lease_acquired_at TEXT NOT NULL DEFAULT '',
                lease_heartbeat_at TEXT NOT NULL DEFAULT '',
                in_flight_round INTEGER NOT NULL DEFAULT 0,
                last_completed_op TEXT NOT NULL DEFAULT '',
                completed_ops_json TEXT NOT NULL DEFAULT '[]',
                recovery_reason TEXT NOT NULL DEFAULT '',
                next_action TEXT NOT NULL DEFAULT '',
                blocker TEXT NOT NULL DEFAULT '',
                cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0, 1)),
                cancel_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_control_run_per_issue
              ON control_runs(issue) WHERE state IN (
                'ADMITTED','DISPATCHED','MAKER_RUNNING','VERIFYING','CHECKING','REPAIR_REQUIRED');
            CREATE TABLE IF NOT EXISTS control_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES control_runs(run_id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                actor_role TEXT NOT NULL,
                action TEXT NOT NULL,
                dispatch_token TEXT NOT NULL DEFAULT '',
                detail_json TEXT NOT NULL DEFAULT '{}',
                utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            CREATE TABLE IF NOT EXISTS control_rounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES control_runs(run_id),
                round_num INTEGER NOT NULL CHECK(round_num >= 1),
                maker_dispatched INTEGER NOT NULL DEFAULT 1 CHECK(maker_dispatched IN (0, 1)),
                confirming_pass INTEGER NOT NULL DEFAULT 0 CHECK(confirming_pass IN (0, 1)),
                outcome TEXT NOT NULL,
                verdict TEXT NOT NULL,
                source_sha TEXT NOT NULL DEFAULT '',
                base_sha TEXT NOT NULL DEFAULT '',
                candidate_sha256 TEXT NOT NULL DEFAULT '',
                diff_sha256 TEXT NOT NULL DEFAULT '',
                policy_sha256 TEXT NOT NULL DEFAULT '',
                check_plan_sha256 TEXT NOT NULL DEFAULT '',
                selection_sha256 TEXT NOT NULL DEFAULT '',
                agents_sha256 TEXT NOT NULL DEFAULT '',
                selected_ids_json TEXT NOT NULL DEFAULT '[]',
                checks_summary_sha256 TEXT NOT NULL DEFAULT '',
                manifest_sha256 TEXT NOT NULL DEFAULT '',
                auditor_report_sha256 TEXT NOT NULL DEFAULT '',
                evidence_refs_json TEXT NOT NULL DEFAULT '{}',
                host_checks_passed INTEGER NOT NULL CHECK(host_checks_passed IN (0, 1)),
                checker_passed INTEGER NOT NULL CHECK(checker_passed IN (0, 1)),
                rubric_decision TEXT NOT NULL DEFAULT 'NOT_VERIFIED',
                rubric_total_score INTEGER,
                rubric_hard_gate_passed INTEGER CHECK(rubric_hard_gate_passed IN (0, 1) OR rubric_hard_gate_passed IS NULL),
                rubric_json TEXT NOT NULL DEFAULT '{}',
                findings_json TEXT NOT NULL DEFAULT '[]',
                repair_scope_json TEXT NOT NULL DEFAULT '[]',
                next_action TEXT NOT NULL DEFAULT '',
                failure_sig TEXT NOT NULL DEFAULT '',
                wall_elapsed_s REAL NOT NULL DEFAULT 0.0,
                cumulative_wall_s REAL NOT NULL DEFAULT 0.0,
                tokens_used INTEGER,
                cost_used REAL,
                consecutive_passes INTEGER NOT NULL DEFAULT 0,
                no_progress_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                UNIQUE(run_id, round_num)
            );
            CREATE INDEX IF NOT EXISTS idx_control_rounds_run_round
              ON control_rounds(run_id, round_num);
        """)
        existing_ctrl_cols = {
            r["name"] for r in self.db.execute("PRAGMA table_info(control_runs)").fetchall()
        }
        for col_name in (
            "streak_candidate_sha256",
            "streak_diff_sha256",
            "streak_policy_sha256",
            "streak_check_plan_sha256",
            "streak_selection_sha256",
            "evidence_dir",
            "lease_owner_start_ticks",
            "lease_owner_host",
            "lease_acquired_at",
            "lease_heartbeat_at",
            "last_completed_op",
            "recovery_reason",
            "next_action",
            "blocker",
        ):
            if col_name not in existing_ctrl_cols:
                self.db.execute(
                    f"ALTER TABLE control_runs ADD COLUMN {col_name} TEXT NOT NULL DEFAULT ''"
                )
        if "frozen_plan_json" not in existing_ctrl_cols:
            self.db.execute(
                "ALTER TABLE control_runs ADD COLUMN frozen_plan_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "completed_ops_json" not in existing_ctrl_cols:
            self.db.execute(
                "ALTER TABLE control_runs ADD COLUMN completed_ops_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "lease_owner_pid" not in existing_ctrl_cols:
            self.db.execute(
                "ALTER TABLE control_runs ADD COLUMN lease_owner_pid INTEGER"
            )
        if "in_flight_round" not in existing_ctrl_cols:
            self.db.execute(
                "ALTER TABLE control_runs ADD COLUMN in_flight_round INTEGER NOT NULL DEFAULT 0"
            )
        existing_round_cols = {
            r["name"] for r in self.db.execute("PRAGMA table_info(control_rounds)").fetchall()
        }
        if "evidence_refs_json" not in existing_round_cols:
            self.db.execute(
                "ALTER TABLE control_rounds ADD COLUMN evidence_refs_json TEXT NOT NULL DEFAULT '{}'"
            )

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "Journal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def plan(self, *, run_id: str, issue: int, source_sha: str, issue_sha: str,
             branch: str, worktree: Path, scope: tuple[str, ...]) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("""
                INSERT INTO jobs(run_id,issue,state,source_sha,issue_sha,branch,worktree,scope_json)
                VALUES (?,?,?,?,?,?,?,?)
            """, (run_id, issue, "PLANNED", source_sha, issue_sha, branch,
                  str(worktree), json.dumps(scope)))
            self.db.execute("INSERT INTO events(run_id,to_state,note) VALUES (?,?,?)",
                            (run_id, "PLANNED", "Scope preflight completed"))
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self.db.execute("ROLLBACK")
            raise StateConflict("Issue already active or run ID already exists") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def get(self, run_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM jobs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise StateConflict("Unknown run ID")
        return dict(row)

    def events(self, run_id: str) -> list[dict[str, Any]]:
        self.get(run_id)
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM events WHERE run_id=? ORDER BY event_id", (run_id,))]

    def transition(self, run_id: str, *, expected: str, next_state: str,
                   note: str = "") -> None:
        if expected not in STATES or next_state not in STATES:
            raise StateConflict("Unknown lifecycle state")
        # Never allow a fabricated success state or a direct recovery-to-prepared transition.
        allowed = {
            "PLANNED": {"PREPARING", "CANCELLED", "BLOCKED"},
            "PREPARING": {"PREPARED", "RECOVERY_REQUIRED", "BLOCKED"},
            "PREPARED": {"CANCELLED", "RECOVERY_REQUIRED"},
            "RECOVERY_REQUIRED": {"CANCELLED", "BLOCKED"},
            "BLOCKED": {"CANCELLED"},
            "CANCELLED": set(),
        }
        if next_state not in allowed[expected]:
            raise StateConflict("Forbidden state transition")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            update = self.db.execute("""
                UPDATE jobs SET state=?,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                WHERE run_id=? AND state=?
            """, (next_state, run_id, expected))
            if update.rowcount != 1:
                raise StateConflict("CAS failed: run was updated, removed or is in another state")
            self.db.execute("""
                INSERT INTO events(run_id,from_state,to_state,note) VALUES (?,?,?,?)
            """, (run_id, expected, next_state, note[:300]))
            self.db.execute("COMMIT")
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def detect_interruption(self, run_id: str) -> bool:
        """Human-triggered crash recovery check; NEVER silently retry a task."""
        status = self.get(run_id)["state"]
        if status == "PREPARING":
            self.transition(run_id, expected="PREPARING",
                            next_state="RECOVERY_REQUIRED",
                            note="Interrupted preparation: inspect git worktree list and branch")
            return True
        return False

    def active_job_for_issue(self, issue: int) -> dict[str, Any] | None:
        row = self.db.execute(
            """SELECT * FROM jobs
               WHERE issue=? AND state IN ('PLANNED','PREPARING','PREPARED','RECOVERY_REQUIRED','BLOCKED')
               ORDER BY rowid DESC LIMIT 1""",
            (issue,),
        ).fetchone()
        return dict(row) if row is not None else None

    def latest_job_for_issue(self, issue: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM jobs WHERE issue=? ORDER BY rowid DESC LIMIT 1",
            (issue,),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_feature_snapshot(self, issue: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT issue, revision, doc_json, updated_by, updated_at FROM feature_docs WHERE issue=?",
            (issue,),
        ).fetchone()
        if row is None:
            return None
        doc = json.loads(row["doc_json"])
        proj_rows = self.db.execute(
            "SELECT unit_id, state, verification_sha256, blocker, evidence_json FROM feature_units WHERE issue=?",
            (issue,),
        ).fetchall()
        proj_by_id = {r["unit_id"]: dict(r) for r in proj_rows}
        doc_units = doc.get("units", [])
        if len(proj_by_id) != len(doc_units):
            raise StateConflict("Journal feature_docs and feature_units projection count mismatch")
        for u in doc_units:
            uid = u.get("id")
            proj = proj_by_id.get(uid)
            if proj is None:
                raise StateConflict(f"Journal unit projection missing unit {uid!r}")
            if proj["state"] != u.get("state"):
                raise StateConflict(f"Journal doc vs unit projection state mismatch on {uid!r}")
            if proj["verification_sha256"] != u.get("verification", {}).get("definition_sha256"):
                raise StateConflict(f"Journal doc vs unit projection verification hash mismatch on {uid!r}")
            doc_ev = json.dumps(u.get("evidence"), sort_keys=True) if u.get("evidence") is not None else None
            proj_ev = (
                json.dumps(json.loads(proj["evidence_json"]), sort_keys=True)
                if proj["evidence_json"] is not None
                else None
            )
            if doc_ev != proj_ev:
                raise StateConflict(f"Journal doc vs unit projection evidence mismatch on {uid!r}")
        return {
            "issue": row["issue"],
            "revision": row["revision"],
            "doc": doc,
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def _apply_feature_snapshot_in_tx(
        self,
        *,
        issue: int,
        expected_revision: int | None,
        revision: int,
        doc_json: str,
        units: list[dict[str, Any]],
        actor: str,
        host_proofs: dict[str, HostVerificationProof] | None = None,
        allow_definition_change: bool = False,
        expected_branch: str | None = None,
    ) -> None:
        parsed = json.loads(doc_json)
        if not isinstance(parsed, dict) or parsed.get("issue") != issue or parsed.get("revision") != revision:
            raise StateConflict("Feature snapshot doc_json disagrees with issue/revision")
        doc_units = parsed.get("units")
        if not isinstance(doc_units, list) or len(doc_units) != len(units):
            raise StateConflict("Feature snapshot doc_json disagrees with units")
        for du, u in zip(doc_units, units):
            if du.get("id") != u.get("id") or du.get("state") != u.get("state"):
                raise StateConflict("Feature snapshot doc_json unit state mismatch")
        doc_branch = str(parsed.get("git", {}).get("branch", "") or "")
        if expected_branch is not None and doc_branch and doc_branch != expected_branch:
            raise StateConflict("Feature snapshot branch mismatch")

        existing_doc_row = self.db.execute(
            "SELECT revision, doc_json FROM feature_docs WHERE issue=?",
            (issue,),
        ).fetchone()
        if expected_revision is None:
            if existing_doc_row is not None:
                raise StateConflict("Feature state already exists for Issue")
            self.db.execute(
                """INSERT INTO feature_docs(issue, revision, doc_json, updated_by)
                   VALUES (?, ?, ?, ?)""",
                (issue, revision, doc_json, actor),
            )
        else:
            if existing_doc_row is None:
                raise StateConflict("CAS failed: missing feature state for Issue")
            if expected_branch is not None:
                prev_branch = str(json.loads(existing_doc_row["doc_json"]).get("git", {}).get("branch", "") or "")
                if prev_branch and prev_branch != expected_branch:
                    raise StateConflict("Persisted branch mismatch during CAS update")
            upd = self.db.execute(
                """UPDATE feature_docs
                   SET revision=?, doc_json=?, updated_by=?,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE issue=? AND revision=?""",
                (revision, doc_json, actor, issue, expected_revision),
            )
            if upd.rowcount != 1:
                raise StateConflict("CAS failed: feature state revision conflict or missing issue")

        prev_rows = self.db.execute(
            "SELECT unit_id, state, verification_sha256, evidence_json FROM feature_units WHERE issue=?",
            (issue,),
        ).fetchall()
        prev_units = {r["unit_id"]: dict(r) for r in prev_rows}

        for unit in units:
            uid = unit["id"]
            new_state = unit["state"]
            ver_sha = unit["verification"]["definition_sha256"]
            ev = unit.get("evidence")
            ev_canonical = json.dumps(ev, sort_keys=True) if ev is not None else None
            prev = prev_units.get(uid)
            if prev is not None and prev["verification_sha256"] != ver_sha and not allow_definition_change:
                raise StateConflict(f"Unauthorized verification definition change on unit {uid}")
            if new_state == "PASSING":
                prev_ev_canonical = (
                    json.dumps(json.loads(prev["evidence_json"]), sort_keys=True)
                    if prev is not None and prev["evidence_json"] is not None
                    else None
                )
                unchanged_passing = (
                    prev is not None
                    and prev["state"] == "PASSING"
                    and prev["verification_sha256"] == ver_sha
                    and prev_ev_canonical == ev_canonical
                )
                if not unchanged_passing:
                    if prev is not None and prev["state"] != "ACTIVE":
                        raise StateConflict(
                            f"Unit {uid} must be ACTIVE before transitioning to PASSING (was {prev['state']})"
                        )
                    proof = (host_proofs or {}).get(uid)
                    verify_host_proof(proof, issue=issue, unit=unit)

        self.db.execute("DELETE FROM feature_units WHERE issue=?", (issue,))
        for unit in units:
            evidence = unit.get("evidence")
            self.db.execute(
                """INSERT INTO feature_units(
                       issue, unit_id, state, verification_sha256,
                       blocker, evidence_json, updated_by
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue,
                    unit["id"],
                    unit["state"],
                    unit["verification"]["definition_sha256"],
                    unit.get("blocker") or "",
                    json.dumps(evidence, sort_keys=True) if evidence is not None else None,
                    actor,
                ),
            )

    def save_feature_snapshot(
        self,
        *,
        issue: int,
        expected_revision: int | None,
        revision: int,
        doc_json: str,
        units: list[dict[str, Any]],
        actor: str,
        host_proofs: dict[str, HostVerificationProof] | None = None,
        allow_definition_change: bool = False,
        expected_branch: str | None = None,
    ) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self._apply_feature_snapshot_in_tx(
                issue=issue,
                expected_revision=expected_revision,
                revision=revision,
                doc_json=doc_json,
                units=units,
                actor=actor,
                host_proofs=host_proofs,
                allow_definition_change=allow_definition_change,
                expected_branch=expected_branch,
            )
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise StateConflict("Feature state constraint/WIP=1 conflict") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def save_checkpoint_and_snapshot(
        self,
        *,
        issue: int,
        run_id: str | None,
        revision_sha: str,
        candidate_sha256: str,
        branch: str,
        worktree_rel: str,
        active_unit: str | None,
        blocker: str,
        next_action: str,
        decision_refs: tuple[str, ...] | list[str],
        issue_sha256: str,
        handoff_json: str,
        snapshot_args: dict[str, Any] | None = None,
        expected_branch: str | None = None,
    ) -> int:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            last_ckpt = self.db.execute(
                "SELECT branch FROM checkpoints WHERE issue=? ORDER BY checkpoint_id DESC LIMIT 1",
                (issue,),
            ).fetchone()
            if expected_branch is not None and last_ckpt is not None and last_ckpt["branch"]:
                if last_ckpt["branch"] != expected_branch:
                    raise StateConflict("Branch mismatch against prior checkpoint")
            if snapshot_args is not None:
                self._apply_feature_snapshot_in_tx(**snapshot_args)
            cur = self.db.execute(
                """INSERT INTO checkpoints(
                       issue, run_id, revision_sha, candidate_sha256, branch,
                       worktree_rel, active_unit, blocker, next_action,
                       decision_refs_json, issue_sha256, handoff_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue,
                    run_id,
                    revision_sha,
                    candidate_sha256,
                    branch,
                    worktree_rel,
                    active_unit,
                    blocker,
                    next_action,
                    json.dumps(list(decision_refs)),
                    issue_sha256,
                    handoff_json,
                ),
            )
            checkpoint_id = int(cur.lastrowid)
            self.db.execute("COMMIT")
            return checkpoint_id
        except sqlite3.IntegrityError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise StateConflict("Feature state constraint/WIP=1 conflict") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def record_checkpoint(
        self,
        *,
        issue: int,
        run_id: str | None,
        revision_sha: str,
        candidate_sha256: str,
        branch: str,
        worktree_rel: str,
        active_unit: str | None,
        blocker: str,
        next_action: str,
        decision_refs: tuple[str, ...] | list[str],
        issue_sha256: str,
        handoff_json: str,
    ) -> int:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            cur = self.db.execute(
                """INSERT INTO checkpoints(
                       issue, run_id, revision_sha, candidate_sha256, branch,
                       worktree_rel, active_unit, blocker, next_action,
                       decision_refs_json, issue_sha256, handoff_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    issue,
                    run_id,
                    revision_sha,
                    candidate_sha256,
                    branch,
                    worktree_rel,
                    active_unit,
                    blocker,
                    next_action,
                    json.dumps(list(decision_refs)),
                    issue_sha256,
                    handoff_json,
                ),
            )
            checkpoint_id = int(cur.lastrowid)
            self.db.execute("COMMIT")
            return checkpoint_id
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def latest_checkpoint(self, issue: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM checkpoints WHERE issue=? ORDER BY checkpoint_id DESC LIMIT 1",
            (issue,),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["decision_refs"] = json.loads(data.pop("decision_refs_json"))
        data["handoff"] = json.loads(data.pop("handoff_json"))
        return data

    def list_checkpoints(self, issue: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM checkpoints WHERE issue=? ORDER BY checkpoint_id",
            (issue,),
        ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["decision_refs"] = json.loads(data.pop("decision_refs_json"))
            data["handoff"] = json.loads(data.pop("handoff_json"))
            results.append(data)
        return results

    def record_signal(
        self,
        *,
        signal_type: str,
        category: str,
        owning_domain: str,
        status: str,
        captured: bool = True,
        issue: int | None = None,
        unit_id: str | None = None,
        run_id: str | None = None,
        check_id: str = "",
        command_sha256: str = "",
        source_sha: str = "",
        candidate_sha256: str = "",
        diff_sha256: str = "",
        started_at: str = "",
        ended_at: str = "",
        duration_s: float = 0.0,
        exit_code: int | None = None,
        finding: str = "",
        evidence_ref: dict[str, Any] | None = None,
        excerpt: str = "",
        max_signals: int = MAX_SIGNAL_ROWS,
    ) -> int:
        if signal_type not in ("process", "runtime"):
            raise StateConflict(f"Invalid signal_type: {signal_type!r}")
        if not str(category).strip() or not str(owning_domain).strip() or not str(status).strip():
            raise StateConflict("Signal category, owning_domain, and status are required")
        if issue is not None and issue <= 0:
            raise StateConflict("Signal issue must be positive")
        if max_signals < 1:
            raise StateConflict("max_signals retention bound must be >= 1")

        safe_finding = _redact_signal_text(finding, max_chars=MAX_FINDING_CHARS)
        safe_excerpt = _redact_signal_text(excerpt, max_chars=MAX_EXCERPT_CHARS)
        safe_ref = _redact_json_value(evidence_ref or {}, max_chars=MAX_FINDING_CHARS)
        ref_json = json.dumps(safe_ref, sort_keys=True)
        ended_expr = ended_at.strip()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if ended_expr:
                cur = self.db.execute(
                    """INSERT INTO signals(
                           issue, unit_id, run_id, signal_type, category, owning_domain,
                           check_id, command_sha256, source_sha, candidate_sha256, diff_sha256,
                           started_at, ended_at, duration_s, exit_code, status, captured,
                           finding, evidence_ref_json, excerpt
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue, unit_id, run_id, signal_type, category.strip(), owning_domain.strip(),
                        str(check_id)[:120], str(command_sha256)[:64], str(source_sha)[:64],
                        str(candidate_sha256)[:64], str(diff_sha256)[:64],
                        started_at.strip()[:64], ended_expr[:64], float(duration_s),
                        exit_code, status.strip()[:40], 1 if captured else 0,
                        safe_finding, ref_json, safe_excerpt,
                    ),
                )
            else:
                cur = self.db.execute(
                    """INSERT INTO signals(
                           issue, unit_id, run_id, signal_type, category, owning_domain,
                           check_id, command_sha256, source_sha, candidate_sha256, diff_sha256,
                           started_at, duration_s, exit_code, status, captured,
                           finding, evidence_ref_json, excerpt
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        issue, unit_id, run_id, signal_type, category.strip(), owning_domain.strip(),
                        str(check_id)[:120], str(command_sha256)[:64], str(source_sha)[:64],
                        str(candidate_sha256)[:64], str(diff_sha256)[:64],
                        started_at.strip()[:64], float(duration_s),
                        exit_code, status.strip()[:40], 1 if captured else 0,
                        safe_finding, ref_json, safe_excerpt,
                    ),
                )
            signal_id = int(cur.lastrowid)
            self.db.execute(
                """DELETE FROM signals
                   WHERE signal_id NOT IN (
                       SELECT signal_id FROM signals ORDER BY signal_id DESC LIMIT ?
                   )""",
                (max_signals,),
            )
            self.db.execute("COMMIT")
            return signal_id
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def query_signals(
        self,
        *,
        issue: int | None = None,
        run_id: str | None = None,
        unit_id: str | None = None,
        signal_type: str | None = None,
        category: str | None = None,
        owning_domain: str | None = None,
        status: str | None = None,
        captured: bool | None = None,
        since: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit), MAX_QUERY_LIMIT))
        clauses: list[str] = []
        params: list[Any] = []
        if issue is not None:
            clauses.append("issue = ?")
            params.append(issue)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if unit_id is not None:
            clauses.append("unit_id = ?")
            params.append(unit_id)
        if signal_type is not None:
            clauses.append("signal_type = ?")
            params.append(signal_type)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if owning_domain is not None:
            clauses.append("owning_domain = ?")
            params.append(owning_domain)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if captured is not None:
            clauses.append("captured = ?")
            params.append(1 if captured else 0)
        if since is not None:
            clauses.append("ended_at >= ?")
            params.append(since)
        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM signals {where_sql} ORDER BY signal_id DESC LIMIT ?"
        params.append(bounded_limit)
        rows = self.db.execute(sql, tuple(params)).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            data = dict(row)
            data["captured"] = bool(data["captured"])
            data["evidence_ref"] = json.loads(data.pop("evidence_ref_json"))
            results.append(data)
        return results

    def prune_signals(self, *, keep: int = MAX_SIGNAL_ROWS) -> int:
        if keep < 0:
            raise StateConflict("Retention keep count must be >= 0")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if keep == 0:
                cur = self.db.execute("DELETE FROM signals")
            else:
                cur = self.db.execute(
                    """DELETE FROM signals
                       WHERE signal_id NOT IN (
                           SELECT signal_id FROM signals ORDER BY signal_id DESC LIMIT ?
                       )""",
                    (keep,),
                )
            deleted = int(cur.rowcount)
            self.db.execute("COMMIT")
            return deleted
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    @staticmethod
    def _decode_control_run(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["policy"] = json.loads(data.pop("policy_json"))
        data["admission"] = json.loads(data.pop("admission_json"))
        data["budget_consumed"] = json.loads(data.pop("budget_consumed_json"))
        raw_plan = data.pop("frozen_plan_json", "{}") or "{}"
        data["frozen_plan"] = json.loads(raw_plan)
        raw_ops = data.pop("completed_ops_json", "[]") or "[]"
        data["completed_ops"] = json.loads(raw_ops)
        data["cancel_requested"] = bool(data["cancel_requested"])
        return data

    def create_control_run(
        self,
        *,
        run_id: str,
        issue: int,
        source_sha: str,
        base_sha: str,
        candidate_sha256: str,
        branch: str,
        worktree: str,
        agents_sha256: str,
        selection_sha256: str,
        check_plan_sha256: str,
        policy_sha256: str,
        policy: dict[str, Any],
        admission: dict[str, Any],
        evidence_dir: str = "",
        frozen_plan: dict[str, Any] | None = None,
        next_action: str = "",
        sequential_only: bool = True,
        actor_role: str = "host",
    ) -> dict[str, Any]:
        safe_policy = _redact_json_value(policy, max_chars=MAX_FINDING_CHARS)
        safe_admission = _redact_json_value(admission, max_chars=MAX_FINDING_CHARS)
        safe_plan = _redact_json_value(frozen_plan or {}, max_chars=MAX_FINDING_CHARS)
        safe_next_action = _redact_signal_text(
            next_action or f"Dispatch Maker within frozen policy {policy_sha256[:12]}",
            max_chars=MAX_FINDING_CHARS,
        )
        initial_ops = [{"op": "admitted", "round_num": 0, "candidate_sha256": candidate_sha256}]
        initial_budget = {
            "rounds": 0,
            "wall_seconds": 0.0,
            "no_progress_count": 0,
            "consecutive_passes": 0,
            "tokens_used": None,
            "cost_usd": None,
        }
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if sequential_only:
                active = self.db.execute(
                    """SELECT run_id, issue, state FROM control_runs
                       WHERE state IN ('ADMITTED','DISPATCHED','MAKER_RUNNING','VERIFYING','CHECKING','REPAIR_REQUIRED')
                       LIMIT 1"""
                ).fetchone()
                if active is not None:
                    raise StateConflict(
                        f"Sequential WIP=1 violation: control run {active['run_id']} "
                        f"(Issue #{active['issue']}, state={active['state']}) is active"
                    )
            self.db.execute(
                """INSERT INTO control_runs(
                       run_id, issue, state, active_role, dispatch_seq, dispatch_token,
                       round_num, consecutive_passes, no_progress_count,
                       last_failure_sig, last_diff_sha256,
                       source_sha, base_sha, candidate_sha256, branch, worktree,
                       agents_sha256, selection_sha256, check_plan_sha256, policy_sha256,
                       policy_json, admission_json, budget_consumed_json,
                       evidence_dir, frozen_plan_json, in_flight_round,
                       last_completed_op, completed_ops_json, next_action
                   ) VALUES (?, ?, 'ADMITTED', NULL, 0, '', 0, 0, 0, '', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'admitted', ?, ?)""",
                (
                    run_id,
                    issue,
                    source_sha,
                    base_sha,
                    candidate_sha256,
                    branch,
                    worktree,
                    agents_sha256,
                    selection_sha256,
                    check_plan_sha256,
                    policy_sha256,
                    json.dumps(safe_policy, sort_keys=True),
                    json.dumps(safe_admission, sort_keys=True),
                    json.dumps(initial_budget, sort_keys=True),
                    str(evidence_dir),
                    json.dumps(safe_plan, sort_keys=True),
                    json.dumps(initial_ops, sort_keys=True),
                    safe_next_action,
                ),
            )
            self.db.execute(
                """INSERT INTO control_events(
                       run_id, from_state, to_state, actor_role, action, dispatch_token, detail_json
                   ) VALUES (?, NULL, 'ADMITTED', ?, 'admit_run', '', ?)""",
                (
                    run_id,
                    actor_role,
                    json.dumps({"policy_sha256": policy_sha256, "selection_sha256": selection_sha256}, sort_keys=True),
                ),
            )
            self.db.execute("COMMIT")
            return self.get_control_run(run_id)
        except sqlite3.IntegrityError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise StateConflict("Control run already exists or active WIP=1 Issue conflict") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def get_control_run(self, run_id: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM control_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise StateConflict(f"Unknown control run ID: {run_id}")
        return self._decode_control_run(row)

    def active_control_runs(self, *, issue: int | None = None) -> list[dict[str, Any]]:
        if issue is not None:
            rows = self.db.execute(
                """SELECT * FROM control_runs
                   WHERE issue=? AND state IN ('ADMITTED','DISPATCHED','MAKER_RUNNING','VERIFYING','CHECKING','REPAIR_REQUIRED')
                   ORDER BY rowid DESC""",
                (issue,),
            ).fetchall()
        else:
            rows = self.db.execute(
                """SELECT * FROM control_runs
                   WHERE state IN ('ADMITTED','DISPATCHED','MAKER_RUNNING','VERIFYING','CHECKING','REPAIR_REQUIRED')
                   ORDER BY rowid DESC"""
            ).fetchall()
        return [self._decode_control_run(r) for r in rows]

    def latest_control_run_for_issue(self, issue: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM control_runs WHERE issue=? ORDER BY rowid DESC LIMIT 1",
            (issue,),
        ).fetchone()
        return self._decode_control_run(row) if row is not None else None

    def control_events(self, run_id: str) -> list[dict[str, Any]]:
        self.get_control_run(run_id)
        rows = self.db.execute(
            "SELECT * FROM control_events WHERE run_id=? ORDER BY event_id",
            (run_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["detail"] = json.loads(d.pop("detail_json"))
            out.append(d)
        return out

    def acquire_dispatch(
        self,
        run_id: str,
        *,
        expected_state: str,
        role: str,
        actor_role: str,
        dispatch_token: str,
        detail: dict[str, Any] | None = None,
        lease_owner_pid: int | None = None,
        lease_owner_start_ticks: str = "",
        lease_owner_host: str = "",
        in_flight_round: int | None = None,
    ) -> dict[str, Any]:
        if expected_state not in ("ADMITTED", "REPAIR_REQUIRED"):
            raise StateConflict(f"Cannot dispatch from state {expected_state!r}")
        if not dispatch_token:
            raise StateConflict("Dispatch token is required")
        safe_detail = _redact_json_value(detail or {}, max_chars=MAX_FINDING_CHARS)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM control_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise StateConflict(f"Unknown control run ID: {run_id}")
            if row["cancel_requested"]:
                raise StateConflict("Cannot dispatch after cancellation was requested")
            if row["dispatch_token"]:
                raise StateConflict(
                    f"Duplicate dispatch blocked: active token {row['dispatch_token']} for role {row['active_role']}"
                )
            if row["state"] != expected_state:
                raise StateConflict(
                    f"CAS failed on dispatch: expected {expected_state}, actual {row['state']}"
                )
            new_seq = int(row["dispatch_seq"]) + 1
            eff_round = int(in_flight_round) if in_flight_round is not None else (int(row["round_num"]) + 1)
            ops = json.loads(row["completed_ops_json"] or "[]")
            ops.append({"op": f"dispatched_{role}", "round_num": eff_round, "dispatch_seq": new_seq})
            ops = ops[-40:]
            upd = self.db.execute(
                """UPDATE control_runs
                   SET state='DISPATCHED', active_role=?, dispatch_seq=?, dispatch_token=?,
                       lease_owner_pid=?, lease_owner_start_ticks=?, lease_owner_host=?,
                       lease_acquired_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                       lease_heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now'),
                       in_flight_round=?, last_completed_op=?, completed_ops_json=?,
                       updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                   WHERE run_id=? AND state=? AND dispatch_token='' AND cancel_requested=0""",
                (
                    role,
                    new_seq,
                    dispatch_token,
                    lease_owner_pid,
                    str(lease_owner_start_ticks or ""),
                    str(lease_owner_host or ""),
                    eff_round,
                    f"dispatched_{role}",
                    json.dumps(ops, sort_keys=True),
                    run_id,
                    expected_state,
                ),
            )
            if upd.rowcount != 1:
                raise StateConflict("CAS failed while acquiring dispatch lease")
            self.db.execute(
                """INSERT INTO control_events(
                       run_id, from_state, to_state, actor_role, action, dispatch_token, detail_json
                   ) VALUES (?, ?, 'DISPATCHED', ?, 'dispatch_role', ?, ?)""",
                (run_id, expected_state, actor_role, dispatch_token, json.dumps(safe_detail, sort_keys=True)),
            )
            self.db.execute("COMMIT")
            return self.get_control_run(run_id)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def transition_control_run(
        self,
        run_id: str,
        *,
        expected: str,
        next_state: str,
        actor_role: str,
        action: str,
        expected_dispatch_token: str | None = None,
        clear_dispatch: bool = False,
        update_fields: dict[str, Any] | None = None,
        detail: dict[str, Any] | None = None,
        round_record: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if expected not in CONTROL_STATES or next_state not in CONTROL_STATES:
            raise StateConflict("Unknown control-plane lifecycle state")
        if next_state not in CONTROL_TRANSITIONS.get(expected, frozenset()):
            raise StateConflict(f"Forbidden control-plane transition: {expected} -> {next_state}")
        allowed_cols = frozenset({
            "active_role",
            "round_num",
            "consecutive_passes",
            "no_progress_count",
            "last_failure_sig",
            "last_diff_sha256",
            "streak_candidate_sha256",
            "streak_diff_sha256",
            "streak_policy_sha256",
            "streak_check_plan_sha256",
            "streak_selection_sha256",
            "candidate_sha256",
            "budget_consumed_json",
            "evidence_dir",
            "lease_owner_pid",
            "lease_owner_start_ticks",
            "lease_owner_host",
            "lease_acquired_at",
            "lease_heartbeat_at",
            "in_flight_round",
            "last_completed_op",
            "completed_ops_json",
            "recovery_reason",
            "next_action",
            "blocker",
            "cancel_requested",
            "cancel_reason",
        })
        updates = dict(update_fields or {})
        unknown_cols = set(updates) - allowed_cols
        if unknown_cols:
            raise StateConflict(f"Unsupported control_runs columns: {sorted(unknown_cols)}")
        if clear_dispatch:
            updates["dispatch_token"] = ""
            updates["active_role"] = None
            updates["lease_owner_pid"] = None
            updates["lease_owner_start_ticks"] = ""
            updates["lease_owner_host"] = ""
            updates["lease_acquired_at"] = ""
            updates["lease_heartbeat_at"] = ""
        safe_detail = _redact_json_value(detail or {}, max_chars=MAX_FINDING_CHARS)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM control_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise StateConflict(f"Unknown control run ID: {run_id}")
            if row["state"] != expected:
                raise StateConflict(
                    f"CAS failed: expected state {expected}, actual {row['state']}"
                )
            if expected_dispatch_token is not None and row["dispatch_token"] != expected_dispatch_token:
                raise StateConflict("Dispatch token mismatch on control-plane transition")
            if "last_completed_op" not in updates:
                updates["last_completed_op"] = action
            if "completed_ops_json" not in updates:
                ops = json.loads(row["completed_ops_json"] or "[]")
                eff_round = updates.get("round_num", row["in_flight_round"] or row["round_num"])
                ops.append({"op": action, "round_num": int(eff_round), "state": next_state})
                updates["completed_ops_json"] = json.dumps(ops[-40:], sort_keys=True)
            set_clauses = ["state=?", "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"]
            params: list[Any] = [next_state]
            for col, val in updates.items():
                if col in ("last_failure_sig", "cancel_reason", "recovery_reason", "next_action", "blocker", "last_completed_op") and isinstance(val, str):
                    val = _redact_signal_text(val, max_chars=MAX_FINDING_CHARS)
                set_clauses.append(f"{col}=?")
                params.append(val)
            params.extend([run_id, expected])
            where_sql = "run_id=? AND state=?"
            if expected_dispatch_token is not None:
                where_sql += " AND dispatch_token=?"
                params.append(expected_dispatch_token)
            upd = self.db.execute(
                f"UPDATE control_runs SET {', '.join(set_clauses)} WHERE {where_sql}",
                tuple(params),
            )
            if upd.rowcount != 1:
                raise StateConflict("CAS failed while transitioning control run")
            self.db.execute(
                """INSERT INTO control_events(
                       run_id, from_state, to_state, actor_role, action, dispatch_token, detail_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    expected,
                    next_state,
                    actor_role,
                    action,
                    expected_dispatch_token if expected_dispatch_token is not None else row["dispatch_token"],
                    json.dumps(safe_detail, sort_keys=True),
                ),
            )
            if round_record is not None:
                safe_selected = _redact_json_value(list(round_record.get("selected_ids", ())), max_chars=MAX_FINDING_CHARS)
                safe_evidence_refs = _redact_json_value(dict(round_record.get("evidence_refs") or {}), max_chars=MAX_FINDING_CHARS)
                safe_rubric = _redact_json_value(round_record.get("rubric") or {}, max_chars=MAX_FINDING_CHARS)
                safe_findings = _redact_json_value(list(round_record.get("findings") or ()), max_chars=MAX_FINDING_CHARS)
                safe_repair_scope = _redact_json_value(list(round_record.get("repair_scope") or ()), max_chars=MAX_FINDING_CHARS)
                rubric_hard_gate = round_record.get("rubric_hard_gate_passed")
                self.db.execute(
                    """INSERT INTO control_rounds(
                           run_id, round_num, maker_dispatched, confirming_pass,
                           outcome, verdict, source_sha, base_sha, candidate_sha256,
                           diff_sha256, policy_sha256, check_plan_sha256, selection_sha256,
                           agents_sha256, selected_ids_json, checks_summary_sha256,
                           manifest_sha256, auditor_report_sha256, evidence_refs_json,
                           host_checks_passed, checker_passed,
                           rubric_decision, rubric_total_score, rubric_hard_gate_passed,
                           rubric_json, findings_json, repair_scope_json,
                           next_action, failure_sig, wall_elapsed_s, cumulative_wall_s,
                           tokens_used, cost_used, consecutive_passes, no_progress_count
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        int(round_record["round_num"]),
                        1 if round_record.get("maker_dispatched", True) else 0,
                        1 if round_record.get("confirming_pass", False) else 0,
                        str(round_record["outcome"]),
                        str(round_record["verdict"]),
                        str(round_record.get("source_sha", "")),
                        str(round_record.get("base_sha", "")),
                        str(round_record.get("candidate_sha256", "")),
                        str(round_record.get("diff_sha256", "")),
                        str(round_record.get("policy_sha256", "")),
                        str(round_record.get("check_plan_sha256", "")),
                        str(round_record.get("selection_sha256", "")),
                        str(round_record.get("agents_sha256", "")),
                        json.dumps(safe_selected, sort_keys=True),
                        str(round_record.get("checks_summary_sha256", "")),
                        str(round_record.get("manifest_sha256", "")),
                        str(round_record.get("auditor_report_sha256", "")),
                        json.dumps(safe_evidence_refs, sort_keys=True),
                        1 if round_record.get("host_checks_passed") else 0,
                        1 if round_record.get("checker_passed") else 0,
                        str(round_record.get("rubric_decision", "NOT_VERIFIED")),
                        round_record.get("rubric_total_score"),
                        None if rubric_hard_gate is None else (1 if rubric_hard_gate else 0),
                        json.dumps(safe_rubric, sort_keys=True),
                        json.dumps(safe_findings, sort_keys=True),
                        json.dumps(safe_repair_scope, sort_keys=True),
                        _redact_signal_text(str(round_record.get("next_action", "")), max_chars=MAX_FINDING_CHARS),
                        _redact_signal_text(str(round_record.get("failure_sig", "")), max_chars=MAX_FINDING_CHARS),
                        float(round_record.get("wall_elapsed_s", 0.0)),
                        float(round_record.get("cumulative_wall_s", 0.0)),
                        round_record.get("tokens_used"),
                        round_record.get("cost_used"),
                        int(round_record.get("consecutive_passes", 0)),
                        int(round_record.get("no_progress_count", 0)),
                    ),
                )
            self.db.execute("COMMIT")
            return self.get_control_run(run_id)
        except sqlite3.IntegrityError as exc:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise StateConflict(f"Control-plane integrity conflict: {exc}") from exc
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def list_control_rounds(self, run_id: str) -> list[dict[str, Any]]:
        self.get_control_run(run_id)
        rows = self.db.execute(
            "SELECT * FROM control_rounds WHERE run_id=? ORDER BY round_num",
            (run_id,),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["maker_dispatched"] = bool(d["maker_dispatched"])
            d["confirming_pass"] = bool(d["confirming_pass"])
            d["host_checks_passed"] = bool(d["host_checks_passed"])
            d["checker_passed"] = bool(d["checker_passed"])
            if d["rubric_hard_gate_passed"] is not None:
                d["rubric_hard_gate_passed"] = bool(d["rubric_hard_gate_passed"])
            d["selected_ids"] = json.loads(d.pop("selected_ids_json"))
            d["evidence_refs"] = json.loads(d.pop("evidence_refs_json") or "{}")
            d["rubric"] = json.loads(d.pop("rubric_json"))
            d["findings"] = json.loads(d.pop("findings_json"))
            d["repair_scope"] = json.loads(d.pop("repair_scope_json"))
            out.append(d)
        return out

    def request_control_cancel(
        self,
        run_id: str,
        *,
        actor_role: str,
        reason: str = "Cancelled by operator",
    ) -> dict[str, Any]:
        run = self.get_control_run(run_id)
        if run["state"] == "CANCELLED":
            return run
        return self.transition_control_run(
            run_id,
            expected=run["state"],
            next_state="CANCELLED",
            actor_role=actor_role,
            action="cancel_run",
            clear_dispatch=True,
            update_fields={
                "cancel_requested": 1,
                "cancel_reason": _redact_signal_text(reason, max_chars=MAX_FINDING_CHARS),
                "recovery_reason": "cancelled_by_operator",
                "next_action": "Run cancelled; preserve worktree without reset",
            },
            detail={"reason": _redact_signal_text(reason, max_chars=MAX_FINDING_CHARS)},
        )

    def record_control_progress(
        self,
        run_id: str,
        *,
        expected_state: str,
        actor_role: str,
        op: str,
        expected_dispatch_token: str | None = None,
        wall_elapsed_delta_s: float = 0.0,
        tokens_delta: int | None = None,
        cost_delta: float | None = None,
        in_flight_round: int | None = None,
        candidate_sha256: str | None = None,
        last_diff_sha256: str | None = None,
        next_action: str | None = None,
        blocker: str | None = None,
        recovery_reason: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Atomically persist mid-round completed op, heartbeat, and elapsed budget under CAS."""
        safe_op = _redact_signal_text(op, max_chars=120)
        safe_detail = _redact_json_value(detail or {}, max_chars=MAX_FINDING_CHARS)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM control_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise StateConflict(f"Unknown control run ID: {run_id}")
            if row["state"] != expected_state:
                raise StateConflict(
                    f"CAS failed on progress update: expected {expected_state}, actual {row['state']}"
                )
            if expected_dispatch_token is not None and row["dispatch_token"] != expected_dispatch_token:
                raise StateConflict("Dispatch token mismatch on progress update")

            consumed = json.loads(row["budget_consumed_json"])
            consumed["wall_seconds"] = round(
                float(consumed.get("wall_seconds", 0.0)) + max(0.0, float(wall_elapsed_delta_s)), 3
            )
            if tokens_delta is not None:
                consumed["tokens_used"] = int(consumed.get("tokens_used") or 0) + int(tokens_delta)
            if cost_delta is not None:
                consumed["cost_usd"] = round(float(consumed.get("cost_usd") or 0.0) + float(cost_delta), 6)

            eff_round = int(in_flight_round) if in_flight_round is not None else int(row["in_flight_round"] or row["round_num"])
            ops = json.loads(row["completed_ops_json"] or "[]")
            ops.append({"op": safe_op, "round_num": eff_round, "state": expected_state})
            ops = ops[-40:]

            set_clauses = [
                "budget_consumed_json=?",
                "last_completed_op=?",
                "completed_ops_json=?",
                "in_flight_round=?",
                "lease_heartbeat_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')",
                "updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')",
            ]
            params: list[Any] = [
                json.dumps(consumed, sort_keys=True),
                safe_op,
                json.dumps(ops, sort_keys=True),
                eff_round,
            ]
            if candidate_sha256 is not None:
                set_clauses.append("candidate_sha256=?")
                params.append(candidate_sha256)
            if last_diff_sha256 is not None:
                set_clauses.append("last_diff_sha256=?")
                params.append(last_diff_sha256)
            if next_action is not None:
                set_clauses.append("next_action=?")
                params.append(_redact_signal_text(next_action, max_chars=MAX_FINDING_CHARS))
            if blocker is not None:
                set_clauses.append("blocker=?")
                params.append(_redact_signal_text(blocker, max_chars=MAX_FINDING_CHARS))
            if recovery_reason is not None:
                set_clauses.append("recovery_reason=?")
                params.append(_redact_signal_text(recovery_reason, max_chars=MAX_FINDING_CHARS))

            where_sql = "run_id=? AND state=?"
            params.extend([run_id, expected_state])
            if expected_dispatch_token is not None:
                where_sql += " AND dispatch_token=?"
                params.append(expected_dispatch_token)
            upd = self.db.execute(
                f"UPDATE control_runs SET {', '.join(set_clauses)} WHERE {where_sql}",
                tuple(params),
            )
            if upd.rowcount != 1:
                raise StateConflict("CAS failed while recording control progress")
            self.db.execute(
                """INSERT INTO control_events(
                       run_id, from_state, to_state, actor_role, action, dispatch_token, detail_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    expected_state,
                    expected_state,
                    actor_role,
                    safe_op,
                    expected_dispatch_token if expected_dispatch_token is not None else row["dispatch_token"],
                    json.dumps(safe_detail, sort_keys=True),
                ),
            )
            self.db.execute("COMMIT")
            return self.get_control_run(run_id)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise

    def record_control_event(
        self,
        run_id: str,
        *,
        expected_state: str,
        actor_role: str,
        action: str,
        recovery_reason: str | None = None,
        next_action: str | None = None,
        blocker: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a non-transition CAS audit/reconciliation event on a control run."""
        safe_action = _redact_signal_text(action, max_chars=120)
        safe_detail = _redact_json_value(detail or {}, max_chars=MAX_FINDING_CHARS)
        try:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM control_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                raise StateConflict(f"Unknown control run ID: {run_id}")
            if row["state"] != expected_state:
                raise StateConflict(
                    f"CAS failed on event: expected {expected_state}, actual {row['state']}"
                )
            set_clauses = ["updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')"]
            params: list[Any] = []
            if recovery_reason is not None:
                set_clauses.append("recovery_reason=?")
                params.append(_redact_signal_text(recovery_reason, max_chars=MAX_FINDING_CHARS))
            if next_action is not None:
                set_clauses.append("next_action=?")
                params.append(_redact_signal_text(next_action, max_chars=MAX_FINDING_CHARS))
            if blocker is not None:
                set_clauses.append("blocker=?")
                params.append(_redact_signal_text(blocker, max_chars=MAX_FINDING_CHARS))
            params.extend([run_id, expected_state])
            upd = self.db.execute(
                f"UPDATE control_runs SET {', '.join(set_clauses)} WHERE run_id=? AND state=?",
                tuple(params),
            )
            if upd.rowcount != 1:
                raise StateConflict("CAS failed while recording control event")
            self.db.execute(
                """INSERT INTO control_events(
                       run_id, from_state, to_state, actor_role, action, dispatch_token, detail_json
                   ) VALUES (?, ?, ?, ?, ?, '', ?)""",
                (run_id, expected_state, expected_state, actor_role, safe_action, json.dumps(safe_detail, sort_keys=True)),
            )
            self.db.execute("COMMIT")
            return self.get_control_run(run_id)
        except BaseException:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
