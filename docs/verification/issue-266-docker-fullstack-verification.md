# Issue #266 Verification Report: Full-stack Containerization & Docker Compose

- **Issue:** [#266 - [Infra][Docker] Full-stack Containerization & Compose for Web Dashboard, Go Backend, and PostgreSQL](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/266)
- **Branch:** `feature/266-docker-fullstack`
- **Base SHA:** `3fbf6ad459efdcdf783fbc02008e568eabe2cc0e`
- **Authority:** `docs/architecture/deployment.md`, `deploy/compose.yaml`, `deploy/README.md`, `contracts/api/openapi.yaml`, `AGENTS.md`
- **Status:** **VERIFIED / PASS**

---

## 1. Summary of Deliverables

1. **Backend Go Containerization (`backend-go/Dockerfile` & `backend-go/.dockerignore`):**
   - Multi-stage Alpine build using `golang:alpine` and runtime `alpine:latest`.
   - Compiles static stripped Go binary `./cmd/server` (`-trimpath -ldflags="-s -w"`).
   - Injects PostgreSQL `database/sql` driver (`github.com/lib/pq`) in container build stage without altering host git files.
   - Embeds automated database migration entrypoint (`/app/entrypoint.sh`) that waits for PostgreSQL readiness (`pg_isready`), initializes `schema_migrations`, idempotently applies all pending `migrations/*.up.sql` scripts, and executes the server.
   - Enforces non-root execution (`appuser:appgroup`), exposes port `8080`.
   - Supports both `/healthz` (contractual OpenAPI path) and `/api/v1/health` (AC1 explicit requirement).

2. **Web Dashboard Containerization (`clients/web-dashboard/Dockerfile` & `clients/web-dashboard/.dockerignore`):**
   - Enabled Next.js `output: "standalone"` in `clients/web-dashboard/next.config.ts`.
   - Multi-stage Node 22 Alpine build (`node:22-alpine`): dependency caching (`npm ci`), standalone build with `NEXT_TELEMETRY_DISABLED=1`, and minimal runner.
   - Enforces non-root execution (`nextjs:nodejs`, UID 1001), exposes port `3000`.

3. **Full-stack Docker Compose Integration (`deploy/compose.yaml`):**
   - Added `backend` service with `depends_on: postgres: condition: service_healthy` on network `local`.
   - Added `web-dashboard` service with `depends_on: backend: condition: service_healthy` on network `local`.
   - Added Compose profile `fullstack` (with subprofiles `backend` and `frontend`), allowing complete stack startup without interfering with standalone infrastructure tests.
   - Secured loopback-only bindings (`127.0.0.1`) with configurable host port environment variables defaulting to `127.0.0.1:8080`, `127.0.0.1:3000`, and `127.0.0.1:5432`.

4. **Environment & Documentation Synchronization (`.env.example` & `deploy/README.md`):**
   - Updated `.env.example` with template variables `PORT`, `JWT_SECRET_KEY`, and `NEXT_PUBLIC_API_URL`.
   - Updated `deploy/README.md` with detailed operational commands for starting, inspecting, checking logs, and stopping the full-stack container environment.

---

## 2. Acceptance Criteria Verification Matrix

| AC ID | Acceptance Criteria Requirement | Implementation & Verification Evidence | Status |
|---|---|---|---|
| **AC1** | Multi-stage `backend-go/Dockerfile` builds lightweight image running non-root; auto-applies migrations on PostgreSQL readiness; `GET /api/v1/health` returns `200 OK`. | Multi-stage Alpine image built. Container ran under `appuser` (UID 1000). Automated entrypoint executed all 6 SQL migrations into PostgreSQL. `GET /api/v1/health` and `GET /healthz` returned `200 OK`. | **PASS** |
| **AC2** | Multi-stage `clients/web-dashboard/Dockerfile` builds standalone Next.js image running non-root; serves Web Dashboard. | Multi-stage Node 22 Alpine build with `output: 'standalone'` succeeded. Container ran under `nextjs` (UID 1001). Served Next.js dashboard HTML on port 3000 returning HTTP `200 OK`. | **PASS** |
| **AC3** | `deploy/compose.yaml` integrates `postgres`, `mqtt-dev`/`mqtt-tls`, `backend`, `web-dashboard`; strict dependency ordering (`service_healthy`); `docker compose config -q` passes without error. | `compose.yaml` updated with `backend` and `web-dashboard` under profile `fullstack`. Verified `docker compose config -q` returned exit code 0. Existing infrastructure test `test_local_infra.py` passed all checks in 293s. | **PASS** |
| **AC4** | `docker compose up -d` starts full stack; web dashboard communicates with backend and backend connects to PostgreSQL; `verify_no_secrets.py` passes on added lines; verification report recorded. | Automated test brought up fullstack via Compose, verified all 3 services achieved `healthy` status, confirmed 11 VN920 channels seeded, confirmed 6 migration scripts logged in `schema_migrations`, confirmed 0 secret leaks in git diff. | **PASS** |

---

## 3. Test & Verification Receipts

### 3.1 Host G0 Context Check
Command:
```bash
python3 scripts/agent_harness/agent_context.py --repo /home/khanh/projects/iot/LoRa-P2P-issue-266 --base main \
  --allowed-path backend-go/Dockerfile \
  --allowed-path backend-go/.dockerignore \
  --allowed-path clients/web-dashboard/Dockerfile \
  --allowed-path clients/web-dashboard/.dockerignore \
  --allowed-path clients/web-dashboard/next.config.ts \
  --allowed-path deploy/compose.yaml \
  --allowed-path deploy/README.md \
  --allowed-path .env.example \
  --allowed-path docs/verification/
```
Output:
```json
{
  "status": "HOST_CONTEXT_LOADED",
  "source_sha": "3fbf6ad459efdcdf783fbc02008e568eabe2cc0e",
  "git_blob_sha": "3b089079bc345f4b30979624ea6c89696aa50c00",
  "agents_sha256": "32a991b015bd2815ed55b8bba7bd3b13277003b14f323afb8c5694d047a5942e",
  "agents_bytes": 7142,
  "selection_sha256": "f301f791323bbf1310880bfd03d3b0e817558763a1504f82056f69831d954ab6"
}
```

### 3.2 Docker Compose Syntax Validation
Command:
```bash
docker compose --env-file .env.example -f deploy/compose.yaml --profile fullstack config -q
```
Result: Exit code `0` (clean, silent validation).

### 3.3 Full-stack End-to-End Orchestration Test
Automated execution with disposable project `issue266-verify` testing all components:
```text
1. Validating Compose config...
PASS: Compose config -q valid.
2. Building and starting fullstack services...
[+] up 7/7
 ✔ Image issue266-verify-web-dashboard       Built
 ✔ Image issue266-verify-backend             Built
 ✔ Network issue266-verify_local             Created
 ✔ Volume issue266-verify_pg_data            Created
 ✔ Container issue266-verify-postgres-1      Healthy
 ✔ Container issue266-verify-backend-1       Healthy
 ✔ Container issue266-verify-web-dashboard-1 Healthy
3. Waiting for services to be healthy...
   Wait 0s: {'backend': 'healthy', 'postgres': 'healthy', 'web-dashboard': 'starting'}
   Wait 2s: {'backend': 'healthy', 'postgres': 'healthy', 'web-dashboard': 'healthy'}
PASS: All fullstack services are healthy!
4. Testing Backend /healthz and /api/v1/health endpoints...
PASS: GET /healthz returned 200 {"status":"ok"}
PASS: GET /api/v1/health returned 200 {"status":"ok"}
5. Testing Web Dashboard HTTP root...
PASS: Web Dashboard returned HTTP 200 with 30695 bytes HTML.
6. Verifying non-root users inside containers...
PASS: Backend runs as non-root user: appuser
PASS: Web Dashboard runs as non-root user: nextjs
7. Verifying PostgreSQL migrations and schema tables...
PASS: PostgreSQL tables created: ['active_gateway_schedules', 'device_generations', 'device_join_counters', 'devices', 'event_quarantine', 'events', 'gateway_channel_allocations', 'gateway_status', 'join_transactions', 'node_health', 'rf_channels', 'schedule_migration_transactions', 'schedule_slots', 'schedules', 'schema_migrations', 'users']
8. Verifying schema_migrations records...
PASS: Applied migration versions: ['000001_rf_channels.up.sql', '000002_device_join_registry.up.sql', '000003_event_storage_and_health.up.sql', '000004_create_gateway_status.up.sql', '000004_create_users_table.up.sql', '000004_schedule_storage.up.sql']
9. Verifying seeded VN920 channels...
PASS: rf_channels count = 11
10. Cleaning up test containers and volumes...
PASS: Cleanup complete.
ALL FULLSTACK CHECKS PASSED SUCCESSFULLY!
```

### 3.4 Regression Testing: Local Infrastructure (`test_local_infra.py`)
Command:
```bash
python3 -u tests/integration/test_local_infra.py
```
Output:
```text
PASS: Compose profiles, loopback-only bindings and dev network isolation
PASS: missing/empty PostgreSQL environment rejected
PASS: broker uid1883, ACL owner1883:1883 mode0600, server-only key mount; no ownership/startup warnings
PASS: each client sees only public CA and its own certificate/key; anonymous sees CA only
PASS: PostgreSQL healthcheck and persistence after container recreation
PASS: separate-network client reaches non-loopback control listener on 192.168.88.113
PASS: postgres reachable via localhost, rejected via non-loopback 192.168.88.113:44651
PASS: mqtt-dev reachable via localhost, rejected via non-loopback 192.168.88.113:44650
PASS: mqtt-tls reachable via localhost, rejected via non-loopback 192.168.88.113:44649
PASS: published TLS port verifies server CA and hostname
PASS: anonymous/no certificate rejected by TLS
PASS: untrusted certificate rejected by TLS
PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1
PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135
PASS: denied receive gw-a on iot/v1/gw/gw-b/downlink/command: MQTT exit27, no payload; Docker process completed in 46.27s
PASS: denied receive gw-b on iot/v1/gw/gw-a/downlink/command: MQTT exit27, no payload; Docker process completed in 46.66s
PASS: denied receive gw-a on iot/v1/gw/#: MQTT exit27, no payload; Docker process completed in 46.74s
PASS: denied receive backend on iot/v1/gw/gw-a/downlink/command: MQTT exit27, no payload; Docker process completed in 46.72s
PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages
----------------------------------------------------------------------
Ran 1 test in 293.322s
OK
```

### 3.5 Web Dashboard Unit Tests & ESLint
Command:
```bash
cd clients/web-dashboard && npm test && npm run lint
```
Output:
```text
ℹ tests 12
ℹ suites 2
ℹ pass 12
ℹ fail 0
ESLint: 0 problems (0 errors, 0 warnings).
```

### 3.6 Secret Scanning Check on Added Diffs
Command:
```bash
python3 -c "import subprocess, sys; sys.path.insert(0, 'scripts'); import verify_no_secrets
diff = subprocess.run(['git', 'diff', '--no-ext-diff', '--unified=0'], capture_output=True, check=True).stdout
added = b'\n'.join(l[1:] for l in diff.splitlines() if l.startswith(b'+') and not l.startswith(b'+++'))
assert not verify_no_secrets.contains_secret(added)
print('PASS: 0 secret violations in added diff lines')"
```
Output:
`PASS: 0 secret violations in added diff lines`

---

## 4. Verification Checkpoint Status

- [x] All touched files strictly within `Target Directories (allowed paths)`.
- [x] Multi-stage build for Go Backend (`backend-go/Dockerfile`) with automated migrations.
- [x] Multi-stage standalone build for Web Dashboard (`clients/web-dashboard/Dockerfile`).
- [x] Both runtime containers enforce non-root unprivileged users (`appuser` and `nextjs`).
- [x] Loopback-only port bindings (`127.0.0.1`) preserved for all published ports.
- [x] Compose profile `fullstack` accurately isolates full-stack execution from lower-level unit infrastructure tests.
- [x] Healthchecks configured for all three services (`postgres`, `backend`, `web-dashboard`).
- [x] Zero secret leakage in added lines and environment templates.
- [x] Regression tests pass (`test_local_infra.py`, `test_infra_security.py`).
- [x] Verification report completed.
