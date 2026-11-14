"""Codex CLI Worker adapter. Workspace sandbox does not replace a disposable VM."""
from __future__ import annotations

import subprocess
import json
import tempfile
from pathlib import Path

from . import antigravity


class WorkerError(RuntimeError):
    pass


def invoke(prompt: str, worktree: Path, timeout: int, required_rules=None,
           selection_sha256=None, evidence_inventory=None, read_only: bool = False) -> dict:
    if required_rules is None and (selection_sha256 is not None or evidence_inventory is not None):
        raise WorkerError("Partial Host scope cannot use the legacy Worker")
    sandbox = "read-only" if read_only else "workspace-write"
    args = ["codex", "--ask-for-approval", "never", "exec", "--sandbox", sandbox]
    try:
        with tempfile.TemporaryDirectory(prefix="harness-worker-report-") as directory:
            root = Path(directory)
            if required_rules is not None:
                schema = root / "report.schema.json"
                schema.write_text(json.dumps(antigravity.scoped_schema(required_rules, selection_sha256)))
                args.extend(["--output-schema", str(schema), "--output-last-message", str(root / "report.json")])
            args.append("-")
            result = antigravity.run_bounded(args, cwd=worktree, input=prompt, timeout=timeout)
            if result.returncode:
                raise WorkerError(f"codex exited {result.returncode}")
            if antigravity.DENIAL.search(result.stderr):
                raise WorkerError("Worker reported a permission denial")
            summary = {"exit_code": result.returncode, "stdout_bytes": len(result.stdout.encode()),
                       "stderr_bytes": len(result.stderr.encode())}
            if required_rules is not None:
                try:
                    from ..quality_gates import safe_read
                except ImportError:
                    from quality_gates import safe_read
                raw = safe_read(root, "report.json")
                antigravity._safe_report_bytes(raw, structured=True)
                report = json.loads(raw, object_pairs_hook=antigravity._reject_duplicate_object_keys,
                                    parse_constant=antigravity._reject_invalid_constant)
                if not isinstance(report, dict) or not isinstance(report.get("reviewed_scope"), list):
                    raise WorkerError("Worker report schema rejected")
                summary["report"] = antigravity.check_report(
                    report, set(report["reviewed_scope"]), required_rules,
                    selection_sha256, evidence_inventory)
            return summary
    except (OSError, subprocess.TimeoutExpired, antigravity.AuditError, ValueError,
            TypeError, KeyError, RecursionError, UnicodeError) as exc:
        # Never include provider stdout/stderr, model prose or source bytes.
        raise WorkerError(f"Worker invocation or report rejected: {type(exc).__name__}") from exc
