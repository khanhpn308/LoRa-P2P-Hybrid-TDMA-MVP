"""Narrow, source-pinned, read-mostly adapter for existing P1 Host CLIs.

P0: NO write/execute/agent invocation tools are exposed to MCP clients.
CLI status and candidate validation may update external SQLite WAL metadata.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_STDOUT = 65536


class HarnessMCPHost:
    """All file/executable locations are fixed by the installed server, never by MCP input."""

    def __init__(self, source: Path | None = None) -> None:
        self.source = (source or Path(__file__).resolve().parents[2]).resolve(strict=True)
        self.scripts = self.source / "scripts" / "agent_harness" / "p1"
        self.state = self.source.parent / ".lora-p1-state" / "state.sqlite"

    @staticmethod
    def _blocked(reason: str) -> dict[str, Any]:
        return {"status": "BLOCKED", "reason": reason}

    def _run(self, script: str, args: list[str], *, timeout: int) -> dict[str, Any]:
        script_path = self.scripts / script
        if not script_path.is_file() or script_path.is_symlink():
            return self._blocked("Trusted Host script unavailable")
        cmd = [sys.executable, str(script_path), *args]
        try:
            result = subprocess.run(
                cmd, cwd=self.source, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout, check=False,
            )
        except subprocess.TimeoutExpired:
            return self._blocked("Host command timed out")
        except OSError:
            return self._blocked("Trusted Host command unavailable")
        if len(result.stdout) > _MAX_STDOUT:
            return self._blocked("Host receipt exceeds size limit")
        try:
            payload = json.loads(result.stdout.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._blocked("Host output is not bounded JSON")
        if not isinstance(payload, dict):
            return self._blocked("Host receipt must be an object")
        if result.returncode != 0:
            return self._blocked("Host rejected request (exit %d)" % result.returncode)
        return payload

    def preflight(self, issue_number: int) -> dict[str, Any]:
        """Dry-run P1 issue preflight. No worktree, journal, build or model calls."""
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or not 1 <= issue_number <= 2_147_483_647:
            return self._blocked("Invalid GitHub issue number")
        return self._run("cli.py", ["prepare", "--issue", str(issue_number),
                                    "--source", str(self.source)], timeout=100)

    def _journal_available(self) -> bool:
        return (self.state.is_file() and not self.state.is_symlink()
                and not self.state.parent.is_symlink())

    def status(self, run_id: str) -> dict[str, Any]:
        """Inspect a known Host run; no new job or worktree is created."""
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            return self._blocked("Invalid Host run ID")
        if not self._journal_available():
            return self._blocked("Existing Host journal required")
        return self._run("cli.py", ["status", "--run-id", run_id,
                                    "--source", str(self.source),
                                    "--state", str(self.state)], timeout=40)

    def verify_candidate(self, run_id: str) -> dict[str, Any]:
        """Check current candidate's allowed paths and hashes; NOT an E2E PASS."""
        if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
            return self._blocked("Invalid Host run ID")
        if not self._journal_available():
            return self._blocked("Existing Host journal required")
        return self._run("host_gate.py", ["--run-id", run_id,
                                          "--state", str(self.state)], timeout=70)
