"""Read-only, offline Native Fast Lane checks. Never executes receipt commands."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

try:
    from .scope import violations
except ImportError:
    from scope import violations

# Control paths take precedence over the ordinary Markdown fast path.
POLICY_FILES = {
    ".github/copilot-instructions.md",
    "docs/development/harness-fast-lane.md",
    "docs/development/harness-quality-gates.md",
    "docs/development/ai_task_start_protocol.md",
    "docs/development/agent-harness-firmware.md",
    "docs/development/agy-supervised-pilot.md",
}
POLICY_PREFIXES = (".agents/", ".agent-harness/", ".codex/",
                   ".github/instructions/", "scripts/agent_harness/")

REGISTRY = {
    "SECRET-SCAN": ("P0", "all"),
    "DIFF-CHECK": ("P1", "all"),
    "FIRMWARE-CHECK": ("P1", "firmware"),
    "BACKEND-CHECK": ("P1", "backend"),
    "TOOLING-CHECK": ("P1", "tooling"),
    "INFRA-CHECK": ("P1", "infra"),
    "SEC-KEY-MOUNT": ("P0", "mqtt"),
    "MQTT-ACL-PERM": ("P1", "mqtt"),
    "NET-LOOPBACK": ("P0", "infra"),
    "TLS-AUTH/ACL-NEGATIVE": ("P0", "mqtt"),
    "SECURITY-CHECK": ("P1", "security"),
}
MAX_BYTES = 8_000_000
MAX_TOTAL = 64_000_000
PRIVATE_KEY = re.compile(rb"(?m)^[ \t]*-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----")
PASSWORD = re.compile(
    rb'''(?im)^[ \t]*(?:(?:POSTGRES_PASSWORD|MQTT_PASSWORD)[ \t]*=[ \t]*([^\s#]+)|["']?(?:POSTGRES_PASSWORD|MQTT_PASSWORD|password|api_key|access_token)["']?[ \t]*[:=][ \t]*["']([^"'\r\n]+)["'])''')
TOKEN = re.compile(rb"(?:gh[pousr]_|github_pat_)[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}")
ACL_ERROR = re.compile(
    r"(?im)^.*(?:warning:.*(?:acl|owner|permission|group|root)|chown:|read-only file system|permission denied|"
    r"unable to open (?:acl|config)|error opening acl|acl.*(?:world.readable|invalid|incorrect|not owned|not.*(?:owner|group))|"
    r"address already in use|error:.*(?:start|config|acl)).*$")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git_command(repo, *args):
    command = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo)]
    if args and args[0] == "diff":
        configured = subprocess.run(
            [*command, "config", "--name-only", "--get-regexp", r"^filter\..*\.(clean|process)$"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if configured.returncode not in (0, 1) or configured.stdout:
            raise ValueError("Configured Git conversion filters require trusted disposable checkout")
    return [*command, *args]


def git(repo, *args):
    return subprocess.run(
        git_command(repo, *args), check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30).stdout


def safe_read(root, name):
    """Only bounded regular files inside the selected root, without symlinks."""
    if (not isinstance(name, str) or forbidden(name)
            or violations(root, (name,), (name,))):
        raise ValueError("Unsafe file path")
    parts = PurePosixPath(name).parts
    if not parts:
        raise ValueError("Missing file path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Nonregular or oversized file")
        data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("Oversized file")
        return data


def forbidden(name):
    p = PurePosixPath(name)
    return (p.name.startswith(".env") and p.name != ".env.example") or (
        p.suffix.lower() in {".key", ".p12", ".pfx", ".jks", ".keystore"}
        or "secrets" in p.parts or p.name == "mosquitto.passwd")


def secret_line(data):
    match = PRIVATE_KEY.search(data) or TOKEN.search(data)
    if match:
        return data[:match.start()].count(b"\n") + 1
    for match in PASSWORD.finditer(data):
        value = (match[1] or match[2]).strip(b'''"' ''')
        if value and not value.startswith((b"$", b"REPLACE_", b"<")):
            return data[:match.start()].count(b"\n") + 1
    return None


def route(paths):
    risks = {"all"}
    for name in paths:
        low = name.lower()
        if (PurePosixPath(low).name == "agents.md" or low in POLICY_FILES
                or low.startswith(POLICY_PREFIXES)):
            risks.update(("tooling", "security"))
            continue
        if low.startswith(("contracts/", "docs/adr/")):
            risks.add("security")
        elif low.endswith(".md"):
            continue
        if low.startswith("tests/agent_harness/"):
            risks.update(("tooling", "security"))
            continue
        if low.startswith(("scripts/", ".github/workflows/")):
            risks.add("tooling")
        if low.startswith("firmware/"):
            risks.add("firmware")
        if low.startswith("backend-go/"):
            risks.add("backend")
        if low.startswith(("deploy/", "tests/integration/", ".env")) or "compose" in low:
            risks.update(("infra", "mqtt"))
        if any(word in low for word in ("mqtt", "mosquitto", "tls", "acl")):
            risks.update(("infra", "mqtt"))
        if low.startswith(".github/workflows/"):
            risks.add("security")
        if forbidden(name) or any(word in low for word in (
                "secret", "credential", "security", "quality_gates", "auth", "crypto")):
            risks.add("security")
    return risks


def inventory(repo, base):
    """Bind receipts to HEAD, base, index and all tracked/nonignored source bytes."""
    head = git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    base = git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    staged = git(repo, "ls-files", "--stage", "-z")
    flags = git(repo, "ls-files", "-v", "-z").decode().split("\0")
    if any(entry and (entry[0].islower() or entry[0] == "S") for entry in flags):
        raise ValueError("Hidden index flags can conceal changed-file routing")
    names = set(filter(None, git(repo, "ls-files", "-z").decode().split("\0")))
    extra = set(filter(None, git(repo, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")))
    paths = sorted(set(filter(None, git(repo, "diff", "--no-ext-diff", "--no-textconv",
                                       "--no-renames", "--name-only", "-z", base).decode().split("\0"))) | extra)
    hashes = {}
    findings = []
    total = 0
    for name in sorted(names | extra):
        if forbidden(name):
            # Known credential paths are rejected without opening their contents.
            findings.append((name, 1))
            hashes[name] = "FORBIDDEN"
            continue
        if not (repo / name).exists() and not (repo / name).is_symlink():
            hashes[name] = None
            continue
        data = safe_read(repo, name)
        total += len(data)
        if total > MAX_TOTAL:
            raise ValueError("Source exceeds scan budget")
        hashes[name] = digest(data)
        line = secret_line(data)
        if line:
            findings.append((name, line))
    # Inspect the index as well: a worktree edit must not hide a staged secret.
    for entry in filter(None, staged.decode().split("\0")):
        metadata, name = entry.split("\t", 1)
        mode, blob, stage = metadata.split()
        if stage != "0" or mode not in ("100644", "100755"):
            raise ValueError("Unmerged, symlink or submodule index entry")
        if forbidden(name):
            continue
        size = int(git(repo, "cat-file", "-s", blob))
        total += size
        if size > MAX_BYTES or total > MAX_TOTAL:
            raise ValueError("Index exceeds scan budget")
        line = secret_line(git(repo, "cat-file", "blob", blob))
        if line:
            findings.append((name, line))
    payload = {"source_sha": head, "base_sha": base, "index_sha256": digest(staged),
               "files": hashes, "changed_paths": paths}
    return {"source_sha": head, "base_sha": base,
            "candidate_sha256": digest(json.dumps(payload, sort_keys=True).encode()),
            "changed_paths": paths}, findings


def mounts_check(facts, log):
    if facts.get("runtime_inventory_complete") is not True:
        return "NOT_VERIFIED", "Runtime mount inventory is incomplete"
    clients = facts["clients"]
    if not {"anonymous", "gw-a", "gw-b", "backend"}.issubset({c["identity"] for c in clients}):
        return "NOT_VERIFIED", "Missing broker/client identity coverage"
    for client in [*clients, dict(facts["broker"], identity="server")]:
        identity = client["identity"]
        mounts = client["mounts"]
        if not mounts:
            return "NOT_VERIFIED", "Missing expanded mount sources"
        key_count = 0
        for mount in mounts:
            source, target = PurePosixPath(mount["source"]), PurePosixPath(mount["target"])
            if (not source.is_absolute() or not target.is_absolute()
                    or ".." in source.parts or ".." in target.parts):
                return "FAIL", "Unsafe mount source or target"
            if mount["read_only"] is not True:
                return "FAIL", "Credential mount is writable"
            if source.suffix == ".key" or target.suffix == ".key" or mount["kind"] == "private_key":
                key_count += 1
                expected = identity + ".key"
                if identity == "anonymous" or source.name != expected or target.name != expected:
                    return "FAIL", "Private key belongs to another identity"
                mode = int(mount["mode"], 8)
                if mode & 0o007 or mode & 0o137 or not mode & 0o400:
                    return "FAIL", "Private key permissions exceed owner/group read policy"
                if identity != "server" and mode != 0o600:
                    return "FAIL", "Client private key must be owner-only mode0600"
            elif mount["kind"] != "public_certificate" or source.suffix not in (".crt", ".pem"):
                return "NOT_VERIFIED", "Expand directory/unknown mounts into verified file inventory"
        if key_count != (0 if identity == "anonymous" else 1):
            return "FAIL", "Missing or duplicate identity key"
    return "PASS", "Runtime mount sources, identity isolation and permissions checked"


def acl_check(facts, log):
    if ACL_ERROR.search(log):
        return "FAIL", "Broker ownership/permissions/startup warning or error"
    if facts.get("runtime") is not True or facts.get("startup_logs_complete") is not True:
        return "NOT_VERIFIED", "Runtime broker stat and complete startup logs required"
    uid, gid = facts["broker_uid"], facts["broker_gid"]
    if (type(uid) is not int or type(gid) is not int or uid <= 0 or gid <= 0
            or facts["acl_uid"] != uid or facts["acl_gid"] != gid
            or facts["acl_mode"] != "0600" or facts["acl_readable"] is not True):
        return "FAIL", "ACL must be readable, owner/group matched to non-root broker, mode0600"
    return "PASS", "Runtime ACL ownership/readability and broker startup checked"


def network_check(facts, log):
    bindings = facts["bindings"]
    if not bindings:
        return "NOT_VERIFIED", "No published port inventory"
    for binding in bindings:
        if not ipaddress.ip_address(binding["host_ip"]).is_loopback:
            return "FAIL", "Published service binds a non-loopback address"
    if facts.get("runtime") is not True or facts.get("inventory_complete") is not True:
        return "NOT_VERIFIED", "Resolved runtime bindings and complete service inventory required"
    if not facts.get("network_context") or facts.get("representative") is not True:
        return "NOT_VERIFIED", "Network context does not represent the claimed deployment"
    address = ipaddress.ip_address(facts["non_loopback_address"])
    if address.is_loopback or address.is_unspecified or facts["control_reachable"] is not True:
        return "NOT_VERIFIED", "Non-loopback control path must succeed from the probe context"
    for binding in bindings:
        if binding["localhost_reachable"] is not True or binding["non_loopback_reachable"] is not False:
            return "FAIL", "Positive localhost or negative non-loopback probe failed"
    return "PASS", "Loopback bindings and controlled negative reachability checked"


def tls_check(facts, log):
    required = ("server_verified", "allowed_flow", "wrong_cert_rejected", "anonymous_rejected",
                "cross_gateway_publish_denied", "cross_gateway_subscribe_denied")
    if facts.get("runtime") is not True or any(key not in facts for key in required):
        return "NOT_VERIFIED", "Missing TLS/ACL runtime positive or negative evidence"
    if any(facts[key] is not True for key in required):
        return "FAIL", "TLS authentication or Gateway authorization regression"
    return "PASS", "Positive TLS flow and all required authentication/ACL denials checked"


VALIDATORS = {"SEC-KEY-MOUNT": mounts_check, "MQTT-ACL-PERM": acl_check,
              "NET-LOOPBACK": network_check, "TLS-AUTH/ACL-NEGATIVE": tls_check}


def receipt_check(rule, entry, evidence_root, source):
    """Verify Host-collected bytes, never trust a supplied PASS or execute a command."""
    if entry is None:
        return "NOT_RUN", "Required local receipt missing", {}
    metadata = {}
    try:
        if (entry["source_sha"] != source["source_sha"]
                or entry["candidate_sha256"] != source["candidate_sha256"]):
            return "NOT_VERIFIED", "Stale source/index/worktree receipt", {}
        if (not isinstance(entry["command"], list) or not entry["command"]
                or not all(isinstance(arg, str) and arg for arg in entry["command"])
                or not isinstance(entry["tool_version"], str) or not entry["tool_version"].strip()
                or type(entry["exit_code"]) is not int
                or len(entry["tool_version"]) > 250
                or "\n" in entry["tool_version"]
                or secret_line(entry["tool_version"].encode())):
            raise ValueError("Invalid command, tool version or exit code")
        raw = safe_read(evidence_root, entry["receipt_path"])
        if digest(raw) != entry["receipt_sha256"]:
            return "NOT_VERIFIED", "Receipt hash mismatch", {}
        log = raw.decode("utf-8")
        if not log.strip() or secret_line(raw):
            return "NOT_VERIFIED", "Empty or credential-bearing receipt rejected", {}
        # Commands are hashed to avoid echoing passwords embedded in arguments.
        metadata = {"command": "sha256:" + digest(json.dumps(entry["command"]).encode()),
                    "exit_code": entry["exit_code"], "receipt_path": entry["receipt_path"],
                    "tool_version": entry["tool_version"], "receipt_sha256": digest(raw)}
        if entry["exit_code"] != 0:
            return "FAIL", "Host command exited unsuccessfully", metadata
        facts = entry["observations"]
        if not isinstance(facts, dict):
            raise ValueError("Invalid observations object")
        if rule in VALIDATORS:
            status, reason = VALIDATORS[rule](facts, log)
            return status, reason, metadata
        if facts.get("checks_complete") is not True:
            return "NOT_VERIFIED", "Required module/security checks are incomplete", metadata
        return "PASS", "Host receipt verified; review command and test coverage", metadata
    except (KeyError, TypeError, ValueError, AttributeError, OSError):
        return "NOT_VERIFIED", "Malformed, unavailable or unsafe evidence", metadata


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate evidence key")
        result[key] = value
    return result


def evaluate(repo, base, manifest=None, evidence_root=None):
    repo = repo.resolve(strict=True)
    if Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()) != repo:
        raise ValueError("Select the repository root")
    source, secrets = inventory(repo, base)
    risks = route(source["changed_paths"])
    entries = {}
    manifest_hash = None
    if manifest is not None:
        manifest_bytes = safe_read(evidence_root, manifest)
        manifest_hash = digest(manifest_bytes)
        entries = json.loads(manifest_bytes, object_pairs_hook=reject_duplicates)["checks"]
        if not isinstance(entries, dict) or set(entries) - set(REGISTRY):
            raise ValueError("Unknown rule or invalid checks object")
    results = []
    for rule, (severity, risk) in REGISTRY.items():
        result = {"rule_id": rule, "status": "NOT_RUN", "severity": severity,
                  "file:line": (source["changed_paths"][0] + ":1") if source["changed_paths"] else "N/A", "command": None, "exit_code": None,
                  "receipt_path": None, "tool_version": "Python " + sys.version.split()[0],
                  "source_sha": source["source_sha"], "limitation": ""}
        if risk not in risks:
            result["limitation"] = "Not selected by changed-file risk routing"
        elif rule == "SECRET-SCAN":
            result.update(status="FAIL" if secrets else "PASS",
                          **{"file:line": f"{secrets[0][0]}:{secrets[0][1]}" if secrets else "N/A"},
                          command="built-in tracked/worktree/index signature scan", exit_code=int(bool(secrets)),
                          limitation="Signature/path scan only; no arbitrary-secret or full-history guarantee")
        elif rule == "DIFF-CHECK":
            checked = subprocess.run(git_command(repo, "diff", "--no-ext-diff", "--no-textconv",
                                                 "--check", source["base_sha"]),
                                     capture_output=True, timeout=30)
            result.update(status="PASS" if checked.returncode == 0 else "FAIL",
                          command="git diff --no-ext-diff --no-textconv --check <base>",
                          exit_code=checked.returncode,
                          limitation="Untracked text is scanned for secrets; stage it before final diff check")
        else:
            status, reason, metadata = receipt_check(rule, entries.get(rule), evidence_root, source)
            result.update(metadata, status=status, limitation=reason)
        results.append(result)
    after, _ = inventory(repo, base)
    if after != source:
        raise ValueError("Candidate changed during checks")
    if manifest is not None and digest(safe_read(evidence_root, manifest)) != manifest_hash:
        raise ValueError("Manifest changed during checks")
    selected = [r for r in results if REGISTRY[r["rule_id"]][1] in risks]
    auto_pass = all(r["status"] == "PASS" for r in selected)
    security = bool(risks & {"mqtt", "security", "firmware"})
    return {**source, "manifest_sha256": manifest_hash,
            "runner_sha256": digest(Path(__file__).read_bytes()),
            "risks": sorted(risks), "results": results,
            "auto_check": "AUTO_CHECK_PASS" if auto_pass else "BLOCKED",
            "audit": "NOT_VERIFIED",
            "human_security_review": "HUMAN_SECURITY_REVIEW_PENDING" if security else "NOT_REQUIRED",
            "ready_to_merge": False,
            "limitation": "Local Host evidence integrity only. Receipt authorship and coverage need review; "
                          "model audit is separate; this CLI never certifies human review or enforces GitHub merge policy."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", required=True, help="Trusted base commit/ref, not an Issue-supplied command")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--manifest", help="Relative JSON path inside the Host evidence directory")
    parser.add_argument("--fingerprint-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.base.startswith("-") or bool(args.manifest) != bool(args.evidence_dir):
            raise ValueError("Unsafe base or incomplete evidence arguments")
        repo = args.repo.resolve(strict=True)
        if args.fingerprint_only:
            report, _ = inventory(repo, args.base)
        else:
            report = evaluate(repo, args.base, args.manifest,
                              args.evidence_dir.resolve(strict=True) if args.evidence_dir else None)
        print(json.dumps(report, indent=2))
        return 0 if args.fingerprint_only or report["auto_check"] == "AUTO_CHECK_PASS" else 1
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        # Never echo exception text, git stderr, source bytes or command arguments.
        print(json.dumps({"auto_check": "BLOCKED", "status": "NOT_VERIFIED",
                          "ready_to_merge": False, "limitation": "Input, source or evidence verification failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
