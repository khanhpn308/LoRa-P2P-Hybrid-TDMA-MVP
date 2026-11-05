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
import tempfile
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
MAX_BATCH_DIFF_BYTES = 60_000
SHA_COMMIT_REGEX = re.compile(r"^[0-9a-f]{7,64}$")
SHA256_REGEX = re.compile(r"^[0-9a-f]{64}$")
HUNK_HEADER_REGEX = re.compile(r"(?m)^@@\s+-[0-9]+(?:,[0-9]+)?\s+\+[0-9]+(?:,[0-9]+)?\s+@@.*$")


def extract_diff_hunks(diff_text: str) -> list[str]:
    """Extract list of unified diff hunk headers from diff text."""
    return HUNK_HEADER_REGEX.findall(diff_text)


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


def fetch_pr_cumulative_diff(repo: str, pr_number: int | None, files: list[dict[str, Any]]) -> str:
    """Fetch exact cumulative git diff via GitHub CLI or assemble from file patches."""
    if pr_number and shutil.which("gh"):
        code, out, _ = _run_cmd([
            "gh", "api", f"repos/{repo}/pulls/{pr_number}", "-H", "Accept: application/vnd.github.v3.diff",
        ])
        if code == 0 and out.strip():
            return out
    chunks: list[str] = []
    for f in sorted(files, key=lambda x: x.get("filename", "")):
        fname = f.get("filename", "")
        patch = f.get("patch", "")
        if patch:
            chunks.append(f"diff --git a/{fname} b/{fname}\n--- a/{fname}\n+++ b/{fname}\n{patch}")
    return "\n".join(chunks)


def build_evidence_inventory(
    evidence_dir: Path | None,
    pr_data: dict[str, Any],
    cumulative_diff: str,
    check_runs: list[dict[str, Any]] | None,
    rule_selection: dict[str, Any] | None,
) -> dict[str, str]:
    """Construct deterministic inventory mapping canonical receipt paths to SHA256 hashes."""
    inventory: dict[str, str] = {}

    diff_bytes = cumulative_diff.encode("utf-8")
    diff_hash = hashlib.sha256(diff_bytes).hexdigest()
    inventory["diff.patch"] = diff_hash

    check_runs_bytes = json.dumps(check_runs or [], sort_keys=True, indent=2).encode("utf-8")
    inventory["check_runs.json"] = hashlib.sha256(check_runs_bytes).hexdigest()

    if rule_selection:
        sel_sha = rule_selection.get("selection_sha256")
        if sel_sha:
            inventory["rule_selection.json"] = sel_sha
        else:
            sel_bytes = json.dumps(rule_selection, sort_keys=True, indent=2).encode("utf-8")
            inventory["rule_selection.json"] = hashlib.sha256(sel_bytes).hexdigest()

    if evidence_dir:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "diff.patch").write_bytes(diff_bytes)
        (evidence_dir / "check_runs.json").write_bytes(check_runs_bytes)
        if rule_selection:
            (evidence_dir / "rule_selection.json").write_text(
                json.dumps(rule_selection, indent=2, sort_keys=True), encoding="utf-8"
            )
        for p in sorted(evidence_dir.iterdir()):
            if p.is_file() and p.name not in (
                "evidence_inventory.json",
                "auditor_prompt.txt",
                "auditor_input.json",
                "auditor_report.json",
                "auditor_context.json",
            ):
                h = hashlib.sha256(p.read_bytes()).hexdigest()
                inventory[p.name] = h

        (evidence_dir / "evidence_inventory.json").write_text(
            json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8"
        )

    return inventory


