# Điểm cần chốt và sai khác giữa tài liệu thiết kế với baseline repo

**Hướng kiến trúc C01–C08 đã được Owner phê duyệt; các mục bên dưới chỉ còn chặn việc đóng băng chi tiết G1/G2/G4, không được dùng để khôi phục giả định trước C01–C08.**

**Quy tắc phân loại:** CONFIRMED = chủ đích kiến trúc trong ADR/baseline; CANDIDATE = đề xuất từ tài liệu đính kèm; BLOCKED = cần ADR hoặc bằng chứng G1/G2 trước khi đóng băng.

| ID / nguồn mục | Vấn đề | Hợp đồng tạm thời / yêu cầu giải quyết | Trạng thái & người duyệt |
|---|---|---|---|
| D01 §6.1 | Tài liệu dùng MAC header 8B + CRC16, thiếu authentication, boot nonce và replay counter | Giữ 8B là **legacy candidate**; **không đóng băng** bit layout. Chọn AEAD hoặc MAC tag, nonce và key/session trước golden bytes | BLOCKED G2 · Node/GW/Security (#12) |
| D02 §5.1, §11 | Superframe 10s, 5 subframe, 15 slot, kích thước/ToA chi tiết | Ghi như **profile thí nghiệm P-10S-15**; xác minh toàn bộ airtime, drift, half-duplex và hoạt động khi nhiều cảnh báo | CANDIDATE G1/G2 · RF/GW/Node |
| D03 §1, §11.2 | 921.4 MHz, Node ≤1% và GW ≤10% được mô tả như quy định bắt buộc | Không khẳng định hợp quy tại Việt Nam; chặn TX bằng policy được RF owner phê duyệt sau khi phân loại thiết bị/pháp lý; mọi TX kể cả P0 tính airtime | BLOCKED G1 · RF/Regulatory |
| D04 §5.2 | Giả định DIO0 TxDone/RxDone đồng thời <50µs; công thức có SPI overhead cố định | Cấm bảo đảm jitter; đo IRQ latency, ToA và sai số clock trên HIL, hiệu chuẩn công thức thực nghiệm | BLOCKED G1/G3 · RF/Embedded |
| D05 §5.3 | Gateway chọn K+3 và ba lần thông báo, ngay cả khi nhận lịch giữa SF | Gateway phải đảm bảo **đủ số chu kỳ quảng bá hoàn chỉnh** trước activate; Node không nhận được lịch không được TX trong khe cũ | CANDIDATE / NEEDS HIL · Gateway/Node |
| D06 §6.3, §5.3 | Topic `iot/gw/{id}/control/schedule/set` vs `iot/v1/gw/{id}/downlink/schedule`; `sched_ack` vs `schedule-ack` | Chọn namespace **repo baseline** `iot/v1/gw/{gateway_id}` và suffix `uplink/schedule-ack`; không hỗ trợ alias ngầm | PROPOSED · Gateway/Go |
| D07 §6.3 | Retain=true cho schedule gây phát lại lịch cũ sau restart | v0.1 chọn **retain=false** cho downlink schedule và yêu cầu Backend reconcile qua status rồi resend cùng id/version còn hiệu lực; persisted local active schedule | PROPOSED · Backend/GW/Infra |
| D08 §6.3 | MQTT v5 hoặc v3.1.1 | **MQTT 5.0 được Project Owner chọn** (ADR-0002). QoS1 + payload `expires_at`; Message Expiry bắt buộc cho schedule/command, không thay application validation | OWNER_ACCEPTED (PR #26 MERGED) / CROSS-TEAM REVIEW PENDING (#14) |
| D09 §6.2, §9.2 | RF DATA có 12B channel/voltage nhưng SQL lưu floating value; không có unit/scaling cố định | MQTT truyền `raw` integer chính xác; mapping scale/unit/threshold phải đi cùng version cấu hình Node, do Backend quy đổi; không suy diễn mặc định mọi cảm biến | PROPOSED · Node/GW/Backend |
| D10 §6.2, §9.2 | RF PRIORITY_ALERT không mang rõ trigger_channel/threshold nhưng DB alert yêu cầu | `trigger` là optional trong MQTT đến khi RF schema có nguồn xác thực; backend chỉ ghi giá trị chắc chắn, không điền bịa | BLOCKED integration · Node/Backend |
| D11 §5.3 / SQL | Radio `SCHED_VER` 8-bit, Backend version INTEGER; wrap-around và restart | Không dùng modulo-256 để quyết định lịch mới hơn; RF v1 phải mang epoch/version đủ rộng hoặc một cơ chế mapping được duyệt. Nếu không giải quyết, fail closed | BLOCKED G2 · All |
| D12 §6.3, §7.4 | QoS1 / ring buffer được mô tả lưu mọi Alert không mất | Bắt buộc buffer có giới hạn, overflow counter và điều kiện mất dữ liệu rõ; không cam kết lưu 100% khi mất kết nối vô hạn | CANDIDATE · Gateway/Backend |
| D13 §9.3 | JWT/login, HTTP+WSS, RBAC; cơ chế identity chưa duyệt | Mô tả bearer token trong OpenAPI **provisional**; bổ sung ADR authn/token lifecycle trước production, luôn enforce RBAC tại Backend | BLOCKED Security · Backend/Web/Mobile |

## Điều kiện mở khóa

- **G1**: đo ToA, drift, turnaround; thẩm định RF và chính sách airtime có thể áp dụng.
- **G2**: ADR authenticated MAC, nonce/replay/persistent boot counter, packet layout và golden vectors C↔Go.
- **G4**: contract schema tests + review producer/consumer, DB migration mapping (ngoài scope PR này).
- **G5/G6**: fault injection, HIL, bảo mật và thử nghiệm thực địa; không đánh dấu PASS từ docs.
