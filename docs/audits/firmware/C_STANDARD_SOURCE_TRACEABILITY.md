# C standard source traceability cho task v2.0.0-DRAFT

Status: `PROPOSED / PENDING HUMAN REVIEW`, [Issue #60](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/60). Đây là evidence foundation và disposition đề xuất, **không phải C Coding Standard mới**, không có rule nào được tự phê duyệt cho monorepo.

## Provenance và giới hạn nguồn

Nguồn S1 được pin tại [upstream docs/C_CODING_STANDARDS.md](https://github.com/khanhpn308/esp32e_sx1768-915Mhz/blob/2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5/docs/C_CODING_STANDARDS.md), commit `2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5` của `khanhpn308/esp32e_sx1768-915Mhz`. Upstream main tại thời điểm R2 trỏ commit này; reference sử dụng SHA bất biến, không phụ thuộc main tiếp tục thay đổi. Metadata nguồn ghi document ID `ESP32-LORA-CSTD`, Version `1.0.0`, ngày `2026-10-17`, header APPROVED và §14 DEC-01..DEC-08. Approval được nguồn ghi cho dự án thử nghiệm không truyền sang monorepo. Authority monorepo vẫn [AGENTS.md](../../../AGENTS.md), [coding standards](../../development/coding-standards.md), [ADR-0001](../../adr/0001-hybrid-tdma.md), [ADR-0002](../../adr/0002-mqtt-5.md), [ADR-0003](../../adr/0003-esp-idf-v6-1.md), [contracts](../../../contracts/README.md) và [gates](../../verification/acceptance-gates.md).

R2 so exact bytes của upstream Git blob với local S1 tại `/home/khanh/projects/iot/mcu/esp32_sx1276/codebase/main/docs/C_CODING_STANDARDS.md`, không sửa hoặc thay artifact local:

| Artifact | Bytes | SHA-256 |
|---|---|---|
| Upstream S1 tại commit đã pin | 41197 | `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de` |
| Local S1 được dùng trong R1 | 41197 | `70fc06ec5f21e21725f0227238ed3ab258e21b113b95f9ef481332d54715c5de` |

Kết quả so byte: `BYTE_IDENTICAL=true`; Git blob SHA-1 `7a5e011bc8133762c8da8433e60c0e801d41b801`, khớp upstream tree. Phân loại provenance hiện tại: `SOURCE_PINNED / LOCAL_BYTE_MATCH`. Chỉ provenance/content được xác minh; không là approval coding standard cho monorepo, API/register correctness hoặc hardware/RF evidence.

Lịch sử R1: checkout local ở HEAD `e46ff22dfe441911310bc9a859c202bf5c4cface` không track S1 và có ignore pattern; GET file ở commit cũ trả 404. Quan sát đó chỉ đúng với checkout/commit cũ, không chứng minh upstream main thiếu file. R2 rút lại kết luận tổng quát `UPSTREAM_REVISION_NOT_VERIFIED` của F-11 bằng immutable source và content comparison; không thay nội dung source hoặc các disposition đã đề xuất.

Đã đọc các bảng §§02–13, metadata, References, §14 và verification states. Mapping giữ nguyên 123 rule IDs/12 categories. Reviewer có thể lấy [raw pinned S1](https://raw.githubusercontent.com/khanhpn308/esp32e_sx1768-915Mhz/2af2bd2a99234b15f59848f4bdd0b1e920c2dcd5/docs/C_CODING_STANDARDS.md), kiểm SHA-256 và chạy checker được lưu đầy đủ trong mô tả [Draft PR #61](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/61); không cần local path của tác giả. Các rule/classification vẫn PROPOSED, không viết standard v2 trong R2.

## Disposition theo rule/category

Mọi classification trong bảng là proposal của R1; rationale kỹ thuật cho disposition là Inference từ S1 và constraints monorepo, không là xác minh official API/register behavior. KEEP giữ engineering intent để review sau, không xác nhận tính đúng mọi hardware/API detail. MODIFY phải viết lại phần phụ thuộc monorepo; RELOCATE chuyển numeric/wire/hardware ownership ra khỏi coding standard khi task tương ứng được duyệt. BLOCKED không cho triển khai dựa trên rule chưa xác minh.

| Category / S1 rule IDs | Source section | Classification | Rationale / monorepo authority | Compatibility impact | Required review owner |
|---|---|---|---|---|---|
| FMT-001, FMT-002, FMT-003, FMT-004, FMT-005, FMT-006, FMT-007, FMT-008, FMT-009 | S1 §02 | KEEP | Giữ style dễ review; đây là proposal kế thừa quy tắc nguồn, không tuyên bố toàn bộ là yêu cầu official ESP-IDF. | Không đổi runtime/wire; formatter áp dụng sau review. | Embedded + QA |
| FMT-010 | S1 §02 | MODIFY | Thay stable links bằng tài liệu exact v6.1 khi soạn v2; source References dùng stable dù gọi v6.1. | Cần kiểm official guide/version trước khi chọn formatter; không cài tool ở R1. | Embedded |
| NAM-001, NAM-002, NAM-003, NAM-007 | S1 §03 | MODIFY | Giữ namespace/module intent, review prefix map theo lora_mac/tdma_common/airtime_policy hiện có; NAM-007 dùng SHOULD nhưng câu cấm cần làm rõ mức. | Không auto-rename public APIs; map demo app_protocol không trở thành module bắt buộc. | Gateway + Node |
| NAM-004, NAM-005, NAM-006, NAM-010, NAM-011, NAM-012, NAM-013, NAM-014, NAM-015, NAM-016, NAM-017 | S1 §03 | KEEP | Giữ static scope, API stability, tên/đơn vị rõ và encapsulation theo source §03. | Không đổi ABI hoặc tên hàm hiện có trong Issue tài liệu. | Embedded |
| API-001, API-003, API-004, API-005, API-008, API-009, API-010 | S1 §04 | KEEP | Giữ public/private API, dependency boundary, buffer/timeout/thread-safety documentation và cấm dependencies chưa duyệt. | Giữ driver/MAC separation theo embedded instructions. | Gateway + Node |
| API-002 | S1 §04 | MODIFY | Header guards/interoperability cần mô tả đúng pure C; extern C chỉ khi có consumer C++ được duyệt, không ép cú pháp C++ vô điều kiện. | Cần compile headers bằng C trong task sau; không thêm C++ dependency. | Embedded + QA |
| API-006, API-007 | S1 §04 | MODIFY | Xác minh CMake dependency names với exact v6.1 và project components. DEC-08 nguồn gán Kconfig role selection vào API-006 nhưng rule API-006 nói REQUIRES/PRIV_REQUIRES. | Không kế thừa single-demo role choice cho hai firmware apps; cần sửa trace nguồn khi owner review v2. | Embedded/Build |
| TYP-001, TYP-002, TYP-003, TYP-004, TYP-007, TYP-008, TYP-009 | S1 §05 | KEEP | Giữ fixed-width tại hardware/wire boundary, size_t, checked conversion/arithmetic, initialization và synchronization thật. | Không áp đặt on-wire widths trước contract; không thay kiểu dữ liệu runtime ở R1. | Embedded + Security/QA |
| TYP-005, TYP-006 | S1 §05 | MODIFY | Giữ explicit encoding/range checks; endianness, scaling/unit là versioned contract/config, không lấy fixed-point ví dụ làm requirement cho mọi sensor. | D01/D09/D11 cần được giải trước codec/DB mapping; không freeze wire endian. | Node/MAC + Backend + Security |
| MEM-001, MEM-002, MEM-004, MEM-005, MEM-006, MEM-007, MEM-008, MEM-009, MEM-011, MEM-012 | S1 §06 | KEEP | Giữ bounded/static storage, allocation checks, lifetime và bounds theo source §06; monorepo E/C cùng có ownership constraints. | Không import kích thước pool hoặc queue demo. | Embedded + QA |
| MEM-003, MEM-010 | S1 §06 | MODIFY | Only-once init cần tính cả controlled recovery/teardown; cutoff stack buffer lớn hơn 256 bytes là số demo, thay bằng budget/measurement review. | Không cấm recovery re-init hợp lệ; stack budgets TBD theo board/load evidence. | Embedded + QA |
| MEM-013 | S1 §06 | BLOCKED_PENDING_DECISION | SPI transaction/DMA guidance phải được kiểm lại với exact v6.1, buffer lifetime và target. Source rule không đủ chứng minh DMA/IRAM correctness. | Không duyệt API/DMA alignment bằng source inspection; cần API review/test. | Driver + Embedded |
| ERR-001, ERR-002, ERR-003, ERR-005, ERR-007, ERR-008, ERR-009 | S1 §07 | KEEP | Giữ error propagation, checked returns, bounded timeout/retry và safe logging theo source §07. | Không thay public error API hoặc error codes hợp đồng ở R1. | Embedded + Security/QA |
| ERR-004, ERR-006, ERR-010 | S1 §07 | MODIFY | Phân biệt recoverable input errors với fatal invariants; reset/reconfigure phải qua owner và approved profile. TxDone không chứng minh peer nhận hay actuator thực thi. | Không cấm mọi defensive assert hoặc hứa reset tự thành công; cần failure/HIL evidence. | Embedded + RF + QA |
| RTOS-001, RTOS-002 | S1 §08 | MODIFY | Nâng rõ single radio owner theo monorepo E; mutex đơn thuần không đủ bảo vệ modem state khi nhiều task tự điều khiển. | Giữ một ownership boundary, không import task/core/priority demo. | Gateway + Node |
| RTOS-003, RTOS-004 | S1 §08 | MODIFY | Giữ ISR ngắn, API/context đúng; timer callback context và toàn bộ ISR call/data residency cần xác minh theo config/API v6.1, IRAM_ATTR riêng chưa là proof. | Không chọn timer API hoặc timing guarantee; FW-003 cần HIL. | Embedded + RF |
| RTOS-005, RTOS-006, RTOS-007, RTOS-008, RTOS-009, RTOS-010 | S1 §08 | KEEP | Giữ synchronization thật, finite waits, stack/queue observability, init-before-enable và overflow handling. | Queue capacities/priorities TBD qua stress/HIL, không cố định theo planning. | Embedded + QA |
| RAD-001, RAD-002, RAD-003, RAD-006, RAD-007, RAD-012 | S1 §09 | MODIFY | Giữ SX1276 driver intent và task-context IRQ/state handling, nhưng register addresses/masks/IRQ mapping phải cite đúng Semtech revision và mode. Không sao chép semantic rule chưa thẩm định. | R1 không certify register behavior hoặc import driver; review datasheet/API trong task driver. | Driver + RF/Hardware |
| RAD-004, RAD-005, RAD-008 | S1 §09 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | RegVersion expected silicon, LoRa mode transition, FIFO limit/pointers thuộc driver/hardware acceptance với datasheet revision và board identity. | Code standard giữ nghĩa vụ validate, không tự freeze chip assumptions từ demo. | RF/Hardware + Driver |
| RAD-009, RAD-010, RAD-011 | S1 §09 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | PHY consistency, PA routing, power và antenna phải theo profile/board/legal approval. Không kế thừa mặc định 915 MHz hoặc bench power claim. | D03/G1 chặn RF profile chưa duyệt; đúng antenna/load không tự chứng minh legal TX. | RF/Hardware + Regulatory |
| PRO-001, PRO-003, PRO-005, PRO-010, PRO-011 | S1 §10 | KEEP | Giữ untrusted-input/bounds, explicit bytewise serialization, CRC không phải auth và checked sensor conversion. | Không chọn layout/endian hoặc xem CRC PASS là security. | Node/MAC + Security + Backend |
| PRO-002, PRO-004 | S1 §10 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | Frame fields/CRC16 và Little-Endian là quyết định demo; chuyển trách nhiệm sang approved Radio MAC contract sau D01/D11. | Không tương thích mặc định với future MAC; không production codec trước approval. | Node/MAC + Gateway + Security + Backend |
| PRO-006, PRO-007, PRO-008 | S1 §10 | MODIFY | Validation cần auth/replay trước side effect; payload limit theo approved contract/airtime, không lấy khuyến nghị 51 bytes; seq_num không đủ replay/business identity. | Tính lại wire overhead/ToA; giữ RF dedup khác MQTT dedup. | Node/MAC + Security + RF + Backend |
| PRO-009 | S1 §10 | MODIFY | Giữ shared codec intent nhưng theo existing lora_mac/tdma_common boundaries, không bắt tạo app_protocol demo. | Future C↔Go vectors sau contract freeze, không claim đối xứng bằng tên component. | Gateway + Node + Backend |
| HW-001, HW-002, HW-003, HW-004, HW-005, HW-006, HW-007 | S1 §11 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | GPIO lock, strapping, SPI/UART allocation và peripheral reservations thuộc board-revision spec, không là style chuẩn C đa-board. | Không đổi mapping; chưa có G1 board evidence thì HARDWARE_UNCONFIRMED theo nguồn, không import sáu GPIO demo. | RF/Hardware + Embedded |
| HW-008 | S1 §11 | KEEP | Giữ guard chống tự đổi partition/eFuse/RF settings khi chưa owner yêu cầu. | Không tạo quyền thay hardware/config trong standard. | Hardware + Security |
| HW-009 | S1 §11 | MODIFY | Giữ evidence logging nhưng expected chip ID, board count và phép đo phải theo actual silicon/test plan. | Không dùng RSSI/SNR hoặc register read làm RF certification. | RF + QA |
| DOC-001, DOC-002, DOC-003, DOC-004, DOC-006 | S1 §12 | KEEP | Giữ public API contracts, documentation/behavior consistency, datasheet rationale và change history. | Cần review API/source references khi implementation tồn tại. | Embedded + QA |
| DOC-005 | S1 §12 | MODIFY | Không gộp hardware/RF/timing vào một HARDWARE_VERIFIED hoặc cứng số board; dùng evidence dimensions độc lập và report sample limits theo G. | Không nâng software/build status thành HIL/RF status. | QA + RF |
| QA-001, QA-002 | S1 §13 | MODIFY | Audit naming/format theo monorepo prefixes và exact v6.1 references sau review; không áp demo prefix map. | Không auto-reformat/rename toàn repo. | Embedded + QA |
| QA-003, QA-005, QA-007, QA-008 | S1 §13 | KEEP | Giữ actual build evidence, honest reporting, selected CERT scope và tách compile/hardware proof. | Không tuyên bố Full CERT C compliance; build evidence gắn actual commit/toolchain. | QA + Embedded |
| QA-004 | S1 §13 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | Pin verification kiểm board-revision spec đã duyệt, không so sáu GPIO demo như universal rule. | Không suy QA PASS thành board approval. | RF/Hardware + QA |
| QA-006 | S1 §13 | MODIFY | Mở rộng parser tests sang auth/replay/reset/wrap/negative và golden C↔Go sau D01/D11, ngoài CRC/truncated cases. | Chưa có golden bytes hợp lệ; không tạo giả vectors trong task này. | Node/MAC + Backend + Security/QA |

## Disposition cho phần không có rule ID

| Source | Classification | Rationale / compatibility impact | Review owner |
|---|---|---|---|
| S1 §09.1 demo profile và DEC-04 | REMOVE_FROM_STANDARD | Không mang bảng frequency/power/antenna “an toàn trên bàn” vào normative C standard; profile thử nghiệm có provenance riêng nếu RF owner cho phép sau G1/D03. Không tạo approval RF mới. | RF/Hardware + Regulatory |
| S1 §14 DEC-03/DEC-07 | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | Little-Endian và CRC16 demo không giải security/wire D01/D11. Chỉ contracts được review mới quyết format. | Node/MAC + Security + Backend |
| S1 §14 DEC-06 và QA checklist sáu GPIO | RELOCATE_TO_CONTRACT_OR_HARDWARE_SPEC | Chỉ có hiệu lực với board revision nguồn đã xác nhận; monorepo chưa được thừa nhận board này bằng standard. | Hardware |
| S1 §14 DEC-08, QA checklist role/prefix | MODIFY | Không ép NODE_TX/GATEWAY_RX/PING_PONG single Kconfig choice cho Gateway/Node apps riêng. API-006/DEC-08 trace không khớp ngay trong nguồn; cần owner sửa ở task sau. | Embedded/Build |
| S1 §13.2 CODE_WRITTEN/BUILD_VERIFIED/HARDWARE_VERIFIED | MODIFY | [AGENTS.md](../../../AGENTS.md) có các evidence dimensions độc lập; [gates](../../verification/acceptance-gates.md) cần điều kiện riêng. Không ánh xạ HARDWARE_VERIFIED thành HIL_VERIFIED/RF_VERIFIED tự động. | QA + RF |
| S1 References dùng Espressif stable và Semtech không ghi revision | BLOCKED_PENDING_DECISION | Local standard có nguồn đọc được nhưng API/register correctness chưa được audit với exact v6.1/datasheet revision. Cần versioned primary sources trước v2 approval; không tái phát hành các assertions phần cứng như fact đã kiểm. | Embedded + RF |

## Rule domains cần thêm sau, chưa viết standard

| Domain / nguồn monorepo | Classification | Rationale / compatibility impact | Owner |
|---|---|---|---|
| Correctness > Safety > Reliability > Maintainability > Performance, Issue #60 | ADD_NEW_RULE | Giữ thứ tự owner yêu cầu, không kế thừa thứ tự demo như một approval mới. | Owner + Embedded/QA |
| `embedded instructions` (historical path; absent at current HEAD), [RTM FW-001..004](../../requirements/requirements.md#rtm) | ADD_NEW_RULE | Single radio owner, timer/ISR-context validation, capacity/overflow/lifetime và recovery có đo kiểm; task/core/stack không chốt trong style. | Gateway + Node + QA |
| [Radio MAC §3](../../../contracts/radio-mac/specification.md), [D01/D11](../../../contracts/OPEN_DECISIONS.md) | ADD_NEW_RULE | Security review gate, nonce uniqueness qua reboot, replay window, parser-before-side-effect và cấm production codec trước approved wire/security. Không chọn crypto. | Security + Node/MAC + Gateway |
| [TDMA §§2–3](../../../contracts/radio-mac/tdma-schedule.md), [MQTT semantics §4](../../../contracts/mqtt/semantic-rules.md) | ADD_NEW_RULE | Planner/Executor boundary, shadow/active, local activation, holdover evidence và monotonic state reconciliation; không dùng numeric candidate như guarantee. | Gateway/TDMA + Node + Backend |
| Radio MAC §4 và D03 | ADD_NEW_RULE | Local airtime admission cho mọi TX gồm alarm/retry; RF policy phải approved, không có bench-power exemption. | RF + Gateway + Node |
| [contract verification](../../../contracts/verification.md), gates, AGENTS.md | ADD_NEW_RULE | Claim gắn source/commit/toolchain/board/test artifact; syntax/build/simulation không thay RF/HIL/security, không Full CERT compliance từ subset. | QA + Security + RF |

## Review handoff

Provenance S1 đã có immutable upstream reference và byte match ở R2; không còn yêu cầu archive lại chỉ để giải F-11. Owner vẫn phải review việc áp dụng source rules vào monorepo; không sửa repository thử nghiệm trong Issue này. Embedded xác minh exact ESP-IDF v6.1 APIs/style; RF xác minh silicon/datasheet revision/board. Security giải D01/D11 trước codec; Gateway/Node/Backend review shared boundaries. [Audit R1](ARCHITECTURE_DOCUMENTATION_AUDIT.md) ghi finding và evidence limitations. Không dùng bảng này để thực thi rule v2.0.0 trước task/approval riêng.
