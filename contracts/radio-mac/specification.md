# Radio MAC — Node ↔ Gateway (LoRa P2P)

**Trạng thái:** `DRAFT / G2 NOT_VERIFIED`. Kiến trúc C01–C08 được Owner phê duyệt; **định dạng byte, mật mã, nonce, phiên bản vô tuyến và timing chưa được đóng băng**.

## 1. Mạng, định danh và quyền (C01/C02/C06/C07)

- Mạng **Multi-Gateway Star**, 1–4 Gateway, một SX1276 bán song công mỗi Gateway. Khi đủ bốn Gateway, mỗi Gateway dùng **một kênh riêng, BW 125 kHz**. Node chỉ kết nối trực tiếp với **Gateway/kênh cố định**; không Mesh, relay, handover hay quét kênh tự động.
- `node_id` là **8-bit theo phạm vi Gateway**, logic identity `(gateway_id, node_id)`. Bản nháp legacy dành `0x00` cho Gateway, `1..254` cho Node và `0xFF` cho broadcast; cách mã hóa cuối cùng phải được G2 phê duyệt. ID không là bằng chứng mật mã; Device UID 128-bit **chưa được chọn**.
- Node chỉ phát dữ liệu ứng dụng khi có mapping/schedule, đồng bộ, quyền thiết bị **còn hiệu lực và có thể kiểm chứng**, cũng như airtime hợp lệ. Gateway mất Internet **không tự gia hạn quyền**. Tạm ngừng/khôi phục/thu hồi/cấp lại quyền thuộc MVP; thu hồi quyền không tự tái cấp slot (C04).
- `Periodic OFF` chỉ tắt báo cáo chu kỳ, **không** tắt phát hiện/gửi Alert hợp lệ.

## 2. Lịch và chuyển lịch (C03/C04)

- Backend tạo/version lịch; User có quyền phê duyệt kế hoạch và **activation window**. Gateway kiểm tra, bền vững hóa `Shadow` trước `STAGE_ACK`, truyền chuẩn bị và nhận ACK xác thực từ các Node bị ảnh hưởng.
- Gateway kích hoạt tại đầu Superframe **bên trong cửa sổ được duyệt** chỉ khi quyền dùng khe cũ đã chấm dứt an toàn, không chồng lấn; nếu không chứng minh được phải **fail closed**. Gateway không thay Slot Assignment/kênh hoặc tự mở rộng cửa sổ.
- `ACTIVE_REPORT` chỉ gửi sau kích hoạt thực tế. `STAGE_ACK`, Beacon hay MQTT PUBACK **không** chứng minh `ACTIVE`. Reboot không tự biến `Shadow` thành `Active`.

## 3. Cảnh báo, định danh sự kiện và ACK (C05/C08)

- **Node phát sinh `event_id` gốc** và giữ nguyên qua RF retry/reset, Gateway offline spool và MQTT QoS1 replay. Gateway ghi nhận lần RX bằng identity riêng; Backend chống trùng bền vững bằng **(gateway_id, node_id, node event_id)** và kiểm tra conflict payload. RF `SEQ_NUM` 8-bit không đủ làm event ID hoặc chống replay.
- Alert ưu tiên dùng **cửa sổ tranh chấp + bounded randomized backoff/CAD khi phù hợp**, sau đó dùng cơ hội retry dự phòng **đã nằm trong lịch Backend/User duyệt**. CAD clear không chứng minh không có va chạm; tất cả retry hữu hạn và không tự giành DATA Slot.
- **Phân biệt** RF ACK (nhận gói đã xác thực), tiếp nhận/lưu bền vững tại Gateway và Backend DB commit. ACK phải ràng buộc danh tính, phiên bảo mật và bản tin gốc; MQTT PUBACK không phải xác nhận lưu DB.
- Gateway chỉ có một Radio Owner; TX/RX không đồng thời. Mọi Beacon, join, ACK, Alert, retry đều qua local airtime admission; ưu tiên không bỏ qua RF/legal policy.

## 4. Bản tin và bản nháp byte layout

| Loại bản tin kế thừa từ bản nháp | Hướng | Vai trò |
|---|---|---|
| `BEACON`, `SCHED_ANNOUNCE` | Gateway → Node | Đồng bộ và thông báo lịch |
| `DATA_TELEMETRY`, `PRIORITY_ALERT` | Node → Gateway | Telemetry và Alert, phải mang/khôi phục chính xác Node-origin Event ID |
| `ACK_PACKET` | Gateway → Node | Xác nhận RF có liên kết danh tính/phiên/bản tin |
| `CMD_DOWNLINK` | Gateway → Node | Điều khiển trong phạm vi được cấp quyền |
| `JOIN_SLOT_REQ`, `JOIN_SLOT_RSP` | Node ↔ Gateway | Đăng ký/khôi phục theo chính sách bảo mật |

**Chỉ để tham khảo lịch sử:** frame 8-byte `MAGIC/VER_TYPE/CTRL_FLAGS/SRC_ID/DST_ID/SCHED_VER/SEQ_NUM/PAYLOAD_LEN` + payload + CRC16 và payload DATA/ALERT 12-byte **không đủ** cho xác thực, epoch/version và Node Event ID. **Không triển khai codec production từ bố cục đó**; G2 phải định nghĩa lại wire layout/version và golden vectors.

## 5. Security và acceptance

- Phải xác thực nguồn và toàn vẹn cho dữ liệu, Beacon, Schedule, ACK, Join, Command; **CRC không phải xác thực**. Nonce không được tái sử dụng trên cùng khóa qua reboot, rollover hoặc khác hướng; nếu không chứng minh được tính duy nhất thì chặn TX. RX kiểm replay window theo identity/session/direction.
- Khóa, quy trình cấp/thu hồi, cấu trúc Event ID, kích thước frame/tag, endian, epoch/version mapping, bộ đếm và cơ chế ACK trên RF: **OPEN G2**. Không tự chọn khóa hoặc format production.
- G1/G3: kiểm tra airtime/guard, CAD hidden terminal, nhiều Node cùng báo động, mất Beacon, reboot, RF compliance Việt Nam. G4/G5: Gateway receipt tracking, Backend dedup, nonce/replay và quyền truy cập. **Chưa có PASS thực nghiệm**.

Xem [TDMA Schedule](tdma-schedule.md), [MQTT contracts](../mqtt/topics.md), [Architecture](../../docs/architecture/system-overview.md).
