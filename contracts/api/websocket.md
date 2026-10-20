# WebSocket Real-time Contract — Backend → Web/Mobile

**0.1.0-draft · Issue #15 · Not implemented · Backend/Web/Mobile review pending.** REST interface: [openapi.yaml](openapi.yaml). WSS message schema: [realtime-event.schema.json](schemas/realtime-event.schema.json).

## Endpoint & authorization

`wss://{backend_host}/api/v1/ws/realtime` production; localhost development may use `ws://localhost:8080/api/v1/ws/realtime` behind isolated network only. Authentication must be established **before** upgrade, enforcing Viewer/Operator/Admin permissions **server-side**. Browser WebSocket does not support arbitrary Authorization headers: choose and document either Secure HttpOnly SameSite cookie + CSRF/Origin protection **or** short-lived single-use WSS ticket before implementation (ADR pending). **Do not** place long-lived bearer JWT/token in query parameters, logs or URL. Invalid/revoked credentials: reject handshake. Check `Origin` and gateway/tenant authorization.

## Server→client events (UTF-8 JSON)

Envelope: `schema_version="1.0-draft"`, `event_id` (server stable unique ID), `type`, `emitted_at` (server RFC3339 UTC), `payload`, optional opaque `cursor`. Event types:
- `TELEMETRY_UPDATE`: `gateway_id,node_id,reading_id,event_id` (source MQTT event ID), `observed_at,data` raw channel values.
- `ALERT_TRIGGERED`: `gateway_id,node_id,alert_id,severity,triggered_at`.
- `SCHEDULE_STATE_CHANGED`: `gateway_id,schedule_id,version,state`; `STAGED` **không** tương đương `ACTIVE`.
- `GATEWAY_STATUS_CHANGED`: `gateway_id,mode,last_seen_at`; online phải suy ra từ backend timeout, không tin retained status vô hạn.

Schema machine-readable và ví dụ valid/invalid: [examples/realtime-cases.json](examples/realtime-cases.json).

## Delivery, ordering và reconnect

- WebSocket là luồng cập nhật **best effort**, không phải message queue bền vững. Gói bị mất khi đứt kết nối không bắt buộc được replay; **không** dùng WSS event làm source of truth.
- Một kết nối TCP giữ thứ tự byte nhưng thứ tự `emitted_at`/data giữa nhiều node, MQTT QoS1, worker hoặc reconnect **không được đảm bảo**. Client dedup bằng server `event_id`, hiển thị dữ liệu dựa `observed_at` và nguồn thời gian (có thể null), không dựa arrival order để ghi đè trạng thái mới.
- Khi reconnect: xác thực lại, lấy snapshot REST `GET /api/v1/gateways/{gw_id}/status`, `GET /api/v1/nodes`, `GET /api/v1/alerts`, `GET /api/v1/nodes/{node_id}/telemetry` và schedule GET nếu có ID; sau đó tiếp tục WSS. Cursor là opaque hint, **không** cam kết server retention/replay cho đến khi có ADR.
- Quá tải: Backend đóng kết nối chậm/backpressure có giới hạn và buộc client resync, không cấp hàng đợi không giới hạn. Ping/pong/heartbeat, token refresh, close codes và origin policy cần được chốt tại implementation.
- Kiểm thử: Web/Mobile dùng mock schema, fixture; chưa có chứng cứ reconnect, authorization hay end-to-end latency PASS.

**RBAC:** Viewer/Operator/Admin nhận các sự kiện được phép xem; mọi HTTP đột biến (ACK, command, schedule) kiểm role phía Backend chứ không dựa trên nút ẩn trong UI.
