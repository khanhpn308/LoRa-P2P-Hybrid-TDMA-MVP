"""Host-only Draft PR preview. No GitHub writes and no trust in model PASS text.

Future publisher requires signed Host-run evidence and CI verified on exact commit.
This module intentionally does NOT offer an --apply switch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p1.worktrees import git, WorktreeError

SHA = re.compile(r"^[0-9a-f]{40}$")
BRANCH = re.compile(r"^(?:feature|fix|chore|research)/[0-9]+-[A-Za-z0-9_.-]+$")


class PublishingBlocked(RuntimeError):
    pass


def preview(repo: Path, *, branch: str, target_base: str,
            expected_sha: str, issue: int) -> dict:
    if not SHA.fullmatch(expected_sha):
        raise PublishingBlocked("A pinned 40-character final commit is required")
    if not BRANCH.fullmatch(branch) or issue < 1 or branch.split("/")[1].split("-")[0] != str(issue):
        raise PublishingBlocked("Branch is not an Issue-scoped feature branch")
    if target_base in ("main", "master") or not target_base:
        # Until P0 has been merged, use the reviewed P0 integration branch.
        raise PublishingBlocked("P1-B must target the current P0 integration branch")
    source = repo.resolve(strict=True)
    if git(source, "branch", "--show-current") != branch:
        raise PublishingBlocked("Current branch differs from PR source")
    if git(source, "rev-parse", "HEAD") != expected_sha:
        raise PublishingBlocked("HEAD differs from reviewed commit")
    if git(source, "status", "--porcelain", "--untracked-files=normal"):
        raise PublishingBlocked("Dirty worktree; evidence is not commit-bound")
    return {
        "status": "DRAFT_PR_PLAN_ONLY",
        "issue": issue, "head": branch, "base": target_base,
        "commit": expected_sha, "requires": [
            "separately verified GitHub CI at this exact SHA",
            "independent read-only AGY PASS with full file coverage",
            "Host-scoped evidence record and secret scan",
            "human security approval of PR publishing identity",
        ],
        "example_command_not_executed": [
            "gh", "pr", "create", "--draft", "--base", target_base,
            "--head", branch, "--title", f"feat(harness): Issue #{issue}",
            "--body", "Evidence required; no auto-merge",
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect planned P1 Draft PR without publishing")
    p.add_argument("--worktree", type=Path, required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--base", required=True)
    p.add_argument("--commit", required=True)
    p.add_argument("--issue", required=True, type=int)
    args = p.parse_args()
    try:
        print(json.dumps(preview(args.worktree, branch=args.branch,
                                 target_base=args.base, expected_sha=args.commit,
                                 issue=args.issue), indent=2))
        return 0
    except (WorktreeError, OSError, PublishingBlocked) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:250]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
