# Sổ quyết định kiến trúc

Register R1 theo [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Design approval, cross-team review và verification độc lập; Git merge hoặc Closed Issue không tự tạo PASS. Nguồn: [AGENTS.md](../../AGENTS.md), [acceptance gates](../verification/acceptance-gates.md).

| ADR | Quyết định / phạm vi | Approval được ghi nhận | Review còn chờ | Evidence / giới hạn |
|---|---|---|---|---|
| [0001: Hybrid TDMA](0001-hybrid-tdma.md) | Backend Planner/User approval, Gateway-local Executor; Local Alarm, Event-Only Remote Logging, Static DATA SF và Maintenance SF mục tiêu 300 s | ARCHITECTURE_DIRECTION_ACCEPTED gốc; OWNER_APPROVED_DESIGN_DIRECTION #125 ngày 2026-11-04; **SUPERSEDED** bởi ADR-0004 (#273) | Owner, Gateway/TDMA, Node/MAC, RF, Backend, API/UI, Security/QA; technical sign-off pending | RF/HIL/Timing/Security/CI NOT_VERIFIED; Toàn bộ mô hình TDMA đã được bãi bỏ bởi ADR-0004 |
| [0002: MQTT 5.0](0002-mqtt-5.md) | MQTT 5.0, QoS1, session/expiry và application validation | OWNER_ACCEPTED, PR #26 merged, theo ADR | PENDING Gateway/Backend/Infra-Security; Issue #14 Closed không thay sign-off | Implementation/integration NOT_VERIFIED; [topics](../../contracts/mqtt/topics.md) vẫn contract DRAFT |
| [0003: ESP-IDF v6.1](0003-esp-idf-v6-1.md) | Exact v6.1 cho Gateway/Node CI và Harness theo [pin](../../firmware/esp-idf-version.txt) | APPROVED BY OWNER, 2026-10-22, Issue #30 | Driver/API migration, ISR và HIL review theo ADR; owner version approval không duyệt toàn bộ firmware | Cần actual-commit build logs; R1 không chạy build/HIL/RF, không chứng nhận các gates này |
| [0004: Pure CAD + CSMA/CA MAC](0004-pure-cad-csma-ca-mac.md) | Bãi bỏ Hybrid TDMA; chuyển đổi sang Event-driven CAD + Exponential Random Backoff (CSMA/CA) kết hợp Gateway Continuous RX 24/7 | OWNER_APPROVED_DESIGN [Issue #273](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/273) (2026-11-09) | Node/MAC, Gateway, Backend, Security | Thay thế toàn diện ADR-0001; bãi bỏ TDMA slotting, superframe, Beacon và Schedule Migration; hạ tầng MQTT schedule deprecated |

ADR-0002/0003 không sửa trong R1. Requirements mới trong [RTM](../requirements/requirements.md#rtm) vẫn PROPOSED dù tham chiếu accepted direction.

Revision [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), docs child [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126), giữ lịch sử Owner approval 2026-10-30 và các invariant không mâu thuẫn. #77 optional periodic, #78/C08 contention và CT-01-ACK-01 Telemetry ACK_BITMAP semantics đã **SUPERSEDED** ở tầng kiến trúc; `P-10S-15` là **OBSOLETE candidate**, không xóa lịch sử hoặc tự sửa wire.

Node local alarm độc lập RF và Event được lưu persistent bounded FIFO. Event chỉ TX trong DATA slot đã duyệt rồi nhận Gateway durable ACK trong slot; thiếu ACK retry cùng Event ở slot hợp lệ kế tiếp của chính Node, hết budget vẫn durable pending. Gateway-origin Event ID/mapping giữ nguyên; Node persistence/counter binding, retry/overflow policy còn OPEN. Maintenance mục tiêu 300 s có authenticated SYNC_BEACON và từng Node HEALTH_REPLY ở slot riêng; Beacon một mình không chứng minh alive. Join CAD bất đồng bộ có thể collision với DATA/ACK/Maintenance; Gateway SX1276 half-duplex tuần tự hóa radio của mình. DATA/READY Guard 50ms mỗi bên là Owner MVP config, drift/turnaround/HIL vẫn NOT_VERIFIED. Xem chi tiết và ranh giới migration contract/schema trong ADR-0001 và kiến trúc; đây chưa là implementation hoặc wire approval.

## Quy trình và open decisions

Thêm ADR theo số duy nhất với Context, Decision, Alternatives, Consequences, Status, Reviewers, Issue và evidence limitations. Cross-component change cần owner phía gửi/nhận review theo [contract index](../../contracts/README.md). Proposal không tự thành hard requirement.

[OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md) là canonical register D01–D13. [Audit R1](../audits/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ phân tích options/dependencies/evidence theo IDs sẵn có, không đóng decision. [C Firmware Coding Standard v2.0.0](../development/firmware/C_CODING_STANDARD_V2.md) đã tồn tại (metadata DRAFT), nhưng selected Rule IDs áp dụng mandatory theo AGENTS.md; [source traceability](../audits/firmware/C_STANDARD_SOURCE_TRACEABILITY.md) lưu lịch sử nguồn.
