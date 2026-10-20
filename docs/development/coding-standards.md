# Engineering and review standards

- One GitHub Issue per coherent change, linked PR, acceptance criteria and evidence.
- Use branch naming `feature/<issue>-...`, `fix/<issue>-...`; review before merge.
- C on ESP-IDF: bounded static/pool memory, explicit lifetime and ownership, bounded queues, no blocking in ISR, serialize SX1276 radio operations, WDT/recovery.
- Go: explicit context cancellation/timeouts, idempotent MQTT ingestion, database migrations, parameterized SQL, restricted concurrent goroutines.
- API: OpenAPI versioning, WSS/REST secure auth, server-side RBAC.
- CI builds are not HIL, time measurement, RF certification or deployment approval.
- AI-generated code must include relevant tests and be human-reviewed; no fabricated logs/benchmarks/citations.
- Never commit SDK `sdkconfig` with secrets, private certificates, access keys, raw production dumps or build artifacts.

## Mandatory path-scoped Issues

- Every Issue (including manually created and AI-generated tasks) MUST specify `Target Directories (allowed paths)` using repo-root-relative paths.
- Engineers and AI may modify only the paths listed. Update Issue scope and obtain owner/cross-team review **before** adding any other path, including tests, docs, migrations and contracts.
- PR authors must repeat allowed paths; reviewers compare the PR `Files changed` to the Issue, not just the label.
- Current checks validate templates and structure, NOT full automatic enforcement of per-Issue path allowances. See `docs/development/task-breakdown-readiness.md`.
