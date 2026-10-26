# Shared Harness MCP execution, Draft, Issue #83

Status: `HARDENED_DRAFT / EXECUTION_DISABLED / PRODUCTION_NO_GO`.
PR #84 remains stacked on Draft PR #82. Neither PR is approved for merge or live execution.

## Current capability

The shared stdio server registers ten tools. Registration is not execution authorization.

| Tools | Current behavior |
|---|---|
| `harness_preflight` | Existing read-only Issue preview, fixed Host CLI |
| `harness_status`, `harness_verify_candidate` | Existing bounded Host inspection; SQLite can update WAL metadata |
| `harness_execution_status` | Validate receipt chain, log hashes, snapshot, journal identity and current candidate before returning a disposition |
| `harness_prepare_issue` | Always `BLOCKED`; no worktree/journal creation |
| `harness_worker_handoff`, `harness_verify_worker`, `harness_run_checks`, `harness_auditor_handoff`, `harness_submit_audit` | Always `BLOCKED` through the public execution guard |

`LORA_HARNESS_MUTATIONS=operator-enabled` no longer authorizes any operation.
There is no enabling environment setting, model argument or client approval hint.
This stdio transport has no authenticated, per-call Host approval channel.
Source/Issue pins from a model are data, not authorization. Preparation also lacks
an atomic Issue-hash check before the underlying legacy CLI mutates its journal.
Until these boundaries receive an approved implementation, preparation must fail
before calling that CLI. Do not patch the guard to enable a deployment.

Native Worker/Auditor execution remains inside Codex/AGY, outside this MCP server.
It has no provider CLI invocation, commit, push, merge, flash or RF tool.
Native model provenance remains `NOT_VERIFIED`; schema-valid JSON cannot attest it.

## Process limits

`mcp_host.bounded_run` is shared by the P0 Host wrapper, ignored-file inspection,
Issue snapshot lookup and the internal command logger.

- Both stdout and stderr are drained incrementally with POSIX selectors. Their
  combined bytes count toward the limit while the process is running.
- P0 captures at most 65,536 combined bytes. Staged command logs have a 300,000-byte
  limit. The overflowing chunk is truncated before writing the log, then execution
  fails. Stderr is counted but never returned as a P0 receipt.
- The monotonic deadline covers pipe draining and process exit, including a process
  that closes its pipes but keeps running. Callers use fixed timeouts, at most
  1,800 seconds; no tool accepts a timeout or command override.
- Each subprocess has a new session. Cleanup sends SIGKILL to its process group
  and reaps its leader, with a five-second reap timeout, on success, timeout,
  overflow and Python interruption. Background descendants in that group are
  killed even when the leader exits successfully.
- Logs use exclusive creation, `O_NOFOLLOW`, mode 0600 and streaming hashes.
  Partial logs receive failure metadata and hashes. Command execution receives a
  small credential-free environment; stderr/log text is not returned to a model.

A process group is not an OS sandbox. A descendant that deliberately escapes its
session is outside this guarantee. SIGKILL of the server itself cannot execute
Python cleanup. Docker containers are daemon-owned; killing the Docker client
cannot prove container termination. The staged build path therefore starts no
Docker container and creates no `CHECKS_VERIFIED` receipt.

Tests of trusted installed source do not test candidate code. Candidate firmware,
Harness source/tests, backend and client code cannot gain PASS from those unrelated
tests. The remaining internal diagnostic path accepts only docs/pilot fixture
changes, runs trusted Host tests, then blocks before builds. It is also behind the
disabled public guard. A future candidate runner needs isolated, bounded execution
and reviewed container lifecycle/cancellation, including cleanup evidence.

## State and evidence checks

Evidence lives outside Git at `../.lora-harness-evidence/<run_id>/`.
Existing directories must be private and owned by the Host OS user; run records
are regular, private files opened with `O_NOFOLLOW`. JSON objects reject duplicate
keys and non-finite constants, and have a 100,000-byte limit.

Each internal stage holds a nonblocking exclusive lock for its entire operation,
including commands and snapshot writes. A second request fails immediately. An
`operation.json` marker is persisted before side effects and removed only after a
committed stage transition. Failure or interruption retains it for manual recovery.
A failed returned result is saved as `failure.json` when possible. No automatic
retry follows partial tests, invalid audit, interrupted writes or stale input.

Receipt and run-record writes use atomic replacement plus file/directory fsync.
These two files are not a single transaction. A crash between them leaves an
unindexed receipt that fails validation; it cannot silently replay the operation.

State validation requires every preceding receipt, its expected filename and hash,
and successful, unchanged logs for each claimed check/build. Missing stages cannot
be fabricated by changing only the current stage. Journal run, Issue, source SHA,
branch and worktree must agree with the external run record. Issue-hash and scope
pins are also queried from the actual SQLite row through a short-lived read-only
connection; legacy CLI status alone does not include those approval fields.

