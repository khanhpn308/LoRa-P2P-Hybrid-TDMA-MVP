# Audit baseline kiến trúc và requirements R1

## Metadata và preflight

TASK_ID: ARCH-DOC-BASELINE-R1

Status hồ sơ: `DRAFT / AWAITING HUMAN TECHNICAL REVIEW`. Đây là audit tài liệu, không là independent model audit hoặc technical acceptance của firmware/RF.

- Repository: [https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP).
- Base branch: `main`, exact SHA `9cb0885ad1de5112e9ae358e15e04e19b6fb38ae`.
- Work branch: `docs/60-architecture-rtm`; HEAD trước sửa bằng base; working tree ban đầu clean.
- Issue: [#60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60), OPEN, author OWNER; snapshot updated_at `2026-10-25T05:50:17Z`.
- Issue body SHA-256 UTF-8: `d387d26a99369e1d29eebbf7e32d48c5a7b01a4b2d71fe92a1eb1f4c3ffe5b6b`. AC và allowlist đã đọc, đúng bảy file trong bảng remediation dưới đây.
- Đọc current main qua GitHub GET branches/main, đối chiếu local HEAD/origin/main; không cập nhật main hoặc ghi đè local changes. Không chạy git fetch vì current commit đã có local.
- Issue body còn câu template "PROPOSED, chưa phải Issue đã được owner cho phép". Chỉ dẫn tiếp tục trực tiếp của user sau khi tạo Issue cho phép thực hiện đúng scope/AC này; đây là execution authorization, không đổi approval của design/requirements. Không sửa Issue hoặc coi template là approval kỹ thuật.
- Scope lần này chỉ docs, không dùng Harness/model runtime, không cấp quyền RF/flash hoặc sửa contracts. Preflight cũ chỉ là tham khảo; mọi finding dưới đây được kiểm lại tại base SHA và live snapshots ngày 2026-10-25.

### Review remediation R2

- Preflight R2 ngày 2026-10-25: Issue #60 OPEN, AC/allowlist không đổi; branch `docs/60-architecture-rtm`, HEAD trước sửa `bc992ad9fe46c4cf0065d8fe64aa928f42a6a492`, working tree clean; Draft PR #61 OPEN/Draft, base main vẫn `9cb0885ad1de5112e9ae358e15e04e19b6fb38ae`.
- Chỉ sửa hai deliverables đã được Issue cho phép. R2 sửa evidence/provenance và khả năng tái chạy validation; không review lại hoặc thay architecture/contracts/23 requirement statuses.
- F-11 được hiệu chỉnh bằng upstream source mới xác minh. Checker R2 đầy đủ, prerequisites, exact commands và output được lưu trong mô tả [Draft PR #61](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/61); không thêm script/path vào repository.

## Source inventory và authority

Hash trong bảng là SHA-256 của bytes **tại base SHA**, kể cả file được sửa trong R1. Links là đường dẫn hiện tại để tra cứu; findings dùng immutable base links khi cần line numbers. File availability không là approval hoặc test verdict.

| Source path | Authority / phạm vi review | Base content SHA-256 |
|---|---|---|
| [AGENTS.md](../../../AGENTS.md) | Repository authority; scaffold, experimental reference và evidence dimensions | `7058ba01fce43361ed17632d591eb9c0f17348e2e9713cb7a7707ea4b0d17cbb` |
| [.github/copilot-instructions.md](../../../.github/copilot-instructions.md) | Repository scope/Issue/governance constraints | `8182eabe61a1b88e1c84aa67e4be53f7527eed4b6bfa40ae29ea0b710bcc40ac` |
| [.github/instructions/embedded.instructions.md](../../../.github/instructions/embedded.instructions.md) | Firmware ownership/ISR/bounded-memory constraints | `d3276bdbcf13f058ab32724f961f90f821a5403482a66979d06b8f8833f17a8e` |
| [docs/architecture/system-overview.md](../../architecture/system-overview.md) | System design DRAFT; toàn file | `a7ab2a8d7fff8a86ea71902bbc02004cde704ecfb22373983742e0172e1a2ef3` |
| [docs/architecture/interfaces.md](../../architecture/interfaces.md) | Interface design DRAFT; toàn file | `1b6fd6bd504342b3eee91182635cf80a033b5fe2cc4d6e9cc0bc491730936e94` |
| [docs/architecture/deployment.md](../../architecture/deployment.md) | Deployment contexts; scaffold warning | `d65c83eb486e5c11c401298bd239c9c232324ecbfc9b189b3fed26298815fd80` |
| [docs/requirements/requirements.md](../../requirements/requirements.md) | Initial draft RTM; tám rows NOT_VERIFIED | `fe40bff63dbec677e08adc7caa1a2366b2f568a7c341ba72e942e42ec3afa899` |
| [docs/adr/0001-hybrid-tdma.md](../../adr/0001-hybrid-tdma.md) | Accepted direction; numeric/evidence approval không có | `03dde87109f3e0d3e716c41c9463c99eddcd1d852db76db149aef5a6baa992b2` |
| [docs/adr/0002-mqtt-5.md](../../adr/0002-mqtt-5.md) | MQTT 5.0 OWNER_ACCEPTED, cross-team PENDING | `14bbfd6f2bc5f5d30f14582103e9d0bd43a3b3f3d2194dad1fc973869c229c04` |
| [docs/adr/0003-esp-idf-v6-1.md](../../adr/0003-esp-idf-v6-1.md) | Owner-approved exact v6.1, evidence riêng | `013a20c882fbef494ad9209cbdbe00879131ab64b90fc074db9e92d0b2970bb5` |
| [docs/adr/README.md](../../adr/README.md) | ADR index trước R1 chỉ list approved firmware baseline | `e1d1c77d5658027fa32256ac1622e888f2dc4bc1bd02d2a11a024cb758acd747` |
| [firmware/esp-idf-version.txt](../../../firmware/esp-idf-version.txt) | Exact pin v6.1; không là build log | `4a048fa9797ece947a2011604f18df0eeaf19c0251d72539b329275267806deb` |
| [contracts/README.md](../../../contracts/README.md) | Contract ownership/versioning; overall PROPOSED | `abfb86fc5f79d75c5b88557dd83fd53add5605918da00ec523b4c0e6b1e1fda1` |
| [contracts/OPEN_DECISIONS.md](../../../contracts/OPEN_DECISIONS.md) | Canonical D01–D13 và gate dependencies | `d2389bab39b2b335913728845e47f88460fde3c1c655aeb0e894a1d61d1b886c` |
| [contracts/radio-mac/specification.md](../../../contracts/radio-mac/specification.md) | Security/wire DRAFT, BLOCKED G2; toàn file | `1c8f05d9f398e61a96c0f7cbaf6d4d9981bb6702475dc2e844827f5582e3ce10` |
| [contracts/radio-mac/tdma-schedule.md](../../../contracts/radio-mac/tdma-schedule.md) | Candidate P-10S-15; lifecycle/safety; toàn file | `df4011e35c24346617329ed8282ad40b4e1be9b4407293075075658d8b66502b` |
| [contracts/radio-mac/test-vectors/README.md](../../../contracts/radio-mac/test-vectors/README.md) | Golden plan, chưa có approved bytes | `2022cde71a29a049687592207b42eafbdd9da8961c4d367912fbaa7b0773f305` |
| [contracts/mqtt/topics.md](../../../contracts/mqtt/topics.md) | MQTT version accepted; contract PENDING; toàn file | `204189acfa35413ccb5ba9721c45589dc0daac33ddc0676461472db3279ea4b0` |
| [contracts/mqtt/semantic-rules.md](../../../contracts/mqtt/semantic-rules.md) | Proposed invariants/state/errors; toàn file | `60d1ea5d66a62b3b422152b4049f64961412a7e0346e0e92d71a65d814811ba2` |
| [contracts/api/openapi.yaml](../../../contracts/api/openapi.yaml) | OpenAPI draft, 14 operations; chưa business implementation | `1cc5bc4fe586a01bfbe478732fa0b27f4dc10ba3c772b6d6cda7a9b214b0cd93` |
| [contracts/api/contract-semantics.md](../../../contracts/api/contract-semantics.md) | REST/WSS proposed validation/recovery; toàn file | `316459726b7f9e7a3ca3bed7151a95f63afcc1afc365503dc0404fd75cbeef70` |
| [contracts/verification.md](../../../contracts/verification.md) | Static checks và integration/HIL plan | `d48558d91b46bc5e95db3d6d69d74ea1c4b8fd3adcacff4231a2f58f3334f5c3` |
| [docs/verification/acceptance-gates.md](../../verification/acceptance-gates.md) | G0–G6 evidence requirements, không là verdict | `e14d7a1bd2f18f399d62e582050390897af58d16fc9f756a00c16df6d776aba3` |
| [docs/development/coding-standards.md](../coding-standards.md) | Engineering constraints; Go draft tách firmware standard | `1816187f7340d7c411c7f8a7c131babc44100d9c1a6b9ba81cc404a44cf9e559` |
| [docs/development/agent-harness-firmware.md](../agent-harness-firmware.md) | Historical Harness P0; AGENTS integration guard có thẩm quyền hiện hành | `6d05d98fb3047ac9af1907f38d3dd6b4ddd0e2227c202fdd0999b14357a90c0c` |
| [.github/workflows/ci-contracts.yml](../../../.github/workflows/ci-contracts.yml) | Actual contract CI behavior: syntax only | `13606a40d684e432b5e71b616134581207c63d150a8c88e922e44f64b874e7e3` |
| [.github/workflows/ci-foundation.yml](../../../.github/workflows/ci-foundation.yml) | Actual structural check entry point | `d43bf6b826672bdb5f4ecacc1bd0aa9e6f92e1c7b8b11a2ce017dac7153bcf2e` |
| [scripts/verify_structure.py](../../../scripts/verify_structure.py) | Actual static structural check, không HIL proof | `a6144afbff08ffb708a53446f1b0e8321b69d26b459c90617bf6b01da958c543` |
| [contracts/tests/check_contracts.py](../../../contracts/tests/check_contracts.py) | Schema/examples/OpenAPI và candidate-geometry tooling | `a63c61de5c2d1a3ecaf63ad1460eebdb8ea6f208bbef5029de1192e13cf3c869` |
| [tests/contract/test_api_contract.py](../../../tests/contract/test_api_contract.py) | REST/WSS contract tests, không deployed behavior | `3f90163cef68b047a37e1b8e054011f94b148f0412a9be34c8b40b0510594b87` |
| [contracts/api/websocket.md](../../../contracts/api/websocket.md) | WSS draft; đã đọc toàn file, năm event types và D13 blocked | `6c28dad30d835b9f1edd77908f307a232227b2e6b9141ca19af66a8e00a7c313` |

Nguồn bổ sung được contracts dẫn chiếu: [WSS](../../../contracts/api/websocket.md), [event schema](../../../contracts/api/schemas/realtime-event.schema.json), [MQTT schemas](../../../contracts/mqtt/schemas/). R1 dùng liên kết của contracts, không duplicate message schemas hoặc review runtime từ schema existence.

Planning artifact đọc local: `/home/khanh/projects/iot/docs/backend_worker_gate1_pack/00_SHARED_INPUTS/esp32_sx1762.md`, SHA-256 `fe42d7736aa8a3b7772ac680923e6cec40e1f784d612eaa39c570895e0946f67`. Đã đọc các phần liên quan §§1/3–6/8/10–12, không làm full citation verification cho các marker `[cite: ...]`; không có bibliography/provenance chain được xác minh trong audit. Phân loại `SOURCE_AVAILABLE_LOCAL / DESIGN_INTENT_ONLY`, không phải approved design hoặc measurement. Không đưa bản planning vào Git.

S1 C standard v1.0.0: [immutable upstream reference](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5/docs/C_CODING_STANDARDS.md) tại commit `2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5`, 41197 bytes, SHA-256 `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de`; exact byte match với S1 local dùng trong R1. Phân loại R2 `SOURCE_PINNED / LOCAL_BYTE_MATCH`; xem [traceability](C_STANDARD_SOURCE_TRACEABILITY.md) và F-11 về correction của kết luận cũ. Approval source-local không truyền sang monorepo. Official Espressif/Semtech docs vẫn là authority cho API/register review sau; R2 không chứng nhận các semantic/hardware claims của source demo.

### Live Issue inventory

Nguồn cho mỗi row gồm GET issue và GET comments ngày 2026-10-25. State/checkbox chỉ là metadata, không độc lập chứng minh technical acceptance. Bảng phản ánh snapshot lúc audit, không hứa trạng thái sẽ không đổi.

| Issue | State tại snapshot | Nội dung/dependency kiểm tra | Comments |
|---|---|---|---|
| [#9](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/9) | CLOSED | Board bring-up; hai công việc tick, AC còn unchecked; không có RF approval tự suy | 0 |
| [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) | OPEN | Driver/radio owner/components và HIL; AC chưa tick | 0 |
| [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) | OPEN | Timing measurements; không gộp TX command→IRQ với ToA RF | 0 |
| [#12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) | OPEN | Security/wire/vectors approval; production codec gate | 0 |
| [#14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) | CLOSED | MQTT schema/lifecycle/producer-consumer review; AC chưa tick | 0 |
| [#15](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15) | OPEN | REST/WSS contract, auth/reconnect, không runtime approval | 0 |
| [#18](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18) | OPEN | Idempotent PostgreSQL/MQTT storage, migrations và integration | 0 |

## Architecture decomposition review

| Boundary | Kết luận có nguồn | Approval / verification |
|---|---|---|
| Planner / local Executor | ADR-0001 và TDMA §2 nhất quán về future schedule vs local activation; architecture R1 làm rõ control/data plane | Direction accepted; details R1 pending, RF/timing NOT_VERIFIED |
| Driver / MAC / TDMA / airtime | Embedded instructions yêu cầu single owner/ISR bounds; AGENTS và component scaffold không chứng minh driver hiện thực | Repository constraints có hiệu lực, implementation/HIL chưa chứng minh |
| Node sync/recovery | TDMA §3 yêu cầu authenticated mapping, dừng unsafe periodic TX; numeric holdover là candidate | D04/D05 và timing/security dependencies chưa đóng |
| MQTT / Storage / REST-WSS | ADR-0002 cùng contracts giữ MQTT 5.0; semantic checks ngoài JSON Schema; API không cho client truy cập MQTT/DB trực tiếp | Version accepted; producer/consumer/auth/runtime vẫn pending |

## Requirements coverage analysis

Trước R1 có tám IDs; sau R1 có 23 IDs: giữ tám IDs/status và thêm 15 PROPOSED. Verification cả 23 vẫn NOT_VERIFIED. Hai bảng RTM join bằng ID để giữ đủ source/design/owner/contract/method/AC/evidence/status mà không gộp design approval với test verdict. Mở rộng statement/AC của IDs cũ là diễn giải DRAFT có nguồn, không ghi nhận owner đã duyệt bổ sung.

| Miền | RTM sau R1 | Source / remaining action |
|---|---|---|
| Memory/concurrency/SPI/ISR/timer/recovery | FW-001..004 | Embedded instructions/coding standards; load/API-context/IRQ-HIL evidence |
| Activation, sync/holdover, half-duplex, airtime, priority | MAC-001..007, RF-001, ALERT-001 | Radio MAC/TDMA và D01–D05/D11; security/profile/timing approval |
| Offline và restart | SYS-001/002 | TDMA §3, MQTT semantics §4; NVS/reset/reconnect tests |
| Authentication, replay, nonce, parser | SEC-001..004 | Radio MAC §3, D01/D11/D13; threat model/ADR/vectors/security tests |
| Event identity, MQTT lifecycle | DATA-001/002 | Topics/semantics, Issue #18; real broker/DB concurrency/replay |
| Evidence và consumer integration | INT-001/002 | Contract verification/API semantics; exact-build/gates và REST/WSS integration |

Các threshold chưa có approval đều TBD kèm hành động đo/decision; không lấy slot/guard/latency/power demo làm PASS threshold. Expected evidence locations trong RTM không được trình bày như existing evidence.

## ADR và contract consistency review

ADR-0001 giữ accepted direction, phần rationale/traceability mới DRAFT. ADR-0002 giữ nguyên owner choice và pending review. ADR-0003 giữ exact v6.1; không suy build evidence từ version pin. ADR index R1 trình bày ba trục riêng.

System diagram trước R1 có MQTT version drift, đã sửa theo ADR-0002. MQTT schedule semantics, Radio MAC safety và API async semantics được link thay vì sao chép schema. Contract CI vẫn syntax-only, khác manual schema/OpenAPI tooling. Không đổi bất kỳ contract hoặc ADR-0002/0003.

Các contract semantics cần producer/consumer review thêm về delayed/reordered reports và restart: MQTT semantics §4 chỉ liệt kê STAGED→ACTIVE, đồng thời đòi reconcile late ACTIVE_REPORT sau EXPIRED. R1 giữ link và không tự mở rộng state machine hoặc chốt xử lý omitted transition. Backend/MQTT owners cần test và quyết trong Issue contract có scope phù hợp; đây là review question, không là implementation failure đã được quan sát.

## Conflict và gap register

Severity là đánh giá của auditor về tác động nếu gap bị bỏ qua; không phải owner disposition. Sources/lines của file thay đổi đều trỏ immutable base SHA, tránh line drift sau remediation. Mỗi finding ghi classification và approval riêng.

### F-01

- Severity: MEDIUM.
- Source: [docs/requirements/requirements.md L5-L14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/requirements/requirements.md#L5-L14); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Bảng có đúng RF-001, MAC-001, MAC-002, SYS-001, ALERT-001, DATA-001, SEC-001, SEC-002; cả tám NOT_VERIFIED; chưa có source/design status/AC/evidence columns.
- Conflicting source: Embedded instructions yêu cầu ownership/bounds/ISR nhưng RTM chưa map chi tiết.
- Classification: Confirmed Fact về số rows/cột; Inference về coverage gap.
- Approval status: Initial draft; approval chưa ghi nhận, không đồng nghĩa rejected.
- Affected subsystem: Requirements / firmware-TDMA.
- Recommendation: Giữ tám IDs, bổ sung trace và IDs mới PROPOSED.
- Required reviewer: Gateway/TDMA + Node/MAC + RF + Backend + Security/QA.
- Remaining verification: Review 15 proposed IDs và thực thi verification từng requirement; R1 chỉ cải thiện hồ sơ.

### F-02

- Severity: HIGH.
- Source: [contracts/radio-mac/specification.md L3-L65](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/contracts/radio-mac/specification.md#L3-L65); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Header ghi SECURITY / WIRE LAYOUT NOT FROZEN; freeze checklist chưa tick. Vector README ghi chưa có khung hex hợp lệ đã duyệt.
- Conflicting source: Không có source approved đối nghịch; legacy envelope là candidate ngay trong spec.
- Classification: Confirmed Fact về trạng thái tài liệu, không kết luận kết quả protocol test.
- Approval status: DRAFT / BLOCKED G2; verification NOT_VERIFIED.
- Affected subsystem: Radio MAC / Security.
- Recommendation: Giữ production codec gate, map SEC-001/003/004 và INT-001.
- Required reviewer: Node/MAC + Gateway + Security + Backend + QA.
- Remaining verification: ADR crypto/nonce/keys/wire và vectors C↔Go với negative/reset/wrap trước G2.

### F-03

- Severity: HIGH.
- Source: [contracts/OPEN_DECISIONS.md L9](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/contracts/OPEN_DECISIONS.md#L9); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: D03 ghi BLOCKED G1 và không khẳng định hợp quy tại Việt Nam; policy phải được RF owner phê duyệt sau phân loại thiết bị/pháp lý.
- Conflicting source: Planning §§1/11.2 dùng frequency/duty như quy định; planning không có thẩm quyền vượt D03.
- Classification: Confirmed Fact về blocker; không cung cấp tư vấn pháp lý hoặc kết luận RF compliance.
- Approval status: RF profile chưa approved theo D03; RF evidence NOT_VERIFIED trong audit.
- Affected subsystem: RF / Hardware / airtime.
- Recommendation: Không nhập số frequency/power/duty demo vào requirements; giữ RF-001/MAC-006 và G1 handoff.
- Required reviewer: RF/Hardware + Regulatory + Gateway/Node.
- Remaining verification: Board/front-end/antenna classification, applicable limits, test setup và reproducible measurements.

### F-04

- Severity: HIGH.
- Source: [contracts/OPEN_DECISIONS.md L8-L11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/contracts/OPEN_DECISIONS.md#L8-L11); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: D02 profile CANDIDATE; D04 BLOCKED G1/G3, yêu cầu đo IRQ latency/ToA/clock thay vì bảo đảm jitter. TDMA §4 ghi các HIL cases NOT_VERIFIED.
- Conflicting source: Planning §5.2 mô tả DIO0 đồng thời và holdover sai số nhỏ như guarantee; không được kế thừa.
- Classification: Confirmed Fact về tài liệu chưa verified; không suy việc chưa đo ở mọi nơi ngoài nguồn đã kiểm.
- Approval status: CANDIDATE / RF_TIMING_NOT_VERIFIED.
- Affected subsystem: TDMA / ISR / sync.
- Recommendation: Tách invariants khỏi numeric candidates; FW-003, MAC-001/004/005, ALERT-001 có measurement action.
- Required reviewer: RF + Gateway/TDMA + Node + QA.
- Remaining verification: ToA RF khác command-to-IRQ; IRQ-to-task, drift/temperature/load, guard margin, holdover và recovery approval.

### F-05

- Severity: MEDIUM.
- Source: [docs/architecture/system-overview.md L12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/architecture/system-overview.md#L12); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Sơ đồ ghi MQTT v3.1.1 or v5 - decision TBD; TLS.
- Conflicting source: ADR-0002 lines 3/10 chọn MQTT 5.0 OWNER_ACCEPTED; MQTT topics line 2 cùng version decision.
- Classification: Confirmed Fact, documentation drift.
- Approval status: MQTT 5.0 OWNER_ACCEPTED; contract cross-team PENDING; implementation NOT_VERIFIED.
- Affected subsystem: Architecture / Gateway / Backend-MQTT.
- Recommendation: Sửa label MQTT theo ADR-0002, giữ trạng thái review/evidence riêng.
- Required reviewer: Gateway + Backend/MQTT + Infra-Security.
- Remaining verification: Human review consistency và actual MQTT 5 integration; sửa label không chứng minh client support.

### F-06

- Severity: MEDIUM.
- Source: [docs/adr/0001-hybrid-tdma.md L3-L8](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/adr/0001-hybrid-tdma.md#L3-L8); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: ADR gốc chỉ sáu bullet status/context/decision/consequences/alternatives/evidence gates; không map requirement IDs hoặc ghi detailed assumptions/trade-offs.
- Conflicting source: Không có decision mới xung đột cần chọn; vấn đề là thiếu rationale/trace.
- Classification: Confirmed Fact về nội dung; Inference về mức đủ cho reviewer.
- Approval status: Accepted architectural direction, radio performance NOT_VERIFIED.
- Affected subsystem: Architecture governance / TDMA.
- Recommendation: Giữ direction, thêm rationale và failure/dependency scope dưới DRAFT review.
- Required reviewer: Gateway/TDMA + Node/MAC + Backend + RF + Security/QA.
- Remaining verification: Sign-off phần diễn giải R1; G1/G2/G3 timing/security vẫn riêng.

### F-07

- Severity: MEDIUM.
- Source: [docs/architecture/interfaces.md L3-L13](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/architecture/interfaces.md#L3-L13); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Bảng gốc có Interface, Producer -> consumer, Source of truth, Reviewers; có cảnh báo dedup/retained, nhưng không có RTM IDs hoặc failure/recovery ownership cho từng boundary.
- Conflicting source: API/WSS semantics và MQTT semantics hiện có trách nhiệm chi tiết hơn; OpenAPI chỉ REST, WSS có nguồn riêng.
- Classification: Confirmed Fact về links/columns; Inference về review risk.
- Approval status: Interface doc DRAFT; contracts vẫn theo approval từng source.
- Affected subsystem: RF / MQTT / API-WSS / Storage.
- Recommendation: Liên kết ownership/validation/recovery/versioning và RTM; không duplicate schema.
- Required reviewer: Gateway + Node + Backend/MQTT + Web/Mobile + Security/QA.
- Remaining verification: Producer/consumer review, runtime negative/reconnect/security tests.

### F-08

- Severity: HIGH.
- Source: [.github/workflows/ci-contracts.yml L12-L17](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/.github/workflows/ci-contracts.yml#L12-L17); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Workflow chạy JSON syntax bằng python3 -m json.tool và in notice Syntax-only; golden vectors/cross-language tests NOT VERIFIED.
- Conflicting source: Có contracts/tests/check_contracts.py và tests/contract/test_api_contract.py cho schema/OpenAPI checks, nhưng workflow trên không gọi chúng; không được nói repo hoàn toàn không có behavioral tooling.
- Classification: Confirmed Fact về workflow/tooling; Inference về nguy cơ overclaim.
- Approval status: Static tooling tồn tại không là contract APPROVED hoặc G1–G6 PASS.
- Affected subsystem: QA / contract integration.
- Recommendation: INT-001 phân tách syntax/schema/build/simulation/conformance/HIL/RF; ghi lệnh và giới hạn thật.
- Required reviewer: QA + Backend + Gateway + Node + RF + Security.
- Remaining verification: Chạy tooling khả dụng; missing dependencies ghi NOT_RUN, golden/runtime/HIL vẫn cần evidence.

### F-09

- Severity: HIGH.
- Source: [AGENTS.md L9-L15](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/AGENTS.md#L9-L15); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Monorepo ghi driver thử nghiệm chỉ reference và không tự đổi pinmap/RF/crypto/frame. S1 §§09.1/10/11/14 có demo RF, Little-Endian/frame và sáu GPIO cùng source-local approval.
- Conflicting source: S1 được source tự ghi APPROVED, nhưng Radio MAC/D01/D03/D11 của monorepo vẫn chưa freeze; không có authority chuyển approval giữa repos.
- Classification: Confirmed Fact về nguồn; Inference về nguy cơ import. Không kết luận đã có import trái phép.
- Approval status: S1 approval chỉ source-local; mapping R1 PROPOSED, hardware/wire NOT_VERIFIED.
- Affected subsystem: Firmware standard / hardware / wire protocol.
- Recommendation: Classify đủ 12 categories, tách engineering rules khỏi board/contract/RF specifics.
- Required reviewer: Embedded + RF/Hardware + Node/MAC + Security + Backend/QA.
- Remaining verification: S1 provenance đã pin và byte-match ở R2; exact API/datasheet review, monorepo adoption và board evidence vẫn cần trước v2 approval.

### F-10

- Severity: MEDIUM.
- Source: [contracts/mqtt/topics.md L1-L2](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/contracts/mqtt/topics.md#L1-L2); các section/source bổ sung ghi trong evidence.
- Exact observed evidence: Live Issue #9 và #14 Closed; #9 còn AC unchecked, #14 còn producer/consumer approval AC unchecked. GET comments của hai Issues trả mảng rỗng. Topics vẫn PENDING CROSS-TEAM REVIEW.
- Conflicting source: Closed state khác nghĩa approval/review trong ADR-0002 và topics. Không kết luận không có evidence ở nơi chưa kiểm.
- Classification: Confirmed Fact về Issue snapshot/file status; Inference rằng close state không đủ chứng minh acceptance.
- Approval status: Issue state không là design approval; pending review/evidence giữ nguyên.
- Affected subsystem: Governance / RF / MQTT.
- Recommendation: Ghi Issue state riêng, yêu cầu owner/reviewer dẫn actual evidence/disposition.
- Required reviewer: Owner + RF + Gateway/Backend + QA.
- Remaining verification: Đối chiếu evidence/PR review records ngoài snapshot nếu owner cung cấp; không reopen/close Issue trong R1.

### F-11

- Severity: MEDIUM đối với provenance gap được báo trong R1; disposition R2 `CORRECTED / SOURCE_PINNED`, không còn giữ gap thiếu upstream reference như finding hiện hành.
- Source: [upstream S1 metadata/§14](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5/docs/C_CODING_STANDARDS.md), tree commit `2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5`, Git blob `7a5e011bc8133762c8da8433e60c0e801d41b801`; so sánh với local S1 của R1.
- Exact observed evidence: upstream và local đều 41197 bytes, SHA-256 `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de`; so exact bytes trả true. Upstream main tại R2 trỏ commit đã pin. Không thay local/source content.
- Conflicting source: kết luận R1 dựa vào checkout/commit cũ `e46ff22dfe441911310bc9a859c202bf5c4cface`, nơi file không track và GET trả 404; quan sát đó không chứng minh upstream main thiếu file. Immutable upstream source R2 thay thế kết luận thiếu provenance, không phủ nhận lịch sử checkout cũ.
- Classification: Confirmed Fact về pinned revision và byte identity; rút lại suy luận tổng quát upstream unavailable/unversioned trong R1.
- Approval status: `SOURCE_PINNED / LOCAL_BYTE_MATCH` chỉ cho provenance; source-local approval không trở thành monorepo/v2 approval.
- Affected subsystem: C standard source traceability.
- Recommendation: dùng immutable upstream link/hash trong traceability và checker tái lập; giữ nguyên 123 source IDs/disposition.
- Required reviewer: Owner + Embedded/QA xác nhận correction và việc áp dụng rule ở task sau.
- Remaining verification: human disposition của R2 và monorepo standard review; F-11 không còn yêu cầu cung cấp archive S1. API/datasheet/hardware/security evidence vẫn độc lập.

### F-12

- Severity: MEDIUM.
- Source: [contracts/verification.md, §2](../../../contracts/verification.md), [contracts/api/websocket.md, §2](../../../contracts/api/websocket.md).
- Exact observed evidence: verification plan còn ghi "all four events"; WSS §2 hiện liệt kê năm event types, gồm COMMAND_STATE_CHANGED được đánh PROPOSED EXTENSION.
- Conflicting source: verification plan chưa cập nhật cardinality theo WSS draft và realtime-event.schema.json hiện tại; không được bỏ event mới khỏi consumer review vì plan cũ.
- Classification: Confirmed Fact về source drift, Inference về thiếu coverage nếu chỉ dựa checklist bốn events; không khẳng định tests thực sự đã bỏ case.
- Approval status: WSS DRAFT/PROPOSED; producer/consumer review PENDING; không approval event extension trong R1.
- Affected subsystem: REST/WSS consumer compatibility và QA plan.
- Recommendation: giữ INT-002 và liên kết canonical WSS/schema trong interfaces; chuyển cập nhật verification plan cho Issue có scope contracts, không sửa ngoài allowlist R1.
- Required reviewer: Backend/API + Web/Mobile + Security/QA.
- Remaining verification: owner disposition cho event extension, unknown-event compatibility và actual five-type coverage trong contract/integration tests.

## Open-decision handoff theo canonical IDs

Bảng chỉ là phân tích options/constraints/risks cho [OPEN_DECISIONS.md](../../../contracts/OPEN_DECISIONS.md), không phải independent decision register. Status lấy từ source; options/trade-offs thêm là `PROPOSED ANALYSIS`, không chọn một option mới. Source/owner phải review trước khi amend canonical contract trong Issue khác.

| Canonical ID / status | Options / trade-off đề xuất để review | Constraints và risk | Impacted components | Dependencies | Owner cần quyết | Required evidence |
|---|---|---|---|---|---|---|
| D01 BLOCKED G2 | AEAD hoặc authenticated MAC/tag theo source; payload/airtime vs security coverage | Không CRC-only, nonce/key lifecycle và authenticated fields chưa freeze | Node, Gateway, codec | Threat model, D03/D11 | Node/GW/Security + Backend | ADR crypto/wire và negative/golden vectors |
| D02 CANDIDATE G1/G2 | Giữ P-10S-15 làm experiment hoặc đề xuất profile khác sau đo | Half-duplex/airtime/guard có thể làm candidate không khả thi; không freeze numeric | Planner, GW/Node timing | D01/D03/D04 | RF/GW/Node | ToA, turnaround, drift và load/HIL traces |
| D03 BLOCKED G1 | Approved test/deployment profile theo device classification; nếu chưa approved thì không TX | Legal/device/antenna/PA constraints; không chọn frequency/power/duty từ demo | RF, airtime policy | Board/front-end identification | RF/Regulatory + Hardware | Applicable-rule assessment, calibrated setup/profile/measurements |
| D04 BLOCKED G1/G3 | Hardware capture nếu board/API hỗ trợ hoặc software timestamp có uncertainty budget | Resolution khác accuracy; ISR/SPI/jitter/drift chưa chứng minh | Driver, sync, TDMA | Board/datasheet/API, D02 | RF/Embedded | Command→IRQ, IRQ→task, clock uncertainty và margin review |
| D05 CANDIDATE / NEEDS HIL | Complete announcement horizon theo source; Node confirmation là lựa chọn cần security/airtime review | Không K+3 mù từ giữa SF; missed update không cho TX slot cũ; holdover threshold TBD | GW/Node, Planner reports | D01/D02/D04/D11 | Gateway/Node | Late arrival, missed Beacon/mapping, restart và switch HIL |
| D06 PROPOSED | Canonical repo namespace vs legacy alias; source không cho implicit alias | Compatibility/ambiguous routing; R1 không thêm topic | Gateway/Go | MQTT contract review | Gateway/Go | Producer/consumer routing/version tests, approval |
| D07 PROPOSED | Source chọn Retain=false + reconcile; chưa có quyền quay lại Retain=true | Stale replay/reboot, active persistence khác MQTT retained snapshot | Backend/GW/Infra | ADR-0002, D05/D11 | Backend/GW/Infra | Retained stale/expiry/reconnect and reset tests |
| D08 OWNER_ACCEPTED / review pending | Giữ MQTT 5.0, review client/session/expiry conformance; không đề xuất 3.1.1 fallback | Version approval không chứng minh broker/client implementation | Gateway/Backend/Broker | ADR-0002, security/ACL config | Gateway/Backend/Infra-Security | MQTT 5 actual transport, SUBACK/expiry/session/TLS tests |
| D09 PROPOSED | Raw integer + versioned scale/unit/config mapping; không đoán sensor units | Conversion overflow/precision hoặc hiểu sai telemetry | Node/GW/Backend/DB | RF payload approval, config version | Node/GW/Backend | Roundtrip raw/scale/version examples và storage tests |
| D10 BLOCKED integration | Trigger optional tới khi RF có authenticated source; mở rộng RF payload cần scope riêng | Bịa channel/threshold hoặc phá compatibility | Node/Backend alerts/API | D01/D09, RF schema | Node/Backend | Source-to-MQTT/API mapping, negative missing-trigger tests |
| D11 BLOCKED G2 | Wider epoch/version hoặc reviewed mapping theo source | Không modulo/truncate; reboot/wrap/replay | RF MAC, GW/Node, Backend | D01, persistence design | All, Security chủ trì security review | Reset/wrap/nonce tests, exact C↔Go vectors |
| D12 CANDIDATE | Bounded queues với overflow counters; persistence/priority policy cần review | Không bảo đảm giữ 100% khi offline vô hạn; RAM/storage/load budget TBD | GW/Backend | Event identity, resource budget | Gateway/Backend + QA | Overflow/soak/power-loss/replay measurements |
| D13 BLOCKED Security | Bearer/JWT hiện provisional; credential/token lifecycle/WSS transport cần ADR options review | Không token URL, luôn server-side RBAC; chưa production auth | Backend/Web/Mobile | Threat model/identity requirements | Backend/Web/Mobile + Security | Auth ADR, scope/Origin/token lifecycle/reconnect security tests |

## Remediation decisions và allowlist

Mọi lựa chọn biên tập R1 là `PROPOSED / PENDING HUMAN REVIEW`. Giữ approved direction/version decisions; không approve firmware protocol hoặc RF profile. Phạm vi không đòi sửa callers/runtime/tests/config/exports vì chỉ thay tài liệu; tác động liên quan là cross-references giữa bảy docs và sources read-only.

| Allowed file, cũng là actual changed file | Remediation / disposition |
|---|---|
| docs/architecture/system-overview.md | Sửa MQTT drift, responsibility/safety/status boundaries; không freeze numbers |
| docs/architecture/interfaces.md | Map owner/consumer/security/recovery/versioning và RTM |
| docs/requirements/requirements.md | Giữ tám IDs/status, thêm 15 PROPOSED và observable AC/evidence requirements |
| docs/adr/0001-hybrid-tdma.md | Giữ accepted direction, mở rộng rationale/dependencies dưới DRAFT |
| docs/adr/README.md | Register ADR-0001/0002/0003, tách review/evidence |
| docs/development/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md | Audit sources/findings/options/validation/handoff |
| docs/development/firmware/C_STANDARD_SOURCE_TRACEABILITY.md | Map 123 S1 IDs/12 categories và future-rule domains; chưa viết v2 |

## Remaining blockers và reviewer handoff

Các blocker dưới đây chặn design/protocol/production acceptance, không bị đóng bằng documentation checks:

- Owner + QA review RTM mới và scope R1; sign-off chưa được cấp bởi tác giả/agent.
- Gateway/TDMA + Node/MAC + RF xử lý D02–D05/D11, holdover/recovery/bootstrap và margin qua HIL.
- Security + Node/GW/Backend xử lý D01/D11, keys/nonce/replay và golden vectors trước production codec.
- Backend/MQTT + Infra-Security review contract/lifecycle/order/identity/expiry; #14 Closed không thay sign-off.
- Backend/Web/Mobile + Security giải D13, API/WSS conformance và consumer integration; #15/#18 chưa là implemented service.
- S1 đã được pin và so byte trong R2; owner review source-rule adoption/approval cho C Standard v2 vẫn còn chờ. Local planning citation markers chưa được independent verification, không lấy làm regulatory/timing evidence.

Không cài tool/dependency, không thay CI, contracts, RF/pinmap, code hoặc GitHub settings; không auto-merge/flash/TX. Draft PR chỉ xin human review hồ sơ, không chứng nhận G0–G6 PASS.

## Validation results R1 và limitations

Các kết quả dưới đây chỉ áp dụng cho documentation/static scope. Không cấp AUDIT_PASS độc lập hoặc G0–G6 PASS. Python `3.12.3`, jsonschema `4.26.0`, PyYAML `6.0.3`; không cài thêm dependencies.

| Exact command / thao tác | Exit / status | Observed result và giới hạn |
|---|---|---|
| `git branch --show-current`, `git rev-parse HEAD`, `git status --porcelain=v1`, `git remote -v`, `git show-ref refs/remotes/origin/main` | 0 từng lệnh | Đúng repo/branch/base; initial tree clean. Final branch commit sẽ khác base và được PR pin; không commit main. |
| GitHub GET `branches/main`, `issues/60`, `issues/60/comments`, và Issues #9/#10/#11/#12/#14/#15/#18 + comments | HTTP 200 | Current main trùng base; Issue #60 OPEN, body/scope không đổi khi recheck trước publication. Dependency state không là approval. |
| `git diff --check` | 0 | Không whitespace error; kiểm lại sau khi stage và trước commit. |
| `python3 scripts/verify_structure.py` | 0 | Foundation/static PASS; tool vẫn in NOT_IMPLEMENTED cho CMakeLists của bốn firmware components. Không build/HIL proof. |
| `find contracts -type f -name '*.json' -print0` piped vào `xargs -0 -r -n1 python3 -m json.tool` với stdout tới `/dev/null`, như ci-contracts.yml | 0 | 11 JSON files parse được, chỉ syntax; không schema/semantic/runtime conformance. |
| `python3 /tmp/r1_validate_docs.py` | 0, rerun trên final docs | Exact Issue allowlist bảy paths; hai bảng RTM có cùng 23 unique IDs, tám cũ giữ NOT_VERIFIED, 15 mới PROPOSED; relative/local links/fragments và references hợp lệ; S1 map 123/123 IDs/12 categories; required finding fields đủ. Không crawl tất cả external URLs. |
| `python3 -c 'import yaml, jsonschema, openapi_spec_validator'` | 1, dependency probe | ModuleNotFoundError cho openapi_spec_validator; đây là môi trường thiếu optional validator, chưa chạy assertion của contract suite. |
| `python3 contracts/tests/check_contracts.py` và `python3 -m unittest discover -s tests/contract -p 'test_*.py' -v` | NOT_RUN | Hai entry points cần openapi-spec-validator chưa có. Không cài dependency vì Issue cấm tự cài tool/dependency; không báo schema/OpenAPI suite PASS. |
| `git diff 9cb0885ad1de5112e9ae358e15e04e19b6fb38ae`, final staged diff và file inventory | 0, manual review + scope check | Chỉ bảy docs; ADR-0002/0003, contracts, firmware, backend, CI/dependencies không đổi. Numeric candidates không được promote; không thêm credential/build artifact hoặc RF/HIL/timing PASS claim. |
| Build ESP-IDF, real broker/DB/API/WSS, C↔Go golden, security execution, simulation, HIL/RF/timing | NOT_RUN / NOT_VERIFIED | Không có implementation change hoặc hardware authorization trong R1; không suy evidence từ static docs checks. |

Local receipts/logs: `/tmp/r1-evidence/commands.json`, `diff-check.log`, `structure.log`, `contract-json-syntax.log`, `optional-validator-dependency.log`, `docs-final.log`. Scripts/source snapshots trong `/tmp/r1_validate_docs.py` và `/tmp/r1-live-sources.json` là artifacts ngoài repository, không là CI dependencies. Đây là historical local evidence R1; script và source snapshots trong /tmp không phải durable reproduction package. R2 thay phụ thuộc này bằng checker đầy đủ và output trong PR description, đọc Issue scope hiện tại và tải pinned S1; không cần /tmp cũ hoặc đường dẫn local của tác giả.

Source provenance checks riêng: local source `git ls-files --error-unmatch docs/C_CODING_STANDARDS.md` exit 1; `git check-ignore -v docs/C_CODING_STANDARDS.md` exit 0; GitHub GET S1 tại source HEAD HTTP 404, GET `.gitignore` tại cùng HEAD HTTP 200, xác nhận ignore pattern. Các lệnh này chỉ kiểm checkout/commit cũ; không chứng minh upstream main thiếu S1. F-11 đã được hiệu chỉnh bằng source/hash R2 ở trên.

Draft PR sẽ chứa base/head SHA, allowlist và các NOT_RUN/NOT_VERIFIED này. Human review còn chờ theo reviewer handoff; không merge trong R1.

## Validation R2 và durable evidence

Nguồn tái lập: mô tả [Draft PR #61](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/61), mục "Review remediation R2 / Reproduction" lưu nguyên checker Python và output. Prerequisites: Python 3.12+ với standard library, Git, GitHub CLI `gh` đã có read access tới hai repositories, checkout PR head cùng base/R1 commits và HTTPS tới GitHub. Không cần package mới hoặc file /tmp của tác giả. Checker kiểm scope cả PR và delta R2, preservation của 23 requirements/architecture/contracts, links/IDs/finding fields, pinned source digest và 123/123 mapping. Scope của checker là documentation structure/provenance, không technical approval; không crawl mọi external URL hoặc chứng minh semantic correctness bằng regex.

Kết quả R2 đã chạy trên nội dung sửa, kiểm lại sau commit và pin final HEAD trong PR description:

| Command / kiểm tra | Exit / observed result |
|---|---|
| `git diff --check` | 0, không whitespace errors |
| `python3 scripts/verify_structure.py` | 0, static foundation only; bốn firmware components vẫn NOT_IMPLEMENTED |
| JSON syntax pipeline của `ci-contracts.yml` | 0, 11 JSON files; không semantic/conformance proof |
| Checker Python nguyên văn trong PR description, chạy từ repo root | 0; exact bảy PR paths, delta R2 chỉ hai docs; RTM byte-identical với R1, tám IDs cũ và 15 PROPOSED, cả 23 NOT_VERIFIED; 140 relative links/fragments, không absolute local links; table columns/references hợp lệ; 123/123 source IDs, 12 categories, dispositions không đổi; F-01..F-12 đủ trường |
| Source byte comparison R2 | Upstream/local đều 41197 bytes và SHA-256 `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de`; byte equality true; upstream Git blob SHA-1 khớp `7a5e011bc8133762c8da8433e60c0e801d41b801` |
| Read-only GitHub preflight | Issue #60 scope/body không đổi; PR #61 OPEN/Draft, đúng branch/head; main baseline không đổi |

Lần thử public API bằng urllib không xác thực trả HTTP 403 rate-limit trước assertions; checker cuối dùng `gh api` với read access sẵn có và đã chạy thành công. Thiếu access/network hoặc Issue body hash thay đổi phải làm checker dừng, không được bỏ qua hoặc suy PASS. R2 không cài tool/dependency và không thay CI.

Full contract suite/OpenAPI dependency, firmware/security/timing/HIL/RF limitations của R1 giữ nguyên. Provenance pin không xác nhận source-local approval có hiệu lực ở monorepo. Không merge hoặc tự đổi Draft thành ready-for-review.
