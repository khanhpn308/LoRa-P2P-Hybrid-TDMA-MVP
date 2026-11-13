# GOCARS — AGY graph-first structural refactoring workflow

Status: integration proposed in Issue [#359](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/359); effective upon owner approval and merge. Scope: `backend-go/`. Native AGY/CodeGraph execution: NOT_VERIFIED by this integration.

## 1. One-time operator setup

1. Review and merge the adoption PR for Issue #359; sync the local trusted repository. The merged, owner-approved adoption is the approval record for GOCARS-2.0, GO-BE-002 and Section 8 review triggers. No extra per-rule approval is needed. This is not approval to edit a future backend Issue.
2. In WSL or the actual AGY environment, open the repository root. Check `git status --short --branch`, `git rev-parse HEAD`, `agy --version`, `codegraph version`. Use the repository-pinned Go toolchain for subsequent backend checks. Do not automatically install or upgrade anything.
3. Verify the CodeGraph MCP registration and actual tool schemas in AGY, or verify the installed CodeGraph CLI. From the exact checkout run the installed version's supported equivalents of:

```sh
codegraph status . --json
codegraph sync .
codegraph explore "Map backend-go server initialization, package dependencies and symbol ownership"
```

If the index does not exist, use `codegraph init --local-only` only when supported and local index creation is authorized. Check the installed command help rather than guessing flags. Confirm Go files and representative symbols appear in the graph, not just a successful exit code. Use an index associated with each candidate worktree; do not reuse stale main-branch evidence. Local `.codegraph/` artifacts are already ignored by the repository.

4. Run `agy` from the repository root, open `/agents` and select `gocars-refactor`. Confirm native tool permissions include MCP or CLI access; tool availability depends on the installed AGY version and operator setup. Restart AGY after updating the agent definition so an existing session does not retain the old executor configuration.

### AGY 1.5.7 executor compatibility

Observed failure: `failed to construct executor: unknown component` for `call_mcp_tool`, `list_resources` and `read_resource`. These are not valid static native tool registry entries in the observed AGY release. Agent v1.1 removed them and the redundant `read_file` alias (historical Issue #213). Agent v1.2 aligns with the canonical native profile adopted in PR #358: `run_command`, `view_file`, `write_to_file`, `replace_file_content`, `invoke_subagent`. Do not reintroduce legacy `write_file`/`edit_file`, `manage_task` or `send_message`. Runtime compatibility must be smoke-tested after restarting AGY. Do not add plugin names or generic MCP tool aliases to the static `tools` list. The connected CodeGraph MCP server can be used if its actual tool is exposed and callable in the selected agent; `/mcp` connection status alone is insufficient. Otherwise invoke CodeGraph CLI via `run_command`. The graph remains mandatory: both transports unavailable => `BLOCKED_CODEGRAPH`, not a bulk file-read fallback.

After syncing the patched branch, exit and restart AGY, select the agent, and first run a harmless read-only CodeGraph smoke query, for example `AUDIT_ONLY: use CodeGraph to identify cmd/server/main.go and BuildServeMux; do not edit files.` Record actual tool output and version. Success must show both executor startup and a genuine graph result. Static tests cannot prove compatibility with a running AGY installation. If a future release reports another unknown tool, record the exact error and update the reviewed native allowlist and regression tests; do not silently downgrade graph requirements or turn on unrelated MCP servers. No Espressif docs authentication is required for a Go backend-only task.

## 2. Normal activation

```text
Refactor lại codebase này.
```

The agent automatically performs graph preflight, package-partitioned structural AUDIT_ONLY and PLAN_ONLY. If a unique applicable OPEN Issue, exact allowed paths and recorded approvals already authorize the plan, it proceeds to REFACTOR and VERIFY with existing Host and Auditor gates. Otherwise it returns the plan and precise missing authorization; it does not create a new Issue or modify main. Use `Refactor backend #N` to disambiguate an existing authorized issue.

## 3. Mandatory graph workflow

- Discover real CodeGraph tools; prefer MCP `codegraph_explore` or the actual CLI. Verify index root, version, freshness, Go coverage and representative source. Neither path available => BLOCKED_CODEGRAPH.
- Start with path metadata and compact Go package/build graph; then graph queries per package/ownership partition. Record symbol, callers, callee/impact and test relationships for planned changes. Retrieve exact current source only when required to reason or patch. No recursive bulk reads as a fallback.
- Use bounded graph results and fresh Worker contexts per coherent change group. Retain a compact external ledger, not the entire source in context. Soft budgets are not correctness limits. Resolve graph gaps, build tags, dynamic registration and external consumers explicitly. Never infer dead code from a missing edge.
- Refresh graph after each change group and candidate switch. Record query commands/receipts, roots and results, coverage gaps, raw-read exceptions and actual regression evidence. No fabricated token savings.

## 4. Authority and verification

GOCARS is a structural planning and review profile; the existing Go Engineering Standard V2 remains authoritative for engineering quality. The integrated source is the accepted baseline, not a second full engineering audit. GOCARS and CG IDs remain separate from the Host V2 rule catalog. Preserve trusted G0 context, exact Issue paths, scoped V2 rule selection/receipts, full changed diff review, fresh Auditor, and human approval. Use existing Native Fast Lane and quality gates; no nested consumer AGY automation.

The accepted design is ADR 0004 / Owner #273, Event-driven CAD/CSMA-CA and Gateway Continuous RX; do not restore historical TDMA scheduling. No R3 engineering changes in routine cleanup; report incidental defects separately. No deployment, auto-merge, destructive operations, or unauthorized Git writes.

The GO-BE-002 structural rule is approved upon adoption; its deterministic AST CI activation is a separate staged issue coordinated with a compliant entry point. Existing gofmt/build/test/vet checks remain. Instruction-level CodeGraph fail-closed behavior is not OS-level interception: an actual supervised AGY/CodeGraph run and any future deterministic graph gates need independent evidence. Static tests only validate configuration and declared policy.

## 5. First-run acceptance

Record actual Agent selection, AGY version, CodeGraph version/transport, candidate SHA/root/index status, real package and impact query receipts, compact ledger, and PLAN_READY or BLOCKED status. Do not claim E2E PASS until a real authorized run produces verified evidence. Keep local index artifacts and sensitive/raw outputs out of commits.
