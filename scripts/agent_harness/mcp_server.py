"""Local P0 Harness MCP stdio bridge. Requires the official MCP Python SDK v2.

No arbitrary shell, Docker, AI subprocess, GitHub write or Git mutation tools.
"""
from __future__ import annotations

from mcp.server import MCPServer
from mcp_host import HarnessMCPHost

host = HarnessMCPHost()
mcp = MCPServer("lora-harness-readonly")


@mcp.tool()
def harness_preflight(issue_number: int) -> dict:
    """Read an OPEN scoped GitHub Issue and preview a unique Host worktree plan.

    Does NOT create a branch/worktree or approve the Issue. A successful
    PREFLIGHT_ONLY is NOT BUILD_VERIFIED or AUDIT_PASS.
    """
    return host.preflight(issue_number)


@mcp.tool()
def harness_status(run_id: str) -> dict:
    """Read a previously prepared Host run from the external SQLite journal.

    No task/agent/build is launched. Report actual persisted state only.
    """
    return host.status(run_id)


@mcp.tool()
def harness_verify_candidate(run_id: str) -> dict:
    """Read Host scope/hash verification for a prepared candidate.

    SCOPE_SCAN_PASS_ONLY is NOT build, audit, HIL or RF verification.
    """
    return host.verify_candidate(run_id)


if __name__ == "__main__":
    mcp.run("stdio")
