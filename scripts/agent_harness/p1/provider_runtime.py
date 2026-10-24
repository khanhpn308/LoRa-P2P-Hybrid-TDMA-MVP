"""P1-B2-B isolated provider smoke-test plan; NOT an unattended coding runner.

An external administrator MUST configure restricted egress, supply a reviewed
CLI image, and provision distinct credential volumes. Docker network membership
alone does not implement an egress allowlist or attest VM isolation.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import re
import signal
import subprocess
import tempfile
import resource
from dataclasses import dataclass

IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
VOLUME = re.compile(r"^lora-agent-(?:codex|agy)-auth-[a-z0-9][a-z0-9-]{0,42}$")
NETWORK = re.compile(r"^lora-agent-egress-[a-z0-9][a-z0-9-]{0,42}$")
NAME = re.compile(r"^lora-p1-probe-(?:codex|agy)-[a-f0-9]{8}$")
OUTPUT_LIMIT = 64_000
MAX_SECONDS = 240
# Exact, known non-fatal Codex CLI startup warning on an immutable Docker
# rootfs. Do NOT ignore other read-only/permission diagnostics.
_CODEX_ALIAS_WARNING = re.compile(
    rb"(?m)^WARNING: proceeding, even though we could not create PATH aliases: "
    rb"Read-only file system \(os error 30\)\r?$"
)


def _effective_probe_stderr(provider: str, stderr: bytes) -> tuple[bytes, int]:
    """Strip only a precise Codex alias-install warning; retain all other lines."""
    if provider != "codex":
        return stderr, 0
    matches = _CODEX_ALIAS_WARNING.findall(stderr)
    # Never accept an unexpectedly repeated startup warning.
    if len(matches) != 1:
        return stderr, 0
    return _CODEX_ALIAS_WARNING.sub(b"", stderr, count=1), 1


class RuntimeBlocked(RuntimeError):
    """Container launch plan violates the verified interface contract."""


@dataclass(frozen=True)
class IsolatedCLI:
    provider: str
    image_id: str
    network: str
    profile_volume: str

    def command(self, snapshot: pathlib.Path, container_name: str,
                prompt: str, *, docker_only_isolation: bool = False) -> list[str]:
        if self.provider not in ("codex", "agy"):
            raise RuntimeBlocked("Unknown provider")
        if docker_only_isolation and self.provider != "codex":
            raise RuntimeBlocked("Docker-only sandbox override is Codex-specific")
        if not IMAGE.fullmatch(self.image_id):
            raise RuntimeBlocked("Provider CLI image must be pinned to inspected sha256 ID")
        if not NETWORK.fullmatch(self.network):
            raise RuntimeBlocked("Only a separately governed provider-egress network is allowed")
        if not VOLUME.fullmatch(self.profile_volume) or (
                not self.profile_volume.startswith("lora-agent-" + self.provider + "-auth-")):
            raise RuntimeBlocked("Invalid provider-isolated authentication volume")
        if not NAME.fullmatch(container_name) or (
                not container_name.startswith("lora-p1-probe-" + self.provider + "-")):
            raise RuntimeBlocked("Invalid owned container name")
        if (not isinstance(prompt, str) or len(prompt) > 4000
                or not prompt.isascii()):
            raise RuntimeBlocked("Smoke prompt exceeds ASCII/size budget")
        if snapshot.is_symlink() or not snapshot.is_dir():
            raise RuntimeBlocked("Missing / symlink smoke snapshot")
        if os.name != "posix" or not hasattr(os, "getuid"):
            raise RuntimeBlocked("Supported Linux / WSL2 environment required")
        root = snapshot.resolve(strict=True)
        provider_env = ([
            "--env", "CODEX_HOME=/home/agent/.codex-clean-pilot",
            "--env", "CODEX_CA_CERTIFICATE=/etc/ssl/certs/ca-certificates.crt",
        ] if self.provider == "codex" else [])
        flags = [
            "docker", "run", "--rm", "--init", "--pull=never",
            "--name", container_name,
            "--network", self.network,
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=96", "--memory=2g", "--cpus=1",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
            "--user", "10001:10001",
            "--env", "HOME=/home/agent",
            "--env", "HTTP_PROXY=http://lora-egress-proxy:3128",
            "--env", "HTTPS_PROXY=http://lora-egress-proxy:3128",
            "--env", "http_proxy=http://lora-egress-proxy:3128",
            "--env", "https_proxy=http://lora-egress-proxy:3128",
            "--env", "NO_PROXY=",
            "--env", "no_proxy=",
            "--mount", f"type=bind,src={root},dst=/workspace,readonly",
            "--mount", f"type=volume,src={self.profile_volume},dst=/home/agent",
            "--workdir", "/workspace",
            *provider_env,
            self.image_id,
        ]
        if self.provider == "codex":
            # Docker is the sole OS boundary in this explicitly accepted mode.
            # The immutable root, read-only /workspace, non-root uid, no caps,
            # and segregated internal egress network must remain in force.
            sandbox = "danger-full-access" if docker_only_isolation else "read-only"
            # A disposable smoke does not need durable Codex session rollouts.
            # Avoid a background write path rather than whitelisting os error 13.
            return flags + ["codex", "--ask-for-approval", "never",
                            "exec", "--ephemeral", "--sandbox", sandbox,
                            "--skip-git-repo-check", prompt]
        return flags + ["agy", "--sandbox", "-p", prompt,
                        "--output-format", "json", "--print-timeout", "3m"]


def verify_preinstalled_resources(spec: IsolatedCLI) -> None:
    """Probe existing Docker resources; no creation, pulls or policy attestation.

    An internal bridge network is required; this does NOT prove outbound ACL enforcement.
    """
    lookups = (
        (["docker", "image", "inspect", "--format", "{{.Id}}", spec.image_id],
         spec.image_id),
        (["docker", "network", "inspect", "--format", "{{.Driver}}|{{.Internal}}", spec.network],
         "bridge|true"),
        (["docker", "volume", "inspect", "--format", "{{.Name}}", spec.profile_volume],
         spec.profile_volume),
    )
    for argv, wanted in lookups:
        try:
            proc = subprocess.run(argv, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, timeout=20,
                                  check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeBlocked("Docker runtime inspection unavailable") from exc
        if proc.returncode or proc.stdout.strip() != wanted:
            raise RuntimeBlocked("Pre-provisioned image, bridge network or auth volume missing")


@dataclass(frozen=True)
class ProbeReceipt:
    provider: str
    status: str
    exit_code: int | None
    sha256: str
    output_bytes: int

    def as_json(self) -> dict:
        return vars(self)


def _run(argv: list[str], *, timeout: int, name: str) -> tuple[int | None, bytes, bytes]:
    """Only accepts argv constructed by IsolatedCLI, never arbitrary Agent commands."""
    if timeout < 1 or timeout > MAX_SECONDS or argv[:2] != ["docker", "run"]:
        raise RuntimeBlocked("Invalid bounded Docker invocation")
    # Use file-backed output, not unbounded subprocess.PIPE accumulation.
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        def limit_output():
            resource.setrlimit(resource.RLIMIT_FSIZE, (OUTPUT_LIMIT, OUTPUT_LIMIT))

        try:
            process = subprocess.Popen(argv, stdout=stdout_file,
                                       stderr=stderr_file, stdin=subprocess.DEVNULL,
                                       start_new_session=True, preexec_fn=limit_output)
        except OSError as exc:
            raise RuntimeBlocked("Docker cannot start: " + type(exc).__name__) from exc
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            # Only the uniquely named container owned by this probe.
            try:
                subprocess.run(["docker", "kill", name],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=15, check=False)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise RuntimeBlocked("Provider probe timed out; container cleanup attempted") from exc
        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(OUTPUT_LIMIT + 1)
        stderr = stderr_file.read(OUTPUT_LIMIT + 1)
        if len(stdout) + len(stderr) > OUTPUT_LIMIT:
            raise RuntimeBlocked("Provider output exceeded capture budget")
        return process.returncode, stdout, stderr




def _safe_permission_line_shapes(stderr: bytes) -> list[dict]:
    """Expose bounded boolean signatures, never stderr text, paths, or tokens."""
    patterns = (
        ("path_aliases", rb"(?i)path aliases"),
        ("startup_proceeding", rb"(?i)warning: proceeding"),
        ("read_only_filesystem", rb"(?i)read.only file system"),
        ("permission_denied", rb"(?i)permission denied"),
        ("operation_not_permitted", rb"(?i)operation not permitted"),
        ("os_error_30", rb"(?i)os error 30"),
        ("os_error_13", rb"(?i)os error 13"),
        ("codex_home", rb"(?i)codex.clean.pilot|[.]codex"),
        ("session_storage", rb"(?i)session|sqlite|database"),
        ("logging", rb"(?i)log(ger|ging|file|s)?"),
        ("workspace", rb"(?i)/workspace"),
        ("usr_local", rb"(?i)/usr/local"),
        ("tmp", rb"(?i)/tmp"),
        ("has_ansi", b"\x1b"),
    )
    matches = []
    for line_no, line in enumerate(stderr.splitlines(), 1):
        if not re.search(
                rb"(?i)(permission denied|read.only file system|operation not permitted)",
                line):
            continue
        matches.append({
            "line_number": line_no,
            "line_bytes": len(line),
            "tags": [key for key, pattern in patterns if re.search(pattern, line)],
        })
        if len(matches) == 6:
            break
    return matches


def safe_probe_diagnostic(provider: str, code: int | None,
                          stdout: bytes, stderr: bytes) -> dict:
    """Bounded keyword signals only: NEVER print model output or credentials."""
    if provider not in ("codex", "agy"):
        raise RuntimeBlocked("Unknown provider")
    effective_stderr, benign_alias_warning_count = _effective_probe_stderr(
        provider, stderr)
    signals = (
        ("sandbox_backend", rb"(?i)(bubblewrap|bwrap|landlock|unshare|seccomp|"
                            rb"user.namespace|sandbox.{0,32}(?:denied|fail)|"
                            rb"operation not permitted)"),
        ("filesystem_permission", rb"(?i)(permission denied|read.only file system)"),
        ("provider_auth", rb"(?i)(authentication required|not logged in|"
                          rb"token.expired|invalid.token|unauthorized)"),
        ("approval", rb"(?i)(approval required|approval denied|soft.denied)"),
        ("network_transport", rb"(?i)(proxy error|certificate|TLS error|"
                              rb"connection reset|connection refused|DNS error|"
                              rb"network unreachable)"),
    )
    return {
        "exit_code": code,
        "stdout_exact_expected_marker": stdout.strip() == (
            b"CODEX_SMOKE_OK" if provider == "codex" else b"AGY_SMOKE_OK"),
        "stderr_bytes": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "benign_codex_alias_warning_count": benign_alias_warning_count,
        "stderr_signals": [name for name, pattern in signals
                           if re.search(pattern, effective_stderr)],
        "permission_line_shapes": _safe_permission_line_shapes(effective_stderr),
    }


def evaluate_probe(provider: str, code: int | None,
                   stdout: bytes, stderr: bytes = b"") -> ProbeReceipt:
    """Validate actual terminal response, NOT a prompt echoed in diagnostic logs."""
    if len(stdout) + len(stderr) > OUTPUT_LIMIT:
        raise RuntimeBlocked("Output too large")
    import json
    if code != 0:
        raise RuntimeBlocked("Provider invocation failed with nonzero exit")
    effective_stderr, _alias_warning_count = _effective_probe_stderr(
        provider, stderr)
    if re.search(rb"(?i)(permission denied|approval required|approval denied|"
                 rb"authentication required|not permitted|soft.denied|"
                 rb"read.only file system|operation not permitted)", effective_stderr):
        raise RuntimeBlocked("Provider permission/authentication denial")
    if provider == "agy":
        try:
            envelope = json.loads(stdout)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeBlocked("Invalid AGY JSON envelope") from exc
        if (not isinstance(envelope, dict)
                or envelope.get("status") != "SUCCESS"
                or envelope.get("error")):
            raise RuntimeBlocked("AGY terminal state is not SUCCESS")
        if str(envelope.get("response", "")).strip() != "AGY_SMOKE_OK":
            raise RuntimeBlocked("AGY smoke marker missing/ambiguous")
    elif provider == "codex":
        if stdout.decode("utf-8", errors="replace").strip() != "CODEX_SMOKE_OK":
            raise RuntimeBlocked("Codex terminal answer is not the expected smoke marker")
    else:
        raise RuntimeBlocked("Unknown provider")
    data = stdout + b"\n" + stderr
    return ProbeReceipt(provider, "READ_ONLY_MODEL_PROBE_PASS_ONLY", code,
                        hashlib.sha256(data).hexdigest(), len(data))
