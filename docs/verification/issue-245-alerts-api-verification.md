# Alerts Query & Operator Acknowledgment REST Endpoints Verification Report

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`  
> **Source Issue:** [#245](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/245)  
> **Component:** `backend-go/internal/domain`, `backend-go/internal/storage`, `backend-go/internal/api`  
> **Toolchain:** Go 1.27.3 (`go version go1.27.3 linux/amd64`), Python 3.12.3  
> **Governing Authorities:** OpenAPI 3.0.3 (`contracts/api/openapi.yaml`), `contracts/api/contract-semantics.md` §1.2, DEC-127-01, DEC-127-04, Go Backend Engineering Standard v2  

---

## 1. Executive Summary

Issue #245 delivers the HTTP REST API endpoints for listing alerts (`GET /api/v1/alerts`) and recording operator workflow acknowledgments (`POST /api/v1/alerts/{alert_id}/acknowledge`) in the Go Backend:
- **Domain DTOs (`backend-go/internal/domain/alert.go`):** Defined `AlertView`, `AlertPage`, and `AlertFilter` conforming strictly to OpenAPI 3.0.3 components `Alert` and `AlertPage`. Implemented helper `EventToAlertView` and strict filter validator `AlertFilter.Validate()`.
- **Transactional Database Repository (`backend-go/internal/storage/event_storage.go`):**
  - `ListAlerts(ctx, filter)`: Cursor-paginated query ordered deterministically by `id DESC`. Supports optional filtering by `severity`, `node_id`, `gateway_id`, and `ack_status`. Dynamically bounds limits (1..100, default 50) and decodes/calculates opaque cursor IDs.
  - `AcknowledgeAlert(ctx, alertID, acknowledgedBy)`: Atomic row-locked PostgreSQL transaction (`SELECT ... FOR UPDATE`). Updates `ack_status = 'ACKNOWLEDGED'`, `acknowledged_at = CURRENT_TIMESTAMP`, and `acknowledged_by`. Idempotent: re-acknowledging an already acknowledged alert safely returns the record without error. Returns `ErrAlertNotFound` (HTTP 404) if the alert does not exist.
- **REST API Handler (`backend-go/internal/api/alert_handler.go`):**
  - `GET /api/v1/alerts`: Parses query parameters, validates bounds/enums, enforces RBAC roles `VIEWER`, `OPERATOR`, `ADMIN` (HTTP 401 on missing/invalid token), and writes JSON `AlertPage`.
  - `POST /api/v1/alerts/{alert_id}/acknowledge`: Validates numeric decimal uint64 `alert_id` using regex `^(0|[1-9][0-9]{0,19})$` (HTTP 400 on malformed ID), enforces RBAC roles `OPERATOR`, `ADMIN` (HTTP 401 on unauthenticated, HTTP 403 Forbidden for `VIEWER`), supports custom operator identification in optional request body, and writes JSON `AlertView`. Strictly an operator workflow transition; never triggers any RF or MQTT action.
- **Unit & Regression Testing:** Comprehensive table-driven tests across domain, storage, and API handlers achieving 100% test pass.

---

## 2. API Contract & Architectural Invariants

### 2.1 Confirmation Layers (§1.2 `contracts/api/contract-semantics.md`)

| Layer | Protocol / Mechanism | Actor | Scope |
|---|---|---|---|
| **Layer 1** | Radio RF ACK (`0x42`) | Gateway Master SX1276 | Direct LoRa RF link down to Node |
| **Layer 2** | MQTT `PUBACK` (QoS 1) | Mosquitto Broker | Gateway-to-Backend wire delivery |
| **Layer 3** | DB Commit & Idempotency | Go Backend & PostgreSQL | Deduplication and persistence in `events` |
| **Layer 4** | UI / Operator Acknowledgment | Web/Mobile REST API | Operator triage transition (`POST /api/v1/alerts/{id}/ack`) |

**Critical Invariant:** `POST /api/v1/alerts/{alert_id}/acknowledge` is strictly Layer 4. It updates the database record state and returns HTTP 200 to the client. It never dispatches an MQTT command or triggers a Gateway RF ACK.

### 2.2 Endpoints Specification

1. **`GET /api/v1/alerts`**
   - **Tags:** `alerts`
   - **RBAC Roles:** `VIEWER`, `OPERATOR`, `ADMIN`
   - **Query Parameters:** `cursor` (string decimal), `limit` (integer 1..100, default 50), `severity` (`P0_EMERGENCY`, `P1_HIGH`, `P2_MEDIUM`, `P3_NORMAL`), `node_id` (1..254), `gateway_id` (1..32 chars), `ack_status` (`UNACKNOWLEDGED`, `ACKNOWLEDGED`).
   - **Responses:** `200 OK` (`AlertPage`), `401 Unauthorized`, `422 Unprocessable Entity`.

2. **`POST /api/v1/alerts/{alert_id}/acknowledge`**
   - **Tags:** `alerts`
   - **RBAC Roles:** `OPERATOR`, `ADMIN` (role `VIEWER` rejected with HTTP 403 Forbidden)
   - **Path Parameters:** `alert_id` (regex `^(0|[1-9][0-9]{0,19})$`)
   - **Request Body (optional):** `{"acknowledged_by": "operator_name"}`
   - **Responses:** `200 OK` (`Alert`), `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.