def partition_diff_batches(
    files: list[dict[str, Any]],
    overall_diff_hash: str,
    cumulative_diff: str | None = None,
    max_batch_bytes: int = MAX_BATCH_DIFF_BYTES,
) -> list[dict[str, Any]]:
    """Partition PR files and diff into bounded batches preserving full untruncated content.

    Each batch contains:
    - batch_index: int (1-based)
    - total_batches: int
    - batch_diff: str (untruncated diff text)
    - batch_diff_sha256: str (SHA-256 of batch_diff)
    - overall_diff_sha256: str (overall diff hash)
    - batch_files: list[str] (files covered in this batch)
    """
    sorted_files = sorted(files, key=lambda x: x.get("filename", ""))
    file_diff_map: list[tuple[str, str]] = []

    for f in sorted_files:
        fname = f.get("filename", "")
        patch = f.get("patch", "")
        status = f.get("status", "modified")
        if patch:
            fdiff = f"diff --git a/{fname} b/{fname}\n--- a/{fname}\n+++ b/{fname}\n{patch}\n"
        elif f.get("is_binary"):
            fdiff = f"diff --git a/{fname} b/{fname}\nBinary files differ\n"
        else:
            fdiff = f"diff --git a/{fname} b/{fname}\n# Empty, binary, or unchanged file ({status})\n"
        file_diff_map.append((fname, fdiff))

    if not file_diff_map:
        diff_text = cumulative_diff or ""
        return [{
            "batch_index": 1,
            "total_batches": 1,
            "batch_diff": diff_text,
            "batch_diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
            "overall_diff_sha256": overall_diff_hash,
            "batch_files": [],
        }]

    total_bytes = sum(len(d.encode("utf-8")) for _, d in file_diff_map)
    full_diff = "".join(d for _, d in file_diff_map) if not cumulative_diff else cumulative_diff
    total_expected_hunks = extract_diff_hunks(full_diff)

    if total_bytes <= max_batch_bytes:
        hunks = extract_diff_hunks(full_diff)
        return [{
            "batch_index": 1,
            "total_batches": 1,
            "batch_diff": full_diff,
            "batch_diff_sha256": hashlib.sha256(full_diff.encode("utf-8")).hexdigest(),
            "overall_diff_sha256": overall_diff_hash,
            "batch_files": [fname for fname, _ in file_diff_map],
            "batch_hunks": hunks,
            "batch_hunk_count": len(hunks),
            "batch_bytes": len(full_diff.encode("utf-8")),
        }]

    batches: list[dict[str, Any]] = []
    current_files: list[str] = []
    current_diff_parts: list[str] = []
    current_bytes = 0

    for fname, fdiff in file_diff_map:
        fbytes = len(fdiff.encode("utf-8"))
        if fbytes > max_batch_bytes:
            if current_files:
                batches.append({
                    "batch_diff": "".join(current_diff_parts),
                    "batch_files": list(current_files),
                })
                current_files = []
                current_diff_parts = []
                current_bytes = 0

            hunk_splits = re.split(r"(?=\n@@ )", fdiff)
            file_header = hunk_splits[0]
            hunks = hunk_splits[1:] if len(hunk_splits) > 1 else [file_header]
            hunk_header = file_header if len(hunk_splits) > 1 else ""

            part_diffs: list[str] = []
            part_bytes = len(hunk_header.encode("utf-8"))

            for hunk in (hunks if hunk_header else [fdiff]):
                hunk_b = len(hunk.encode("utf-8"))
                if part_diffs and (part_bytes + hunk_b > max_batch_bytes):
                    batches.append({
                        "batch_diff": hunk_header + "".join(part_diffs),
                        "batch_files": [fname],
                    })
                    part_diffs = [hunk]
                    part_bytes = len(hunk_header.encode("utf-8")) + hunk_b
                else:
                    part_diffs.append(hunk)
                    part_bytes += hunk_b

            if part_diffs:
                batches.append({
                    "batch_diff": hunk_header + "".join(part_diffs),
                    "batch_files": [fname],
                })
        else:
            if current_files and (current_bytes + fbytes > max_batch_bytes):
                batches.append({
                    "batch_diff": "".join(current_diff_parts),
                    "batch_files": list(current_files),
                })
                current_files = [fname]
                current_diff_parts = [fdiff]
                current_bytes = fbytes
            else:
                current_files.append(fname)
                current_diff_parts.append(fdiff)
                current_bytes += fbytes

    if current_files:
        batches.append({
            "batch_diff": "".join(current_diff_parts),
            "batch_files": list(current_files),
        })

    total_batches = len(batches)
    total_partitioned_hunks = 0
    for idx, b in enumerate(batches, start=1):
        b["batch_index"] = idx
        b["total_batches"] = total_batches
        b["batch_diff_sha256"] = hashlib.sha256(b["batch_diff"].encode("utf-8")).hexdigest()
        b["overall_diff_sha256"] = overall_diff_hash
        b_hunks = extract_diff_hunks(b["batch_diff"])
        b["batch_hunks"] = b_hunks
        b["batch_hunk_count"] = len(b_hunks)
        b["batch_bytes"] = len(b["batch_diff"].encode("utf-8"))
        total_partitioned_hunks += len(b_hunks)

    if total_expected_hunks and total_partitioned_hunks < len(total_expected_hunks):
        raise PRReviewError(
            f"Hunk preservation mismatch in diff partitioning: expected {len(total_expected_hunks)} hunks, "
            f"partitioned {total_partitioned_hunks} hunks. Truncation or hunk loss detected."
        )

    return batches


