# Hợp đồng giao tiếp giữa các nhóm — LoRa P2P Hybrid TDMA MVP

**Revision:** 0.2.0-draft · **Status:** V2 MIGRATION / EVENT-ONLY CONTRACTS ALIGNED · **Ngày:** 2026-11-07 (Issue #128 / Umbrella #125).

Các tệp trong thư mục này định nghĩa giao diện để Firmware Node, Firmware Gateway, Backend Go, Web và Mobile phát triển độc lập. **Đây là thiết kế hợp đồng, không phải bằng chứng đã triển khai, đã nghiệm thu hay đạt an toàn RF.** Tham chiếu kiến trúc: contracts/radio-mac/specification.md (Rev 0.3.0-draft), contracts/radio-mac/tdma-schedule.md, contracts/OPEN_DECISIONS.md trên main (PR #205, PR #206).

| Ranh giới/đầu mối | Nguồn chuẩn đề xuất | Chủ trì → Cùng duyệt | Issue |
|---|---|---|---|
| Node ↔ Gateway RF Custom MAC | [radio-mac/specification.md](radio-mac/specification.md) | Embedded Node + Gateway → RF/Security, Backend | [#12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12), [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127) |
| Backend Planner → Gateway Executor → Node | [radio-mac/tdma-schedule.md](radio-mac/tdma-schedule.md) | Backend + Gateway → Node/RF | #12, #14, #128 |
| Gateway ↔ Mosquitto ↔ Backend Go | [mqtt/topics.md](mqtt/topics.md), [mqtt/schemas/](mqtt/schemas/) | Gateway + Backend/Infra → Security | [#14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14), [#128](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/128), [#221](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/221) |
| Backend REST → Next.js/Kotlin Android | [api/openapi.yaml](api/openapi.yaml) | Backend → Web/Mobile | [#15](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15), [#128](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/128), [#154](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/154) |
| Backend WSS → Next.js/Kotlin Android | [api/websocket.md](api/websocket.md), [api/schemas/](api/schemas/) | Backend → Web/Mobile | #15, #128 |

## Quy tắc hợp đồng & Kiến trúc Event-Only V2

1. **Thẩm quyền hợp đồng:** Hợp đồng chỉ có hiệu lực khi chủ sở hữu phía gửi **và** phía nhận duyệt qua PR/ADR. Không suy diễn việc xuất hiện trong Git là đã được phê duyệt, đạt an toàn RF hay hoàn thành HIL (#169).
2. **Event-Only Architecture & Zero Periodic Telemetry:** Bãi bỏ hoàn toàn chế độ truyền định kỳ DATA_TELEMETRY (0x03/0x23) và topic uplink/telemetry theo Quyết định Owner #125 / PR #133. Chuyển dịch sang mô hình:
   - **Physical Button Trigger & Event-Only (Refs #230):** Bãi bỏ cơ cấu cảnh báo tại chỗ (còi buzzer, đèn LED báo động, relay) và cảm biến phức tạp theo Quyết định Owner #230; Node dùng nút nhấn vật lý (button press qua GPIO/EXT0) làm nguồn sinh sự kiện duy nhất cho MVP.
   - **Event-Only Remote Logging:** Node chỉ truyền UP_EVENT (0x41, 26B) trong khe tĩnh (Static DATA Slot) độc quyền của mình.
   - **Same-Slot ACK:** Gateway ghi bền vững (WAL/SQLite) trước khi phát DOWN_EVENT_ACK (0x42, 19B) ngay trong cùng khe DATA của Node.
3. **Phân định 4 tầng xác nhận độc lập:**
   - **RF ACK** (DOWN_EVENT_ACK 0x42 19B): Gateway phản hồi Node sau khi commit WAL; Node xóa hoặc đánh dấu sự kiện trong hàng đợi NVS.
   - **MQTT Transport PUBACK**: Broker Mosquitto xác nhận đã nhận gói tin qua QoS 1; không chứng minh Backend đã ghi nhận CSDL.
   - **Backend DB Commit**: Backend Go xác thực, khử trùng lặp qua UNIQUE(gateway_id, event_id) và lưu trữ bền vững vào PostgreSQL.
   - **UI Acknowledgement**: Người vận hành gọi POST /api/v1/alerts/{id}/acknowledge để ghi nhận quy trình xử lý của con người; không bao giờ được coi là RF ACK.
4. **Đăng ký kênh độc quyền VN920_V1 (Refs #154):** Mỗi Gateway được cấp phát độc quyền một kênh tĩnh CH00–CH10 (920.250–922.750 MHz, 125 kHz BW), lưu trữ bền vững trong PostgreSQL; không chia sẻ kênh giữa các Gateway trong MVP.
   - Phân biệt rạch ròi các trạng thái: CHANNEL_ALLOCATED (đã cấp kênh) $	o$ SCHEDULE_STAGED (đã nạp lịch dự phòng) $	o$ SCHEDULE_ACTIVE (lịch đang kích hoạt) $	o$ RF_AUTHORIZED (cho phép phát sóng).
   - Việc được cấp kênh chưa cấu thành quyền phát sóng RF nếu thiếu lịch ACTIVE hợp lệ và đồng hồ tin cậy.
5. **Giám sát & Bảo trì V2:**
   - UP_HEALTH_REPLY (0x44, 21B): Phản ánh PENDING_COUNT (độ sâu hàng đợi FIFO tức thời chưa được ACK).
   - UP_DIAG_METRICS (0x4A, 23B, PR #205): Phản ánh DROPPED_EVENT_COUNT (bộ đếm tích lũy sự kiện bị tràn/hủy do hàng đợi đầy) và DIAG_SEQ.
   - Tuyệt đối không gộp chung hoặc đánh đồng PENDING_COUNT với DROPPED_EVENT_COUNT.
6. **Kế hoạch chuyển đổi và hủy bỏ (Deprecation Policy):**
   - Topic uplink/telemetry, endpoint REST /api/v1/nodes/{id}/telemetry, sự kiện WSS TELEMETRY_UPDATE, và lệnh SET_PERIODIC_MODE được đánh dấu DEPRECATED_HISTORICAL.
   - Giữ nguyên cấu trúc dữ liệu của các schema 1.0-draft để các hệ thống giải mã log lịch sử không bị gián đoạn.
   - Cấm mọi firmware và producer V2 xuất bản dữ liệu đo kiểm định kỳ lên uplink/telemetry hoặc gửi lệnh SET_PERIODIC_MODE.

## Trạng thái

- **Radio MAC V2 (0.3.0-draft):** Đã căn chỉnh baseline MVP (PR #205, PR #206); Join CAD bất đồng bộ (tối đa 3 lần thử lại), khe DATA W500ms + G50ms (chu kỳ 600ms/Node, 15 slots 9000ms), khe READY R400ms + G50ms (chu kỳ 500ms/Node) trong Migration theo yêu cầu, Beacon 0x43 32B HMAC-SHA256-128 trong Maintenance (~300s). Bãi bỏ hoàn toàn countdown 3->2->1 theo DEC-MH-05, D05, #208. HIL #169 tiếp tục đo kiểm thực địa độc lập.
- **MQTT / REST / WebSocket V2 (Issue #128, #221, #232):** Đồng bộ hóa schema sự kiện UP_EVENT 0x41 (`event_ref`, `event_code`, `event_value`), hủy bỏ telemetry định kỳ và countdown schedule, chuẩn hóa REST route cấp phát kênh VN920_V1 (`/api/v1/channels`, `/api/v1/gateways/{gw_id}/channel*`), bổ sung schema relay UP_JOIN_HELLO 0x45 68B, cập nhật validator kiểm tra hình học lịch V2 và bộ test tương thích.
- Bất đồng và lộ trình kỹ thuật được cập nhật tại [OPEN_DECISIONS.md](OPEN_DECISIONS.md).
