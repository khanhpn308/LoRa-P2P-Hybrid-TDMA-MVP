#!/usr/bin/env python3
"""Structural dependency boundary enforcement for firmware C, Go, clients, and contracts (H2-INS-06 / FBK-04).

Uses actual CMake/C include graphs, Go package import graphs, TypeScript/JS module imports,
and OpenAPI/JSON-Schema $ref resolution—never raw substring grep. Read-only.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import pathlib
import re
import sys
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML is in environment
    yaml = None

DOMAINS = ("firmware", "backend-go", "clients", "contracts")
MAX_SCAN_FILE_BYTES = 2_000_000

_C_COMMENT_RE = re.compile(r"//[^\n]*|/\*[\s\S]*?\*/")
_C_INCLUDE_RE = re.compile(r'^\s*#\s*include\s*"([^"\n]+)"', re.MULTILINE)
_CMAKE_REGISTER_RE = re.compile(r"idf_component_register\s*\(([\s\S]*?)\)", re.IGNORECASE)
_CMAKE_KW_RE = re.compile(
    r"\b(SRCS|INCLUDE_DIRS|PRIV_INCLUDE_DIRS|REQUIRES|PRIV_REQUIRES|LDFRAGMENTS|EMBED_FILES|EMBED_TXTFILES)\b"
)
_CMAKE_EXTRA_DIRS_RE = re.compile(r"set\s*\(\s*EXTRA_COMPONENT_DIRS\s+([^)]+)\)", re.IGNORECASE)

_GO_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_GO_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_GO_MOD_RE = re.compile(r"^\s*module\s+(\S+)", re.MULTILINE)
_GO_MOD_REQ_RE = re.compile(r"^\s*(?:require\s+)?([A-Za-z0-9._~/-]+)\s+v[0-9]", re.MULTILINE)
_GO_IMPORT_SINGLE_RE = re.compile(r'^\s*import\s+(?:[A-Za-z_][A-Za-z0-9_]*|\.)?\s*"([^"]+)"', re.MULTILINE)
_GO_IMPORT_BLOCK_RE = re.compile(r"^\s*import\s*\(([\s\S]*?)\)", re.MULTILINE)
_GO_IMPORT_ENTRY_RE = re.compile(r'"([^"]+)"')

_TS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:type\s+)?(?:[\s\S]*?\s+from\s+)?|export\s+[\s\S]*?\s+from\s+|require\s*\(\s*|import\s*\(\s*)["']([^"']+)["']""",
    re.MULTILINE,
)

FORBIDDEN_STACK_TOKENS = ("lorawan", "lmic", "chirpstack", "sx126x")
FORBIDDEN_BACKEND_TOKENS = ("redis", "influxdb", "gorm.io", "lorawan", "chirpstack")
FORBIDDEN_CLIENT_DB_PKGS = frozenset({
    "pg", "pg-pool", "postgres", "mysql", "mysql2", "sqlite3", "better-sqlite3",
    "prisma", "@prisma/client", "typeorm", "drizzle-orm", "sequelize", "knex",
    "mqtt", "aedes", "mosquitto", "ioredis", "redis",
})


