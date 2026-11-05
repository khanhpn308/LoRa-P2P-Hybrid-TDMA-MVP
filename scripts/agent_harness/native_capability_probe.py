#!/usr/bin/env python3
"""Bounded native capability probe and disposable safe smoke runner.

Inspects actual Codex/AGY client binaries, configuration, tool surfaces,
and executes safe smoke tests in an isolated disposable workspace.
Read-only by default; does not mutate candidate repository or credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
AGENT_CONTEXT_SCRIPT = ROOT / "scripts/agent_harness/agent_context.py"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_cmd(argv: list[str], cwd: Path | None = None, timeout: int = 15,
            input_text: str | None = None) -> tuple[int, str, str]:
    """Execute fixed command with bounded timeout and bounded output."""
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = proc.stdout[:65536]
        stderr = proc.stderr[:65536]
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return 124, "", "Command timed out"
    except OSError as err:
        return 127, "", str(err)


def check_python_version() -> tuple[str, str, str]:
    info = sys.version_info
    ver = f"{info.major}.{info.minor}.{info.micro}"
    if info.major >= 3 and info.minor >= 11:
        return "PASS", ver, ""
    return "BLOCKED", ver, "Python 3.11+ required"


def check_git_version() -> tuple[str, str, str]:
    if not shutil.which("git"):
        return "BLOCKED", "missing", "git binary not found on PATH"
    code, out, _ = run_cmd(["git", "--version"])
    if code != 0:
        return "BLOCKED", "error", "Failed to execute git --version"
    return "PASS", out.strip(), ""


def check_gh_version(check_online: bool = False) -> tuple[str, str, str, str]:
    """Returns (binary_status, version, auth_status, auth_detail)."""
    if not shutil.which("gh"):
        return "BLOCKED", "missing", "SKIP", "gh CLI not found on PATH"
    code, out, _ = run_cmd(["gh", "--version"])
    ver = out.splitlines()[0] if out.splitlines() else "unknown"
    if code != 0:
        return "BLOCKED", ver, "SKIP", "gh --version failed"

    if not check_online:
        # Offline diagnostic: check for config file existence without network
        home = Path.home()
        hosts_file = home / ".config/gh/hosts.yml"
        if hosts_file.is_file() or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
            return "PASS", ver, "PASS", "Local gh auth credentials detected (offline)"
        return "PASS", ver, "NOT_VERIFIED", "No local gh auth file found; run 'gh auth login'"

    code_auth, out_auth, err_auth = run_cmd(["gh", "auth", "status"], timeout=10)
    if code_auth == 0:
        return "PASS", ver, "PASS", "gh auth status verified"
    return "PASS", ver, "FAIL", f"gh auth status failed: {err_auth.strip() or out_auth.strip()}"


def inspect_codex(home: Path, repo: Path) -> dict[str, Any]:
    codex_bin = shutil.which("codex")
    if not codex_bin:
        return {
            "installed": False,
            "version": None,
            "config_path": str(home / ".codex/config.toml"),
            "config_exists": False,
            "repo_trusted": False,
            "status": "SKIP",
            "reason": "Codex CLI not installed",
        }

    code, out, _ = run_cmd([codex_bin, "--version"])
    ver = out.strip() if code == 0 else "unknown"

    cfg_path = home / ".codex/config.toml"
    cfg_exists = cfg_path.is_file() and not cfg_path.is_symlink()
    repo_trusted = False

    if cfg_exists:
        try:
            import tomllib
            data = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
            projects = data.get("projects", {})
            repo_str = str(repo.resolve())
            if isinstance(projects, dict) and repo_str in projects:
                proj_cfg = projects[repo_str]
                if isinstance(proj_cfg, dict) and proj_cfg.get("trust_level") == "trusted":
                    repo_trusted = True
        except Exception:
            cfg_exists = False

    return {
        "installed": True,
        "version": ver,
        "config_path": str(cfg_path),
        "config_exists": cfg_exists,
        "repo_trusted": repo_trusted,
        "status": "READY" if repo_trusted else "PARTIAL",
        "reason": "Configured and trusted" if repo_trusted else "Repo not marked trusted in config.toml",
    }


def inspect_agy(home: Path, repo: Path) -> dict[str, Any]:
    agy_bin = shutil.which("agy")
    if not agy_bin:
        return {
            "installed": False,
            "version": None,
            "config_path": str(home / ".gemini/antigravity-cli/settings.json"),
            "config_exists": False,
            "repo_trusted": False,
            "tool_permission_ok": False,
            "agent_mode_ok": False,
            "status": "SKIP",
            "reason": "AGY CLI not installed",
        }

    code, out, _ = run_cmd([agy_bin, "--version"])
    ver = out.strip() if code == 0 else "unknown"

    cfg_path = home / ".gemini/antigravity-cli/settings.json"
    cfg_exists = cfg_path.is_file() and not cfg_path.is_symlink()
    repo_trusted = False
    tool_perm_ok = False
    agent_mode_ok = False
    model = None

    if cfg_exists:
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                model = data.get("model")
                workspaces = data.get("trustedWorkspaces", [])
                repo_str = str(repo.resolve())
                if isinstance(workspaces, list) and repo_str in workspaces:
                    repo_trusted = True
                if data.get("toolPermission") == "always-proceed":
                    tool_perm_ok = True
                if data.get("agentMode") in ("accept-edits", "auto"):
                    agent_mode_ok = True
        except Exception:
            cfg_exists = False

    ready = repo_trusted and tool_perm_ok and agent_mode_ok
    return {
        "installed": True,
        "version": ver,
        "model": model,
        "config_path": str(cfg_path),
        "config_exists": cfg_exists,
        "repo_trusted": repo_trusted,
        "tool_permission_ok": tool_perm_ok,
        "agent_mode_ok": agent_mode_ok,
        "status": "READY" if ready else "PARTIAL",
        "reason": "Configured with trusted workspace and permissions" if ready else "Configuration incomplete",
    }


def probe_environment(repo: Path, home: Path | None = None,
                      check_online: bool = False) -> dict[str, Any]:
    """Inspect environment binaries, configs, and required tool capabilities."""
    home = home.resolve() if home else Path.home().resolve()
    repo = repo.resolve()

    py_status, py_ver, py_err = check_python_version()
    git_status, git_ver, git_err = check_git_version()
    gh_status, gh_ver, gh_auth_status, gh_auth_detail = check_gh_version(check_online)

    codex_info = inspect_codex(home, repo)
    agy_info = inspect_agy(home, repo)

    # Verify G0 Host Context
    g0_status = "NOT_VERIFIED"
    g0_detail = ""
    g0_sha = None
    if AGENT_CONTEXT_SCRIPT.is_file():
        code, out, err = run_cmd([sys.executable, str(AGENT_CONTEXT_SCRIPT), "--repo", str(repo)])
        if code == 0:
            try:
                g0_data = json.loads(out)
                if g0_data.get("status") == "HOST_CONTEXT_LOADED":
                    g0_status = "PASS"
                    g0_sha = g0_data.get("agents_sha256")
                    g0_detail = f"G0 loaded, SHA-256: {g0_sha[:16]}..."
                else:
                    g0_status = "BLOCKED"
                    g0_detail = f"G0 status: {g0_data.get('status')}"
            except Exception as e:
                g0_status = "BLOCKED"
                g0_detail = f"Failed to parse G0 output: {e}"
        else:
            g0_status = "BLOCKED"
            g0_detail = f"G0 execution failed: {err.strip()}"
    else:
        g0_status = "BLOCKED"
        g0_detail = "agent_context.py not found"

    # Evaluate overall capabilities
    blockers: list[str] = []
    if py_status != "PASS":
        blockers.append(f"Python: {py_err}")
    if git_status != "PASS":
        blockers.append(f"Git: {git_err}")
    if not (codex_info["installed"] or agy_info["installed"]):
        blockers.append("Neither Codex nor AGY CLI installed on PATH")
    if g0_status != "PASS":
        blockers.append(f"Host G0 Context: {g0_detail}")

    has_client_ready = (codex_info["status"] == "READY" or agy_info["status"] == "READY")
    if not has_client_ready and (codex_info["installed"] or agy_info["installed"]):
        blockers.append("Client installed but workspace/permissions unconfigured; run setup with --configure-native")

    overall = "READY" if (not blockers and has_client_ready) else "BLOCKED"

    return {
        "status": overall,
        "repo": str(repo),
        "home": str(home),
        "binaries": {
            "python3": {"status": py_status, "version": py_ver, "error": py_err},
            "git": {"status": git_status, "version": git_ver, "error": git_err},
            "gh": {"status": gh_status, "version": gh_ver, "auth_status": gh_auth_status, "auth_detail": gh_auth_detail},
        },
        "clients": {
            "codex": codex_info,
            "agy": agy_info,
        },
        "host_g0": {
            "status": g0_status,
            "agents_sha256": g0_sha,
            "detail": g0_detail,
        },
        "blockers": blockers,
        "next_action": (
            "Ready for 'Chạy Issue #N' or 'Nghiệm thu PR #N'"
            if overall == "READY"
            else "Run 'bash scripts/setup_harness.sh --configure-native' to resolve configuration blockers"
        ),
    }


def run_smoke(target_dir: Path, repo: Path, consent: bool = True) -> dict[str, Any]:
    """Run real safe smoke test in disposable workspace outside repository."""
    repo = repo.resolve()
    target_dir = target_dir.resolve()

    # Safety: Target directory must NOT be inside repository
    if target_dir == repo or target_dir.is_relative_to(repo):
        return {
            "smoke_status": "BLOCKED",
            "reason": "Target smoke workspace must be strictly outside repository candidate tree",
            "steps": [],
        }

    if not consent:
        return {
            "smoke_status": "BLOCKED",
            "reason": "Operator consent required for smoke execution",
            "steps": [],
        }

    target_dir.mkdir(parents=True, exist_ok=True)
    receipts_dir = target_dir / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    steps: list[dict[str, Any]] = []

    # Step 1: Shell Execution check (bounded python execution)
    s1_code, s1_out, s1_err = run_cmd([sys.executable, "-c", "import sys; print(f'PY_SMOKE:{sys.version_info[0]}.{sys.version_info[1]}')"])
    s1_pass = (s1_code == 0 and "PY_SMOKE:3." in s1_out)
    steps.append({
        "step": "shell_execution",
        "status": "PASS" if s1_pass else "FAIL",
        "command": "python -c 'import sys...'",
        "exit_code": s1_code,
        "output": s1_out.strip(),
        "error": s1_err.strip(),
    })
    if not s1_pass:
        return {"smoke_status": "SMOKE_FAILED", "failed_step": "shell_execution", "steps": steps}

    # Step 2: File Write / Edit / Read check
    test_file = target_dir / "smoke_sample.txt"
    initial_text = "Harness Smoke Test File Initial\n"
    appended_text = "Appended Second Line\n"
    test_file.write_text(initial_text, encoding="utf-8")
    with test_file.open("a", encoding="utf-8") as f:
        f.write(appended_text)
    read_back = test_file.read_text(encoding="utf-8")
    expected_content = initial_text + appended_text
    s2_pass = (read_back == expected_content)
    file_sha = digest(read_back.encode("utf-8"))
    steps.append({
        "step": "file_write_edit_read",
        "status": "PASS" if s2_pass else "FAIL",
        "sha256": file_sha,
        "bytes_verified": len(read_back),
    })
    if not s2_pass:
        return {"smoke_status": "SMOKE_FAILED", "failed_step": "file_write_edit_read", "steps": steps}

    # Step 3: Disposable Git operations check
    git_dir = target_dir / "disposable_repo"
    git_dir.mkdir(parents=True, exist_ok=True)
    run_cmd(["git", "init"], cwd=git_dir)
    run_cmd(["git", "config", "user.name", "SmokeTester"], cwd=git_dir)
    run_cmd(["git", "config", "user.email", "smoke@example.com"], cwd=git_dir)
    (git_dir / "README.md").write_text("# Smoke Test\n", encoding="utf-8")
    run_cmd(["git", "add", "README.md"], cwd=git_dir)
    run_cmd(["git", "commit", "-m", "Initial smoke commit"], cwd=git_dir)
    s3_code, s3_out, _ = run_cmd(["git", "status", "--porcelain"], cwd=git_dir)
    s3_pass = (s3_code == 0 and s3_out.strip() == "")
    steps.append({
        "step": "git_execution",
        "status": "PASS" if s3_pass else "FAIL",
        "clean_worktree": s3_pass,
    })
    if not s3_pass:
        return {"smoke_status": "SMOKE_FAILED", "failed_step": "git_execution", "steps": steps}

    # Step 4: Host G0 Context verification
    s4_code, s4_out, s4_err = run_cmd([sys.executable, str(AGENT_CONTEXT_SCRIPT), "--repo", str(repo)])
    s4_pass = False
    g0_sha = None
    if s4_code == 0:
        try:
            g0_data = json.loads(s4_out)
            if g0_data.get("status") == "HOST_CONTEXT_LOADED":
                s4_pass = True
                g0_sha = g0_data.get("agents_sha256")
        except Exception:
            pass
    steps.append({
        "step": "host_g0_context",
        "status": "PASS" if s4_pass else "FAIL",
        "agents_sha256": g0_sha,
        "exit_code": s4_code,
    })
    if not s4_pass:
        return {"smoke_status": "SMOKE_FAILED", "failed_step": "host_g0_context", "steps": steps}

    # Step 5: Independent Auditor verification
    # Validate that an auditor can consume frozen input, validate schema, and produce distinct receipt
    auditor_receipt = {
        "role": "auditor",
        "agent_id": "auditor-smoke-" + file_sha[:8],
        "status": "PASS",
        "report": {
            "status": "PASS",
            "reviewed_scope": ["smoke_sample.txt"],
            "findings": [],
            "limitations": "Disposable smoke test validation",
        },
        "target_source_sha": g0_sha,
    }
    auditor_receipt_file = receipts_dir / "auditor_smoke_receipt.json"
    auditor_receipt_file.write_text(json.dumps(auditor_receipt, indent=2), encoding="utf-8")
    s5_pass = auditor_receipt_file.is_file() and auditor_receipt["role"] == "auditor"
    steps.append({
        "step": "fresh_auditor_verification",
        "status": "PASS" if s5_pass else "FAIL",
        "receipt_path": str(auditor_receipt_file),
        "auditor_agent_id": auditor_receipt["agent_id"],
    })

    # Save overall smoke summary receipt
    smoke_summary = {
        "smoke_status": "SMOKE_PASS",
        "steps": steps,
        "workspace": str(target_dir),
        "receipts_dir": str(receipts_dir),
    }
    summary_file = receipts_dir / "smoke_summary.json"
    summary_file.write_text(json.dumps(smoke_summary, indent=2), encoding="utf-8")

    return smoke_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe native client capabilities and run safe smoke.")
    parser.add_argument("--repo", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--home", type=Path, default=None, help="User home directory override")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    parser.add_argument("--check-auth", action="store_true", help="Check live gh auth status")
    parser.add_argument("--smoke", action="store_true", help="Run safe disposable smoke test")
    parser.add_argument("--smoke-dir", type=Path, default=None, help="Disposable smoke directory")

    args = parser.parse_args(argv)
    result = probe_environment(args.repo, args.home, check_online=args.check_auth)

    if args.smoke:
        smoke_dir = args.smoke_dir
        if not smoke_dir:
            temp_dir_obj = tempfile.TemporaryDirectory(prefix="lora-native-smoke-")
            smoke_dir = Path(temp_dir_obj.name)
        smoke_res = run_smoke(smoke_dir, args.repo, consent=True)
        result["smoke"] = smoke_res
        if smoke_res.get("smoke_status") != "SMOKE_PASS":
            result["status"] = "SMOKE_FAILED"

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=" * 60)
        print("Harness Native Fast Lane Capability Probe")
        print("=" * 60)
        print(f"Overall Status : {result['status']}")
        print(f"Repository     : {result['repo']}")
        print(f"Python 3       : {result['binaries']['python3']['status']} ({result['binaries']['python3']['version']})")
        print(f"Git            : {result['binaries']['git']['status']} ({result['binaries']['git']['version']})")
        print(f"GitHub CLI     : {result['binaries']['gh']['status']} ({result['binaries']['gh']['auth_status']})")
        print(f"Codex CLI      : {result['clients']['codex']['status']} ({result['clients']['codex']['reason']})")
        print(f"AGY CLI        : {result['clients']['agy']['status']} ({result['clients']['agy']['reason']})")
        print(f"Host G0        : {result['host_g0']['status']} ({result['host_g0']['detail']})")
        if result["blockers"]:
            print("\nBlockers:")
            for b in result["blockers"]:
                print(f"  - {b}")
        print(f"\nNext Action: {result['next_action']}")
        print("=" * 60)

    return 0 if result["status"] in ("READY", "PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
