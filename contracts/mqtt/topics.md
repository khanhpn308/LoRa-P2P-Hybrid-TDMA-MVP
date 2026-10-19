# MQTT Contract — DRAFT v0

Topic prefix: `iot/v1/gw/{gateway_id}`. Confirm MQTT version supported in Gateway and Go clients via ADR.

| Topic suffix | Publisher -> subscriber | QoS | Retain |
|---|---|---|---|
| `uplink/telemetry` | Gateway -> Go | 1 | no |
| `uplink/alert` | Gateway -> Go | 1 | no |
| `uplink/status` | Gateway -> Go | 1 | reviewed separately |
| `uplink/schedule-ack` | Gateway -> Go | 1 | no |
| `downlink/schedule` | Go -> Gateway | 1 | **TBD: unsafe to blindly apply retained stale schedules** |
| `downlink/command` | Go -> Gateway | 1 | no |

All events require `schema_version`, `gateway_id`, `node_id` where applicable, unique `event_id` or epoch+counter, observed timestamp basis, and explicit validation. Schedule commands must contain version, activation horizon, expiration, authentication, ACK/NACK, and must never trigger immediate per-slot RF execution.

No claim that QoS 1 eliminates duplicates or ensures deadline; Go performs idempotent storage.

## Security
- TLS with authenticated Gateway and backend, least-privilege per-gateway topics, no exposed credentials.
- Development-only localhost MQTT listener is deliberately unencrypted in `dev-insecure` Compose profile. Never bridge that to public networks.
- Frontend/Mobile never directly access MQTT.
