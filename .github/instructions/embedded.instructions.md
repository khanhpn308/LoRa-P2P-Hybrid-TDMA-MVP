---
applyTo: "firmware/**"
---
# Embedded / ESP-IDF rules

Target ESP32 + SX1276, C, ESP-IDF, FreeRTOS. **Single radio owner** serializes SPI and modem state. No blocking operations or SPI in ISR. Timer/IRQ handlers timestamp then notify a bounded task or queue. Prove priorities and jitter on device; do not promise microsecond timing from source inspection alone.

Prefer static buffers, fixed-sized queues and clear ownership; avoid repeated malloc/free in steady-state. Include capacity, timeout and overflow handling. Driver, Radio MAC, Gateway TDMA executor and Node TDMA client stay separate. Never bypass local airtime limits or transmit arbitrary RF frames without verified allowed configuration.

CRC is not cryptographic authentication. Reject unversioned/unvalidated schedule and radio commands. Test actual TX/RX state transitions on hardware.

## Agent-first C standard v2 — consultation (technical activation pending)

For a scoped firmware Issue, AI Workers and Auditors MUST read and assess the applicable sections/Rule IDs of [`C_CODING_STANDARD_V2.md`](../../docs/development/firmware/C_CODING_STANDARD_V2.md), as routed by `AGENTS.md`; report consulted IDs, approval status, blocked decisions and required evidence. **Project Owner approved advancing the v2 DRAFT on 2026-10-28 (Issue #97), but domain technical reviews and policy enforcement activation are PENDING.** Draft-only rules do not override this file, `AGENTS.md`, approved ADRs or versioned contracts. Do not apply draft-only rules as mandatory without a separately reviewed activation change; never infer RF/HIL/security PASS from the rulebook. Third-party ESP32 skills are read-only audit candidates under the [gap-analysis plan](../../docs/development/firmware/ESP32_SKILL_GAP_ANALYSIS_PLAN.md), not installed/activated by this approval.
