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
    from .observability import (
        ObservabilityError,
        cleanup_owned_artifacts,
        diagnose_failures,
        ingest_checks_summary,
        query_signals,
        record_process_signal,
    )
    from .p1.state import (
        HostVerificationProof,
        Journal,
        StateConflict,
        issue_host_proof,
        verify_host_proof,
    )
    from .p1.worktrees import WorktreeError, inspect_worktree
    from .quality_gates import digest as qg_digest, evaluate as evaluate_quality_gates, inventory, safe_read, secret_line
    from .scope import parse_allowed_paths, violations
except ImportError:
    from agent_context import ContextGateError, load_context
    from observability import (
        ObservabilityError,
        cleanup_owned_artifacts,
        diagnose_failures,
        ingest_checks_summary,
        query_signals,
        record_process_signal,
    )
    from p1.state import (
        HostVerificationProof,
        Journal,
        StateConflict,
        issue_host_proof,
        verify_host_proof,
    )
    from p1.worktrees import WorktreeError, inspect_worktree
    from quality_gates import digest as qg_digest, evaluate as evaluate_quality_gates, inventory, safe_read, secret_line
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
    trusted_sha = evidence.get("trusted_definition_sha256")
    if trusted_sha is not None and trusted_sha != expected_verification_sha256:
        raise VerificationTamperError(f"{label}.trusted_definition_sha256 does not match unit definition")
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


def _normalize_cmd(cmd: str | list[str]) -> str:
    if isinstance(cmd, list):
        return " ".join(part.strip() for part in cmd if str(part).strip())
    return " ".join(str(cmd).split())


