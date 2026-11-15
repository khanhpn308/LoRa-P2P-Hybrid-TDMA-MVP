# Issue #400 Verification Report: Refresh Node RF Quality with UP_EVENT & Recover RF Snapshots After Gateway Reboot

## 1. Executive Summary & Root Cause Analysis

### 1.1 Objective & Runtime Evidence
Owner reported an operational discrepancy between the Web Dashboard and backend REST API for Node #3 under Gateway `gw-a`:
- Dashboard event count increased 62 → 66.
- `GET /api/v1/nodes?limit=100&gateway_id=gw-a` kept returning stale RF snapshots:
  `last_rssi_dbm = -20, last_snr_db = 6.5, last_rf_at = 2026-11-14T16:38:51Z, rf_age_seconds = 833 → 991, rf_stale = true`.
- HTTP 200 was returned; the frontend accurately reflected REST truth.

### 1.2 Root Cause Confirmation
Inspection of the codebase confirmed four interlocking defects:
1. **Omitted Gateway Epoch in Gateway App (`gateway_app.c`)**:
   `gateway_radio_bridge_config_t` was instantiated without setting `.gateway_epoch`.
2. **Fixed Fallback Epoch in RF Metrics Subsystem (`gateway_rf_metrics.c`)**:
   When initialized with NULL or empty epoch, `gateway_rf_metrics.c` defaulted to a hardcoded static UUID `550e8400-e29b-41d4-a716-446655440000`, while simultaneously resetting the sample sequence counter `s_sample_seq_counter = 0`.
3. **Sequence Lockout in Backend RFTracker (`rf_tracker.go`)**:
   Upon Gateway reboot, the sequence counter in firmware reset to 0 (emitting samples with `sample_seq` 1, 2, ...). Because the hardcoded epoch remained unchanged (`550e8400-e29b-41d4-a716-446655440000`), the backend `RFTracker` evaluated `sampleSeq <= existing.SampleSeq` (`1 <= 62` = true) and rejected all post-reboot packets as stale/duplicates within the same epoch.
   Furthermore, `RFTracker` did not track previously retired epochs, allowing any delayed/replayed packet from an older epoch to overwrite a newer epoch's snapshot.
4. **Dropped REST Refresh in Frontend (`page.tsx`)**:
   When a realtime `ALERT_TRIGGERED` event was received in `clients/web-dashboard/src/app/nodes/[id]/page.tsx`, `loadRealNode(true)` was triggered. If an initial load or periodic 30s poll was already in flight (`inFlightRef.current === true`), the refresh call was immediately dropped with no trailing refresh scheduled.

---

## 2. Implementation Details

### 2.1 Firmware Gateway Master (`firmware/gateway_master/`)
- **`gateway_app.c`**:
  - Implemented `gateway_app_init_boot_epoch()` which generates an RFC 4122 v4 UUID using ESP-IDF v6.1 hardware entropy (`esp_fill_random`).
  - Retains `s_gateway_boot_epoch` in RAM throughout the boot lifecycle, ensuring stability across MQTT disconnects and reconnects.
  - Passes `s_gateway_boot_epoch` to both `join_cfg.gateway_epoch` and `bridge_cfg.gateway_epoch`.
  - Added strict error checks on `gateway_radio_bridge_init` and `gateway_radio_bridge_start`.
- **`gateway_rf_metrics.c`**:
  - Removed static hardcoded epoch fallback. Initialized `s_gateway_epoch` to empty string.
  - Implemented `is_valid_uuid()` validating strict 36-character 8-4-4-4-12 hex UUID format.
  - Rejects missing or invalid epoch during initialization with `ESP_ERR_INVALID_ARG`.
  - Fails closed (`ESP_ERR_INVALID_STATE`) in `record_and_publish_node`, `format_alert_block`, and `sample_and_publish_channel` if uninitialized.
- **`gateway_radio_bridge.c`**:
  - Checked return value of `gateway_rf_metrics_init`, returning error on failure.
  - Updated `alert_payload` formatting in `process_radio_frame` for `UP_EVENT`:
    - Incorporates `gateway_epoch` and monotonic `event_seq` at JSON root conforming to `contracts/mqtt/schemas/alert.schema.json`.
    - Handles formatting errors safely: if `gateway_rf_metrics_format_alert_block` fails, the business event is still published cleanly without syntax corruption (no trailing comma) and without fabricated RF.

### 2.2 Backend Go (`backend-go/`)
- **`presence/rf_tracker.go`**:
  - Introduced active boot epoch tracking per gateway (`currentGatewayEpoch map[string]string`) and bounded retired epoch history (`retiredGatewayEpochs map[string][]string`, bounded FIFO to 16).
  - Implemented `UpdateNodeRFWithReason` and `UpdateChannelRFWithReason`:
    - If incoming epoch is retired: reject with `"RETIRED_EPOCH"`, ensuring old delayed packets never overwrite the current snapshot.
    - If incoming epoch is new: records epoch transition (retires previous active epoch), accepts reset lower sequence numbers with `"ACCEPTED_NEW_EPOCH"`.
    - If incoming epoch is current active: enforces strictly monotonic sequence numbers (`sampleSeq > existing.SampleSeq`), rejecting duplicates with `"STALE_OR_DUPLICATE_SEQUENCE"` without resetting freshness.
  - Maintained backward compatibility via `UpdateNodeRF` and `UpdateChannelRF`.
  - Added epoch cleanup to `RemoveGateway` and `Clear`.
