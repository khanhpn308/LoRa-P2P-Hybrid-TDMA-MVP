# Firmware AI Harness — repository entry point

> Status: DRAFT for Issue #30. This file is instructions, NOT evidence of runtime activation.

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
2. **Worker (Codex in initial pilot):** modifies only paths authorized in the Issue, supplies tests and a change note. Cannot certify its own code.
3. **Auditor (fresh Antigravity `agy` headless session):** read-only review of code/diff against requirements, datasheet, failure paths and coding standards. No editing, no shared Worker conversation. Return PASS/FAIL/INCONCLUSIVE with file:line findings and gaps.
4. **Human engineer:** RF/hardware/ISR/timer/security/contract decisions, HIL measurement approval, PR review and merge.

The Host, never an Agent's text or exit code alone, decides whether a gate passed. `agy` must return `status=SUCCESS`, schema-valid `structured_output` and complete exact `reviewed_scope`. AGY's read-only instruction is NOT a security boundary; a disposable environment is required for unattended execution. Flow: Issue -> isolated branch -> Worker -> scope gate -> deterministic tests/build -> independent Auditor -> evidence -> DRAFT PR -> human review. A failed or unavailable gate is NOT_VERIFIED/FAIL and blocks acceptance.

## Stop conditions
- Changed file outside approved Issue `Target Directories (allowed paths)`, secrets, external symlink, untrusted tool configuration, unauthorized radio command, unapproved version/contract change.
- `main` branch, dirty worktree before run, missing toolchain or test logs, unbounded retries, model/tool failure, unsupported hardware assumptions.
- Never auto-merge, auto-flash, auto-transmit RF, or bypass branch protections. Do not run Agent with host-global credentials or unreviewed shell permissions.

## Verification semantics
`CODE_WRITTEN` / `BUILD_VERIFIED` / `AUDIT_PASS` / `SIMULATION_VERIFIED` / `HIL_VERIFIED` / `RF_VERIFIED` are **independent evidence dimensions**. Missing proof is `NOT_VERIFIED`. Build or audit never implies hardware RF PASS.

See the canonical workflow: [Firmware Agent Harness](docs/development/agent-harness-firmware.md).
