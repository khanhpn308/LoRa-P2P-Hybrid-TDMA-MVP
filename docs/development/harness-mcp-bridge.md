# Shared LoRa Harness MCP Bridge — P0 (DRAFT)

**Issue #81.** Local read-mostly MCP server on `stdio` usable by **Codex CLI** and **AGY CLI**. Keep one trusted Host Harness, not two separate implementations.

## Purpose and scope

Operator says **“Kiểm tra Issue #N bằng Harness”** in the chat. The selected Coordinator may call MCP tools without requiring an issue-specific terminal command. MCP exposes tools; it does **not** orchestrate Worker/Auditor agents by itself.

| MCP Tool | Trusted Host operation | Actual evidence |
|---|---|---|
| `harness_preflight(issue_number)` | Existing `p1/cli.py prepare` dry-run, read GitHub Issue | `PREFLIGHT_ONLY`; no branch, worktree, journal or build |
| `harness_status(run_id)` | Existing `p1/cli.py status` | Real persisted SQLite state; possible external SQLite WAL metadata writes |
| `harness_verify_candidate(run_id)` | Existing `p1/host_gate.py`, without Docker image | `SCOPE_SCAN_PASS_ONLY`; not build, audit or RF/HIL |

All arguments are typed/validated, executable paths fixed inside the installed reviewed source clone, subprocess timeouts/output bounded, and stderr intentionally not returned. Tools **cannot** execute arbitrary shell commands, write source, start Docker or AI, access credentials, commit/push/merge or transmit RF. Do not enable a new write tool without a separate security-reviewed Issue.

## One-time MCP installation (operator action, not repeated per Issue)

Use Python 3.11+ with official MCP Python SDK **v2**. Review/install `scripts/agent_harness/mcp-requirements.txt` in an isolated local Python environment; lock the resolved SDK version for deployment. The entrypoint is `scripts/agent_harness/mcp_server.py`. Never install packages dynamically from a model tool call.

Configure **Codex** in trusted project `.codex/config.toml` or user `~/.codex/config.toml`:

```toml
[mcp_servers.lora_harness]
command = "/home/khanh/.venvs/lora-mcp/bin/python"
args = ["/home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/scripts/agent_harness/mcp_server.py"]
startup_timeout_sec = 20
```

Configure **AGY** in workspace `.agents/mcp_config.json` or `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "lora_harness": {
      "command": "/home/khanh/.venvs/lora-mcp/bin/python",
      "args": ["/home/khanh/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP/scripts/agent_harness/mcp_server.py"]
    }
  }
}
```

These are **templates**, deliberately not auto-enabled by the P0 PR before trusted dependency installation and staging handshake verification. Both CLIs show connected MCP tools via `/mcp`. AGY's custom Coordinator remains separately selectable via `/agents`; Codex uses its native session instructions and MCP tools. Configuring an MCP server does not create a new model or agent.

## Verification and limitations

- Offline unit tests: `python3 -m unittest discover -s tests/agent_harness -p test_mcp_host.py -v`.
- Next, after install: test the **real MCP client↔server handshake** and all three tools in Codex and AGY staging sessions, capture exact response/error receipts and versions. P0 has **NOT** completed that smoke in the development environment.
- A dry-run-generated `run_id` is ephemeral, **not** a persisted PREPARED job; never pass it to Host state checks as proof of execution.
- Current `host_gate.py` only validates scope and optionally previews build commands. It does **not** run builds or generate Audit PASS. Current `state.py` does **not** persist `AWAIT_HUMAN`.
- Do not expose secrets/auth profiles, arbitrary filesystem paths, scripts/commands from GitHub Issue bodies, or Docker socket through MCP. The MCP server process runs with the operator's OS permissions; it is not a sandbox.
- High-risk shell/build/worktree mutations require a separate Issue, independently reviewed Host authorization/approval mechanism, complete evidence, and human engineering review. No third-party wrapper of AGY consumer login.

**P0 status:** Local Host wrapper unit tests 6/6 PASS in an isolated code fixture. Official MCP SDK transport integration on the user's WSL2: **NOT_VERIFIED**. Autonomous Issue → Worker → Build → Auditor: **NOT_IMPLEMENTED**. ESP32 HIL / RF / TDMA compliance: **NOT_VERIFIED**.

References: [MCP Python SDK](https://py.sdk.modelcontextprotocol.io/), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp), [AGY MCP](https://antigravity.google/docs/mcp).
