"""Staged deterministic MCP Host execution.

Only fixed commands and versioned Host scripts may run. No provider CLI invocation.
Run state/receipts are persisted OUTSIDE the source/worktree. Fail closed.
"""
from __future__ import annotations

import hashlib
import fcntl
from functools import wraps
from contextlib import closing
import stat
import sqlite3
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

from mcp_host import HarnessMCPHost, bounded_run
from mcp_approval import ApprovalAuthority, _HEX32
from mcp_docker import DockerLifecycle
from adapters.antigravity import _reject_duplicate_object_keys, _reject_invalid_constant

_RUN = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_OUTPUT = 300_000
_STAGES = ("PREPARED", "WORKER_HANDOFF", "SCOPE_VERIFIED", "CHECKS_VERIFIED",
           "AUDITOR_HANDOFF", "AWAIT_HUMAN")
_MAX_SOURCE_FILE = 6_000_000
_MAX_FIRMWARE_FILES = 5000


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or info.st_size > 100_000):
            raise ValueError("Unsafe evidence file")
        data = stream.read(100_001)
    if len(data) > 100_000:
        raise ValueError("Evidence too large")
    value = json.loads(data, object_pairs_hook=_reject_duplicate_object_keys,
                       parse_constant=_reject_invalid_constant)
    if not isinstance(value, dict):
        raise ValueError("Evidence must be an object")
    return value


