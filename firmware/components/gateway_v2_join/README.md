# gateway_v2_join

Gateway V2 Over-the-Air Join Handshake Relay Engine for Hybrid TDMA MVP.

## Features
- **5-Message V2 Handshake Relay:** Handles `UP_JOIN_HELLO`, relays to Backend via MQTT 5.0, dispatches `DOWN_JOIN_GRANT`, receives `UP_JOIN_CONFIRM`, and validates `UP_JOIN_READY`.
- **Session Key Activation:** Installs ephemeral derived session keys (`K_SESSION_ENC`, `K_SESSION_MAC`) into `session_key_store`.
- **MQTT Envelope Serialization:** Generates standard JSON schemas matching `contracts/mqtt/schemas/` for cloud coordination.
