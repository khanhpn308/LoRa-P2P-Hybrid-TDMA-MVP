# MQTT Contract v1 — Gateway ↔ Mosquitto ↔ Backend Go
**0.1.0-draft, PROPOSED, Issue #14. Chưa triển khai, chưa nghiệm thu.**

## 1. Topics, QoS và ownership

Root `iot/v1/gw/{gateway_id}`. MQTT 3.1.1/v5 cần chốt bằng ADR. Dùng TLS với xác thực broker/Gateway, ACL theo client ID thật; chỉ profile `dev-insecure` localhost bị cô lập mới được chạy cleartext.

| Suffix | Publisher → Consumer | QoS | Retain | Schema |
|---|---|---:|---|---|
| `uplink/telemetry` | Gateway → Backend | 1 | false | [telemetry](schemas/telemetry.schema.json) |
| `uplink/alert` | Gateway → Backend | 1 | false | [alert](schemas/alert.schema.json) |
| `uplink/status` | Gateway → Backend | 1 | true | [status](schemas/status.schema.json) |
| `uplink/schedule-ack` | Gateway → Backend | 1 | false | [schedule-ack](schemas/schedule-ack.schema.json) |
| `uplink/command-ack` (bổ sung đề xuất) | Gateway → Backend | 1 | false | [command-ack](schemas/command-ack.schema.json) |
| `downlink/schedule` | Backend → Gateway | 1 | **false** | [schedule](schemas/schedule.schema.json) |
| `downlink/command` | Backend → Gateway | 1 | false | [command](schemas/command.schema.json) |

Gateway chỉ publish `uplink/#` và subscribe `downlink/#` của **chính mình**; Backend ngược lại. Web/Mobile không truy cập MQTT trực tiếp. Không tạo ngầm alias `iot/gw/{id}/control/schedule/set` hay `uplink/sched_ack` nêu trong tài liệu đính kèm: namespace canonical là của repository.

## 2. Envelope & dữ liệu

MQTT JSON UTF-8; `schema_version="1.0-draft"` độc lập với tiền tố topic `v1`. `event_id` phải duy nhất ổn định qua QoS1 retry và offline-buffer replay, có `gateway_epoch` UUID boot-session và `event_seq` dạng chuỗi thập phân (tránh lỗi JS > 2^53). Backend lưu unique `(gateway_id,event_id)`. Tuyệt đối không chỉ dùng `SEQ_NUM` 8-bit hoặc thời gian phát để deduplicate; node reset / rollover làm trùng.

`observed_at` là RFC3339 UTC hoặc null; `observed_time_source` nêu cơ sở clock, `radio_rx_monotonic_us` là chuỗi thời gian tương đối theo boot Gateway, `buffered` xác định sự kiện phát lại. Backend gán `ingested_at` bằng server clock. `data` truyền integer raw RF §6.2; unit/scale cần mapping theo phiên bản cấu hình cảm biến, không suy diễn. Nếu PRIORITY_ALERT 12B thiếu kênh/ngưỡng thì **không bịa `trigger`**; trường này optional đến khi RF v1 được duyệt.

QoS1 có thể giao trùng và sai thứ tự; không có cam kết latency, exactly-once hay bảo đảm buffer không bao giờ tràn. Gateway cung cấp `offline_dropped_telemetry`, `offline_dropped_alert` khi mất dữ liệu; `event_id` của một bản ghi không đổi khi resubmit.

## 3. Transaction lịch TDMA

Backend: `PROPOSED → SENT → STAGED → ACTIVE` hoặc `REJECTED / EXPIRED`; Gateway: validate → stage shadow NVS → announce ≥`min_announce_superframes` chu kỳ hoàn chỉnh → activate tại ranh giới superframe → report.

- `STAGE_ACK`: Gateway đã validate/persist; **không** chứng minh các Node nhận được lịch và **không** cho Backend cập nhật ACTIVE.
- `VERIFY_NACK`: từ chối với `reason_code`; active trước đó giữ nguyên.
- `ACTIVE_REPORT`: Gateway đã kích hoạt thực tế. Backend chỉ đánh ACTIVE khi `request_id`, `schedule_version`, identity và mốc activation khớp.

`downlink/schedule retain=false`: retained stale schedule nguy hiểm sau reboot. Sau reconnect Backend đối chiếu retained `uplink/status` (chỉ phản ánh last-known), rồi resend request còn hiệu lực nếu cần. Gateway phải reject `expires_at` đã qua/clock không đáng tin, duplicate cũ, sai gateway, slot trùng, thông số airtime lỗi. Gateway tự chọn SF activate đủ xa; Backend **không** điều khiển radio từng slot. MQTT v5 Message Expiry, nếu dùng, chỉ hỗ trợ bổ sung và không thay `expires_at` validation.

## 4. Downlink commands và xác nhận

`command_id` idempotent; `created_at/expires_at` bắt buộc, action theo allowlist và RBAC chỉ do Backend kiểm. `uplink/command-ack` (proposed) phân biệt `QUEUED`, `DISPATCHED`, `NODE_ACKED`, `REJECTED`, `EXPIRED`, `UNKNOWN`. Broker PUBACK **không phải** chứng cứ Node thi hành lệnh. Gateway không phát lệch slot hoặc vượt airtime policy. `uplink/status` retained không chứng minh thiết bị đang online; Backend phải có timeout/LWT và server ingest time.

## 5. Negative tests / giới hạn

- QoS1 duplicate, reconnect và offline replay: giữ ID, chỉ lưu một lần vào DB.
- Expired, retained stale, wrong gateway, non-monotonic version, overlapping slot, thiếu announcement horizon → NACK/fail closed.
- Thiếu/nhầm ACL hoặc command quá hạn → từ chối.
- JSON Schema không thay được kiểm tra liên trường: unique slot/node, thời hạn với clock, transition hợp lệ và airtime.
- [Fixture](examples/cases.json) / [Hướng dẫn kiểm thử](../verification.md): chỉ là synthetic test; HIL/consumer approval **NOT_VERIFIED**.
