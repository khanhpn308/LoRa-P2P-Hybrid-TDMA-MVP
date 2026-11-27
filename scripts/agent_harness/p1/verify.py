"""Host-owned P1-B candidate verification; no Agent execution or GitHub mutation.

The receipt proves a bounded scope/secret precheck, NOT build/audit/HIL/RF PASS.
It is invalid if the worktree changes after receipt collection.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
from typing import Any

try:
    from ..scope import violations
except ImportError:
    from scope import violations

from .state import Journal
from .worktrees import git, WorktreeError

SHA = re.compile(r"^[0-9a-f]{40}$")
SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    rb"|(?:ghp_|gho_|ghs_|github_pat_)[A-Za-z0-9_]{12,}"
    rb"|sk-(?:proj-)?[A-Za-z0-9_-]{18,}"
    rb"|AIza[0-9A-Za-z_-]{28,}"
    rb"|(?i:password|api[_-]?key|access[_-]?token)\s*[:=]\s*"
    rb"['\"]?[A-Za-z0-9_-]{20,}",
)
MAX_FILES = 80
MAX_FILE_BYTES = 120_000
MAX_DIFF_BYTES = 90_000


class VerificationBlocked(RuntimeError):
    """Cannot assert that an untrusted candidate stays within approved scope."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _paths(repo: pathlib.Path) -> list[str]:
    tracked = git(repo, "diff", "--no-renames", "--name-only", "-z", "HEAD").split("\0")
    extra = git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return sorted(set(p for p in tracked + extra if p))


def verify_candidate(journal: Journal, run_id: str) -> dict[str, Any]:
    item = journal.get(run_id)
    if item["state"] != "PREPARED":
        raise VerificationBlocked("Job is not PREPARED")
    worktree = pathlib.Path(item["worktree"])
    if worktree.is_symlink() or not worktree.is_dir():
        raise VerificationBlocked("Missing or symlink worktree")
    root = worktree.resolve(strict=True)
    try:
        if pathlib.Path(git(root, "rev-parse", "--show-toplevel")) != root:
            raise VerificationBlocked("Git root changed")
        if git(root, "rev-parse", "HEAD") != item["source_sha"]:
            raise VerificationBlocked("Source SHA changed without Host approval")
        if git(root, "branch", "--show-current") != item["branch"]:
            raise VerificationBlocked("Issue branch changed")
        listing = git(root, "worktree", "list", "--porcelain")
        if ("worktree " + str(root)) not in listing.splitlines():
            raise VerificationBlocked("Not a registered Git worktree")
        allowed = tuple(json.loads(item["scope_json"]))
        changed = _paths(root)
        if not changed:
            raise VerificationBlocked("No candidate changes")
        if len(changed) > MAX_FILES:
            raise VerificationBlocked("Candidate exceeds changed file budget")
        problems = violations(root, allowed, changed)
        if problems:
            raise VerificationBlocked("; ".join(problems)[:300])
        hashes: dict[str, str | None] = {}
        total = 0
        for name in changed:
            file = root / name
            if not file.exists():
                hashes[name] = None  # Deleted tracked file.
                continue
            if not file.is_file() or file.is_symlink():
                raise VerificationBlocked("Symlink/nonregular changed file")
            data = file.read_bytes()
            total += len(data)
            if (len(data) > MAX_FILE_BYTES or b"\0" in data
                    or SECRET.search(data)):
                raise VerificationBlocked("Binary, oversized or suspected secret in changed files")
            hashes[name] = sha(data)
        if total > 1_000_000:
            raise VerificationBlocked("Candidate source exceeds evidence budget")
        diff = git(root, "diff", "--no-ext-diff", "--no-renames", "HEAD")
        if (len(diff.encode()) > MAX_DIFF_BYTES or "Binary files " in diff
                or "GIT binary patch" in diff):
            raise VerificationBlocked("Non-auditable diff; split Issue or request human review")
    except (OSError, ValueError, WorktreeError, json.JSONDecodeError) as exc:
        raise VerificationBlocked("Candidate verification failed: " + str(exc)[:200]) from exc
    # Diff and untracked source are both represented; raw secrets never enter receipt.
    tracked_diff_sha = sha(diff.encode())
    cand_fingerprint = sha(
        json.dumps(
            {
                "base_sha": item["source_sha"],
                "branch": item["branch"],
                "files_sha256": hashes,
                "tracked_diff_sha256": tracked_diff_sha,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    return {
        "status": "SCOPE_SCAN_PASS_ONLY",
        "issue": item["issue"], "run_id": run_id, "base_sha": item["source_sha"],
        "branch": item["branch"], "paths": changed, "files_sha256": hashes,
        "tracked_diff_sha256": tracked_diff_sha, "candidate_sha256": cand_fingerprint,
        "changed_file_count": len(changed),
        "build": "NOT_VERIFIED", "audit": "NOT_VERIFIED",
        "hil": "NOT_VERIFIED", "rf": "NOT_VERIFIED",
    }
