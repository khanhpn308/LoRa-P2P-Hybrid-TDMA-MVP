#!/usr/bin/env python3
"""Opt-in local Harness MCP SDK installation and Codex/AGY stdio registration.

Read-only plan by default. No root privileges, shell injection, or repo mutations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "lora_harness"
SDK_VERSION = "2.3.0"
SERVER = ROOT / "scripts/agent_harness/mcp_server.py"
REQUIREMENTS = ROOT / "scripts/agent_harness/mcp-requirements.txt"
SMOKE = ROOT / "scripts/agent_harness/mcp_smoke.py"


def venv_path(home: Path) -> Path:
    return home / ".local/share/lora-harness/mcp-venv"


def command_line(home: Path) -> list[str]:
    return [str(venv_path(home) / "bin/python"), str(SERVER)]


def agy_path(home: Path) -> Path:
    return home / ".gemini/config/mcp_config.json"


def run(argv: list[str], timeout: int = 15) -> subprocess.CompletedProcess:
    """Fixed argv, no shell, bounded duration and bounded returned output."""
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, timeout=timeout, check=False)
    if len(result.stdout) > 65536:
        raise RuntimeError("Command output too large")
    return result


def installed_sdk(home: Path) -> bool:
    py = venv_path(home) / "bin/python"
    if not py.is_file() or py.is_symlink():
        return False
    try:
        return run([str(py), "-c",
            f"import importlib.metadata; assert importlib.metadata.version('mcp') == '{SDK_VERSION}'"]).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def parse_codex_entry(value: object) -> tuple[str, list[str]] | None:
    if not isinstance(value, dict):
        return None
    transport = value.get("transport", value)
    if not isinstance(transport, dict):
        return None
    cmd, args = transport.get("command"), transport.get("args")
    if isinstance(cmd, str) and isinstance(args, list) and all(isinstance(x, str) for x in args):
        return (cmd, args)
    return None


def codex_config(command: list[str]) -> tuple[str, str]:
    """Return state, no secrets; don't overwrite unrecognized existing entries."""
    if not shutil.which("codex"):
        return ("SKIP", "Codex CLI unavailable")
    try:
        result = run(["codex", "mcp", "list", "--json"])
        if result.returncode:
            return ("BLOCKED", "Codex MCP list failed")
        data = json.loads(result.stdout)
        if isinstance(data, dict) and "servers" in data:
            data = data["servers"]
        if isinstance(data, list):
            entries = {x.get("name"): x for x in data if isinstance(x, dict)}
        elif isinstance(data, dict):
            entries = data
        else:
            return ("BLOCKED", "Unexpected Codex MCP list schema")
        if NAME not in entries:
            return ("INSTALL", "Codex entry missing")
        if isinstance(entries[NAME], dict) and entries[NAME].get("enabled") is False:
            return ("BLOCKED", "Codex MCP entry is disabled")
        actual = parse_codex_entry(entries[NAME])
        return ("READY", "Codex configured") if actual == (command[0], command[1:]) else ("BLOCKED", "Conflicting Codex entry; do not overwrite")
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return ("BLOCKED", "Cannot safely inspect Codex MCP config")


def secure_parent(path: Path, home: Path) -> None:
    """Reject symlinked config/parents and writes outside selected home."""
    home = home.resolve(strict=True)
    try:
        relative = path.relative_to(home)
    except ValueError as exc:
        raise RuntimeError("Config path not inside home") from exc
    current = home
    for piece in relative.parts:
        current = current / piece
        if current.is_symlink():
            raise RuntimeError("Symlinked config path is not allowed")