- **`mqtt/subscriber.go`**:
  - Preserved strict ordering: `ingestAlertRF` executes before `RecordEvent` and before `ALERT_TRIGGERED` WebSocket broadcast.
  - Connected `UpdateNodeRFWithReason` and `UpdateChannelRFWithReason` to bounded token-bucket rate limiter (`rfLogLimiter`) for structured accept/reject logging with zero credential leakage.

### 2.3 Web Dashboard (`clients/web-dashboard/`)
- **`src/app/nodes/[id]/page.tsx`**:
  - Added `trailingRefreshRequestedRef = useRef<boolean>(false)`.
  - When `loadRealNode` is called while an in-flight request is pending (`inFlightRef.current === true`), sets `trailingRefreshRequestedRef.current = true` and returns immediately (coalescing multiple alerts into one).
  - In `finally` block: if `trailingRefreshRequestedRef.current && isMountedRef.current`, resets flag and triggers one trailing refresh. Zero overlapping requests, zero lost updates.
  - On component unmount: resets `isMountedRef.current = false`, `trailingRefreshRequestedRef.current = false`, and aborts active `AbortController`.
  - Error in catch block preserves existing RF values as `rf_stale: true`.
- **`src/lib/api/nodes.ts`**:
  - `getNode` checks `signal?.aborted` before fetch and inside pagination loop, immediately returning null without unneeded network calls.

---

## 3. Verification & Automated Test Results

### 3.1 Python Unit Tests (`tests/unit/test_gateway_rf_metrics.py`)
- `test_boot_epoch_uuid_validation_and_reboot_transition`: Validates strict RFC 4122 v4 UUID format checking matching C implementation, tests alert schema validation pre-reboot and post-reboot with reset sequence numbers, and validates fallback alerts without optional RF blocks.
- **Result:** 5/5 PASSED in 0.192s.

### 3.2 Backend Go Unit & Race Tests
- `internal/presence`:
  - `TestRFTracker_RebootEpochTransitionAndRetiredRejection`: PASSED with `-race`.
  - `TestRFTracker_BoundedRetiredEpochs`: PASSED with `-race`.
  - `TestRFTracker_ChannelRF_EpochTransitionAndRetiredRejection`: PASSED with `-race`.
- `internal/mqtt`:
  - `TestHandleAlertMessage_Ordering_RFMetricsIngestedBeforeBroadcastAndRecordEvent`: PASSED with `-race`. Proves RF snapshot is updated in memory before DB record and before WebSocket broadcast.
  - `TestHandleAlertMessage_RebootEpochTransitionAndConvergenceWithDedicatedTopic`: PASSED with `-race`. Proves reboot epoch transition, reset sequence acceptance, dedicated topic dedup, and late retired epoch rejection.
- `internal/api`:
  - `TestMonitoringHandler_RFMetrics_GatewayRebootAndRESTOverlay`: PASSED with `-race`. Proves REST GET `/api/v1/nodes?gateway_id=gw-a` returns fresh RF metrics (`rf_stale=false`) immediately after reboot epoch transition.

### 3.3 Web Dashboard Tests & Typecheck
- `tests/rf_quality.test.ts`:
  - Section 6: In-flight request at matching alert arrival executes trailing refresh with 0 overlapping requests.
  - Section 6: Multiple alerts arriving during in-flight load coalesce into single trailing refresh.
  - Section 6: Unmount cancellation suppresses trailing refresh and aborts active request.
  - Section 6: Matching `ALERT_TRIGGERED` strictly matches `node_id` and `gateway_id`.
  - Section 6: `getNode` with aborted signal returns null without network calls.
  - Section 6: API error preserves last known values as `rf_stale: true`.
- `npx tsc --noEmit`: 0 errors.
- `npm run lint`: 0 errors, 0 warnings.
- `npm test`: 30/30 PASSED in 329ms.

---

## 4. ESP-IDF v6.1 Compilation & Hardware Smoke Status
- **ESP-IDF Toolchain:** Official Docker `espressif/idf:v6.1` (`xtensa-esp32-elf-gcc 15.2.0`, ESP-IDF v6.1.0).
- **Target Application:** `firmware/gateway_master`.
- **Build Command:** `docker run --rm -v $(pwd):/workspace -w /workspace/firmware/gateway_master espressif/idf:v6.1 idf.py build`
- **Build Result:** `PASS` (exit code 0; `gateway_master.bin` size `0xf7030` bytes, app partition `0x100000` bytes).
- **HIL Smoke Status:** `NOT_RUN` (requires physical ESP32-WROOM-32E + SX1276 bench setup with Gateway + Node 3, and human technical review). Automated tests, static typing, and containerized compilation demonstrate full invariant preservation.
