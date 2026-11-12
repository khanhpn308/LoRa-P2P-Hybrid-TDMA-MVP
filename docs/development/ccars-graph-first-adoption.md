# CCARS v1.3 Graph-First adoption and local acceptance

Status: repository integration candidate, Issue [#357](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/357). Human review and live AGY/CodeGraph verification remain required. Reviewed source baseline: `f8f85e07704347ae5c2d7f5a79845c9bd625c1c5`.

## Tracked integration

- [CCARS v1.3](c-clean-code-refactoring-standard.md) organizes accepted C code; no baseline recertification.
- [Project AGY agent](../../.agents/agents/c-structural-refactor.md) and [Coordinator](../../.agents/agents/harness-coordinator.md): Graph-First entrypoint and delegated Worker handoff.
- [AGENTS.md](../../AGENTS.md): CodeGraph mandatory for CCARS; ordinary coding remains optional.
- [Existing quality gates](harness-quality-gates.md): CCARS and this runbook are control-policy paths routed to TOOLING-CHECK and SECURITY-CHECK, with CI path triggers. REF/CG IDs remain structural identifiers, not C/Go selector inputs.

## Local acceptance — operator WSL / AGY

1. Use an inspected checkout/branch containing the integration. Preserve existing changes; do not reset/stash or edit main. Check root and HEAD. Restart AGY if needed; inspect `/agents` for `c-structural-refactor` and `/mcp` for actual CodeGraph tools. A tracked definition or MCP config entry alone is not live access.
2. Verify installed CodeGraph product/version and actual supported tool schemas. Use `codegraph --version` and `codegraph status` if supported. Verify exact worktree/source identity, relevant C/H coverage and representative symbols (e.g. `node_update_oled_unjoined`, file-qualified `app_main`). Existing read-only `lora_harness` MCP is separate; see [MCP onboarding](harness-mcp-onboarding.md). Upstream IDE support does not prove AGY CLI support.
3. Initialize/sync only with explicit authorization and the installed version's supported command. Inspect exclusions: secrets, generated outputs, SDK caches and unrelated files. Keep derived index/cache out of commits and LLM context. No implicit global config changes, installation, tool upgrade or permission expansion.
4. Select the project agent and enter:

   ```text
   Refactor lại codebase này.
   ```

   Default PLAN_ONLY without authorized OPEN Issue and exact paths. Expect actual graph calls, bounded inventory, ownership/impact map, KEEP/MOVE/SPLIT/GROUP/DEFER and graph evidence. No tracked edits, Issue/branch creation or bulk source reads by default.
5. Test negative cases in a disposable environment: MCP and equivalent authorized CLI unavailable; wrong root; stale graph; missing relevant symbol; unresolved indirect dependency. Expect BLOCKED_CODEGRAPH or DEFER, not recursive scanning or writes.
6. After smoke and human review, use a separate approved pilot Issue:

   ```text
   Chạy CCARS Refactor Issue #N
   ```

   Reuse [Native Fast Lane](harness-fast-lane.md), G0, scoped C V2 selection, existing Host checks and independent Auditor. Verify actual candidate graph before and after each patch. Pilot suggestion: only Node OLED presentation, preserve existing behavior and Kconfig. Issue #357 does not authorize firmware edits.

## Existing Host tests and limits

Run from a trusted checkout:

```bash
python3 -m unittest discover -s tests/agent_harness -p test_quality_gates.py -v
```

Record exact candidate SHA, commands/exits and actual evidence for routing, independent review and AGY/CodeGraph smoke. No new MCP server, duplicate technical quality framework, selector groups, firmware/contract or user-config changes. Runtime gate independently observing actual graph calls/fingerprints before edits and OS/credential isolation remain separately reviewed implementation tasks. Do not infer hard enforcement from instruction text, routing tests or CI.

Architecture authority remains unchanged. Historical Hybrid TDMA instructions conflict with newer approved Pure CAD ADR at the reviewed baseline. STOP_AND_REPORT if affected; no architecture migration during cleanup.
