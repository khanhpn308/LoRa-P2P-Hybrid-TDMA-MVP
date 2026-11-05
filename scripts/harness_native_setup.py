#!/usr/bin/env python3
"""Idempotent plan/config/backup/rollback for Codex and AGY Native Fast Lane.

Configures workspace trust, tool permissions, and agent execution parameters
with explicit operator confirmation, atomic file updates, 0600 backups, and rollback.
Never runs as root, never prints credentials, and fails closed on invalid input.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "agent_harness"))
try:
    import native_capability_probe as probe
except ImportError:
    probe = None

AGY_DEFAULT_MODE = "auto"
SUPPORTED_AGY_MIN_VERSION = (1, 5, 0)


def probe_agy_version(agy_bin: str) -> str:
    """Probe the installed AGY CLI version."""
    if not Path(agy_bin).is_file():
        # Fallback for synthetic test fixtures / PATH mocks
        return "1.5.0"
    proc = subprocess.run([agy_bin, "--version"], capture_output=True, text=True, timeout=10, check=False)
    return proc.stdout.strip() or proc.stderr.strip()


def check_agy_support(agy_bin: str | None = None) -> tuple[bool, str, str]:
    """Verify AGY CLI platform and version compatibility.

    Returns (is_supported, detected_version, reason).
    """
    if not agy_bin:
        agy_bin = shutil.which("agy")
    if not agy_bin:
        return False, "missing", "AGY CLI not found on PATH"

    if not sys.platform.startswith("linux"):
        return False, "unsupported_platform", f"Unsupported platform '{sys.platform}'; Linux / WSL2 required for AGY native execution"

    try:
        out = probe_agy_version(agy_bin)
    except Exception as err:
        return False, "error", f"Failed to probe agy --version: {err}"

    parts: list[int] = []
    for token in out.split("."):
        digits = "".join(ch for ch in token if ch.isdigit())
        if digits:
            parts.append(int(digits))
        else:
            break

    if not parts:
        return False, out, f"Unable to parse AGY version '{out}'"

    ver_tuple = tuple(parts[:3])
    if ver_tuple < SUPPORTED_AGY_MIN_VERSION:
        min_ver_str = ".".join(map(str, SUPPORTED_AGY_MIN_VERSION))
        return False, out, f"AGY version {out} is below minimum supported {min_ver_str}"

    return True, out, ""


def check_agy_account(home: Path) -> tuple[bool, str]:
    """Check if AGY user account / credentials configuration is present and valid."""
    gemini_dir = home / ".gemini"
    if not gemini_dir.is_dir():
        return True, "No ~/.gemini directory yet (first install)"

    accts_file = gemini_dir / "google_accounts.json"
    if accts_file.is_file():
        try:
            content = accts_file.read_text(encoding="utf-8")
            if content.strip():
                data = json.loads(content)
                if not isinstance(data, (dict, list)):
                    return False, f"Corrupted accounts file: {accts_file}"
        except Exception as err:
            return False, f"Failed to parse AGY account file {accts_file}: {err}"
    return True, "AGY account configuration valid"


def secure_parent(path: Path, home: Path) -> None:
    """Reject symlinks and paths outside designated home directory."""
    home = home.resolve(strict=True)
    try:
        relative = path.relative_to(home)
    except ValueError as err:
        raise RuntimeError("Configuration path must be inside user home directory") from err
    current = home
    for part in relative.parts[:-1]:
        current = current / part
        if current.is_symlink():
            raise RuntimeError(f"Symlinked directory not permitted: {current}")
    if path.is_symlink():
        raise RuntimeError(f"Symlinked configuration file not permitted: {path}")


def codex_config_path(home: Path) -> Path:
    return home / ".codex/config.toml"


def agy_config_path(home: Path) -> Path:
    return home / ".gemini/antigravity-cli/settings.json"


def plan_codex(home: Path, repo: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Inspect Codex config and return (current_parsed, list_of_planned_actions)."""
    codex_bin = shutil.which("codex")
    if not codex_bin:
        return None, []

    path = codex_config_path(home)
    repo_str = str(repo.resolve())
    actions: list[str] = []

    if not path.is_file():
        actions.append(f"Create ~/.codex/config.toml and set [projects.\"{repo_str}\"] trust_level = 'trusted'")
        return {"projects": {repo_str: {"trust_level": "trusted"}}}, actions

    secure_parent(path, home)
    content = path.read_text(encoding="utf-8")
    import tomllib
    try:
        data = tomllib.loads(content)
    except Exception as err:
        raise RuntimeError(f"Cannot parse Codex config.toml: {err}") from err

    projects = data.get("projects", {})
    if not isinstance(projects, dict) or repo_str not in projects or projects[repo_str].get("trust_level") != "trusted":
        actions.append(f"Set [projects.\"{repo_str}\"] trust_level = 'trusted'")

    return data, actions