def build_auditor_prompt(
    pr_data: dict[str, Any],
    rule_selection: dict[str, Any] | None,
    evidence_inventory: dict[str, str],
    cumulative_diff: str,
    batch_info: dict[str, Any] | None = None,
    max_unbatched_bytes: int = MAX_BATCH_DIFF_BYTES,
) -> str:
    """Build bounded read-only prompt for independent Auditor without silent truncation."""
    required_paths = sorted({f.get("filename", "") for f in pr_data.get("files", [])})
    rules = rule_selection.get("rules", []) if rule_selection else []
    sel_sha = rule_selection.get("selection_sha256", "NONE") if rule_selection else "NONE"

    # Enforce no silent truncation
    diff_bytes = cumulative_diff.encode("utf-8")
    if batch_info is None and len(diff_bytes) > max_unbatched_bytes:
        raise PRReviewError(
            f"Cumulative diff ({len(diff_bytes)} bytes) exceeds single-batch limit "
            f"({max_unbatched_bytes} bytes). Silent truncation is strictly forbidden; "
            f"diff batching must be used."
        )

    rules_lines: list[str] = []
    for r in rules:
        if isinstance(r, dict):
            rules_lines.append(
                f"- Rule {r.get('rule_id')}: sha256={r.get('rule_sha256')} - {r.get('title', r.get('description', ''))}"
            )
        else:
            rules_lines.append(f"- Rule {r}")

    evidence_lines = [f"- {p}: sha256={h}" for p, h in sorted(evidence_inventory.items())]

    if batch_info:
        batch_idx = batch_info.get("batch_index", 1)
        tot_batches = batch_info.get("total_batches", 1)
        b_sha = batch_info.get("batch_diff_sha256", "")
        ov_sha = batch_info.get("overall_diff_sha256", "")
        scope_files = sorted(batch_info.get("batch_files", []))
        batch_section = f"""Batch Review Mode: Part {batch_idx} of {tot_batches}
Batch Diff SHA256: {b_sha}
Overall Diff SHA256: {ov_sha}
Batch Reviewed Scope ({len(scope_files)} files):
{json.dumps(scope_files, indent=2)}
"""
        scope_rule = f'"reviewed_scope" MUST be the exact list of {len(scope_files)} batch files above.'
    else:
        batch_section = ""
        scope_files = required_paths
        scope_rule = f'"reviewed_scope" MUST be the exact list of {len(required_paths)} changed files above.'

    prompt = f"""You are a fresh, independent, read-only code and compliance Auditor.
Your audit is strictly read-only: do NOT make edits or self-approve.
You must review the full diff and evaluate compliance against applicable Host-selected Rule IDs.

PR Number: #{pr_data.get('number')}
PR Title: {pr_data.get('title')}
PR Author: @{pr_data.get('author')}
Base SHA: {pr_data.get('base_sha')}
Head SHA: {pr_data.get('head_sha')}

Mandatory PR Scope ({len(required_paths)} files):
{json.dumps(required_paths, indent=2)}
{batch_section}
Host Selection SHA256:
{sel_sha}

Applicable Scoped Rule IDs ({len(rules)} rules):
{chr(10).join(rules_lines) if rules_lines else "(No code standards rules required for docs/non-code changes)"}

Host Evidence Inventory:
{chr(10).join(evidence_lines)}

Cumulative PR Diff (full untruncated content):
```diff
{cumulative_diff}
```

Instructions:
1. Output ONLY a valid JSON object matching the required audit schema.
2. Root keys must be: "status", "findings", "limitations", "reviewed_scope", and when rules are selected: "selection_sha256", "rule_results".
3. {scope_rule}
4. "selection_sha256" MUST be exactly "{sel_sha}".
5. In "rule_results", you must evaluate each applicable Rule ID:
   - "rule_id": string
   - "rule_sha256": string (must match Host hash)
   - "status": "PASS" | "FAIL" | "NOT_RUN" | "NOT_VERIFIED" | "WAIVED_WITH_REASON"
   - "evidence": [{{"receipt_path": "<from evidence inventory>", "receipt_sha256": "<matching sha256>"}}]
   - "reason": detailed explanation
6. If all rules and correctness checks pass with zero defects:
   - "status" = "PASS"
   - "findings" = []
   - "limitations" = []
"""
    return prompt


