"""Deterministic, bounded routing of tracked standards. Never executes rule text."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import stat
import subprocess

try:
    from .scope import violations
except ImportError:
    from scope import violations

STANDARDS = {
    "C": "docs/development/firmware/C_CODING_STANDARD_V2.md",
    "GO": "docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md",
}
GROUPS = {
    "C": {"GOV": 10, "C": 20, "MEM": 8, "ERR": 7, "RTOS": 10, "ARCH": 7,
          "SEC": 8, "RAD": 9, "MAC": 7, "TDMA": 10, "QA": 8},
    "GO": {"GGS": 14, "GB": 10, "AR": 8, "GO": 14, "CT": 9, "MQ": 12,
           "SC": 8, "DB": 10, "RT": 11, "OB": 12, "SE": 9, "TS": 11,
           "QG": 8, "AI": 12},
}
MAX_STANDARD_BYTES = 120_000
MAX_PROMPT_BYTES = 48_000
MAX_RULES = 128
MAX_CODE_BYTES = 2_000_000
MAX_PARTITION_RULES = 128
MAX_PARTITION_PROMPT_BYTES = 48_000
MAX_PARTITIONS = 4
MAX_AGGREGATE_RULES = 256
MAX_AGGREGATE_BYTES = 192_000
RULE_ID = re.compile(r"[A-Z]+-[0-9]{3}")
BASELINE = {
    "C": {*(f"GOV-{n:03}" for n in range(1, 11)), "C-001",
          *(f"MEM-{n:03}" for n in range(1, 9)), *(f"ERR-{n:03}" for n in range(1, 8)),
          *(f"QA-{n:03}" for n in range(1, 9)), "RTOS-003", "SEC-001", "SEC-004"},
    "GO": {"GB-001", "GB-002", "GGS-001", "GGS-006", "GO-001", "SE-002",
           "SE-003", "SE-004", "SE-007", "SE-009", "QG-001", "QG-002", "QG-005",
           "QG-007", "QG-008", "AI-001", "AI-002", "AI-008", "AI-009",
           "AI-011", "AI-012"},
}
PATH_GROUPS = {
    "C": {"sx1276": ("RTOS", "RAD"), "lora_mac": ("SEC", "MAC"),
          "tdma": ("ARCH", "TDMA", "RTOS"), "airtime": ("RAD", "TDMA"),
          "gateway_master": ("ARCH", "RTOS"), "sensor_node": ("ARCH", "RTOS")},
    "GO": {"cmd/server": ("AR", "RT", "OB"), "internal/app": ("AR", "RT", "OB"),
           "internal/config": ("AR", "OB"), "internal/api": ("CT", "RT", "SE", "TS"),
           "mqtt": ("MQ", "CT", "RT", "SE", "TS"),
           "scheduler": ("SC", "RT", "TS"), "storage": ("DB", "CT", "RT", "SE", "TS"),
           "migrations": ("DB", "CT", "RT", "SE", "TS"),
           "telemetry": ("CT", "MQ", "DB", "RT", "SE", "TS"),
           "alert": ("CT", "MQ", "DB", "RT", "SE", "TS")},
}
OPERATIONS = {
    "C": ((r"(?i)\b(?:isr|irq|interrupt|iram[ _]+attr|esp[ _]+timer|freertos|(?:x|v|ux|ul)?(?:task|queue|semaphore)|mutex|callback|spi|dma)\w*", ("RTOS", "MEM")),
          (r"(?i)\b(?:sx1276|lora|radio|airtime)\w*", ("RAD",)),
          (r"(?i)\b(?:aes|nonce|replay|crypto|mic|payload|decode|parse|frame|packet|buffer|memcpy)\w*", ("SEC",)),
          (r"(?i)\b(?:tdma|superframe|guard|schedule)\w*", ("TDMA",))),
    "GO": ((r"(?i)\b(?:sql|postgres|pgx|transaction|database|db|prepare)\w*", ("DB",)),
           (r"(?i)\b(?:mqtt|puback|mosquitto)\w*", ("MQ", "CT")),
           (r"(?i)\b(?:tls|auth|credential|crypto|rbac)\w*", ("SE",)),
           (r"\b(?:goroutine|go[ \t]+\w+|chan|sync|context)\b", ("RT",)),
           (r"(?i)\b(?:json|http|websocket|decode|validate)\w*", ("CT", "SE"))),
}
GO_COMPOSITION_AND_CONFIG_PREFIXES = (
    "backend-go/cmd/server/",
    "backend-go/internal/app/",
    "backend-go/internal/config/",
)
CONCRETE_DB_OPS = re.compile(
    r"(?i)(?:"
    r"\b(?:select\s+.+\s+from|insert\s+into|update\s+.+\s+set|delete\s+from|"
    r"create\s+table|drop\s+table|alter\s+table|truncate\s+table)\b|"
    r"\.(?:QueryRow|QueryContext|QueryRowContext|Exec|ExecContext|"
    r"Prepare|PrepareContext|Begin|BeginTx|Commit|Rollback|Ping|PingContext)\s*\("
    r"|\.Query\s*\([^)]|"
    r"\b(?:SetMaxOpenConns|SetMaxIdleConns|SetConnMaxLifetime|SetConnMaxIdleTime)\s*\("
    r"|"
    r"\b(?:sql\.Tx|sql\.Stmt|sql\.Rows|sql\.Result|pgx\.Batch|pgxpool\.Pool)\b"
    r")"
)
CONCRETE_MQ_OPS = re.compile(
    r"(?i)(?:"
    r"\b(?:puback|mosquitto)\b|"
    r"\.(?:Publish|Subscribe|Unsubscribe|SubscribeMultiple|UnsubscribeMultiple)\s*\("
    r"|"
    r"\b(?:AddBroker|SetClientID|SetCleanSession|SetKeepAlive|SetAutoReconnect|"
    r"SetConnectRetry|SetConnectRetryInterval|SetMaxReconnectInterval|"
    r"SetSessionExpiryInterval|SetOrderMatters|SetDefaultPublishHandler|"
    r"SetConnectionLostHandler|SetOnConnectHandler|SetReconnectingHandler|"
    r"NewClientOptions)\s*\("
    r"|"
    r"\b(?:mqtt\.Message|mqtt\.Client|mqtt\.Token|mqtt\.ClientOptions|"
    r"paho\.Message|paho\.Client|paho\.Token|paho\.ClientOptions)\b"
    r")"
)
CONCRETE_SC_OPS = re.compile(
    r"(?i)(?:\b(?:superframe|slot_id|beacon_sync|scheduler\.\w+)\b|\w*(?:tdma|timeslot)\w*)"
)


class StandardsError(ValueError):
    """Missing, stale, ambiguous or unbounded mandatory standards input."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


