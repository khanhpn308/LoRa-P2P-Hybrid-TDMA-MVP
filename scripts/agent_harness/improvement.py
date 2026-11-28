#!/usr/bin/env python3
"""P08-D Controlled Harness Meta-Improvement Experiment Loop (H2-FBK-10, H2-FBK-11, OD-10).

Implements a separate, bounded improvement loop:
  failure attribution -> hypothesis -> isolated one-change experiment ->
  matched baseline/candidate evaluation -> independent holdout & negative controls ->
  KEEP / REJECT decision -> durable Journal + SHA-bound evidence -> safe workspace discard.

KEEP is an experiment recommendation only, never autonomous merge/deployment.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    from .observability import diagnose_failures, record_process_signal, redact_data, redact_text
    from .orchestrator import RoleAccessDenied, authorize_role_action
    from .p1.state import Journal, StateConflict
    from .quality_gates import REGISTRY as QG_REGISTRY, evaluate as evaluate_quality_gates, secret_line
    from .scope import violations as scope_violations
except ImportError:
    from observability import diagnose_failures, record_process_signal, redact_data, redact_text
    from orchestrator import RoleAccessDenied, authorize_role_action
    from p1.state import Journal, StateConflict
    from quality_gates import REGISTRY as QG_REGISTRY, evaluate as evaluate_quality_gates, secret_line
    from scope import violations as scope_violations

SCHEMA_VERSION = "1.0"
EXPERIMENT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
SHA64_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_EXPERIMENT_LOG_BYTES = 200_000
MAX_REPETITIONS = 10

VALID_MODES = frozenset({"CONTROLLED_FIXTURE", "REPRESENTATIVE_TASK"})
VALID_DIRECTIONS = frozenset({"higher_is_better", "lower_is_better"})

# Surfaces that an improvement candidate MUST NEVER modify (anti-Goodhart & safety invariant).
PROTECTED_EXPERIMENT_PREFIXES: tuple[str, ...] = (
    "AGENTS.md",
    ".agents/",
    ".agent-harness/",
    ".github/workflows/",
    "contracts/",
    "docs/adr/",
    "firmware/components/sx1276_driver/",
    "scripts/agent_harness/adapters/",
    "scripts/agent_harness/agent_context.py",
    "scripts/agent_harness/check.py",
    "scripts/agent_harness/improvement.py",
    "scripts/agent_harness/observability.py",
    "scripts/agent_harness/orchestrator.py",
    "scripts/agent_harness/p1/state.py",
    "scripts/agent_harness/pr_review.py",
    "scripts/agent_harness/pr_review_policy.py",
    "scripts/agent_harness/quality_gates.py",
    "scripts/agent_harness/scope.py",
    "scripts/agent_harness/standards_policy.py",
    "tests/agent_harness/fixtures/improvement/",
)


class ImprovementError(RuntimeError):
    """Base error for P08-D controlled improvement loop failures."""


class ProtocolError(ImprovementError):
    """Raised when OD-10 experiment protocol invariants are violated."""


class TamperingError(ImprovementError):
    """Raised on oracle, holdout, rubric, guardrail, or evidence tampering/replay."""


class BudgetError(ImprovementError):
    """Raised on invalid or exhausted finite experiment budget."""


class UnauthorizedPromotionError(ImprovementError):
    """Raised on unauthorized experiment promotion or direct main merge attempt."""


class WorkspaceIsolationError(ImprovementError):
    """Raised when disposable workspace isolation or ownership guarantees fail."""


@dataclass(frozen=True)
class ExperimentBudget:
    max_wall_seconds: float
    max_rounds: int = 1
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    require_token_budget: bool = False
    require_cost_budget: bool = False

    def validate(self) -> None:
        if self.max_wall_seconds <= 0:
            raise ProtocolError("max_wall_seconds must be > 0")
        if self.max_rounds < 1:
            raise ProtocolError("max_rounds must be >= 1")
        if self.max_tokens is not None and self.max_tokens < 0:
            raise ProtocolError("max_tokens must be >= 0")
        if self.max_cost_usd is not None and self.max_cost_usd < 0:
            raise ProtocolError("max_cost_usd must be >= 0")
        if self.require_token_budget and self.max_tokens is None:
            raise ProtocolError("require_token_budget=True requires explicit max_tokens")
        if self.require_cost_budget and self.max_cost_usd is None:
            raise ProtocolError("require_cost_budget=True requires explicit max_cost_usd")


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _canonical_sha256(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_symlink(path: pathlib.Path, *, label: str = "path", stop_at: pathlib.Path | None = None) -> None:
    cur = path
    while True:
        if cur.is_symlink():
            raise WorkspaceIsolationError(f"Symlink rejected for {label}: {cur}")
        if stop_at is not None and cur == stop_at:
            break
        parent = cur.parent
        if parent == cur:
            break
        cur = parent


def _run_git(repo: pathlib.Path, *args: str, timeout: int = 30) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise WorkspaceIsolationError(f"git {' '.join(args[:2])} failed or timed out") from exc
    if proc.returncode != 0:
        raise WorkspaceIsolationError(f"git {args[0]} exited {proc.returncode}")
    return proc.stdout.strip()


def _is_protected_experiment_path(path: str) -> bool:
    norm = path.strip().lstrip("./")
    for prefix in PROTECTED_EXPERIMENT_PREFIXES:
        if prefix.endswith("/"):
            if norm.startswith(prefix) or norm == prefix.rstrip("/"):
                return True
        elif norm == prefix:
            return True
    low = norm.lower()
    if any(tok in low for tok in ("holdout", "oracle")) and low.startswith(("tests/", "scripts/agent_harness/")):
        return True
    return False


def validate_experiment_scope(allowed_paths: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Validate strict single-experiment allowed paths without protected surfaces or wildcards."""
    if not allowed_paths:
        raise ProtocolError("Experiment allowed_paths must be non-empty")
    cleaned: list[str] = []
    for raw in allowed_paths:
        item = str(raw).strip()
        if not item:
            raise ProtocolError("Experiment allowed_paths contains empty path")
        if "*" in item or "?" in item:
            raise ProtocolError(f"Wildcard paths are forbidden in OD-10 scope: {item!r}")
        if item.startswith("/") or ".." in pathlib.PurePosixPath(item).parts:
            raise ProtocolError(f"Unsafe path in experiment allowed_paths: {item!r}")
        if _is_protected_experiment_path(item):
            raise ProtocolError(f"Experiment allowed_paths cannot modify protected surface: {item!r}")
        if item not in cleaned:
            cleaned.append(item)
    return tuple(cleaned)