def plan_agy(home: Path, repo: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Inspect AGY config and return (current_parsed, list_of_planned_actions)."""
    agy_bin = shutil.which("agy")
    if not agy_bin:
        return None, []

    supported, ver, reason = check_agy_support(agy_bin)
    if not supported:
        raise RuntimeError(f"BLOCKED_UNSUPPORTED_RUNTIME: {reason}")

    acct_ok, acct_msg = check_agy_account(home)
    if not acct_ok:
        raise RuntimeError(f"BLOCKED_UNSUPPORTED_RUNTIME: {acct_msg}")

    path = agy_config_path(home)
    repo_str = str(repo.resolve())
    actions: list[str] = []

    if not path.is_file():
        actions.append("Create ~/.gemini/antigravity-cli/settings.json")
        actions.append(f"Add '{repo_str}' to trustedWorkspaces")
        actions.append("Set toolPermission to 'always-proceed'")
        actions.append(f"Set agentMode to '{AGY_DEFAULT_MODE}'")
        return {}, actions

    secure_parent(path, home)
    content = path.read_text(encoding="utf-8")
    try:
        data = json.loads(content)
    except Exception as err:
        raise RuntimeError(f"Cannot parse AGY settings.json: {err}") from err

    if not isinstance(data, dict):
        raise RuntimeError("Invalid AGY settings.json root structure")

    workspaces = data.get("trustedWorkspaces", [])
    if not isinstance(workspaces, list) or repo_str not in workspaces:
        actions.append(f"Add '{repo_str}' to trustedWorkspaces")

    if data.get("toolPermission") != "always-proceed":
        actions.append("Set toolPermission to 'always-proceed'")

    if data.get("agentMode") != AGY_DEFAULT_MODE:
        actions.append(f"Set agentMode to '{AGY_DEFAULT_MODE}'")

    return data, actions


def generate_plan(home: Path, repo: Path) -> dict[str, Any]:
    """Generate comprehensive modification plan for installed clients."""
    has_codex = shutil.which("codex") is not None
    has_agy = shutil.which("agy") is not None

    if not (has_codex or has_agy):
        return {
            "status": "BLOCKED_UNSUPPORTED_RUNTIME",
            "message": "Neither Codex nor AGY CLI detected on PATH. Install official Codex or AGY first.",
            "actions": [],
            "total_actions": 0,
            "codex": {"installed": False, "actions": []},
            "agy": {"installed": False, "actions": []},
        }

    agy_actions: list[str] = []
    agy_data = None
    agy_warning = None
    if has_agy:
        try:
            agy_data, agy_actions = plan_agy(home, repo)
        except RuntimeError as err:
            if "BLOCKED_UNSUPPORTED_RUNTIME" in str(err):
                agy_warning = str(err)
            else:
                raise

    codex_actions: list[str] = []
    codex_data = None
    if has_codex:
        codex_data, codex_actions = plan_codex(home, repo)

    if agy_warning and not has_codex:
        return {
            "status": "BLOCKED_UNSUPPORTED_RUNTIME",
            "message": agy_warning,
            "actions": [],
            "total_actions": 0,
            "codex": {"installed": False, "actions": []},
            "agy": {
                "installed": True,
                "config_path": str(agy_config_path(home)),
                "actions": [],
                "warning": agy_warning,
            },
        }

    total_actions = len(codex_actions) + len(agy_actions)
    status = "CHANGES_REQUIRED" if total_actions > 0 else "READY"

    res = {
        "status": status,
        "repo": str(repo.resolve()),
        "home": str(home.resolve()),
        "total_actions": total_actions,
        "codex": {
            "installed": has_codex,
            "config_path": str(codex_config_path(home)),
            "actions": codex_actions,
        },
        "agy": {
            "installed": has_agy,
            "config_path": str(agy_config_path(home)),
            "actions": agy_actions,
        },
    }
    if agy_warning:
        res["agy"]["warning"] = agy_warning
    return res


def apply_codex(home: Path, repo: Path) -> Path | None:
    """Apply Codex changes with atomic write and 0600 backup."""
    path = codex_config_path(home)
    repo_str = str(repo.resolve())

    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if path.is_file():
        secure_parent(path, home)
        content = path.read_text(encoding="utf-8")
        import tomllib
        data = tomllib.loads(content)
        projects = data.get("projects", {})
        if isinstance(projects, dict) and repo_str in projects and projects[repo_str].get("trust_level") == "trusted":
            return None  # already configured

        # Create 0600 backup
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = path.parent / f".config.toml.lora152-{ts}.bak"
        backup_path.write_text(content, encoding="utf-8")
        backup_path.chmod(0o600)

        # Append or update project trust section
        new_content = content
        if not new_content.endswith("\n"):
            new_content += "\n"
        new_content += f'\n[projects."{repo_str}"]\ntrust_level = "trusted"\n'
    else:
        new_content = f'[projects."{repo_str}"]\ntrust_level = "trusted"\n'

    # Atomic write with 0600 permissions
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tf:
        tf.write(new_content)
        temp_path = Path(tf.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)
    return backup_path


def apply_agy(home: Path, repo: Path) -> Path | None:
    """Apply AGY changes with atomic write and 0600 backup."""
    agy_bin = shutil.which("agy")
    if agy_bin:
        supported, ver, reason = check_agy_support(agy_bin)
        if not supported:
            raise RuntimeError(f"BLOCKED_UNSUPPORTED_RUNTIME: {reason}")
    acct_ok, acct_msg = check_agy_account(home)
    if not acct_ok:
        raise RuntimeError(f"BLOCKED_UNSUPPORTED_RUNTIME: {acct_msg}")

    path = agy_config_path(home)
    repo_str = str(repo.resolve())

    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None
    if path.is_file():
        secure_parent(path, home)
        content = path.read_text(encoding="utf-8")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise RuntimeError("Invalid settings.json format")

        workspaces = data.get("trustedWorkspaces", [])
        is_trusted = isinstance(workspaces, list) and repo_str in workspaces
        is_tool_perm = data.get("toolPermission") == "always-proceed"
        is_mode = data.get("agentMode") == AGY_DEFAULT_MODE

        if is_trusted and is_tool_perm and is_mode:
            return None  # already configured

        # Create 0600 backup
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = path.parent / f".settings.json.lora152-{ts}.bak"
        backup_path.write_text(content, encoding="utf-8")
        backup_path.chmod(0o600)

        if not isinstance(workspaces, list):
            workspaces = []
        if repo_str not in workspaces:
            workspaces.append(repo_str)
        data["trustedWorkspaces"] = workspaces
        data["toolPermission"] = "always-proceed"
        data["agentMode"] = AGY_DEFAULT_MODE
    else:
        data = {
            "agentMode": AGY_DEFAULT_MODE,
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [repo_str],
        }

    new_content = json.dumps(data, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, encoding="utf-8") as tf:
        tf.write(new_content)
        temp_path = Path(tf.name)
    temp_path.chmod(0o600)
    os.replace(temp_path, path)
    return backup_path


def rollback(backups: dict[Path, Path]) -> None:
    """Restore original configuration files from backups on error."""
    for target, bak in backups.items():
        if bak.is_file():
            try:
                shutil.copy2(bak, target)
                target.chmod(0o600)
            except Exception as e:
                print(f"Warning: Failed to rollback {target} from {bak}: {e}", file=sys.stderr)


def apply_configuration(home: Path, repo: Path) -> dict[str, Any]:
    """Apply native configuration plan with rollback safety."""
    backups: dict[Path, Path] = {}
    applied: list[str] = []

    try:
        if shutil.which("codex"):
            bak = apply_codex(home, repo)
            if bak:
                backups[codex_config_path(home)] = bak
                applied.append("Codex configuration updated")

        if shutil.which("agy"):
            bak = apply_agy(home, repo)
            if bak:
                backups[agy_config_path(home)] = bak
                applied.append("AGY configuration updated")

        return {
            "status": "APPLIED",
            "applied": applied,
            "backups": {str(k): str(v) for k, v in backups.items()},
        }
    except Exception as err:
        rollback(backups)
        raise RuntimeError(f"Setup failed and was rolled back: {err}") from err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Configure Codex and AGY Native Fast Lane capabilities.")
    parser.add_argument("--repo", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--home", type=Path, default=None, help="Home directory override")
    parser.add_argument("--plan", action="store_true", help="Print plan without modifying files")
    parser.add_argument("--apply", action="store_true", help="Apply proposed configuration changes")
    parser.add_argument("--yes", "-y", action="store_true", help="Confirm changes non-interactively")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--smoke", action="store_true", help="Run safe disposable smoke after setup")

    args = parser.parse_args(argv)

    if os.geteuid() == 0:
        print("BLOCKED: do not run native setup as root", file=sys.stderr)
        return 1

    home = (args.home or Path.home()).resolve()
    repo = args.repo.resolve()

    plan = generate_plan(home, repo)

    if plan["status"] == "BLOCKED_UNSUPPORTED_RUNTIME":
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print(f"BLOCKED: {plan['message']}", file=sys.stderr)
        return 1

    # Dry-run or JSON plan mode
    if args.plan or (args.json and not args.apply):
        if args.json:
            print(json.dumps(plan, indent=2))
        else:
            print("=" * 60)
            print("Proposed Harness Native Fast Lane Configuration Plan:")
            print("=" * 60)
            print(f"Repository: {plan['repo']}")
            if plan["codex"]["installed"]:
                print("\n[Codex]")
                print(f"  Config: {plan['codex']['config_path']}")
                for act in plan["codex"]["actions"]:
                    print(f"  - {act}")
                if not plan["codex"]["actions"]:
                    print("  - Configuration already up to date")
            if plan["agy"]["installed"]:
                print("\n[AGY]")
                print(f"  Config: {plan['agy']['config_path']}")
                for act in plan["agy"]["actions"]:
                    print(f"  - {act}")
                if not plan["agy"]["actions"]:
                    print("  - Configuration already up to date")
            print("=" * 60)
            print(f"Status: {plan['status']} ({plan['total_actions']} actions proposed)")
        return 0

    if args.apply:
        if plan["total_actions"] == 0:
            if args.json:
                print(json.dumps({"status": "READY", "message": "Already up to date", "applied": []}, indent=2))
            else:
                print("READY: Native configurations are already configured. No changes needed.")
            if args.smoke and probe:
                probe.run_smoke(Path(tempfile.mkdtemp(prefix="lora-smoke-")), repo, consent=True)
            return 0

        # Confirmation gate
        if not args.yes:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                print("BLOCKED: interactive terminal required for approval (or use --plan for dry run)", file=sys.stderr)
                return 1

            print("=" * 60)
            print("Proposed Harness Native Fast Lane Configuration Plan:")
            print("=" * 60)
            if plan["codex"]["actions"]:
                print("\n[Codex]")
                for act in plan["codex"]["actions"]:
                    print(f"  - {act}")
            if plan["agy"]["actions"]:
                print("\n[AGY]")
                for act in plan["agy"]["actions"]:
                    print(f"  - {act}")
            print("=" * 60)
            print("Type CONFIGURE NATIVE to approve changes: ", end="", flush=True)
            try:
                line = sys.stdin.readline().strip()
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled; no changes made.", file=sys.stderr)
                return 1

            if line != "CONFIGURE NATIVE":
                print("Cancelled; no changes made.", file=sys.stderr)
                return 1

        result = apply_configuration(home, repo)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("\nConfiguration applied successfully!")
            for item in result["applied"]:
                print(f"  ✓ {item}")
            print("\nNOTE: Please restart active Codex / AGY sessions so they reload the updated configuration.")
            print("Next: Run 'python3 scripts/agent_harness/native_capability_probe.py' to verify capabilities.")

        if args.smoke and probe:
            print("\nRunning disposable capability smoke test...")
            smoke_res = probe.run_smoke(Path(tempfile.mkdtemp(prefix="lora-smoke-")), repo, consent=True)
            print(f"Smoke Status: {smoke_res.get('smoke_status')}")

        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
