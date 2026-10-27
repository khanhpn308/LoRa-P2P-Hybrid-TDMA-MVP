"""Create a nonprivileged, reviewable Host approval request from live P1 preflight.

This command/tool NEVER signs, executes or asks for root credentials.
The root signer treats the request as untrusted data, not authorization.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import uuid

from mcp_host import HarnessMCPHost
from mcp_approval import validate_request, canonical


class ApprovalRequestMaker:
    def __init__(self, host: HarnessMCPHost | None = None, directory: Path | None = None):
        self.host = host or HarnessMCPHost()
        self.directory = directory or (Path.home() / ".local/state/lora-harness/approval-requests")

    def _private_directory(self) -> Path:
        path = self.directory
        if path.is_symlink():
            raise ValueError("Approval request directory cannot be symlinked")
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = path.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError("Approval request directory must be user-owned mode 0700")
        return path

    def create(self, issue_number: int) -> dict:
        if isinstance(issue_number, bool) or not isinstance(issue_number, int) or not 1 <= issue_number <= 2_147_483_647:
            return {"status": "BLOCKED", "reason": "Invalid Issue number"}
        try:
            preflight = self.host.preflight(issue_number)
            if (preflight.get("state") != "PREFLIGHT_ONLY"
                    or preflight.get("issue") != issue_number):
                raise ValueError("Live Issue preflight rejected")
            record = validate_request({
                "version": 1,
                "repository": "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP",
                "issue": issue_number,
                "base_sha": preflight.get("source_sha"),
                "issue_sha256": preflight.get("issue_sha256"),
                "scope": preflight.get("approved_scope"),
            })
            directory = self._private_directory()
            path = directory / ("issue-%d-%s.json" % (issue_number, uuid.uuid4().hex))
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(canonical(record))
                    stream.flush()
                    os.fsync(stream.fileno())
            except BaseException:
                path.unlink(missing_ok=True)
                raise
            return {
                "status": "APPROVAL_REQUIRED",
                "issue": issue_number,
                "source_sha": record["base_sha"],
                "issue_sha256": record["issue_sha256"],
                "approved_scope": record["scope"],
                "request_file": str(path),
                "operator_command": "sudo /usr/bin/python3 /usr/local/sbin/lora-harness-approve approve --request " + str(path),
                "note": "Operator must independently inspect the Issue/scope before typing the signer confirmation. No root GitHub login.",
            }
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return {"status": "BLOCKED", "reason": type(exc).__name__ + ": approval request rejected"}
