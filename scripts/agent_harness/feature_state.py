"""P04 Feature State & Session Continuity (H2-STA-01..06, OD-02, OD-08).

Single source of truth ownership (OD-02):
- GitHub Issue: backlog, scope, acceptance criteria (issue_sha256, approved_scope)
- Git: revision identity (base_sha, head_sha, branch, candidate_sha256)
- SQLite Journal: local execution runs, CAS transitions, checkpoints
- Host receipts: trusted verification evidence (ONLY host_verifier marks PASSING)
- Versioned feature JSON: one-way durable export/handoff (no duplicate backlog)
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

try:
    from .agent_context import ContextGateError, load_context
    from .p1.state import Journal, StateConflict
    from .p1.worktrees import WorktreeError, inspect_worktree
    from .quality_gates import inventory, secret_line
    from .scope import parse_allowed_paths, violations
except ImportError:
    from agent_context import ContextGateError, load_context
    from p1.state import Journal, StateConflict
    from p1.worktrees import WorktreeError, inspect_worktree
    from quality_gates import inventory, secret_line
    from scope import parse_allowed_paths, violations

REPO = "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP"
SCHEMA_VERSION = "1.0"
UNIT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ABS_PATH_RE = re.compile(
    r"(?:^|[\s\"'=])(?:/(?:home|Users|tmp|var|etc|opt|root|mnt|srv)/|[A-Za-z]:\\\\|[A-Za-z]:/)"
)

UNIT_STATES = frozenset({"PENDING", "ACTIVE", "BLOCKED", "PASSING", "STALE"})
STATE_SYNONYMS = {
    "PENDING": "PENDING",
    "pending": "PENDING",
    "ACTIVE": "ACTIVE",
    "active": "ACTIVE",
    "IN_PROGRESS": "ACTIVE",
    "in_progress": "ACTIVE",
    "BLOCKED": "BLOCKED",
    "blocked": "BLOCKED",
    "PASSING": "PASSING",
    "passing": "PASSING",
    "STALE": "STALE",
    "stale": "STALE",
}
WRITER_ROLES = frozenset({"coordinator", "worker", "host_verifier", "operator"})
SOURCE_OF_TRUTH = {
    "backlog_scope": "github_issue",
    "revision": "git",
    "execution_journal": "sqlite_journal",
    "verification_evidence": "host_receipts",
    "feature_surface": "one_way_export_only",
}
FIELD_OWNERS = {
    "issue_meta": "github_issue",
    "git": "git",
    "units.definition": "coordinator_from_issue",
    "units.verification": "operator_or_approved_spec",
    "units.state.ACTIVE_BLOCKED_PENDING": "coordinator",
    "units.state.PASSING": "host_verifier",
    "units.state.STALE": "host_verifier",
    "units.evidence": "host_verifier",
    "handoff": "coordinator",
}
DEFAULT_DECISION_REFS = ("ADR-0004", "OD-02", "OD-08")


class FeatureStateError(RuntimeError):
    """Base error for feature state & session continuity."""


class ValidationError(FeatureStateError):
    """Schema, ID, scope, path hygiene, or secret validation failure."""


class UnauthorizedTransition(FeatureStateError):
    """Actor is not permitted to perform the requested state transition."""


class WIPViolation(FeatureStateError):
    """More than one unit cannot be ACTIVE in the same Issue execution."""


class DependencyBlocked(FeatureStateError):
    """Unit dependencies are missing or not yet PASSING."""


class RevisionConflict(FeatureStateError):
    """CAS revision mismatch or stale revision/receipt."""


class VerificationTamperError(FeatureStateError):
    """Unauthorized or unexpected modification to a unit's verification definition."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_unit_state(raw: str) -> str:
    if not isinstance(raw, str) or raw not in STATE_SYNONYMS:
        raise ValidationError(f"Unknown or unsupported unit state: {raw!r}")
    return STATE_SYNONYMS[raw]


def compute_verification_sha256(verification: dict[str, Any]) -> str:
    if not isinstance(verification, dict):
        raise ValidationError("Unit verification definition must be an object")
    criteria = verification.get("criteria")
    commands = verification.get("commands")
    if (
        not isinstance(criteria, list)
        or not criteria
        or not all(isinstance(c, str) and c.strip() for c in criteria)
    ):
        raise ValidationError("Unit verification.criteria must be a non-empty list of strings")
    if (
        not isinstance(commands, list)
        or not commands
        or not all(isinstance(c, str) and c.strip() for c in commands)
    ):
        raise ValidationError("Unit verification.commands must be a non-empty list of strings")
    payload = {"criteria": criteria, "commands": commands}
    return _sha256_bytes(_canonical_json(payload).encode("utf-8"))


def validate_relative_path(path: str, *, label: str = "path") -> str:
    if not isinstance(path, str) or not path.strip() or path != path.strip():
        raise ValidationError(f"Invalid {label}: {path!r}")
    if path.startswith("/") or "\\" in path or "//" in path:
        raise ValidationError(f"Absolute or backslash {label} forbidden: {path!r}")
    pp = pathlib.PurePosixPath(path)
    if ".." in pp.parts or ABS_PATH_RE.search(path):
        raise ValidationError(f"Unsafe {label}: {path!r}")
    return path


def _check_portable_hygiene(obj: Any) -> None:
    serialized = json.dumps(obj, sort_keys=True, ensure_ascii=False)
    raw = serialized.encode("utf-8")
    if secret_line(raw):
        raise ValidationError("Secret signature detected in feature state payload")
    if ABS_PATH_RE.search(serialized):
        raise ValidationError("Absolute machine path forbidden in portable feature state")


def _validate_evidence(
    evidence: Any,
    *,
    expected_verification_sha256: str,
    label: str = "evidence",
) -> dict[str, Any]:
    if not isinstance(evidence, dict):
        raise ValidationError(f"{label} must be an object")
    if evidence.get("verified_by") != "host_verifier":
        raise UnauthorizedTransition(f"{label}.verified_by must be 'host_verifier'")
    if evidence.get("exit_code") != 0:
        raise ValidationError(f"{label}.exit_code must be 0")
    if evidence.get("status") not in ("VERIFIED", "PASS", "AUTO_CHECK_PASS"):
        raise ValidationError(f"{label}.status is not a valid passing host status")
    if not SHA1_RE.fullmatch(str(evidence.get("source_sha", ""))):
        raise ValidationError(f"{label}.source_sha must be a 40-char git SHA")
    if not SHA256_RE.fullmatch(str(evidence.get("candidate_sha256", ""))):
        raise ValidationError(f"{label}.candidate_sha256 must be a 64-char SHA-256")
    if evidence.get("verification_sha256") != expected_verification_sha256:
        raise VerificationTamperError(f"{label}.verification_sha256 does not match unit definition")
    if not SHA256_RE.fullmatch(str(evidence.get("receipt_sha256", ""))):
        raise ValidationError(f"{label}.receipt_sha256 must be a 64-char SHA-256")
    validate_relative_path(str(evidence.get("receipt_path", "")), label=f"{label}.receipt_path")
    return dict(evidence)