@dataclass(frozen=True)
class BoundaryViolation:
    rule_id: str
    domain: str
    path: str
    line: int
    source: str
    reason: str
    fix: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_text_safe(root: pathlib.Path, path: pathlib.Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        return None
    if resolved.stat().st_size > MAX_SCAN_FILE_BYTES:
        return None
    return resolved.read_text(encoding="utf-8", errors="replace")


def _rel(root: pathlib.Path, path: pathlib.Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def _strip_c_comments(text: str) -> str:
    # Preserve line numbers by replacing comment content with spaces/newlines.
    def _repl(match: re.Match[str]) -> str:
        return "".join("\n" if ch == "\n" else " " for ch in match.group(0))

    return _C_COMMENT_RE.sub(_repl, text)


def _strip_go_comments_preserve_strings(text: str) -> str:
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
        elif ch == "`":
            out.append(ch)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "`":
                    i += 1
                    break
                i += 1
        elif ch == "'" :
            out.append(ch)
            i += 1
            while i < n:
                out.append(text[i])
                if text[i] == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            out.append("  ")
            i += 2
            while i < n and not (text[i] == "*" and i + 1 < n and text[i + 1] == "/"):
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            if i + 1 < n:
                out.append("  ")
                i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _parse_cmake_requires(text: str) -> list[str]:
    cleaned = re.sub(r"#[^\n]*", "", text)
    reqs: list[str] = []
    for block in _CMAKE_REGISTER_RE.findall(cleaned):
        tokens = block.replace("\n", " ").split()
        active_kw: str | None = None
        for tok in tokens:
            if _CMAKE_KW_RE.fullmatch(tok):
                active_kw = tok
                continue
            if active_kw in ("REQUIRES", "PRIV_REQUIRES"):
                cleaned_tok = tok.strip('"').strip("'")
                if cleaned_tok and not cleaned_tok.startswith("${"):
                    reqs.append(cleaned_tok)
    return reqs


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []
    seen_cycle_keys: set[tuple[str, ...]] = set()

    def dfs(node: str) -> None:
        visiting.add(node)
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if nxt not in graph:
                continue
            if nxt in visiting:
                idx = stack.index(nxt)
                cyc = stack[idx:] + [nxt]
                canon = tuple(sorted(cyc[:-1]))
                if canon not in seen_cycle_keys:
                    seen_cycle_keys.add(canon)
                    cycles.append(cyc)
            elif nxt not in visited:
                dfs(nxt)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        if node not in visited:
            dfs(node)
    return cycles


def check_firmware_boundaries(repo: pathlib.Path) -> list[BoundaryViolation]:
    root = repo.resolve()
    fw_dir = root / "firmware"
    if not fw_dir.is_dir():
        return []

    violations: list[BoundaryViolation] = []

    # Discover components across the 3-tier ESP-IDF layout (REF-002 / REF-005).
    comp_tiers: dict[str, str] = {}
    comp_paths: dict[str, pathlib.Path] = {}
    header_owners: dict[str, set[str]] = {}

    tier_roots = [
        ("shared", fw_dir / "components"),
        ("gateway", fw_dir / "gateway_master" / "components"),
        ("sensor_node", fw_dir / "sensor_node" / "components"),
    ]
    for tier, base_dir in tier_roots:
        if not base_dir.is_dir():
            continue
        for comp_dir in sorted(p for p in base_dir.iterdir() if p.is_dir() and not p.is_symlink()):
            cname = comp_dir.name
            comp_tiers[cname] = tier
            comp_paths[cname] = comp_dir
            for hdr in comp_dir.rglob("*.h"):
                if hdr.is_symlink():
                    continue
                rel_hdr = hdr.relative_to(comp_dir).as_posix()
                if "/test/" in f"/{rel_hdr}":
                    continue
                header_owners.setdefault(hdr.name, set()).add(cname)

    # Record main entrypoints and check REF-001 main/ directory hygiene.
    main_headers: dict[str, str] = {}
    for app_name in ("gateway_master", "sensor_node"):
        app_dir = fw_dir / app_name
        main_dir = app_dir / "main"
        if not main_dir.is_dir():
            continue
        for f in sorted(main_dir.iterdir()):
            if f.is_symlink():
                continue
            if f.is_file():
                if f.suffix in (".c", ".cpp") and f.name != "main.c":
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-FW-005",
                            domain="firmware",
                            path=_rel(root, f),
                            line=1,
                            source=f.name,
                            reason=f"Application main/ must contain only main.c entrypoint; found subsystem source {f.name!r} (CCARS REF-001).",
                            fix=f"Relocate {f.name} to firmware/{app_name}/components/<component>/ and register it via CMakeLists.txt.",
                        )
                    )
                if f.suffix == ".h":
                    main_headers[f.name] = app_name

    # Build directed dependency graph from CMakeLists REQUIRES/PRIV_REQUIRES and non-test #includes.
    dep_graph: dict[str, set[str]] = {c: set() for c in comp_tiers}
    edge_meta: dict[tuple[str, str], tuple[str, int, str]] = {}

    for cname, comp_dir in sorted(comp_paths.items()):
        tier = comp_tiers[cname]
        cmake = comp_dir / "CMakeLists.txt"
        cmake_txt = _read_text_safe(root, cmake)
        if cmake_txt is not None:
            for req in _parse_cmake_requires(cmake_txt):
                low = req.lower()
                if any(tok in low for tok in FORBIDDEN_STACK_TOKENS):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-FW-004",
                            domain="firmware",
                            path=_rel(root, cmake),
                            line=1,
                            source=req,
                            reason=f"Forbidden external radio/LoRaWAN stack dependency {req!r} violates ARCH-005/GOV-005.",
                            fix=f"Remove {req!r} from CMakeLists.txt; use approved P2P custom MAC components (sx1276_driver, lora_mac).",
                        )
                    )
                if req in comp_tiers and req != cname:
                    dep_graph[cname].add(req)
                    edge_meta.setdefault((cname, req), (_rel(root, cmake), 1, f"CMake REQUIRES {req}"))

        # Check source and public/private header includes (excluding unit test mocks).
        for src in sorted(comp_dir.rglob("*")):
            if src.is_symlink() or not src.is_file() or src.suffix not in (".c", ".h"):
                continue
            rel_src = _rel(root, src)
            if "/test/" in f"/{rel_src}":
                continue
            raw = _read_text_safe(root, src)
            if raw is None:
                continue
            stripped = _strip_c_comments(raw)
            for match in _C_INCLUDE_RE.finditer(stripped):
                inc = match.group(1)
                line_no = stripped[: match.start()].count("\n") + 1
                inc_low = inc.lower()
                if any(tok in inc_low for tok in FORBIDDEN_STACK_TOKENS):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-FW-004",
                            domain="firmware",
                            path=rel_src,
                            line=line_no,
                            source=inc,
                            reason=f"Forbidden external stack header {inc!r} violates ARCH-005/GOV-005.",
                            fix="Remove LoRaWAN/unsupported transceiver headers and use approved P2P components.",
                        )
                    )
                    continue
                if "../main/" in inc or pathlib.PurePosixPath(inc).name in main_headers or (
                    inc in ("gateway_app.h", "node_app.h") and tier == "shared"
                ):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-FW-001" if tier == "shared" else "DEP-FW-002",
                            domain="firmware",
                            path=rel_src,
                            line=line_no,
                            source=inc,
                            reason=f"Component {cname!r} ({tier}) must not include application main header {inc!r} (REF-005).",
                            fix="Move shared declarations into a component public include/ header; main/ orchestrates components, never vice versa.",
                        )
                    )
                    continue

                base_hdr = pathlib.PurePosixPath(inc).name
                owners = header_owners.get(base_hdr, set())
                for target_comp in sorted(owners):
                    if target_comp == cname:
                        continue
                    dep_graph[cname].add(target_comp)
                    edge_meta.setdefault((cname, target_comp), (rel_src, line_no, f'#include "{inc}"'))

    # Enforce three-tier directionality across component edges.
    for src_comp, targets in sorted(dep_graph.items()):
        src_tier = comp_tiers[src_comp]
        for dst_comp in sorted(targets):
            dst_tier = comp_tiers[dst_comp]
            loc_path, loc_line, loc_src = edge_meta.get(
                (src_comp, dst_comp), (_rel(root, comp_paths[src_comp]), 1, dst_comp)
            )
            if src_tier == "shared" and dst_tier != "shared":
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-FW-001",
                        domain="firmware",
                        path=loc_path,
                        line=loc_line,
                        source=loc_src,
                        reason=(
                            f"Shared component {src_comp!r} depends on application-specific "
                            f"component {dst_comp!r} ({dst_tier}), violating three-tier boundary (CCARS REF-005)."
                        ),
                        fix=f"Invert the dependency via a callback/interface owned by {src_comp!r}, or relocate shared logic cleanly.",
                    )
                )
            elif src_tier in ("gateway", "sensor_node") and dst_tier in ("gateway", "sensor_node") and src_tier != dst_tier:
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-FW-002",
                        domain="firmware",
                        path=loc_path,
                        line=loc_line,
                        source=loc_src,
                        reason=(
                            f"Application component {src_comp!r} ({src_tier}) depends on other "
                            f"application component {dst_comp!r} ({dst_tier}) (CCARS REF-005)."
                        ),
                        fix=f"Extract genuinely shared interfaces to firmware/components/ instead of cross-coupling {src_tier} and {dst_tier}.",
                    )
                )

    for cyc in _find_cycles(dep_graph):
        a, b = cyc[0], cyc[1]
        loc_path, loc_line, loc_src = edge_meta.get((a, b), (_rel(root, comp_paths[a]), 1, " -> ".join(cyc)))
        violations.append(
            BoundaryViolation(
                rule_id="DEP-FW-003",
                domain="firmware",
                path=loc_path,
                line=loc_line,
                source=" -> ".join(cyc),
                reason=f"Cyclic firmware component dependency detected: {' -> '.join(cyc)} (ARCH-007/REF-005).",
                fix="Break the cycle by extracting shared types or moving the callback boundary to the caller component.",
            )
        )

    return violations


