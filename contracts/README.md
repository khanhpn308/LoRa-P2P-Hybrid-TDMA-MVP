# Hợp đồng giao tiếp — LoRa P2P Hybrid TDMA MVP

**G01–G10: `OWNER_APPROVED / LOCKED` (2026-10-30).** Đây là các ràng buộc bắt buộc cho tất cả contract và implementation; không được thay đổi nếu Owner chưa phê duyệt quyết định mới. **Schema/byte layout/timing/security parameters còn chưa được chốt không tự được xem là LOCKED hoặc VERIFIED.**

## Ràng buộc đã khóa

| ID | Quy tắc bắt buộc |
|---|---|
| **G01** | MVP có **1–4 Gateway**, mạng **Star**, mỗi Gateway dùng kênh RF riêng, LoRa **BW 125 kHz**. |
| **G02** | Node gắn cố định với một Gateway và một kênh; **không Mesh, roaming hoặc chuyển Gateway tự động**. |
| **G03** | Định danh logic Node là **`(gateway_id, node_id)`**, với `node_id` **8-bit** theo phạm vi Gateway. |
| **G04** | **Backend** tạo/quản lý phiên bản lịch TDMA; **User được phân quyền** phê duyệt. |
| **G05** | **Gateway** thực thi và kiểm tra an toàn cục bộ; **không tự thay đổi Slot Assignment** đã được duyệt. |
| **G06** | **Node tạo Event ID gốc**; Gateway nhận/chuyển tiếp; Backend lưu bền vững và chống trùng theo nguồn sự kiện. |
| **G07** | MVP bắt buộc có **tạm ngừng, khôi phục, thu hồi và cấp lại quyền Node**. |
| **G08** | **`Periodic OFF` không tắt** khả năng phát hiện và gửi cảnh báo hợp lệ. |
| **G09** | Alert sử dụng **cửa sổ tranh chấp** và **cơ hội retry dự phòng** thuộc lịch đã được Backend/User phê duyệt. |
| **G10** | Các giao tiếp phải có xác thực, phân quyền theo ngữ cảnh, xử lý lỗi và truy vết phù hợp; **CRC không thay thế xác thực mật mã**. |

Mọi chức năng Owner yêu cầu thuộc **MVP**; **Mesh tạm ngoài phạm vi**. Quyền Node khi Gateway mất Internet chỉ tiếp tục khi còn hiệu lực và chứng minh được, **không tự gia hạn** (C07). Chuyển lịch phải tuân chuẩn bị/ACK, Slot Lease và safe cutover (C04). Đây là phần của kiến trúc đã duyệt, không phải thông số RF được đo.

## Giao diện giữa các nhóm

| Ranh giới | Contract hiện có |
|---|---|
| Node ↔ Gateway | [Radio MAC](radio-mac/specification.md) |
| Backend Planner ↔ Gateway Executor ↔ Node | [TDMA Schedule](radio-mac/tdma-schedule.md) |
| Gateway ↔ Mosquitto ↔ Backend Go | [MQTT topics](mqtt/topics.md) và [JSON Schemas](mqtt/schemas/) |
| Backend ↔ Web/Mobile | [REST OpenAPI](api/openapi.yaml), [WebSocket](api/websocket.md) |

**Version:** RF `PROTO_VER`, MQTT `schema_version`, REST `/api/v1` và WSS `schema_version` độc lập; thay đổi phá vỡ tương thích phải cập nhật phiên bản, schema/fixtures, tests và review các phía liên quan. Không sử dụng LoRaWAN MAC/ChirpStack. Web/Mobile không truy cập trực tiếp MQTT hoặc PostgreSQL.

**Chưa khóa định dạng thực thi:** RF frame/authentication/nonce/key lifecycle, Event ID wire encoding, thời gian Superframe/Slot/guard, quyền và thời hạn lease, tần số/công suất hợp quy, chi tiết cấp lại khóa, phương thức xác thực WebSocket. Các giá trị ví dụ `P-10S-15`, 921.4 MHz, tỷ lệ airtime và latency target **không được tự xem là thông số đã duyệt**. Đây là công việc thiết kế/kiểm thử còn lại; **không hạ trạng thái G01–G10**.

**Trạng thái:** `G01–G10 LOCKED`; giao diện chi tiết vẫn ở phiên bản `1.1-draft` để tiếp tục chốt, **implementation/contract tests/RF/HIL NOT_VERIFIED**. Danh sách thông số chi tiết còn phải xử lý nằm trong [OPEN_DECISIONS.md](OPEN_DECISIONS.md).
