"""P08-A Role & Control-Plane Integration (H2-ORC-01/02/05, OD-08/09).

Unifies Native Fast Lane Coordinator planning with deterministic Host admission,
role ACL enforcement, frozen per-run policy inputs for P08-B, dispatch leasing,
and budget/cancellation control inside the existing P04 SQLite Journal.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from .adapters.antigravity import AuditError, RUBRIC_DIMENSIONS, check_report as check_audit_report, validate_rubric
    from .agent_context import ContextGateError, load_context
    from .check import freeze_checks, run_checks
    from .feature_state import compute_candidate_snapshot
    from .observability import ObservabilityError, redact_data, redact_text, record_process_signal
    from .p1.process import ProcessBlocked, execute_checked
    from .p1.state import Journal, StateConflict
    from .p1.worktrees import WorktreeError, inspect_worktree
    from .quality_gates import evaluate as evaluate_quality_gates, inventory as inventory_repo
    from .scope import parse_allowed_paths, violations
    from .snapshot import REFERENCES as SNAPSHOT_REFERENCES, assemble, digest, unchanged
    from .standards_policy import StandardsError, select_rules
except ImportError:
    from adapters.antigravity import AuditError, RUBRIC_DIMENSIONS, check_report as check_audit_report, validate_rubric
    from agent_context import ContextGateError, load_context
    from check import freeze_checks, run_checks
    from feature_state import compute_candidate_snapshot
    from observability import ObservabilityError, redact_data, redact_text, record_process_signal
    from p1.process import ProcessBlocked, execute_checked
    from p1.state import Journal, StateConflict
    from p1.worktrees import WorktreeError, inspect_worktree
    from quality_gates import evaluate as evaluate_quality_gates, inventory as inventory_repo
    from scope import parse_allowed_paths, violations
    from snapshot import REFERENCES as SNAPSHOT_REFERENCES, assemble, digest, unchanged
    from standards_policy import StandardsError, select_rules

try:
    import harness_doctor
except ImportError:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    import harness_doctor

BRANCH_ISSUE_RE = re.compile(r"^(?:feature|fix|chore|research|docs)/([1-9][0-9]*)-[A-Za-z0-9_.-]+$")
PROTECTED_PATH_PREFIXES = (
    "contracts/",
    "docs/adr/",
    "firmware/components/sx1276_driver/",
    ".agent-harness/",
    ".agents/",
    "AGENTS.md",
)

VALID_ROLES = frozenset({"planner", "orchestrator", "maker", "host", "checker", "owner"})

ROLE_PERMISSIONS: dict[str, dict[str, frozenset[str]]] = {
    "planner": {
        "allowed": frozenset({
            "propose_scope",
            "propose_plan",
            "propose_rules",
            "activate_unit",
            "request_dispatch",
            "record_checkpoint",
        }),
        "prohibited": frozenset({
            "approve_scope",
            "approve_policy",
            "edit_candidate",
            "modify_verification_defs",
            "write_host_receipt",
            "certify_pass",
            "transition_unit_passing",
            "issue_verdict",
            "mutate_evidence",
            "merge_pr",
            "rf_tx",
            "flash_device",
            "override_hard_gate",
            "substitute_model_for_host_evidence",
        }),
    },
    "orchestrator": {
        "allowed": frozenset({
            "admit_run",
            "route_feedback",
            "request_dispatch",
            "request_cancel",
            "escalate",
            "record_checkpoint",
            "collect_receipts",
        }),
        "prohibited": frozenset({
            "approve_scope",
            "approve_policy",
            "edit_candidate",
            "modify_verification_defs",
            "write_host_receipt",
            "certify_pass",
            "transition_unit_passing",
            "issue_verdict",
            "mutate_evidence",
            "merge_pr",
            "rf_tx",
            "flash_device",
            "override_hard_gate",
            "substitute_model_for_host_evidence",
        }),
    },
    "maker": {
        "allowed": frozenset({
            "read_candidate",
            "edit_candidate",
            "run_local_check",
            "submit_worker_report",
        }),
        "prohibited": frozenset({
            "approve_scope",
            "approve_policy",
            "admit_run",
            "dispatch_role",
            "modify_verification_defs",
            "write_host_receipt",
            "certify_pass",
            "transition_unit_passing",
            "issue_verdict",
            "mutate_evidence",
            "merge_pr",
            "rf_tx",
            "flash_device",
            "override_hard_gate",
            "substitute_model_for_host_evidence",
        }),
    },
    "host": {
        "allowed": frozenset({
            "admit_run",
            "dispatch_role",
            "execute_checks",
            "write_host_receipt",
            "freeze_candidate",
            "transition_state",
            "transition_unit_passing",
            "enforce_budget",
            "cancel_run",
            "escalate",
            "record_signal",
            "record_checkpoint",
        }),
        "prohibited": frozenset({
            "approve_scope",
            "approve_policy",
            "edit_candidate",
            "issue_verdict",
            "merge_pr",
            "rf_tx",
            "flash_device",
            "override_hard_gate",
            "substitute_model_for_host_evidence",
        }),
    },
    "checker": {
        "allowed": frozenset({
            "read_frozen_candidate",
            "read_evidence",
            "execute_readonly_checks",
            "issue_verdict",
            "score_rubric",
        }),
        "prohibited": frozenset({
            "approve_scope",
            "approve_policy",
            "edit_candidate",
            "mutate_evidence",
            "modify_verification_defs",
            "write_host_receipt",
            "certify_pass",
            "transition_unit_passing",
            "dispatch_role",
            "merge_pr",
            "rf_tx",
            "flash_device",
            "override_hard_gate",
            "substitute_model_for_host_evidence",
        }),
    },
    "owner": {
        "allowed": frozenset({
            "approve_scope",
            "approve_policy",
            "authorize_protected_action",
            "merge_pr",
            "review_pr",
            "request_cancel",
        }),
        "prohibited": frozenset({
            "substitute_model_for_host_evidence",
        }),
    },
}

ROLE_ISOLATION_DISCLOSURE = {
    "logical_acl_enforced": True,
    "os_process_sandbox_for_native_ui": False,
    "native_full_access_mode": "SUPERVISED_ONLY",
    "note": (
        "Logical Role ACL and Host SHA/CAS gates do not establish OS/network/process isolation "
        "under interactive operator Full Access; native UI controls cannot be mechanically enforced "
        "by CLI instructions alone."
    ),
}


class ControlPlaneError(RuntimeError):
    """Base error for P08-A control-plane failures."""


class AdmissionError(ControlPlaneError):
    """Run failed mandatory admission prerequisites."""


class RoleAccessDenied(ControlPlaneError):
    """Role attempted an action outside its ACL or approved scope."""


class DuplicateDispatchError(ControlPlaneError):
    """Attempted to dispatch while an active dispatch lease is still held."""


class BudgetExhaustedError(ControlPlaneError):
    """Run reached or could not satisfy a frozen finite budget limit."""


class CapabilityError(ControlPlaneError):
    """Required role or provider capability is unavailable."""


class PolicyError(ControlPlaneError):
    """Per-run policy configuration or budget enforceability is invalid."""


@dataclass(frozen=True)
class RunPolicy:
    schema_version: str = "1.0"
    consecutive_passes_required: int = 1
    max_rounds: int = 1
    max_wall_seconds: int = 1800
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    require_token_budget: bool = False
    require_cost_budget: bool = False
    no_progress_threshold: int = 2
    wip_limit: int = 1
    sequential_only: bool = True
    cancellation_policy: str = "FAIL_CLOSED_PRESERVE_WORK"
    escalation_policy: str = "BLOCK_AND_ESCALATE_TO_OWNER"
    owner_approval_status: str = "PENDING_OWNER_APPROVAL"
    approved_by: str = ""
    human_approval_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_sha256(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_protected_path(path: str) -> bool:
    norm = path.lstrip("./")
    return any(
        norm == prefix if not prefix.endswith("/") else norm.startswith(prefix) or norm == prefix.rstrip("/")
        for prefix in PROTECTED_PATH_PREFIXES
    )


def _scope_covers_path(approved_scope: tuple[str, ...] | list[str], target_path: str) -> bool:
    if not target_path or target_path.startswith("/") or "\\" in target_path:
        return False
    parts = pathlib.PurePosixPath(target_path).parts
    if ".." in parts:
        return False
    return any(target_path.startswith(a) if a.endswith("/") else target_path == a for a in approved_scope)


def authorize_role_action(
    role: str,
    action: str,
    *,
    target_path: str | None = None,
    repo: pathlib.Path | None = None,
    approved_scope: tuple[str, ...] | list[str] = (),
    model_output_as_evidence: bool = False,
) -> dict[str, Any]:
    """Deterministically enforce Role ACL (planner, orchestrator, maker, host, checker, owner)."""
    if model_output_as_evidence:
        raise RoleAccessDenied("Model output cannot substitute for Host evidence")
    if role not in VALID_ROLES:
        raise RoleAccessDenied(f"Unknown control-plane role: {role!r}")
    perms = ROLE_PERMISSIONS[role]
    if action in perms["prohibited"] or action not in perms["allowed"]:
        raise RoleAccessDenied(f"Role {role!r} is not permitted to perform {action!r}")
    if role == "maker" and action == "edit_candidate":
        if not target_path or not approved_scope:
            raise RoleAccessDenied("Maker edit_candidate requires explicit target_path and approved_scope")
        if not _scope_covers_path(approved_scope, target_path):
            raise RoleAccessDenied(f"Maker edit denied outside approved scope: {target_path!r}")
        if repo is not None:
            errs = violations(repo, approved_scope, [target_path])
            if errs:
                raise RoleAccessDenied("; ".join(errs)[:240])
    return {
        "allowed": True,
        "role": role,
        "action": action,
        "control_layer": "logical_acl",
        "os_sandbox_enforced": False,
    }


def build_run_policy(
    *,
    consecutive_passes_required: int = 1,
    max_rounds: int = 1,
    max_wall_seconds: int = 1800,
    max_tokens: int | None = None,
    max_cost_usd: float | None = None,
    require_token_budget: bool = False,
    require_cost_budget: bool = False,
    no_progress_threshold: int = 2,
    wip_limit: int = 1,
    sequential_only: bool = True,
    cancellation_policy: str = "FAIL_CLOSED_PRESERVE_WORK",
    escalation_policy: str = "BLOCK_AND_ESCALATE_TO_OWNER",
    approved_by: str = "",
    token_metering_available: bool = False,
    cost_metering_available: bool = False,
) -> dict[str, Any]:
    """Validate and freeze per-run policy inputs for P08-A/P08-B without inventing approvals."""
    if wip_limit != 1 or not sequential_only:
        raise PolicyError("P08-A enforces sequential WIP=1 only; parallel fleet requires P09 approval")
    if type(consecutive_passes_required) is not int or consecutive_passes_required < 1 or consecutive_passes_required > 10:
        raise PolicyError("consecutive_passes_required must be an integer in 1..10")
    if type(max_rounds) is not int or max_rounds < 1 or max_rounds > 20:
        raise PolicyError("max_rounds must be a finite integer in 1..20")
    if max_rounds < consecutive_passes_required:
        raise PolicyError("max_rounds cannot be less than consecutive_passes_required")
    if type(max_wall_seconds) is not int or max_wall_seconds < 1 or max_wall_seconds > 86_400:
        raise PolicyError("max_wall_seconds must be an integer in 1..86400")
    if type(no_progress_threshold) is not int or no_progress_threshold < 1 or no_progress_threshold > 10:
        raise PolicyError("no_progress_threshold must be an integer in 1..10")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
        raise PolicyError("max_tokens must be a positive integer when specified")
    if max_cost_usd is not None and (isinstance(max_cost_usd, bool) or not isinstance(max_cost_usd, (int, float)) or max_cost_usd <= 0):
        raise PolicyError("max_cost_usd must be a positive number when specified")

    if require_token_budget and (max_tokens is None or not token_metering_available):
        raise PolicyError("Required enforceable token budget cannot be satisfied (token metering UNAVAILABLE)")
    if require_cost_budget and (max_cost_usd is None or not cost_metering_available):
        raise PolicyError("Required enforceable cost budget cannot be satisfied (cost metering UNAVAILABLE)")

    clean_approver = str(approved_by or "").strip()
    approval_status = "OWNER_APPROVED" if clean_approver else "PENDING_OWNER_APPROVAL"
    policy = RunPolicy(
        consecutive_passes_required=consecutive_passes_required,
        max_rounds=max_rounds,
        max_wall_seconds=max_wall_seconds,
        max_tokens=max_tokens,
        max_cost_usd=float(max_cost_usd) if max_cost_usd is not None else None,
        require_token_budget=bool(require_token_budget),
        require_cost_budget=bool(require_cost_budget),
        no_progress_threshold=no_progress_threshold,
        wip_limit=wip_limit,
        sequential_only=sequential_only,
        cancellation_policy=cancellation_policy,
        escalation_policy=escalation_policy,
        owner_approval_status=approval_status,
        approved_by=clean_approver,
        human_approval_required=True,
    )
    payload = policy.to_dict()
    payload["metric_availability"] = {
        "rounds": "AVAILABLE",
        "wall_seconds": "AVAILABLE",
        "no_progress": "AVAILABLE",
        "tokens": "AVAILABLE" if token_metering_available else "UNAVAILABLE",
        "cost_usd": "AVAILABLE" if cost_metering_available else "UNAVAILABLE",
    }
    payload["policy_sha256"] = _canonical_sha256(payload)
    return payload


def probe_role_capabilities(
    *,
    maker_provider: str = "auto",
    checker_provider: str = "auto",
    require_executable: bool = True,
    capability_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Probe supported role/provider capabilities and fail closed if required capability is missing."""
    overrides = capability_overrides or {}
    codex_path = overrides.get("codex_path", shutil.which("codex"))
    agy_path = overrides.get("agy_path", shutil.which("agy"))
    docker_ok = bool(overrides.get("docker_ok", shutil.which("docker") is not None))
    esp_idf_ok = bool(overrides.get("esp_idf_ok", False))
    mcp_sdk_ok = bool(overrides.get("mcp_sdk_ok", False))

    doctor_caps = harness_doctor.build_role_capabilities(
        ai_ok=bool(codex_path or agy_path),
        codex_path=codex_path,
        agy_path=agy_path,
        docker_ok=docker_ok,
        esp_idf_ok=esp_idf_ok,
        mcp_sdk_ok=mcp_sdk_ok,
    )

    maker_providers = {
        "codex": bool(codex_path),
        "native_supervised": bool(agy_path or codex_path or overrides.get("native_supervised")),
        "fixture": bool(overrides.get("fixture_maker", maker_provider == "fixture")),
    }
    checker_providers = {
        "agy": bool(agy_path),
        "native_subagent": bool(agy_path or overrides.get("native_subagent")),
        "fixture": bool(overrides.get("fixture_checker", checker_provider == "fixture")),
    }

    if maker_provider == "auto":
        selected_maker = next((k for k in ("codex", "native_supervised", "fixture") if maker_providers[k]), None)
    else:
        if maker_provider not in maker_providers:
            raise CapabilityError(f"Unsupported maker_provider: {maker_provider!r}")
        selected_maker = maker_provider if maker_providers[maker_provider] else None

    if checker_provider == "auto":
        selected_checker = next((k for k in ("agy", "native_subagent", "fixture") if checker_providers[k]), None)
    else:
        if checker_provider not in checker_providers:
            raise CapabilityError(f"Unsupported checker_provider: {checker_provider!r}")
        selected_checker = checker_provider if checker_providers[checker_provider] else None

    if require_executable and selected_maker is None:
        raise CapabilityError(f"Required Maker capability unavailable for provider={maker_provider!r}")
    if require_executable and selected_checker is None:
        raise CapabilityError(f"Required Checker capability unavailable for provider={checker_provider!r}")

    return {
        "maker_provider": selected_maker or "UNAVAILABLE",
        "checker_provider": selected_checker or "UNAVAILABLE",
        "maker_available": selected_maker is not None,
        "checker_available": selected_checker is not None,
        "host_verifier_available": True,
        "doctor_capabilities": doctor_caps,
        "isolation_disclosure": ROLE_ISOLATION_DISCLOSURE,
    }


