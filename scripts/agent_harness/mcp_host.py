"""Narrow, source-pinned, read-mostly adapter for existing P1 Host CLIs.

P0: NO write/execute/agent invocation tools are exposed to MCP clients.
CLI status and candidate validation may update external SQLite WAL metadata.
"""
from __future__ import annotations

import json
import re
import os
import selectors
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAX_STDOUT = 65536


def bounded_run(argv: list[str], cwd: Path, *, timeout: float,
                limit: int = _MAX_STDOUT, log=None, env=None) -> subprocess.CompletedProcess:
    """Bound both pipes while running; always reap the POSIX process group.

    Only trusted fixed argv may call this helper. It is not a sandbox for a
    process that can escape its session, or a daemon-owned Docker container.
    """
    if os.name != "posix" or not 0 < timeout <= 1800 or not 0 < limit <= 50_000_000:
        raise ValueError("Unsupported process bounds")
    start = time.monotonic()
    output = bytearray()
    total = 0
    proc = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, env=env)
    try:
        with selectors.DefaultSelector() as selector:
            for stream in (proc.stdout, proc.stderr):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ)
            while selector.get_map():
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv[0], timeout)
                for key, _ in selector.select(min(remaining, 0.05)):
                    chunk = os.read(key.fd, min(65536, limit - total + 1))
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = limit - total
                    kept = chunk[:available]
                    if log is not None:
                        log.write(kept)
                    elif key.fileobj is proc.stdout:
                        output.extend(kept)
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("Host process output limit exceeded")
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv[0], timeout)
            code = proc.wait(timeout=remaining)
        return subprocess.CompletedProcess(argv, code, bytes(output), b"")
    finally:
        # Also remove background children after a successful leader exit.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        finally:
            proc.stdout.close()
            proc.stderr.close()
            proc.wait(timeout=5)


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
        if (script not in {"cli.py", "host_gate.py"} or not script_path.is_file()
                or script_path.is_symlink() or self.scripts.is_symlink()
                or script_path.resolve() != script_path):
            return self._blocked("Trusted Host script unavailable")
        cmd = [sys.executable, str(script_path), *args]
        try:
            result = bounded_run(cmd, self.source, timeout=timeout)
        except subprocess.TimeoutExpired:
            return self._blocked("Host command timed out")
        except (OSError, ValueError):
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
        try:
            parent = self.state.parent.stat(follow_symlinks=False)
            file = self.state.stat(follow_symlinks=False)
            return (stat.S_ISDIR(parent.st_mode) and stat.S_ISREG(file.st_mode)
                    and self.state.resolve() == self.state
                    and parent.st_uid == file.st_uid == os.getuid()
                    and not (parent.st_mode & 0o077 or file.st_mode & 0o077))
        except OSError:
            return False

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
