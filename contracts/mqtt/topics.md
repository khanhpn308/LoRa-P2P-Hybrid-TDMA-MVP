# MQTT Contract v1 — Gateway ↔ Mosquitto ↔ Backend Go
**Version:** `0.2.0-draft` · **MQTT 5.0:** `OWNER_ACCEPTED` (ADR-0002) · **V2 Architecture Alignment:** `EVENT-ONLY / STATIC TDMA` (Issue #128, Umbrella #125) · **Implementation:** `NOT_VERIFIED`.

## 1. Topics, QoS và ownership

Root `iot/v1/gw/{gateway_id}`. **MQTT 5.0 bắt buộc** cho Gateway và Backend (xem [ADR-0002](../../docs/adr/0002-mqtt-5.md)); MQTT 3.1.1 không thuộc contract v1. Dùng TLS với xác thực broker/Gateway, ACL theo **authenticated principal** (username/verified client certificate); ràng buộc với gateway_id, không tin ClientID tự khai báo; chỉ profile `dev-insecure` localhost bị cô lập mới được chạy cleartext.

| Suffix | Publisher → Consumer | QoS | Retain | Schema / Giao thức V2 | Trạng thái |
|---|---|---:|---|---|---|
| `uplink/telemetry` | Gateway → Backend | 1 | false | [telemetry](schemas/telemetry.schema.json) | **DEPRECATED_LEGACY** (Cấm phát sinh mới ở V2; chỉ đọc log lịch sử) |
| `uplink/alert` | Gateway → Backend | 1 | false | [alert](schemas/alert.schema.json) (V2 `UP_EVENT` 0x41, 26B) | **ACTIVE_V2_EVENT_PLANE** (Sự kiện vượt ngưỡng cảm biến) |
| `uplink/status` | Gateway → Backend | 1 | true | [status](schemas/status.schema.json) (V2 Health 0x44 & Diag 0x4A, VN920) | **ACTIVE** (Snapshot vận hành, kênh VN920, hàng đợi/mất gói) |
| `uplink/schedule-ack` | Gateway → Backend | 1 | false | [schedule-ack](schemas/schedule-ack.schema.json) | **ACTIVE** (Xác nhận STAGE_ACK / VERIFY_NACK / ACTIVE_REPORT) |
| `uplink/command-ack` (bổ sung đề xuất) | Gateway → Backend | 1 | false | [command-ack](schemas/command-ack.schema.json) | **ACTIVE** (Kết quả thi hành lệnh Node, phân biệt NODE_ACKED) |
| `uplink/join-hello` (NEW · V2) | Gateway → Backend | 1 | **false** | [join-hello](schemas/join-hello.schema.json) (V2 `UP_JOIN_HELLO` 0x45, 68B) | **ACTIVE_V2_JOIN_PLANE** (Relay bản tin Hello gia nhập mạng V2) |
| `uplink/session-key-ack` (NEW · DRAFT) | Gateway → Backend | 1 | **false** | [session-key-ack](schemas/session-key-ack.schema.json) | **DRAFT** (Xác nhận cài đặt khóa phiên bền vững vào NVS) |
| `downlink/schedule` | Backend → Gateway | 1 | **false** | [schedule](schemas/schedule.schema.json) | **ACTIVE_V2** (Lịch TDMA tĩnh V2: W500/G50, 15 khe 9000ms) |
| `downlink/command` | Backend → Gateway | 1 | false | [command](schemas/command.schema.json) | **ACTIVE** (Lệnh điều khiển Node; cấm SET_PERIODIC_MODE) |
| `downlink/session-key-install` (NEW · DRAFT) | Backend → Gateway | 1 | **false** | [session-key-install](schemas/session-key-install.schema.json) | **DRAFT** (Cài đặt cặp khóa phiên được bọc AES-256-GCM) |

Gateway chỉ publish `uplink/#` và subscribe `downlink/#` của **chính mình**; Backend ngược lại. Topic `gateway_id` phải khớp danh tính đã được Broker xác thực; payload `gateway_id` phải khớp topic/identity (semantic check), không dùng riêng `ClientID` tự khai báo để cấp quyền. Web/Mobile không truy cập MQTT trực tiếp. Không tạo ngầm alias `iot/gw/{id}/control/schedule/set` hay `uplink/sched_ack` nêu trong tài liệu đính kèm: namespace canonical là của repository.

## 1.1. MQTT 5.0 — session và expiry

| Luồng | Quy tắc MQTT 5.0 |
|---|---|
| Gateway CONNECT | `Clean Start=1`, `Session Expiry Interval=0`; subscribe lại sau reconnect. Uplink offline buffer giới hạn tại Gateway. |
| Backend CONNECT | Client ID cố định; `Clean Start=0`, `Session Expiry Interval>0`. Thời hạn, queue limit và broker persistence phải cấu hình/kiểm thử trước triển khai. |
| `downlink/schedule`, `downlink/command` | **Bắt buộc** `Message Expiry Interval` (giây nguyên dương, không vượt thời gian còn lại đến `expires_at` tại lúc publish); không publish nếu còn <1 giây hoặc đã quá hạn. `Retain=false`. |
| Tất cả topics | QoS/Retain theo bảng trên; MQTT 5 Reason Codes cần được log. Không bắt buộc User Properties hoặc Topic Alias. |

**Message Expiry không thay `expires_at`:** Gateway phải kiểm tra thời hạn bằng đồng hồ tin cậy và xác thực ID/version. Broker PUBACK không có nghĩa là command đã được Node thực thi. Backend reconcile schedule/status sau reconnect, không điều khiển từng slot bằng MQTT.

## 2. Envelope & dữ liệu

MQTT JSON UTF-8; `schema_version="1.0-draft"` độc lập với tiền tố topic `v1`. `event_id` phải duy nhất ổn định qua QoS1 retry và offline-buffer replay, có `gateway_epoch` UUID boot-session và `event_seq` dạng chuỗi thập phân (tránh lỗi JS > 2^53). Backend lưu unique `(gateway_id,event_id)`. Tuyệt đối không chỉ dùng `SEQ_NUM` 8-bit hoặc thời gian phát để deduplicate; node reset / rollover làm trùng.

`observed_at` là RFC3339 UTC hoặc null; `observed_time_source` nêu cơ sở clock, `radio_rx_monotonic_us` là chuỗi thời gian tương đối theo boot Gateway, `buffered` xác định sự kiện phát lại. Backend gán `ingested_at` bằng server clock. `data` truyền integer raw RF §6.2; unit/scale cần mapping theo phiên bản cấu hình cảm biến, không suy diễn. Nếu PRIORITY_ALERT 12B thiếu kênh/ngưỡng thì **không bịa `trigger`**; trường này optional đến khi RF v1 được duyệt.

QoS1 có thể giao trùng và sai thứ tự; không có cam kết latency, exactly-once hay bảo đảm buffer không bao giờ tràn. Gateway cung cấp `offline_dropped_telemetry`, `offline_dropped_alert` khi mất dữ liệu; `event_id` của một bản ghi không đổi khi resubmit.

## 3. Transaction lịch TDMA

Backend: `PROPOSED → SENT → STAGED → ACTIVE` hoặc `REJECTED / EXPIRED`; Gateway: validate → stage shadow NVS → chuyển đổi lịch V2 trong chu kỳ Maintenance on-demand qua `DOWN_SCHED_PREPARE` (80B) $\to$ 100% `UP_SCHED_READY 0x4C` (41B) $\to$ `DOWN_SCHED_DECISION` (80B) COMMIT tại $K_{\text{TARGET}}$ (bãi bỏ hoàn toàn cơ chế countdown $3 \to 2 \to 1$ qua Beacon và Schedule Lease theo DEC-MH-05, D05, #208 / PR #206) → report `ACTIVE_REPORT`.

- `STAGE_ACK`: Gateway đã validate/persist; **không** chứng minh các Node nhận được lịch và **không** cho Backend cập nhật ACTIVE.
- `VERIFY_NACK`: từ chối với `reason_code`; active trước đó giữ nguyên.
- `ACTIVE_REPORT`: Gateway đã kích hoạt thực tế. Backend chỉ đánh ACTIVE khi `request_id`, `schedule_version`, identity và mốc activation khớp.

`downlink/schedule retain=false`: retained stale schedule nguy hiểm sau reboot. Sau reconnect Backend đối chiếu retained `uplink/status` (chỉ phản ánh last-known), rồi resend request còn hiệu lực nếu cần. Gateway phải reject `expires_at` đã qua/clock không đáng tin, duplicate cũ, sai gateway, slot trùng, thông số airtime lỗi. Gateway tự chọn SF activate đủ xa; Backend **không** điều khiển radio từng slot. MQTT 5.0 Message Expiry là bắt buộc khi publish schedule/command, nhưng không thay `expires_at` validation (mục 1.1).

## 4. Downlink commands và xác nhận

`command_id` idempotent; `created_at/expires_at` bắt buộc, action theo allowlist và RBAC chỉ do Backend kiểm. `uplink/command-ack` (proposed) phân biệt `QUEUED`, `DISPATCHED`, `NODE_ACKED`, `REJECTED`, `EXPIRED`, `UNKNOWN`. Broker PUBACK **không phải** chứng cứ Node thi hành lệnh. Gateway không phát lệch slot hoặc vượt airtime policy. `uplink/status` retained không chứng minh thiết bị đang online; Backend phải có timeout/LWT và server ingest time.

## 5. Quy tắc chính xác và tài liệu chi tiết

Các ràng buộc **MUST/SHOULD**, state transition table, error-code ownership, trường phân biệt planned/actual activation, checklist 7 schemas, ví dụ/negative scenarios nằm tại [semantic-rules.md](semantic-rules.md). Đây là phần hợp đồng cần Gateway/Backend/Infra-Security review, không phải chứng cứ chạy test.

- MQTT 5 `SUBACK`: nếu subscription yêu cầu QoS 1 thì Granted QoS `0x01` mới đáp ứng profile; `0x00` là downgraded QoS 0, không đánh dấu pipeline `READY`.
- `downlink/#`: subscribe `Retain Handling=2` để không nhận retained history ở thời điểm SUBSCRIBE; vẫn phải reject bất kỳ retained/live stale proposal nếu xuất hiện. Không dùng cờ `RETAIN` đơn lẻ làm chứng cứ freshness.
- Broker TLS/ACL: bind topic identity theo authenticated username/certificate; `ClientID` do client tự khai báo không phải credential.
- Session: `Clean Start` và `Session Expiry` độc lập; Will Delay có thể kết thúc sớm khi `Session Expiry=0`. `uplink/status` retained chỉ là snapshot; online/offline phải đối chiếu thời điểm ingest/timeout/broker connection/LWT design được duyệt.
- MQTT `PUBACK` trên từng hop không đồng nghĩa Go DB commit hay radio application ACK; Backend cần thiết kế commit-before-ACK và durable idempotency ở Issue #18 (chưa triển khai/verify ở #14).

## 6. Negative tests / giới hạn

- QoS1 duplicate, reconnect và offline replay: giữ ID, chỉ lưu một lần vào DB.
- MQTT 5.0: thử CONNECT/session, Message Expiry (thiếu, quá dài, hết hạn), Reason Codes và khởi động lại Broker/Gateway.
- Expired, retained stale, wrong gateway, non-monotonic version, overlapping slot, thiếu announcement horizon → NACK/fail closed.
- Thiếu/nhầm ACL hoặc command quá hạn → từ chối.
- JSON Schema không thay được kiểm tra liên trường: unique slot/node, thời hạn với clock, transition hợp lệ và airtime.
- [Fixture](examples/cases.json) / [Hướng dẫn kiểm thử](../verification.md): chỉ là synthetic test; HIL/consumer approval **NOT_VERIFIED**.

## 7. SESSION_KEY_INSTALL / SESSION_KEY_ACK (new versioned draft)

Based on OWNER_APPROVED design decisions `MQTT-SESSION-KEY-01`, `MQTT-KEY-WRAP-01`, `MQTT-KEY-ACK-01` ([PR #116](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568895005)). Detailed cryptographic/cross-field proposal: [session-key-security.md](session-key-security.md), `schemas/session-key-{install,ack}.schema.json`, `examples/session-key-cases.json`. Reconciled with Event-Only architecture and V2 Join Protocol (#125, #126, #127, #128, #136, #154).

- New messages are `schema_version="1.1-draft"`; existing older 1.0-draft schema/fixtures are not silently rewritten in this PR. Cross-team version compatibility review required.
- `gateway_id` remains a **string** MQTT identity (e.g. `gw01`), distinct from `target_gw_id:uint8` RF code; enforce an authenticated Backend-provisioned mapping. In MVP, Gateways hold exclusive VN920 channels CH00–CH10 (Issue #154).
- `downlink/session-key-install`: QoS1, Retain=false, MQTT5 Message Expiry Interval bounded by `install_deadline`. Install requires authentic Node key confirmation (`UP_JOIN_CONFIRM:19B` in V1, or `UP_JOIN_KEY_CONFIRM:31B` / `DOWN_JOIN_FINISH:31B` in V2 #127/#136) and current authorized target/assignment. Ciphertext=64B (UP[32]||DL[32]) under per-Gateway AES-256-GCM is an Owner-approved V1 design; V2 key distribution vs local derivation is `OPEN_DECISION / BLOCKED_BY_#127`. No bootstrap root/confirm key is transmitted.
- `uplink/session-key-ack`: QoS1, Retain=false, application-level HMAC. `INSTALLED` is sent only after secure *inactive* persistence. MQTT PUBACK alone never advances install state.
- Post-install activation: Key installation places the slot into `INSTALLED_INACTIVE` on the Gateway; it does not grant TDMA DATA slot or active lease. Pre-staging before `not_before` is permitted, but keys cannot be used for DATA TX before `not_before` or after `expires_at`. In V2 flow (#136, #208), Node readiness `UP_JOIN_READY` (0x49, verified at edge via `K_KC_UP`, not data session keys) and Backend TDMA schedule staging occur only after successful session key installation; schedule cutover uses PREPARE → 100% READY → DECISION COMMIT at $K_{\text{TARGET}}$ (countdown 3→2→1 is superseded per Owner Decision #208 / PR #206).
- Event-Only data plane (#125): Key installation enables cryptographic verification for event-triggered transmissions (`Event TX → ACK RX`) and Maintenance superframe health sync; periodic business telemetry remains superseded.
- Static JSON Schema validation ≠ GCM tag verification, authenticated current session, durable Flash write, G2/G4 or radio tests. This contract is pending cross-team/G2 security review.

## 8. Đăng ký kênh độc quyền VN920_V1 & Ranh giới vòng đời (#154)

Theo Quyết định Owner (2026-11-05), Backend Go quản lý đăng ký kênh độc quyền trong bảng CSDL PostgreSQL:
- **Kênh hợp lệ:** CH00–CH10 (tương ứng 920.250 MHz đến 922.750 MHz, khoảng cách kênh 250 kHz, băng thông 125 kHz BW).
- **Tính độc quyền:** Mỗi Gateway được gán tối đa 1 kênh; không chia sẻ kênh giữa các Gateway trong MVP.
- **Ranh giới trạng thái (State Hierarchy):**
  1. `CHANNEL_ALLOCATED`: Gateway đã được Backend cấp phát kênh trong CSDL qua REST API (`POST /api/v1/gateways/{id}/channels/request`). Trạng thái này **chưa cho phép phát sóng RF**.
  2. `SCHEDULE_STAGED`: Gateway đã nhận và lưu bền vững cấu hình lịch TDMA dự phòng từ Backend (`downlink/schedule`).
  3. `SCHEDULE_ACTIVE`: Gateway đã kích hoạt lịch TDMA thực tế tại ranh giới superframe và báo cáo `ACTIVE_REPORT`.
  4. `RF_AUTHORIZED`: Gateway đã hội tụ đủ: Kênh được cấp + Lịch ACTIVE hợp lệ + Đồng hồ UTC tin cậy + Giới hạn Duty Cycle an toàn. Chỉ khi đạt trạng thái này mới được phát sóng RF.
- **Quan hệ với MQTT:** Gateway công bố `channel_id` (VD: `"CH04"`) trong bản tin snapshot `uplink/status`. Nếu Gateway bị thu hồi kênh hoặc chưa được cấp kênh, nó không được phép kích hoạt lịch phát RF.

## 9. Phân định bốn tầng xác nhận (Four-Layer Confirmation Model)

Tuyệt đối không đánh đồng hoặc suy diễn các tầng xác nhận sau:
1. **RF ACK (`DOWN_EVENT_ACK 0x42`, 19B):** Gateway gửi trả về Node ngay trong cùng khe DATA sau khi đã lưu bền vững sự kiện vào WAL/SQLite cục bộ. Node dựa vào đây để xóa/latch sự kiện trong NVS.
2. **MQTT Transport PUBACK:** Broker Mosquitto xác nhận hop truyền mạng qua giao thức MQTT 5.0 QoS 1. Gói tin đến broker **không** đồng nghĩa Backend Go đã commit vào CSDL.
3. **Backend DB Commit:** Backend Go nhận bản tin MQTT, kiểm tra tính lũy thừa qua `UNIQUE(gateway_id, event_id)`, lưu bền vững vào bảng PostgreSQL. Nếu trùng lặp, backend khử trùng lặp an toàn.
4. **UI Acknowledgement:** Người vận hành gọi REST endpoint `POST /api/v1/alerts/{id}/acknowledge` để xác nhận đã xử lý cảnh báo trong quy trình làm việc con người. Hành động này **không phát sinh bất kỳ bản tin RF ACK nào** xuống Node.

## 10. V2 Join Hello Relay Envelope (`uplink/join-hello`) (#221)

Chuyển tiếp bản tin gia nhập mạng V2 `UP_JOIN_HELLO` (0x45, 68B) nhận được từ sóng RF lên Backend Go qua broker Mosquitto:
- **Nguyên tắc Zero-Knowledge biên:** Gateway SX1276 chỉ đóng gói khung tin thô 68 byte (`raw_frame_hex`), metadata sóng RF (`rssi`, `snr`), định danh trạm đích (`target_gw_id`) và timestamp vào envelope. Gateway **tuyệt đối không nắm giữ** khóa gốc $K_{\text{JOIN}}$ hay khóa yêu cầu $K_{\text{JREQ}}$ và không được can thiệp sửa đổi byte nào trong khung 68B.
- **Ràng buộc định danh trạm (Identity Binding):** Broker MQTT xác thực Gateway qua TLS client certificate (mTLS principal). Topic `iot/v1/gw/{gateway_id}/uplink/join-hello` và trường `gateway_id` trong payload phải khớp chính xác với danh tính đã xác thực. Backend độc lập ánh xạ `gateway_id` sang mã số trạm nội bộ và đối chiếu với `target_gw_id` trong payload cũng như byte 7 (`TARGET_GW_ID`) của khung tin thô; nếu không khớp, gói tin bị từ chối fail-closed.
- **Tính lũy thừa & Khử trùng lặp:** Bản tin xuất bản với QoS 1, `Retain=false`. Khử trùng lặp hop mạng thông qua `(gateway_id, event_id)` với `event_id` bất biến `gateway_id:gateway_epoch:event_seq`. Tại tầng ứng dụng, Backend thực hiện khóa hàng (`FOR UPDATE`) trên bảng CSDL PostgreSQL, kiểm tra tính đơn điệu của `JOIN_COUNTER` và đối chiếu SHA-256 (`raw_hello_sha256`) để bảo đảm xử lý idempotent cho các gói tin truyền lại nguyên vẹn hoặc từ chối đòn tấn công phát lại (Replay Attack).
