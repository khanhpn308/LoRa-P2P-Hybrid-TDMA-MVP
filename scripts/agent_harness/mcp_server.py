"""Shared Codex/AGY MCP stdio Host bridge.

A MCP server exposes trusted Host capabilities. It does NOT start native
Gemini/Codex model sessions or attest Auditor provenance. Require explicit
reviewed Host authorization before execution. Mutations currently fail closed.
"""
from __future__ import annotations

from mcp.server import MCPServer
from mcp_host import HarnessMCPHost
from mcp_execution import MCPExecution

host = HarnessMCPHost()
execution = MCPExecution(host)
mcp = MCPServer("lora-harness")


@mcp.tool()
def harness_preflight(issue_number: int) -> dict:
    """Read an OPEN, strictly scoped GitHub Issue; return dry-run plan and pins.

    No worktree is created. Operator must approve base_sha and issue_sha256.
    """
    return host.preflight(issue_number)


@mcp.tool()
def harness_status(run_id: str) -> dict:
    """Read persisted legacy P1 Host SQLite state (not a model self-report)."""
    return host.status(run_id)


@mcp.tool()
def harness_verify_candidate(run_id: str) -> dict:
    """Validate actual changed-file allowlist and SHA. Not build/audit PASS."""
    return host.verify_candidate(run_id)


@mcp.tool()
def harness_prepare_issue(issue_number: int, approved_base_sha: str,
                          approved_issue_sha256: str) -> dict:
    """HOST MUTATION: create a dedicated pinned Git worktree and external journal.

    BLOCKED in this draft. This transport has no trustworthy Host approval
    channel or atomic Issue-pin apply. Environment flags and client/model
    claims cannot authorize execution. No commits, pushes, PRs or main edits.
    """
    return execution.prepare(issue_number, approved_base_sha, approved_issue_sha256)


@mcp.tool()
def harness_worker_handoff(run_id: str) -> dict:
    """Create controlled handoff for a FRESH native Worker in Codex/AGY.

    MCP does NOT spawn the AI. Coordinator must actually invoke a native
    scoped Worker and obtain real tool records; no nested consumer agy -p.
    """
    return execution.worker_handoff(run_id)


@mcp.tool()
def harness_verify_worker(run_id: str) -> dict:
    """Use trusted Host gate to verify the post-Worker changed paths and hashes."""
    return execution.verify_worker(run_id)


@mcp.tool()
def harness_run_checks(run_id: str) -> dict:
    """HOST EXECUTION: bounded structure/Harness tests, two offline ESP-IDF builds.

    BLOCKED pending reviewed Host authorization, isolated candidate tests,
    and daemon-owned container lifecycle supervision. No Docker is started.
    Not HIL, RF, timing or tests for unrelated backend/client components.
    """
    return execution.run_checks(run_id)


@mcp.tool()
def harness_auditor_handoff(run_id: str) -> dict:
    """Freeze changed candidate files/schema into external read-only snapshot.

    Coordinator MUST invoke a fresh native read-only Auditor separately.
    This tool does NOT invoke models or prove independence.
    """
    return execution.auditor_handoff(run_id)


@mcp.tool()
def harness_submit_audit(run_id: str, audit_report: dict) -> dict:
    """Validate submitted Auditor JSON, exact changed scope and snapshot hashes.

    Produces AWAIT_HUMAN only as operator-review disposition. The Host cannot
    authenticate native subagent provenance from model-provided text alone.
    No auto-merge or security-pass attestation.
    """
    return execution.submit_audit(run_id, audit_report)


@mcp.tool()
def harness_execution_status(run_id: str) -> dict:
    """Read external evidence stage and Host SQLite state. No Agent execution."""
    return execution.status(run_id)


if __name__ == "__main__":
    mcp.run("stdio")
