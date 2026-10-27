"""Shared Codex/AGY MCP stdio Host bridge.

A MCP server exposes trusted Host capabilities. It does NOT start native
Gemini/Codex model sessions or attest Auditor provenance. Require explicit
reviewed independent signed Host authorization before execution. Unsigned mutations fail closed.
"""
from __future__ import annotations

from mcp.server import MCPServer
from mcp_host import HarnessMCPHost
from mcp_execution import MCPExecution
from mcp_approval_request import ApprovalRequestMaker

host = HarnessMCPHost()
execution = MCPExecution(host)
request_maker = ApprovalRequestMaker(host)
mcp = MCPServer("lora-harness")


@mcp.tool()
def harness_preflight(issue_number: int) -> dict:
    """Read an OPEN, strictly scoped GitHub Issue; return dry-run plan and pins.

    No worktree is created. Operator must approve base_sha and issue_sha256.
    """
    return host.preflight(issue_number)


@mcp.tool()
def harness_approval_request(issue_number: int) -> dict:
    """Prepare an UNPRIVILEGED approval request using the operator's existing gh login.

    Returns a private JSON request path and a root-signer command for the
    operator to confirm in their own TTY. Does NOT sign, authorize or execute.
    """
    return request_maker.create(issue_number)


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

    A separately installed root-owned signer must sign the exact Issue/source
    pins after operator TTY confirmation. Host revalidates them before mutation.
    Environment flags and model self-claims never grant privileges.
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

    Requires valid root-signed grant, deterministic scope verification, pinned
    local ESP-IDF image and daemon cleanup. Not RF/HIL/timing verification, nor
    proof of tests for unrelated backend/client components.
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