def _scope_covers(approved_scope: list[str] | tuple[str, ...], unit_path: str) -> bool:
    for entry in approved_scope:
        if entry.endswith("/"):
            if unit_path.startswith(entry) or (unit_path + "/") == entry:
                return True
        elif unit_path == entry:
            return True
    return False


def validate_unit(
    unit: dict[str, Any],
    *,
    approved_scope: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not isinstance(unit, dict):
        raise ValidationError("Each unit must be an object")
    uid = unit.get("id")
    if not isinstance(uid, str) or not UNIT_ID_RE.fullmatch(uid):
        raise ValidationError(f"Malformed unit id: {uid!r}")
    behavior = unit.get("behavior")
    if not isinstance(behavior, str) or not behavior.strip() or len(behavior) > 500:
        raise ValidationError(f"Unit {uid}: behavior must be a non-empty string <= 500 chars")
    verification = copy.deepcopy(unit.get("verification"))
    computed_hash = compute_verification_sha256(verification)
    declared_hash = verification.get("definition_sha256")
    if declared_hash is not None and declared_hash != computed_hash:
        raise VerificationTamperError(f"Unit {uid}: verification definition_sha256 mismatch")
    verification["definition_sha256"] = computed_hash

    deps = unit.get("dependencies", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) and UNIT_ID_RE.fullmatch(d) for d in deps):
        raise ValidationError(f"Unit {uid}: dependencies must be a list of valid unit IDs")
    if uid in deps:
        raise ValidationError(f"Unit {uid}: self-dependency forbidden")
    if len(deps) != len(set(deps)):
        raise ValidationError(f"Unit {uid}: duplicate dependency IDs")

    scope = unit.get("scope")
    if not isinstance(scope, list) or not scope:
        raise ValidationError(f"Unit {uid}: scope must be a non-empty list")
    normalized_scope = [validate_relative_path(s, label=f"unit {uid} scope") for s in scope]
    if approved_scope:
        for path in normalized_scope:
            if not _scope_covers(approved_scope, path):
                raise ValidationError(f"Unit {uid}: scope {path!r} is outside Issue approved_scope")

    state = normalize_unit_state(unit.get("state", "PENDING"))
    blocker = str(unit.get("blocker", "") or "")
    if state == "BLOCKED" and not blocker.strip():
        raise ValidationError(f"Unit {uid}: BLOCKED unit requires non-empty blocker reason")

    raw_history = unit.get("evidence_history", [])
    if not isinstance(raw_history, list):
        raise ValidationError(f"Unit {uid}: evidence_history must be a list")
    history: list[dict[str, Any]] = []
    for idx, entry in enumerate(raw_history):
        if not isinstance(entry, dict):
            raise ValidationError(f"Unit {uid}: evidence_history[{idx}] must be an object")
        history.append(dict(entry))

    evidence = unit.get("evidence")
    if state == "PASSING":
        if evidence is None:
            raise ValidationError(f"Unit {uid}: PASSING unit requires bound host evidence")
        evidence = _validate_evidence(
            evidence, expected_verification_sha256=computed_hash, label=f"unit {uid} evidence"
        )
    elif evidence is not None:
        raise ValidationError(f"Unit {uid}: non-PASSING state {state} must not carry active passing evidence")

    return {
        "id": uid,
        "behavior": behavior.strip(),
        "verification": verification,
        "dependencies": list(deps),
        "scope": normalized_scope,
        "state": state,
        "blocker": blocker.strip(),
        "evidence": evidence,
        "evidence_history": history,
    }


