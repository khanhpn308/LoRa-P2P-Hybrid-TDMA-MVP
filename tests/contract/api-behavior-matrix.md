# Issue #15 — Behavioral/negative test matrix (NOT RUN)

**Contract draft:** `feature/15-api-wss-contract-spec`. These cases are **acceptance targets**, not evidence of a live Backend/Web/Flutter implementation. The schema fixture tests in `test_api_contract.py` do not execute WSS handshake, RBAC middleware, MQTT, RF or the DB.

| ID | Method / scenario | Expected | Status |
|---|---|---|---|
| AUTH-01 | Missing Bearer to private REST endpoint | HTTP 401 + `WWW-Authenticate` + Error body; no information disclosure | NOT_RUN |
| AUTH-02 | Valid VIEWER calls schedule review/activation or command POST | HTTP 403; no side effect | NOT_RUN |
| AUTH-03 | Operator queries a Gateway not owned/visible to principal | Reject (403 or existence-hiding 404 per approved policy); no cross-tenant leak | NOT_RUN |
| REST-01 | POST commands with same idempotency key + identical canonical payload twice | Same persisted `command_id`; no duplicate enqueue | NOT_RUN |
| REST-02 | Same key reused with changed payload | HTTP 409, no new command | NOT_RUN |
| REST-03 | Review APPROVE; activation request returns 202 | Remains non-ACTIVE until matching ACTIVE_REPORT; rejects mismatched version | NOT_RUN |
| REST-04 | Gateway reports STAGE_ACK then delayed ACTIVE_REPORT | STAGED first, ACTIVE only on validated activation report | NOT_RUN |
| REST-05 | Client sends invalid idempotency header, unexpected JSON, expired command | 400/422 as spec/semantic policy; no mutation | NOT_RUN |
| WS-01 | Browser Origin not allowlisted or auth missing | Reject handshake before HTTP 101 | NOT_RUN |
| WS-02 | Authenticated VIEWER subscribes/accesses unauthorized Gateway event | No event leak, log security finding | NOT_RUN |
| WS-03 | Client tries WSS mutation event | Rejected; no schedule/command effect | NOT_RUN |
| WS-04 | Reconnect while REST snapshot delayed and live events arriving | Bounded live buffer, apply baseline then reconcile; no stale overwrite | NOT_RUN |
| WS-05 | Outbound/inbound queue overflow | Bounded disconnect/STALE and REST resync; no unbounded RAM growth | NOT_RUN |
| WS-06 | Duplicate/reordered COMMAND_STATE_CHANGED | Highest persisted state_revision wins; no rollback | NOT_RUN |
| WS-07 | Disconnect and client passes `cursor` | No implied event replay; REST snapshot required | NOT_RUN |
| CHAN-01 | Concurrent requests for distinct available channels | Both granted with distinct `allocation_generation` >= 1; 201 Created | NOT_RUN |
| CHAN-02 | Two Gateways request the same channel concurrently | First wins (201 Created); second receives 409 Conflict; no dual assignment | NOT_RUN |
| CHAN-03 | Gateway requests second channel when already holding one | HTTP 409 Conflict; Gateway holds at most one channel in MVP | NOT_RUN |
| CHAN-04 | VIEWER calls channel request or release endpoint | HTTP 403 Forbidden; RBAC violation prevented | NOT_RUN |
| CHAN-05 | Release channel while Gateway schedule is ACTIVE (force=false) | HTTP 409 Conflict; release blocked until schedule deactivated | NOT_RUN |
| CHAN-06 | Release channel when schedule is idle or with force=true | HTTP 200 OK, status=RELEASED, Gateway reassignment unlocked | NOT_RUN |
| CHAN-07 | Non-ADMIN queries `GET /api/v1/channels` | Returns all channels; `assigned_gateway_id` redacted for foreign Gateways | NOT_RUN |
| EVENT-01 | Client queries deprecated `GET /api/v1/nodes/{id}/telemetry` | Deprecation header/flag present; historical logs returned; no active stream | NOT_RUN |
| EVENT-02 | V2 node triggers local alarm; sends `UP_EVENT 0x41` | Gateway persists WAL before same-slot `DOWN_EVENT_ACK 0x42`; publishes `uplink/alert` | NOT_RUN |
| EVENT-03 | MQTT QoS 1 duplicate delivery to Backend | Deduplicated via `UNIQUE(gateway_id, event_id)` in PostgreSQL; exactly-once DB state | NOT_RUN |
| EVENT-04 | Operator calls `POST /api/v1/alerts/{id}/acknowledge` | UI state updated to acknowledged; no RF downlink packet generated | NOT_RUN |
| SECURITY-01 | Production browser WSS authentication D13 unresolved | No production auth-enabled claim or unsafe fallback before signed ADR | BLOCKED_SECURITY |

## Actual verification evidence required

Record environment, timestamp, Python/OpenAPI/jsonschema versions, commit SHA, test invocation, stdout/stderr, expected vs actual and reviewer. No manual or GitHub CI "syntax PASS" stands in for these behavioral tests. Any extension to `.github/workflows/` requires separate Issue scope approval.
