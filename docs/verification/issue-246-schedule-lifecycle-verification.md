# TDMA Schedule Lifecycle REST API, MQTT Dispatcher & PostgreSQL Storage Verification Report

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#246](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/246)
> **Component:** `backend-go` (`api`, `mqtt`, `storage`, `migrations`, `cmd/server`)
> **Toolchain:** Go 1.27.3 (`go version go1.27.3 linux/amd64`), Python 3.12.3
> **Governing Authorities:** OpenAPI 3.0.3 (`contracts/api/openapi.yaml`), `contracts/api/contract-semantics.md`, `contracts/mqtt/topics.md`, `contracts/mqtt/schemas/schedule.schema.json`, `contracts/mqtt/schemas/schedule-ack.schema.json`, DEC-MH-05 (`contracts/OPEN_DECISIONS.md`), Issue #154, Go Backend Engineering Standard v2

---

## 1. Executive Summary

Issue #246 integrates the complete TDMA Schedule Lifecycle into the Go Backend, bridging the core planner (`internal/scheduler`) to the external API, MQTT 5.0 transport, and persistent PostgreSQL database:

1. **PostgreSQL Schema Migration & Storage (`000004_schedule_storage.up.sql`, `internal/storage/schedule_storage.go`):**
   - Implements Migration 000004 defining tables: `schedules`, `schedule_slots`, `active_gateway_schedules`, and `schedule_migration_transactions`.
   - Implements `PostgresScheduleStorage` satisfying `scheduler.ScheduleRepository` with atomic transactions (`BEGIN ... COMMIT`), parameterized queries, and row-level locks (`SELECT ... FOR UPDATE`).
   - Persists schedule proposals, slot geometry, active schedules, review states, and 100% READY migration transactions.

2. **HTTP REST Endpoints (`internal/api/schedule_handler.go`):**
   - `POST /api/v1/gateways/{gw_id}/schedules/generate`: PROPOSED candidate profile generation with `ADMIN` role check and active VN920 channel allocation prerequisite; returns HTTP 202 Accepted.
   - `GET /api/v1/gateways/{gw_id}/schedules/{schedule_id}`: Schedule lifecycle state inspection with RBAC authorization (`ADMIN`, `OPERATOR`, `VIEWER`); returns HTTP 200 OK.
   - `POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/review`: Human operator review recording (`APPROVED` or `REJECTED`) with `ADMIN` role check; returns HTTP 200 OK without triggering RF transmission.
   - `POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests`: Asynchronous staging dispatch to Gateway with `ADMIN` role check, mandatory `X-Idempotency-Key` header, prerequisite `review_state == APPROVED` check (HTTP 409 if unapproved), active channel allocation check (HTTP 409 if no channel assigned), and expected version verification (HTTP 409 if mismatched); returns HTTP 202 Accepted.

3. **MQTT 5.0 Schedule Dispatcher & Ack Consumer (`internal/mqtt/`):**
   - `ScheduleDispatcher` (`internal/mqtt/schedule_dispatcher.go`): Constructs JSON compliant with `schedule.schema.json`, calculates `Message Expiry Interval = floor(expires_at - now)` in whole seconds, and publishes to `iot/v1/gw/{gateway_id}/downlink/schedule` with QoS 1 and Retain=false. Rejects schedules with <1s remaining expiry.
   - `ScheduleAckConsumer` (`internal/mqtt/schedule_consumer.go`): Ingests messages from `iot/v1/gw/+/uplink/schedule-ack`, validates JSON schema (`schedule-ack.schema.json`), validates semantic bindings (`event_id == gw:epoch:seq`, topic gateway match), and forwards reports to `LifecycleEngine`.
   - Strict 4-layer confirmation invariant (`MQ-009`): `STAGE_ACK` records staging only and **never promotes schedule to ACTIVE**; transition to `ACTIVE` occurs **only upon verified `ACTIVE_REPORT`**.

4. **Composition Root (`cmd/server/main.go`):**
   - Explicit composition root wiring `PostgresScheduleStorage`, `PostgresChannelRepository`, `Planner`, `ScheduleDispatcher`, `HealthHandler`, and `ScheduleHandler`.
   - Provides graceful HTTP server shutdown on SIGINT/SIGTERM.

---

## 2. Standards Compliance Matrix (Go Backend Engineering Standard v2)

