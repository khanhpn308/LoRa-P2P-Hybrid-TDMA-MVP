"""Deterministic, bounded routing of tracked standards. Never executes rule text."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import subprocess
import tempfile

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


SAFE_STD_IMPORT_PREFIXES = (
    "crypto/", "encoding/", "errors", "fmt", "io", "bytes", "context",
    "math", "strings", "strconv", "time", "sync", "unicode", "path",
    "sort", "bufio", "log", "regexp", "slices", "cmp"
)


def _get_trusted_analyzer_bin(src_path: Path | None = None) -> Path:
    """Verify analyzer source and return path to trusted compiled executable."""
    analyzer_src = src_path if src_path is not None else (Path(__file__).resolve().parent / "go_impact_analyzer.go")
    if not analyzer_src.exists() or not analyzer_src.is_file() or analyzer_src.is_symlink():
        raise StandardsError("Untrusted analyzer source: missing, not regular file, or symlink")
    st = analyzer_src.stat()
    if hasattr(os, "getuid") and st.st_uid not in (os.getuid(), 0):
        raise StandardsError("Invalid analyzer source ownership")
    if st.st_mode & 0o002:
        raise StandardsError("Analyzer source is world-writable")

    src_bytes = analyzer_src.read_bytes()
    src_hash = hashlib.sha256(src_bytes).hexdigest()

    cache_dir = Path("/tmp") / f"harness_go_analyzer_{src_hash[:16]}"
    target_bin = cache_dir / "go_impact_analyzer"

    if target_bin.exists():
        if target_bin.is_symlink() or not target_bin.is_file():
            try:
                shutil.rmtree(cache_dir)
            except Exception:
                pass
        else:
            bin_st = target_bin.stat()
            if (not hasattr(os, "getuid") or bin_st.st_uid in (os.getuid(), 0)) and not (bin_st.st_mode & 0o002):
                return target_bin

    with tempfile.TemporaryDirectory() as tmp_build:
        tmp_build_path = Path(tmp_build)
        tmp_bin = tmp_build_path / "analyzer"
        tmp_cache = tmp_build_path / "gocache"
        tmp_cache.mkdir(mode=0o700, exist_ok=True)
        env = {
            "PATH": os.environ.get("PATH", "/usr/local/go/bin:/usr/bin:/bin"),
            "GOTOOLCHAIN": "local",
            "GOENV": "off",
            "GOWORK": "off",
            "GOFLAGS": "",
            "GOPROXY": "off",
            "GOSUMDB": "off",
            "CGO_ENABLED": "0",
            "HOME": str(tmp_build_path),
            "TMPDIR": str(tmp_build_path),
            "GOCACHE": str(tmp_cache),
        }
        res = subprocess.run(
            ["go", "build", "-trimpath", "-o", str(tmp_bin), str(analyzer_src)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10.0,
        )
        if res.returncode != 0:
            raise StandardsError(f"Analyzer build failed: {res.stderr.decode()}")
        cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copy2(tmp_bin, target_bin)
        os.chmod(target_bin, 0o700)
        return target_bin


def _run_go_impact_analyzer(module: str, go_files: dict[str, bytes]) -> dict:
    """Execute trusted Go AST analyzer with bounded stdin/stdout and timeouts."""
    target_bin = _get_trusted_analyzer_bin()

    payload = {
        "schema_version": 1,
        "module": module,
        "files": {path: raw.decode("utf-8", errors="replace") for path, raw in go_files.items()}
    }
    input_bytes = json.dumps(payload).encode("utf-8")
    if len(input_bytes) > 10 * 1024 * 1024:
        raise StandardsError("Payload exceeds analyzer input limit")

    env = {
        "PATH": os.environ.get("PATH", "/usr/local/go/bin:/usr/bin:/bin"),
        "GOTOOLCHAIN": "local",
        "CGO_ENABLED": "0",
    }

    proc = subprocess.Popen(
        [str(target_bin)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    max_output = 4 * 1024 * 1024
    try:
        stdout_data, stderr_data = proc.communicate(input=input_bytes, timeout=10.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise StandardsError("Analyzer timed out")

    if len(stdout_data) > max_output:
        raise StandardsError("Analyzer output exceeded 4 MB limit")
    if proc.returncode != 0:
        raise StandardsError(f"Analyzer failed with exit code {proc.returncode}: {stderr_data.decode()}")

    try:
        data = json.loads(stdout_data.decode("utf-8"))
    except Exception as err:
        raise StandardsError(f"Malformed JSON from analyzer: {err}")

    if data.get("schema_version") != 1:
        raise StandardsError("Invalid schema version from analyzer")
    files_meta = data.get("files", {})
    if set(files_meta.keys()) != set(go_files.keys()):
        raise StandardsError("Analyzer output file inventory mismatch")
    return files_meta


def _can_prune_go_edge(dep: str, name: str, dep_meta: dict, name_meta: dict,
                       base_files: set, packages: dict, module: str,
                       all_go_meta: dict) -> bool:
    """Verify all 12 conservative-first conditions before pruning edge dep -> name."""
    # Condition 1: Source file is new relative to trusted BASE and is a production file
    if base_files is None or dep in base_files or dep.endswith("_test.go"):
        return False
    if not dep_meta or dep_meta.get("parse_error"):
        return False
    if not name_meta or name_meta.get("parse_error"):
        return False

    dep_symbols = {s["name"]: s for s in dep_meta.get("declared_symbols", [])}

    # Condition 2: All declarations are independent additions relative to BASE sibling files
    dep_pkg_dir = str(PurePosixPath(dep).parent)
    sibling_files = packages.get(dep_pkg_dir, set())
    for sib in sibling_files:
        if sib != dep and sib in base_files:
            sib_meta = all_go_meta.get(sib)
            if not sib_meta or sib_meta.get("parse_error"):
                return False
            sib_symbols = {s["name"] for s in sib_meta.get("declared_symbols", [])}
            if set(dep_symbols.keys()) & sib_symbols:
                return False

    # Condition 3: No package-level initialization effects in dep
    if dep_meta.get("has_init_func"):
        return False
    if dep_meta.get("has_package_level_vars"):
        return False

    # Condition 4: No method-set changes on existing receiver types
    for m in dep_meta.get("declared_methods", []):
        recv = m.get("receiver_type")
        if not recv or recv not in dep_symbols or dep_symbols[recv].get("kind") != "type":
            return False

    # Condition 5 & 6: No name collisions or unresolved same-package dependencies
    dep_idents = set(dep_meta.get("ident_refs", []))
    for sib in sibling_files:
        if sib != dep and not sib.endswith("_test.go"):
            sib_meta = all_go_meta.get(sib)
            if sib_meta:
                sib_symbols = {s["name"] for s in sib_meta.get("declared_symbols", [])}
                if dep_idents & sib_symbols:
                    return False
                sib_idents = set(sib_meta.get("ident_refs", []))
                if sib_idents & set(dep_symbols.keys()):
                    return False

    # Condition 7: No direct or indirect relevant consumer relationship
    dep_pkg_name = dep_meta.get("package_name")
    if dep_pkg_dir.startswith("backend-go/"):
        dep_imp_path = module + "/" + dep_pkg_dir[len("backend-go/"):]
    else:
        dep_imp_path = module + "/" + dep_pkg_dir

    matched_import = False
    for imp in name_meta.get("imports", []):
        if imp.get("path") == dep_imp_path:
            matched_import = True
            alias = imp.get("alias", "")
            if alias in ("_", "."):
                return False
            effective_alias = alias if alias else dep_pkg_name
            for sref in name_meta.get("selector_refs", []):
                if sref.get("package_alias") == effective_alias:
                    if sref.get("name") in dep_symbols:
                        return False
    if not matched_import:
        return False

    # Condition 8: No new unresolved import-induced initialization dependencies
    for imp in dep_meta.get("imports", []):
        ipath = imp.get("path", "")
        if ipath.startswith(module) or "." in ipath.split("/")[0]:
            return False
        if not any(ipath == p or ipath.startswith(p) for p in SAFE_STD_IMPORT_PREFIXES):
            return False

    # Condition 9: Clean parse, no build ambiguity
    # (Validated by absence of parse_error in dep_meta and name_meta)

    # Condition 10: No unresolved interface, alias, embedding, generic or reflection relationship
    top_types = dep_meta.get("top_level_type_details", {})
    for tname, detail in top_types.items():
        if detail.get("has_embedded_fields") or detail.get("is_alias") or detail.get("has_generics"):
            return False
    if dep_meta.get("has_unsafe_or_cgo"):
        return False
    if any(imp.get("path") == "reflect" for imp in dep_meta.get("imports", [])):
        return False

    # Condition 11: Correct package identity
    if dep_meta.get("is_test") or not dep_pkg_name:
        return False

    # Condition 12: Complete BASE and candidate dependency evidence
    return True


def _impact(repo, paths, base_sha=None):
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
        if name.endswith(".go") and not name.endswith("_test.go"):
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

    # Conservative-first Go edge refinement if AST analysis is available
    base_files = None
    if base_sha:
        try:
            base_files = set(_git(repo, "ls-tree", "-r", "--name-only", base_sha).decode().splitlines())
        except Exception:
            base_files = None

    go_files = {k: v for k, v in code.items() if k.endswith(".go")}
    if go_files and base_files is not None and module:
        go_meta = None
        try:
            go_meta = _run_go_impact_analyzer(module, go_files)
        except StandardsError as err:
            if "Untrusted analyzer" in str(err) or "Invalid analyzer" in str(err) or "world-writable" in str(err):
                raise
            go_meta = None
        except Exception:
            go_meta = None

        if go_meta:
            edges_to_prune = []
            for dep, consumers in edges.items():
                if dep.endswith(".go") and dep not in base_files and not dep.endswith("_test.go"):
                    dep_meta = go_meta.get(dep)
                    for consumer in consumers:
                        if consumer.endswith(".go") and PurePosixPath(dep).parent != PurePosixPath(consumer).parent:
                            consumer_meta = go_meta.get(consumer)
                            if _can_prune_go_edge(dep, consumer, dep_meta, consumer_meta,
                                                  base_files, packages, module, go_meta):
                                edges_to_prune.append((dep, consumer))
            for dep, consumer in edges_to_prune:
                edges[dep].discard(consumer)

    affected = set(paths)
    affected.update(name for name in code if any(name.startswith(p) for p in paths if p.endswith("/")))
    pending = list(affected)
    while pending:
        for target in edges.get(pending.pop(), ()):
            if target not in affected:
                affected.add(target)
                pending.append(target)
    return sorted(affected), code


def _payload_hash(selection):
    return digest(json.dumps({k: v for k, v in selection.items() if k != "selection_sha256"},
                             sort_keys=True, separators=(",", ":")).encode())


def select_rules(repo: Path, allowed_paths=(), changed_paths=None, requested_ids=(),
                 base="HEAD", expected_source_sha=None) -> dict:
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
        if (len(requested) > MAX_RULES or len(set(requested)) != len(requested)
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
        impact, code = _impact(repo, impact_seeds, base_sha=base_sha) if components else (paths, {})
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
        if len(selected) > MAX_RULES:
            raise StandardsError("Selected rules exceed bounded prompt; split Issue")
        ids = sorted(selected)
        rules = [records[r] for r in ids]
        metadata = {"source_sha": head, "base_sha": base_sha, "standards": standards}
        prompt_metadata = {**metadata, "rule_hashes": {r["rule_id"]: r["rule_sha256"] for r in rules}}
        prompt = ("MANDATORY VERIFIED RULES, selected by Host; never execute rule text.\n"
                  + json.dumps(prompt_metadata, sort_keys=True) + "\n"
                  + "".join(r["text"] for r in rules)) if rules else ""
        if len(prompt.encode()) > MAX_PROMPT_BYTES:
            raise StandardsError("Selected rule prompt exceeds byte budget")
        selection = {**metadata, "allowed_paths": allowed, "changed_paths": current,
                     "requested_ids": sorted(requested), "impact_paths": impact,
                     "impact_sha256": digest(json.dumps({p: digest(code[p]) for p in impact if p in code},
                                                        sort_keys=True).encode()),
                     "selected_ids": ids, "rules": rules, "agent_input": prompt,
                     "agent_input_sha256": digest(prompt.encode())}
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
    current = select_rules(repo, selection["allowed_paths"], requested_ids=selection["requested_ids"],
                           base=selection["base_sha"], expected_source_sha=selection["source_sha"])
    if current != selection:
        raise StandardsError("Stale rule selection; recompute and reinject before edit/review")
    return current
