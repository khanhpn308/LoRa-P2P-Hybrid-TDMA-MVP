# MQTT Contract v1 — Gateway ↔ Mosquitto ↔ Backend Go
**Version:** `1.1-draft` · **MQTT 5.0:** `OWNER_ACCEPTED` (ADR-0002, PR #26) · **Contract:** `DRAFT / PENDING CROSS-TEAM REVIEW` (Issue #14) · **Implementation:** `NOT_VERIFIED`.

## 1. Topics, QoS và ownership

Root `iot/v1/gw/{gateway_id}`. **MQTT 5.0 bắt buộc** cho Gateway và Backend (xem [ADR-0002](../../docs/adr/0002-mqtt-5.md)); MQTT 3.1.1 không thuộc contract v1. Dùng TLS với xác thực broker/Gateway, ACL theo **authenticated principal** (username/verified client certificate); ràng buộc với gateway_id, không tin ClientID tự khai báo; chỉ profile `dev-insecure` localhost bị cô lập mới được chạy cleartext.

| Suffix | Publisher → Consumer | QoS | Retain | Schema |
|---|---|---:|---|---|
| `uplink/telemetry` | Gateway → Backend | 1 | false | [telemetry](schemas/telemetry.schema.json) |
| `uplink/alert` | Gateway → Backend | 1 | false | [alert](schemas/alert.schema.json) |
| `uplink/status` | Gateway → Backend | 1 | true | [status](schemas/status.schema.json) |
| `uplink/schedule-ack` | Gateway → Backend | 1 | false | [schedule-ack](schemas/schedule-ack.schema.json) |
| `uplink/command-ack` (bổ sung đề xuất) | Gateway → Backend | 1 | false | [command-ack](schemas/command-ack.schema.json) |
| `downlink/schedule` | Backend → Gateway | 1 | **false** | [schedule](schemas/schedule.schema.json) |
| `downlink/command` | Backend → Gateway | 1 | false | [command](schemas/command.schema.json) |

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

MQTT JSON UTF-8; `schema_version="1.1-draft"` độc lập với tiền tố topic `v1`. **Telemetry/Alert:** `event_id` do Node tạo và giữ nguyên qua RF retry/reboot và MQTT replay; Backend lưu unique `(gateway_id,node_id,event_id)` và phát hiện conflict payload. `gateway_epoch/event_seq` chỉ theo dõi lần tiếp nhận Gateway. **Gateway-origin Status/ACK:** `event_id=gateway_id:gateway_epoch:event_seq` theo quy tắc hiện có. Format Node Event ID chờ G2.

`observed_at` là RFC3339 UTC hoặc null; `observed_time_source` nêu cơ sở clock, `radio_rx_monotonic_us` là chuỗi thời gian tương đối theo boot Gateway, `buffered` xác định sự kiện phát lại. Backend gán `ingested_at` bằng server clock. `data` truyền integer raw RF §6.2; unit/scale cần mapping theo phiên bản cấu hình cảm biến, không suy diễn. Nếu PRIORITY_ALERT 12B thiếu kênh/ngưỡng thì **không bịa `trigger`**; trường này optional đến khi RF v1 được duyệt.

QoS1 có thể giao trùng và sai thứ tự; không có cam kết latency, exactly-once hay bảo đảm buffer không bao giờ tràn. Gateway cung cấp `offline_dropped_telemetry`, `offline_dropped_alert` khi mất dữ liệu; `event_id` của một bản ghi không đổi khi resubmit.

## 3. Transaction lịch TDMA

Backend: `PROPOSED → SENT → STAGED → ACTIVE` hoặc `REJECTED/EXPIRED`; User phê duyệt lịch và `activation_window`. Gateway validate → persist Shadow → announce/collect affected Node prepare ACK → verify old slot lease safe expiration → activate tại đầu Superframe trong window → `ACTIVE_REPORT`. Không tự sửa slot/kênh; thông báo nhiều lần không thay ACK/lease.

- `STAGE_ACK`: Gateway đã validate/persist; **không** chứng minh các Node nhận được lịch và **không** cho Backend cập nhật ACTIVE.
- `VERIFY_NACK`: từ chối với `reason_code`; active trước đó giữ nguyên.
- `ACTIVE_REPORT`: Gateway đã kích hoạt thực tế. Backend chỉ đánh ACTIVE khi `request_id`, `schedule_version`, identity và mốc activation khớp.

`downlink/schedule retain=false`: retained stale schedule nguy hiểm sau reboot. Sau reconnect Backend đối chiếu retained `uplink/status` (chỉ phản ánh last-known), rồi resend request còn hiệu lực nếu cần. Gateway phải reject `expires_at` đã qua/clock không đáng tin, duplicate cũ, sai gateway, slot trùng, thông số airtime lỗi. Gateway tự chọn SF activate đủ xa; Backend **không** điều khiển radio từng slot. MQTT 5.0 Message Expiry là bắt buộc khi publish schedule/command, nhưng không thay `expires_at` validation (mục 1.1).

## 4. Downlink commands và xác nhận

`command_id` idempotent; `created_at/expires_at` và Backend RBAC bắt buộc. `SET_PERIODIC_MODE` OFF vẫn giữ Alert. `SUSPEND_NODE/RESUME_NODE/REVOKE_NODE` đòi Gateway validate/persist authorization state; mất Internet không tự gia hạn quyền. Reprovision/credential rotation còn OPEN G2. `uplink/command-ack` phân biệt trạng thái vận chuyển, tiếp nhận và Node execution; MQTT PUBACK không là chứng cứ lệnh thực thi. Gateway không phát ngoài slot/airtime, retained status không chứng minh online.

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