def _extract_go_imports(text: str) -> list[tuple[str, int]]:
    cleaned = _strip_go_comments_preserve_strings(text)
    imports: list[tuple[str, int]] = []
    for m in _GO_IMPORT_SINGLE_RE.finditer(cleaned):
        line_no = cleaned[: m.start()].count("\n") + 1
        imports.append((m.group(1), line_no))
    for blk in _GO_IMPORT_BLOCK_RE.finditer(cleaned):
        base_offset = blk.start(1)
        block_text = blk.group(1)
        for em in _GO_IMPORT_ENTRY_RE.finditer(block_text):
            line_no = cleaned[: base_offset + em.start()].count("\n") + 1
            imports.append((em.group(1), line_no))
    return imports


def check_go_boundaries(repo: pathlib.Path) -> list[BoundaryViolation]:
    root = repo.resolve()
    go_dir = root / "backend-go"
    if not go_dir.is_dir():
        return []

    violations: list[BoundaryViolation] = []
    gomod_path = go_dir / "go.mod"
    gomod_txt = _read_text_safe(root, gomod_path)
    if not gomod_txt:
        return []

    mod_match = _GO_MOD_RE.search(gomod_txt)
    module_path = mod_match.group(1) if mod_match else ""

    for req_match in _GO_MOD_REQ_RE.finditer(gomod_txt):
        dep = req_match.group(1)
        if any(tok in dep.lower() for tok in FORBIDDEN_BACKEND_TOKENS):
            line_no = gomod_txt[: req_match.start()].count("\n") + 1
            violations.append(
                BoundaryViolation(
                    rule_id="DEP-GO-006",
                    domain="backend-go",
                    path=_rel(root, gomod_path),
                    line=line_no,
                    source=dep,
                    reason=f"Forbidden external service/ORM/LoRaWAN dependency {dep!r} in go.mod violates ARCH-005/GO-ARCH-011.",
                    fix="Remove unapproved datastore/ORM/LoRaWAN dependency; use approved Go stdlib/PostgreSQL/MQTT modular monolith stack.",
                )
            )

    internal_prefix = f"{module_path}/internal/" if module_path else "/internal/"
    cmd_prefix = f"{module_path}/cmd/" if module_path else "/cmd/"

    pkg_graph: dict[str, set[str]] = {}
    edge_meta: dict[tuple[str, str], tuple[str, int, str]] = {}

    for go_file in sorted(go_dir.rglob("*.go")):
        if go_file.is_symlink() or not go_file.is_file():
            continue
        rel_path = _rel(root, go_file)
        if go_file.name.endswith("_test.go"):
            continue
        raw = _read_text_safe(root, go_file)
        if raw is None:
            continue

        rel_from_go = go_file.relative_to(go_dir).as_posix()
        is_cmd_main = rel_from_go == "cmd/server/main.go"
        is_internal = rel_from_go.startswith("internal/")
        src_pkg = ""
        if is_internal:
            src_pkg = pathlib.PurePosixPath(rel_from_go).parent.as_posix()[len("internal/") :]
            pkg_graph.setdefault(src_pkg, set())

        for imp, line_no in _extract_go_imports(raw):
            imp_low = imp.lower()
            if any(tok in imp_low for tok in FORBIDDEN_BACKEND_TOKENS):
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-GO-006",
                        domain="backend-go",
                        path=rel_path,
                        line=line_no,
                        source=imp,
                        reason=f"Forbidden stack import {imp!r} violates ARCH-005/GO-ARCH-011.",
                        fix="Remove forbidden import and retain approved PostgreSQL + Mosquitto MQTT 5.0 modular monolith architecture.",
                    )
                )

            if is_internal and (imp.startswith(cmd_prefix) or "/cmd/" in imp):
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-GO-001",
                        domain="backend-go",
                        path=rel_path,
                        line=line_no,
                        source=imp,
                        reason=f"Internal package {src_pkg!r} must not import executable entrypoint {imp!r} (GOCARS GO-ARCH-001).",
                        fix="Move shared interfaces or types into internal/ and keep cmd/server as composition-only entrypoint.",
                    )
                )

            if is_cmd_main:
                forbidden_direct = (
                    "internal/storage",
                    "internal/mqtt",
                    "internal/api",
                    "internal/realtime",
                    "database/sql",
                    "paho",
                )
                if any(tok in imp for tok in forbidden_direct):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-GO-002",
                            domain="backend-go",
                            path=rel_path,
                            line=line_no,
                            source=imp,
                            reason=f"Entrypoint cmd/server/main.go directly imports {imp!r}, bypassing internal/app composition root (GO-BE-002/GO-BE-003).",
                            fix="Assemble transport and persistence dependencies inside internal/app and invoke app.New(cfg) from main.go.",
                        )
                    )

            if internal_prefix and imp.startswith(internal_prefix):
                dst_pkg = imp[len(internal_prefix) :]
                if is_internal:
                    if dst_pkg != src_pkg:
                        pkg_graph[src_pkg].add(dst_pkg)
                        edge_meta.setdefault((src_pkg, dst_pkg), (rel_path, line_no, imp))

                    if src_pkg == "domain" and (
                        dst_pkg in ("api", "mqtt", "storage", "realtime", "app")
                    ):
                        violations.append(
                            BoundaryViolation(
                                rule_id="DEP-GO-003",
                                domain="backend-go",
                                path=rel_path,
                                line=line_no,
                                source=imp,
                                reason=f"Domain package internal/domain must not depend on transport/persistence/app package {dst_pkg!r} (GO-ARCH-003).",
                                fix="Keep internal/domain pure; invert dependency with domain-owned types/interfaces consumed by adapters.",
                            )
                        )
                    if src_pkg == "storage" and dst_pkg in ("api", "mqtt", "realtime", "app"):
                        violations.append(
                            BoundaryViolation(
                                rule_id="DEP-GO-004",
                                domain="backend-go",
                                path=rel_path,
                                line=line_no,
                                source=imp,
                                reason=f"Persistence package internal/storage must not depend on transport/bootstrap package {dst_pkg!r} (GO-ARCH-003).",
                                fix="Remove transport/bootstrap import from internal/storage; return domain structs or errors.",
                            )
                        )

            if is_internal and src_pkg in ("domain", "storage") and imp in ("net/http",):
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-GO-003" if src_pkg == "domain" else "DEP-GO-004",
                        domain="backend-go",
                        path=rel_path,
                        line=line_no,
                        source=imp,
                        reason=f"Package internal/{src_pkg} must not depend on HTTP transport {imp!r} (GO-ARCH-003).",
                        fix="Keep HTTP transport concerns in internal/api.",
                    )
                )

    for cyc in _find_cycles(pkg_graph):
        a, b = cyc[0], cyc[1]
        loc_path, loc_line, loc_src = edge_meta.get((a, b), ("backend-go/internal/" + a, 1, " -> ".join(cyc)))
        violations.append(
            BoundaryViolation(
                rule_id="DEP-GO-005",
                domain="backend-go",
                path=loc_path,
                line=loc_line,
                source=" -> ".join(cyc),
                reason=f"Go internal package import cycle detected: {' -> '.join(cyc)} (GO-ARCH-004).",
                fix="Extract shared contract/types to internal/domain or invert via a consumer-owned interface.",
            )
        )

    return violations


