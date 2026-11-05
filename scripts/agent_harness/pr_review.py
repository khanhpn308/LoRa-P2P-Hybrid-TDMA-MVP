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
    try:
        from .adapters import antigravity
    except ImportError:
        antigravity = None
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
    try:
        from adapters import antigravity
    except ImportError:
        antigravity = None

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
        "is_live": True,
    }

    # 2. Files with pagination and fail-closed checks
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
        status = f.get("status", "modified")
        if status not in ("added", "modified", "removed", "renamed"):
            raise PRReviewError(f"Unsupported git file status '{status}' for {filename}")
        parsed_files.append({
            "filename": filename,
            "status": status,
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
    code, out, _ = _run_cmd(["gh", "api", f"repos/{repo}/rulesets"])
    if code == 0:
        try:
            rulesets = json.loads(out)
            if isinstance(rulesets, list) and len(rulesets) > 0:
                return f"ACTIVE_RULESETS ({len(rulesets)} configured)"
        except Exception:
            pass

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


def fetch_latest_base_sha(repo: str, pr_number: int) -> str:
    """Fetch current base SHA directly from GitHub to detect base branch drift."""
    code, out, err = _run_cmd([
        "gh", "api", f"repos/{repo}/pulls/{pr_number}", "--jq", ".base.sha",
    ])
    if code != 0 or not out.strip():
        raise PRReviewError(f"Could not re-verify BASE SHA for PR #{pr_number}: {err.strip()}")
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


def validate_and_load_auditor_report(
    report_path: Path,
    pr_data: dict[str, Any],
    rule_selection: dict[str, Any] | None,
) -> dict[str, Any]:
    """Validate external Auditor report against schema and exact changed paths."""
    if not report_path.is_file():
        raise PRReviewError(f"Auditor report path not found: {report_path}")

    raw_text = report_path.read_text(encoding="utf-8")
    try:
        raw_report = json.loads(raw_text)
    except Exception as exc:
        raise PRReviewError(f"Auditor report is not valid JSON: {exc}") from exc

    if not isinstance(raw_report, dict):
        raise PRReviewError("Auditor report must be a JSON object")

    auditor_id = raw_report.get("auditor_id") or raw_report.get("agent_id")
    body = raw_report.get("report", raw_report)
    if isinstance(body, dict):
        auditor_id = auditor_id or body.get("auditor_id") or body.get("agent_id")
    else:
        raise PRReviewError("Auditor report body must be a JSON object")

    clean_body = {k: v for k, v in body.items() if k not in ("auditor_id", "agent_id")}
    required_paths = {f.get("filename", "") for f in pr_data.get("files", [])}

    if antigravity:
        try:
            req_rules = rule_selection.get("rules") if rule_selection else None
            if req_rules:
                sel_sha = rule_selection.get("selection_sha256")
                inv = raw_report.get("evidence_inventory") or (body.get("evidence_inventory") if isinstance(body, dict) else {}) or {}
                validated = antigravity.check_report(
                    clean_body,
                    required_paths=required_paths,
                    required_rules=req_rules,
                    selection_sha256=sel_sha,
                    evidence_inventory=inv,
                )
            elif "rule_results" in clean_body:
                sel_sha = rule_selection.get("selection_sha256") if rule_selection else clean_body.get("selection_sha256")
                inv = raw_report.get("evidence_inventory") or (body.get("evidence_inventory") if isinstance(body, dict) else {}) or {}
                validated = antigravity.check_report(
                    clean_body,
                    required_paths=required_paths,
                    required_rules=[],
                    selection_sha256=sel_sha,
                    evidence_inventory=inv,
                )
            else:
                validated = antigravity.check_report(
                    clean_body,
                    required_paths=required_paths,
                    required_rules=None,
                )
            if auditor_id:
                validated["auditor_id"] = auditor_id
            return validated
        except Exception as exc:
            # Return report with failure finding
            fail_report = {
                "status": "FAIL",
                "findings": [
                    {
                        "severity": "CRITICAL",
                        "file": "audit",
                        "line": 1,
                        "rule": "AUDIT-SCHEMA",
                        "explanation": f"Auditor report validation failed: {exc}",
                        "fix": "Re-run independent Auditor with matching scope.",
                    }
                ],
                "limitations": [f"Audit validation error: {exc}"],
                "reviewed_scope": list(required_paths),
            }
            if auditor_id:
                fail_report["auditor_id"] = auditor_id
            return fail_report

    if auditor_id and isinstance(clean_body, dict):
        clean_body["auditor_id"] = auditor_id
    return clean_body


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
        f"| `SECRET_SCAN_PASS` | **{dims.get('SECRET_SCAN_PASS')}** | Static diff credential & secret pattern scan |",
        f"| `SECURITY_REVIEW_PASS` | **{dims.get('SECURITY_REVIEW_PASS')}** | Independent security & cryptographic specialist review |",
        f"| `AI_REVIEW_PASS` | **{dims.get('AI_REVIEW_PASS')}** | Fresh read-only model Auditor verification |",
        f"| `HUMAN_APPROVED` | **{dims.get('HUMAN_APPROVED')}** | Required human approvals: {rec.get('required_approvals')} |",
        f"| `HIL_RF_PASS` | **{dims.get('HIL_RF_PASS')}** | Hardware-in-the-Loop RF test evidence |",
        f"| `MERGE_ENFORCEMENT_ACTIVE` | **{dims.get('MERGE_ENFORCEMENT_ACTIVE')}** | GitHub branch protection / ruleset enforcement |",
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
        f"> **Non-auto-merge policy:** This Harness is strictly read-only and **never merges PRs automatically**.",
        f"> `READY_FOR_HUMAN_REVIEW` indicates that automated gates passed and the PR is ready for human peer review.",
        f"> Human sign-off requirements for this PR ({risk} risk): **>= {rec.get('required_approvals')} specialist approval(s)**.",
        "> Reviewers cannot self-approve their own PRs.",
        "",
        "---",
        f"*Report generated at {snapshot.get('timestamp_utc')} UTC by LoRa P2P Harness PR Reviewer.*",
    ])

    return "\n".join(lines)