TRUSTED_SYSTEM_FILTERS = {
    "filter.lfs.clean": "git-lfs clean -- %f",
    "filter.lfs.process": "git-lfs filter-process",
    "filter.lfs.smudge": "git-lfs smudge -- %f",
}


def check_git_filters(repo, exc_class=StandardsError,
                      err_msg="Configured Git filters require trusted disposable checkout"):
    repo_path = Path(repo).resolve()
    cmd = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(repo_path),
           "config", "-z", "--show-origin", "--show-scope", "--get-regexp", r"^filter\..*\.(clean|process)$"]
    try:
        configured = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise exc_class(err_msg) from exc

    if configured.returncode not in (0, 1):
        raise exc_class(err_msg)

    if configured.returncode == 0 and configured.stdout:
        raw = configured.stdout
        parts = raw.split(b"\0")
        if len(parts) < 4 or (len(parts) - 1) % 3 != 0:
            raise exc_class(err_msg)

        for i in range(0, len(parts) - 1, 3):
            try:
                scope = parts[i].decode("utf-8", errors="strict").strip()
                origin = parts[i + 1].decode("utf-8", errors="strict").strip()
                key_val = parts[i + 2].decode("utf-8", errors="strict")
            except UnicodeError:
                raise exc_class(err_msg)

            key, sep, val = key_val.partition("\n")
            if not sep:
                raise exc_class(err_msg)
            key = key.strip()
            val = val.strip()

            if scope != "system":
                raise exc_class(err_msg)

            if not origin.startswith("file:"):
                raise exc_class(err_msg)

            raw_path = origin[5:]
            origin_path = Path(raw_path)
            if not origin_path.is_absolute():
                raise exc_class(err_msg)

            try:
                st = origin_path.lstat()
                if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
                    raise exc_class(err_msg)
                resolved_origin = origin_path.resolve(strict=True)
                if not stat.S_ISREG(resolved_origin.stat().st_mode):
                    raise exc_class(err_msg)
            except OSError:
                raise exc_class(err_msg)

            is_inside_repo = False
            try:
                resolved_origin.relative_to(repo_path)
                is_inside_repo = True
            except ValueError:
                is_inside_repo = False

            if is_inside_repo or resolved_origin.is_relative_to(repo_path):
                raise exc_class(err_msg)

            if key not in TRUSTED_SYSTEM_FILTERS or val != TRUSTED_SYSTEM_FILTERS[key]:
                raise exc_class(err_msg)

    try:
        for attr_file in repo_path.glob("**/.gitattributes"):
            if attr_file.is_symlink():
                raise exc_class(err_msg)
            if attr_file.is_file():
                for line in attr_file.read_text(errors="ignore").splitlines():
                    tokens = None
                    try:
                        tokens = shlex.split(line, comments=True)
                    except ValueError:
                        pass
                    if tokens is None:
                        raise exc_class(err_msg)
                    if len(tokens) >= 2:
                        for attr in tokens[1:]:
                            if attr == "filter" or attr.startswith("filter="):
                                raise exc_class(err_msg)

        gitdir_proc = subprocess.run(["git", "--no-optional-locks", "-C", str(repo_path), "rev-parse", "--git-dir"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, timeout=10, check=False)
        if gitdir_proc.returncode == 0:
            gitdir_str = gitdir_proc.stdout.decode("utf-8", errors="ignore").strip()
            gitdir = Path(gitdir_str)
            if not gitdir.is_absolute():
                gitdir = (repo_path / gitdir).resolve()
            info_attr = gitdir / "info" / "attributes"
            if info_attr.is_symlink():
                raise exc_class(err_msg)
            if info_attr.is_file():
                for line in info_attr.read_text(errors="ignore").splitlines():
                    tokens = None
                    try:
                        tokens = shlex.split(line, comments=True)
                    except ValueError:
                        pass
                    if tokens is None:
                        raise exc_class(err_msg)
                    if len(tokens) >= 2:
                        for attr in tokens[1:]:
                            if attr == "filter" or attr.startswith("filter="):
                                raise exc_class(err_msg)
    except (OSError, subprocess.SubprocessError):
        raise exc_class(err_msg)


def _git(repo, *args):
    if args and args[0] == "diff":
        check_git_filters(repo, StandardsError, "Configured Git filters require trusted disposable checkout")
    done = subprocess.run(["git", "--no-optional-locks", "-c", "core.fsmonitor=false",
                           "-c", "filter.lfs.clean=", "-c", "filter.lfs.process=", "-c", "filter.lfs.smudge=",
                           "-C", str(repo), *args], stdin=subprocess.DEVNULL,
                          capture_output=True, timeout=30, check=False)
    if done.returncode or len(done.stdout) > MAX_CODE_BYTES:
        raise StandardsError("Cannot verify standards source identity")
    return done.stdout


def _read(repo, name, limit=MAX_STANDARD_BYTES):
    if (not isinstance(name, str) or not name or name.startswith("/") or "\\" in name
            or ".." in PurePosixPath(name).parts or "\x00" in name):
        raise StandardsError("Unsafe standards/impact path")
    directory = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = PurePosixPath(name).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise StandardsError("Empty, nonregular or oversized standards/impact source")
        data = stream.read(limit + 1)
        if len(data) != info.st_size or b"\x00" in data:
            raise StandardsError("Standards/impact source changed or is not text")
        data.decode("utf-8", errors="strict")
        return data


def parse_standard(data: bytes, component: str) -> dict:
    """Validate complete fixed ID inventory and compact index, return atomic rows."""
    groups = GROUPS[component]
    lines = data.decode("utf-8", errors="strict").splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "| Group | Rule IDs |":
        raise StandardsError("Missing compact standards index")
    expected = {f"{group}-{n:03}" for group, size in groups.items() for n in range(1, size + 1)}
    indexed = {}
    for line in lines[1:]:
        if not line.startswith("|"):
            break
        if re.fullmatch(r"\|[- |]+\|\s*", line):
            continue
        match = re.fullmatch(r"\| ([A-Z]+) \| ([A-Z]+)-001\.\.([0-9]{3}) \|\s*", line)
        if not match or match[1] != match[2] or match[1] in indexed:
            raise StandardsError("Malformed or duplicate standards index")
        indexed[match[1]] = int(match[3])
    if indexed != groups:
        raise StandardsError("Broken or partial standards index")
    rules = {}
    in_rules = False
    fields = 5 if component == "C" else 6
    for number, line in enumerate(lines, 1):
        if line.startswith("| Rule ID | Scope | Directive | Verify |"):
            in_rules = True
            continue
        if not line.startswith("|"):
            in_rules = False
            continue
        if not in_rules or re.fullmatch(r"\|[- |]+\|\s*", line):
            continue
        cells = [x.strip() for x in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
        if (len(cells) != fields or not all(cells) or not RULE_ID.fullmatch(cells[0])
                or cells[0] not in expected or cells[0] in rules):
            raise StandardsError("Malformed, duplicate or unknown atomic Rule ID")
        rules[cells[0]] = {"rule_id": cells[0], "component": component,
                           "scope": cells[1], "directive": cells[2], "verify": cells[3],
                           "failure_action": cells[4].strip("`"),
                           "source": cells[5] if fields == 6 else STANDARDS[component] + "#15-sourceprovenance-and-migration-matrix",
                           "line": number, "text": line,
                           "rule_sha256": digest(line.encode("utf-8"))}
    if set(rules) != expected:
        raise StandardsError("Missing or partial atomic Rule ID inventory")
    return rules


def actual_paths(repo, base):
    names = _git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                 "--name-only", "-z", base).decode().split("\0")
    names += _git(repo, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    return sorted(set(filter(None, names)))


def _component(path):
    if path.startswith("firmware/") and not path.endswith(".md"):
        return "C"
    if (path.startswith("backend-go/") and not path.endswith(".md")) or path == ".go-version":
        return "GO"
    return None


def _impact(repo, paths):
    """Conservative transitive C include and local Go import caller/consumer closure."""
    names = _git(repo, "ls-files", "-z").decode().split("\0")
    names += _git(repo, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")
    code = {}
    total = 0
    for name in sorted(set(filter(None, names))):
        if not _component(name) or not name.endswith((".c", ".h", ".go", ".sql")):
            continue
        if not (repo / name).exists() and not (repo / name).is_symlink():
            continue
        raw = _read(repo, name, MAX_CODE_BYTES)
        total += len(raw)
        if total > MAX_CODE_BYTES or len(code) >= 2000:
            raise StandardsError("Code dependency inspection exceeds bounded budget")
        code[name] = raw
    edges = {name: set() for name in code}
    by_header = {}
    for name in code:
        if name.endswith(".h"):
            by_header.setdefault(PurePosixPath(name).name, set()).add(name)
    module = None
    if any(name.endswith(".go") for name in code):
        data = _read(repo, "backend-go/go.mod")
        match = re.search(rb"(?m)^module\s+(\S+)\s*$", data)
        if not match:
            raise StandardsError("Cannot resolve Go module dependency mapping")
        module = match[1].decode()
    packages = {}
    for name in code:
        if name.endswith(".go"):
            packages.setdefault(str(PurePosixPath(name).parent), set()).add(name)
    for name, raw in code.items():
        text = raw.decode()
        if name.endswith((".c", ".h")):
            for include in re.findall(r'(?m)^\s*#\s*include\s*[<"]([^>"\n]+)[>"]', text):
                matches = by_header.get(PurePosixPath(include).name, set())
                if len(matches) > 1:
                    raise StandardsError("Ambiguous local C include mapping")
                for header in matches:
                    edges[header].add(name)
            counterpart = str(PurePosixPath(name).with_suffix(".c" if name.endswith(".h") else ".h"))
            if counterpart in code:
                edges[name].add(counterpart)
                edges[counterpart].add(name)
        elif name.endswith(".go"):
            if name.endswith("_test.go"):
                base_source = str(PurePosixPath(name).with_name(PurePosixPath(name).name[:-8] + ".go"))
                if base_source in code:
                    edges[base_source].add(name)
            imports = re.findall(r'(?m)^\s*import\s+(?:\([^)]*\)|[^\n]+)', text)
            for imported in re.findall(r'"([^"\n]+)"', "\n".join(imports)):
                if imported.startswith(module + "/"):
                    package = "backend-go/" + imported[len(module) + 1:]
                    if package not in packages:
                        raise StandardsError("Unresolved local Go import mapping")
                    if package != str(PurePosixPath(name).parent):
                        for dep in packages[package]:
                            edges[dep].add(name)
    affected = set(paths)
    affected.update(name for name in code if any(name.startswith(p) for p in paths if p.endswith("/")))
    pending = list(affected)
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in affected:
                affected.add(target)
                pending.append(target)
    return sorted(affected), code


def forbidden(name: str) -> bool:
    p = PurePosixPath(name)
    return (p.name.startswith(".env") and p.name != ".env.example") or (
        p.suffix.lower() in {".key", ".p12", ".pfx", ".jks", ".keystore"}
        or "secrets" in p.parts or p.name == "mosquitto.passwd")


def compute_candidate_sha256(repo: Path, base: str = "HEAD") -> str:
    repo = Path(repo).resolve()
    head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    base_sha = _git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    staged = _git(repo, "ls-files", "--stage", "-z")
    flags = _git(repo, "ls-files", "-v", "-z").decode().split("\0")
    if any(entry and (entry[0].islower() or entry[0] == "S") for entry in flags):
        raise StandardsError("Hidden index flags can conceal changed-file routing")
    names = set(filter(None, _git(repo, "ls-files", "-z").decode().split("\0")))
    extra = set(filter(None, _git(repo, "ls-files", "--others", "--exclude-standard", "-z").decode().split("\0")))
    paths = sorted(set(filter(None, _git(repo, "diff", "--no-ext-diff", "--no-textconv",
                                       "--no-renames", "--name-only", "-z", base_sha).decode().split("\0"))) | extra)
    hashes = {}
    for name in sorted(names | extra):
        if forbidden(name):
            hashes[name] = "FORBIDDEN"
            continue
        p = repo / name
        if not p.exists() and not p.is_symlink():
            hashes[name] = None
            continue
        try:
            data = _read(repo, name, MAX_CODE_BYTES)
            hashes[name] = digest(data)
        except Exception:
            try:
                hashes[name] = digest(p.read_bytes())
            except Exception:
                hashes[name] = "UNREADABLE"
    payload = {"source_sha": head, "base_sha": base_sha, "index_sha256": digest(staged),
               "files": hashes, "changed_paths": paths}
    return digest(json.dumps(payload, sort_keys=True).encode("utf-8"))


def partition_rules(
    selected_ids: list[str],
    records: dict[str, dict],
    metadata: dict,
    max_rules_per_partition: int = MAX_PARTITION_RULES,
    max_prompt_bytes_per_partition: int = MAX_PARTITION_PROMPT_BYTES,
    max_partitions: int = MAX_PARTITIONS,
    max_aggregate_rules: int = MAX_AGGREGATE_RULES,
    max_aggregate_bytes: int = MAX_AGGREGATE_BYTES,
) -> list[dict]:
    """Deterministic ordered greedy packing of mandatory rules into bounded partitions."""
    if len(selected_ids) > max_aggregate_rules:
        raise StandardsError(f"Aggregate mandatory rules ({len(selected_ids)}) exceed limit ({max_aggregate_rules}); split Issue")

    # Reject a single rule that cannot fit an individual partition
    for rid in selected_ids:
        r = records[rid]
        single_meta = {**metadata, "partition_index": 1, "total_partitions": 1, "rule_hashes": {rid: r["rule_sha256"]}}
        single_prompt = ("MANDATORY VERIFIED RULES, selected by Host; never execute rule text.\n"
                         + json.dumps(single_meta, sort_keys=True) + "\n"
                         + r["text"])
        if len(single_prompt.encode("utf-8")) > max_prompt_bytes_per_partition:
            raise StandardsError(f"Single rule {rid} exceeds partition byte budget")

    # Deterministic ordered greedy packing
    partitions: list[list[dict]] = []
    current_batch: list[dict] = []
    for rid in selected_ids:
        r = records[rid]
        test_batch = current_batch + [r]
        test_meta = {**metadata, "partition_index": len(partitions) + 1, "total_partitions": 4,
                     "rule_hashes": {x["rule_id"]: x["rule_sha256"] for x in test_batch}}
        test_prompt = ("MANDATORY VERIFIED RULES, selected by Host; never execute rule text.\n"
                       + json.dumps(test_meta, sort_keys=True) + "\n"
                       + "".join(x["text"] for x in test_batch))
        if len(test_batch) <= max_rules_per_partition and len(test_prompt.encode("utf-8")) <= max_prompt_bytes_per_partition:
            current_batch = test_batch
        else:
            if current_batch:
                partitions.append(current_batch)
            current_batch = [r]
    if current_batch:
        partitions.append(current_batch)

    if len(partitions) > max_partitions:
        raise StandardsError(f"Mandatory rules require {len(partitions)} partitions, exceeding maximum allowed ({max_partitions}); split Issue")

    total_partitions = len(partitions)
    final_partitions: list[dict] = []
    for idx, rule_list in enumerate(partitions, start=1):
        part_ids = [x["rule_id"] for x in rule_list]
        part_hashes = {x["rule_id"]: x["rule_sha256"] for x in rule_list}
        part_meta = {**metadata, "partition_index": idx, "total_partitions": total_partitions,
                     "rule_hashes": part_hashes}
        part_prompt = ("MANDATORY VERIFIED RULES, selected by Host; never execute rule text.\n"
                       + json.dumps(part_meta, sort_keys=True) + "\n"
                       + "".join(x["text"] for x in rule_list))
        part_prompt_bytes = len(part_prompt.encode("utf-8"))
        if len(rule_list) > max_rules_per_partition or part_prompt_bytes > max_prompt_bytes_per_partition:
            raise StandardsError(f"Partition {idx} exceeds partition budget")
        part_dict = {
            "partition_index": idx,
            "total_partitions": total_partitions,
            "selected_ids": part_ids,
            "rules": rule_list,
            "rule_hashes": part_hashes,
            "agent_input": part_prompt,
            "agent_input_sha256": digest(part_prompt.encode("utf-8")),
            "prompt_bytes": part_prompt_bytes,
        }
        part_dict["partition_hash"] = digest(json.dumps({k: val for k, val in part_dict.items() if k != "partition_hash"},
                                                        sort_keys=True, separators=(",", ":")).encode("utf-8"))
        final_partitions.append(part_dict)

    # Invariants verification
    total_bytes = sum(p["prompt_bytes"] for p in final_partitions)
    if total_bytes > max_aggregate_bytes:
        raise StandardsError(f"Total serialized partition bytes ({total_bytes}) exceed aggregate limit ({max_aggregate_bytes}); split Issue")
    all_partition_ids = [rid for p in final_partitions for rid in p["selected_ids"]]
    if all_partition_ids != selected_ids:
        raise StandardsError("Partitions do not match complete mandatory union")
    if len(all_partition_ids) != len(set(all_partition_ids)):
        raise StandardsError("Partitions have overlapping rule IDs")
    for p in final_partitions:
        for r in p["rules"]:
            if digest(r["text"].encode("utf-8")) != r["rule_sha256"]:
                raise StandardsError(f"Rule {r['rule_id']} text hash mismatch")

    return final_partitions


def _payload_hash(selection):
    return digest(json.dumps({k: v for k, v in selection.items() if k != "selection_sha256"},
                             sort_keys=True, separators=(",", ":")).encode("utf-8"))


def select_rules(repo: Path, allowed_paths=(), changed_paths=None, requested_ids=(),
                 base="HEAD", expected_source_sha=None, version=None, candidate_sha256=None) -> dict:
    """Union Host baseline, dependency/path/operation rules and valid Coordinator IDs."""
    try:
        repo = Path(repo).resolve(strict=True)
        if base.startswith("-"):
            raise StandardsError("Unsafe base")
        head = _git(repo, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
        base_sha = _git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
        if expected_source_sha is not None and expected_source_sha != head:
            raise StandardsError("Wrong standards source SHA")
        allowed = sorted(set(allowed_paths))
        current = actual_paths(repo, base_sha)
        if changed_paths is not None and sorted(set(changed_paths)) != current:
            raise StandardsError("Supplied changed paths omit or differ from actual diff")
        if allowed and violations(repo, allowed, current):
            raise StandardsError("Actual diff exceeds Issue allowlist")
        if any(not isinstance(p, str) or not p or p.startswith("/") or ".." in PurePosixPath(p).parts
               or "\\" in p or any(c in p for c in "*?[]{}") for p in allowed):
            raise StandardsError("Unsafe or unbounded allowed paths")
        requested = list(requested_ids)
        if (len(requested) > MAX_AGGREGATE_RULES or len(set(requested)) != len(requested)
                or any(not isinstance(r, str) or not RULE_ID.fullmatch(r) for r in requested)):
            raise StandardsError("Malformed, duplicate or unbounded requested Rule IDs")
        known = {f"{g}-{n:03}": component for component, groups in GROUPS.items()
                 for g, count in groups.items() for n in range(1, count + 1)}
        if set(requested) - set(known):
            raise StandardsError("Unknown requested Rule ID")
        paths = sorted(set(current + allowed))
        components = {c for p in paths if (c := _component(p))}
        components.update(known[r] for r in requested)
        impact_seeds = current if current else allowed
        impact, code = _impact(repo, impact_seeds) if components else (paths, {})
        components.update(c for p in impact if (c := _component(p)))
        selected = set(requested)
        standards = {}
        records = {}
        for component in sorted(components):
            name = STANDARDS[component]
            raw = _read(repo, name)
            blob = _git(repo, "rev-parse", "--verify", "HEAD:" + name).decode().strip()
            if _git(repo, "hash-object", "--no-filters", "--", name).decode().strip() != blob:
                raise StandardsError("Standard differs from tracked HEAD")
            _git(repo, "diff", "--no-ext-diff", "--no-textconv", "--cached", "--quiet", "HEAD", "--", name)
            rows = parse_standard(raw, component)
            records.update(rows)
            standards[component] = {"path": name, "git_blob_sha": blob, "sha256": digest(raw)}
            selected.update(BASELINE[component])
            groups = set()
            for path in impact:
                if _component(path) != component:
                    continue
                if component == "C":
                    if path.endswith((".c", ".h", "/")):
                        selected.update(f"C-{n:03}" for n in (1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 19, 20))
                    if path.endswith((".c", "/")):
                        selected.update(("C-003", "C-015"))
                    if path.endswith((".h", "/")):
                        selected.update(("C-004", "C-005", "C-012"))
                    if PurePosixPath(path).name == "CMakeLists.txt" or path.endswith(".cmake"):
                        selected.add("C-006")
                        groups.add("ARCH")
                elif path.endswith((".go", "/")):
                    groups.update(("GB", "GGS", "GO", "QG", "AI"))
                    if path.endswith("_test.go"):
                        selected.add("TS-001")
                elif PurePosixPath(path).name in ("go.mod", "go.sum"):
                    groups.update(("GB", "AR", "QG", "AI"))
                    selected.add("SE-008")
                elif path == ".go-version":
                    groups.add("QG")
                parts = PurePosixPath(path).parts if path.endswith("/") else PurePosixPath(path).parent.parts
                for token, applicable in PATH_GROUPS[component].items():
                    if "/" in token:
                        matched = f"/{token}/" in f"/{path.rstrip('/')}/" or path.rstrip("/").endswith("/" + token)
                    elif component == "GO":
                        matched = token in parts
                    else:
                        matched = any(token in p for p in parts)
                    if matched:
                        groups.update(applicable)
                text = (path + "\n" + code.get(path, b"").decode())
                text += "\n" + text.replace("_", " ")
                is_comp_or_config = component == "GO" and any(
                    (path.rstrip("/") + "/").startswith(prefix)
                    for prefix in GO_COMPOSITION_AND_CONFIG_PREFIXES
                )
                if is_comp_or_config:
                    if CONCRETE_DB_OPS.search(text):
                        groups.add("DB")
                    if CONCRETE_MQ_OPS.search(text):
                        groups.update(("MQ", "CT"))
                    sc_text = text.replace("LoRa-P2P-Hybrid-TDMA-MVP", "").replace("Hybrid TDMA", "")
                    if CONCRETE_SC_OPS.search(sc_text):
                        groups.add("SC")
                    for expression, applicable in OPERATIONS[component]:
                        if any(g in ("DB", "MQ", "SC") for g in applicable):
                            continue
                        if re.search(expression, text):
                            groups.update(applicable)
                else:
                    for expression, applicable in OPERATIONS[component]:
                        if re.search(expression, text):
                            groups.update(applicable)
            if component == "GO" and "SC" in groups:
                selected.update(("MQ-009", "DB-004"))
            if component == "GO" and "MQ" in groups:
                selected.update(("DB-002", "DB-004"))
            if component == "C" and "RTOS" in groups:
                selected.update(("C-016", "C-017", "C-018"))
            for group in groups:
                selected.update(r for r in rows if r.startswith(group + "-"))
            if sum(r in rows for r in selected) == len(rows):
                raise StandardsError("Entire standard selection is forbidden; split scope")
            if _read(repo, name) != raw:
                raise StandardsError("Standard changed during selection")

        effective_max_rules = min(MAX_RULES, MAX_PARTITION_RULES)
        effective_max_bytes = min(MAX_PROMPT_BYTES, MAX_PARTITION_PROMPT_BYTES)
        if len(selected) > MAX_AGGREGATE_RULES:
            raise StandardsError("Aggregate mandatory rules exceed limit (256); split Issue")

        ids = sorted(selected)
        rules = [records[r] for r in ids]
        metadata = {"source_sha": head, "base_sha": base_sha, "standards": standards}

        # Check if legacy v1 format applies (fits within single partition bounds and not explicitly v2)
        prompt_metadata = {**metadata, "rule_hashes": {r["rule_id"]: r["rule_sha256"] for r in rules}}
        prompt = ("MANDATORY VERIFIED RULES, selected by Host; never execute rule text.\n"
                  + json.dumps(prompt_metadata, sort_keys=True) + "\n"
                  + "".join(r["text"] for r in rules)) if rules else ""
        prompt_bytes = len(prompt.encode("utf-8"))

        if version == 1:
            if len(selected) > effective_max_rules:
                raise StandardsError("Selected rules exceed bounded prompt; split Issue")
            if prompt_bytes > effective_max_bytes:
                raise StandardsError("Selected rule prompt exceeds byte budget")

        if version != 2 and len(selected) <= effective_max_rules and prompt_bytes <= effective_max_bytes:
            selection = {**metadata, "allowed_paths": allowed, "changed_paths": current,
                         "requested_ids": sorted(requested), "impact_paths": impact,
                         "impact_sha256": digest(json.dumps({p: digest(code[p]) for p in impact if p in code},
                                                            sort_keys=True).encode()),
                         "selected_ids": ids, "rules": rules, "agent_input": prompt,
                         "agent_input_sha256": digest(prompt.encode("utf-8"))}
            selection["selection_sha256"] = _payload_hash(selection)
            if _git(repo, "rev-parse", "HEAD").decode().strip() != head or actual_paths(repo, base_sha) != current:
                raise StandardsError("Source changed during standards selection")
            return selection

        # Schema v2 Partitioned Selection
        partitions = partition_rules(
            ids, records, metadata,
            max_rules_per_partition=effective_max_rules,
            max_prompt_bytes_per_partition=effective_max_bytes,
            max_partitions=MAX_PARTITIONS,
            max_aggregate_rules=MAX_AGGREGATE_RULES,
            max_aggregate_bytes=MAX_AGGREGATE_BYTES,
        )
        combined_prompt = "\n".join(p["agent_input"] for p in partitions) if partitions else ""
        diff_bytes = _git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", base_sha)
        diff_sha256 = digest(diff_bytes)
        if candidate_sha256 is None:
            candidate_sha256 = compute_candidate_sha256(repo, base_sha)
        aggregate_union_hash = digest(json.dumps({
            "selected_ids": ids,
            "rule_hashes": {r["rule_id"]: r["rule_sha256"] for r in rules},
        }, sort_keys=True, separators=(",", ":")).encode("utf-8"))

        selection = {
            "schema_version": 2,
            "base_sha": base_sha,
            "source_sha": head,
            "candidate_sha256": candidate_sha256,
            "diff_sha256": diff_sha256,
            "allowed_paths": allowed,
            "changed_paths": current,
            "impact_paths": impact,
            "impact_sha256": digest(json.dumps({p: digest(code[p]) for p in impact if p in code},
                                               sort_keys=True).encode()),
            "requested_ids": sorted(requested),
            "standards": standards,
            "selected_ids": ids,
            "rules": rules,
            "rule_count": len(ids),
            "partition_count": len(partitions),
            "total_partition_bytes": sum(p["prompt_bytes"] for p in partitions),
            "partitions": partitions,
            "aggregate_union_hash": aggregate_union_hash,
            "agent_input": combined_prompt,
            "agent_input_sha256": digest(combined_prompt.encode("utf-8")),
        }
        selection["selection_sha256"] = _payload_hash(selection)
        if _git(repo, "rev-parse", "HEAD").decode().strip() != head or actual_paths(repo, base_sha) != current:
            raise StandardsError("Source changed during standards selection")
        return selection
    except StandardsError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as exc:
        raise StandardsError("Standards source, index or dependency verification failed") from exc


def verify_selection(repo, selection):
    if not isinstance(selection, dict) or _payload_hash(selection) != selection.get("selection_sha256"):
        raise StandardsError("Selection text/hash was changed")
    v = selection.get("schema_version", 1)
    if v not in (1, 2):
        raise StandardsError(f"Unsupported selection schema version: {v}")
    if v == 2:
        required_v2_keys = {
            "schema_version", "base_sha", "source_sha", "candidate_sha256", "diff_sha256",
            "allowed_paths", "changed_paths", "impact_paths", "impact_sha256", "requested_ids",
            "standards", "selected_ids", "rules", "rule_count", "partition_count",
            "total_partition_bytes", "partitions", "aggregate_union_hash",
            "agent_input", "agent_input_sha256", "selection_sha256"
        }
        if set(selection) != required_v2_keys:
            raise StandardsError("Malformed v2 selection schema")
        parts = selection["partitions"]
        if not isinstance(parts, list) or len(parts) != selection["partition_count"] or len(parts) > MAX_PARTITIONS:
            raise StandardsError("Invalid partition manifest")
        all_ids = []
        for idx, p in enumerate(parts, 1):
            if not isinstance(p, dict):
                raise StandardsError("Invalid partition record")
            expected_p_keys = {
                "partition_index", "total_partitions", "selected_ids", "rules",
                "rule_hashes", "agent_input", "agent_input_sha256", "prompt_bytes", "partition_hash"
            }
            if set(p) != expected_p_keys:
                raise StandardsError("Malformed partition manifest record")
            if p["partition_index"] != idx or p["total_partitions"] != len(parts):
                raise StandardsError("Partition ordering or count mismatch")
            if len(p["selected_ids"]) > MAX_PARTITION_RULES or p["prompt_bytes"] > MAX_PARTITION_PROMPT_BYTES:
                raise StandardsError("Partition exceeds bounded resource limits")
            p_hash = digest(json.dumps({k: val for k, val in p.items() if k != "partition_hash"},
                                       sort_keys=True, separators=(",", ":")).encode("utf-8"))
            if p["partition_hash"] != p_hash:
                raise StandardsError("Partition hash tampered")
            all_ids.extend(p["selected_ids"])
        if all_ids != selection["selected_ids"] or len(all_ids) != len(set(all_ids)):
            raise StandardsError("Partitions do not match complete mandatory union")
        current = select_rules(
            repo, selection["allowed_paths"], requested_ids=selection["requested_ids"],
            base=selection["base_sha"], expected_source_sha=selection["source_sha"],
            version=2, candidate_sha256=selection["candidate_sha256"],
        )
        if current != selection:
            raise StandardsError("Stale rule selection; recompute and reinject before edit/review")
        return current
    current = select_rules(repo, selection["allowed_paths"], requested_ids=selection["requested_ids"],
                           base=selection["base_sha"], expected_source_sha=selection["source_sha"],
                           version=1)
    if current != selection:
        raise StandardsError("Stale rule selection; recompute and reinject before edit/review")
    return current
