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
from feature_state import session_start, session_checkpoint, session_close, FeatureStateError
from observability import ObservabilityError, diagnose_failures, query_signals, redact_data
from orchestrator import (
    ControlPlaneError,
    admit_run,
    build_run_policy,
    cancel_run,
    probe_role_capabilities,
)

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
    prep.add_argument("--state", type=Path, default=None,
                      help="Local Host SQLite journal, outside source worktree by default")
    status = sub.add_parser("status")
    status.add_argument("--run-id", default=None)
    status.add_argument("--issue", type=int, default=None)
    status.add_argument("--source", type=Path, default=Path.cwd())
    status.add_argument("--state", type=Path, default=None)
    recover = sub.add_parser("recover")
    recover.add_argument("--run-id", required=True)
    recover.add_argument("--source", type=Path, default=Path.cwd())
    recover.add_argument("--state", type=Path, default=None)
    resume = sub.add_parser("resume")
    resume.add_argument("--issue", type=int, required=True)
    resume.add_argument("--repo", type=Path, default=Path.cwd())
    resume.add_argument("--state", type=Path, default=None)
    resume.add_argument("--feature-file", type=Path, default=None)
    resume.add_argument("--offline", action="store_true")
    ckpt = sub.add_parser("checkpoint")
    ckpt.add_argument("--issue", type=int, required=True)
    ckpt.add_argument("--repo", type=Path, default=Path.cwd())
    ckpt.add_argument("--state", type=Path, default=None)
    ckpt.add_argument("--next-action", required=True)
    ckpt.add_argument("--blocker", default="")
    ckpt.add_argument("--export", type=Path, default=None)
    close_p = sub.add_parser("close")
    close_p.add_argument("--issue", type=int, required=True)
    close_p.add_argument("--repo", type=Path, default=Path.cwd())
    close_p.add_argument("--state", type=Path, default=None)
    close_p.add_argument("--next-action", required=True)
    close_p.add_argument("--blocker", default="")
    close_p.add_argument("--evidence-dir", type=Path, default=None)
    close_p.add_argument("--export", type=Path, default=None)
    close_p.add_argument("--cleanup-path", type=Path, action="append", default=[])
    close_p.add_argument("--allowed-temp-root", type=Path, action="append", default=[])
    sig_p = sub.add_parser("signals")
    sig_p.add_argument("--issue", type=int, default=None)
    sig_p.add_argument("--run-id", default=None)
    sig_p.add_argument("--domain", default=None)
    sig_p.add_argument("--status", default=None)
    sig_p.add_argument("--source", type=Path, default=Path.cwd())
    sig_p.add_argument("--state", type=Path, default=None)
    sig_p.add_argument("--limit", type=int, default=50)
    sig_p.add_argument("--diagnose", action="store_true")
    adm_p = sub.add_parser("admit", help="P08-A control-plane admission with frozen policy")
    adm_p.add_argument("--issue", type=int, required=True)
    adm_p.add_argument("--repo", type=Path, default=Path.cwd())
    adm_p.add_argument("--state", type=Path, default=None)
    adm_p.add_argument("--base-sha", default=None)
    adm_p.add_argument("--approved-by", default="")
    adm_p.add_argument("--supervised-issue-open", action="store_true")
    adm_p.add_argument("--max-rounds", type=int, default=1)
    adm_p.add_argument("--consecutive-passes", type=int, default=1)
    adm_p.add_argument("--max-wall-seconds", type=int, default=1800)
    adm_p.add_argument("--no-progress-threshold", type=int, default=2)
    adm_p.add_argument("--require-token-budget", action="store_true")
    adm_p.add_argument("--require-cost-budget", action="store_true")
    adm_p.add_argument("--maker-provider", default="auto")
    adm_p.add_argument("--checker-provider", default="auto")
    can_p = sub.add_parser("cancel", help="Cancel active P08-A control-plane run safely")
    can_p.add_argument("--run-id", required=True)
    can_p.add_argument("--source", type=Path, default=Path.cwd())
    can_p.add_argument("--state", type=Path, default=None)
    can_p.add_argument("--requested-by", default="owner")
    can_p.add_argument("--reason", default="Cancelled by operator")
    cap_p = sub.add_parser("capabilities", help="Probe role/provider capabilities")
    cap_p.add_argument("--source", type=Path, default=Path.cwd())
    cap_p.add_argument("--maker-provider", default="auto")
    cap_p.add_argument("--checker-provider", default="auto")
    args = parser.parse_args()
    if getattr(args, "issue", None) is not None and args.issue < 1:
        parser.error("Issue must be positive")
    os.umask(0o077)
    source = (getattr(args, "source", None) or getattr(args, "repo", None) or Path.cwd()).resolve()
    state = getattr(args, "state", None) or (source.parent / ".lora-p1-state" / "state.sqlite")
    try:
        if args.command == "prepare":
            data = plan_payload(source, args.issue, run_id=uuid.uuid4().hex)
            item = data["worktree_plan"]
            if args.expected_base_sha is not None and item.base_sha != args.expected_base_sha:
                raise PreflightError("Actual source HEAD does not match approved base SHA")
            preview = {"state": "PREFLIGHT_ONLY", "issue": args.issue,
                       "run_id": data["run_id"], "source_sha": item.base_sha,
                       "issue_sha256": data["issue_sha"],
                       "branch": item.branch, "worktree": str(item.target),
                       "approved_scope": list(data["scope"])}
            if not args.apply:
                print(json.dumps(preview, indent=2))
                return 0
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
                journal.record_checkpoint(
                    issue=args.issue,
                    run_id=data["run_id"],
                    revision_sha=item.base_sha,
                    candidate_sha256="",
                    branch=item.branch,
                    worktree_rel=f"worktree:{item.target.name}",
                    active_unit=None,
                    blocker="",
                    next_action="Begin or resume Issue execution in prepared worktree",
                    decision_refs=("OD-02", "OD-08"),
                    issue_sha256=data["issue_sha"],
                    handoff_json=json.dumps({
                        "issue": args.issue,
                        "branch": item.branch,
                        "source_sha": item.base_sha,
                        "next_action": "Begin or resume Issue execution in prepared worktree",
                    }, sort_keys=True),
                )
                preview["state"] = "PREPARED"
                print(json.dumps(preview, indent=2))
                return 0
        if args.command == "resume":
            res = session_start(
                issue=args.issue,
                repo=args.repo,
                state_db=state,
                feature_file=args.feature_file,
                offline=args.offline,
            )
            print(json.dumps(res, indent=2))
            return 2 if res["status"] in ("BLOCKED", "RECOVERY_REQUIRED") else 0
        if args.command == "checkpoint":
            res = session_checkpoint(
                issue=args.issue,
                repo=args.repo,
                state_db=state,
                next_action=args.next_action,
                blocker=args.blocker,
                export_path=args.export,
            )
            print(json.dumps(res, indent=2))
            return 0
        if args.command == "close":
            res = session_close(
                issue=args.issue,
                repo=args.repo,
                state_db=state,
                next_action=args.next_action,
                blocker=args.blocker,
                evidence_dir=args.evidence_dir,
                export_path=args.export,
                cleanup_paths=args.cleanup_path or None,
                allowed_temp_roots=args.allowed_temp_root or None,
            )
            print(json.dumps(res, indent=2))
            return 0
        if args.command == "signals":
            if args.diagnose:
                res = diagnose_failures(state, issue=args.issue, run_id=args.run_id, limit=args.limit)
            else:
                sigs = query_signals(
                    state,
                    issue=args.issue,
                    run_id=args.run_id,
                    owning_domain=args.domain,
                    status=args.status,
                    limit=args.limit,
                )
                res = {"count": len(sigs), "signals": sigs}
            print(json.dumps(res, indent=2))
            return 0
        if args.command == "capabilities":
            res = probe_role_capabilities(
                maker_provider=args.maker_provider,
                checker_provider=args.checker_provider,
                require_executable=False,
            )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0
        if args.command == "admit":
            approval = (
                {"status": "OWNER_APPROVED", "approved_by": args.approved_by, "isolated_pilot_attested": True}
                if args.approved_by.strip()
                else (
                    {"status": "SUPERVISED_ISSUE_OPEN", "isolated_pilot_attested": True}
                    if args.supervised_issue_open
                    else None
                )
            )
            pol = build_run_policy(
                consecutive_passes_required=args.consecutive_passes,
                max_rounds=args.max_rounds,
                max_wall_seconds=args.max_wall_seconds,
                no_progress_threshold=args.no_progress_threshold,
                require_token_budget=args.require_token_budget,
                require_cost_budget=args.require_cost_budget,
                approved_by=args.approved_by,
            )
            res = admit_run(
                repo=args.repo,
                issue=args.issue,
                journal_path=state,
                base_sha=args.base_sha,
                approval=approval,
                policy=pol,
                maker_provider=args.maker_provider,
                checker_provider=args.checker_provider,
            )
            print(json.dumps(redact_data(res), indent=2, sort_keys=True))
            return 0
        if args.command == "cancel":
            res = cancel_run(
                journal_path=state,
                run_id=args.run_id,
                requested_by=args.requested_by,
                reason=args.reason,
            )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0
        with Journal(state) as journal:
            if args.command == "recover":
                changed = journal.detect_interruption(args.run_id)
                print(json.dumps({"run_id": args.run_id,
                                  "marked_recovery": changed,
                                  "state": journal.get(args.run_id)["state"]}, indent=2))
                return 0
            if args.run_id:
                item = journal.get(args.run_id)
            elif args.issue is not None:
                item = journal.active_job_for_issue(args.issue) or journal.latest_job_for_issue(args.issue)
                if item is None:
                    raise StateConflict("No job found for Issue")
            else:
                raise PreflightError("status requires --run-id or --issue")
            ckpt_row = journal.latest_checkpoint(item["issue"])
            ctrl_row = journal.latest_control_run_for_issue(item["issue"])
            out_payload = {
                "run_id": item["run_id"],
                "issue": item["issue"],
                "state": item["state"],
                "source_sha": item["source_sha"],
                "branch": item["branch"],
                "worktree": item["worktree"],
                "history": journal.events(item["run_id"]),
                "latest_checkpoint": ckpt_row["handoff"] if ckpt_row else None,
            }
            if ctrl_row is not None:
                out_payload["control_run"] = {
                    "run_id": ctrl_row["run_id"],
                    "state": ctrl_row["state"],
                    "round_num": ctrl_row["round_num"],
                    "consecutive_passes": ctrl_row["consecutive_passes"],
                    "policy_sha256": ctrl_row["policy_sha256"],
                    "rounds": journal.list_control_rounds(ctrl_row["run_id"]),
                }
            print(json.dumps(out_payload, indent=2))
            return 0
    except (OSError, PreflightError, WorktreeError, StateConflict, FeatureStateError, ObservabilityError, ControlPlaneError, subprocess.SubprocessError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)[:240]}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
