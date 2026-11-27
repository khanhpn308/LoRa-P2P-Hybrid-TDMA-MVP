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
        ref = subprocess.run(
            ["git", "-C", str(repo), "show-ref", "--verify", "--quiet",
             "refs/heads/" + branch],
            text=True, capture_output=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorktreeError("Cannot safely inspect existing Git branch") from exc
    if ref.returncode == 0:
        raise WorktreeError("Generated branch already exists")
    if ref.returncode != 1:
        raise WorktreeError("Git branch lookup failed; refusing to create worktree")
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


def cleanup_owned_worktree(plan: WorktreePlan) -> bool:
    """Safely remove ONLY an untouched worktree owned by this exact WorktreePlan.

    Refuses symlinks, dirty worktrees, unowned branches, or diverged HEADs so
    user/concurrent worktrees are never affected.
    """
    parent = (plan.source.resolve() / ".." / ".lora-p1-worktrees" / plan.source.resolve().name).resolve()
    if plan.target.is_symlink():
        raise WorktreeError("Refusing to remove symlinked worktree target")
    if not plan.target.exists():
        return False
    resolved_target = plan.target.resolve(strict=True)
    if resolved_target.parent != parent:
        raise WorktreeError("Refusing cleanup outside owned .lora-p1-worktrees namespace")
    if BRANCH.fullmatch(plan.branch) is None:
        raise WorktreeError("Invalid owned branch identity")
    if git(resolved_target, "branch", "--show-current") != plan.branch:
        raise WorktreeError("Worktree branch mismatch; refusing cleanup")
    if git(resolved_target, "rev-parse", "HEAD") != plan.base_sha:
        raise WorktreeError("Worktree has commits beyond base SHA; refusing cleanup")
    if git(resolved_target, "status", "--porcelain", "--untracked-files=all"):
        raise WorktreeError("Worktree has uncommitted/untracked changes; preserving work")
    git(plan.source, "worktree", "remove", str(resolved_target))
    git(plan.source, "branch", "-d", plan.branch)
    return True


def inspect_worktree(
    worktree: pathlib.Path,
    *,
    expected_branch: str | None = None,
    expected_base_sha: str | None = None,
) -> dict[str, object]:
    """Read-only verification of an isolated Git worktree for safe session resume.

    Never modifies, resets, stashes, or deletes worktree contents.
    """
    if worktree.is_symlink() or not worktree.exists() or not worktree.is_dir():
        raise WorktreeError("Missing or symlink worktree")
    root = worktree.resolve(strict=True)
    top = git(root, "rev-parse", "--show-toplevel")
    if pathlib.Path(top) != root:
        raise WorktreeError("Worktree path is not a Git top-level root")
    listing = git(root, "worktree", "list", "--porcelain")
    if ("worktree " + str(root)) not in listing.splitlines():
        raise WorktreeError("Path is not a registered Git worktree")
    branch = git(root, "branch", "--show-current")
    head_sha = git(root, "rev-parse", "HEAD")
    porcelain = git(root, "status", "--porcelain", "--untracked-files=normal")
    dirty_paths = [line[3:] for line in porcelain.splitlines() if len(line) > 3]
    if expected_branch is not None and branch != expected_branch:
        raise WorktreeError(f"Worktree branch mismatch: expected {expected_branch!r}, got {branch!r}")
    base_is_ancestor = None
    if expected_base_sha is not None:
        if SHA.fullmatch(expected_base_sha) is None:
            raise WorktreeError("Invalid expected_base_sha")
        anc = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", expected_base_sha, head_sha],
            text=True, capture_output=True, check=False, timeout=20,
        )
        if anc.returncode not in (0, 1):
            raise WorktreeError("Failed to verify base SHA ancestry")
        base_is_ancestor = (anc.returncode == 0)
    return {
        "worktree": str(root),
        "branch": branch,
        "head_sha": head_sha,
        "expected_base_sha": expected_base_sha,
        "base_matches_head": (head_sha == expected_base_sha) if expected_base_sha else None,
        "base_is_ancestor": base_is_ancestor,
        "dirty": bool(porcelain),
        "dirty_paths": dirty_paths,
    }
