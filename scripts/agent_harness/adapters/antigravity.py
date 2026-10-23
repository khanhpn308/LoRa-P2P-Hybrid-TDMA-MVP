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


def check_report(report: Any, required_paths: set[str]) -> dict:
    if not isinstance(report, dict):
        raise AuditError("structured_output must be an object")
    if report.get("status") not in STATES:
        raise AuditError("missing or invalid review status")
    for field in ("findings", "limitations", "reviewed_scope"):
        if not isinstance(report.get(field), list):
            raise AuditError(f"missing {field} array")
    if (not all(isinstance(p, str) for p in report["reviewed_scope"])
            or not required_paths.issubset(set(report["reviewed_scope"]))):
        raise AuditError("auditor did not explicitly review all changed paths")
    if not all(isinstance(x, str) for x in report["limitations"]):
        raise AuditError("invalid limitations")
    for item in report["findings"]:
        if not isinstance(item, dict) or item.get("severity") not in SEVERITIES:
            raise AuditError("invalid finding severity")
        if (not isinstance(item.get("line"), int) or isinstance(item["line"], bool)
                or item["line"] < 1):
            raise AuditError("invalid finding line number")
        for key in ("file", "rule", "explanation", "fix"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise AuditError(f"invalid finding field {key}")
    if report["status"] == "PASS" and (report["findings"] or report["limitations"]):
        raise AuditError("PASS requires zero findings and zero limitations")
    return report


def parse_result(exit_code: int, stdout: str, stderr: str,
                 required_paths: set[str]) -> dict:
    if exit_code != 0:
        raise AuditError(f"agy exited {exit_code}")
    if DENIAL.search(stderr):
        raise AuditError("agy reported a permission denial")
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, TypeError) as exc:
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
