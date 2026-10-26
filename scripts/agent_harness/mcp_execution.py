"""Staged deterministic MCP Host execution.

Only fixed commands and versioned Host scripts may run. No provider CLI invocation.
Run state/receipts are persisted OUTSIDE the source/worktree. Fail closed.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

from mcp_host import HarnessMCPHost

_RUN = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_OUTPUT = 300_000
_MAX_SOURCE_FILE = 6_000_000
_MAX_FIRMWARE_FILES = 5000


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    if len(data) > 100_000:
        raise ValueError("Host evidence exceeds size limit")
    tmp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


class MCPExecution:
    def __init__(self, host: HarnessMCPHost | None = None) -> None:
        self.host = host or HarnessMCPHost()
        self.root = self.host.source.parent / ".lora-harness-evidence"

    @staticmethod
    def _blocked(reason: str) -> dict:
        return {"status": "BLOCKED", "reason": reason}

    def _enabled(self) -> bool:
        # Configure only after approving Host security scope. MCP hints are NOT authorization.
        return os.environ.get("LORA_HARNESS_MUTATIONS") == "operator-enabled"

    def _external(self, run_id: str, *, create: bool = False) -> Path:
        if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
            raise ValueError("Invalid run ID")
        if self.root.is_symlink():
            raise ValueError("Evidence root symlink")
        if create:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        dest = self.root / run_id
        if dest.is_symlink():
            raise ValueError("Evidence run symlink")
        if create:
            dest.mkdir(mode=0o700, exist_ok=False)
        if not dest.is_dir():
            raise ValueError("Run evidence not found")
        return dest

    def _state(self, run_id: str) -> tuple[dict, Path]:
        dest = self._external(run_id)
        file = dest / "run.json"
        if not file.is_file() or file.is_symlink() or file.stat().st_size > 100_000:
            raise ValueError("Evidence run record not present")
        state = json.loads(file.read_text())
        if state["run_id"] != run_id:
            raise ValueError("Run ID mismatch")
        return state, dest

    def _receipt(self, run_id: str, stage: str, data: dict) -> None:
        _, dest = self._state(run_id)
        lockpath = dest / ".lock"
        fd = os.open(lockpath, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            state, _ = self._state(run_id)
            current = state["stage"]
            transitions = {
                "PREPARED": "WORKER_HANDOFF",
                "WORKER_HANDOFF": "SCOPE_VERIFIED",
                "SCOPE_VERIFIED": "CHECKS_VERIFIED",
                "CHECKS_VERIFIED": "AUDITOR_HANDOFF",
                "AUDITOR_HANDOFF": "AWAIT_HUMAN",
            }
            if transitions.get(current) != stage:
                raise ValueError("Out-of-order or repeated stage")
            receipt = dest / (stage.lower() + ".json")
            if receipt.exists() or receipt.is_symlink():
                raise ValueError("Stage receipt already exists")
            _atomic_json(receipt, data)
            state["stage"] = stage
            state.setdefault("receipts", {})[stage] = {
                "file": receipt.name, "sha256": _sha(receipt)
            }
            _atomic_json(dest / "run.json", state)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _job(self, run_id: str) -> dict:
        response = self.host.status(run_id)
        if response.get("state") != "PREPARED":
            raise ValueError("Host job is not PREPARED")
        return response

    def _scope(self, run_id: str) -> dict:
        info = self.host.verify_candidate(run_id)
        if info.get("status") != "SCOPE_SCAN_PASS_ONLY":
            raise ValueError("Deterministic Host scope verification failed")
        return info

    def prepare(self, issue: int, base_sha: str, issue_sha256: str) -> dict:
        """Prepare exactly the approved Issue and SHA; requires operator-enabled MCP runtime."""
        if not self._enabled():
            return self._blocked("Operator has not enabled mutating MCP execution")
        if isinstance(issue, bool) or not isinstance(issue, int) or issue < 1:
            return self._blocked("Invalid Issue")
        if not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha):
            return self._blocked("Invalid source pin")
        if not isinstance(issue_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", issue_sha256):
            return self._blocked("Invalid Issue SHA-256")
        preview = self.host.preflight(issue)
        if (preview.get("state") != "PREFLIGHT_ONLY" or
                preview.get("source_sha") != base_sha or
                preview.get("issue_sha256") != issue_sha256):
            return self._blocked("Issue/source changed since preflight")
        if not self.host._journal_available() and self.host.state.exists():
            return self._blocked("Host state journal unsafe")
        receipt = self.host._run("cli.py", [
            "prepare", "--issue", str(issue), "--source", str(self.host.source),
            "--state", str(self.host.state), "--expected-base-sha", base_sha,
            "--apply",
        ], timeout=115)
        if (receipt.get("state") != "PREPARED" or
                receipt.get("issue_sha256") != issue_sha256 or
                receipt.get("source_sha") != base_sha):
            return self._blocked("Host preparation was not verified; inspect journal")
        run_id = receipt.get("run_id")
        try:
            dest = self._external(run_id, create=True)
            _atomic_json(dest / "run.json", {
                "issue": issue, "run_id": run_id, "base_sha": base_sha,
                "issue_sha256": issue_sha256, "stage": "PREPARED",
                "branch": receipt.get("branch"), "worktree": receipt.get("worktree"),
                "approved_scope": receipt.get("approved_scope"),
                "receipts": {}, "proof": "HOST_PREPARED_ONLY",
            })
            return {"status": "PREPARED", "run_id": run_id,
                    "approved_scope": receipt.get("approved_scope"),
                    "worktree": receipt.get("worktree"), "branch": receipt.get("branch"),
                    "base_sha": base_sha, "evidence_dir": str(dest)}
        except (OSError, ValueError) as exc:
            return self._blocked("Host worktree prepared; evidence setup failed; manual recovery required")

    def worker_handoff(self, run_id: str) -> dict:
        if not self._enabled():
            return self._blocked("Execution disabled")
        try:
            state, _ = self._state(run_id)
            self._job(run_id)
            if state["stage"] != "PREPARED":
                raise ValueError("Worker has already been handed off")
            guidance = {
                "status": "WORKER_HANDOFF", "run_id": run_id,
                "worktree": state["worktree"], "allowed_paths": state["approved_scope"],
                "base_sha": state["base_sha"], "issue_sha256": state["issue_sha256"],
                "instructions": "Invoke a FRESH native CLI Worker subagent. Modify only allowed paths; no network, Docker, credentials, git pushes, shell or provider wrappers. Do not report completion until Host verifies actual changed files.",
                "native_worker_provenance": "NOT_VERIFIED",
            }
            self._receipt(run_id, "WORKER_HANDOFF", guidance)
            return guidance
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            return self._blocked(str(exc)[:160])

    def verify_worker(self, run_id: str) -> dict:
        if not self._enabled():
            return self._blocked("Execution disabled")
        try:
            state, _ = self._state(run_id)
            if state["stage"] != "WORKER_HANDOFF":
                raise ValueError("Worker handoff is required")
            info = self._scope(run_id)
            if sorted(info["paths"]) != sorted(set(info["paths"])):
                raise ValueError("Duplicate changed paths")
            self._receipt(run_id, "SCOPE_VERIFIED", info)
            return info
        except (OSError, ValueError, KeyError) as exc:
            return self._blocked(str(exc)[:160])

    def _command(self, argv: list[str], cwd: Path, outfile: Path, timeout: int) -> dict:
        """No shell/AI-provided command. Disk receipt bounded; stderr never returned to model."""
        try:
            with outfile.open("xb") as f:
                os.chmod(outfile, 0o600)
                start = time.monotonic()
                p = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL,
                                   stdout=f, stderr=subprocess.STDOUT, check=False,
                                   timeout=timeout)
                elapsed = round(time.monotonic()-start, 3)
            if outfile.stat().st_size > 50_000_000:
                raise ValueError("Host command log too large")
            return {"exit_code": p.returncode, "elapsed_seconds": elapsed,
                    "log": outfile.name, "log_sha256": _sha(outfile)}
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {"exit_code": None, "status": "BLOCKED", "reason": "Host process failed/timed out"}

    @staticmethod
    def _copy_firmware(source: Path, dest: Path) -> None:
        """Only normal firmware source/build metadata, never symlinks, hidden credentials or build outputs."""
        extensions = {".c", ".h", ".cpp", ".hpp", ".s", ".S", ".cmake", ".txt",
                      ".csv", ".json", ".yml", ".yaml", ".ld", ".py"}
        count = 0
        size = 0
        firmware = source / "firmware"
        if not firmware.is_dir() or firmware.is_symlink():
            raise ValueError("Firmware directory is invalid")
        for root, dirs, files in os.walk(firmware, followlinks=False):
            top = Path(root)
            dirs[:] = [d for d in dirs if d not in ("build", ".git", "__pycache__", ".venv")
                       and not d.startswith(".")]
            if any((top / d).is_symlink() for d in dirs):
                raise ValueError("Symlink firmware directory")
            for name in files:
                f = top / name
                if f.is_symlink() or not f.is_file():
                    raise ValueError("Nonregular firmware file")
                if name.startswith(".") or (name.startswith("sdkconfig") and name != "sdkconfig.defaults"):
                    continue
                if f.suffix not in extensions and name not in ("CMakeLists.txt", "Kconfig", "Kconfig.projbuild", "sdkconfig.defaults"):
                    continue
                count += 1
                size += f.stat().st_size
                if count > _MAX_FIRMWARE_FILES or f.stat().st_size > _MAX_SOURCE_FILE or size > 45_000_000:
                    raise ValueError("Firmware source exceeds bounded budget")
                target = dest / f.relative_to(source)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(f, target)
                target.chmod(0o644)

    def run_checks(self, run_id: str) -> dict:
        """Deterministic host checks and two offline firmware builds on disposable copies."""
        if not self._enabled():
            return self._blocked("Execution disabled")
        image_id = os.environ.get("LORA_HARNESS_DOCKER_IMAGE_ID", "")
        if not _DIGEST.fullmatch(image_id):
            return self._blocked("Operator-pinned Docker image ID required")
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "SCOPE_VERIFIED":
                raise ValueError("Host must first verify Worker scope")
            job = self._job(run_id)
            before = self._scope(run_id)
            # P1 checks cover Harness and ESP-IDF firmware only.
            # Backend/client/contracts have distinct test contracts and MUST
            # never be marked verified by unrelated firmware builds.
            supported_prefixes = (
                "firmware/", "scripts/agent_harness/", "tests/agent_harness/",
                "docs/", ".agents/agents/",
            )
            if any(not p.startswith(supported_prefixes) for p in before["paths"]):
                return self._blocked("Changed component requires unsupported layer-specific tests")
            prior = json.loads((dest / "scope_verified.json").read_text())
            if before != prior:
                raise ValueError("Candidate changed after scope receipt")
            # Run fixed trusted structure/Harness tests (not model-controlled command).
            tests = {}
            tests["structure"] = self._command(
                [sys.executable, "scripts/verify_structure.py"], self.host.source,
                dest / "structure.log", 90)
            tests["harness_unit"] = self._command(
                [sys.executable, "-m", "unittest", "discover", "-s",
                 "tests/agent_harness", "-v"], self.host.source,
                dest / "harness-unit.log", 240)
            if any(x.get("exit_code") != 0 for x in tests.values()):
                return self._blocked("Host tests failed; read external log receipts")
            # Copied source only; no original candidate bind mount. No host creds.
            from p1.runtime_boundary import BuildBoundary
            boundary = BuildBoundary(image_id)
            builds = {}
            with tempfile.TemporaryDirectory(prefix="lora-mcp-build-") as tmp:
                scratch = Path(tmp) / "repo"
                scratch.mkdir(mode=0o700)
                self._copy_firmware(Path(job["worktree"]), scratch)
                for app in ("gateway_master", "sensor_node"):
                    command = boundary.command(scratch, app)
                    builds[app] = self._command(command, self.host.source,
                                                dest / (app+".log"), 1800)
                    if builds[app].get("exit_code") != 0:
                        return self._blocked("Offline firmware build failed; inspect receipts")
            after = self._scope(run_id)
            if before != after:
                raise ValueError("Candidate SHA/scope changed during verification")
            receipt = {"status": "CHECKS_VERIFIED", "run_id": run_id,
                       "candidate": before, "tests": tests, "builds": builds,
                       "image_id": image_id, "esp_idf": "v6.1",
                       "hil": "NOT_VERIFIED", "rf": "NOT_VERIFIED"}
            self._receipt(run_id, "CHECKS_VERIFIED", receipt)
            return {"status": "CHECKS_VERIFIED", "run_id": run_id,
                    "tests": tests, "builds": builds, "evidence_dir": str(dest)}
        except Exception as exc:
            return self._blocked("Host check incomplete: " + type(exc).__name__)

    def auditor_handoff(self, run_id: str) -> dict:
        """Freeze actual candidate and context; no Gemini/Codex subprocess invoked."""
        if not self._enabled():
            return self._blocked("Execution disabled")
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "CHECKS_VERIFIED":
                raise ValueError("Checks must pass before audit handoff")
            self._job(run_id)
            checks = json.loads((dest / "checks_verified.json").read_text())
            candidate = self._scope(run_id)
            if candidate != checks["candidate"]:
                raise ValueError("Candidate changed since tests")
            snapshot = dest / "snapshot"
            snapshot.mkdir(mode=0o700)
            # The Auditor must see the actual, pinned Issue Acceptance Criteria.
            from p1.cli import issue_info
            issue_body = issue_info(self.host.source, state["issue"])["body"]
            if hashlib.sha256(issue_body.encode()).hexdigest() != state["issue_sha256"]:
                raise ValueError("Issue body changed since approval")
            issue_copy = snapshot / "issue.md"
            issue_copy.write_text(issue_body, encoding="utf-8")
            issue_copy.chmod(0o444)
            source_root = Path(state["worktree"])
            manifest = {"issue.md": _sha(issue_copy)}
            for reference in ("AGENTS.md", ".github/copilot-instructions.md",
                              "docs/development/agy-native-coordinator-sop.md"):
                src = source_root / reference
                if not src.is_file() or src.is_symlink() or src.stat().st_size > 120_000:
                    raise ValueError("Required policy reference missing/unsafe")
                dest_ref = snapshot / "source" / reference
                dest_ref.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(src, dest_ref)
                dest_ref.chmod(0o444)
                manifest["source/"+reference] = _sha(dest_ref)
            for name in candidate["paths"]:
                item = source_root / name
                if item.is_symlink():
                    raise ValueError("Symlink in audit input")
                rel = snapshot / "source" / name
                rel.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if item.is_file():
                    shutil.copyfile(item, rel)
                    rel.chmod(0o444)
                    manifest["source/"+name] = _sha(rel)
                else:
                    manifest["deleted/"+name] = "DELETED"
            schema = self.host.source / "scripts/agent_harness/adapters/audit.schema.json"
            shutil.copyfile(schema, snapshot / "audit.schema.json")
            (snapshot / "audit.schema.json").chmod(0o444)
            manifest["audit.schema.json"] = _sha(snapshot / "audit.schema.json")
            receipt = {"status": "AUDITOR_HANDOFF", "run_id": run_id,
                       "candidate": candidate, "snapshot_files_sha256": manifest,
                       "snapshot": str(snapshot),
                       "instructions": "Use a FRESH native Codex/AGY Auditor subagent with no shell/write tools. Read actual frozen file bytes, Issue AC and policies; return ONLY strict audit schema JSON. A native subagent context is not OS/provider isolation.",
                       "auditor_provenance": "NOT_VERIFIED"}
            self._receipt(run_id, "AUDITOR_HANDOFF", receipt)
            return receipt
        except Exception as exc:
            return self._blocked("Could not freeze audit snapshot: "+type(exc).__name__)

    def submit_audit(self, run_id: str, report: dict) -> dict:
        """Validate native Auditor's reported JSON; does NOT authenticate model provenance."""
        if not self._enabled():
            return self._blocked("Execution disabled")
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "AUDITOR_HANDOFF":
                raise ValueError("Auditor handoff is required")
            from adapters.antigravity import check_report
            frozen = json.loads((dest / "auditor_handoff.json").read_text())
            candidate = self._scope(run_id)
            if candidate != frozen["candidate"]:
                raise ValueError("Candidate changed after frozen snapshot")
            snapshot = Path(frozen["snapshot"])
            expected = frozen["snapshot_files_sha256"]
            actual = {}
            for item in snapshot.rglob("*"):
                if item.is_symlink():
                    raise ValueError("Snapshot symlink")
                if item.is_file():
                    actual[item.relative_to(snapshot).as_posix()] = _sha(item)
            if actual != {k: v for k, v in expected.items() if not k.startswith("deleted/")}:
                raise ValueError("Snapshot files changed")
            checked = check_report(report, set(candidate["paths"]))
            if checked["status"] != "PASS":
                return self._blocked("Auditor did not report PASS")
            # The Host validates shape/scope/hashes only. Without attestable native
            # invocation receipts it CANNOT truthfully assert Auditor independence.
            result = {"status": "AWAIT_HUMAN", "run_id": run_id,
                      "host_checks": "PASS", "auditor_report_schema_scope": "PASS",
                      "auditor_reported_status": "PASS",
                      "native_auditor_provenance": "NOT_VERIFIED",
                      "human_review": "PENDING",
                      "hil": "NOT_VERIFIED", "rf": "NOT_VERIFIED",
                      "source": state["base_sha"], "issue": state["issue"]}
            _atomic_json(dest / "auditor-report.json", checked)
            self._receipt(run_id, "AWAIT_HUMAN", result)
            return {**result, "evidence_manifest": str(dest / "run.json")}
        except Exception as exc:
            return self._blocked("Host audit validation failed: " + type(exc).__name__)
