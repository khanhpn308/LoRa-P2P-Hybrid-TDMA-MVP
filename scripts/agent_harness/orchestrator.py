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
    from .agent_context import ContextGateError, load_context
    from .check import freeze_checks
    from .feature_state import compute_candidate_snapshot
    from .observability import ObservabilityError, redact_data, redact_text, record_process_signal
    from .p1.process import ProcessBlocked, execute_checked
    from .p1.state import Journal, StateConflict
    from .p1.worktrees import WorktreeError, inspect_worktree
    from .scope import parse_allowed_paths, violations
    from .snapshot import REFERENCES as SNAPSHOT_REFERENCES, assemble, digest, unchanged
    from .standards_policy import StandardsError, select_rules
except ImportError:
    from agent_context import ContextGateError, load_context
    from check import freeze_checks
    from feature_state import compute_candidate_snapshot
    from observability import ObservabilityError, redact_data, redact_text, record_process_signal
    from p1.process import ProcessBlocked, execute_checked
    from p1.state import Journal, StateConflict
    from p1.worktrees import WorktreeError, inspect_worktree
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


def _verify_budget_before_dispatch(
    journal: Journal,
    run: dict[str, Any],
    *,
    elapsed_wall_seconds: float,
) -> None:
    policy = run["policy"]
    consumed = run["budget_consumed"]
    rounds_used = int(run["round_num"])
    no_prog = int(run["no_progress_count"])
    total_wall = float(consumed.get("wall_seconds", 0.0)) + max(0.0, float(elapsed_wall_seconds))

    reason = ""
    if rounds_used >= int(policy["max_rounds"]):
        reason = f"max_rounds exhausted ({rounds_used}/{policy['max_rounds']})"
    elif no_prog >= int(policy["no_progress_threshold"]):
        reason = f"no_progress_threshold reached ({no_prog}/{policy['no_progress_threshold']})"
    elif total_wall > float(policy["max_wall_seconds"]):
        reason = f"max_wall_seconds exhausted ({total_wall:.1f}>{policy['max_wall_seconds']})"
    elif policy.get("require_token_budget") and consumed.get("tokens_used") is None:
        reason = "Required enforceable token budget unavailable"
    elif policy.get("require_cost_budget") and consumed.get("cost_usd") is None:
        reason = "Required enforceable cost budget unavailable"

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
    failure_sig: str = "",
    wall_elapsed_s: float = 0.0,
    tokens_used: int | None = None,
    cost_used: float | None = None,
    actor_role: str = "host",
) -> dict[str, Any]:
    """Host-owned round evaluation: updates budgets, no-progress, and transitions safely."""
    authorize_role_action(actor_role, "enforce_budget")
    if outcome not in ("PASS", "REVISE", "FAIL", "TIMEOUT", "BLOCK"):
        raise ControlPlaneError(f"Invalid round outcome: {outcome!r}")

    with Journal(journal_path) as journal:
        run = journal.get_control_run(run_id)
        if run["dispatch_token"] != dispatch_token:
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

        if budget_reason:
            next_state = "ESCALATED"
            action = "budget_exhausted"
            consec = 0
        elif outcome == "TIMEOUT":
            next_state = "ESCALATED"
            action = "timeout_escalated"
            consec = 0
        elif outcome == "BLOCK":
            next_state = "BLOCKED"
            action = "round_blocked"
            consec = 0
        elif outcome == "PASS":
            if not (host_checks_passed and checker_passed):
                raise RoleAccessDenied("Cannot record PASS without both Host checks and Checker PASS")
            consec += 1
            no_prog = 0
            if consec >= int(policy["consecutive_passes_required"]):
                next_state = "READY_FOR_HUMAN_REVIEW"
                action = "round_accepted_for_human_review"
            elif new_round >= int(policy["max_rounds"]):
                next_state = "ESCALATED"
                action = "max_rounds_before_consecutive_passes"
            else:
                next_state = "REPAIR_REQUIRED"
                action = "await_next_consecutive_pass"
        else:
            consec = 0
            repeated = (bool(failure_sig) and failure_sig == last_sig) or (
                bool(diff_sha256) and diff_sha256 == last_diff
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

        consumed["no_progress_count"] = no_prog
        consumed["consecutive_passes"] = consec

        updated = journal.transition_control_run(
            run_id,
            expected=run["state"],
            next_state=next_state,
            actor_role=actor_role,
            action=action,
            expected_dispatch_token=dispatch_token,
            clear_dispatch=True,
            update_fields={
                "round_num": new_round,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
                "last_failure_sig": failure_sig,
                "last_diff_sha256": diff_sha256,
                "budget_consumed_json": json.dumps(consumed, sort_keys=True),
            },
            detail={
                "outcome": outcome,
                "budget_reason": budget_reason,
                "round_num": new_round,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
            },
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
            next_action=(
                "Human review & merge decision (ready_to_merge=False)"
                if next_state == "READY_FOR_HUMAN_REVIEW"
                else f"Inspect {next_state} ({action})"
            ),
            decision_refs=("OD-08", "OD-09"),
            issue_sha256=updated["admission"].get("issue_sha256", ""),
            handoff_json=json.dumps({
                "run_id": run_id,
                "state": next_state,
                "round_num": new_round,
                "consecutive_passes": consec,
                "no_progress_count": no_prog,
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
        diff_sha256=diff_sha256,
        duration_s=new_wall,
        exit_code=0 if next_state == "READY_FOR_HUMAN_REVIEW" else 1,
        finding=budget_reason or f"Round {new_round} ended in {next_state} ({action})",
        evidence_ref={"run_id": run_id, "round_num": new_round, "state": next_state},
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
    evidence_inv = {"checks_summary.json": hashlib.sha256(checks_bytes).hexdigest()}

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
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    if all((root / ref).exists() for ref in SNAPSHOT_REFERENCES):
        hashes = assemble(root, snapshot_dir, list(snap["changed_paths"]), diff_proc.stdout, [proc_receipt.json()])
    else:
        hashes = {}
        for rel in sorted(snap["changed_paths"]):
            src = root / rel
            if src.is_file() and not src.is_symlink():
                b = src.read_bytes()
                dst = snapshot_dir / "source" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(b)
                dst.chmod(0o444)
                hashes[rel] = digest(b)
        (snapshot_dir / "changes.patch").write_text(diff_proc.stdout, encoding="utf-8")
        (snapshot_dir / "checks.json").write_text(json.dumps([proc_receipt.json()], indent=2), encoding="utf-8")
        for fname in ("changes.patch", "checks.json"):
            (snapshot_dir / fname).chmod(0o444)
            hashes[fname] = digest((snapshot_dir / fname).read_bytes())
    schema_src = pathlib.Path(__file__).resolve().parent / "adapters" / "audit.schema.json"
    schema_dst = snapshot_dir / "audit.schema.json"
    schema_dst.write_bytes(schema_src.read_bytes() if schema_src.is_file() else b"{}\n")
    schema_dst.chmod(0o444)
    hashes["audit.schema.json"] = digest(schema_dst.read_bytes())
    if checker_fn is not None:
        audit_report = checker_fn(snapshot_dir, evidence_inv, admitted)
    else:
        audit_report = {
            "status": "PASS",
            "findings": [],
            "limitations": ["Controlled non-destructive fixture verification only; native UI isolation NOT_VERIFIED"],
            "reviewed_scope": list(snap["changed_paths"]),
            "selection_sha256": admitted["selection"]["selection_sha256"],
            "rule_results": [],
        }
    if not unchanged(snapshot_dir, hashes):
        raise RoleAccessDenied("Checker mutated frozen review snapshot")

    (evidence_dir / "audit_report.json").write_text(json.dumps(audit_report, indent=2, sort_keys=True), encoding="utf-8")

    checker_ok = audit_report.get("status") == "PASS"
    final_run = record_round_result(
        journal_path=journal_path,
        run_id=run_id,
        dispatch_token=checker_token,
        outcome="PASS" if checker_ok else "REVISE",
        host_checks_passed=(proc_receipt.exit_code == 0),
        checker_passed=checker_ok,
        diff_sha256=snap["diff_sha256"],
        failure_sig="" if checker_ok else "checker_revise",
        wall_elapsed_s=proc_receipt.duration_s,
    )
    with Journal(journal_path) as journal:
        events = journal.control_events(run_id)
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
        "events": events,
        "isolation_disclosure": ROLE_ISOLATION_DISCLOSURE,
    }
    (evidence_dir / "control_plane_summary.json").write_text(json.dumps(redact_data(summary), indent=2, sort_keys=True), encoding="utf-8")
    return summary


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
            print(json.dumps({"run": run, "events": events}, indent=2, sort_keys=True))
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
    except (ControlPlaneError, StateConflict, ObservabilityError, OSError, ValueError, subprocess.SubprocessError) as exc:
        safe_msg, _, _ = redact_text(str(exc), max_bytes=240)
        print(json.dumps({"state": "BLOCKED", "reason": safe_msg}))
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
