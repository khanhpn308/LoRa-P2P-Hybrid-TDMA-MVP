# Shared Harness MCP Execution — signed Host authorization (Issue #83)

**State:** `CODE_IMPLEMENTED / LOCAL_TESTS_ON_NEW_HEAD_NOT_VERIFIED / INDEPENDENT_REVIEW_PENDING / PRODUCTION_NO_GO`. GitHub Actions acceptance is `OWNER_WAIVED`, **not** PASS; workflow configuration and protections remain unchanged.

## Operator-signed authority

An MCP prompt, YAML instruction, environment flag or client approval hint is **not** authorization. `mcp_approval.py` verifies a root-signed Ed25519 grant bound to the exact Issue number, approved base SHA, live Issue body SHA-256, canonical allowed paths, six stages, random grant ID and expiry (at most 8 hours). The public key and grants are **root-owned and not writable by the MCP/Worker Linux UID**. The private signing key is root-only and **must never be available to an Agent or a mutable repo checkout**.

Install the reviewed signer as a root-owned, non-group/world-writable file outside Git, for example `/usr/local/sbin/lora-harness-approve`. Its Python runtime and `cryptography` package must also be **root-owned**, not the model-user virtualenv. It refuses to run from a writable checkout, without root, or without an interactive operator TTY. It uses fixed trusted `git` and `gh` read-only queries; root must be provisioned separate read-only GitHub Issue access. Never give the model passwordless sudo or import source modules from a writable checkout into the privileged signer.

After independent setup and operator review, use a real TTY to invoke the installed signer with `init` once and `approve --issue N --source /trusted/repo` for an individual Issue. The signer displays the Issue/source SHA and allowed paths and requires the exact displayed confirmation phrase. The Agent cannot call this signer through MCP. Each valid grant is consumed once under an external Host lock **before** local journal/worktree mutation; a failed preparation is NOT automatically retried. The Host CLI now separately requires `--expected-issue-sha256` and re-reads Issue scope/body just before creating its local journal.

**Atomicity limitation:** GitHub's remote Issue API and local SQLite/Git do not have a shared atomic transaction. Host revalidation minimizes stale-issue windows, but a remote edit immediately after the final read cannot be prevented; downstream gates require renewed approval on drift. Do not claim distributed atomicity or cryptographic OS isolation when Worker shares the Host UID.

## Docker lifecycle, build proof and recovery

`mcp_docker.py` uses a pinned image digest, fixed ESP-IDF targets, a **disposable copy** of approved firmware source, unique run/app Docker labels and `--cidfile`. Docker flags include `--pull=never`, `--network=none`, `--read-only`, `--cap-drop=ALL`, `--security-opt=no-new-privileges`, nonroot UID and memory/CPU/PID bounds. No candidate working tree, credentials or Docker socket is handed to the native Worker through MCP.

The Host subprocess wrapper bounds combined stdout/stderr **during execution** and kills/reaps its POSIX process group on error/timeout. Because Docker containers are daemon-owned, the lifecycle supervisor independently queries containers by its unique label, removes active IDs, checks known container IDs are gone and returns BLOCKED when daemon cleanup is unavailable, CID is malformed, no actual container was observed, build exit is nonzero or candidate SHA changed. `CHECKS_VERIFIED` now requires valid build log hashes **and verified Docker cleanup receipts**.

A process group is not an OS sandbox, and Docker daemon privileges remain sensitive. This must be tested on an isolated trusted WSL2 Host before execution is enabled. HIL/RF/TDMA timing remain NOT_VERIFIED. The current fixed suite verifies Harness/ESP-IDF layers only; backend/contracts/client task scopes require additional approved test gates.

External evidence is private and SHA-checked. Operations acquire a Host lock, create an `operation.json` marker before side effects and retain markers/partial evidence on crash; no automatic retry, rollback or silent repair. A schema-valid Auditor report does not prove that a native Auditor was actually invoked. Native subagent invocation records and an independent reviewer are required before claiming independent audit; final `AWAIT_HUMAN` always requires operator inspection.

## New acceptance tests and status

- `test_mcp_approval.py`: authentic/tampered/expired/wrong-scope Ed25519 approvals, private file modes and symlinks.
- `test_mcp_docker.py`: fixed Docker argv, restricted mount, leaked container, client crash, timeout, invalid CID and daemon outage.
- `test_mcp_execution.py`: one-time signed grant consumption, stale Issue SHA checked **before** journal/worktree side effects, evidence/scope/process failure paths.
- Run on updated branch via the operator's `~/.venvs/lora-mcp/bin/python -m unittest discover -s tests/agent_harness -v`; then `python -m compileall -q scripts/agent_harness tests/agent_harness`, `python scripts/verify_structure.py` and `git diff --check`.

**New code tests are NOT_VERIFIED**, since the assistant cannot execute the user's private worktree or Docker daemon. Earlier Codex 164/164 regressions and 46/46 MCP tests apply only to the earlier commit, not this new implementation. Native Codex/AGY execution, supervised E2E, HIL and RF remain NOT_VERIFIED. This remains a stacked Draft PR; do not merge/activate until independent review and local test evidence.