def _check_snapshot(dest: Path, frozen: dict) -> None:
    snapshot = dest / "snapshot"
    if frozen["snapshot"] != str(snapshot) or snapshot.is_symlink() or not snapshot.is_dir():
        raise ValueError("Invalid snapshot root")
    expected = frozen["snapshot_files_sha256"]
    actual = {}
    size = 0
    for count, item in enumerate(snapshot.rglob("*")):
        if count >= 250:
            raise ValueError("Snapshot entry budget exceeded")
        info = item.stat(follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("Nonregular snapshot input")
        size += info.st_size
        if info.st_size > 120_000 or size > 2_000_000 or len(actual) >= 100:
            raise ValueError("Snapshot budget exceeded")
        actual[item.relative_to(snapshot).as_posix()] = _sha(item)
    if actual != {k: v for k, v in expected.items() if not k.startswith("deleted/")}:
        raise ValueError("Snapshot files changed")


def _stage(expected: str):
    """Serialize the entire side effect, not just its final state write."""
    def decorate(method):
        @wraps(method)
        def guarded(self, run_id, *args, **kwargs):
            if not self._enabled(run_id):
                return self._blocked("No valid signed operator grant for this run")
            fd = None
            try:
                dest = self._external(run_id)
                fd = os.open(dest / ".lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                state, _ = self._state(run_id)
                if state["stage"] != expected:
                    raise ValueError("Out-of-order or repeated operation")
                marker = dest / "operation.json"
                if marker.exists() or marker.is_symlink():
                    raise ValueError("Interrupted/failed operation requires manual recovery")
                _atomic_json(marker, {"stage": expected, "operation": method.__name__})
                result = method(self, run_id, *args, **kwargs)
                if self._state(run_id)[0]["stage"] != expected:
                    marker.unlink()
                else:
                    _atomic_json(dest / "failure.json", result)
                return result
            except (OSError, ValueError, KeyError, TypeError):
                return self._blocked("Stage busy, invalid, or requires manual recovery")
            finally:
                if fd is not None:
                    os.close(fd)
        return guarded
    return decorate


def _atomic_json(path: Path, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode()
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
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
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

    def _enabled(self, run_id: str | None = None) -> bool:
        # Signature authority is root-owned and separate from the model/MCP UID.
        # This is authorization, NOT a sandbox or proof of operator physical presence.
        if not run_id:
            return False
        try:
            state, _ = self._state(run_id)
            grant_id = state.get("approval_id")
            if not isinstance(grant_id, str) or not _HEX32.fullmatch(grant_id):
                return False
            ApprovalAuthority().verify(
                issue=state["issue"], base_sha=state["base_sha"],
                issue_sha256=state["issue_sha256"],
                scope=state["approved_scope"], action="prepare",
                expected_id=grant_id)
            return True
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _check_evidence_root(self) -> None:
        if self.root.is_symlink():
            raise ValueError("Unsafe evidence root")
        info = self.root.stat(follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077):
            raise ValueError("Evidence root must be private and Host-owned")

    def _external(self, run_id: str, *, create: bool = False) -> Path:
        if not isinstance(run_id, str) or not _RUN.fullmatch(run_id):
            raise ValueError("Invalid run ID")
        if self.root.is_symlink() or self.root.parent.resolve() != self.root.parent:
            raise ValueError("Evidence root symlink")
        if create:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        dest = self.root / run_id
        if dest.is_symlink():
            raise ValueError("Evidence run symlink")
        if create:
            dest.mkdir(mode=0o700, exist_ok=False)
        for directory in (self.root, dest):
            info = directory.stat(follow_symlinks=False)
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                raise ValueError("Evidence directory must be private and Host-owned")
        return dest

    def _state(self, run_id: str) -> tuple[dict, Path]:
        dest = self._external(run_id)
        state = _read_json(dest / "run.json")
        if state["run_id"] != run_id or state["stage"] not in _STAGES:
            raise ValueError("Run ID/stage mismatch")
        if (not isinstance(state["issue"], int) or isinstance(state["issue"], bool)
                or not 1 <= state["issue"] <= 2_147_483_647
                or not _SHA.fullmatch(state["base_sha"])
                or not re.fullmatch(r"[0-9a-f]{64}", state["issue_sha256"])):
            raise ValueError("Invalid run pins")
        from scope import parse_allowed_paths
        scope = state["approved_scope"]
        if not isinstance(scope, list) or not scope or len(scope) != len(set(scope)):
            raise ValueError("Invalid approved scope")
        parsed = parse_allowed_paths("## Target Directories (allowed paths)\n" +
                                     "\n".join("- `" + name + "`" for name in scope))
        if tuple(scope) != parsed:
            raise ValueError("Noncanonical approved scope")
        expected = _STAGES[1:_STAGES.index(state["stage"]) + 1]
        if set(state["receipts"]) != set(expected):
            raise ValueError("Incomplete evidence chain")
        for stage in expected:
            entry = state["receipts"][stage]
            path = dest / (stage.lower() + ".json")
            receipt = _read_json(path)
            if entry != {"file": path.name, "sha256": _sha(path)}:
                raise ValueError("Evidence receipt hash mismatch")
            if stage == "CHECKS_VERIFIED":
                for key, logname in (("structure", "structure.log"),
                                     ("harness_unit", "harness-unit.log"),
                                     ("gateway_master", "gateway_master.log"),
                                     ("sensor_node", "sensor_node.log")):
                    section = "tests" if key in ("structure", "harness_unit") else "builds"
                    log = receipt[section][key]
                    file = dest / logname
                    info = file.stat(follow_symlinks=False)
                    if (not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_OUTPUT
                            or log["exit_code"] != 0 or log["log"] != logname
                            or _sha(file) != log["log_sha256"]):
                        raise ValueError("Missing/changed command evidence")
            if stage == "AUDITOR_HANDOFF":
                _check_snapshot(dest, receipt)
            if stage == "AWAIT_HUMAN":
                _read_json(dest / "auditor-report.json")
                if _sha(dest / "auditor-report.json") != receipt["auditor_report_sha256"]:
                    raise ValueError("Auditor report changed")
        for stage in _STAGES[1:]:
            path = dest / (stage.lower() + ".json")
            if stage not in expected and (path.exists() or path.is_symlink()):
                raise ValueError("Uncommitted receipt requires manual recovery")
        return state, dest

    def _receipt(self, run_id: str, stage: str, data: dict) -> None:
        # Caller holds the operation lock, including all preceding side effects.
        state, dest = self._state(run_id)
        if _STAGES.index(stage) != _STAGES.index(state["stage"]) + 1:
            raise ValueError("Out-of-order or repeated stage")
        receipt = dest / (stage.lower() + ".json")
        if receipt.exists() or receipt.is_symlink():
            raise ValueError("Stage receipt already exists")
        _atomic_json(receipt, data)
        state["stage"] = stage
        state["receipts"][stage] = {"file": receipt.name, "sha256": _sha(receipt)}
        _atomic_json(dest / "run.json", state)

    def _job(self, run_id: str) -> dict:
        response = self.host.status(run_id)
        if response.get("state") != "PREPARED":
            raise ValueError("Host job is not PREPARED")
        state, _ = self._state(run_id)
        for field, expected in (("run_id", run_id), ("issue", state["issue"]),
                                ("source_sha", state["base_sha"]),
                                ("worktree", state["worktree"]), ("branch", state["branch"])):
            if response.get(field) != expected:
                raise ValueError("Host journal and execution state disagree")
        # Legacy status omits Issue/scope pins. Cross-check their real journal row.
        if not self.host._journal_available():
            raise ValueError("Host journal unavailable")
        try:
            with closing(sqlite3.connect(self.host.state.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
                row = db.execute("SELECT issue_sha, scope_json FROM jobs WHERE run_id=?", (run_id,)).fetchone()
            if (row is None or row[0] != state["issue_sha256"] or len(row[1]) > 100_000
                    or json.loads(row[1]) != state["approved_scope"]):
                raise ValueError("Host Issue/scope approval differs from execution record")
        except sqlite3.Error as exc:
            raise ValueError("Cannot validate Host journal pins") from exc
        return response

    def _scope(self, run_id: str) -> dict:
        info = self.host.verify_candidate(run_id)
        if info.get("status") != "SCOPE_SCAN_PASS_ONLY":
            raise ValueError("Deterministic Host scope verification failed")
        # Existing Host gate excludes gitignored untracked files. They may
        # contain secrets/build artifacts hidden from the diff, so block them.
        job = self._job(run_id)
        worktree = Path(job["worktree"])
        if not worktree.is_dir() or worktree.is_symlink():
            raise ValueError("Unsafe candidate directory")
        ignored = bounded_run(
            ["git", "-C", str(worktree), "ls-files", "--others", "--ignored",
             "--exclude-standard", "-z"], worktree, timeout=30, limit=_MAX_OUTPUT)
        if ignored.returncode or ignored.stdout:
            raise ValueError("Candidate contains ignored/untracked files")
        state, _ = self._state(run_id)
        from scope import violations
        if (info.get("base_sha") != state["base_sha"] or not info.get("paths")
                or violations(worktree, state["approved_scope"], info["paths"])):
            raise ValueError("Candidate differs from approved base/scope")
        return info

    def status(self, run_id: str) -> dict:
        try:
            state, dest = self._state(run_id)
            job = self._job(run_id)
            marker = dest / "operation.json"
            if marker.exists() or marker.is_symlink():
                return self._blocked("Operation active or manual recovery required")
            if _STAGES.index(state["stage"]) >= 2:
                frozen = _read_json(dest / "scope_verified.json")
                if frozen != self._scope(run_id):
                    raise ValueError("Candidate changed since verification")
            return {"status": state["stage"], "run_id": run_id,
                    "issue": state["issue"], "receipts": state["receipts"],
                    "evidence_dir": str(dest), "host_sqlite_state": job["state"],
                    "native_auditor_provenance": "NOT_VERIFIED"}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            return self._blocked("Run missing, inconsistent, or evidence changed")

    def prepare(self, issue: int, base_sha: str, issue_sha256: str) -> dict:
        """Consume an independent, signed, exact-Issue grant before any mutation.

        A consumed authorization cannot be used to silently retry a failed
        preparation. Remote GitHub edits are rechecked at the Host CLI boundary.
        """
        if (isinstance(issue, bool) or not isinstance(issue, int) or issue <= 0
                or not isinstance(base_sha, str) or not _SHA.fullmatch(base_sha)
                or not isinstance(issue_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", issue_sha256)):
            return self._blocked("Invalid Issue/source approval pins")
        try:
            preview = self.host.preflight(issue)
            if (preview.get("state") != "PREFLIGHT_ONLY"
                    or preview.get("source_sha") != base_sha
                    or preview.get("issue_sha256") != issue_sha256):
                raise ValueError("Issue/source changed since preflight")
            scope = preview.get("approved_scope")
            if not isinstance(scope, list) or not scope:
                raise ValueError("Preflight scope unavailable")
            grant = ApprovalAuthority().verify(issue=issue, base_sha=base_sha,
                    issue_sha256=issue_sha256, scope=scope, action="prepare")
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._check_evidence_root()
            lock_path = self.root / ".approval.lock"
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                used = self.root / ("consumed-" + grant["grant_id"])
                if used.exists() or used.is_symlink():
                    raise ValueError("Approval already consumed; no implicit retry")
                # Recheck signed grant while holding local consumption lock.
                ApprovalAuthority().verify(issue=issue, base_sha=base_sha,
                    issue_sha256=issue_sha256, scope=scope, action="prepare",
                    expected_id=grant["grant_id"])
                _atomic_json(used, {"issue": issue, "base_sha": base_sha,
                    "issue_sha256": issue_sha256, "approval_id": grant["grant_id"],
                    "disposition": "CONSUMED_BEFORE_LOCAL_MUTATION"})
            finally:
                os.close(fd)
            # Trust the Host CLI to re-fetch the Issue body immediately BEFORE
            # planning its SQLite journal and worktree. No shell command accepted.
            receipt = self.host._run("cli.py", [
                "prepare", "--issue", str(issue), "--source", str(self.host.source),
                "--state", str(self.host.state), "--apply",
                "--expected-base-sha", base_sha,
                "--expected-issue-sha256", issue_sha256], timeout=115)
            if (receipt.get("state") != "PREPARED" or
                    receipt.get("issue_sha256") != issue_sha256 or
                    receipt.get("source_sha") != base_sha or
                    receipt.get("approved_scope") != scope):
                raise ValueError("Preparation failed/stale; manual recovery required")
            run_id = receipt["run_id"]
            dest = self._external(run_id, create=True)
            _atomic_json(dest / "run.json", {
                "issue": issue, "run_id": run_id, "base_sha": base_sha,
                "issue_sha256": issue_sha256, "approval_id": grant["grant_id"],
                "stage": "PREPARED", "branch": receipt["branch"],
                "worktree": receipt["worktree"], "approved_scope": scope,
                "receipts": {}, "human_review": "PENDING",
            })
            return {"status": "PREPARED", "run_id": run_id,
                    "approved_scope": scope, "worktree": receipt["worktree"],
                    "branch": receipt["branch"], "evidence_dir": str(dest)}
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            return self._blocked("Host approval/preparation failed: " + type(exc).__name__)

    @_stage("PREPARED")
    def worker_handoff(self, run_id: str) -> dict:
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

    @_stage("WORKER_HANDOFF")
    def verify_worker(self, run_id: str) -> dict:
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
        """Streaming cap on both pipes and disk; never return log text to MCP."""
        start = time.monotonic()
        created = False
        try:
            fd = os.open(outfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            created = True
            with os.fdopen(fd, "wb") as stream:
                result = bounded_run(argv, cwd, timeout=timeout, limit=_MAX_OUTPUT,
                                     log=stream,
                                     env={"PATH": "/usr/bin:/bin", "HOME": "/tmp", "LANG": "C.UTF-8"})
            return {"exit_code": result.returncode,
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "log": outfile.name, "log_sha256": _sha(outfile)}
        except (OSError, subprocess.SubprocessError, ValueError):
            receipt = {"exit_code": None, "status": "BLOCKED",
                       "elapsed_seconds": round(time.monotonic() - start, 3),
                       "reason": "Host process failed, exceeded output limit, or timed out"}
            if created:
                receipt.update(log=outfile.name, log_sha256=_sha(outfile))
            return receipt

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

    @_stage("SCOPE_VERIFIED")
    def run_checks(self, run_id: str) -> dict:
        """Diagnostic Host tests only; no build PASS without daemon supervision."""
        image_id = os.environ.get("LORA_HARNESS_DOCKER_IMAGE_ID", "")
        if not _DIGEST.fullmatch(image_id):
            return self._blocked("Operator-pinned Docker image ID required")
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "SCOPE_VERIFIED":
                raise ValueError("Host must first verify Worker scope")
            self._job(run_id)
            before = self._scope(run_id)
            # Trusted-source tests do not exercise candidate code changes.
            supported_prefixes = (
                "docs/", "firmware/", "tests/agent_harness/fixtures/pilot/",
            )
            if any(not p.startswith(supported_prefixes) for p in before["paths"]):
                return self._blocked("Candidate code needs isolated candidate tests/build cancellation; not supported")
            prior = _read_json(dest / "scope_verified.json")
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
            # Build only on a fresh disposable copy of candidate firmware.
            # Docker containers are daemon-owned: the supervisor *must* observe
            # and verify cleanup of the run/app label even after CLI timeout.
            builds = {}
            with tempfile.TemporaryDirectory(prefix="lora-harness-build-") as tmp:
                scratch = Path(tmp).resolve()
                self._copy_firmware(Path(state["worktree"]), scratch)
                docker = DockerLifecycle()
                for app in ("gateway_master", "sensor_node"):
                    builds[app] = docker.build(
                        run_id=run_id, app=app, image_id=image_id,
                        scratch=scratch, evidence=dest,
                        command_runner=lambda argv, outfile, timeout:
                            self._command(argv, self.host.source, outfile, timeout))
            after = self._scope(run_id)
            if after != before:
                raise ValueError("Candidate changed while performing Docker builds")
            receipt = {
                "status": "CHECKS_VERIFIED", "run_id": run_id,
                "candidate": before, "tests": tests, "builds": builds,
                "image_id": image_id, "esp_idf": "v6.1",
                "hil": "NOT_VERIFIED", "rf": "NOT_VERIFIED",
            }
            self._receipt(run_id, "CHECKS_VERIFIED", receipt)
            return {"status": "CHECKS_VERIFIED", "run_id": run_id,
                    "tests": tests, "builds": builds, "image_id": image_id,
                    "evidence_dir": str(dest)}
        except Exception as exc:
            return self._blocked("Host check incomplete: " + type(exc).__name__)

    @_stage("CHECKS_VERIFIED")
    def auditor_handoff(self, run_id: str) -> dict:
        """Freeze actual candidate and context; no Gemini/Codex subprocess invoked."""
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "CHECKS_VERIFIED":
                raise ValueError("Checks must pass before audit handoff")
            self._job(run_id)
            checks = _read_json(dest / "checks_verified.json")
            candidate = self._scope(run_id)
            if candidate != checks["candidate"]:
                raise ValueError("Candidate changed since tests")
            snapshot = dest / "snapshot"
            snapshot.mkdir(mode=0o700)
            # The Auditor must see the actual, pinned Issue Acceptance Criteria.
            response = bounded_run(
                ["gh", "issue", "view", str(state["issue"]), "--repo",
                 "khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP", "--json", "body,state"],
                self.host.source, timeout=40, limit=65536)
            issue = json.loads(response.stdout)
            if response.returncode != 0 or issue["state"] != "OPEN":
                raise ValueError("Issue unavailable or closed")
            issue_body = issue["body"]
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
                if (not src.is_file() or src.is_symlink() or src.resolve() != src
                        or src.stat().st_size > 120_000):
                    raise ValueError("Required policy reference missing/unsafe")
                dest_ref = snapshot / "source" / reference
                dest_ref.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                shutil.copyfile(src, dest_ref)
                dest_ref.chmod(0o444)
                manifest["source/"+reference] = _sha(dest_ref)
            for name in candidate["paths"]:
                item = source_root / name
                if item.is_symlink() or item.resolve() != item:
                    raise ValueError("Symlink in audit input")
                rel = snapshot / "source" / name
                rel.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if item.is_file():
                    shutil.copyfile(item, rel)
                    rel.chmod(0o444)
                    manifest["source/"+name] = _sha(rel)
                    if manifest["source/"+name] != candidate["files_sha256"].get(name):
                        raise ValueError("Snapshot bytes differ from verified candidate")
                else:
                    manifest["deleted/"+name] = "DELETED"
            schema = self.host.source / "scripts/agent_harness/adapters/audit.schema.json"
            if schema.resolve() != schema or not schema.is_file() or schema.stat().st_size > 120_000:
                raise ValueError("Unsafe audit schema")
            shutil.copyfile(schema, snapshot / "audit.schema.json")
            (snapshot / "audit.schema.json").chmod(0o444)
            manifest["audit.schema.json"] = _sha(snapshot / "audit.schema.json")
            if candidate != self._scope(run_id):
                raise ValueError("Candidate changed while freezing snapshot")
            receipt = {"status": "AUDITOR_HANDOFF", "run_id": run_id,
                       "candidate": candidate, "snapshot_files_sha256": manifest,
                       "snapshot": str(snapshot),
                       "instructions": "Use a FRESH native Codex/AGY Auditor subagent with no shell/write tools. Read actual frozen file bytes, Issue AC and policies; return ONLY strict audit schema JSON. A native subagent context is not OS/provider isolation.",
                       "auditor_provenance": "NOT_VERIFIED"}
            self._receipt(run_id, "AUDITOR_HANDOFF", receipt)
            return receipt
        except Exception as exc:
            return self._blocked("Could not freeze audit snapshot: "+type(exc).__name__)

    @_stage("AUDITOR_HANDOFF")
    def submit_audit(self, run_id: str, report: dict) -> dict:
        """Validate native Auditor's reported JSON; does NOT authenticate model provenance."""
        try:
            state, dest = self._state(run_id)
            if state["stage"] != "AUDITOR_HANDOFF":
                raise ValueError("Auditor handoff is required")
            from adapters.antigravity import check_report
            frozen = _read_json(dest / "auditor_handoff.json")
            candidate = self._scope(run_id)
            if candidate != frozen["candidate"]:
                raise ValueError("Candidate changed after frozen snapshot")
            _check_snapshot(dest, frozen)
            if len(json.dumps(report, allow_nan=False).encode()) > 100_000:
                raise ValueError("Audit report too large")
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
            result["auditor_report_sha256"] = _sha(dest / "auditor-report.json")
            self._receipt(run_id, "AWAIT_HUMAN", result)
            return {**result, "evidence_manifest": str(dest / "run.json")}
        except Exception as exc:
            return self._blocked("Host audit validation failed: " + type(exc).__name__)
