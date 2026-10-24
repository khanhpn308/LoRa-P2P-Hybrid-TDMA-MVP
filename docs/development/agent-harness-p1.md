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


## P1-B2-A — Deterministic Codex→Check→AGY→Repair pilot (Issue #34)

**Status: SIMULATION CODE, awaiting CI; NOT a live autonomous run.**

The new `scripts/agent_harness/p1/pilot.py` links P1-A's PREPARED SQLite job to an independent pilot journal with compare-and-swap transitions. It allows at most two bounded repair attempts, requires every Worker candidate to pass P1-B1 Git scope/secret/symlink/source-SHA checks, recomputes the exact candidate hash after the Host check and after the Auditor, and enforces full changed-file coverage using P0's AGY report validator.

The state sequence is:
`READY → WORKER_RUNNING → VERIFYING → AUDITING → AWAIT_HUMAN`. Check or audit FAIL transitions to `REPAIR_REQUIRED → WORKER_RUNNING` while a budget remains. A repeated identical failed diff, malformed audit, scope violation, missing paths, or budget exhaustion gives `BLOCKED`. Worker/check/Auditor interruption gives `RECOVERY_REQUIRED`; the Host NEVER auto-resumes a partially modified candidate. SQLite records metadata and SHA-256 receipt hashes, not model tokens, raw output, credentials or private keys.

### Safe WSL2 dry-run with ZERO account/quota usage

From a clean checkout of this P1-B2 feature branch:

~~~bash
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/agent_harness/p1/pilot_demo.py
~~~

The demo provisions only a disposable local Git repository under a temporary directory. Its fake Worker writes a harmless Python fixture; the first fake Host verification FAILS, the second succeeds after the Worker changes the candidate; the fake independent Auditor returns complete PASS. The expected terminal result is `SIMULATED_AWAIT_HUMAN` with two attempts. Even if all tests pass, `build`, `audit`, `hil` and `rf` are explicitly `NOT_VERIFIED`. The demo does not invoke `codex`, `agy`, `idf.py`, Docker or GitHub writes.

### Live provider integration: NOT YET AUTHORIZED

A future production adapter must satisfy ALL of the following before anyone invokes `run_simulated_cycle` with real process callbacks or promotes its results:

1. Provision a disposable per-Issue runtime outside the personal WSL2 host; validate container/VM identity, UID, mounts, resource limits and process kill/restart behavior. Do not pass normal `~/.ssh`, `~/.git-credentials`, `~/.codex`, `~/.gemini`, GitHub write token, or host Docker socket into the Worker. Only operator-approved, scoped provider authentication and egress are allowed.
2. Verify actual Codex CLI and AGY headless versions/flags with harmless, read-only requests; approve provider sign-in mechanisms without credential extraction, account sharing or quota bypass. On AGY, status SUCCESS + schema-valid structured_output + permission diagnostics must all pass; `exit=0` alone does not suffice.
3. Use a Host-owned ESP-IDF v6.1 image identity and deterministic build receipt, not an AI narrative. Record raw logs only in a separately access-controlled redacted evidence location; preserve exact candidate fingerprint across checks and review.
4. Auditor must receive a bounded independent snapshot with zero write access; never reuse the Worker writable tree or conversation. Require an actual verified PASS with full changed-file coverage.
5. Only after code is committed by a trusted Host and tests/CI are re-verified at the final exact commit SHA may a separately reviewed least-privileged Host publisher create a **Draft** PR. No automatic merge. No ESP32 flash/RF/HIL or MAC/security changes without human review.

The P1-B2-A simulation is intentionally a test harness for these invariants, **not proof** that model isolation, network policy, provider credentials or a safe unattended runtime exist.

Current Antigravity source: https://antigravity.google/docs/cli/headless/


## P1-B2-B — Operator-controlled real CLI smoke tests (Issue #34)

**Status: CODE_WRITTEN / CI or WSL2 LIVE NOT_VERIFIED until evidence exists.** This stage tests model CLI authentication and response under constrained Docker settings only, before permitting a live coding task. It is NOT an end-to-end autonomous coding run.

