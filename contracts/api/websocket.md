# WebSocket v1 — Backend → Web / Mobile (Issue #15)

**Contract:** `0.2.0-draft / PROPOSED` · **Production implementation:** `NOT_IMPLEMENTED` · **Auth decision D13:** `TBD / BLOCKED_SECURITY` · **Producer/consumer approval:** `PENDING`.
Baseline: BM05 WebSocket/WSS learning material, [OpenAPI](openapi.yaml), [Event JSON Schema](schemas/realtime-event.schema.json) and [API Contract Semantics](contract-semantics.md). Endpoint is `wss://{backend_host}/api/v1/ws/realtime`; isolated localhost development may use `ws://localhost:8080/api/v1/ws/realtime`. Use JSON UTF-8 text WebSocket messages, not LoRa RF frames.

## 1. Trust boundary and subscription model (v1 proposal)

- `WSS` protects the client→server channel when TLS is configured correctly; use strict `Origin` allowlist for browsers (prevents CSWSH in cookie-based profiles), **plus** authentication and server-side authorization. `Origin` is not a credential (non-browser clients can forge it).
- Browser `new WebSocket(url)` cannot set an arbitrary `Authorization` header. **Do not place long-lived JWT/Bearer credentials in query strings**. D13 is still unresolved: possible secure `HttpOnly/Secure/SameSite` cookie with CSWSH/CSRF safeguards **or** atomic short-lived single-use ticket issued over authenticated REST. `POST /api/v1/auth/ws-ticket` is **NOT in OpenAPI** and MUST NOT be assumed implemented/approved.
- Until D13 is approved, production handshake method is `TBD`. Server **MUST** reject unauthenticated/unauthorized upgrades; no "allow-all until auth exists" fallback. No secrets in access logs. Token/session expiration and revocation require disconnect/reauthorization strategy in implementation.
- Proposed v1 subscription: **server-selected authorized visibility scope at handshake**, limited to gateways/nodes accessible to the authenticated user. No client-supplied `SUBSCRIBE` / `UNSUBSCRIBE` protocol in v1; client requests a narrower view via REST UI filters. The server must enforce object-level scope for **every** event before fan-out, not merely RBAC role. No tenant leakage, even if Web UI hides unauthorized devices.
- Authorized roles `ADMIN | OPERATOR | VIEWER` may read permitted events. All state-mutating operations (alert ACK, command, schedule review/activation) use HTTPS REST endpoints with their `x-roles`, never WSS client mutation packets. Unknown WSS client application message types: reject/close under approved policy (WSS v1 is server-push only).

## 2. Envelope and event types

Machine-readable envelope: `schema_version="1.1-draft"`, `event_id` (Backend-origin server-event identity), `type`, `emitted_at` (UTC RFC3339), `payload`, optional opaque `cursor`. Server-event `event_id` is distinct from MQTT source `payload.event_id`. Do not use a WSS event ID to deduplicate Gateway telemetry in PostgreSQL.

| Event `type` | Required payload | Client reconciliation |
|---|---|---|
| `TELEMETRY_UPDATE` | `gateway_id, node_id, reading_id, event_id, observed_at, data` | Use `(gateway_id,node_id,payload.event_id)` as Node-origin business identity; Gateway reception epoch is not the source event ID. |
| `ALERT_TRIGGERED` | `gateway_id, node_id, alert_id, severity, triggered_at` | Correlate `alert_id`; do not overwrite ACK status from a newer REST snapshot. |
| `SCHEDULE_STATE_CHANGED` | `gateway_id, schedule_id, version, state` | `STAGED != ACTIVE`; only a verified Gateway `ACTIVE_REPORT` in Backend justifies `ACTIVE`. |
| `GATEWAY_STATUS_CHANGED` | `gateway_id, mode, last_seen_at` | Retained MQTT status is not proof of live connection; trust REST/backend freshness policy. |
| `COMMAND_STATE_CHANGED` (**PROPOSED EXTENSION**) | `gateway_id, node_id, command_id, state, state_revision` | Read after HTTP 202 from `GET /api/v1/gateways/{gw_id}/nodes/{node_id}/commands/{command_id}`; compare revisions (decimal strings, not JS Number). `NODE_ACKED` is **not** actuator success. |