def attribute_failure_from_journal(
    journal_path: pathlib.Path,
    *,
    issue: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Derive bounded failure attribution from existing P06 Journal signals."""
    _reject_symlink(journal_path, label="journal_path")
    diag = diagnose_failures(journal_path, issue=issue, run_id=run_id, limit=20)
    latest = diag.get("latest_failure")
    if latest is None:
        return {
            "source": "journal_signals",
            "issue": issue,
            "run_id": run_id or "",
            "failure_count": 0,
            "owning_domain": "harness",
            "check_id": "",
            "status": "NO_FAILURE_RECORDED",
            "finding": "No recorded failure signal; requires explicit baseline defect or controlled fixture.",
            "remediation": "",
        }
    return {
        "source": "journal_signals",
        "issue": issue,
        "run_id": run_id or "",
        "failure_count": int(diag.get("failure_count", 0)),
        "signal_id": latest.get("signal_id"),
        "owning_domain": str(latest.get("owning_domain", "harness")),
        "check_id": str(latest.get("check_id", "")),
        "category": str(latest.get("category", "")),
        "status": str(latest.get("status", "FAIL")),
        "finding": str(latest.get("finding", "")),
        "evidence_ref": latest.get("evidence_ref", {}),
        "remediation": str(latest.get("remediation", "")),
    }


def _default_oracle_spec() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "oracle_id": "od10-host-oracle-v1",
        "protected_prefixes": list(PROTECTED_EXPERIMENT_PREFIXES),
        "hard_gates": ["SECRET-SCAN", "DIFF-CHECK", "SCOPE-CHECK", "ORACLE-INTEGRITY"],
        "zero_regression_required": True,
    }


def _default_negative_controls_spec() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "controls": [
            {"id": "NC-OUT-OF-SCOPE", "kind": "unauthorized_path", "expected": "REJECT"},
            {"id": "NC-ORACLE-TAMPER", "kind": "oracle_modification", "expected": "REJECT"},
            {"id": "NC-SECRET-LEAK", "kind": "secret_scan", "expected": "REJECT"},
            {"id": "NC-NOT-RUN-SKIP", "kind": "missing_mandatory_check", "expected": "REJECT"},
        ],
    }


def build_experiment_plan(
    *,
    experiment_id: str,
    hypothesis: str,
    one_change_summary: str,
    attributed_subsystem: str,
    attributed_failure: dict[str, Any],
    target_metric: str,
    direction: str,
    min_delta: float,
    baseline_revision: str,
    allowed_paths: list[str] | tuple[str, ...],
    mode: str = "CONTROLLED_FIXTURE",
    threshold_approval: dict[str, Any] | None = None,
    budget: ExperimentBudget | None = None,
    repetitions: int = 1,
    matched_env: dict[str, Any] | None = None,
    workload_spec: dict[str, Any] | None = None,
    checks_spec: dict[str, Any] | None = None,
    holdout_spec: dict[str, Any] | None = None,
    negative_controls_spec: dict[str, Any] | None = None,
    oracle_spec: dict[str, Any] | None = None,
    non_regression_metrics: list[str] | tuple[str, ...] = ("mandatory_checks_passed", "hard_gates_passed"),
    issue: int | None = None,
    run_id: str = "",
) -> dict[str, Any]:
    """Freeze a complete OD-10 experiment plan and cryptographic digests before execution."""
    authorize_role_action("planner", "propose_experiment")
    if not EXPERIMENT_ID_RE.fullmatch(experiment_id):
        raise ProtocolError(f"Invalid experiment_id: {experiment_id!r}")
    hyp = hypothesis.strip()
    one_change = one_change_summary.strip()
    if not hyp or not one_change:
        raise ProtocolError("OD-10 requires non-empty hypothesis and one_change_summary")
    if len(hyp) > 500:
        raise ProtocolError("Hypothesis exceeds bounded 500-char limit")
    if not attributed_subsystem.strip():
        raise ProtocolError("OD-10 requires attributed_subsystem")
    if not target_metric.strip():
        raise ProtocolError("OD-10 requires target_metric")
    if direction not in VALID_DIRECTIONS:
        raise ProtocolError(f"Unsupported metric direction: {direction!r}")
    if min_delta <= 0:
        raise ProtocolError("OD-10 improvement threshold min_delta must be > 0")
    if SHA40_RE.fullmatch(baseline_revision) is None:
        raise ProtocolError(f"baseline_revision must be a 40-char git SHA: {baseline_revision!r}")
    if mode not in VALID_MODES:
        raise ProtocolError(f"Unsupported experiment mode: {mode!r}")
    if repetitions < 1 or repetitions > MAX_REPETITIONS:
        raise ProtocolError(f"repetitions must be in [1, {MAX_REPETITIONS}]")

    norm_paths = validate_experiment_scope(allowed_paths)
    eff_budget = budget or ExperimentBudget(max_wall_seconds=120.0, max_rounds=1)
    eff_budget.validate()

    approval = dict(threshold_approval or {"status": "PENDING_OWNER_APPROVAL"})
    approval_status = str(approval.get("status", "PENDING_OWNER_APPROVAL"))
    if mode == "CONTROLLED_FIXTURE" and approval_status not in ("CONTROLLED_FIXTURE", "OWNER_APPROVED"):
        approval = {"status": "CONTROLLED_FIXTURE", "approved_by": "fixture-routing-only"}
        approval_status = "CONTROLLED_FIXTURE"
    if approval_status == "OWNER_APPROVED" and not str(approval.get("approved_by", "")).strip():
        raise ProtocolError("OWNER_APPROVED threshold requires non-empty approved_by")

    eff_oracle = dict(oracle_spec or _default_oracle_spec())
    eff_holdout = dict(holdout_spec or {})
    eff_neg = dict(negative_controls_spec or _default_negative_controls_spec())
    eff_workload = dict(workload_spec or {})
    eff_checks = dict(checks_spec if checks_spec is not None else {"commands": [], "run_quality_gates": True})

    # Validate frozen holdout case IDs (non-empty, unique) when holdout cases are declared.
    raw_holdout_cases = eff_holdout.get("cases", [])
    if not isinstance(raw_holdout_cases, list):
        raise ProtocolError("holdout_spec['cases'] must be a list")
    seen_holdout_ids: set[str] = set()
    for hc in raw_holdout_cases:
        if not isinstance(hc, dict):
            raise ProtocolError("Each frozen holdout case must be a dict")
        hcid = str(hc.get("id", "")).strip()
        if not hcid:
            raise ProtocolError("Each frozen holdout case must declare a non-empty 'id'")
        if hcid in seen_holdout_ids:
            raise ProtocolError(f"Duplicate frozen holdout case id: {hcid!r}")
        seen_holdout_ids.add(hcid)

    # Enforce strict separation between REPRESENTATIVE_TASK and fixture quality-gate exceptions.
    raw_run_qg = eff_checks.get("run_quality_gates", True)
    if not isinstance(raw_run_qg, bool):
        raise ProtocolError("checks_spec['run_quality_gates'] must be a boolean")
    raw_cmds = eff_checks.get("commands", [])
    if not isinstance(raw_cmds, list):
        raise ProtocolError("checks_spec['commands'] must be a list")
    for cmd in raw_cmds:
        if not isinstance(cmd, (list, tuple)) or not cmd or not all(isinstance(arg, str) and arg for arg in cmd):
            raise ProtocolError("Each command in checks_spec['commands'] must be a non-empty list of strings")
    if mode == "REPRESENTATIVE_TASK":
        if raw_run_qg is not True:
            raise ProtocolError("REPRESENTATIVE_TASK cannot bypass mandatory quality gates (run_quality_gates=False forbidden)")
        if eff_checks.get("fixture_exception") or eff_checks.get("fixture_quality_gate_exempt"):
            raise ProtocolError("REPRESENTATIVE_TASK cannot declare fixture quality-gate exceptions")
        if not raw_cmds:
            raise ProtocolError("REPRESENTATIVE_TASK requires at least one required check command in checks_spec['commands']")
    elif raw_run_qg is False:
        eff_checks["fixture_exception"] = True
        eff_checks.setdefault("fixture_exception_reason", "CONTROLLED_FIXTURE_ONLY")
    eff_env = dict(
        matched_env
        or {
            "python_version": sys.version.split()[0],
            "model": "NOT_USED_DETERMINISTIC_HOST",
            "reasoning_setting": "N/A",
            "repetitions": repetitions,
        }
    )
    eff_env["repetitions"] = repetitions

    oracle_sha = _canonical_sha256(eff_oracle)
    holdout_sha = _canonical_sha256(eff_holdout)
    neg_sha = _canonical_sha256(eff_neg)
    workload_sha = _canonical_sha256(eff_workload)
    checks_sha = _canonical_sha256(eff_checks)
    evaluator_sha = _canonical_sha256(
        {
            "oracle_sha256": oracle_sha,
            "holdout_sha256": holdout_sha,
            "negative_controls_sha256": neg_sha,
            "checks_spec_sha256": checks_sha,
            "non_regression_metrics": list(non_regression_metrics),
        }
    )
    policy_obj = {
        "mode": mode,
        "target_metric": target_metric,
        "direction": direction,
        "min_delta": float(min_delta),
        "threshold_approval": approval,
        "non_regression_metrics": list(non_regression_metrics),
        "allowed_paths": list(norm_paths),
        "budget": asdict(eff_budget),
        "protected_prefixes": list(PROTECTED_EXPERIMENT_PREFIXES),
    }
    policy_sha = _canonical_sha256(policy_obj)

    plan_core = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "issue": issue,
        "run_id": run_id,
        "mode": mode,
        "hypothesis": hyp,
        "one_change_summary": one_change,
        "attributed_subsystem": attributed_subsystem.strip(),
        "attributed_failure": attributed_failure,
        "target_metric": target_metric.strip(),
        "direction": direction,
        "min_delta": float(min_delta),
        "threshold_approval": approval,
        "non_regression_metrics": list(non_regression_metrics),
        "baseline_revision": baseline_revision,
        "allowed_paths": list(norm_paths),
        "repetitions": repetitions,
        "matched_env": eff_env,
        "budget": asdict(eff_budget),
        "oracle_sha256": oracle_sha,
        "holdout_sha256": holdout_sha,
        "negative_controls_sha256": neg_sha,
        "workload_sha256": workload_sha,
        "checks_spec_sha256": checks_sha,
        "evaluator_sha256": evaluator_sha,
        "policy_sha256": policy_sha,
    }
    plan_sha = _canonical_sha256(plan_core)

    return {
        **plan_core,
        "plan_sha256": plan_sha,
        "oracle_spec": eff_oracle,
        "holdout_spec": eff_holdout,
        "negative_controls_spec": eff_neg,
        "workload_spec": eff_workload,
        "checks_spec": eff_checks,
        # Maker only receives the hypothesis, allowed paths, and change summary (never holdout/oracle answers).
        "maker_view": {
            "experiment_id": experiment_id,
            "hypothesis": hyp,
            "one_change_summary": one_change,
            "attributed_subsystem": attributed_subsystem.strip(),
            "target_metric": target_metric.strip(),
            "baseline_revision": baseline_revision,
            "allowed_paths": list(norm_paths),
            "plan_sha256": plan_sha,
        },
    }


def _write_json_artifact(path: pathlib.Path, payload: Any) -> str:
    _reject_symlink(path, label=path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(redact_data(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return _bytes_sha256(raw)


def _owner_marker_path(workspace_root: pathlib.Path, experiment_id: str, role: str) -> pathlib.Path:
    return workspace_root / f".owner-{experiment_id}-{role}.json"


def create_disposable_workspace(
    *,
    source_repo: pathlib.Path,
    workspace_root: pathlib.Path,
    experiment_id: str,
    role: str,
    baseline_revision: str,
) -> dict[str, Any]:
    """Create an isolated, explicitly owned disposable git clone at baseline_revision."""
    authorize_role_action("host", "evaluate_experiment")
    if role not in ("baseline", "candidate"):
        raise WorkspaceIsolationError(f"Invalid disposable workspace role: {role!r}")
    _reject_symlink(source_repo, label="source_repo")
    _reject_symlink(workspace_root, label="workspace_root")
    src = source_repo.resolve(strict=True)
    workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ws_root = workspace_root.resolve(strict=True)
    if ws_root == src or ws_root.is_relative_to(src) or src.is_relative_to(ws_root):
        raise WorkspaceIsolationError("Disposable workspace_root must reside outside source_repo")

    actual_rev = _run_git(src, "rev-parse", "--verify", f"{baseline_revision}^{{commit}}")
    if actual_rev != baseline_revision:
        raise WorkspaceIsolationError("Baseline revision mismatch in source_repo")

    target = ws_root / experiment_id / role
    if target.exists() or target.is_symlink():
        raise WorkspaceIsolationError(f"Disposable workspace target already exists: {target}")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)

    clone_proc = subprocess.run(
        ["git", "clone", "--quiet", str(src), str(target)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )
    if clone_proc.returncode != 0:
        raise WorkspaceIsolationError(f"Disposable git clone failed with exit {clone_proc.returncode}")

    branch_name = f"exp/{experiment_id}/{role}"
    _run_git(target, "config", "user.name", "Harness Experiment")
    _run_git(target, "config", "user.email", "harness-exp@example.invalid")
    _run_git(target, "checkout", "-q", "-b", branch_name, baseline_revision)
    if _run_git(target, "rev-parse", "HEAD") != baseline_revision:
        raise WorkspaceIsolationError("Disposable workspace HEAD did not match baseline_revision")

    marker_path = _owner_marker_path(ws_root, experiment_id, role)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": experiment_id,
        "role": role,
        "workspace_path": str(target),
        "workspace_root": str(ws_root),
        "source_repo": str(src),
        "baseline_revision": baseline_revision,
        "branch": branch_name,
        "created_at": _utc_now(),
    }
    marker_sha = _write_json_artifact(marker_path, marker)
    return {
        **marker,
        "marker_path": str(marker_path),
        "marker_sha256": marker_sha,
    }


def discard_disposable_workspace(
    *,
    workspace_info: dict[str, Any],
    workspace_root: pathlib.Path,
) -> dict[str, Any]:
    """Safely discard ONLY an explicitly owned disposable workspace; never touch source_repo or main."""
    authorize_role_action("host", "discard_experiment_workspace")
    _reject_symlink(workspace_root, label="workspace_root")
    ws_root = workspace_root.resolve(strict=True)
    experiment_id = str(workspace_info.get("experiment_id", ""))
    role = str(workspace_info.get("role", ""))
    target = pathlib.Path(str(workspace_info.get("workspace_path", "")))
    marker_path = _owner_marker_path(ws_root, experiment_id, role)

    _reject_symlink(marker_path, label="owner_marker", stop_at=ws_root)
    if not marker_path.is_file():
        raise WorkspaceIsolationError(f"Missing ownership marker; refusing to discard {target}")
    marker_data = json.loads(marker_path.read_text(encoding="utf-8"))
    if (
        marker_data.get("experiment_id") != experiment_id
        or marker_data.get("role") != role
        or marker_data.get("workspace_path") != str(target)
        or marker_data.get("workspace_root") != str(ws_root)
    ):
        raise WorkspaceIsolationError("Ownership marker mismatch; refusing workspace discard")

    if target.is_symlink():
        raise WorkspaceIsolationError("Refusing to discard symlinked workspace")
    existed_before = target.exists()
    if existed_before:
        resolved_target = target.resolve(strict=True)
        expected_parent = (ws_root / experiment_id).resolve(strict=True)
        if resolved_target.parent != expected_parent or not resolved_target.is_relative_to(ws_root):
            raise WorkspaceIsolationError("Refusing discard outside owned experiment workspace_root")
        shutil.rmtree(resolved_target)
        # Clean empty parent experiment dir if both baseline and candidate are discarded.
        if expected_parent.exists() and not any(expected_parent.iterdir()):
            expected_parent.rmdir()
    marker_path.unlink(missing_ok=True)
    return {
        "experiment_id": experiment_id,
        "role": role,
        "workspace_path": str(target),
        "existed_before": existed_before,
        "exists_after": target.exists(),
        "discarded": True,
        "discarded_at": _utc_now(),
    }


def _collect_workspace_changes(workspace: pathlib.Path, baseline_revision: str) -> list[str]:
    diff_proc = subprocess.run(
        ["git", "-C", str(workspace), "diff", "--name-only", "--no-renames", "-z", baseline_revision],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if diff_proc.returncode != 0:
        raise WorkspaceIsolationError(f"git diff exited {diff_proc.returncode}")
    status_proc = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if status_proc.returncode != 0:
        raise WorkspaceIsolationError(f"git status exited {status_proc.returncode}")

    paths: set[str] = set()
    for raw in diff_proc.stdout.split(b"\0"):
        if raw:
            paths.add(raw.decode("utf-8", errors="replace"))
    entries = status_proc.stdout.split(b"\0")
    idx = 0
    while idx < len(entries):
        entry = entries[idx]
        idx += 1
        if len(entry) < 4:
            continue
        xy = entry[:2].decode("ascii", errors="replace")
        path = entry[3:].decode("utf-8", errors="replace")
        if path:
            paths.add(path)
        if "R" in xy or "C" in xy:
            if idx < len(entries) and entries[idx]:
                paths.add(entries[idx].decode("utf-8", errors="replace"))
            idx += 1
    return sorted(paths)


def _compute_candidate_fingerprint(workspace: pathlib.Path, baseline_revision: str) -> dict[str, Any]:
    head_sha = _run_git(workspace, "rev-parse", "HEAD")
    changed_paths = _collect_workspace_changes(workspace, baseline_revision)
    file_hashes: dict[str, str] = {}
    for rel in changed_paths:
        p = workspace / rel
        if p.is_symlink():
            raise TamperingError(f"Symlink introduced in experiment workspace: {rel}")
        if p.is_file():
            file_hashes[rel] = _bytes_sha256(p.read_bytes())
        else:
            file_hashes[rel] = "DELETED"
    cand_sha = _canonical_sha256(
        {
            "baseline_revision": baseline_revision,
            "head_sha": head_sha,
            "changed_paths": changed_paths,
            "file_hashes": file_hashes,
        }
    )
    return {
        "head_sha": head_sha,
        "changed_paths": changed_paths,
        "file_hashes": file_hashes,
        "candidate_sha256": cand_sha,
    }


def _verify_frozen_plan_integrity(plan: dict[str, Any]) -> None:
    if _canonical_sha256(plan["oracle_spec"]) != plan["oracle_sha256"]:
        raise TamperingError("Oracle specification digest drifted from frozen plan")
    if _canonical_sha256(plan["holdout_spec"]) != plan["holdout_sha256"]:
        raise TamperingError("Holdout specification digest drifted from frozen plan")
    if _canonical_sha256(plan["negative_controls_spec"]) != plan["negative_controls_sha256"]:
        raise TamperingError("Negative controls specification digest drifted from frozen plan")
    if _canonical_sha256(plan["workload_spec"]) != plan["workload_sha256"]:
        raise TamperingError("Workload specification digest drifted from frozen plan")
    if _canonical_sha256(plan["checks_spec"]) != plan["checks_spec_sha256"]:
        raise TamperingError("Checks specification digest drifted from frozen plan")


def _run_bounded_command(
    cmd: list[str],
    *,
    cwd: pathlib.Path,
    log_path: pathlib.Path,
    timeout_s: float,
) -> dict[str, Any]:
    if timeout_s <= 0:
        raise BudgetError("Insufficient remaining wall budget for command execution")
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout_s,
        )
        rc = int(proc.returncode)
        raw_out = proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        rc = 124
        raw_out = (exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""))
    elapsed = round(time.monotonic() - started, 4)
    safe_log, was_redacted, was_truncated = redact_text(raw_out, max_bytes=MAX_EXPERIMENT_LOG_BYTES)
    _reject_symlink(log_path, label=log_path.name)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_bytes = safe_log.encode("utf-8")
    log_path.write_bytes(log_bytes)
    return {
        "command": list(cmd),
        "command_sha256": _canonical_sha256(list(cmd)),
        "exit_code": rc,
        "timed_out": timed_out,
        "duration_s": elapsed,
        "log_path": str(log_path.name),
        "log_sha256": _bytes_sha256(log_bytes),
        "redacted": was_redacted,
        "truncated": was_truncated,
        "stdout": safe_log,
    }


def evaluate_workspace(
    *,
    workspace: pathlib.Path,
    role: str,
    plan: dict[str, Any],
    evidence_dir: pathlib.Path,
    budget_state: dict[str, Any],
    evaluator_fn: Callable[[pathlib.Path, dict[str, Any], int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run independent Host evaluation on baseline or candidate workspace across repetitions."""
    authorize_role_action("host", "evaluate_experiment")
    _verify_frozen_plan_integrity(plan)

    baseline_rev = str(plan["baseline_revision"])
    allowed_paths = list(plan["allowed_paths"])
    repetitions = int(plan["repetitions"])
    budget_limit = plan["budget"]
    max_wall_s = float(budget_limit["max_wall_seconds"])

    fp = _compute_candidate_fingerprint(workspace, baseline_rev)
    changed_paths = fp["changed_paths"]
    out_of_scope = scope_violations(workspace, allowed_paths, changed_paths) if role == "candidate" else []
    protected_hits = [p for p in changed_paths if _is_protected_experiment_path(p)] if role == "candidate" else []
    tampering_detected = bool(out_of_scope or protected_hits)

    # Hard gates: REPRESENTATIVE_TASK cannot bypass quality gates; fixture exceptions are strictly separated.
    is_fixture = (plan.get("mode") == "CONTROLLED_FIXTURE")
    checks_spec = plan.get("checks_spec", {})
    run_qg = checks_spec.get("run_quality_gates", True)
    gate_result: dict[str, Any] = {
        "status": "NOT_RUN",
        "auto_check": "NOT_RUN",
        "fixture_exception": False,
        "selected_rules": [],
    }
    if not is_fixture and run_qg is not True:
        hard_gates_passed = False
        gate_result = {
            "auto_check": "BLOCKED",
            "status": "BYPASS_FORBIDDEN",
            "fixture_exception": False,
            "selected_rules": [],
            "built_in_scan_status": "NOT_RUN",
            "diff_check_status": "NOT_RUN",
        }
    elif is_fixture and run_qg is False:
        hard_gates_passed = True
        gate_result = {
            "auto_check": "FIXTURE_EXEMPT",
            "status": "FIXTURE_EXEMPT",
            "fixture_exception": True,
            "fixture_exception_reason": str(checks_spec.get("fixture_exception_reason") or "CONTROLLED_FIXTURE_ONLY"),
            "selected_rules": [],
            "built_in_scan_status": "FIXTURE_EXEMPT",
            "diff_check_status": "FIXTURE_EXEMPT",
        }
    else:
        hard_gates_passed = True
        qg_manifest = checks_spec.get("quality_gate_manifest")
        qg_ev_dir = checks_spec.get("quality_gate_evidence_dir")
        qg_ev_root = pathlib.Path(qg_ev_dir).resolve() if qg_ev_dir else None
        qg = evaluate_quality_gates(
            workspace,
            baseline_rev,
            manifest=qg_manifest,
            evidence_root=qg_ev_root,
        )
        by_rule = {r.get("rule_id"): r for r in qg.get("results", []) if isinstance(r, dict)}
        selected_risks = set(qg.get("risks", []))
        selected_rules = sorted(
            (
                {"rule_id": str(r["rule_id"]), "status": str(r["status"])}
                for r in qg.get("results", [])
                if isinstance(r, dict)
                and r.get("rule_id") in QG_REGISTRY
                and QG_REGISTRY[r["rule_id"]][1] in selected_risks
            ),
            key=lambda item: item["rule_id"],
        )
        sec_status = by_rule.get("SECRET-SCAN", {}).get("status", "NOT_VERIFIED")
        diff_status = by_rule.get("DIFF-CHECK", {}).get("status", "NOT_VERIFIED")
        auto_check_val = str(qg.get("auto_check", "BLOCKED"))
        gate_result = {
            "auto_check": auto_check_val,
            "status": "PASS" if auto_check_val == "AUTO_CHECK_PASS" else "FAIL",
            "fixture_exception": False,
            "selected_rules": selected_rules,
            "built_in_scan_status": sec_status,
            "diff_check_status": diff_status,
        }
        if (
            auto_check_val != "AUTO_CHECK_PASS"
            or not selected_rules
            or any(item["status"] != "PASS" for item in selected_rules)
            or sec_status != "PASS"
            or diff_status != "PASS"
        ):
            hard_gates_passed = False

    commands_Spec = list(checks_spec.get("commands", []))
    rep_runs: list[dict[str, Any]] = []
    metric_samples: dict[str, list[float]] = {}
    all_mandatory_passed = hard_gates_passed and not tampering_detected
    required_checks_passed = hard_gates_passed and not tampering_detected
    if not is_fixture and not commands_Spec:
        required_checks_passed = False
        all_mandatory_passed = False
    metric_gaming_detected = False

    for rep in range(1, repetitions + 1):
        remaining_s = max_wall_s - float(budget_state.get("wall_seconds", 0.0))
        if remaining_s <= 0:
            budget_state["budget_exhausted"] = True
            budget_state["exhaustion_reason"] = "Wall-time budget exhausted before evaluation repetition"
            break

        rep_cmd_receipts: list[dict[str, Any]] = []
        rep_passed = hard_gates_passed and not tampering_detected
        rep_start = time.monotonic()

        for idx, cmd in enumerate(commands_Spec):
            rem = max_wall_s - float(budget_state.get("wall_seconds", 0.0)) - (time.monotonic() - rep_start)
            if rem <= 0:
                budget_state["budget_exhausted"] = True
                budget_state["exhaustion_reason"] = "Wall-time budget exhausted during command check"
                rep_passed = False
                break
            log_file = evidence_dir / f"{role}_rep{rep}_cmd{idx}.log"
            rec = _run_bounded_command(list(cmd), cwd=workspace, log_path=log_file, timeout_s=rem)
            stdout_text = rec.pop("stdout", "")
            rep_cmd_receipts.append(rec)
            if rec["timed_out"]:
                budget_state["budget_exhausted"] = True
                budget_state["exhaustion_reason"] = f"Command timed out after {rec['duration_s']}s"
                rep_passed = False
            elif rec["exit_code"] != 0:
                rep_passed = False

            # Optional JSON metric extraction from deterministic host command output.
            if stdout_text.strip().startswith("{"):
                try:
                    parsed = json.loads(stdout_text)
                    if isinstance(parsed, dict) and isinstance(parsed.get("metrics"), dict):
                        for mk, mv in parsed["metrics"].items():
                            if isinstance(mv, (int, float)) and not isinstance(mv, bool):
                                metric_samples.setdefault(str(mk), []).append(float(mv))
                except json.JSONDecodeError:
                    pass

        if evaluator_fn is not None and not budget_state.get("budget_exhausted"):
            ev_out = evaluator_fn(workspace, plan, rep)
            if bool(ev_out.get("tampering_detected")) or bool(ev_out.get("metric_gaming_detected")):
                metric_gaming_detected = True
                tampering_detected = True
                rep_passed = False
            if not bool(ev_out.get("mandatory_passed", True)):
                rep_passed = False
            if ev_out.get("tokens_used") is not None:
                prev_tok = budget_state.get("tokens_used")
                base_tok = 0 if prev_tok in (None, "NOT_VERIFIED") else int(prev_tok)
                budget_state["tokens_used"] = base_tok + int(ev_out["tokens_used"])
            if ev_out.get("cost_usd") is not None:
                prev_cost = budget_state.get("cost_usd")
                base_cost = 0.0 if prev_cost in (None, "NOT_VERIFIED") else float(prev_cost)
                budget_state["cost_usd"] = round(base_cost + float(ev_out["cost_usd"]), 6)
            for mk, mv in dict(ev_out.get("metrics", {})).items():
                if isinstance(mv, (int, float)) and not isinstance(mv, bool):
                    metric_samples.setdefault(str(mk), []).append(float(mv))

        rep_elapsed = round(time.monotonic() - rep_start, 4)
        budget_state["wall_seconds"] = round(float(budget_state.get("wall_seconds", 0.0)) + rep_elapsed, 4)
        cmds_complete_and_ok = (len(rep_cmd_receipts) == len(commands_Spec)) and all(
            c.get("exit_code") == 0 and not c.get("timed_out") for c in rep_cmd_receipts
        )
        if not cmds_complete_and_ok:
            required_checks_passed = False
        if not rep_passed or not cmds_complete_and_ok:
            all_mandatory_passed = False

        metric_samples.setdefault("mandatory_checks_passed", []).append(1.0 if rep_passed else 0.0)
        metric_samples.setdefault("hard_gates_passed", []).append(1.0 if hard_gates_passed else 0.0)
        metric_samples.setdefault("eval_wall_seconds", []).append(rep_elapsed)
        rep_runs.append(
            {
                "repetition": rep,
                "passed": rep_passed and cmds_complete_and_ok,
                "elapsed_s": rep_elapsed,
                "commands": rep_cmd_receipts,
            }
        )

    _verify_frozen_plan_integrity(plan)

    if len(rep_runs) != repetitions:
        required_checks_passed = False
        all_mandatory_passed = False

    metrics_summary: dict[str, Any] = {}
    for mk, vals in sorted(metric_samples.items()):
        metrics_summary[mk] = round(sum(vals) / len(vals), 6) if vals else 0.0

    final_mandatory_ok = all_mandatory_passed and required_checks_passed and not budget_state.get("budget_exhausted", False)
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "role": role,
        "baseline_revision": baseline_rev,
        "plan_sha256": plan["plan_sha256"],
        "oracle_sha256": plan["oracle_sha256"],
        "evaluator_sha256": plan["evaluator_sha256"],
        "policy_sha256": plan["policy_sha256"],
        "head_sha": fp["head_sha"],
        "candidate_sha256": fp["candidate_sha256"],
        "changed_paths": changed_paths,
        "unauthorized_paths": out_of_scope,
        "protected_paths_touched": protected_hits,
        "tampering_detected": tampering_detected,
        "metric_gaming_detected": metric_gaming_detected,
        "hard_gates": gate_result,
        "hard_gates_passed": hard_gates_passed,
        "fixture_quality_gate_exempt": bool(is_fixture and run_qg is False),
        "required_checks_count": len(commands_Spec),
        "required_checks_passed": bool(required_checks_passed and not budget_state.get("budget_exhausted", False)),
        "mandatory_checks_passed": final_mandatory_ok,
        "repetitions": rep_runs,
        "metrics": metrics_summary,
    }


