"""PR Review Policy Evaluator: Scoped Rule IDs, Evidence Gates, and Human Merge Policy.

Enforces read-only PR review gates PR-01 to PR-08.
Never merges, never self-approves, never executes untrusted PR contents.
"""
from __future__ import annotations

import enum
import fnmatch
import json
from pathlib import PurePosixPath
import re
from typing import Any, Iterable


class GateStatus(str, enum.Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    NOT_VERIFIED = "NOT_VERIFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HostVerdict(str, enum.Enum):
    READY_FOR_HUMAN_REVIEW = "READY_FOR_HUMAN_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    BLOCKED = "BLOCKED"
    NOT_VERIFIED = "NOT_VERIFIED"


# High risk path patterns requiring >= 2 specialist approvals and strict HIL/security
HIGH_RISK_PATTERNS = (
    "firmware/components/sx1276_driver/**",
    "firmware/components/lora_mac/**",
    "firmware/components/tdma_common/**",
    "firmware/components/airtime_policy/**",
    "contracts/**",
    "hardware/**",
    "scripts/agent_harness/**",
    ".agents/**",
    ".github/workflows/**",
    "deploy/**",
)

# Medium risk path patterns requiring >= 1 relevant owner
MEDIUM_RISK_PATTERNS = (
    "firmware/**",
    "backend-go/**",
    "clients/**",
    "simulator/**",
    "tests/**",
    "scripts/**",
)

# Security credential scan patterns
PRIVATE_KEY_REGEX = re.compile(r"(?m)^[ \t]*-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
TOKEN_REGEX = re.compile(r"\b(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}\b|\bAKIA[A-Z0-9]{16}\b")
PASSWORD_REGEX = re.compile(
    r'''(?im)^[ \t]*(?:(?:POSTGRES_PASSWORD|MQTT_PASSWORD)[ \t]*=[ \t]*([^\s#]+)|["']?(?:POSTGRES_PASSWORD|MQTT_PASSWORD|password|api_key|access_token)["']?[ \t]*[:=][ \t]*["']([^"'\r\n]{8,})["'])'''
)

CONFLICT_MARKER_REGEX = re.compile(r"^(?:\+)?(<{7}|={7}|>{7})(?:\s.*)?$", re.MULTILINE)
PROMPT_INJECTION_REGEX = re.compile(
    r"(?i)(ignore\s+all\s+(?:previous|prior)\s+instructions|"
    r"you\s+are\s+now\s+in\s+developer\s+mode|"
    r"override\s+(?:system|security|gate)\s+rules|"
    r"bypass\s+all\s+checks|"
    r"mark\s+(?:all\s+)?(?:gates?\s+)?as\s+pass|"
    r"auto[-_\s]*merge\s+(?:this\s+pr|immediately))"
)

RULE_ID_REGEX = re.compile(r"^[A-Z]+-[0-9]{3}$")
HASH_REGEX = re.compile(r"^[0-9a-f]{64}$")

try:
    from .standards_policy import GROUPS as _STANDARDS_GROUPS
except (ImportError, Exception):
    try:
        from standards_policy import GROUPS as _STANDARDS_GROUPS
    except (ImportError, Exception):
        _STANDARDS_GROUPS = {}

# Synchronized from standards_policy.py (C Coding Standard v2 and Go Backend Standard v2)
# C groups: GOV, C, MEM, ERR, RTOS, ARCH, SEC, RAD, MAC, TDMA, QA
# Go groups: GGS, GB, AR, GO, CT, MQ, SC, DB, RT, OB, SE, TS, QG, AI
_BASE_KNOWN_RULE_PREFIXES = frozenset({
    # C Standard v2 groups (11)
    "ARCH", "C", "ERR", "GOV", "MAC", "MEM", "QA", "RAD", "RTOS", "SEC", "TDMA",
    # Go Standard v2 groups (14)
    "AI", "AR", "CT", "DB", "GB", "GGS", "GO", "MQ", "OB", "QG", "RT", "SC", "SE", "TS",
})

KNOWN_RULE_PREFIXES = frozenset(
    _BASE_KNOWN_RULE_PREFIXES
    | {prefix for lang_groups in _STANDARDS_GROUPS.values() for prefix in lang_groups.keys()}
)


def is_synthetic_fixture_path(path: str) -> bool:
    """Check if a path is a synthetic test fixture rather than actual code or contract."""
    norm = path.strip("/").lower()
    return "/fixtures/" in norm or norm.startswith("tests/agent_harness/fixtures/") or norm.startswith("tests/fixtures/")


def is_security_sensitive_path(path: str) -> bool:
    """Check if a path touches security, cryptographic, TLS, or auth boundaries."""
    norm = path.strip("/").lower()
    if is_synthetic_fixture_path(norm):
        return False
    if norm.startswith("contracts/"):
        return True
    if any(k in norm for k in ("crypto", "tls", "auth", "secret", "token", "credential", "rbac")):
        return True
    if norm.startswith("firmware/components/sx1276_driver/") or norm.startswith("firmware/components/lora_mac/"):
        return True
    return False


class CodeOwnerRule:
    """Represents a single rule in CODEOWNERS."""

    def __init__(self, pattern: str, owners: list[str]) -> None:
        self.pattern = pattern
        self.owners = owners

    def matches(self, path: str) -> bool:
        norm = path.strip("/")
        pat = self.pattern.strip()
        if pat == "*":
            return True
        if pat.startswith("/"):
            # Root-relative
            sub = pat.lstrip("/")
            if sub.endswith("/"):
                return norm == sub.rstrip("/") or norm.startswith(sub)
            return norm == sub or fnmatch.fnmatch(norm, sub)
        # Anywhere in tree
        if pat.endswith("/"):
            sub = pat.rstrip("/")
            return sub in norm.split("/") or norm.startswith(pat) or f"/{pat}" in f"/{norm}/"
        return fnmatch.fnmatch(norm, pat) or fnmatch.fnmatch(PurePosixPath(norm).name, pat)


def parse_codeowners(content: str) -> list[CodeOwnerRule]:
    """Parse .github/CODEOWNERS content into ordered rules (last match wins)."""
    rules: list[CodeOwnerRule] = []
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            pattern = parts[0]
            owners = [o for o in parts[1:] if o.startswith("@")]
            if owners:
                rules.append(CodeOwnerRule(pattern, owners))
    return rules


def match_codeowners(rules: list[CodeOwnerRule], path: str) -> list[str]:
    """Find owners for a path. Later rules in CODEOWNERS override earlier rules."""
    matched_owners: list[str] = []
    for rule in rules:
        if rule.matches(path):
            matched_owners = rule.owners
    return matched_owners


def get_required_codeowners(rules: list[CodeOwnerRule], changed_files: Iterable[str]) -> dict[str, list[str]]:
    """Map each changed file to its assigned code owners."""
    file_owners: dict[str, list[str]] = {}
    for f in changed_files:
        file_owners[f] = match_codeowners(rules, f)
    return file_owners


def classify_risk(changed_files: Iterable[str]) -> RiskLevel:
    """Classify review risk level based on affected paths."""
    files = list(changed_files)
    if not files:
        return RiskLevel.LOW

    for f in files:
        norm = f.strip("/")
        for high_pat in HIGH_RISK_PATTERNS:
            if fnmatch.fnmatch(norm, high_pat) or norm.startswith(high_pat.rstrip("/*")):
                return RiskLevel.HIGH

    for f in files:
        norm = f.strip("/")
        for med_pat in MEDIUM_RISK_PATTERNS:
            if fnmatch.fnmatch(norm, med_pat) or norm.startswith(med_pat.rstrip("/*")):
                return RiskLevel.MEDIUM

    # Only docs / safe markdown / templates
    return RiskLevel.LOW


def get_approval_policy_recommendation(risk: RiskLevel) -> dict[str, Any]:
    """Return non-binding proposed project human review policy recommendation."""
    if risk == RiskLevel.HIGH:
        return {
            "required_approvals": 2,
            "description": "HIGH risk: requires >= 2 specialist human approvals with relevant disciplines (RF, Security, Architecture, Firmware).",
        }
    if risk == RiskLevel.MEDIUM:
        return {
            "required_approvals": 1,
            "description": "MEDIUM risk: requires >= 1 relevant component owner / peer reviewer approval.",
        }
    return {
        "required_approvals": 1,
        "description": "LOW risk: requires >= 1 independent human reviewer sign-off.",
    }


def eval_pr01_governance(
    pr_data: dict[str, Any],
    linked_issue: dict[str, Any] | None,
    allowed_paths: list[str] | None,
    codeowners_rules: list[CodeOwnerRule],
) -> dict[str, Any]:
    """PR-01 GOVERNANCE: Issue linkage, path allowlist, branch name, and owner independence."""
    blockers: list[str] = []
    changed_files = [f.get("filename", "") for f in pr_data.get("files", [])]
    author = pr_data.get("author", "")

    # 1. Issue linkage
    if not linked_issue:
        blockers.append("No linked OPEN Issue found; PR must reference an active Issue with acceptance criteria.")
    else:
        if linked_issue.get("state") != "OPEN":
            blockers.append(f"Linked Issue #{linked_issue.get('number')} is not OPEN (state: {linked_issue.get('state')}).")

    # 2. Path allowlist / scope
    if allowed_paths is not None:
        for f in changed_files:
            in_scope = False
            for allowed in allowed_paths:
                if allowed.endswith("/"):
                    if f.startswith(allowed):
                        in_scope = True
                        break
                elif f == allowed:
                    in_scope = True
                    break
            if not in_scope:
                blockers.append(f"Path outside Issue scope: {f}")

    # 3. Branch naming convention
    head_ref = pr_data.get("head_ref", "")
    valid_branch_prefix = ("feature/", "fix/", "docs/", "chore/", "research/", "feat/")
    if not any(head_ref.startswith(p) for p in valid_branch_prefix):
        blockers.append(f"Branch '{head_ref}' does not follow repository naming conventions (feature/, fix/, docs/, chore/, research/).")

    # 4. Reviewer independence (Author self-approval forbidden)
    reviews = pr_data.get("reviews", [])
    for r in reviews:
        reviewer = r.get("user", {}).get("login") or r.get("author", "")
        state = r.get("state", "").upper()
        if reviewer == author and state == "APPROVED":
            blockers.append(f"Self-approval detected: PR author '@{author}' cannot approve own PR.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else f"Linked to OPEN Issue; all {len(changed_files)} files within scope; author independence verified."
    return {"gate": "PR-01 GOVERNANCE", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr02_architecture_contract(
    changed_files: Iterable[str],
    pr_data: dict[str, Any],
) -> dict[str, Any]:
    """PR-02 ARCHITECTURE/CONTRACT: Approved ADR, versioned contracts/ compatibility."""
    files = list(changed_files)
    contract_paths = [f for f in files if f.startswith("contracts/")]
    adr_paths = [f for f in files if f.startswith("docs/adr/")]
    arch_paths = [f for f in files if f.startswith("docs/architecture/") or f.startswith("docs/requirements/")]

    touched = contract_paths + adr_paths + arch_paths
    if not touched:
        return {
            "gate": "PR-02 ARCHITECTURE/CONTRACT",
            "status": GateStatus.NOT_APPLICABLE.value,
            "summary": "No contracts, ADRs, or architecture requirements modified in this PR.",
            "blockers": [],
        }

    # If contracts are touched, human specialist sign-off is mandatory
    reviews = pr_data.get("reviews", [])
    author = pr_data.get("author", "")
    approved_reviewers = [
        r.get("user", {}).get("login") or r.get("author", "")
        for r in reviews
        if r.get("state", "").upper() == "APPROVED" and (r.get("user", {}).get("login") or r.get("author", "")) != author
    ]

    blockers: list[str] = []
    if contract_paths and not approved_reviewers:
        blockers.append(f"Versioned interface contracts modified ({len(contract_paths)} files); requires human specialist sign-off before merge.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else f"Contract changes ({len(touched)} files) validated with specialist approval."
    return {"gate": "PR-02 ARCHITECTURE/CONTRACT", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr03_rule_id(
    rule_selection: dict[str, Any] | None,
    changed_files: Iterable[str],
    pr_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """PR-03 RULE-ID: Scoped C/Go Rule IDs, never full standard, no unselected rules.

    Fail-closed: validates deterministic Host selection, tracked #137 schema,
    per-ID rule hashes, HEAD commit SHA binding, and test-rule applicability.
    """
    files = list(changed_files)
    if not rule_selection or not isinstance(rule_selection, dict):
        return {
            "gate": "PR-03 RULE-ID",
            "status": GateStatus.NOT_VERIFIED.value,
            "summary": "No Rule-ID routing receipt available.",
            "blockers": ["Rule selection receipt missing."],
        }

    # Handle explicit router error or failure
    if rule_selection.get("status") == "BLOCKED" or "error" in rule_selection:
        err = rule_selection.get("error", "Rule selection failed closed.")
        return {
            "gate": "PR-03 RULE-ID",
            "status": GateStatus.BLOCKED.value,
            "summary": f"Rule-ID selection failed: {err}",
            "blockers": [f"Rule-ID selection failed: {err}"],
        }

    has_c = any(f.startswith("firmware/") and (f.endswith(".c") or f.endswith(".h")) for f in files)
    has_go = any(f.startswith("backend-go/") and f.endswith(".go") for f in files)
    has_go_test = any(f.startswith("backend-go/") and f.endswith("_test.go") for f in files)

    source = rule_selection.get("source")
    if not source:
        source = "verified_host" if "selection_sha256" in rule_selection else "fixture"

    # Non-code changes (docs only) do not load standards
    if not (has_c or has_go):
        return {
            "gate": "PR-03 RULE-ID",
            "status": GateStatus.NOT_APPLICABLE.value,
            "summary": "Docs / non-code change: code standards routing not applicable.",
            "blockers": [],
            "rules": [],
            "selection_source": source,
        }

    blockers: list[str] = []

    # Offline fixture evidence cannot assert live PR GREEN status
    is_live_pr = pr_data is not None and pr_data.get("is_live", False)
    if source == "fixture" and is_live_pr:
        blockers.append("Synthetic fixture rule evidence cannot be used for live PR verification.")

    # 1. Pinned source SHA binding to PR HEAD commit
    if pr_data and pr_data.get("head_sha") and rule_selection.get("source_sha"):
        if rule_selection["source_sha"] != pr_data["head_sha"]:
            blockers.append(
                f"Rule selection source SHA ({rule_selection['source_sha'][:8]}) "
                f"does not match PR HEAD ({pr_data['head_sha'][:8]})."
            )

    # 2. Extract and validate selected Rule IDs
    raw_ids = rule_selection.get("selected_ids", rule_selection.get("rules", []))
    selected_ids: list[str] = []
    if isinstance(raw_ids, list):
        for item in raw_ids:
            if isinstance(item, dict):
                rid = item.get("rule_id", "")
                if rid:
                    selected_ids.append(rid)
            elif isinstance(item, str):
                selected_ids.append(item)
            else:
                selected_ids.append(str(item))

    # Reject malformed or bogus Rule IDs
    bogus = [
        r for r in selected_ids
        if not RULE_ID_REGEX.match(r) or r.split("-")[0] not in KNOWN_RULE_PREFIXES
    ]
    if bogus:
        blockers.append(f"Malformed or bogus Rule ID detected: {', '.join(bogus[:3])}.")

    # 3. Selection hash verification
    sel_sha = rule_selection.get("selection_sha256")
    if source == "verified_host":
        if not sel_sha or not isinstance(sel_sha, str) or not HASH_REGEX.match(sel_sha):
            blockers.append("Rule selection missing or malformed selection_sha256 receipt.")
    elif sel_sha:
        if not isinstance(sel_sha, str) or not HASH_REGEX.match(sel_sha):
            blockers.append("Rule selection has malformed selection_sha256 receipt.")

    # 4. Check rule count budget
    rule_count = rule_selection.get("rule_count", len(selected_ids))
    if rule_count > 128:
        blockers.append(f"Selected rule count ({rule_count}) exceeds bounded budget (128).")

    # 5. Check standards loaded and required rules applicability
    standards = rule_selection.get("standards", {})
    standards_set: set[str] = set(standards.keys()) if isinstance(standards, dict) else set(standards)

    if has_c:
        if "C" not in standards_set:
            blockers.append("Firmware C code changed but C Coding Standard v2 not selected.")
        if not any(r.startswith("C-") for r in selected_ids):
            blockers.append("Firmware C code changed but no C-* rules selected.")

    if has_go:
        if "GO" not in standards_set:
            blockers.append("Backend Go code changed but Go Backend Engineering Standard v2 not selected.")

    # R-01 mandatory check: TS-001 must be selected if Go test files are modified
    if has_go_test:
        if "TS-001" not in selected_ids:
            blockers.append("Backend Go test code changed (*_test.go) but mandatory TS-001 rule not selected.")

    # Entire standard check
    if rule_selection.get("entire_standard_selected"):
        blockers.append("Entire standard selection is forbidden; rules must be scoped.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else f"Scoped standards ({', '.join(sorted(standards_set)) or 'DOCS'}); {len(selected_ids)} rules bounded and verified."
    return {
        "gate": "PR-03 RULE-ID",
        "status": status.value,
        "summary": summary,
        "blockers": blockers,
        "rules": selected_ids,
        "selection_source": source,
    }


def eval_pr04_correctness(
    pr_data: dict[str, Any],
    auditor_report: dict[str, Any] | None,
    rule_selection: dict[str, Any] | None = None,
    expected_diff_sha256: str | None = None,
) -> dict[str, Any]:
    """PR-04 CORRECTNESS: Behavior, conflict markers, patch completeness, snapshot binding, and auditor findings."""
    blockers: list[str] = []
    files = pr_data.get("files", [])

    for f in files:
        patch = f.get("patch", "")
        filename = f.get("filename", "")
        status = f.get("status", "")

        # Conflict marker scan
        if patch and CONFLICT_MARKER_REGEX.search(patch):
            blockers.append(f"Git conflict marker found in patch for {filename}.")

        # Supported git status
        if status not in ("added", "modified", "removed", "renamed"):
            blockers.append(f"Unsupported git file status '{status}' for {filename}.")

        # Missing or truncated patch on modified/added file
        if status in ("added", "modified") and "patch" not in f and not f.get("is_binary"):
            blockers.append(f"Missing patch diff for {filename}.")

    # Evaluate Auditor report if present
    if auditor_report:
        report_status = auditor_report.get("status", "")
        findings = auditor_report.get("findings", [])
        limitations = auditor_report.get("limitations", [])

        if report_status == "PASS" and (findings or limitations):
            blockers.append("Auditor report status PASS cannot carry findings or limitations.")

        p0_p1 = [find for find in findings if find.get("severity") in ("P0", "P1", "CRITICAL", "HIGH")]
        if p0_p1:
            desc = ", ".join(f"{item.get('rule', item.get('rule_id', 'BUG'))}: {item.get('explanation', item.get('detail', ''))[:80]}" for item in p0_p1[:3])
            blockers.append(f"Auditor reported {len(p0_p1)} unresolved high-severity finding(s): {desc}")

        # Check snapshot binding (mandatory frozen base/head/diff)
        rep_base = auditor_report.get("base_sha")
        expected_base = pr_data.get("base_sha")
        if expected_base:
            if not rep_base:
                blockers.append("Auditor report missing mandatory base_sha snapshot binding.")
            elif rep_base != expected_base:
                blockers.append(f"Auditor report base_sha ({rep_base[:8]}) does not match PR base_sha ({expected_base[:8]}).")

        rep_head = auditor_report.get("head_sha")
        expected_head = pr_data.get("head_sha")
        if expected_head:
            if not rep_head:
                blockers.append("Auditor report missing mandatory head_sha snapshot binding.")
            elif rep_head != expected_head:
                blockers.append(f"Auditor report head_sha ({rep_head[:8]}) does not match PR head_sha ({expected_head[:8]}).")

        rep_diff = auditor_report.get("diff_sha256")
        if expected_diff_sha256:
            valid_diffs = (
                set(expected_diff_sha256)
                if isinstance(expected_diff_sha256, (set, list, tuple))
                else {expected_diff_sha256}
            )
            if not rep_diff:
                blockers.append("Auditor report missing mandatory diff_sha256 snapshot binding.")
            elif rep_diff not in valid_diffs:
                blockers.append("Auditor report diff_sha256 does not match PR diff snapshot.")

        # Check diff.patch receipt hash in rule results
        if expected_diff_sha256:
            valid_diffs = (
                set(expected_diff_sha256)
                if isinstance(expected_diff_sha256, (set, list, tuple))
                else {expected_diff_sha256}
            )
            for item in auditor_report.get("rule_results", []):
                if isinstance(item, dict):
                    for ref in item.get("evidence", []):
                        if isinstance(ref, dict) and ref.get("receipt_path") == "diff.patch":
                            if ref.get("receipt_sha256") not in valid_diffs:
                                blockers.append("Auditor rule evidence diff.patch hash does not match PR diff snapshot.")
                                break

        # Check coverage
        required_paths = {f.get("filename", "") for f in files}
        reviewed_scope = set(auditor_report.get("reviewed_scope", []))
        if required_paths and reviewed_scope != required_paths:
            missing = required_paths - reviewed_scope
            extra = reviewed_scope - required_paths
            blockers.append(f"Auditor report reviewed_scope does not match changed files (missing: {sorted(missing)[:3]}, extra: {sorted(extra)[:3]}).")

        # Check per-rule coverage if rule results are present
        if rule_selection and "rule_results" in auditor_report:
            raw_rules = rule_selection.get("selected_ids", rule_selection.get("rules", []))
            expected_ids = set()
            for item in raw_rules:
                if isinstance(item, dict):
                    expected_ids.add(item.get("rule_id", ""))
                elif isinstance(item, str):
                    expected_ids.add(item)
            covered_ids = {r.get("rule_id") for r in auditor_report.get("rule_results", []) if isinstance(r, dict)}
            missing = expected_ids - covered_ids
            if missing:
                blockers.append(f"Auditor report missing per-rule results for Rule IDs: {', '.join(sorted(missing)[:5])}.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else "No git conflict markers; diff structure valid; correctness checks pass."
    return {"gate": "PR-04 CORRECTNESS", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr05_security(
    pr_data: dict[str, Any],
) -> dict[str, Any]:
    """PR-05 SECURITY (Static scan): Secret scanning, prompt injection defense."""
    blockers: list[str] = []
    files = pr_data.get("files", [])

    # 1. Scan added patch lines for secrets
    for f in files:
        patch = f.get("patch", "")
        if patch:
            for line in patch.splitlines():
                if line.startswith("+") and not line.startswith("+++"):
                    content = line[1:]
                    if PRIVATE_KEY_REGEX.search(content) or TOKEN_REGEX.search(content) or PASSWORD_REGEX.search(content):
                        blockers.append(f"Potential credential or private key detected in diff of {f.get('filename')}.")
                        break

    # 2. Check untrusted text (PR body, comments) for prompt injection patterns
    untrusted_texts = [
        pr_data.get("body", ""),
        pr_data.get("title", ""),
    ]
    for c in pr_data.get("comments", []):
        untrusted_texts.append(c.get("body", ""))

    for text in untrusted_texts:
        if text and PROMPT_INJECTION_REGEX.search(text):
            blockers.append("Adversarial prompt injection pattern detected in untrusted PR text; command interpretation strictly denied.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else "Secret scan clean; untrusted text sanitized; no credential leaks."
    return {"gate": "PR-05 SECURITY", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr06_testing(
    check_runs: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """PR-06 TESTING: Automated CI workflow receipts, commit check-runs."""
    if check_runs is None or len(check_runs) == 0:
        return {
            "gate": "PR-06 TESTING",
            "status": GateStatus.NOT_VERIFIED.value,
            "summary": "No CI check-runs recorded for HEAD commit. Automated CI verification is pending or unconfigured.",
            "blockers": ["CI check-run receipts absent."],
        }

    failures: list[str] = []
    in_progress: list[str] = []
    passed: list[str] = []

    for cr in check_runs:
        name = cr.get("name", "unknown")
        status = cr.get("status", "")
        conclusion = cr.get("conclusion", "")

        if status != "completed":
            in_progress.append(name)
        elif conclusion in ("failure", "timed_out", "action_required"):
            failures.append(f"{name} ({conclusion})")
        elif conclusion in ("success", "neutral", "skipped"):
            passed.append(name)

    blockers: list[str] = []
    if failures:
        blockers.append(f"CI check-run failure(s): {', '.join(failures)}.")
    if in_progress:
        return {
            "gate": "PR-06 TESTING",
            "status": GateStatus.NOT_VERIFIED.value,
            "summary": f"CI check-runs still in progress: {', '.join(in_progress)}.",
            "blockers": [f"Checks in progress: {', '.join(in_progress)}"],
        }

    status = GateStatus.FAIL if failures else (GateStatus.BLOCKED if blockers else GateStatus.PASS)
    summary = "; ".join(blockers) if blockers else f"All {len(passed)} CI check-runs succeeded ({', '.join(passed[:4])})."
    return {"gate": "PR-06 TESTING", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr07_rf_hil(
    changed_files: Iterable[str],
    pr_data: dict[str, Any],
    hil_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """PR-07 RF/HIL: Distinction between computed ToA and measured HIL; explicit N/A for non-RF."""
    files = list(changed_files)
    rf_firmware_files = [
        f for f in files
        if f.startswith("firmware/") or f.startswith("hardware/") or f.startswith("contracts/radio-mac/")
    ]

    if not rf_firmware_files:
        return {
            "gate": "PR-07 RF/HIL",
            "status": GateStatus.NOT_APPLICABLE.value,
            "summary": "PR does not modify RF stack, MAC timing, SX1276 driver, or firmware hardware paths.",
            "blockers": [],
        }

    # For RF/firmware, check if HIL receipt exists and human RF sign-off is recorded
    blockers: list[str] = []
    if hil_receipt is None or hil_receipt.get("status") != "PASS":
        blockers.append("Hardware-in-the-Loop (HIL) test receipt absent; RF timing/duty-cycle must be empirically verified.")

    # Check human RF owner approval
    reviews = pr_data.get("reviews", [])
    author = pr_data.get("author", "")
    rf_approved = any(
        r.get("state", "").upper() == "APPROVED" and (r.get("user", {}).get("login") or r.get("author", "")) != author
        for r in reviews
    )
    if not rf_approved:
        blockers.append("Human Embedded/RF specialist sign-off required for firmware/radio modifications.")

    status = GateStatus.BLOCKED if blockers else GateStatus.PASS
    summary = "; ".join(blockers) if blockers else "RF/HIL verification and specialist review validated."
    return {"gate": "PR-07 RF/HIL", "status": status.value, "summary": summary, "blockers": blockers}


def eval_pr08_merge_integrity(
    pr_data: dict[str, Any],
    head_sha_at_start: str,
    head_sha_at_end: str,
    ruleset_status: str | None = None,
    base_sha_at_start: str | None = None,
    base_sha_at_end: str | None = None,
) -> dict[str, Any]:
    """PR-08 MERGE-INTEGRITY: TOCTOU race protection (HEAD and BASE), unresolved review threads, rulesets visibility."""
    blockers: list[str] = []
    changes_requested: list[str] = []

    # 1. TOCTOU check: PR head must not change during review
    if head_sha_at_start != head_sha_at_end:
        blockers.append(
            f"PR HEAD SHA race detected! Started review at {head_sha_at_start[:8]}, "
            f"but HEAD is now {head_sha_at_end[:8]}. Review is STALE."
        )

    # 2. TOCTOU check: PR base must not change during review
    if base_sha_at_start and base_sha_at_end and base_sha_at_start != base_sha_at_end:
        blockers.append(
            f"PR BASE SHA race detected! Started review at {base_sha_at_start[:8]}, "
            f"but BASE is now {base_sha_at_end[:8]}. Review is STALE."
        )

    # 3. Check for unresolved review threads or outstanding CHANGES_REQUESTED
    reviews = pr_data.get("reviews", [])
    for r in reviews:
        if r.get("state", "").upper() == "CHANGES_REQUESTED":
            reviewer = r.get("user", {}).get("login") or r.get("author", "reviewer")
            changes_requested.append(f"Outstanding CHANGES_REQUESTED review by @{reviewer}.")

    review_comments = pr_data.get("review_comments", [])
    unresolved_threads = [rc for rc in review_comments if rc.get("unresolved", False)]
    if unresolved_threads:
        changes_requested.append(f"{len(unresolved_threads)} unresolved conversation thread(s) remain on PR diff.")

    # 4. Ruleset / branch protection visibility note
    protection_note = ruleset_status or "MERGE_PROTECTION_NOT_VERIFIED"

    all_issues = blockers + changes_requested
    if blockers:
        status = GateStatus.BLOCKED
    elif changes_requested:
        status = GateStatus.CHANGES_REQUESTED
    else:
        status = GateStatus.PASS

    summary = "; ".join(all_issues) if all_issues else f"HEAD SHA verified immutable ({head_sha_at_end[:8]}); no unresolved threads; merge protection: {protection_note}."
    return {
        "gate": "PR-08 MERGE-INTEGRITY",
        "status": status.value,
        "summary": summary,
        "blockers": all_issues,
        "ruleset_visibility": protection_note,
    }


def evaluate_pr_policy(
    pr_data: dict[str, Any],
    linked_issue: dict[str, Any] | None,
    allowed_paths: list[str] | None,
    codeowners_content: str,
    rule_selection: dict[str, Any] | None,
    auditor_report: dict[str, Any] | None,
    check_runs: list[dict[str, Any]] | None,
    hil_receipt: dict[str, Any] | None,
    head_sha_at_start: str,
    head_sha_at_end: str,
    ruleset_status: str | None = None,
    base_sha_at_start: str | None = None,
    base_sha_at_end: str | None = None,
    expected_diff_sha256: str | None = None,
) -> dict[str, Any]:
    """Synthesize complete policy evaluation and determine Host verdict.

    Strict separation:
    - SECRET_SCAN_PASS (basic static regex scan) != SECURITY_REVIEW_PASS (independent specialist review).
    - READY_FOR_HUMAN_REVIEW indicates only ready to start human review, NOT ready to merge.
    - ready_to_merge is always False in automated reports.
    """
    changed_files = [f.get("filename", "") for f in pr_data.get("files", [])]
    author = pr_data.get("author", "")
    codeowners_rules = parse_codeowners(codeowners_content)
    risk = classify_risk(changed_files)
    policy_rec = get_approval_policy_recommendation(risk)

    # Evaluate all 8 gates
    g1 = eval_pr01_governance(pr_data, linked_issue, allowed_paths, codeowners_rules)
    g2 = eval_pr02_architecture_contract(changed_files, pr_data)
    g3 = eval_pr03_rule_id(rule_selection, changed_files, pr_data)
    g4 = eval_pr04_correctness(pr_data, auditor_report, rule_selection, expected_diff_sha256=expected_diff_sha256)
    g5 = eval_pr05_security(pr_data)
    g6 = eval_pr06_testing(check_runs)
    g7 = eval_pr07_rf_hil(changed_files, pr_data, hil_receipt)
    g8 = eval_pr08_merge_integrity(
        pr_data, head_sha_at_start, head_sha_at_end, ruleset_status,
        base_sha_at_start, base_sha_at_end
    )

    gates = [g1, g2, g3, g4, g5, g6, g7, g8]
    all_blockers = [b for g in gates for b in g.get("blockers", [])]

    # Automated check pass
    auto_check_pass = (
        g1["status"] == GateStatus.PASS.value and
        g3["status"] in (GateStatus.PASS.value, GateStatus.NOT_APPLICABLE.value) and
        g5["status"] == GateStatus.PASS.value and
        g6["status"] == GateStatus.PASS.value and
        g7["status"] in (GateStatus.PASS.value, GateStatus.NOT_APPLICABLE.value)
    )

    # R-03: Separate SECRET_SCAN_PASS from SECURITY_REVIEW_PASS
    secret_scan_pass = "PASS" if g5["status"] == GateStatus.PASS.value else "FAIL"

    # Evaluate SECURITY_REVIEW_PASS
    security_touched = any(is_security_sensitive_path(f) for f in changed_files)
    if not security_touched:
        security_review_pass = "NOT_APPLICABLE"
    else:
        # Check for independent security specialist sign-off or specialist receipt
        reviews = pr_data.get("reviews", [])
        security_approved = False
        for r in reviews:
            rev_name = r.get("user", {}).get("login") or r.get("author", "")
            rev_state = r.get("state", "").upper()
            if rev_state == "APPROVED" and rev_name != author:
                if rev_name in ("@security-lead", "security-lead", "architect-lead") or r.get("role") == "security_specialist":
                    security_approved = True

        if pr_data.get("security_receipt") and pr_data["security_receipt"].get("status") == "PASS":
            security_approved = True

        if security_approved:
            security_review_pass = "PASS"
        else:
            security_review_pass = "NOT_VERIFIED"
            if any((f.startswith("contracts/") or "crypto" in f.lower()) and not is_synthetic_fixture_path(f) for f in changed_files):
                all_blockers.append("Independent security review receipt or specialist sign-off absent for security-sensitive paths.")

    # R-02: Auditor evaluation
    ai_review_pass = "NOT_VERIFIED"
    if auditor_report:
        # Check author self-audit
        auditor_id = auditor_report.get("auditor_id")
        if auditor_id and auditor_id == author:
            all_blockers.append(f"Auditor self-review rejected: author '@{author}' cannot act as independent Auditor.")
            ai_review_pass = "FAIL"
        else:
            # Check secret leaks in auditor report
            report_str = json.dumps(auditor_report)
            if PRIVATE_KEY_REGEX.search(report_str) or TOKEN_REGEX.search(report_str):
                all_blockers.append("Credential or private key detected in auditor report output.")
                ai_review_pass = "FAIL"
            else:
                ai_review_pass = "PASS" if auditor_report.get("status") == "PASS" else "FAIL"

    # Human approval status
    valid_approvals = [
        r.get("user", {}).get("login") or r.get("author", "")
        for r in pr_data.get("reviews", [])
        if r.get("state", "").upper() == "APPROVED" and (r.get("user", {}).get("login") or r.get("author", "")) != author
    ]
    human_approved = "APPROVED" if len(valid_approvals) >= policy_rec["required_approvals"] else "PENDING"
    hil_rf_pass = g7["status"]

    # Compute Final Verdict
    if head_sha_at_start != head_sha_at_end or (base_sha_at_start and base_sha_at_end and base_sha_at_start != base_sha_at_end):
        verdict = HostVerdict.BLOCKED
    elif any(g["status"] == GateStatus.BLOCKED.value for g in (g1, g2, g3, g4, g5, g7, g8)):
        verdict = HostVerdict.BLOCKED
    elif g6["status"] == GateStatus.FAIL.value or g8["status"] == GateStatus.CHANGES_REQUESTED.value or any(r.get("state", "").upper() == "CHANGES_REQUESTED" for r in pr_data.get("reviews", [])):
        verdict = HostVerdict.CHANGES_REQUESTED
    elif any(g["status"] == GateStatus.NOT_VERIFIED.value for g in (g1, g3, g6)):
        verdict = HostVerdict.NOT_VERIFIED
    elif all_blockers:
        verdict = HostVerdict.BLOCKED
    else:
        verdict = HostVerdict.READY_FOR_HUMAN_REVIEW

    ruleset_note = ruleset_status or "MERGE_PROTECTION_NOT_VERIFIED"
    merge_active = "ENFORCED" if ("ENFORCED" in ruleset_note or "ACTIVE" in ruleset_note) else "NOT_VERIFIED"

    return {
        "verdict": verdict.value,
        "ready_to_merge": False,  # Never auto-merges
        "risk_level": risk.value,
        "policy_recommendation": policy_rec,
        "gates": gates,
        "blockers": all_blockers,
        "dimensions": {
            "AUTO_CHECK_PASS": auto_check_pass,
            "SECRET_SCAN_PASS": secret_scan_pass,
            "SECURITY_REVIEW_PASS": security_review_pass,
            "AI_REVIEW_PASS": ai_review_pass,
            "HUMAN_APPROVED": human_approved,
            "HIL_RF_PASS": hil_rf_pass,
            "MERGE_ENFORCEMENT_ACTIVE": merge_active,
        },
        "changed_files_count": len(changed_files),
        "required_codeowners": get_required_codeowners(codeowners_rules, changed_files),
    }
