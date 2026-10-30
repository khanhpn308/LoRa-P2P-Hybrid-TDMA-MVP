# Sổ quyết định kiến trúc

**Các quyết định Owner mới nhất C01–C08 và chính sách C09:** [G0 — Owner Decisions](../architecture/g0-owner-decisions.md). Các ADR/R1 cũ chưa được tự động sửa trạng thái phê duyệt hoặc trạng thái kiểm thử.

Register R1 theo [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Design approval, cross-team review và verification độc lập; Git merge hoặc Closed Issue không tự tạo PASS. Nguồn: [AGENTS.md](../../AGENTS.md), [acceptance gates](../verification/acceptance-gates.md).

| ADR | Quyết định / phạm vi | Approval được ghi nhận | Review còn chờ | Evidence / giới hạn |
|---|---|---|---|---|
| [0001: Hybrid TDMA](0001-hybrid-tdma.md) | Backend Planner, Gateway-local Executor, Node local timing và autonomy | ARCHITECTURE_DIRECTION_ACCEPTED, giữ ý nghĩa accepted direction gốc | Rationale/traceability R1 DRAFT; Gateway/TDMA, Node/MAC, RF, Backend, Security/QA | RF_TIMING_NOT_VERIFIED; wire/security/profile cần G1/G2/G3/G5, không approval numeric constants |
| [0002: MQTT 5.0](0002-mqtt-5.md) | MQTT 5.0, QoS1, session/expiry và application validation | OWNER_ACCEPTED, PR #26 merged, theo ADR | PENDING Gateway/Backend/Infra-Security; Issue #14 Closed không thay sign-off | Implementation/integration NOT_VERIFIED; [topics](../../contracts/mqtt/topics.md) vẫn contract DRAFT |
| [0003: ESP-IDF v6.1](0003-esp-idf-v6-1.md) | Exact v6.1 cho Gateway/Node CI và Harness theo [pin](../../firmware/esp-idf-version.txt) | APPROVED BY OWNER, 2026-10-22, Issue #30 | Driver/API migration, ISR và HIL review theo ADR; owner version approval không duyệt toàn bộ firmware | Cần actual-commit build logs; R1 không chạy build/HIL/RF, không chứng nhận các gates này |

ADR-0002/0003 không sửa trong R1. Requirements mới trong [RTM](../requirements/requirements.md#rtm) vẫn PROPOSED dù tham chiếu accepted direction.

## Quy trình và open decisions

Thêm ADR theo số duy nhất với Context, Decision, Alternatives, Consequences, Status, Reviewers, Issue và evidence limitations. Cross-component change cần owner phía gửi/nhận review theo [contract index](../../contracts/README.md). Proposal không tự thành hard requirement.

[OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md) là canonical register D01–D13. [Audit R1](../audits/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ phân tích options/dependencies/evidence theo IDs sẵn có, không đóng decision. C Firmware Coding Standard v2.0.0 là task sau; hiện chỉ có [source traceability đề xuất](../audits/firmware/C_STANDARD_SOURCE_TRACEABILITY.md).
