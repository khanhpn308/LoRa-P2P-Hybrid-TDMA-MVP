"""ESP-IDF Docker-first toolchain resolver, with explicitly permitted native fallback.

No host-specific paths or network downloads. Version and image checks fail closed.
Builds are NOT an isolation boundary for the Codex Worker itself.
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass

VERSION = re.compile(r"^v?(\d+\.\d+(?:\.\d+)?)$")
IDENTIFIED_VERSION = re.compile(r"^ESP-IDF\s+v?(\d+\.\d+(?:\.\d+)?)\s*$")
MODES = {"container_first", "container_only", "native_first", "native_only"}
CONTAINER_BASE = "espressif/idf"


class ToolchainError(RuntimeError):
    """Toolchain missing, untrusted, or version-mismatched."""


def normalize_version(value: str) -> str:
    match = VERSION.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise ToolchainError("Approved ESP-IDF version must be exact X.Y or X.Y.Z (not latest or release branch)")
    return match.group(1)


def load_project_version(repo: pathlib.Path) -> str:
    """Use firmware/esp-idf-version.txt as the single authoritative toolchain release."""
    path = repo / "firmware" / "esp-idf-version.txt"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ToolchainError("Missing firmware/esp-idf-version.txt") from exc
    if not value.startswith("v"):
        raise ToolchainError("Baseline must use exact vX.Y or vX.Y.Z tag")
    return normalize_version(value)


def actual_version(output: str, expected: str) -> str:
    versions = [m.group(1) for line in output.splitlines()
                if (m := IDENTIFIED_VERSION.fullmatch(line.strip())) is not None]
    if len(versions) != 1 or versions[0] != expected:
        raise ToolchainError(f"ESP-IDF version is missing or differs from approved {expected}")
    return versions[0]


def check(args: list[str], *, cwd: pathlib.Path | None = None,
          timeout: int = 45) -> str:
    try:
        p = subprocess.run(args, cwd=cwd, text=True, capture_output=True,
                           timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolchainError(f"Toolchain command unavailable/timed out: {args[0]}") from exc
    if p.returncode:
        # A Docker error (especially exit 125) is usually explained by stderr.
        # Expose only a bounded, redacted diagnostic; do not log environment
        # variables, full command arguments or untrusted multiline output.
        diagnostic = p.stderr.strip()[-1200:]
        diagnostic = re.sub(
            r"(?i)(authorization|api[_-]?key|token|password|secret)\s*[:=]\s*\S+",
            r"\1=[REDACTED]", diagnostic,
        )
        diagnostic = re.sub(r"[\r\n\t]+", " ", diagnostic)
        if not diagnostic:
            diagnostic = "No Docker/tool stderr was returned"
        raise ToolchainError(
            f"Toolchain check failed: {args[0]}, exit {p.returncode}: {diagnostic}"
        )
    if len(p.stdout) > 8192:
        raise ToolchainError("Toolchain version/inspect response exceeds limit")
    return p.stdout.strip()


@dataclass(frozen=True)
class ResolvedIDF:
    provider: str
    version: str
    identity: str
    executable: str | None = None
    idf_path: pathlib.Path | None = None
    image: str | None = None

    def command(self, repo: pathlib.Path, project: pathlib.Path, *args: str) -> list[str]:
        """Return an argument-vector, not a shell command, suitable for Host subprocess."""
        root = repo.resolve(strict=True)
        folder = project.resolve(strict=True)
        if folder != root and root not in folder.parents:
            raise ToolchainError("Project must be inside the approved worktree")
        relative = folder.relative_to(root)
        if self.provider == "docker":
            if not self.image or not self.identity:
                raise ToolchainError("Docker image identity not verified")
            if os.name != "posix" or not hasattr(os, "getuid"):
                raise ToolchainError("Docker runner requires supported POSIX host")
            return [
                "docker", "run", "--rm", "--pull=never",
                "--network=none", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--pids-limit=256",
                "--memory=6g", "--cpus=2", "--read-only",
                "--tmpfs=/tmp:rw,nosuid,nodev,size=1g",
                "--user", f"{os.getuid()}:{os.getgid()}",
                "--env", "HOME=/tmp",
                "--mount", f"type=bind,src={root},dst=/workspace,rw",
                "--workdir", "/workspace/" + relative.as_posix(),
                self.identity, "idf.py", *args,
            ]
        if self.provider == "native-path":
            if not self.executable:
                raise ToolchainError("Native executable not verified")
            return [self.executable, *args]
        if self.provider == "native-export":
            if not self.idf_path:
                raise ToolchainError("Native IDF_PATH not verified")
            # IDF export.sh is sourced in the SAME subprocess as idf.py.
            # Positional shell parameters protect paths with spaces from injection.
            return [
                "bash", "--noprofile", "--norc", "-c",
                'source "$1/export.sh" >/dev/null && shift && exec "$@"',
                "--", str(self.idf_path), "idf.py", *args,
            ]
        raise ToolchainError("Unknown toolchain provider")

    def evidence(self) -> dict:
        data = {"provider": self.provider, "version": self.version, "identity": self.identity}
        if self.image:
            data["image"] = self.image
        return data


def _docker(expected: str, repo: pathlib.Path) -> ResolvedIDF:
    if shutil.which("docker") is None:
        raise ToolchainError("Docker CLI missing")
    if os.name != "posix" or not hasattr(os, "getuid"):
        raise ToolchainError("Docker toolchain requires POSIX/WSL2")
    image = f"{CONTAINER_BASE}:v{expected}"
    # Do not pull an arbitrary or floating image. Installation is operator-owned.
    identity = check(["docker", "image", "inspect", "--format", "{{.Id}}", image])
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ToolchainError("Docker image identity is not a SHA-256 image ID")
    candidate = ResolvedIDF("docker", expected, identity, image=image)
    line = check(candidate.command(repo, repo, "--version"), cwd=repo)
    actual_version(line, expected)
    return candidate


def _native(expected: str, repo: pathlib.Path,
            environment: dict[str, str]) -> ResolvedIDF:
    executable = shutil.which("idf.py")
    if executable:
        candidate = ResolvedIDF(
            "native-path", expected,
            identity=str(pathlib.Path(executable).resolve()),
            executable=executable,
        )
        try:
            line = check(candidate.command(repo, repo, "--version"), cwd=repo)
            actual_version(line, expected)
            return candidate
        except ToolchainError:
            # A wrong-version PATH must not shadow an explicitly supplied IDF_PATH.
            pass

    # Native autodetection is deterministic, not a recursive traversal of HOME.
    # Path may come from VS Code ESP-IDF integration or a local session.
    for name in ("IDF_PATH", "ESP_IDF_ROOT"):
        value = environment.get(name)
        if not value:
            continue
        root = pathlib.Path(value).expanduser().resolve()
        if not (root / "export.sh").is_file() or not (root / "tools" / "idf.py").is_file():
            continue
        candidate = ResolvedIDF("native-export", expected,
                                identity=str(root), idf_path=root)
        line = check(candidate.command(repo, repo, "--version"), cwd=repo)
        actual_version(line, expected)
        return candidate
    raise ToolchainError("No matching activated idf.py or valid IDF_PATH/ESP_IDF_ROOT")


def resolve(repo: pathlib.Path, *, version: str, mode: str = "container_first",
            allow_native_fallback: bool = False,
            environment: dict[str, str] | None = None) -> ResolvedIDF:
    """Fail closed. Container-first -> native only with explicit opt-in."""
    expected = normalize_version(version)
    if mode not in MODES:
        raise ToolchainError(f"Unrecognized toolchain mode: {mode}")
    root = repo.resolve(strict=True)
    env = os.environ if environment is None else environment
    plans = {
        "container_only": ("docker",),
        "native_only": ("native",),
        "native_first": ("native", "docker"),
        "container_first": ("docker", "native") if allow_native_fallback else ("docker",),
    }
    failures = []
    for provider in plans[mode]:
        try:
            return (_docker(expected, root) if provider == "docker"
                    else _native(expected, root, env))
        except ToolchainError as exc:
            failures.append(f"{provider}: {exc}")
    raise ToolchainError("; ".join(failures))