def _resolve_ts_module(src_file: pathlib.Path, src_root: pathlib.Path, spec: str) -> str | None:
    if spec.startswith("@/"):
        rel = spec[2:]
        base = src_root / rel
    elif spec.startswith("."):
        base = (src_file.parent / spec).resolve()
    else:
        return None
    candidates = [
        base,
        base.with_suffix(".ts"),
        base.with_suffix(".tsx"),
        base / "index.ts",
        base / "index.tsx",
    ]
    for cand in candidates:
        if cand.is_file() and cand.resolve().is_relative_to(src_root):
            return cand.resolve().relative_to(src_root).as_posix()
    if base.is_relative_to(src_root):
        return base.relative_to(src_root).as_posix()
    return None


def _client_layer(rel_in_src: str) -> str:
    if rel_in_src.startswith("types/"):
        return "types"
    if rel_in_src.startswith("lib/"):
        return "lib"
    if rel_in_src.startswith("components/"):
        return "components"
    if rel_in_src.startswith("app/"):
        return "app"
    return "other"


def check_client_boundaries(repo: pathlib.Path) -> list[BoundaryViolation]:
    root = repo.resolve()
    web_dir = root / "clients" / "web-dashboard"
    if not web_dir.is_dir():
        return []

    violations: list[BoundaryViolation] = []
    pkg_json = web_dir / "package.json"
    pkg_txt = _read_text_safe(root, pkg_json)
    if pkg_txt:
        try:
            pkg_data = json.loads(pkg_txt)
            for section in ("dependencies", "devDependencies"):
                deps = pkg_data.get(section, {})
                if isinstance(deps, dict):
                    for pkg_name in sorted(deps):
                        if pkg_name.lower() in FORBIDDEN_CLIENT_DB_PKGS:
                            violations.append(
                                BoundaryViolation(
                                    rule_id="DEP-CLI-001",
                                    domain="clients",
                                    path=_rel(root, pkg_json),
                                    line=1,
                                    source=pkg_name,
                                    reason=f"Client package.json declares direct DB/broker package {pkg_name!r}; clients must talk only to Backend REST/WSS (AGENTS.md §1).",
                                    fix=f"Remove {pkg_name!r} from clients/web-dashboard/package.json and use Backend REST/WSS endpoints.",
                                )
                            )
        except json.JSONDecodeError:
            violations.append(
                BoundaryViolation(
                    rule_id="DEP-CLI-001",
                    domain="clients",
                    path=_rel(root, pkg_json),
                    line=1,
                    source="package.json",
                    reason="Malformed client package.json prevents dependency verification.",
                    fix="Fix JSON syntax in clients/web-dashboard/package.json.",
                )
            )

    src_root = (web_dir / "src").resolve()
    if not src_root.is_dir():
        return violations

    ts_graph: dict[str, set[str]] = {}
    edge_meta: dict[tuple[str, str], tuple[str, int, str]] = {}

    for ts_file in sorted(src_root.rglob("*")):
        if ts_file.is_symlink() or not ts_file.is_file() or ts_file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        raw = _read_text_safe(root, ts_file)
        if raw is None:
            continue
        cleaned = _strip_c_comments(raw)
        rel_repo = _rel(root, ts_file)
        rel_src = ts_file.resolve().relative_to(src_root).as_posix()
        src_layer = _client_layer(rel_src)
        ts_graph.setdefault(rel_src, set())

        for match in _TS_IMPORT_RE.finditer(cleaned):
            spec = match.group(1).strip()
            line_no = cleaned[: match.start()].count("\n") + 1
            spec_low = spec.lower()
            pkg_root = spec.split("/")[0] if not spec.startswith("@") else "/".join(spec.split("/")[:2])
            if pkg_root.lower() in FORBIDDEN_CLIENT_DB_PKGS or any(
                seg in spec_low for seg in ("backend-go", "firmware/", "mosquitto", "postgresql")
            ):
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-CLI-001",
                        domain="clients",
                        path=rel_repo,
                        line=line_no,
                        source=spec,
                        reason=f"Client module imports direct DB/broker/server source {spec!r}; clients may only use authenticated REST/WSS (AGENTS.md §1, interfaces.md).",
                        fix="Replace direct DB/MQTT/backend import with src/lib/api or src/lib/realtime client calls.",
                    )
                )
                continue

            target_rel = _resolve_ts_module(ts_file, src_root, spec)
            if target_rel:
                if target_rel != rel_src:
                    ts_graph[rel_src].add(target_rel)
                    edge_meta.setdefault((rel_src, target_rel), (rel_repo, line_no, spec))
                dst_layer = _client_layer(target_rel)
                if src_layer == "types" and dst_layer in ("lib", "components", "app"):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-CLI-002",
                            domain="clients",
                            path=rel_repo,
                            line=line_no,
                            source=spec,
                            reason=f"Client types layer ({rel_src}) must not depend on {dst_layer} ({target_rel}).",
                            fix="Keep src/types/ dependency-free; move shared API adapters to src/lib/.",
                        )
                    )
                elif src_layer == "lib" and dst_layer in ("components", "app"):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-CLI-002",
                            domain="clients",
                            path=rel_repo,
                            line=line_no,
                            source=spec,
                            reason=f"Client library layer ({rel_src}) must not import UI {dst_layer} ({target_rel}).",
                            fix="Move UI components out of src/lib/ or pass callbacks from components/app.",
                        )
                    )

    for cyc in _find_cycles(ts_graph):
        a, b = cyc[0], cyc[1]
        loc_path, loc_line, loc_src = edge_meta.get((a, b), (f"clients/web-dashboard/src/{a}", 1, " -> ".join(cyc)))
        violations.append(
            BoundaryViolation(
                rule_id="DEP-CLI-003",
                domain="clients",
                path=loc_path,
                line=loc_line,
                source=" -> ".join(cyc),
                reason=f"Client module import cycle detected: {' -> '.join(cyc)}.",
                fix="Extract shared types to src/types/ or break the mutual import between modules.",
            )
        )

    return violations


