"""P1-A safe preparation CLI: dry-run default; no Agent execution or GitHub mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from p1.state import Journal, StateConflict
from p1.worktrees import WorktreeError, make_plan, prepare, git
from scope import parse_allowed_paths

REPO = "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP"


class PreflightError(RuntimeError):
    pass


def issue_info(source: Path, issue: int) -> dict:
    try:
        p = subprocess.run(
            ["gh", "issue", "view", str(issue), "--repo", REPO, "--json", "title,body,state"],
            cwd=source, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=40, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PreflightError("Cannot query GitHub Issue") from exc
    if p.returncode or len(p.stdout) > 55_000:
        raise PreflightError("GitHub Issue lookup failed or exceeded limit")
    try:
        data = json.loads(p.stdout)
        if not isinstance(data, dict) or data.get("state") != "OPEN":
            raise PreflightError("Issue is not OPEN")
        if not isinstance(data.get("body"), str):
            raise PreflightError("Issue body missing")
        scope = parse_allowed_paths(data["body"])
    except (ValueError, TypeError) as exc:
        raise PreflightError("Malformed Issue or missing strict scope") from exc
    return {"title": str(data.get("title", ""))[:180], "body": data["body"],
            "scope": scope}


def plan_payload(source: Path, issue: int, *, run_id: str) -> dict:
    plan = make_plan(source, issue, run_id)
    data = issue_info(source, issue)
    issue_hash = hashlib.sha256(data["body"].encode("utf-8")).hexdigest()
    return {"run_id": run_id, "issue": issue, "title": data["title"],
            "issue_sha": issue_hash, "scope": data["scope"], "worktree_plan": plan}


def main() -> int:
    parser = argparse.ArgumentParser(description="P1-A: preflight/prepare worktree without invoking AI")
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--issue", type=int, required=True)
    prep.add_argument("--source", type=Path, default=Path.cwd())
    prep.add_argument("--apply", action="store_true", help="Create SQLite record + git worktree")
    prep.add_argument("--expected-base-sha", default=None,
                      help="Optional 40-character approved HEAD pin; blocks if source changed")
    prep.add_argument("--expected-issue-sha256", default=None,
                      help="Pinned Issue body; required for signed MCP approvals")
    prep.add_argument("--state", type=Path, default=None,
                      help="Local Host SQLite journal, outside source worktree by default")
    status = sub.add_parser("status")
    status.add_argument("--run-id", required=True)
    status.add_argument("--source", type=Path, default=Path.cwd())
    status.add_argument("--state", type=Path, default=None)
    recover = sub.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--source", type=Path, default=Path.cwd())
    recover.add_argument("--state", type=Path, default=None)
    args = parser.parse_args()
    if getattr(args, "issue", 1) < 1:
        parser.error("Issue must be positive")
    os.umask(0o077)
    source = args.source.resolve()
    state = args.state or (source.parent / ".lora-p1-state" / "state.sqlite")
    try:
        if args.command == "prepare":
            data = plan_payload(source, args.issue, run_id=uuid.uuid4().hex)
            item = data["worktree_plan"]
            if args.expected_base_sha is not None and item.base_sha != args.expected_base_sha:
                raise PreflightError("Actual source HEAD does not match approved base SHA")
            if (args.expected_issue_sha256 is not None
                    and data["issue_sha"] != args.expected_issue_sha256):
                raise PreflightError("Issue body changed since explicit approval")
            preview = {"state": "PREFLIGHT_ONLY", "issue": args.issue,
                       "run_id": data["run_id"], "source_sha": item.base_sha,
                       "issue_sha256": data["issue_sha"],
                       "branch": item.branch, "worktree": str(item.target),
                       "approved_scope": list(data["scope"])}
            if not args.apply:
                print(json.dumps(preview, indent=2))
                return 0
            # Re-read the live Issue immediately before the first local mutation.
            # The remote GitHub API is not transactionally lockable by this client;
            # changes after this check still require a manual stale-Issue stop.
            fresh = issue_info(source, args.issue)
            if (hashlib.sha256(fresh["body"].encode("utf-8")).hexdigest() != data["issue_sha"]
                    or fresh["scope"] != data["scope"]):
                raise PreflightError("Issue changed immediately before preparation")
            with Journal(state) as journal:
                journal.plan(run_id=data["run_id"], issue=args.issue,
                             source_sha=item.base_sha, issue_sha=data["issue_sha"],
                             branch=item.branch, worktree=item.target,
                             scope=data["scope"])
                journal.transition(data["run_id"], expected="PLANNED",
                                   next_state="PREPARING", note="Preparing Git worktree")
                try:
                    prepare(item)
                except WorktreeError as exc:
                    journal.transition(data["run_id"], expected="PREPARING",
                                       next_state="RECOVERY_REQUIRED",
                                       note="Manual recovery required after git worktree add")
                    raise PreflightError(str(exc)) from exc
                journal.transition(data["run_id"], expected="PREPARING",
                                   next_state="PREPARED", note="Verified branch, SHA and clean tree")
                preview["state"] = "PREPARED"
                print(json.dumps(preview, indent=2))
                return 0
        with Journal(state) as journal:
            if args.command == "recover":
                changed = journal.detect_interruption(args.run_id)
                print(json.dumps({"run_id": args.run_id,
                                  "marked_recovery": changed,
                                  "state": journal.get(args.run_id)["state"]}, indent=2))
                return 0
            item = journal.get(args.run_id)
            print(json.dumps({"run_id": item["run_id"], "issue": item["issue"],
                              "state": item["state"], "source_sha": item["source_sha"],
                              "branch": item["branch"], "worktree": item["worktree"],
                              "history": journal.events(args.run_id)}, indent=2))
            return 0
    except (OSError, PreflightError, WorktreeError, StateConflict, subprocess.SubprocessError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)[:240]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