def evaluate_holdout(
    *,
    workspace: pathlib.Path,
    plan: dict[str, Any],
    evidence_dir: pathlib.Path,
    budget_state: dict[str, Any],
    holdout_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run independent held-out evaluation never exposed to Maker, enforcing exact frozen ID match."""
    authorize_role_action("checker", "audit_experiment")
    _verify_frozen_plan_integrity(plan)

    holdout_spec = plan.get("holdout_spec", {})
    raw_cases = holdout_spec.get("cases", [])
    cases = list(raw_cases) if isinstance(raw_cases, list) else []
    if not cases:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": plan["experiment_id"],
            "baseline_revision": plan["baseline_revision"],
            "plan_sha256": plan["plan_sha256"],
            "holdout_sha256": plan["holdout_sha256"],
            "status": "MISSING_FAIL",
            "error_code": "HOLDOUT_CASES_MISSING",
            "frozen_case_ids": [],
            "executed_case_ids": [],
            "missing_case_ids": [],
            "duplicate_case_ids": [],
            "unexpected_case_ids": [],
            "unexecuted_case_ids": [],
            "id_match_exact": False,
            "cases_total": 0,
            "cases_passed": 0,
            "regression": True,
            "results": [],
        }

    frozen_ids: list[str] = []
    seen_frozen: set[str] = set()
    invalid_frozen = False
    for case in cases:
        if not isinstance(case, dict):
            invalid_frozen = True
            frozen_ids.append("")
            continue
        cid = str(case.get("id", "")).strip()
        if not cid or cid in seen_frozen:
            invalid_frozen = True
        seen_frozen.add(cid)
        frozen_ids.append(cid)

    if invalid_frozen:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": plan["experiment_id"],
            "baseline_revision": plan["baseline_revision"],
            "plan_sha256": plan["plan_sha256"],
            "holdout_sha256": plan["holdout_sha256"],
            "status": "FAIL",
            "error_code": "INVALID_FROZEN_HOLDOUT_IDS",
            "frozen_case_ids": frozen_ids,
            "executed_case_ids": [],
            "missing_case_ids": [],
            "duplicate_case_ids": [c for c in frozen_ids if frozen_ids.count(c) > 1],
            "unexpected_case_ids": [],
            "unexecuted_case_ids": frozen_ids,
            "id_match_exact": False,
            "cases_total": len(cases),
            "cases_passed": 0,
            "regression": True,
            "results": [],
        }

    fn_by_id: dict[str, list[dict[str, Any]]] = {}
    unexpected_case_ids: list[str] = []
    duplicate_case_ids: list[str] = []
    malformed_fn = False
    if holdout_fn is not None:
        fn_res = holdout_fn(workspace, plan)
        if not isinstance(fn_res, dict) or not isinstance(fn_res.get("cases"), list):
            malformed_fn = True
        else:
            for item in fn_res["cases"]:
                if not isinstance(item, dict):
                    malformed_fn = True
                    continue
                cid = str(item.get("case_id") if "case_id" in item else item.get("id", "")).strip()
                if not cid:
                    unexpected_case_ids.append("<EMPTY>")
                    continue
                if cid not in seen_frozen:
                    unexpected_case_ids.append(cid)
                    continue
                fn_by_id.setdefault(cid, []).append(item)
                if len(fn_by_id[cid]) > 1 and cid not in duplicate_case_ids:
                    duplicate_case_ids.append(cid)

    results: list[dict[str, Any]] = []
    executed_case_ids: list[str] = []
    missing_case_ids: list[str] = []
    unexecuted_case_ids: list[str] = []
    passed_count = 0
    max_wall = float(plan["budget"]["max_wall_seconds"])

    for idx, case in enumerate(cases):
        cid = frozen_ids[idx]
        cmd = case.get("command")
        if cmd:
            if cid in fn_by_id:
                if cid not in duplicate_case_ids:
                    duplicate_case_ids.append(cid)
                unexecuted_case_ids.append(cid)
                results.append({"case_id": cid, "executed": False, "passed": False, "reason": "DUPLICATE_CASE_EXECUTION"})
                continue
            rem = max_wall - float(budget_state.get("wall_seconds", 0.0))
            if rem <= 0:
                budget_state["budget_exhausted"] = True
                budget_state["exhaustion_reason"] = "Wall-time budget exhausted before holdout check"
                unexecuted_case_ids.append(cid)
                results.append({"case_id": cid, "executed": False, "passed": False, "reason": "BUDGET_EXHAUSTED"})
                continue
            rec = _run_bounded_command(
                list(cmd),
                cwd=workspace,
                log_path=evidence_dir / f"holdout_case_{idx}.log",
                timeout_s=rem,
            )
            budget_state["wall_seconds"] = round(float(budget_state.get("wall_seconds", 0.0)) + rec["duration_s"], 4)
            if rec["timed_out"]:
                budget_state["budget_exhausted"] = True
                budget_state["exhaustion_reason"] = f"Holdout case {cid} timed out after {rec['duration_s']}s"
                unexecuted_case_ids.append(cid)
                results.append(
                    {
                        "case_id": cid,
                        "executed": False,
                        "passed": False,
                        "exit_code": rec["exit_code"],
                        "log_path": rec["log_path"],
                        "log_sha256": rec["log_sha256"],
                        "reason": "TIMED_OUT",
                    }
                )
            else:
                ok = rec["exit_code"] == 0
                executed_case_ids.append(cid)
                if ok:
                    passed_count += 1
                results.append(
                    {
                        "case_id": cid,
                        "executed": True,
                        "passed": ok,
                        "exit_code": rec["exit_code"],
                        "log_path": rec["log_path"],
                        "log_sha256": rec["log_sha256"],
                    }
                )
        else:
            if holdout_fn is None:
                unexecuted_case_ids.append(cid)
                results.append({"case_id": cid, "executed": False, "passed": False, "reason": "NO_EXECUTABLE_HOLDOUT_RUNNER"})
            elif cid not in fn_by_id:
                missing_case_ids.append(cid)
                unexecuted_case_ids.append(cid)
                results.append({"case_id": cid, "executed": False, "passed": False, "reason": "CASE_NOT_EXECUTED"})
            elif len(fn_by_id[cid]) > 1:
                unexecuted_case_ids.append(cid)
                results.append({"case_id": cid, "executed": False, "passed": False, "reason": "DUPLICATE_CASE_EXECUTION"})
            else:
                item = fn_by_id[cid][0]
                was_executed = item.get("executed", True)
                raw_passed = item.get("passed")
                if was_executed is not True:
                    unexecuted_case_ids.append(cid)
                    results.append(
                        {
                            "case_id": cid,
                            "executed": False,
                            "passed": False,
                            "reason": str(item.get("reason") or "CASE_NOT_EXECUTED"),
                        }
                    )
                elif not isinstance(raw_passed, bool):
                    unexecuted_case_ids.append(cid)
                    results.append(
                        {
                            "case_id": cid,
                            "executed": False,
                            "passed": False,
                            "reason": "INVALID_BOOLEAN_PASSED",
                        }
                    )
                else:
                    executed_case_ids.append(cid)
                    if raw_passed:
                        passed_count += 1
                    results.append(
                        {
                            "case_id": cid,
                            "executed": True,
                            "passed": raw_passed,
                            "reason": str(item.get("reason", "")),
                        }
                    )

    id_match_exact = (
        not malformed_fn
        and not missing_case_ids
        and not duplicate_case_ids
        and not unexpected_case_ids
        and not unexecuted_case_ids
        and len(executed_case_ids) == len(frozen_ids)
        and set(executed_case_ids) == seen_frozen
    )
    all_ok = id_match_exact and len(results) == len(frozen_ids) and passed_count == len(frozen_ids)
    error_code = ""
    if not all_ok:
        if duplicate_case_ids:
            error_code = "HOLDOUT_DUPLICATE_CASE_IDS"
        elif unexpected_case_ids or malformed_fn:
            error_code = "HOLDOUT_UNEXPECTED_OR_MALFORMED_CASE_IDS"
        elif missing_case_ids:
            error_code = "HOLDOUT_MISSING_CASE_IDS"
        elif unexecuted_case_ids:
            error_code = "HOLDOUT_UNEXECUTED_CASE"
        else:
            error_code = "HOLDOUT_CASE_FAILED"

    out: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "baseline_revision": plan["baseline_revision"],
        "plan_sha256": plan["plan_sha256"],
        "holdout_sha256": plan["holdout_sha256"],
        "status": "PASS" if all_ok else "FAIL",
        "frozen_case_ids": frozen_ids,
        "executed_case_ids": executed_case_ids,
        "missing_case_ids": missing_case_ids,
        "duplicate_case_ids": duplicate_case_ids,
        "unexpected_case_ids": unexpected_case_ids,
        "unexecuted_case_ids": unexecuted_case_ids,
        "id_match_exact": id_match_exact,
        "cases_total": len(frozen_ids),
        "cases_passed": passed_count,
        "regression": not all_ok,
        "results": results,
    }
    if error_code:
        out["error_code"] = error_code
    return out


def evaluate_negative_controls(
    *,
    workspace: pathlib.Path,
    plan: dict[str, Any],
    candidate_eval: dict[str, Any],
    negative_control_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Verify anti-Goodhart and guardrail negative controls still reject seeded bad inputs."""
    authorize_role_action("checker", "audit_experiment")
    _verify_frozen_plan_integrity(plan)

    controls = list(plan.get("negative_controls_spec", {}).get("controls", []))
    if not controls:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": plan["experiment_id"],
            "baseline_revision": plan["baseline_revision"],
            "plan_sha256": plan["plan_sha256"],
            "negative_controls_sha256": plan["negative_controls_sha256"],
            "status": "MISSING_FAIL",
            "controls_total": 0,
            "controls_passed": 0,
            "results": [],
        }

    custom_results: dict[str, bool] = {}
    if negative_control_fn is not None:
        custom_out = negative_control_fn(workspace, plan)
        for item in custom_out.get("controls", []):
            custom_results[str(item.get("id"))] = bool(item.get("rejected_as_expected"))

    results: list[dict[str, Any]] = []
    passed = 0
    for ctrl in controls:
        cid = str(ctrl.get("id", "NC"))
        kind = str(ctrl.get("kind", ""))
        if cid in custom_results:
            ok = custom_results[cid]
        elif kind == "unauthorized_path":
            ok = bool(scope_violations(workspace, list(plan["allowed_paths"]), ["docs/adr/0004-pure-cad-csma-ca-mac.md"]))
        elif kind == "oracle_modification":
            ok = _is_protected_experiment_path("scripts/agent_harness/quality_gates.py")
        elif kind == "secret_scan":
            # Verify secret scanner still rejects seeded credential pattern and candidate did not game metrics.
            probe_detected = secret_line(b"api_" + b"key = \"probe-seeded-secret\"\n") is not None
            ok = probe_detected and not bool(candidate_eval.get("metric_gaming_detected")) and not bool(candidate_eval.get("tampering_detected"))
        elif kind == "missing_mandatory_check":
            ok = bool(candidate_eval.get("mandatory_checks_passed"))
        else:
            ok = False
        if ok:
            passed += 1
        results.append({"id": cid, "kind": kind, "rejected_as_expected": ok})

    all_ok = passed == len(controls)
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "baseline_revision": plan["baseline_revision"],
        "plan_sha256": plan["plan_sha256"],
        "negative_controls_sha256": plan["negative_controls_sha256"],
        "status": "PASS" if all_ok else "FAIL",
        "controls_total": len(controls),
        "controls_passed": passed,
        "results": results,
    }


