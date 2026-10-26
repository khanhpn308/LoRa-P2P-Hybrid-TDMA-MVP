# Shared Harness MCP — staged execution (Draft, Issue #83)

**Status:** IMPLEMENTED_IN_DRAFT, not live-verified. Depends on P0 Draft PR #82. This is **not** an unattended general-purpose AI runner. Both Codex and AGY can call the same local MCP stdio tools, while native subagent orchestration stays inside their respective CLIs.

## 1. One-time configuration and safety

1. Review and merge P0 PR #82, then review this stacked PR separately. Until then, use only the isolated development worktree, **not main**.
2. Install the reviewed, patch-pinned MCP SDK in a dedicated venv; configure **both** Codex and AGY to point to the same trusted `scripts/agent_harness/mcp_server.py` (one server process per client).
3. P0 tools remain available with write execution DISABLED by default. Enabling `LORA_HARNESS_MUTATIONS=operator-enabled` in the **trusted MCP server process environment** unlocks potentially mutating Host tools; this setting **does not authenticate the user's per-Issue approval**. The operator must still approve each bounded tool call through the client's UI. If approval prompts are unavailable or are auto-accepted, **DO NOT enable execution**. Prompt-level instructions are not a security boundary.
4. A pinned, inspected local Docker image ID is required as `LORA_HARNESS_DOCKER_IMAGE_ID=sha256:...` to run firmware builds. Do not supply Docker daemon sockets, provider credentials or arbitrary paths via MCP arguments.
5. Operator must verify available native Worker/Auditor capabilities in the running client. MCP itself does not call these models, and cannot prove their independent origin from a JSON blob alone.

## 2. MCP tools and effects

| Tool | Effect | Required source |
|---|---|---|
| `harness_preflight(issue_number)` | P0 read/preview; returns source and Issue SHA | Existing trusted P1-A CLI |
| `harness_prepare_issue(issue_number,approved_base_sha,approved_issue_sha256)` | Host-only Git worktree + SQLite plan, external evidence run record; **MUTATES** disk | P1-A `prepare --apply`, rechecks both pins |
| `harness_worker_handoff(run_id)` | External handoff receipt with actual allowed paths; **does not spawn AI** | P1-A PREPARED |
| `harness_verify_worker(run_id)` | Host changed-path, binary/symlink/secret and SHA gate; external receipt | P1-B `verify_candidate` |
| `harness_run_checks(run_id)` | Fixed structure and Harness tests; pinned ESP-IDF v6.1 Docker builds for Gateway/Node using disposable **copied firmware tree**, external logs; candidate SHA before/after | Host-only `BuildBoundary` and checked image ID |
| `harness_auditor_handoff(run_id)` | Freeze changed candidate bytes, exact current Issue/AC, selected policy references, schema with SHA manifest; **does not spawn AI** | Valid Host checks |
| `harness_submit_audit(run_id,audit_report)` | Host validates report keys/scope, candidate and snapshot hashes; stores report/receipts and returns `AWAIT_HUMAN` | Fresh native Auditor report supplied by agent |
| `harness_execution_status(run_id)` | Read external receipt index and Host P1 SQLite state | External Host evidence |
| `harness_status`, `harness_verify_candidate` | Existing P0 inspection tools, unchanged | Trusted Host |

**Execution constraints:** fixed Host subprocess commands; no arbitrary paths/executables, no built-in GitHub writes, no push/commit/merge, no firmware flash or RF transmissions. Failure => `BLOCKED`, retain evidence for manual diagnosis. **A successful JSON audit does not prove native model independence.** `AWAIT_HUMAN` means a human must validate the native invocation record and inspect the changed files; `AUDIT_PASS` is not independently attested by MCP.

## 3. Coordinator run protocol

In **Codex or AGY**, with MCP connected, user says “Chạy Issue #N”. Agent must:

