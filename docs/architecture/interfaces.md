# Ownership của các interface

Status: `DRAFT / PENDING CROSS-TEAM REVIEW`, remediation [#60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Bảng tổ chức lại trách nhiệm từ [contract index](../../contracts/README.md), không tạo interface hoặc schema mới. Implementation/conformance vẫn `NOT_VERIFIED` nếu chưa có báo cáo riêng theo [acceptance gates](../verification/acceptance-gates.md).

## Luồng hành vi Event/Alert và Device Onboarding

| Luồng | Producer → Consumer | Trách nhiệm và điều kiện |
|---|---|---|
| Trigger / Alert | Sensor Node → Gateway | Node đánh giá Trigger cục bộ; xếp ưu tiên Alert cao hơn periodic telemetry; dùng Priority Access và ACK/retry trong giới hạn backoff/airtime. `periodic_reporting=OFF` không chặn Alert |
| Periodic telemetry | Sensor Node → Gateway | Chỉ chạy khi cấu hình `ON` và có slot TDMA hợp lệ. `OFF` vẫn giữ Beacon, Join và downlink cần thiết |
| Unknown Node Discovery | Unprovisioned Node → Gateway → Backend | Join/identity có rate limit; Gateway đối chiếu registry và gửi detection event; phát hiện không tương đương xác thực hay quyền ứng dụng |
| Device Approval | Web → Backend | Người có quyền Accept/Reject Node ở trạng thái Pending. Backend sở hữu quyết định authorization |
| Provisioning / Activation | Backend → Gateway → Node → Gateway/Backend | Backend tạo cấu hình sau approval; Gateway lên lịch downlink phù hợp half-duplex/airtime; Node kiểm tra và ACK. Chỉ chuyển Active khi activation thực sự hợp lệ, không suy từ MQTT PUBACK |
| Multi-Gateway reception (candidate) | Một Node → nhiều Gateway → Backend | Backend cần nhận diện trùng cùng logical event; cần bổ sung cross-Gateway identity, RF coexistence và serving-Gateway policy trước khi triển khai |
| Mesh forwarding (candidate riêng) | Node → relay → Gateway | Chưa có approved routing/forwarding contract; định hướng dưới 5 hop không được dùng như tính năng sẵn có |

Các luồng mới mô tả **hành vi hệ thống**, không tự định nghĩa MQTT topic mới, API route mới hay Radio MAC packet byte layout. Short ID 2B / header khoảng 10B trong *Kiến trúc LoRa.docx* đang khác legacy candidate 1B / 8B trong [Radio MAC draft](../../contracts/radio-mac/specification.md); cần Issue thay đổi contract và review Node/Gateway/Backend/Security trước implementation. Phân biệt Multi-Gateway Discovery và Mesh; RF channel, LBT, duty và timing vẫn cần G1/G2/G3.

## Chủ sở hữu, validation và recovery

| Interface / hướng | Producer và consumer chịu trách nhiệm | Nguồn chuẩn / trạng thái | Failure và recovery owner | RTM / reviewers |
|---|---|---|---|---|
| RF Node ↔ Gateway | Node/Gateway kiểm version, length, destination, auth/replay trước dispatch; single radio owner tuần tự hóa SPI/state | [Radio MAC §§1–4](../../contracts/radio-mac/specification.md), [vectors](../../contracts/radio-mac/test-vectors/README.md); security/wire BLOCKED G2 | Radio owner xử lý IRQ/timeout; Node mất sync chuyển safe recovery; cả hai không bypass airtime | MAC-001/002/004/005/006/007, FW-002/003, SEC-001/003/004; Node/MAC + Gateway/TDMA + RF + Security/QA |
| Backend Planner → Gateway Executor → Node | Backend quản proposal/version; Gateway validate/persist/announce/switch tại boundary; Node xác thực mapping. Backend kiểm actual report trước ACTIVE | [TDMA §§2–3](../../contracts/radio-mac/tdma-schedule.md), [MQTT semantics §4](../../contracts/mqtt/semantic-rules.md); DRAFT, profile/horizon candidate | Gateway reject invalid proposal, giữ active hợp lệ; không promote shadow sau reboot. Backend reconcile late reports; Node dừng slot cũ nếu chưa có lịch mới | MAC-003/004, SYS-001/002; Backend + Gateway + Node/RF + QA |
| Gateway MQTT producer → Backend consumer | Gateway giữ event identity khi retry/buffer; Backend kiểm topic/principal/payload, schema, semantic consistency và dedup | [topics §§1–2](../../contracts/mqtt/topics.md), MQTT semantics §§1–3; MQTT 5.0 OWNER_ACCEPTED, contract PENDING | Gateway quản buffer/drop counters; Backend quản persistence, duplicate conflict/quarantine và bounded retry. PUBACK khác durable business acceptance | DATA-001/002, FW-001/004, SEC-002; Gateway + Backend/Storage + Infra/Security |
| Backend MQTT producer → Gateway consumer | Backend kiểm authorization/ID/version/expiry; Gateway kiểm lại identity/clock/expiry, schedule semantics và airtime trước execution | topics §§1/3/4, MQTT semantics §§3–5; [ADR-0002](../adr/0002-mqtt-5.md) và draft contracts | Backend/Broker quản delivery/ACL diagnostics; Gateway chỉ NACK lỗi thực sự nhận/phát hiện. Broker denial không bảo đảm Gateway NACK. Không suy NODE_ACKED từ PUBACK | MAC-003/006, SEC-002/004, DATA-002; Backend + Gateway + Node + Infra/Security |
| REST Backend ↔ React/Flutter | Backend enforce AuthN/RBAC/resource scope và request validation; client giữ idempotency key khi retry, phân biệt 202/STAGED/ACTIVE | [OpenAPI](../../contracts/api/openapi.yaml), [API semantics](../../contracts/api/contract-semantics.md); DRAFT, auth D13 provisional | Backend sở hữu error/conflict/ticket; client đọc status/reconcile. Backend alert acknowledge không phải RF ACK | INT-002, SEC-002, MAC-003; Backend/API + Web/Mobile + Security |
| WSS Backend → React/Flutter | Backend kiểm AuthN/AuthZ/Origin trước upgrade/fan-out; client dedup theo domain identity và REST resync | [WSS](../../contracts/api/websocket.md), [event schema](../../contracts/api/schemas/realtime-event.schema.json), API semantics; DRAFT, D13 blocked | Backend quản backpressure theo design được review; client đánh STALE/resync khi mất continuity. Retained status không chứng minh online | INT-002, DATA-001, SEC-002; Backend + Web/Mobile + Security/QA |
| Backend ↔ PostgreSQL | Storage quản migrations/transactions/event uniqueness theo MQTT semantics §2 và [Issue #18](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18) | [migrations](../../backend-go/migrations/); implementation NOT_VERIFIED | Backend xử lý DB unavailable/duplicate conflict, có restore evidence; client không truy cập DB trực tiếp | DATA-001, INT-001/002; Backend/Storage + QA |

IDs dẫn về [RTM](../requirements/requirements.md#rtm), IDs mới là PROPOSED. Owners là vai trò cần review, không tuyên bố đã assign/sign off.

## Trust boundaries

RF CRC, MQTT TLS và Backend authorization giải quyết các ranh giới khác nhau. Radio MAC §3 yêu cầu RF authentication/replay; MQTT semantics §§1–3 yêu cầu broker ACL theo authenticated principal cùng topic/payload check; API semantics yêu cầu server-side authorization. Không dùng lớp này để bỏ qua lớp khác. Nonce/key/wire vẫn [D01/D11](../../contracts/OPEN_DECISIONS.md); browser WSS credential transport vẫn D13, không chọn cơ chế mới ở đây.

## Versioning và compatibility

Theo contract index §Quy tắc hợp đồng, RF protocol, MQTT schema, REST API và WSS schema versions độc lập application version. Producer/consumer review mọi thay đổi field width, enum, endian, authenticated data, error semantics hoặc timing; breaking change cần ADR/version handling/vectors. Không thêm alias topic hoặc truncate schedule version để nối RF draft với Backend version. Nguồn: D06/D11 và Radio MAC §3.

Không chép schemas vào tài liệu này. Khi architecture và contract khác nhau, lập finding và chuyển contract owner xử lý; Issue #60 không cho phép sửa contracts. Draft contract là nguồn chuẩn cho thiết kế đề xuất, chưa là production approval.

## Review và evidence

Producer/consumer cùng duyệt theo [contract verification](../../contracts/verification.md). Syntax/schema/OpenAPI tests chỉ hỗ trợ phần thực sự kiểm; MQTT/TLS/DB/WSS runtime, security, C↔Go vectors và RF/HIL cần evidence riêng với Issue/commit/environment/versions/expected/actual/reviewer. Xem [audit R1](../development/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) cho gap và reviewer handoff.
