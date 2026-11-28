#!/usr/bin/env python3
"""Harness V2 P07 Advanced Pack integration, link/freshness checks, and DB schema generator.

Implements deterministic source-derived DB schema metadata generation and freshness checks
(without live/production DB access), Advanced Pack SPEC §5.2 completeness and link
validation, QUALITY_SCORE/debt surface checks, and plan-lifecycle / quality-debt helpers.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

REQUIRED_SPEC_SURFACES: tuple[tuple[str, str], ...] = (
    ("architecture", "ARCHITECTURE.md"),
    ("design_docs", "docs/design-docs/index.md"),
    ("product_specs", "docs/product-specs/index.md"),
    ("plans", "docs/PLANS.md"),
    ("tech_debt", "exec-plans/tech-debt-tracker.md"),
    ("db_schema", "docs/generated/db-schema.md"),
    ("references", "docs/references/"),
    ("quality_score", "docs/QUALITY_SCORE.md"),
    ("reliability", "docs/RELIABILITY.md"),
    ("security", "docs/SECURITY.md"),
    ("frontend", "docs/FRONTEND.md"),
    ("testing", "docs/TESTING.md"),
    ("orchestration", "Orchestration policy"),
    ("evaluator_rubric", "evaluator-rubric.md"),
    ("loop_state", "loop-state.md"),
    ("experiment_log", "Experiment log"),
)

VALID_QUALITY_GRADES = ("A", "B", "C", "D", "NOT_VERIFIED")
PLAN_STATES = ("DRAFT", "ACTIVE", "BLOCKED", "COMPLETED", "ARCHIVED")
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+)(?:#[^)\s]*)?\)")
PREFIX_RE = re.compile(r"^(\d+)_")


@dataclass(frozen=True)
class MigrationRecord:
    order: int
    filename: str
    numeric_prefix: str
    down_filename: str
    down_exists: bool
    sha256: str
    tables_created: tuple[str, ...]
    tables_altered: tuple[str, ...]
    tables_dropped: tuple[str, ...]
    indexes_created: tuple[str, ...]
    indexes_dropped: tuple[str, ...]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_symlink(path: pathlib.Path, label: str) -> None:
    if path.is_symlink():
        raise ValueError(f"{label} must not be a symlink: {path}")


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\r\n]*", "", sql)
    return sql


def _split_top_level_commas(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    in_single = False
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "'" and (i == 0 or body[i - 1] != "\\"):
            in_single = not in_single
            current.append(ch)
        elif not in_single:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth = max(0, depth - 1)
                current.append(ch)
            elif ch == "," and depth == 0:
                item = "".join(current).strip()
                if item:
                    parts.append(item)
                current = []
                i += 1
                continue
            else:
                current.append(ch)
        else:
            current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _extract_create_tables(sql: str) -> list[tuple[str, list[str]]]:
    cleaned = _strip_sql_comments(sql)
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s*\(",
        flags=re.IGNORECASE,
    )
    results: list[tuple[str, list[str]]] = []
    pos = 0
    while True:
        match = pattern.search(cleaned, pos)
        if not match:
            break
        table_name = match.group(1)
        start = match.end()
        depth = 1
        i = start
        in_single = False
        while i < len(cleaned) and depth > 0:
            ch = cleaned[i]
            if ch == "'" and (i == 0 or cleaned[i - 1] != "\\"):
                in_single = not in_single
            elif not in_single:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        body = cleaned[start : max(start, i - 1)]
        cols: list[str] = []
        for entry in _split_top_level_commas(body):
            first = entry.split(None, 1)[0].upper() if entry.split() else ""
            if first in ("CONSTRAINT", "PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "EXCLUDE"):
                continue
            tokens = entry.split()
            if len(tokens) >= 2:
                col_name = tokens[0].strip('"')
                col_type = tokens[1]
                # Keep type compact without overflowing table cell
                if "(" in col_type and ")" not in col_type:
                    # Reattach e.g. NUMERIC(5, 2)
                    rest = entry[len(tokens[0]) :].strip()
                    paren_end = rest.find(")")
                    if paren_end != -1:
                        col_type = rest[: paren_end + 1]
                cols.append(f"{col_name} ({col_type})")
        results.append((table_name, cols))
        pos = i
    return results


def _git_last_commit_for_migrations(repo_root: pathlib.Path) -> str:
    try:
        proc = subprocess.run(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(repo_root),
                "log",
                "-n",
                "1",
                "--format=%H",
                "--",
                "backend-go/migrations",
                "backend-go/Dockerfile",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return "UNCOMMITTED_OR_NO_HISTORY"


def inspect_migrations(repo: pathlib.Path) -> dict[str, Any]:
    """Deterministically inspect migration SQL sources and runner semantics without DB access."""
    _reject_symlink(repo, "repo")
    repo_root = repo.resolve(strict=True)
    mig_dir = repo_root / "backend-go" / "migrations"
    _reject_symlink(mig_dir, "migrations dir")
    if not mig_dir.is_dir():
        raise ValueError(f"Missing migrations directory: {mig_dir}")

    up_files = sorted(
        p for p in mig_dir.iterdir() if p.is_file() and not p.is_symlink() and p.name.endswith(".up.sql")
    )
    if not up_files:
        raise ValueError("No *.up.sql migration files found")

    all_tracked_inputs: list[pathlib.Path] = sorted(
        p for p in mig_dir.iterdir() if p.is_file() and not p.is_symlink() and p.suffix == ".sql"
    )
    dockerfile = repo_root / "backend-go" / "Dockerfile"
    if dockerfile.is_file() and not dockerfile.is_symlink():
        all_tracked_inputs.append(dockerfile)

    tree_parts: list[str] = []
    for path in sorted(all_tracked_inputs, key=lambda p: p.relative_to(repo_root).as_posix()):
        rel = path.relative_to(repo_root).as_posix()
        digest = _sha256_bytes(path.read_bytes())
        tree_parts.append(f"{rel}:{digest}\n")
    migrations_tree_sha256 = _sha256_bytes("".join(tree_parts).encode("utf-8"))

    runner_info: dict[str, Any] = {
        "runner_file": "backend-go/Dockerfile (/app/migrate.sh)",
        "present": dockerfile.is_file(),
        "uses_advisory_lock": False,
        "tracks_full_filename": False,
        "sorts_lexicographically": False,
        "on_error_stop": False,
    }
    if dockerfile.is_file():
        df_text = dockerfile.read_text(encoding="utf-8")
        runner_info["uses_advisory_lock"] = "pg_advisory_lock" in df_text
        runner_info["tracks_full_filename"] = "WHERE version = '${base}'" in df_text and "VALUES ('${base}')" in df_text
        runner_info["sorts_lexicographically"] = "-name '*.up.sql' | sort" in df_text
        runner_info["on_error_stop"] = "ON_ERROR_STOP=1" in df_text

    records: list[MigrationRecord] = []
    prefix_map: dict[str, list[str]] = {}
    active_tables: dict[str, dict[str, Any]] = {}
    dropped_tables: dict[str, str] = {}
    active_indexes: dict[str, dict[str, str]] = {}

    for idx, up_path in enumerate(up_files, start=1):
        fname = up_path.name
        m_pref = PREFIX_RE.match(fname)
        num_prefix = m_pref.group(1) if m_pref else "NONE"
        prefix_map.setdefault(num_prefix, []).append(fname)

        down_name = fname[: -len(".up.sql")] + ".down.sql"
        down_exists = (mig_dir / down_name).is_file() and not (mig_dir / down_name).is_symlink()

        raw = up_path.read_bytes()
        sha = _sha256_bytes(raw)
        sql_text = raw.decode("utf-8")
        cleaned = _strip_sql_comments(sql_text)

        created_names: list[str] = []
        for tname, cols in _extract_create_tables(sql_text):
            created_names.append(tname)
            dropped_tables.pop(tname, None)
            active_tables[tname] = {
                "table": tname,
                "created_in": fname,
                "columns": list(cols),
                "altered_in": [],
            }

        altered_names: list[str] = []
        for alter_m in re.finditer(
            r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_.]*)\s+([^;]+);",
            cleaned,
            flags=re.IGNORECASE,
        ):
            tname = alter_m.group(1)
            stmt = alter_m.group(2)
            altered_names.append(tname)
            tbl = active_tables.get(tname)
            if tbl is not None:
                if fname not in tbl["altered_in"]:
                    tbl["altered_in"].append(fname)
                for add_m in re.finditer(
                    r"ADD\s+(?:COLUMN\s+)?(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+([A-Za-z0-9_]+(?:\([^)]*\))?)",
                    stmt,
                    flags=re.IGNORECASE,
                ):
                    col_sig = f"{add_m.group(1)} ({add_m.group(2)})"
                    if not any(c.startswith(add_m.group(1) + " ") for c in tbl["columns"]):
                        tbl["columns"].append(col_sig)
                for drop_m in re.finditer(
                    r"DROP\s+COLUMN\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
                    stmt,
                    flags=re.IGNORECASE,
                ):
                    col_name = drop_m.group(1)
                    tbl["columns"] = [c for c in tbl["columns"] if not c.startswith(col_name + " ")]

        dropped_names: list[str] = []
        for drop_t in re.finditer(
            r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_.]*)",
            cleaned,
            flags=re.IGNORECASE,
        ):
            tname = drop_t.group(1)
            dropped_names.append(tname)
            active_tables.pop(tname, None)
            dropped_tables[tname] = fname

        idx_created: list[str] = []
        for idx_m in re.finditer(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+([A-Za-z_][A-Za-z0-9_.]*)",
            cleaned,
            flags=re.IGNORECASE,
        ):
            iname, tname = idx_m.group(1), idx_m.group(2)
            idx_created.append(iname)
            active_indexes[iname] = {"index": iname, "table": tname, "created_in": fname}

        idx_dropped: list[str] = []
        for drop_i in re.finditer(
            r"DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)",
            cleaned,
            flags=re.IGNORECASE,
        ):
            iname = drop_i.group(1)
            idx_dropped.append(iname)
            active_indexes.pop(iname, None)

        records.append(
            MigrationRecord(
                order=idx,
                filename=fname,
                numeric_prefix=num_prefix,
                down_filename=down_name,
                down_exists=down_exists,
                sha256=sha,
                tables_created=tuple(created_names),
                tables_altered=tuple(sorted(set(altered_names))),
                tables_dropped=tuple(dropped_names),
                indexes_created=tuple(idx_created),
                indexes_dropped=tuple(idx_dropped),
            )
        )

    # Remove indexes belonging to dropped tables
    for iname in list(active_indexes):
        if active_indexes[iname]["table"] in dropped_tables:
            active_indexes.pop(iname, None)

    duplicate_prefixes = {k: v for k, v in sorted(prefix_map.items()) if len(v) > 1}
    ops_guide = repo_root / "docs" / "development" / "POSTGRESQL_OPERATIONS_GUIDE.md"
    ops_mentions_golang_migrate = False
    if ops_guide.is_file() and not ops_guide.is_symlink():
        ops_mentions_golang_migrate = "golang-migrate" in ops_guide.read_text(encoding="utf-8")

    return {
        "migrations_source_commit": _git_last_commit_for_migrations(repo_root),
        "migrations_tree_sha256": migrations_tree_sha256,
        "migration_count": len(records),
        "migrations": [
            {
                "order": r.order,
                "filename": r.filename,
                "numeric_prefix": r.numeric_prefix,
                "down_filename": r.down_filename,
                "down_exists": r.down_exists,
                "sha256": r.sha256,
                "tables_created": list(r.tables_created),
                "tables_altered": list(r.tables_altered),
                "tables_dropped": list(r.tables_dropped),
                "indexes_created": list(r.indexes_created),
                "indexes_dropped": list(r.indexes_dropped),
            }
            for r in records
        ],
        "duplicate_numeric_prefixes": duplicate_prefixes,
        "runner": runner_info,
        "ops_guide_mentions_golang_migrate": ops_mentions_golang_migrate,
        "active_tables": [active_tables[k] for k in sorted(active_tables)],
        "dropped_tables": [{"table": k, "dropped_in": dropped_tables[k]} for k in sorted(dropped_tables)],
        "active_indexes": [active_indexes[k] for k in sorted(active_indexes)],
    }


def render_db_schema(repo: pathlib.Path) -> str:
    """Render deterministic Markdown DB schema metadata from SQL migration sources."""
    info = inspect_migrations(repo)
    lines: list[str] = [
        "# Generated Database Schema Metadata",
        "",
        "> **DO NOT HAND-EDIT.** This file is deterministically generated from migration SQL sources.",
        "> Re-run the generation command below whenever `backend-go/migrations/` or `backend-go/Dockerfile` changes.",
        "",
        "## Provenance & Freshness",
        "",
        f"- **Generated from:** `backend-go/migrations/*.up.sql` + `backend-go/Dockerfile` (`/app/migrate.sh`)",
        f"- **Migrations source commit:** `{info['migrations_source_commit']}`",
        f"- **Migrations tree SHA-256:** `{info['migrations_tree_sha256']}`",
        "- **Generation command:** `python3 scripts/agent_harness/advanced_pack.py generate-db-schema --repo . --output docs/generated/db-schema.md`",
        "- **Freshness check command:** `python3 scripts/agent_harness/advanced_pack.py check-db-schema --repo . --schema docs/generated/db-schema.md`",
        "- **Verification status:** `SOURCE_DERIVED_ONLY` (`LIVE_DB_INTROSPECTION: NOT_RUN`, `MIGRATION_EXECUTION: NOT_VERIFIED`)",
        "",
        "## Migration Runner Semantics & Duplicate Numeric Prefixes",
        "",
        f"- **Actual runtime runner:** `{info['runner']['runner_file']}` (`present={info['runner']['present']}`, "
        f"`pg_advisory_lock={info['runner']['uses_advisory_lock']}`, "
        f"`lexicographic_sort={info['runner']['sorts_lexicographically']}`, "
        f"`full_filename_version_key={info['runner']['tracks_full_filename']}`, "
        f"`on_error_stop={info['runner']['on_error_stop']}`).",
        "- **Runner tracking table:** `schema_migrations (version VARCHAR(128) PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT NOW())` created under session advisory lock before applying pending `*.up.sql` files inside individual transactions.",
    ]

    dups = info["duplicate_numeric_prefixes"]
    if dups:
        dup_desc = "; ".join(f"`{pref}` -> {', '.join(f'`{n}`' for n in names)}" for pref, names in dups.items())
        lines.append(
            f"- **Duplicate numeric prefix warning:** {dup_desc}. "
            "Because `/app/migrate.sh` keys `schema_migrations.version` by full filename (`${base}`) and orders lexicographically (`sort`), "
            "multiple `000004_*` files execute deterministically in alphabetical order (`000004_create_gateway_status` -> "
            "`000004_create_users_table` -> `000004_schedule_storage`)."
        )
    if info["ops_guide_mentions_golang_migrate"]:
        lines.append(
            "- **Documentation drift note:** `docs/development/POSTGRESQL_OPERATIONS_GUIDE.md` references `golang-migrate`, "
            "which rejects duplicate numeric prefixes (`000004_*`). The actual containerized runner in `backend-go/Dockerfile` "
            "is `/app/migrate.sh` (custom `psql` runner), **not** `golang-migrate`."
        )

    lines.extend(
        [
            "",
            "## Migration Inventory (Ordered Execution Sequence)",
            "",
            "| # | Up Migration | Prefix | Down SQL | SHA-256 | DDL Summary |",
            "|---|---|---|---|---|---|",
        ]
    )

    for m in info["migrations"]:
        summary_parts: list[str] = []
        if m["tables_created"]:
            summary_parts.append("CREATE " + ", ".join(m["tables_created"]))
        if m["tables_altered"]:
            summary_parts.append("ALTER " + ", ".join(m["tables_altered"]))
        if m["tables_dropped"]:
            summary_parts.append("DROP " + ", ".join(m["tables_dropped"]))
        summary = "; ".join(summary_parts) if summary_parts else "DDL/DML update"
        down_flag = "YES" if m["down_exists"] else "NO"
        lines.append(
            f"| {m['order']} | `{m['filename']}` | `{m['numeric_prefix']}` | {down_flag} | `{m['sha256'][:12]}...` | {summary} |"
        )

    lines.extend(
        [
            "",
            f"## Active Source-Derived Tables ({len(info['active_tables'])} application tables + 1 runner table)",
            "",
            "| Table | Source Migration | Source-Derived Columns |",
            "|---|---|---|",
            "| `schema_migrations` | `backend-go/Dockerfile` (`/app/migrate.sh`) | `version (VARCHAR(128))`, `applied_at (TIMESTAMPTZ)` |",
        ]
    )
    for tbl in info["active_tables"]:
        cols_str = ", ".join(f"`{c}`" for c in tbl["columns"]) if tbl["columns"] else "(none parsed)"
        origin = tbl["created_in"]
        if tbl["altered_in"]:
            origin += " + " + ", ".join(tbl["altered_in"])
        lines.append(f"| `{tbl['table']}` | `{origin}` | {cols_str} |")

    if info["dropped_tables"]:
        lines.extend(
            [
                "",
                "## Dropped Historical Tables (Superseded TDMA Cleanup)",
                "",
                "| Table | Dropped In |",
                "|---|---|",
            ]
        )
        for dtbl in info["dropped_tables"]:
            lines.append(f"| `{dtbl['table']}` | `{dtbl['dropped_in']}` |")

    lines.extend(
        [
            "",
            "## Explicit Limitations",
            "",
            "- **Static source derivation only:** Derived offline from `backend-go/migrations/*.up.sql` and `backend-go/Dockerfile`; no live or production PostgreSQL database was accessed (`LIVE_DB_INTROSPECTION: NOT_RUN`).",
            "- **Does not prove migration runtime success:** Applying migrations against PostgreSQL 16 (including constraints, seeds, and rollback `.down.sql` parity) requires an authorized integration test run (`MIGRATION_EXECUTION: NOT_VERIFIED` by this generator).",
            "- **Column summary scope:** Parses top-level `CREATE TABLE` / `ALTER TABLE` / `DROP TABLE` DDL; constraints, triggers, and seed rows live in the authoritative `.up.sql` files.",
            "",
        ]
    )

    body = "\n".join(lines)
    body_sha256 = _sha256_bytes(body.encode("utf-8"))
    return f"{body}<!-- GENERATED_BODY_SHA256: {body_sha256} -->\n"


def generate_db_schema(repo: pathlib.Path, output_path: pathlib.Path) -> dict[str, Any]:
    """Write deterministic generated DB schema Markdown to output_path."""
    _reject_symlink(repo, "repo")
    _reject_symlink(output_path, "output schema path")
    repo_root = repo.resolve(strict=True)
    resolved_out = output_path.resolve()
    if not resolved_out.is_relative_to(repo_root):
        raise ValueError("Generated schema path must reside inside target repository")
    content = render_db_schema(repo_root)
    resolved_out.parent.mkdir(parents=True, exist_ok=True)
    resolved_out.write_text(content, encoding="utf-8")
    info = inspect_migrations(repo_root)
    return {
        "status": "GENERATED",
        "output": resolved_out.relative_to(repo_root).as_posix(),
        "migrations_tree_sha256": info["migrations_tree_sha256"],
        "migration_count": info["migration_count"],
        "active_table_count": len(info["active_tables"]),
    }


def check_db_schema_freshness(repo: pathlib.Path, schema_path: pathlib.Path) -> dict[str, Any]:
    """Verify generated DB schema matches current migration sources without hand-edits."""
    _reject_symlink(repo, "repo")
    _reject_symlink(schema_path, "schema_path")
    repo_root = repo.resolve(strict=True)
    if not schema_path.is_file():
        return {
            "status": "FAIL",
            "reason": f"Missing generated DB schema file: {schema_path}",
        }
    resolved_schema = schema_path.resolve(strict=True)
    if not resolved_schema.is_relative_to(repo_root):
        return {
            "status": "FAIL",
            "reason": "Generated DB schema path escapes repository root",
        }

    actual = resolved_schema.read_text(encoding="utf-8")
    expected = render_db_schema(repo_root)
    info = inspect_migrations(repo_root)

    tree_match = re.search(r"Migrations tree SHA-256:\*\*\s*`([0-9a-f]{64})`", actual)
    recorded_tree_sha = tree_match.group(1) if tree_match else None
    footer_match = re.search(r"<!-- GENERATED_BODY_SHA256:\s*([0-9a-f]{64})\s*-->\s*$", actual)
    if not footer_match:
        return {
            "status": "FAIL",
            "reason": "Missing GENERATED_BODY_SHA256 integrity footer in docs/generated/db-schema.md",
            "expected_migrations_tree_sha256": info["migrations_tree_sha256"],
            "recorded_migrations_tree_sha256": recorded_tree_sha,
        }

    body_without_footer = actual[: footer_match.start()]
    actual_body_sha = _sha256_bytes(body_without_footer.encode("utf-8"))
    if actual_body_sha != footer_match.group(1):
        return {
            "status": "FAIL",
            "reason": "Generated DB schema appears hand-edited (footer SHA-256 mismatch); regenerate via advanced_pack.py",
            "expected_migrations_tree_sha256": info["migrations_tree_sha256"],
            "recorded_migrations_tree_sha256": recorded_tree_sha,
        }

    if recorded_tree_sha != info["migrations_tree_sha256"] or actual != expected:
        return {
            "status": "FAIL",
            "reason": "Generated DB schema is stale relative to backend-go/migrations/ or backend-go/Dockerfile; regenerate",
            "expected_migrations_tree_sha256": info["migrations_tree_sha256"],
            "recorded_migrations_tree_sha256": recorded_tree_sha,
        }

    return {
        "status": "PASS",
        "migrations_tree_sha256": info["migrations_tree_sha256"],
        "migration_count": info["migration_count"],
        "active_table_count": len(info["active_tables"]),
        "duplicate_numeric_prefixes": info["duplicate_numeric_prefixes"],
    }


def validate_markdown_links(repo_root: pathlib.Path, doc_path: pathlib.Path) -> list[str]:
    """Return list of broken local relative links inside doc_path."""
    _reject_symlink(doc_path, "markdown doc")
    if not doc_path.is_file():
        return [f"Missing document: {doc_path.relative_to(repo_root).as_posix()}"]
    text = doc_path.read_text(encoding="utf-8")
    broken: list[str] = []
    rel_doc = doc_path.relative_to(repo_root).as_posix()
    for target in LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        resolved = (doc_path.parent / target).resolve()
        if not resolved.is_relative_to(repo_root) or not resolved.exists():
            broken.append(f"{rel_doc}: broken link `{target}`")
    return broken


def verify_advanced_pack(repo: pathlib.Path) -> dict[str, Any]:
    """Run all P07 Advanced Pack surface, link, quality-score, and DB freshness checks."""
    _reject_symlink(repo, "repo")
    repo_root = repo.resolve(strict=True)
    failures: list[str] = []

    adv_path = repo_root / "docs" / "harness" / "ADVANCED_PACK.md"
    qs_path = repo_root / "docs" / "QUALITY_SCORE.md"
    db_path = repo_root / "docs" / "generated" / "db-schema.md"

    for p in (adv_path, qs_path, db_path):
        _reject_symlink(p, p.name)
        if not p.is_file():
            failures.append(f"Missing required P07 surface: {p.relative_to(repo_root).as_posix()}")

    mapped_surfaces: dict[str, bool] = {}
    if adv_path.is_file():
        adv_text = adv_path.read_text(encoding="utf-8")
        for key, marker in REQUIRED_SPEC_SURFACES:
            ok = marker in adv_text
            mapped_surfaces[key] = ok
            if not ok:
                failures.append(f"ADVANCED_PACK.md missing SPEC §5.2 surface mapping: {marker}")
        for required_marker in ("P08", "P09", "SUPERSEDED", "NOT_VERIFIED", "ADR-0004"):
            if required_marker not in adv_text:
                failures.append(f"ADVANCED_PACK.md missing required authority/status marker: {required_marker}")
        failures.extend(validate_markdown_links(repo_root, adv_path))

    if qs_path.is_file():
        qs_text = qs_path.read_text(encoding="utf-8")
        for required_section in (
            "Product Domains",
            "Architectural Layers",
            "Benchmark",
            "Simplification",
            "Technical Debt",
            "NOT_VERIFIED",
            "#424",
            "GitHub Issues",
        ):
            if required_section not in qs_text:
                failures.append(f"QUALITY_SCORE.md missing required section/reference: {required_section}")
        if "hard gate" not in qs_text.lower():
            failures.append("QUALITY_SCORE.md must explicitly state that no score overrides a hard gate")
        failures.extend(validate_markdown_links(repo_root, qs_path))

    db_check = check_db_schema_freshness(repo_root, db_path)
    if db_check["status"] != "PASS":
        failures.append(f"DB schema freshness failed: {db_check['reason']}")

    return {
        "status": "PASS" if not failures else "FAIL",
        "exit_code": 0 if not failures else 1,
        "mapped_surfaces": mapped_surfaces,
        "db_schema_check": db_check,
        "failure_count": len(failures),
        "failures": failures,
    }


def transition_plan_lifecycle(
    plan: dict[str, Any],
    *,
    target_state: str,
    evidence_ref: str = "",
    approved_by: str = "",
) -> dict[str, Any]:
    """Execute one validated plan lifecycle transition (for P07 lifecycle verification)."""
    if target_state not in PLAN_STATES:
        raise ValueError(f"Invalid plan state: {target_state!r}")
    current = plan.get("state", "DRAFT")
    allowed = {
        "DRAFT": ("ACTIVE", "BLOCKED"),
        "ACTIVE": ("BLOCKED", "COMPLETED"),
        "BLOCKED": ("ACTIVE",),
        "COMPLETED": ("ARCHIVED",),
        "ARCHIVED": (),
    }
    if target_state not in allowed.get(current, ()):
        raise ValueError(f"Illegal plan transition {current} -> {target_state}")
    if target_state in ("COMPLETED", "ARCHIVED") and not evidence_ref.strip():
        raise ValueError(f"Transition to {target_state} requires non-empty evidence_ref")
    if target_state == "ARCHIVED" and not approved_by.strip():
        raise ValueError("Transition to ARCHIVED requires explicit human/owner approval")

    updated = json.loads(json.dumps(plan))
    updated["state"] = target_state
    history = list(updated.get("history", []))
    history.append(
        {
            "from": current,
            "to": target_state,
            "evidence_ref": evidence_ref,
            "approved_by": approved_by,
        }
    )
    updated["history"] = history
    return updated


def record_quality_debt_update(
    snapshot: dict[str, Any],
    *,
    domain: str,
    new_grade: str,
    evidence_ref: str,
    revision: str,
    debt_issue: int | None = None,
    debt_status: str | None = None,
    hard_gate_passed: bool = True,
) -> dict[str, Any]:
    """Update a domain quality grade and optional linked GitHub debt status with hard-gate guard."""
    if new_grade not in VALID_QUALITY_GRADES:
        raise ValueError(f"Invalid quality grade: {new_grade!r}")
    if new_grade == "A" and not hard_gate_passed:
        raise ValueError("Hard-gate failure blocks grade A promotion")
    if not evidence_ref.strip() or not revision.strip():
        raise ValueError("Quality update requires both evidence_ref and revision")

    updated = json.loads(json.dumps(snapshot))
    domains = updated.setdefault("domains", {})
    prev_grade = domains.get(domain, {}).get("grade", "NOT_VERIFIED")
    domains[domain] = {
        "grade": new_grade,
        "evidence_ref": evidence_ref,
        "revision": revision,
        "hard_gate_passed": hard_gate_passed,
    }
    if debt_issue is not None:
        debt_map = updated.setdefault("debt", {})
        entry = debt_map.get(str(debt_issue), {"issue": debt_issue})
        if debt_status:
            entry["status"] = debt_status
        entry["last_reviewed_revision"] = revision
        debt_map[str(debt_issue)] = entry

    updated.setdefault("changelog", []).append(
        {
            "domain": domain,
            "from_grade": prev_grade,
            "to_grade": new_grade,
            "revision": revision,
            "evidence_ref": evidence_ref,
            "debt_issue": debt_issue,
        }
    )
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Harness V2 P07 Advanced Pack & DB Schema Utility")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate-db-schema", help="Generate docs/generated/db-schema.md from SQL migrations")
    p_gen.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_gen.add_argument("--output", type=pathlib.Path, default=pathlib.Path("docs/generated/db-schema.md"))
    p_gen.add_argument("--json", action="store_true")

    p_chk = sub.add_parser("check-db-schema", help="Verify docs/generated/db-schema.md freshness")
    p_chk.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_chk.add_argument("--schema", type=pathlib.Path, default=pathlib.Path("docs/generated/db-schema.md"))
    p_chk.add_argument("--json", action="store_true")

    p_ver = sub.add_parser("verify", help="Verify Advanced Pack mapping, links, QUALITY_SCORE, and DB schema freshness")
    p_ver.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    p_ver.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    try:
        repo = args.repo.resolve(strict=True)
        if args.cmd == "generate-db-schema":
            out_path = args.output if args.output.is_absolute() else (repo / args.output)
            res = generate_db_schema(repo, out_path)
            print(json.dumps(res, indent=2, sort_keys=True) if args.json else f"{res['status']}: {res['output']}")
            return 0
        if args.cmd == "check-db-schema":
            schema_path = args.schema if args.schema.is_absolute() else (repo / args.schema)
            res = check_db_schema_freshness(repo, schema_path)
            print(json.dumps(res, indent=2, sort_keys=True) if args.json else f"{res['status']}")
            return 0 if res["status"] == "PASS" else 1
        if args.cmd == "verify":
            res = verify_advanced_pack(repo)
            print(json.dumps(res, indent=2, sort_keys=True) if args.json else f"{res['status']}: {res['failure_count']} failures")
            return int(res["exit_code"])
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "BLOCKED", "exit_code": 2, "error": str(exc)}, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
