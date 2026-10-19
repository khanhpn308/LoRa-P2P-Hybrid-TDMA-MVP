# Release gates and required evidence

Evidence includes issue ID, commit or firmware hash, board revision, ESP-IDF/toolchain version, test configuration, logs, timestamp, test owner, criterion and disposition. Never label a result PASS based on AI prediction.

| Gate | Purpose | Evidence |
|---|---|---|
| G0 | Baseline scope, responsibilities and RTM | Approved requirements + ADRs |
| G1 | Hardware/RF/airtime feasibility | RF regulatory assessment, ToA calculations and actual measurements |
| G2 | Versioned custom MAC and TDMA protocol | Bit/byte layouts, failure states, security plan, vectors |
| G3 | Embedded bring-up and autonomous gateway | Hardware test reports, timing and restart logs |
| G4 | Backend and client integration | MQTT dedup, API authorization, migration/restore, E2E |
| G5 | Security/reliability | Threat model, replay/nonce checks, fault injection, soak tests |
| G6 | Pilot acceptance | Field measurements, latency distributions, decision record |

Permitted status: PASS, PARTIAL_WITH_FINDINGS, FAIL, NOT_VERIFIED. No automatic promotion on code-only check for RF, security or HIL gates.

Use `docs/verification/` for small measurement reports and GitHub Actions artifacts or controlled lab storage for large traces.