def _resolve_json_pointer(doc: Any, pointer: str) -> bool:
    if pointer == "#":
        return True
    if not pointer.startswith("#/"):
        return False
    cur = doc
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False
    return True


def _iter_refs(obj: Any, path_prefix: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            found.append((path_prefix or "$", obj["$ref"]))
        for k, v in obj.items():
            found.extend(_iter_refs(v, f"{path_prefix}.{k}" if path_prefix else str(k)))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            found.extend(_iter_refs(item, f"{path_prefix}[{idx}]"))
    return found


def check_contract_boundaries(repo: pathlib.Path) -> list[BoundaryViolation]:
    root = repo.resolve()
    contracts_dir = root / "contracts"
    if not contracts_dir.is_dir():
        return []

    violations: list[BoundaryViolation] = []
    schema_files = sorted(contracts_dir.rglob("*.json")) + sorted(contracts_dir.rglob("*.yaml")) + sorted(contracts_dir.rglob("*.yml"))

    for cfile in schema_files:
        if cfile.is_symlink() or not cfile.is_file():
            continue
        rel_path = _rel(root, cfile)
        raw = _read_text_safe(root, cfile)
        if raw is None:
            continue
        try:
            if cfile.suffix == ".json":
                doc = json.loads(raw)
            elif yaml is not None:
                doc = yaml.safe_load(raw)
            else:
                continue
        except Exception as exc:
            violations.append(
                BoundaryViolation(
                    rule_id="DEP-CTR-001",
                    domain="contracts",
                    path=rel_path,
                    line=1,
                    source=cfile.name,
                    reason=f"Contract file failed structural parse: {exc}",
                    fix="Fix JSON/YAML syntax in contract file.",
                )
            )
            continue

        for ref_loc, ref in _iter_refs(doc):
            if "://" in ref or ref.startswith("/"):
                violations.append(
                    BoundaryViolation(
                        rule_id="DEP-CTR-002",
                        domain="contracts",
                        path=rel_path,
                        line=1,
                        source=ref,
                        reason=f"Contract $ref {ref!r} at {ref_loc} must not use external URLs or absolute paths.",
                        fix="Use local fragment pointers (#/...) or relative paths within contracts/.",
                    )
                )
                continue
            if ref.startswith("#"):
                if not _resolve_json_pointer(doc, ref):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-CTR-001",
                            domain="contracts",
                            path=rel_path,
                            line=1,
                            source=ref,
                            reason=f"Unresolved internal JSON pointer $ref {ref!r} at {ref_loc}.",
                            fix=f"Define target {ref!r} or fix broken pointer in {rel_path}.",
                        )
                    )
            else:
                file_part, _, frag = ref.partition("#")
                target = (cfile.parent / file_part).resolve()
                if not target.is_relative_to(contracts_dir.resolve()):
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-CTR-002",
                            domain="contracts",
                            path=rel_path,
                            line=1,
                            source=ref,
                            reason=f"Contract $ref {ref!r} escapes contracts/ boundary into implementation or parent tree.",
                            fix="Keep all contract $ref targets self-contained inside contracts/.",
                        )
                    )
                    continue
                if not target.is_file() or target.is_symlink():
                    violations.append(
                        BoundaryViolation(
                            rule_id="DEP-CTR-001",
                            domain="contracts",
                            path=rel_path,
                            line=1,
                            source=ref,
                            reason=f"Contract $ref {ref!r} points to missing or symlink target.",
                            fix="Create or fix relative schema reference inside contracts/.",
                        )
                    )
                    continue
                if frag:
                    target_raw = _read_text_safe(root, target)
                    if target_raw is not None and (target.suffix == ".json" or yaml is not None):
                        try:
                            target_doc = json.loads(target_raw) if target.suffix == ".json" else yaml.safe_load(target_raw)
                        except Exception as exc:
                            violations.append(
                                BoundaryViolation(
                                    rule_id="DEP-CTR-001",
                                    domain="contracts",
                                    path=rel_path,
                                    line=1,
                                    source=ref,
                                    reason=f"Contract $ref target {file_part} failed to parse ({type(exc).__name__}).",
                                    fix=f"Fix malformed JSON/YAML in {file_part}.",
                                )
                            )
                            continue
                        if not _resolve_json_pointer(target_doc, "#" + frag):
                            violations.append(
                                BoundaryViolation(
                                    rule_id="DEP-CTR-001",
                                    domain="contracts",
                                    path=rel_path,
                                    line=1,
                                    source=ref,
                                    reason=f"Contract $ref fragment #{frag} does not exist in {file_part}.",
                                    fix=f"Fix pointer #{frag} or add missing definition in {file_part}.",
                                )
                            )

    return violations


