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



- **Owner revised G06:** Gateway tạo Event ID khi lần đầu nhận, xác thực và persist một uplink mới; Node không mang Event ID. Gateway persist ánh xạ `(gateway_id,node_id,security_session,frame_counter) → (event_id,payload)` và giữ nguyên qua RF retry/reset, offline spool và MQTT QoS1 replay. Backend dedup theo Gateway Event ID và phát hiện conflict payload. Mất mapping/không bảo đảm tính duy nhất thì fail closed/reconcile, không cấp ID khác cho cùng frame. PR #116 vẫn còn G06 cũ, phải cập nhật riêng.
- Alert ưu tiên dùng **cửa sổ tranh chấp + bounded randomized backoff/CAD khi phù hợp**, sau đó dùng cơ hội retry dự phòng **đã nằm trong lịch Backend/User duyệt**. CAD clear không chứng minh không có va chạm; tất cả retry hữu hạn và không tự giành DATA Slot.
- **Phân biệt** ACK trong Beacon (Gateway đã persist uplink hợp lệ) với Backend DB commit. ACK Bitmap phải ràng buộc Gateway, Node, phiên bảo mật và Superframe/packet context qua Beacon được xác thực; MQTT PUBACK không phải xác nhận lưu DB.
- Gateway chỉ có một Radio Owner; TX/RX không đồng thời. Mọi Beacon, join, ACK, Alert, retry đều qua local airtime admission; ưu tiên không bỏ qua RF/legal policy.

## 4. Phân loại Uplink/Downlink và byte layout (CT-01)

**Chỉ Node phát Uplink; chỉ Gateway phát Downlink.** Mỗi loại gói có Payload riêng. Mã `VER_TYPE` và kích thước Header/MIC là DRAFT, không coi là production codec.

| Node → Gateway | Chức năng | Gateway → Node | Chức năng |
|---|---|---|---|
| `UP_TELEMETRY` | Nhiệt độ định kỳ | `DOWN_BEACON_ACK` | Đồng bộ + ACK_BITMAP |
| `UP_ALERT` | Cảnh báo | `DOWN_SCHED_PREPARE` | Lịch mới |
| `UP_SCHED_READY` | Node xác nhận chuẩn bị lịch | `DOWN_COMMAND` | Lệnh tới Node |
| `UP_CMD_RESULT` | Kết quả lệnh | `DOWN_JOIN_ACCEPT` | Chấp thuận gia nhập |
| `UP_JOIN_REQUEST` | Gia nhập/khôi phục | `DOWN_AUTH_UPDATE` | Cập nhật quyền |

**OWNER DECIDED Telemetry Payload:** chỉ `TEMP_X10` (int16 2B, nhiệt độ °C×10; 35,5°C→355). Loại `PROVISION_INSTANCE`, `EVENT_COUNTER`, `SCHED_TOKEN`, `SLOT_ID`, các channel khác, battery và duty khỏi RF Telemetry. Endian, rounding, sentinel còn OPEN G2.

**DRAFT RF Telemetry frame candidate = 17B:** `[VER_TYPE:1][NODE_ID:1][KEY_ID:1][FRAME_COUNTER:4][TEMP_X10:2][MIC:8]`. Frame Counter cho chống replay/dedup, không phải Event ID. Thuật toán, nonce, MIC length/key lifecycle, endian, counter persistence, golden vectors còn OPEN G2; không triển khai codec production từ candidate.

**LOCKED:** Gateway gửi ACK_BITMAP 16-bit (2B) trong Beacon cho Telemetry, Beacon N+1 xác nhận uplink N đã Gateway persist. Bitmap chưa có byte order/offset/on-air encoding được duyệt; ACK cho Alert vẫn OPEN. Retry phải giữ nguyên frame identity; ACK của kỳ trước không tự chuyển sang kỳ sau.

**OWNER DECIDED schedule countdown:** Gateway phát 3 nhịp thông báo hoàn chỉnh `3 → 2 → 1` trước khi đổi lịch tại đầu Superframe. Không bắt đầu nhịp giữa Superframe. Ba thông báo không thay affected Node ACK hoặc old Slot Lease safe termination; thiếu điều kiện, hết activation window hoặc mất trusted clock thì fail closed và báo Backend. Wire format countdown còn OPEN G2.

**Legacy:** frame 8B + CRC16 và 12B sensor payload trong thiết kế ban đầu không còn là RF codec hiện hành.
## 5. Security và acceptance

- Phải xác thực nguồn và toàn vẹn cho dữ liệu, Beacon, Schedule, ACK, Join, Command; **CRC không phải xác thực**. Nonce không được tái sử dụng trên cùng khóa qua reboot, rollover hoặc khác hướng; nếu không chứng minh được tính duy nhất thì chặn TX. RX kiểm replay window theo identity/session/direction.
- Khóa, quy trình cấp/thu hồi, Gateway-origin Event ID/persistent dedup, kích thước frame/tag, endian, epoch/version mapping, bộ đếm và ACK cho Alert/Command/Join: **OPEN G2**. **Ngoại lệ đã LOCKED:** Beacon mang ACK_BITMAP Telemetry 2 byte theo CT-01-ACK-01; không được xem là đã freeze codec. Không tự chọn khóa hoặc format production.
- G1/G3: kiểm tra airtime/guard, CAD hidden terminal, nhiều Node cùng báo động, mất Beacon, reboot, RF compliance Việt Nam. G4/G5: Gateway receipt tracking, Backend dedup, nonce/replay và quyền truy cập. **Chưa có PASS thực nghiệm**.

Xem [TDMA Schedule](tdma-schedule.md), [MQTT contracts](../mqtt/topics.md), [Architecture](../../docs/architecture/system-overview.md).
