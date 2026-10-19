# Requirements Traceability Matrix — initial draft

Each requirement needs Issue, design owner, test method, measured evidence and decision (PASS/PARTIAL/FAIL/NOT_VERIFIED).

| ID | Requirement | Owner | Verification | Status |
|---|---|---|---|---|
| RF-001 | TX frequency/ERP/emissions/duty limitations meet applicable VN requirements | RF | Qualified RF tests + regulatory assessment | NOT_VERIFIED |
| MAC-001 | TDMA slots do not overlap in validated nominal operation | Gateway + Node | HIL two-to-fifteen node timestamp traces | NOT_VERIFIED |
| MAC-002 | Lost beacon/old schedule disables unsafe periodic TX | Node | Fault injection HIL | NOT_VERIFIED |
| SYS-001 | Gateway can operate locally without MQTT/Backend | Gateway | Disconnect, restart, bounded buffer tests | NOT_VERIFIED |
| ALERT-001 | Evaluate RF alarm delivery latency and contention percentiles | RF + Gateway | Repeatable experiments P50/P95/P99 | NOT_VERIFIED |
| DATA-001 | MQTT redelivery must not create duplicate events | Backend | QoS 1 replay test | NOT_VERIFIED |
| SEC-001 | RF frames authenticate control and prevent replay | Embedded security | Threat model + protocol/HIL tests | NOT_VERIFIED |
| SEC-002 | TLS, identity, least-privilege ACL and RBAC | Backend | Security integration tests | NOT_VERIFIED |

**Important:** The <3 s alarm goal is a research TARGET, not an SLA. Define exact endpoints (Node detection→GW; Node detection→Backend/Web) and maximum concurrent alerts before any PASS decision. Mobile push cannot be given hard real-time guarantees.
