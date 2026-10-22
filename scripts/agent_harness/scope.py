"""Fail-closed Issue path-scope validator. No external Python dependencies."""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
from typing import Iterable

HEADER = re.compile(r"^#{2,6}\s+Target Directories \(allowed paths\)\s*$", re.I)
ITEM = re.compile(r"^\s*-\s+`([^`]+)`\s*(?:\([^)]*\))?\s*$")


def parse_allowed_paths(issue_body: str) -> tuple[str, ...]:
    """Extract only the first contiguous bullet list below the exact heading."""
    inside = False
    paths: list[str] = []
    for line in issue_body.splitlines():
        if not inside:
            if HEADER.match(line):
                inside = True
            continue
        if not line.strip() and not paths:
            continue
        m = ITEM.match(line)
        if not m:
            if paths:
                break
            raise ValueError("Scope heading must have an immediate backtick bullet list")
        value = m.group(1)
        if (not value or value.startswith("/") or "\\" in value or ".." in value.split("/")
                or any(ch in value for ch in "*?[]{}") or "//" in value
                or value.startswith("./") or value.strip() != value):
            raise ValueError(f"Unsafe Issue scope: {value!r}")
        normalized = pathlib.PurePosixPath(value.rstrip("/")).as_posix()
        if normalized in (".", ""):
            raise ValueError("Repository root is not a valid scope")
        paths.append(normalized + ("/" if value.endswith("/") else ""))
    if not paths:
        raise ValueError("Issue missing Target Directories (allowed paths)")
    return tuple(dict.fromkeys(paths))


def _git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            check=True, timeout=20)
    return result.stdout


def changed_paths(repo: pathlib.Path) -> tuple[str, ...]:
    """Track modified, deleted and untracked (nonignored) paths."""
    tracked = _git(repo, "diff", "--name-only", "--no-renames", "-z", "HEAD").split("\0")
    untracked = _git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    return tuple(sorted(set(p for p in tracked + untracked if p)))


def violations(repo: pathlib.Path, allowed: Iterable[str],
               paths: Iterable[str]) -> list[str]:
    root = repo.resolve()
    failures: list[str] = []
    for path in paths:
        pp = pathlib.PurePosixPath(path)
        if path.startswith("/") or "\\" in path or ".." in pp.parts:
            failures.append(f"unsafe path: {path}")
            continue
        candidate = root / path
        if any(p.is_symlink() for p in (candidate, *candidate.parents) if p != root and root in p.parents):
            failures.append(f"symlink escape/forbidden in changed path: {path}")
            continue
        if not candidate.resolve().is_relative_to(root):
            failures.append(f"symlink escape: {path}")
            continue
        if not any(path.startswith(a) if a.endswith("/") else path == a for a in allowed):
            failures.append(f"outside Issue scope: {path}")
    return failures


def assert_scoped(repo: pathlib.Path, issue_body: str) -> dict:
    scope = parse_allowed_paths(issue_body)
    changed = changed_paths(repo)
    problems = violations(repo, scope, changed)
    if problems:
        raise ValueError("; ".join(problems))
    return {"allowed": list(scope), "changed": list(changed), "scope_pass": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate changed paths against a GitHub Issue body")
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--issue-body", type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        result = assert_scoped(args.repo, args.issue_body.read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"scope_pass": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