def load_trusted_definitions(
    definitions_path: pathlib.Path,
    *,
    repo: pathlib.Path,
) -> dict[str, dict[str, Any]]:
    """Load external Host-owned expected unit verification definitions outside candidate control."""
    repo_root = repo.resolve(strict=True)
    if definitions_path.is_symlink() or definitions_path.parent.is_symlink() or not definitions_path.is_file():
        raise VerificationTamperError("Trusted definitions file must be a real non-symlink file")
    resolved = definitions_path.resolve(strict=True)
    if resolved.is_relative_to(repo_root):
        raise VerificationTamperError("Trusted definitions must reside outside candidate worktree")
    raw = resolved.read_bytes()
    if len(raw) > 512_000 or secret_line(raw):
        raise VerificationTamperError("Trusted definitions file oversized or contains secret signature")
    payload = json.loads(raw.decode("utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict) and isinstance(payload.get("units"), list):
        for item in payload["units"]:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("verification"), dict):
                v = copy.deepcopy(item["verification"])
                v["definition_sha256"] = compute_verification_sha256(v)
                by_id[item["id"]] = v
    elif isinstance(payload, dict):
        for uid, verif in payload.items():
            if isinstance(uid, str) and isinstance(verif, dict):
                v = copy.deepcopy(verif)
                v["definition_sha256"] = compute_verification_sha256(v)
                by_id[uid] = v
    else:
        raise VerificationTamperError("Malformed trusted definitions payload")
    if not by_id:
        raise VerificationTamperError("Trusted definitions contain no unit entries")
    return by_id


def _resolve_trusted_definitions(
    trusted_definitions: dict[str, Any] | pathlib.Path | None,
    *,
    repo: pathlib.Path | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve and validate mandatory frozen trusted verification definitions."""
    if trusted_definitions is None:
        raise VerificationTamperError("Transition to PASSING requires frozen trusted_definitions")
    if isinstance(trusted_definitions, pathlib.Path):
        if repo is None:
            raise VerificationTamperError("repo is required when loading trusted_definitions from Path")
        return load_trusted_definitions(trusted_definitions, repo=repo)
    if not isinstance(trusted_definitions, dict):
        raise VerificationTamperError("trusted_definitions must be a mapping or external JSON Path")

    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(trusted_definitions.get("units"), list):
        for item in trusted_definitions["units"]:
            if isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("verification"), dict):
                v = copy.deepcopy(item["verification"])
                v["definition_sha256"] = compute_verification_sha256(v)
                by_id[item["id"]] = v
    else:
        for uid, verif in trusted_definitions.items():
            if isinstance(uid, str) and isinstance(verif, dict):
                v = copy.deepcopy(verif)
                v["definition_sha256"] = compute_verification_sha256(v)
                by_id[uid] = v
    if not by_id:
        raise VerificationTamperError("Trusted definitions contain no unit entries")
    return by_id


def _assert_matches_trusted_definition(
    unit: dict[str, Any],
    def_map: dict[str, dict[str, Any]],
) -> str:
    uid = unit["id"]
    expected_def = def_map.get(uid)
    if expected_def is None:
        raise VerificationTamperError(f"Unit {uid!r} missing from external trusted definitions")
    expected_def_sha = compute_verification_sha256(expected_def)
    if unit["verification"]["definition_sha256"] != expected_def_sha:
        raise VerificationTamperError(
            f"Unit {uid!r} verification definition differs from external trusted definition"
        )
    return expected_def_sha


def _validate_command_receipt_entry(
    entry: Any,
    *,
    ev_root: pathlib.Path,
    actual_source_sha: str,
    actual_cand_sha: str,
    actual_diff_sha: str,
    unit_ver_sha: str,
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValidationError("Host check receipt entry must be an object")
    obs = entry.get("observations")
    if (
        entry.get("waived")
        or entry.get("owner_waived")
        or entry.get("commit_only")
        or entry.get("skipped")
        or (
            isinstance(obs, dict)
            and any(obs.get(k) for k in ("waived", "owner_waived", "commit_only", "skipped", "self_asserted"))
        )
    ):
        raise UnauthorizedTransition("Waived, skipped, commit-only, or self-asserted receipts cannot mark a unit PASSING")
    if entry.get("self_asserted") or entry.get("verified_by") in ("worker", "maker", "agent"):
        raise UnauthorizedTransition("Worker self-asserted observations cannot mark a unit PASSING")
    if not isinstance(obs, dict) or obs.get("checks_complete") is not True:
        raise UnauthorizedTransition("Host receipt missing checks_complete=true observation")
    if obs.get("actor") in ("worker", "maker") or entry.get("actor") in ("worker", "maker"):
        raise UnauthorizedTransition("Worker-authored receipt cannot mark a unit PASSING")

    if entry.get("exit_code") != 0 or type(entry.get("exit_code")) is not int:
        raise UnauthorizedTransition("Host command receipt exit_code must be integer 0")
    if entry.get("source_sha") != actual_source_sha or entry.get("candidate_sha256") != actual_cand_sha:
        raise RevisionConflict("Stale receipt: source_sha or candidate_sha256 mismatch")

    entry_diff_sha = entry.get("diff_sha256")
    if entry_diff_sha is None:
        entry_diff_sha = obs.get("diff_sha256")
    if not SHA256_RE.fullmatch(str(entry_diff_sha or "")) or entry_diff_sha != actual_diff_sha:
        raise RevisionConflict("Missing or stale diff_sha256 in Host command receipt")

    obs_ver_sha = entry.get("verification_sha256")
    if obs_ver_sha is None:
        obs_ver_sha = obs.get("verification_sha256")
    if not SHA256_RE.fullmatch(str(obs_ver_sha or "")) or obs_ver_sha != unit_ver_sha:
        raise VerificationTamperError("Host command receipt verification_sha256 mismatches unit definition")

    cmd = entry.get("command")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(a, str) and a for a in cmd):
        raise ValidationError("Host command receipt must carry non-empty argv command list")
    cmd_sha = qg_digest(json.dumps(cmd).encode("utf-8"))
    if entry.get("command_sha256") is not None and entry.get("command_sha256") != cmd_sha:
        raise ValidationError("Host command receipt command_sha256 mismatch")

    tool_ver = entry.get("tool_version")
    if (
        not isinstance(tool_ver, str)
        or not tool_ver.strip()
        or len(tool_ver) > 250
        or "\n" in tool_ver
        or secret_line(tool_ver.encode("utf-8"))
    ):
        raise ValidationError("Host command receipt missing valid tool_version")

    receipt_path = validate_relative_path(str(entry.get("receipt_path", "")), label="receipt_path")
    declared_sha = str(entry.get("receipt_sha256", ""))
    if not SHA256_RE.fullmatch(declared_sha):
        raise ValidationError("Host command receipt missing valid receipt_sha256")
    raw_log = safe_read(ev_root, receipt_path)
    actual_log_sha = qg_digest(raw_log)
    if actual_log_sha != declared_sha:
        raise UnauthorizedTransition(f"Recomputed log hash mismatch for {receipt_path}")
    if not raw_log.decode("utf-8").strip() or secret_line(raw_log):
        raise UnauthorizedTransition(f"Empty or secret-bearing log rejected for {receipt_path}")

    return {
        "command": list(cmd),
        "command_norm": _normalize_cmd(cmd),
        "command_sha256": cmd_sha,
        "exit_code": 0,
        "source_sha": actual_source_sha,
        "candidate_sha256": actual_cand_sha,
        "diff_sha256": actual_diff_sha,
        "verification_sha256": unit_ver_sha,
        "tool_version": tool_ver.strip(),
        "receipt_path": receipt_path,
        "receipt_sha256": actual_log_sha,
    }


def verify_host_gate_evidence(
    doc: dict[str, Any],
    unit_id: str,
    *,
    repo: pathlib.Path,
    base_sha: str,
    evidence_dir: pathlib.Path,
    manifest_name: str = "manifest.json",
    trusted_definitions: dict[str, dict[str, Any]] | pathlib.Path | None = None,
) -> HostVerificationProof:
    """Verify unit completion strictly through trusted Host quality_gates evaluation."""
    validated = validate_feature_doc(doc)
    target = _find_unit(validated, unit_id)
    if target["state"] != "ACTIVE":
        raise ValidationError(
            f"Unit {unit_id!r} must be ACTIVE before PASSING (current state={target['state']})"
        )
    repo_root = repo.resolve(strict=True)
    if evidence_dir.is_symlink() or not evidence_dir.is_dir():
        raise ValidationError("External evidence_dir must be a real non-symlink directory")
    ev_root = evidence_dir.resolve(strict=True)
    if ev_root.is_relative_to(repo_root):
        raise ValidationError("Host evidence_dir must remain outside candidate worktree")

    def_map = _resolve_trusted_definitions(trusted_definitions, repo=repo_root)
    expected_def_sha = _assert_matches_trusted_definition(target, def_map)

    try:
        eval_result = evaluate_quality_gates(repo_root, base_sha, manifest_name, ev_root)
    except Exception as exc:
        raise UnauthorizedTransition(f"Trusted Host quality_gates evaluation failed: {exc}") from exc

    if eval_result.get("auto_check") != "AUTO_CHECK_PASS":
        failed_rules = [
            f"{r['rule_id']}:{r['status']}"
            for r in eval_result.get("results", [])
            if r.get("status") in ("FAIL", "BLOCKED", "NOT_VERIFIED")
        ]
        raise UnauthorizedTransition(
            f"Trusted Host quality_gates did not pass AUTO_CHECK_PASS ({', '.join(failed_rules) or eval_result.get('auto_check')})"
        )

    expected_source_sha = validated["git"].get("head_sha") or validated["git"].get("base_sha")
    expected_cand_sha = validated["git"].get("candidate_sha256")
    actual_source_sha = str(eval_result.get("source_sha", ""))
    actual_cand_sha = str(eval_result.get("candidate_sha256", ""))
    actual_diff_sha = str(eval_result.get("diff_sha256", ""))
    if expected_source_sha and actual_source_sha != expected_source_sha:
        raise RevisionConflict("Stale candidate: Host evaluated source_sha mismatches feature state")
    if expected_cand_sha and actual_cand_sha != expected_cand_sha:
        raise RevisionConflict("Stale candidate: Host evaluated candidate_sha256 mismatches feature state")
    if not SHA256_RE.fullmatch(actual_diff_sha):
        raise ValidationError("Host quality_gates evaluation missing diff_sha256")

    manifest_raw = safe_read(ev_root, manifest_name)
    manifest_doc = json.loads(manifest_raw.decode("utf-8"))
    checks = manifest_doc.get("checks", {})
    unit_ver_sha = target["verification"]["definition_sha256"]
    required_cmds = [_normalize_cmd(c) for c in target["verification"]["commands"]]

    candidate_receipts: list[tuple[str, dict[str, Any]]] = []
    raw_cmd_receipts = manifest_doc.get("command_receipts")
    if raw_cmd_receipts is not None:
        if not isinstance(raw_cmd_receipts, list):
            raise ValidationError("manifest.command_receipts must be a list")
        for item in raw_cmd_receipts:
            candidate_receipts.append((str(item.get("gate_rule_id", "UNIT-CHECK") if isinstance(item, dict) else "UNIT-CHECK"), item))

    for res in eval_result.get("results", []):
        if res.get("status") != "PASS":
            continue
        rid = str(res.get("rule_id", ""))
        if rid in ("SECRET-SCAN", "DIFF-CHECK", "STANDARDS-CHECK"):
            continue
        entry = checks.get(rid)
        if isinstance(entry, dict):
            candidate_receipts.append((rid, entry))

    verified_by_cmd: dict[str, tuple[str, dict[str, Any]]] = {}
    last_rejection: Exception | None = None
    for gate_id, raw_entry in candidate_receipts:
        try:
            verified = _validate_command_receipt_entry(
                raw_entry,
                ev_root=ev_root,
                actual_source_sha=actual_source_sha,
                actual_cand_sha=actual_cand_sha,
                actual_diff_sha=actual_diff_sha,
                unit_ver_sha=unit_ver_sha,
            )
            verified_by_cmd.setdefault(verified["command_norm"], (gate_id, verified))
        except (UnauthorizedTransition, VerificationTamperError, RevisionConflict) as exc:
            last_rejection = exc
            if isinstance(raw_entry, dict) and _normalize_cmd(raw_entry.get("command", [])) in required_cmds:
                raise
        except ValidationError as exc:
            last_rejection = exc

    matched_receipts: list[dict[str, Any]] = []
    missing_cmds: list[str] = []
    primary_gate_id = ""
    for req_cmd in required_cmds:
        hit = verified_by_cmd.get(req_cmd)
        if hit is None:
            missing_cmds.append(req_cmd)
        else:
            gate_id, rec = hit
            if not primary_gate_id:
                primary_gate_id = gate_id
            matched_receipts.append({k: v for k, v in rec.items() if k != "command_norm"})

    if missing_cmds:
        if last_rejection is not None and not matched_receipts:
            raise last_rejection
        raise ValidationError(
            f"Missing verified Host receipts for required unit command(s): {missing_cmds}"
        )

    primary = matched_receipts[0]
    command_receipts_sha = _sha256_bytes(_canonical_json(matched_receipts).encode("utf-8"))

    return issue_host_proof(
        issue=validated["issue"],
        unit_id=unit_id,
        verification_sha256=unit_ver_sha,
        source_sha=actual_source_sha,
        candidate_sha256=actual_cand_sha,
        manifest_sha256=str(eval_result["manifest_sha256"]),
        runner_sha256=str(eval_result["runner_sha256"]),
        receipt_path=primary["receipt_path"],
        receipt_sha256=primary["receipt_sha256"],
        gate_rule_id=primary_gate_id,
        auto_check="AUTO_CHECK_PASS",
        diff_sha256=actual_diff_sha,
        command_receipts_sha256=command_receipts_sha,
        tool_version=primary["tool_version"],
        trusted_definition_sha256=expected_def_sha,
    )


def verify_unit_passing(
    doc: dict[str, Any],
    unit_id: str,
    *,
    proof: HostVerificationProof,
    expected_revision: int | None = None,
    command_receipts: list[dict[str, Any]] | None = None,
    trusted_definitions: dict[str, Any] | pathlib.Path | None = None,
    repo: pathlib.Path | None = None,
) -> dict[str, Any]:
    if not isinstance(proof, HostVerificationProof):
        raise UnauthorizedTransition(
            "Only a verified HostVerificationProof from trusted Host evaluation may mark a unit PASSING"
        )
    if not SHA256_RE.fullmatch(str(proof.diff_sha256 or "")) or not SHA256_RE.fullmatch(
        str(proof.command_receipts_sha256 or "")
    ):
        raise ValidationError("HostVerificationProof must bind diff_sha256 and complete command_receipts_sha256")

    def_map = _resolve_trusted_definitions(trusted_definitions, repo=repo)
    updated = validate_feature_doc(copy.deepcopy(doc))
    _check_cas(updated, expected_revision)

    target = _find_unit(updated, unit_id)
    if target["state"] != "ACTIVE":
        raise ValidationError(
            f"Unit {unit_id!r} must be ACTIVE before PASSING (current state={target['state']})"
        )
    expected_def_sha = _assert_matches_trusted_definition(target, def_map)
    if proof.verification_sha256 != expected_def_sha or proof.trusted_definition_sha256 != expected_def_sha:
        raise VerificationTamperError(
            f"HostVerificationProof for unit {unit_id!r} does not match frozen trusted definition"
        )

    expected_source_sha = updated["git"].get("head_sha") or updated["git"].get("base_sha")
    expected_cand_sha = updated["git"].get("candidate_sha256")
    if expected_source_sha and proof.source_sha != expected_source_sha:
        raise RevisionConflict("Stale proof: source_sha does not match current candidate")
    if expected_cand_sha and proof.candidate_sha256 != expected_cand_sha:
        raise RevisionConflict("Stale proof: candidate_sha256 does not match current candidate")

    evidence_payload: dict[str, Any] = {
        "verified_by": "host_verifier",
        "status": "AUTO_CHECK_PASS",
        "exit_code": 0,
        "source_sha": proof.source_sha,
        "candidate_sha256": proof.candidate_sha256,
        "diff_sha256": proof.diff_sha256,
        "verification_sha256": proof.verification_sha256,
        "trusted_definition_sha256": expected_def_sha,
        "command_receipts_sha256": proof.command_receipts_sha256,
        "tool_version": proof.tool_version,
        "receipt_path": proof.receipt_path,
        "receipt_sha256": proof.receipt_sha256,
        "gate_rule_id": proof.gate_rule_id,
        "manifest_sha256": proof.manifest_sha256,
        "runner_sha256": proof.runner_sha256,
        "recorded_at": _utc_now(),
    }
    if command_receipts is not None:
        evidence_payload["command_receipts"] = copy.deepcopy(command_receipts)

    normalized_evidence = _validate_evidence(
        evidence_payload,
        expected_verification_sha256=target["verification"]["definition_sha256"],
        label="host_proof",
    )

    target["state"] = "PASSING"
    target["blocker"] = ""
    target["evidence"] = normalized_evidence
    verify_host_proof(proof, issue=updated["issue"], unit=target)
    target["evidence_history"].append(copy.deepcopy(normalized_evidence))

    updated["revision"] += 1
    updated["handoff"]["active_unit"] = None
    updated["handoff"]["blocker"] = ""
    refs_to_add = [
        {"path": normalized_evidence["receipt_path"], "sha256": normalized_evidence["receipt_sha256"]}
    ]
    if command_receipts:
        for rec in command_receipts:
            refs_to_add.append({"path": rec["receipt_path"], "sha256": rec["receipt_sha256"]})
    for ref in refs_to_add:
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


def sanitize_imported_doc(
    doc: dict[str, Any],
    *,
    repo: pathlib.Path | None = None,
    base_sha: str | None = None,
    evidence_dir: pathlib.Path | None = None,
    manifest_name: str = "manifest.json",
    trusted_definitions: dict[str, Any] | pathlib.Path | None = None,
) -> tuple[dict[str, Any], dict[str, HostVerificationProof]]:
    """Never trust imported PASSING claims without live Host verification."""
    cleaned = validate_feature_doc(copy.deepcopy(doc))
    proofs: dict[str, HostVerificationProof] = {}
    for unit in cleaned["units"]:
        if unit["state"] != "PASSING":
            continue
        verified_proof: HostVerificationProof | None = None
        if repo is not None and evidence_dir is not None:
            probe_doc = copy.deepcopy(cleaned)
            for pu in probe_doc["units"]:
                if pu["id"] == unit["id"]:
                    pu["state"] = "ACTIVE"
                    pu["evidence"] = None
                elif pu["state"] == "ACTIVE":
                    pu["state"] = "PENDING"
            probe_doc["handoff"]["active_unit"] = unit["id"]
            eval_base = base_sha or cleaned["git"].get("base_sha") or "HEAD"
            try:
                verified_proof = verify_host_gate_evidence(
                    probe_doc,
                    unit["id"],
                    repo=repo,
                    base_sha=eval_base,
                    evidence_dir=evidence_dir,
                    manifest_name=manifest_name,
                    trusted_definitions=trusted_definitions,
                )
            except (FeatureStateError, StateConflict, OSError, ValueError):
                verified_proof = None
        if verified_proof is not None:
            proofs[unit["id"]] = verified_proof
            continue
        prior = unit["evidence"]
        unit["state"] = "STALE"
        unit["evidence"] = None
        unit["evidence_history"].append({
            "status": "UNVERIFIED_ON_IMPORT",
            "reason": "Portable import requires trusted Host verification",
            "prior_candidate_sha256": prior["candidate_sha256"] if isinstance(prior, dict) else "",
            "prior_source_sha": prior["source_sha"] if isinstance(prior, dict) else "",
            "prior_receipt_sha256": prior["receipt_sha256"] if isinstance(prior, dict) else "",
            "imported_at": _utc_now(),
        })
    return validate_feature_doc(cleaned), proofs


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
        "diff_sha256": source_info["diff_sha256"],
        "candidate_sha256": source_info["candidate_sha256"],
        "changed_paths": source_info["changed_paths"],
    }


def _next_action_for(
    doc: dict[str, Any] | None,
    *,
    job: dict[str, Any] | None,
    checkpoint: dict[str, Any] | None,
    drift: dict[str, Any],
) -> tuple[str, str, str]:
    saved_next = (
        checkpoint["next_action"]
        if checkpoint is not None and checkpoint.get("next_action")
        else (doc["handoff"]["next_action"] if doc is not None else "")
    )
    saved_blocker = (
        checkpoint["blocker"]
        if checkpoint is not None and checkpoint.get("blocker")
        else (doc["handoff"]["blocker"] if doc is not None else "")
    )

    if job and job["state"] == "RECOVERY_REQUIRED":
        return (
            "RECOVERY_REQUIRED",
            "Inspect interrupted run worktree/branch and uncommitted files; do not reset or auto-retry.",
            saved_blocker,
        )
    if drift.get("branch_mismatch"):
        return (
            "BLOCKED",
            "Current Git branch mismatches recorded Issue branch; verify worktree before editing.",
            saved_blocker or "Branch mismatch detected during session resume",
        )
    if drift.get("issue_drift"):
        return (
            "BLOCKED",
            "Live GitHub Issue body/scope changed since last checkpoint; review updated AC and re-scope.",
            saved_blocker or "Live GitHub Issue scope/body drift",
        )
    if saved_blocker:
        return (
            "BLOCKED",
            saved_next or f"Resolve recorded blocker: {saved_blocker}",
            saved_blocker,
        )
    if doc is None:
        if checkpoint is not None and saved_next:
            return ("READY_TO_RESUME", saved_next, "")
        return (
            "NEEDS_INIT",
            "Initialize feature units for this Issue before starting implementation.",
            "",
        )

    if drift.get("stale_units"):
        return (
            "READY_TO_RESUME",
            f"Re-activate and re-verify stale unit {drift['stale_units'][0]} after revision drift.",
            "",
        )
    active = [u for u in doc["units"] if u["state"] == "ACTIVE"]
    if active:
        u = active[0]
        return (
            "READY_TO_RESUME",
            saved_next or f"Continue active unit {u['id']} ({u['behavior']}); run Host checks before marking PASSING.",
            "",
        )
    stale = [u for u in doc["units"] if u["state"] == "STALE"]
    if stale:
        u = stale[0]
        return (
            "READY_TO_RESUME",
            saved_next or f"Re-activate and re-verify stale unit {u['id']} after revision drift.",
            "",
        )
    blocked = [u for u in doc["units"] if u["state"] == "BLOCKED"]
    by_id = {u["id"]: u for u in doc["units"]}
    ready = [
        u for u in doc["units"]
        if u["state"] == "PENDING" and all(by_id[d]["state"] == "PASSING" for d in u["dependencies"])
    ]
    if ready:
        u = ready[0]
        return ("READY_TO_RESUME", saved_next or f"Activate next ready unit {u['id']}: {u['behavior']}", "")
    if blocked:
        u = blocked[0]
        return ("BLOCKED", saved_next or f"Resolve blocker on unit {u['id']}: {u['blocker']}", u["blocker"])
    if all(u["state"] == "PASSING" for u in doc["units"]):
        return (
            "ALL_UNITS_PASSING_LOCAL",
            saved_next or "Run final quality_gates.py, fresh independent Auditor, and open/update Draft PR for human review.",
            "",
        )
    return ("BLOCKED", saved_next or "No ready unit found; inspect unit dependencies and blockers.", saved_blocker)


def session_start(
    *,
    issue: int,
    repo: pathlib.Path,
    state_db: pathlib.Path | None = None,
    feature_file: pathlib.Path | None = None,
    issue_data: dict[str, Any] | None = None,
    offline: bool = False,
    expected_revision: int | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Verify G0 context, live Issue/worktree/candidate/branch/revision, and restore checkpoint."""
    root = repo.resolve()
    try:
        g0 = load_context(root)
    except ContextGateError as exc:
        return {"status": "BLOCKED", "issue": issue, "reason": f"G0 gate blocked: {exc}"}

    job: dict[str, Any] | None = None
    checkpoint: dict[str, Any] | None = None
    stored_doc: dict[str, Any] | None = None
    loaded_revision: int | None = None
    from_journal = False
    control_run: dict[str, Any] | None = None
    control_rounds: list[dict[str, Any]] = []
    if state_db is not None and state_db.exists():
        with Journal(state_db) as journal:
            job = journal.active_job_for_issue(issue) or journal.latest_job_for_issue(issue)
            if job and job["state"] == "PREPARING":
                journal.detect_interruption(job["run_id"])
                job = journal.get(job["run_id"])
            snap = journal.get_feature_snapshot(issue)
            if snap is not None:
                stored_doc = validate_feature_doc(snap["doc"])
                loaded_revision = snap["revision"]
                from_journal = True
            checkpoint = journal.latest_checkpoint(issue)
            control_run = journal.latest_control_run_for_issue(issue)
            if control_run is not None:
                control_rounds = journal.list_control_rounds(control_run["run_id"])

    default_export = root / "docs" / "harness" / "features" / f"issue-{issue}.json"
    source_file = feature_file if feature_file is not None else (default_export if default_export.is_file() else None)
    if stored_doc is None and source_file is not None:
        raw_doc = load_feature_doc(source_file)
        stored_doc, _ = sanitize_imported_doc(raw_doc)
        loaded_revision = stored_doc["revision"]

    if expected_revision is not None and loaded_revision != expected_revision:
        raise RevisionConflict(
            f"CAS revision mismatch on resume: expected {expected_revision}, actual {loaded_revision}"
        )

    expected_base = (
        (job["source_sha"] if job else None)
        or (stored_doc["git"].get("base_sha") if stored_doc else None)
        or None
    )
    snap_git = compute_candidate_snapshot(root, base_sha=expected_base)

    recorded_branches = [
        b for b in (
            expected_branch,
            job["branch"] if job else None,
            checkpoint["branch"] if checkpoint else None,
            stored_doc["git"].get("branch") if stored_doc else None,
        ) if b
    ]
    branch_mismatch = any(b != snap_git["branch"] for b in recorded_branches)

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
                "blocker": checkpoint["blocker"] if checkpoint else "",
                "next_action": "Preserve worktree changes and inspect out-of-scope paths before continuing.",
            }

    drift: dict[str, Any] = {
        "drift_reasons": [],
        "stale_units": [],
        "issue_drift": False,
        "branch_mismatch": branch_mismatch,
        "checkpoint_revision_changed": False,
    }
    if branch_mismatch:
        drift["drift_reasons"].append("branch_mismatch")
    if checkpoint is not None:
        if checkpoint["revision_sha"] and checkpoint["revision_sha"] != snap_git["source_sha"]:
            drift["checkpoint_revision_changed"] = True
            if "source_sha_changed" not in drift["drift_reasons"]:
                drift["drift_reasons"].append("source_sha_changed")
        if checkpoint["candidate_sha256"] and checkpoint["candidate_sha256"] != snap_git["candidate_sha256"]:
            drift["checkpoint_revision_changed"] = True
            if "candidate_sha256_changed" not in drift["drift_reasons"]:
                drift["drift_reasons"].append("candidate_sha256_changed")

    if stored_doc is not None:
        stored_doc, doc_drift = reconcile_revision_drift(
            stored_doc,
            current_source_sha=snap_git["source_sha"],
            current_candidate_sha256=snap_git["candidate_sha256"],
            current_branch=snap_git["branch"],
            current_issue_sha256=live_issue.get("issue_sha256") if live_issue else None,
        )
        drift["drift_reasons"] = list(dict.fromkeys(drift["drift_reasons"] + doc_drift["drift_reasons"]))
        drift["stale_units"] = doc_drift["stale_units"]
        drift["issue_drift"] = doc_drift["issue_drift"]
        drift["branch_mismatch"] = drift["branch_mismatch"] or doc_drift["branch_mismatch"]
        if (
            from_journal
            and state_db is not None
            and state_db.exists()
            and not drift["branch_mismatch"]
            and not drift["issue_drift"]
            and (doc_drift["drift_reasons"] or doc_drift["stale_units"])
        ):
            with Journal(state_db) as journal:
                try:
                    journal.save_feature_snapshot(
                        issue=issue,
                        expected_revision=loaded_revision,
                        revision=stored_doc["revision"],
                        doc_json=json.dumps(stored_doc, sort_keys=True),
                        units=stored_doc["units"],
                        actor="host_verifier",
                        expected_branch=snap_git["branch"],
                    )
                except StateConflict as exc:
                    raise RevisionConflict(str(exc)) from exc

    status, next_action, blocker = _next_action_for(
        stored_doc, job=job, checkpoint=checkpoint, drift=drift
    )
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
    saved_checkpoint = (
        {
            "checkpoint_id": checkpoint["checkpoint_id"],
            "revision_sha": checkpoint["revision_sha"],
            "candidate_sha256": checkpoint["candidate_sha256"],
            "branch": checkpoint["branch"],
            "active_unit": checkpoint["active_unit"],
            "blocker": checkpoint["blocker"],
            "next_action": checkpoint["next_action"],
            "created_at": checkpoint["created_at"],
        }
        if checkpoint is not None
        else None
    )
    obs_summary: dict[str, Any] = {
        "captured_signal_count": 0,
        "recent_signals": [],
        "latest_failure": None,
    }
    if state_db is not None and state_db.exists():
        recent_sigs = query_signals(state_db, issue=issue, limit=10)
        diag = diagnose_failures(state_db, issue=issue, limit=10)
        obs_summary = {
            "captured_signal_count": sum(1 for s in recent_sigs if s.get("captured")),
            "recent_signals": [
                {
                    "signal_id": s["signal_id"],
                    "category": s["category"],
                    "owning_domain": s["owning_domain"],
                    "check_id": s["check_id"],
                    "status": s["status"],
                    "ended_at": s["ended_at"],
                }
                for s in recent_sigs[:5]
            ],
            "latest_failure": diag.get("latest_failure"),
        }

    latest_ctrl_round = control_rounds[-1] if control_rounds else None
    control_run_summary = None
    if control_run is not None:
        ctrl_state = control_run["state"]
        ctrl_receipt_refs = dict(latest_ctrl_round.get("evidence_refs") or {}) if latest_ctrl_round else {}
        ctrl_decision = (
            latest_ctrl_round["verdict"]
            if latest_ctrl_round is not None
            else ("CANCELLED" if ctrl_state == "CANCELLED" else ctrl_state)
        )
        ctrl_blocker = control_run.get("blocker", "")
        ctrl_next = control_run.get("next_action", "") or (
            latest_ctrl_round["next_action"] if latest_ctrl_round else ""
        )
        ctrl_rec_reason = control_run.get("recovery_reason", "")
        if ctrl_state in ("DISPATCHED", "MAKER_RUNNING", "VERIFYING", "CHECKING"):
            ctrl_rec_reason = ctrl_rec_reason or f"active_or_interrupted_in_{ctrl_state.lower()}"
            if status not in ("BLOCKED", "RECOVERY_REQUIRED"):
                status = "RECOVERY_REQUIRED"
                next_action = f"Run Host reconcile for control run {control_run['run_id']} ({ctrl_state}) before resuming"
        elif ctrl_state in ("BLOCKED", "ESCALATED") and status not in ("BLOCKED", "RECOVERY_REQUIRED"):
            blocker = blocker or ctrl_blocker or control_run.get("last_failure_sig", "")
            next_action = ctrl_next or next_action
        ctrl_policy = control_run.get("policy") if isinstance(control_run.get("policy"), dict) else {}
        ctrl_consumed = control_run.get("budget_consumed") if isinstance(control_run.get("budget_consumed"), dict) else {}
        ctrl_rem_wall = max(
            0.0,
            round(float(ctrl_policy.get("max_wall_seconds", 0.0)) - float(ctrl_consumed.get("wall_seconds", 0.0)), 3),
        )
        control_run_summary = {
            "run_id": control_run["run_id"],
            "state": ctrl_state,
            "phase": ctrl_state,
            "resume_phase": control_run.get("resume_phase", ""),
            "round_num": control_run["round_num"],
            "in_flight_round": control_run.get("in_flight_round", 0),
            "policy_sha256": control_run["policy_sha256"],
            "owner_approval_status": ctrl_policy.get("owner_approval_status"),
            "cancel_requested": control_run["cancel_requested"],
            "evidence_dir": control_run.get("evidence_dir", ""),
            "receipt_refs": ctrl_receipt_refs,
            "last_completed_op": control_run.get("last_completed_op", ""),
            "lease": {
                "active_role": control_run.get("active_role"),
                "dispatch_seq": control_run.get("dispatch_seq", 0),
                "token_present": bool(control_run.get("dispatch_token")),
                "owner_pid": control_run.get("lease_owner_pid"),
                "owner_host": control_run.get("lease_owner_host", ""),
                "acquired_at": control_run.get("lease_acquired_at", ""),
                "heartbeat_at": control_run.get("lease_heartbeat_at", ""),
            },
            "recovery_reason": ctrl_rec_reason,
            "decision": ctrl_decision,
            "blocker": ctrl_blocker,
            "next_action": ctrl_next,
            "budget_consumed": ctrl_consumed,
            "remaining_wall_seconds": ctrl_rem_wall,
        }

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
        "blocker": blocker,
        "evidence_refs": stored_doc["handoff"]["evidence_refs"] if stored_doc else [],
        "decision_refs": stored_doc["handoff"]["decision_refs"] if stored_doc else list(DEFAULT_DECISION_REFS),
        "last_checkpoint_id": checkpoint["checkpoint_id"] if checkpoint else None,
        "saved_checkpoint": saved_checkpoint,
        "control_run": control_run_summary,
        "observability": obs_summary,
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
    expected_revision: int | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Persist an atomic SQLite checkpoint + CAS snapshot and optional one-way portable export."""
    if not next_action.strip():
        raise ValidationError("Checkpoint requires a non-empty next_action")
    root = repo.resolve()
    snap_git = compute_candidate_snapshot(root, base_sha=base_sha)
    if expected_branch is not None and snap_git["branch"] != expected_branch:
        raise RevisionConflict(
            f"Branch mismatch on checkpoint: expected {expected_branch!r}, got {snap_git['branch']!r}"
        )
    wt_rel = _relative_worktree_label(root, pathlib.Path(snap_git["worktree"]))

    with Journal(state_db) as journal:
        job = journal.active_job_for_issue(issue) or journal.latest_job_for_issue(issue)
        if job is not None and job["branch"] and job["branch"] != snap_git["branch"]:
            raise RevisionConflict(
                f"Branch mismatch against job {job['branch']!r}: current {snap_git['branch']!r}"
            )
        snap = journal.get_feature_snapshot(issue)
        prior_ckpt = journal.latest_checkpoint(issue)
        if prior_ckpt is not None and prior_ckpt["branch"] and prior_ckpt["branch"] != snap_git["branch"]:
            raise RevisionConflict(
                f"Branch mismatch against prior checkpoint {prior_ckpt['branch']!r}: current {snap_git['branch']!r}"
            )

        doc: dict[str, Any] | None = None
        cas_expected: int | None = None
        if snap is not None:
            doc = validate_feature_doc(snap["doc"])
            cas_expected = snap["revision"]
            if expected_revision is not None and snap["revision"] != expected_revision:
                raise RevisionConflict(
                    f"CAS revision mismatch on checkpoint: expected {expected_revision}, actual {snap['revision']}"
                )
        elif expected_revision is not None:
            raise RevisionConflict(
                f"CAS revision mismatch on checkpoint: expected {expected_revision}, no persisted feature state"
            )
        elif feature_file is not None and feature_file.is_file():
            doc, _ = sanitize_imported_doc(load_feature_doc(feature_file))

        active_unit = None
        issue_sha256 = ""
        evidence_refs: list[dict[str, str]] = []
        completed_units: list[str] = []
        snapshot_args: dict[str, Any] | None = None
        if doc is not None:
            if doc["git"].get("branch") and doc["git"]["branch"] != snap_git["branch"]:
                raise RevisionConflict(
                    f"Branch mismatch against feature state {doc['git']['branch']!r}: current {snap_git['branch']!r}"
                )
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
            snapshot_args = {
                "issue": issue,
                "expected_revision": expected_revision if expected_revision is not None else cas_expected,
                "revision": doc["revision"],
                "doc_json": json.dumps(doc, sort_keys=True),
                "units": doc["units"],
                "actor": "coordinator",
                "expected_branch": snap_git["branch"],
            }

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
        try:
            checkpoint_id = journal.save_checkpoint_and_snapshot(
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
                snapshot_args=snapshot_args,
                expected_branch=snap_git["branch"],
            )
        except StateConflict as exc:
            raise RevisionConflict(str(exc)) from exc

    exported_to = None
    if export_path is not None and doc is not None:
        exported_to = str(export_feature_doc(doc, export_path))

    return {
        "status": "CHECKPOINT_SAVED",
        "checkpoint_id": checkpoint_id,
        "issue": issue,
        "revision": doc["revision"] if doc is not None else None,
        "branch": snap_git["branch"],
        "source_sha": snap_git["source_sha"],
        "candidate_sha256": snap_git["candidate_sha256"],
        "active_unit": active_unit,
        "blocker": blocker.strip(),
        "exported_to": exported_to,
        "next_action": next_action.strip(),
    }


def session_close(
    *,
    issue: int,
    repo: pathlib.Path,
    state_db: pathlib.Path,
    next_action: str,
    blocker: str = "",
    feature_file: pathlib.Path | None = None,
    export_path: pathlib.Path | None = None,
    evidence_dir: pathlib.Path | None = None,
    cleanup_paths: list[pathlib.Path] | None = None,
    allowed_temp_roots: list[pathlib.Path] | None = None,
    owner_run_id: str | None = None,
    decision_refs: tuple[str, ...] | list[str] = DEFAULT_DECISION_REFS,
    base_sha: str | None = None,
    expected_revision: int | None = None,
    expected_branch: str | None = None,
) -> dict[str, Any]:
    """Cleanly close a session: ingest P05 receipts, persist atomic P04 checkpoint,
    preserve PARTIAL/BLOCKED and dirty worktrees, and clean only owned temp artifacts.
    """
    root = repo.resolve()
    ingested_signals: list[dict[str, Any]] = []
    retained_evidence: set[pathlib.Path] = {state_db.resolve()}
    if evidence_dir is not None:
        if evidence_dir.is_symlink():
            raise ValidationError("evidence_dir must not be a symlink")
        ev_resolved = evidence_dir.resolve(strict=True)
        if ev_resolved.is_relative_to(root):
            raise ValidationError("Host evidence_dir must remain outside candidate worktree")
        for child in ev_resolved.iterdir():
            if child.is_file() and not child.name.endswith(".tmp"):
                retained_evidence.add(child.resolve())
        if (ev_resolved / "checks_summary.json").is_file():
            ingested_signals = ingest_checks_summary(
                ev_resolved,
                journal_path=state_db,
                issue=issue,
                run_id=owner_run_id,
            )

    ckpt = session_checkpoint(
        issue=issue,
        repo=root,
        state_db=state_db,
        next_action=next_action,
        blocker=blocker,
        feature_file=feature_file,
        export_path=export_path,
        decision_refs=decision_refs,
        base_sha=base_sha,
        expected_revision=expected_revision,
        expected_branch=expected_branch,
    )

    cleanup_result: dict[str, Any] | None = None
    if cleanup_paths:
        cleanup_result = cleanup_owned_artifacts(
            cleanup_paths,
            allowed_temp_roots=list(allowed_temp_roots or []),
            repo=root,
            owner_issue=issue,
            owner_run_id=owner_run_id,
            retained_evidence_paths=retained_evidence,
        )

    snap_git = compute_candidate_snapshot(root, base_sha=base_sha)
    with Journal(state_db) as journal:
        snap = journal.get_feature_snapshot(issue)
        job = journal.active_job_for_issue(issue) or journal.latest_job_for_issue(issue)

    units_list = snap["doc"]["units"] if snap is not None else []
    has_blocked_unit = any(u["state"] == "BLOCKED" for u in units_list)
    all_passing = bool(units_list) and all(u["state"] == "PASSING" for u in units_list)
    if blocker.strip() or has_blocked_unit or (job and job["state"] == "RECOVERY_REQUIRED"):
        session_outcome = "BLOCKED"
    elif all_passing and not snap_git["dirty"]:
        session_outcome = "DONE_FOR_REVIEW"
    else:
        session_outcome = "PARTIAL"

    record_process_signal(
        journal_path=state_db,
        signal_type="process",
        category="session",
        owning_domain="harness",
        status=session_outcome,
        captured=True,
        issue=issue,
        unit_id=ckpt.get("active_unit"),
        run_id=owner_run_id or (job["run_id"] if job else None),
        check_id="session-close",
        source_sha=ckpt["source_sha"],
        candidate_sha256=ckpt["candidate_sha256"],
        finding=blocker.strip() or ckpt["next_action"],
        evidence_ref={"checkpoint_id": ckpt["checkpoint_id"], "exported_to": ckpt.get("exported_to") or ""},
    )

    return {
        "status": "SESSION_CLOSED",
        "session_outcome": session_outcome,
        "issue": issue,
        "checkpoint": ckpt,
        "has_uncommitted_work": snap_git["dirty"],
        "dirty_paths": snap_git["dirty_paths"],
        "ingested_signals": len(ingested_signals),
        "cleanup": cleanup_result,
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
        cleaned, _ = sanitize_imported_doc(load_feature_doc(feature_file))
        return cleaned, None
    raise ValidationError(f"No feature state found for Issue #{issue}")


def _save_to_journal_and_optional_file(
    doc: dict[str, Any],
    *,
    actor: str,
    expected_revision: int | None,
    state_db: pathlib.Path | None,
    feature_file: pathlib.Path | None,
    host_proofs: dict[str, HostVerificationProof] | None = None,
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
                host_proofs=host_proofs,
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
    p_init.add_argument("--trusted-definitions", type=pathlib.Path, default=None)
    p_init.add_argument("--base-sha", default=None)
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

    p_ver = sub.add_parser("verify-unit", help="Transition unit to PASSING strictly via Host quality_gates evaluation")
    p_ver.add_argument("--issue", type=int, required=True)
    p_ver.add_argument("--unit-id", required=True)
    p_ver.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_ver.add_argument("--base-sha", default=None)
    p_ver.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    p_ver.add_argument("--manifest", default="manifest.json")
    p_ver.add_argument("--trusted-definitions", type=pathlib.Path, required=True)
    p_ver.add_argument("--expected-revision", type=int, default=None)
    p_ver.add_argument("--state", type=pathlib.Path, default=None)
    p_ver.add_argument("--feature-file", type=pathlib.Path, default=None)

    p_start = sub.add_parser("session-start", help="Resume / inspect Issue continuity at session start")
    p_start.add_argument("--issue", type=int, required=True)
    p_start.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_start.add_argument("--state", type=pathlib.Path, default=None)
    p_start.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_start.add_argument("--expected-revision", type=int, default=None)
    p_start.add_argument("--expected-branch", default=None)
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
    p_ckpt.add_argument("--expected-revision", type=int, default=None)
    p_ckpt.add_argument("--expected-branch", default=None)

    p_close = sub.add_parser("session-close", help="Cleanly close session with checkpoint, receipts, and safe temp cleanup")
    p_close.add_argument("--issue", type=int, required=True)
    p_close.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_close.add_argument("--state", type=pathlib.Path, required=True)
    p_close.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_close.add_argument("--export", type=pathlib.Path, default=None)
    p_close.add_argument("--evidence-dir", type=pathlib.Path, default=None)
    p_close.add_argument("--cleanup-path", type=pathlib.Path, action="append", default=[])
    p_close.add_argument("--allowed-temp-root", type=pathlib.Path, action="append", default=[])
    p_close.add_argument("--run-id", default=None)
    p_close.add_argument("--next-action", required=True)
    p_close.add_argument("--blocker", default="")
    p_close.add_argument("--base-sha", default=None)
    p_close.add_argument("--expected-revision", type=int, default=None)
    p_close.add_argument("--expected-branch", default=None)

    p_exp = sub.add_parser("export", help="One-way export from Journal to portable JSON")
    p_exp.add_argument("--issue", type=int, required=True)
    p_exp.add_argument("--state", type=pathlib.Path, required=True)
    p_exp.add_argument("--out", type=pathlib.Path, required=True)

    p_imp = sub.add_parser("import", help="Import portable feature JSON into fresh Journal")
    p_imp.add_argument("--feature-file", type=pathlib.Path, required=True)
    p_imp.add_argument("--state", type=pathlib.Path, required=True)
    p_imp.add_argument("--repo", type=pathlib.Path, default=None)
    p_imp.add_argument("--base-sha", default=None)
    p_imp.add_argument("--evidence-dir", type=pathlib.Path, default=None)
    p_imp.add_argument("--manifest", default="manifest.json")
    p_imp.add_argument("--trusted-definitions", type=pathlib.Path, default=None)

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
            if args.trusted_definitions is not None:
                trusted_map = load_trusted_definitions(args.trusted_definitions, repo=root)
                for u in raw_units:
                    if isinstance(u, dict) and u.get("id") in trusted_map:
                        t_hash = trusted_map[u["id"]]["definition_sha256"]
                        if compute_verification_sha256(u.get("verification")) != t_hash:
                            raise VerificationTamperError(
                                f"Unit {u.get('id')!r} verification differs from trusted external definitions"
                            )
                    elif isinstance(u, dict):
                        raise VerificationTamperError(
                            f"Unit {u.get('id')!r} missing from trusted external definitions"
                        )
            issue_meta = {"title": "", "issue_sha256": "", "scope": ()}
            if not args.offline:
                issue_meta = _fetch_issue(root, args.issue)
            snap_git = compute_candidate_snapshot(root, base_sha=args.base_sha)
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
            if args.expected_revision is not None and doc["revision"] != args.expected_revision:
                raise RevisionConflict(
                    f"CAS revision mismatch: expected {args.expected_revision}, actual {doc['revision']}"
                )
            base_sha = args.base_sha or doc["git"].get("base_sha") or "HEAD"
            proof = verify_host_gate_evidence(
                doc,
                args.unit_id,
                repo=args.repo,
                base_sha=base_sha,
                evidence_dir=args.evidence_dir,
                manifest_name=args.manifest,
                trusted_definitions=args.trusted_definitions,
            )
            updated = verify_unit_passing(
                doc,
                args.unit_id,
                proof=proof,
                expected_revision=args.expected_revision,
                trusted_definitions=args.trusted_definitions,
                repo=args.repo,
            )
            _save_to_journal_and_optional_file(
                updated,
                actor="host_verifier",
                expected_revision=rev,
                state_db=args.state,
                feature_file=args.feature_file,
                host_proofs={args.unit_id: proof},
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
                expected_revision=args.expected_revision,
                expected_branch=args.expected_branch,
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
                expected_revision=args.expected_revision,
                expected_branch=args.expected_branch,
            )
            print(json.dumps(res, indent=2, ensure_ascii=False))
            return 0

        if args.command == "session-close":
            res = session_close(
                issue=args.issue,
                repo=args.repo,
                state_db=args.state,
                next_action=args.next_action,
                blocker=args.blocker,
                feature_file=args.feature_file,
                export_path=args.export,
                evidence_dir=args.evidence_dir,
                cleanup_paths=args.cleanup_path or None,
                allowed_temp_roots=args.allowed_temp_root or None,
                owner_run_id=args.run_id,
                base_sha=args.base_sha,
                expected_revision=args.expected_revision,
                expected_branch=args.expected_branch,
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
            doc, proofs = sanitize_imported_doc(
                doc,
                repo=args.repo,
                base_sha=args.base_sha,
                evidence_dir=args.evidence_dir,
                manifest_name=args.manifest,
                trusted_definitions=args.trusted_definitions,
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
                    host_proofs=proofs or None,
                )
            print(json.dumps({
                "status": "IMPORTED",
                "issue": doc["issue"],
                "revision": doc["revision"],
                "verified_passing": sorted(proofs.keys()),
                "stale_units": [u["id"] for u in doc["units"] if u["state"] == "STALE"],
            }, indent=2))
            return 0
    except (FeatureStateError, ObservabilityError, StateConflict, WorktreeError, ContextGateError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:260]}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
