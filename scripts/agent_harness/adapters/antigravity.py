"""Headless Antigravity auditor adapter: fail closed on envelope and coverage."""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import tempfile
from pathlib import Path
from typing import Any

_ORIG_SUBPROCESS_RUN = subprocess.run

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
RUBRIC_DIMENSIONS = (
    "correctness",
    "verification",
    "scope_discipline",
    "reliability",
    "maintainability",
    "handoff_readiness",
)
RUBRIC_DECISIONS = {"ACCEPT", "REVISE", "BLOCK"}
_RUBRIC_KEYS = frozenset(("version", "decision", "hard_gate_passed", "total_score", "dimensions"))
_RUBRIC_DIM_KEYS = frozenset(("score", "rationale", "evidence", "findings"))
_HASH = re.compile(r"[0-9a-f]{64}")
HOST_TIMEOUT_GRACE_SECONDS = 30


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


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def run_bounded(args, *, cwd, input=None, timeout):
    """Keep provider output off the console, bound bytes, and kill process group on timeout/cancel."""
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        if subprocess.run is not _ORIG_SUBPROCESS_RUN:
            done = subprocess.run(args, cwd=cwd, input=input, text=True,
                                  stdout=output, stderr=errors, timeout=timeout,
                                  start_new_session=True, check=False)
        else:
            proc = subprocess.Popen(
                args,
                cwd=cwd,
                stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
                stdout=output,
                stderr=errors,
                text=True,
                start_new_session=True,
            )
            try:
                proc.communicate(input=input, timeout=timeout)
            except subprocess.TimeoutExpired:
                _kill_process_group(proc.pid)
                proc.communicate()
                raise
            except BaseException:
                if proc.poll() is None:
                    _kill_process_group(proc.pid)
                    proc.communicate()
                raise
            done = subprocess.CompletedProcess(args, proc.returncode, None, None)
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


def scoped_schema(required_rules, selection_sha256, required_paths=None, *, include_rubric: bool = False):
    """Generate the closed scoped schema without changing legacy consumers."""
    if (not isinstance(required_rules, list) or len(required_rules) > 128
            or not isinstance(selection_sha256, str) or not _HASH.fullmatch(selection_sha256)):
        raise AuditError("Missing or unbounded Host scoped selection")
    schema = json.loads(Path(__file__).with_name("audit.schema.json").read_text())
    for key in ("selection_sha256", "rule_results"):
        schema["properties"][key] = schema["$defs"][key]
        schema["required"].append(key)
    if include_rubric:
        schema["properties"]["rubric"] = schema["$defs"]["rubric"]
        schema["required"].append("rubric")
    schema["properties"]["selection_sha256"] = {"type": "string", "enum": [selection_sha256]}
    schema["properties"]["rule_results"].update(minItems=len(required_rules), maxItems=len(required_rules))
    if required_rules:
        schema["properties"]["rule_results"]["items"]["properties"]["rule_id"] = {
            "type": "string", "enum": [r["rule_id"] for r in required_rules]}
    if required_paths is not None:
        schema["properties"]["reviewed_scope"].update(
            minItems=len(required_paths), maxItems=len(required_paths))
    return schema


