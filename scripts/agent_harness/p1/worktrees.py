"""Create per-Issue git worktrees; never remove existing trees or force-delete branches."""
from __future__ import annotations

import pathlib
import re
import subprocess
from dataclasses import dataclass

BRANCH = re.compile(r"^feature/([1-9][0-9]*)-agent-([0-9a-f]{8})$")
SHA = re.compile(r"^[a-f0-9]{40}$")


class WorktreeError(RuntimeError):
    pass


def git(repo: pathlib.Path, *args: str, timeout: int = 30) -> str:
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           check=False, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeError("git command unavailable or timed out") from exc
    if p.returncode:
        # Git output can contain remote user data or local paths; do not relay it.
        raise WorktreeError(f"git {args[0]} failed with exit {p.returncode}")
    return p.stdout.strip()


@dataclass(frozen=True)
class WorktreePlan:
    source: pathlib.Path
    target: pathlib.Path
    branch: str
    base_sha: str
    issue: int

    def command(self) -> list[str]:
        return ["git", "-C", str(self.source), "worktree", "add",
                "-b", self.branch, str(self.target), self.base_sha]


def make_plan(source: pathlib.Path, issue: int, run_id: str) -> WorktreePlan:
    repo = source.resolve(strict=True)
    if git(repo, "rev-parse", "--show-toplevel") != str(repo):
        raise WorktreeError("Source must be the root of an actual Git worktree")
    if git(repo, "status", "--porcelain", "--untracked-files=normal"):
        raise WorktreeError("Source Git worktree must be clean")
    sha = git(repo, "rev-parse", "--verify", "HEAD")
    if SHA.fullmatch(sha) is None:
        raise WorktreeError("Invalid source commit SHA")
    if not isinstance(issue, int) or issue < 1 or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise WorktreeError("Invalid issue or random run ID")
    branch = f"feature/{issue}-agent-{run_id[:8]}"
    if BRANCH.fullmatch(branch) is None:
        raise WorktreeError("Invalid generated branch name")
    # Dedicated sibling of source: no writes to main or current repository.
    parent = repo.parent / ".lora-p1-worktrees"
    if parent.is_symlink():
        raise WorktreeError("Worktree parent must not be a symlink")
    target = parent / repo.name / f"issue-{issue}-{run_id[:8]}"
    if target.exists() or target.is_symlink():
        raise WorktreeError("Worktree target already exists")
    try:
        git(repo, "show-ref", "--verify", "--quiet", "refs/heads/" + branch)
    except WorktreeError:
        pass  # --quiet exits 1 if the ref does not exist; verify the target anyway.
    else:
        raise WorktreeError("Generated branch already exists")
    return WorktreePlan(repo, target, branch, sha, issue)


def prepare(plan: WorktreePlan) -> None:
    if plan.target.exists() or plan.target.is_symlink():
        raise WorktreeError("Refusing to overwrite an existing worktree")
    root = plan.target.parent
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink():
        raise WorktreeError("Worktree root became a symlink")
    try:
        p = subprocess.run(plan.command(), text=True, capture_output=True,
                           check=False, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeError("Worktree creation interrupted; manual inspection required") from exc
    if p.returncode:
        raise WorktreeError(f"git worktree add failed: exit {p.returncode}")
    if git(plan.target, "rev-parse", "HEAD") != plan.base_sha:
        raise WorktreeError("New worktree is not at the pinned source commit")
    if git(plan.target, "branch", "--show-current") != plan.branch:
        raise WorktreeError("New worktree branch identity mismatch")
    if git(plan.target, "status", "--porcelain", "--untracked-files=normal"):
        raise WorktreeError("New worktree is unexpectedly dirty")
