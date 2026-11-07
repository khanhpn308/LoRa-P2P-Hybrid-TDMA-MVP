# Issue #15 / #128 — REST/WSS Contract Invariants (V2 ALIGNED)

**Baseline:** [OpenAPI 3.0.3](openapi.yaml), [WSS](websocket.md) and [WSS JSON Schema](schemas/realtime-event.schema.json). **Status:** `DRAFT/PENDING`; no Go implementation, React integration, Flutter delivery or production security approval. Updated under Issue #128 (Umbrella #125) and VN920_V1 (#154).

## REST / HTTP semantics

- `GET /healthz` is liveness only (not radio or database readiness). All business paths use `/api/v1`. The new endpoints are **proposed additions** and do not retroactively exist in a deployed service.
- `ADMIN` alone may review/propose activation of a schedule and release channels; `OPERATOR` may request channels and post commands; `VIEWER` is read-only. Existing Gateway/Node views require server-side resource-scope checks, not merely `x-roles` field or hidden React buttons. 401 requires `WWW-Authenticate`; 403 means authenticated-but-forbidden; structured `Error` body with `request_id`; logs must redact tokens/secrets.
- `POST /gateways/{gw_id}/schedules/generate` returns 202 only for the queued proposal. `POST /gateways/{gw_id}/schedules/{schedule_id}/review` records APPROVE/REJECT but never activates Gateway. Approved plan stays `PROPOSED` with optional `review_state=APPROVED`; rejected review sets state `REJECTED`. `POST .../activation-requests` (ADMIN only) checks `review_state=APPROVED`, `expected_version`, Gateway identity and no conflicting staged schedule. Its `202` means dispatch intent persisted, **not** SENT/STAGED/ACTIVE. Backend transitions to SENT only on actual publish; STAGED only on valid `STAGE_ACK`; ACTIVE only on correlated `ACTIVE_REPORT` verified at Gateway. Deadline passed before activation leads EXPIRED; a late report needs reconciliation, not blind state reversal. No cloud per-slot radio control.
- Client POST retries: `X-Idempotency-Key` required for commands, schedule activation requests, and channel allocation requests. Scope key to authenticated actor + operation + resource and canonical request fingerprint. Repeat with same fingerprint returns existing 201/202/ticket; reuse with different payload → 409. Key retention, idempotency store transaction and request canonicalization are implementation decisions pending review; never claim hardware exactly-once. `POST /alerts/{id}/acknowledge` must itself be logically idempotent and never become radio-level ACK.
- `POST /nodes/{node_id}/commands` returns `CommandTicket` 202. `GET /nodes/{node_id}/commands/{command_id}` provides subsequent state. `NODE_ACKED` proves no physical actuator state unless RF application-level execution proof was designed. Command expiry, retry and observability remain downstream contracts.
- **Event-Only Migration & Deprecation:** `GET /api/v1/nodes/{node_id}/telemetry` is marked `deprecated: true`. It is maintained strictly for reading historical periodic telemetry logs. Active V2 nodes transmit events upon local threshold violation; live operational events are queried via `GET /api/v1/alerts`.
- **Four Confirmation Layers Distinction:**
  1. `RF ACK`: `DOWN_EVENT_ACK 0x42` (19B) emitted by Gateway in the same DATA slot after local WAL commit.
  2. `MQTT PUBACK`: Mosquitto transport QoS 1 delivery acknowledgment.
  3. `Backend DB Commit`: PostgreSQL commit with deduplication `UNIQUE(gateway_id, event_id)`.
  4. `UI Acknowledgement`: User calls `POST /api/v1/alerts/{alert_id}/acknowledge`. This is purely an operator workflow state transition and **never triggers radio ACK**.
- Validate path/query/body; reject unknown keys, trailing JSON garbage, invalid decimals, stale dates, conflicts. Limit body size and rate, but production limits remain TBD. JWT bearer/login is **PROVISIONAL D13**, not approved production scheme. Tokens must not be accepted from URL query.
- Pagination cursor is opaque and scoped to query filters; use deterministic ordering and stable tie-break IDs. All 64-bit identifiers are decimal strings (not JS Number). API version prefix `v1` and schema `1.0.0-draft` are independent of MQTT version. Changes to enum, required fields, operation paths and HTTP error semantics need consumer impact review and version handling; new WSS event types may break exhaustive handlers.

