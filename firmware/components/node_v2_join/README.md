# node_v2_join

Sensor Node V2 Over-the-Air Join Handshake Engine for Hybrid TDMA MVP.

## Features
- **5-Message V2 Handshake:** Drives state transitions from `UNJOINED`, CAD channel evaluation, `UP_JOIN_HELLO`, `DOWN_JOIN_GRANT`, `UP_JOIN_CONFIRM`, `DOWN_JOIN_FINISH`, to `UP_JOIN_READY`.
- **Anti-Replay Counter Persistence:** Monotonically updates and commits join counter to non-volatile flash (`nvs`) before radio emission to prevent rollback attacks.
- **Fail-Closed Lockout:** Locks out join state machine upon cryptographic or protocol faults.