def _fetch_live_issue(repo: pathlib.Path, issue: int) -> dict[str, Any]:
    if not shutil.which("gh"):
        raise AdmissionError("GitHub CLI (gh) unavailable")
    try:
        proc = subprocess.run(
            ["gh", "issue", "view", str(issue), "--json", "number,title,body,state,url"],
            cwd=repo,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=40,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdmissionError("Cannot query GitHub Issue") from exc
    if proc.returncode or len(proc.stdout) > 55_000:
        raise AdmissionError("GitHub Issue lookup failed or exceeded limit")
    data = json.loads(proc.stdout)
    if not isinstance(data, dict):
        raise AdmissionError("Malformed Issue response")
    return data


def _is_linked_git_worktree(repo: pathlib.Path) -> bool:
    """Return True only when repo is an isolated linked worktree (git-dir != git-common-dir)."""
    try:
        p_dir = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-dir"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15,
        )
        p_common = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AdmissionError("Cannot verify git worktree isolation") from exc
    if p_dir.returncode or p_common.returncode:
        raise AdmissionError("Cannot inspect git-dir / git-common-dir")
    git_dir = pathlib.Path(p_dir.stdout.strip())
    common_dir = pathlib.Path(p_common.stdout.strip())
    if not git_dir.is_absolute():
        git_dir = (repo / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    if not common_dir.is_absolute():
        common_dir = (repo / common_dir).resolve()
    else:
        common_dir = common_dir.resolve()
    return git_dir != common_dir


def _validate_approval(
    approval: dict[str, Any] | None,
    *,
    scope: tuple[str, ...],
    require_owner_approval: bool,
    require_protected_approval: bool,
    allow_fixture_mode: bool = False,
) -> dict[str, Any]:
    if not isinstance(approval, dict):
        raise AdmissionError("Missing explicit admission approval")
    status = str(approval.get("status", "")).strip()
    approved_by = str(approval.get("approved_by", "")).strip()
    if status in ("", "MISSING", "REJECTED", "DENIED"):
        raise AdmissionError(f"Admission rejected due to approval status={status or 'MISSING'}")
    has_owner_approval = status == "OWNER_APPROVED" and bool(approved_by)
    if require_owner_approval and not has_owner_approval:
        raise AdmissionError("Explicit Owner approval (approved_by) is required")
    touches_protected = any(_is_protected_path(p) for p in scope)
    if touches_protected and require_protected_approval and not has_owner_approval:
        raise AdmissionError("Protected path scope requires explicit Owner approval")
    if status == "SUPERVISED_ISSUE_OPEN":
        if not approval.get("isolated_pilot_attested", False):
            raise AdmissionError("Supervised Issue execution requires isolated_pilot_attested=True")
    elif status == "FIXTURE_APPROVED":
        if not allow_fixture_mode:
            raise AdmissionError("FIXTURE_APPROVED is restricted to explicit fixture mode")
    elif not has_owner_approval:
        raise AdmissionError(f"Unsupported admission approval status: {status!r}")
    return {
        "status": status,
        "approved_by": approved_by,
        "touches_protected": touches_protected,
        "human_merge_approval_required": True,
        "fixture_mode": bool(allow_fixture_mode),
    }


def admit_run(
    *,
    repo: pathlib.Path,
    issue: int,
    journal_path: pathlib.Path,
    run_id: str | None = None,
    base_sha: str | None = None,
    issue_data: dict[str, Any] | None = None,
    approval: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    check_profile: str = "software",
    maker_provider: str = "auto",
    checker_provider: str = "auto",
    capability_overrides: dict[str, Any] | None = None,
    require_isolated_worktree: bool = True,
    require_owner_approval: bool = False,
    require_protected_approval: bool = True,
    require_executable_capabilities: bool = True,
    allow_fixture_mode: bool = False,
    requested_rule_ids: list[str] | tuple[str, ...] = (),
) -> dict[str, Any]:
    """Admit a single scoped Issue run into the P08-A control plane (fail closed)."""
    authorize_role_action("orchestrator", "admit_run")
    authorize_role_action("host", "admit_run")

    if type(issue) is not int or issue < 1:
        raise AdmissionError("Issue must be a positive integer")
    if journal_path.is_symlink() or journal_path.parent.is_symlink():
        raise AdmissionError("Journal path must not be a symlink")

    root = repo.resolve(strict=True)
    if journal_path.resolve().is_relative_to(root):
        raise AdmissionError("Host Journal must reside outside candidate worktree")

    try:
        g0 = load_context(root)
    except ContextGateError as exc:
        raise AdmissionError(f"G0 AGENTS.md gate failed: {exc}") from exc

    raw_issue = issue_data if issue_data is not None else _fetch_live_issue(root, issue)
    if raw_issue.get("state") != "OPEN":
        raise AdmissionError("Issue must be OPEN")
    body = raw_issue.get("body")
    if not isinstance(body, str) or not body.strip():
        raise AdmissionError("Issue body missing")
    try:
        scope = parse_allowed_paths(body)
    except ValueError as exc:
        raise AdmissionError(f"Invalid Issue scope: {exc}") from exc
    issue_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()

    approval_record = _validate_approval(
        approval,
        scope=scope,
        require_owner_approval=require_owner_approval,
        require_protected_approval=require_protected_approval,
        allow_fixture_mode=allow_fixture_mode,
    )

    try:
        wt_info = inspect_worktree(root, expected_base_sha=base_sha)
    except WorktreeError as exc:
        raise AdmissionError(f"Isolated worktree check failed: {exc}") from exc
    branch = str(wt_info["branch"])
    branch_match = BRANCH_ISSUE_RE.fullmatch(branch)
    if not branch or branch == "main" or branch_match is None or int(branch_match.group(1)) != issue:
        raise AdmissionError(f"Branch {branch!r} must be a dedicated Issue #{issue} branch (never main)")
    if require_isolated_worktree and not allow_fixture_mode:
        if not _is_linked_git_worktree(root):
            raise AdmissionError("Isolated linked git worktree required; primary checkout is forbidden")
    if require_isolated_worktree and base_sha is not None and wt_info["base_is_ancestor"] is False:
        raise AdmissionError("Worktree HEAD does not descend from approved base_sha")

    resolved_base = base_sha or str(wt_info["head_sha"])
    snap = compute_candidate_snapshot(root, base_sha=resolved_base)
    if snap["changed_paths"]:
        scope_errs = violations(root, scope, snap["changed_paths"])
        if scope_errs:
            raise AdmissionError("Candidate has pre-existing out-of-scope paths: " + "; ".join(scope_errs)[:200])

    try:
        check_plan = freeze_checks(
            root,
            allowed_paths=scope,
            base_sha=resolved_base,
            profile=check_profile,
        )
    except ValueError as exc:
        raise AdmissionError(f"Cannot freeze verification policy: {exc}") from exc

    try:
        selection = select_rules(
            root,
            list(scope),
            requested_ids=list(requested_rule_ids),
            base=resolved_base,
            expected_source_sha=g0["source_sha"],
        )
    except StandardsError as exc:
        raise AdmissionError(f"Host standards selection failed: {exc}") from exc

    caps = probe_role_capabilities(
        maker_provider=maker_provider,
        checker_provider=checker_provider,
        require_executable=require_executable_capabilities,
        capability_overrides=capability_overrides,
    )

    frozen_policy = policy if policy is not None else build_run_policy()
    if "policy_sha256" not in frozen_policy:
        raise PolicyError("Frozen policy missing policy_sha256")
    if frozen_policy.get("wip_limit") != 1 or not frozen_policy.get("sequential_only"):
        raise PolicyError("Admitted policy must enforce sequential WIP=1")

    rid = run_id or (dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    admission_record = {
        "issue": issue,
        "issue_sha256": issue_sha256,
        "scope": list(scope),
        "approval": approval_record,
        "check_plan_sha256": check_plan["plan_sha256"],
        "selection_sha256": selection["selection_sha256"],
        "selected_ids": list(selection["selected_ids"]),
        "capabilities": {
            "maker_provider": caps["maker_provider"],
            "checker_provider": caps["checker_provider"],
            "isolation_disclosure": ROLE_ISOLATION_DISCLOSURE,
        },
        "admitted_at": _utc_now(),
    }

    with Journal(journal_path) as journal:
        created = journal.create_control_run(
            run_id=rid,
            issue=issue,
            source_sha=snap["source_sha"],
            base_sha=resolved_base,
            candidate_sha256=snap["candidate_sha256"],
            branch=branch,
            worktree=str(root),
            agents_sha256=g0["agents_sha256"],
            selection_sha256=selection["selection_sha256"],
            check_plan_sha256=check_plan["plan_sha256"],
            policy_sha256=frozen_policy["policy_sha256"],
            policy=frozen_policy,
            admission=admission_record,
            sequential_only=bool(frozen_policy["sequential_only"]),
            actor_role="host",
        )
        journal.record_checkpoint(
            issue=issue,
            run_id=rid,
            revision_sha=snap["source_sha"],
            candidate_sha256=snap["candidate_sha256"],
            branch=branch,
            worktree_rel=f"worktree:{root.name}",
            active_unit=None,
            blocker="",
            next_action=f"Dispatch Maker within frozen policy {frozen_policy['policy_sha256'][:12]}",
            decision_refs=("OD-08", "OD-09"),
            issue_sha256=issue_sha256,
            handoff_json=json.dumps({
                "run_id": rid,
                "issue": issue,
                "state": created["state"],
                "policy_sha256": frozen_policy["policy_sha256"],
            }, sort_keys=True),
        )

    record_process_signal(
        journal_path=journal_path,
        signal_type="process",
        category="control_plane",
        owning_domain="harness",
        status="PASS",
        captured=True,
        issue=issue,
        run_id=rid,
        check_id="admit_run",
        source_sha=snap["source_sha"],
        candidate_sha256=snap["candidate_sha256"],
        exit_code=0,
        finding=f"Admitted Issue #{issue} run {rid} (WIP=1)",
        evidence_ref={"run_id": rid, "policy_sha256": frozen_policy["policy_sha256"]},
    )

    return {
        "run": created,
        "g0": {k: g0[k] for k in ("status", "source_sha", "git_blob_sha", "agents_sha256", "agents_bytes")},
        "check_plan": check_plan,
        "selection": selection,
        "capabilities": caps,
        "policy": frozen_policy,
        "admission": admission_record,
    }


def remaining_wall_seconds(run: dict[str, Any], *, elapsed_wall_seconds: float = 0.0) -> float:
    """Compute remaining cumulative wall-time budget for the run (never negative-pass)."""
    max_wall = float(run["policy"]["max_wall_seconds"])
    consumed_wall = float(run["budget_consumed"].get("wall_seconds", 0.0))
    return max_wall - (consumed_wall + max(0.0, float(elapsed_wall_seconds)))


def bound_subprocess_timeout(requested_timeout: int | float, remaining_wall_s: float) -> float:
    """Bound any subprocess timeout strictly by remaining cumulative wall budget."""
    if remaining_wall_s <= 0:
        raise BudgetExhaustedError("Remaining cumulative wall-time budget exhausted")
    return max(0.1, min(float(requested_timeout), float(remaining_wall_s)))


def _verify_budget_before_dispatch(
    journal: Journal,
    run: dict[str, Any],
    *,
    elapsed_wall_seconds: float,
) -> float:
    policy = run["policy"]
    consumed = run["budget_consumed"]
    rounds_used = int(run["round_num"])
    no_prog = int(run["no_progress_count"])
    total_wall = float(consumed.get("wall_seconds", 0.0)) + max(0.0, float(elapsed_wall_seconds))
    remaining = float(policy["max_wall_seconds"]) - total_wall

    reason = ""
    if rounds_used >= int(policy["max_rounds"]):
        reason = f"max_rounds exhausted ({rounds_used}/{policy['max_rounds']})"
    elif no_prog >= int(policy["no_progress_threshold"]):
        reason = f"no_progress_threshold reached ({no_prog}/{policy['no_progress_threshold']})"
    elif remaining <= 0.0:
        reason = f"max_wall_seconds exhausted ({total_wall:.1f}>={policy['max_wall_seconds']})"
    elif policy.get("require_token_budget") and consumed.get("tokens_used") is None:
        reason = "Required enforceable token budget unavailable"
    elif policy.get("max_tokens") is not None and consumed.get("tokens_used") is not None and int(consumed["tokens_used"]) >= int(policy["max_tokens"]):
        reason = f"max_tokens exhausted ({consumed['tokens_used']}/{policy['max_tokens']})"
    elif policy.get("require_cost_budget") and consumed.get("cost_usd") is None:
        reason = "Required enforceable cost budget unavailable"
    elif policy.get("max_cost_usd") is not None and consumed.get("cost_usd") is not None and float(consumed["cost_usd"]) >= float(policy["max_cost_usd"]):
        reason = f"max_cost_usd exhausted ({consumed['cost_usd']}/{policy['max_cost_usd']})"

    if reason:
        journal.transition_control_run(
            run["run_id"],
            expected=run["state"],
            next_state="ESCALATED",
            actor_role="host",
            action="budget_exhausted",
            clear_dispatch=True,
            detail={"reason": reason, "escalation_policy": policy["escalation_policy"]},
        )
        raise BudgetExhaustedError(reason)
    return remaining


def dispatch_role(
    *,
    repo: pathlib.Path,
    journal_path: pathlib.Path,
    run_id: str,
    role: str,
    requested_by: str = "orchestrator",
    elapsed_wall_seconds: float = 0.0,
) -> dict[str, Any]:
    """Acquire an exclusive single-active dispatch lease for Maker or Checker."""
    authorize_role_action(requested_by, "request_dispatch")
    authorize_role_action("host", "dispatch_role")
    if role not in ("maker", "checker"):
        raise RoleAccessDenied(f"Only 'maker' or 'checker' may be dispatched; got {role!r}")

    root = repo.resolve(strict=True)
    try:
        g0 = load_context(root)
    except ContextGateError as exc:
        raise AdmissionError(f"G0 AGENTS.md drift before dispatch: {exc}") from exc

    with Journal(journal_path) as journal:
        run = journal.get_control_run(run_id)
        if run["cancel_requested"] or run["state"] == "CANCELLED":
            raise ControlPlaneError("Run is cancelled; dispatch refused")
        if run["dispatch_token"]:
            raise DuplicateDispatchError(
                f"Duplicate dispatch blocked for run {run_id} (active_role={run['active_role']})"
            )
        if run["state"] not in ("ADMITTED", "REPAIR_REQUIRED"):
            raise DuplicateDispatchError(
                f"Cannot dispatch role {role!r} while run is in state {run['state']!r}"
            )
        if role == "maker" and int(run["consecutive_passes"]) > 0:
            raise RoleAccessDenied(
                "Maker dispatch forbidden between confirming passes on an immutable candidate"
            )
        if g0["agents_sha256"] != run["agents_sha256"]:
            journal.transition_control_run(
                run_id,
                expected=run["state"],
                next_state="BLOCKED",
                actor_role="host",
                action="g0_drift_blocked",
                detail={"expected_agents_sha256": run["agents_sha256"], "actual": g0["agents_sha256"]},
            )
            raise AdmissionError("AGENTS.md SHA-256 drifted since admission")
        snap = compute_candidate_snapshot(root, base_sha=run["base_sha"])
        if snap["branch"] != run["branch"]:
            journal.transition_control_run(
                run_id,
                expected=run["state"],
                next_state="BLOCKED",
                actor_role="host",
                action="branch_drift_blocked",
                detail={"expected_branch": run["branch"], "actual": snap["branch"]},
            )
            raise AdmissionError("Worktree branch drifted since admission")

        _verify_budget_before_dispatch(journal, run, elapsed_wall_seconds=elapsed_wall_seconds)

        token = uuid.uuid4().hex
        try:
            updated = journal.acquire_dispatch(
                run_id,
                expected_state=run["state"],
                role=role,
                actor_role="host",
                dispatch_token=token,
                detail={"requested_by": requested_by, "target_role": role},
            )
        except StateConflict as exc:
            raise DuplicateDispatchError(str(exc)) from exc

    record_process_signal(
        journal_path=journal_path,
        signal_type="process",
        category="control_plane",
        owning_domain="harness",
        status="PASS",
        captured=True,
        issue=updated["issue"],
        run_id=run_id,
        check_id=f"dispatch_{role}",
        source_sha=updated["source_sha"],
        candidate_sha256=updated["candidate_sha256"],
        exit_code=0,
        finding=f"Dispatched {role} (seq={updated['dispatch_seq']})",
        evidence_ref={"run_id": run_id, "dispatch_seq": updated["dispatch_seq"]},
    )
    return updated


def transition_state(
    *,
    journal_path: pathlib.Path,
    run_id: str,
    expected: str,
    next_state: str,
    actor_role: str = "host",
    action: str = "transition_state",
    dispatch_token: str | None = None,
    clear_dispatch: bool = False,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a role-checked CAS state transition in the Host Journal."""
    authorize_role_action(actor_role, "transition_state")
    if next_state == "READY_FOR_HUMAN_REVIEW":
        raise RoleAccessDenied("Use record_round_result with Host + Checker PASS to reach READY_FOR_HUMAN_REVIEW")
    with Journal(journal_path) as journal:
        return journal.transition_control_run(
            run_id,
            expected=expected,
            next_state=next_state,
            actor_role=actor_role,
            action=action,
            expected_dispatch_token=dispatch_token,
            clear_dispatch=clear_dispatch,
            detail=detail,
        )


def record_round_result(
    *,
    journal_path: pathlib.Path,
    run_id: str,
    dispatch_token: str,
    outcome: str,
    host_checks_passed: bool,
    checker_passed: bool,
    diff_sha256: str = "",
    candidate_sha256: str = "",
    policy_sha256: str = "",
    check_plan_sha256: str = "",
    selection_sha256: str = "",
    selected_ids: list[str] | tuple[str, ...] = (),
    checks_summary_sha256: str = "",
    manifest_sha256: str = "",
    auditor_report_sha256: str = "",
    rubric: dict[str, Any] | None = None,
    findings: list[dict[str, Any]] | None = None,
    repair_scope: list[str] | tuple[str, ...] = (),
    next_action: str = "",
    maker_dispatched: bool = True,
    confirming_pass: bool = False,
    checks_complete: bool = True,
    verdict: str = "",
    allow_empty_dispatch_in_verifying: bool = False,
    failure_sig: str = "",
    wall_elapsed_s: float = 0.0,
    tokens_used: int | None = None,
    cost_used: float | None = None,
    actor_role: str = "host",
) -> dict[str, Any]:
    """Host-owned round evaluation: updates budgets, streak binding, round history, and transitions safely."""
    authorize_role_action(actor_role, "enforce_budget")
    if outcome not in ("PASS", "REVISE", "FAIL", "TIMEOUT", "BLOCK"):
        raise ControlPlaneError(f"Invalid round outcome: {outcome!r}")

    with Journal(journal_path) as journal:
        run = journal.get_control_run(run_id)
        if run["cancel_requested"] or run["state"] == "CANCELLED":
            raise ControlPlaneError("Run is cancelled; round result refused")
        if not (allow_empty_dispatch_in_verifying and run["state"] == "VERIFYING" and confirming_pass):
            if not dispatch_token or run["dispatch_token"] != dispatch_token:
                raise StateConflict("Dispatch token mismatch when recording round result")
        policy = run["policy"]
        consumed = dict(run["budget_consumed"])
        new_round = int(run["round_num"]) + 1
        new_wall = round(float(consumed.get("wall_seconds", 0.0)) + max(0.0, float(wall_elapsed_s)), 3)

        if tokens_used is not None:
            prev_tok = consumed.get("tokens_used") or 0
            consumed["tokens_used"] = int(prev_tok) + int(tokens_used)
        if cost_used is not None:
            prev_cost = consumed.get("cost_usd") or 0.0
            consumed["cost_usd"] = round(float(prev_cost) + float(cost_used), 6)

        consumed["rounds"] = new_round
        consumed["wall_seconds"] = new_wall

        consec = int(run["consecutive_passes"])
        no_prog = int(run["no_progress_count"])
        last_sig = str(run["last_failure_sig"])
        last_diff = str(run["last_diff_sha256"])

        eff_cand = str(candidate_sha256 or run["candidate_sha256"])
        eff_diff = str(diff_sha256 or run["last_diff_sha256"])
        eff_pol = str(policy_sha256 or run["policy_sha256"])
        eff_plan = str(check_plan_sha256 or run["check_plan_sha256"])
        eff_sel = str(selection_sha256 or run["selection_sha256"])

        streak_cand = str(run.get("streak_candidate_sha256") or "")
        streak_diff = str(run.get("streak_diff_sha256") or "")
        streak_pol = str(run.get("streak_policy_sha256") or "")
        streak_plan = str(run.get("streak_check_plan_sha256") or "")
        streak_sel = str(run.get("streak_selection_sha256") or "")

        policy_tampered = (
            (bool(policy_sha256) and policy_sha256 != run["policy_sha256"])
            or (bool(check_plan_sha256) and check_plan_sha256 != run["check_plan_sha256"])
        )

        budget_reason = ""
        if policy.get("require_token_budget") and consumed.get("tokens_used") is None:
            budget_reason = "Required enforceable token budget unavailable"
        elif policy.get("max_tokens") is not None and consumed.get("tokens_used") is not None:
            if int(consumed["tokens_used"]) > int(policy["max_tokens"]):
                budget_reason = f"max_tokens exceeded ({consumed['tokens_used']}>{policy['max_tokens']})"
        if not budget_reason and policy.get("require_cost_budget") and consumed.get("cost_usd") is None:
            budget_reason = "Required enforceable cost budget unavailable"
        elif not budget_reason and policy.get("max_cost_usd") is not None and consumed.get("cost_usd") is not None:
            if float(consumed["cost_usd"]) > float(policy["max_cost_usd"]):
                budget_reason = f"max_cost_usd exceeded ({consumed['cost_usd']}>{policy['max_cost_usd']})"
        if not budget_reason and new_wall > float(policy["max_wall_seconds"]):
            budget_reason = f"max_wall_seconds exceeded ({new_wall}>{policy['max_wall_seconds']})"

        eff_outcome = outcome
        eff_verdict = verdict or (
            "ACCEPT" if outcome == "PASS" else ("BLOCK" if outcome == "BLOCK" else ("TIMEOUT" if outcome == "TIMEOUT" else "REVISE"))
        )
        new_streak_cand = ""
        new_streak_diff = ""
        new_streak_pol = ""
        new_streak_plan = ""
        new_streak_sel = ""

        if policy_tampered:
            next_state = "BLOCKED"
            action = "policy_or_check_plan_drift"
            consec = 0
            eff_outcome = "BLOCK"
            eff_verdict = "BLOCK"
            failure_sig = failure_sig or "policy_or_check_plan_drift"
        elif budget_reason:
            next_state = "ESCALATED"
            action = "budget_exhausted"
            consec = 0
            eff_verdict = "BLOCK"
        elif outcome == "TIMEOUT":
            next_state = "ESCALATED"
            action = "timeout_escalated"
            consec = 0
            eff_verdict = "TIMEOUT"
        elif outcome == "BLOCK":
            next_state = "BLOCKED"
            action = "round_blocked"
            consec = 0
            eff_verdict = "BLOCK"
        elif outcome == "PASS":
            if not (host_checks_passed and checker_passed and checks_complete):
                raise RoleAccessDenied("Cannot record PASS without complete Host checks and Checker PASS")
            if rubric is not None:
                try:
                    validate_rubric(
                        {
                            "status": "PASS",
                            "findings": list(findings or ()),
                            "limitations": [],
                            "rule_results": [],
                            "rubric": rubric,
                        }
                    )
                except AuditError as exc:
                    raise RoleAccessDenied(f"Cannot record PASS with invalid/non-ACCEPT rubric: {exc}") from exc
            drift_against_streak = consec > 0 and (
                (bool(streak_cand) and eff_cand != streak_cand)
                or (bool(streak_diff) and eff_diff != streak_diff)
                or (bool(streak_pol) and eff_pol != streak_pol)
                or (bool(streak_plan) and eff_plan != streak_plan)
                or (bool(streak_sel) and eff_sel != streak_sel)
            )
            if confirming_pass and drift_against_streak:
                consec = 0
                eff_outcome = "REVISE"
                eff_verdict = "REVISE"
                failure_sig = failure_sig or "confirming_pass_drift"
                repeated = (bool(failure_sig) and failure_sig == last_sig) or (
                    bool(eff_diff) and eff_diff == last_diff
                )
                no_prog = (no_prog + 1) if repeated else 1
                if no_prog >= int(policy["no_progress_threshold"]):
                    next_state = "ESCALATED"
                    action = "confirming_pass_drift_escalated"
                elif new_round >= int(policy["max_rounds"]):
                    next_state = "ESCALATED"
                    action = "confirming_pass_drift_max_rounds"
                else:
                    next_state = "REPAIR_REQUIRED"
                    action = "confirming_pass_drift_reset"
            else:
                if drift_against_streak:
                    # Different candidate/policy edit resets streak before counting this pass.
                    consec = 1
                else:
                    consec += 1
                no_prog = 0
                new_streak_cand = eff_cand
                new_streak_diff = eff_diff
                new_streak_pol = eff_pol
                new_streak_plan = eff_plan
                new_streak_sel = eff_sel
                if consec >= int(policy["consecutive_passes_required"]):
                    next_state = "READY_FOR_HUMAN_REVIEW"
                    action = "round_accepted_for_human_review"
                    eff_verdict = "ACCEPT"
                elif new_round >= int(policy["max_rounds"]):
                    next_state = "ESCALATED"
                    action = "max_rounds_before_consecutive_passes"
                    eff_verdict = "REVISE"
                else:
                    next_state = "REPAIR_REQUIRED"
                    action = "await_next_consecutive_pass"
                    eff_verdict = "ACCEPT"
        else:
            consec = 0
            repeated = (bool(failure_sig) and failure_sig == last_sig) or (
                bool(eff_diff) and eff_diff == last_diff
            )
            no_prog = (no_prog + 1) if repeated else 1
            if no_prog >= int(policy["no_progress_threshold"]):
                next_state = "ESCALATED"
                action = "no_progress_escalated"
            elif new_round >= int(policy["max_rounds"]):
                next_state = "ESCALATED"
                action = "max_rounds_exhausted"
            else:
                next_state = "REPAIR_REQUIRED"
                action = "revise_requested"
            eff_verdict = "REVISE"

        consumed["no_progress_count"] = no_prog
        consumed["consecutive_passes"] = consec

        resolved_next_action = next_action or (
            "Human review & merge decision (ready_to_merge=False)"
            if next_state == "READY_FOR_HUMAN_REVIEW"
            else (
                "Confirming verification & independent audit on immutable candidate (no Maker edit)"
                if next_state == "REPAIR_REQUIRED" and consec > 0
                else (
                    f"Targeted Maker repair in scope {list(repair_scope)}"
                    if next_state == "REPAIR_REQUIRED" and repair_scope
                    else f"Inspect {next_state} ({action})"
                )
            )
        )

        round_rec = {
            "round_num": new_round,
            "maker_dispatched": bool(maker_dispatched),
            "confirming_pass": bool(confirming_pass),
            "outcome": eff_outcome,
            "verdict": eff_verdict,
            "source_sha": str(run["source_sha"]),
            "base_sha": str(run["base_sha"]),
            "candidate_sha256": eff_cand,
            "diff_sha256": eff_diff,
            "policy_sha256": eff_pol,
            "check_plan_sha256": eff_plan,
            "selection_sha256": eff_sel,
            "agents_sha256": str(run["agents_sha256"]),
            "selected_ids": list(selected_ids or run["admission"].get("selected_ids", [])),
            "checks_summary_sha256": checks_summary_sha256,
            "manifest_sha256": manifest_sha256,
            "auditor_report_sha256": auditor_report_sha256,
            "host_checks_passed": bool(host_checks_passed),
            "checker_passed": bool(checker_passed),
            "rubric_decision": str((rubric or {}).get("decision", "NOT_VERIFIED")),
            "rubric_total_score": (rubric or {}).get("total_score"),
            "rubric_hard_gate_passed": (rubric or {}).get("hard_gate_passed"),
            "rubric": rubric or {},
            "findings": list(findings or ()),
            "repair_scope": list(repair_scope),
            "next_action": resolved_next_action,
            "failure_sig": failure_sig,
            "wall_elapsed_s": round(max(0.0, float(wall_elapsed_s)), 3),
            "cumulative_wall_s": new_wall,
            "tokens_used": tokens_used,
            "cost_used": cost_used,
            "consecutive_passes": consec,
            "no_progress_count": no_prog,
        }

        updated = journal.transition_control_run(
            run_id,
            expected=run["state"],
            next_state=next_state,
            actor_role=actor_role,
            action=action,
            expected_dispatch_token=(
                None if (allow_empty_dispatch_in_verifying and run["state"] == "VERIFYING" and confirming_pass) else dispatch_token
            ),
            clear_dispatch=True,
            update_fields={
                "round_num": new_round,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
                "last_failure_sig": failure_sig,
                "last_diff_sha256": eff_diff,
                "candidate_sha256": eff_cand,
                "streak_candidate_sha256": new_streak_cand,
                "streak_diff_sha256": new_streak_diff,
                "streak_policy_sha256": new_streak_pol,
                "streak_check_plan_sha256": new_streak_plan,
                "streak_selection_sha256": new_streak_sel,
                "budget_consumed_json": json.dumps(consumed, sort_keys=True),
            },
            detail={
                "outcome": eff_outcome,
                "verdict": eff_verdict,
                "budget_reason": budget_reason,
                "round_num": new_round,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
                "candidate_sha256": eff_cand,
            },
            round_record=round_rec,
        )
        journal.record_checkpoint(
            issue=updated["issue"],
            run_id=run_id,
            revision_sha=updated["source_sha"],
            candidate_sha256=updated["candidate_sha256"],
            branch=updated["branch"],
            worktree_rel=f"worktree:{pathlib.Path(updated['worktree']).name}",
            active_unit=None,
            blocker=budget_reason or failure_sig if next_state in ("BLOCKED", "ESCALATED") else "",
            next_action=resolved_next_action,
            decision_refs=("OD-08", "OD-09"),
            issue_sha256=updated["admission"].get("issue_sha256", ""),
            handoff_json=json.dumps({
                "run_id": run_id,
                "state": next_state,
                "round_num": new_round,
                "verdict": eff_verdict,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
                "candidate_sha256": eff_cand,
                "ready_to_merge": False,
            }, sort_keys=True),
        )

    sig_status = "PASS" if next_state == "READY_FOR_HUMAN_REVIEW" else (
        "BLOCKED" if next_state in ("BLOCKED", "ESCALATED") else "FAIL"
    )
    record_process_signal(
        journal_path=journal_path,
        signal_type="process",
        category="control_plane",
        owning_domain="harness",
        status=sig_status,
        captured=True,
        issue=updated["issue"],
        run_id=run_id,
        check_id=action,
        source_sha=updated["source_sha"],
        candidate_sha256=updated["candidate_sha256"],
        diff_sha256=eff_diff,
        duration_s=new_wall,
        exit_code=0 if next_state == "READY_FOR_HUMAN_REVIEW" else 1,
        finding=budget_reason or f"Round {new_round} ended in {next_state} ({action})",
        evidence_ref={"run_id": run_id, "round_num": new_round, "state": next_state, "verdict": eff_verdict},
    )
    if budget_reason:
        raise BudgetExhaustedError(budget_reason)
    return updated


def cancel_run(
    *,
    journal_path: pathlib.Path,
    run_id: str,
    requested_by: str = "owner",
    reason: str = "Cancelled by operator",
) -> dict[str, Any]:
    """Cancel an admitted/active run safely without destructive workspace resets."""
    authorize_role_action(requested_by, "request_cancel")
    authorize_role_action("host", "cancel_run")
    with Journal(journal_path) as journal:
        updated = journal.request_control_cancel(run_id, actor_role=requested_by, reason=reason)
        journal.record_checkpoint(
            issue=updated["issue"],
            run_id=run_id,
            revision_sha=updated["source_sha"],
            candidate_sha256=updated["candidate_sha256"],
            branch=updated["branch"],
            worktree_rel=f"worktree:{pathlib.Path(updated['worktree']).name}",
            active_unit=None,
            blocker=updated["cancel_reason"],
            next_action="Run cancelled; worktree preserved without reset",
            decision_refs=("OD-08", "OD-09"),
            issue_sha256=updated["admission"].get("issue_sha256", ""),
            handoff_json=json.dumps({
                "run_id": run_id,
                "state": "CANCELLED",
                "reason": updated["cancel_reason"],
            }, sort_keys=True),
        )
    record_process_signal(
        journal_path=journal_path,
        signal_type="process",
        category="control_plane",
        owning_domain="harness",
        status="CANCELLED",
        captured=True,
        issue=updated["issue"],
        run_id=run_id,
        check_id="cancel_run",
        source_sha=updated["source_sha"],
        candidate_sha256=updated["candidate_sha256"],
        exit_code=1,
        finding=updated["cancel_reason"] or "Run cancelled",
        evidence_ref={"run_id": run_id},
    )
    return updated


def _extract_repair_scope(
    findings: list[dict[str, Any]],
    approved_scope: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    """Return (in_scope_files, out_of_scope_files) referenced by findings."""
    in_scope: list[str] = []
    out_of_scope: list[str] = []
    for item in findings:
        fpath = str(item.get("file", "")).strip()
        if not fpath:
            continue
        if _scope_covers_path(approved_scope, fpath):
            if fpath not in in_scope:
                in_scope.append(fpath)
        else:
            if fpath not in out_of_scope:
                out_of_scope.append(fpath)
    return in_scope, out_of_scope


def build_rubric_report(
    *,
    decision: str,
    hard_gate_passed: bool,
    scores: dict[str, int] | None = None,
    evidence_refs: list[dict[str, str]] | None = None,
    findings_notes: dict[str, list[str]] | None = None,
    rationale: str = "Evaluated against Host receipts and frozen candidate.",
) -> dict[str, Any]:
    """Construct a schema-valid 6-dimension 0-2 rubric object."""
    default_score = 2 if decision == "ACCEPT" else (1 if decision == "REVISE" else 0)
    dims: dict[str, Any] = {}
    total = 0
    ev_list = list(evidence_refs or [])
    for dim in RUBRIC_DIMENSIONS:
        sc = int((scores or {}).get(dim, default_score))
        total += sc
        dims[dim] = {
            "score": sc,
            "rationale": rationale,
            "evidence": ev_list,
            "findings": list((findings_notes or {}).get(dim, [])),
        }
    return {
        "version": "1.0",
        "decision": decision,
        "hard_gate_passed": bool(hard_gate_passed),
        "total_score": total,
        "dimensions": dims,
    }


def classify_round_outcome(
    *,
    approved_scope: tuple[str, ...],
    expected_candidate_sha256: str,
    expected_diff_sha256: str,
    expected_source_sha: str,
    expected_planned_check_ids: list[str] | tuple[str, ...],
    checks_summary: dict[str, Any] | None,
    audit_report: dict[str, Any] | None = None,
    evidence_inventory: dict[str, str] | None = None,
    integrity_error: str = "",
    missing_prerequisites: list[str] | tuple[str, ...] = (),
    approval_denied: bool = False,
    newly_applicable_rules: bool = False,
    timed_out: bool = False,
) -> dict[str, Any]:
    """Deterministic Host verdict classification: ACCEPT / REVISE / BLOCK / TIMEOUT."""
    if approval_denied:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "approval_denied",
            "repair_scope": [],
            "next_action": "Owner approval required for protected/policy action",
        }
    if integrity_error:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": f"integrity_failed:{integrity_error[:80]}",
            "repair_scope": [],
            "next_action": "Inspect integrity/drift violation; do not accept",
        }
    if timed_out or (checks_summary is not None and checks_summary.get("timed_out")):
        return {
            "outcome": "TIMEOUT",
            "verdict": "TIMEOUT",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "wall_budget_or_subprocess_timeout",
            "repair_scope": [],
            "next_action": "Timeout reached; worktree preserved, escalate to Owner",
        }
    if missing_prerequisites:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "missing_prerequisites",
            "repair_scope": [],
            "next_action": "Install/authorize missing prerequisites before re-running",
        }

    if checks_summary is None:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "missing_host_checks_summary",
            "repair_scope": [],
            "next_action": "Host verification summary missing",
        }

    # Verify receipt binds to exact frozen candidate & diff
    if (
        checks_summary.get("candidate_sha256") != expected_candidate_sha256
        or checks_summary.get("diff_sha256") != expected_diff_sha256
        or checks_summary.get("source_sha") != expected_source_sha
    ):
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "candidate_receipt_mismatch",
            "repair_scope": [],
            "next_action": "Candidate/diff SHA in check receipt disagrees with frozen snapshot",
        }

    results_list = checks_summary.get("results") or []
    result_by_id = {str(r.get("check_id", "")): r for r in results_list if isinstance(r, dict)}
    missing_planned = [cid for cid in expected_planned_check_ids if cid not in result_by_id]
    not_verified_checks = [
        str(r.get("check_id", ""))
        for r in results_list
        if isinstance(r, dict) and r.get("status") in ("NOT_VERIFIED", "NOT_RUN", "WAIVED_WITH_REASON")
    ]
    failed_checks = [
        str(r.get("check_id", ""))
        for r in results_list
        if isinstance(r, dict) and r.get("status") not in ("PASS",)
    ]

    qg = checks_summary.get("quality_gates") or {}
    qg_auto = qg.get("auto_check")
    qg_results = {str(r.get("rule_id", "")): r for r in (qg.get("results") or []) if isinstance(r, dict)}
    qg_risks = set(qg.get("risks") or ())
    secret_fail = qg_results.get("SECRET-SCAN", {}).get("status") == "FAIL"
    if secret_fail:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "secret_scan_or_hard_gate_blocked",
            "repair_scope": [],
            "next_action": "Resolve P0 SECRET-SCAN / blocked quality gate (never waive)",
        }

    qg_unverified = any(
        r.get("status") in ("NOT_VERIFIED", "WAIVED_WITH_REASON")
        for r in qg_results.values()
        if r.get("rule_id") != "STANDARDS-CHECK"
        and (not qg_risks or r.get("rule_id") in ("SECRET-SCAN", "DIFF-CHECK") or r.get("status") == "WAIVED_WITH_REASON")
    )
    if qg_unverified:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "quality_gates_unverified_or_waived",
            "repair_scope": [],
            "next_action": "Unverified or waived quality gate rejected (never waive)",
        }

    if not_verified_checks:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": f"unverified_checks:{','.join(sorted(not_verified_checks))}",
            "repair_scope": [],
            "next_action": "Missing required check prerequisite/evidence; blocked",
        }

    if missing_planned:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": f"partial_check_set:{','.join(sorted(missing_planned))}",
            "repair_scope": [],
            "next_action": "Partial check set rejected; all planned checks must run",
        }

    if newly_applicable_rules:
        return {
            "outcome": "REVISE",
            "verdict": "REVISE",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": "newly_applicable_rules",
            "repair_scope": list(approved_scope),
            "next_action": "Inject newly triggered standards rules and re-run targeted Maker repair",
        }

    host_ok = (
        checks_summary.get("status") == "PASS"
        and int(checks_summary.get("exit_code", 1)) == 0
        and not failed_checks
        and (qg_auto in (None, "AUTO_CHECK_PASS"))
    )
    if not host_ok:
        sig = f"host_checks_failed:{','.join(sorted(failed_checks)) or qg_auto or 'fail'}"
        return {
            "outcome": "REVISE",
            "verdict": "REVISE",
            "host_checks_passed": False,
            "checker_passed": False,
            "checks_complete": False,
            "failure_sig": sig,
            "repair_scope": list(approved_scope),
            "next_action": "Targeted Maker repair of failing Host checks, then reverify",
        }

    if audit_report is None:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": "missing_checker_report",
            "repair_scope": [],
            "next_action": "Independent Checker evaluation missing (NOT_VERIFIED)",
        }

    findings = list(audit_report.get("findings") or [])
    in_scope_files, out_of_scope_files = _extract_repair_scope(findings, approved_scope)
    if out_of_scope_files:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": f"impossible_scope:{','.join(out_of_scope_files)}",
            "repair_scope": [],
            "next_action": "Findings require edits outside approved Issue scope; escalate for scope amendment",
        }

    rubric = audit_report.get("rubric")
    if not isinstance(rubric, dict):
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": "missing_rubric",
            "repair_scope": [],
            "next_action": "Checker report missing required 6-dimension rubric",
        }

    try:
        validate_rubric(audit_report, evidence_inventory=evidence_inventory)
    except AuditError as exc:
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": f"invalid_rubric:{str(exc)[:80]}",
            "repair_scope": [],
            "next_action": "Invalid or inconsistent rubric rejected",
        }

    decision = rubric["decision"]
    if not rubric["hard_gate_passed"] or decision == "BLOCK":
        return {
            "outcome": "BLOCK",
            "verdict": "BLOCK",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": "checker_hard_gate_block",
            "repair_scope": [],
            "next_action": "Hard gate / Checker BLOCK; human intervention required",
        }

    if audit_report.get("status") != "PASS" or decision == "REVISE" or findings:
        rules_hit = sorted({str(f.get("rule", "")) for f in findings if f.get("rule")})
        sig = f"checker_revise:{','.join(rules_hit) or audit_report.get('status')}"
        return {
            "outcome": "REVISE",
            "verdict": "REVISE",
            "host_checks_passed": True,
            "checker_passed": False,
            "checks_complete": True,
            "failure_sig": sig,
            "repair_scope": in_scope_files or list(approved_scope),
            "next_action": f"Targeted Maker repair for in-scope findings {in_scope_files or list(approved_scope)}",
        }

    return {
        "outcome": "PASS",
        "verdict": "ACCEPT",
        "host_checks_passed": True,
        "checker_passed": True,
        "checks_complete": True,
        "failure_sig": "",
        "repair_scope": [],
        "next_action": "Candidate verified & accepted by independent Checker",
    }


def _assemble_review_snapshot(
    root: pathlib.Path,
    snapshot_dir: pathlib.Path,
    changed_paths: list[str],
    diff_text: str,
    receipts: list[dict[str, Any]],
) -> dict[str, str]:
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if all((root / ref).exists() for ref in SNAPSHOT_REFERENCES):
        hashes = assemble(root, snapshot_dir, changed_paths, diff_text, receipts)
    else:
        hashes = {}
        for rel in sorted(changed_paths):
            src = root / rel
            if src.is_file() and not src.is_symlink():
                b = src.read_bytes()
                dst = snapshot_dir / "source" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(b)
                dst.chmod(0o444)
                hashes[rel] = digest(b)
        (snapshot_dir / "changes.patch").write_text(diff_text, encoding="utf-8")
        (snapshot_dir / "checks.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
        for fname in ("changes.patch", "checks.json"):
            (snapshot_dir / fname).chmod(0o444)
            hashes[fname] = digest((snapshot_dir / fname).read_bytes())
    schema_src = pathlib.Path(__file__).resolve().parent / "adapters" / "audit.schema.json"
    schema_dst = snapshot_dir / "audit.schema.json"
    schema_dst.write_bytes(schema_src.read_bytes() if schema_src.is_file() else b"{}\n")
    schema_dst.chmod(0o444)
    hashes["audit.schema.json"] = digest(schema_dst.read_bytes())
    return hashes


def run_maker_checker_loop(
    *,
    repo: pathlib.Path,
    issue: int,
    journal_path: pathlib.Path,
    evidence_dir: pathlib.Path,
    issue_data: dict[str, Any] | None = None,
    maker_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]],
    checker_fn: Callable[[pathlib.Path, dict[str, str], dict[str, Any]], dict[str, Any]] | None = None,
    verify_fn: Callable[[pathlib.Path, dict[str, Any], pathlib.Path, pathlib.Path, float], dict[str, Any]] | None = None,
    approval: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    base_sha: str | None = None,
    check_profile: str = "software",
    maker_provider: str = "fixture",
    checker_provider: str = "fixture",
    capability_overrides: dict[str, Any] | None = None,
    require_isolated_worktree: bool = True,
    require_protected_approval: bool = True,
    require_executable_capabilities: bool = True,
    allow_fixture_mode: bool = False,
    requested_rule_ids: list[str] | tuple[str, ...] = (),
    cancel_check: Callable[[int], bool] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
    requested_timeout: int = 300,
) -> dict[str, Any]:
    """Execute P08-B multi-round Maker -> Host verification -> independent Checker loop."""
    import time as _time

    clock = monotonic_fn or _time.monotonic
    root = repo.resolve(strict=True)
    if evidence_dir.is_symlink() or evidence_dir.resolve().is_relative_to(root):
        raise AdmissionError("Evidence directory must reside outside candidate worktree and not be a symlink")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    admitted = admit_run(
        repo=root,
        issue=issue,
        journal_path=journal_path,
        base_sha=base_sha,
        issue_data=issue_data,
        approval=approval,
        policy=policy or build_run_policy(consecutive_passes_required=1, max_rounds=1, max_wall_seconds=300),
        check_profile=check_profile,
        maker_provider=maker_provider,
        checker_provider=checker_provider,
        capability_overrides=capability_overrides,
        require_isolated_worktree=require_isolated_worktree,
        require_protected_approval=require_protected_approval,
        require_executable_capabilities=require_executable_capabilities,
        allow_fixture_mode=allow_fixture_mode,
        requested_rule_ids=requested_rule_ids,
    )
    run_id = admitted["run"]["run_id"]
    scope = tuple(admitted["admission"]["scope"])
    frozen_plan_path = evidence_dir / "frozen_check_plan.json"
    frozen_plan_path.write_text(json.dumps(admitted["check_plan"], indent=2, sort_keys=True), encoding="utf-8")
    (evidence_dir / "admission.json").write_text(json.dumps(redact_data(admitted["admission"]), indent=2, sort_keys=True), encoding="utf-8")
    (evidence_dir / "policy.json").write_text(json.dumps(admitted["policy"], indent=2, sort_keys=True), encoding="utf-8")

    feedback_findings: list[dict[str, Any]] = []
    feedback_summary = ""
    repair_scope: list[str] = list(scope)
    last_round_run = admitted["run"]
    selection = admitted["selection"]

    while True:
        round_started = clock()
        with Journal(journal_path) as journal:
            cur_run = journal.get_control_run(run_id)
        if cur_run["state"] in ("READY_FOR_HUMAN_REVIEW", "BLOCKED", "ESCALATED", "CANCELLED"):
            last_round_run = cur_run
            break
        if cur_run["cancel_requested"] or (cancel_check is not None and cancel_check(int(cur_run["round_num"]) + 1)):
            last_round_run = cancel_run(
                journal_path=journal_path,
                run_id=run_id,
                requested_by="owner",
                reason="Cancellation requested before round dispatch",
            )
            break

        try:
            rem_wall = remaining_wall_seconds(cur_run)
            if rem_wall <= 0:
                raise BudgetExhaustedError("Cumulative wall-time budget exhausted")
        except BudgetExhaustedError as exc:
            with Journal(journal_path) as journal:
                last_round_run = journal.transition_control_run(
                    run_id,
                    expected=cur_run["state"],
                    next_state="ESCALATED",
                    actor_role="host",
                    action="budget_exhausted",
                    clear_dispatch=True,
                    detail={"reason": str(exc)},
                )
            break

        confirming_pass = int(cur_run["consecutive_passes"]) > 0
        next_round_num = int(cur_run["round_num"]) + 1
        round_ev = evidence_dir / f"round-{next_round_num:02d}"
        round_ev.mkdir(parents=True, exist_ok=True)
        maker_token = ""
        maker_dispatched = False
        tokens_this_round: int | None = None
        cost_this_round: float | None = None

        if not confirming_pass:
            try:
                maker_run = dispatch_role(repo=root, journal_path=journal_path, run_id=run_id, role="maker")
            except (BudgetExhaustedError, ControlPlaneError):
                with Journal(journal_path) as journal:
                    last_round_run = journal.get_control_run(run_id)
                break
            maker_token = maker_run["dispatch_token"]
            maker_dispatched = True
            transition_state(
                journal_path=journal_path,
                run_id=run_id,
                expected="DISPATCHED",
                next_state="MAKER_RUNNING",
                actor_role="host",
                action="maker_started",
                dispatch_token=maker_token,
            )
            round_rem = bound_subprocess_timeout(requested_timeout, rem_wall - max(0.0, clock() - round_started))
            maker_ctx = {
                **admitted,
                "round_num": next_round_num,
                "selection": selection,
                "feedback": feedback_summary,
                "findings": list(feedback_findings),
                "repair_scope": list(repair_scope),
                "timeout_seconds": round_rem,
            }
            maker_res = maker_fn(root, maker_ctx) or {}
            if maker_res.get("tokens_used") is not None:
                tokens_this_round = int(maker_res["tokens_used"])
            if maker_res.get("cost_used") is not None:
                cost_this_round = float(maker_res["cost_used"])
            changed_path = str(maker_res.get("changed_path", ""))
            if changed_path:
                authorize_role_action("maker", "edit_candidate", target_path=changed_path, repo=root, approved_scope=scope)

            snap = compute_candidate_snapshot(root, base_sha=admitted["run"]["base_sha"])
            if snap["changed_paths"]:
                errs = violations(root, scope, snap["changed_paths"])
                if errs:
                    last_round_run = record_round_result(
                        journal_path=journal_path,
                        run_id=run_id,
                        dispatch_token=maker_token,
                        outcome="BLOCK",
                        verdict="BLOCK",
                        host_checks_passed=False,
                        checker_passed=False,
                        checks_complete=False,
                        candidate_sha256=snap["candidate_sha256"],
                        diff_sha256=snap["diff_sha256"],
                        policy_sha256=admitted["policy"]["policy_sha256"],
                        check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                        selection_sha256=selection["selection_sha256"],
                        selected_ids=selection["selected_ids"],
                        repair_scope=[],
                        next_action="Out-of-scope edit blocked; preserve worktree for human inspection",
                        maker_dispatched=True,
                        confirming_pass=False,
                        failure_sig="scope_violation",
                        wall_elapsed_s=max(0.0, clock() - round_started),
                        tokens_used=tokens_this_round,
                        cost_used=cost_this_round,
                    )
                    break

            refreshed = select_rules(
                root,
                list(scope),
                requested_ids=list(requested_rule_ids),
                base=admitted["run"]["base_sha"],
                expected_source_sha=admitted["g0"]["source_sha"],
            )
            newly_triggered = refreshed["agent_input_sha256"] != selection["agent_input_sha256"]
            selection = refreshed
            if newly_triggered:
                last_round_run = record_round_result(
                    journal_path=journal_path,
                    run_id=run_id,
                    dispatch_token=maker_token,
                    outcome="REVISE",
                    verdict="REVISE",
                    host_checks_passed=False,
                    checker_passed=False,
                    checks_complete=False,
                    candidate_sha256=snap["candidate_sha256"],
                    diff_sha256=snap["diff_sha256"],
                    policy_sha256=admitted["policy"]["policy_sha256"],
                    check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                    selection_sha256=selection["selection_sha256"],
                    selected_ids=selection["selected_ids"],
                    repair_scope=list(snap["changed_paths"] or scope),
                    next_action="Inject newly applicable rules and re-run Maker repair",
                    maker_dispatched=True,
                    confirming_pass=False,
                    failure_sig="newly_applicable_rules",
                    wall_elapsed_s=max(0.0, clock() - round_started),
                    tokens_used=tokens_this_round,
                    cost_used=cost_this_round,
                )
                feedback_summary = "Host detected newly applicable rules; re-inspect and repair in scope."
                feedback_findings = []
                continue

            transition_state(
                journal_path=journal_path,
                run_id=run_id,
                expected="MAKER_RUNNING",
                next_state="VERIFYING",
                actor_role="host",
                action="host_verifying",
                dispatch_token=maker_token,
            )
        else:
            # Confirming pass: NO Maker dispatch or edit allowed; verify same immutable candidate!
            snap = compute_candidate_snapshot(root, base_sha=admitted["run"]["base_sha"])
            if (
                snap["candidate_sha256"] != cur_run["streak_candidate_sha256"]
                or snap["diff_sha256"] != cur_run["streak_diff_sha256"]
            ):
                transition_state(
                    journal_path=journal_path,
                    run_id=run_id,
                    expected="REPAIR_REQUIRED",
                    next_state="VERIFYING",
                    actor_role="host",
                    action="confirming_host_verify_drift",
                )
                last_round_run = record_round_result(
                    journal_path=journal_path,
                    run_id=run_id,
                    dispatch_token="",
                    allow_empty_dispatch_in_verifying=True,
                    outcome="REVISE",
                    verdict="REVISE",
                    host_checks_passed=False,
                    checker_passed=False,
                    checks_complete=False,
                    candidate_sha256=snap["candidate_sha256"],
                    diff_sha256=snap["diff_sha256"],
                    policy_sha256=admitted["policy"]["policy_sha256"],
                    check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                    selection_sha256=selection["selection_sha256"],
                    selected_ids=selection["selected_ids"],
                    repair_scope=list(scope),
                    next_action="Candidate drifted between confirming passes; streak reset",
                    maker_dispatched=False,
                    confirming_pass=True,
                    failure_sig="confirming_pass_candidate_drift",
                    wall_elapsed_s=max(0.0, clock() - round_started),
                )
                feedback_summary = "Candidate changed before confirming pass; streak reset."
                feedback_findings = []
                continue
            transition_state(
                journal_path=journal_path,
                run_id=run_id,
                expected="REPAIR_REQUIRED",
                next_state="VERIFYING",
                actor_role="host",
                action="confirming_host_verifying",
            )

        # 2. Host Verification Phase (frozen check plan + full diff impact, bounded by remaining wall)
        try:
            ver_rem = bound_subprocess_timeout(requested_timeout, rem_wall - max(0.0, clock() - round_started))
        except BudgetExhaustedError as exc:
            last_round_run = record_round_result(
                journal_path=journal_path,
                run_id=run_id,
                dispatch_token=maker_token,
                allow_empty_dispatch_in_verifying=confirming_pass,
                outcome="TIMEOUT",
                verdict="TIMEOUT",
                host_checks_passed=False,
                checker_passed=False,
                checks_complete=False,
                candidate_sha256=snap["candidate_sha256"],
                diff_sha256=snap["diff_sha256"],
                policy_sha256=admitted["policy"]["policy_sha256"],
                check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                selection_sha256=selection["selection_sha256"],
                selected_ids=selection["selected_ids"],
                next_action=str(exc),
                maker_dispatched=maker_dispatched,
                confirming_pass=confirming_pass,
                failure_sig="wall_budget_exhausted_before_verify",
                wall_elapsed_s=max(0.0, clock() - round_started),
                tokens_used=tokens_this_round,
                cost_used=cost_this_round,
            )
            break

        if verify_fn is not None:
            checks_summary = verify_fn(root, admitted, round_ev, frozen_plan_path, ver_rem)
        else:
            checks_summary = run_checks(
                root,
                base_sha=admitted["run"]["base_sha"],
                profile=check_profile,
                evidence_dir=round_ev,
                frozen_plan_path=frozen_plan_path,
                timeout=max(1, int(ver_rem)),
                max_total_seconds=ver_rem,
                run_quality_gates=True,
                journal_path=journal_path,
                issue=issue,
                run_id=run_id,
            )

        summary_bytes = json.dumps(checks_summary, indent=2, sort_keys=True).encode("utf-8")
        summary_path = round_ev / "checks_summary.json"
        if not summary_path.is_file():
            summary_path.write_bytes(summary_bytes)
        checks_summary_sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
        manifest_path_round = round_ev / "manifest.json"
        manifest_sha = hashlib.sha256(manifest_path_round.read_bytes()).hexdigest() if manifest_path_round.is_file() else ""
        evidence_inv = {"checks_summary.json": checks_summary_sha}
        if manifest_sha:
            evidence_inv["manifest.json"] = manifest_sha

        planned_ids = [str(c["check_id"]) for c in admitted["check_plan"]["checks"]]
        pre_cls = classify_round_outcome(
            approved_scope=scope,
            expected_candidate_sha256=snap["candidate_sha256"],
            expected_diff_sha256=snap["diff_sha256"],
            expected_source_sha=snap["source_sha"],
            expected_planned_check_ids=planned_ids,
            checks_summary=checks_summary,
            audit_report={"status": "PASS", "findings": [], "limitations": [], "rubric": build_rubric_report(decision="ACCEPT", hard_gate_passed=True)},
            evidence_inventory=None,
        )
        if pre_cls["outcome"] != "PASS":
            try:
                last_round_run = record_round_result(
                    journal_path=journal_path,
                    run_id=run_id,
                    dispatch_token=maker_token,
                    allow_empty_dispatch_in_verifying=confirming_pass,
                    outcome=pre_cls["outcome"],
                    verdict=pre_cls["verdict"],
                    host_checks_passed=pre_cls["host_checks_passed"],
                    checker_passed=False,
                    checks_complete=pre_cls["checks_complete"],
                    candidate_sha256=snap["candidate_sha256"],
                    diff_sha256=snap["diff_sha256"],
                    policy_sha256=admitted["policy"]["policy_sha256"],
                    check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                    selection_sha256=selection["selection_sha256"],
                    selected_ids=selection["selected_ids"],
                    checks_summary_sha256=checks_summary_sha,
                    manifest_sha256=manifest_sha,
                    repair_scope=pre_cls["repair_scope"],
                    next_action=pre_cls["next_action"],
                    maker_dispatched=maker_dispatched,
                    confirming_pass=confirming_pass,
                    failure_sig=pre_cls["failure_sig"],
                    wall_elapsed_s=max(0.0, clock() - round_started),
                    tokens_used=tokens_this_round,
                    cost_used=cost_this_round,
                )
            except BudgetExhaustedError:
                with Journal(journal_path) as journal:
                    last_round_run = journal.get_control_run(run_id)
                break
            if last_round_run["state"] in ("BLOCKED", "ESCALATED", "CANCELLED", "READY_FOR_HUMAN_REVIEW"):
                break
            feedback_summary = f"Host verification failed ({pre_cls['failure_sig']}). Repair in scope."
            feedback_findings = []
            repair_scope = pre_cls["repair_scope"] or list(scope)
            continue

        # Release Maker lease (if held) before dispatching fresh independent Checker
        with Journal(journal_path) as journal:
            journal.transition_control_run(
                run_id,
                expected="VERIFYING",
                next_state="REPAIR_REQUIRED",
                actor_role="host",
                action="confirming_checks_passed_prepare_checker" if confirming_pass else "maker_verified_ready_for_checker",
                expected_dispatch_token=maker_token if maker_dispatched else None,
                clear_dispatch=True,
                update_fields={"candidate_sha256": snap["candidate_sha256"], "last_diff_sha256": snap["diff_sha256"]},
            )

        # 3. Independent Checker Phase on frozen read-only snapshot
        try:
            checker_run = dispatch_role(repo=root, journal_path=journal_path, run_id=run_id, role="checker")
        except (BudgetExhaustedError, ControlPlaneError):
            with Journal(journal_path) as journal:
                last_round_run = journal.get_control_run(run_id)
            break
        checker_token = checker_run["dispatch_token"]
        transition_state(
            journal_path=journal_path,
            run_id=run_id,
            expected="DISPATCHED",
            next_state="CHECKING",
            actor_role="host",
            action="checker_started",
            dispatch_token=checker_token,
        )
        authorize_role_action("checker", "read_frozen_candidate")
        authorize_role_action("checker", "issue_verdict")
        authorize_role_action("checker", "score_rubric")

        diff_proc = subprocess.run(
            ["git", "-C", str(root), "diff", "--no-ext-diff", "--no-textconv", "--no-renames", admitted["run"]["base_sha"]],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=20,
        )
        snapshot_dir = round_ev / "frozen_snapshot"
        receipts_for_snap = checks_summary.get("results") or [checks_summary]
        hashes = _assemble_review_snapshot(root, snapshot_dir, list(snap["changed_paths"]), diff_proc.stdout, receipts_for_snap)

        audit_report: dict[str, Any] | None = None
        integrity_err = ""
        try:
            chk_rem = bound_subprocess_timeout(requested_timeout, rem_wall - max(0.0, clock() - round_started))
            if checker_fn is not None:
                checker_ctx = {
                    **admitted,
                    "round_num": next_round_num,
                    "selection": selection,
                    "confirming_pass": confirming_pass,
                    "timeout_seconds": chk_rem,
                }
                audit_report = checker_fn(snapshot_dir, evidence_inv, checker_ctx)
            else:
                ev_refs = [{"receipt_path": "checks_summary.json", "receipt_sha256": checks_summary_sha}]
                audit_report = {
                    "status": "PASS",
                    "findings": [],
                    "limitations": [],
                    "reviewed_scope": list(snap["changed_paths"]),
                    "selection_sha256": selection["selection_sha256"],
                    "rule_results": [
                        {
                            "rule_id": r["rule_id"],
                            "rule_sha256": r["rule_sha256"],
                            "status": "PASS",
                            "evidence": ev_refs,
                            "reason": "Verified against Host checks_summary.json",
                        }
                        for r in selection["rules"]
                    ],
                    "rubric": build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs),
                }
            if not unchanged(snapshot_dir, hashes):
                integrity_err = "Checker mutated frozen review snapshot"
            after_snap = compute_candidate_snapshot(root, base_sha=admitted["run"]["base_sha"])
            if after_snap["candidate_sha256"] != snap["candidate_sha256"] or after_snap["diff_sha256"] != snap["diff_sha256"]:
                integrity_err = "Candidate changed during Checker evaluation"
            if hashlib.sha256(summary_path.read_bytes()).hexdigest() != checks_summary_sha:
                integrity_err = "Host evidence mutated during Checker evaluation"
            g0_after = load_context(root)
            if g0_after["agents_sha256"] != admitted["g0"]["agents_sha256"]:
                integrity_err = "AGENTS.md drifted during Checker evaluation"
            if audit_report is not None and not integrity_err:
                check_audit_report(
                    audit_report,
                    set(snap["changed_paths"]),
                    required_rules=selection["rules"],
                    selection_sha256=selection["selection_sha256"],
                    evidence_inventory=evidence_inv,
                    require_rubric=True,
                )
        except BudgetExhaustedError as exc:
            last_round_run = record_round_result(
                journal_path=journal_path,
                run_id=run_id,
                dispatch_token=checker_token,
                outcome="TIMEOUT",
                verdict="TIMEOUT",
                host_checks_passed=True,
                checker_passed=False,
                checks_complete=True,
                candidate_sha256=snap["candidate_sha256"],
                diff_sha256=snap["diff_sha256"],
                policy_sha256=admitted["policy"]["policy_sha256"],
                check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                selection_sha256=selection["selection_sha256"],
                selected_ids=selection["selected_ids"],
                checks_summary_sha256=checks_summary_sha,
                manifest_sha256=manifest_sha,
                next_action=str(exc),
                maker_dispatched=maker_dispatched,
                confirming_pass=confirming_pass,
                failure_sig="wall_budget_exhausted_before_checker",
                wall_elapsed_s=max(0.0, clock() - round_started),
                tokens_used=tokens_this_round,
                cost_used=cost_this_round,
            )
            break
        except (AuditError, ContextGateError, ValueError) as exc:
            integrity_err = f"audit_validation_failed:{exc}"

        audit_bytes = json.dumps(audit_report or {"error": integrity_err}, indent=2, sort_keys=True).encode("utf-8")
        (round_ev / "audit_report.json").write_bytes(audit_bytes)
        (evidence_dir / "audit_report.json").write_bytes(audit_bytes)
        audit_sha = hashlib.sha256(audit_bytes).hexdigest()

        final_cls = classify_round_outcome(
            approved_scope=scope,
            expected_candidate_sha256=snap["candidate_sha256"],
            expected_diff_sha256=snap["diff_sha256"],
            expected_source_sha=snap["source_sha"],
            expected_planned_check_ids=planned_ids,
            checks_summary=checks_summary,
            audit_report=audit_report,
            evidence_inventory=evidence_inv,
            integrity_error=integrity_err,
        )
        findings_list = list((audit_report or {}).get("findings") or [])
        try:
            last_round_run = record_round_result(
                journal_path=journal_path,
                run_id=run_id,
                dispatch_token=checker_token,
                outcome=final_cls["outcome"],
                verdict=final_cls["verdict"],
                host_checks_passed=final_cls["host_checks_passed"],
                checker_passed=final_cls["checker_passed"],
                checks_complete=final_cls["checks_complete"],
                candidate_sha256=snap["candidate_sha256"],
                diff_sha256=snap["diff_sha256"],
                policy_sha256=admitted["policy"]["policy_sha256"],
                check_plan_sha256=admitted["check_plan"]["plan_sha256"],
                selection_sha256=selection["selection_sha256"],
                selected_ids=selection["selected_ids"],
                checks_summary_sha256=checks_summary_sha,
                manifest_sha256=manifest_sha,
                auditor_report_sha256=audit_sha,
                rubric=(audit_report or {}).get("rubric"),
                findings=findings_list,
                repair_scope=final_cls["repair_scope"],
                next_action=final_cls["next_action"],
                maker_dispatched=maker_dispatched,
                confirming_pass=confirming_pass,
                failure_sig=final_cls["failure_sig"],
                wall_elapsed_s=max(0.0, clock() - round_started),
                tokens_used=tokens_this_round,
                cost_used=cost_this_round,
            )
        except BudgetExhaustedError:
            with Journal(journal_path) as journal:
                last_round_run = journal.get_control_run(run_id)
            break

        if last_round_run["state"] in ("READY_FOR_HUMAN_REVIEW", "BLOCKED", "ESCALATED", "CANCELLED"):
            break
        if int(last_round_run["consecutive_passes"]) > 0:
            feedback_summary = "Confirming verification & independent audit required on unchanged candidate."
            feedback_findings = []
            repair_scope = []
        else:
            feedback_findings = findings_list
            repair_scope = final_cls["repair_scope"] or list(scope)
            feedback_summary = f"Resolve only these in-scope findings: {json.dumps(findings_list)[:1200]}"

    with Journal(journal_path) as journal:
        events = journal.control_events(run_id)
        rounds = journal.list_control_rounds(run_id)
    summary = {
        "run_id": run_id,
        "issue": issue,
        "state": last_round_run["state"],
        "round_num": last_round_run["round_num"],
        "consecutive_passes": last_round_run["consecutive_passes"],
        "no_progress_count": last_round_run["no_progress_count"],
        "ready_to_merge": False,
        "human_approval_required": True,
        "policy_sha256": admitted["policy"]["policy_sha256"],
        "owner_approval_status": admitted["policy"]["owner_approval_status"],
        "candidate_sha256": last_round_run["candidate_sha256"],
        "rounds": rounds,
        "events": events,
        "isolation_disclosure": ROLE_ISOLATION_DISCLOSURE,
        "mode": "FIXTURE_CONTROLLED" if allow_fixture_mode else "REAL_EXECUTION",
    }
    (evidence_dir / "control_plane_summary.json").write_text(
        json.dumps(redact_data(summary), indent=2, sort_keys=True), encoding="utf-8"
    )
    return summary


def run_controlled_dispatch(
    *,
    repo: pathlib.Path,
    issue: int,
    journal_path: pathlib.Path,
    evidence_dir: pathlib.Path,
    issue_data: dict[str, Any],
    maker_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]],
    checker_fn: Callable[[pathlib.Path, dict[str, str], dict[str, Any]], dict[str, Any]] | None = None,
    approval: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    base_sha: str | None = None,
) -> dict[str, Any]:
    """Execute a controlled, non-destructive end-to-end fixture dispatch route with external receipts."""
    root = repo.resolve(strict=True)
    if evidence_dir.is_symlink() or evidence_dir.resolve().is_relative_to(root):
        raise AdmissionError("Evidence directory must reside outside candidate worktree and not be a symlink")
    evidence_dir.mkdir(parents=True, exist_ok=True)

    admitted = admit_run(
        repo=root,
        issue=issue,
        journal_path=journal_path,
        base_sha=base_sha,
        issue_data=issue_data,
        approval=approval or {"status": "FIXTURE_APPROVED", "approved_by": "fixture-owner", "isolated_pilot_attested": True},
        policy=policy or build_run_policy(consecutive_passes_required=1, max_rounds=1, max_wall_seconds=300),
        maker_provider="fixture",
        checker_provider="fixture",
        capability_overrides={"fixture_maker": True, "fixture_checker": True},
        require_isolated_worktree=False,
        require_protected_approval=False,
        allow_fixture_mode=True,
    )
    run_id = admitted["run"]["run_id"]
    scope = tuple(admitted["admission"]["scope"])
    (evidence_dir / "admission.json").write_text(json.dumps(redact_data(admitted["admission"]), indent=2, sort_keys=True), encoding="utf-8")
    (evidence_dir / "policy.json").write_text(json.dumps(admitted["policy"], indent=2, sort_keys=True), encoding="utf-8")

    # 1. Dispatch Maker
    maker_run = dispatch_role(repo=root, journal_path=journal_path, run_id=run_id, role="maker")
    maker_token = maker_run["dispatch_token"]
    transition_state(
        journal_path=journal_path,
        run_id=run_id,
        expected="DISPATCHED",
        next_state="MAKER_RUNNING",
        actor_role="host",
        action="maker_started",
        dispatch_token=maker_token,
    )
    maker_res = maker_fn(root, admitted)
    changed_path = str(maker_res.get("changed_path", ""))
    if changed_path:
        authorize_role_action("maker", "edit_candidate", target_path=changed_path, repo=root, approved_scope=scope)

    snap = compute_candidate_snapshot(root, base_sha=admitted["run"]["base_sha"])
    if snap["changed_paths"]:
        errs = violations(root, scope, snap["changed_paths"])
        if errs:
            transition_state(
                journal_path=journal_path,
                run_id=run_id,
                expected="MAKER_RUNNING",
                next_state="BLOCKED",
                actor_role="host",
                action="scope_violation",
                dispatch_token=maker_token,
                clear_dispatch=True,
                detail={"errors": errs},
            )
            raise RoleAccessDenied("; ".join(errs)[:240])

    # 2. Host deterministic verification using safe bounded fixture binary
    transition_state(
        journal_path=journal_path,
        run_id=run_id,
        expected="MAKER_RUNNING",
        next_state="VERIFYING",
        actor_role="host",
        action="host_verifying",
        dispatch_token=maker_token,
    )
    proc_receipt = execute_checked(["true"], root, timeout=15, execution_id=f"ctrl-{run_id[:16]}")
    checks_summary = {
        "run_id": run_id,
        "issue": issue,
        "source_sha": snap["source_sha"],
        "candidate_sha256": snap["candidate_sha256"],
        "diff_sha256": snap["diff_sha256"],
        "fixture_receipt": proc_receipt.json(),
        "status": "PASS" if proc_receipt.exit_code == 0 else "FAIL",
    }
    checks_bytes = json.dumps(checks_summary, indent=2, sort_keys=True).encode("utf-8")
    (evidence_dir / "checks_summary.json").write_bytes(checks_bytes)
    checks_sha = hashlib.sha256(checks_bytes).hexdigest()
    evidence_inv = {"checks_summary.json": checks_sha}

    # Release maker dispatch into REPAIR_REQUIRED so checker can acquire fresh dispatch
    with Journal(journal_path) as journal:
        journal.transition_control_run(
            run_id,
            expected="VERIFYING",
            next_state="REPAIR_REQUIRED",
            actor_role="host",
            action="maker_verified_ready_for_checker",
            expected_dispatch_token=maker_token,
            clear_dispatch=True,
            update_fields={"candidate_sha256": snap["candidate_sha256"], "last_diff_sha256": snap["diff_sha256"]},
        )

    # 3. Dispatch Fresh Checker on frozen snapshot
    checker_run = dispatch_role(repo=root, journal_path=journal_path, run_id=run_id, role="checker")
    checker_token = checker_run["dispatch_token"]
    transition_state(
        journal_path=journal_path,
        run_id=run_id,
        expected="DISPATCHED",
        next_state="CHECKING",
        actor_role="host",
        action="checker_started",
        dispatch_token=checker_token,
    )
    authorize_role_action("checker", "read_frozen_candidate")
    authorize_role_action("checker", "issue_verdict")

    diff_proc = subprocess.run(
        ["git", "-C", str(root), "diff", "--no-ext-diff", "--no-textconv", "--no-renames", admitted["run"]["base_sha"]],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    snapshot_dir = evidence_dir / "frozen_snapshot"
    hashes = _assemble_review_snapshot(root, snapshot_dir, list(snap["changed_paths"]), diff_proc.stdout, [proc_receipt.json()])
    if checker_fn is not None:
        audit_report = checker_fn(snapshot_dir, evidence_inv, admitted)
    else:
        ev_refs = [{"receipt_path": "checks_summary.json", "receipt_sha256": checks_sha}]
        audit_report = {
            "status": "PASS",
            "findings": [],
            "limitations": ["Controlled non-destructive fixture verification only; native UI isolation NOT_VERIFIED"],
            "reviewed_scope": list(snap["changed_paths"]),
            "selection_sha256": admitted["selection"]["selection_sha256"],
            "rule_results": [],
            "rubric": build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs),
        }
    if not unchanged(snapshot_dir, hashes):
        raise RoleAccessDenied("Checker mutated frozen review snapshot")

    audit_bytes = json.dumps(audit_report, indent=2, sort_keys=True).encode("utf-8")
    (evidence_dir / "audit_report.json").write_bytes(audit_bytes)
    audit_sha = hashlib.sha256(audit_bytes).hexdigest()

    checker_ok = audit_report.get("status") == "PASS"
    final_run = record_round_result(
        journal_path=journal_path,
        run_id=run_id,
        dispatch_token=checker_token,
        outcome="PASS" if checker_ok else "REVISE",
        host_checks_passed=(proc_receipt.exit_code == 0),
        checker_passed=checker_ok,
        diff_sha256=snap["diff_sha256"],
        candidate_sha256=snap["candidate_sha256"],
        policy_sha256=admitted["policy"]["policy_sha256"],
        check_plan_sha256=admitted["check_plan"]["plan_sha256"],
        selection_sha256=admitted["selection"]["selection_sha256"],
        selected_ids=admitted["selection"]["selected_ids"],
        checks_summary_sha256=checks_sha,
        auditor_report_sha256=audit_sha,
        rubric=audit_report.get("rubric"),
        findings=audit_report.get("findings") or [],
        failure_sig="" if checker_ok else "checker_revise",
        wall_elapsed_s=proc_receipt.duration_s,
    )
    with Journal(journal_path) as journal:
        events = journal.control_events(run_id)
        rounds = journal.list_control_rounds(run_id)
    summary = {
        "run_id": run_id,
        "issue": issue,
        "state": final_run["state"],
        "ready_to_merge": False,
        "human_approval_required": True,
        "policy_sha256": admitted["policy"]["policy_sha256"],
        "owner_approval_status": admitted["policy"]["owner_approval_status"],
        "candidate_sha256": snap["candidate_sha256"],
        "evidence_inventory": evidence_inv,
        "rounds": rounds,
        "events": events,
        "isolation_disclosure": ROLE_ISOLATION_DISCLOSURE,
    }
    (evidence_dir / "control_plane_summary.json").write_text(json.dumps(redact_data(summary), indent=2, sort_keys=True), encoding="utf-8")
    return summary


def run_pilot_scenarios(
    *,
    journal_path: pathlib.Path,
    evidence_dir: pathlib.Path,
) -> dict[str, Any]:
    """Execute >=5 recorded P08-B pilot rounds across controlled scenarios in disposable repos."""
    import tempfile

    ev_root = evidence_dir.resolve()
    if journal_path.is_symlink() or ev_root.is_symlink():
        raise AdmissionError("Pilot journal and evidence directory must not be symlinks")
    ev_root.mkdir(parents=True, exist_ok=True)

    def _init_fixture_repo(base_tmp: pathlib.Path, name: str, issue_num: int) -> tuple[pathlib.Path, str]:
        repo_p = base_tmp / name
        repo_p.mkdir()
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.name", "P08B Pilot"],
            ["git", "config", "user.email", "p08b@example.invalid"],
        ):
            subprocess.run(cmd, cwd=repo_p, check=True, capture_output=True, timeout=15)
        (repo_p / "AGENTS.md").write_text("# Pilot AGENTS\n- Follow P08-B.\n", encoding="utf-8")
        (repo_p / "README.md").write_text("initial\n", encoding="utf-8")
        (repo_p / "scripts").mkdir(parents=True, exist_ok=True)
        (repo_p / "scripts" / "verify_structure.py").write_text(
            "import pathlib, sys\nsys.exit(0 if 'FIXED' in pathlib.Path('README.md').read_text() else 1)\n",
            encoding="utf-8",
        )
        for ref in SNAPSHOT_REFERENCES:
            ref_path = repo_p / ref
            if not ref_path.exists():
                ref_path.parent.mkdir(parents=True, exist_ok=True)
                ref_path.write_text("Read-only fixture reference.\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo_p, check=True, capture_output=True, timeout=15)
        subprocess.run(["git", "commit", "-qm", "pilot base"], cwd=repo_p, check=True, capture_output=True, timeout=15)
        base = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_p, check=True, capture_output=True, text=True, timeout=15
        ).stdout.strip()
        subprocess.run(["git", "checkout", "-qb", f"feature/{issue_num}-pilot"], cwd=repo_p, check=True, capture_output=True, timeout=15)
        return repo_p, base

    scenarios: list[dict[str, Any]] = []
    total_rounds = 0
    with tempfile.TemporaryDirectory(prefix="p08b-pilot-") as tmp:
        tmp_path = pathlib.Path(tmp)
        if ev_root.is_relative_to(tmp_path) or journal_path.resolve().is_relative_to(tmp_path):
            raise AdmissionError("Pilot state and evidence must reside outside temp repos")

        # Scenario 1 (2 rounds): Seeded Host check failure -> targeted repair -> actual check.py reverify -> ACCEPT
        r1_repo, r1_base = _init_fixture_repo(tmp_path, "s1_repair", 43901)
        s1_calls = {"n": 0}

        def _s1_maker(wt: pathlib.Path, ctx: dict[str, Any]) -> dict[str, Any]:
            s1_calls["n"] += 1
            text = "BROKEN\n" if s1_calls["n"] == 1 else "FIXED\n"
            (wt / "README.md").write_text(text, encoding="utf-8")
            return {"changed_path": "README.md"}

        def _s1_checker(_snap: pathlib.Path, ev_inv: dict[str, str], ctx: dict[str, Any]) -> dict[str, Any]:
            ev_refs = [{"receipt_path": k, "receipt_sha256": v} for k, v in sorted(ev_inv.items())]
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": ctx["selection"]["selection_sha256"],
                "rule_results": [],
                "rubric": build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs),
            }

        res1 = run_maker_checker_loop(
            repo=r1_repo,
            issue=43901,
            journal_path=journal_path,
            evidence_dir=ev_root / "scenario_1_seeded_fail_repair_accept",
            issue_data={"state": "OPEN", "title": "Pilot S1", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=_s1_maker,
            checker_fn=_s1_checker,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "pilot-fixture"},
            policy=build_run_policy(consecutive_passes_required=1, max_rounds=3, max_wall_seconds=120, no_progress_threshold=2),
            base_sha=r1_base,
            check_profile="quick",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False,
            require_protected_approval=False,
            allow_fixture_mode=True,
        )
        scenarios.append({"scenario": "seeded_fail_repair_accept", "state": res1["state"], "rounds": len(res1["rounds"]), "run_id": res1["run_id"]})
        total_rounds += len(res1["rounds"])

        # Scenario 2 (3 rounds): Checker REVISE -> targeted repair -> N=2 same-candidate consecutive passes -> ACCEPT
        r2_repo, r2_base = _init_fixture_repo(tmp_path, "s2_npass", 43902)
        s2_maker_calls = {"n": 0}
        s2_checker_calls = {"n": 0}

        def _s2_maker(wt: pathlib.Path, ctx: dict[str, Any]) -> dict[str, Any]:
            s2_maker_calls["n"] += 1
            content = "FIXED draft\n" if s2_maker_calls["n"] == 1 else "FIXED final\n"
            (wt / "README.md").write_text(content, encoding="utf-8")
            return {"changed_path": "README.md"}

        def _s2_checker(_snap: pathlib.Path, ev_inv: dict[str, str], ctx: dict[str, Any]) -> dict[str, Any]:
            s2_checker_calls["n"] += 1
            ev_refs = [{"receipt_path": k, "receipt_sha256": v} for k, v in sorted(ev_inv.items())]
            if s2_checker_calls["n"] == 1:
                return {
                    "status": "FAIL",
                    "findings": [{"severity": "MEDIUM", "file": "README.md", "line": 1, "rule": "DOC-001", "explanation": "Needs final wording", "fix": "Change to FIXED final"}],
                    "limitations": [],
                    "reviewed_scope": ["README.md"],
                    "selection_sha256": ctx["selection"]["selection_sha256"],
                    "rule_results": [],
                    "rubric": build_rubric_report(decision="REVISE", hard_gate_passed=True, evidence_refs=ev_refs, findings_notes={"correctness": ["Needs final wording"]}),
                }
            return {
                "status": "PASS",
                "findings": [],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": ctx["selection"]["selection_sha256"],
                "rule_results": [],
                "rubric": build_rubric_report(decision="ACCEPT", hard_gate_passed=True, evidence_refs=ev_refs),
            }

        res2 = run_maker_checker_loop(
            repo=r2_repo,
            issue=43902,
            journal_path=journal_path,
            evidence_dir=ev_root / "scenario_2_revise_and_n2_same_candidate",
            issue_data={"state": "OPEN", "title": "Pilot S2", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=_s2_maker,
            checker_fn=_s2_checker,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "pilot-fixture"},
            policy=build_run_policy(consecutive_passes_required=2, max_rounds=4, max_wall_seconds=120, no_progress_threshold=3),
            base_sha=r2_base,
            check_profile="quick",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False,
            require_protected_approval=False,
            allow_fixture_mode=True,
        )
        scenarios.append({
            "scenario": "checker_revise_then_n2_same_candidate_accept",
            "state": res2["state"],
            "rounds": len(res2["rounds"]),
            "maker_invocations": s2_maker_calls["n"],
            "run_id": res2["run_id"],
        })
        total_rounds += len(res2["rounds"])

        # Scenario 3 (2 rounds): Repeated identical failure / no-progress -> ESCALATED
        r3_repo, r3_base = _init_fixture_repo(tmp_path, "s3_noprog", 43903)

        def _s3_maker(wt: pathlib.Path, ctx: dict[str, Any]) -> dict[str, Any]:
            (wt / "README.md").write_text("STILL_BROKEN\n", encoding="utf-8")
            return {"changed_path": "README.md"}

        res3 = run_maker_checker_loop(
            repo=r3_repo,
            issue=43903,
            journal_path=journal_path,
            evidence_dir=ev_root / "scenario_3_no_progress_escalated",
            issue_data={"state": "OPEN", "title": "Pilot S3", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=_s3_maker,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "pilot-fixture"},
            policy=build_run_policy(consecutive_passes_required=1, max_rounds=5, max_wall_seconds=120, no_progress_threshold=2),
            base_sha=r3_base,
            check_profile="quick",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False,
            require_protected_approval=False,
            allow_fixture_mode=True,
        )
        scenarios.append({"scenario": "repeated_failure_no_progress_escalated", "state": res3["state"], "rounds": len(res3["rounds"]), "run_id": res3["run_id"]})
        total_rounds += len(res3["rounds"])

        # Scenario 4 (1 round): Impossible scope / hard-gate BLOCK -> BLOCKED
        r4_repo, r4_base = _init_fixture_repo(tmp_path, "s4_block", 43904)

        def _s4_maker(wt: pathlib.Path, ctx: dict[str, Any]) -> dict[str, Any]:
            (wt / "README.md").write_text("FIXED\n", encoding="utf-8")
            return {"changed_path": "README.md"}

        def _s4_checker(_snap: pathlib.Path, ev_inv: dict[str, str], ctx: dict[str, Any]) -> dict[str, Any]:
            ev_refs = [{"receipt_path": k, "receipt_sha256": v} for k, v in sorted(ev_inv.items())]
            return {
                "status": "FAIL",
                "findings": [{"severity": "CRITICAL", "file": "contracts/radio-mac/spec.md", "line": 1, "rule": "SEC-001", "explanation": "Requires out-of-scope contract edit", "fix": "Amend scope"}],
                "limitations": [],
                "reviewed_scope": ["README.md"],
                "selection_sha256": ctx["selection"]["selection_sha256"],
                "rule_results": [],
                "rubric": build_rubric_report(decision="BLOCK", hard_gate_passed=False, evidence_refs=ev_refs, findings_notes={"scope_discipline": ["Out of scope"]}),
            }

        res4 = run_maker_checker_loop(
            repo=r4_repo,
            issue=43904,
            journal_path=journal_path,
            evidence_dir=ev_root / "scenario_4_hard_gate_block",
            issue_data={"state": "OPEN", "title": "Pilot S4", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=_s4_maker,
            checker_fn=_s4_checker,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "pilot-fixture"},
            policy=build_run_policy(consecutive_passes_required=1, max_rounds=3, max_wall_seconds=120, no_progress_threshold=2),
            base_sha=r4_base,
            check_profile="quick",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False,
            require_protected_approval=False,
            allow_fixture_mode=True,
        )
        scenarios.append({"scenario": "hard_gate_impossible_scope_blocked", "state": res4["state"], "rounds": len(res4["rounds"]), "run_id": res4["run_id"]})
        total_rounds += len(res4["rounds"])

        # Scenario 5 (0 dispatched rounds, cancelled before dispatch): Cancellation preserves worktree
        r5_repo, r5_base = _init_fixture_repo(tmp_path, "s5_cancel", 43905)
        (r5_repo / "README.md").write_text("WIP preserved\n", encoding="utf-8")
        res5 = run_maker_checker_loop(
            repo=r5_repo,
            issue=43905,
            journal_path=journal_path,
            evidence_dir=ev_root / "scenario_5_cancellation",
            issue_data={"state": "OPEN", "title": "Pilot S5", "body": "## Target Directories (allowed paths)\n- `README.md`\n"},
            maker_fn=_s4_maker,
            approval={"status": "FIXTURE_APPROVED", "approved_by": "pilot-fixture"},
            policy=build_run_policy(consecutive_passes_required=1, max_rounds=2, max_wall_seconds=120),
            base_sha=r5_base,
            check_profile="quick",
            capability_overrides={"fixture_maker": True, "fixture_checker": True},
            require_isolated_worktree=False,
            require_protected_approval=False,
            allow_fixture_mode=True,
            cancel_check=lambda _rnd: True,
        )
        scenarios.append({
            "scenario": "cancellation_preserves_work",
            "state": res5["state"],
            "rounds": len(res5["rounds"]),
            "worktree_preserved": (r5_repo / "README.md").read_text(encoding="utf-8") == "WIP preserved\n",
            "run_id": res5["run_id"],
        })

    pilot_summary = {
        "schema_version": "1.0",
        "mode": "FIXTURE_CONTROLLED",
        "independent_provider_evaluation": "NOT_VERIFIED",
        "human_rubric_calibration": "NOT_VERIFIED",
        "total_recorded_rounds": total_rounds,
        "scenarios": scenarios,
        "journal_path": str(journal_path),
        "evidence_dir": str(ev_root),
    }
    (ev_root / "pilot_summary.json").write_text(json.dumps(redact_data(pilot_summary), indent=2, sort_keys=True), encoding="utf-8")
    return pilot_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P08-A Unified Role & Control-Plane CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_cap = sub.add_parser("capabilities", help="Probe role/provider capabilities and isolation disclosure")
    p_cap.add_argument("--maker-provider", default="auto")
    p_cap.add_argument("--checker-provider", default="auto")
    p_cap.add_argument("--json", action="store_true")

    p_adm = sub.add_parser("admit", help="Validate admission prerequisites and persist control run")
    p_adm.add_argument("--issue", type=int, required=True)
    p_adm.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_adm.add_argument("--state", type=pathlib.Path, required=True)
    p_adm.add_argument("--base-sha", default=None)
    p_adm.add_argument("--approved-by", default="")
    p_adm.add_argument("--supervised-issue-open", action="store_true")
    p_adm.add_argument("--max-rounds", type=int, default=1)
    p_adm.add_argument("--consecutive-passes", type=int, default=1)
    p_adm.add_argument("--max-wall-seconds", type=int, default=1800)
    p_adm.add_argument("--no-progress-threshold", type=int, default=2)
    p_adm.add_argument("--require-token-budget", action="store_true")
    p_adm.add_argument("--require-cost-budget", action="store_true")
    p_adm.add_argument("--maker-provider", default="auto")
    p_adm.add_argument("--checker-provider", default="auto")

    p_st = sub.add_parser("status", help="Inspect control-plane run state and event trace")
    p_st.add_argument("--run-id", default=None)
    p_st.add_argument("--issue", type=int, default=None)
    p_st.add_argument("--state", type=pathlib.Path, required=True)

    p_can = sub.add_parser("cancel", help="Cancel an active control-plane run without destructive reset")
    p_can.add_argument("--run-id", required=True)
    p_can.add_argument("--state", type=pathlib.Path, required=True)
    p_can.add_argument("--requested-by", default="owner")
    p_can.add_argument("--reason", default="Cancelled by operator")

    p_demo = sub.add_parser("demo-dispatch", help="Run non-destructive fixture dispatch route on a disposable worktree")
    p_demo.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    p_demo.add_argument("--state", type=pathlib.Path, required=True)
    p_demo.add_argument("--issue", type=int, default=437)

    p_pilot = sub.add_parser("pilot", help="Run >=5 recorded P08-B Maker-Checker pilot rounds in controlled fixtures")
    p_pilot.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    p_pilot.add_argument("--state", type=pathlib.Path, required=True)

    args = parser.parse_args(argv)
    try:
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
                journal_path=args.state,
                base_sha=args.base_sha,
                approval=approval,
                policy=pol,
                maker_provider=args.maker_provider,
                checker_provider=args.checker_provider,
            )
            print(json.dumps(redact_data(res), indent=2, sort_keys=True))
            return 0

        if args.command == "status":
            with Journal(args.state) as journal:
                if args.run_id:
                    run = journal.get_control_run(args.run_id)
                elif args.issue is not None:
                    run = journal.latest_control_run_for_issue(args.issue)
                    if run is None:
                        raise ControlPlaneError(f"No control run found for Issue #{args.issue}")
                else:
                    raise ControlPlaneError("status requires --run-id or --issue")
                events = journal.control_events(run["run_id"])
                rounds = journal.list_control_rounds(run["run_id"])
            print(json.dumps({"run": run, "rounds": rounds, "events": events}, indent=2, sort_keys=True))
            return 0

        if args.command == "cancel":
            res = cancel_run(
                journal_path=args.state,
                run_id=args.run_id,
                requested_by=args.requested_by,
                reason=args.reason,
            )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0

        if args.command == "demo-dispatch":
            import tempfile

            ev_root = args.evidence_dir.resolve()
            if args.state.is_symlink() or ev_root.is_symlink():
                raise AdmissionError("Evidence and state paths must not be symlinks")
            with tempfile.TemporaryDirectory(prefix="p08a-fixture-repo-") as tmp:
                tmp_path = pathlib.Path(tmp)
                if ev_root.is_relative_to(tmp_path) or args.state.resolve().is_relative_to(tmp_path):
                    raise AdmissionError("Evidence/state paths must reside outside fixture repo")
                fixture_repo = tmp_path / "repo"
                fixture_repo.mkdir()
                for cmd in (
                    ["git", "init", "-q"],
                    ["git", "config", "user.name", "P08A Fixture"],
                    ["git", "config", "user.email", "p08a@example.invalid"],
                ):
                    subprocess.run(cmd, cwd=fixture_repo, check=True, capture_output=True, timeout=15)
                (fixture_repo / "AGENTS.md").write_text("# Fixture AGENTS\n- Follow P08-A.\n", encoding="utf-8")
                (fixture_repo / "README.md").write_text("before\n", encoding="utf-8")
                for ref in SNAPSHOT_REFERENCES:
                    ref_path = fixture_repo / ref
                    if not ref_path.exists():
                        ref_path.parent.mkdir(parents=True, exist_ok=True)
                        ref_path.write_text("Read-only fixture reference.\n", encoding="utf-8")
                subprocess.run(["git", "add", "."], cwd=fixture_repo, check=True, capture_output=True, timeout=15)
                subprocess.run(["git", "commit", "-qm", "fixture base"], cwd=fixture_repo, check=True, capture_output=True, timeout=15)
                subprocess.run(["git", "checkout", "-qb", f"feature/{args.issue}-fixture"], cwd=fixture_repo, check=True, capture_output=True, timeout=15)

                def _fixture_maker(wt: pathlib.Path, _admitted: dict[str, Any]) -> dict[str, Any]:
                    (wt / "README.md").write_text("after controlled fixture dispatch\n", encoding="utf-8")
                    return {"changed_path": "README.md"}

                res = run_controlled_dispatch(
                    repo=fixture_repo,
                    issue=args.issue,
                    journal_path=args.state,
                    evidence_dir=ev_root,
                    issue_data={
                        "state": "OPEN",
                        "title": "Controlled P08-A Fixture Dispatch",
                        "body": "## Target Directories (allowed paths)\n- `README.md`\n",
                    },
                    maker_fn=_fixture_maker,
                )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0

        if args.command == "pilot":
            res = run_pilot_scenarios(
                journal_path=args.state,
                evidence_dir=args.evidence_dir,
            )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0
    except (ControlPlaneError, StateConflict, ObservabilityError, OSError, ValueError, subprocess.SubprocessError) as exc:
        safe_msg, _, _ = redact_text(str(exc), max_bytes=240)
        print(json.dumps({"state": "BLOCKED", "reason": safe_msg}))
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
