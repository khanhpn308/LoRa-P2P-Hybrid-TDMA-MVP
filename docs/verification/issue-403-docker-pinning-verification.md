# Issue #403 Verification Report: Pin Docker Base Images & Remove Build-Time `sed` Patch

- **Issue:** [#403 - [GO][Infra] Pin Docker base image versions and remove build-time sed patch in backend-go/Dockerfile](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/403)
- **Branch:** `fix/403-pin-docker-base-remove-sed`
- **Base SHA:** `aec70071774e0eb2607eaea8d297d11782ad9c05`
- **Authority:** `AGENTS.md`, `.go-version`, `backend-go/go.mod`, `contracts/api/openapi.yaml`, `contracts/api/contract-semantics.md`, `deploy/compose.yaml`

---

## 1. Summary of Changes

1. **`backend-go/Dockerfile`:**
   - Pinned builder base image from `golang:alpine` to `golang:1.27.3-alpine` (matching `.go-version` and `backend-go/go.mod` `1.27.3`).
   - Pinned runtime base image from `alpine:latest` to `alpine:3.24.3`.
   - Removed the build-time `RUN sed -i` mutation against `internal/api/health_handler.go` so `docker build` compiles the exact Go source tested by `go test ./...`.
   - Copied both `go.mod` and `go.sum` (`COPY go.mod go.sum ./`).
   - Preserved `CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /server ./cmd/server`, non-root `appuser:appgroup`, and `/app/entrypoint.sh`.

2. **`backend-go/internal/api/health_handler.go`:**
   - Registered both `GET /healthz` (OpenAPI canonical liveness path, used by `deploy/compose.yaml` healthcheck) and `GET /api/v1/health` (Issue #266 AC1 path) directly in `HealthHandler.RegisterRoutes(mux *http.ServeMux)` pointing to `h.handleHealthz`.
   - Because `BuildServeMux` registers `HealthHandler` on `rootMux`, Go `http.ServeMux` method+path specificity (`GET /api/v1/health`) takes precedence over the `/api/v1/` auth middleware subtree without bypassing auth for any other `/api/v1/` endpoint.
   - `contracts/api/` was left untouched (no unapproved OpenAPI schema alteration).

3. **`backend-go/internal/api/health_handler_test.go` & `backend-go/internal/api/router_test.go`:**
   - Replaced `TestHealthHandler_Healthz` with table-driven `TestHealthHandler_HealthEndpoints` covering both `GET /healthz` and `GET /api/v1/health` (`200 OK`, `Content-Type: application/json; charset=utf-8`, `{"status":"ok"}`) as well as `POST` method rejection (`405 Method Not Allowed`).
   - Updated `TestBuildServeMux_NilDependencies_HealthCheck` to verify both `/healthz` and `/api/v1/health` return `200 OK` unauthenticated through `BuildServeMux`, while `/api/v1/gateways` still returns `401 Unauthorized`.

---

## 2. Acceptance Criteria Matrix

| AC | Requirement | Evidence | Status |
|---|---|---|---|
| **AC1** | Pin builder stage to `golang:1.27.3-alpine` | `backend-go/Dockerfile` line 3 (`FROM golang:1.27.3-alpine AS builder`); verified `GOVERSION=go1.27.3`. | **PASS** |
| **AC2** | Pin runtime stage to explicit Alpine version tag | `backend-go/Dockerfile` line 13 (`FROM alpine:3.24.3`); verified `/etc/alpine-release` = `3.24.3` in built container. | **PASS** |
| **AC3** | Remove `RUN sed -i` step from `backend-go/Dockerfile` | `RUN sed -i` removed; Go source compiled verbatim in `docker build`. | **PASS** |
| **AC4** | Consistent health routing directly in `health_handler.go` with unit tests | Both `GET /healthz` and `GET /api/v1/health` registered in `health_handler.go` and tested in `health_handler_test.go` + `router_test.go`. | **PASS** |
| **AC5** | `go test ./...` passes and matches binary compiled inside `docker build` | `go vet ./...` and `go test ./...` exited `0` across all packages in `golang:1.27.3-alpine` (`GOTOOLCHAIN=local`). | **PASS** |
| **AC6** | `docker build` succeeds cleanly and `GET` healthcheck returns `200 OK` in container | `docker build --network=host` exited `0`; live container running as `uid=100(appuser) gid=101(appgroup)` returned `200 OK` `{"status":"ok"}` for both `/healthz` and `/api/v1/health`, `405` for `POST /healthz`, and `401` for unauthenticated `/api/v1/gateways`. | **PASS** |

---

## 3. Verification Commands & Observations

1. **Go formatting, vet, and full test suite (`golang:1.27.3-alpine`, `GOTOOLCHAIN=local`):**
   - `gofmt -l internal/api/` -> empty output (`PASS`). *(Note: untouched baseline file `internal/presence/rf_tracker.go` already fails repo-wide `gofmt -l .` on `main` and was left untouched per Issue #403 scope.)*
   - `go vet ./...` -> exit `0` (`PASS`).
   - `go test -v ./internal/api -run "TestHealthHandler|TestBuildServeMux_NilDependencies_HealthCheck"` -> exit `0` (`PASS`).
   - `go test ./...` inside `golang:1.27.3-alpine` -> exit `0`, all 13 tested packages `ok` (`cmd/server`, `internal/api`, `internal/app`, `internal/auth`, `internal/config`, `internal/domain`, `internal/jsonboundary`, `internal/mqtt`, `internal/presence`, `internal/realtime`, `internal/security`, `internal/storage`; `internal/auth/bcrypt` has no test files). *(Note on host environment: host `/usr/local/go/bin/go` is `go1.27.1` and host WSL2 drops SYNs to `127.0.0.1:5432` instead of `ECONNREFUSED`, causing `TestApp_New_PersistentMode_SubscriberInitialized` in `internal/app` to block when run directly on WSL2 host without Docker.)*

2. **Docker build & container runtime check:**
   - `docker build --network=host -t issue403-backend:verify backend-go` -> exit `0`. *(Note: default bridge `docker build` hit transient `proxy.golang.org` TCP resets in this WSL2 environment; `--network=host` resolved module fetches cleanly, consistent with `clients/web-dashboard` in `deploy/compose.yaml`.)*
   - Live container smoke test (`issue403-backend:verify`):
     - `id` -> `uid=100(appuser) gid=101(appgroup) groups=101(appgroup)`
     - `/etc/alpine-release` -> `3.24.3`
     - `GET /healthz` -> `HTTP/1.1 200 OK` `{"status":"ok"}`
     - `GET /api/v1/health` -> `HTTP/1.1 200 OK` `{"status":"ok"}`
     - `POST /healthz` -> `HTTP/1.1 405 Method Not Allowed`
     - `GET /api/v1/gateways` (unauth) -> `HTTP/1.1 401 Unauthorized`

3. **Compose & Contract Checks:**
   - `docker compose --env-file .env.example -f deploy/compose.yaml --profile fullstack config -q` -> exit `0`.
   - `python3 contracts/tests/check_contracts.py` -> exit `0` (`12 schemas, 40 MQTT cases, 18 WS cases, 15 REST operations`).
