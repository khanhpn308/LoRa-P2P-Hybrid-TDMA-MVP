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
| SECURITY-01 | Production browser WSS authentication D13 unresolved | No production auth-enabled claim or unsafe fallback before signed ADR | BLOCKED_SECURITY |

## Actual verification evidence required

Record environment, timestamp, Python/OpenAPI/jsonschema versions, commit SHA, test invocation, stdout/stderr, expected vs actual and reviewer. No manual or GitHub CI "syntax PASS" stands in for these behavioral tests. Any extension to `.github/workflows/` requires separate Issue scope approval.
