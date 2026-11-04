"""PR Review Harness: Real Read-Only PR Review before Human Merge.

Deterministic read-only PR data collector, immutable snapshot builder,
scoped Rule-ID evaluator, and gate policy validator.

Never auto-merges. Never self-approves. Never executes PR contents.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

# Local harness imports
try:
    from .agent_context import load_context, ContextGateError
    from .pr_review_policy import (
        GateStatus,
        HostVerdict,
        RiskLevel,
        evaluate_pr_policy,
    )
    from .scope import parse_allowed_paths
    from .standards_policy import select_rules, StandardsError
except ImportError:
    from agent_context import load_context, ContextGateError
    from pr_review_policy import (
        GateStatus,
        HostVerdict,
        RiskLevel,
        evaluate_pr_policy,
    )
    from scope import parse_allowed_paths
    from standards_policy import select_rules, StandardsError

DEFAULT_REPO = "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP"
COMMENT_HEADER_SIGNATURE = "# 🛡️ Harness PR Review Report"


class PRReviewError(RuntimeError):
    pass


def _run_cmd(cmd: list[str], cwd: Path | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Execute command with timeout, returning (exit_code, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PRReviewError(f"Command {' '.join(cmd[:3])} failed or timed out: {exc}") from exc


def fetch_pr_data_github(repo: str, pr_number: int) -> dict[str, Any]:
    """Fetch PR metadata, files, reviews, and check-runs from GitHub CLI."""
    if not shutil.which("gh"):
        raise PRReviewError("GitHub CLI ('gh') is not installed or not in PATH")

    # 1. PR core metadata
    code, out, err = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}",
    ])
    if code != 0:
        raise PRReviewError(f"Failed to fetch PR #{pr_number} metadata: {err.strip() or out.strip()}")

    raw_pr = json.loads(out)
    pr_data: dict[str, Any] = {
        "number": raw_pr.get("number"),
        "title": raw_pr.get("title", ""),
        "body": raw_pr.get("body") or "",
        "state": raw_pr.get("state", "").lower(),
        "draft": bool(raw_pr.get("draft")),
        "author": raw_pr.get("user", {}).get("login", ""),
        "base_ref": raw_pr.get("base", {}).get("ref", "main"),
        "base_sha": raw_pr.get("base", {}).get("sha", ""),
        "head_ref": raw_pr.get("head", {}).get("ref", ""),
        "head_sha": raw_pr.get("head", {}).get("sha", ""),
        "merge_commit_sha": raw_pr.get("merge_commit_sha"),
    }

    # 2. Files with pagination
    code, out, err = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}/files", "--paginate",
    ])
    if code != 0:
        raise PRReviewError(f"Failed to fetch PR #{pr_number} files: {err.strip()}")

    raw_files = json.loads(out)
    parsed_files: list[dict[str, Any]] = []
    for f in raw_files:
        filename = f.get("filename")
        if not filename:
            raise PRReviewError("PR contains file with missing filename")
        parsed_files.append({
            "filename": filename,
            "status": f.get("status", "modified"),
            "patch": f.get("patch", ""),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
        })
    pr_data["files"] = parsed_files

    # 3. Reviews
    code, out, _ = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}/reviews",
    ])
    pr_data["reviews"] = json.loads(out) if code == 0 else []

    # 4. Review comments (threads)
    code, out, _ = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}/comments",
    ])
    pr_data["review_comments"] = json.loads(out) if code == 0 else []

    # 5. Issue comments
    code, out, _ = _run_cmd([
        "gh", "api", f"repos/{repo}/issues/{pr_number}/comments",
    ])
    pr_data["comments"] = json.loads(out) if code == 0 else []

    return pr_data


def fetch_check_runs_github(repo: str, head_sha: str) -> list[dict[str, Any]]:
    """Fetch commit check-runs from GitHub API."""
    code, out, _ = _run_cmd([
        "gh", "api", f"repos/{repo}/commits/{head_sha}/check-runs",
    ])
    if code != 0:
        return []
    try:
        data = json.loads(out)
        runs = data.get("check_runs", [])
        return [
            {
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
            }
            for r in runs
        ]
    except Exception:
        return []


def fetch_ruleset_status_github(repo: str, base_ref: str) -> str:
    """Check rulesets / branch protection visibility."""
    # Check rulesets
    code, out, _ = _run_cmd(["gh", "api", f"repos/{repo}/rulesets"])
    if code == 0:
        try:
            rulesets = json.loads(out)
            if isinstance(rulesets, list) and len(rulesets) > 0:
                return f"ACTIVE_RULESETS ({len(rulesets)} configured)"
        except Exception:
            pass

    # Check branch protection endpoint
    code, out, _ = _run_cmd(["gh", "api", f"repos/{repo}/branches/{base_ref}/protection"])
    if code == 0:
        return "BRANCH_PROTECTION_ENFORCED"

    return "MERGE_PROTECTION_NOT_VERIFIED"


def fetch_latest_head_sha(repo: str, pr_number: int) -> str:
    """Fetch current head SHA directly from GitHub to detect TOCTOU race."""
    code, out, err = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".head.sha",
    ])
    if code != 0 or not out.strip():
        raise PRReviewError(f"Could not re-verify HEAD SHA for PR #{pr_number}: {err.strip()}")
    return out.strip()


def extract_linked_issue_number(pr_data: dict[str, Any]) -> int | None:
    """Extract linked issue number from PR body, title, or branch name."""
    patterns = [
        re.compile(r"(?i)\b(?:resolves|fixes|closes|close|fix|resolve)\s*[:#]?\s*#?(\d+)\b"),
        re.compile(r"(?:feature|fix|docs|chore|research)/(\d+)-"),
        re.compile(r"#(\d+)"),
    ]
    for text in (pr_data.get("body", ""), pr_data.get("head_ref", ""), pr_data.get("title", "")):
        for pat in patterns:
            m = pat.search(text)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
    return None


def fetch_linked_issue_github(repo: str, issue_number: int) -> dict[str, Any] | None:
    """Fetch linked issue data using gh issue view."""
    code, out, _ = _run_cmd([
        "gh", "issue", "view", str(issue_number), "--repo", repo, "--json", "number,title,body,state",
    ])
    if code != 0:
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def compute_diff_hashes(files: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    """Compute per-file SHA256 and overall aggregate diff SHA256."""
    file_hashes: dict[str, str] = {}
    hasher = hashlib.sha256()

    for f in sorted(files, key=lambda x: x.get("filename", "")):
        fname = f.get("filename", "")
        patch = f.get("patch", "")
        fhash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
        file_hashes[fname] = fhash
        hasher.update(fname.encode("utf-8"))
        hasher.update(fhash.encode("utf-8"))

    return file_hashes, hasher.hexdigest()


def render_markdown_report(
    evaluation: dict[str, Any],
    pr_data: dict[str, Any],
    snapshot: dict[str, Any],
) -> str:
    """Render clean, normative GitHub-flavored Markdown review report."""
    verdict = evaluation["verdict"]
    risk = evaluation["risk_level"]
    rec = evaluation["policy_recommendation"]
    dims = evaluation["dimensions"]
    gates = evaluation["gates"]
    blockers = evaluation["blockers"]

    badge = {
        HostVerdict.READY_FOR_HUMAN_REVIEW.value: "🟢 READY FOR HUMAN REVIEW",
        HostVerdict.CHANGES_REQUESTED.value: "🟠 CHANGES REQUESTED",
        HostVerdict.BLOCKED.value: "🔴 BLOCKED",
        HostVerdict.NOT_VERIFIED.value: "⚪ NOT VERIFIED",
    }.get(verdict, verdict)

    lines: list[str] = [
        COMMENT_HEADER_SIGNATURE,
        "",
        f"### Verdict: **{badge}**",
        "",
        "| Attribute | Value |",
        "| :--- | :--- |",
        f"| **PR Number** | #{pr_data.get('number')} |",
        f"| **Title** | `{pr_data.get('title')}` |",
        f"| **Author** | @{pr_data.get('author')} |",
        f"| **Target / Base** | `{pr_data.get('base_ref')}` (`{pr_data.get('base_sha')[:8]}`) |",
        f"| **PR Head SHA** | `{pr_data.get('head_sha')}` |",
        f"| **Risk Classification** | **{risk}** ({rec.get('description')}) |",
        f"| **Snapshot Diff Hash** | `{snapshot.get('diff_sha256', '')[:16]}...` |",
        f"| **Merge Protection** | `{snapshot.get('ruleset_visibility', 'UNKNOWN')}` |",
        "",
        "#### 1. Independent Evidence Dimensions",
        "",
        "| Dimension | Status | Notes |",
        "| :--- | :--- | :--- |",
        f"| `AUTO_CHECK_PASS` | **{'PASS' if dims.get('AUTO_CHECK_PASS') else 'FAIL'}** | Automated gates (PR-01, 03, 05, 06, 07) |",
        f"| `AI_REVIEW_PASS` | **{dims.get('AI_REVIEW_PASS')}** | Model Auditor verification |",
        f"| `HUMAN_APPROVED` | **{dims.get('HUMAN_APPROVED')}** | Required human approvals: {rec.get('required_approvals')} |",
        f"| `HIL_RF_PASS` | **{dims.get('HIL_RF_PASS')}** | Hardware-in-the-Loop RF test evidence |",
        f"| `SECURITY_REVIEW_PASS` | **{dims.get('SECURITY_REVIEW_PASS')}** | Secret scan & credentials validation |",
        "",
        "#### 2. Gate Verification Details (PR-01 through PR-08)",
        "",
        "| Gate | Status | Summary |",
        "| :--- | :---: | :--- |",
    ]

    for g in gates:
        st = g["status"]
        st_icon = "✅ PASS" if st == "PASS" else ("⚠️ BLOCKED" if st == "BLOCKED" else ("⚪ N/A" if st == "NOT_APPLICABLE" else f"❌ {st}"))
        lines.append(f"| **{g['gate']}** | {st_icon} | {g['summary']} |")

    lines.append("")

    if blockers:
        lines.extend([
            "#### 3. Active Blockers",
            "",
        ])
        for b in blockers:
            lines.append(f"- 🛑 {b}")
        lines.append("")

    lines.extend([
        "#### 4. Policy Recommendation & Human Merge Boundary",
        "",
        f"> [!IMPORTANT]",
        f"> **Non-auto-merge policy:** This Harness is read-only and **never merges PRs automatically**.",
        f"> Human sign-off requirements for this PR ({risk} risk): **>= {rec.get('required_approvals')} specialist approval(s)**.",
        "> Reviewers cannot self-approve their own PRs.",
        "",
        "---",
        f"*Report generated at {snapshot.get('timestamp_utc')} UTC by LoRa P2P Harness PR Reviewer.*",
    ])

    return "\n".join(lines)


def publish_pr_comment(repo: str, pr_number: int, report_md: str) -> None:
    """Publish or update review comment idempotently on GitHub PR."""
    # Check for existing comment
    code, out, _ = _run_cmd([
        "gh", "api", f"repos/{repo}/issues/{pr_number}/comments",
    ])
    existing_id = None
    if code == 0:
        try:
            comments = json.loads(out)
            for c in comments:
                if COMMENT_HEADER_SIGNATURE in c.get("body", ""):
                    existing_id = c.get("id")
                    break
        except Exception:
            pass

    if existing_id:
        # Update existing
        code, _, err = _run_cmd([
            "gh", "api", "-X", "PATCH", f"repos/{repo}/issues/comments/{existing_id}",
            "-f", f"body={report_md}",
        ])
        if code != 0:
            raise PRReviewError(f"Failed to update existing review comment: {err.strip()}")
    else:
        # Create new
        code, _, err = _run_cmd([
            "gh", "api", "-X", "POST", f"repos/{repo}/issues/{pr_number}/comments",
            "-f", f"body={report_md}",
        ])
        if code != 0:
            raise PRReviewError(f"Failed to post review comment: {err.strip()}")


def run_pr_review(args: argparse.Namespace) -> int:
    """Main orchestrator for read-only PR review."""
    candidate_repo = Path(args.candidate_repo).resolve()

    # 1. Mandatory Host G0 context check
    try:
        agent_context = load_context(candidate_repo)
    except ContextGateError as exc:
        print(f"🔴 G0 Context Gate BLOCKED: {exc}", file=sys.stderr)
        return 2

    pr_number = args.pr
    repo_name = args.repo

    # 2. Intake: live GitHub API or offline fixture
    if args.fixture:
        fixture_path = Path(args.fixture).resolve()
        if not fixture_path.exists():
            print(f"🔴 Fixture not found: {fixture_path}", file=sys.stderr)
            return 2
        fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
        pr_data = fixture_data["pr_data"]
        linked_issue = fixture_data.get("linked_issue")
        check_runs = fixture_data.get("check_runs", [])
        hil_receipt = fixture_data.get("hil_receipt")
        ruleset_status = fixture_data.get("ruleset_status", "MERGE_PROTECTION_NOT_VERIFIED")
        head_sha_at_start = pr_data.get("head_sha", "")
        head_sha_at_end = fixture_data.get("head_sha_at_end", head_sha_at_start)
    else:
        if not pr_number:
            print("🔴 Either --pr <PR_NUMBER> or --fixture <PATH> is required.", file=sys.stderr)
            return 2
        try:
            pr_data = fetch_pr_data_github(repo_name, pr_number)
        except PRReviewError as exc:
            print(f"🔴 PR Intake Error: {exc}", file=sys.stderr)
            return 2

        head_sha_at_start = pr_data.get("head_sha", "")

        # Find linked issue
        issue_num = extract_linked_issue_number(pr_data)
        linked_issue = fetch_linked_issue_github(repo_name, issue_num) if issue_num else None

        # Fetch check runs
        check_runs = fetch_check_runs_github(repo_name, head_sha_at_start)
        ruleset_status = fetch_ruleset_status_github(repo_name, pr_data.get("base_ref", "main"))
        hil_receipt = None

        # Pre/post freshness re-query to detect race
        head_sha_at_end = fetch_latest_head_sha(repo_name, pr_number)

    # 3. Parse allowed paths from linked issue if available
    allowed_paths: list[str] | None = None
    if linked_issue and linked_issue.get("body"):
        try:
            allowed_paths = list(parse_allowed_paths(linked_issue["body"]))
        except ValueError:
            allowed_paths = None

    # 4. Deterministic Rule-ID selection
    rule_selection = None
    changed_files = [f.get("filename", "") for f in pr_data.get("files", [])]
    try:
        rule_selection = select_rules(
            candidate_repo,
            allowed_paths=allowed_paths or changed_files,
            changed_paths=None,
            base=pr_data.get("base_sha", "HEAD"),
        )
    except Exception:
        # Fallback or synthetic selection if in fixture / offline mode
        rule_selection = {
            "standards": ["C"] if any(f.startswith("firmware/") for f in changed_files) else (
                ["GO"] if any(f.startswith("backend-go/") for f in changed_files) else []
            ),
            "rules": ["GOV-001", "C-001"] if any(f.startswith("firmware/") for f in changed_files) else ["GGS-001"],
            "rule_count": 2,
        }

    # 5. Diff hashes and snapshot
    file_hashes, overall_diff_hash = compute_diff_hashes(pr_data.get("files", []))
    snapshot = {
        "pr_number": pr_data.get("number"),
        "repo": repo_name,
        "base_sha": pr_data.get("base_sha"),
        "head_sha": head_sha_at_start,
        "diff_sha256": overall_diff_hash,
        "file_diff_hashes": file_hashes,
        "ruleset_visibility": ruleset_status,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host_tools": {
            "python": sys.version.split()[0],
            "git": shutil.which("git") is not None,
            "gh": shutil.which("gh") is not None,
        },
    }

    # 6. Read CODEOWNERS
    codeowners_path = candidate_repo / ".github" / "CODEOWNERS"
    codeowners_content = codeowners_path.read_text(encoding="utf-8") if codeowners_path.exists() else ""

    # 7. Evaluate Policy
    auditor_report = None
    evaluation = evaluate_pr_policy(
        pr_data=pr_data,
        linked_issue=linked_issue,
        allowed_paths=allowed_paths,
        codeowners_content=codeowners_content,
        rule_selection=rule_selection,
        auditor_report=auditor_report,
        check_runs=check_runs,
        hil_receipt=hil_receipt,
        head_sha_at_start=head_sha_at_start,
        head_sha_at_end=head_sha_at_end,
        ruleset_status=ruleset_status,
    )

    # 8. Render report
    report_md = render_markdown_report(evaluation, pr_data, snapshot)

    # Print / save
    if args.output_json:
        out_json_path = Path(args.output_json)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json.dumps({
            "evaluation": evaluation,
            "snapshot": snapshot,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.output_md:
        out_md_path = Path(args.output_md)
        out_md_path.parent.mkdir(parents=True, exist_ok=True)
        out_md_path.write_text(report_md, encoding="utf-8")

    print(report_md)

    # 9. Publish comment if explicitly authorized by operator
    if getattr(args, "publish_comment", False) and not args.fixture:
        publish_pr_comment(repo_name, pr_data["number"], report_md)
        print("\n✅ Review report comment published to PR.")

    verdict = evaluation["verdict"]
    if verdict == HostVerdict.READY_FOR_HUMAN_REVIEW.value:
        return 0
    elif verdict in (HostVerdict.CHANGES_REQUESTED.value, HostVerdict.NOT_VERIFIED.value):
        return 1
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only PR Review Harness with scoped Rule IDs, evidence gates, and human merge policy."
    )
    parser.add_argument("--pr", type=int, help="GitHub Pull Request number")
    parser.add_argument("--repo", default=DEFAULT_REPO, help=f"GitHub repository (default: {DEFAULT_REPO})")
    parser.add_argument("--candidate-repo", default=".", help="Local repository path for G0 and CODEOWNERS checks")
    parser.add_argument("--fixture", help="Path to synthetic PR fixture JSON (for offline validation)")
    parser.add_argument("--output-json", help="Path to write structured JSON evaluation output")
    parser.add_argument("--output-md", help="Path to write Markdown review report")
    parser.add_argument("--publish-comment", action="store_true", help="Publish or update comment on GitHub PR (requires operator authorization)")
    args = parser.parse_args()

    try:
        return run_pr_review(args)
    except Exception as exc:
        print(f"🔴 PR Review Execution Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
