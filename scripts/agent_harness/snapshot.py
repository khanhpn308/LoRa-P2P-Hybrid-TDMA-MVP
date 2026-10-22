"""Bounded independent file snapshot for read-only source review."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

REFERENCES = (
    "AGENTS.md",
    ".github/copilot-instructions.md",
    ".github/instructions/embedded.instructions.md",
    "docs/adr/0001-hybrid-tdma.md",
    "docs/architecture/system-overview.md",
    "docs/verification/acceptance-gates.md",
    "contracts/radio-mac/specification.md",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assemble(repo: Path, dest: Path, changed: list[str], diff: str, receipts: list[dict]) -> dict:
    if not changed or len(changed) > 80 or len(diff.encode()) > 90000:
        raise ValueError("Audit inventory/diff exceeds limits")
    if "GIT binary patch" in diff or "Binary files " in diff:
        raise ValueError("Binary changes need human review")
    hashes = {}
    for name in sorted(set(changed).union(REFERENCES)):
        src = repo / name
        if not src.exists():
            if name in REFERENCES:
                raise ValueError("Missing reference " + name)
            continue
        if not src.is_file() or src.is_symlink():
            raise ValueError("Nonregular/symlink audit source " + name)
        b = src.read_bytes()
        if len(b) > 120000 or b"\0" in b:
            raise ValueError("Nontext/oversize audit source " + name)
        target = dest / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b)
        target.chmod(0o444)
        hashes[name] = digest(b)
    (dest / "changes.patch").write_text(diff, encoding="utf-8")
    (dest / "checks.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
    for name in ("changes.patch", "checks.json"):
        (dest / name).chmod(0o444)
        hashes[name] = digest((dest / name).read_bytes())
    return hashes


def unchanged(dest: Path, before: dict) -> bool:
    expected = {"audit.schema.json", "changes.patch", "checks.json"}
    expected.update("source/" + key for key in before
                    if key not in ("changes.patch", "checks.json", "audit.schema.json"))
    actual = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    if actual != expected:
        return False
    for path, before_hash in before.items():
        target = dest / path if path in ("changes.patch", "checks.json", "audit.schema.json") else dest / "source" / path
        if not target.is_file() or target.is_symlink() or digest(target.read_bytes()) != before_hash:
            return False
    return True