def read_agy(path: Path, home: Path) -> dict:
    secure_parent(path, home)
    if not path.exists():
        return {"mcpServers": {}}
    if not path.is_file() or path.stat().st_size > 1_000_000:
        raise RuntimeError("AGY configuration is not a bounded regular file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("AGY MCP JSON cannot be safely parsed") from exc
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
        raise RuntimeError("Invalid AGY mcpServers object")
    return data


def agy_config(command: list[str], home: Path) -> tuple[str, str]:
    if not shutil.which("agy"):
        return ("SKIP", "AGY CLI unavailable")
    try:
        data = read_agy(agy_path(home), home)
    except RuntimeError as exc:
        return ("BLOCKED", str(exc))
    entry = data["mcpServers"].get(NAME)
    if entry is None:
        return ("INSTALL", "AGY entry missing")
    wanted = {"command": command[0], "args": command[1:]}
    return ("READY", "AGY configured") if entry == wanted else ("BLOCKED", "Conflicting AGY entry; do not overwrite")


def write_agy(home: Path, command: list[str]) -> None:
    path = agy_path(home)
    data = read_agy(path, home)
    if NAME in data["mcpServers"]:
        raise RuntimeError("AGY entry changed since plan")
    data["mcpServers"][NAME] = {"command": command[0], "args": command[1:]}
    secure_parent(path, home)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    secure_parent(path, home)
    backup = None
    if path.exists():
        fd, backup_name = tempfile.mkstemp(prefix=".mcp-backup-", dir=path.parent)
        backup = Path(backup_name)
        try:
            with os.fdopen(fd, "wb") as dst, path.open("rb") as src:
                shutil.copyfileobj(src, dst)
        except BaseException:
            backup.unlink(missing_ok=True)
            raise
    fd, tmp_name = tempfile.mkstemp(prefix=".mcp-new-", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.chmod(tmp, 0o600)
        secure_parent(path, home)
        os.replace(tmp, path)
        check = read_agy(path, home)
        assert check["mcpServers"][NAME]["command"] == command[0]
    except BaseException:
        tmp.unlink(missing_ok=True)
        if backup is not None:
            os.replace(backup, path)
        else:
            path.unlink(missing_ok=True)
        raise
    # Keep backup on success for operator recovery; never print its contents.
    if backup:
        print(f"AGY backup: {backup}")


def plan(home: Path) -> dict:
    cmd = command_line(home)
    codex, agy = codex_config(cmd), agy_config(cmd, home)
    sdk = installed_sdk(home)
    return {"sdk": "READY" if sdk else "INSTALL",
            "sdk_version": SDK_VERSION,
            "venv": str(venv_path(home)), "server": str(SERVER),
            "codex": {"status": codex[0], "detail": codex[1]},
            "agy": {"status": agy[0], "detail": agy[1]},
            "transport": "stdio", "tools": ["harness_preflight", "harness_status", "harness_verify_candidate"],
            "note": "Read-only MCP bridge; Native Coordinator execution stays separate."}


def apply(home: Path) -> int:
    if os.geteuid() == 0:
        print("BLOCKED: do not install user MCP as root", file=sys.stderr)
        return 1
    if not sys.stdin.isatty():
        print("BLOCKED: interactive terminal required for approval", file=sys.stderr)
        return 1
    before = plan(home)
    print(json.dumps(before, indent=2))
    if before["codex"]["status"] == "BLOCKED" or before["agy"]["status"] == "BLOCKED":
        print("BLOCKED: conflicting/invalid MCP config; no changes made")
        return 1
    if before["codex"]["status"] == before["agy"]["status"] == "SKIP":
        print("BLOCKED: neither Codex nor AGY installed")
        return 1
    if not all(x.is_file() and not x.is_symlink()
               for x in (SERVER, SMOKE, REQUIREMENTS)):
        print("BLOCKED: reviewed MCP sources unavailable or symlinked")
        return 1
    # Do not let an edited requirements file add new pip arguments/packages.
    try:
        requested = [line.strip() for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
                     if line.strip() and not line.lstrip().startswith("#")]
    except (OSError, UnicodeError):
        requested = []
    if requested != [f"mcp=={SDK_VERSION}"]:
        print("BLOCKED: MCP dependency pin does not match reviewed SDK")
        return 1
    if sys.version_info < (3, 11):
        print("BLOCKED: Python 3.11+ required for this MCP SDK")
        return 1
    print("Will create user venv, download pinned MCP SDK if missing, register MCP only in detected CLIs.")
    print("No root, no Docker/firmware changes; existing unrelated MCP entries are preserved.")
    if input("Type INSTALL MCP to confirm: ").strip() != "INSTALL MCP":
        print("Cancelled: no changes made")
        return 1
    py = venv_path(home) / "bin/python"
    if not installed_sdk(home):
        if not py.is_file():
            run_result = run([sys.executable, "-m", "venv", str(venv_path(home))], 60)
            if run_result.returncode:
                print("BLOCKED: cannot create venv (install python3-venv)", file=sys.stderr)
                return 1
        try:
            installed = run([str(py), "-m", "pip", "install", "--disable-pip-version-check",
                             "--no-input", "-r", str(REQUIREMENTS)], 240)
        except (OSError, subprocess.TimeoutExpired):
            print("BLOCKED: MCP SDK installation failed or timed out")
            return 1
        if installed.returncode or not installed_sdk(home):
            print("BLOCKED: MCP SDK installation failed; no client configs changed")
            return 1
    try:
        smoke = run([str(py), str(SMOKE), str(SERVER)], 40)
    except (OSError, subprocess.TimeoutExpired):
        print("BLOCKED: MCP handshake timed out or failed")
        return 1
    if smoke.returncode:
        print("BLOCKED: MCP smoke failed; client configs untouched")
        return 1
    print("MCP stdio handshake / list_tools / negative call: PASS")
    cmd = command_line(home)
    failures = []
    if before["codex"]["status"] == "INSTALL":
        try:
            result = run(["codex", "mcp", "add", NAME, "--", *cmd], 30)
            if result.returncode:
                failures.append("Codex registration returned nonzero")
            elif codex_config(cmd)[0] != "READY":
                failures.append("Codex registration verification failed")
            else:
                print("Codex MCP config: PASS")
        except (OSError, subprocess.TimeoutExpired):
            failures.append("Codex registration failed")
    if before["agy"]["status"] == "INSTALL":
        try:
            write_agy(home, cmd)
            if agy_config(cmd, home)[0] != "READY":
                failures.append("AGY registration verification failed")
            else:
                print("AGY MCP config: PASS")
        except (OSError, RuntimeError, ValueError):
            failures.append("AGY registration failed; inspect user configuration")
    print("CLI live-session handshake: NOT_VERIFIED; restart Codex/AGY and inspect /mcp")
    if failures:
        for f in failures:
            print("BLOCKED:", f)
        return 1
    print("MCP_INSTALL_AND_LOCAL_SMOKE_PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--plan", action="store_true")
    group.add_argument("--apply", action="store_true")
    group.add_argument("--needs-setup", action="store_true")
    args = parser.parse_args()
    home = Path.home()
    if args.apply:
        return apply(home)
    report = plan(home)
    if args.needs_setup:
        return 0 if (report["codex"]["status"] in ("INSTALL", "BLOCKED") or
                     report["agy"]["status"] in ("INSTALL", "BLOCKED") or
                     (report["sdk"] == "INSTALL" and
                      (report["codex"]["status"] != "SKIP" or
                       report["agy"]["status"] != "SKIP"))) else 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