def evaluate_dependencies(
    repo: pathlib.Path,
    *,
    domains: tuple[str, ...] | list[str] = DOMAINS,
) -> dict[str, Any]:
    root = repo.resolve(strict=True)
    selected = tuple(dict.fromkeys(domains))
    unknown = set(selected) - set(DOMAINS)
    if unknown:
        raise ValueError(f"Unsupported dependency domain(s): {sorted(unknown)}")

    checkers = {
        "firmware": check_firmware_boundaries,
        "backend-go": check_go_boundaries,
        "clients": check_client_boundaries,
        "contracts": check_contract_boundaries,
    }
    violations: list[BoundaryViolation] = []
    for dom in selected:
        violations.extend(checkers[dom](root))

    return {
        "status": "FAIL" if violations else "PASS",
        "domains": list(selected),
        "violation_count": len(violations),
        "violations": [v.to_dict() for v in violations],
    }


def domains_for_paths(paths: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for path in paths:
        low = path.lower()
        if low.startswith("firmware/"):
            selected.append("firmware")
        if low.startswith("backend-go/"):
            selected.append("backend-go")
        if low.startswith("clients/"):
            selected.append("clients")
        if low.startswith("contracts/"):
            selected.append("contracts")
        if low.startswith(("scripts/agent_harness/", "tests/agent_harness/")):
            return DOMAINS
    return tuple(dict.fromkeys(selected))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Enforce approved structural dependency boundaries.")
    parser.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    parser.add_argument(
        "--domain",
        action="append",
        choices=("all", *DOMAINS),
        default=None,
        help="Domain(s) to check (default: all)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.repo.is_symlink() or not args.repo.is_dir():
            raise ValueError("Repository path must be a non-symlink directory")
        requested = args.domain or ["all"]
        domains = DOMAINS if "all" in requested else tuple(dict.fromkeys(requested))
        report = evaluate_dependencies(args.repo, domains=domains)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            if report["status"] == "PASS":
                print(f"PASS: dependency boundaries verified for {', '.join(report['domains'])}")
            else:
                for v in report["violations"]:
                    print(
                        f"FAIL [{v['rule_id']}] {v['path']}:{v['line']} ({v['source']}): "
                        f"{v['reason']} | Fix: {v['fix']}"
                    )
        return 0 if report["status"] == "PASS" else 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
