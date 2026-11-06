# Điểm cần chốt và sai khác giữa tài liệu thiết kế với baseline repo

**Quy tắc phân loại trạng thái:**
- `OWNER_APPROVED_DESIGN`: Thiết kế đã được Project Owner phê duyệt chính thức bằng văn bản/commit; làm cơ sở ràng buộc kiến trúc nhưng chưa đồng nghĩa với hoàn tất kiểm thử vật lý hay code production.
- `CONFIRMED`: Chủ đích kiến trúc đã được xác nhận trong ADR hoặc baseline repo.
- `CANDIDATE`: Đề xuất kỹ thuật đang chờ xem xét liên chức năng và phê duyệt từ Owner.
- `OPEN_DECISION`: Vấn đề kỹ thuật mở cần lựa chọn phương án trước khi đóng băng hợp đồng.
- `BLOCKED`: Điểm nghẽn kỹ thuật bắt buộc phải có ADR mới hoặc bằng chứng đo đạc vật lý G1/G2 trước khi đóng băng.

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
| **DEC-127-03** | RF PHY / TDMA | Áp dụng **Lựa chọn A: Giới hạn vận hành hệ thống MVP V1 chỉ ở SF7 và SF8** (nguyên tắc khe 400ms). *Bổ chính #201:* Hình minh họa cửa sổ con $100\text{ms}/20\text{ms}/100\text{ms}$ và phong bì 220ms không hợp lệ cho SF8 (ToA Event 113.152ms, ACK 102.912ms). Việc tái phân bổ cửa sổ con cho SF8 trong khe 400ms được theo dõi dưới `DEC-127-06`. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-127-04** | Node Policy | Khi hàng đợi sự kiện NVS FIFO của Node đầy tải do mất kết nối kéo dài, áp dụng chính sách **`RING_BUFFER_DROP_OLDEST`** (ghi đè sự kiện cũ nhất để ưu tiên cảnh báo mới nhất). Bắt buộc lưu bền vững `DROPPED_EVENT_COUNT` trong NVS. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-MH-01** | Wire Codepoint | Phê duyệt chính thức mã bản tin đồng bộ mạng `DOWN_SYNC_BEACON` (`0x43`, 80B) mang chữ ký số Ed25519 (64B) theo thiết kế PR #190. Bố cục wire được đóng băng an toàn. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |
| **DEC-MH-02** | Wire Codepoint | Phê duyệt chính thức mã bản tin sức khỏe định kỳ `UP_HEALTH_REPLY` (`0x44`, 21B, AES-128-CCM) theo thiết kế PR #190. *Bổ chính #201:* Khẳng định ngân sách 21B không có trường cho `DROPPED_EVENT_COUNT`; kênh truyền tải số liệu mất gói theo dõi dưới `DEC-MH-08`. | `OWNER_APPROVED_DESIGN` · Owner Phê duyệt (2026-11-06) |

---

## 2. Bảng Quyết định Ứng viên & Mở (CANDIDATE & OPEN_DECISION)

