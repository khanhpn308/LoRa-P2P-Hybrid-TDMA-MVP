# Harness MCP onboarding — Codex + AGY (Issue #95)

> **Status:** proposed implementation, pending WSL2 real-client testing and Human Security Review.  
> **Dependencies:** MCP Python SDK v2.3.0, Python 3.11+, GitHub CLI for preflight only.  
> **Security boundary:** the MCP tool surface is read-only P1 Host inspection; it **does not** run Native Fast Lane coding tasks or activate Draft PR #84's signed execution.

## One command on a new WSL2/Linux checkout

```bash
cd ~/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
bash scripts/setup_harness.sh
```

In an interactive terminal, if Codex or AGY is installed and MCP is absent, the setup shows an explicit plan and asks you to enter `INSTALL MCP` before making **any** user configuration change. Decline to continue with plain Doctor checks. Noninteractive execution and `--json` remain read-only. A developer can explicitly request installation later:

```bash
bash scripts/setup_harness.sh --install-mcp
```

For a **dry-run plan without changing anything**:

```bash
python3 scripts/harness_mcp_setup.py --plan
```

## What is installed and how it is registered

1. Create/reuse isolated user venv at `~/.local/share/lora-harness/mcp-venv` (never write a venv to Git working tree).
2. Install **pinned** SDK `mcp==2.3.0` using `pip --no-input`. Requires network on the first install; does not require sudo. Review dependency/provenance risks before confirmation.
3. Launch a temporary **stdio** MCP server with the venv Python and verify protocol negotiation, exactly three tools in `tools/list` and an invalid Issue #0 returning `BLOCKED`. The negative call is offline and must not trigger any GitHub request.
4. Register `lora_harness` in **Codex** via the supported `codex mcp add lora_harness -- <venv-python> <server.py>` command, then re-read the config. Existing unrelated MCP servers remain unchanged.
5. Register `lora_harness` in **AGY** `~/.gemini/config/mcp_config.json`, modifying only `mcpServers.lora_harness`. Original entries are preserved, a 0600 backup is created for existing config, and new config is written atomically (0600).
6. If Codex or AGY is absent, skip that client with an explicit `SKIP`. Conflicting `lora_harness` entries, malformed AGY JSON and symlinked configs are **BLOCKED**, never overwritten automatically.

**The installer will not:** install Codex/AGY, request account passwords/tokens, change shell profiles, use root, add Docker permissions, initialize signer, start firmware/Go services or push/merge a PR.

## MCP tools and limits

| MCP tool | Allowed operation | Not implied |
|---|---|---|
| `harness_preflight(issue_number)` | P1 `prepare` dry-run for a scoped OPEN Issue; needs local `gh auth` | No worktree, no code, no approval |
| `harness_status(run_id)` | Read existing Host SQLite journal (may touch SQLite WAL metadata outside repo) | No agent execution |
| `harness_verify_candidate(run_id)` | Read scope/hash check with trusted `host_gate.py` | No build/audit/security sign-off |

MCP does **not** automatically create an Agent. With Codex or AGY you can still type **`Chạy Issue #N`**; this invokes the existing Native Fast Lane Coordinator under `AGENTS.md` and SOP, **not** the read-only MCP tools. MCP lets both clients call the same P1 read tools. Full execution through MCP remains unmerged and not authorized in this onboarding change.

### Read-only MCP versus Native Execution Bootstrap (Issue #152)
- **`--install-mcp` (Issue #95):** Registers the 3 read-only Host inspection tools (`harness_preflight`, `harness_status`, `harness_verify_candidate`) via MCP stdio protocol. It does **not** provide Shell execution, File Edit, Git mutation or subagent spawning.
- **`--configure-native` (Issue #152):** Configures client settings and permissions for native tool execution (Shell, File Edit, Git, fresh independent Auditor) for the Native Fast Lane (`Chạy Issue #N` / `Nghiệm thu PR #N`).
- Running `--install-mcp` does not replace `--configure-native`, and vice-versa. Do not assume MCP tools suffice for coding or PR review execution.

## After installation: client connection verification

Exit existing CLI sessions and **restart** both Codex and AGY so they reload MCP configs. In Codex run `codex mcp list` and open `/mcp` in the TUI. In AGY use `/mcp` and inspect `lora_harness`. The setup smoke proves that the server works from an isolated MCP SDK **client**, but it cannot prove live connection inside both interactive clients; record these as `NOT_VERIFIED` until checked separately.

Re-run the safe local smoke after install:

```bash
~/.local/share/lora-harness/mcp-venv/bin/python scripts/agent_harness/mcp_smoke.py scripts/agent_harness/mcp_server.py
```

Expected: `MCP_STDIO_SMOKE_PASS`. No issue mutation, Docker, code editing or RF test occurs.

## Troubleshooting and security

- `python3 -m venv` fails: install `python3-venv` through approved package management; never use `sudo pip`.
- Missing `codex` or `agy`: install from that provider's official instructions and rerun.
- Config conflict: inspect existing entry and resolve manually; do not reset/delete unrelated MCPs.
- `gh auth` missing: only `harness_preflight` needs authenticated GitHub; the offline smoke still runs.
- Installer abort after successful SDK install: venv remains reusable; client config remains unchanged until smoke succeeds.
- Python SDK/transitive dependencies: **pin and review** upgrades separately; exact top-level SDK pin is not an entire transitive lockfile.
- MCP server runs as the current OS user. Separate CLI conversations are **not** filesystem, credential or provider isolation.
- No claims of CI, Firmware Build, HIL, RF or penetration-test PASS from setup/handshake.

## Developer verification before merging

```bash
bash -n scripts/setup_harness.sh
python3 -m unittest discover -s tests/agent_harness -p test_mcp_host.py -v
python3 -m unittest discover -s tests/agent_harness -p test_harness_mcp_setup.py -v
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/harness_mcp_setup.py --plan
git diff --check
```

**Acceptance needs additional real WSL2 testing** with installed Codex/AGY, a genuine stdio client smoke, config backup verification, independent security review, and evidence of CLI `/mcp` connection. GitHub Actions `OWNER_WAIVED` does not mean `CI_PASS`.
