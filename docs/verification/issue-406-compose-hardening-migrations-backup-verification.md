# Issue #406 Verification Report: Compose Hardening, Decoupled Migrations, and `pg_data` Backup/Restore

- **Issue:** [#406 - [Infra] Harden Docker Compose restart/resource policies, decouple DB migrations, and add pg_data backup runbook](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/406)
- **Branch:** `feature/406-harden-compose-migrations-backup`
- **Base SHA:** `aec70071774e0eb2607eaea8d297d11782ad9c05`
- **Authority:** `docs/architecture/deployment.md`, `deploy/compose.yaml`, `deploy/README.md`, `AGENTS.md`

---

## 1. Summary of Changes

1. **Decoupled Migration Runner (`backend-go/Dockerfile`):**
   - `/app/entrypoint.sh` now waits only for `pg_isready` (when `DATABASE_URL` is non-empty) and executes `"$@"`, removing `psql` migration execution from normal `backend` container startup.
   - Added `/app/migrate.sh` (non-root `appuser:appgroup`, mode `+x`):
     - Requires non-empty `DATABASE_URL` and waits for `pg_isready`.
     - Acquires PostgreSQL session advisory lock `pg_advisory_lock(748291045239184721)` once across a single `psql -v ON_ERROR_STOP=1` session before creating `schema_migrations`.
     - Validates sorted `/app/migrations/*.up.sql` filenames and wraps each pending migration check, `\i` execution, and `schema_migrations` insert in `BEGIN; ... COMMIT;`.
     - Releases `pg_advisory_unlock(748291045239184721)` upon completion; partial failure aborts immediately via `ON_ERROR_STOP=1`, rolling back the failed transaction and releasing the session lock on disconnect.
2. **Compose Policies & Service Ordering (`deploy/compose.yaml`):**
   - Added one-shot `migrate` service (`profiles: ["fullstack", "backend", "migrate"]`, `restart: "no"`, `entrypoint: ["/app/migrate.sh"]`, `depends_on: postgres: condition: service_healthy`).
   - Updated `backend` to depend on `postgres` (`service_healthy`) and `migrate` (`service_completed_successfully`).
   - Added `restart: unless-stopped` to `postgres`, `mqtt-dev`, `mqtt-tls`, `backend`, and `web-dashboard`.
   - Added `deploy.resources.limits` and `reservations` across all 6 services (`postgres`: 1.0 CPU / 512M, `mqtt-dev`: 0.5 CPU / 128M, `mqtt-tls`: 0.5 CPU / 256M, `migrate`: 0.5 CPU / 128M, `backend`: 1.0 CPU / 256M, `web-dashboard`: 1.0 CPU / 512M).
3. **Documentation & Runbooks (`deploy/README.md`, `docs/architecture/deployment.md`):**
   - Documented the decoupled `migrate` service, resource sizing assumptions, restart policies, and a repeatable external-host `pg_dump -Fc` / `pg_restore` backup/restore runbook (explicitly prohibiting database dumps inside tracked Git paths).

---

## 2. Verification Matrix

| Check | Scope & Method | Observed Result | Status |
|---|---|---|---|
| Compose config validation | `docker compose --env-file .env.example -f deploy/compose.yaml --profile fullstack --profile dev-insecure --profile tls --profile migrate config -q` + normalized JSON inspection | Exit 0; verified restart policies, resource limits/reservations on all 6 services, and `backend` dependency on `migrate` (`service_completed_successfully`) | **PASS** |
| Concurrent migration race & idempotency | Two parallel `docker compose run --rm --no-deps migrate` invocations against fresh `postgres:16-alpine` | Both exited 0; `pg_advisory_lock` serialized execution; `schema_migrations` count = `11` | **PASS** |
| Partial-failure rollback | Mounted disposable `000001_good.up.sql` + failing `000002_bad.up.sql` against `rollback_test` DB | Exited non-zero (`ON_ERROR_STOP=1`); `good_tbl` committed (`000001_good.up.sql` recorded); `should_rollback` rolled back and absent from `schema_migrations` | **PASS** |
| Decoupled `backend` startup & health | `docker compose --profile backend up -d --wait`; inspected `backend` logs + HTTP `GET /healthz` and `GET /api/v1/health` | Zero migration `psql` calls in `backend` logs; both endpoints returned HTTP 200 `{"status":"ok"}` | **PASS** |
| Runtime restart & cgroup limits | `docker inspect` on `postgres`, `backend`, `migrate` + `docker compose restart backend` | Confirmed `RestartPolicy` (`unless-stopped` / `no`), `Memory` (512M / 256M / 128M), `NanoCpus` (1.0 / 1.0 / 0.5); `backend` recovered to `healthy` with HTTP 200 on `/healthz` | **PASS** |
| `pg_data` backup & restore drill | Inserted sentinel gateway row -> `pg_dump -Fc --no-owner --no-privileges` (38,335 bytes) -> `pg_restore --list` -> `down -v` -> fresh `postgres` -> `pg_restore` + idempotent `--clean --if-exists` -> `--profile backend up -d --wait` | `schema_migrations=11`, `rf_channels=11`, sentinel `'Backup Drill GW'` restored; `migrate` skipped all 11 migrations and `backend` became `healthy` | **PASS** |
| Unit tests (`tests/integration`) | `test_infra_security.py` (11 tests) and `test_verify_no_secrets.py` (7 tests) | 18/18 tests passed (`OK`) | **PASS** |
| `web-dashboard` / `mqtt-tls` runtime | Not rebuilt/started in this Issue verification run (unchanged application code/TLS certs) | Config JSON verified; live container startup `NOT_RUN` in this run | **NOT_RUN** |

---

## 3. Evidence Output Excerpt

Tool versions observed: `Docker version 29.8.0, build 88096ef`, `Docker Compose version v5.5.1`, `Python 3.12.3`.

```text
PASS: docker compose config -q exited 0 across all profiles
PASS: normalized compose JSON verifies restart policies, resource limits, and migrate dependency
PASS: built migrate and backend images
PASS: postgres healthy
PASS: concurrent cold-start migrate race serialized safely; schema_migrations count=11
PASS: partial migration failure aborted on ON_ERROR_STOP=1 and rolled back cleanly
PASS: backend started without running migrations; /healthz and /api/v1/health returned 200 OK
PASS: docker inspect verified RestartPolicy and CPU/Memory cgroup limits on postgres, backend, migrate
PASS: backend container restart recovered to healthy without running migrations
PASS: pg_dump -Fc succeeded (38335 bytes, sha256=dcf1f1f83ebcf9b7...)
PASS: pg_restore drill verified (schema_migrations=11, rf_channels=11, sentinel='Backup Drill GW', backend healthy)
```

## 4. Limitations & Pre-existing Baseline Notes

- `go test ./...` was run on host (`go1.27.1`, whereas `.go-version` pins `1.27.3`); all non-DB-dependent Go packages passed, while `TestApp_Run_PersistentMode_RealSubscriberLifecycle` in `internal/app` timed out dialing host `127.0.0.1:5432` because no host PostgreSQL listener was active outside Compose. No `.go` source files were modified in Issue #406.
- `test_local_infra.py` was not executed because `main` (`aec70071774e0eb2607eaea8d297d11782ad9c05`) binds `mqtt-dev` to `0.0.0.0:1883` for LAN hardware testing (commit `4570c82`), which is outside Issue #406 scope and conflicts with `test_local_infra.py`'s `127.0.0.1`-only port assertion.
- `quality_gates.py` `SECRET-SCAN` flags pre-existing baseline file `clients/web-dashboard/tests/integration.test.ts:31` on `main`; zero secret signatures were introduced in the Issue #406 diff (`backend-go/Dockerfile`, `deploy/compose.yaml`, `deploy/README.md`, `docs/architecture/deployment.md`, `docs/verification/`).
- Human security/infrastructure review remains required before production deployment.
