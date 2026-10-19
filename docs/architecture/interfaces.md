# Interface ownership (DRAFT)

| Interface | Producer -> consumer | Source of truth | Reviewers |
|---|---|---|---|
| LoRa MAC | Node <-> Gateway | contracts/radio-mac/specification.md | Both Embedded/RF owners |
| TDMA schedule | Go -> MQTT -> Gateway -> Nodes | contracts/mqtt/topics.md + radio-mac specification | Backend + Gateway + Node |
| Gateway events | Gateway -> MQTT -> Go | contracts/mqtt/topics.md & schemas | Gateway + Backend |
| REST / WSS | Go -> Clients | contracts/api/openapi.yaml (REST only) | Backend + Frontend |
| Persistence | Backend <-> PostgreSQL | backend-go/migrations | Backend + QA |

Treat schema versions independently of application versions. Changes that alter byte order, field size, address space, authenticated data or timing must be made through a reviewed ADR and regression vectors.

MQTT QoS 1 can redeliver; deduplicate by a stable, sufficiently wide session/boot ID and event ID, not an 8-bit sequence number in isolation. Be careful with retained schedules: validate freshness, authenticity and activation epoch before use.
