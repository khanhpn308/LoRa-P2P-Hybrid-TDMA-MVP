# Firmware AI Coding Harness — P0 Codex + Antigravity

**Status: DRAFT, Issue #30, PR #31.** This is a controlled software pilot, NOT an unattended production runner and NOT a firmware implementation.

## Architecture and scope

- LoRa **P2P**, ESP32 + SX1276, local Gateway TDMA Master; Go Backend plans schedules. No LoRaWAN assumptions.
- Existing firmware is only a scaffold; experimental driver has not been imported.
- Radio-MAC v1 wire/security remains DRAFT; no production codec, RF limits or radio performance may be approved by Agent output.
- Current firmware CI uses ESP-IDF `release-v5.4`, while the experimental code targeted v6.1. Engineering must approve the version before Issue #10 driver import.
- Keep original acceptance gates G0–G6 in `docs/verification/acceptance-gates.md` separate from host software checks.

## P0 implemented in this PR

1. Python Host preflight reads an OPEN GitHub Issue with an explicit, exact `Target Directories (allowed paths)` list, refuses a dirty worktree and requires an Issue-number feature branch.
2. Codex CLI acts as the Worker in `workspace-write` mode. The Host, not Worker text, validates all changes; file scope, symlink changes and binary or oversized diffs are rejected.
3. Deterministic Host checks run structure tests, Python harness unit tests and BOTH ESP-IDF app builds. Host records command exit code and output SHA-256/length, but does not store raw logs in the manifest.
4. Antigravity CLI (`agy`) acts as fresh independent Auditor. Host creates a bounded copied snapshot of changed code and relevant reference docs, embeds full review data into the prompt, and uses `--output-format json`, `--json-schema` and `--sandbox`.
5. `exit_code == 0` alone is NOT success. Host requires `status=SUCCESS`, nonmissing `structured_output`, a structurally valid report, zero findings/limitations for PASS, explicit per-changed-file `reviewed_scope`, and no observed permission soft-denial.
6. Host verifies audit snapshot integrity after the model invocation. Up to two OPTIONAL repair rounds are supported; repeated identical diff, timeout, scope violation and audit INCONCLUSIVE stop the job.
7. Each P0 run creates a unique ignored `artifacts/agent-harness/<run-id>/manifest.json`. `BUILD_VERIFIED_LOCAL_UNCOMMITTED_TREE` and `AUDIT_PASS_SOFTWARE_ONLY` never imply real HIL or RF verification.

## Quick checks, no model/token usage

On a clean clone with `chore/30-firmware-agent-harness` checked out:

```bash
python3 -m compileall -q scripts/agent_harness tests/agent_harness
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/agent_harness/run.py --issue 30
```

Last command is PREFLIGHT ONLY. It requires `gh` login and a clean Issue-number branch. It does not call Codex, AGY or ESP-IDF.

## Explicit local pilot only on a disposable isolated runner

**Do not run `--execute` on a credentialed personal WSL2 machine.** Prepare a disposable VM/container and per-Issue worktree, with controlled network, separate authorized provider credentials, no personal home/SSH tokens, no privileged Docker socket, limited CPU/time, and external host-owned evidence/approval.

After Issue scope and board pinout are approved and a matching ESP-IDF toolchain version is recorded in an ADR, run from the isolated Issue branch:

```bash
python3 scripts/agent_harness/run.py --issue 10 --execute \
  --accept-isolated-pilot \
  --expected-idf-version '<engineering-approved idf.py --version substring>' \
  --max-repairs 1
```

The flag `--accept-isolated-pilot` is ONLY an acknowledgment, not isolation or enforcement. The runner cannot attest Docker/VM isolation. Codex and AGY internal sandbox flags also do not replace a strong external boundary. The host does not commit, push, merge, open PRs, flash ESP32, transmit RF or approve HIL in P0.

## What remains to implement (P1 and later)

- Real provisioned **isolated per-Issue Git Worktree**, filesystem/network/identity boundaries and least-privilege short-lived GitHub publisher.
- Durable SQLite checkpoints, recovery after process/WSL crash, process-tree cleanup, resource budgets and verified tool versions.
- Full immutable logs with secret redaction, static analysis, code-coverage policy, CI evidence bound to a final commit SHA, security scanning and automatic Draft PR.
- Model-agnostic routing for `agy` Worker / Codex Auditor; quota/rate-limit tracking under provider authorization.
- Lab-controlled HIL/logic-analyzer/RF testing with real board metadata and human technical sign-off.

**P0 evidence scope:** Pure-Python tests and GitHub Actions validate the harness software. Live Codex/AGY credentials, unattended sandbox security, firmware build, RF/TDMA and HIL are **NOT_VERIFIED** until separately measured.

## Official CLI guidance

- https://antigravity.google/docs/cli/headless/
- https://developers.openai.com/cookbook/examples/codex/build_iterative_repair_loops_with_codex
- https://developers.openai.com/blog/codex-as-a-platform
