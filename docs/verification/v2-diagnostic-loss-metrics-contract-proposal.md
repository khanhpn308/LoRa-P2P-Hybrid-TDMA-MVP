# V2 Diagnostic Loss Metrics — `UP_DIAG_METRICS 0x4A` (23B)

**Document ID:** DOC-VERIF-V2-DIAG-METRICS-001  
**Status:** OWNER_APPROVED_MVP_WIRE_DESIGN (2026-11-07) · IMPLEMENTATION_NOT_VERIFIED · G2_NOT_VERIFIED  
**Authority:** [Issue #204](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/204), [Issue #208](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/208), DEC-MH-08, DEC-127-04  
**Contract coordination:** #127 (Radio MAC), #128 (MQTT/API), #131 (Firmware), #18/#132 (Backend), #130 (Simulation), #169 (LAB HIL).  
**Change:** Supersedes earlier 26B/29B/33B diagnostic candidates and previous `MAINT_SEQ/DIAG_FLAGS/BATTERY_MV` candidate payload. Those older proposals remain only in Git history and must NOT be implemented as current V2.

## 1. Purpose and invariant

A Node with a full persistent Event queue applies `RING_BUFFER_DROP_OLDEST`, stores an increasing cumulative count of overwritten Events, and reports that count independently from the unchanged health message.

- `UP_HEALTH_REPLY 0x44` stays exactly **21B**. Its `PENDING_COUNT` is current pending queue depth, **not** cumulative loss.
- Diagnostic is an authenticated **management** record; it is **not** sensor telemetry, an Event, or a replacement for immediate `DOWN_EVENT_ACK 0x42`.
- Join is separately allowed at any time by CAD/backoff; diagnostic transmission **is not** asynchronous CAD access.
- The Owner explicitly approved **0x4A and 23B** on 2026-11-07. Implementation may start without waiting for full RF/HIL sign-off, while test status must remain truthful.

## 2. Owner-approved on-air frame

**Exactly 23 octets**: 7B V2 header (AAD) + 8B AES-128-CCM ciphertext + 8B authentication tag. Multi-byte integers are **big-endian**.

| Byte offset | Field | Bytes | Cryptographic handling | Semantics |
| --- | --- | ---: | --- | --- |
| 0 | `VER_TYPE=0x4A` | 1 | AAD | V2 `UP_DIAG_METRICS` |
| 1 | `NODE_ID` | 1 | AAD | Gateway-local Node identity |
| 2 | `SESSION_SEL` | 1 | AAD | Authorized uplink session selector |
| 3–6 | `FRAME_COUNTER` | 4 | AAD | u32 BE, monotonic nonce/replay sequence |
| 7–10 | `DROPPED_EVENT_COUNT` | 4 | Encrypted | u32 BE, durable cumulative FIFO-overwrite count |
| 11–14 | `DIAG_SEQ` | 4 | Encrypted | u32 BE, durable monotonic diagnostic report ID |
| 15–22 | `CCM_TAG` | 8 | Authentication tag | AES-128-CCM-8 |
| **Total** | | **23** | | |

Encryption key: `K_SESSION_UP` (Node↔Gateway, unknown to Backend). 13B nonce as in V2:

```text
NONCE = SESSION_NONCE_PREFIX[8B] || 0x01 (UP) || FRAME_COUNTER[4B]
AAD   = VER_TYPE || NODE_ID || SESSION_SEL || FRAME_COUNTER
```

**One unified uplink `FRAME_COUNTER` namespace** is required for packet types 0x41 Event, 0x44 Health, and 0x4A Diagnostic under the same key/session; no nonce reuse across types, retries or reboot. For an exact retransmission of the *same* report, retransmit the **same cached wire bytes** or use a genuinely fresh monotonic frame counter for a new encryption, never reuse `(key, nonce)` with changed plaintext.

**Counters:** `DROPPED_EVENT_COUNT` increases only when an Event is actually overwritten/dropped by the approved queue overflow policy. `DIAG_SEQ` identifies report occurrences for idempotent ingest; it must not silently reset after power loss/rejoin. Overflow, NVS corruption, reinstall/device-generation changes and atomic persistence are implementation/recovery specifications, not claims of test PASS.

## 3. Access scheduling / receive and ingest

- The Node transmits `UP_DIAG_METRICS` only in an **explicitly scheduled/authorized Normal Maintenance management opportunity**, when the value changes or upon authenticated request. **Do not** insert into DATA Event/ACK slots and **do not** transmit during `SCHEDULE_MIGRATION`.
- Exact timing of Management opportunity, downlink request/receipt, retry limits and how it coexists with Beacon/Health remain **implementation details to version and test**. This is **not** a permission to autonomously TX diagnostics outside assigned opportunities.
- Gateway authenticates CCM, validates `NODE_ID/SESSION_SEL/FRAME_COUNTER`, durably processes diagnostics and forwards mapped values with Gateway identity to Backend. Backend performs **idempotent** storage keyed by device generation and report sequence (and network/Gateway/Node identity); duplicate/out-of-order reports cannot decrease the persisted cumulative dropped count.
- An RF diagnostic receipt (if later designed) is separate from Event ACK; neither MQTT QoS1 PUBACK nor Backend PostgreSQL COMMIT is an RF Event ACK. No additional on-air diagnostic ACK codepoint is approved here.

## 4. Cross-component contract impact

| Producer / Consumer | Requirement |
| --- | --- |
| Node firmware `#131` | Persistent drop counter, `DIAG_SEQ`, per-session shared uplink counter, CCM8 packer and bounded management TX |
| Gateway MAC `#127` | 0x4A receive/parser, AES-CCM8 authentication, duplicate/replay behavior, durable acceptance and forwarding |
| MQTT/API `#128` | Versioned diagnostic record schema with unambiguous `dropped_event_count`, `diag_seq`, Node identity and device generation |
| Backend `#18/#132` | Idempotent ingest/store; no inference of dropped count from Health `PENDING_COUNT` |
| Simulation `#130` | Golden vectors, malformed packets, replay, wrong session, power loss, contention, timeout and sequence rollover |

**Timing baseline from #208:** 500ms usable DATA + 50ms leading/trailing guards, 400ms usable schedule READY + 50ms guards, Maintenance recurrence ~300s. Those values are Owner-approved *MVP configuration*, **not** measurements proving RF timing or legal compliance. Diagnostic uses separately scheduled Management airtime, not those 500/400ms event/READY windows.

## 5. Minimum implementation/test checklist

- [ ] Decode/encode `0x4A` exact 23B and validate byte-order; wrong length/codepoint/CCM tag rejected.
- [ ] Verify shared UP counter nonce uniqueness across Event/Health/Diagnostic, reboot/power-loss and retries.
- [ ] NVS power-loss/reboot unit tests for cumulative drop count and `DIAG_SEQ` high-water.
- [ ] Verify duplicate diagnostic RF/MQTT messages do not double count or create decreasing totals.
- [ ] Test no transmission during DATA Event, Join TX, Schedule Migration or other occupied single-radio windows.
- [ ] Build and run unit/contract tests, Go↔ESP-IDF vector parity, then bench HIL when available; **do not** label HIL PASS without evidence.

## 6. Change-control and status

This PR owns **this design document only**. Implementation of `contracts/radio-mac/**`, `firmware/**`, `backend-go/**`, `contracts/mqtt/**` or tests belongs in separate reviewed issue-specific PRs. Owner requested direct PR remediation/merge on 2026-11-07 and waived the G0/Auditor requirement for this operation. Report those gates as **OWNER_WAIVED**, not PASS. This document's merge is not proof that an executable 0x4A implementation exists.

**Status:** `OWNER_APPROVED_MVP_WIRE_DESIGN / DOC_UPDATED / PRODUCTION_IMPLEMENTATION_NOT_VERIFIED / RF_HIL_NOT_VERIFIED`.
