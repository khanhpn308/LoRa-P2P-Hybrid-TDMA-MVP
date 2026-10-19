# Engineering and review standards

- One GitHub Issue per coherent change, linked PR, acceptance criteria and evidence.
- Use branch naming `feature/<issue>-...`, `fix/<issue>-...`; review before merge.
- C on ESP-IDF: bounded static/pool memory, explicit lifetime and ownership, bounded queues, no blocking in ISR, serialize SX1276 radio operations, WDT/recovery.
- Go: explicit context cancellation/timeouts, idempotent MQTT ingestion, database migrations, parameterized SQL, restricted concurrent goroutines.
- API: OpenAPI versioning, WSS/REST secure auth, server-side RBAC.
- CI builds are not HIL, time measurement, RF certification or deployment approval.
- AI-generated code must include relevant tests and be human-reviewed; no fabricated logs/benchmarks/citations.
- Never commit SDK `sdkconfig` with secrets, private certificates, access keys, raw production dumps or build artifacts.