1. Call `harness_preflight`; inspect GitHub Issue, Acceptance Criteria and exact allowed paths; present source SHA/Issue SHA and risks for operator approval. Stop if Issue is already completed or conflicts with a merged PR.
2. After explicit approval, use `harness_prepare_issue` and record the **new** PREPARED `run_id`. Do not use preflight dry-run run_id.
3. Call `harness_worker_handoff`; spawn a **fresh, narrow native Worker** within the current CLI. For Codex, use Codex native agent tooling, for AGY use native `define_subagent`/`invoke_subagent`. MCP does not spawn either.
4. Once native Worker has actually finished coding, call `harness_verify_worker`. If BLOCKED, stop; do not broaden scope without amending Issue and renewed owner approval.
5. Call `harness_run_checks` (Host executes limited trusted test suite and both ESP-IDF v6.1 scaffold builds). If a software layer needs additional verification, mark `NOT_VERIFIED`; do not call the Issue complete.
6. Call `harness_auditor_handoff`; spawn a **fresh** native Auditor with tool write/shell/MCP access disabled; read actual frozen files, Issue and policies; produce schema-conformant report. Reject any shared Worker conversation. Context separation is not OS/provider isolation.
7. Call `harness_submit_audit` with genuine native response. Host checks structure/scope/SHA and stores evidence; report can reach `AWAIT_HUMAN` but native provenance remains `NOT_VERIFIED` unless separately evidenced.
8. Stop. Present external `run.json`, logs, scope hashes, audit receipts, actual tool-execution IDs and remaining risks for a human to review. Commit/push/PR/merge are **separate**, deliberately absent MCP tools.

**No automatic retry** after interrupted preparation, stale Issue SHA, partial Docker build, out-of-scope change, invalid/missing auditor response or hash drift. Inspect external Host journal and worktree before authorizing a repair.

## 4. Known limitations / required validation

- This implementation has **NOT** been connected to Codex or AGY on the operator's WSL2. P0 stdio smoke PASS applies only to 3 original tools, not newly added endpoints.
- New Host tests cover bounded state transitions. Live end-to-end Workspace/Worker/Build/Auditor execution in both CLIs is **NOT_VERIFIED**.
- Current tests use the trusted Harness source for Host structure/unittest runs; changes in backend/clients/contracts need their own additional test gates before a broader deployment. Gateway/Node Docker scaffold builds do not prove RF/HIL/TDMA timing.
- Source copy is firmware-only with limited extensions; unrecognized project files must fail/require review rather than silently claim unrelated components were tested.
- Stage receipts are recorded outside Git source in `../.lora-harness-evidence/<run_id>/`; mode 0700/0600. P1's SQLite state still remains `PREPARED` and does not store `AWAIT_HUMAN`. MCP uses its own external `run.json` state.
- Native Auditor provenance cannot be authenticated by accepting its returned JSON; a human reviewer must correlate actual native subagent tool records and approve it.
- The env opt-in and MCP tool annotations are **not authentication, authorization or sandboxing**. Never enable mutating tools on an untrusted MCP client, auto-approved session, secrets-bearing writable workspace or a machine whose Docker access is not appropriately controlled.
- No unattended provider scripting through consumer AGY CLI is implemented. No production security approval.

## 5. Staging verification checklist

- [ ] P0 #82 merged/rebased without losing changes; working tree clean.
- [ ] New Python unit tests PASS, old Harness suite PASS, static lints/checks pass.
- [ ] Codex and AGY each see 10 MCP tools after restart.
- [ ] New tool calls fail closed while execution is disabled.
- [ ] Operator-enabled supervised run on a **new** low-risk Issue: preflight pins, Host prepare, native Worker, Host path SHA gate, build logs, Auditor handoff and accurate AWAIT_HUMAN evidence.
- [ ] Independent technical/security review of tool permissions and Host receipts.
- [ ] HIL, RF, TDMA timing and fully unattended behavior remain NOT_VERIFIED.

References: [Issue #62 (accepted pilot)](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/62), [P0 Issue #81](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/81), [MCP SDK v2](https://py.sdk.modelcontextprotocol.io/).
