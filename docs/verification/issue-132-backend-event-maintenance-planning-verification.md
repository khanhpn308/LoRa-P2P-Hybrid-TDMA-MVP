# Issue #132 Verification Report: Backend Event-Only Ingest, Durable Dedup, and Maintenance Planning

## 1. Executive Summary

This report documents the implementation, standards compliance, and test verification results for **Issue #132** (`[Migration][Backend] Event-only ingest, durable dedup and approved Maintenance planning (#125)`).

The backend delivery establishes:
1. **Event-Only & Deprecated Periodic Flow Handling** (`backend-go/internal/api/`):
   - Periodic telemetry access routes (`GET /api/v1/nodes/{node_id}/telemetry`) return HTTP `410 Gone` (`DEPRECATED_HISTORICAL`), enforcing the deprecation of periodic polling.
   - `GET /api/v1/alerts` supports cursor-based pagination (`cursor` and `limit`) returning `AlertPageDTO`.
   - `POST /api/v1/alerts/{alert_id}/acknowledge` provides operator workflow acknowledgment with idempotent conflict detection (`409 Conflict` on already-acknowledged alerts).
   - Strict 4-layer confirmation decoupling: UI acknowledgment modifies DB state only and **never emits an RF ACK** to the Node.
2. **Channel-Integrated TDMA Maintenance Schedule Planning & Guard** (`backend-go/internal/api/`):
   - Integrates with exclusive VN920 channel allocation rules established in #154 (`ChannelVerified: true`).
   - Enforces the invariant: `DB_ASSIGNED ≠ SCHEDULE_ACTIVE ≠ RF_TX_AUTHORIZED`.
   - Wires `ScheduleGuard` into `ChannelHandler`: prevents channel re-assignment or release when an active schedule exists (`ErrActiveScheduleOnChannel`, returning HTTP `409 Conflict`).
   - Reviews and approves staged schedules (`POST /api/v1/gateways/{gw_id}/schedules/{schedule_id}/review`).
   - Concurrency-safe in-memory reviews protected by `sync.RWMutex` (`TestScheduleHandler_ConcurrentAccess`).
3. **Durable Event Storage & Query Repository** (`backend-go/internal/storage/`):
   - Segregated `EventQueryRepository` interface extending `EventRepository` without breaking existing MQTT consumer dependencies.
   - Robust column scanning: selects Migration 000003 columns `event_ref, event_code, event_value` with complete null safety and exact data fidelity into `AlertDTO`.
   - Atomic acknowledgment using `SELECT ... FOR UPDATE` row locks.
   - Node health queries (`ListNodeHealth`) derived strictly from authenticated Node replies (`UP_HEALTH_REPLY 0x44`), NOT Gateway beacon transmissions.
4. **Comprehensive Real PostgreSQL Integration Test Suite** (`tests/integration/test_backend_event_schedule_postgres.py`):
   - Complete verification running against a live PostgreSQL 16 container (`postgres:16-alpine`) checking all 8 criteria.

---

## 2. Standards Compliance Matrix (Go Engineering Standard v2)

| Rule ID / Standard | Requirement | Implementation Evidence | Status |
| :--- | :--- | :--- | :--- |
| **G-ERR-001 / G-ERR-002** | Explicit error handling & sentinel errors | Explicit domain errors `ErrAlreadyAcknowledged`, `ErrActiveScheduleOnChannel` handled without bare panics | PASS |
| **G-SEC-001** | Bounded input validation & safety | Request bodies read with `io.LimitReader(r.Body, maxPayloadBytes+1)`, JSON decoded via `jsonboundary.DecodeObject`, identifiers validated via `domain.ValidateGatewayID` | PASS |
| **G-SEC-002** | Secure HTTP headers & CORS | Standard security headers injected on all HTTP handlers | PASS |
| **G-CONC-001** | Data race freedom | Full backend suite verified with Go race detector (`go test -count=1 -race ./...`), including `ScheduleHandler.reviews` mutex protection | PASS |
| **G-MOD-001** | Modular Monolith architecture | Storage abstractions cleanly segregated; `EventQueryRepository` encapsulates REST querying while `EventRepository` serves MQTT ingest | PASS |
| **G-SQL-001** | Concurrency-safe DB transactions & typed schema | Row-level locking `FOR UPDATE` in `AcknowledgeEvent`; clean scan of `event_ref`, `event_code`, `event_value` matching migration 000003 | PASS |
| **DEC-125-01** | Event-only ingest architecture | Periodic endpoints return HTTP 410 Gone; Node event stream deduplicated on `(gateway_id, node_id, event_ref)` | PASS |
| **DEC-125-02** | 4-layer confirmation separation | Gateway RF ACK (`0x42`) ≠ PUBACK ≠ DB commit ≠ Operator UI ACK | PASS |
| **DEC-154-01** | Channel assignment lifecycle | Validated VN920 channel presence before TDMA schedule generation; channel release guarded by active schedule presence | PASS |

