# Hợp đồng giao tiếp giữa các nhóm — LoRa P2P Hybrid TDMA MVP

**Revision:** 1.1-draft · **Status:** PROPOSED / REQUIRES CROSS-TEAM REVIEW · **Ngày:** 2026-10-20.

Các tệp trong thư mục này định nghĩa giao diện để Firmware Node, Firmware Gateway, Backend Go, Web và Mobile phát triển độc lập. **Đây là thiết kế hợp đồng, không phải bằng chứng đã triển khai, đã nghiệm thu hay đạt an toàn RF.** Tham chiếu kiến trúc gốc: tài liệu `esp32_sx1762.md` người đề xuất cung cấp (mục 1, 3, 5–9, 11) và baseline tại `docs/architecture/system-overview.md`.

| Ranh giới/đầu mối | Nguồn chuẩn đề xuất | Chủ trì → Cùng duyệt | Issue |
|---|---|---|---|
| Node ↔ Gateway RF Custom MAC | [radio-mac/specification.md](radio-mac/specification.md) | Embedded Node + Gateway → RF/Security, Backend | [#12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) |
| Backend Planner → Gateway Executor → Node | [radio-mac/tdma-schedule.md](radio-mac/tdma-schedule.md) | Backend + Gateway → Node/RF | #12, #14 |
| Gateway ↔ Mosquitto ↔ Backend Go | [mqtt/topics.md](mqtt/topics.md), [mqtt/schemas/](mqtt/schemas/) | Gateway + Backend/Infra → Security | [#14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) |
| Backend REST → Next.js/Kotlin Android | [api/openapi.yaml](api/openapi.yaml) | Backend → Web/Mobile | [#15](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15) |
| Backend WSS → Next.js/Kotlin Android | [api/websocket.md](api/websocket.md), [api/schemas/](api/schemas/) | Backend → Web/Mobile | #15 |

## Quy tắc hợp đồng

1. Hợp đồng chỉ có hiệu lực khi chủ sở hữu phía gửi **và** phía nhận duyệt qua PR/ADR. Không suy diễn việc xuất hiện trong Git là đã được phê duyệt.
2. Không dùng LoRaWAN/ChirpStack. Backend chỉ lập lịch; Gateway cục bộ điều khiển SX1276 bán song công và duy trì chế độ offline.
3. Ba lớp version độc lập: RF `PROTO_VER` (chưa chốt byte layout), MQTT `schema_version`, REST `/api/v1` + OpenAPI và sự kiện WSS `schema_version`. Thay đổi phá vỡ tương thích yêu cầu ADR, bump version, vectors và review.
4. `event_id` Telemetry/Alert do **Node tạo**, không đổi khi RF/MQTT retry; dedup nghiệp vụ theo `(gateway_id,node_id,event_id)`. Gateway-origin Status/ACK dùng event ID riêng. `SEQ_NUM` 8-bit không dùng làm khóa sự kiện.
5. Các con số 10 s / 2 s / 400 ms / SF7 / 921.4 MHz / 1%–10% / trễ <3 s từ bản thiết kế là **đầu vào/giả thuyết đo kiểm**, không là SLA hay RF-compliance đã xác nhận.
6. Chỉ những tệp `contracts/` được sửa trong bộ hồ sơ này; CI hiện tại chỉ kiểm tra cú pháp JSON. Xem [trình tự kiểm tra](verification.md) để chạy kiểm tra hành vi riêng.

## Trạng thái

- **MQTT / REST / WebSocket**: đủ mức làm mock, tích hợp schema draft và review; chưa có producer/consumer thực tế PASS.
- **Radio MAC v1**: *BLOCKED G2* đến khi chốt authenticated framing/nonce/key provisioning, tính airtime và có cross-language golden vectors; không dùng định dạng 8 byte + CRC16 như giao thức production.
- Danh sách bất đồng/giả định cần xử lý tại [OPEN_DECISIONS.md](OPEN_DECISIONS.md).

**Bảo vệ phạm vi:** #12, #14, #15 đều cho phép sửa `contracts/`. Không tự thay đổi firmware, SQL migration, CI workflow hay tài liệu ngoài phạm vi Issue.
