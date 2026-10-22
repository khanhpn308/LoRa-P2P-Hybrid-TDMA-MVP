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
import time
from dataclasses import dataclass

IMAGE = re.compile(r"^sha256:[0-9a-f]{64}$")
VOLUME = re.compile(r"^lora-agent-(?:codex|agy)-auth-[a-z0-9][a-z0-9-]{0,42}$")
NETWORK = re.compile(r"^lora-agent-egress-[a-z0-9][a-z0-9-]{0,42}$")
NAME = re.compile(r"^lora-p1-probe-(?:codex|agy)-[a-f0-9]{8}$")
OUTPUT_LIMIT = 64_000
MAX_SECONDS = 240


class RuntimeBlocked(RuntimeError):
    """Container launch plan violates the verified interface contract."""


@dataclass(frozen=True)
class IsolatedCLI:
    provider: str
    image_id: str
    network: str
    profile_volume: str

    def command(self, snapshot: pathlib.Path, container_name: str,
                prompt: str) -> list[str]:
        if self.provider not in ("codex", "agy"):
            raise RuntimeBlocked("Unknown provider")
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
        flags = [
            "docker", "run", "--rm", "--init", "--pull=never",
            "--name", container_name,
            "--network", self.network,
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=96", "--memory=2g", "--cpus=1",
            "--read-only", "--tmpfs", "/tmp:rw,nosuid,nodev,size=256m",
            "--user", "10001:10001",
            "--env", "HOME=/home/agent",
            "--mount", f"type=bind,src={root},dst=/workspace,readonly",
            "--mount", f"type=volume,src={self.profile_volume},dst=/home/agent",
            "--workdir", "/workspace",
            self.image_id,
        ]
        if self.provider == "codex":
            return flags + ["codex", "exec", "--sandbox", "read-only",
                            "--ask-for-approval", "never", prompt]
        return flags + ["agy", "--sandbox", "-p", prompt,
                        "--output-format", "json", "--print-timeout", "3m"]


@dataclass(frozen=True)
class ProbeReceipt:
    provider: str
    state: str
    exit_code: int | None
    sha256: str
    output_bytes: int

    def as_json(self) -> dict:
        return vars(self)


def _run(argv: list[str], *, timeout: int, name: str) -> tuple[int | None, bytes]:
    """Only accepts argv constructed by IsolatedCLI, never arbitrary Agent commands."""
    if timeout < 1 or timeout > MAX_SECONDS or argv[:2] != ["docker", "run"]:
        raise RuntimeBlocked("Invalid bounded Docker invocation")
    try:
        process = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                   start_new_session=True)
    except OSError as exc:
        raise RuntimeBlocked("Docker cannot start: " + type(exc).__name__) from exc
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
        # Kill ONLY the uniquely named container we created (not a generic cleanup).
        try:
            subprocess.run(["docker", "kill", name],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise RuntimeBlocked("Provider probe timed out; container cleanup attempted") from exc
    combined = stdout + b"\n" + stderr
    if len(combined) > OUTPUT_LIMIT:
        raise RuntimeBlocked("Provider output exceeded capture budget")
    return process.returncode, combined


def evaluate_probe(provider: str, code: int | None, output: bytes) -> ProbeReceipt:
    if len(output) > OUTPUT_LIMIT:
        raise RuntimeBlocked("Output too large")
    import json
    if code != 0:
        raise RuntimeBlocked("Provider invocation failed with nonzero exit")
    # Never write provider output to a manifest. Only a SHA/length is returned.
    if provider == "agy":
        # Stderr is not JSON: separate it by reading the envelope prefix from
        # the combined payload. Only one response envelope is accepted.
        raw = output.split(b"\n", 1)[0]
        try:
            envelope = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RuntimeBlocked("Invalid AGY JSON envelope") from exc
        if (not isinstance(envelope, dict)
                or envelope.get("status") != "SUCCESS"
                or envelope.get("error")):
            raise RuntimeBlocked("AGY terminal state is not SUCCESS")
        if "AGY_SMOKE_OK" not in str(envelope.get("response", "")):
            raise RuntimeBlocked("AGY smoke marker missing")
    elif provider == "codex":
        if b"CODEX_SMOKE_OK" not in output:
            raise RuntimeBlocked("Codex smoke marker missing")
    else:
        raise RuntimeBlocked("Unknown provider")
    return ProbeReceipt(provider, "READ_ONLY_MODEL_PROBE_PASS_ONLY", code,
                        hashlib.sha256(output).hexdigest(), len(output))
