# Verification Report: Xác thực sự tồn tại của thiết bị và khóa K_join trước khi tạo Join Request PENDING

- **Issue:** #329
- **Title:** `[Backend][MQTT] Xác thực sự tồn tại của thiết bị và khóa K_join trước khi tạo Join Request PENDING`
- **Component:** `backend-go` (`internal/mqtt`, `internal/storage`)
- **Date:** 2026-11-11
- **Status:** PASS

---

## 1. Mục tiêu và Bối cảnh (Objective & Background)

Theo Lưu đồ phê duyệt Join của Backend (Architecture Flowchart 2026-11-11):
- Khi Gateway chuyển tiếp gói `UP_JOIN_HELLO` qua MQTT (topic `iot/v1/gw/{gw_id}/uplink/join-hello` hoặc `.../join-request`), Backend cần:
  1. Kiểm tra thiết bị và khóa $K_{join}$ theo MAC (tra cứu trong `devices` và `device_generations`).
  2. **Nếu Không (Thiết bị lạ / chưa nạp khóa):** Drop Packet âm thầm (Fail-silent drop), ghi log cảnh báo nội bộ:
     `[MQTT Subscriber] Dropping join request from unregistered device: mac=<mac>`
     Không tạo bản ghi rác trong cơ sở dữ liệu `device_join_requests`, không bắn WebSocket `NODE_JOIN_REQUEST` lên Web UI nhằm chống tấn công làm phiền giao diện (UI Spam DoS / Alert Fatigue).
  3. **Nếu Có (Thiết bị hợp lệ):** Thêm request vào `device_join_requests` với `status = PENDING` và phát thông báo Realtime WebSocket lên Web Frontend để người vận hành phê duyệt.

Trước Issue #329, `GatewayStatusSubscriber.handleJoinMessage` chỉ kiểm tra độ dài chuỗi MAC (`len(mac) == 12`) rồi lập tức tạo `PENDING` request và phát WebSocket. Bất kỳ MAC lạ nào cũng lọt vào hàng chờ trên Web.

---

## 2. Chi tiết Thay đổi (Implementation Details)

### 2.1 Interface & Storage (`internal/storage/join_request_storage.go`)
- Bổ sung phương thức `IsDeviceRegistered(ctx context.Context, mac string) (bool, error)` vào interface `JoinRequestStorage`.
- Triển khai trong `PostgresJoinRequestStorage`:
  - Chuẩn hóa MAC, decode thành 6 bytes nhị phân.
  - Thực thi truy vấn có tham số kiểm tra cả `devices` (trạng thái `ACTIVE`) và `device_generations` (trạng thái `is_active = TRUE`):
    ```sql
    SELECT 1
    FROM devices d
    JOIN device_generations g
      ON d.network_id = g.network_id AND d.device_mac = g.device_mac
    WHERE d.device_mac = $1 AND d.status = 'ACTIVE' AND g.is_active = TRUE
    LIMIT 1;
    ```
  - Trả về `true` khi tìm thấy, `false` khi `sql.ErrNoRows`.

### 2.2 MQTT Subscriber (`internal/mqtt/subscriber.go`)
- Trong `GatewayStatusSubscriber.handleJoinMessage`:
  - Trước khi gọi `CreateOrUpdatePendingRequest`, gọi `s.joinReqStore.IsDeviceRegistered(ctx, mac)`.
  - Nếu xảy ra lỗi truy vấn: ghi log và dừng xử lý an toàn (`return`).
  - Nếu `!isRegistered`: ghi log đúng định dạng yêu cầu:
    `log.Printf("[MQTT Subscriber] Dropping join request from unregistered device: mac=%s", mac)`
    và kết thúc hàm (`return`), hoàn toàn không tạo `device_join_requests` và không phát WebSocket `NODE_JOIN_REQUEST`.

### 2.3 Unit & Integration Tests
- `backend-go/internal/storage/join_request_storage_test.go`:
  - `TestPostgresJoinRequestStorage_IsDeviceRegistered_Success`: Thiết bị đã nạp khóa và active -> trả về `true, nil`.
  - `TestPostgresJoinRequestStorage_IsDeviceRegistered_NotFound`: Thiết bị chưa đăng ký -> trả về `false, nil`.
  - `TestPostgresJoinRequestStorage_IsDeviceRegistered_InvalidMAC`: MAC không hợp lệ -> trả về lỗi.
