# Ma trận truy vết requirements, baseline R1

Status tài liệu: `DRAFT`, [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Ưu tiên theo Issue: Correctness > Safety > Reliability > Maintainability > Performance.

Giữ nguyên tám IDs và verification `NOT_VERIFIED` của baseline. Design approval của tám requirements gốc chưa được ghi nhận trong nguồn B, dùng `DRAFT / APPROVAL_NOT_RECORDED`; không suy approval từ ADR có accepted direction. Các IDs mới là `PROPOSED`, câu "phải" mô tả normative intent chờ owner/reviewer duyệt, chưa là requirement đã được chấp thuận. Evidence location dưới đây là nơi yêu cầu nộp evidence trong task sau, **không chứng minh artifact/test đã tồn tại hoặc đã chạy**. Nguồn thẩm quyền: [AGENTS.md](../../AGENTS.md), G và V.

## Nguồn và quan hệ ADR/Contract

| Mã nguồn | Repository path / section | Design authority |
|---|---|---|
| B | [RTM trước R1, base SHA](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/9cb0885ad1de5112e9ae358e15e04e19b6fb38ae/docs/requirements/requirements.md#L5-L16) | Initial draft, tám IDs gốc; mọi status NOT_VERIFIED |
| A1 | [ADR-0001](../adr/0001-hybrid-tdma.md) | Architecture direction accepted; RF/timing chưa verified |
| A2 | [ADR-0002](../adr/0002-mqtt-5.md) | MQTT 5.0 OWNER_ACCEPTED; cross-team review pending |
| A3 | [ADR-0003](../adr/0003-esp-idf-v6-1.md) | Exact ESP-IDF v6.1 approved by owner; build/HIL riêng |
| E | [embedded instructions](../../.github/instructions/embedded.instructions.md) | Repository firmware constraints; không là HIL evidence |
| C | [coding standards hiện hành](../development/coding-standards.md) | Engineering/review constraints; không import standard demo |
| R | [Radio MAC specification](../../contracts/radio-mac/specification.md) | DRAFT, security/wire BLOCKED G2 |
| T | [TDMA schedule](../../contracts/radio-mac/tdma-schedule.md) | Candidate profile và safety invariants, chưa freeze |
| M | [MQTT semantic rules](../../contracts/mqtt/semantic-rules.md) | Proposed contract rules, cross-team pending |
| P | [MQTT topics](../../contracts/mqtt/topics.md) | Contract DRAFT; protocol version owner-accepted |
| A | [API semantics](../../contracts/api/contract-semantics.md), [OpenAPI](../../contracts/api/openapi.yaml) | PROPOSED, auth D13 chưa approved |
| Dxx | [OPEN_DECISIONS](../../contracts/OPEN_DECISIONS.md) | Canonical decision IDs; không tự đóng trong RTM |
| V | [contract verification](../../contracts/verification.md) | Verification plan; không tự tạo PASS |
| G | [acceptance gates](../verification/acceptance-gates.md) | Evidence requirements G0–G6 |

A1 áp dụng xuyên suốt firmware/TDMA/SYS; A2 cho MQTT/DATA và A3 cho mọi firmware requirement. Source/contract chi tiết từng row tiếp tục giới hạn approval. ID Dxx trong row là source decision, không là requirement ID mới.

<a id="rtm"></a>

## Requirements và design status

Hai bảng được join bằng ID. Mỗi requirement có normative statement, source/ADR/Contract, design status, owner/reviewer, verification method, observable AC, evidence location và verification status. Owner/reviewer là vai trò đề xuất, không phải assignment hoặc sign-off đã có.

| ID | Normative statement | Source / ADR / Contract section | Design status | Owner / required reviewer |
|---|---|---|---|---|
| RF-001 | TX frequency/ERP/emissions/duty limitations phải đáp ứng quy định VN áp dụng cho thiết bị/kịch bản thực. | B, R §4, D03 | DRAFT / APPROVAL_NOT_RECORDED | RF / RF-Hardware + Regulatory |
| MAC-001 | TDMA slots không overlap trong nominal operation được validate. | B, T §§1/3 | DRAFT / APPROVAL_NOT_RECORDED | Gateway + Node / RF + QA |
| MAC-002 | Mất Beacon hoặc lịch cũ phải vô hiệu hóa periodic TX không an toàn. | B, T §3 | DRAFT / APPROVAL_NOT_RECORDED | Node / Gateway + RF |
| SYS-001 | Gateway phải vận hành local an toàn khi không có MQTT/Backend. | B, A1, T §3 | DRAFT / APPROVAL_NOT_RECORDED | Gateway / Backend + RF + QA |
| ALERT-001 | Phải đánh giá latency và contention percentiles của RF alarm. | B, T §§1/4 | DRAFT / APPROVAL_NOT_RECORDED | RF + Gateway / Node + Backend + QA |
| DATA-001 | MQTT redelivery không được tạo duplicate business events. | B, M §2, P §2 | DRAFT / APPROVAL_NOT_RECORDED | Backend / Gateway + Storage + QA |
| SEC-001 | RF frames phải xác thực control/data và ngăn replay. | B, R §3, D01/D11 | DRAFT / APPROVAL_NOT_RECORDED | Embedded Security / Node + Gateway + QA |
| SEC-002 | TLS, identity, least-privilege ACL và server-side RBAC phải bảo vệ integration. | B, A2, M §§1/3, A | DRAFT / APPROVAL_NOT_RECORDED | Backend / Gateway + Infra-Security + Web/Mobile |
| FW-001 | Firmware phải dùng bounded buffers/queues với lifetime/ownership rõ; tránh malloc/free lặp trong steady state. | E, C | PROPOSED | Gateway + Node / Embedded + QA |
| FW-002 | Single Radio Owner phải tuần tự hóa SPI và modem state cho SX1276. | E, R §§1/4 | PROPOSED | Gateway + Node / Driver + RF |
| FW-003 | ISR/timer handlers chỉ timestamp/notify bounded task hoặc queue; không SPI/blocking network. | E, R §4 | PROPOSED | Gateway + Node / Embedded + RF |
| FW-004 | Task/queue/I/O recovery phải bounded, có timeout/overflow và watchdog handling được review. | E, C, D12 | PROPOSED | Gateway + Node / Embedded + QA |
| MAC-003 | Gateway phải validate/stage/announce lịch versioned, chỉ activate ở boundary; Backend phân biệt STAGED với actual ACTIVE. | A1, T §2, M §4 | PROPOSED | Gateway + Backend / Node + QA |
| MAC-004 | Node chỉ holdover nếu có timing/sync evidence; nếu không bảo đảm slot an toàn phải ngừng periodic TX và recovery. | T §3, D04/D05 | PROPOSED | Node / Gateway + RF |
| MAC-005 | Gateway phải phân xử Beacon/DL/ACK/priority/data trên một radio half-duplex. | A1, T §§1/3, R §4 | PROPOSED | Gateway / Node + RF |
| MAC-006 | Gateway và Node phải local airtime admission cho mọi loại TX, kể cả alarm/retry/join/Beacon/ACK. | R §4, D03 | PROPOSED | Gateway + Node / RF-Regulatory + QA |
| MAC-007 | Priority access phải bounded và tuân authenticated MAC, ACK/retry và local airtime; không coi CAD bảo đảm không collision. | R §§1/4, T §§1/4 | PROPOSED | Node + Gateway / RF + QA |
| SYS-002 | Reboot/reconnect phải khôi phục active/shadow và reconcile idempotently; không promote shadow hoặc execute stale proposal. | T §3, M §§2/4, D11/D12 | PROPOSED | Gateway + Backend / Node + Security-QA |
| SEC-003 | Nonce phải duy nhất trên cùng key qua reset/rollover/direction; chưa chứng minh uniqueness thì chặn TX. | R §3, D01/D11 | PROPOSED | Node + Gateway / Security + QA |
| SEC-004 | Parser phải validate untrusted RF/schedule input trước dispatch; serialize tường minh, không cast packed struct làm wire. | R §3, M §§1/4, D01/D11 | PROPOSED | Node + Gateway + Backend / Security-QA |
| DATA-002 | MQTT reconnect/expiry/session handling phải theo ADR-0002 và draft topic semantics, tách transport ACK khỏi business outcome. | A2, P §§1/3/4, M §3 | PROPOSED | Gateway + Backend / Infra-Security + QA |
| INT-001 | Phải tách syntax/schema/build/simulation khỏi behavioral C↔Go conformance, HIL/RF và security evidence. | V, G, A3 | PROPOSED | QA / Gateway + Node + Backend + RF + Security |
| INT-002 | REST/WSS consumers phải theo Backend authorization, idempotency và state-resync semantics; không bypass MQTT/DB boundaries. | A, M §2, D13 | PROPOSED | Backend + Web/Mobile / Security + QA |

## Verification và acceptance criteria

| ID | Verification method | Observable / measurable AC | Evidence location, hiện PENDING | Verification status |
|---|---|---|---|---|
| RF-001 | Qualified RF tests + regulatory assessment | Có board/profile/legal assessment được reviewer chấp thuận và phép đo theo điều kiện đó; threshold TBD do RF owner xác định sau phân loại thiết bị. | G1: docs/verification/; raw RF artifacts | NOT_VERIFIED |
| MAC-001 | HIL timestamp traces với hai đến mười lăm Node theo yêu cầu gốc | Trace TX/RX/slot ownership không overlap trong profile/load đã duyệt; guard/drift budget TBD, đo rồi owner quyết margin. | G1/G2/G3: tests/hil/, docs/verification/ | NOT_VERIFIED |
| MAC-002 | Fault injection HIL | Missing Beacon, version mismatch và thiếu mapping mới không gây TX theo slot lỗi thời; loss/holdover threshold TBD qua drift/guard evidence. | G3: tests/hil/, docs/verification/ | NOT_VERIFIED |
| SYS-001 | Disconnect, restart, bounded-buffer tests | Mất backhaul không cần per-slot commands; active hợp lệ còn chạy, airtime/sync invariants còn hiệu lực, overflow quan sát được; không hứa offline vô hạn không mất dữ liệu. | G3/G4: tests/hil/, tests/integration/ | NOT_VERIFIED |
| ALERT-001 | Repeatable experiments P50/P95/P99 | Định nghĩa detection→GW và detection→Backend/Web, concurrent alarms/load, sample count và uncertainty; ghi phân phối/loss. SLA và PASS thresholds TBD qua owner decision; mục tiêu dưới 3 s không là SLA. | G1/G3/G6: docs/verification/, raw traces | NOT_VERIFIED |
| DATA-001 | QoS 1 replay và concurrent DB integration tests | Cùng gateway/event identity khi retry, offline replay và reboot chỉ tạo một logical record/alert; conflicting payload cùng ID được phát hiện, không ghi đè âm thầm. | G4: tests/integration/; DB constraint/transaction evidence, Issue #18 | NOT_VERIFIED |
| SEC-001 | Threat model + protocol/HIL tests | Đủ approval cho security/wire; forged Beacon/ACK/Schedule, tampered tag và replay bị reject trước side effect; CRC không thay authentication. | G2/G5: approved ADR, golden vectors, protocol/HIL evidence | NOT_VERIFIED |
| SEC-002 | Security integration tests | Wrong principal/topic/payload identity, unauthorized resource/action và stale input bị từ chối; transport/version approval không thay auth design D13. | G4/G5: tests/integration/, security review artifacts | NOT_VERIFIED |
| FW-001 | Static review + memory/overflow stress tests | Mỗi buffer/queue có capacity/owner và overflow path; không out-of-bounds/use-after-lifetime. Capacity/stack budgets TBD qua measured load, không lấy số demo. | G3: review và memory/stack stress logs | NOT_VERIFIED |
| FW-002 | Call-path review + concurrent-request HIL | Mọi radio operation đi qua owner, không concurrent SPI/state mutation; lock/queue failure được xử lý có giới hạn. | G3: driver review, HIL SPI/state traces, Issue #10 | NOT_VERIFIED |
| FW-003 | ISR/API review + IRQ-to-task HIL | Không forbidden call trong ISR; init-before-enable, ISR overflow và latency được kiểm. Jitter/guard threshold TBD qua đo trên board/toolchain thật. | G1/G3: IRQ/task traces, API-context review | NOT_VERIFIED |
| FW-004 | Fault injection queue-full, timeout và radio stall | Từng failure path có observable verdict/counter và safe recovery; retry/resource limits TBD qua stress evidence, không treo hoặc TX ngoài policy. | G3/G5: fault/soak logs, review recovery policy | NOT_VERIFIED |
| MAC-003 | Lifecycle tests + late-arrival/reset HIL | Sai identity/expiry/clock/overlap/version bị reject; persist trước STAGE_ACK; đủ complete announcement cycles; ACTIVE_REPORT khớp actual switch. Horizon cụ thể vẫn candidate. | G2/G3/G4: state traces và activation measurements | NOT_VERIFIED |
| MAC-004 | Beacon-loss, drift/temp/power HIL | Authenticated mapping và uncertainty không vượt approved guard budget trước TX; threshold số Beacon/lease TBD do owner quyết sau phép đo; không mặc định ba lần. | G1/G3: sync/drift/holdover traces | NOT_VERIFIED |
| MAC-005 | Schedule semantic tests + RF turnaround HIL | Không simultaneous TX/RX; ACK/retry không lấn cửa sổ khác; timing budget gồm overhead thực. Margin/turnaround TBD qua đo. | G1/G2/G3: timeline/turnaround evidence | NOT_VERIFIED |
| MAC-006 | Admission unit tests + HIL TX-denial | Budget exhausted/invalid policy thì deny TX và có reason; không emergency bypass. Window/power/duty treatment TBD theo G1 approval. | G1/G3: approved policy, admission tests và TX traces | NOT_VERIFIED |
| MAC-007 | Concurrent alarm/CAD/retry fault tests | Quan sát collision/loss/backoff/retry và budget denial; không endless retry. Backoff/retry/latency thresholds TBD sau load/timing review. | G1/G2/G3: contention experiments, ALERT-001 evidence | NOT_VERIFIED |
| SYS-002 | Power-cut staging/activation, corrupt-state, reconnect tests | Phân biệt active/shadow; identity/epoch không reuse gây replay; original event IDs giữ nguyên nếu queue durable. Không tự hiểu proposal expires_at là active lease. | G3/G4/G5: NVS/fault/reconciliation logs | NOT_VERIFIED |
| SEC-003 | Threat model + power-loss/wrap protocol tests | Design được duyệt chỉ ra persistence/session/key lifecycle; negative tests nonce reuse/replay fail closed. Không chọn cipher/tag/nonce format trong RTM. | G2/G5: security ADR, persistence tests, approved vectors | NOT_VERIFIED |
| SEC-004 | Malformed/truncated/version/auth/replay boundary tests | Invalid length/direction/destination/version/reserved/auth/replay không gây OOB hoặc side effect; byte order/width theo contract đã duyệt, hiện BLOCKED. | G2/G5: parser negative tests và C↔Go vectors | NOT_VERIFIED |
| DATA-002 | Real broker reconnect, stale retained, expiry/ACL tests | Resubscribe/verify QoS, reject stale/wrong identity/untrusted clock, bounded buffers; PUBACK không cập nhật ACTIVE hoặc NODE_ACKED. Queue/session durations TBD qua integration. | G4/G5: Mosquitto/client traces, transport review | NOT_VERIFIED |
| INT-001 | Evidence manifest review + đúng test/build/gate tương ứng | Mỗi claim có Issue/commit/environment/versions/expected/actual/reviewer; Gateway và Node build exact v6.1 có logs khi claim build. Không PASS RF từ CI hoặc Closed Issue. | Từng gate: source-bound reports; actual evidence hiện chưa đính | NOT_VERIFIED |
| INT-002 | RBAC/resource-scope, 202/status và reconnect tests | Viewer/unauthorized scope bị chặn; 202 không ACTIVE; retry cùng key không tạo action mới; duplicate/out-of-order/overflow không làm UI rollback, có REST resync. Auth D13 còn blocked. | G4/G5: tests/contract/, tests/integration/, client integration traces | NOT_VERIFIED |

## Hành động còn chờ và giới hạn

Threshold TBD không được dùng để quyết PASS. RF/Gateway/Node đo timing/ToA/turnaround/drift theo [Issue #11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11), trình profile/guard/holdover margin cho owner review qua D02–D05. Security/Node/Gateway giải D01/D11 và [Issue #12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) trước production codec/vectors. Backend/Gateway/Infra review MQTT rules trước integration acceptance; Backend/Web/Mobile/Security giải D13 trước production auth.

Mục tiêu alarm dưới 3 s vẫn là research TARGET, không là SLA. Phải định nghĩa exact endpoints và concurrent alerts trước verdict; mobile push không có hard real-time guarantee theo nguồn B. R1 không chạy phép thử nào của các requirements trên. [Audit R1](../development/firmware/ARCHITECTURE_DOCUMENTATION_AUDIT.md) chỉ ghi deterministic documentation checks và gaps; [C standard traceability](../development/firmware/C_STANDARD_SOURCE_TRACEABILITY.md) là proposal cho task sau.
