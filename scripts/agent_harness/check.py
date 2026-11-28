#!/usr/bin/env python3
"""Unified OD-03 Check Runner & Impact-to-Check Matrix (H2-FBK-01, H2-FBK-02, FBK-05, OD-07).

Freezes required checks from approved scope before edits, recomputes on the full diff,
executes actual commands (nonzero on failure or missing prerequisites, never fabricated PASS),
and emits Host-collected receipts compatible with quality_gates.py and feature_state.py.
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
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

try:
    from .dependency_checks import domains_for_paths
    from .observability import contains_secret, ingest_checks_summary, redact_text
    from .quality_gates import digest, evaluate as evaluate_quality_gates, inventory, route, secret_line
    from .scope import parse_allowed_paths
except ImportError:
    from dependency_checks import domains_for_paths
    from observability import contains_secret, ingest_checks_summary, redact_text
    from quality_gates import digest, evaluate as evaluate_quality_gates, inventory, route, secret_line
    from scope import parse_allowed_paths

PROFILES = ("quick", "software", "integration", "bench")
LEVEL_ORDER = {"quick": 0, "software": 1, "integration": 2, "bench": 3}
MAX_LOG_BYTES = 2_000_000


@dataclass(frozen=True)
class CheckSpec:
    check_id: str
    domain: str
    level: str
    command: list[str]
    cwd_rel: str
    gate_rule_id: str
    description: str
    prerequisite: str = ""

    def command_sha256(self) -> str:
        return digest(json.dumps(self.command).encode("utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "command_sha256": self.command_sha256(),
        }


def _has_harness_impact(paths: list[str]) -> bool:
    for p in paths:
        low = p.lower()
        if (
            low == "agents.md"
            or low.startswith(("scripts/agent_harness/", "tests/agent_harness/", ".agents/", ".agent-harness/", ".github/workflows/"))
            or low in (
                "docs/development/harness-quality-gates.md",
                "docs/development/harness-pr-review.md",
                "docs/development/harness-fast-lane.md",
            )
            or low in ("scripts/verify_structure.py", "scripts/harness_doctor.py")
        ):
            return True
    return False


def _has_domain(paths: list[str], prefix: str, exact: tuple[str, ...] = ()) -> bool:
    for p in paths:
        low = p.lower()
        if low.startswith(prefix) or low in exact:
            return True
    return False


def _has_advanced_pack_impact(paths: list[str]) -> bool:
    for p in paths:
        low = p.lower()
        if (
            low
            in (
                "docs/harness/advanced_pack.md",
                "docs/quality_score.md",
                "docs/generated/db-schema.md",
                "docs/harness/harness_spec.md",
                "docs/harness/harness_master_plan.md",
                "scripts/agent_harness/advanced_pack.py",
                "tests/agent_harness/test_advanced_pack.py",
                "backend-go/dockerfile",
            )
            or low.startswith("backend-go/migrations/")
        ):
            return True
    return False


def plan_checks(
    paths: list[str] | tuple[str, ...],
    *,
    profile: str = "software",
    include_harness_behavior_smoke: bool = True,
) -> list[CheckSpec]:
    """Compute deterministic required checks from paths + profile via the OD-03 matrix."""
    if profile not in PROFILES:
        raise ValueError(f"Unsupported check profile: {profile!r}")
    norm_paths = sorted({p.strip() for p in paths if p.strip()})
    max_level = LEVEL_ORDER[profile]
    specs: dict[str, CheckSpec] = {}

    def add(spec: CheckSpec) -> None:
        if LEVEL_ORDER[spec.level] <= max_level:
            specs.setdefault(spec.check_id, spec)

    # Always run lightweight monorepo structure check.
    add(
        CheckSpec(
            check_id="verify-structure",
            domain="foundation",
            level="quick",
            command=["python3", "scripts/verify_structure.py"],
            cwd_rel=".",
            gate_rule_id="TOOLING-CHECK",
            description="Static monorepo foundation and toolchain pin invariant check",
        )
    )

    harness_hit = _has_harness_impact(norm_paths)
    advanced_pack_hit = _has_advanced_pack_impact(norm_paths)
    fw_hit = _has_domain(norm_paths, "firmware/", ("tests/unit/",)) or _has_domain(norm_paths, "tests/unit/")
    go_hit = _has_domain(norm_paths, "backend-go/", (".go-version",))
    cli_hit = _has_domain(norm_paths, "clients/")
    ctr_hit = _has_domain(norm_paths, "contracts/", ("tests/contract/",)) or _has_domain(norm_paths, "tests/contract/")
    integ_hit = _has_domain(norm_paths, "deploy/") or _has_domain(norm_paths, "tests/integration/") or any(
        p.lower().startswith(".env") or "compose" in p.lower() for p in norm_paths
    )
    hil_hit = _has_domain(norm_paths, "tests/hil/") or _has_domain(norm_paths, "hardware/")

    if advanced_pack_hit:
        add(
            CheckSpec(
                check_id="advanced-pack-freshness",
                domain="harness",
                level="quick",
                command=["python3", "scripts/agent_harness/advanced_pack.py", "verify", "--repo", ".", "--json"],
                cwd_rel=".",
                gate_rule_id="TOOLING-CHECK",
                description="Verify Advanced Pack SPEC §5.2 links, QUALITY_SCORE, and DB schema freshness",
            )
        )

    if harness_hit:
        add(
            CheckSpec(
                check_id="harness-compile",
                domain="harness",
                level="quick",
                command=["python3", "-m", "compileall", "-q", "scripts/agent_harness", "tests/agent_harness"],
                cwd_rel=".",
                gate_rule_id="TOOLING-CHECK",
                description="Compile Python harness and tests (ci-agent-harness.yml)",
            )
        )
        add(
            CheckSpec(
                check_id="audit-schema-json",
                domain="harness",
                level="quick",
                command=["python3", "-m", "json.tool", "scripts/agent_harness/adapters/audit.schema.json"],
                cwd_rel=".",
                gate_rule_id="TOOLING-CHECK",
                description="Validate Auditor JSON schema syntax (ci-agent-harness.yml)",
            )
        )
        add(
            CheckSpec(
                check_id="dependency-boundaries",
                domain="harness",
                level="quick",
                command=["python3", "scripts/agent_harness/dependency_checks.py", "--repo", ".", "--json"],
                cwd_rel=".",
                gate_rule_id="TOOLING-CHECK",
                description="Verify approved dependency boundaries across firmware, Go, clients, contracts",
            )
        )
        if include_harness_behavior_smoke:
            add(
                CheckSpec(
                    check_id="harness-doctor-smoke",
                    domain="harness",
                    level="quick",
                    command=["python3", "scripts/harness_doctor.py", "--profile", "core", "--json"],
                    cwd_rel=".",
                    gate_rule_id="TOOLING-CHECK",
                    description="Read-only startup/health diagnostics smoke (FBK-05)",
                )
            )
        add(
            CheckSpec(
                check_id="harness-unit",
                domain="harness",
                level="software",
                command=["python3", "-m", "unittest", "discover", "-s", "tests/agent_harness", "-v"],
                cwd_rel=".",
                gate_rule_id="TOOLING-CHECK",
                description="Full agent_harness unit and regression suite (ci-agent-harness.yml)",
            )
        )
        add(
            CheckSpec(
                check_id="harness-security-gates",
                domain="harness",
                level="software",
                command=[
                    "python3",
                    "-m",
                    "unittest",
                    "tests/agent_harness/test_quality_gates.py",
                    "tests/agent_harness/test_standards_policy.py",
                    "-v",
                ],
                cwd_rel=".",
                gate_rule_id="SECURITY-CHECK",
                description="Verify fail-closed security, secret-scan, and standards policy gates",
            )
        )

    dep_domains = domains_for_paths(norm_paths)
    if not harness_hit and dep_domains:
        for dom in dep_domains:
            gate = {
                "firmware": "FIRMWARE-CHECK",
                "backend-go": "BACKEND-CHECK",
                "clients": "TOOLING-CHECK",
                "contracts": "SECURITY-CHECK",
            }[dom]
            add(
                CheckSpec(
                    check_id=f"dependency-boundaries-{dom}",
                    domain=dom,
                    level="quick",
                    command=["python3", "scripts/agent_harness/dependency_checks.py", "--repo", ".", "--domain", dom, "--json"],
                    cwd_rel=".",
                    gate_rule_id=gate,
                    description=f"Enforce structural dependency boundaries for {dom}",
                )
            )

    if go_hit:
        add(
            CheckSpec(
                check_id="go-format",
                domain="backend-go",
                level="quick",
                command=["gofmt", "-d", "."],
                cwd_rel="backend-go",
                gate_rule_id="BACKEND-CHECK",
                description="Go formatting check (ci-backend.yml)",
                prerequisite="go_toolchain",
            )
        )
        add(
            CheckSpec(
                check_id="go-vet",
                domain="backend-go",
                level="software",
                command=["go", "vet", "./..."],
                cwd_rel="backend-go",
                gate_rule_id="BACKEND-CHECK",
                description="Go static vet check (ci-backend.yml)",
                prerequisite="go_pinned",
            )
        )
        add(
            CheckSpec(
                check_id="go-test",
                domain="backend-go",
                level="software",
                command=["go", "test", "./..."],
                cwd_rel="backend-go",
                gate_rule_id="BACKEND-CHECK",
                description="Go unit test suite (ci-backend.yml)",
                prerequisite="go_pinned",
            )
        )
        add(
            CheckSpec(
                check_id="go-build",
                domain="backend-go",
                level="software",
                command=["go", "build", "./cmd/server"],
                cwd_rel="backend-go",
                gate_rule_id="BACKEND-CHECK",
                description="Go server binary build (ci-backend.yml)",
                prerequisite="go_pinned",
            )
        )

    if fw_hit:
        add(
            CheckSpec(
                check_id="firmware-unit",
                domain="firmware",
                level="software",
                command=["python3", "-m", "unittest", "discover", "-s", "tests/unit", "-v"],
                cwd_rel=".",
                gate_rule_id="FIRMWARE-CHECK",
                description="Firmware C/Python host unit tests",
            )
        )
        add(
            CheckSpec(
                check_id="firmware-gateway-build",
                domain="firmware",
                level="software",
                command=["python3", "scripts/agent_harness/toolchains/check.py", "--target", "gateway_master"],
                cwd_rel=".",
                gate_rule_id="FIRMWARE-CHECK",
                description="ESP-IDF v6.1 gateway_master build (ci-firmware.yml)",
                prerequisite="esp_idf_v6_1",
            )
        )
        add(
            CheckSpec(
                check_id="firmware-sensor-build",
                domain="firmware",
                level="software",
                command=["python3", "scripts/agent_harness/toolchains/check.py", "--target", "sensor_node"],
                cwd_rel=".",
                gate_rule_id="FIRMWARE-CHECK",
                description="ESP-IDF v6.1 sensor_node build (ci-firmware.yml)",
                prerequisite="esp_idf_v6_1",
            )
        )

    if ctr_hit:
        add(
            CheckSpec(
                check_id="contracts-conformance",
                domain="contracts",
                level="software",
                command=["python3", "contracts/tests/check_contracts.py"],
                cwd_rel=".",
                gate_rule_id="SECURITY-CHECK",
                description="Contract schema & OpenAPI conformance (ci-contracts.yml)",
                prerequisite="python_contract_deps",
            )
        )
        add(
            CheckSpec(
                check_id="contracts-unit",
                domain="contracts",
                level="software",
                command=["python3", "-m", "unittest", "discover", "-s", "tests/contract", "-v"],
                cwd_rel=".",
                gate_rule_id="SECURITY-CHECK",
                description="Contract unit test suite",
            )
        )

    if cli_hit:
        add(
            CheckSpec(
                check_id="web-unit",
                domain="clients",
                level="software",
                command=["node", "--test", "--experimental-strip-types", "tests/api_client.test.ts", "tests/integration.test.ts", "tests/rf_quality.test.ts"],
                cwd_rel="clients/web-dashboard",
                gate_rule_id="TOOLING-CHECK",
                description="Web dashboard TypeScript unit tests",
                prerequisite="node_web",
            )
        )
        add(
            CheckSpec(
                check_id="web-lint",
                domain="clients",
                level="software",
                command=["npm", "run", "lint"],
                cwd_rel="clients/web-dashboard",
                gate_rule_id="TOOLING-CHECK",
                description="Web dashboard ESLint",
                prerequisite="node_web",
            )
        )

    if profile == "integration" and (integ_hit or go_hit or _has_domain(norm_paths, "contracts/mqtt/")):
        add(
            CheckSpec(
                check_id="integration-suite",
                domain="integration",
                level="integration",
                command=["python3", "-m", "unittest", "discover", "-s", "tests/integration", "-v"],
                cwd_rel=".",
                gate_rule_id="INFRA-CHECK",
                description="Local PostgreSQL/Mosquitto integration and restart suite",
                prerequisite="docker_infra",
            )
        )

    if profile == "bench" and (hil_hit or fw_hit):
        add(
            CheckSpec(
                check_id="bench-hil-suite",
                domain="bench",
                level="bench",
                command=["python3", "-m", "unittest", "discover", "-s", "tests/hil", "-v"],
                cwd_rel=".",
                gate_rule_id="FIRMWARE-CHECK",
                description="Authorized bench/HIL verification (OD-07)",
                prerequisite="bench_authorized",
            )
        )

    return list(specs.values())


def freeze_checks(
    repo: pathlib.Path,
    *,
    allowed_paths: list[str] | tuple[str, ...],
    base_sha: str,
    profile: str = "software",
    out_path: pathlib.Path | None = None,
) -> dict[str, Any]:
    """Freeze required check definitions from approved scope before edits."""
    root = repo.resolve(strict=True)
    specs = plan_checks(list(allowed_paths), profile=profile)
    plan_payload = {
        "schema_version": "1.0",
        "base_sha": base_sha,
        "profile": profile,
        "allowed_paths": list(allowed_paths),
        "checks": [s.to_dict() for s in specs],
    }
    plan_payload["plan_sha256"] = digest(
        json.dumps(
            {
                "base_sha": base_sha,
                "profile": profile,
                "allowed_paths": list(allowed_paths),
                "checks": plan_payload["checks"],
            },
            sort_keys=True,
        ).encode("utf-8")
    )
    if out_path is not None:
        resolved = out_path.resolve()
        if out_path.is_symlink() or resolved.is_relative_to(root):
            raise ValueError("Frozen check plan must reside outside candidate worktree and not be a symlink")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(plan_payload, indent=2, sort_keys=True), encoding="utf-8")
    return plan_payload


def _check_prerequisite(
    prereq: str,
    repo: pathlib.Path,
    *,
    allow_bench: bool = False,
    bench_auth: pathlib.Path | None = None,
) -> tuple[bool, str, str]:
    """Verify required toolchain/environment before claiming execution."""
    if not prereq:
        return True, f"Python {sys.version.split()[0]}", ""

    if prereq in ("go_toolchain", "go_pinned"):
        go_bin = shutil.which("go")
        if not go_bin:
            return False, "go=MISSING", "Go compiler not found on PATH"
        pin_file = repo / ".go-version"
        expected = pin_file.read_text(encoding="utf-8").strip() if pin_file.is_file() else ""
        p = subprocess.run([go_bin, "env", "GOVERSION"], capture_output=True, text=True, timeout=15, check=False)
        actual = p.stdout.strip()
        if prereq == "go_pinned" and expected and actual != f"go{expected}":
            return False, f"go={actual or 'UNKNOWN'}", f"Pinned Go go{expected} required, found {actual}"
        return True, actual or "go", ""

    if prereq == "esp_idf_v6_1":
        docker = shutil.which("docker")
        if not docker:
            return False, "docker=MISSING", "Docker engine required for pinned ESP-IDF v6.1 build"
        return True, "docker+espressif/idf:v6.1", ""

    if prereq == "python_contract_deps":
        p = subprocess.run(
            ["python3", "-c", "import yaml, jsonschema, openapi_spec_validator"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if p.returncode != 0:
            return False, "python-contracts=MISSING", "Missing contract validator deps (pyyaml/jsonschema/openapi-spec-validator)"
        return True, f"Python {sys.version.split()[0]}", ""

    if prereq == "node_web":
        if not shutil.which("node") or not shutil.which("npm"):
            return False, "node=MISSING", "Node/npm not found on PATH"
        if not (repo / "clients" / "web-dashboard" / "node_modules").is_dir():
            return False, "node_modules=MISSING", "clients/web-dashboard/node_modules missing in clean worktree"
        p = subprocess.run(["node", "--version"], capture_output=True, text=True, timeout=10, check=False)
        return True, f"node {p.stdout.strip()}", ""

    if prereq == "docker_infra":
        if not shutil.which("docker"):
            return False, "docker=MISSING", "Docker daemon required for integration profile"
        p = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15, check=False)
        if p.returncode != 0:
            return False, "docker=UNAVAILABLE", "Docker daemon not reachable for integration checks"
        return True, "docker-ready", ""

    if prereq == "bench_authorized":
        if not allow_bench or bench_auth is None:
            return False, "bench=NOT_AUTHORIZED", "HIL/RF bench requires explicit --allow-bench and external --bench-auth receipt"
        if bench_auth.is_symlink() or not bench_auth.is_file():
            return False, "bench=INVALID_AUTH", "External bench authorization file missing or symlink"
        resolved_auth = bench_auth.resolve(strict=True)
        if resolved_auth.is_relative_to(repo.resolve(strict=True)):
            return False, "bench=UNTRUSTED_AUTH", "Bench authorization file must be outside candidate repo"
        auth = json.loads(resolved_auth.read_text(encoding="utf-8"))
        if auth.get("authorized") is not True or auth.get("equipment_available") is not True:
            return False, "bench=NOT_VERIFIED", "Bench equipment unavailable or explicit authorization false"
        return True, str(auth.get("bench_id", "authorized-bench")), ""

    return False, "UNKNOWN_PREREQ", f"Unknown prerequisite {prereq!r}"


def _run_bounded_check(cmd: list[str], cwd: pathlib.Path, timeout: int) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with tempfile.TemporaryFile() as out_f:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            out_f.seek(0)
            raw = out_f.read(MAX_LOG_BYTES)
            text = raw.decode("utf-8", errors="replace")
            return 124, text + f"\n[check.py] Timed out after {timeout}s\n"
        except BaseException:
            if proc.poll() is None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except OSError:
                    pass
                proc.wait()
            raise
        out_f.seek(0)
        raw = out_f.read(MAX_LOG_BYTES + 1)
        truncated = len(raw) > MAX_LOG_BYTES
        if truncated:
            raw = raw[:MAX_LOG_BYTES]
        text = raw.decode("utf-8", errors="replace")
        if truncated:
            text += "\n[check.py] Output truncated at 2MB bound\n"
        return int(proc.returncode), text


def run_checks(
    repo: pathlib.Path,
    *,
    base_sha: str,
    profile: str = "software",
    evidence_dir: pathlib.Path | None = None,
    frozen_plan_path: pathlib.Path | None = None,
    verification_sha256: str | None = None,
    allow_bench: bool = False,
    bench_auth: pathlib.Path | None = None,
    timeout: int = 300,
    run_quality_gates: bool = True,
    journal_path: pathlib.Path | None = None,
    issue: int | None = None,
    unit_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Execute OD-03 impact-routed checks and emit Host-bound receipts."""
    repo_root = repo.resolve(strict=True)
    if repo.is_symlink():
        raise ValueError("Candidate repo must not be a symlink")

    if profile == "bench" and not allow_bench:
        return {
            "status": "NOT_VERIFIED",
            "profile": profile,
            "hil_rf": "NOT_VERIFIED",
            "reason": "Bench/HIL/RF execution requires explicit --allow-bench authorization and equipment verification (OD-07).",
            "results": [],
            "exit_code": 2,
        }

    if evidence_dir is None:
        ev_root = pathlib.Path(tempfile.mkdtemp(prefix="lora-check-ev-")).resolve()
        created_temp_ev = True
    else:
        if evidence_dir.is_symlink():
            raise ValueError("evidence_dir must not be a symlink")
        evidence_dir.mkdir(parents=True, exist_ok=True)
        ev_root = evidence_dir.resolve(strict=True)
        if ev_root.is_relative_to(repo_root):
            raise ValueError("Host evidence_dir must remain outside candidate worktree")
        created_temp_ev = False

    source, secrets = inventory(repo_root, base_sha)
    diff_specs = plan_checks(source["changed_paths"], profile=profile)
    spec_by_id: dict[str, CheckSpec] = {s.check_id: s for s in diff_specs}

    if frozen_plan_path is not None:
        if frozen_plan_path.is_symlink() or not frozen_plan_path.is_file():
            raise ValueError("Frozen plan missing or is a symlink")
        if frozen_plan_path.resolve(strict=True).is_relative_to(repo_root):
            raise ValueError("Frozen plan must reside outside candidate worktree")
        frozen = json.loads(frozen_plan_path.read_text(encoding="utf-8"))
        expected_hash = digest(
            json.dumps(
                {
                    "base_sha": frozen["base_sha"],
                    "profile": frozen["profile"],
                    "allowed_paths": frozen["allowed_paths"],
                    "checks": frozen["checks"],
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        if frozen.get("plan_sha256") != expected_hash:
            raise ValueError("Frozen check plan checksum mismatch")
        if frozen.get("base_sha") != source["base_sha"]:
            raise ValueError("Frozen check plan base_sha mismatch")
        for item in frozen.get("checks", []):
            cid = item["check_id"]
            if cid not in spec_by_id:
                spec_by_id[cid] = CheckSpec(
                    check_id=cid,
                    domain=item["domain"],
                    level=item["level"],
                    command=list(item["command"]),
                    cwd_rel=item["cwd_rel"],
                    gate_rule_id=item["gate_rule_id"],
                    description=item["description"],
                    prerequisite=item.get("prerequisite", ""),
                )

    ordered_specs = list(spec_by_id.values())
    check_results: list[dict[str, Any]] = []
    command_receipts: list[dict[str, Any]] = []
    mandatory_checks: list[dict[str, Any]] = []
    gate_checks_map: dict[str, dict[str, Any]] = {}
    gate_priority: dict[str, int] = {}
    overall_failed = False
    prereq_blocked = False

    def _record_gate(gate_rule_id: str, receipt_obj: dict[str, Any], prio: int) -> None:
        # Precedence: FAIL (3) > NOT_VERIFIED / NOT_RUN / prerequisite_missing (2) > PASS (1)
        prev = gate_priority.get(gate_rule_id, 0)
        if prio > prev or prev == 0:
            gate_checks_map[gate_rule_id] = receipt_obj
            gate_priority[gate_rule_id] = prio

    for spec in ordered_specs:
        prereq_ok, tool_ver, prereq_err = _check_prerequisite(
            spec.prerequisite, repo_root, allow_bench=allow_bench, bench_auth=bench_auth
        )
        log_name = f"check_{spec.check_id}.log"
        log_path = ev_root / log_name
        if not prereq_ok:
            prereq_blocked = True
            msg = f"PREREQUISITE_MISSING ({spec.prerequisite}): {prereq_err}\n"
            log_path.write_text(msg, encoding="utf-8")
            log_bytes = log_path.read_bytes()
            log_sha = digest(log_bytes)
            obs_missing: dict[str, Any] = {
                "checks_complete": False,
                "check_id": spec.check_id,
                "diff_sha256": source["diff_sha256"],
                "prerequisite_missing": spec.prerequisite,
                "reason": prereq_err,
            }
            if verification_sha256:
                obs_missing["verification_sha256"] = verification_sha256
            missing_receipt = {
                "source_sha": source["source_sha"],
                "candidate_sha256": source["candidate_sha256"],
                "diff_sha256": source["diff_sha256"],
                "command": list(spec.command),
                "command_sha256": spec.command_sha256(),
                "exit_code": 2,
                "status": "NOT_VERIFIED",
                "tool_version": tool_ver,
                "receipt_path": log_name,
                "receipt_sha256": log_sha,
                "gate_rule_id": spec.gate_rule_id,
                "observations": obs_missing,
            }
            command_receipts.append(missing_receipt)
            _record_gate(spec.gate_rule_id, missing_receipt, 2)
            mandatory_checks.append(
                {
                    "check_id": spec.check_id,
                    "domain": spec.domain,
                    "level": spec.level,
                    "gate_rule_id": spec.gate_rule_id,
                    "status": "NOT_VERIFIED",
                    "exit_code": 2,
                    "prerequisite": spec.prerequisite,
                    "prerequisite_missing": True,
                    "reason": prereq_err,
                    "source_sha": source["source_sha"],
                    "candidate_sha256": source["candidate_sha256"],
                    "diff_sha256": source["diff_sha256"],
                    "command_sha256": spec.command_sha256(),
                    "receipt_path": log_name,
                    "receipt_sha256": log_sha,
                }
            )
            check_results.append(
                {
                    "check_id": spec.check_id,
                    "domain": spec.domain,
                    "level": spec.level,
                    "status": "NOT_VERIFIED",
                    "exit_code": 2,
                    "tool_version": tool_ver,
                    "receipt_path": log_name,
                    "receipt_sha256": log_sha,
                    "reason": prereq_err,
                }
            )
            continue

        cwd = (repo_root / spec.cwd_rel).resolve()
        if not cwd.is_relative_to(repo_root) or not cwd.is_dir():
            raise ValueError(f"Unsafe or missing cwd for check {spec.check_id}: {spec.cwd_rel}")

        started_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        started = time.monotonic()
        rc, output = _run_bounded_check(spec.command, cwd, timeout)
        duration_s = round(time.monotonic() - started, 3)
        ended_at = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Special case: `gofmt -d .` exits 0 even when formatting diffs exist!
        if spec.check_id == "go-format" and rc == 0 and output.strip():
            rc = 1

        if not output.strip():
            output = f"[check.py] {spec.check_id} exited {rc} in {duration_s}s\n"
        secret_hit = contains_secret(output)
        output, was_redacted, was_truncated = redact_text(output, max_bytes=MAX_LOG_BYTES)
        if secret_hit:
            output = "[check.py] Secret signature detected and redacted; failing check\n" + output
            rc = rc or 1

        log_path.write_text(output, encoding="utf-8")
        log_bytes = log_path.read_bytes()
        log_sha = digest(log_bytes)

        obs: dict[str, Any] = {
            "checks_complete": rc == 0,
            "check_id": spec.check_id,
            "diff_sha256": source["diff_sha256"],
        }
        if verification_sha256:
            obs["verification_sha256"] = verification_sha256

        receipt_status = "PASS" if rc == 0 else "FAIL"
        finding_text = ""
        if rc != 0:
            finding_text, _, _ = redact_text(
                output[-1000:] if len(output) > 1000 else output,
                max_bytes=800,
            )
        receipt = {
            "source_sha": source["source_sha"],
            "candidate_sha256": source["candidate_sha256"],
            "diff_sha256": source["diff_sha256"],
            "command": list(spec.command),
            "command_sha256": spec.command_sha256(),
            "exit_code": rc,
            "status": receipt_status,
            "tool_version": tool_ver,
            "receipt_path": log_name,
            "receipt_sha256": log_sha,
            "gate_rule_id": spec.gate_rule_id,
            "observations": obs,
        }
        command_receipts.append(receipt)

        if rc == 0:
            _record_gate(spec.gate_rule_id, receipt, 1)
        else:
            overall_failed = True
            _record_gate(spec.gate_rule_id, receipt, 3)

        mandatory_checks.append(
            {
                "check_id": spec.check_id,
                "domain": spec.domain,
                "level": spec.level,
                "gate_rule_id": spec.gate_rule_id,
                "status": receipt_status,
                "exit_code": rc,
                "prerequisite": spec.prerequisite,
                "prerequisite_missing": False,
                "source_sha": source["source_sha"],
                "candidate_sha256": source["candidate_sha256"],
                "diff_sha256": source["diff_sha256"],
                "command_sha256": spec.command_sha256(),
                "receipt_path": log_name,
                "receipt_sha256": log_sha,
            }
        )

        check_results.append(
            {
                "check_id": spec.check_id,
                "domain": spec.domain,
                "level": spec.level,
                "status": receipt_status,
                "exit_code": rc,
                "started_at": started_at,
                "ended_at": ended_at,
                "duration_s": duration_s,
                "tool_version": tool_ver,
                "receipt_path": log_name,
                "receipt_sha256": log_sha,
                "redacted": bool(was_redacted or secret_hit),
                "truncated": bool(was_truncated),
                "finding": finding_text,
            }
        )

    manifest_doc = {
        "checks": gate_checks_map,
        "command_receipts": command_receipts,
        "mandatory_checks": mandatory_checks,
        "planned_checks": [s.check_id for s in ordered_specs],
    }
    manifest_path = ev_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_doc, indent=2, sort_keys=True), encoding="utf-8")

    qg_report = None
    if run_quality_gates:
        qg_report = evaluate_quality_gates(repo_root, base_sha, "manifest.json", ev_root)

    # Check if candidate drifted during check execution.
    after_source, _ = inventory(repo_root, base_sha)
    if after_source != source:
        raise ValueError("Candidate source changed during check execution")

    if overall_failed:
        final_status = "FAIL"
        exit_code = 1
    elif prereq_blocked:
        final_status = "NOT_VERIFIED"
        exit_code = 2
    elif qg_report is not None and qg_report.get("auto_check") != "AUTO_CHECK_PASS":
        final_status = "FAIL"
        exit_code = 1
    else:
        final_status = "PASS"
        exit_code = 0

    summary = {
        "schema_version": "1.0",
        "status": final_status,
        "exit_code": exit_code,
        "profile": profile,
        "source_sha": source["source_sha"],
        "base_sha": source["base_sha"],
        "diff_sha256": source["diff_sha256"],
        "candidate_sha256": source["candidate_sha256"],
        "changed_paths": source["changed_paths"],
        "evidence_dir": str(ev_root),
        "manifest_path": str(manifest_path),
        "checks_executed": len(check_results),
        "results": check_results,
        "quality_gates": {
            "auto_check": qg_report.get("auto_check") if qg_report else "NOT_RUN",
            "human_security_review": qg_report.get("human_security_review") if qg_report else "NOT_RUN",
            "risks": qg_report.get("risks", []) if qg_report else [],
            "results": qg_report.get("results", []) if qg_report else [],
        },
        "hil_rf": "NOT_VERIFIED",
        "recorded_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (ev_root / "checks_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    if journal_path is not None:
        if journal_path.is_symlink():
            raise ValueError("journal_path must not be a symlink")
        if journal_path.resolve().is_relative_to(repo_root):
            raise ValueError("Host journal_path must remain outside candidate worktree")
        ingested = ingest_checks_summary(
            ev_root,
            journal_path=journal_path,
            issue=issue,
            unit_id=unit_id,
            run_id=run_id,
        )
        summary["signals_recorded"] = len(ingested)
    if created_temp_ev:
        summary["temporary_evidence_dir"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Unified OD-03 Harness Verification & Check Runner")
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument("--base", default="HEAD")
    parser.add_argument("--profile", choices=PROFILES, default="software")
    parser.add_argument("--evidence-dir", type=pathlib.Path, default=None)
    parser.add_argument("--allowed-path", action="append", default=[])
    parser.add_argument("--issue-body", type=pathlib.Path, default=None)
    parser.add_argument("--freeze-checks", type=pathlib.Path, default=None, help="Write frozen check plan outside repo")
    parser.add_argument("--verify-frozen", type=pathlib.Path, default=None, help="Verify and union frozen check plan")
    parser.add_argument("--verification-sha256", default=None)
    parser.add_argument("--allow-bench", action="store_true")
    parser.add_argument("--bench-auth", type=pathlib.Path, default=None)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--no-quality-gates", action="store_true")
    parser.add_argument("--journal", type=pathlib.Path, default=None, help="Optional external Host SQLite journal for bounded signal logging")
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--unit-id", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        if args.base.startswith("-"):
            raise ValueError("Unsafe base ref")
        repo = args.repo.resolve(strict=True)
        if args.freeze_checks is not None:
            allowed = list(args.allowed_path)
            if args.issue_body is not None:
                allowed.extend(parse_allowed_paths(args.issue_body.read_text(encoding="utf-8")))
            if not allowed:
                raise ValueError("--freeze-checks requires --allowed-path or --issue-body")
            plan = freeze_checks(
                repo,
                allowed_paths=tuple(dict.fromkeys(allowed)),
                base_sha=args.base,
                profile=args.profile,
                out_path=args.freeze_checks,
            )
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 0

        res = run_checks(
            repo,
            base_sha=args.base,
            profile=args.profile,
            evidence_dir=args.evidence_dir,
            frozen_plan_path=args.verify_frozen,
            verification_sha256=args.verification_sha256,
            allow_bench=args.allow_bench,
            bench_auth=args.bench_auth,
            timeout=args.timeout,
            run_quality_gates=not args.no_quality_gates,
            journal_path=args.journal,
            issue=args.issue,
            unit_id=args.unit_id,
            run_id=args.run_id,
        )
        if args.json:
            print(json.dumps(res, indent=2, sort_keys=True))
        else:
            print(f"{res['status']} ({res['profile']}): {res['checks_executed']} check(s) -> {res.get('evidence_dir', 'N/A')}")
            for r in res.get("results", []):
                print(f"  [{r['status']}] {r['check_id']} (exit={r['exit_code']}, tool={r['tool_version']})")
            if res.get("quality_gates"):
                print(f"  quality_gates: {res['quality_gates'].get('auto_check')}")
        return int(res["exit_code"])
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED", "exit_code": 2, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
