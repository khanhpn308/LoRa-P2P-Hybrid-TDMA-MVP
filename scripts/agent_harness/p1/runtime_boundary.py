"""Host-owned process policy for credential-free firmware verification.

This is NOT an unattended model runtime; Codex/AGY need separately authorized
provider access and egress controls. Never mount personal auth or Docker socket.
"""
from __future__ import annotations

import os
import pathlib
import re
from dataclasses import dataclass

ID = re.compile(r"^sha256:[0-9a-f]{64}$")


class BoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class BuildBoundary:
    image_id: str

    def command(self, worktree: pathlib.Path, target: str) -> list[str]:
        if not ID.fullmatch(self.image_id):
            raise BoundaryError("Only an inspected local Docker image ID is allowed")
        if target not in {"gateway_master", "sensor_node"}:
            raise BoundaryError("Only approved ESP-IDF firmware build targets are allowed")
        if not worktree.is_dir() or worktree.is_symlink():
            raise BoundaryError("Invalid worktree")
        root = worktree.resolve(strict=True)
        if os.name != "posix" or not hasattr(os, "getuid"):
            raise BoundaryError("Runner requires a supported POSIX host")
        return [
            "docker", "run", "--rm", "--pull=never", "--network=none",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=256", "--memory=6g", "--cpus=2", "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=1g",
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--env", "HOME=/tmp",
            "--mount", f"type=bind,src={root},dst=/workspace",
            "--workdir", f"/workspace/firmware/{target}",
            self.image_id, "idf.py", "build",
        ]


def deny_model_execution_in_build_boundary(program: str) -> None:
    if program in ("agy", "codex"):
        raise BoundaryError("Models cannot run in the no-network build sandbox")
