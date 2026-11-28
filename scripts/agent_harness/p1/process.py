"""Host-side bounded command supervisor for non-secret deterministic test jobs.

This P1-B1 module allows ONLY benign test-fixture binaries (true/false/sleep).
Model execution is NOT authorized. A separate externally hardened,
network-restricted container/VM with scoped credentials is mandatory for Codex/AGY.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import os
import pathlib
import re
import signal
import subprocess
from dataclasses import dataclass

# P1-B1 tests only: arbitrary Host shell/Python/model commands are forbidden.
# Expand only when execution is moved behind an externally isolated runner.
SAFE_FIXTURES = {"true", "false", "sleep"}
MAX_CAPTURE = 20_000
EXECUTION_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class ProcessBlocked(RuntimeError):
    pass


@dataclass(frozen=True)
class Receipt:
    command: str
    exit_code: int | None
    status: str
    duration_s: float
    output_sha256: str
    output_bytes: int
    execution_id: str | None = None
    started_at: str = ""
    ended_at: str = ""

    def json(self) -> dict:
        return vars(self)


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def execute_checked(argv: list[str], cwd: pathlib.Path, *,
                    timeout: int = 30,
                    execution_id: str | None = None) -> Receipt:
    """No command shell, new process group, kill child processes on timeout or cancel."""
    if not argv or pathlib.Path(argv[0]).name not in SAFE_FIXTURES:
        raise ProcessBlocked("Only test fixture commands are permitted on Host in P1-B1")
    if timeout < 1 or timeout > 3600:
        raise ProcessBlocked("Invalid timeout")
    if execution_id is not None and (
        not isinstance(execution_id, str) or EXECUTION_ID.fullmatch(execution_id) is None
    ):
        raise ProcessBlocked("Invalid execution identity")
    if not cwd.is_dir() or cwd.is_symlink():
        raise ProcessBlocked("Invalid workdir")
    # No secrets, home, SSH/GitHub tokens or credential-bearing environment.
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}
    import time
    started_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv, cwd=cwd, env=env, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise ProcessBlocked(f"Process cannot start: {type(exc).__name__}") from exc
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        # Children belong to a dedicated process group on POSIX.
        _kill_process_group(proc.pid)
        out, err = proc.communicate()
        status = "TIMEOUT"
        code = None
    except BaseException:
        # Cancellation / KeyboardInterrupt cleanup without affecting other executions.
        if proc.poll() is None:
            _kill_process_group(proc.pid)
            proc.communicate()
        raise
    else:
        status = "EXIT_SUCCESS" if proc.returncode == 0 else "EXIT_FAILURE"
        code = proc.returncode
    ended_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    combined = out + b"\n" + err
    # This caps *stored* output; do not use with untrusted high-volume jobs
    # without an external memory-limited runner.
    if len(combined) > MAX_CAPTURE:
        status = "OUTPUT_LIMIT_EXCEEDED"
    return Receipt(argv[0], code, status, round(time.monotonic()-start, 3),
                   hashlib.sha256(combined).hexdigest(), len(combined),
                   execution_id=execution_id, started_at=started_at, ended_at=ended_at)
