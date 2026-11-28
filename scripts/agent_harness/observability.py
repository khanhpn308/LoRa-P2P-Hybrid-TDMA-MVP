#!/usr/bin/env python3
"""P06 Bounded Redacted Observability, Signal Attribution, Cleanup & Handoff Verification.

Implements HARNESS_MASTER_PLAN.md §9, H2-FBK-06, and H2-GOV-03 by reusing P04
SQLite Journal/checkpoints and P05 check/gate/PR receipts without external
collectors, daemons, or OpenTelemetry stacks.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

try:
    from .p1.state import (
        Journal,
        MAX_EXCERPT_CHARS,
        MAX_FINDING_CHARS,
        MAX_QUERY_LIMIT,
        MAX_SIGNAL_ROWS,
        StateConflict,
        _SENSITIVE_KEY_RE,
        _is_safe_placeholder,
        _redact_signal_text,
    )
    from .quality_gates import digest, secret_line
except ImportError:
    from p1.state import (
        Journal,
        MAX_EXCERPT_CHARS,
        MAX_FINDING_CHARS,
        MAX_QUERY_LIMIT,
        MAX_SIGNAL_ROWS,
        StateConflict,
        _SENSITIVE_KEY_RE,
        _is_safe_placeholder,
        _redact_signal_text,
    )
    from quality_gates import digest, secret_line

SCHEMA_VERSION = "1.0"
DEFAULT_EXCERPT_BYTES = 4096
DEFAULT_LOG_BYTES = 2_000_000
OWNER_MARKER_NAME = ".harness-owner.json"
PROTECTED_EVIDENCE_NAMES = frozenset(
    {
        "state.sqlite",
        "state.sqlite-wal",
        "state.sqlite-shm",
        "manifest.json",
        "checks_summary.json",
        "quality-manifest.json",
        "pre-audit-gates.json",
        "post-audit-gates.json",
        "auditor-report.json",
        "auditor_report.json",
        "auditor_context.json",
        "auditor_prompt.txt",
        "diff.patch",
        "changes.patch",
        "remediation.patch",
        "checks.log",
        "checks.json",
        "worker-report.json",
        "selected-rules.json",
        "initial-rules.json",
        "g0-context.json",
        "rule_selection.json",
        "check_runs.json",
    }
)

_BEARER_DETECT_RE = re.compile(r"(?i)(?:authorization\s*[:=]\s*bearer\s+|bearer\s+)[A-Za-z0-9._~+/=-]{12,}")
_URL_CRED_DETECT_RE = re.compile(r"(?:postgres(?:ql)?|mqtts?|https?|redis)://[^:\s/@]+:[^@\s/]+@")
_KV_DETECT_RE = re.compile(
    r"""(?im)\b(?:POSTGRES_PASSWORD|MQTT_PASSWORD|password|passwd|api[_-]?key|access[_-]?token|auth[_-]?token|secret|private[_-]?key)\b\s*[:=]\s*["']?([^"'\s\r\n#]+)"""
)

RUNTIME_SIGNAL_CATALOG: tuple[dict[str, str], ...] = (
    {
        "signal_id": "uart_radio",
        "owning_domain": "firmware",
        "collector": "scripts/agent_harness/check.py --profile bench --allow-bench --bench-auth <path> / tests/hil/",
        "signals": "ESP-IDF UART console logs, SX1276 DIO/IRQ/RSSI/SNR, CAD/CSMA-CA timings",
        "authority_note": "OD-07: Strictly NOT_VERIFIED without physical bench authorization and equipment.",
    },
    {
        "signal_id": "mqtt_broker",
        "owning_domain": "mqtt",
        "collector": "tests/integration/test_local_infra.py / tests/integration/mqtt_session_key/ / quality_gates.py",
        "signals": "Mosquitto startup logs, ACL uid/gid/mode, TLS/ACL positive & negative exit probes",
        "authority_note": "Requires Docker runtime; NOT_VERIFIED when offline/unexecuted.",
    },
    {
        "signal_id": "db_postgres",
        "owning_domain": "infra",
        "collector": "tests/integration/test_*_postgres.py / quality_gates.py INFRA-CHECK",
        "signals": "PostgreSQL healthcheck, schema migration & dedup persistence queries",
        "authority_note": "Requires Docker PostgreSQL runtime; NOT_VERIFIED when unexecuted.",
    },
    {
        "signal_id": "go_api",
        "owning_domain": "backend-go",
        "collector": "scripts/agent_harness/check.py (go-test, go-vet, go-build) / backend-go/cmd/server",
        "signals": "/healthz HTTP handler checks, Go unit tests, static vet & build receipts",
        "authority_note": "Requires pinned Go toolchain (1.27.3) or matching container.",
    },
    {
        "signal_id": "web_ui",
        "owning_domain": "clients",
        "collector": "clients/web-dashboard runtime DOM/network verification (not static screenshots alone)",
        "signals": "Authenticated REST/WSS runtime state before/after user action",
        "authority_note": "NOT_VERIFIED unless live client runtime verification executed.",
    },
    {
        "signal_id": "harness_process",
        "owning_domain": "harness",
        "collector": "check.py, quality_gates.py, pr_review.py, run.py, feature_state.py, harness_doctor.py",
        "signals": "Issue/unit/run lifecycle, candidate SHA/diff fingerprints, check receipts, findings, checkpoints",
        "authority_note": "Host SQLite Journal + external evidence dir; bounded and redacted.",
    },
)

_DOMAIN_REMEDIATION: dict[str, str] = {
    "firmware": "Inspect firmware C/CMake check log and run unit tests or ESP-IDF v6.1 disposable build.",
    "backend-go": "Inspect Go test/vet/build log and verify pinned Go 1.27.3 compatibility.",
    "clients": "Inspect client lint/build/runtime state log under clients/.",
    "contracts": "Inspect contracts/ schema/$ref validation failure and preserve versioned compatibility.",
    "infra": "Inspect Docker/Compose/PostgreSQL runtime logs and loopback/mount checks.",
    "mqtt": "Inspect Mosquitto ACL/TLS/mount logs without exposing keys or relaxing denials.",
    "harness": "Inspect Harness unit/doctor/gate logs and verify bounded scope & G0 invariants.",
    "security": "Inspect SECRET-SCAN/SECURITY-CHECK finding, remove secret from worktree+index, and route to human review.",
    "foundation": "Run scripts/verify_structure.py and resolve monorepo layout or pin drift.",
}


class ObservabilityError(RuntimeError):
    """Raised on unsafe paths, retention errors, or invalid observability inputs."""