def _check_dependency_graph(units: list[dict[str, Any]]) -> None:
    by_id = {u["id"]: u for u in units}
    for u in units:
        for dep in u["dependencies"]:
            if dep not in by_id:
                raise DependencyBlocked(f"Unit {u['id']}: missing dependency {dep!r}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(uid: str) -> None:
        if uid in visited:
            return
        if uid in visiting:
            raise ValidationError(f"Dependency cycle involving unit {uid!r}")
        visiting.add(uid)
        for dep in by_id[uid]["dependencies"]:
            dfs(dep)
        visiting.remove(uid)
        visited.add(uid)

    for uid in by_id:
        dfs(uid)


def validate_feature_doc(
    doc: dict[str, Any],
    *,
    check_secrets: bool = True,
    check_paths: bool = True,
) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise ValidationError("Feature document must be a JSON object")
    if doc.get("schema_version") != SCHEMA_VERSION:
        raise ValidationError(f"Unsupported schema_version: {doc.get('schema_version')!r}")
    issue = doc.get("issue")
    if not isinstance(issue, int) or isinstance(issue, bool) or issue < 1:
        raise ValidationError("issue must be a positive integer")
    revision = doc.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ValidationError("revision must be an integer >= 1")

    sot = doc.get("source_of_truth")
    if not isinstance(sot, dict) or sot != SOURCE_OF_TRUTH:
        raise ValidationError("source_of_truth must match OD-02 single-writer contract")

    issue_meta = doc.get("issue_meta", {})
    if not isinstance(issue_meta, dict):
        raise ValidationError("issue_meta must be an object")
    approved_scope = list(issue_meta.get("approved_scope", []))
    for path in approved_scope:
        validate_relative_path(path, label="approved_scope")
    issue_sha = str(issue_meta.get("issue_sha256", "") or "")
    if issue_sha and not SHA256_RE.fullmatch(issue_sha):
        raise ValidationError("issue_meta.issue_sha256 must be 64-char hex when present")

    git_meta = doc.get("git", {})
    if not isinstance(git_meta, dict):
        raise ValidationError("git metadata must be an object")
    for sha_key in ("base_sha", "head_sha"):
        val = str(git_meta.get(sha_key, "") or "")
        if val and not SHA1_RE.fullmatch(val):
            raise ValidationError(f"git.{sha_key} must be 40-char hex when present")
    cand_sha = str(git_meta.get("candidate_sha256", "") or "")
    if cand_sha and not SHA256_RE.fullmatch(cand_sha):
        raise ValidationError("git.candidate_sha256 must be 64-char hex when present")

    raw_units = doc.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise ValidationError("units must be a non-empty list")

    units: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_unit in raw_units:
        unit = validate_unit(raw_unit, approved_scope=approved_scope or None)
        if unit["id"] in seen_ids:
            raise ValidationError(f"Duplicate unit id: {unit['id']!r}")
        seen_ids.add(unit["id"])
        units.append(unit)

    _check_dependency_graph(units)

    active_units = [u["id"] for u in units if u["state"] == "ACTIVE"]
    if len(active_units) > 1:
        raise WIPViolation(f"WIP=1 violated: multiple ACTIVE units {active_units}")

    handoff = doc.get("handoff", {})
    if not isinstance(handoff, dict):
        raise ValidationError("handoff must be an object")
    active_handoff = handoff.get("active_unit")
    if active_handoff is not None:
        if active_handoff not in seen_ids:
            raise ValidationError(f"handoff.active_unit {active_handoff!r} does not exist in units")
        if active_units and active_handoff != active_units[0]:
            raise ValidationError("handoff.active_unit disagrees with ACTIVE unit in units")
    elif active_units:
        raise ValidationError("handoff.active_unit must match the ACTIVE unit")

    worktree_rel = str(handoff.get("worktree_rel", ".") or ".")
    if worktree_rel != ".":
        validate_relative_path(worktree_rel, label="handoff.worktree_rel")

    evidence_refs = handoff.get("evidence_refs", [])
    if not isinstance(evidence_refs, list):
        raise ValidationError("handoff.evidence_refs must be a list")
    cleaned_refs: list[dict[str, str]] = []
    for ref in evidence_refs:
        if not isinstance(ref, dict):
            raise ValidationError("handoff.evidence_refs entries must be objects")
        rpath = validate_relative_path(str(ref.get("path", "")), label="evidence_ref.path")
        rhash = str(ref.get("sha256", ""))
        if not SHA256_RE.fullmatch(rhash):
            raise ValidationError("evidence_ref.sha256 must be 64-char hex")
        cleaned_refs.append({"path": rpath, "sha256": rhash})

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "issue": issue,
        "revision": revision,
        "source_of_truth": dict(SOURCE_OF_TRUTH),
        "issue_meta": {
            "title": str(issue_meta.get("title", "") or "")[:180],
            "issue_sha256": issue_sha,
            "approved_scope": approved_scope,
        },
        "git": {
            "base_sha": str(git_meta.get("base_sha", "") or ""),
            "head_sha": str(git_meta.get("head_sha", "") or ""),
            "branch": str(git_meta.get("branch", "") or ""),
            "candidate_sha256": cand_sha,
        },
        "units": units,
        "handoff": {
            "active_unit": active_handoff,
            "completed_units": [u["id"] for u in units if u["state"] == "PASSING"],
            "evidence_refs": cleaned_refs,
            "blocker": str(handoff.get("blocker", "") or ""),
            "next_action": str(handoff.get("next_action", "") or ""),
            "decision_refs": list(handoff.get("decision_refs", list(DEFAULT_DECISION_REFS))),
            "worktree_rel": worktree_rel,
            "updated_at": str(handoff.get("updated_at", "") or _utc_now()),
        },
    }
    if check_secrets or check_paths:
        _check_portable_hygiene(normalized)
    return normalized


def create_feature_doc(
    issue: int,
    *,
    units: list[dict[str, Any]],
    title: str = "",
    issue_sha256: str = "",
    approved_scope: tuple[str, ...] | list[str] = (),
    base_sha: str = "",
    head_sha: str = "",
    branch: str = "",
    candidate_sha256: str = "",
    next_action: str = "Activate the first ready unit before editing",
    decision_refs: tuple[str, ...] | list[str] = DEFAULT_DECISION_REFS,
) -> dict[str, Any]:
    doc = {
        "schema_version": SCHEMA_VERSION,
        "issue": issue,
        "revision": 1,
        "source_of_truth": dict(SOURCE_OF_TRUTH),
        "issue_meta": {
            "title": title[:180],
            "issue_sha256": issue_sha256,
            "approved_scope": list(approved_scope),
        },
        "git": {
            "base_sha": base_sha,
            "head_sha": head_sha or base_sha,
            "branch": branch,
            "candidate_sha256": candidate_sha256,
        },
        "units": units,
        "handoff": {
            "active_unit": None,
            "completed_units": [],
            "evidence_refs": [],
            "blocker": "",
            "next_action": next_action,
            "decision_refs": list(decision_refs),
            "worktree_rel": ".",
            "updated_at": _utc_now(),
        },
    }
    return validate_feature_doc(doc)


def _find_unit(doc: dict[str, Any], unit_id: str) -> dict[str, Any]:
    for unit in doc["units"]:
        if unit["id"] == unit_id:
            return unit
    raise ValidationError(f"Unknown unit id: {unit_id!r}")


def _check_cas(doc: dict[str, Any], expected_revision: int | None) -> None:
    if expected_revision is not None and doc["revision"] != expected_revision:
        raise RevisionConflict(
            f"CAS revision mismatch: expected {expected_revision}, actual {doc['revision']}"
        )