def _check_budget_status(plan: dict[str, Any], budget_consumed: dict[str, Any]) -> tuple[bool, str]:
    limit = plan["budget"]
    if budget_consumed.get("budget_exhausted"):
        return False, str(budget_consumed.get("exhaustion_reason") or "BUDGET_EXHAUSTED")
    if float(budget_consumed.get("wall_seconds", 0.0)) > float(limit["max_wall_seconds"]):
        return False, "BUDGET_EXHAUSTED: wall_seconds exceeded max_wall_seconds"
    if int(budget_consumed.get("rounds", 0)) > int(limit["max_rounds"]):
        return False, "BUDGET_EXHAUSTED: rounds exceeded max_rounds"

    tokens_used = budget_consumed.get("tokens_used", "NOT_VERIFIED")
    if limit.get("require_token_budget") and (tokens_used in (None, "NOT_VERIFIED") or isinstance(tokens_used, bool)):
        return False, "METERING_UNAVAILABLE: require_token_budget set but token metering is NOT_VERIFIED"
    if isinstance(tokens_used, (int, float)) and not isinstance(tokens_used, bool):
        if limit.get("max_tokens") is not None and tokens_used > int(limit["max_tokens"]):
            return False, "BUDGET_EXHAUSTED: tokens_used exceeded max_tokens"

    cost_used = budget_consumed.get("cost_usd", "NOT_VERIFIED")
    if limit.get("require_cost_budget") and (cost_used in (None, "NOT_VERIFIED") or isinstance(cost_used, bool)):
        return False, "METERING_UNAVAILABLE: require_cost_budget set but cost metering is NOT_VERIFIED"
    if isinstance(cost_used, (int, float)) and not isinstance(cost_used, bool):
        if limit.get("max_cost_usd") is not None and cost_used > float(limit["max_cost_usd"]):
            return False, "BUDGET_EXHAUSTED: cost_usd exceeded max_cost_usd"

    return True, "WITHIN_BUDGET"


