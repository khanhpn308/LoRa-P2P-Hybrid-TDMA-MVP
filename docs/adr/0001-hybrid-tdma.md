# ADR-0001: Phân chia Hybrid TDMA Planner và Executor

- Design status: `ARCHITECTURE_DIRECTION_ACCEPTED`, diễn đạt lại status gốc "Accepted as architectural direction"; không cấp approval mới.
- Owner revision 2026-11-04: `OWNER_APPROVED_DESIGN_DIRECTION`, [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), docs child [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126): Local Alarm + Event-Only Remote Logging + Static TDMA + Maintenance Superframe. Các quyết định cũ không mâu thuẫn tiếp tục áp dụng; lịch sử supersession ở phần dưới.
- Evidence status: `RF_TIMING_NOT_VERIFIED`; ADR này không đóng G1/G2/G3 hoặc security gates.
- Rationale/traceability bổ sung R1: `DRAFT / PENDING TECHNICAL REVIEW`, [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60).
- Reviewers cần có: Gateway/TDMA, Node/MAC, RF/Hardware, Backend/MQTT, Security/QA; chưa ghi nhận sign-off R1.

## Bối cảnh và vấn đề

Baseline đã chọn Gateway ESP32 + SX1276 là TDMA Master một radio half-duplex, Backend lập lịch tương lai và Gateway tiếp tục khi mất backhaul. Nguồn: [ADR gốc tại base SHA](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/adr/0001-hybrid-tdma.md#L3-L8), [Radio MAC §1](../../contracts/radio-mac/specification.md), [TDMA §§2–3](../../contracts/radio-mac/tdma-schedule.md).

Inference kỹ thuật R1: điều khiển từng slot qua Backend làm executor phụ thuộc Wi-Fi/MQTT delay/reconnect. Baseline không có timing evidence cho đường mạng này nên không thể dùng delivery làm chứng minh slot safety. Nguồn đối chiếu: [MQTT semantics §§3–4](../../contracts/mqtt/semantic-rules.md), [G1/G3](../verification/acceptance-gates.md).

## Quyết định và phạm vi

**Quyết định hiện hành:** Go Backend độc quyền lập và quản lý phiên bản lịch, User có quyền phê duyệt lịch và cửa sổ kích hoạt. Gateway kiểm tra/stage và thực thi cục bộ, không tự sửa phân bổ khe hay kênh. Gateway chọn điểm chuyển tại ranh giới Superframe **trong cửa sổ đã duyệt**; Node chỉ TX theo ánh xạ, quyền và đồng bộ đã xác thực. Hướng Planner/Executor của ADR gốc vẫn giữ nguyên; bổ sung điều kiện chuyển lịch và quyền theo C03–C04 Owner-approved (2026-10-30).

| Vai trò | Trách nhiệm và giới hạn | RTM / contract |
|---|---|---|
| Backend Planner | Tạo và version lịch, quản lý quyết định phê duyệt của User và khoảng kích hoạt, publish ID/version/K_TARGET, reconcile actual report. Không tự suy ACTIVE từ PUBACK hoặc STAGE_ACK | SYS-001, MAC-003; MQTT semantics §4, [API semantics](../../contracts/api/contract-semantics.md) |
| Gateway Executor | Validate identity/version, collision/half-duplex/airtime; persist shadow; Backend ký PREPARE 80B, cần 100% UP_SCHED_READY 0x4C (41B) của các Node bị ảnh hưởng và Backend ký DECISION 80B; chỉ switch tại K_TARGET rồi report actual activation. Không tự đổi Slot Assignment | MAC-003/005/006; TDMA §2, MQTT semantics §4 |
| Node TDMA client | Local alarm độc lập RF; persistent bounded Event FIFO; xác thực Beacon/session/mapping và quyền. Chỉ TX Event trong DATA slot tĩnh của mình, nhận ACK trong slot; Maintenance HEALTH_REPLY theo lịch. Thiếu lịch hoặc timing an toàn thì không phát slot cũ | MAC-002/004/007, ALERT-001, SEC-001; #125 |
| Radio owner / driver | Tuần tự hóa SPI/state; ISR không SPI/log/blocking; chuyển event sang task có giới hạn | FW-002/003/004; [AGENTS.md](../../AGENTS.md) (repo authority) và [C Standard v2](../development/firmware/C_CODING_STANDARD_V2.md) (selected mandatory Rule IDs theo AGENTS.md, metadata DRAFT) |

Quy mô hiện hành: Multi-Gateway Star 1–4 Gateway, mỗi Gateway kênh riêng BW 125 kHz và Node cố định một Gateway/kênh (C01/C02). Node ID 8-bit theo Gateway (C06); Gateway tạo Event ID bền vững khi nhận RF mới, Backend chống lưu trùng Event ID do Gateway tạo (Owner G06 revision). Event dùng DATA slot tĩnh đã Backend/User duyệt theo #125; Gateway không tự tái cấp slot. Mesh ngoài phạm vi hiện tại; mọi chức năng Owner yêu cầu thuộc MVP (C09). Xem [kiến trúc](../architecture/system-overview.md). IDs tham chiếu [RTM](../requirements/requirements.md#rtm); các yêu cầu kỹ thuật chưa được duyệt vẫn PROPOSED. ADR không freeze wire layout, cipher, GPIO hoặc numeric RF/timing profile.

## Control plane và data plane

Control plane quản lý proposal, version, authorization, staging và activation report qua [MQTT contracts](../../contracts/mqtt/topics.md); Gateway giữ quyền quyết định thời điểm local execution. Theo #125, Node phát hiện vi phạm, kích hoạt local alarm độc lập với mạng rồi ghi Event vào persistent bounded FIFO. Không có Event thì không phát application data. Mỗi DATA slot thực hiện Node `Event TX → ACK RX`, Gateway `Event RX → durable acceptance → ACK TX`. Không có Node broadcast chặn mạng hoặc tranh khe Node khác.

Thiếu ACK hợp lệ thì retry cùng Event trong slot hợp lệ kế tiếp của chính Node. Retry budget hữu hạn nhưng policy/số lần còn OPEN; hết budget vẫn giữ durable pending cho recovery. Gateway idempotently ACK duplicate đã nhận bền vững, giữ ánh xạ `(gateway_id,node_id,security_session,frame_counter) → event_id` qua reboot/RF retry/MQTT replay; Backend dedup theo `(gateway_id,event_id)` và phát hiện payload conflict. ACK xác nhận Gateway durable acceptance, không phải Backend DB commit hoặc exactly-once delivery. Node không truyền Event ID; cách giữ cùng Event trong FIFO qua reboot/retry và liên kết security counter cần G2 compatibility review riêng, không tự đổi identity/nonce/wire.

Maintenance Superframe nằm giữa các DATA Superframe theo lịch, mục tiêu heartbeat/sync **300 s**. Gateway phát authenticated `SYNC_BEACON`, từng Node trả `HEALTH_REPLY` trong slot không chồng lấn. Beacon đơn phương không chứng minh Node alive. Owner-approved MVP config: DATA W500/G50ms mỗi bên, READY R400/G_R50ms mỗi bên, Join CAD mọi lúc/3 retry, Beacon HMAC32B, Diagnostic23B, reboot RX-only chờ Backend kích hoạt. RF timing/turnaround/HIL vẫn NOT_VERIFIED. Các contract/schema/MQTT/API đang dùng thiết kế cũ cần child G2/G4 của #125; ADR này không âm thầm đổi interfaces.

## Lịch sử quyết định bị thay thế

Owner revision #125 ngày 2026-11-04 supersedes các quy tắc ứng dụng/MAC sau; giữ lịch sử approval và không xóa evidence.

| Quyết định trước đây | Disposition và ranh giới compatibility |
|---|---|
| #77 optional periodic, `UP_TELEMETRY` / `TEMP_X10`, `uplink/telemetry` làm luồng mặc định; `Periodic ON/OFF` / `SET_PERIODIC_MODE` | **SUPERSEDED_BY_EVENT_ONLY**; bỏ business periodic mode qua migration topic/schema/API/UI có version; không tái dùng packet `0x26` âm thầm. |
| C08 / #78 priority Alert contention, CAP/PCSS/CAD/backoff làm access path thông thường | **SUPERSEDED_BY_STATIC_TDMA**; giữ local alarm, quyền và RF/airtime safety. |
| CT-01-ACK-01, Owner approval 2026-10-30: `ACK_BITMAP` 16-bit/2B trong Beacon N+1 ACK Telemetry kỳ N; không ACK Telemetry riêng | **SUPERSEDED semantics / NOT_APPLICABLE_TO_EVENT_ACK**. Không sửa trường/offset hay tái dùng `0x21`; Beacon 28B/HMAC transcript/keys/anti-replay phải có G2 compatibility review trước thay wire. |
| Beacon mỗi DATA SF cho Telemetry ACK và `P-10S-15` 5 subframes/400 ms slots/PCSS | **OBSOLETE candidate**; tính lại DATA/Maintenance theo ToA và guard đo được. Giữ countdown 3→2→1, affected Node ACK, lease và Join/Recovery safety. |

Approval gốc của Planner/Executor và C01–C09 không mâu thuẫn được giữ. Supersession kiến trúc không phê duyệt UP_ALERT payload, Event ACK/UP_HEALTH_REPLY codepoint hoặc wire mới; registry/Beacon auth contracts cần Issue G2 riêng. Child #126 chỉ thay năm tệp kiến trúc, không tuyên bố đã migration toàn bộ active references.

## Các lựa chọn và trade-offs

| Phương án | Disposition | Rationale và hệ quả |
|---|---|---|
| Backend plan + Gateway execute locally | Hướng đã accepted | Giữ local timing/fail-safe; Gateway/Node phải quản state machine, persistence, version reconciliation và reset recovery. Nguồn: ADR gốc, TDMA §§2–3. |
| Cloud/MQTT kích hoạt từng slot | Đã rejected cho MVP trong ADR gốc | Inference: không có bounded delivery evidence, tăng coupling với backhaul; xung đột local Master/SYS-001. |
| ChirpStack / LoRaWAN | Đã rejected cho MVP trong ADR gốc | Ngoài Custom LoRa P2P scope theo [AGENTS.md](../../AGENTS.md); không đưa LoRaWAN MAC/OTAA vào design. |
| Redis / microservices làm mặc định | Đã rejected cho MVP trong ADR gốc | Giữ Go Modular Monolith + PostgreSQL theo [system overview](../architecture/system-overview.md). Giảm số thành phần vận hành là rationale Inference R1, không là benchmark. |

## Autonomy và failure invariants

Clarification R2 theo [Issue #64](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/64) và [review #63](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/63#issuecomment-6395708147), vẫn thuộc R1 `DRAFT / PENDING TECHNICAL REVIEW`. Các inference/limitations dưới đây không đổi accepted direction hoặc contract state machine.

Theo quyết định C07, Gateway mất Backend chỉ chấp nhận Node khi quyền thiết bị còn hiệu lực **và chứng minh được**; không tự gia hạn. Đồng thời, Gateway chỉ tiếp tục persisted Active schedule đã xác thực khi identity/version, profile/airtime, sync/time confidence và local safety còn hợp lệ. `expires_at` của schedule proposal chỉ giới hạn acceptance/activation của proposal, **không phải** thời hạn Active Schedule hoặc Device Authorization Lease. Định dạng/thời hạn quyền, nguồn thời gian và cách kiểm tra sau reboot vẫn OPEN G2/G3; không có mặc định chạy vô hạn. Proposed safety inference cho SYS-001: khi không chứng minh được điều kiện TX thì chặn TX bị ảnh hưởng, reason phải quan sát được; fallback/bootstrap và resume procedure cần Gateway/Node/RF/Security review, không tự chọn ở R2.

Buffer phải bounded, có overflow/drop observability; không hứa giữ mọi event khi offline vô hạn. Reconnect reconcile identity/version/current status, không execute stale retained schedule/command. Event đã persist trong durable queue giữ identity gốc khi replay. Nguồn: MQTT semantics §2/§4, D12; SYS-001/002, DATA-001/002.

Ba clock domains phải phân biệt khi review: trusted UTC dùng kiểm proposal expiry; local monotonic clock dùng TDMA deadlines trong một boot/context; Beacon-derived RF synchronization giúp Node căn slot với Gateway. MQTT delivery không là slot clock; monotonic timestamp không tự là UTC và không mặc nhiên so sánh được xuyên reboot/thiết bị. Nguồn: MQTT semantics §§2.4/3/4, TDMA §§2–3. Inference cần review: provenance, mapping/uncertainty giữa các domain, UTC jump/loss, reset discontinuity và holdover policy phải có fault/HIL evidence trước timing acceptance. R2 không chọn clock source, ngưỡng drift/guard hoặc cách tiếp tục active khi clock mất tin cậy. Coverage proposal nằm tại open items của RTM, chưa là requirement mới.

Gateway reboot phân biệt authenticated persisted active với shadow chưa active; không âm thầm promote shadow. Corrupt/inconsistent NVS hoặc thiếu continuity identity/epoch/version không cấp quyền TX; recovery procedure còn pending. Node thiếu mapping mới không đoán slot. Counter reset/wrap hoặc rollback không được làm schedule/replay cũ thành hợp lệ. Bootstrap khi không có active hợp lệ và holdover khi mất Beacon cần security/timing design; ADR không chọn số Beacon hoặc thời gian recovery. Nguồn: TDMA §3, MQTT semantics §§2/4, [D01/D05/D11/D12](../../contracts/OPEN_DECISIONS.md); SYS-002.

MQTT semantics §4 chỉ liệt kê STAGED→ACTIVE khi có actual `ACTIVE_REPORT` đã đối chiếu, đồng thời yêu cầu reconcile report đến muộn sau Backend `EXPIRED`. Transition cho trường hợp này chưa được duyệt. Backend phải kiểm request/schedule/version/Gateway/epoch, planned-vs-actual activation và current Gateway status trước mọi disposition; PUBACK/STAGE_ACK không chứng minh ACTIVE. Duplicate/reordered/late reports không được làm lùi newer state hoặc blind EXPIRED→ACTIVE. Đây là open transition/reconciliation design cho Backend + Gateway + contract owners, cần Issue riêng có scope contracts và integration evidence G4, không tự sửa bảng transition tại R2. Xem MAC-003 và INT-002.

Single-radio half-duplex buộc DATA/Event ACK, Maintenance SYNC_BEACON/HEALTH_REPLY, schedule/downlink, JOIN/RECOVERY và guard chia sẻ timeline, gồm boundary sang Superframe kế tiếp. Static validator phải kiểm ownership và mọi TX/RX/guard không chồng lấn. ToA, security overhead, durable-write latency, RX↔TX turnaround, jitter và drift qua mục tiêu 300 s/holdover phải có timing budget và HIL/RF evidence trước chọn slot/guard. Mất sync vượt policy thì fail-closed TX và recovery chỉ khi còn quyền hợp lệ; local alarm tiếp tục độc lập. Nguồn: #125; MAC-001/004/005/006/007. Các tham số và validator implementation chưa verified.

## Dependencies, rủi ro và quyết định mở

- D01/D11: authenticated framing, nonce/replay/key lifecycle và epoch/version mapping; CRC không đủ, không production codec trước approval. Nguồn: Radio MAC §§2–3, [vector plan](../../contracts/radio-mac/test-vectors/README.md); SEC-001/003/004.
- D02/D03/D04: RF/legal applicability, ToA, IRQ-to-task latency, clock drift và guard margin cần G1/G3 theo [Issue #11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11). Không chốt superframe/slot/guard/jitter.
- D05: Owner chốt ba nhịp announcement trọn Superframe 3→2→1; Node ACK/lease safety vẫn là điều kiện riêng. D07/D12: restart/reconnect và bounded buffering cần review/HIL/integration. D08 giữ MQTT 5.0 OWNER_ACCEPTED theo [ADR-0002](0002-mqtt-5.md); version approval không thay contract review.

Canonical register: [OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md). Options/constraints/evidence handoff R1 trong [audit](../audits/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ dẫn về IDs sẵn có, không đóng decisions hoặc sửa contracts.

Các hướng C01–C09 không mâu thuẫn và revision #125 đã được Owner chốt, nhưng không tự đóng canonical D01–D13 về tham số RF, wire/crypto, thời gian và contract. RF/MAC/Security/Backend owners còn phải quyết validity/reconciliation và clock/key lifecycle; [RTM open items](../requirements/requirements.md) chỉ đề xuất coverage gaps sau khi đối chiếu các requirement hiện có. Không chọn cipher/MIC/nonce/key lifecycle, RF power/frequency/profile, slot/guard, clock thresholds hoặc alarm SLA. G0 vẫn `NOT_VERIFIED` cho đến human Requirements/ADR approval; evidence G1–G6 là nghĩa vụ riêng.

## Truy vết và giới hạn evidence

Requirements chính: MAC-001/002/003/004/005/006/007, SYS-001/002, FW-001/002/003/004, SEC-001/003/004, DATA-001/002 và INT-001 trong RTM. Contract definitions theo Radio MAC/TDMA/MQTT links trên; exact firmware baseline giữ [ADR-0003](0003-esp-idf-v6-1.md).

Firmware vẫn scaffold theo AGENTS.md. ADR không chứng minh implementation, nonce safety, timing/RF compliance hoặc compatibility C↔Go. Build, schema validation và simulation không thay acceptance gates. Chỉ human review có evidence mới đóng từng gate; R1 dừng ở Draft PR.
