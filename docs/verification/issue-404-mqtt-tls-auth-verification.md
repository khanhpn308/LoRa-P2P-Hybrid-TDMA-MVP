# Issue #404 Verification — MQTT TLS Client Authentication & Removal of Hardcoded LAN Fallback

- **Issue:** `#404` (`[GO][Security] Support MQTT TLS client authentication and remove hardcoded LAN fallback`)
- **Base Commit:** `aec70071774e0eb2607eaea8d297d11782ad9c05`
- **Branch:** `feature/404-mqtt-tls-auth`
- **Toolchain:** `go version go1.27.3 linux/amd64` (`go env GOVERSION = go1.27.3`), `Docker Compose version v5.5.1`
- **Status:** `PARTIAL / READY_FOR_HUMAN_SECURITY_REVIEW` (`ai:human-audit-req` pending)

## Summary of Changes

1. **`backend-go/internal/config/config.go` & `config_test.go`**
   - Added MQTT TLS/auth fields (`MQTTTLSEnabled`, `MQTTTLSCAFile`, `MQTTTLSCertFile`, `MQTTTLSKeyFile`, `MQTTTLSServerName`, `MQTTUsername`, `MQTTPassword`) parsed from `MQTT_TLS_ENABLED`, `MQTT_TLS_CA_FILE`, `MQTT_TLS_CERT_FILE`, `MQTT_TLS_KEY_FILE`, `MQTT_TLS_SERVER_NAME`, `MQTT_USERNAME`, `MQTT_PASSWORD`.
   - Invalid `MQTT_TLS_ENABLED` values fail closed (`ErrInvalidMQTTConfig`) rather than silently disabling TLS.
   - `ResolveMQTTBrokerURIWithScheme` / `ResolveMQTTBrokerURI` resolve `tls://` (default port `8883`) when TLS is enabled and `tcp://` (default port `1883`) otherwise.
   - Removed the hardcoded `192.168.88.113` LAN IP fallback from `ResolveMQTTBrokerURI`; unresolved `mqtt-dev` now returns `ErrUnresolvedMQTTHost`.
   - Added `BuildMQTTTLSConfig()` enforcing `MinVersion: tls.VersionTLS12`, `InsecureSkipVerify: false`, required valid PEM CA cert, paired client cert/key validation for mTLS, and fail-closed checks for missing/unreadable/mismatched files.
   - Preserved `Config.String()` redaction via `RedactURI` and boolean `*Set` flags (no passwords or private keys logged).

2. **`backend-go/internal/mqtt/tls.go`, `subscriber.go`, `tls_test.go`**
   - Added `ClientAuthOptions`, `WithTLSConfig`, `WithClientAuth`, `WithCredentials`, and `BuildTLSConfig` in `internal/mqtt/tls.go`.
   - `GatewayStatusSubscriber.Start` calls `buildClientOptions()` before connecting or starting background goroutines, failing closed if `tls://` lacks valid CA/TLS settings, if `tcp://` is given TLS config (preventing silent downgrade), or if password is supplied without username.
   - Redacted broker URIs in subscriber connection logs (`redactBrokerURI`).
   - Added unit tests and an in-process `tls.Listen` (`tls.RequireAndVerifyClientCert`) mTLS handshake test (`TestSubscriber_RealTLSHandshake_mTLS`).

3. **`backend-go/internal/app/wiring.go`, `lifecycle.go`, `app_test.go`**
   - `app.New` propagates errors from `cfg.ResolveMQTTBrokerURI()` and `cfg.BuildMQTTTLSConfig()`, closing DB handles and failing closed on startup misconfiguration.
   - `lifecycle.go` logs redacted broker URI via `config.RedactURI`.
   - Added tests for unresolved host failure, missing TLS CA failure, and valid TLS startup; updated fake DB/MQTT test DSNs to use closed ephemeral local ports (`connect_timeout=1`) to avoid host-specific firewall SYN-drop stalls.

4. **Deployment & Configuration (`deploy/compose.yaml`, `deploy/mosquitto/acl`, `.env.example`, `deploy/README.md`)**
   - Configured `backend` service in `deploy/compose.yaml` to connect to `mqtt-tls:8883` with `MQTT_TLS_ENABLED=true` and read-only `/run/secrets/mqtt` bind mount (`${MQTT_BACKEND_CERT_DIR:-./secrets/backend}`).
   - Updated `deploy/mosquitto/acl` with active V2 uplink/downlink topics used by `GatewayStatusSubscriber`.
   - Documented TLS/mTLS and optional username/password environment variables in `.env.example` and `deploy/README.md` (including `subjectAltName=DNS:mqtt-tls,DNS:localhost,IP:127.0.0.1` and isolated `deploy/secrets/backend` permissions).

## Observed Verification Results

| Check | Command | Result | Notes |
|---|---|---|---|
| Go formatting (changed pkgs) | `test -z "$(gofmt -l internal/config internal/mqtt internal/app)"` | **PASS** (exit 0) | Pre-existing `internal/presence/rf_tracker.go` (outside scope) remains unformatted on baseline. |
| Go vet | `go vet ./...` | **PASS** (exit 0) | Clean across `backend-go`. |
| Go race tests (target pkgs) | `go test -race -count=1 ./internal/config/... ./internal/mqtt/... ./internal/app/...` | **PASS** (exit 0) | Includes in-process mTLS handshake test and fail-closed tests. |
| Full Go test suite | `go test ./...` | **PASS** (exit 0) | All backend Go packages passed. |
| Go server build | `go build -o /tmp/backend-server-404 ./cmd/server` | **PASS** (exit 0) | Binary removed after verification. |
| Compose validation | `docker compose --env-file .env.example -f deploy/compose.yaml [--profile tls --profile fullstack / --profile dev-insecure --profile fullstack] config -q` | **PASS** (exit 0) | All 3 profile combinations validated. |
| Integration security unit tests | `python3 -m unittest discover -s tests/integration -p test_verify_no_secrets.py -v` & `test_infra_security.py -v` | **PASS** (7 + 11 tests, exit 0) | All mocked/unit checks passed. |
| Diff hygiene | `git diff --check aec70071774e0eb2607eaea8d297d11782ad9c05` | **PASS** (exit 0) | No whitespace/conflict markers. |
| Secret scan (changed files & diff) | `verify_no_secrets.forbidden_path` & `contains_secret` on all changed files + added diff lines | **PASS** | Zero secrets in Issue #404 files/diff. Full-repo `python3 scripts/verify_no_secrets.py` exited 1 due to pre-existing baseline matches in untouched `internal/auth/service_test.go`, `clients/web-dashboard/*`, and `scripts/agent_harness/quality_gates.py`. |

## Remaining `NOT_VERIFIED` / Pending Items

- **Live Docker `backend` <-> `mqtt-tls` E2E run:** `NOT_VERIFIED` (Docker Compose `config -q` and Go in-process `tls.Listen` mTLS handshake ran; full container-to-container `backend` + `mqtt-tls` + `postgres` runtime test was not executed).
- **Full `tests/integration/test_local_infra.py` Docker run:** `NOT_RUN` (baseline `mqtt-dev` in `compose.yaml` binds `0.0.0.0:1883` from an earlier LAN PR outside Issue #404 scope).
- **Human Security Review (`ai:human-audit-req`):** `PENDING` (required before merge per `AGENTS.md` and Issue #404).