## VN920_V1 Exclusive Channel Allocation Semantics (#154)

- **Channel Allocation Space:** Exactly 11 channels CH00–CH10 (920.250–922.750 MHz, 125 kHz BW, 250 kHz spacing).
- **Backend Persistent Registry:** Allocation state is persistently stored in PostgreSQL. In MVP, each Gateway holds at most one channel, and no channel is shared across Gateways.
- **`GET /api/v1/channels`:** Returns all 11 channels and their status (`AVAILABLE` vs `ALLOCATED`). Privacy guard: `assigned_gateway_id` is included only for `ADMIN` users or when the assigned gateway matches the caller's authorized scope; redacted (`null`) for other callers to prevent tenant topology disclosure.
- **`POST /api/v1/gateways/{gw_id}/channels/request`:**
  - Idempotent request using `X-Idempotency-Key`.
  - Rejects with `409 Conflict` if the channel is already allocated to another Gateway, or if the Gateway already holds a different channel.
  - Returns `201 Created` with `ChannelAllocation` containing `allocation_generation` (monotonic uint32) and `rf_authorized: false`.
- **`GET /api/v1/gateways/{gw_id}/channel`:**
  - Reads the currently allocated VN920 channel for the specified Gateway. Returns 200 with `ChannelAllocation` or 404 if not allocated.
- **`DELETE /api/v1/gateways/{gw_id}/channel`:**
  - ADMIN only. Releases the channel assignment.
  - **Release Safety Guard:** Rejects with `409 Conflict` if the Gateway has an `ACTIVE` TDMA schedule, unless `force=true` query parameter is explicitly provided.
- **State Hierarchy Invariant:**
  `CHANNEL_ALLOCATED` $\to$ `SCHEDULE_STAGED` $\to$ `SCHEDULE_ACTIVE` $\to$ `RF_AUTHORIZED`.
  Channel allocation is a prerequisite for TDMA scheduling, but channel allocation alone **never authorizes RF transmission**.

- **Alert & Realtime Event Synchronization (Issue #232):**
  - REST entity `Alert` and WSS `ALERT_TRIGGERED` contain `event_ref` (u32), `event_code` (u8, button press = 0x01), and `event_value` (i16, button press = 1), matching the discrete payload of `UP_EVENT` 0x41 (26B).
  - Countdown parameter `min_announce_superframes` in `GenerateScheduleRequest` is marked `deprecated: true` per Owner Decision #208. Schedule migration occurs on-demand during Maintenance cycles.

## WSS / state continuity

- AuthN/AuthZ and Origin checked **before** 101 upgrade. No direct MQTT/PG from Web/Mobile and no client-origin mutating WSS events. Subscription v1 derives per-gateway scope from authenticated principal at handshake; same RBAC + object-level checks apply at fan-out. D13 credential transport: `TBD/BLOCKED_SECURITY`.
- Event envelope `event_id` is issued by Backend; `ALERT_TRIGGERED.payload.event_id` is stable MQTT gateway ID built from `gateway_id:gateway_epoch:seq`. Client must not use WSS envelope ID as dedup key.
- `TELEMETRY_UPDATE` is preserved for historical playback only. Active V2 live alerts arrive via `ALERT_TRIGGERED`.
- WSS is best effort; `cursor` does not imply server replay. On connect/reconnect: connect/temporarily buffer live → fetch REST snapshots → apply baseline → drain buffer/reconcile by domain IDs/revision. If overflow, mark STALE and resync. An out-of-order/duplicate `COMMAND_STATE_CHANGED` must not roll back a newer revision. WSS cannot self-certify Gateway online from retained status.
- Future `COMMAND_STATE_CHANGED` is an additive schema proposal with compatibility risks. Unknown event type should be ignored safely and trigger refresh rather than crash. `NODE_ACKED` is protocol-level ACK of the defined type, not verified physical state. Actual WSS origin/auth, pagination, ordering, reconnect and backpressure integration tests: `NOT_VERIFIED`.

## Verification before contract approval

- Official OpenAPI parser/semantic validator with reported version; JSON Schema Draft2020-12 + FormatChecker, REST error/command/schedule/channel examples positive/negative and WSS examples.
- Producer Go + consumer React/Flutter technical reviews, plus Security for D13; review request names do not equal approval.
- Scope strictly within Issue #128 allowed paths. No auto-merge.
