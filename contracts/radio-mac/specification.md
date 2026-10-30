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

**CT-01-ACK-01 — `OWNER_APPROVED / LOCKED` (2026-10-30):** Gateway gộp ACK của Telemetry định kỳ vào Beacon. **Không có gói `RF_ACK` riêng** cho Telemetry định kỳ. `ACK_BITMAP` có độ dài cố định **16 bit = 2 byte** cho tối đa 15 Node trên mỗi Gateway; danh sách Node ID trong Beacon không được dùng cho ACK Telemetry.

- **Bit mapping:** mỗi Node có một `ACK_INDEX` duy nhất trong phạm vi Gateway, được provision/sync cùng cấu hình (đề xuất index `1..15`, bit `0` reserved). `NODE_ID` 8-bit không đồng nhất với `ACK_INDEX`; thay đổi mapping phải chuyển cấu hình an toàn để không báo ACK nhầm. Mapping chính xác và byte order thuộc wire codec G2 chưa freeze.
- **ACK epoch:** Beacon của Superframe `N+1` xác nhận các uplink đủ điều kiện trong Superframe `N`; tính liên kết epoch phải được bảo vệ bởi cơ chế xác thực Beacon. Bit `1` chỉ được set khi frame hợp lệ **đã được Gateway persist thành công** (không phải PostgreSQL commit). Bit `0` chỉ là **NOT_ACKNOWLEDGED**, không khẳng định Gateway mất frame.
- **Giới hạn không nhập nhằng:** mỗi Node chỉ có **một Telemetry uplink đang chờ ACK** trong cửa sổ Bitmap tương ứng; Node không gửi Telemetry mới làm mất dấu bản tin chưa xác nhận. Cơ chế nhiều uplink/Node, ACK Alert/Command/Join là **OPEN**, không được gán nghĩa tùy tiện cho Bitmap này.
- **Retry và chống trùng:** khi thiếu ACK hoặc mất Beacon, Node giữ frame chờ và retry trong cơ hội lịch cho phép, không tự chiếm slot. Retransmit cùng ứng dụng giữ nguyên identity/counter và authenticated frame bytes; Gateway dedup theo Gateway/Node/security-session/frame-counter và tái ACK khi nhận retransmission hợp lệ. ACK bit của cửa sổ cũ **không được carry forward** sang cửa sổ mới để tránh ACK nhầm packet khác; trường hợp mất Beacon liên tiếp phải kiểm thử.
- **RF constraints:** Beacon phải xác thực và tuân TX/RX half-duplex, airtime admission; verify ToA/PHY payload và failure modes trong HIL/RF. 2 byte chỉ là `ACK_BITMAP`, không phải tổng Beacon frame length.



- **Node phát sinh `event_id` gốc** và giữ nguyên qua RF retry/reset, Gateway offline spool và MQTT QoS1 replay. Gateway ghi nhận lần RX bằng identity riêng; Backend chống trùng bền vững bằng **(gateway_id, node_id, node event_id)** và kiểm tra conflict payload. RF `SEQ_NUM` 8-bit không đủ làm event ID hoặc chống replay.
- Alert ưu tiên dùng **cửa sổ tranh chấp + bounded randomized backoff/CAD khi phù hợp**, sau đó dùng cơ hội retry dự phòng **đã nằm trong lịch Backend/User duyệt**. CAD clear không chứng minh không có va chạm; tất cả retry hữu hạn và không tự giành DATA Slot.
- **Phân biệt** ACK trong Beacon (Gateway đã persist uplink hợp lệ) với Backend DB commit. ACK Bitmap phải ràng buộc Gateway, Node, phiên bảo mật và Superframe/packet context qua Beacon được xác thực; MQTT PUBACK không phải xác nhận lưu DB.
- Gateway chỉ có một Radio Owner; TX/RX không đồng thời. Mọi Beacon, join, ACK, Alert, retry đều qua local airtime admission; ưu tiên không bỏ qua RF/legal policy.

## 4. Bản tin và bản nháp byte layout

| Loại bản tin kế thừa từ bản nháp | Hướng | Vai trò |
|---|---|---|
| `BEACON_ACK`, `SCHED_ANNOUNCE` | Gateway → Node | Beacon đồng bộ và ACK_BITMAP 2B cho Telemetry cửa sổ trước; thông báo lịch |
| `DATA_TELEMETRY`, `PRIORITY_ALERT` | Node → Gateway | Telemetry và Alert, phải mang/khôi phục chính xác Node-origin Event ID |
| `CMD_DOWNLINK` | Gateway → Node | Điều khiển trong phạm vi được cấp quyền |
| `JOIN_SLOT_REQ`, `JOIN_SLOT_RSP` | Node ↔ Gateway | Đăng ký/khôi phục theo chính sách bảo mật |

**Chỉ để tham khảo lịch sử:** frame 8-byte `MAGIC/VER_TYPE/CTRL_FLAGS/SRC_ID/DST_ID/SCHED_VER/SEQ_NUM/PAYLOAD_LEN` + payload + CRC16 và payload DATA/ALERT 12-byte **không đủ** cho xác thực, epoch/version và Node Event ID. **Không triển khai codec production từ bố cục đó**; G2 phải định nghĩa lại wire layout/version và golden vectors.

## 5. Security và acceptance

- Phải xác thực nguồn và toàn vẹn cho dữ liệu, Beacon, Schedule, ACK, Join, Command; **CRC không phải xác thực**. Nonce không được tái sử dụng trên cùng khóa qua reboot, rollover hoặc khác hướng; nếu không chứng minh được tính duy nhất thì chặn TX. RX kiểm replay window theo identity/session/direction.
- Khóa, quy trình cấp/thu hồi, cấu trúc Event ID, kích thước frame/tag, endian, epoch/version mapping, bộ đếm và ACK cho Alert/Command/Join: **OPEN G2**. **Ngoại lệ đã LOCKED:** Beacon mang ACK_BITMAP Telemetry 2 byte theo CT-01-ACK-01; không được xem là đã freeze codec. Không tự chọn khóa hoặc format production.
- G1/G3: kiểm tra airtime/guard, CAD hidden terminal, nhiều Node cùng báo động, mất Beacon, reboot, RF compliance Việt Nam. G4/G5: Gateway receipt tracking, Backend dedup, nonce/replay và quyền truy cập. **Chưa có PASS thực nghiệm**.

Xem [TDMA Schedule](tdma-schedule.md), [MQTT contracts](../mqtt/topics.md), [Architecture](../../docs/architecture/system-overview.md).