- `backend-go/internal/mqtt/subscriber_test.go`:
  - `TestHandleJoinMessage_UnregisteredDevice_Dropped`: Gói join từ thiết bị chưa đăng ký -> bị drop âm thầm, không gọi `CreateOrUpdatePendingRequest`, không broadcast WebSocket, log đúng chuỗi cảnh báo.
  - `TestHandleJoinMessage_RegisteredDevice_PendingAndBroadcast`: Gói join từ thiết bị hợp lệ -> tạo bản ghi `PENDING` và broadcast WebSocket thành công.
  - `TestHandleJoinMessage_InvalidMAC_Dropped`: Gói tin với MAC sai định dạng -> drop trước khâu tra cứu storage.
  - `TestHandleJoinMessage_StorageError_SafeReturn`: Lỗi database khi tra cứu -> fail-safe drop.
  - `TestHandleJoinMessage_ExtractMACFromRawFrame`: Trích xuất MAC từ `raw_frame_hex` khi `device_mac` rỗng -> xử lý chính xác.

---

## 3. Kết quả Kiểm thử (Test Execution Results)

### 3.1 Unit Tests `internal/storage`
```bash
go test -v ./internal/storage/...
```
Kết quả:
```text
=== RUN   TestPostgresJoinRequestStorage_IsDeviceRegistered_Success
--- PASS: TestPostgresJoinRequestStorage_IsDeviceRegistered_Success (0.00s)
=== RUN   TestPostgresJoinRequestStorage_IsDeviceRegistered_NotFound
--- PASS: TestPostgresJoinRequestStorage_IsDeviceRegistered_NotFound (0.00s)
=== RUN   TestPostgresJoinRequestStorage_IsDeviceRegistered_InvalidMAC
--- PASS: TestPostgresJoinRequestStorage_IsDeviceRegistered_InvalidMAC (0.00s)
PASS
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage	0.009s
```

### 3.2 Unit Tests `internal/mqtt`
```bash
go test -v ./internal/mqtt/...
```
Kết quả:
```text
=== RUN   TestHandleJoinMessage_UnregisteredDevice_Dropped
--- PASS: TestHandleJoinMessage_UnregisteredDevice_Dropped (0.00s)
=== RUN   TestHandleJoinMessage_RegisteredDevice_PendingAndBroadcast
--- PASS: TestHandleJoinMessage_RegisteredDevice_PendingAndBroadcast (0.00s)
=== RUN   TestHandleJoinMessage_InvalidMAC_Dropped
--- PASS: TestHandleJoinMessage_InvalidMAC_Dropped (0.00s)
=== RUN   TestHandleJoinMessage_StorageError_SafeReturn
--- PASS: TestHandleJoinMessage_StorageError_SafeReturn (0.00s)
=== RUN   TestHandleJoinMessage_ExtractMACFromRawFrame
--- PASS: TestHandleJoinMessage_ExtractMACFromRawFrame (0.00s)
PASS
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt	0.014s
```

### 3.3 Toàn bộ Bộ Kiểm thử Backend với Race Detector (`go test -race ./...`)
```bash
go vet ./... && go test -race ./...
```
Kết quả:
```text
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/cmd/server	13.854s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/api	1.124s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/auth	113.100s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/domain	1.031s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/jsonboundary	1.022s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/mqtt	1.048s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/presence	1.016s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/realtime	1.518s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/security	1.016s
ok  	github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/backend-go/internal/storage	1.072s
```
100% tests PASS, 0 race condition detected, 0 compilation warning.

### 3.4 Định dạng Code (`gofmt -l`)
```bash
gofmt -l backend-go/internal/mqtt/ backend-go/internal/storage/ backend-go/cmd/server/ backend-go/internal/api/
```
Output rỗng (100% tuân thủ chuẩn `gofmt`).

---

## 4. Tiêu chuẩn Kỹ thuật Tuân thủ (Standards Compliance)

- **SE-002 / SE-007**: Không in lộ khóa bí mật ($K_{join}$) hay token trong log; log âm thầm chỉ ghi MAC của thiết bị lạ bị drop.
- **SE-003 / SE-004**: Kiểm tra xác thực thiết bị phía server trước khi đưa vào hàng đợi duyệt; phòng chống DoS spam hàng chờ WebSocket.
- **DB-002 / DB-004**: Sử dụng truy vấn SQL có tham số (`$1`), timeout rõ ràng qua `context.WithTimeout(..., 5*time.Second)`.
- **MQ-001 .. MQ-012**: Tương thích xử lý topic MQTT ingress `iot/v1/gw/{gw_id}/uplink/join-(hello|request)`, giữ đúng quy tắc phân định vai trò Gateway vs Backend.
- **QG-001 / QG-002 / QG-005**: Kiểm thử 100% pass với Go 1.27, race detector sạch sẽ.