| ID / Nguồn | Vấn đề | Đề xuất giải quyết / Quy tắc candidate | Trạng thái & Cơ quan phụ trách |
|---|---|---|---|
| **DEC-MH-03** | Chu kỳ xen kẽ Khe Bảo trì | Xen kẽ 1 chu kỳ Maintenance Superframe sau mỗi ~300s giữa các chu kỳ Static DATA Superframe (~10s). | `CANDIDATE` · Gateway / MAC Scheduler |
| **DEC-MH-04** | Ngưỡng khóa sóng do mất Beacon | Cho phép Holdover khi $N_{\text{MISSED}} \in \{1, 2\}$ nếu drift $\le 25\text{ms}$; khóa cứng phát sóng fail-closed khi $N_{\text{MISSED}} \ge 3$. | `CANDIDATE` · Node Clock Manager / MAC |
| **DEC-MH-05** | Đồng bộ chuyển lịch 3 chu kỳ | Phát cờ đếm ngược $3 \to 2 \to 1$ trong Beacon và yêu cầu 100% Node bị ảnh hưởng sẵn sàng trước khi cắt chuyển lịch active. | `CANDIDATE` (Đồng bộ với SEC-05) · GW / Backend |
| **DEC-MH-06** | Rào chắn bán song công SX1276 | Thiết lập khoảng bảo vệ tối thiểu giữa RX và TX turnaround để tránh xung đột phần cứng khi radio đang nhận packet. | `CANDIDATE` (Chờ đo đạc #169) · Embedded / RF |
| **DEC-127-05** | SLA ghi bền vững WAL tại Gateway | Xác định giới hạn mili-giây cho thao tác ghi SQLite/WAL tại Gateway trước khi phát `DOWN_EVENT_ACK` trên RF để cam kết 0% mất dữ liệu. | `OPEN_DECISION` · Gateway Engine / SQLite |
| **DEC-127-06** | Tái phân bổ cửa sổ con trong Khe Tĩnh cho SF8 (TIM-01) | Cửa sổ con cũ $100\text{ms}/20\text{ms}/100\text{ms}$ và phong bì 220ms không đủ cho SF8. Đề xuất: Phương án A: Tái phân bổ trong khe 400ms (Lead 25ms, UP_EVENT 125ms, Turnaround/WAL 35ms, DOWN_ACK 115ms, Trailing 100ms); Phương án B: Giới hạn DATA slot ở SF7; Phương án C: Nới rộng slot lên 500ms. | `OPEN_DECISION` / `CANDIDATE` (Chờ đo đạc #169) · MAC Scheduler / RF |
| **DEC-MH-07** | Cửa sổ phát Beacon 80B trong Maintenance Superframe (TIM-02) | ToA Beacon 80B Ed25519 tại SF8 là 256.512ms > cửa sổ 250ms. Đề xuất: Phương án A: Tăng Slot 0 lên 400ms trong Maintenance Superframe (~300s); Phương án B: Khóa PHY Beacon phát ở SF7 (ToA 143.616ms). Giữ nguyên bố cục wire Ed25519 80B (`DEC-MH-01`). | `OPEN_DECISION` · Gateway / MAC Scheduler |
| **DEC-MH-08** | Cơ chế truyền tải số liệu mất mát `DROPPED_EVENT_COUNT` (MAC-01) | Bố cục 21B `UP_HEALTH_REPLY` (`DEC-MH-02`) không có trường cho `DROPPED_EVENT_COUNT`. Đề xuất: Phương án 1 (Khuyến nghị): Bản tin chẩn đoán riêng biệt (e.g. `UP_DIAG_METRICS`, 0x4A, candidate) truyền theo chu kỳ bảo trì, giữ nguyên 21B; Phương án 2: Phiên bản sửa đổi layout Health frame trong tương lai (cần Owner duyệt); Phương án 3: Bit cảnh báo trong `STATUS_FLAGS`. | `OPEN_DECISION` · MAC Protocol / Backend Go |

---

## 3. Bảng Quyết định Lịch sử (D01 .. D13) và Trạng thái Chuyển đổi V2

| ID Lịch sử | Vấn đề gốc | Trạng thái hiện tại trong Kiến trúc V2 | Phân loại & Tham chiếu |
|---|---|---|---|
| **D01 §6.1** | Header 8B + CRC16 thiếu xác thực | Đã thay thế hoàn toàn bằng Header Unicast V2 7B + AES-128-CCM-8. Bản tin 0x45..0x49 và 0x41..0x44 đã được phê duyệt thiết kế. | `OWNER_APPROVED_DESIGN` · Xem `specification.md` |
| **D02 §5.1** | Profile Superframe P-10S-15 | Đã bãi bỏ khe tranh chấp PCSS. Thay thế bằng mô hình Static DATA Superframe + Maintenance Superframe (~300s). | `OWNER_APPROVED_DESIGN` · Xem `tdma-schedule.md` |
| **D03 §1** | Pháp lý tần số 921.4 MHz và airtime | Tuân thủ băng tần VN920 (920.250–922.750 MHz); hạn ngạch Node $\le 1.0\%$, GW $\le 10\%$. Công suất phát $\le +14\text{ dBm}$. | `CONFIRMED` / Chờ HIL #169 |
| **D04 §5.2** | Giả định jitter DIO0 < 50µs | Bắt buộc đo kiểm thực tế trên bench hardware. | `BLOCKED` trên Issue #169 |
| **D05 §5.3** | Gateway chọn K+3 chuyển lịch | Đã chính thức chuẩn hóa cơ chế đếm ngược $3 \to 2 \to 1$ qua Beacon và hàng rào 100%-READY (`DEC-SEC-05`). | `OWNER_APPROVED_DESIGN` |
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
