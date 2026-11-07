# Device Registration & K_JOIN Provisioning REST Endpoint Verification Report

> **Document Status:** `IMPLEMENTED_AND_BUILD_VERIFIED`
> **Source Issue:** [#242](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/242)
> **Component:** `contracts/api`, `backend-go/internal/api`, `backend-go/internal/storage`
> **Toolchain:** Go 1.27.3 (`go version go1.27.3 linux/amd64`), Python 3.12.3
> **Governing Authorities:** DEC-SEC-01 (`contracts/OPEN_DECISIONS.md`), ADR-0002, Go Backend Engineering Standard v2

---

## 1. Executive Summary

Issue #242 implements the REST API endpoint `POST /api/v1/devices/provision` for the Go Backend to register devices and securely provision root keys ($K_{\text{JOIN}}$):
- **Contract Specification (`contracts/api/openapi.yaml`):** Endpoint defined under tags `["nodes", "provisioning"]`, restricted to `x-roles: ["ADMIN"]`. Request body strictly typed (`DeviceProvisionRequest`), returning `201 Created` (`DeviceProvisionResponse`) without ever echoing raw or wrapped keys. Negative responses `400`, `401`, `403`, `409` fully specified.
- **REST API Handler (`backend-go/internal/api/provision_handler.go`):** Strict deserialization using `jsonboundary.DecodeObject`, input sanitization (12-char lowercase hexadecimal MAC, 32-byte binary CSPRNG $K_{\text{JOIN}}$ from 64-char hex or 32-byte Base64), RBAC `ADMIN` token authorization, authenticated key wrapping via AES-256-GCM with a unique 12-byte CSPRNG nonce, immediate in-memory zeroization of raw key material, and audit logging with zero secret leakage.
- **Transactional Database Repository (`backend-go/internal/storage/provision_storage.go`):** Atomic PostgreSQL transaction (`BEGIN ... COMMIT`) executing:
  1. `INSERT INTO devices (network_id, device_mac, status) VALUES ($1, $2, 'ACTIVE') ON CONFLICT DO NOTHING;`
  2. Row-level lock (`SELECT ... FOR UPDATE`) checking active device status and ensuring no active generation already exists.
  3. `INSERT INTO device_generations (network_id, device_mac, generation, k_join_wrapped, is_active) VALUES ($1, $2, $3, $4, TRUE);`
  4. `INSERT INTO device_join_counters (network_id, device_mac, generation, last_join_counter) VALUES ($1, $2, $3, $4);`
- **Unit Test Coverage:** Comprehensive table-driven tests (`provision_handler_test.go`, `provision_storage_test.go`) achieving 100% test pass and high statement coverage across positive flows, negative edge cases, RBAC roles, conflict handling, and tamper detection.

---

## 2. API Contract Specification

### 2.1 Endpoint Summary

- **Method & Path:** `POST /api/v1/devices/provision`
- **Tags:** `nodes`, `provisioning`
- **Security:** `bearerAuth` required, `x-roles: ["ADMIN"]`

### 2.2 Request Schema (`DeviceProvisionRequest`)

| Field | Type | Required | Constraints / Format | Description |
|---|---|---|---|---|
| `network_id` | integer (int64) | Yes | Minimum: 1 | Network identifier |
| `device_mac` | string | Yes | Pattern `^[0-9a-f]{12}$` | Canonical 12 lowercase hexadecimal characters (6 bytes) |
| `k_join` | string | Yes | Pattern `^(?:[0-9a-fA-F]{64}\|[A-Za-z0-9+/]{43}=?)$` | 256-bit CSPRNG key in 64 hex characters or 32-byte Base64 |
| `generation` | integer | No | Minimum: 1, Maximum: 65535, Default: 1 | Key generation number |
| `initial_join_counter` | integer | No | Minimum: 0, Maximum: 4294967295, Default: 0 | Initial monotonic join counter |

### 2.3 Response Schemas

- **`201 Created` (`DeviceProvisionResponse`):**
  ```json
  {
    "device_mac": "001122334455",
    "network_id": 1,
    "generation": 1,
    "status": "ACTIVE",
    "created_at": "2026-11-08T00:00:00Z"
  }
  ```
  *(Raw $K_{\text{JOIN}}$ and wrapped key bytes are never exposed in the response).*
- **`400 Bad Request`:** Malformed JSON, non-canonical MAC, truncated/extended key size, out-of-range parameters.
- **`401 Unauthorized`:** Missing or invalid Bearer token.
- **`403 Forbidden`:** Valid Bearer token but non-`ADMIN` role (e.g. `OPERATOR`, `VIEWER`).
- **`409 Conflict`:** Device already has an active generation or conflicting generation counter.

---

## 3. Cryptographic Key Wrapping & Security Guarantees

1. **AES-256-GCM Envelope Wrapping (`SE-007`):**
   - Backend Master Key ($K_{\text{MASTER\_KEY}}$) is a 256-bit (32-byte) key.
   - For every provisioned device, a cryptographically secure 12-byte random nonce is generated using `crypto/rand.Reader`.
   - The ciphertext and 16-byte authentication tag are computed via standard GCM: $C = \text{AES-GCM-Seal}(\text{nonce}, K_{\text{JOIN}}, \text{nil})$.
   - The persisted envelope in PostgreSQL (`device_generations.k_join_wrapped`) has layout:
     ```text
     [ NONCE (12 bytes) | CIPHERTEXT (32 bytes) | AUTH_TAG (16 bytes) ] = 60 bytes total
     ```
   - This satisfies the database schema constraint `chk_k_join_wrapped_length (>= 32 bytes)`.
2. **In-Memory Zeroization (`SE-003`):**
   - Intermediate buffers containing decoded raw $K_{\text{JOIN}}$ are explicitly zeroized (`zeroize(b)`) immediately upon exit from decoding and wrapping functions via deferred routines and synchronous wiping.
3. **Zero Secret Leakage in Logs (`SE-003`):**
   - Audit logs record:
     `device provisioned successfully: network_id=1 device_mac=001122334455 generation=1`
   - Neither $K_{\text{JOIN}}$, $K_{\text{MASTER\_KEY}}$, nor wrapped ciphertext is ever output to stdout, stderr, or application logs.
4. **RBAC Authorization (`SE-004`):**
   - Bearer token must authenticate with role `ADMIN`.
   - Missing/invalid token returns HTTP 401; non-`ADMIN` role returns HTTP 403.

---

## 4. Verification Evidence & Test Receipts

### 4.1 OpenAPI Contract Validation
```bash
/usr/bin/python3 contracts/tests/check_contracts.py
```
**Output:**
```text
PASS OpenAPI semantic spec + 19 HTTP operations
PASS: 11 schemas, 33 MQTT cases, 18 WS cases, 19 REST operations
NOT VERIFIED: device/auth/nonce/timing/RF, MQTT roundtrip, HTTP/WSS implementation.
```
Exit code: `0`.

### 4.2 Storage Unit Tests (`provision_storage_test.go`)
```bash
cd backend-go && go test -v ./internal/storage -run TestPostgresProvisionStorage
```
**Results:**
- `TestPostgresProvisionStorage_ProvisionDevice_Table/success_initial_provision`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/success_default_generation_when_zero`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/nil_input_returns_ErrInvalidProvisionInput`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/zero_network_id_returns_ErrInvalidProvisionInput`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/short_wrapped_key_returns_ErrInvalidProvisionInput`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/conflict_active_generation_already_exists`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/conflict_generation_number_already_exists`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/device_revoked_returns_ErrDeviceNotActive`: PASS
- `TestPostgresProvisionStorage_ProvisionDevice_Table/context_cancellation_propagates_error`: PASS

### 4.3 REST API Handler Unit Tests (`provision_handler_test.go`)
```bash
cd backend-go && go test -v ./internal/api -run "TestProvisionHandler|TestAESGCMKeyWrapper|TestStaticAuthenticator"
```
**Results:**
- `TestProvisionHandler_Table/positive_registration_with_hex_key_(HTTP_201)`: PASS
- `TestProvisionHandler_Table/positive_registration_with_base64_key_(HTTP_201)`: PASS
- `TestProvisionHandler_Table/missing_authorization_header_(HTTP_401)`: PASS
- `TestProvisionHandler_Table/invalid_bearer_token_(HTTP_401)`: PASS
- `TestProvisionHandler_Table/non-admin_operator_token_(HTTP_403)`: PASS
- `TestProvisionHandler_Table/non-admin_viewer_token_(HTTP_403)`: PASS
- `TestProvisionHandler_Table/malformed_MAC_-_uppercase_not_canonical_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/malformed_MAC_-_too_short_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/malformed_MAC_-_invalid_characters_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/truncated_key_size_-_16_bytes_hex_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/extended_key_size_-_40_bytes_hex_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/zero_network_id_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/invalid_generation_zero_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/malformed_JSON_body_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/empty_bearer_token_string_(HTTP_401)`: PASS
- `TestProvisionHandler_Table/empty_k_join_string_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/unpadded_base64_key_(HTTP_201)`: PASS
- `TestProvisionHandler_Table/url-safe_base64_key_(HTTP_201)`: PASS
- `TestProvisionHandler_Table/storage_invalid_provision_input_maps_to_400_(HTTP_400)`: PASS
- `TestProvisionHandler_Table/conflict_on_existing_active_generation_(HTTP_409)`: PASS
- `TestProvisionHandler_Table/conflict_on_duplicate_generation_number_(HTTP_409)`: PASS
- `TestProvisionHandler_Table/device_not_active_conflict_(HTTP_409)`: PASS
- `TestProvisionHandler_Table/internal_storage_error_(HTTP_500)`: PASS
- `TestAESGCMKeyWrapper_RoundTrip`: PASS (verifies 60-byte envelope, decryption, and authentication tag tampering rejection)
- `TestProvisionHandler_UnconfiguredDependencies`: PASS
- `TestProvisionHandler_WrapFailure`: PASS
- `TestStaticAuthenticator_Nil`: PASS

### 4.4 Full Suite Execution & Lint Verification
```bash
cd backend-go && go test ./...
cd backend-go && gofmt -l .
```
Both commands exited with returncode `0` and zero formatting diffs.

---

## 5. Traceability Matrix

| Requirement / Standard | Implementation Artifact | Verification Result |
|---|---|---|
| OpenAPI spec for `/api/v1/devices/provision` | `contracts/api/openapi.yaml` | `check_contracts.py` PASS (19 ops) |
| Strict input validation (`SE-002`) | `backend-go/internal/api/provision_handler.go` | HTTP 400 test cases PASS |
| Zero secret logging (`SE-003`) | `provision_handler.go` | Verified: only network_id & mac logged |
| RBAC ADMIN authorization (`SE-004`) | `provision_handler.go` | HTTP 401 & 403 test cases PASS |
| AES-256-GCM key wrapping (`SE-007`) | `provision_handler.go` (`AESGCMKeyWrapper`) | Roundtrip & tamper tests PASS |
| Transaction safety (`DB-001`, `DB-002`) | `backend-go/internal/storage/provision_storage.go` | Parameterized queries, Tx rollback |
| Row-level locks & conflict (`DB-003`) | `provision_storage.go` | `FOR UPDATE` queries, HTTP 409 tests PASS |
| Context cancellation (`RT-001`) | `provision_storage.go` | Cancelled context test PASS |
| Clean style & testing (`GGS-001`, `TS-001`) | Co-located unit test suites | Table-driven unit tests PASS |