def activate_unit(
    doc: dict[str, Any],
    unit_id: str,
    *,
    actor: str = "coordinator",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    if actor not in ("coordinator", "operator"):
        raise UnauthorizedTransition(f"Actor {actor!r} cannot activate units")
    updated = validate_feature_doc(copy.deepcopy(doc))
    _check_cas(updated, expected_revision)

    active = [u["id"] for u in updated["units"] if u["state"] == "ACTIVE" and u["id"] != unit_id]
    if active:
        raise WIPViolation(
            f"WIP=1 violation: unit {active[0]!r} is still ACTIVE; must be PASSING or BLOCKED first"
        )

    target = _find_unit(updated, unit_id)
    if target["state"] == "PASSING":
        raise ValidationError(f"Unit {unit_id!r} is already PASSING")

    by_id = {u["id"]: u for u in updated["units"]}
    unmet = [dep for dep in target["dependencies"] if by_id[dep]["state"] != "PASSING"]
    if unmet:
        raise DependencyBlocked(f"Unit {unit_id!r} has unmet dependencies: {unmet}")

    target["state"] = "ACTIVE"
    target["blocker"] = ""
    updated["revision"] += 1
    updated["handoff"]["active_unit"] = unit_id
    updated["handoff"]["blocker"] = ""
    updated["handoff"]["next_action"] = f"Implement and verify unit {unit_id}"
    updated["handoff"]["updated_at"] = _utc_now()
    return validate_feature_doc(updated)


def block_unit(
    doc: dict[str, Any],
    unit_id: str,
    *,
    reason: str,
    actor: str = "coordinator",
    expected_revision: int | None = None,
) -> dict[str, Any]:
    if actor not in ("coordinator", "operator", "host_verifier"):
        raise UnauthorizedTransition(f"Actor {actor!r} cannot block units")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("Blocking a unit requires a non-empty reason")
    updated = validate_feature_doc(copy.deepcopy(doc))
    _check_cas(updated, expected_revision)

    target = _find_unit(updated, unit_id)
    if target["state"] == "PASSING":
        raise ValidationError("Cannot mark a PASSING unit BLOCKED without drift/revalidation")
    target["state"] = "BLOCKED"
    target["blocker"] = reason.strip()[:300]
    target["evidence"] = None
    updated["revision"] += 1
    if updated["handoff"]["active_unit"] == unit_id:
        updated["handoff"]["active_unit"] = None
    updated["handoff"]["blocker"] = target["blocker"]
    updated["handoff"]["next_action"] = f"Resolve blocker on unit {unit_id}: {target['blocker']}"
    updated["handoff"]["updated_at"] = _utc_now()
    return validate_feature_doc(updated)


def verify_unit_passing(
    doc: dict[str, Any],
    unit_id: str,
    *,
    actor: str,
    receipt: dict[str, Any],
    expected_revision: int | None = None,
) -> dict[str, Any]:
    if actor != "host_verifier":
        raise UnauthorizedTransition(
            f"Only trusted host_verifier may mark unit PASSING (rejected actor={actor!r})"
        )
    if not isinstance(receipt, dict):
        raise ValidationError("Host verification receipt must be a dict")
    if receipt.get("waived") or receipt.get("owner_waived") or receipt.get("commit_only"):
        raise UnauthorizedTransition("Waivers or commits alone cannot mark a unit PASSING")
    if receipt.get("status") == "SCOPE_SCAN_PASS_ONLY":
        raise UnauthorizedTransition("SCOPE_SCAN_PASS_ONLY cannot mark a feature unit PASSING")
    if receipt.get("checks_complete") is not True:
        raise ValidationError("Host receipt must confirm checks_complete=true")

    updated = validate_feature_doc(copy.deepcopy(doc))
    _check_cas(updated, expected_revision)

    target = _find_unit(updated, unit_id)
    if target["state"] != "ACTIVE":
        raise ValidationError(
            f"Unit {unit_id!r} must be ACTIVE before PASSING (current state={target['state']})"
        )

    expected_source_sha = updated["git"].get("head_sha") or updated["git"].get("base_sha")
    expected_cand_sha = updated["git"].get("candidate_sha256")
    if expected_source_sha and receipt.get("source_sha") != expected_source_sha:
        raise RevisionConflict("Stale receipt: source_sha does not match current candidate")
    if expected_cand_sha and receipt.get("candidate_sha256") != expected_cand_sha:
        raise RevisionConflict("Stale receipt: candidate_sha256 does not match current candidate")

    normalized_evidence = _validate_evidence(
        {
            "verified_by": receipt.get("verified_by", actor),
            "status": receipt.get("status", "VERIFIED"),
            "exit_code": receipt.get("exit_code"),
            "source_sha": receipt.get("source_sha", expected_source_sha),
            "candidate_sha256": receipt.get("candidate_sha256", expected_cand_sha),
            "verification_sha256": receipt.get("verification_sha256"),
            "receipt_path": receipt.get("receipt_path"),
            "receipt_sha256": receipt.get("receipt_sha256"),
            "recorded_at": receipt.get("recorded_at") or _utc_now(),
        },
        expected_verification_sha256=target["verification"]["definition_sha256"],
        label="receipt",
    )

    target["state"] = "PASSING"
    target["blocker"] = ""
    target["evidence"] = normalized_evidence
    target["evidence_history"].append(copy.deepcopy(normalized_evidence))

    updated["revision"] += 1
    updated["handoff"]["active_unit"] = None
    updated["handoff"]["blocker"] = ""
    ref = {"path": normalized_evidence["receipt_path"], "sha256": normalized_evidence["receipt_sha256"]}
    if ref not in updated["handoff"]["evidence_refs"]:
        updated["handoff"]["evidence_refs"].append(ref)
    updated["handoff"]["updated_at"] = _utc_now()
    return validate_feature_doc(updated)


def reconcile_revision_drift(
    doc: dict[str, Any],
    *,
    current_source_sha: str,
    current_candidate_sha256: str,
    current_branch: str | None = None,
    current_issue_sha256: str | None = None,
    current_verifications: dict[str, dict[str, Any]] | None = None,
    allow_definition_change: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invalidate stale PASSING units on revision/verification drift while keeping history."""
    updated = validate_feature_doc(copy.deepcopy(doc))
    drift_reasons: list[str] = []
    stale_units: list[str] = []

    if current_verifications:
        for unit in updated["units"]:
            new_verif = current_verifications.get(unit["id"])
            if new_verif is None:
                continue
            new_hash = compute_verification_sha256(new_verif)
            if new_hash != unit["verification"]["definition_sha256"]:
                if not allow_definition_change:
                    raise VerificationTamperError(
                        f"Unit {unit['id']}: verification definition changed without authorization"
                    )
                unit["verification"] = {**copy.deepcopy(new_verif), "definition_sha256": new_hash}
                drift_reasons.append(f"verification_changed:{unit['id']}")

    prev_source = updated["git"].get("head_sha") or updated["git"].get("base_sha")
    prev_cand = updated["git"].get("candidate_sha256")
    if prev_source and prev_source != current_source_sha:
        drift_reasons.append("source_sha_changed")
    if prev_cand and prev_cand != current_candidate_sha256:
        drift_reasons.append("candidate_sha256_changed")

    issue_drift = False
    stored_issue_sha = updated["issue_meta"].get("issue_sha256", "")
    if current_issue_sha256 and stored_issue_sha and current_issue_sha256 != stored_issue_sha:
        issue_drift = True
        drift_reasons.append("issue_scope_changed")

    branch_mismatch = False
    stored_branch = updated["git"].get("branch", "")
    if current_branch and stored_branch and current_branch != stored_branch:
        branch_mismatch = True
        drift_reasons.append("branch_mismatch")

    for unit in updated["units"]:
        if unit["state"] != "PASSING" or unit["evidence"] is None:
            continue
        ev = unit["evidence"]
        reasons: list[str] = []
        if ev["source_sha"] != current_source_sha:
            reasons.append("source_sha_drift")
        if ev["candidate_sha256"] != current_candidate_sha256:
            reasons.append("candidate_sha256_drift")
        if ev["verification_sha256"] != unit["verification"]["definition_sha256"]:
            reasons.append("verification_definition_drift")
        if reasons:
            unit["state"] = "STALE"
            unit["evidence"] = None
            unit["evidence_history"].append({
                "status": "INVALIDATED",
                "reason": ",".join(reasons),
                "prior_candidate_sha256": ev["candidate_sha256"],
                "prior_source_sha": ev["source_sha"],
                "prior_receipt_sha256": ev["receipt_sha256"],
                "current_candidate_sha256": current_candidate_sha256,
                "current_source_sha": current_source_sha,
                "invalidated_at": _utc_now(),
            })
            stale_units.append(unit["id"])

    updated["git"]["head_sha"] = current_source_sha
    updated["git"]["candidate_sha256"] = current_candidate_sha256
    if drift_reasons or stale_units:
        updated["revision"] += 1
        updated["handoff"]["updated_at"] = _utc_now()

    return validate_feature_doc(updated), {
        "drift_reasons": drift_reasons,
        "stale_units": stale_units,
        "issue_drift": issue_drift,
        "branch_mismatch": branch_mismatch,
    }


def export_feature_doc(doc: dict[str, Any], out_path: pathlib.Path) -> pathlib.Path:
    validated = validate_feature_doc(doc)
    if out_path.is_symlink() or out_path.parent.is_symlink():
        raise ValidationError("Refusing to export feature state through symlink")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")
    if tmp.is_symlink():
        raise ValidationError("Refusing to write temporary feature export through symlink")
    payload = json.dumps(validated, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _check_portable_hygiene(validated)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, out_path)
    return out_path


def load_feature_doc(path: pathlib.Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValidationError(f"Feature state file missing or is a symlink: {path}")
    raw = path.read_bytes()
    if len(raw) > 512_000:
        raise ValidationError("Feature state file exceeds 512 KB bound")
    if secret_line(raw):
        raise ValidationError("Secret signature detected in feature state file")
    data = json.loads(raw.decode("utf-8"))
    return validate_feature_doc(data)


def _fetch_issue(repo: pathlib.Path, issue: int) -> dict[str, Any]:
    try:
        p = subprocess.run(
            ["gh", "issue", "view", str(issue), "--repo", REPO, "--json", "title,body,state"],
            cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=40, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FeatureStateError("Cannot query GitHub Issue") from exc
    if p.returncode or len(p.stdout) > 55_000:
        raise FeatureStateError("GitHub Issue lookup failed or exceeded limit")
    data = json.loads(p.stdout)
    if not isinstance(data, dict) or data.get("state") != "OPEN":
        raise FeatureStateError(f"Issue #{issue} is not OPEN")
    body = data.get("body")
    if not isinstance(body, str):
        raise FeatureStateError(f"Issue #{issue} body missing")
    scope = parse_allowed_paths(body)
    return {
        "title": str(data.get("title", ""))[:180],
        "body": body,
        "scope": scope,
        "issue_sha256": _sha256_bytes(body.encode("utf-8")),
    }


def _relative_worktree_label(repo_root: pathlib.Path, worktree_path: pathlib.Path) -> str:
    resolved_repo = repo_root.resolve()
    resolved_wt = worktree_path.resolve()
    if resolved_wt == resolved_repo:
        return "."
    try:
        rel = resolved_wt.relative_to(resolved_repo).as_posix()
        return validate_relative_path(rel, label="worktree_rel")
    except ValueError:
        return f"worktree:{resolved_wt.name}"


def compute_candidate_snapshot(repo: pathlib.Path, *, base_sha: str | None = None) -> dict[str, Any]:
    wt = inspect_worktree(repo, expected_base_sha=base_sha)
    inv_base = base_sha if (base_sha and wt.get("base_is_ancestor")) else "HEAD"
    source_info, _ = inventory(pathlib.Path(wt["worktree"]), inv_base)
    return {
        **wt,
        "source_sha": source_info["source_sha"],
        "base_sha": source_info["base_sha"],
        "candidate_sha256": source_info["candidate_sha256"],
        "changed_paths": source_info["changed_paths"],
    }


def _next_action_for(
    doc: dict[str, Any] | None,
    *,
    job: dict[str, Any] | None,
    wt: dict[str, Any],
    drift: dict[str, Any],
) -> tuple[str, str]:
    if job and job["state"] == "RECOVERY_REQUIRED":
        return (
            "RECOVERY_REQUIRED",
            "Inspect interrupted run worktree/branch and uncommitted files; do not reset or auto-retry.",
        )
    if drift.get("branch_mismatch"):
        return (
            "BLOCKED",
            "Current Git branch mismatches recorded Issue branch; verify worktree before editing.",
        )
    if drift.get("issue_drift"):
        return (
            "BLOCKED",
            "Live GitHub Issue body/scope changed since last checkpoint; review updated AC and re-scope.",
        )
    if doc is None:
        return (
            "NEEDS_INIT",
            "Initialize feature units for this Issue before starting implementation.",
        )

    active = [u for u in doc["units"] if u["state"] == "ACTIVE"]
    if active:
        u = active[0]
        return (
            "READY_TO_RESUME",
            f"Continue active unit {u['id']} ({u['behavior']}); run Host checks before marking PASSING.",
        )
    stale = [u for u in doc["units"] if u["state"] == "STALE"]
    if stale:
        u = stale[0]
        return (
            "READY_TO_RESUME",
            f"Re-activate and re-verify stale unit {u['id']} after revision drift.",
        )
    blocked = [u for u in doc["units"] if u["state"] == "BLOCKED"]
    by_id = {u["id"]: u for u in doc["units"]}
    ready = [
        u for u in doc["units"]
        if u["state"] == "PENDING" and all(by_id[d]["state"] == "PASSING" for d in u["dependencies"])
    ]
    if ready:
        u = ready[0]
        return ("READY_TO_RESUME", f"Activate next ready unit {u['id']}: {u['behavior']}")
    if blocked:
        u = blocked[0]
        return ("BLOCKED", f"Resolve blocker on unit {u['id']}: {u['blocker']}")
    if all(u["state"] == "PASSING" for u in doc["units"]):
        return (
            "ALL_UNITS_PASSING_LOCAL",
            "Run final quality_gates.py, fresh independent Auditor, and open/update Draft PR for human review.",
        )
    return ("BLOCKED", "No ready unit found; inspect unit dependencies and blockers.")


def session_start(
    *,
    issue: int,
    repo: pathlib.Path,
    state_db: pathlib.Path | None = None,
    feature_file: pathlib.Path | None = None,
    issue_data: dict[str, Any] | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """Verify G0 context, live Issue/worktree/candidate, and produce compact resume state."""
    root = repo.resolve()
    try:
        g0 = load_context(root)
    except ContextGateError as exc:
        return {"status": "BLOCKED", "issue": issue, "reason": f"G0 gate blocked: {exc}"}

    job: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    stored_doc: dict[str, Any] | None = None
    if state_db is not None and state_db.exists():
        with Journal(state_db) as journal:
            job = journal.active_job_for_issue(issue) or journal.latest_job_for_issue(issue)
            if job and job["state"] == "PREPARING":
                journal.detect_interruption(job["run_id"])
                job = journal.get(job["run_id"])
            snap = journal.get_feature_snapshot(issue)
            if snap is not None:
                stored_doc = validate_feature_doc(snap["doc"])
            checkpoint = journal.latest_checkpoint(issue)

    default_export = root / "docs" / "harness" / "features" / f"issue-{issue}.json"
    source_file = feature_file if feature_file is not None else (default_export if default_export.is_file() else None)
    if stored_doc is None and source_file is not None:
        stored_doc = load_feature_doc(source_file)

    expected_base = (
        (job["source_sha"] if job else None)
        or (stored_doc["git"].get("base_sha") if stored_doc else None)
        or None
    )
    snap_git = compute_candidate_snapshot(root, base_sha=expected_base)

    live_issue: dict[str, Any] | None = issue_data
    if live_issue is None and not offline:
        live_issue = _fetch_issue(root, issue)
    if live_issue is not None and snap_git["changed_paths"]:
        scope = live_issue.get("scope") or parse_allowed_paths(live_issue["body"])
        scope_errors = violations(root, scope, snap_git["changed_paths"])
        if scope_errors:
            return {
                "status": "BLOCKED",
                "issue": issue,
                "reason": "; ".join(scope_errors)[:240],
                "has_uncommitted_work": snap_git["dirty"],
                "next_action": "Preserve worktree changes and inspect out-of-scope paths before continuing.",
            }

    drift = {"drift_reasons": [], "stale_units": [], "issue_drift": False, "branch_mismatch": False}
    if stored_doc is not None:
        stored_doc, drift = reconcile_revision_drift(
            stored_doc,
            current_source_sha=snap_git["source_sha"],
            current_candidate_sha256=snap_git["candidate_sha256"],
            current_branch=snap_git["branch"],
            current_issue_sha256=live_issue.get("issue_sha256") if live_issue else None,
        )
        if state_db is not None and state_db.exists() and (drift["drift_reasons"] or drift["stale_units"]):
            with Journal(state_db) as journal:
                current_snap = journal.get_feature_snapshot(issue)
                if current_snap is not None:
                    journal.save_feature_snapshot(
                        issue=issue,
                        expected_revision=current_snap["revision"],
                        revision=stored_doc["revision"],
                        doc_json=json.dumps(stored_doc, sort_keys=True),
                        units=stored_doc["units"],
                        actor="host_verifier",
                    )

    status, next_action = _next_action_for(stored_doc, job=job, wt=snap_git, drift=drift)
    units_summary = (
        {
            "active": [u["id"] for u in stored_doc["units"] if u["state"] == "ACTIVE"],
            "passing": [u["id"] for u in stored_doc["units"] if u["state"] == "PASSING"],
            "stale": [u["id"] for u in stored_doc["units"] if u["state"] == "STALE"],
            "blocked": [{"id": u["id"], "reason": u["blocker"]} for u in stored_doc["units"] if u["state"] == "BLOCKED"],
            "pending": [u["id"] for u in stored_doc["units"] if u["state"] == "PENDING"],
        }
        if stored_doc
        else None
    )
    return {
        "status": status,
        "issue": issue,
        "agents_sha256": g0["agents_sha256"],
        "branch": snap_git["branch"],
        "source_sha": snap_git["source_sha"],
        "candidate_sha256": snap_git["candidate_sha256"],
        "has_uncommitted_work": snap_git["dirty"],
        "changed_paths": snap_git["changed_paths"],
        "job_state": job["state"] if job else None,
        "revision": stored_doc["revision"] if stored_doc else None,
        "units": units_summary,
        "drift": drift,
        "evidence_refs": stored_doc["handoff"]["evidence_refs"] if stored_doc else [],
        "decision_refs": stored_doc["handoff"]["decision_refs"] if stored_doc else list(DEFAULT_DECISION_REFS),
        "last_checkpoint_id": checkpoint["checkpoint_id"] if checkpoint else None,
        "next_action": next_action,
    }


def session_checkpoint(
    *,
    issue: int,
    repo: pathlib.Path,
    state_db: pathlib.Path,
    next_action: str,
    blocker: str = "",
    feature_file: pathlib.Path | None = None,
    export_path: pathlib.Path | None = None,
    decision_refs: tuple[str, ...] | list[str] = DEFAULT_DECISION_REFS,
    base_sha: str | None = None,
) -> dict[str, Any]:
    """Persist an atomic SQLite checkpoint and optional one-way portable export."""
    if not next_action.strip():
        raise ValidationError("Checkpoint requires a non-empty next_action")
    root = repo.resolve()
    snap_git = compute_candidate_snapshot(root, base_sha=base_sha)
    wt_rel = _relative_worktree_label(root, pathlib.Path(snap_git["worktree"]))

    with Journal(state_db) as journal:
        job = journal.active_job_for_issue(issue) or journal.latest_job_for_issue(issue)
        snap = journal.get_feature_snapshot(issue)
        doc: dict[str, Any] | None = None
        if snap is not None:
            doc = validate_feature_doc(snap["doc"])
        elif feature_file is not None and feature_file.is_file():
            doc = load_feature_doc(feature_file)

        active_unit = None
        issue_sha256 = ""
        evidence_refs: list[dict[str, str]] = []
        completed_units: list[str] = []
        if doc is not None:
            doc, _ = reconcile_revision_drift(
                doc,
                current_source_sha=snap_git["source_sha"],
                current_candidate_sha256=snap_git["candidate_sha256"],
                current_branch=snap_git["branch"],
            )
            active_unit = doc["handoff"]["active_unit"]
            issue_sha256 = doc["issue_meta"]["issue_sha256"]
            evidence_refs = doc["handoff"]["evidence_refs"]
            completed_units = doc["handoff"]["completed_units"]
            doc["handoff"]["blocker"] = blocker.strip()
            doc["handoff"]["next_action"] = next_action.strip()
            doc["handoff"]["decision_refs"] = list(decision_refs)
            doc["handoff"]["worktree_rel"] = wt_rel
            doc["handoff"]["updated_at"] = _utc_now()
            doc["revision"] += 1
            doc = validate_feature_doc(doc)
            journal.save_feature_snapshot(
                issue=issue,
                expected_revision=snap["revision"] if snap is not None else None,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="coordinator",
            )

        handoff = {
            "issue": issue,
            "branch": snap_git["branch"],
            "source_sha": snap_git["source_sha"],
            "candidate_sha256": snap_git["candidate_sha256"],
            "worktree_rel": wt_rel,
            "active_unit": active_unit,
            "completed_units": completed_units,
            "evidence_refs": evidence_refs,
            "blocker": blocker.strip(),
            "next_action": next_action.strip(),
            "decision_refs": list(decision_refs),
            "updated_at": _utc_now(),
        }
        _check_portable_hygiene(handoff)
        checkpoint_id = journal.record_checkpoint(
            issue=issue,
            run_id=job["run_id"] if job else None,
            revision_sha=snap_git["source_sha"],
            candidate_sha256=snap_git["candidate_sha256"],
            branch=snap_git["branch"],
            worktree_rel=wt_rel,
            active_unit=active_unit,
            blocker=blocker.strip(),
            next_action=next_action.strip(),
            decision_refs=decision_refs,
            issue_sha256=issue_sha256,
            handoff_json=json.dumps(handoff, sort_keys=True),
        )

    exported_to = None
    if export_path is not None and doc is not None:
        exported_to = str(export_feature_doc(doc, export_path))

    return {
        "status": "CHECKPOINT_SAVED",
        "checkpoint_id": checkpoint_id,
        "issue": issue,
        "source_sha": snap_git["source_sha"],
        "candidate_sha256": snap_git["candidate_sha256"],
        "active_unit": active_unit,
        "exported_to": exported_to,
        "next_action": next_action.strip(),
    }


def _load_from_journal_or_file(
    *, issue: int, state_db: pathlib.Path | None, feature_file: pathlib.Path | None
) -> tuple[dict[str, Any], int | None]:
    if state_db is not None and state_db.exists():
        with Journal(state_db) as journal:
            snap = journal.get_feature_snapshot(issue)
            if snap is not None:
                return validate_feature_doc(snap["doc"]), snap["revision"]
    if feature_file is not None:
        return load_feature_doc(feature_file), None
    raise ValidationError(f"No feature state found for Issue #{issue}")


def _save_to_journal_and_optional_file(
    doc: dict[str, Any],
    *,
    actor: str,
    expected_revision: int | None,
    state_db: pathlib.Path | None,
    feature_file: pathlib.Path | None,
) -> None:
    if state_db is not None:
        with Journal(state_db) as journal:
            snap = journal.get_feature_snapshot(doc["issue"])
            rev = snap["revision"] if snap is not None else None
            if expected_revision is not None and rev != expected_revision:
                raise RevisionConflict(f"CAS revision mismatch: expected {expected_revision}, actual {rev}")
            journal.save_feature_snapshot(
                issue=doc["issue"],
                expected_revision=rev,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor=actor,
            )
    if feature_file is not None:
        export_feature_doc(doc, feature_file)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P04 Feature State & Session Continuity CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Initialize per-Issue feature units")
    p_init.add_argument("--issue", type=int, required=True)
    p_init.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_init.add_argument("--units-file", type=pathlib.Path, required=True)
    p_init.add_argument("--state", type=pathlib.Path, default=None)
    p_init.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_init.add_argument("--offline", action="store_true")

    p_val = sub.add_parser("validate", help="Validate a feature state JSON file")
    p_val.add_argument("--feature-file", type=pathlib.Path, required=True)

    p_act = sub.add_parser("activate", help="Activate a ready unit (enforces WIP=1 and deps)")
    p_act.add_argument("--issue", type=int, required=True)
    p_act.add_argument("--unit-id", required=True)
    p_act.add_argument("--actor", default="coordinator")
    p_act.add_argument("--expected-revision", type=int, default=None)
    p_act.add_argument("--state", type=pathlib.Path, default=None)
    p_act.add_argument("--feature-file", type=pathlib.Path, default=None)

    p_blk = sub.add_parser("block", help="Mark a unit BLOCKED with mandatory reason")
    p_blk.add_argument("--issue", type=int, required=True)
    p_blk.add_argument("--unit-id", required=True)
    p_blk.add_argument("--reason", required=True)
    p_blk.add_argument("--actor", default="coordinator")
    p_blk.add_argument("--expected-revision", type=int, default=None)
    p_blk.add_argument("--state", type=pathlib.Path, default=None)
    p_blk.add_argument("--feature-file", type=pathlib.Path, default=None)

    p_ver = sub.add_parser("verify-unit", help="Host verifier transition to PASSING from receipt")
    p_ver.add_argument("--issue", type=int, required=True)
    p_ver.add_argument("--unit-id", required=True)
    p_ver.add_argument("--receipt", type=pathlib.Path, required=True)
    p_ver.add_argument("--actor", default="host_verifier")
    p_ver.add_argument("--expected-revision", type=int, default=None)
    p_ver.add_argument("--state", type=pathlib.Path, default=None)
    p_ver.add_argument("--feature-file", type=pathlib.Path, default=None)

    p_start = sub.add_parser("session-start", help="Resume / inspect Issue continuity at session start")
    p_start.add_argument("--issue", type=int, required=True)
    p_start.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_start.add_argument("--state", type=pathlib.Path, default=None)
    p_start.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_start.add_argument("--offline", action="store_true")

    p_ckpt = sub.add_parser("checkpoint", help="Record atomic checkpoint at session end")
    p_ckpt.add_argument("--issue", type=int, required=True)
    p_ckpt.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_ckpt.add_argument("--state", type=pathlib.Path, required=True)
    p_ckpt.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_ckpt.add_argument("--export", type=pathlib.Path, default=None)
    p_ckpt.add_argument("--next-action", required=True)
    p_ckpt.add_argument("--blocker", default="")
    p_ckpt.add_argument("--base-sha", default=None)

    p_exp = sub.add_parser("export", help="One-way export from Journal to portable JSON")
    p_exp.add_argument("--issue", type=int, required=True)
    p_exp.add_argument("--state", type=pathlib.Path, required=True)
    p_exp.add_argument("--out", type=pathlib.Path, required=True)

    p_imp = sub.add_parser("import", help="Import portable feature JSON into fresh Journal")
    p_imp.add_argument("--feature-file", type=pathlib.Path, required=True)
    p_imp.add_argument("--state", type=pathlib.Path, required=True)
    p_imp.add_argument("--repo", type=pathlib.Path, default=None)

    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "validate":
            doc = load_feature_doc(args.feature_file)
            print(json.dumps({"status": "VALID", "issue": doc["issue"], "revision": doc["revision"]}, indent=2))
            return 0

        if args.command == "init":
            root = args.repo.resolve()
            raw_units = json.loads(args.units_file.read_text(encoding="utf-8"))
            if isinstance(raw_units, dict):
                raw_units = raw_units.get("units", [])
            issue_meta = {"title": "", "issue_sha256": "", "scope": ()}
            if not args.offline:
                issue_meta = _fetch_issue(root, args.issue)
            snap_git = compute_candidate_snapshot(root)
            doc = create_feature_doc(
                args.issue,
                units=raw_units,
                title=issue_meta["title"],
                issue_sha256=issue_meta["issue_sha256"],
                approved_scope=issue_meta["scope"],
                base_sha=snap_git["base_sha"],
                head_sha=snap_git["source_sha"],
                branch=snap_git["branch"],
                candidate_sha256=snap_git["candidate_sha256"],
            )
            _save_to_journal_and_optional_file(
                doc,
                actor="coordinator",
                expected_revision=None,
                state_db=args.state,
                feature_file=args.feature_file,
            )
            print(json.dumps({"status": "INITIALIZED", "issue": args.issue, "revision": doc["revision"]}, indent=2))
            return 0

        if args.command == "activate":
            doc, rev = _load_from_journal_or_file(
                issue=args.issue, state_db=args.state, feature_file=args.feature_file
            )
            updated = activate_unit(
                doc, args.unit_id, actor=args.actor, expected_revision=args.expected_revision
            )
            _save_to_journal_and_optional_file(
                updated,
                actor=args.actor,
                expected_revision=rev,
                state_db=args.state,
                feature_file=args.feature_file,
            )
            print(json.dumps({"status": "ACTIVE", "unit_id": args.unit_id, "revision": updated["revision"]}, indent=2))
            return 0

        if args.command == "block":
            doc, rev = _load_from_journal_or_file(
                issue=args.issue, state_db=args.state, feature_file=args.feature_file
            )
            updated = block_unit(
                doc, args.unit_id, reason=args.reason, actor=args.actor, expected_revision=args.expected_revision
            )
            _save_to_journal_and_optional_file(
                updated,
                actor=args.actor,
                expected_revision=rev,
                state_db=args.state,
                feature_file=args.feature_file,
            )
            print(json.dumps({"status": "BLOCKED", "unit_id": args.unit_id, "revision": updated["revision"]}, indent=2))
            return 0

        if args.command == "verify-unit":
            doc, rev = _load_from_journal_or_file(
                issue=args.issue, state_db=args.state, feature_file=args.feature_file
            )
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            updated = verify_unit_passing(
                doc, args.unit_id, actor=args.actor, receipt=receipt, expected_revision=args.expected_revision
            )
            _save_to_journal_and_optional_file(
                updated,
                actor=args.actor,
                expected_revision=rev,
                state_db=args.state,
                feature_file=args.feature_file,
            )
            print(json.dumps({"status": "PASSING", "unit_id": args.unit_id, "revision": updated["revision"]}, indent=2))
            return 0

        if args.command == "session-start":
            res = session_start(
                issue=args.issue,
                repo=args.repo,
                state_db=args.state,
                feature_file=args.feature_file,
                offline=args.offline,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 2 if res["status"] in ("BLOCKED", "RECOVERY_REQUIRED") else 0

        if args.command == "checkpoint":
            res = session_checkpoint(
                issue=args.issue,
                repo=args.repo,
                state_db=args.state,
                next_action=args.next_action,
                blocker=args.blocker,
                feature_file=args.feature_file,
                export_path=args.export,
                base_sha=args.base_sha,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        if args.command == "export":
            with Journal(args.state) as journal:
                snap = journal.get_feature_snapshot(args.issue)
                if snap is None:
                    raise ValidationError(f"No feature state in Journal for Issue #{args.issue}")
                out = export_feature_doc(snap["doc"], args.out)
            print(json.dumps({"status": "EXPORTED", "path": str(out)}, indent=2))
            return 0

        if args.command == "import":
            doc = load_feature_doc(args.feature_file)
            if args.repo is not None:
                snap_git = compute_candidate_snapshot(args.repo.resolve(), base_sha=doc["git"].get("base_sha") or None)
                doc, _ = reconcile_revision_drift(
                    doc,
                    current_source_sha=snap_git["source_sha"],
                    current_candidate_sha256=snap_git["candidate_sha256"],
                    current_branch=snap_git["branch"],
                )
            with Journal(args.state) as journal:
                existing = journal.get_feature_snapshot(doc["issue"])
                if existing is not None:
                    raise StateConflict(f"Journal already holds feature state for Issue #{doc['issue']}")
                journal.save_feature_snapshot(
                    issue=doc["issue"],
                    expected_revision=None,
                    revision=doc["revision"],
                    doc_json=json.dumps(doc, sort_keys=True),
                    units=doc["units"],
                    actor="coordinator",
                )
            print(json.dumps({"status": "IMPORTED", "issue": doc["issue"], "revision": doc["revision"]}, indent=2))
            return 0
    except (FeatureStateError, StateConflict, WorktreeError, ContextGateError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:260]}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