---

## 3. Test Verification Results

### 3.1 Go Backend Unit & Race Suite (`go test -count=1 -race ./...`)
Toolchain: Go 1.27.1 (`/usr/local/go/bin/go`)

| Package | Duration | Status | Notes |
| :--- | :--- | :--- | :--- |
| `internal/api` | 1.050s | PASS | Alert, Schedule (w/ race test), Channel (w/ guard test), Node, Health HTTP handlers |
| `internal/storage` | 1.093s | PASS | Event storage, query methods, channel repo mocks |
| `internal/mqtt` | 1.049s | PASS | Event consumer backward compatibility preserved |
| `internal/domain` | 1.032s | PASS | Validation logic and models |
| `internal/scheduler` | 1.166s | PASS | TDMA planner constraints & lifecycle |
| `internal/security` | 1.026s | PASS | Key storage and auth |
| `internal/jsonboundary` | 1.024s | PASS | Safe JSON parsing |

### 3.2 Static Checks
- `go vet ./...`: PASS (0 warnings)
- `gofmt -l .`: PASS (0 unformatted files)

### 3.3 Real PostgreSQL Container Integration Suite
Executed against real PostgreSQL 16 container (`postgres:16-alpine`):

| Test Case | Description | Duration | Status |
| :--- | :--- | :--- | :--- |
| `test_01_migrations_and_catalogue` | Applies 000001, 000002, 000003 migrations; verifies VN920_V1 11-channel catalogue | ~1.2s | PASS |
| `test_02_exclusive_channel_allocation_and_conflict` | Allocates CH00 exclusively to gw-alpha; verifies second gateway claim fails with unique constraint violation | ~1.3s | PASS |
| `test_03_state_hierarchy_isolation` | Proves state hierarchy invariant: DB_ASSIGNED ≠ SCHEDULE_ACTIVE ≠ RF_TX_AUTHORIZED | ~1.1s | PASS |
| `test_04_discrete_event_ingest_and_deduplication` | Ingests UP_EVENT; verifies duplicate delivery returns DEDUPLICATED idempotently | ~1.3s | PASS |
| `test_05_conflicting_payload_quarantine` | Ingests event with same event_id but different payload SHA-256; verifies quarantine record creation | ~1.2s | PASS |
| `test_06_four_layer_confirmation_ui_acknowledgment` | Verifies operator UI ack updates DB ack_status; verifies duplicate ack fails; verifies RF ACK not emitted | ~1.4s | PASS |
| `test_07_node_health_from_authenticated_node_replies` | Verifies node health derives strictly from authenticated UP_HEALTH_REPLY (0x44) | ~1.2s | PASS |
| `test_08_container_restart_persistence` | Verifies database state and deduplication survive container stop and restart | ~1.5s | PASS |

Additional integration regressions:
- `test_event_storage_postgres.py`: 8/8 PASS
- `test_mqtt_join_hello_postgres.py`: 3/3 PASS

### 3.4 Repository Contract & Lint Validations
- `contracts/tests/check_contracts.py`: PASS (11 schemas, 33 MQTT cases, 18 WS cases, 18 REST operations)
- `scripts/verify_structure.py`: PASS (Monorepo directory, CMake, versions)
- `tests/agent_harness`: PASS (351/351 test cases)

---

## 4. Hardware & RF Boundary

- Physical HIL Bench / RF Transmission: Gate G3 / RF HIL remains **`NOT_VERIFIED`** (pending physical bench setup #169).
- No RF signals were emitted; no hardware flashed.
- Client authorization and confirmation boundaries are enforced by Backend Go services.
