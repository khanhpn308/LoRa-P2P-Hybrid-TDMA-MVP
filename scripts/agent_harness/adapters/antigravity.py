"""Headless Antigravity auditor adapter: fail closed on envelope and coverage."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

DENIAL = re.compile(
    r"(permission denied|permission (was )?(soft[- ]?)?denied|"
    r"approval (required|denied)|not permitted|"
    r"tool .* (was )?denied|soft[- ]denied)",
    re.IGNORECASE,
)
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
STATES = {"PASS", "FAIL", "INCONCLUSIVE"}


class AuditError(ValueError):
    """A model response cannot be accepted as an independent audit."""


# Match the existing audit.schema.json (closed root and finding objects).
# If the schema changes, test_schema_contract_requires_review must fail and the
# Host validator must be independently reviewed before accepting new reports.
_ROOT_KEYS = frozenset(("status", "findings", "limitations", "reviewed_scope"))
_FINDING_KEYS = frozenset(("severity", "file", "line", "rule", "explanation", "fix"))
_MAX_ENVELOPE_BYTES = 160_000


def _canonical_path(value: Any) -> bool:
    """Reject aliases instead of silently normalizing untrusted audit paths.

    Lexical only: removed files are valid reviewed paths, even if absent on disk.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        return False
    if value.startswith("/") or "\\" in value or re.match(r"^[A-Za-z]:", value):
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def check_report(report: Any, required_paths: set[str]) -> dict:
    """Validate complete audit structure and exact paths supplied by the Host."""
    if not isinstance(report, dict) or set(report) != _ROOT_KEYS:
        raise AuditError("audit report keys differ from required schema")
    if not isinstance(report["status"], str) or report["status"] not in STATES:
        raise AuditError("missing or invalid review status")
    for field in ("findings", "limitations", "reviewed_scope"):
        if not isinstance(report[field], list):
            raise AuditError(f"missing {field} array")
    if not isinstance(required_paths, (set, frozenset)) or not all(
            _canonical_path(path) for path in required_paths):
        raise AuditError("invalid Host required scope")
    scope = report["reviewed_scope"]
    if not all(_canonical_path(path) for path in scope):
        raise AuditError("invalid reviewed_scope path")
    if len(scope) != len(set(scope)) or set(scope) != required_paths:
        raise AuditError("auditor reviewed_scope is not the exact changed path set")
    if not all(isinstance(item, str) for item in report["limitations"]):
        raise AuditError("invalid limitations")
    for item in report["findings"]:
        if not isinstance(item, dict) or set(item) != _FINDING_KEYS:
            raise AuditError("invalid finding keys")
        if (not isinstance(item["severity"], str)
                or item["severity"] not in SEVERITIES):
            raise AuditError("invalid finding severity")
        if type(item["line"]) is not int or item["line"] < 1:
            raise AuditError("invalid finding line number")
        if not _canonical_path(item["file"]):
            raise AuditError("invalid finding file path")
        for key in ("rule", "explanation", "fix"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise AuditError(f"invalid finding field {key}")
    if report["status"] == "PASS" and (report["findings"] or report["limitations"]):
        raise AuditError("PASS requires zero findings and zero limitations")
    return report


def _reject_duplicate_object_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_invalid_constant(_value: str) -> None:
    raise AuditError("non-finite JSON constant rejected")


def parse_result(exit_code: int, stdout: str, stderr: str,
                 required_paths: set[str]) -> dict:
    if exit_code != 0:
        raise AuditError(f"agy exited {exit_code}")
    if not isinstance(stderr, str) or DENIAL.search(stderr):
        raise AuditError("agy reported a permission denial")
    if not isinstance(stdout, str):
        raise AuditError("agy stdout is not a JSON envelope")
    try:
        if len(stdout.encode("utf-8")) > _MAX_ENVELOPE_BYTES:
            raise AuditError("agy envelope exceeds the maximum size")
        envelope = json.loads(
            stdout, object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_invalid_constant,
        )
    except (json.JSONDecodeError, UnicodeError, TypeError, ValueError) as exc:
        if isinstance(exc, AuditError):
            raise
        raise AuditError("agy stdout is not a JSON envelope") from exc
    if not isinstance(envelope, dict) or envelope.get("status") != "SUCCESS":
        raise AuditError("agy terminal status is not SUCCESS")
    if envelope.get("error"):
        raise AuditError("agy envelope contains error")
    if not isinstance(envelope.get("structured_output"), dict):
        raise AuditError("agy structured_output missing")
    return check_report(envelope["structured_output"], required_paths)


def invoke(prompt: str, snapshot: Path, schema: Path, timeout: int,
           required_paths: set[str]) -> dict:
    """Run only in an operator-provisioned sandbox. This is NOT a VM boundary."""
    args = ["agy", "--sandbox", "-p", prompt, "--output-format", "json",
            "--json-schema", str(schema), "--print-timeout", f"{max(1, timeout // 60)}m"]
    try:
        result = subprocess.run(
            args, cwd=snapshot, input=None, text=True,
            capture_output=True, timeout=timeout, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise AuditError(f"agy unavailable or timed out: {type(exc).__name__}") from exc
    if len(result.stdout.encode("utf-8")) > 160_000:
        raise AuditError("agy envelope exceeds the maximum size")
    return parse_result(result.returncode, result.stdout, result.stderr, required_paths)
