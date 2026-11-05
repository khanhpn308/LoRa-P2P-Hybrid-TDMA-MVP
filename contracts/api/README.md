# Backend ↔ Web/Mobile API & WSS contracts

**Issue #15 revision: DRAFT / requires Backend + Web/Mobile + Security review. Not implemented.** OpenAPI version `1.0.0-draft`; WSS envelope `1.0-draft`. Never infer G4 integration PASS from schema or CI syntax.

- [OpenAPI REST](openapi.yaml) — **14** operations (11 previous + 3 PROPOSED extensions: human schedule review, activation request, command ticket polling); `/healthz` is process liveness only. Commands / activation requests require an `X-Idempotency-Key` in this proposed revision (breaking vs older examples; cross-team approval mandatory). No client directly connects to MQTT/PostgreSQL.
- [WSS semantics](websocket.md) and [machine schema](schemas/realtime-event.schema.json) — server→client best effort, 4 legacy event types + **proposed** `COMMAND_STATE_CHANGED`, no durable replay. See [REST/WSS contract invariants](contract-semantics.md).
- [WSS examples](examples/realtime-cases.json), [REST examples](examples/rest-cases.json), [behavioral tests](../../tests/contract/test_api_contract.py) — synthetic conformance cases, not live client or RF evidence.
- Server `x-roles` **and object-level authorization** required; 401/403 must be distinguished. HTTP 202 means accepted for processing, not Gateway/Node execution. `STAGED` is not `ACTIVE`.
- D13 (JWT issuance/refresh, cookie/WS ticket auth, revocation) remains **BLOCKED_SECURITY/TBD**. Dev-only mocks are never credentials for production.
- All 64-bit numeric IDs are decimal strings in JSON. MQTT `event_id` uses `gateway_id:gateway_epoch(UUID):event_seq`; server WSS envelope event ID is separate. RF timing/airtime/legal decisions remain independent `NOT_VERIFIED`.
- Breaking/extension changes require review of Backend, React and Flutter client use-cases, schema bump/compatibility assessment and test evidence **before** merge.

Local validation (requires installed `jsonschema`, `PyYAML`, `openapi-spec-validator` as declared in `contracts/tests/requirements.txt`): `python3 -m unittest discover -s tests/contract -p 'test_*.py' -v`. CI's existing `ci-contracts.yml` is syntax-only; it does **not** run these tests.