---

## 3. Verification Evidence & Test Receipts

### 3.1 OpenAPI Contract Validation
```bash
/usr/bin/python3 contracts/tests/check_contracts.py
```
**Output:**
```text
PASS ALERT-VALID (schema=True)
PASS ALERT-SEVERITY-INVALID (schema=False)
PASS OpenAPI semantic spec + 19 HTTP operations
PASS: 11 schemas, 33 MQTT cases, 18 WS cases, 19 REST operations
NOT VERIFIED: device/auth/nonce/timing/RF, MQTT roundtrip, HTTP/WSS implementation.
```
Exit code: `0`.

### 3.2 Domain Model Tests (`alert_test.go`)
```bash
cd backend-go && go test -v ./internal/domain -run TestAlert
```
**Output:**
```text
=== RUN   TestAlertFilter_Validate
=== RUN   TestAlertFilter_Validate/valid_empty_filter
=== RUN   TestAlertFilter_Validate/valid_populated_filter
=== RUN   TestAlertFilter_Validate/invalid_negative_limit
=== RUN   TestAlertFilter_Validate/invalid_excessive_limit
=== RUN   TestAlertFilter_Validate/invalid_severity_enum
=== RUN   TestAlertFilter_Validate/invalid_node_id_zero
=== RUN   TestAlertFilter_Validate/valid_node_id_max_254
=== RUN   TestAlertFilter_Validate/invalid_node_id_255
=== RUN   TestAlertFilter_Validate/invalid_ack_status_enum
=== RUN   TestAlertFilter_Validate/valid_ack_status_acknowledged
--- PASS: TestAlertFilter_Validate (0.00s)
=== RUN   TestEventToAlertView
--- PASS: TestEventToAlertView (0.00s)
PASS
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain	0.007s
```
Exit code: `0`.

### 3.3 Storage Repository Tests (`event_storage_test.go`)
```bash
cd backend-go && go test -v ./internal/storage -run "TestListAlerts|TestAcknowledgeAlert"
```
**Output:**
```text
=== RUN   TestListAlerts_Table
=== RUN   TestListAlerts_Table/positive_default_list
=== RUN   TestListAlerts_Table/positive_filtered_by_severity_and_node_id
=== RUN   TestListAlerts_Table/empty_list_when_no_events
=== RUN   TestListAlerts_Table/invalid_limit_negative
=== RUN   TestListAlerts_Table/invalid_limit_excessive
=== RUN   TestListAlerts_Table/invalid_severity_enum
=== RUN   TestListAlerts_Table/invalid_node_id_zero
=== RUN   TestListAlerts_Table/invalid_cursor_non-decimal
=== RUN   TestListAlerts_Table/valid_decimal_cursor
--- PASS: TestListAlerts_Table (0.00s)
=== RUN   TestAcknowledgeAlert_Table
=== RUN   TestAcknowledgeAlert_Table/positive_initial_acknowledgment
=== RUN   TestAcknowledgeAlert_Table/idempotent_re-acknowledgment_on_already_acknowledged_alert
=== RUN   TestAcknowledgeAlert_Table/alert_not_found_returns_ErrAlertNotFound
--- PASS: TestAcknowledgeAlert_Table (0.00s)
PASS
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage	0.005s
```
Exit code: `0`.

