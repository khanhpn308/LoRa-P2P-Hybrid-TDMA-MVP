"""Local firmware Agent harness pilot. NOT a hardened unattended runner."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Any

from scope import assert_scoped, _git


def command(argv: list[str], cwd: pathlib.Path, timeout: int, input_text: str | None = None, stdout_limit: int = 80000) -> dict[str, Any]:
    try:
        result = subprocess.run(argv, cwd=cwd, input=input_text, text=True,
                                capture_output=True, timeout=timeout, check=False)
        return {"command": argv, "exit_code": result.returncode,
                "stdout": result.stdout[-stdout_limit:], "stderr": result.stderr[-20000:]}
    except subprocess.TimeoutExpired:
        return {"command": argv, "exit_code": None, "error": "TIMEOUT"}
    except OSError as exc:
        return {"command": argv, "exit_code": None, "error": str(exc)}


def run(args: argparse.Namespace) -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    evidence = repo / "artifacts" / "agent-harness" / f"issue-{args.issue}"
    evidence.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "issue": args.issue, "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "branch": "NOT_VERIFIED", "commit": "NOT_VERIFIED",
        "build": "NOT_VERIFIED", "auditor": "NOT_VERIFIED", "hil": "NOT_VERIFIED",
        "rf": "NOT_VERIFIED", "steps": [], "result": "BLOCKED",
    }

    def finish(status: str, code: int) -> int:
        record["result"] = status
        (evidence / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"HARNESS {status}: {evidence / 'manifest.json'}")
        return code

    try:
        branch = _git(repo, "branch", "--show-current").strip()
        head = _git(repo, "rev-parse", "HEAD").strip()
        record.update({"branch": branch, "commit": head})
        if not branch or branch in ("main", "master") or not branch.startswith(("feature/", "fix/", "chore/", "research/")):
            record["error"] = "Run only on an explicit non-main Issue branch"
            return finish("BLOCKED", 2)
        if _git(repo, "status", "--porcelain").strip():
            record["error"] = "Worktree must be clean before a new run"
            return finish("BLOCKED", 2)
    except subprocess.SubprocessError as exc:
        record["error"] = str(exc)
        return finish("BLOCKED", 2)

    if not shutil.which("gh"):
        record["error"] = "gh CLI missing"
        return finish("BLOCKED", 2)
    issue = command(["gh", "issue", "view", str(args.issue), "--json", "title,body",
                     "--jq", "."], repo, 45)
    if issue["exit_code"] != 0:
        record["error"] = "GitHub Issue lookup failed"
        record["steps"].append(issue)
        return finish("BLOCKED", 2)
    try:
        payload = json.loads(issue["stdout"])
        allowed = __import__("scope").parse_allowed_paths(payload["body"])
    except (ValueError, KeyError, TypeError) as exc:
        record["error"] = f"Invalid Issue scope: {exc}"
        return finish("BLOCKED", 2)
    record["allowed_paths"] = list(allowed)
    record["issue_title"] = payload["title"]
    if not args.execute:
        return finish("PREFLIGHT_ONLY", 0)

    for name in ("codex", "gemini", "idf.py"):
        if not shutil.which(name):
            record["error"] = f"Required executable unavailable: {name}"
            return finish("BLOCKED", 2)

    # Explicitly opt-in, pilot only; restrict the Worker with Codex workspace sandbox.
    worker_instructions = (repo / ".agent-harness" / "worker.md").read_text(encoding="utf-8")
    worker_prompt = (f"{worker_instructions}\n\nGitHub Issue #{args.issue}: {payload['title']}\n"
                     f"{payload['body']}\n\nAllowed paths: {allowed!r}\n"
                     "Implement within scope; do not commit, push, merge or flash.")
    worker = command(["codex", "--ask-for-approval", "never", "exec", "--sandbox",
                      "workspace-write", "-"], repo, args.max_seconds, worker_prompt)
    record["steps"].append({"stage": "worker", **worker})
    if worker["exit_code"] != 0:
        return finish("WORKER_FAILED", 3)

    try:
        checked = assert_scoped(repo, payload["body"])
        record["scope"] = checked
        if not checked["changed"]:
            record["error"] = "Worker changed no files"
            return finish("NO_CHANGES", 3)
        # Intent-to-add makes new in-scope sources appear in the real diff sent
        # to the auditor; never rely on a tracked-only diff for new source.
        untracked = [p for p in _git(repo, "ls-files", "--others",
                                   "--exclude-standard", "-z").split("\0") if p]
        if untracked:
            _git(repo, "add", "-N", "--", *untracked)
        _git(repo, "diff", "--check")
    except (ValueError, subprocess.SubprocessError) as exc:
        record["error"] = str(exc)
        return finish("SCOPE_FAILED", 3)

    tests = [
        (["python3", "scripts/verify_structure.py"], repo),
        (["python3", "-m", "unittest", "discover", "-s", "tests/agent_harness", "-v"], repo),
        (["idf.py", "build"], repo / "firmware" / "gateway_master"),
        (["idf.py", "build"], repo / "firmware" / "sensor_node"),
    ]
    for argv, cwd in tests:
        result = command(argv, cwd, args.max_seconds)
        record["steps"].append({"stage": "deterministic", **result})
        if result["exit_code"] != 0:
            return finish("CHECKS_FAILED", 4)
    record["build"] = "BUILD_VERIFIED_IN_LOCAL_WORKTREE_ONLY"

    diff = command(["git", "diff", "--no-ext-diff", "--binary", "HEAD"], repo, 30, stdout_limit=1000000)
    if diff["exit_code"] != 0:
        return finish("DIFF_FAILED", 4)
    # Include untracked file content in auditor input only through an explicit inventory.
    record["steps"].append({"stage": "diff_inventory", "changed": record["scope"]["changed"]})
    if len(diff["stdout"]) > 90000:
        record["error"] = "Diff exceeds audit context budget"
        return finish("AUDIT_INCONCLUSIVE", 5)
    auditor_rules = (repo / ".agent-harness" / "auditor.md").read_text(encoding="utf-8")
    audit_prompt = (f"{auditor_rules}\n\nIssue #{args.issue}: {payload['title']}\n"
                    f"Approved paths: {allowed!r}\n"
                    f"Changed inventory: {record['scope']['changed']!r}\n"
                    f"Diff (tracked files only):\n{diff['stdout']}\n"
                    "Untracked files, if any, have NOT been inspected: return INCONCLUSIVE. "
                    "Return only the JSON review object.")
    audit = command(["gemini", "--approval-mode=plan", "--output-format", "json",
                     "-p", audit_prompt], repo, args.max_seconds)
    record["steps"].append({"stage": "auditor", **audit})
    if audit["exit_code"] != 0:
        return finish("AUDIT_INCONCLUSIVE", 5)
    try:
        parsed = json.loads(audit["stdout"])
        review = json.loads(parsed["response"])
        record["auditor_report"] = review
        if review["status"] == "PASS" and review.get("findings") == []:
            record["auditor"] = "AUDIT_PASS_SOFTWARE_ONLY"
            return finish("READY_FOR_DRAFT_PR_AND_HUMAN_REVIEW", 0)
        record["auditor"] = review.get("status", "INCONCLUSIVE")
    except (ValueError, TypeError, KeyError) as exc:
        record["error"] = f"Auditor JSON invalid: {exc}"
    return finish("AUDIT_NOT_PASSED", 5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Firmware harness local pilot (no commit/push/merge)")
    parser.add_argument("--issue", type=int, required=True)
    parser.add_argument("--execute", action="store_true", help="Run agents/build on an isolated, authorized machine")
    parser.add_argument("--max-seconds", type=int, default=900)
    args = parser.parse_args()
    if args.issue < 1 or args.max_seconds < 30 or args.max_seconds > 3600:
        parser.error("Invalid issue or max-seconds (30..3600)")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
