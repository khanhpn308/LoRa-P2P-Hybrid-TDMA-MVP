# Backend ↔ Web/Mobile API & WSS contracts

**Issue #128 revision: DRAFT / V2 Event-Only & VN920 Channel Migration (Refs #15, #125, #154).** OpenAPI version `1.0.0-draft`; WSS envelope `1.0-draft`. Never infer G4 integration PASS from schema or CI syntax.

- [OpenAPI REST](openapi.yaml) — **18** operations (14 baseline + 4 VN920_V1 channel allocation endpoints: list channels, request exclusive channel, read assignment, release channel). `/healthz` is process liveness only. `/api/v1/nodes/{node_id}/telemetry` is marked `deprecated: true` (historical decode only; live nodes emit discrete events under `/api/v1/alerts`). Commands, activation requests, and channel allocation requests require an `X-Idempotency-Key`. No client directly connects to MQTT/PostgreSQL.
- [WSS semantics](websocket.md) and [machine schema](schemas/realtime-event.schema.json) — server→client best effort; `TELEMETRY_UPDATE` is legacy/playback; `ALERT_TRIGGERED` is the active Event-Only live carrier; `COMMAND_STATE_CHANGED` tracks asynchronous execution; no durable replay. See [REST/WSS contract invariants](contract-semantics.md).
- [WSS examples](examples/realtime-cases.json), [REST examples](examples/rest-cases.json), [behavioral tests](../../tests/contract/test_api_contract.py) — synthetic conformance cases, not live client or RF evidence.
- Server `x-roles` **and object-level authorization** required; 401/403 must be distinguished. HTTP 202 means accepted for processing, not Gateway/Node execution. `STAGED` is not `ACTIVE`.
- VN920_V1 channel allocation: Gateway holds at most one exclusive channel in CH00–CH10. Strict state sequence: `CHANNEL_ALLOCATED` $\to$ `SCHEDULE_STAGED` $\to$ `SCHEDULE_ACTIVE` $\to$ `RF_AUTHORIZED`. Channel release is blocked (409) if schedule is `ACTIVE`.
- Four confirmation layers remain strictly separate: RF ACK != MQTT PUBACK != DB Commit != UI Acknowledgement.
- D13 (JWT issuance/refresh, cookie/WS ticket auth, revocation) remains **BLOCKED_SECURITY/TBD**. Dev-only mocks are never credentials for production.
- All 64-bit numeric IDs are decimal strings in JSON. MQTT `event_id` uses `gateway_id:gateway_epoch(UUID):event_seq`; server WSS envelope event ID is separate. RF timing/airtime/legal decisions remain independent `NOT_VERIFIED`.
- Breaking/extension changes require review of Backend, React and Flutter client use-cases, schema bump/compatibility assessment and test evidence **before** merge.

Local validation (requires installed `jsonschema`, `PyYAML`, `openapi-spec-validator` as declared in `contracts/tests/requirements.txt`): `python3 -m unittest discover -s tests/contract -p 'test_*.py' -v`. CI's existing `ci-contracts.yml` is syntax-only; it does **not** run these tests.
