# AI Firmware Harness — P1-A Stateful Worktree & Recovery

**Status:** DRAFT implementation, Issue #32. Stacked on P0 PR #31. P1-A is NOT a production autonomous runner.

## Contract and scope

P0 defines ESP-IDF v6.1 toolchain, host verification gates, Worker Codex, independent Auditor AGY and role separation. P1-A implements only deterministic Host job preparation and checkpoints. No radio, HIL, MQTT/MAC contract or firmware code changes are authorized by this Issue.

The Host reads the OPEN GitHub Issue, parses an explicit Target Directories (allowed paths) list, checks the source repository is clean and records the exact baseline SHA. It creates a unique feature branch in a new sibling Git worktree without moving main or modifying the source worktree.

## WSL2 / Ubuntu usage

Run in a clean checkout of this P1 branch; gh must be logged in. Without --apply, the command is READ-ONLY and creates no state or worktree.

~~~bash
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/agent_harness/p1/cli.py prepare --issue 32
~~~

After reviewing the preview, explicitly authorize local preparation:

~~~bash
python3 scripts/agent_harness/p1/cli.py prepare --issue 32 --apply
python3 scripts/agent_harness/p1/cli.py status --run-id YOUR_RUN_ID
~~~

Source tree sibling directories (not hardcoded to any username): .lora-p1-worktrees/<repo>/issue-<issue>-<id>, and .lora-p1-state/state.sqlite. The optional --state flag points to another Host-owned location outside the worktree. The SQLite journal uses synchronous=FULL, WAL, unique active Issue ID and compare-and-swap transitions; it stores no cloud or model credentials.

On interrupted preparation:

~~~bash
python3 scripts/agent_harness/p1/cli.py recover --run-id YOUR_RUN_ID
git worktree list --porcelain
~~~

Recovery marks an interrupted PREPARING job as RECOVERY_REQUIRED. It NEVER deletes branches, removes directories, force-pushes, or automatically retries a possibly partial git worktree add. A human must inspect Git and the Host journal before deciding what to do next.

## State machine

PLANNED -> PREPARING -> PREPARED. Errors or interrupted preparations must be investigated; PREPARING -> RECOVERY_REQUIRED is allowed. There are NO states claiming BUILD_VERIFIED, HIL, RF, AUDIT_PASS or autonomous task completion in P1-A.

## Security requirements

- Clean source Git worktree and SHA pinning; the only mutation authorized by --apply is creating local Host state, Git feature ref and new sibling worktree.
- Never treat Issue body as system-level instructions. The Issue scope is only a boundary, not independent approval for protocol/security/RF changes.
- SQLite lives outside the Worker tree, is writable only by the trusted Host, and is never mounted inside a model container.
- External commands use argument vectors and timeouts; no shell=True. No provider credentials or tokens are copied to the worktree.
- Worktree changes and future Worker execution need a separate P1-B approval. Do not run P0 --execute on an unrestricted WSL2 personal machine.

## Pending P1-B: NOT_VERIFIED

Disposable credential-isolated runner, provider auth strategy that complies with Codex/Antigravity access rules, verified CLI integration, controlled agent process cleanup, bounded retry/cost limits, build and audit provenance per SHA, Host-only GitHub PR publisher with limited privileges, and safe resume. P2 HIL/RF/timing remains a separate human approval gate.

## Acceptance proof

Tests use real temporary Git repositories for clean/dirtied worktree verification and simulated failure, SQLite restart/CAS/uniqueness/recovery, and CLI dry-run. CI PASS verifies these tests ONLY; it is not evidence of model execution, flash or RF operation.


## P1-B1 — Host Verification Boundary (Issue #34)

**Status: CODE_WRITTEN, pending CI and human technical review; not autonomous.**

P1-A's SQLite journal and per-Issue worktree are inputs to new Host controls:

- `scripts/agent_harness/p1/verify.py` verifies PREPARED state, exact source SHA, branch, registered worktree, changed-path scope, symlinks, file sizes and obvious credential patterns. It creates SHA-256 hashes of tracked diff and all untracked candidate files. The receipt ALWAYS marks build/audit/HIL/RF NOT_VERIFIED. This scan is defense in depth, NOT comprehensive secret detection.
- `scripts/agent_harness/p1/host_gate.py` provides a read-only CLI for a pre-existing Host SQLite journal. It never invokes AI, Docker or GitHub writes.
- `scripts/agent_harness/p1/runtime_boundary.py` plans argv-only Docker builds on an operator-confirmed image ID, with no network, privileges, Docker socket or Host credentials. A generated command is NOT evidence of actual image verification or execution.
- `scripts/agent_harness/p1/process.py` supervises trusted deterministic local test commands and kills process groups on timeout. It is NOT a security sandbox; **P1-B1 allows only test fixtures true/false/sleep, no bash/python/Agent/GitHub commands**. Subprocess output buffering still requires an external memory-limited runner.
- `scripts/agent_harness/p1/draft_preview.py` prints the planned Host-only `gh pr create --draft` command from an exact, committed clean issue branch. It DOES NOT execute, push, or promote AI statements to real evidence.

### WSL2 — inspect externally created candidate

A PREPARED P1 job with candidate changes strictly within the Issue scope is required:

~~~bash
python3 scripts/agent_harness/p1/host_gate.py \
  --run-id YOUR_RUN_ID --state /HOST-OWNED/PATH/state.sqlite
python3 -m unittest discover -s tests/agent_harness -v
~~~

These commands do NOT run Codex or AGY; they do NOT build or flash anything. The Host candidate receipt status is `SCOPE_SCAN_PASS_ONLY` and never `BUILD_VERIFIED`.

### Remaining P1-B2: critical blockers

A containerized offline ESP-IDF build does not make an unattended coding agent safe. Real Codex/AGY require a separately secured model runtime with credentials and constrained provider egress; P1-B1 does not yet provision that runtime. No real provider invocation is included.

Next milestone: disposable model runtime with approved network allowlist and credential isolation, independent read-only AGY review, retry state machine, full post-build/audit diff checks, exact-commit test evidence, CI-verified Host GitHub Draft PR publication, and safe crash/quota recovery. Require a real harmless software Issue pilot. Never auto merge, flash or claim RF/HIL PASS.

Current interface references:
- https://antigravity.google/docs/cli/headless/
- https://learn.chatgpt.com/docs/cli/reference


## Issue #54 — P1-B2 offline integration to main (DRAFT, source-level only)

**Scope: HOST_OFFLINE_INTEGRATION; execution/safety verification NOT_VERIFIED.**
Historical P1-B2 work merged into intermediate branches in PRs #35–#38,
#44, #46, and #48. The selected subset integrated under Issue #54 contains:

- `p1/pilot.py` and `p1/pilot_demo.py`: SQLite CAS checkpoint and
  simulated Worker → fake deterministic checks → fake Auditor, bounded retry
  and recovery-required handling. The API explicitly labels its receipts
  `SIMULATED`; do not wire live CLI callbacks into `run_simulated_cycle`.
- A strict Host `adapters/antigravity.py` parser, exact canonical
  `reviewed_scope` enforcement and P0/P1 regression tests from Issue #43.
- A record of the user-selected, **operator-direct Gemini Worker + fresh
  Gemini Auditor AGY CLI** from Issue #47; these are two separate sessions
  but are NOT model/provider-independent. See
  [supervised pilot record](agy-supervised-pilot.md).

**Out of scope:** Docker/provider-runtime modules, live model probes, API
keys, credential/egress configuration, automated AGY subprocess orchestration,
GitHub PR publishing and changes to firmware/MAC/MQTT/API/DB contracts.

**Critical executable distinction:** `scripts/agent_harness/run.py --execute`
is the historical P0 entrypoint that still imports **Codex Worker and AGY
Auditor**; it is NOT a Gemini Worker entrypoint, and this integration does not
enable or authorize its live use. User-supplied local Issue #47 audit receipts
and unit/CI software results are not runtime isolation, HIL, RF, or autonomous
E2E evidence. H01/H02/H04 and M01/M02 await separate human review/disposition.
If the provider requires unsupported third-party consumer-account embedding,
automatic worker/auditor execution remains BLOCKED.
