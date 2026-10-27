#!/usr/bin/env python3
"""Offline-first, read-only developer diagnostics for Native Harness Fast Lane.

No authentication tokens, command stdout/stderr or private-key contents are printed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON = (3, 10)
PROFILES = ("core", "firmware", "infra", "all")


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


def collect(repo: Path = ROOT, profile: str = "core",
            check_auth: bool = False) -> dict:
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
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

    for path in ("AGENTS.md", ".github/copilot-instructions.md",
                 "docs/development/harness-fast-lane.md",
                 "docs/development/harness-quality-gates.md",
                 ".agents/agents/harness-coordinator.md"):
        add("config:" + path, (repo / path).is_file(), True,
            "Repository configuration present", "Missing repository configuration",
            "Sync main and verify checkout; do not generate fake agent config.")

    codex, agy = shutil.which("codex"), shutil.which("agy")
    add("codex_cli", bool(codex), False,
        "Codex CLI found", "Codex CLI not found",
        "Install via the provider's official instructions if you choose Codex.")
    add("agy_cli", bool(agy), False,
        "AGY CLI found", "AGY CLI not found",
        "Install via official instructions if you choose AGY.")
    add("ai_provider", bool(codex or agy), True,
        "At least one AI CLI present", "Neither codex nor agy is available",
        "Install at least one CLI and authenticate it manually.")

    needs_docker = profile in ("firmware", "infra", "all")
    if needs_docker:
        docker = shutil.which("docker")
        add("docker_cli", bool(docker), True,
            "Docker CLI installed", "Docker CLI missing",
            "Install Docker Engine in WSL2/Linux; Docker Desktop is optional.")
        daemon = bool(docker) and probe(["docker", "info", "--format",
                                         "{{.ServerVersion}}"], 15)
        add("docker_daemon", daemon, True, "Docker daemon accessible without sudo",
            "Docker daemon/socket unavailable to current user",
            "Check systemd/service and socket privileges; do not chmod 666 docker.sock.")
        if profile in ("infra", "all"):
            add("docker_compose", bool(docker) and daemon and
                probe(["docker", "compose", "version"]), True,
                "Docker Compose plugin available", "Docker Compose plugin unavailable",
                "Install docker-compose-plugin from the supported repository.")
        if profile in ("firmware", "all"):
            version_file = repo / "firmware" / "esp-idf-version.txt"
            try:
                pin = version_file.read_text(encoding="utf-8").strip()
            except OSError:
                pin = ""
            add("esp_idf_pin", pin == "v6.1", True, "Repository pins ESP-IDF v6.1",
                "ESP-IDF pin differs from expected v6.1 or is missing",
                "Do not upgrade SDK silently; inspect firmware/esp-idf-version.txt.")
            image_ok = bool(docker) and daemon and probe(
                ["docker", "image", "inspect", "espressif/idf:v6.1"], 15)
            add("esp_idf_image", image_ok, True,
                "ESP-IDF v6.1 image cached locally",
                "ESP-IDF v6.1 image missing or inaccessible",
                "After reviewing storage/network requirements: docker pull espressif/idf:v6.1")
    else:
        for name in ("docker_cli", "docker_daemon", "docker_compose",
                     "esp_idf_pin", "esp_idf_image"):
            checks.append(item(name, "SKIP", False, "Not required in core profile"))

    failures = [v["check"] for v in checks if v["required"] and v["status"] != "PASS"]
    return {"schema_version": 1, "profile": profile,
            "ready": not failures, "failed_required_checks": failures,
            "checks": checks,
            "limitations": [
                "This preflight does not establish Build, HIL, RF, TLS or security PASS.",
                "Offline auth configuration is not proof of a valid GitHub session.",
                "Full Access and agent isolation are not validated by repository files.",
            ]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="core")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--check-auth", action="store_true",
                        help="Opt-in gh auth status; may access GitHub")
    args = parser.parse_args(argv)
    report = collect(profile=args.profile, check_auth=args.check_auth)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"LoRa Harness doctor | profile={args.profile}")
        for result in report["checks"]:
            print(f"[{result['status']}] {result['check']}: {result['detail']}")
            if result["status"] in ("FAIL", "WARN") and result["hint"]:
                print(f"  Remedy: {result['hint']}")
        print("READY" if report["ready"] else "NOT_READY")
        print("Build/HIL/RF/security are NOT_VERIFIED by this doctor.")
    return 0 if report["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