def aggregate_batch_reports(
    batch_reports: list[dict[str, Any]],
    required_paths: set[str],
    expected_base_sha: str | None = None,
    expected_head_sha: str | None = None,
    expected_diff_sha256: str | None = None,
    rule_selection: dict[str, Any] | None = None,
    expected_batches_count: int | None = None,
    expected_hunks: list[str] | None = None,
) -> dict[str, Any]:
    """Aggregate multiple batch audit reports with mandatory coverage, snapshot binding, and hunk verification."""
    if not batch_reports:
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-NO-REPORTS",
                    "explanation": "No batch reports provided for aggregation.",
                    "fix": "Run Auditor across all batches.",
                }
            ],
            "limitations": ["No batch reports to aggregate"],
            "reviewed_scope": [],
            "base_sha": expected_base_sha,
            "head_sha": expected_head_sha,
            "diff_sha256": expected_diff_sha256,
        }

    # 1. Batch count validation
    if expected_batches_count is not None and len(batch_reports) != expected_batches_count:
        err_msg = (
            f"Batch count mismatch: expected {expected_batches_count} batch reports, "
            f"received {len(batch_reports)}."
        )
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-COVERAGE-MISMATCH",
                    "explanation": err_msg,
                    "fix": "Ensure all batch reports are provided without omissions.",
                }
            ],
            "limitations": [err_msg],
            "reviewed_scope": [],
            "base_sha": expected_base_sha,
            "head_sha": expected_head_sha,
            "diff_sha256": expected_diff_sha256,
        }

    all_reviewed: set[str] = set()
    all_findings: list[dict[str, Any]] = []
    all_limitations: list[str] = []
    all_reported_hunks: set[str] = set()
    seen_finding_keys: set[tuple[str, str, int, str, str]] = set()
    rule_results_map: dict[str, dict[str, Any]] = {}

    for rep in batch_reports:
        all_reviewed.update(rep.get("reviewed_scope", []))
        if "hunks" in rep and isinstance(rep["hunks"], list):
            all_reported_hunks.update(rep["hunks"])
        for f in rep.get("findings", []):
            key = (
                f.get("severity", ""),
                f.get("file", ""),
                f.get("line", 0),
                f.get("rule", ""),
                f.get("explanation", ""),
            )
            if key not in seen_finding_keys:
                seen_finding_keys.add(key)
                all_findings.append(f)
        for lim in rep.get("limitations", []):
            if lim not in all_limitations:
                all_limitations.append(lim)

        for rr in rep.get("rule_results", []):
            rid = rr.get("rule_id", "")
            if rid not in rule_results_map:
                rule_results_map[rid] = dict(rr)
                rule_results_map[rid]["evidence"] = list(rr.get("evidence", []))
            else:
                existing = rule_results_map[rid]
                if rr.get("status") == "FAIL":
                    existing["status"] = "FAIL"
                elif rr.get("status") != "PASS" and existing["status"] == "PASS":
                    existing["status"] = rr.get("status")
                ev_seen = {(e.get("receipt_path"), e.get("receipt_sha256")) for e in existing["evidence"]}
                for ev in rr.get("evidence", []):
                    ev_key = (ev.get("receipt_path"), ev.get("receipt_sha256"))
                    if ev_key not in ev_seen:
                        ev_seen.add(ev_key)
                        existing["evidence"].append(ev)

    # 2. Hunk coverage validation if expected hunks are specified
    if expected_hunks is not None:
        missing_hunks = set(expected_hunks) - all_reported_hunks
        if missing_hunks:
            err_msg = (
                f"Hunk coverage mismatch: expected {len(expected_hunks)} hunks, missing {len(missing_hunks)}. "
                f"Truncated/missing hunks detected."
            )
            return {
                "status": "FAIL",
                "findings": [
                    {
                        "severity": "CRITICAL",
                        "file": "audit",
                        "line": 1,
                        "rule": "AUDIT-COVERAGE-MISMATCH",
                        "explanation": err_msg,
                        "fix": "Re-run Auditor ensuring complete hunk coverage.",
                    }
                ],
                "limitations": [err_msg],
                "reviewed_scope": sorted(all_reviewed),
                "base_sha": expected_base_sha,
                "head_sha": expected_head_sha,
                "diff_sha256": expected_diff_sha256,
            }

    # 3. Mandatory path coverage verification
    missing_paths = required_paths - all_reviewed
    unexpected_paths = all_reviewed - required_paths
    if missing_paths or unexpected_paths:
        err_msg = (
            f"Mandatory coverage check failed: reviewed scope does not match required changed paths. "
            f"Missing: {sorted(missing_paths)}, Unexpected: {sorted(unexpected_paths)}"
        )
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-COVERAGE-MISMATCH",
                    "explanation": err_msg,
                    "fix": "Ensure all changed files are reviewed across diff batches.",
                }
            ],
            "limitations": [err_msg],
            "reviewed_scope": sorted(all_reviewed),
            "base_sha": expected_base_sha,
            "head_sha": expected_head_sha,
            "diff_sha256": expected_diff_sha256,
        }

    # Determine aggregated status
    has_critical = any(f.get("severity") in ("CRITICAL", "HIGH", "P0", "P1") for f in all_findings)
    any_fail = any(rep.get("status") == "FAIL" for rep in batch_reports)
    any_inconclusive = any(rep.get("status") == "INCONCLUSIVE" for rep in batch_reports)

    if has_critical or any_fail or all_findings:
        overall_status = "FAIL"
    elif any_inconclusive or all_limitations:
        overall_status = "INCONCLUSIVE"
    else:
        overall_status = "PASS"

    agg: dict[str, Any] = {
        "status": overall_status,
        "findings": all_findings,
        "limitations": all_limitations,
        "reviewed_scope": sorted(all_reviewed),
    }

    if expected_base_sha:
        agg["base_sha"] = expected_base_sha
    if expected_head_sha:
        agg["head_sha"] = expected_head_sha
    if expected_diff_sha256:
        agg["diff_sha256"] = expected_diff_sha256

    has_rules = bool(rule_selection and rule_selection.get("rules") and rule_selection.get("selection_sha256"))
    if has_rules:
        agg["selection_sha256"] = rule_selection["selection_sha256"]
        agg["rule_results"] = list(rule_results_map.values())

    return agg


