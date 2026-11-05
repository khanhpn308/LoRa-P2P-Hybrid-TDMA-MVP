"""Headless Antigravity auditor adapter: fail closed on envelope and coverage."""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
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
_RULE_KEYS = frozenset(("rule_id", "rule_sha256", "status", "evidence", "reason"))
_RULE_STATES = {"PASS", "FAIL", "NOT_RUN", "NOT_VERIFIED", "WAIVED_WITH_REASON"}
_HASH = re.compile(r"[0-9a-f]{64}")


def _safe_report_bytes(raw: bytes, structured=False) -> None:
    try:
        from ..quality_gates import secret_line
    except ImportError:
        from quality_gates import secret_line
    assignment = re.search(
        rb"(?i)\b(?:authorization|api[_-]?key|token|password|secret)\s*[:=]\s*[^\s\"',}]+", raw)
    if (len(raw) > _MAX_ENVELOPE_BYTES or secret_line(raw)
            or structured and (b"PRIVATE KEY-----" in raw or assignment)):
        raise AuditError("Oversized or credential-bearing model output rejected")


def run_bounded(args, *, cwd, input=None, timeout):
    """Keep provider output off the console and bound bytes before decoding."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        done = subprocess.run(args, cwd=cwd, input=input, text=True,
                              stdout=output, stderr=errors, timeout=timeout, check=False)
        streams = []
        for value, stream in ((done.stdout, output), (done.stderr, errors)):
            if isinstance(value, str):
                raw = value.encode("utf-8")
            else:
                stream.seek(0)
                raw = stream.read(_MAX_ENVELOPE_BYTES + 1)
            _safe_report_bytes(raw)
            streams.append(raw.decode("utf-8", errors="strict"))
        return subprocess.CompletedProcess(args, done.returncode, *streams)


def scoped_schema(required_rules, selection_sha256, required_paths=None):
    """Generate the closed scoped schema without changing legacy consumers."""
    if (not isinstance(required_rules, list) or len(required_rules) > 128
            or not isinstance(selection_sha256, str) or not _HASH.fullmatch(selection_sha256)):
        raise AuditError("Missing or unbounded Host scoped selection")
    schema = json.loads(Path(__file__).with_name("audit.schema.json").read_text())
    for key in ("selection_sha256", "rule_results"):
        schema["properties"][key] = schema["$defs"][key]
        schema["required"].append(key)
    schema["properties"]["selection_sha256"] = {"type": "string", "enum": [selection_sha256]}
    schema["properties"]["rule_results"].update(minItems=len(required_rules), maxItems=len(required_rules))
    if required_rules:
        schema["properties"]["rule_results"]["items"]["properties"]["rule_id"] = {
            "type": "string", "enum": [r["rule_id"] for r in required_rules]}
    if required_paths is not None:
        schema["properties"]["reviewed_scope"].update(
            minItems=len(required_paths), maxItems=len(required_paths))
    return schema


def _check_rules(report, required_rules, selection_sha256, evidence_inventory):
    if (not isinstance(selection_sha256, str) or not _HASH.fullmatch(selection_sha256)
            or report["selection_sha256"] != selection_sha256
            or not isinstance(required_rules, list) or len(required_rules) > 128
            or not isinstance(evidence_inventory, dict)
            or any(not _canonical_path(p) or not isinstance(h, str) or not _HASH.fullmatch(h)
                   for p, h in evidence_inventory.items())):
        raise AuditError("Invalid Host selection or evidence inventory")
    expected = {}
    for rule in required_rules:
        rid, row_hash = rule["rule_id"], rule["rule_sha256"]
        if (not isinstance(rid, str) or not re.fullmatch(r"[A-Z]+-[0-9]{3}", rid)
                or rid in expected or not isinstance(row_hash, str) or not _HASH.fullmatch(row_hash)):
            raise AuditError("Invalid Host Rule ID inventory")
        expected[rid] = row_hash
    results = report["rule_results"]
    if not isinstance(results, list) or len(results) != len(expected):
        raise AuditError("Missing or excessive per-rule coverage")
    seen = set()
    for item in results:
        if not isinstance(item, dict) or set(item) != _RULE_KEYS:
            raise AuditError("Invalid per-rule report schema")
        rid = item["rule_id"]
        if (not isinstance(rid, str) or rid in seen or rid not in expected
                or item["rule_sha256"] != expected[rid]
                or not isinstance(item["status"], str) or item["status"] not in _RULE_STATES
                or not isinstance(item["reason"], str) or not item["reason"].strip()
                or len(item["reason"].encode()) > 2000
                or not isinstance(item["evidence"], list) or len(item["evidence"]) > 32):
            raise AuditError("Unknown, duplicate, stale or malformed per-rule result")
        seen.add(rid)
        references = set()
        for reference in item["evidence"]:
            if (not isinstance(reference, dict)
                    or set(reference) != {"receipt_path", "receipt_sha256"}):
                raise AuditError("Invalid rule evidence reference")
            path, sha = reference["receipt_path"], reference["receipt_sha256"]
            if (not _canonical_path(path) or path in references or path not in evidence_inventory
                    or sha != evidence_inventory[path]):
                raise AuditError("Untrusted, missing or changed rule evidence")
            references.add(path)
        if item["status"] == "PASS" and not references:
            raise AuditError("Per-rule PASS requires Host-inventoried evidence")
        if report["status"] == "PASS" and item["status"] != "PASS":
            raise AuditError("Overall PASS cannot hide incomplete or waived rules")


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


def check_report(report: Any, required_paths: set[str], required_rules=None,
                 selection_sha256=None, evidence_inventory=None) -> dict:
    """Validate complete audit structure and exact paths supplied by the Host."""
    scoped = required_rules is not None
    if not scoped and (selection_sha256 is not None or evidence_inventory is not None):
        raise AuditError("Partial Host scope cannot fall back to legacy validation")
    if scoped and evidence_inventory is None:
        evidence_inventory = {}
    keys = _ROOT_KEYS | {"selection_sha256", "rule_results"} if scoped else _ROOT_KEYS
    if not isinstance(report, dict) or set(report) != keys:
        raise AuditError("audit report keys differ from required schema")
    try:
        _safe_report_bytes(json.dumps(report, allow_nan=False).encode(), structured=True)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise AuditError("Invalid or unbounded report encoding") from exc
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
    if scoped:
        try:
            _check_rules(report, required_rules, selection_sha256, evidence_inventory)
        except AuditError:
            raise
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise AuditError("Scoped rule or evidence verification failed") from exc
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
                 required_paths: set[str], required_rules=None,
                 selection_sha256=None, evidence_inventory=None) -> dict:
    if exit_code != 0:
        raise AuditError(f"agy exited {exit_code}")
    if not isinstance(stderr, str) or DENIAL.search(stderr):
        raise AuditError("agy reported a permission denial")
    if not isinstance(stdout, str):
        raise AuditError("agy stdout is not a JSON envelope")
    try:
        _safe_report_bytes(stdout.encode("utf-8"))
        _safe_report_bytes(stderr.encode("utf-8"))
        envelope = json.loads(
            stdout, object_pairs_hook=_reject_duplicate_object_keys,
            parse_constant=_reject_invalid_constant,
        )
    except (json.JSONDecodeError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        if isinstance(exc, AuditError):
            raise
        raise AuditError("agy stdout is not a JSON envelope") from exc
    if not isinstance(envelope, dict) or envelope.get("status") != "SUCCESS":
        raise AuditError("agy terminal status is not SUCCESS")
    if envelope.get("error"):
        raise AuditError("agy envelope contains error")
    if not isinstance(envelope.get("structured_output"), dict):
        raise AuditError("agy structured_output missing")
    return check_report(envelope["structured_output"], required_paths, required_rules,
                        selection_sha256, evidence_inventory)


def invoke(prompt: str, snapshot: Path, schema: Path, timeout: int,
           required_paths: set[str], required_rules=None,
           selection_sha256=None, evidence_inventory=None) -> dict:
    """Run only in an operator-provisioned sandbox. This is NOT a VM boundary."""
    args = ["agy", "--sandbox", "-p", prompt, "--output-format", "json",
            "--json-schema", str(schema), "--print-timeout", f"{max(1, timeout // 60)}m"]
    try:
        with tempfile.TemporaryDirectory(prefix="harness-audit-schema-") as directory:
            if required_rules is not None:
                scoped = Path(directory) / "audit.schema.json"
                scoped.write_text(json.dumps(scoped_schema(required_rules, selection_sha256, required_paths)))
                args[args.index("--json-schema") + 1] = str(scoped)
            result = run_bounded(args, cwd=snapshot, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError, UnicodeError) as exc:
        raise AuditError(f"agy unavailable or timed out: {type(exc).__name__}") from exc
    if len(result.stdout.encode("utf-8")) > 160_000:
        raise AuditError("agy envelope exceeds the maximum size")
    return parse_result(result.returncode, result.stdout, result.stderr, required_paths,
                        required_rules, selection_sha256, evidence_inventory)