Audit snapshots are bounded, reject symlinks/nonregular entries and verify their
complete file manifest. Frozen candidate bytes must match the Host candidate hashes,
and the candidate is rechecked after copying. Policy/schema ancestor symlinks are
rejected. Audit reports use the existing strict schema and exact reviewed scope.
Final status revalidates receipts, report, snapshot and current candidate; it blocks
if evidence or candidate bytes have changed. `AWAIT_HUMAN` is a disposition requiring
human review, not native provenance, security approval, HIL or RF PASS.

Private files and hashes detect corruption relative to the recorded manifest.
They are not signed attestation or isolation from an attacker with the same OS UID
who can rewrite both data and manifests. A future Worker must not have write access
to the Host installation, approval authority, evidence or credentials.

## Local verification, 2026-10-27 operator timezone

Implementation scope is Issue #83's six explicit paths. The owner approved adding
`tests/agent_harness/test_mcp_host.py`, and the live Issue scope was updated before
editing that test. No workflow, contract, firmware, toolchain pin or dependency
manifest was changed. Source discovery used narrow reads; CodeGraph was unavailable
and no `.codegraph/` directory was present. Graph checks are `NOT_RUN`.

Use these commands from the reviewed feature checkout:

```sh
python3 -m unittest discover -s tests/agent_harness -v
python3 -m compileall -q scripts/agent_harness tests/agent_harness
python3 scripts/verify_structure.py
git diff --check
```

The Python 3.12.3 baseline had 133 passing tests. The final suite passed all
164 tests, including 46 focused MCP tests. Command receipts are recorded in the PR update. Added failure cases exercise live stdout/stderr
flooding, exact output limits, bounded disk logs, early EOF, nonzero exit, failed
spawn, timeout, SIGTERM-ignoring descendants, background cleanup, interruption,
credential canaries, exclusive logs, concurrent stages, crash recovery, journal
mismatch, missing/tampered receipts/logs, unsafe snapshots and stale final status.
Stage tests override the guard only on isolated temporary test objects and mock
GitHub/model/build boundaries. They never enable a running MCP deployment.

The existing requirement `mcp>=2.0,<3.0` resolved to official SDK **2.3.0**, with
`mcp-types==2.3.0`, in a temporary Python venv. `pip check` passed. Import/registration
and a real SDK Client-to-server stdio smoke passed outside the restricted sandbox:
ten tools listed; four read-only calls with invalid inputs returned `BLOCKED`.
No mutating MCP endpoint was called. This proves transport discovery and rejection,
not valid-Issue execution or E2E. The sandbox attempt timed out; subsequent transport
checks used the same code outside that boundary. The client test reads SDK snake-case
attributes and accepts JSON text content for the server's plain `dict` return type.

Reproduce with the reviewed SDK installed, substituting its Python executable:

```sh
PYTHONPATH=tests/agent_harness /path/to/venv/bin/python -c \
  'import asyncio; from test_mcp_execution import sdk_readonly_smoke; asyncio.run(sdk_readonly_smoke())'
```

Only SDK 2.3.0 was tested. The dependency range is not a deployment lock. Native
Codex/AGY client integration and other SDK versions remain `NOT_VERIFIED`.

## GitHub Actions blocker

All five PR-triggered runs on initial head `070b6afd6693aaf8dd47029de06b0fb316529a93`
failed before a runner started. Their check annotations identify account payment or
spending-limit failure. Missing logs returned `BlobNotFound`, consistent with no job
execution. Detailed annotations were read through GitHub's check-runs API.

| Workflow | Initial failing run |
|---|---|
| Foundation | [40356912409](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/actions/runs/40356912409) |
| Backend Go | [40356912805](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/actions/runs/40356912805) |
| Clients | [40356912106](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/actions/runs/40356912106) |
| Contract syntax | [40356912252](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/actions/runs/40356912252) |
| Harness | [40356912138](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/actions/runs/40356912138) |

The account owner must repair Billing & plans or spending limits before CI can run.
The owner subsequently waived GitHub Actions as a completion condition for this
task. Record this as `OWNER_WAIVED`, while the observed CI result remains
`FAILURE / BILLING_BLOCKED`; it is not a CI PASS.
No checks were removed, bypassed or disabled, and no runner/permissions changes were
made. Local tests cannot turn these GitHub checks into PASS. Do not change toolchain
pins or workflows to conceal an account-level failure.

## Remaining acceptance gates

- GitHub CI is owner-waived for this task; CI execution on the updated head is
  `NOT_VERIFIED`. Existing checks and protections remain unchanged.
- P0 PR #82 remains Draft/unmerged. Keep the stacked base until human approval.
- Reviewed Host authorization and atomic approval/Issue-pin apply are required.
- Candidate execution isolation and Docker lifecycle cleanup remain unimplemented.
- Independent security review and native Codex/AGY invocation records are pending.
- Real supervised Issue-to-Worker-to-build-to-Auditor E2E is `NOT_RUN`.
- ESP-IDF builds, HIL, RF, TDMA timing and hardware acceptance are `NOT_VERIFIED`.

References: [Issue #83](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/83),
[PR #82](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/82),
[PR #84](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/84),
[official SDK](https://py.sdk.modelcontextprotocol.io/).