def run_auto_audit(
    pr_data: dict[str, Any],
    rule_selection: dict[str, Any] | None,
    evidence_inventory: dict[str, str],
    cumulative_diff: str,
    evidence_dir: Path,
    timeout: int = 300,
    max_batch_bytes: int = MAX_BATCH_DIFF_BYTES,
) -> dict[str, Any]:
    """Spawn fresh independent Auditor in sandbox with full-diff batching and coverage checks."""
    if not antigravity:
        raise PRReviewError("antigravity adapter not available; cannot spawn Auditor")

    if not shutil.which("agy"):
        raise PRReviewError("Auditor binary 'agy' not found in PATH; cannot spawn independent Auditor")

    required_paths = {f.get("filename", "") for f in pr_data.get("files", [])}
    has_rules = bool(rule_selection and rule_selection.get("rules") and rule_selection.get("selection_sha256"))
    required_rules = rule_selection.get("rules") if has_rules else None
    sel_sha = rule_selection.get("selection_sha256") if has_rules else None
    target_inventory = evidence_inventory if has_rules else None
    schema_path = Path(__file__).resolve().parent / "adapters" / "audit.schema.json"

    evidence_dir.mkdir(parents=True, exist_ok=True)

    diff_hash = evidence_inventory.get("diff.patch", "")
    batches = partition_diff_batches(
        pr_data.get("files", []),
        overall_diff_hash=diff_hash,
        cumulative_diff=cumulative_diff,
        max_batch_bytes=max_batch_bytes,
    )

    batch_reports: list[dict[str, Any]] = []

    for batch in batches:
        b_idx = batch["batch_index"]
        b_total = batch["total_batches"]
        b_files = set(batch["batch_files"])
        b_diff = batch["batch_diff"]

        prompt = build_auditor_prompt(
            pr_data,
            rule_selection,
            evidence_inventory,
            b_diff,
            batch_info=batch if b_total > 1 else None,
            max_unbatched_bytes=max_batch_bytes,
        )

        prompt_file = evidence_dir / (f"auditor_prompt_batch_{b_idx}.txt" if b_total > 1 else "auditor_prompt.txt")
        prompt_file.write_text(prompt, encoding="utf-8")

        batch_report = antigravity.invoke(
            prompt=prompt,
            snapshot=evidence_dir,
            schema=schema_path,
            timeout=timeout,
            required_paths=b_files if b_total > 1 else required_paths,
            required_rules=required_rules,
            selection_sha256=sel_sha,
            evidence_inventory=target_inventory,
        )
        if b_total > 1:
            batch_report_file = evidence_dir / f"auditor_report_batch_{b_idx}.json"
            batch_report_file.write_text(json.dumps(batch_report, indent=2, sort_keys=True), encoding="utf-8")
        batch_reports.append(batch_report)

    final_report = aggregate_batch_reports(
        batch_reports=batch_reports,
        required_paths=required_paths,
        expected_base_sha=pr_data.get("base_sha"),
        expected_head_sha=pr_data.get("head_sha"),
        expected_diff_sha256=diff_hash,
        rule_selection=rule_selection,
        expected_batches_count=len(batches),
    )

    report_file = evidence_dir / "auditor_report.json"
    report_file.write_text(json.dumps(final_report, indent=2, sort_keys=True), encoding="utf-8")
    return final_report