| Rule ID | Category | Requirement | Implementation Evidence | Status |
| :--- | :--- | :--- | :--- | :--- |
| **AR-001** | Architecture | Modular monolith boundaries | Clean isolation between `internal/api`, `internal/storage`, `internal/mqtt`, and `internal/scheduler` | **PASS** |
| **AR-002** | Architecture | Explicit composition root | Handlers, storage repositories, planner, and dispatcher wired explicitly in `cmd/server/main.go` | **PASS** |
| **AR-004** | Architecture | Clean dependency direction | `internal/scheduler` domain contains zero HTTP/MQTT dependencies; contracts passed via interfaces | **PASS** |
| **GGS-001** | Style | gofmt formatting | Clean `gofmt -l .` with zero diffs | **PASS** |
| **GGS-006** | Style | Explicit error handling | All errors checked and wrapped; zero panics or discarded errors | **PASS** |
| **GGS-008** | Style | context.Context as 1st param | Every storage and API method accepts `ctx context.Context` as first parameter | **PASS** |
| **SE-002** | Security | Input sanitization & regex | Path values sanitized via `domain.ValidateGatewayID` and `scheduleIDRegex`; payload bounded with `io.LimitReader` and `jsonboundary` | **PASS** |
| **SE-003** | Security | Zero secret leakage in logs | Zero cryptographic keys, tokens, or hashes leaked in application logs or test output | **PASS** |
| **SE-004** | Security | RBAC enforcement | `ADMIN` enforced on `/generate`, `/review`, and `/activation-requests`; `VIEWER` permitted read-only | **PASS** |
| **MQ-001** | MQTT | Canonical topic namespace | Publishes strictly to `iot/v1/gw/{id}/downlink/schedule`; subscribes to `iot/v1/gw/+/uplink/schedule-ack` | **PASS** |
| **MQ-004** | MQTT | Retain=false & Message Expiry | Enforced `Retain=false`, `QoS=1`, and `Message Expiry Interval = floor(expires_at - now)`; rejects expiry < 1s | **PASS** |
| **MQ-009** | MQTT | STAGED -> ACTIVE transition | `STAGE_ACK` never advances to `ACTIVE`; only verified `ACTIVE_REPORT` advances state to `ACTIVE` | **PASS** |
| **DB-001** | Database | Transaction safety | All multi-row updates execute inside `s.db.BeginTx(ctx, ...)` with deferred `Rollback()` | **PASS** |
| **DB-002** | Database | Parameterized queries | 100% of SQL statements use parameterized placeholders (`$1, $2, ...`) | **PASS** |
| **DB-003** | Database | Safe row locks | Row lock `SELECT ... FOR UPDATE` utilized during terminal decision recording | **PASS** |
| **QG-001** | Quality | 100% unit test pass | All unit and race detector tests pass across all packages with 0 failures | **PASS** |
| **TS-001** | Testing | Table-driven tests | Comprehensive positive, negative, boundary, and idempotency table-driven tests | **PASS** |

---

## 3. Test Verification Results

### 3.1 Go Backend Race Suite (`go test -v -race ./...`)
```bash
cd backend-go && go test -v -race ./...
```
**Output Summary:**
```text
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api	        1.085s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain	        1.018s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary	1.016s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt	        1.045s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler	1.198s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security	1.012s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage	    1.159s
```
- **Total Packages:** 7 packages tested
- **Pass Rate:** 100% PASS
- **Data Races Detected:** 0

### 3.2 Contract Validation Suite (`contracts/tests/check_contracts.py`)
```bash
PYTHONPATH=/home/khanh/.local/lib/python3.12/site-packages python3 contracts/tests/check_contracts.py
```
**Output:**
```text
PASS OpenAPI semantic spec + 19 HTTP operations
PASS: 11 schemas, 33 MQTT cases, 18 WS cases, 19 REST operations
NOT VERIFIED: device/auth/nonce/timing/RF, MQTT roundtrip, HTTP/WSS implementation.
```
- Exit code: `0`

### 3.3 Static Linter & Formatting
- `go vet ./...`: PASS (0 warnings)
- `gofmt -l .`: PASS (0 unformatted files)

---

## 4. Acceptance Criteria Verification Traceability

| Acceptance Criteria | Description | Verification Method | Status |
| :--- | :--- | :--- | :--- |
| **AC1** | Migration `000004_schedule_storage.up.sql` and `PostgresScheduleStorage` | `TestPostgresScheduleStorage_*` covering save, get, slots, active schedule upsert, and transactions | **PASS** |
| **AC2** | `ScheduleHandler` REST endpoints (`/generate`, `/{id}`, `/review`, `/activation-requests`) with RBAC & idempotency | `TestScheduleHandler_ActivationRequest_Table`, `TestScheduleHandler_ActivationRequest_Idempotency`, `TestScheduleHandler_RBAC_Roles` | **PASS** |
| **AC3** | MQTT 5.0 `ScheduleDispatcher` (`downlink/schedule`) & `ScheduleAckConsumer` (`uplink/schedule-ack`) | `TestScheduleDispatcher_DispatchSchedule_Table`, `TestScheduleAckConsumer_HandleMessage_Table` | **PASS** |
| **AC4** | Unit & Integration Testing (positive, negative, unapproved 409, channel missing 409, STAGE_ACK vs ACTIVE_REPORT) | Table-driven test suites in `schedule_handler_test.go`, `schedule_dispatcher_test.go`, `schedule_consumer_test.go`, `schedule_storage_test.go` | **PASS** |
| **AC5** | Non-regression, race detector, contract validation, and verification dossier | `go test -v -race ./...`, `check_contracts.py`, verification dossier in `docs/verification/` | **PASS** |

---

## 5. Hardware / RF Boundary & Human Decisions Reserved

- **Physical RF / HIL Gate G3:** Local mock and simulated environments verified; live RF transmission and hardware flashing remain **`NOT_VERIFIED`** pending physical lab testbench setup (#169).
- **No Direct Push to main:** Implementation developed on dedicated feature branch `feature/246-schedule-lifecycle-api-mqtt-storage`.
- **Merge Enforcement:** Awaiting human peer review and merge approval.