**Compatibility:** fifth event `COMMAND_STATE_CHANGED` extends the previous four-type draft. Clients with exhaustive event-type switches may break. Frontend/Mobile reviewer must approve handling unknown `type` as ignore+telemetry/re-sync rather than crash. Do **not** claim backwards compatibility without test. MQTT v1 schema identity was refined in #14: Telemetry source Event ID originates at Node (opaque, format OPEN G2), not Gateway boot epoch; backend validates `(gateway_id,node_id,event_id)` before fan-out.

## 3. Delivery, order, slow consumer, resync

1. WSS is **best-effort live push**, no broker-style durability, exactly-once, offline queue, cursor replay or global ordering guarantee. A `cursor` is **opaque hint only** until retention/replay ADR, not a server replay checkpoint. HTTP/WebSocket TCP preserves bytes order per *one connection* only.
2. After initial connection or reconnect, client starts a **bounded temporary live-event buffer**, then fetches REST baseline snapshots: `GET /api/v1/gateways/{gw_id}/status`, `GET /api/v1/nodes`, `GET /api/v1/alerts`, `GET /api/v1/gateways/{gw_id}/nodes/{node_id}/telemetry`, `GET /api/v1/gateways/{gw_id}/schedules/{schedule_id}`, and `GET /api/v1/gateways/{gw_id}/nodes/{node_id}/commands/{command_id}` when relevant. Apply snapshot, then drain live buffer **with per-domain reconciliation**.
3. Telemetry dedup uses original Gateway event ID; alerts keyed by `alert_id`; schedules keyed by `gateway_id + schedule_id + version` with strict lifecycle; commands keyed by `command_id + state_revision` and must not regress to an older revision. If revision absent/ambiguous, prefer REST resync rather than guessing latest from arrival order. Unknown `observed_at` can be `null`.
4. When inbound resync buffer overflows or a per-client outbound queue is full, mark UI `STALE / RESYNCING`; discard affected buffer and repeat bounded REST resync or disconnect slow client. **Never** present a partial event stream as complete. Queue lengths, rate, heartbeat ping/pong timeouts, close-code mapping are implementation policy `TBD / NOT_BENCHMARKED`, not a numeric SLA.
5. Ping/Pong detects half-open TCP only within configured timeout/scheduler assumptions; reconnect with exponential backoff + jitter; no unconditional tight reconnect loops. Race/fan-out concurrency is backend implementation concern, not a guarantee of RFC 6455.

## 4. Negative contract cases / verification split

- JSON Schema: unknown `type`; missing `event_id`; malformed MQTT source `event_id`; wrong command UUID; missing `state_revision`; illegal command state; non-UTC `emitted_at`; extra undeclared payload keys.
- Behavioral tests (not satisfied by JSON Schema): wrong `Origin`, missing/expired auth, unauthorized gateway subscription, WSS receiving a mutation attempt, duplicate/reordered events, REST snapshot/event race, slow consumer overflow, live cursor used incorrectly as replay.
- These require executable tests and recorded results in `tests/contract/`, plus integration/security tests for real WSS. Synthetic fixtures alone do not prove those behaviors.

## 5. Source/authority and pending decisions

- [BM04] `BM04_GIAO_TRINH_REST_HTTPS_OPENAPI_FINAL(1).md`: HTTP 202, RBAC, OpenAPI draft, command ticket polling extension (proposed).
- [BM05] `BM05_GIAO_TRINH_WEBSOCKET_WSS_FINAL(1).md`: RFC 6455, Origin/auth, bounded hub, best-effort resync.
- [System design] `esp32_sx1762.md` and `docs/architecture/system-overview.md`: Backend plans; Gateway local TDMA Master.
- Existing [D13](../OPEN_DECISIONS.md) **BLOCKED Security** — leave unresolved pending approved auth ADR; no production token policy invented.
- Existing #14 MQTT draft: stable Gateway-event identities and `STAGE_ACK != ACTIVE_REPORT`; backend must perform cross-contract mapping.
