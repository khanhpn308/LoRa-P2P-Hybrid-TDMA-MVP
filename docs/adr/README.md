# Sổ quyết định kiến trúc

Register R1 theo [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Design approval, cross-team review và verification độc lập; Git merge hoặc Closed Issue không tự tạo PASS. Nguồn: [AGENTS.md](../../AGENTS.md), [acceptance gates](../verification/acceptance-gates.md).

| ADR | Quyết định / phạm vi | Approval được ghi nhận | Review còn chờ | Evidence / giới hạn |
|---|---|---|---|---|
| [0001: Hybrid TDMA](0001-hybrid-tdma.md) | Backend Planner/User approval, Gateway-local Executor; Local Alarm, Event-Only Remote Logging, Static DATA SF và Maintenance SF mục tiêu 300 s | ARCHITECTURE_DIRECTION_ACCEPTED gốc; OWNER_APPROVED_DESIGN_DIRECTION #125 ngày 2026-11-04; supersession ghi trong ADR | Owner, Gateway/TDMA, Node/MAC, RF, Backend, API/UI, Security/QA; technical sign-off pending | RF/HIL/Timing/Security/CI NOT_VERIFIED; Event ACK/HEALTH_REPLY và Beacon/HMAC compatibility cần G2, không approval numeric constants |
| [0002: MQTT 5.0](0002-mqtt-5.md) | MQTT 5.0, QoS1, session/expiry và application validation | OWNER_ACCEPTED, PR #26 merged, theo ADR | PENDING Gateway/Backend/Infra-Security; Issue #14 Closed không thay sign-off | Implementation/integration NOT_VERIFIED; [topics](../../contracts/mqtt/topics.md) vẫn contract DRAFT |
| [0003: ESP-IDF v6.1](0003-esp-idf-v6-1.md) | Exact v6.1 cho Gateway/Node CI và Harness theo [pin](../../firmware/esp-idf-version.txt) | APPROVED BY OWNER, 2026-10-22, Issue #30 | Driver/API migration, ISR và HIL review theo ADR; owner version approval không duyệt toàn bộ firmware | Cần actual-commit build logs; R1 không chạy build/HIL/RF, không chứng nhận các gates này |

ADR-0002/0003 không sửa trong R1. Requirements mới trong [RTM](../requirements/requirements.md#rtm) vẫn PROPOSED dù tham chiếu accepted direction.

Revision [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), docs child [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126), giữ lịch sử Owner approval 2026-10-30 và các invariant không mâu thuẫn. #77 optional periodic, #78/C08 contention và CT-01-ACK-01 Telemetry ACK_BITMAP semantics đã **SUPERSEDED** ở tầng kiến trúc; `P-10S-15` là **OBSOLETE candidate**, không xóa lịch sử hoặc tự sửa wire.

Node local alarm độc lập RF và Event được lưu persistent bounded FIFO. Event chỉ TX trong DATA slot đã duyệt rồi nhận Gateway durable ACK trong slot; thiếu ACK retry cùng Event ở slot hợp lệ kế tiếp của chính Node, hết budget vẫn durable pending. Gateway-origin Event ID/mapping giữ nguyên; Node persistence/counter binding, retry/overflow policy còn OPEN. Maintenance mục tiêu 300 s có authenticated SYNC_BEACON và từng Node HEALTH_REPLY ở slot riêng; Beacon một mình không chứng minh alive. DATA/ACK/JOIN/RECOVERY/maintenance phải không overlap; drift/guard/holdover/offline thresholds cần đo. Xem chi tiết và ranh giới migration contract/schema trong ADR-0001 và kiến trúc; đây chưa là implementation hoặc wire approval.

## Quy trình và open decisions

Thêm ADR theo số duy nhất với Context, Decision, Alternatives, Consequences, Status, Reviewers, Issue và evidence limitations. Cross-component change cần owner phía gửi/nhận review theo [contract index](../../contracts/README.md). Proposal không tự thành hard requirement.

[OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md) là canonical register D01–D13. [Audit R1](../audits/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ phân tích options/dependencies/evidence theo IDs sẵn có, không đóng decision. C Firmware Coding Standard v2.0.0 là task sau; hiện chỉ có [source traceability đề xuất](../audits/firmware/C_STANDARD_SOURCE_TRACEABILITY.md).
