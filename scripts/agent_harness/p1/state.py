"""SQLite journal for a single-issue, fail-closed firmware task.

It stores workflow metadata, never model credentials, shell output or source code.
SQLite is local Host state, NOT the application's PostgreSQL database.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

STATES = frozenset({
    "PLANNED", "PREPARING", "PREPARED", "RECOVERY_REQUIRED",
    "BLOCKED", "CANCELLED",
})


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
        """)

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
        return {
            "issue": row["issue"],
            "revision": row["revision"],
            "doc": json.loads(row["doc_json"]),
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def save_feature_snapshot(
        self,
        *,
        issue: int,
        expected_revision: int | None,
        revision: int,
        doc_json: str,
        units: list[dict[str, Any]],
        actor: str,
    ) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if expected_revision is None:
                self.db.execute(
                    """INSERT INTO feature_docs(issue, revision, doc_json, updated_by)
                       VALUES (?, ?, ?, ?)""",
                    (issue, revision, doc_json, actor),
                )
            else:
                upd = self.db.execute(
                    """UPDATE feature_docs
                       SET revision=?, doc_json=?, updated_by=?,
                           updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')
                       WHERE issue=? AND revision=?""",
                    (revision, doc_json, actor, issue, expected_revision),
                )
                if upd.rowcount != 1:
                    raise StateConflict("CAS failed: feature state revision conflict or missing issue")
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
                        json.dumps(evidence) if evidence is not None else None,
                        actor,
                    ),
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
