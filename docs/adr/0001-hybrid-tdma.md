# ADR-0001: Phân chia Hybrid TDMA Planner và Executor

- Design status: `ARCHITECTURE_DIRECTION_ACCEPTED`, diễn đạt lại status gốc "Accepted as architectural direction"; không cấp approval mới.
- Evidence status: `RF_TIMING_NOT_VERIFIED`; ADR này không đóng G1/G2/G3 hoặc security gates.
- Rationale/traceability bổ sung R1: `DRAFT / PENDING TECHNICAL REVIEW`, [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60).
- Reviewers cần có: Gateway/TDMA, Node/MAC, RF/Hardware, Backend/MQTT, Security/QA; chưa ghi nhận sign-off R1.

## Bối cảnh và vấn đề

Baseline đã chọn Gateway ESP32 + SX1276 là TDMA Master một radio half-duplex, Backend lập lịch tương lai và Gateway tiếp tục khi mất backhaul. Nguồn: [ADR gốc tại base SHA](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/adr/0001-hybrid-tdma.md#L3-L8), [Radio MAC §1](../../contracts/radio-mac/specification.md), [TDMA §§2–3](../../contracts/radio-mac/tdma-schedule.md).

Inference kỹ thuật R1: điều khiển từng slot qua Backend làm executor phụ thuộc Wi-Fi/MQTT delay/reconnect. Baseline không có timing evidence cho đường mạng này nên không thể dùng delivery làm chứng minh slot safety. Nguồn đối chiếu: [MQTT semantics §§3–4](../../contracts/mqtt/semantic-rules.md), [G1/G3](../verification/acceptance-gates.md).

## Quyết định và phạm vi

Giữ quyết định gốc: Go Backend tính và quản lý version của lịch tương lai; Gateway validate, stage và execute locally; Node timestamp Beacon và theo slot đã được cho phép. Gateway có local fallback/bootstrap design, không cần Backend cho từng TX/RX instant. Nguồn: ADR gốc, Radio MAC §1, TDMA §§2–3.

| Vai trò | Trách nhiệm và giới hạn | RTM / contract |
|---|---|---|
| Backend Planner | Lưu proposal/review/dispatch intent, publish ID/version/expiry, reconcile actual report. Không tự suy ACTIVE từ PUBACK hoặc STAGE_ACK | SYS-001, MAC-003; MQTT semantics §4, [API semantics](../../contracts/api/contract-semantics.md) |
| Gateway Executor | Validate identity/version/expiry, collision/half-duplex/airtime; persist shadow; đủ complete announcement cycles; switch tại local boundary rồi report actual activation | MAC-003/005/006; TDMA §2, MQTT semantics §4 |
| Node TDMA client | Xác thực Beacon/session/mapping. Thiếu lịch mới hoặc mất bảo đảm timing thì không phát slot cũ | MAC-002/004, SEC-001; TDMA §3 |
| Radio owner / driver | Tuần tự hóa SPI/state; ISR không SPI/log/blocking; chuyển event sang task có giới hạn | FW-002/003/004; [embedded instructions](../../.github/instructions/embedded.instructions.md) |

IDs tham chiếu [RTM](../requirements/requirements.md#rtm); IDs mới vẫn PROPOSED. ADR không freeze wire layout, cipher, timer API, GPIO hoặc numeric RF/timing profile.

## Control plane và data plane

Control plane quản lý proposal, version, authorization, staging và activation report qua [MQTT contracts](../../contracts/mqtt/topics.md); Gateway giữ quyền quyết định thời điểm local execution. Data plane nhận RF data/alerts hợp lệ, áp dụng RF ACK policy, chuyển event vào bounded MQTT buffer; Backend validate/dedup/lưu PostgreSQL, cung cấp REST/WSS. Nguồn: Radio MAC §§1/3, MQTT topics §§2–4, API semantics. Phân chia này không thêm service hoặc protocol mới.

## Các lựa chọn và trade-offs

| Phương án | Disposition | Rationale và hệ quả |
|---|---|---|
| Backend plan + Gateway execute locally | Hướng đã accepted | Giữ local timing/fail-safe; Gateway/Node phải quản state machine, persistence, version reconciliation và reset recovery. Nguồn: ADR gốc, TDMA §§2–3. |
| Cloud/MQTT kích hoạt từng slot | Đã rejected cho MVP trong ADR gốc | Inference: không có bounded delivery evidence, tăng coupling với backhaul; xung đột local Master/SYS-001. |
| ChirpStack / LoRaWAN | Đã rejected cho MVP trong ADR gốc | Ngoài Custom LoRa P2P scope theo [AGENTS.md](../../AGENTS.md); không đưa LoRaWAN MAC/OTAA vào design. |
| Redis / microservices làm mặc định | Đã rejected cho MVP trong ADR gốc | Giữ Go Modular Monolith + PostgreSQL theo [system overview](../architecture/system-overview.md). Giảm số thành phần vận hành là rationale Inference R1, không là benchmark. |

## Autonomy và failure invariants

Theo TDMA §3 và MQTT semantics §4, Gateway mất Backend tiếp tục active schedule chỉ khi state/profile còn hợp lệ và local safety được thỏa mãn. Buffer phải bounded, có overflow observability; không hứa giữ mọi event khi offline vô hạn. Reconnect phải reconcile identity/version/current status; không execute stale retained schedule/command. Xem SYS-001/002.

Gateway reboot phân biệt persisted active với shadow chưa active; không âm thầm promote shadow. Node thiếu mapping mới không đoán slot. Counter reset/wrap không được làm schedule/replay cũ thành hợp lệ. Bootstrap khi không có active hợp lệ và holdover khi mất Beacon cần security/timing design; ADR không chọn số Beacon hoặc thời gian recovery. Nguồn: TDMA §3, [D01/D05/D11/D12](../../contracts/OPEN_DECISIONS.md).

Single-radio half-duplex buộc Beacon, downlink, ACK, priority access và periodic RX chia sẻ timeline. Inference: ACK/retry/security overhead có thể làm candidate profile không còn phù hợp, cần tính lại airtime và đo turnaround. CAD không chứng minh không collision; alarm vẫn chịu airtime admission. Nguồn: Radio MAC §4, TDMA §§1/3; MAC-005/006/007.

## Dependencies, rủi ro và quyết định mở

- D01/D11: authenticated framing, nonce/replay/key lifecycle và epoch/version mapping; CRC không đủ, không production codec trước approval. Nguồn: Radio MAC §§2–3, [vector plan](../../contracts/radio-mac/test-vectors/README.md); SEC-001/003/004.
- D02/D03/D04: RF/legal applicability, ToA, IRQ-to-task latency, clock drift và guard margin cần G1/G3 theo [Issue #11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11). Không chốt superframe/slot/guard/jitter.
- D05/D07/D12: announcement horizon, restart/reconnect và bounded buffering cần review/HIL/integration. D08 giữ MQTT 5.0 OWNER_ACCEPTED theo [ADR-0002](0002-mqtt-5.md); version approval không thay contract review.

Canonical register: [OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md). Options/constraints/evidence handoff R1 trong [audit](../development/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ dẫn về IDs sẵn có, không đóng decisions hoặc sửa contracts.

## Truy vết và giới hạn evidence

Requirements chính: MAC-001/002/003/004/005/006/007, SYS-001/002, FW-001/002/003/004, SEC-001/003/004, DATA-001/002 và INT-001 trong RTM. Contract definitions theo Radio MAC/TDMA/MQTT links trên; exact firmware baseline giữ [ADR-0003](0003-esp-idf-v6-1.md).

Firmware vẫn scaffold theo AGENTS.md. ADR không chứng minh implementation, nonce safety, timing/RF compliance hoặc compatibility C↔Go. Build, schema validation và simulation không thay acceptance gates. Chỉ human review có evidence mới đóng từng gate; R1 dừng ở Draft PR.
