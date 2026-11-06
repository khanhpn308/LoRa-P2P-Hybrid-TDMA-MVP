# Điểm cần chốt và sai khác giữa tài liệu thiết kế với baseline repo

**Quy tắc phân loại trạng thái:**
- `OWNER_APPROVED_DESIGN`: Thiết kế đã được Project Owner phê duyệt chính thức bằng văn bản/commit; làm cơ sở ràng buộc kiến trúc nhưng chưa đồng nghĩa với hoàn tất kiểm thử vật lý hay code production.
- `OWNER_APPROVED_DIRECTION`: Chủ trương định hướng kỹ thuật đã được Project Owner phê duyệt chính thức (2026-11-06); xác lập nguyên tắc kiến trúc và tiêu chí thẩm định fail-closed nhưng **không đóng băng các hằng số số học cố định** hay gán byte wire khi chưa có đo đạc thực tế / hợp đồng riêng.
- `CONFIRMED`: Chủ đích kiến trúc đã được xác nhận trong ADR hoặc baseline repo.
- `CANDIDATE`: Đề xuất kỹ thuật đang chờ xem xét liên chức năng và phê duyệt từ Owner.
- `PLANNED_NOT_IMPLEMENTED`: Đã được chấp thuận định hướng trong kiến trúc nhưng chưa cấp phát mã trên dây (wire codepoint) hoặc chưa triển khai mã nguồn trong phạm vi hợp đồng hiện tại.
- `OPEN_DECISION`: Vấn đề kỹ thuật mở cần lựa chọn phương án trước khi đóng băng hợp đồng.
- `BLOCKED`: Điểm nghẽn kỹ thuật bắt buộc phải có ADR mới hoặc bằng chứng đo đạc vật lý G1/G2 trước khi đóng băng.
- `BLOCKED_FOR_OWNER_DECISION`: Đề xuất kỹ thuật hoặc cơ chế đang chờ quyết định phê duyệt chính thức từ Project Owner trước khi trở thành ràng buộc hợp đồng.
- `NOT_HIL_VERIFIED`: Chưa có bằng chứng đo đạc thực tế trên phần cứng thật (Issue #169).

---

## 1. Bảng Quyết định V2 Đã Được Owner Phê Duyệt (OWNER_APPROVED_DESIGN)

| ID Quyết định | Hợp phần / Phạm vi | Tóm tắt Quyết định Được Duyệt | Trạng thái & Thẩm quyền phê duyệt |
|---|---|---|---|
| **DEC-SEC-01** | Cryptographic Trust | Thỏa thuận khóa Ephemeral X25519 ECDH tại biên (Node $\leftrightarrow$ Gateway). Backend **Zero-Knowledge** đối với bí mật $Z$ và các khóa phiên dữ liệu unicast $K_{\text{SESSION\_UP}}$, $K_{\text{SESSION\_DOWN}}$. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-02** | MQTT Contract | Giữ nguyên PR #123 (`session-keys.schema.json`) phục vụ V1 lịch sử; áp dụng Phương án B (Session Binding Ticket) cho V2 ở Issue tiếp nối #128. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-03** | Wire Codepoint | Phê duyệt thiết kế sơ bộ gói tin `UP_JOIN_READY` (`0x49`, 31B) với cơ chế xác thực kép: `GW_READY_TAG` (8B) cho Gateway và `BACKEND_READY_PROOF` (16B) cho Backend. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-04** | Security Proof | Yêu cầu bắt buộc bằng chứng phân phối mật mã xác nhận đã nhận Finish (`FINISH31`) trong `BACKEND_READY_PROOF` trước khi Backend lập lịch hoạt động. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-05** | State Machine | Khóa phiên mới sinh được đóng băng ở trạng thái `INSTALLED_INACTIVE` đến đúng ranh giới $K_{\text{target}}$; bắt buộc vượt qua 8 tầng bảo vệ fail-closed trước khi phát sóng. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-06** | Hardware / NVS | Bộ đếm `JOIN_COUNTER` phải được commit tăng bền vững vào NVS flash trước khi gửi Hello; phát hiện lỗi đọc hoặc tua lùi bộ đếm phải khóa cứng radio. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-SEC-07** | Cryptography | Tuân thủ triệt để RFC 7748 Section 6.1: Nếu $\text{X25519}(\text{priv}, \text{pub}) == 0^{32}$, Node và Gateway lập tức hủy phiên và xóa sạch trạng thái mật mã. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06, Commit `f5dd608`) |
| **DEC-127-01** | Wire Codepoint | Phê duyệt chính thức mã bản tin sự kiện `UP_EVENT` (`0x41`, 26B) và xác nhận sự kiện tức thì `DOWN_EVENT_ACK` (`0x42`, 19B) theo thiết kế PR #189. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-127-02** | Cryptography | Chốt độ dài thẻ xác thực AES-128-CCM cho dữ liệu ứng dụng là **8 byte ($M=8$)** nhằm tối ưu hóa thời gian chiếm dụng sóng RF airtime. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-127-03** | RF PHY | MVP hỗ trợ SF7/SF8; ví dụ 400ms lịch sử là NON_NORMATIVE. Baseline DATA V2 Owner chốt 2026-11-07: `W_MS=500ms` hữu dụng + `G_MS=50ms` mỗi bên; chu kỳ Node 600ms. | `OWNER_APPROVED_MVP_CONFIG / NOT_HIL_VERIFIED` · #208 |
| **DEC-127-04** | Node Policy | Khi hàng đợi sự kiện NVS FIFO của Node đầy tải do mất kết nối kéo dài, áp dụng chính sách **`RING_BUFFER_DROP_OLDEST`** (ghi đè sự kiện cũ nhất để ưu tiên cảnh báo mới nhất). Bắt buộc lưu bền vững `DROPPED_EVENT_COUNT` trong NVS. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-MH-01** | Beacon | **SUPERSEDED:** Beacon V2 `0x43` **32B**: header16 + HMAC-SHA256-128 tag16, `KEY_ID` byte12, khóa nhóm 256-bit per-Gateway qua trusted out-of-band provisioning; Ed25519-80B cũ không còn là định dạng đích. Beacon không được ký lệnh đổi lịch. | `OWNER_APPROVED_MVP_DESIGN / NOT_IMPLEMENTED` · #209/#208 |
| **DEC-MH-02** | Wire Codepoint | Phê duyệt chính thức mã bản tin sức khỏe định kỳ `UP_HEALTH_REPLY` (`0x44`, 21B, AES-128-CCM) theo thiết kế PR #190. *Bổ chính #201:* Khẳng định ngân sách 21B không có trường cho `DROPPED_EVENT_COUNT`; kênh truyền tải số liệu mất gói theo dõi dưới `DEC-MH-08`. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |

---

## 2. Bảng Quyết định Ứng viên & Mở (CANDIDATE & OPEN_DECISION)

| ID / Nguồn | Vấn đề | Đề xuất giải quyết / Quy tắc candidate | Trạng thái & Cơ quan phụ trách |
|---|---|---|---|
| **DEC-MH-03** | Maintenance cadence | Danh định ~300s giữa các Maintenance Superframe; Maintenance bao gồm Beacon, Health theo Node và Shared Control theo nhu cầu. Join dùng CAD bất đồng bộ **mọi lúc**, không bắt buộc trong Maintenance. Thời lượng Maintenance và RF overhead là timing profile riêng. | `OWNER_APPROVED_MVP_DIRECTION / TIMING_TO_IMPLEMENT` · #208 |
| **DEC-MH-04** | Beacon miss/holdover | Sau **hơn 3 Beacon liên tiếp** không nhận được, Node ghi nhận trạng thái mất kết nối (`N_MISSED > 3`). Đây là ngưỡng báo trạng thái; DATA TX phải tạm khóa sớm hơn nếu bound sai số clock vượt Guard/thiếu đồng bộ đáng tin cậy, lịch không tự hết hạn. | `OWNER_APPROVED_MVP_MONITORING_RULE / CLOCK_BOUND_NOT_HIL_VERIFIED` · #208 |
| **DEC-MH-05** | Schedule migration | **Bãi bỏ countdown 3→2→1** và Schedule Lease. Một Maintenance on-demand dùng Backend-signed `DOWN_SCHED_PREPARE` **80B** → per-Node `UP_SCHED_READY 0x4C` **41B** (R=400ms hữu dụng, G_R=50ms mỗi bên) → Backend-signed `DOWN_SCHED_DECISION` **80B** COMMIT/ABORT. Chỉ COMMIT sau khi Backend xác minh **100% READY của mọi Node bị ảnh hưởng**, kể cả offline; kích hoạt ở K_TARGET, mất quyết định thì fail-closed. | `OWNER_APPROVED_MVP_DESIGN / CODEPOINT_0x4B_0x4D_CANDIDATE / NOT_IMPLEMENTED` · #208 |
| **DEC-MH-06** | Rào chắn bán song công SX1276 | Thiết lập khoảng bảo vệ tối thiểu giữa RX và TX turnaround để tránh xung đột phần cứng khi radio đang nhận packet. | `CANDIDATE` (Chờ đo đạc #169) · Embedded / RF |
| **DEC-127-05** | SLA ghi bền vững WAL tại Gateway | Xác định giới hạn mili-giây cho thao tác ghi SQLite/WAL tại Gateway trước khi phát `DOWN_EVENT_ACK` trên RF để cam kết 0% mất dữ liệu. | `OPEN_DECISION` · Gateway Engine / SQLite |
| **DEC-127-06** | DATA slot timing SF7/SF8 | Baseline triển khai: `NODE_ID == SLOT_INDEX` 1..15, `W_MS=500ms` hữu dụng bao gồm UP_EVENT→GW durable WAL→immediate DOWN_EVENT_ACK cùng Slot; `G_MS=50ms` mỗi bên; full Slot 600ms, 15 Slot = 9000ms chưa tính superframe overhead. Thay W live phải qua signed migration + 100% READY. Guard và timing có thể điều chỉnh bằng versioned profile, không mặc định timing/HIL PASS. | `OWNER_APPROVED_MVP_NUMERIC_CONFIG / HIL_NOT_VERIFIED` · #208 |
| **DEC-MH-07** | Beacon Window | `DOWN_SYNC_BEACON 0x43` **32B HMAC** thay thế mục tiêu 80B Ed25519. Cửa sổ Beacon phải chứa PHY ToA SF7/SF8 + turnaround/guard; không mặc định 250ms hay 400ms là đã được đo. Beacon trong Maintenance (~300s recurrence), không có Beacon ở DATA Slot0. | `OWNER_APPROVED_MVP_BEACON / HIL_NOT_VERIFIED` · #209/#208 |
| **DEC-MH-08** | Diagnostic packet | `UP_DIAG_METRICS 0x4A` **23B** được Owner phê duyệt: V2 header7 (AAD), encrypted `DROPPED_EVENT_COUNT:u32BE + DIAG_SEQ:u32BE` 8B, CCM-8 tag8. Health 0x44/21B giữ nguyên; Diagnostics chỉ TX trong Normal Maintenance Management cơ hội đã cấp, hoãn khi Schedule Migration. | `OWNER_APPROVED_MVP_WIRE_DESIGN / IMPLEMENTATION_NOT_VERIFIED` · #204/#205 |

---

## 2A. Baseline bổ sung ngày 2026-11-07 — chuẩn bị triển khai V2

**Quyết định mới nhất của Owner ưu tiên hơn mô tả lịch sử và draft chưa đồng bộ.**

| Scope | Baseline triển khai | Trạng thái |
| --- | --- | --- |
| Join CAD | Node Join bất kỳ lúc nào, CAD/backoff, tối đa 3 retry sau lần đầu; Gateway đáp Join ngay khi Backend chấp thuận và radio có thể TX, chấp nhận collision Event/ACK; Event retry ở lượt Slot Node tiếp theo | OWNER_APPROVED_MVP_DESIGN #208 |
| Reboot Node | DATA_TX_DISABLED, RX_ONLY, cần Backend kích hoạt lại và xác minh session/sync/schedule; không tự TX chỉ vì có NVS schedule | OWNER_APPROVED_MVP_DESIGN #208 |
| Diagnostic | 0x4A 23B; giữ Health 21B; REPORT chỉ trong Normal Maintenance Management khi được cấp | OWNER_APPROVED_MVP_WIRE_DESIGN #204 |
| Beacon key | 256-bit random per-Gateway K_BEACON, trusted local OOB provisioning cho Gateway/Node; byte12 KEY_ID; HMAC-SHA256-128; key compromise có thể spoof Beacon, không authorize schedule | OWNER_APPROVED_MVP_SECURITY_DESIGN #209 |
| Schedule wire | Backend Ed25519 PREPARE 80B, SCHED_READY 0x4C 41B, DECISION Ed25519 80B; candidate 0x4B/0x4D cần wire registry agreement | OWNER_APPROVED_MVP_DESIGN #208 |
| No Schedule Lease | Lịch đã COMMIT tiếp tục có hiệu lực tới khi đổi lịch với 100% READY và COMMIT ký, không tự hết hạn theo thời gian | OWNER_APPROVED_MVP_DESIGN #208 |

**Verification:** Bắt đầu code/test không phụ thuộc HIL toàn diện, nhưng không đánh dấu timing/legal/security/HIL PASS khi chưa có bằng chứng. Review trước RF deploy.

## 3. Bảng Quyết định Lịch sử (D01 .. D13) và Trạng thái Chuyển đổi V2

| ID Lịch sử | Vấn đề gốc | Trạng thái hiện tại trong Kiến trúc V2 | Phân loại & Tham chiếu |
|---|---|---|---|
| **D01 §6.1** | Header 8B + CRC16 thiếu xác thực | Đã thay thế hoàn toàn bằng Header Unicast V2 7B + AES-128-CCM-8. Bản tin 0x45..0x49 và 0x41..0x44 đã được phê duyệt thiết kế. | `OWNER_APPROVED_DESIGN` · Xem `specification.md` |
| **D02 §5.1** | Profile Superframe P-10S-15 | Đã bãi bỏ khe tranh chấp PCSS. Thay thế bằng mô hình Static DATA Superframe + Maintenance Superframe (~300s). | `OWNER_APPROVED_DESIGN` · Xem `tdma-schedule.md` |
| **D03 §1** | Pháp lý tần số 921.4 MHz và airtime | Tuân thủ băng tần VN920 (920.250–922.750 MHz); hạn ngạch Node $\le 1.0\%$, GW $\le 10\%$. Công suất phát $\le +14\text{ dBm}$. | `CONFIRMED` / Chờ HIL #169 |
| **D04 §5.2** | Giả định jitter DIO0 < 50µs | Bắt buộc đo kiểm thực tế trên bench hardware. | `BLOCKED` trên Issue #169 |
| **D05 §5.3** | Chuyển lịch/Countdown lịch sử | Countdown 3→2→1 **SUPERSEDED** bởi signed PREPARE→100% distinct Schedule READY→signed COMMIT/ABORT tại K_TARGET, tất cả trong một Maintenance nếu đủ thời gian. Quyền DATA của Node mới sau Join vẫn phải chờ Backend-authorized activation riêng. | `OWNER_APPROVED_MVP_DESIGN` · #208 |
| **D06 §6.3** | Namespace MQTT topics | Sử dụng định dạng chuẩn `iot/v1/gw/{gateway_id}/...`. | `CONFIRMED` · ADR-0002 |
| **D07 §6.3** | Cờ retain trên topic schedule | Cấm retain=true cho downlink schedule để tránh kích hoạt lịch cũ sau khởi động lại. | `CONFIRMED` |
| **D08 §6.3** | Phiên bản giao thức MQTT | Bắt buộc MQTT 5.0 (Mosquitto 2.0) với QoS1 và User Properties. | `OWNER_ACCEPTED` (PR #26 MERGED) |
| **D09 §6.2** | Định dạng giá trị cảm biến thô | `UP_EVENT` truyền `raw integer` (`EVENT_VALUE: i16`); Backend chịu trách nhiệm quy đổi theo cấu hình loại cảm biến. | `OWNER_APPROVED_DESIGN` |
| **D10 §6.2** | Thiếu mã kích hoạt cảnh báo | `UP_EVENT` bổ sung trường `EVENT_CODE (1B)` xác thực rõ ràng loại cảnh báo. | `OWNER_APPROVED_DESIGN` |
| **D11 §5.3** | `SCHED_VER` 8-bit wrap-around | Không dùng modulo-256; phiên bản lịch được gắn chặt với Epoch và thế hệ phiên bảo mật (`SESSION_SEL`). | `OWNER_APPROVED_DESIGN` |
| **D12 §6.3** | Tràn bộ đệm sự kiện tại Gateway | Bắt buộc Gateway có giới hạn buffer, bộ đếm tràn và ghi WAL trước khi xác nhận. | `CONFIRMED` |
| **D13 §9.3** | Xác thực JWT / RBAC tại Backend | Enforce RBAC tại Backend; OpenAPI mang tính chất provisional cho đến khi có ADR xác thực người dùng. | `CONFIRMED` |

---

## 4. Điều kiện Tiên quyết Mở khóa Cổng Kỹ thuật (Gating Prerequisites)

- **Cổng G1 (RF & PHY Timing):** Phụ thuộc tuyệt đối vào kết quả đo đạc thực tế thời gian chiếm sóng ToA, jitter ngắt, độ trôi dạt thạch anh và công suất phát tại **Issue #169**. Không được phép công nhận PASS từ tài liệu lý thuyết.
- **Cổng G2 (Security & Protocol Cryptography):**
  - **Issue #173:** Hoàn thành bộ Golden Vectors kiểm tra chéo Go $\leftrightarrow$ ESP-IDF mbedTLS cho HKDF-SHA256, HMAC và X25519.
  - **Issue #174:** Kiểm thử tích hợp thực tế với broker Mosquitto 2.0 xác minh mTLS ACL cho từng định danh Gateway.
  - **Issue #175:** Kiểm thử HIL ngắt nguồn đột ngột (Power-Loss Fault Injection) xác minh tính toàn vẹn của NVS flash và bộ đếm monotonic trên Gateway/Node.
- **Cổng G4 (Contract Schemas & Migrations):** Đăng ký JSON Schemas cho Session Binding Ticket V2 (Issue #128) và kiểm thử hợp đồng tự động.
- **Cổng G5/G6 (HIL & Triển khai Hiện trường):** Thử nghiệm tải thực tế trên thiết bị phần cứng; không suy diễn kết quả từ mô phỏng.
