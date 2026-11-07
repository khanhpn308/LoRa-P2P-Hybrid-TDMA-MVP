# Contract tests — LoRa P2P Hybrid TDMA MVP

**Version:** `0.2.0-draft` · **Issue #128 / Umbrella #125 Alignment:** V2 Event-Only, Static TDMA & VN920 Channel Allocation.

## 1. Test Execution

Dependencies: `python3 -m pip install -r contracts/tests/requirements.txt` (includes `jsonschema`, `PyYAML`, `openapi-spec-validator`, `pytest`).

- **Contract Schema & Spec Validator:**
  ```bash
  python3 contracts/tests/check_contracts.py
  ```
  Validates:
  - 10 JSON Schemas under Draft 2020-12 with `FormatChecker`.
  - 28 MQTT cases (including V2 static geometry, diagnostic fields, invalid channel).
  - 18 WebSocket cases (including `ALERT_TRIGGERED`, `COMMAND_STATE_CHANGED`).
  - OpenAPI 3.0.3 spec: 18 operations, `x-roles` enforcement, `401/403` error definitions.
  - Schedule semantic validator: `V2-VN920-STATIC-15N` (W500/G50, 15 slots 9000ms) and candidate `P-10S-15`.

- **Python Unit Test Suite:**
  ```bash
  python3 -m unittest discover -s tests/contract -v
  # or
  python3 -m pytest tests/contract -v
  ```
  Suites:
  - `test_api_contract.py`: REST OpenAPI operations, protected roles, idempotency headers, REST component schemas, telemetry deprecation.
  - `test_mqtt_session_key_contract.py`: Session key install/ACK envelopes, AAD encoding, clock boundaries (SK-01..SK-15).
  - `test_radio_mac_timing_consistency.py`: TDMA timing consistency and mathematical bounds across SF7/SF8.

## 2. Behavioral Matrix

Synthetic conformance cases and negative scenarios are defined in [api-behavior-matrix.md](api-behavior-matrix.md), including:
- `AUTH-01..AUTH-03`: RBAC and tenant isolation.
- `REST-01..REST-05`: Idempotency, schedule staging/activation state transitions.
- `CHAN-01..CHAN-07`: Exclusive VN920 channel allocation, conflict resolution, active schedule release guard.
- `EVENT-01..EVENT-04`: Event-Only durable WAL commit before RF ACK, MQTT QoS 1 dedup, UI ACK separation.
- `WS-01..WS-07`: WebSocket origin, authentication, resync and revision rollback prevention.
