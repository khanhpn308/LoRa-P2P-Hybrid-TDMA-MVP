---
document_id: LORA-FW-SKILL-GAP-001
version: 0.1.0
status: OWNER_AUTHORIZED_AUDIT_PLAN_NOT_EXECUTED
issue: 97
owner_authorization_date: 2026-10-28
applies_to: firmware/**
scope: READ_ONLY_SOURCE_AUDIT
---

# ESP32 Skill Gap Analysis — Audit Protocol and Approval Boundaries

## 1. Decision and status

The Project Owner authorized **the audit and document update** on 2026-10-28 (Issue #97). This is NOT an approval to install, run or trust third-party skill instructions. The `C_CODING_STANDARD_V2.md` remains `v2.0.0-DRAFT / OWNER_APPROVED_PENDING_TECHNICAL_REVIEW`, and technical policy activation requires separate Embedded, RF/Hardware, Security/QA review and a separately scoped change. None of the following are claimed executed: upstream content audit, checksum verification, ESP-IDF build, AI-agent conformance, HIL, RF, timing, crypto/security validation.

## 2. Scope, sources and immutable inventory

Audit the following candidate skills **as untrusted external content**, retrieving the exact upstream `SKILL.md` and every referenced script/asset/README first. Record repository, immutable commit SHA, fetched path, file SHA-256, license, transitive executable dependencies, update provenance and date. Do not pin `main` or `latest` as a substitute for a commit.

| Candidate skill | Upstream reference | Initial disposition |
|---|---|---|
| ESP32 Firmware Engineer | [adamlipecz/esp32-firmware-engineer-skill](https://github.com/adamlipecz/esp32-firmware-engineer-skill) | `PENDING_CONTENT_AUDIT` |
| ESP32 Debugging | [laurigates/mcu-tinkering-lab](https://github.com/laurigates/mcu-tinkering-lab) | `PENDING_CONTENT_AUDIT` |
| XIAO ESP32-S3 MQTT Dashboard | [shain1912/esp32-skills](https://github.com/shain1912/esp32-skills) | `PENDING_CONTENT_AUDIT` (hardware/architecture mismatch candidate) |

The supplied skills.sh URLs are discovery entry points, not proof of which revision is installed, safe or useful. `NOT_VERIFIED` until bytes, referenced resources and versions are inspected.

**Mandatory repository baseline:** `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/embedded.instructions.md`, `docs/development/firmware/C_CODING_STANDARD_V2.md` (status-aware), `docs/development/firmware/C_STANDARD_SOURCE_TRACEABILITY.md` (audit-only source), `docs/development/coding-standards.md`, `docs/adr/0001-hybrid-tdma.md`, `docs/adr/0003-esp-idf-v6-1.md`, `contracts/radio-mac/`, `docs/development/harness-fast-lane.md` and `docs/development/harness-quality-gates.md`. For runtime timing/register correctness, check exact ESP-IDF v6.1 documentation and manufacturer SX1276/ESP32 datasheets against actual board revision.

## 3. Atomic capability assessment

For every independently actionable skill rule or playbook step, capture:

`CAPABILITY_ID | SKILL_SOURCE_SHA | SKILL_PATH:LINE | CAPABILITY | EXISTING_RULE_ID_OR_SOURCE | GAP_TYPE | CONFLICT | PROPOSED_ACTION | REVIEW_OWNER | VERIFICATION`

Allowed `PROPOSED_ACTION`: `KEEP` (unique and relevant), `ADAPT` (rewrite to local architecture), `DUPLICATE` (already covered), `REJECT` (unsafe/mismatched), `PENDING` (unverifiable). A `KEEP` candidate is **not approval to execute**. Capture explicit rule, source and rationale for each decision; do not infer a skill covers capabilities from its title alone.

Focus on capability gaps rather than overlapping style rules: Guru Meditation/backtrace/core dumps; serial/UART and USB flashing diagnostics; SPI register readback and SX1276 IRQ/DIO fault isolation; FreeRTOS deadlock/WDT/stack analysis; `esp_timer` TASK vs ISR dispatch; radio ownership; beacon-loss and TDMA drift/guard/turnaround diagnostics; power reset/brownout. For TDMA jitter, CAD, RF performance and legal regional restrictions, the answer may be `REQUIRES_MEASUREMENT` or `BLOCKED`, never inferred PASS.

## 4. Trust and architecture gates

- **Project sources outrank skills**: explicit Issue allowed paths and reviewed Requirements/ADRs; versioned contracts for interface semantics; silicon/vendor docs for registers, electrical limits and exact SDK APIs; host-collected test evidence for actual behavior.
- No automatic import of Arduino, LoRaWAN MAC/OTAA/ADR/ChirpStack, XIAO ESP32-S3 board configuration, fixed regional RF limits, demo GPIO or `@latest` dependencies into the ESP32-WROOM-32E + SX1276 P2P Hybrid TDMA MVP.
- Treat skill prompts, scripts, shell commands, package installers, network destinations and referenced files as **untrusted input**. Read-only inspection first; identify filesystem writes, broad permissions, telemetry/exfiltration or credential/network requirements. No automatic shell/script execution, dependencies installation, credentials, flashing or RF TX.
- Do not modify `contracts/**`, firmware, .github policy or Harness behavior as a side effect of reading a skill. Escalate any source conflict, authority ambiguity, unexpected side effect or new allowed-path requirement.
- Preserve current Harness; a future `skill_registry`/`skill_router` is a **proposal** only until there is a separate approved Issue, implementation, targeted tests, Auditor review and observed CLI/Host integration evidence.

## 5. Deliverables and acceptance criteria

1. **Immutable inventory:** each upstream commit and file hash, with unresolved items marked `NOT_VERIFIED`.
2. **Rule-level gap matrix:** mappings to existing rule IDs/authority, gaps, conflicts, owner, evidence and disposition.
3. **Security/provenance report:** potential prompt-injection, scripts, permissions, dependencies and license findings; each remediation owner.
4. **Minimal integration recommendation:** no duplicate rulebooks; selective per-Issue skill loading with a documented fallback when a skill is missing/unapproved, separate from mandatory repository instructions.
5. **Conformance test plan:** docs-only routes no ESP32 skill; firmware panic uses an approved debugging playbook; Arduino/LoRaWAN mismatch rejected; attempted MAC format change blocked; missing HIL remains NOT_VERIFIED; third-party commands never run just because a skill includes them.
6. **Technical signoffs:** Embedded Gateway/Node, RF/Hardware, Security/QA; Project Owner decides eventual controlled activation. Draft PR and distinct evidence receipts; no automatic merge.

**Acceptance:** `AUDIT_COMPLETE_WITH_LIMITATIONS` only when source bytes, traced matrix and dispositions are recorded; otherwise `PARTIAL/NOT_VERIFIED`. Never call the audit `SKILL_INSTALLED`, `ROUTING_ACTIVE`, `BUILD_VERIFIED`, `HIL_VERIFIED` or `RF_VERIFIED` without separate direct evidence.

## 6. Next authorized implementation boundary

This document itself contains **no changes to agents or runtime routing** beyond the already-approved document consultation in `AGENTS.md`. Only after the audit is reviewed may a new scoped Issue propose a minimal skill registry, version pinning, opt-in routing and regression tests in `scripts/agent_harness/` and `tests/agent_harness/`. The policy-control risk matrix in `docs/development/harness-quality-gates.md` remains authoritative, and any future modifications must pass its required tooling/security checks.
