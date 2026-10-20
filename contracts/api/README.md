# Backend ↔ Web/Mobile contracts

**Draft for owner review; no API/WebSocket production implementation.**

- [OpenAPI REST](openapi.yaml): `/api/v1` status, nodes, paginated telemetry/alerts, schedule generation+read state, alert acknowledge, queued commands, admin audit, provisional login; `/healthz` is liveness, not RF readiness.
- [WebSocket design](websocket.md), [event JSON Schema](schemas/realtime-event.schema.json) and [mock fixtures](examples/realtime-cases.json).
- OpenAPI `x-roles` lists authorization roles; Backend **must** enforce roles and resource ownership. Common 401/403/404/409/422 errors modeled by Error body. 202 means **accepted for processing**, not radio success.
- Current auth scheme JWT bearer and login are **proposals**, not approved token issuance, refresh, cookie/WS-ticket or MFA design. Do not expose bearer in URL.
- API numeric primary keys transmitted as **decimal strings** to avoid JS 53-bit integer precision loss. MQTT raw integers remain raw; sensor calibration units are not invented.
- Client can start with mocks, but completed code and field mappings to PostgreSQL require separate authorized Issue/PR and producer/consumer review.

All examples are synthetic. Test with `python3 contracts/tests/check_contracts.py` (dependencies documented in `contracts/verification.md`).
