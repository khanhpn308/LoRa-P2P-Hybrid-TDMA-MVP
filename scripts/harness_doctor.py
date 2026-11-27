#!/usr/bin/env python3
"""Offline-first, read-only developer diagnostics for Native Harness Fast Lane.

No authentication tokens, command stdout/stderr or private-key contents are printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
PROFILES = ("core", "firmware", "backend", "web", "infra", "all")
FIRMWARE_TARGETS = ("gateway_master", "sensor_node")
_GO_VERSION_RE = re.compile(r"go(\d+\.\d+(?:\.\d+)?)")
_GOMOD_GO_RE = re.compile(r"^go\s+(\d+\.\d+(?:\.\d+)?)\s*$", re.MULTILINE)
_GIT_FILTER_RE = re.compile(r"^filter\.([^.\s]+)\.(?:clean|process)\s+\S")


def probe(argv: list[str], timeout: int = 10) -> bool:
    """Run a bounded fixed command; suppress output to avoid credential exposure."""
    try:
        completed = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        )
        return completed.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def probe_stdout(argv: list[str], timeout: int = 10) -> tuple[int | None, str]:
    """Run a bounded fixed command returning (returncode, stdout); suppress stderr."""
    try:
        completed = subprocess.run(
            argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
        )
        raw = completed.stdout or b""
        if isinstance(raw, bytes):
            text = raw[:8192].decode("utf-8", errors="replace")
        else:
            text = str(raw)[:8192]
        return completed.returncode, text
    except (OSError, subprocess.TimeoutExpired):
        return None, ""


def item(name: str, status: str, required: bool, detail: str, hint: str = "") -> dict:
    return {"check": name, "status": status, "required": required,
            "detail": detail, "hint": hint}


def auth_configured() -> bool:
    """Presence only; never open hosts.yml or read token values."""
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return True
    config = os.environ.get("GH_CONFIG_DIR")
    base = Path(config).expanduser() if config else Path.home() / ".config" / "gh"
    return (base / "hosts.yml").is_file()


def _no_symlink_components(repo: Path, relative: str) -> bool:
    root = repo.resolve()
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            return False
    return current.is_file() and current.resolve().is_relative_to(root)


def _find_off_path_binary(candidate: Path) -> str | None:
    try:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    except OSError:
        pass
    return None


def _parse_go_version_from_bin(go_bin: str) -> str | None:
    rc, out = probe_stdout([go_bin, "version"], timeout=10)
    if rc != 0:
        return None
    m = _GO_VERSION_RE.search(out)
    return m.group(1) if m else None


def _env_isolation_ok() -> tuple[bool, str]:
    prod_flags = []
    for var in ("LORA_ALLOW_PROD_DB", "LORA_ALLOW_RF_TX"):
        val = os.environ.get(var, "").strip().lower()
        if val in ("1", "true", "yes", "on"):
            prod_flags.append(var)
    for var in ("LORA_ENV", "APP_ENV"):
        val = os.environ.get(var, "").strip().lower()
        if val in ("prod", "production"):
            prod_flags.append(f"{var}={val}")
    if prod_flags:
        return False, "Unsafe production/RF environment override active: " + ", ".join(prod_flags)
    return True, "Dev/test isolation defaults active; no deploy/flash/RF/prod overrides"


def build_role_capabilities(
    *,
    ai_ok: bool,
    codex_path: str | None,
    agy_path: str | None,
    docker_ok: bool,
    esp_idf_ok: bool,
    mcp_sdk_ok: bool,
) -> list[dict]:
    """Publish explicit role capability, invocation, prerequisites and isolation boundaries (H2-TOL-01/OD-04)."""
    return [
        {
            "role": "coordinator",
            "owner": "Owner / Native Fast Lane Coordinator",
            "invocation": "AGENTS.md + .agents/agents/harness-coordinator.md (Chay Issue #N / Nghiem thu PR #N)",
            "prerequisites": ["AGENTS.md G0 PASS", "gh auth", "ai_provider (agy or codex)"],
            "permissions": {"read": "repo + GH Issue/PR", "write": "planning/handoff only (or explicit Worker fallback)", "network": "gh CLI only", "credentials": "user gh session; no secret echo"},
            "isolation_mode": "operator_cli_context_only_no_os_sandbox",
            "status": "AVAILABLE_SUPERVISED_ONLY" if ai_ok else "UNAVAILABLE_BLOCKED",
        },
        {
            "role": "worker",
            "owner": "Scoped Worker (AGY interactive or Codex CLI)",
            "invocation": "Native AGY/Codex session or scripts/agent_harness/adapters/codex.py",
            "prerequisites": ["G0 agent_context.py", "Host-selected Rule IDs", "isolated Issue branch/worktree"],
            "permissions": {"read": "candidate worktree + injected rules", "write": "allowed Issue paths only (codex --sandbox workspace-write)", "network": "none in offline build boundary", "credentials": "none"},
            "isolation_mode": "workspace_write_or_operator_supervised_not_vm_sandbox",
            "status": "AVAILABLE_SUPERVISED_ONLY" if (codex_path or agy_path) else "UNAVAILABLE_BLOCKED",
        },
        {
            "role": "host_verifier",
            "owner": "Trusted Host Deterministic Gates",
            "invocation": "scripts/agent_harness/{agent_context.py,quality_gates.py,pr_review.py,scope.py}",
            "prerequisites": ["Python >= 3.10", "git", "clean git filter config"],
            "permissions": {"read": "candidate + external evidence dir", "write": "external evidence dir only", "network": "gh read-only in pr_review.py", "credentials": "gh user session only"},
            "isolation_mode": "host_deterministic_fail_closed",
            "status": "AVAILABLE",
        },
        {
            "role": "auditor",
            "owner": "Fresh Independent Auditor",
            "invocation": "invoke_subagent (Fresh-Independent-Auditor) or pr_review.py --auto-audit (adapters/antigravity.py)",
            "prerequisites": ["agy CLI for headless auto-audit or native invoke_subagent", "frozen diff + evidence inventory"],
            "permissions": {"read": "frozen snapshot/evidence only", "write": "NONE (read-only; evidence mutation fails closed)", "network": "none during review", "credentials": "none"},
            "isolation_mode": "read_only_context_separated_snapshot",
            "status": "AVAILABLE" if agy_path else "UNAVAILABLE_HEADLESS_FAIL_CLOSED",
        },
        {
            "role": "build_boundary",
            "owner": "Host Firmware Build Sandbox",
            "invocation": "scripts/agent_harness/toolchains/resolver.py / p1/runtime_boundary.py",
            "prerequisites": ["Docker engine", "espressif/idf:v6.1 image", "firmware managed_components cache"],
            "permissions": {"read": "worktree bind mount", "write": "worktree build dir + tmpfs /tmp", "network": "none (--network=none)", "credentials": "none (--cap-drop=ALL, --read-only)"},
            "isolation_mode": "docker_network_none_readonly_cap_drop",
            "status": "AVAILABLE" if (docker_ok and esp_idf_ok) else "UNAVAILABLE_BLOCKED",
        },
        {
            "role": "mcp_readonly_bridge",
            "owner": "Optional Read-Only MCP Host Bridge",
            "invocation": "scripts/agent_harness/mcp_server.py (opt-in via --install-mcp)",
            "prerequisites": ["mcp==2.3.0 in ~/.local/share/lora-harness/mcp-venv"],
            "permissions": {"read": "preflight/status/verify_candidate", "write": "NONE (read-only P1 bridge)", "network": "gh read-only in preflight", "credentials": "none"},
            "isolation_mode": "read_only_3_tools_no_write",
            "status": "AVAILABLE_OPTIONAL" if mcp_sdk_ok else "OPTIONAL_NOT_CONFIGURED",
        },
    ]


def collect(repo: Path = ROOT, profile: str = "core",
            check_auth: bool = False) -> dict:
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    repo = repo.resolve()
    checks: list[dict] = []

    def add(name: str, ok: bool, required: bool, success: str,
            failure: str, hint: str = "") -> None:
        checks.append(item(name, "PASS" if ok else ("FAIL" if required else "WARN"),
                           required, success if ok else failure, "" if ok else hint))

    add("python", sys.version_info >= MIN_PYTHON, True,
        "Python version supported", "Python 3.10 or newer required",
        "Install Python 3 with your OS package manager.")

    git = shutil.which("git")
    add("git", bool(git) and probe(["git", "--version"]), True,
        "Git executable available", "Git is unavailable",
        "Install git (Ubuntu: sudo apt-get install git).")

    is_repo = bool(git) and probe(
        ["git", "-C", str(repo), "rev-parse", "--show-toplevel"])
    add("repository", is_repo, True, "Git checkout detected",
        "Not inside a Git checkout", "Run from a cloned repository checkout.")

    if is_repo:
        try:
            dirty = subprocess.run(
                ["git", "-C", str(repo), "status", "--porcelain",
                 "--untracked-files=normal"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=10, check=False,
            )
            clean = dirty.returncode == 0 and not dirty.stdout
        except (OSError, subprocess.TimeoutExpired):
            clean = False
        add("working_tree", clean, False,
            "No local changes detected", "Local changes exist or status unavailable",
            "Preserve changes; never reset/stash automatically.")

        # Detect unsafe clean/process Git filters (matches quality_gates.py policy).
        rc_flt, out_flt = probe_stdout(
            ["git", "-C", str(repo), "config", "--get-regexp", r"^filter\..*\.(clean|process)$"],
            timeout=10,
        )
        unsafe_filters = [
            line for line in out_flt.splitlines()
            if (m := _GIT_FILTER_RE.match(line.strip())) is not None and m.group(1) != "lfs"
        ]
        filter_ok = rc_flt in (0, 1) and not unsafe_filters
        add("git_clean_filters", filter_ok, True,
            "No unsafe Git clean/process filters configured",
            "Unsupported Git clean/process filter detected",
            "Remove non-LFS filter.*.clean/process before running Host gates.")

    agents_ok = _no_symlink_components(repo, "AGENTS.md")
    add("agents_context_integrity", agents_ok, True,
        "AGENTS.md is a regular non-symlinked file",
        "AGENTS.md missing or uses symlinked path",
        "Ensure AGENTS.md is a tracked regular file inside the checkout.")

    gh = shutil.which("gh")
    add("gh", bool(gh), True, "GitHub CLI present", "GitHub CLI missing",
        "Install gh using the supported OS package.")
    configured = auth_configured()
    add("gh_auth_config", configured, True, "GitHub auth configuration detected; "
        "token validity NOT_VERIFIED", "GitHub auth not configured",
        "Run gh auth login as your normal WSL/Linux user (not root).")
    if check_auth:
        add("gh_auth_online", bool(gh) and probe(["gh", "auth", "status"], 15),
            True, "gh auth status succeeded", "gh auth status failed",
            "Check account/network; run gh auth login if needed.")
    else:
        checks.append(item("gh_auth_online", "SKIP", False,
                           "NOT_VERIFIED: use --check-auth to validate online"))

    for path in ("AGENTS.md",
                 "docs/development/harness-fast-lane.md",
                 "docs/development/harness-quality-gates.md",
                 ".agents/agents/harness-coordinator.md"):
        add("config:" + path, (repo / path).is_file(), True,
            "Repository configuration present", "Missing repository configuration",
            "Sync main and verify checkout; do not generate fake agent config.")

    codex, agy = shutil.which("codex"), shutil.which("agy")
    codex_off_path = None if codex else _find_off_path_binary(Path.home() / ".local" / "bin" / "codex")
    if codex:
        add("codex_cli", True, False, "Codex CLI found on PATH", "")
    elif codex_off_path:
        add("codex_cli", False, False, "",
            f"Codex CLI not on PATH (found off-PATH at {codex_off_path})",
            "Add ~/.local/bin to PATH if invoking Codex CLI.")
    else:
        add("codex_cli", False, False, "", "Codex CLI not found",
            "Install via the provider's official instructions if you choose Codex.")

    add("agy_cli", bool(agy), False,
        "AGY CLI found", "AGY CLI not found",
        "Install via official instructions if you choose AGY.")
    ai_ok = bool(codex or agy)
    add("ai_provider", ai_ok, True,
        "At least one AI CLI present on PATH", "Neither codex nor agy is available on PATH",
        "Install at least one CLI (or add ~/.local/bin to PATH) and authenticate it manually.")

    env_ok, env_detail = _env_isolation_ok()
    add("env_isolation", env_ok, True, env_detail, env_detail,
        "Unset production DB / RF TX overrides before running Harness bootstrap or verification.")

    needs_docker = profile in ("firmware", "backend", "infra", "all")
    docker = shutil.which("docker") if needs_docker else None
    daemon = False
    esp_idf_image_ok = False
    if needs_docker:
        add("docker_cli", bool(docker), profile != "backend",
            "Docker CLI installed", "Docker CLI missing",
            "Install Docker Engine in WSL2/Linux; Docker Desktop is optional.")
        daemon = bool(docker) and probe(["docker", "info", "--format",
                                         "{{.ServerVersion}}"], 15)
        add("docker_daemon", daemon, profile != "backend",
            "Docker daemon accessible without sudo",
            "Docker daemon/socket unavailable to current user",
            "Check systemd/service and socket privileges; do not chmod 666 docker.sock.")
        if profile in ("infra", "all"):
            add("docker_compose", bool(docker) and daemon and
                probe(["docker", "compose", "version"]), True,
                "Docker Compose plugin available", "Docker Compose plugin unavailable",
                "Install docker-compose-plugin from the supported repository.")
        else:
            checks.append(item("docker_compose", "SKIP", False, f"Not required in {profile} profile"))

        if profile in ("firmware", "all"):
            version_file = repo / "firmware" / "esp-idf-version.txt"
            try:
                pin = version_file.read_text(encoding="utf-8").strip()
            except OSError:
                pin = ""
            add("esp_idf_pin", pin == "v6.1", True, "Repository pins ESP-IDF v6.1",
                "ESP-IDF pin differs from expected v6.1 or is missing",
                "Do not upgrade SDK silently; inspect firmware/esp-idf-version.txt.")
            esp_idf_image_ok = bool(docker) and daemon and probe(
                ["docker", "image", "inspect", "espressif/idf:v6.1"], 15)
            add("esp_idf_image", esp_idf_image_ok, True,
                "ESP-IDF v6.1 image cached locally",
                "ESP-IDF v6.1 image missing or inaccessible",
                "After reviewing storage/network requirements: docker pull espressif/idf:v6.1")

            # Check firmware managed_components dependency cache against dependencies.lock.
            lock_targets = [
                t for t in FIRMWARE_TARGETS
                if (repo / "firmware" / t / "dependencies.lock").is_file()
            ]
            if lock_targets:
                missing_targets = []
                for target in lock_targets:
                    tdir = repo / "firmware" / target
                    managed = tdir / "managed_components"
                    lock_txt = (tdir / "dependencies.lock").read_text(encoding="utf-8", errors="ignore")
                    if not managed.is_dir() or not any(managed.iterdir()):
                        missing_targets.append(target)
                    elif "espressif/mqtt" in lock_txt and not (managed / "espressif__mqtt").is_dir():
                        missing_targets.append(f"{target}(espressif__mqtt)")
                add("firmware_deps_cache", not missing_targets, True,
                    "Firmware managed_components cache present for offline builds",
                    "Missing firmware managed_components cache: " + ", ".join(missing_targets),
                    "Hydrate dependencies with explicit authorization before running --network=none builds.")
            else:
                checks.append(item("firmware_deps_cache", "SKIP", False,
                                   "No firmware dependencies.lock found in checkout"))
        else:
            for name in ("esp_idf_pin", "esp_idf_image", "firmware_deps_cache"):
                checks.append(item(name, "SKIP", False, f"Not required in {profile} profile"))
    else:
        for name in ("docker_cli", "docker_daemon", "docker_compose",
                     "esp_idf_pin", "esp_idf_image", "firmware_deps_cache"):
            checks.append(item(name, "SKIP", False, f"Not required in {profile} profile"))

    # Backend (Go) pin & toolchain checks
    if profile in ("backend", "all"):
        go_ver_file = repo / ".go-version"
        go_mod_file = repo / "backend-go" / "go.mod"
        go_pin = ""
        try:
            go_pin = go_ver_file.read_text(encoding="utf-8").strip()
        except OSError:
            go_pin = ""
        go_mod_ver = ""
        try:
            m = _GOMOD_GO_RE.search(go_mod_file.read_text(encoding="utf-8"))
            go_mod_ver = m.group(1) if m else ""
        except OSError:
            go_mod_ver = ""
        go_pin_ok = bool(go_pin) and go_pin == go_mod_ver
        add("go_pin", go_pin_ok, True,
            f"Repository pins Go {go_pin} consistently (.go-version & go.mod)",
            f"Go version pin missing or mismatched (.go-version={go_pin!r}, go.mod={go_mod_ver!r})",
            "Align .go-version and backend-go/go.mod before building.")

        host_go_bin = shutil.which("go") or _find_off_path_binary(Path("/usr/local/go/bin/go"))
        host_go_ver = _parse_go_version_from_bin(host_go_bin) if host_go_bin else None
        host_go_exact = bool(go_pin) and host_go_ver == go_pin
        if host_go_ver is None:
            add("go_host_version", False, False, "",
                "Host go binary not found",
                f"Use pinned Docker golang:{go_pin or '1.27.3'}-alpine image.")
        elif not host_go_exact:
            add("go_host_version", False, False, "",
                f"Host Go version drift: {host_go_ver} != pinned {go_pin} ({host_go_bin})",
                f"Do not rely on drifted host Go; use Docker golang:{go_pin}-alpine.")
        else:
            add("go_host_version", True, False, f"Host Go matches pinned {go_pin}", "")

        go_image = f"golang:{go_pin}-alpine" if go_pin else "golang:1.27.3-alpine"
        go_docker_ok = bool(docker) and daemon and probe(
            ["docker", "image", "inspect", go_image], 15)
        add("go_docker_image", go_docker_ok, False,
            f"Pinned Go container image cached ({go_image})",
            f"Pinned Go container image missing ({go_image})",
            f"After reviewing network/storage requirements: docker pull {go_image}")

        add("go_toolchain", go_pin_ok and (host_go_exact or go_docker_ok), True,
            f"Pinned Go {go_pin} toolchain available",
            f"No matching pinned Go {go_pin or '?'} toolchain (host drift/absent and {go_image} missing)",
            f"Ensure {go_image} is cached or install exact Go {go_pin}.")
    else:
        for name in ("go_pin", "go_host_version", "go_docker_image", "go_toolchain"):
            checks.append(item(name, "SKIP", False, f"Not required in {profile} profile"))

    # Web (Next.js) dependency cache checks
    if profile in ("web", "all"):
        web_dir = repo / "clients" / "web-dashboard"
        pkg_ok = (web_dir / "package.json").is_file() and (web_dir / "package-lock.json").is_file()
        add("web_lockfile", pkg_ok, True,
            "Web package.json and package-lock.json present",
            "Missing clients/web-dashboard package.json or package-lock.json",
            "Verify checkout integrity for clients/web-dashboard.")
        node_bin = shutil.which("node")
        npm_bin = shutil.which("npm")
        add("node_cli", bool(node_bin) and bool(npm_bin), True,
            "Node.js and npm available", "Node.js or npm missing on PATH",
            "Install pinned Node.js runtime before running web checks.")
        node_mods = web_dir / "node_modules"
        web_deps_ok = node_mods.is_dir() and any(node_mods.iterdir())
        add("web_deps_cache", web_deps_ok, True,
            "Web node_modules dependency cache present",
            "Missing clients/web-dashboard/node_modules dependency cache",
            "Run 'npm ci --prefix clients/web-dashboard' only when dependency installation is authorized.")
    else:
        for name in ("web_lockfile", "node_cli", "web_deps_cache"):
            checks.append(item(name, "SKIP", False, f"Not required in {profile} profile"))

    mcp_py = Path.home() / ".local/share/lora-harness/mcp-venv/bin/python"
    mcp_sdk_ok = _find_off_path_binary(mcp_py) is not None
    capabilities = build_role_capabilities(
        ai_ok=ai_ok,
        codex_path=codex,
        agy_path=agy,
        docker_ok=bool(docker) and daemon,
        esp_idf_ok=esp_idf_image_ok,
        mcp_sdk_ok=mcp_sdk_ok,
    )

    failures = [v["check"] for v in checks if v["required"] and v["status"] != "PASS"]
    return {"schema_version": 1, "profile": profile, "repo": str(repo),
            "ready": not failures, "failed_required_checks": failures,
            "checks": checks, "capabilities": capabilities,
            "limitations": [
                "This preflight does not establish Build, HIL, RF, TLS or security PASS.",
                "Offline auth configuration is not proof of a valid GitHub session.",
                "Full Access / Turbo CLI mode is NOT an OS/filesystem/network sandbox.",
                "Bootstrap and diagnostics never install packages, deploy, flash, or transmit RF by default.",
            ]}


def run_smoke_checks(repo: Path, profile: str) -> dict:
    """Execute read-only, non-destructive baseline smoke checks (no auto-install/network)."""
    repo = repo.resolve()
    smoke_commands: list[tuple[str, list[str]]] = [
        ("g0_agent_context", [sys.executable, str(ROOT / "scripts/agent_harness/agent_context.py"), "--repo", str(repo)]),
        ("verify_structure", [sys.executable, str(repo / "scripts/verify_structure.py")]),
        ("quality_gates_head", [sys.executable, str(ROOT / "scripts/agent_harness/quality_gates.py"), "--repo", str(repo), "--base", "HEAD"]),
    ]
    if profile in ("firmware", "all"):
        smoke_commands.append((
            "toolchain_check",
            [sys.executable, str(ROOT / "scripts/agent_harness/toolchains/check.py"),
             "--version", "6.1", "--repo", str(repo), "--check-deps"],
        ))
    results: list[dict] = []
    all_ok = True
    for name, cmd in smoke_commands:
        rc, out = probe_stdout(cmd, timeout=60)
        passed = rc == 0
        if not passed:
            all_ok = False
        results.append({
            "smoke": name,
            "status": "PASS" if passed else "FAIL",
            "exit_code": rc,
            "command": [Path(cmd[0]).name, *[Path(c).name if i == 1 else c for i, c in enumerate(cmd[1:], start=1)]],
            "summary": out.strip()[:240],
        })
    return {"executed": True, "passed": all_ok, "checks": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="core")
    parser.add_argument("--repo", type=Path, default=ROOT,
                        help="Target repository checkout path (defaults to trusted root)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--check-auth", action="store_true",
                        help="Opt-in gh auth status; may access GitHub")
    parser.add_argument("--smoke", action="store_true",
                        help="Run read-only baseline smoke checks without modifying files")
    args = parser.parse_args(argv)
    report = collect(repo=args.repo, profile=args.profile, check_auth=args.check_auth)
    if args.smoke:
        smoke = run_smoke_checks(repo=args.repo, profile=args.profile)
        report["smoke"] = smoke
        if not smoke["passed"]:
            report["ready"] = False
            report["failed_required_checks"].extend(
                [f"smoke:{s['smoke']}" for s in smoke["checks"] if s["status"] != "PASS"]
            )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"LoRa Harness doctor | profile={args.profile} | repo={report['repo']}")
        for result in report["checks"]:
            print(f"[{result['status']}] {result['check']}: {result['detail']}")
            if result["status"] in ("FAIL", "WARN") and result["hint"]:
                print(f"  Remedy: {result['hint']}")
        if "smoke" in report:
            for s in report["smoke"]["checks"]:
                print(f"[{s['status']}] smoke:{s['smoke']} (exit={s['exit_code']})")
        print("READY" if report["ready"] else "NOT_READY")
        print("Build/HIL/RF/security are NOT_VERIFIED by this doctor.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