def decide_experiment(
    *,
    plan: dict[str, Any],
    baseline_eval: dict[str, Any],
    candidate_eval: dict[str, Any],
    holdout_eval: dict[str, Any],
    negative_controls: dict[str, Any],
    budget_consumed: dict[str, Any],
    aborted_reason: str = "",
) -> dict[str, Any]:
    """Deterministic KEEP/REJECT gate enforcing OD-10, H2-FBK-10, and H2-FBK-11."""
    authorize_role_action("orchestrator", "record_experiment_decision")
    target = str(plan["target_metric"])
    direction = str(plan["direction"])
    min_delta = float(plan["min_delta"])

    base_metrics = dict(baseline_eval.get("metrics", {}))
    cand_metrics = dict(candidate_eval.get("metrics", {}))
    metric_delta: dict[str, float] = {}
    for k in sorted(set(base_metrics) | set(cand_metrics)):
        bv = base_metrics.get(k)
        cv = cand_metrics.get(k)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)):
            metric_delta[k] = round(float(cv) - float(bv), 6)

    target_base = base_metrics.get(target)
    target_cand = cand_metrics.get(target)
    if isinstance(target_base, (int, float)) and isinstance(target_cand, (int, float)):
        raw_diff = float(target_cand) - float(target_base)
        effective_gain = raw_diff if direction == "higher_is_better" else -raw_diff
    else:
        effective_gain = None

    def _reject(reason_code: str, detail: str, *, decision: str = "REJECT") -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": plan["experiment_id"],
            "mode": plan["mode"],
            "decision": decision,
            "reason_code": reason_code,
            "decision_reason": detail,
            "promotion_status": "NOT_PROMOTED",
            "independent_eval_status": "FAIL" if decision == "REJECT" else decision,
            "holdout_status": str(holdout_eval.get("status", "NOT_VERIFIED")),
            "negative_controls_status": str(negative_controls.get("status", "NOT_VERIFIED")),
            "target_metric": target,
            "direction": direction,
            "min_delta": min_delta,
            "effective_gain": effective_gain,
            "metric_delta": metric_delta,
        }

    if aborted_reason:
        return _reject("EXPERIMENT_ABORTED", aborted_reason, decision="ABORTED")

    budget_ok, budget_msg = _check_budget_status(plan, budget_consumed)
    if not budget_ok:
        code = "METERING_UNAVAILABLE" if budget_msg.startswith("METERING_UNAVAILABLE") else "BUDGET_EXHAUSTED"
        return _reject(code, budget_msg)

    if (
        candidate_eval.get("tampering_detected")
        or candidate_eval.get("metric_gaming_detected")
        or candidate_eval.get("unauthorized_paths")
        or candidate_eval.get("protected_paths_touched")
    ):
        return _reject(
            "TAMPERING_OR_METRIC_GAMING",
            "Candidate modified unauthorized/protected paths, oracle, or triggered metric-gaming detection",
        )

    if (
        candidate_eval.get("plan_sha256") != plan["plan_sha256"]
        or candidate_eval.get("oracle_sha256") != plan["oracle_sha256"]
        or baseline_eval.get("plan_sha256") != plan["plan_sha256"]
        or holdout_eval.get("holdout_sha256") != plan["holdout_sha256"]
        or negative_controls.get("negative_controls_sha256") != plan["negative_controls_sha256"]
    ):
        return _reject("EVIDENCE_HASH_DRIFT", "Frozen plan/oracle/holdout/negative-control digest mismatch")

    if not candidate_eval.get("hard_gates_passed") or not candidate_eval.get("mandatory_checks_passed"):
        return _reject(
            "HARD_GATE_OR_MANDATORY_CHECK_FAILED",
            "Candidate failed mandatory hard gates or required checks",
        )

    if plan.get("mode") == "REPRESENTATIVE_TASK":
        checks_spec = plan.get("checks_spec", {})
        if checks_spec.get("run_quality_gates") is not True or candidate_eval.get("fixture_quality_gate_exempt"):
            return _reject(
                "QUALITY_GATE_BYPASS_FORBIDDEN",
                "REPRESENTATIVE_TASK cannot bypass mandatory quality gates",
            )
        hard_gates = candidate_eval.get("hard_gates", {})
        selected_rules = hard_gates.get("selected_rules", [])
        if (
            hard_gates.get("auto_check") != "AUTO_CHECK_PASS"
            or not isinstance(selected_rules, list)
            or not selected_rules
            or any(not isinstance(item, dict) or item.get("status") != "PASS" for item in selected_rules)
        ):
            return _reject(
                "HARD_GATE_OR_MANDATORY_CHECK_FAILED",
                "REPRESENTATIVE_TASK requires AUTO_CHECK_PASS across all selected mandatory quality gates",
            )
        req_cmds = list(checks_spec.get("commands", []))
        if (
            not req_cmds
            or candidate_eval.get("required_checks_passed") is not True
            or len(candidate_eval.get("repetitions", [])) != int(plan.get("repetitions", 1))
        ):
            return _reject(
                "REQUIRED_CHECKS_FAILED_OR_MISSING",
                "REPRESENTATIVE_TASK requires all configured required checks to execute and pass across all repetitions",
            )

    # Zero-tolerance non-regression check on mandatory non-regression metrics.
    for m_name in plan.get("non_regression_metrics", []):
        bv = base_metrics.get(m_name)
        cv = cand_metrics.get(m_name)
        if isinstance(bv, (int, float)) and isinstance(cv, (int, float)) and float(cv) < float(bv):
            return _reject(
                "MANDATORY_METRIC_REGRESSION",
                f"Mandatory metric {m_name!r} regressed from {bv} to {cv}",
            )

    if holdout_eval.get("status") != "PASS" or holdout_eval.get("regression"):
        return _reject("HOLDOUT_FAILED_OR_MISSING", f"Holdout status: {holdout_eval.get('status')}")

    frozen_holdout_cases = plan.get("holdout_spec", {}).get("cases", [])
    frozen_holdout_ids = [
        str(c.get("id", "")).strip() for c in frozen_holdout_cases if isinstance(c, dict)
    ]
    ho_results = holdout_eval.get("results", [])
    ho_result_ids = [str(r.get("case_id", "")).strip() for r in ho_results if isinstance(r, dict)]
    ho_exec_ids = [str(x).strip() for x in holdout_eval.get("executed_case_ids", [])]
    if (
        not frozen_holdout_ids
        or any(not cid for cid in frozen_holdout_ids)
        or len(set(frozen_holdout_ids)) != len(frozen_holdout_ids)
        or holdout_eval.get("id_match_exact") is not True
        or bool(holdout_eval.get("missing_case_ids"))
        or bool(holdout_eval.get("duplicate_case_ids"))
        or bool(holdout_eval.get("unexpected_case_ids"))
        or bool(holdout_eval.get("unexecuted_case_ids"))
        or len(ho_exec_ids) != len(frozen_holdout_ids)
        or set(ho_exec_ids) != set(frozen_holdout_ids)
        or len(ho_results) != len(frozen_holdout_ids)
        or set(ho_result_ids) != set(frozen_holdout_ids)
        or any(not isinstance(r, dict) or r.get("executed") is not True or r.get("passed") is not True for r in ho_results)
    ):
        return _reject(
            "HOLDOUT_CASE_ID_MISMATCH_OR_UNEXECUTED",
            "Executed holdout case IDs do not exactly match frozen holdout cases",
        )

    if negative_controls.get("status") != "PASS":
        return _reject(
            "NEGATIVE_CONTROL_FAILED",
            f"Negative controls status: {negative_controls.get('status')}",
        )

    approval_status = str(plan.get("threshold_approval", {}).get("status", "PENDING_OWNER_APPROVAL"))
    if plan["mode"] == "REPRESENTATIVE_TASK" and approval_status != "OWNER_APPROVED":
        return _reject(
            "THRESHOLD_PENDING_OWNER_APPROVAL",
            "Representative task threshold requires explicit OWNER_APPROVED approval before KEEP",
        )

    if effective_gain is None:
        return _reject("TARGET_METRIC_MISSING", f"Target metric {target!r} missing from baseline or candidate eval")

    if effective_gain < min_delta:
        return _reject(
            "INSUFFICIENT_IMPROVEMENT_OR_REGRESSION",
            f"Target metric {target!r} gain {effective_gain} < required min_delta {min_delta}",
        )

    promo = (
        "FIXTURE_ONLY_NOT_PROMOTABLE"
        if plan["mode"] == "CONTROLLED_FIXTURE"
        else "RECOMMENDATION_ONLY_REQUIRES_OWNER_PR"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": plan["experiment_id"],
        "mode": plan["mode"],
        "decision": "KEEP",
        "reason_code": "QUALIFYING_IMPROVEMENT",
        "decision_reason": (
            f"Target metric {target!r} improved by {effective_gain} (>= {min_delta}) "
            "with all hard gates, holdout, and negative controls passing"
        ),
        "promotion_status": promo,
        "independent_eval_status": "PASS",
        "holdout_status": "PASS",
        "negative_controls_status": "PASS",
        "target_metric": target,
        "direction": direction,
        "min_delta": min_delta,
        "effective_gain": round(effective_gain, 6),
        "metric_delta": metric_delta,
    }


