# Firmware AI Harness — repository entry point

> Status: P0 Issue #30 remains DRAFT. For the single **operator-supervised Issue #47 pilot**, the active choice is **Gemini Worker + Gemini Auditor through two separate direct Antigravity CLI sessions**. No unattended AGY Harness integration is authorized.

Read `.github/copilot-instructions.md`, `.github/instructions/embedded.instructions.md`, `docs/architecture/system-overview.md`, `docs/verification/acceptance-gates.md`, and `docs/development/agent-harness-firmware.md` before firmware tasks.

## Architecture and authority
- ESP32 + SX1276, ESP-IDF/FreeRTOS, pure C; custom LoRa **P2P**, not LoRaWAN. Gateway executes real-time hybrid TDMA locally; Go backend plans/version-controls schedules.
- Approved requirements/ADRs and versioned `contracts/` outrank Agent output. Semtech datasheet (correct revision) governs register semantics. Human verification governs real RF/HIL/timing claims.
- Current repository firmware is a **scaffold**. Never claim imported SX1276 driver, tested RF or TDMA implementation exists.
- Experimental driver from `khanhpn308/esp32e_sx1768-915Mhz` is reference only. Do not copy code or modify wire protocol without a separate scoped Issue and review.
- DO NOT change PCB pin mapping, RF band/power, cryptographic fields, MAC frame layout, MQTT/API/DB contracts, firmware target version, or branch settings on an Agent's initiative.
- **Approved toolchain baseline: ESP-IDF `v6.1` (ADR-0003, owner 2026-10-22)**. Read `firmware/esp-idf-version.txt`; Gateway/Node CI and Harness must use exactly this release. Do not silently downgrade, use floating `release-v6.1`, or treat a build as HIL/RF evidence.

## Roles and execution order
1. **Host Coordinator (deterministic):** Issue/scope validation, clean branch/worktree, bounded process timeouts, compiler/test logs, diff checks, evidence manifest, human stop gates.
2. **Worker (Issue #47: Gemini via operator-direct `agy` CLI):** creates only the Issue-approved harmless README change in a controlled branch under human-supervised permissions. Cannot certify its own code. The Codex Worker and adapters in P0/P1 historical draft are legacy and NOT the Worker for this pilot.
3. **Auditor (fresh operator-direct Antigravity `agy` Gemini session):** review immutable, read-only snapshot without sharing the Worker's conversation or writable working tree. No edits/tools granted. Return PASS/FAIL/INCONCLUSIVE with file:line findings and gaps. Sessions differ, but Gemini Worker and Auditor are **not model/provider-independent**.
4. **Human engineer:** RF/hardware/ISR/timer/security/contract decisions, HIL measurement approval, PR review and merge.

The Host, never an Agent's text or exit code alone, decides whether a gate passed. `agy` must return `status=SUCCESS`, schema-valid `structured_output` and complete exact `reviewed_scope`. AGY's read-only instruction is NOT a security boundary; a disposable environment is required for unattended execution. Flow: Issue -> isolated branch -> Worker -> scope gate -> deterministic tests/build -> independent Auditor -> evidence -> DRAFT PR -> human review. A failed or unavailable gate is NOT_VERIFIED/FAIL and blocks acceptance.

## Stop conditions
- Changed file outside approved Issue `Target Directories (allowed paths)`, secrets, external symlink, untrusted tool configuration, unauthorized radio command, unapproved version/contract change.
- `main` branch, dirty worktree before run, missing toolchain or test logs, unbounded retries, model/tool failure, unsupported hardware assumptions.
- Never auto-merge, auto-flash, auto-transmit RF, or bypass branch protections. Do not run Agent with host-global credentials or unreviewed shell permissions.

## Verification semantics
`CODE_WRITTEN` / `BUILD_VERIFIED` / `AUDIT_PASS` / `SIMULATION_VERIFIED` / `HIL_VERIFIED` / `RF_VERIFIED` are **independent evidence dimensions**. Missing proof is `NOT_VERIFIED`. Build or audit never implies hardware RF PASS.

See historical P0 workflow: [Firmware Agent Harness](docs/development/agent-harness-firmware.md). **Current supervised pilot instructions:** [Dual AGY Pilot](docs/development/agy-supervised-pilot.md).


## Integration guard — Issue #54

On `main`, the selected user-facing supervised model is **Gemini Worker via
operator-direct official `agy`** and a separate **Gemini Auditor via a fresh
operator-direct `agy`** context. This is **not** the legacy P0
`scripts/agent_harness/run.py --execute` pipeline, which still runs Codex
Worker and is NOT approved for the dual-AGY workflow. The selected P1-B2
`p1/pilot.py` is a **fake/simulated** deterministic coordinator, not a
live provider adapter. Neither component may be passed off as autonomous
Gemini-to-Gemini Harness execution. Consumer AGY credentials must never
be embedded into a third-party autonomous Harness. H01/H02/H04 are
NOT_VERIFIED. See `docs/development/agy-supervised-pilot.md` for the
historical Issue #47 operator-only runbook.
