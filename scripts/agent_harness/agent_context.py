"""Fail-closed loader for the exact tracked AGENTS.md used in agent prompts.

This verifies bytes read by a Host, NOT that an LLM comprehended instructions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys


MAX_AGENTS_BYTES = 65536
HEX_SHA = re.compile(r"^[0-9a-f]{40,64}$")


class ContextGateError(RuntimeError):
    """Mandatory repository instruction input could not be verified."""


def _git(root: Path, *args: str) -> str:
    try:
        done = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", "-C", str(root), *args],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ContextGateError("Git unavailable or timed out") from exc
    if done.returncode or len(done.stdout) > 2048:
        raise ContextGateError("Cannot verify Git source identity")
    return done.stdout.decode("utf-8", errors="strict").strip()


def load_context(repo: Path) -> dict:
    """Return exact, bounded HEAD-tracked instructions as verified prompt input.

    The Host must insert 'agent_input' into the *actual* Worker/Auditor
    request. Merely obtaining a hash does not enforce model behavior.
    """
    try:
        root = Path(repo).resolve(strict=True)
        path = root / "AGENTS.md"
        if not root.is_dir() or path.is_symlink():
            raise ContextGateError("Repository or AGENTS.md is unsafe")
        st = path.lstat()
        if not stat.S_ISREG(st.st_mode) or not (0 < st.st_size <= MAX_AGENTS_BYTES):
            raise ContextGateError("AGENTS.md missing, empty or oversized")
        data = path.read_bytes()
        if len(data) != st.st_size or b"\x00" in data:
            raise ContextGateError("AGENTS.md changed or has nontext data")
        text = data.decode("utf-8", errors="strict")
        if not text.strip():
            raise ContextGateError("AGENTS.md is empty")
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve(strict=True)
        if top != root:
            raise ContextGateError("Repository root mismatch")
        commit = _git(root, "rev-parse", "--verify", "HEAD")
        expected_blob = _git(root, "rev-parse", "--verify", "HEAD:AGENTS.md")
        actual_blob = _git(root, "hash-object", "--no-filters", "--", str(path))
        if (not HEX_SHA.fullmatch(commit) or
                not HEX_SHA.fullmatch(expected_blob) or
                actual_blob != expected_blob):
            raise ContextGateError("AGENTS.md differs from HEAD; do not run Worker")
        # Detect in-place changes between initial read and verified prompt use.
        if path.read_bytes() != data:
            raise ContextGateError("AGENTS.md changed during context preflight")
        h = hashlib.sha256(data).hexdigest()
        formatted = ("===== BEGIN REQUIRED TRUSTED AGENTS.md =====\n"
                     + text + "\n===== END REQUIRED TRUSTED AGENTS.md =====\n"
                     + "AGENTS_SHA256=" + h + "\n")
        return {
            "status": "HOST_CONTEXT_LOADED",
            "source_sha": commit,
            "git_blob_sha": expected_blob,
            "agents_sha256": h,
            "agents_bytes": len(data),
            "agent_input": formatted,
        }
    except ContextGateError:
        raise
    except (OSError, UnicodeError, ValueError) as exc:
        raise ContextGateError("AGENTS.md cannot be verified") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-sha256", default=None)
    args = parser.parse_args(argv)
    try:
        source = load_context(args.repo)
        if args.expected_sha256 is not None and args.expected_sha256 != source["agents_sha256"]:
            raise ContextGateError("AGENTS.md SHA-256 does not match supplied expectation")
        print(json.dumps(source, ensure_ascii=False))
        return 0
    except ContextGateError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
