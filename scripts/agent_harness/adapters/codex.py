"""Codex CLI Worker adapter. Workspace sandbox does not replace a disposable VM."""
from __future__ import annotations

import subprocess
from pathlib import Path


class WorkerError(RuntimeError):
    pass


def invoke(prompt: str, worktree: Path, timeout: int) -> dict:
    args = ["codex", "exec", "--sandbox", "workspace-write",
            "--ask-for-approval", "never", "-"]
    try:
        result = subprocess.run(
            args, cwd=worktree, input=prompt, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkerError(f"codex unavailable or timed out: {type(exc).__name__}") from exc
    if result.returncode:
        raise WorkerError(f"codex exited {result.returncode}")
    return {"exit_code": result.returncode, "stdout_bytes": len(result.stdout.encode()),
            "stderr_bytes": len(result.stderr.encode())}