def validate_rubric(report: dict[str, Any], evidence_inventory: dict[str, str] | None = None) -> dict[str, Any]:
    """Validate structured 6-dimension 0-2 evaluator rubric (H2-ORC-04 / H2-FBK-03).

    Hard failures cannot be averaged away by a high total score.
    """
    rubric = report.get("rubric")
    if not isinstance(rubric, dict) or set(rubric) != _RUBRIC_KEYS:
        raise AuditError("Invalid rubric keys or structure")
    if rubric.get("version") != "1.0":
        raise AuditError("Unsupported rubric version")
    decision = rubric.get("decision")
    if not isinstance(decision, str) or decision not in RUBRIC_DECISIONS:
        raise AuditError("Invalid rubric decision")
    hard_gate_passed = rubric.get("hard_gate_passed")
    if type(hard_gate_passed) is not bool:
        raise AuditError("rubric.hard_gate_passed must be boolean")
    total_score = rubric.get("total_score")
    if type(total_score) is not int or not (0 <= total_score <= 12):
        raise AuditError("rubric.total_score must be an integer 0..12")
    dims = rubric.get("dimensions")
    if not isinstance(dims, dict) or set(dims) != set(RUBRIC_DIMENSIONS):
        raise AuditError("rubric.dimensions must contain exact six dimensions")

    computed_total = 0
    zero_dim = False
    for name in RUBRIC_DIMENSIONS:
        dim = dims[name]
        if not isinstance(dim, dict) or set(dim) != _RUBRIC_DIM_KEYS:
            raise AuditError(f"Invalid rubric dimension keys for {name}")
        score = dim.get("score")
        if type(score) is not int or score not in (0, 1, 2):
            raise AuditError(f"Rubric dimension {name} score must be integer 0, 1, or 2")
        if score == 0:
            zero_dim = True
        computed_total += score
        rationale = dim.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 1000:
            raise AuditError(f"Rubric dimension {name} requires bounded non-empty rationale")
        dim_findings = dim.get("findings")
        if not isinstance(dim_findings, list) or len(dim_findings) > 32 or not all(
            isinstance(f, str) and f.strip() and len(f) <= 300 for f in dim_findings
        ):
            raise AuditError(f"Rubric dimension {name} findings malformed")
        ev_list = dim.get("evidence")
        if not isinstance(ev_list, list) or len(ev_list) > 16:
            raise AuditError(f"Rubric dimension {name} evidence malformed")
        seen_ev = set()
        for ref in ev_list:
            if not isinstance(ref, dict) or set(ref) != {"receipt_path", "receipt_sha256"}:
                raise AuditError(f"Rubric dimension {name} evidence ref keys invalid")
            rpath, rsha = ref["receipt_path"], ref["receipt_sha256"]
            if not _canonical_path(rpath) or rpath in seen_ev or not _HASH.fullmatch(str(rsha)):
                raise AuditError(f"Rubric dimension {name} evidence ref invalid or duplicate")
            if evidence_inventory is not None:
                if rpath not in evidence_inventory or evidence_inventory[rpath] != rsha:
                    raise AuditError(f"Rubric dimension {name} evidence not in Host inventory")
            seen_ev.add(rpath)
        if score == 2 and evidence_inventory is not None and name in ("correctness", "verification") and not seen_ev:
            raise AuditError(f"Rubric dimension {name} score=2 requires Host-inventoried evidence")

    if total_score != computed_total:
        raise AuditError(f"rubric.total_score ({total_score}) disagrees with sum of dimensions ({computed_total})")

    has_blocking_finding = any(f.get("severity") in ("CRITICAL", "HIGH") for f in report.get("findings", []))
    has_incomplete_rule = any(
        r.get("status") in ("FAIL", "NOT_RUN", "NOT_VERIFIED", "WAIVED_WITH_REASON")
        for r in report.get("rule_results", [])
    )
    if not hard_gate_passed and decision == "ACCEPT":
        raise AuditError("Hard gate failure cannot be averaged away into rubric ACCEPT")
    if not hard_gate_passed and decision != "BLOCK":
        raise AuditError("Hard gate failure requires rubric decision BLOCK")
    if (has_blocking_finding or has_incomplete_rule or report.get("status") != "PASS") and decision == "ACCEPT":
        raise AuditError("Report with findings, incomplete rules, or non-PASS status cannot yield rubric ACCEPT")
    if zero_dim and decision == "ACCEPT":
        raise AuditError("Zero-score dimension cannot yield rubric ACCEPT")
    if decision == "ACCEPT" and (computed_total < 12 or report.get("findings") or report.get("limitations")):
        raise AuditError("Rubric ACCEPT requires 12/12 across all six dimensions and zero findings/limitations")
    if report.get("status") == "PASS" and decision != "ACCEPT":
        raise AuditError("Overall PASS cannot carry non-ACCEPT rubric decision")
    return rubric


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
                 selection_sha256=None, evidence_inventory=None,
                 *, require_rubric: bool = False) -> dict:
    """Validate complete audit structure and exact paths supplied by the Host."""
    scoped = required_rules is not None
    if not scoped and (selection_sha256 is not None or evidence_inventory is not None):
        raise AuditError("Partial Host scope cannot fall back to legacy validation")
    if scoped and evidence_inventory is None:
        evidence_inventory = {}
    has_rubric = isinstance(report, dict) and ("rubric" in report or require_rubric)
    keys = set(_ROOT_KEYS)
    if scoped:
        keys.update(("selection_sha256", "rule_results"))
    if has_rubric:
        keys.add("rubric")
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
    if has_rubric:
        validate_rubric(report, evidence_inventory=evidence_inventory if scoped else None)
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
                 selection_sha256=None, evidence_inventory=None,
                 *, require_rubric: bool = False) -> dict:
    if exit_code != 0:
        err_hint = stderr.strip() or stdout.strip()
        if "timeout" in err_hint.lower():
            raise AuditError(f"agy print-timeout expired: {err_hint[:200]}")
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
    if not isinstance(envelope, dict):
        raise AuditError("agy envelope is not a dictionary")
    if envelope.get("status") != "SUCCESS":
        st = envelope.get("status", "UNKNOWN")
        err = str(envelope.get("error", ""))
        if "timeout" in str(st).lower() or "timeout" in err.lower():
            raise AuditError(f"agy print-timeout expired: status={st} error={err[:200]}")
        raise AuditError(f"agy terminal status is not SUCCESS ({st})")
    if envelope.get("error"):
        err = str(envelope.get("error"))
        if "timeout" in err.lower():
            raise AuditError(f"agy print-timeout expired: {err[:200]}")
        raise AuditError(f"agy envelope contains error: {err[:200]}")
    if not isinstance(envelope.get("structured_output"), dict):
        raise AuditError("agy structured_output missing")
    return check_report(envelope["structured_output"], required_paths, required_rules,
                        selection_sha256, evidence_inventory, require_rubric=require_rubric)


