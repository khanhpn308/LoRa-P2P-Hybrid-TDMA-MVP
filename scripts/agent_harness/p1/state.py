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