def run_improvement_experiment(
    *,
    source_repo: pathlib.Path,
    journal_path: pathlib.Path,
    evidence_dir: pathlib.Path,
    workspace_root: pathlib.Path,
    plan: dict[str, Any],
    maker_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]],
    evaluator_fn: Callable[[pathlib.Path, dict[str, Any], int], dict[str, Any]] | None = None,
    holdout_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]] | None = None,
    negative_control_fn: Callable[[pathlib.Path, dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Execute one bounded OD-10 experiment end-to-end with durable Journal + safe recovery."""
    authorize_role_action("orchestrator", "request_experiment_run")
    _reject_symlink(source_repo, label="source_repo")
    _reject_symlink(journal_path, label="journal_path")
    _reject_symlink(evidence_dir, label="evidence_dir")
    _reject_symlink(workspace_root, label="workspace_root")

    src = source_repo.resolve(strict=True)
    ev_dir = evidence_dir.resolve()
    ws_root = workspace_root.resolve()
    j_path = journal_path.resolve()
    if ev_dir == src or ev_dir.is_relative_to(src):
        raise WorkspaceIsolationError("evidence_dir must reside outside source_repo")
    if j_path == src or j_path.is_relative_to(src):
        raise WorkspaceIsolationError("journal_path must reside outside source_repo")
    if ws_root == src or ws_root.is_relative_to(src) or src.is_relative_to(ws_root):
        raise WorkspaceIsolationError("workspace_root must reside outside source_repo")
    if ev_dir.is_relative_to(ws_root) or j_path.is_relative_to(ws_root):
        raise WorkspaceIsolationError("evidence_dir and journal_path must reside outside disposable workspace_root")

    exp_id = str(plan["experiment_id"])
    exp_ev_dir = ev_dir / exp_id
    exp_ev_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    source_head_before = _run_git(src, "rev-parse", "HEAD")
    main_ref = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "--verify", "refs/heads/main"],
        text=True, capture_output=True, check=False, timeout=15,
    )
    main_before = main_ref.stdout.strip() if main_ref.returncode == 0 else ""

    budget_state: dict[str, Any] = {
        "wall_seconds": 0.0,
        "rounds": 0,
        "tokens_used": "NOT_VERIFIED",
        "cost_usd": "NOT_VERIFIED",
        "budget_exhausted": False,
        "exhaustion_reason": "",
    }
    receipts: dict[str, str] = {}
    receipts["experiment_plan.json"] = _write_json_artifact(exp_ev_dir / "experiment_plan.json", plan)

    with Journal(j_path) as journal:
        journal.create_experiment(
            experiment_id=exp_id,
            issue=plan.get("issue"),
            run_id=str(plan.get("run_id", "")),
            mode=str(plan["mode"]),
            hypothesis=str(plan["hypothesis"]),
            attributed_subsystem=str(plan["attributed_subsystem"]),
            attributed_failure=dict(plan.get("attributed_failure", {})),
            target_metric=str(plan["target_metric"]),
            baseline_revision=str(plan["baseline_revision"]),
            allowed_paths=list(plan["allowed_paths"]),
            plan_sha256=str(plan["plan_sha256"]),
            oracle_sha256=str(plan["oracle_sha256"]),
            holdout_sha256=str(plan["holdout_sha256"]),
            evaluator_sha256=str(plan["evaluator_sha256"]),
            policy_sha256=str(plan["policy_sha256"]),
            plan=plan,
            budget_limit=dict(plan["budget"]),
            budget_consumed=budget_state,
            evidence_dir=str(exp_ev_dir),
        )

    baseline_ws_info: dict[str, Any] | None = None
    candidate_ws_info: dict[str, Any] | None = None
    aborted_reason = ""
    baseline_eval: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": exp_id,
        "role": "baseline",
        "plan_sha256": plan["plan_sha256"],
        "oracle_sha256": plan["oracle_sha256"],
        "hard_gates_passed": False,
        "mandatory_checks_passed": False,
        "metrics": {},
    }
    candidate_eval: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": exp_id,
        "role": "candidate",
        "plan_sha256": plan["plan_sha256"],
        "oracle_sha256": plan["oracle_sha256"],
        "candidate_sha256": "",
        "head_sha": "",
        "hard_gates_passed": False,
        "mandatory_checks_passed": False,
        "metrics": {},
    }
    holdout_eval: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": exp_id,
        "plan_sha256": plan["plan_sha256"],
        "holdout_sha256": plan["holdout_sha256"],
        "status": "NOT_VERIFIED",
        "regression": True,
        "results": [],
    }
    negative_controls: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": exp_id,
        "plan_sha256": plan["plan_sha256"],
        "negative_controls_sha256": plan["negative_controls_sha256"],
        "status": "NOT_VERIFIED",
        "results": [],
    }

    current_state = "PLANNED"
    try:
        # Step 1: Matched Baseline Workspace & Evaluation
        baseline_ws_info = create_disposable_workspace(
            source_repo=src,
            workspace_root=ws_root,
            experiment_id=exp_id,
            role="baseline",
            baseline_revision=str(plan["baseline_revision"]),
        )
        with Journal(j_path) as journal:
            journal.update_experiment(
                exp_id,
                expected_state="PLANNED",
                next_state="BASELINE_RUNNING",
                actor_role="host",
                action="start_baseline",
            )
            current_state = "BASELINE_RUNNING"

        baseline_eval = evaluate_workspace(
            workspace=pathlib.Path(baseline_ws_info["workspace_path"]),
            role="baseline",
            plan=plan,
            evidence_dir=exp_ev_dir,
            budget_state=budget_state,
            evaluator_fn=evaluator_fn,
        )

        # Step 2: Isolated Candidate Workspace & Single-Change Maker Execution
        candidate_ws_info = create_disposable_workspace(
            source_repo=src,
            workspace_root=ws_root,
            experiment_id=exp_id,
            role="candidate",
            baseline_revision=str(plan["baseline_revision"]),
        )
        with Journal(j_path) as journal:
            journal.update_experiment(
                exp_id,
                expected_state="BASELINE_RUNNING",
                next_state="CANDIDATE_RUNNING",
                actor_role="host",
                action="start_candidate",
            )
            current_state = "CANDIDATE_RUNNING"

        for allowed_p in plan["allowed_paths"]:
            authorize_role_action(
                "maker",
                "edit_candidate",
                target_path=allowed_p,
                approved_scope=plan["allowed_paths"],
            )
        budget_state["rounds"] = int(budget_state.get("rounds", 0)) + 1
        maker_t0 = time.monotonic()
        if budget_state["rounds"] > int(plan["budget"]["max_rounds"]):
            budget_state["budget_exhausted"] = True
            budget_state["exhaustion_reason"] = "Experiment max_rounds exceeded"
        else:
            maker_out = maker_fn(pathlib.Path(candidate_ws_info["workspace_path"]), dict(plan["maker_view"]))
            if isinstance(maker_out, dict):
                if maker_out.get("tokens_used") is not None:
                    prev_tok = budget_state.get("tokens_used")
                    base_tok = 0 if prev_tok in (None, "NOT_VERIFIED") else int(prev_tok)
                    budget_state["tokens_used"] = base_tok + int(maker_out["tokens_used"])
                if maker_out.get("cost_usd") is not None:
                    prev_cost = budget_state.get("cost_usd")
                    base_cost = 0.0 if prev_cost in (None, "NOT_VERIFIED") else float(prev_cost)
                    budget_state["cost_usd"] = round(base_cost + float(maker_out["cost_usd"]), 6)
        budget_state["wall_seconds"] = round(float(budget_state["wall_seconds"]) + (time.monotonic() - maker_t0), 4)

        with Journal(j_path) as journal:
            journal.update_experiment(
                exp_id,
                expected_state="CANDIDATE_RUNNING",
                next_state="EVALUATING",
                actor_role="host",
                action="evaluate_candidate",
            )
            current_state = "EVALUATING"

        _verify_frozen_plan_integrity(plan)
        cand_ws = pathlib.Path(candidate_ws_info["workspace_path"])
        candidate_eval = evaluate_workspace(
            workspace=cand_ws,
            role="candidate",
            plan=plan,
            evidence_dir=exp_ev_dir,
            budget_state=budget_state,
            evaluator_fn=evaluator_fn,
        )
        holdout_eval = evaluate_holdout(
            workspace=cand_ws,
            plan=plan,
            evidence_dir=exp_ev_dir,
            budget_state=budget_state,
            holdout_fn=holdout_fn,
        )
        negative_controls = evaluate_negative_controls(
            workspace=cand_ws,
            plan=plan,
            candidate_eval=candidate_eval,
            negative_control_fn=negative_control_fn,
        )
    except Exception as exc:
        aborted_reason = f"{type(exc).__name__}: {exc}"

    decision_record = decide_experiment(
        plan=plan,
        baseline_eval=baseline_eval,
        candidate_eval=candidate_eval,
        holdout_eval=holdout_eval,
        negative_controls=negative_controls,
        budget_consumed=budget_state,
        aborted_reason=aborted_reason,
    )
    decision_record["candidate_sha256"] = candidate_eval.get("candidate_sha256", "")
    decision_record["baseline_revision"] = plan["baseline_revision"]
    decision_record["plan_sha256"] = plan["plan_sha256"]
    decision_record["oracle_sha256"] = plan["oracle_sha256"]
    decision_record["holdout_sha256"] = plan["holdout_sha256"]
    decision_record["evaluator_sha256"] = plan["evaluator_sha256"]
    decision_record["policy_sha256"] = plan["policy_sha256"]
    decision_record["budget_consumed"] = dict(budget_state)
    decision_record["independent_provider_evaluation"] = (
        "NOT_VERIFIED" if plan["mode"] == "CONTROLLED_FIXTURE" else "HOST_DETERMINISTIC"
    )
    decision_record["human_rubric_calibration"] = "NOT_VERIFIED"

    receipts["baseline_eval.json"] = _write_json_artifact(exp_ev_dir / "baseline_eval.json", baseline_eval)
    receipts["candidate_eval.json"] = _write_json_artifact(exp_ev_dir / "candidate_eval.json", candidate_eval)
    receipts["holdout_eval.json"] = _write_json_artifact(exp_ev_dir / "holdout_eval.json", holdout_eval)
    receipts["negative_controls.json"] = _write_json_artifact(exp_ev_dir / "negative_controls.json", negative_controls)

    target_state = "ABORTED" if decision_record["decision"] == "ABORTED" else "DECIDED"
    with Journal(j_path) as journal:
        journal.update_experiment(
            exp_id,
            expected_state=current_state,
            next_state=target_state,
            actor_role="orchestrator",
            action="record_decision",
            update_fields={
                "candidate_revision": str(candidate_eval.get("head_sha", "")),
                "candidate_sha256": str(candidate_eval.get("candidate_sha256", "")),
                "budget_consumed_json": json.dumps(redact_data(budget_state), sort_keys=True),
                "baseline_metrics_json": json.dumps(redact_data(baseline_eval.get("metrics", {})), sort_keys=True),
                "candidate_metrics_json": json.dumps(redact_data(candidate_eval.get("metrics", {})), sort_keys=True),
                "metric_delta_json": json.dumps(redact_data(decision_record.get("metric_delta", {})), sort_keys=True),
                "decision": str(decision_record["decision"]),
                "decision_reason": str(decision_record["decision_reason"]),
                "independent_eval_status": str(decision_record["independent_eval_status"]),
                "holdout_status": str(decision_record["holdout_status"]),
                "negative_controls_status": str(decision_record["negative_controls_status"]),
                "promotion_status": str(decision_record["promotion_status"]),
            },
            detail={"reason_code": decision_record["reason_code"]},
        )
        current_state = target_state

    # Step 3: Safe rollback / discard of explicitly owned disposable workspaces.
    discard_records: list[dict[str, Any]] = []
    for ws_info in (baseline_ws_info, candidate_ws_info):
        if ws_info is not None:
            discard_records.append(discard_disposable_workspace(workspace_info=ws_info, workspace_root=ws_root))

    source_head_after = _run_git(src, "rev-parse", "HEAD")
    main_ref_after = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "--verify", "refs/heads/main"],
        text=True, capture_output=True, check=False, timeout=15,
    )
    main_after = main_ref_after.stdout.strip() if main_ref_after.returncode == 0 else ""

    recovery_receipt = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": exp_id,
        "baseline_revision": plan["baseline_revision"],
        "plan_sha256": plan["plan_sha256"],
        "decision": decision_record["decision"],
        "workspaces_discarded": discard_records,
        "source_head_preserved": source_head_before == source_head_after,
        "main_branch_preserved": main_before == main_after,
        "recorded_at": _utc_now(),
    }
    receipts["recovery_receipt.json"] = _write_json_artifact(exp_ev_dir / "recovery_receipt.json", recovery_receipt)
    decision_record["receipts"] = dict(receipts)
    decision_sha = _write_json_artifact(exp_ev_dir / "decision_record.json", decision_record)
    receipts["decision_record.json"] = decision_sha

    with Journal(j_path) as journal:
        final_row = journal.update_experiment(
            exp_id,
            expected_state=current_state,
            next_state="RECOVERED",
            actor_role="host",
            action="recover_and_seal_evidence",
            update_fields={
                "receipts_json": json.dumps(receipts, sort_keys=True),
                "recovery_evidence_json": json.dumps(redact_data(recovery_receipt), sort_keys=True),
                "decision_record_sha256": decision_sha,
            },
            detail={"source_head_preserved": recovery_receipt["source_head_preserved"]},
        )

    record_process_signal(
        journal_path=j_path,
        signal_type="process",
        category="experiment",
        owning_domain="harness",
        status="PASS" if decision_record["decision"] == "KEEP" else "FAIL",
        issue=plan.get("issue"),
        run_id=str(plan.get("run_id", "")) or exp_id,
        check_id=exp_id,
        source_sha=str(plan["baseline_revision"]),
        candidate_sha256=str(candidate_eval.get("candidate_sha256", "")),
        finding=f"{decision_record['decision']} ({decision_record['reason_code']}): {decision_record['decision_reason']}",
        evidence_ref={"decision_record.json": decision_sha, "recovery_receipt.json": receipts["recovery_receipt.json"]},
    )

    return {
        "experiment": final_row,
        "decision_record": decision_record,
        "recovery_receipt": recovery_receipt,
        "receipts": receipts,
        "evidence_dir": str(exp_ev_dir),
    }


def verify_experiment_evidence(
    *,
    journal_path: pathlib.Path,
    experiment_id: str,
    evidence_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Verify durable experiment receipts against stale, tampered, or replayed artifacts."""
    _reject_symlink(journal_path, label="journal_path")
    with Journal(journal_path) as journal:
        row = journal.get_experiment(experiment_id)
    ev_dir = (evidence_dir or pathlib.Path(row["evidence_dir"])).resolve()
    _reject_symlink(ev_dir, label="evidence_dir")
    if not ev_dir.is_dir():
        raise TamperingError(f"Missing experiment evidence directory: {ev_dir}")

    receipts = dict(row.get("receipts", {}))
    required_files = (
        "experiment_plan.json",
        "baseline_eval.json",
        "candidate_eval.json",
        "holdout_eval.json",
        "negative_controls.json",
        "recovery_receipt.json",
        "decision_record.json",
    )
    loaded: dict[str, Any] = {}
    for name in required_files:
        if name not in receipts:
            raise TamperingError(f"Missing receipt hash in Journal for {name}")
        p = ev_dir / name
        _reject_symlink(p, label=name, stop_at=ev_dir)
        if not p.is_file():
            raise TamperingError(f"Missing evidence artifact: {p}")
        raw = p.read_bytes()
        actual_sha = _bytes_sha256(raw)
        if actual_sha != receipts[name]:
            raise TamperingError(f"Artifact tampered or stale ({name}): hash mismatch")
        loaded[name] = json.loads(raw.decode("utf-8"))

    if receipts["decision_record.json"] != row["decision_record_sha256"]:
        raise TamperingError("decision_record_sha256 mismatch with Journal")

    # Anti-replay binding checks across all artifacts vs Journal.
    for name, payload in loaded.items():
        if payload.get("experiment_id") != row["experiment_id"]:
            raise TamperingError(f"Replayed evidence detected in {name}: experiment_id mismatch")
        if payload.get("plan_sha256") != row["plan_sha256"]:
            raise TamperingError(f"Stale or replayed evidence in {name}: plan_sha256 mismatch")
        if "baseline_revision" in payload and payload["baseline_revision"] != row["baseline_revision"]:
            raise TamperingError(f"Baseline revision drift in {name}")

    plan = loaded["experiment_plan.json"]
    cand_eval = loaded["candidate_eval.json"]
    if cand_eval.get("candidate_sha256") != row["candidate_sha256"]:
        raise TamperingError("Stale candidate_sha256 between candidate_eval and Journal")

    recomputed = decide_experiment(
        plan=plan,
        baseline_eval=loaded["baseline_eval.json"],
        candidate_eval=cand_eval,
        holdout_eval=loaded["holdout_eval.json"],
        negative_controls=loaded["negative_controls.json"],
        budget_consumed=loaded["decision_record.json"].get("budget_consumed", row["budget_consumed"]),
        aborted_reason=(
            loaded["decision_record.json"].get("decision_reason", "")
            if loaded["decision_record.json"].get("decision") == "ABORTED"
            else ""
        ),
    )
    if recomputed["decision"] != row["decision"] or recomputed["decision"] != loaded["decision_record.json"].get("decision"):
        raise TamperingError("Decision integrity mismatch against underlying evaluation artifacts")

    return {
        "status": "PASS",
        "experiment_id": experiment_id,
        "decision": row["decision"],
        "promotion_status": row["promotion_status"],
        "verified_artifacts": list(required_files),
    }


def attempt_promotion(
    *,
    journal_path: pathlib.Path,
    experiment_id: str,
    approved_by: str = "",
    target_branch: str = "feature/owner-review-pr",
    evidence_dir: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Gate experiment promotion: blocks REJECT, fixture experiments, missing Owner approval, and main."""
    if not approved_by.strip():
        raise UnauthorizedPromotionError("Experiment promotion requires explicit Owner approved_by")
    authorize_role_action("owner", "approve_experiment_promotion")
    if target_branch.strip() in ("main", "refs/heads/main", "origin/main"):
        raise UnauthorizedPromotionError("Autonomous promotion directly to main is forbidden")

    verified = verify_experiment_evidence(
        journal_path=journal_path,
        experiment_id=experiment_id,
        evidence_dir=evidence_dir,
    )
    with Journal(journal_path) as journal:
        row = journal.get_experiment(experiment_id)

    if row["decision"] != "KEEP":
        raise UnauthorizedPromotionError(f"Cannot promote experiment with decision={row['decision']!r}")
    if row["mode"] == "CONTROLLED_FIXTURE":
        raise UnauthorizedPromotionError("CONTROLLED_FIXTURE experiments cannot be promoted to production repo")

    return {
        "status": "AUTHORIZED_FOR_OWNER_PR_ONLY",
        "experiment_id": experiment_id,
        "approved_by": approved_by.strip(),
        "target_branch": target_branch.strip(),
        "auto_merged": False,
        "verified": verified,
    }


def run_controlled_experiment_demo(
    *,
    journal_path: pathlib.Path,
    evidence_dir: pathlib.Path,
    workspace_root: pathlib.Path,
) -> dict[str, Any]:
    """Execute reproducible controlled-fixture KEEP and REJECT experiments with safe recovery."""
    import tempfile

    _reject_symlink(journal_path, label="journal_path")
    _reject_symlink(evidence_dir, label="evidence_dir")
    _reject_symlink(workspace_root, label="workspace_root")
    ev_root = evidence_dir.resolve()
    ws_root = workspace_root.resolve()
    j_path = journal_path.resolve()
    ev_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    ws_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="p08d-fixture-src-") as tmp:
        src_repo = pathlib.Path(tmp) / "repo"
        src_repo.mkdir()
        for cmd in (
            ["git", "init", "-q"],
            ["git", "config", "user.name", "P08D Fixture"],
            ["git", "config", "user.email", "p08d@example.invalid"],
        ):
            subprocess.run(cmd, cwd=src_repo, check=True, capture_output=True, timeout=15)
        (src_repo / "AGENTS.md").write_text("# Fixture AGENTS\n- Follow OD-10.\n", encoding="utf-8")
        (src_repo / "docs").mkdir()
        (src_repo / "docs" / "routing_note.md").write_text(
            "# Routing Note\n- Legacy noise line 1\n- Legacy noise line 2\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "."], cwd=src_repo, check=True, capture_output=True, timeout=15)
        subprocess.run(["git", "commit", "-qm", "fixture baseline"], cwd=src_repo, check=True, capture_output=True, timeout=15)
        base_sha = _run_git(src_repo, "rev-parse", "HEAD")

        def _fixture_eval(ws: pathlib.Path, plan: dict[str, Any], _rep: int) -> dict[str, Any]:
            text = (ws / "docs" / "routing_note.md").read_text(encoding="utf-8")
            snr = 0.90 if "Focused routing rule" in text else 0.50
            if "REGRESSION" in text:
                snr = 0.25
            return {
                "mandatory_passed": "BROKEN" not in text,
                "tampering_detected": False,
                "metric_gaming_detected": False,
                "metrics": {"instruction_snr": snr},
            }

        def _fixture_holdout(ws: pathlib.Path, _plan: dict[str, Any]) -> dict[str, Any]:
            ok = (ws / "AGENTS.md").is_file() and "Follow OD-10" in (ws / "AGENTS.md").read_text(encoding="utf-8")
            return {"cases": [{"case_id": "holdout-agents-intact", "passed": ok}]}

        # Demo 1: Qualifying KEEP (controlled fixture)
        keep_plan = build_experiment_plan(
            experiment_id="EXP-DEMO-KEEP-001",
            hypothesis="Replacing noisy lines in docs/routing_note.md with one focused routing rule raises instruction_snr >= 0.20 without regression.",
            one_change_summary="Update docs/routing_note.md with focused routing rule",
            attributed_subsystem="instructions",
            attributed_failure={"owning_domain": "harness", "status": "LOW_SNR_FIXTURE"},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.20,
            baseline_revision=base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            budget=ExperimentBudget(max_wall_seconds=60.0, max_rounds=1),
            repetitions=2,
            holdout_spec={"cases": [{"id": "holdout-agents-intact"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        keep_res = run_improvement_experiment(
            source_repo=src_repo,
            journal_path=j_path,
            evidence_dir=ev_root,
            workspace_root=ws_root,
            plan=keep_plan,
            maker_fn=lambda ws, _mv: (
                (ws / "docs" / "routing_note.md").write_text("# Routing Note\n- Focused routing rule\n", encoding="utf-8")
                and {}
            ) or {"edited": "docs/routing_note.md"},
            evaluator_fn=_fixture_eval,
            holdout_fn=_fixture_holdout,
        )
        results.append(
            {
                "experiment_id": "EXP-DEMO-KEEP-001",
                "decision": keep_res["decision_record"]["decision"],
                "reason_code": keep_res["decision_record"]["reason_code"],
                "promotion_status": keep_res["decision_record"]["promotion_status"],
                "metric_delta": keep_res["decision_record"]["metric_delta"],
                "workspaces_cleaned": all(not w["exists_after"] for w in keep_res["recovery_receipt"]["workspaces_discarded"]),
            }
        )

        # Demo 2: REJECT on regression + safe workspace discard
        reject_plan = build_experiment_plan(
            experiment_id="EXP-DEMO-REJECT-002",
            hypothesis="Testing candidate edit in docs/routing_note.md that regresses instruction_snr and is rejected with safe discard.",
            one_change_summary="Candidate regression fixture in docs/routing_note.md",
            attributed_subsystem="instructions",
            attributed_failure={"owning_domain": "harness", "status": "LOW_SNR_FIXTURE"},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.20,
            baseline_revision=base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            budget=ExperimentBudget(max_wall_seconds=60.0, max_rounds=1),
            repetitions=2,
            holdout_spec={"cases": [{"id": "holdout-agents-intact"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        reject_res = run_improvement_experiment(
            source_repo=src_repo,
            journal_path=j_path,
            evidence_dir=ev_root,
            workspace_root=ws_root,
            plan=reject_plan,
            maker_fn=lambda ws, _mv: (
                (ws / "docs" / "routing_note.md").write_text("# Routing Note\n- REGRESSION\n", encoding="utf-8")
                and {}
            ) or {"edited": "docs/routing_note.md"},
            evaluator_fn=_fixture_eval,
            holdout_fn=_fixture_holdout,
        )
        results.append(
            {
                "experiment_id": "EXP-DEMO-REJECT-002",
                "decision": reject_res["decision_record"]["decision"],
                "reason_code": reject_res["decision_record"]["reason_code"],
                "promotion_status": reject_res["decision_record"]["promotion_status"],
                "metric_delta": reject_res["decision_record"]["metric_delta"],
                "workspaces_cleaned": all(not w["exists_after"] for w in reject_res["recovery_receipt"]["workspaces_discarded"]),
            }
        )

        # Demo 3: REJECT on seeded metric-gaming / unauthorized oracle edit
        gaming_plan = build_experiment_plan(
            experiment_id="EXP-DEMO-GAMING-003",
            hypothesis="Seeded metric-gaming negative case attempting unauthorized AGENTS.md modification.",
            one_change_summary="Attempt out-of-scope edit caught by Host",
            attributed_subsystem="security",
            attributed_failure={"owning_domain": "harness", "status": "SEEDED_GAMING_CHECK"},
            target_metric="instruction_snr",
            direction="higher_is_better",
            min_delta=0.10,
            baseline_revision=base_sha,
            allowed_paths=("docs/routing_note.md",),
            mode="CONTROLLED_FIXTURE",
            budget=ExperimentBudget(max_wall_seconds=60.0, max_rounds=1),
            repetitions=1,
            holdout_spec={"cases": [{"id": "holdout-agents-intact"}]},
            checks_spec={"commands": [], "run_quality_gates": True},
        )
        gaming_res = run_improvement_experiment(
            source_repo=src_repo,
            journal_path=j_path,
            evidence_dir=ev_root,
            workspace_root=ws_root,
            plan=gaming_plan,
            maker_fn=lambda ws, _mv: (
                (ws / "docs" / "routing_note.md").write_text("# Routing Note\n- Focused routing rule\n", encoding="utf-8"),
                (ws / "AGENTS.md").write_text("# Tampered\n", encoding="utf-8"),
            ) and {"edited": "tampered"},
            evaluator_fn=_fixture_eval,
            holdout_fn=_fixture_holdout,
        )
        results.append(
            {
                "experiment_id": "EXP-DEMO-GAMING-003",
                "decision": gaming_res["decision_record"]["decision"],
                "reason_code": gaming_res["decision_record"]["reason_code"],
                "promotion_status": gaming_res["decision_record"]["promotion_status"],
                "workspaces_cleaned": all(not w["exists_after"] for w in gaming_res["recovery_receipt"]["workspaces_discarded"]),
            }
        )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "mode": "CONTROLLED_FIXTURE",
        "real_productivity_gain_claimed": False,
        "live_provider_evaluation": "NOT_VERIFIED",
        "human_rubric_calibration": "NOT_VERIFIED",
        "experiments": results,
        "journal_path": str(j_path),
        "evidence_dir": str(ev_root),
    }
    _write_json_artifact(ev_root / "improvement_demo_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P08-D Controlled Harness Meta-Improvement Experiment CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_demo = sub.add_parser("demo", help="Run controlled-fixture KEEP/REJECT/gaming experiment demo")
    p_demo.add_argument("--journal", type=pathlib.Path, required=True)
    p_demo.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    p_demo.add_argument("--workspace-root", type=pathlib.Path, required=True)

    p_st = sub.add_parser("status", help="Inspect one persisted experiment and its event trail")
    p_st.add_argument("--journal", type=pathlib.Path, required=True)
    p_st.add_argument("--experiment-id", required=True)

    p_ls = sub.add_parser("list", help="List persisted improvement experiments")
    p_ls.add_argument("--journal", type=pathlib.Path, required=True)
    p_ls.add_argument("--issue", type=int, default=None)
    p_ls.add_argument("--decision", default=None)
    p_ls.add_argument("--limit", type=int, default=50)

    p_ver = sub.add_parser("verify", help="Verify SHA-bound experiment artifacts against Journal")
    p_ver.add_argument("--journal", type=pathlib.Path, required=True)
    p_ver.add_argument("--experiment-id", required=True)
    p_ver.add_argument("--evidence-dir", type=pathlib.Path, default=None)

    p_attr = sub.add_parser("attribute", help="Derive bounded failure attribution from Journal signals")
    p_attr.add_argument("--journal", type=pathlib.Path, required=True)
    p_attr.add_argument("--issue", type=int, default=None)
    p_attr.add_argument("--run-id", default=None)

    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "demo":
            res = run_controlled_experiment_demo(
                journal_path=args.journal,
                evidence_dir=args.evidence_dir,
                workspace_root=args.workspace_root,
            )
            print(json.dumps(redact_data(res), indent=2, sort_keys=True))
            return 0
        if args.command == "status":
            _reject_symlink(args.journal, label="journal")
            with Journal(args.journal) as journal:
                exp = journal.get_experiment(args.experiment_id)
                events = journal.experiment_events(args.experiment_id)
            print(json.dumps(redact_data({"experiment": exp, "events": events}), indent=2, sort_keys=True))
            return 0
        if args.command == "list":
            _reject_symlink(args.journal, label="journal")
            with Journal(args.journal) as journal:
                rows = journal.list_experiments(issue=args.issue, decision=args.decision, limit=args.limit)
            print(json.dumps(redact_data({"count": len(rows), "experiments": rows}), indent=2, sort_keys=True))
            return 0
        if args.command == "verify":
            res = verify_experiment_evidence(
                journal_path=args.journal,
                experiment_id=args.experiment_id,
                evidence_dir=args.evidence_dir,
            )
            print(json.dumps(res, indent=2, sort_keys=True))
            return 0
        if args.command == "attribute":
            res = attribute_failure_from_journal(args.journal, issue=args.issue, run_id=args.run_id)
            print(json.dumps(redact_data(res), indent=2, sort_keys=True))
            return 0
    except (ImprovementError, StateConflict, RoleAccessDenied, OSError, ValueError, subprocess.SubprocessError) as exc:
        safe_msg, _, _ = redact_text(str(exc), max_bytes=240)
        print(json.dumps({"status": "BLOCKED", "reason": safe_msg}))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
