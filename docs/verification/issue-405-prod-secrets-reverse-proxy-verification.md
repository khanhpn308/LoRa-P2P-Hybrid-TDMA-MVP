# Issue #405 Verification Report: Production Secret Validation, Restricted Bindings & Reverse Proxy

- **Issue:** [#405 - [GO][Security] Enforce production secret validation and restrict backend host binding behind reverse proxy](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/405)
- **Branch:** `feature/405-prod-secret-validation-reverse-proxy`
- **Base SHA:** `aec70071774e0eb2607eaea8d297d11782ad9c05`
- **Authority:** `AGENTS.md`, `docs/architecture/deployment.md`, `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md`
- **Human Security Review:** `HUMAN_SECURITY_REVIEW_PENDING` (`ai:human-audit-req` / `risk:security`)

---

## 1. Summary of Changes

1. **Runtime Environment Mode & Fail-Fast Secret Validation (`backend-go/internal/config/config.go`, `backend-go/internal/app/wiring.go`):**
   - Added `AppEnv` (`APP_ENV`, defaulting to `development`; supports `development`/`dev`/`local`/`test`, `staging`, `production`/`prod`, and rejects unknown `APP_ENV` values instead of silently falling back to insecure dev defaults).
   - Added `Validate()`, `IsProduction()`, `RequiresStrictSecrets()`, `LoadWithError()`, and `LoadFromEnvWithError()`.
   - In `production` and `staging` modes, `LoadFromEnv` and `Validate()` no longer fall back to `DefaultJWTSecret` and no longer derive `DeviceProvisionMasterKey` from `JWT_SECRET_KEY`. Startup fails fast via `app.New(cfg)` when `JWT_SECRET_KEY` is missing, `< 32` bytes, blank, or matches default/placeholder literals (`DefaultJWTSecret`, legacy compose dev literal, `REPLACE_WITH_*`), or when `DEVICE_PROVISION_MASTER_KEY` is missing, `< 32` bytes, invalid 64-char hex, all zeros, or derived from `JWT_SECRET_KEY`.
   - Validation errors never echo secret values or `DATABASE_URL` credentials.
   - Added `PostgresSSLMode` (`POSTGRES_SSLMODE`) support with validation against PostgreSQL SSL modes (`disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`) and automatic query parameter injection when `DATABASE_URL` omits `sslmode`.

2. **Compose Hardening & Configurable PostgreSQL SSL Mode (`deploy/compose.yaml`, `.env.example`):**
   - Removed the hardcoded `JWT_SECRET_KEY` fallback literal from `deploy/compose.yaml`.
   - Restricted default `BACKEND_PORT_BIND` to `127.0.0.1:8080` and `WEB_PORT_BIND` to `127.0.0.1:3000`.
   - Made `DATABASE_URL` `sslmode` configurable via `${POSTGRES_SSLMODE:-disable}` and allowed full `DATABASE_URL` override for external PostgreSQL deployments.
   - Added `APP_ENV`, `POSTGRES_SSLMODE`, `DEVICE_PROVISION_MASTER_KEY`, `BACKEND_PORT_BIND`, `WEB_PORT_BIND`, `PROXY_CERT_DIR`, and `PROXY_HTTPS_BIND` templates to `.env.example` using `REPLACE_WITH_*` placeholders.

3. **TLS Reverse Proxy & Production Overlay (`deploy/reverse-proxy/nginx.conf`, `deploy/reverse-proxy/compose.prod.yaml`, `deploy/compose.yaml`):**
   - Added `reverse-proxy` (`nginx:1.27-alpine`, profile `reverse-proxy`) terminating TLS 1.2/1.3 on port `443` and proxying `/healthz`, `/api/v1/`, and WSS `/api/v1/ws/realtime` to `backend:8080`, and `/` to `web-dashboard:3000`.
   - Added production Compose overlay `deploy/reverse-proxy/compose.prod.yaml` enforcing `APP_ENV=production`, required `JWT_SECRET_KEY` and `DEVICE_PROVISION_MASTER_KEY` interpolation, and `ports: !reset []` on `postgres`, `backend`, and `web-dashboard` so only `reverse-proxy` exposes port `443`.
   - Documented production secret validation, PostgreSQL TLS configuration, and reverse-proxy deployment in `deploy/README.md` and `docs/architecture/deployment.md`.

---

## 2. Verification & Test Evidence

| Check | Command | Result | Notes |
|---|---|---|---|
| Host G0 context & Go V2 selection | `python3 scripts/agent_harness/agent_context.py --repo /home/khanh/projects/iot/LoRa-P2P-issue-405 --base aec70071774e0eb2607eaea8d297d11782ad9c05 ...` | **PASS** (exit 0) | `HOST_CONTEXT_LOADED`; 108 Go V2 rules selected (`selection_sha256`: `ecd0b97df0f1347ed45828cc5c96dcc408667f57d9c229172377b2677b47b830`) |
| Go `config` unit tests (`-race`) | `go test -v -race ./internal/config/...` (Go `1.27.3`) | **PASS** (exit 0) | All existing + 14 new production secret / SSL mode / non-leakage subtests passed |
| Go `app` unit tests (scoped) | `go test -v ./internal/app -run "TestApp_New\|TestApp_Run_Graceful\|TestApp_Run_Deterministic\|TestApp_Run_Fatal"` | **PASS** (exit 0) | Includes `TestApp_New_ProductionFailFastSecretValidation`; baseline `TestApp_Run_PersistentMode_RealSubscriberLifecycle` timed out on unstarted local Postgres/MQTT (`127.0.0.1:5432`) |
| Go `vet` & `build` | `go vet ./... && go build ./...` | **PASS** (exit 0) | Clean compile & vet across `backend-go` |
| Compose validation (`config -q`) | `docker compose --env-file .env.example -f deploy/compose.yaml --profile fullstack --profile reverse-proxy config -q` | **PASS** (exit 0) | Validated both base `compose.yaml` and `compose.prod.yaml` overlay |
| Nginx syntax test | `docker run --rm ... nginx:1.27-alpine sh -c 'nginx -t && which nc'` | **PASS** (exit 0) | `nginx:1.27.5` syntax OK; `/usr/bin/nc` present for container healthcheck |
| Live E2E Compose prod + reverse-proxy HTTPS/WSS | Disposable `docker compose ... -f deploy/compose.yaml -f deploy/reverse-proxy/compose.prod.yaml --profile fullstack --profile reverse-proxy up -d --build --wait` | **PASS** (exit 0) | All 4 services healthy; HTTPS `/healthz` 200; HTTPS `/` 200; `/api/v1/gateways` 401 via Nginx->backend; WSS `/api/v1/ws/realtime` reached backend over TLS; 0 host ports on `postgres`/`backend`/`web-dashboard`; `/app/server` failed fast in container under `APP_ENV=production` without secrets |
| Secret scanner unit tests | `python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v` | **PASS** (exit 0, 7 tests) | All 7 tests OK |
| Infra security unit tests | `python3 -m unittest discover -s tests/integration -p test_infra_security.py -v` | **PASS** (exit 0, 11 tests) | All 11 tests OK |
| Repo secret scan | `python3 scripts/verify_no_secrets.py` | **BASELINE_FAIL** (exit 1) | 0 findings in Issue #405 changed/added files or diff; pre-existing fixture failures in `backend-go/internal/auth/service_test.go`, `clients/web-dashboard/...`, `scripts/agent_harness/quality_gates.py` on `main` |
| Local MQTT/TLS infra test | `python3 -u tests/integration/test_local_infra.py` | **BASELINE_FAIL** (exit 1) | Fails at line 49 due to pre-existing `mqtt-dev` `0.0.0.0:1883` binding on `main` (outside Issue #405 scope) |
| Structure & whitespace checks | `python3 scripts/verify_structure.py && git diff --check aec70071774e0eb2607eaea8d297d11782ad9c05` | **PASS** (exit 0) | No whitespace errors; monorepo invariants OK |
