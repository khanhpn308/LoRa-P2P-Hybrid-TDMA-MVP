"""Host-side bounded command supervisor for non-secret deterministic test jobs.

Model execution is NOT authorized by this module. A separate externally hardened,
network-restricted container/VM with scoped credentials is mandatory for Codex/AGY.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import signal
import subprocess
from dataclasses import dataclass

PROHIBITED = {"agy", "codex", "docker", "gh", "sudo", "su"}
MAX_CAPTURE = 20_000


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

    def json(self) -> dict:
        return vars(self)


def execute_checked(argv: list[str], cwd: pathlib.Path, *,
                    timeout: int = 30) -> Receipt:
    """No command shell, new process group, kill child processes on timeout."""
    if not argv or pathlib.Path(argv[0]).name in PROHIBITED:
        raise ProcessBlocked("Command is prohibited in trusted Host supervision")
    if timeout < 1 or timeout > 3600:
        raise ProcessBlocked("Invalid timeout")
    if not cwd.is_dir() or cwd.is_symlink():
        raise ProcessBlocked("Invalid workdir")
    # No secrets, home, SSH/GitHub tokens or credential-bearing environment.
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"}
    import time
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
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, err = proc.communicate()
        status = "TIMEOUT"
        code = None
    else:
        status = "EXIT_SUCCESS" if proc.returncode == 0 else "EXIT_FAILURE"
        code = proc.returncode
    combined = out + b"\n" + err
    # This caps *stored* output; do not use with untrusted high-volume jobs
    # without an external memory-limited runner.
    if len(combined) > MAX_CAPTURE:
        status = "OUTPUT_LIMIT_EXCEEDED"
    return Receipt(argv[0], code, status, round(time.monotonic()-start, 3),
                   hashlib.sha256(combined).hexdigest(), len(combined))