def invoke(prompt: str, snapshot: Path, schema: Path, timeout: int,
           required_paths: set[str], required_rules=None,
           selection_sha256=None, evidence_inventory=None,
           effort: str = "low", *, require_rubric: bool = False) -> dict:
    """Run only in an operator-provisioned sandbox. This is NOT a VM boundary."""
    if not snapshot.is_dir() or snapshot.is_symlink():
        raise AuditError("Auditor snapshot must be a non-symlink directory")
    print_timeout = f"{timeout}s"
    host_timeout = timeout + HOST_TIMEOUT_GRACE_SECONDS
    args = ["agy", "--sandbox", "-p", prompt, "--output-format", "json",
            "--effort", effort,
            "--json-schema", str(schema), "--print-timeout", print_timeout]
    try:
        with tempfile.TemporaryDirectory(prefix="harness-audit-schema-") as directory:
            if required_rules is not None:
                scoped = Path(directory) / "audit.schema.json"
                scoped.write_text(json.dumps(scoped_schema(
                    required_rules, selection_sha256, required_paths, include_rubric=require_rubric)))
                args[args.index("--json-schema") + 1] = str(scoped)
            elif require_rubric:
                rubric_only = json.loads(Path(__file__).with_name("audit.schema.json").read_text())
                rubric_only["properties"]["rubric"] = rubric_only["$defs"]["rubric"]
                rubric_only["required"].append("rubric")
                scoped = Path(directory) / "audit.schema.json"
                scoped.write_text(json.dumps(rubric_only))
                args[args.index("--json-schema") + 1] = str(scoped)
            result = run_bounded(args, cwd=snapshot, timeout=host_timeout)
    except subprocess.TimeoutExpired as exc:
        raise AuditError(
            f"Host subprocess timeout expired after {host_timeout}s: process did not terminate within grace period"
        ) from exc
    except (OSError, UnicodeError) as exc:
        raise AuditError(f"agy unavailable or execution error: {type(exc).__name__}: {exc}") from exc
    if len(result.stdout.encode("utf-8")) > 160_000:
        raise AuditError("agy envelope exceeds the maximum size")
    return parse_result(result.returncode, result.stdout, result.stderr, required_paths,
                        required_rules, selection_sha256, evidence_inventory,
                        require_rubric=require_rubric)