### 3.4 REST API Handler Unit & RBAC Tests (`alert_handler_test.go`)
```bash
cd backend-go && go test -v ./internal/api -run "TestAlertHandler"
```
**Output:**
```text
=== RUN   TestAlertHandler_ListAlerts_Table
=== RUN   TestAlertHandler_ListAlerts_Table/positive_default_first_page
=== RUN   TestAlertHandler_ListAlerts_Table/positive_with_limit_10
=== RUN   TestAlertHandler_ListAlerts_Table/positive_filtered_by_severity
=== RUN   TestAlertHandler_ListAlerts_Table/positive_filtered_by_node_id
=== RUN   TestAlertHandler_ListAlerts_Table/positive_filtered_by_gateway_id
=== RUN   TestAlertHandler_ListAlerts_Table/positive_filtered_by_ack_status
=== RUN   TestAlertHandler_ListAlerts_Table/pagination_with_cursor_and_limit=1
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_negative_limit
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_zero_limit
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_excessive_limit
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_non-numeric_limit
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_negative_cursor
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_non-numeric_cursor
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_severity_enum
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_node_id_zero
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_node_id_255
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_gateway_id_with_special_characters
=== RUN   TestAlertHandler_ListAlerts_Table/invalid_ack_status_enum
--- PASS: TestAlertHandler_ListAlerts_Table (0.00s)
=== RUN   TestAlertHandler_AcknowledgeAlert_Table
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/positive_initial_acknowledgment
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/idempotent_re-acknowledgment_on_already_acknowledged_alert
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/alert_not_found_returns_404
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/malformed_alert_id_alphabetic
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/malformed_alert_id_with_leading_zero
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/malformed_alert_id_negative
=== RUN   TestAlertHandler_AcknowledgeAlert_Table/malformed_JSON_body_returns_400
--- PASS: TestAlertHandler_AcknowledgeAlert_Table (0.00s)
=== RUN   TestAlertHandler_RBAC_Table
=== RUN   TestAlertHandler_RBAC_Table/GET_/alerts_missing_token_->_401
=== RUN   TestAlertHandler_RBAC_Table/GET_/alerts_invalid_token_->_401
=== RUN   TestAlertHandler_RBAC_Table/GET_/alerts_VIEWER_token_->_200
=== RUN   TestAlertHandler_RBAC_Table/GET_/alerts_OPERATOR_token_->_200
=== RUN   TestAlertHandler_RBAC_Table/GET_/alerts_ADMIN_token_->_200
=== RUN   TestAlertHandler_RBAC_Table/POST_/alerts/{id}/ack_missing_token_->_401
=== RUN   TestAlertHandler_RBAC_Table/POST_/alerts/{id}/ack_invalid_token_->_401
=== RUN   TestAlertHandler_RBAC_Table/POST_/alerts/{id}/ack_VIEWER_token_->_403_Forbidden
=== RUN   TestAlertHandler_RBAC_Table/POST_/alerts/{id}/ack_OPERATOR_token_->_200_OK
=== RUN   TestAlertHandler_RBAC_Table/POST_/alerts/{id}/ack_ADMIN_token_->_200_OK
--- PASS: TestAlertHandler_RBAC_Table (0.00s)
PASS
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api	0.055s
```
Exit code: `0`.

### 3.5 Full Backend Regression Suite Execution (Race Detector)
```bash
cd backend-go && go test -race ./...
```
**Output:**
```text
?   	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/cmd/server	[no test files]
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api	1.174s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain	1.106s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary	1.068s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt	1.121s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/scheduler	1.206s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security	1.061s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage	1.173s
```
Exit code: `0`.

### 3.6 Code Formatting (`gofmt`)
```bash
cd backend-go && gofmt -l .
```
Exit code: `0` (zero unformatted files).

---

## 4. Traceability Matrix

| Requirement / Standard Rule | Implementation Artifact | Verification Result |
|---|---|---|
| OpenAPI Schemas `Alert`, `AlertPage` (`contracts/api/openapi.yaml`) | `domain/alert.go` | `check_contracts.py` PASS |
| Clean Domain Boundaries (`GB-001`, `GB-002`) | `backend-go/internal/domain/alert.go` | Zero HTTP/SQL imports in domain package |
| Clean Code Style & Idioms (`GGS-001`, `GGS-006`, `GGS-008`) | Handlers & Storage repository | `gofmt` PASS, explicit error returns |
| Strict Input Validation (`SE-002`) | `alert_handler.go` (`alertIDRegex`, enums) | HTTP 400 & 422 test cases PASS |
| Zero Secret / Token Logging (`SE-003`) | `alert_handler.go` | No token or sensitive payload logged |
| RBAC Authorization Enforcement (`SE-004`) | `alert_handler.go` | HTTP 401 & 403 test cases PASS |
| Transaction Safety & Row Locks (`DB-001`, `DB-003`) | `event_storage.go` (`FOR UPDATE` row lock) | Concurrent safety & transaction rollback PASS |
| Parameterized SQL Queries (`DB-002`) | `event_storage.go` | Parameterized `$1, $2, ...` queries PASS |
| Context Propagation (`RT-001`) | `event_storage.go` | `Context` passed to all database queries |
| Table-Driven Tests (`TS-001`, `QG-001`) | `alert_handler_test.go`, `event_storage_test.go` | 100% test pass across all cases |