def publish_pr_comment(
    repo: str,
    pr_number: int,
    report_md: str,
    expected_head: str,
    expected_base: str,
) -> None:
    """Publish or update review comment idempotently on GitHub PR with TOCTOU check."""
    # Re-verify latest head and base SHA before posting
    current_head = fetch_latest_head_sha(repo, pr_number)
    current_base = fetch_latest_base_sha(repo, pr_number)
    if current_head != expected_head or current_base != expected_base:
        raise PRReviewError(
            f"Cannot publish review comment: PR base or head SHA changed (TOCTOU race detected! "
            f"expected {expected_head[:8]}/{expected_base[:8]}, current {current_head[:8]}/{current_base[:8]})"
        )

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
        code, _, err = _run_cmd([
            "gh", "api", "-X", "PATCH", f"repos/{repo}/issues/comments/{existing_id}",
            "-f", f"body={report_md}",
        ])
        if code != 0:
            raise PRReviewError(f"Failed to update existing review comment: {err.strip()}")
    else:
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
        load_context(candidate_repo)
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
        base_sha_at_start = pr_data.get("base_sha", "")
        base_sha_at_end = fixture_data.get("base_sha_at_end", base_sha_at_start)
        fixture_rule_selection = fixture_data.get("rule_selection")
        fixture_auditor_report = fixture_data.get("auditor_report")
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
        base_sha_at_start = pr_data.get("base_sha", "")

        # Find linked issue
        issue_num = extract_linked_issue_number(pr_data)
        linked_issue = fetch_linked_issue_github(repo_name, issue_num) if issue_num else None

        # Fetch check runs
        check_runs = fetch_check_runs_github(repo_name, head_sha_at_start)
        ruleset_status = fetch_ruleset_status_github(repo_name, pr_data.get("base_ref", "main"))
        hil_receipt = None
        fixture_rule_selection = None
        fixture_auditor_report = None

        # Pre/post freshness re-query to detect race
        head_sha_at_end = fetch_latest_head_sha(repo_name, pr_number)
        base_sha_at_end = fetch_latest_base_sha(repo_name, pr_number)

    # 3. Parse allowed paths from linked issue if available
    allowed_paths: list[str] | None = None
    if linked_issue and linked_issue.get("body"):
        try:
            allowed_paths = list(parse_allowed_paths(linked_issue["body"]))
        except ValueError:
            allowed_paths = None

    # 4. Deterministic Rule-ID selection (R-01: Fail-closed on errors, no fake injection!)
    changed_files = [f.get("filename", "") for f in pr_data.get("files", [])]
    has_c = any(f.startswith("firmware/") and (f.endswith(".c") or f.endswith(".h")) for f in changed_files)
    has_go = any(f.startswith("backend-go/") and f.endswith(".go") for f in changed_files)

    if args.fixture:
        if fixture_rule_selection:
            rule_selection = fixture_rule_selection
            rule_selection.setdefault("source", "fixture")
        else:
            standards = ["C"] if has_c else (["GO"] if has_go else ["DOCS"])
            rule_selection = {
                "source": "fixture",
                "standards": standards,
                "rules": ["C-001"] if has_c else (["GGS-001"] if has_go else []),
                "selected_ids": ["C-001"] if has_c else (["GGS-001"] if has_go else []),
                "rule_count": 1 if (has_c or has_go) else 0,
            }
    else:
        try:
            rule_selection = select_rules(
                candidate_repo,
                allowed_paths=allowed_paths or changed_files,
                changed_paths=None,
                base=pr_data.get("base_sha", "HEAD"),
            )
            rule_selection["source"] = "verified_host"
        except Exception as exc:
            rule_selection = {
                "status": "BLOCKED",
                "error": f"Deterministic Rule-ID selection failed: {exc}",
                "source": "verified_host",
                "selected_ids": [],
                "rules": [],
            }

    # 5. Auditor Report Intake (R-02)
    auditor_report = None
    if getattr(args, "auditor_report", None):
        auditor_report_path = Path(args.auditor_report).resolve()
        auditor_report = validate_and_load_auditor_report(auditor_report_path, pr_data, rule_selection)
    elif fixture_auditor_report:
        auditor_report = fixture_auditor_report

    # 6. Diff hashes and snapshot (R-05: Schema 1.0, bound base/head/diff/rules)
    file_hashes, overall_diff_hash = compute_diff_hashes(pr_data.get("files", []))
    snapshot = {
        "schema_version": "1.0",
        "pr_number": pr_data.get("number"),
        "repo": repo_name,
        "base_ref": pr_data.get("base_ref"),
        "base_sha": base_sha_at_start,
        "head_ref": pr_data.get("head_ref"),
        "head_sha": head_sha_at_start,
        "merge_commit_sha": pr_data.get("merge_commit_sha"),
        "diff_sha256": overall_diff_hash,
        "file_diff_hashes": file_hashes,
        "rule_selection_sha256": rule_selection.get("selection_sha256") if rule_selection else None,
        "ruleset_visibility": ruleset_status,
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host_tools": {
            "python": sys.version.split()[0],
            "git": shutil.which("git") is not None,
            "gh": shutil.which("gh") is not None,
        },
    }

    # 7. Read CODEOWNERS
    codeowners_path = candidate_repo / ".github" / "CODEOWNERS"
    codeowners_content = codeowners_path.read_text(encoding="utf-8") if codeowners_path.exists() else ""

    # 8. Evaluate Policy
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
        base_sha_at_start=base_sha_at_start,
        base_sha_at_end=base_sha_at_end,
    )

    # 9. Render report
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

    # 10. Publish comment if explicitly authorized by operator
    if getattr(args, "publish_comment", False) and not args.fixture:
        publish_pr_comment(
            repo_name,
            pr_data["number"],
            report_md,
            expected_head=head_sha_at_start,
            expected_base=base_sha_at_start,
        )
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
    parser.add_argument("--auditor-report", help="Path to external Auditor report JSON")
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