def validate_and_load_auditor_report(
    report_path: Path,
    pr_data: dict[str, Any],
    rule_selection: dict[str, Any] | None,
    evidence_inventory: dict[str, str] | None = None,
    expected_diff_sha256: str | None = None,
) -> dict[str, Any]:
    """Validate external Auditor report against schema, evidence inventory, exact changed paths, and snapshot binding."""
    if not report_path.is_file():
        raise PRReviewError(f"Auditor report path not found: {report_path}")

    raw_text = report_path.read_text(encoding="utf-8")
    try:
        report = json.loads(raw_text)
    except Exception as exc:
        raise PRReviewError(f"Auditor report is not valid JSON: {exc}") from exc

    if not isinstance(report, dict):
        raise PRReviewError("Auditor report must be a JSON object")

    required_paths = {f.get("filename", "") for f in pr_data.get("files", [])}

    # Extract snapshot fields and core report from potential envelope
    envelope_data: dict[str, Any] = {}
    if "structured_output" in report:
        envelope_data = {k: v for k, v in report.items() if k != "structured_output"}
        core_report = report["structured_output"]
    elif "report" in report and isinstance(report["report"], dict):
        envelope_data = {k: v for k, v in report.items() if k != "report"}
        core_report = report["report"]
    else:
        core_report = dict(report)

    rep_base = (
        core_report.get("base_sha")
        or envelope_data.get("base_sha")
        or core_report.get("snapshot", {}).get("base_sha")
        or envelope_data.get("snapshot", {}).get("base_sha")
    )
    rep_head = (
        core_report.get("head_sha")
        or envelope_data.get("head_sha")
        or core_report.get("snapshot", {}).get("head_sha")
        or envelope_data.get("snapshot", {}).get("head_sha")
    )
    rep_diff = (
        core_report.get("diff_sha256")
        or envelope_data.get("diff_sha256")
        or core_report.get("snapshot", {}).get("diff_sha256")
        or envelope_data.get("snapshot", {}).get("diff_sha256")
    )

    expected_base = pr_data.get("base_sha")
    expected_head = pr_data.get("head_sha")
    valid_diff_hashes = set()
    if isinstance(expected_diff_sha256, (set, list, tuple)):
        valid_diff_hashes.update(expected_diff_sha256)
    elif expected_diff_sha256:
        valid_diff_hashes.add(expected_diff_sha256)
    if evidence_inventory and evidence_inventory.get("diff.patch"):
        valid_diff_hashes.add(evidence_inventory["diff.patch"])

    # 1. Anti-fabrication check: detect conflicting metadata between envelope and inner report
    if envelope_data and isinstance(core_report, dict):
        for field in ("base_sha", "head_sha", "diff_sha256"):
            env_val = envelope_data.get(field) or envelope_data.get("snapshot", {}).get(field)
            rep_val = core_report.get(field) or core_report.get("snapshot", {}).get(field)
            if env_val and rep_val and env_val != rep_val:
                return {
                    "status": "FAIL",
                    "findings": [
                        {
                            "severity": "CRITICAL",
                            "file": "audit",
                            "line": 1,
                            "rule": "AUDIT-SNAPSHOT-MISMATCH",
                            "explanation": f"Fabricated wrapper detected: envelope {field} ({env_val[:8]}) conflicts with inner report {field} ({rep_val[:8]}).",
                            "fix": "Do not wrap obsolete reports; run a fresh Auditor on current snapshot.",
                        }
                    ],
                    "limitations": [f"Snapshot mismatch: conflicting {field}"],
                    "reviewed_scope": list(required_paths),
                }

    # 2. Mandatory presence & format checks for snapshot binding (fail closed on absent fields)
    if not rep_base or not isinstance(rep_base, str) or not SHA_COMMIT_REGEX.match(rep_base):
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": "Auditor report missing or malformed mandatory base_sha snapshot binding.",
                    "fix": "Re-run independent Auditor with frozen base_sha snapshot binding.",
                }
            ],
            "limitations": ["Missing base_sha snapshot binding"],
            "reviewed_scope": list(required_paths),
        }

    if expected_base and rep_base != expected_base:
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": f"Auditor report base_sha ({rep_base[:8]}) does not match PR base_sha ({expected_base[:8]}).",
                    "fix": "Re-run independent Auditor against the exact current PR base snapshot.",
                }
            ],
            "limitations": ["Snapshot mismatch: base_sha changed"],
            "reviewed_scope": list(required_paths),
        }

    if not rep_head or not isinstance(rep_head, str) or not SHA_COMMIT_REGEX.match(rep_head):
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": "Auditor report missing or malformed mandatory head_sha snapshot binding.",
                    "fix": "Re-run independent Auditor with frozen head_sha snapshot binding.",
                }
            ],
            "limitations": ["Missing head_sha snapshot binding"],
            "reviewed_scope": list(required_paths),
        }

    if expected_head and rep_head != expected_head:
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": f"Auditor report head_sha ({rep_head[:8]}) does not match PR head_sha ({expected_head[:8]}).",
                    "fix": "Re-run independent Auditor against the exact current PR head snapshot.",
                }
            ],
            "limitations": ["Snapshot mismatch: head_sha changed"],
            "reviewed_scope": list(required_paths),
        }

    if not rep_diff or not isinstance(rep_diff, str) or not SHA256_REGEX.match(rep_diff):
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": "Auditor report missing or malformed mandatory diff_sha256 snapshot binding.",
                    "fix": "Re-run independent Auditor with frozen diff_sha256 snapshot binding.",
                }
            ],
            "limitations": ["Missing diff_sha256 snapshot binding"],
            "reviewed_scope": list(required_paths),
        }

    if valid_diff_hashes and rep_diff not in valid_diff_hashes:
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-SNAPSHOT-MISMATCH",
                    "explanation": f"Auditor report diff_sha256 ({rep_diff[:8]}...) does not match PR diff snapshot.",
                    "fix": "Re-run independent Auditor against the exact current PR cumulative diff.",
                }
            ],
            "limitations": ["Snapshot mismatch: diff_sha256 changed"],
            "reviewed_scope": list(required_paths),
        }

    # Check diff.patch receipt evidence hash
    expected_patch_sha = (
        (evidence_inventory.get("diff.patch") if evidence_inventory else None)
        or expected_diff_sha256
    )
    if expected_patch_sha and "rule_results" in core_report:
        for item in core_report.get("rule_results", []):
            if isinstance(item, dict):
                for ref in item.get("evidence", []):
                    if isinstance(ref, dict) and ref.get("receipt_path") == "diff.patch":
                        if ref.get("receipt_sha256") != expected_patch_sha:
                            return {
                                "status": "FAIL",
                                "findings": [
                                    {
                                        "severity": "CRITICAL",
                                        "file": "audit",
                                        "line": 1,
                                        "rule": "AUDIT-SNAPSHOT-MISMATCH",
                                        "explanation": f"Rule evidence diff.patch hash does not match PR diff snapshot.",
                                        "fix": "Re-run Auditor with valid evidence receipts from current PR snapshot.",
                                    }
                                ],
                                "limitations": ["Snapshot mismatch: diff.patch receipt hash changed"],
                                "reviewed_scope": list(required_paths),
                            }

    # 2. Mandatory Coverage Check
    reviewed_scope = set(core_report.get("reviewed_scope", []))
    if required_paths and reviewed_scope != required_paths:
        missing = required_paths - reviewed_scope
        extra = reviewed_scope - required_paths
        return {
            "status": "FAIL",
            "findings": [
                {
                    "severity": "CRITICAL",
                    "file": "audit",
                    "line": 1,
                    "rule": "AUDIT-COVERAGE-MISMATCH",
                    "explanation": f"Auditor report reviewed_scope does not match changed files: missing {sorted(missing)}, extra {sorted(extra)}",
                    "fix": "Ensure Auditor reviews 100% of changed files in the PR scope.",
                }
            ],
            "limitations": [f"Coverage mismatch: missing {len(missing)} file(s)"],
            "reviewed_scope": list(required_paths),
        }

    # 3. Clean non-schema metadata for antigravity validator
    has_rules = bool(rule_selection and rule_selection.get("rules") and rule_selection.get("selection_sha256"))
    snapshot_keys = {"base_sha", "head_sha", "diff_sha256", "snapshot"}
    if not has_rules:
        snapshot_keys.update({"selection_sha256", "rule_results"})
    snapshot_fields = {k: v for k, v in core_report.items() if k in snapshot_keys}
    clean_report = {k: v for k, v in core_report.items() if k not in snapshot_keys}

    if antigravity:
        try:
            required_rules = rule_selection.get("rules") if has_rules else None
            sel_sha = rule_selection.get("selection_sha256") if has_rules else None
            validated = antigravity.check_report(
                clean_report,
                required_paths=required_paths,
                required_rules=required_rules,
                selection_sha256=sel_sha,
                evidence_inventory=evidence_inventory if has_rules else None,
            )
            validated.update(snapshot_fields)
            if rep_base and "base_sha" not in validated:
                validated["base_sha"] = rep_base
            if rep_head and "head_sha" not in validated:
                validated["head_sha"] = rep_head
            if rep_diff and "diff_sha256" not in validated:
                validated["diff_sha256"] = rep_diff
            return validated
        except Exception as exc:
            return {
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

    clean_report.update(snapshot_fields)
    return clean_report


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

    # 5. Diff hashes and snapshot (R-05: Schema 1.0, bound base/head/diff/rules)
    file_hashes, overall_diff_hash = compute_diff_hashes(pr_data.get("files", []))
    cumulative_diff = fetch_pr_cumulative_diff(repo_name, pr_number, pr_data.get("files", []))

    # Evidence inventory and external evidence dir
    evidence_dir = Path(args.evidence_dir).resolve() if getattr(args, "evidence_dir", None) else None
    evidence_inventory = build_evidence_inventory(
        evidence_dir=evidence_dir,
        pr_data=pr_data,
        cumulative_diff=cumulative_diff,
        check_runs=check_runs,
        rule_selection=rule_selection,
    )

    # Optional export of frozen auditor context
    if getattr(args, "export_auditor_context", None):
        export_path = Path(args.export_auditor_context).resolve()
        export_path.parent.mkdir(parents=True, exist_ok=True)
        diff_hash = evidence_inventory.get("diff.patch", "")
        batches = partition_diff_batches(
            pr_data.get("files", []),
            overall_diff_hash=diff_hash,
            cumulative_diff=cumulative_diff,
            max_batch_bytes=MAX_BATCH_DIFF_BYTES,
        )
        auditor_prompt = build_auditor_prompt(
            pr_data,
            rule_selection,
            evidence_inventory,
            batches[0]["batch_diff"],
            batch_info=batches[0] if len(batches) > 1 else None,
            max_unbatched_bytes=MAX_BATCH_DIFF_BYTES,
        )
        context_payload = {
            "pr_number": pr_data.get("number"),
            "title": pr_data.get("title"),
            "author": pr_data.get("author"),
            "base_ref": pr_data.get("base_ref"),
            "base_sha": base_sha_at_start,
            "head_ref": pr_data.get("head_ref"),
            "head_sha": head_sha_at_start,
            "diff_sha256": overall_diff_hash,
            "required_paths": sorted({f.get("filename", "") for f in pr_data.get("files", [])}),
            "rule_selection": rule_selection,
            "selection_sha256": rule_selection.get("selection_sha256") if rule_selection else None,
            "evidence_inventory": evidence_inventory,
            "cumulative_diff": cumulative_diff,
            "batches": batches,
            "auditor_prompt": auditor_prompt,
        }
        export_path.write_text(json.dumps(context_payload, indent=2, sort_keys=True), encoding="utf-8")
        if evidence_dir:
            (evidence_dir / "auditor_prompt.txt").write_text(auditor_prompt, encoding="utf-8")
        print(f"✅ Auditor context exported to {export_path}")
        if not getattr(args, "auditor_report", None) and not getattr(args, "auto_audit", False):
            return 0

    # 6. Auditor Report Intake (R-02)
    auditor_report = None
    if getattr(args, "auditor_report", None):
        auditor_report_path = Path(args.auditor_report).resolve()
        auditor_report = validate_and_load_auditor_report(
            auditor_report_path,
            pr_data,
            rule_selection,
            evidence_inventory=evidence_inventory,
            expected_diff_sha256={h for h in (overall_diff_hash, evidence_inventory.get("diff.patch")) if h},
        )
    elif getattr(args, "auto_audit", False):
        try:
            target_evidence_dir = evidence_dir or Path(tempfile.mkdtemp(prefix=f"harness-evidence-pr{pr_number or 0}-"))
            audit_timeout = getattr(args, "audit_timeout", 300)
            auditor_report = run_auto_audit(
                pr_data=pr_data,
                rule_selection=rule_selection,
                evidence_inventory=evidence_inventory,
                cumulative_diff=cumulative_diff,
                evidence_dir=target_evidence_dir,
                timeout=audit_timeout,
            )
        except Exception as exc:
            required_paths = sorted({f.get("filename", "") for f in pr_data.get("files", [])})
            auditor_report = {
                "status": "FAIL",
                "findings": [
                    {
                        "severity": "CRITICAL",
                        "file": "audit",
                        "line": 1,
                        "rule": "AUDIT-SPAWN",
                        "explanation": f"Independent Auditor auto-spawn failed: {exc}",
                        "fix": "Verify native toolchain and re-run independent Auditor.",
                    }
                ],
                "limitations": [f"Auto-audit spawn failure: {exc}"],
                "reviewed_scope": required_paths,
            }
    elif fixture_auditor_report:
        auditor_report = fixture_auditor_report

    # 7. Post-audit freshness verification to detect TOCTOU race during audit
    if not args.fixture and pr_number:
        head_sha_at_end = fetch_latest_head_sha(repo_name, pr_number)
        base_sha_at_end = fetch_latest_base_sha(repo_name, pr_number)

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
        expected_diff_sha256={h for h in (overall_diff_hash, evidence_inventory.get("diff.patch")) if h},
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
    parser.add_argument("--auto-audit", action="store_true", help="Automatically spawn fresh independent Auditor via agy sandbox")
    parser.add_argument("--audit-timeout", type=int, default=300, help="Timeout in seconds for Auditor auto-spawn (default: 300)")
    parser.add_argument("--evidence-dir", help="Directory for external evidence storage (outside candidate worktree)")
    parser.add_argument("--export-auditor-context", help="Path to write frozen auditor context JSON")
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