Files:
- `p1/provider_runtime.py`: plans read-only, no-privilege Codex/AGY Docker invocations, uses reviewed immutable image ID, distinct preprovisioned provider home volumes, bounded memory/CPU/PIDs and a disposable read-only fixture (NOT the monorepo). Probes existing Docker image, user-defined bridge network and auth volume before execution; never builds/pulls images or creates networks.
- `p1/provider_probe.py`: defaults to `PLAN_ONLY`. Explicit `--execute --confirm-external-egress-policy` enables ONLY a harmless, read-only, single-turn provider smoke test. Returns `READ_ONLY_MODEL_PROBE_PASS_ONLY` or `BLOCKED` with hash/size receipt, never raw model output or credentials.
- `tests/agent_harness/test_p1_b2_live_probe.py`: CLI argument/permission/denial/timeout-policy and fake-provider integration tests, no real tokens.

### Operator preparation and safety prerequisites

**Not handled by the Harness:** A reviewed, immutable container image must already contain the supported Codex CLI or Antigravity CLI and required dependencies. Validate each CLI version/flags against actual image binaries; the CLI versions seen on WSL2 are not evidence of versions inside the image. The Docker daemon and image supply chain must be trusted. Never put credentials in Docker image layers, `docker build --build-arg`, environment variables printed in logs or Git files.

Provision a *dedicated auth volume per provider* (names `lora-agent-codex-auth-...` and `lora-agent-agy-auth-...`) with isolated authorized login, owned/writable by container UID 10001. These are persistent volumes; users must rotate/revoke credentials according to provider terms and never mount their normal WSL2 user home, `~/.codex`, `~/.gemini`, SSH keys, GitHub write token, or host Docker socket. The provider should be authenticated interactively within this isolated profile, using an approved login flow. Do not copy browser cookies, harvest tokens, share accounts or circumvent usage limits.

Create an externally secured, dedicated **bridge** network named `lora-agent-egress-...` with verified outbound allowlist/proxy and resource governance. **Docker bridge networking alone is NOT egress allowlisting**; this module can only verify that the network exists and uses driver `bridge`, not that its firewall policy is effective. A private network with no external provider connectivity will fail the live smoke, and that is preferable to silently broadening outbound access.

### Running in dry-run mode (no quota)

From a clean PR branch/worktree with P1-B2-B code, after the image, profile volume and dedicated network have been provisioned:

~~~bash
python3 -m unittest discover -s tests/agent_harness -v

# Obtain the immutable ID from the operator-approved CLI image:
docker image inspect YOUR_REVIEWED_CLI_IMAGE --format '{{.Id}}'

python3 scripts/agent_harness/p1/provider_probe.py \
  --provider codex --image-id sha256:YOUR64CHARIMAGEID \
  --network lora-agent-egress-reviewed \
  --profile-volume lora-agent-codex-auth-pilot

python3 scripts/agent_harness/p1/provider_probe.py \
  --provider agy --image-id sha256:YOUR64CHARIMAGEID \
  --network lora-agent-egress-reviewed \
  --profile-volume lora-agent-agy-auth-pilot
~~~

Replace the placeholder image ID(s) with a real reviewed 64-hex SHA-256. Codex and AGY may be installed in **different** approved CLI images. The dry-run does not authenticate, run models, make network calls, create a Docker container or inspect provider credentials.

### Explicit real smoke test (requires external human approval)

After independently verifying network filtering and dedicated profiles, re-run each command with:

~~~text
--execute --confirm-external-egress-policy
~~~

This confirmation flag is an **operator acknowledgment**, NOT attestation or a substitute for actual network/VM security. A real provider request consumes provider quota. Codex is invoked in read-only mode; AGY gets `--sandbox` and no dangerous permission bypass. The fake README fixture is read-only, not a working Git repository. Codex therefore uses `--skip-git-repo-check` **only for this disposable non-Git smoke directory**; normal per-Issue code changes must retain Git/source-SHA validation. The command validates the terminal response, soft permission denials (including exit 0 cases), errors and bounded output.

PASS here means **only** that the provider responded in an isolated, read-only smoke test. It does not prove an end-to-end Agent loop, firmware build, audit coverage, complete quota governance, precise egress restriction or unattended safety. HIL, RF and TDMA remain NOT_VERIFIED.

### Subsequent P1-B2-C work (still open)

Integrate an externally isolated, per-Issue **scratch copy** of code for the Codex Worker; import only vetted changed paths into the Host-owned worktree; build Gateway and Node with trusted Docker ESP-IDF v6.1 receipts; send a separate immutable AGY snapshot and require a full schema-valid independent report; enforce post-build/audit candidate hashes, crash recovery, final SHA provenance and Host-owned Draft PR publication only after CI. Do not pass P1-B2-A's `SIMULATED` receipts off as real build or audit evidence.