class CleanupError(ObservabilityError):
    """Raised when cleanup refuses unsafe, unowned, symlinked, or evidence paths."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def contains_secret(text: str) -> bool:
    """Return True when text contains recognizable credential or private-key material."""
    if not text:
        return False
    raw = text.encode("utf-8", errors="replace")
    if secret_line(raw) is not None:
        return True
    if _BEARER_DETECT_RE.search(text) or _URL_CRED_DETECT_RE.search(text):
        return True
    for m in _KV_DETECT_RE.finditer(text):
        val = m.group(1).strip()
        if val and not val.startswith(("$", "REPLACE_", "<", "[REDACTED")):
            return True
    return False


def redact_text(text: str, *, max_bytes: int = DEFAULT_EXCERPT_BYTES) -> tuple[str, bool, bool]:
    """Redact credentials and bound UTF-8 size. Returns (redacted, was_redacted, was_truncated)."""
    if not text:
        return "", False, False
    if max_bytes < 64:
        raise ObservabilityError("max_bytes bound must be >= 64")
    redacted = _redact_signal_text(text, max_chars=max(len(text) + 64, MAX_EXCERPT_CHARS))
    # Fail-safe pass: if quality_gates.secret_line still flags any line, scrub that line explicitly.
    if secret_line(redacted.encode("utf-8", errors="replace")) is not None:
        safe_lines: list[str] = []
        for line in redacted.splitlines():
            if secret_line(line.encode("utf-8", errors="replace")) is not None:
                safe_lines.append("[REDACTED:SECRET_LINE]")
            else:
                safe_lines.append(line)
        redacted = "\n".join(safe_lines)
    was_redacted = redacted != text
    encoded = redacted.encode("utf-8", errors="replace")
    was_truncated = False
    if len(encoded) > max_bytes:
        was_truncated = True
        suffix = b"\n...[TRUNCATED]"
        keep = max(0, max_bytes - len(suffix))
        redacted = encoded[:keep].decode("utf-8", errors="ignore") + suffix.decode("utf-8")
    return redacted, was_redacted, was_truncated


def redact_data(
    obj: Any,
    *,
    max_string_bytes: int = DEFAULT_EXCERPT_BYTES,
    sensitive_context: bool = False,
) -> Any:
    """Recursively redact JSON data by both key and value, including nested credentials."""
    if isinstance(obj, str):
        if sensitive_context and not _is_safe_placeholder(obj):
            return "[REDACTED]"
        sanitized, _, _ = redact_text(obj, max_bytes=max_string_bytes)
        return sanitized
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        if sensitive_context:
            return "[REDACTED]"
        return obj
    if isinstance(obj, list):
        return [
            redact_data(item, max_string_bytes=max_string_bytes, sensitive_context=sensitive_context)
            for item in obj[:200]
        ]
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in list(obj.items())[:100]:
            raw_key = str(k)
            safe_key, _, _ = redact_text(raw_key, max_bytes=max_string_bytes)
            child_sensitive = sensitive_context or (_SENSITIVE_KEY_RE.search(raw_key) is not None)
            out[safe_key] = redact_data(
                v,
                max_string_bytes=max_string_bytes,
                sensitive_context=child_sensitive,
            )
        return out
    return obj


def _reject_symlink_path(path: pathlib.Path, *, label: str = "path") -> pathlib.Path:
    if path.is_symlink():
        raise ObservabilityError(f"{label} must not be a symlink: {path}")
    for parent in path.parents:
        if parent.is_symlink():
            raise ObservabilityError(f"{label} parent must not be a symlink: {parent}")
    return path


def _safe_read_json(path: pathlib.Path, *, max_bytes: int = DEFAULT_LOG_BYTES) -> Any:
    _reject_symlink_path(path, label="input file")
    if not path.is_file():
        raise ObservabilityError(f"Missing regular JSON file: {path}")
    size = path.stat().st_size
    if size > max_bytes:
        raise ObservabilityError(f"JSON input exceeds {max_bytes} byte limit: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_read_excerpt(path: pathlib.Path, *, max_bytes: int = DEFAULT_EXCERPT_BYTES) -> tuple[str, bool, bool]:
    _reject_symlink_path(path, label="log file")
    if not path.is_file():
        return "", False, False
    with path.open("rb") as fh:
        raw = fh.read(max_bytes + 1)
    truncated_read = len(raw) > max_bytes
    if truncated_read:
        raw = raw[-max_bytes:]
    text = raw.decode("utf-8", errors="replace")
    redacted, was_redacted, was_truncated = redact_text(text, max_bytes=max_bytes)
    return redacted, was_redacted, (truncated_read or was_truncated)


def record_process_signal(
    *,
    journal_path: pathlib.Path,
    signal_type: str = "process",
    category: str,
    owning_domain: str,
    status: str,
    captured: bool = True,
    issue: int | None = None,
    unit_id: str | None = None,
    run_id: str | None = None,
    check_id: str = "",
    command: list[str] | str | None = None,
    source_sha: str = "",
    candidate_sha256: str = "",
    diff_sha256: str = "",
    started_at: str = "",
    ended_at: str = "",
    duration_s: float = 0.0,
    exit_code: int | None = None,
    finding: str = "",
    evidence_ref: dict[str, Any] | None = None,
    excerpt: str = "",
    max_signals: int = MAX_SIGNAL_ROWS,
) -> dict[str, Any]:
    """Persist a bounded, redacted process or runtime signal into the Host Journal."""
    _reject_symlink_path(journal_path, label="journal")
    cmd_sha = ""
    if command is not None:
        cmd_sha = digest(json.dumps(command).encode("utf-8"))
    safe_finding, f_red, _ = redact_text(finding, max_bytes=MAX_FINDING_CHARS)
    safe_excerpt, e_red, e_trunc = redact_text(excerpt, max_bytes=MAX_EXCERPT_CHARS)
    safe_ref = redact_data(evidence_ref or {}, max_string_bytes=MAX_FINDING_CHARS)
    with Journal(journal_path) as journal:
        signal_id = journal.record_signal(
            signal_type=signal_type,
            category=category,
            owning_domain=owning_domain,
            status=status,
            captured=captured,
            issue=issue,
            unit_id=unit_id,
            run_id=run_id,
            check_id=check_id,
            command_sha256=cmd_sha,
            source_sha=source_sha,
            candidate_sha256=candidate_sha256,
            diff_sha256=diff_sha256,
            started_at=started_at,
            ended_at=ended_at,
            duration_s=duration_s,
            exit_code=exit_code,
            finding=safe_finding,
            evidence_ref=safe_ref,
            excerpt=safe_excerpt,
            max_signals=max_signals,
        )
    return {
        "signal_id": signal_id,
        "status": status,
        "redacted": f_red or e_red,
        "truncated": e_trunc,
    }


def ingest_checks_summary(
    evidence_dir: pathlib.Path,
    *,
    journal_path: pathlib.Path,
    issue: int | None = None,
    unit_id: str | None = None,
    run_id: str | None = None,
    summary_name: str = "checks_summary.json",
    max_signals: int = MAX_SIGNAL_ROWS,
) -> list[dict[str, Any]]:
    """Ingest P05 check.py checks_summary.json into bounded redacted Journal signals."""
    _reject_symlink_path(evidence_dir, label="evidence_dir")
    _reject_symlink_path(journal_path, label="journal")
    summary_path = evidence_dir / summary_name
    summary = _safe_read_json(summary_path)
    if not isinstance(summary, dict) or not isinstance(summary.get("results"), list):
        raise ObservabilityError("Malformed checks_summary.json")

    recorded: list[dict[str, Any]] = []
    source_sha = str(summary.get("source_sha", ""))
    cand_sha = str(summary.get("candidate_sha256", ""))
    diff_sha = str(summary.get("diff_sha256", ""))
    recorded_at = str(summary.get("recorded_at", ""))

    with Journal(journal_path) as journal:
        for item in summary["results"]:
            if not isinstance(item, dict):
                continue
            check_id = str(item.get("check_id", ""))
            domain = str(item.get("domain", "harness"))
            status = str(item.get("status", "NOT_VERIFIED"))
            receipt_rel = str(item.get("receipt_path", ""))
            receipt_sha = str(item.get("receipt_sha256", ""))
            excerpt = ""
            if receipt_rel and "/" not in receipt_rel and "\\" not in receipt_rel:
                excerpt, _, _ = _safe_read_excerpt(evidence_dir / receipt_rel, max_bytes=DEFAULT_EXCERPT_BYTES)
            finding = str(item.get("finding") or item.get("reason") or "")
            if not finding and status != "PASS":
                finding = f"Check {check_id} exited {item.get('exit_code')} ({status}) in domain {domain}"
            sig_id = journal.record_signal(
                signal_type="process",
                category="check",
                owning_domain=domain,
                status=status,
                captured=status != "NOT_RUN",
                issue=issue,
                unit_id=unit_id,
                run_id=run_id,
                check_id=check_id,
                command_sha256=str(item.get("command_sha256", "")),
                source_sha=source_sha,
                candidate_sha256=cand_sha,
                diff_sha256=diff_sha,
                started_at=str(item.get("started_at", "")),
                ended_at=str(item.get("ended_at", "")) or recorded_at,
                duration_s=float(item.get("duration_s", 0.0) or 0.0),
                exit_code=item.get("exit_code"),
                finding=finding,
                evidence_ref={
                    "receipt_path": receipt_rel,
                    "receipt_sha256": receipt_sha,
                    "summary_path": summary_name,
                },
                excerpt=excerpt,
                max_signals=max_signals,
            )
            recorded.append({"signal_id": sig_id, "check_id": check_id, "owning_domain": domain, "status": status})

        qg = summary.get("quality_gates")
        if isinstance(qg, dict) and qg.get("auto_check") and qg.get("auto_check") != "NOT_RUN":
            auto_status = "PASS" if qg.get("auto_check") == "AUTO_CHECK_PASS" else "FAIL"
            failed_rules = [
                f"{r.get('rule_id')}:{r.get('status')}"
                for r in qg.get("results", [])
                if isinstance(r, dict) and r.get("status") not in ("PASS", "NOT_RUN")
            ]
            sig_id = journal.record_signal(
                signal_type="process",
                category="gate",
                owning_domain="harness",
                status=auto_status,
                captured=True,
                issue=issue,
                unit_id=unit_id,
                run_id=run_id,
                check_id="quality_gates",
                source_sha=source_sha,
                candidate_sha256=cand_sha,
                diff_sha256=diff_sha,
                ended_at=recorded_at,
                exit_code=0 if auto_status == "PASS" else 1,
                finding=", ".join(failed_rules)[:MAX_FINDING_CHARS],
                evidence_ref={"manifest_path": "manifest.json", "summary_path": summary_name},
                max_signals=max_signals,
            )
            recorded.append({"signal_id": sig_id, "check_id": "quality_gates", "owning_domain": "harness", "status": auto_status})
    return recorded


def ingest_pr_review_report(
    report_path: pathlib.Path,
    *,
    journal_path: pathlib.Path,
    issue: int | None = None,
    run_id: str | None = None,
    max_signals: int = MAX_SIGNAL_ROWS,
) -> list[dict[str, Any]]:
    """Ingest pr_review.py JSON output into bounded redacted Journal signals."""
    _reject_symlink_path(journal_path, label="journal")
    doc = _safe_read_json(report_path)
    if not isinstance(doc, dict) or not isinstance(doc.get("evaluation"), dict):
        raise ObservabilityError("Malformed PR review JSON report")
    ev = doc["evaluation"]
    snap = doc.get("snapshot") if isinstance(doc.get("snapshot"), dict) else {}
    verdict = str(ev.get("verdict", "NOT_VERIFIED"))
    status = "PASS" if verdict == "READY_FOR_HUMAN_REVIEW" else ("BLOCKED" if verdict == "BLOCKED" else "FAIL")
    if verdict == "NOT_VERIFIED":
        status = "NOT_VERIFIED"
    findings = ev.get("findings", [])
    finding_summary = "; ".join(
        f"{f.get('gate', f.get('rule', 'PR'))}:{f.get('message', f.get('explanation', ''))}"
        for f in findings[:5]
        if isinstance(f, dict)
    )
    with Journal(journal_path) as journal:
        sig_id = journal.record_signal(
            signal_type="process",
            category="pr_review",
            owning_domain="harness",
            status=status,
            captured=True,
            issue=issue,
            run_id=run_id,
            check_id=f"pr-{snap.get('pr_number', 'review')}",
            source_sha=str(snap.get("head_sha", "")),
            diff_sha256=str(snap.get("diff_sha256", "")),
            ended_at=str(snap.get("timestamp_utc", "")),
            exit_code=0 if verdict == "READY_FOR_HUMAN_REVIEW" else 1,
            finding=finding_summary or f"PR review verdict={verdict}",
            evidence_ref={
                "report_path": report_path.name,
                "pr_number": snap.get("pr_number"),
                "verdict": verdict,
            },
            max_signals=max_signals,
        )
    return [{"signal_id": sig_id, "verdict": verdict, "status": status}]


def query_signals(
    journal_path: pathlib.Path,
    *,
    issue: int | None = None,
    run_id: str | None = None,
    unit_id: str | None = None,
    signal_type: str | None = None,
    category: str | None = None,
    owning_domain: str | None = None,
    status: str | None = None,
    captured: bool | None = None,
    since: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Bounded query of redacted signals from SQLite Journal."""
    _reject_symlink_path(journal_path, label="journal")
    if not journal_path.exists():
        return []
    with Journal(journal_path) as journal:
        return journal.query_signals(
            issue=issue,
            run_id=run_id,
            unit_id=unit_id,
            signal_type=signal_type,
            category=category,
            owning_domain=owning_domain,
            status=status,
            captured=captured,
            since=since,
            limit=min(max(1, limit), MAX_QUERY_LIMIT),
        )


