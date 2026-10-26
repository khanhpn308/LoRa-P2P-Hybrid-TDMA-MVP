"""Daemon-aware, fail-closed Docker lifecycle for disposable ESP-IDF builds.

MCP accepts NO container ID, label, command or host path from a model. The
supervisor is called with a verified Host run ID and a temporary firmware copy.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import stat
import time

from mcp_host import bounded_run

_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CID = re.compile(r"[0-9a-f]{64}\Z")
_RUN = re.compile(r"[0-9a-f]{32}\Z")
_APPS = ("gateway_master", "sensor_node")


class DockerLifecycle:
    def __init__(self, *, docker: str = "/usr/bin/docker"):
        # Fixed trusted binary; never use model-controlled executable or shell.
        self.docker = docker
        if self.docker != "/usr/bin/docker":
            raise ValueError("Unreviewed Docker executable")

    def _call(self, argv: list[str], *, timeout=35):
        return bounded_run([self.docker, *argv], Path("/"), timeout=timeout,
                           limit=65536, env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"})

    def _list(self, label: str) -> set[str]:
        result = self._call(["ps", "-aq", "--no-trunc", "--filter", f"label={label}"])
        if result.returncode != 0:
            raise ValueError("Cannot query Docker daemon for owned containers")
        ids = result.stdout.decode("ascii", "strict").split()
        if any(not _CID.fullmatch(v) for v in ids) or len(ids) > 4:
            raise ValueError("Unexpected Docker label query result")
        return set(ids)

    def _cleanup(self, label: str, cidfile: Path) -> dict:
        """Kill daemon-owned containers, even if their docker CLI process was killed."""
        seen = set()
        if cidfile.is_symlink():
            raise ValueError("Container ID file is a symlink")
        if cidfile.is_file():
            value = cidfile.read_text().strip()
            if not _CID.fullmatch(value):
                raise ValueError("Invalid daemon container ID receipt")
            seen.add(value)
        for _ in range(3):
            active = self._list(label)
            seen.update(active)
            for cid in active:
                response = self._call(["rm", "-f", cid], timeout=30)
                if response.returncode != 0:
                    raise ValueError("Daemon refused container cleanup")
            # Verify that none remain under the unique run/app label.
            if not self._list(label):
                for cid in seen:
                    check = self._call(["container", "inspect", cid], timeout=20)
                    if check.returncode == 0:
                        raise ValueError("Container still exists after cleanup")
                return {"cleanup_verified": True, "containers_seen": len(seen)}
            time.sleep(.3)
        raise ValueError("Docker container cleanup not verified")

    def build(self, *, run_id: str, app: str, image_id: str,
              scratch: Path, evidence: Path, command_runner) -> dict:
        if (not isinstance(run_id, str) or not _RUN.fullmatch(run_id)
                or app not in _APPS or not isinstance(image_id, str)
                or not _SHA.fullmatch(image_id)):
            raise ValueError("Invalid pinned Docker build arguments")
        base = scratch / "firmware"
        appdir = base / app
        if (not appdir.is_dir() or appdir.is_symlink()
                or scratch.resolve() != scratch
                or base.resolve() != base):
            raise ValueError("Untrusted disposable build input")
        cidfile = evidence / (app + ".cid")
        if cidfile.exists() or cidfile.is_symlink():
            raise ValueError("Container ID receipt must not exist before run")
        label = "lora.harness.run=" + run_id + "-" + app
        argv = [
            self.docker, "run", "--rm", "--pull=never", "--network=none",
            "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges", "--pids-limit=256",
            "--memory=6g", "--cpus=2", "--user=%d:%d" % (os.getuid(), os.getgid()),
            "--label", label, "--cidfile", str(cidfile),
            "--tmpfs=/tmp:rw,nosuid,size=1024m",
            "--mount", "type=bind,src=%s,dst=/workspace/firmware" % base,
            "--workdir=/workspace/firmware/" + app,
            image_id, "idf.py", "build",
        ]
        # Build tool manages bounded stdout and POSIX process group of Docker
        # client; Docker daemon container is separately supervised here.
        try:
            receipt = command_runner(argv, evidence / (app + ".log"), 1800)
        finally:
            # On ANY exception or timeout, cleanup remains mandatory.
            cleanup = self._cleanup(label, cidfile)
        if receipt.get("exit_code") != 0 or not cleanup["cleanup_verified"]:
            raise ValueError("Docker build failed or cleanup not verified")
        receipt.update(cleanup)
        receipt["image_id"] = image_id
        receipt["app"] = app
        return receipt