def diagnose_failures(
    journal_path: pathlib.Path,
    *,
    issue: int | None = None,
    run_id: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Trace failed/blocked/unverified signals to owning domain and remediation."""
    signals = query_signals(journal_path, issue=issue, run_id=run_id, limit=limit)
    failures: list[dict[str, Any]] = []
    for sig in signals:
        if sig["status"] in ("FAIL", "BLOCKED", "ERROR", "TIMEOUT", "NOT_VERIFIED"):
            domain = sig["owning_domain"]
            failures.append(
                {
                    "signal_id": sig["signal_id"],
                    "check_id": sig["check_id"],
                    "category": sig["category"],
                    "owning_domain": domain,
                    "status": sig["status"],
                    "exit_code": sig["exit_code"],
                    "source_sha": sig["source_sha"],
                    "candidate_sha256": sig["candidate_sha256"],
                    "finding": sig["finding"],
                    "evidence_ref": sig["evidence_ref"],
                    "remediation": _DOMAIN_REMEDIATION.get(
                        domain, "Inspect recorded evidence receipt and resolve failure in owning domain."
                    ),
                }
            )
    priority = {"runtime_probe": 0, "check": 1, "worker": 2, "auditor": 2, "pr_review": 2, "experiment": 2, "gate": 3, "session": 4}
    prioritized = sorted(failures, key=lambda f: (priority.get(f["category"], 3), -int(f["signal_id"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "issue": issue,
        "total_inspected": len(signals),
        "failure_count": len(failures),
        "failures": failures,
        "latest_failure": prioritized[0] if prioritized else None,
    }


def collect_runtime_signal_map(
    *,
    repo: pathlib.Path,
    journal_path: pathlib.Path | None = None,
    evidence_dir: pathlib.Path | None = None,
    issue: int | None = None,
) -> dict[str, Any]:
    """Map captured vs planned/unavailable process and runtime signals honestly."""
    repo_root = _reject_symlink_path(repo, label="repo").resolve(strict=True)
    captured_signals: list[dict[str, Any]] = []
    captured_domains: set[str] = set()

    if journal_path is not None and journal_path.exists():
        for sig in query_signals(journal_path, issue=issue, limit=50):
            if sig["captured"]:
                captured_signals.append(sig)
                captured_domains.add(sig["owning_domain"])

    if evidence_dir is not None and evidence_dir.exists():
        _reject_symlink_path(evidence_dir, label="evidence_dir")
        summary_file = evidence_dir / "checks_summary.json"
        if summary_file.is_file():
            summary = _safe_read_json(summary_file)
            for res in summary.get("results", []):
                if isinstance(res, dict) and res.get("status") != "NOT_RUN":
                    captured_domains.add(str(res.get("domain", "harness")))
                    captured_signals.append(
                        {
                            "signal_type": "process",
                            "category": "check_receipt",
                            "owning_domain": str(res.get("domain", "harness")),
                            "check_id": str(res.get("check_id", "")),
                            "status": str(res.get("status", "NOT_VERIFIED")),
                            "captured": True,
                            "source_sha": summary.get("source_sha", ""),
                            "candidate_sha256": summary.get("candidate_sha256", ""),
                            "evidence_ref": {
                                "receipt_path": res.get("receipt_path", ""),
                                "receipt_sha256": res.get("receipt_sha256", ""),
                            },
                        }
                    )

    planned_or_unavailable: list[dict[str, Any]] = []
    for entry in RUNTIME_SIGNAL_CATALOG:
        sid = entry["signal_id"]
        dom = entry["owning_domain"]
        is_captured = dom in captured_domains and sid != "uart_radio"
        if sid == "uart_radio":
            # RF/HIL bench stays NOT_VERIFIED unless explicitly captured as runtime uart_radio signal.
            is_captured = any(
                s.get("signal_type") == "runtime" and s.get("check_id") == "uart_radio" and s.get("captured")
                for s in captured_signals
            )
        if not is_captured:
            planned_or_unavailable.append(
                {
                    **entry,
                    "captured": False,
                    "status": "NOT_VERIFIED",
                }
            )

    return {
        "schema_version": SCHEMA_VERSION,
        "repo": str(repo_root),
        "issue": issue,
        "captured_count": len(captured_signals),
        "unavailable_count": len(planned_or_unavailable),
        "captured_signals": captured_signals[:50],
        "unavailable_or_planned_signals": planned_or_unavailable,
    }


def _assert_no_nested_symlinks(directory: pathlib.Path) -> None:
    for root, dirs, files in os.walk(directory, followlinks=False):
        root_p = pathlib.Path(root)
        for name in dirs + files:
            candidate = root_p / name
            if candidate.is_symlink():
                raise CleanupError(f"Refusing cleanup containing symlink: {candidate}")


def write_owner_marker(
    directory: pathlib.Path,
    *,
    issue: int,
    run_id: str,
) -> pathlib.Path:
    """Write explicit ownership metadata inside a dedicated temporary scratch directory."""
    _reject_symlink_path(directory, label="owned temp dir")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    marker = directory / OWNER_MARKER_NAME
    payload = {
        "owner": "lora-harness",
        "issue": int(issue),
        "run_id": str(run_id),
        "created_at": _utc_now(),
    }
    marker.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return marker


def _validate_owner_marker(
    marker_path: pathlib.Path,
    *,
    target: pathlib.Path,
    owner_issue: int | None,
    owner_run_id: str | None,
) -> dict[str, Any]:
    if marker_path.is_symlink() or not marker_path.is_file():
        raise CleanupError(f"Refusing cleanup without valid non-symlink {OWNER_MARKER_NAME}: {target}")
    marker = _safe_read_json(marker_path)
    if (
        not isinstance(marker, dict)
        or marker.get("owner") != "lora-harness"
        or type(marker.get("issue")) is not int
        or marker["issue"] <= 0
        or not isinstance(marker.get("run_id"), str)
        or not marker["run_id"].strip()
    ):
        raise CleanupError(f"Invalid ownership marker for {target}")
    if owner_issue is not None and marker.get("issue") != owner_issue:
        raise CleanupError(f"Cleanup issue ownership mismatch in {target}")
    if owner_run_id is not None and marker.get("run_id") != owner_run_id:
        raise CleanupError(f"Cleanup run_id ownership mismatch in {target}")
    return marker


def cleanup_owned_artifacts(
    owned_paths: list[pathlib.Path],
    *,
    allowed_temp_roots: list[pathlib.Path],
    repo: pathlib.Path | None = None,
    owner_issue: int | None = None,
    owner_run_id: str | None = None,
    retained_evidence_paths: set[pathlib.Path] | None = None,
) -> dict[str, Any]:
    """Safely, idempotently, and non-destructively remove only explicitly owned temp artifacts.

    Refuses symlinks, candidate repo paths, paths outside allowed_temp_roots,
    protected review evidence, and any directory or file (including .tmp) lacking
    valid matching ownership metadata.
    """
    if not allowed_temp_roots:
        raise CleanupError("cleanup requires explicit allowed_temp_roots")
    resolved_roots: list[pathlib.Path] = []
    for root in allowed_temp_roots:
        _reject_symlink_path(root, label="allowed_temp_root")
        resolved_roots.append(root.resolve())

    resolved_repo = None
    if repo is not None:
        _reject_symlink_path(repo, label="repo")
        resolved_repo = repo.resolve(strict=True)

    retained = {p.resolve() for p in (retained_evidence_paths or set())}
    removed: list[str] = []
    already_absent: list[str] = []
    preserved_evidence: list[str] = []

    for raw_target in owned_paths:
        if raw_target.is_symlink():
            raise CleanupError(f"Refusing to remove symlink target: {raw_target}")
        for parent in raw_target.parents:
            if parent.is_symlink():
                raise CleanupError(f"Refusing cleanup through symlinked parent: {parent}")

        if not raw_target.exists():
            already_absent.append(str(raw_target))
            continue

        target = raw_target.resolve(strict=True)
        if resolved_repo is not None and (target == resolved_repo or target.is_relative_to(resolved_repo)):
            raise CleanupError(f"Refusing cleanup inside candidate repository: {target}")
        if not any(target == r or target.is_relative_to(r) for r in resolved_roots):
            raise CleanupError(f"Refusing cleanup outside allowed_temp_roots: {target}")
        if target in resolved_roots:
            raise CleanupError(f"Refusing cleanup of temp root itself: {target}")
        if target in retained or target.name in PROTECTED_EVIDENCE_NAMES:
            raise CleanupError(f"Refusing cleanup of required review evidence: {target.name}")

        if target.is_dir():
            _assert_no_nested_symlinks(target)
            _validate_owner_marker(
                target / OWNER_MARKER_NAME,
                target=target,
                owner_issue=owner_issue,
                owner_run_id=owner_run_id,
            )
            for root_dir, _, files in os.walk(target, followlinks=False):
                for fname in files:
                    fpath = (pathlib.Path(root_dir) / fname).resolve()
                    if fpath in retained or fname in PROTECTED_EVIDENCE_NAMES:
                        raise CleanupError(f"Refusing cleanup containing protected evidence {fname}")
            shutil.rmtree(target)
            removed.append(str(target))
        elif target.is_file():
            if target.name == OWNER_MARKER_NAME:
                raise CleanupError(f"Refusing standalone deletion of ownership marker: {target}")
            if target.parent in resolved_roots:
                raise CleanupError(f"Refusing cleanup of file directly under temp root without owned subdir: {target}")
            _validate_owner_marker(
                target.parent / OWNER_MARKER_NAME,
                target=target,
                owner_issue=owner_issue,
                owner_run_id=owner_run_id,
            )
            target.unlink()
            removed.append(str(target))
        else:
            raise CleanupError(f"Refusing cleanup of non-regular path: {target}")

    for item in sorted(retained):
        if item.exists():
            preserved_evidence.append(str(item))

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "CLEANED",
        "removed": removed,
        "already_absent": already_absent,
        "preserved_evidence": preserved_evidence,
    }


def evaluate_fresh_session(
    *,
    answers: dict[str, str],
    expected_resume: dict[str, Any],
) -> dict[str, Any]:
    """Grade Fresh Session Test 5/5 under frozen HARNESS_SPEC.md §7.2 criteria."""
    checks: dict[str, dict[str, Any]] = {}

    sys_text = str(answers.get("system", "")).lower()
    checks["1_system"] = {
        "passed": (
            ("lora" in sys_text and "p2p" in sys_text)
            and ("cad" in sys_text or "csma" in sys_text or "adr-0004" in sys_text or "0004" in sys_text)
            and ("agents.md" in sys_text or "0004-pure-cad-csma-ca-mac.md" in sys_text)
        ),
        "detail": "Must identify LoRa P2P Event-Only MVP, CAD/CSMA-CA (ADR-0004), and source path.",
    }

    org_text = str(answers.get("organization", "")).lower()
    checks["2_organization"] = {
        "passed": (
            "firmware" in org_text
            and ("backend-go" in org_text or "backend" in org_text)
            and ("scripts/agent_harness" in org_text or "contracts" in org_text)
        ),
        "detail": "Must identify repo domains (firmware, backend-go, clients/contracts/agent_harness).",
    }

    start_text = str(answers.get("startup", "")).lower()
    checks["3_startup"] = {
        "passed": (
            ("agent_context.py" in start_text or "setup_harness.sh" in start_text or "harness_doctor.py" in start_text)
            and ("session-start" in start_text or "p1/cli.py resume" in start_text or "resume" in start_text)
        ),
        "detail": "Must identify G0/bootstrap and session-start/resume startup commands.",
    }

    ver_text = str(answers.get("verification", "")).lower()
    checks["4_verification"] = {
        "passed": (
            ("check.py" in ver_text or "quality_gates.py" in ver_text or "pr_review.py" in ver_text)
            and ("not_verified" in ver_text or "hil" in ver_text or "rf" in ver_text)
        ),
        "detail": "Must identify deterministic check/gate commands and separate NOT_VERIFIED boundary.",
    }

    state_text = str(answers.get("current_state_and_next_action", "")).lower()
    expected_issue = str(expected_resume.get("issue", ""))
    expected_branch = str(expected_resume.get("branch", "")).lower()
    expected_sha_prefix = str(expected_resume.get("source_sha", ""))[:8].lower()
    expected_next = str(expected_resume.get("next_action", "")).lower()
    expected_blocker = str(expected_resume.get("blocker", "")).lower()
    next_tokens = [tok for tok in re.findall(r"[a-z0-9_.-]{4,}", expected_next)][:4]
    state_ok = (
        bool(expected_issue)
        and expected_issue in state_text
        and (not expected_branch or expected_branch in state_text)
        and (not expected_sha_prefix or expected_sha_prefix in state_text)
        and (not next_tokens or any(tok in state_text for tok in next_tokens))
        and (not expected_blocker or expected_blocker[:12] in state_text or "block" in state_text)
    )
    checks["5_current_state_and_next_action"] = {
        "passed": state_ok,
        "detail": "Must identify exact Issue, branch, revision, blocker, and safe next_action from durable handoff.",
    }

    score = sum(1 for item in checks.values() if item["passed"])
    return {
        "schema_version": SCHEMA_VERSION,
        "score": score,
        "max_score": 5,
        "passed": score == 5,
        "checks": checks,
    }


def build_fresh_session_bundle(
    *,
    issue: int,
    repo: pathlib.Path,
    state_db: pathlib.Path | None = None,
    feature_file: pathlib.Path | None = None,
    offline: bool = False,
) -> dict[str, Any]:
    """Build a zero-chat durable handoff bundle for an independent fresh session."""
    from feature_state import session_start

    resumed = session_start(
        issue=issue,
        repo=repo,
        state_db=state_db,
        feature_file=feature_file,
        offline=offline,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "repo": str(repo.resolve()),
        "issue": issue,
        "resume_snapshot": redact_data(resumed),
        "authoritative_files": [
            "AGENTS.md",
            "docs/development/harness-fast-lane.md",
            "docs/development/harness-quality-gates.md",
            "docs/adr/0004-pure-cad-csma-ca-mac.md",
        ],
    }


def _git(repo: pathlib.Path, *args: str) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
        timeout=30,
    )
    return p.stdout.strip()


def run_golden_journey(
    *,
    source_repo: pathlib.Path,
    issue: int = 433,
) -> dict[str, Any]:
    """Execute a repeatable disposable golden journey with controlled failure injection & repair."""
    from check import freeze_checks, run_checks
    from feature_state import (
        activate_unit,
        compute_verification_sha256,
        create_feature_doc,
        session_checkpoint,
        session_start,
        verify_host_gate_evidence,
        verify_unit_passing,
    )

    src_root = _reject_symlink_path(source_repo, label="source_repo").resolve(strict=True)
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="lora-p06-journey-")).resolve()
    prev_path = os.environ.get("PATH")
    prev_gh_cfg = os.environ.get("GH_CONFIG_DIR")
    try:
        # Provide hermetic runner prerequisites outside cand when executing on headless CI runners
        # without interactive AI CLIs or user GitHub auth config, without weakening harness_doctor gates.
        if not shutil.which("codex") and not shutil.which("agy"):
            fixture_bin = temp_root / "fixture_bin"
            fixture_bin.mkdir(mode=0o700, parents=True)
            stub_codex = fixture_bin / "codex"
            stub_codex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub_codex.chmod(0o700)
            os.environ["PATH"] = f"{fixture_bin}{os.pathsep}{prev_path or ''}"

        gh_cfg_base = (
            pathlib.Path(prev_gh_cfg).expanduser()
            if prev_gh_cfg
            else pathlib.Path.home() / ".config" / "gh"
        )
        if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or (gh_cfg_base / "hosts.yml").is_file()):
            fixture_gh = temp_root / "fixture_gh"
            fixture_gh.mkdir(mode=0o700, parents=True)
            (fixture_gh / "hosts.yml").write_text("github.com:\n    user: fixture-runner\n", encoding="utf-8")
            os.environ["GH_CONFIG_DIR"] = str(fixture_gh)

        cand = temp_root / "candidate"
        cand.mkdir(parents=True)
        _git(cand, "init", "-q")
        _git(cand, "config", "user.name", "Harness Golden Journey")
        _git(cand, "config", "user.email", "harness@example.invalid")

        # Populate real repository foundation & harness artifacts from source_repo without touching source_repo.
        copy_paths = (
            ".gitignore",
            "AGENTS.md",
            ".github/CODEOWNERS",
            ".github/pull_request_template.md",
            ".github/ISSUE_TEMPLATE/embedded_task.yml",
            ".github/ISSUE_TEMPLATE/backend_task.yml",
            ".github/ISSUE_TEMPLATE/frontend_task.yml",
            ".github/ISSUE_TEMPLATE/research_task.yml",
            ".github/ISSUE_TEMPLATE/bug_report.yml",
            ".github/workflows/ci-backend.yml",
            ".agents/agents/harness-coordinator.md",
            "firmware/esp-idf-version.txt",
            "firmware/gateway_master/CMakeLists.txt",
            "firmware/sensor_node/CMakeLists.txt",
            ".go-version",
            "backend-go/go.mod",
            "deploy/compose.yaml",
            "contracts/radio-mac/specification.md",
            "contracts/mqtt/topics.md",
            "contracts/api/openapi.yaml",
            "docs/architecture/system-overview.md",
            "docs/requirements/requirements.md",
            "docs/verification/acceptance-gates.md",
            "docs/development/task-breakdown-readiness.md",
            "scripts/setup_project_gate.sh",
            "scripts/verify_structure.py",
            "scripts/harness_doctor.py",
            "scripts/agent_harness/dependency_checks.py",
            "scripts/agent_harness/adapters/audit.schema.json",
            "docs/development/harness-fast-lane.md",
            "docs/development/harness-quality-gates.md",
            "docs/development/AI_TASK_START_PROTOCOL.md",
            "docs/development/agent-harness-firmware.md",
            "docs/development/agy-supervised-pilot.md",
            "docs/development/c-clean-code-refactoring-standard.md",
            "docs/development/ccars-graph-first-adoption.md",
            "docs/development/firmware/C_CODING_STANDARD_V2.md",
            "docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md",
            "docs/adr/0004-pure-cad-csma-ca-mac.md",
        )
        for rel in copy_paths:
            src_file = src_root / rel
            if src_file.is_file():
                dst_file = cand / rel
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)

        (cand / "tests/agent_harness").mkdir(parents=True, exist_ok=True)
        (cand / "tests/agent_harness/__init__.py").write_text("", encoding="utf-8")
        for d_rel in (
            "firmware/components/sx1276_driver",
            "firmware/components/lora_mac",
            "firmware/components/airtime_policy",
            "clients",
        ):
            (cand / d_rel).mkdir(parents=True, exist_ok=True)
            (cand / d_rel / ".keep").write_text("ok\n", encoding="utf-8")
        (cand / "README.md").write_text("# Golden Journey Disposable Repo\n", encoding="utf-8")

        _git(cand, "add", "-A")
        _git(cand, "commit", "-qm", "baseline")
        base_sha = _git(cand, "rev-parse", "HEAD")
        branch = f"feature/{issue}-golden-journey"
        _git(cand, "checkout", "-qb", branch)

        # Create a small in-scope Python module under scripts/ that we will verify, inject failure into, and repair.
        target_rel = "scripts/verify_structure.py"
        original_script = (cand / target_rel).read_text(encoding="utf-8")

        host_root = temp_root / "host_state"
        host_root.mkdir(mode=0o700)
        journal_path = host_root / "state.sqlite"
        ev_before = host_root / "ev_before"
        ev_fail = host_root / "ev_fail"
        ev_after = host_root / "ev_after"
        trusted_defs_path = host_root / "trusted_defs.json"
        frozen_plan_path = host_root / "frozen_plan.json"

        verification_def = {
            "criteria": ["Repository structure check passes without errors"],
            "commands": ["python3 scripts/verify_structure.py"],
        }
        ver_sha = compute_verification_sha256(verification_def)
        trusted_defs_path.write_text(
            json.dumps(
                {
                    "units": [
                        {"id": "U1", "verification": verification_def, "definition_sha256": ver_sha}
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        unit = {
            "id": "U1",
            "behavior": "Verify repository structure and recover cleanly from failure injection",
            "dependencies": [],
            "scope": [target_rel],
            "verification": verification_def,
        }
        doc = create_feature_doc(
            issue,
            units=[unit],
            title="Golden Journey P06",
            issue_sha256=digest(b"golden-journey"),
            approved_scope=(target_rel,),
            base_sha=base_sha,
            head_sha=base_sha,
            branch=branch,
            candidate_sha256=digest(b"init"),
        )
        doc = activate_unit(doc, "U1", actor="coordinator")
        with Journal(journal_path) as journal:
            journal.save_feature_snapshot(
                issue=issue,
                expected_revision=None,
                revision=doc["revision"],
                doc_json=json.dumps(doc, sort_keys=True),
                units=doc["units"],
                actor="coordinator",
                expected_branch=branch,
            )

        freeze_checks(cand, allowed_paths=(target_rel,), base_sha=base_sha, profile="quick", out_path=frozen_plan_path)

        # 1. Baseline PASS
        res_before = run_checks(
            cand,
            base_sha=base_sha,
            profile="quick",
            evidence_dir=ev_before,
            frozen_plan_path=frozen_plan_path,
            verification_sha256=ver_sha,
        )
        ingest_checks_summary(ev_before, journal_path=journal_path, issue=issue, unit_id="U1", run_id="golden-1-before")

        # 2. Controlled Failure Injection (syntax/exit failure + synthetic credential inside output check)
        (cand / target_rel).write_text(
            "import sys\nprint('token=ghp_1234567890abcdef1234567890abcdef1234')\nsys.exit(1)\n",
            encoding="utf-8",
        )
        res_fail = run_checks(
            cand,
            base_sha=base_sha,
            profile="quick",
            evidence_dir=ev_fail,
            frozen_plan_path=frozen_plan_path,
            verification_sha256=ver_sha,
        )
        ingest_checks_summary(ev_fail, journal_path=journal_path, issue=issue, unit_id="U1", run_id="golden-2-injected")
        diagnosis = diagnose_failures(journal_path, issue=issue, run_id="golden-2-injected")

        # Verify no raw synthetic token leaked into SQLite signals or persisted failure logs
        fail_log_text = (ev_fail / "check_verify-structure.log").read_text(encoding="utf-8")
        raw_token = "ghp_1234567890abcdef1234567890abcdef1234"
        secret_leaked = raw_token in fail_log_text or any(
            raw_token in json.dumps(s) for s in query_signals(journal_path, issue=issue)
        )

        # 3. Scoped repair & rerun same workload
        (cand / target_rel).write_text(original_script + "\n# P06 golden repair verified\n", encoding="utf-8")
        res_after = run_checks(
            cand,
            base_sha=base_sha,
            profile="quick",
            evidence_dir=ev_after,
            frozen_plan_path=frozen_plan_path,
            verification_sha256=ver_sha,
        )
        ingest_checks_summary(ev_after, journal_path=journal_path, issue=issue, unit_id="U1", run_id="golden-3-repaired")

        # 4. Sync candidate_sha256 for repaired active unit & verify via Host proof + checkpoint
        with Journal(journal_path) as journal:
            snap = journal.get_feature_snapshot(issue)
            assert snap is not None
            cur_doc = snap["doc"]
            cur_doc["git"]["candidate_sha256"] = res_after["candidate_sha256"]
            cur_doc["revision"] += 1
            journal.save_feature_snapshot(
                issue=issue,
                expected_revision=snap["revision"],
                revision=cur_doc["revision"],
                doc_json=json.dumps(cur_doc, sort_keys=True),
                units=cur_doc["units"],
                actor="coordinator",
                expected_branch=branch,
            )
            snap = journal.get_feature_snapshot(issue)
            assert snap is not None
            cur_doc = snap["doc"]
            proof = verify_host_gate_evidence(
                cur_doc,
                "U1",
                repo=cand,
                base_sha=base_sha,
                evidence_dir=ev_after,
                manifest_name="manifest.json",
                trusted_definitions=trusted_defs_path,
            )
            passed_doc = verify_unit_passing(
                cur_doc,
                "U1",
                proof=proof,
                expected_revision=snap["revision"],
                trusted_definitions=trusted_defs_path,
                repo=cand,
            )
            journal.save_feature_snapshot(
                issue=issue,
                expected_revision=snap["revision"],
                revision=passed_doc["revision"],
                doc_json=json.dumps(passed_doc, sort_keys=True),
                units=passed_doc["units"],
                actor="host_verifier",
                host_proofs={"U1": proof},
                expected_branch=branch,
            )

        ckpt = session_checkpoint(
            issue=issue,
            repo=cand,
            state_db=journal_path,
            next_action="Run fresh-session resume and open Draft PR for human review",
            base_sha=base_sha,
        )
        resumed = session_start(
            issue=issue,
            repo=cand,
            state_db=journal_path,
            offline=True,
            issue_data={"title": "Golden Journey P06", "body": f"- `{target_rel}`", "scope": (target_rel,), "issue_sha256": digest(b"golden-journey")},
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "PASS" if (res_before["status"] == "PASS" and res_fail["status"] == "FAIL" and res_after["status"] == "PASS" and not secret_leaked and diagnosis["failure_count"] >= 1) else "FAIL",
            "before_status": res_before["status"],
            "injected_failure_status": res_fail["status"],
            "diagnosis_top": diagnosis["latest_failure"],
            "after_repair_status": res_after["status"],
            "secret_leaked": secret_leaked,
            "checkpoint_id": ckpt["checkpoint_id"],
            "resumed_status": resumed["status"],
            "resumed_units": resumed["units"],
            "signals_recorded": len(query_signals(journal_path, issue=issue)),
            "hil_rf": "NOT_VERIFIED",
        }
    finally:
        if prev_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = prev_path
        if prev_gh_cfg is None:
            os.environ.pop("GH_CONFIG_DIR", None)
        else:
            os.environ["GH_CONFIG_DIR"] = prev_gh_cfg
        shutil.rmtree(temp_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P06 Observability, Diagnostics, Cleanup & Handoff CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_rec = sub.add_parser("record-checks", help="Ingest check.py evidence_dir into Journal signals")
    p_rec.add_argument("--evidence-dir", type=pathlib.Path, required=True)
    p_rec.add_argument("--journal", type=pathlib.Path, required=True)
    p_rec.add_argument("--issue", type=int, default=None)
    p_rec.add_argument("--unit-id", default=None)
    p_rec.add_argument("--run-id", default=None)

    p_pr = sub.add_parser("record-pr-review", help="Ingest pr_review.py JSON output into Journal signals")
    p_pr.add_argument("--report", type=pathlib.Path, required=True)
    p_pr.add_argument("--journal", type=pathlib.Path, required=True)
    p_pr.add_argument("--issue", type=int, default=None)
    p_pr.add_argument("--run-id", default=None)

    p_sig = sub.add_parser("record-signal", help="Record a redacted process or runtime signal")
    p_sig.add_argument("--journal", type=pathlib.Path, required=True)
    p_sig.add_argument("--signal-type", choices=("process", "runtime"), default="process")
    p_sig.add_argument("--category", required=True)
    p_sig.add_argument("--domain", required=True)
    p_sig.add_argument("--status", required=True)
    p_sig.add_argument("--issue", type=int, default=None)
    p_sig.add_argument("--unit-id", default=None)
    p_sig.add_argument("--run-id", default=None)
    p_sig.add_argument("--check-id", default="")
    p_sig.add_argument("--exit-code", type=int, default=None)
    p_sig.add_argument("--finding", default="")
    p_sig.add_argument("--excerpt", default="")
    p_sig.add_argument("--unplanned", action="store_true", help="Mark signal as planned/unavailable (captured=false)")

    p_q = sub.add_parser("query", help="Query bounded redacted signals and diagnose failures")
    p_q.add_argument("--journal", type=pathlib.Path, required=True)
    p_q.add_argument("--issue", type=int, default=None)
    p_q.add_argument("--run-id", default=None)
    p_q.add_argument("--unit-id", default=None)
    p_q.add_argument("--domain", default=None)
    p_q.add_argument("--status", default=None)
    p_q.add_argument("--signal-type", choices=("process", "runtime"), default=None)
    p_q.add_argument("--limit", type=int, default=50)
    p_q.add_argument("--diagnose", action="store_true")

    p_map = sub.add_parser("runtime-map", help="Report captured vs unavailable/planned runtime & process signals")
    p_map.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_map.add_argument("--journal", type=pathlib.Path, default=None)
    p_map.add_argument("--evidence-dir", type=pathlib.Path, default=None)
    p_map.add_argument("--issue", type=int, default=None)

    p_cln = sub.add_parser("cleanup", help="Safely and idempotently clean explicitly owned temporary artifacts")
    p_cln.add_argument("--path", type=pathlib.Path, action="append", required=True)
    p_cln.add_argument("--allowed-root", type=pathlib.Path, action="append", required=True)
    p_cln.add_argument("--repo", type=pathlib.Path, default=None)
    p_cln.add_argument("--issue", type=int, default=None)
    p_cln.add_argument("--run-id", default=None)

    p_gj = sub.add_parser("golden-journey", help="Run repeatable disposable golden journey & failure injection")
    p_gj.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_gj.add_argument("--issue", type=int, default=433)

    p_fs = sub.add_parser("fresh-session-eval", help="Build or evaluate a 5/5 Fresh Session handoff bundle")
    p_fs.add_argument("--issue", type=int, required=True)
    p_fs.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_fs.add_argument("--journal", type=pathlib.Path, default=None)
    p_fs.add_argument("--feature-file", type=pathlib.Path, default=None)
    p_fs.add_argument("--answers-file", type=pathlib.Path, default=None)
    p_fs.add_argument("--offline", action="store_true")

    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        if args.command == "record-checks":
            out = ingest_checks_summary(
                args.evidence_dir,
                journal_path=args.journal,
                issue=args.issue,
                unit_id=args.unit_id,
                run_id=args.run_id,
            )
            print(json.dumps({"status": "RECORDED", "signals": out}, indent=2))
            return 0
        if args.command == "record-pr-review":
            out = ingest_pr_review_report(
                args.report,
                journal_path=args.journal,
                issue=args.issue,
                run_id=args.run_id,
            )
            print(json.dumps({"status": "RECORDED", "signals": out}, indent=2))
            return 0
        if args.command == "record-signal":
            out = record_process_signal(
                journal_path=args.journal,
                signal_type=args.signal_type,
                category=args.category,
                owning_domain=args.domain,
                status=args.status,
                captured=not args.unplanned,
                issue=args.issue,
                unit_id=args.unit_id,
                run_id=args.run_id,
                check_id=args.check_id,
                exit_code=args.exit_code,
                finding=args.finding,
                excerpt=args.excerpt,
            )
            print(json.dumps(out, indent=2))
            return 0
        if args.command == "query":
            if args.diagnose:
                out = diagnose_failures(args.journal, issue=args.issue, run_id=args.run_id, limit=args.limit)
            else:
                sigs = query_signals(
                    args.journal,
                    issue=args.issue,
                    run_id=args.run_id,
                    unit_id=args.unit_id,
                    owning_domain=args.domain,
                    status=args.status,
                    signal_type=args.signal_type,
                    limit=args.limit,
                )
                out = {"count": len(sigs), "signals": sigs}
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0
        if args.command == "runtime-map":
            out = collect_runtime_signal_map(
                repo=args.repo,
                journal_path=args.journal,
                evidence_dir=args.evidence_dir,
                issue=args.issue,
            )
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0
        if args.command == "cleanup":
            out = cleanup_owned_artifacts(
                args.path,
                allowed_temp_roots=args.allowed_root,
                repo=args.repo,
                owner_issue=args.issue,
                owner_run_id=args.run_id,
            )
            print(json.dumps(out, indent=2))
            return 0
        if args.command == "golden-journey":
            out = run_golden_journey(source_repo=args.repo, issue=args.issue)
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 0 if out["status"] == "PASS" else 1
        if args.command == "fresh-session-eval":
            bundle = build_fresh_session_bundle(
                issue=args.issue,
                repo=args.repo,
                state_db=args.journal,
                feature_file=args.feature_file,
                offline=args.offline,
            )
            if args.answers_file is not None:
                answers = _safe_read_json(args.answers_file)
                if not isinstance(answers, dict):
                    raise ObservabilityError("answers_file must be a JSON object")
                ev = evaluate_fresh_session(answers=answers, expected_resume=bundle["resume_snapshot"])
                print(json.dumps({"bundle": bundle, "evaluation": ev}, indent=2, ensure_ascii=False))
                return 0 if ev["passed"] else 1
            print(json.dumps(bundle, indent=2, ensure_ascii=False))
            return 0
    except (ObservabilityError, StateConflict, OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": redact_text(str(exc), max_bytes=400)[0]}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
