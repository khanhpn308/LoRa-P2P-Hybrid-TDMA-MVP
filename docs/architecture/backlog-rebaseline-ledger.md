# Source-Bound Backlog Rebaseline & Authority Ledger (Issue #199)

**Trạng thái tài liệu:** `OWNER_BOUND_AUDIT_REPORT` / `CANONICAL_REBASELINE`  
**Ngày thực hiện:** 2026-11-06  
**Live main HEAD snapshot:** `270888a076f4234ea3b59f38ef7f1c01e6435c22`  
**Commit cơ sở:** `Merge pull request #198 from khanhpn308/feature/127-g2-integration-review`  
**Mã băm AGENTS.md được xác thực (SHA-256):** `32a991b015bd2815ed55b8bba7bd3b13277003b14f323afb8c5694d047a5942e` (7,142 bytes)  
**Quyền hạn & Phạm vi:** Thực thi theo yêu cầu của Issue #199. Báo cáo này đối chiếu toàn bộ GitHub Issues đang mở ngoài Harness với các quyết định kỹ thuật của Project Owner, ADR, Requirements và các PR đã thực sự merge vào branch `main`. Tuyệt đối không tự ý thiết kế lại kiến trúc, không tự đóng hàng loạt issue, không tự ý sửa đổi binary wire contract hay xóa mã nguồn firmware khi chưa có Issue migration được duyệt.

---

## 1. Nguyên tắc Thẩm quyền & Thứ tự Ưu tiên (Authority Hierarchy)

Mọi đề xuất điều chỉnh backlog, cập nhật Acceptance Criteria (AC), phân loại superseded hoặc lập kế hoạch chuyển đổi kỹ thuật đều phải tuân thủ nghiêm ngặt 5 bậc thẩm quyền:

1. **Owner-Approved Decisions (Quyết định của Owner đã ghi nhận), ADR và Requirements đã phê duyệt trên `main`:**
   - Là căn cứ pháp lý cao nhất cho kiến trúc và yêu cầu hệ thống.
   - Chỉ có giá trị trong phạm vi phiên bản và thời điểm đã được phê duyệt; quyết định mới hơn của Owner có biên bản/commit ghi nhận sẽ thay thế quyết định cũ.
2. **PR đã merge vào chính branch `main` và mã nguồn thực tế tại HEAD của `main`:**
   - Bằng chứng duy nhất xác nhận sự tích hợp chính thức vào repository.
   - Merge vào nhánh phụ/feature/draft **không** đồng nghĩa với merged-to-main.
   - Một PR đã merge hoặc Issue đã đóng **không tự động chứng minh** tính sẵn sàng sản xuất (production-ready), đóng băng G2, hay vượt qua kiểm thử RF/HIL.
3. **Versioned Contracts trên `main` (`contracts/`):**
   - Ràng buộc giao tiếp giữa các hợp phần trong phạm vi trạng thái phê duyệt thực tế (DRAFT, CANDIDATE, APPROVED).
   - Bản tin mang nhãn DRAFT/PROVISIONAL không cấp quyền triển khai production V2 nếu thiếu quyết định đóng băng (G2 freeze). Nếu contract trên `main` xung đột với định hướng của Owner/ADR, phải ghi nhận `CONFLICT/BLOCKED`.
4. **PR đang Open / Draft, Issue đề xuất (PROPOSED), Mockup / Test Scaffolding:**
   - Chỉ là ứng viên để xem xét (Candidates for Review), **tuyệt đối không** được coi là kiến trúc hiện hành hoặc cơ sở để triển khai tiếp theo.
5. **Datasheet chính hãng, Exact SDK (ESP-IDF v6.1), Mã nguồn thực tế, Kết quả đo đạc HIL/RF vật lý:**
   - Thẩm quyền duy nhất cho phần cứng, thanh ghi và giới hạn thời gian thực.
   - Bất kỳ mâu thuẫn nào giữa tài liệu mô tả và phần cứng thực tế đều phải lập Conflict Register và báo cáo `STOP_AND_REPORT`; không áp dụng nguyên tắc suy đoán.

---

## 2. Bảng Quyết định Nguồn Gốc Đã Tích Hợp (Authoritative Decision Ledger)

Bảng dưới đây tổng hợp toàn bộ các quyết định kỹ thuật cốt lõi đã được Project Owner phê duyệt và các PR đã thực sự merge vào branch `main` tính đến commit `270888a`:

| Quyết định / Hợp phần | Issue & PR Merged to Main | Commit Merge SHA & Nguồn file trên Main | Tóm tắt Quyết định Được Duyệt | Trạng thái Thẩm quyền | Cơ quan Kiểm thử / Evidence Owner |
|---|---|---|---|---|---|
| **Multi-Gateway Star C01–C09** | [#115](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/115) / [PR #116](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116) | Commit merge to main; `docs/architecture/system-overview.md`, `docs/requirements/requirements.md`, `docs/adr/0001-hybrid-tdma.md` | Hệ thống Star 1–4 Gateway; kênh BW125 cô lập; Gateway làm TDMA Master cục bộ; Backend lập lịch nhưng không can thiệp thời gian thực RF. | `OWNER_APPROVED` / Architecture Baseline | Backend & Gateway Architecture |
| **Event-Only Static TDMA + Maintenance SF** | [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126) / [PR #133](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/133) | `a5467d498dc359570b8716158376f79fbf931fe6`<br>`docs/architecture/system-overview.md`, `docs/requirements/requirements.md`, `docs/adr/0001-hybrid-tdma.md` | Bãi bỏ hoàn toàn việc truyền telemetry định kỳ trên RF; loại bỏ khe tranh chấp PCSS/CAP; thay bằng khe tĩnh Static DATA slot cho Event và Maintenance Superframe (~300s) cho đồng bộ/sức khỏe. | `OWNER_APPROVED` / Core MAC Paradigm | MAC / TDMA / Firmware (#131, #130) |
| **Presentation Stack Selection** | [#111](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/111) / [PR #112](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/112) | `5f5868ec37d8ca7398593dcbebf27818f755aa30`<br>`docs/architecture/interfaces.md`, `AGENTS.md` | Web sử dụng **Next.js + TypeScript**; Mobile sử dụng **Kotlin native Android**; giao tiếp qua REST/WSS của Backend. Flutter là doc drift cũ, không mở lại lựa chọn. | `OWNER_ACCEPTED` / Presentation Standard | Web & Mobile UI Teams |
| **MQTT 5.0 / Gateway ↔ Backend** | [#14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) / [PR #26](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/26) | Merged to main; `docs/adr/0002-mqtt-5.md` | Sử dụng Mosquitto MQTT 5.0 TLS, QoS1; idempotency dựa trên `event_id` do Gateway gán bền vững; Backend deduplication. | `OWNER_ACCEPTED` / ADR-0002 | Backend Go & MQTT Infra (#174) |
| **ESP-IDF v6.1 Baseline** | ADR-0003 | Merged to main; `docs/adr/0003-esp-idf-v6-1.md`, `firmware/esp-idf-version.txt` | Chuẩn hóa toolchain ESP-IDF v6.1 chính thức cho ESP32-WROOM-32E. Build pass không tương đương RF/HIL timing pass. | `ACCEPTED` / Toolchain Baseline | Firmware & Embedded QA |
| **Theoretical ToA & Guard Budget Model** | [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) / [PR #171](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/171) | `ff5c51aa`<br>`docs/adr/0004-theoretical-timing-guard-budget.md`, `docs/verification/rf-timing-methodology-and-harness.md` | Công cụ tính toán ToA lý thuyết và mô hình ngân sách bảo vệ (guard budget). Xác nhận Guard Time thực tế chuyển giao cho đo đạc vật lý #169. | `OWNER_APPROVED` / Theoretical Baseline | RF / Modeling Team |
| **V2 Post-Join READY & Activation Design** | [#136](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/136) / [PR #168](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/168) | `51157d26`<br>`docs/verification/join-v2-ready-tdma-activation-design.md`, `test-matrix.md` | Thiết kế handshake UP_JOIN_READY (0x49) và giao thức chuyển lịch 3 chu kỳ đếm ngược $3 \to 2 \to 1$. | `OWNER_APPROVED_DESIGN` / Implementation Ready: NO | G2 Integration / Test Team |
| **V2 Event DATA / ACK Specification** | [#177](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/177) / [PR #189](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/189) | `ed3e29c9`<br>`docs/verification/v2-event-ack-compatibility-review.md`, `negative-test-matrix.md` | Phê duyệt `DEC-127-01` (`UP_EVENT` 0x41 26B, `DOWN_EVENT_ACK` 0x42 19B), `DEC-127-02` (CCM tag 8B), `DEC-127-03` (SF7/SF8), `DEC-127-04` (DROP_OLDEST FIFO). | `OWNER_APPROVED_DESIGN` | MAC / Security QA |
| **V2 Maintenance SF & Sync/Health** | [#178](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/178) / [PR #190](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/190) | `7f490154`<br>`docs/verification/v2-maintenance-beacon-health-compatibility.md`, `test-matrix.md` | Phê duyệt `DEC-MH-01` (`DOWN_SYNC_BEACON` 0x43 80B Ed25519), `DEC-MH-02` (`UP_HEALTH_REPLY` 0x44 21B CCM-8); chu kỳ mục tiêu 300s. | `OWNER_APPROVED_DESIGN` | MAC / Gateway Team |
| **V2 Cryptographic Trust & X25519 Session Keys** | [#182](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/182) / [PR #193](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/193) | `949f7d31`<br>`docs/verification/v2-join-session-key-compatibility-decisions.md`, `security-test-matrix.md` | Phê duyệt `DEC-SEC-01` đến `DEC-SEC-07`: Ephemeral X25519 ECDH, Backend Zero-Knowledge, dual-auth READY, INSTALLED_INACTIVE fail-closed, NVS counter. | `OWNER_APPROVED_DESIGN` / G2=NOT_VERIFIED | Crypto / Security Team |
| **V2 MAC Specification & TDMA Integration** | [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127) / [PR #198](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/198) | `270888a0`<br>`contracts/radio-mac/specification.md`, `tdma-schedule.md`, `contracts/OPEN_DECISIONS.md` | Cập nhật Radio MAC Specification v2.0.0-DRAFT và TDMA Schedule v2.0.0-DRAFT; tích hợp mã gói tin V2 (0x41..0x49), loại bỏ V1 candidate và P-10S-15 PCSS. | `OWNER_APPROVED_DESIGN` / Draft Contract Integrated | MAC / TDMA Team |
| **MQTT Session Key Install/ACK V1 Contract** | [#122](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/122) / [PR #123](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/123) | `9ab052e2`<br>`contracts/mqtt/session-key-security.md`, schemas | Hợp đồng cài đặt khóa phiên cho Gateway qua MQTT mTLS; V2 sẽ dùng Session Binding Ticket (#128). | `OWNER_APPROVED_DESIGN` (V1 Historic) | Security / MQTT Team (#173, #174) |
| **PCB HW-001 & SX1276 Pinmap** | [#150](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/150) / [PR #166](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/166) | `481afac5`<br>`docs/verification/pcb-hw001-pinmap.md`, `docs/hardware/sx1276/*` | Khóa cố định pinmap HW-001 cho ESP32 + SX1276 (SCK=18, MISO=19, MOSI=27, NSS=5, DIO0=26, RST=14, Wake=33/39). | `LOCKED_HARDWARE_PINMAP` | Hardware & Embedded Team |
| **Shared Firmware Components Merged** | [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) / [PR #170](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/170); [#179](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/179) / [PR #183](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/183); [#180](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/180) / [PR #184](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/184); [#181](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/181) / [PR #185](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/185) | `20204b9f`, `5a146dc0`, `3f338724`, `be823653`<br>`firmware/components/*` | Tích hợp các module dùng chung: SX1276 non-blocking driver, airtime_policy, lora_mac và tdma_common. | `MERGED_TO_MAIN` / **Mang mã legacy P-10S-15** | Firmware QA / Physical Test (#169) |
| **VN920 Channel Plan Requirement** | [#154](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/154) | Owner-approved requirement | Tuân thủ quy hoạch kênh VN920 (CH00..CH10: 920.250–922.750 MHz, BW125); cấp phát độc quyền Gateway. | `OWNER_APPROVED_REQUIREMENT` | Backend Storage / RF |

---

## 3. Sổ Đăng Ký Xung Đột & Độ Lệch Hệ Thống (Conflict Register & System Drift)

### 3.1. Độ Lệch Tài Liệu Presentation (Presentation Doc Drift — Đã Khắc Phục)
- **Nguồn xung đột:** `docs/architecture/system-overview.md` (dòng 32) trước đây ghi: *"Công nghệ Mobile trong các tài liệu cũ chưa thống nhất (Flutter/Kotlin), cần quyết định riêng trước implementation."*
- **Quyết định có thẩm quyền:** Quyết định Owner #111 / PR #112 (commit `5f5868ec37d8ca7398593dcbebf27818f755aa30`) đã phê duyệt chính thức: **Next.js + TypeScript cho Web** và **Kotlin native Android cho Mobile**, giao tiếp thông qua REST/WSS của Backend. `docs/architecture/interfaces.md` và `AGENTS.md` trên `main` đã ghi nhận đầy đủ.
- **Biện pháp xử lý trong PR này:** Đã chỉnh sửa dòng 32 `docs/architecture/system-overview.md` để đồng bộ hoàn toàn với #111/#112. Mọi tài liệu hoặc Issue nhắc đến Flutter được xác định là doc drift lịch sử và không có giá trị thi hành.

### 3.2. Nợ Tương Thích Triển Khai Firmware (Firmware Implementation Legacy Debt)
- **Hiện trạng trên `main`:**
  - `firmware/components/tdma_common/include/tdma_common.h`: Mã nguồn C đã merge vẫn định nghĩa các hằng số khe tranh chấp của Profile P-10S-15: `TDMA_PCSS_WINDOW_DURATION_MS = 1000`, `TDMA_PCSS_SLOT_DURATION_MS = 250`, `TDMA_PCSS_SLOTS_PER_FRAME = 4`, cùng độ dài khe cố định 400ms.
  - `firmware/components/lora_mac/include/lora_mac.h`: Mã nguồn C hiện thực kiểu khung V1 (`0x01 = DATA`, `0x02 = JOIN_REQUEST`, `0x03 = JOIN_ACCEPT`, `0x04 = PRIORITY_ALERT`) với header 8B chưa mã hóa và kiểm tra CRC-16.
- **Ràng buộc tương thích:** Tuyệt đối không xóa hoặc tự ý viết lại mã nguồn này trong Issue #199. Việc chuyển đổi mã nguồn firmware sang cấu trúc V2 (0x41..0x49 và Static DATA) thuộc phạm vi sở hữu của Issue chuyển đổi **#131** và phải có kết quả đo đạc vật lý từ **#169**.

### 3.3. Độ Lệch Hợp Đồng MQTT & API (MQTT/API Contract Drift)
- **Hiện trạng trên `main`:** `contracts/mqtt/topics.md` vẫn còn chứa các định nghĩa `uplink/telemetry` định kỳ và các trường dữ liệu kinh doanh cũ.
- **Ràng buộc tương thích:** Issue **#128** (`[Migration][G4] Version Event-only MQTT/API schemas`) là đơn vị chịu trách nhiệm phiên bản hóa và đồng bộ hợp đồng MQTT/API theo Event-Only sau khi PR #198 đã tích hợp MAC contract. Các file contract DRAFT trên `main` không tự động trở thành normative V2 nếu chưa hoàn tất G4 review.

### 3.4. Trạng Thái PR Đang Mở Đối Chiếu Với Hợp Đồng Main
- **PR #198 (Đã merge tại HEAD `270888a`):** Đã hoàn tất việc tích hợp Radio MAC Specification v2.0.0-DRAFT và TDMA Schedule v2.0.0-DRAFT vào `contracts/radio-mac/`.
- **PR #124 (Open - cho Issue #12):** Đề xuất tài liệu V1 Bootstrap/Join; là tài liệu ứng viên lịch sử, **không** được merge đè lên hợp đồng V2.
- **PR #134 (Open - cho Issue #129):** Đề xuất cập nhật tài liệu hướng dẫn chuyển đổi firmware; đang chờ review.
- **PR #114 (Open - cho Issue #79):** Nhánh cũ `codex/phong-week2` chứa các giả định onboarding cũ; cần rebaseline theo hồ sơ V2 Join (#136/#182).

---

## 4. Danh Mục Toàn Bộ 42 Issues Mở Ngoài Harness & Ma Trận Thẩm Quyền

Dưới đây là bảng đối chiếu chi tiết 42 Open Issues ngoài Harness trên repository tại thời điểm baseline:

| Issue # | Tiêu Đề | Labels | Trích dẫn AC Cốt Lõi / Tóm tắt Scope | Nguồn Thẩm Quyền & PR Merged | Độ Lệch / Xung Đột Hệ Thống | Đề Xuất Xử Lý (Disposition) | Trạng Thái Phê Duyệt / Gate |
|---|---|---|---|---|---|---|---|
| **#12** | [Contract] Đặc tả Radio MAC v1 an toàn và bộ Golden Test Vectors | layer:mac-tdma, type:contract, ai:human-audit-req, risk:security, wave:1 | Đặc tả Radio MAC v1, cơ chế xác thực/replay, Golden Vectors giải mã mong đợi, đánh giá airtime/guard. | Thay thế bởi PR #198 (V2 MAC Contract); PR #124 đang open. | Mang nội dung V1 candidate cũ; V2 đã có hồ sơ #177/#182 và PR #198. | **KEEP / HISTORICAL RECONCILIATION** (Khép lại hoặc ghi nhận làm V1 baseline, không dùng làm V2 contract) | DRAFT / CONTRACT_GATE |
| **#13** | [MAC] Hiện thực lora_mac, tdma_common và airtime_policy an toàn | layer:fw-gateway, layer:fw-node, layer:mac-tdma, type:feature, wave:2 | Hiện thực 100% Golden Vectors, policy từ chối phát quá hạn ngạch airtime, build pass cả Gateway và Node. | PR #183 (airtime), PR #184 (lora_mac), PR #185 (tdma_common) đã merge to main. | Đã merge một phần mã nguồn khung; còn mang nợ tương thích P-10S-15. | **KEEP / VERIFY** (Duy trì để nghiệm thu integration test thực tế sau khi cập nhật V2) | ACTUAL: PARTIAL_MERGED / HIL_NOT_VERIFIED |
| **#17** | [Sim] Giả lập Gateway MQTT 10–15 Nodes để kiểm thử Backend | layer:mqtt-infra, layer:backend-go, type:test, wave:2 | Outbound event đạt JSON Schema validation; kịch bản 15 nodes có kết quả tái lập; log báo SIMULATOR_PASS, không báo RF_HIL_PASS. | Phụ thuộc hợp đồng Event-only #128; kế thừa ADR-0002. | Cần điều chỉnh fixture giả lập theo Event-only thay vì periodic telemetry. | **KEEP / UPDATE FIXTURES** (Đồng bộ payload với #128 khi #128 merge) | READY_FOR_REVIEW / SIM_PASS_ONLY |
| **#18** | [Backend][Event-only] PostgreSQL migrations, MQTT Event ingest và durable idempotent storage (#125) | layer:backend-go, type:feature, risk:reliability, wave:2 | DB migration chạy trên PostgreSQL thật; deduplication (gateway_id, event_id); RF ACK $\neq$ DB commit. | Căn cứ Quyết định #125/PR #133; tuân thủ Go Standard v2. | Hoàn toàn phù hợp với kiến trúc Event-only trên main. | **KEEP / IMPLEMENT** (Tiếp tục triển khai theo phạm vi backend đã duyệt) | OWNER_APPROVED_DESIGN / UNIMPLEMENTED |
| **#19** | [Backend][Static TDMA] Event-only Schedule Planner, Maintenance SF và schedule lifecycle/API (#125) | layer:mac-tdma, layer:backend-go, type:feature, risk:reliability, wave:2 | Planner tạo lịch Static DATA + Maintenance SF (~300s); vòng đời PROPOSED/STAGED/ACTIVE; Gateway Shadow cutover. | Căn cứ Quyết định #125/PR #133; kế thừa PR #198 (TDMA Schedule). | Cần liên kết chặt với TDMA schedule specification v2.0.0-DRAFT vừa merge trong PR #198. | **KEEP / IMPLEMENT** (Tiến hành theo hợp đồng TDMA mới nhất) | OWNER_APPROVED_DESIGN / UNIMPLEMENTED |
| **#43** | [P1-B2][C03][Security] Siết Host Audit Validator theo exact scope và audit schema (M02) | (Governance) | check_report là Host validator duy nhất; reviewed_scope bằng đúng changed paths; kiểm tra audit schema. | Tương thích quy trình Harness và PR Review Policy PR #142/PR #146. | Thuộc mảng Governance / Security Audit. | **KEEP / VERIFY** (Hoàn thành kiểm thử validator độc lập) | REVIEW_READY |
| **#45** | [P1-B2][C02][Security] Operator-direct AGY Gemini Auditor + credential isolation (H01/H04) | (Governance) | Owner xác nhận entitlement; cách ly credential; snapshot immutable; không lộ secrets. | Phù hợp với Native Fast Lane trong AGENTS.md. | Thuộc mảng Governance / Security Isolation. | **KEEP / VERIFY** (Duy trì ranh giới bảo mật cho Auditor) | REVIEW_READY |
| **#49** | [Docs] Chuẩn hóa Wave Labels, Issue Numbers và Project sync script | type:docs | Gắn nhãn wave:1..wave:4; bỏ tiền tố W1/W2 trên title; script lint project verification. | Đã hoàn tất phần lớn trong các đợt rebaseline trước. | Script verify cần được cập nhật theo danh mục Issue mới sau #199. | **UPDATE / CLOSE_POST_VERIFICATION** (Cập nhật script kiểm tra sau khi chốt #199) | DOCS_READY |
| **#60** | [Docs][Architecture] Architecture & Requirements Baseline Remediation — R1 | (Docs/G0) | Phân loại nguồn bắt buộc; giải quyết thiếu sót tài liệu kiến trúc R1. | Đã có PR #61 và các văn bản R2 kế thừa (#64). | Đã được thay thế bởi các đợt cập nhật Requirements & Overview sau PR #116/#133. | **HISTORICAL / SUPERSEDED** (Giữ làm audit trail lịch sử, không gán active gate) | HISTORICAL_RECORD |
| **#63** | [G0][Review] Requirements & Architecture Technical Review — after PR #61 | (G0/Review) | Review kỹ thuật kiến trúc sau PR #61; xác minh tính nhất quán của G0. | Đã thực hiện qua các checkpoint của Owner trên main. | Các nội dung đánh giá đã được phản ánh trong ADR-0001 và requirements.md. | **HISTORICAL / SUPERSEDED** (Lưu vết quyết định, khép lại sau khi kiểm tra) | HISTORICAL_RECORD |
| **#64** | [G0][Docs] Requirements & ADR-0001 Remediation — R2 | (G0/Docs) | Hoàn thiện Requirements và ADR-0001 phiên bản R2. | Đã được cập nhật trực tiếp trong PR #116 và PR #133 trên main. | Không còn thay đổi mở; main đã chứa requirements.md và ADR-0001 mới nhất. | **HISTORICAL / SUPERSEDED** (Đề xuất đóng vì nội dung đã merge vào main) | MERGED_COVERAGE |
| **#68** | [Firmware][AI] C Coding Standard v2.0.0-DRAFT — Agent-First | (Standards) | Soạn thảo và hoàn thiện C Standard v2 ràng buộc Agent. | Đã được Project Owner phê duyệt áp dụng bắt buộc theo Quyết định #137 (2026-11-04). | Tiêu đề còn nhãn DRAFT nhưng Owner #137 đã xác nhận tính ràng buộc pháp lý. | **KEEP / FORMALIZE** (Cập nhật trạng thái tiêu chuẩn thành binding standard) | OWNER_APPROVED_BINDING |
| **#70** | [Backend][AI] Go Engineering Standard v2.0.0-DRAFT — Google Go Style | (Standards) | Soạn thảo và hoàn thiện Go Standard v2 ràng buộc Agent. | Đã được Project Owner phê duyệt áp dụng bắt buộc theo Quyết định #137 (2026-11-04). | Tương tự #68, tiêu chuẩn đã có hiệu lực thực thi theo quyết định của Owner. | **KEEP / FORMALIZE** (Cập nhật trạng thái tiêu chuẩn thành binding standard) | OWNER_APPROVED_BINDING |
| **#73** | Wave 1 – Foundation | wave:1 | Issue tracker quản lý phạm vi Wave 1. | Quản lý tiến độ lịch sử; chịu tác động của rebaseline 24/10 và 06/11. | Một số Issue con (#12, #77, #78) có thay đổi lớn về bản chất kỹ thuật. | **UPDATE TRACKER** (Điều chỉnh danh mục Issue con theo rebaseline #199) | TRACKER_ONLY |
| **#74** | Wave 2 – AI Core Development | wave:2 | Issue tracker quản lý phạm vi Wave 2. | Chịu tác động bởi việc chuyển giao #13, #17, #18, #19 và các migration issues. | Cần đồng bộ với danh mục V2 migration. | **UPDATE TRACKER** (Cập nhật dependency links) | TRACKER_ONLY |
| **#75** | Wave 3 – System Integration | wave:3 | Issue tracker quản lý Wave 3 (Tích hợp hệ thống). | Phụ thuộc vào kết quả của Wave 1 & 2. | Chưa kích hoạt triển khai diện rộng; cần chờ V2 integration. | **KEEP / TRACKER** (Duy trì cấu trúc mốc phát triển) | FUTURE_PHASE |
| **#76** | Wave 4 – Verification & Pilot | wave:4 | Issue tracker quản lý Wave 4 (Kiểm thử thực địa & Pilot). | Phụ thuộc vào HIL RF timing (#169) và tích hợp hoàn chỉnh. | Chưa kích hoạt; phụ thuộc vào evidence vật lý. | **KEEP / TRACKER** (Duy trì cấu trúc mốc phát triển) | FUTURE_PHASE |
| **#77** | [Design][Edge] Event-Driven Trigger & Optional Periodic Reporting — Architecture Draft | layer:fw-node, layer:mac-tdma, layer:backend-go, type:research, wave:1 | Kiến trúc trigger sự kiện kết hợp truyền telemetry định kỳ tùy chọn; đánh giá tác động pin và airtime. | Bị thay thế hoàn toàn bởi Quyết định #125/PR #133 (Event-only Static TDMA). | **XUNG ĐỘT TRỰC TIẾP:** Đề xuất periodic reporting trái ngược với quyết định cấm truyền định kỳ trên RF của Owner. Phần trigger phần cứng đã có #149; phần FIFO sự kiện đã có #131. | **SUPERSEDE / ĐỀ XUẤT CLOSE AS NOT_PLANNED** (Chứng minh bị #125/#133 thay thế; phạm vi con đã chuyển giao sang #149 và #131) | SUPERSEDED_BY_#125 |
| **#78** | [Design][MAC] Hybrid TDMA Event-Only Mode & Priority Access — Protocol Proposal | layer:fw-gateway, layer:fw-node, layer:mac-tdma, type:research, wave:1 | Đề xuất khe ưu tiên (Priority Access / Contention / PCSS) cho sự kiện khẩn cấp; xử lý va chạm bằng CAD backoff. | Bị thay thế hoàn toàn bởi Quyết định #125/PR #133 và PR #198. | **XUNG ĐỘT TRỰC TIẾP:** Đề xuất khe tranh chấp và backoff va chạm đã bị Owner bãi bỏ; thay thế bằng cơ chế truyền trong khe tĩnh riêng (own static slot) và retry bền vững. | **SUPERSEDE / ĐỀ XUẤT CLOSE AS NOT_PLANNED** (Chứng minh bị #125/#133/#198 thay thế; quy trình slot tĩnh do #127/#131 sở hữu) | SUPERSEDED_BY_#125_#127 |
| **#79** | [Thiết kế][Onboarding] Phát hiện Node → Phê duyệt → Cấp cấu hình → Kích hoạt | layer:fw-gateway, layer:fw-node, layer:backend-go, layer:web-ui, layer:mobile-app, wave:1 | Quy trình 4 bước onboarding Node; có cờ `periodic_enabled` và chu kỳ báo cáo định kỳ. | Kế thừa hồ sơ V2 Join #136/PR #168 và #182/PR #193; PR #114 đang mở. | AC hiện tại còn chứa cờ `periodic_enabled` và giả định cấu hình chu kỳ telemetry trái với #125. | **REBASELINE / REWRITE AC** (Loại bỏ `periodic_enabled`, căn chỉnh theo quy trình V2 Join/READY dual-auth 0x49) | REQUIRES_REBASELINE |
| **#80** | [Design][Mobile Android] Kotlin MVP UI Layouts & Approval Gate — No Code | layer:mobile-app, type:research, wave:1 | Thiết kế layout UI Kotlin native: Dashboard, Node List, Event Log, Approval Gate, nút gạt Periodic ON/OFF. | Khớp với Quyết định #111/PR #112 (chọn Kotlin native); xung đột với #125 về UI định kỳ. | Khẳng định Kotlin native là đúng; tuy nhiên phần giao diện Periodic ON/OFF và chu kỳ gửi tin cần loại bỏ do hệ thống là Event-only. | **REBASELINE / UPDATE AC** (Giữ nguyên kiến trúc Kotlin native; loại bỏ toggle định kỳ; tập trung vào duyệt kích hoạt Node và quản lý sự kiện) | REQUIRES_REBASELINE |
| **#90** | [Thiết kế][Onboarding][Node/Gateway] Phát hiện Node và điều phối Downlink — #79 | layer:fw-gateway, layer:fw-node, type:research, wave:1 | Chi tiết kỹ thuật phía Node/Gateway cho quy trình onboarding #79; xử lý bản tin phát hiện và cấu hình. | Chịu tác động trực tiếp của hồ sơ V2 Join #182/PR #193 và #136/PR #168. | Các định dạng bản tin cũ trong issue này chưa phản ánh bản tin UP_JOIN_HELLO (68B), DOWN_JOIN_GRANT (141B), UP_JOIN_READY (31B). | **REBASELINE / REWRITE AC** (Đồng bộ cấu trúc bản tin với hồ sơ V2 Join đã duyệt DEC-SEC-01..07) | REQUIRES_REBASELINE |
| **#91** | [Thiết kế][Onboarding][Backend] Phê duyệt, cấp cấu hình và kích hoạt Node — #79 | layer:backend-go, layer:web-ui, layer:mobile-app, wave:1 | Backend lưu trữ trạng thái onboarding, sinh cấu hình slot và cấp quyền qua REST API / MQTT. | Kế thừa Issue #135 (Backend Join auth) và #182 (Session key ticket). | Cần đồng bộ loại bỏ việc lưu cấu hình chu kỳ telemetry trong bảng cơ sở dữ liệu `nodes`. | **REBASELINE / REWRITE AC** (Căn chỉnh theo mô hình Session Binding Ticket và xác thực Hello 68B của #135/#182) | REQUIRES_REBASELINE |
| **#97** | [Docs][Firmware] Record owner approval and define ESP32 Skill Gap Analysis review plan | (Firmware/Docs) | Kế hoạch đánh giá năng lực lập trình ESP32; tài liệu read-only theo AGENTS.md. | AGENTS.md xác nhận tài liệu Skill Gap Analysis là READ-ONLY, không tự động kích hoạt bên thứ ba. | Không có xung đột; duy trì quản trị tài liệu. | **KEEP / DOCUMENTATION_GOVERNANCE** | DOCS_ONLY |
| **#102** | [Firmware][Docs] Build indexed ESP32 + SX1276 engineering playbook from five selected skills | (Firmware/Docs) | Xây dựng sổ tay kỹ thuật lập trình ESP32 + SX1276 dựa trên 5 skill đã chọn. | Đã tích hợp các tài liệu tham khảo SX1276 trong PR #157/#167 và routing trong PR #160. | Cần đảm bảo tài liệu tuân thủ C Standard v2 và không vi phạm quy tắc Hot Context. | **KEEP / IMPLEMENT** (Hoàn thiện tài liệu theo phạm vi tham chiếu driver SX1276 đã khóa) | DOCS_PENDING |
| **#106** | docs(adr): fix retired embedded-instructions link and C Standard v2 draft status | (Docs/ADR) | Sửa liên kết tài liệu cũ trong ADR; cập nhật trạng thái C Standard v2. | PR #107 đang mở để xử lý issue này. | Đang chờ review PR #107. | **KEEP / REVIEW_PR_107** (Xem xét và merge PR #107 khi đạt chất lượng) | PR_OPEN (#107) |
| **#108** | docs(firmware): owner-approve and freeze five Hot/Cold firmware documents | (Firmware/Docs) | Owner phê duyệt và đóng băng 5 tài liệu firmware Hot/Cold. | Liên quan mật thiết đến cấu trúc tài liệu tham chiếu SX1276 tại `docs/hardware/sx1276/`. | Chờ quyết định phê duyệt chính thức của Owner đối với toàn bộ bộ tài liệu. | **KEEP / AWAIT_OWNER_FREEZE** (Duy trì trạng thái chờ Owner đóng băng) | PENDING_OWNER_ACTION |
| **#117** | [Contracts] Đồng bộ Radio MAC, TDMA, MQTT, API với kiến trúc C01–C08 | (Contracts) | Cập nhật toàn diện các hợp đồng theo kiến trúc đa Gateway C01–C08. | Phần lớn đã được thực hiện qua PR #123 (MQTT keys), PR #133 (Event-only), và PR #198 (MAC V2). | Không tự ý tạo ra quy định mới về tranh chấp C08; lấy hợp đồng vừa merge trên main làm chuẩn. | **REBASELINE / REWRITE AC** (Thu hẹp phạm vi vào việc rà soát tính nhất quán giữa các hợp đồng đã merge trên main) | REQUIRES_REBASELINE |
| **#125** | [Migration][G0/G2/G4] Replace periodic telemetry/alert contention with Event-Only Static TDMA + Maintenance SF | (Migration/Epic) | Issue Epic điều phối toàn bộ chiến dịch chuyển đổi sang Event-Only Static TDMA và Maintenance Superframe. | PR #133 đã merge phần kiến trúc và requirements; các issue con (#127..#132) đang xử lý từng lớp. | Là gốc thẩm quyền cho toàn bộ đợt chuyển đổi kiến trúc 04/11. | **KEEP / EPIC_TRACKER** (Duy trì làm Epic quản lý tiến độ chuyển đổi, đóng khi các issue con hoàn tất) | OWNER_APPROVED_EPIC |
| **#127** | [Migration][G2] Version Event ACK, Health and Maintenance SF compatibility (#125) | (Migration/G2) | Phiên bản hóa hợp đồng Radio MAC: Event DATA/ACK, Health, Maintenance SF; cập nhật specification và tdma-schedule. | **PR #198 ĐÃ MERGE VÀO MAIN** (commit `270888a076f4234ea3b59f38ef7f1c01e6435c22`). | Hợp đồng đã được merge vào main. Issue vẫn đang mở trên GitHub do PR không chứa từ khóa auto-close. | **VERIFY_COMPLETION / PROPOSE_CLOSE** (Xác nhận PR #198 đã hoàn thành mục tiêu hợp đồng G2 của #127; chuẩn bị đóng sau kiểm tra) | ACTUAL: MERGED_IN_PR_198 |
| **#128** | [Migration][G4] Version Event-only MQTT/API schemas, examples and contract checks (#125) | (Migration/G4) | Cập nhật hợp đồng MQTT và REST/WSS: loại bỏ telemetry, thêm Event ingest, session binding ticket và schema checks. | Kế thừa trực tiếp hợp đồng MAC vừa merge từ PR #198 (#127). | Là chủ sở hữu duy nhất cho việc sửa đổi `contracts/mqtt/` và `contracts/api/` theo Event-Only. | **KEEP / ACTIVE_OWNER** (Tiến hành triển khai hợp đồng MQTT/API V2 ngay sau khi PR #198 đã merge) | READY_FOR_IMPLEMENTATION |
| **#129** | [Migration][Docs] Supersede legacy firmware guidance and implementation roadmaps (#125) | (Migration/Docs) | Đính chính các tài liệu hướng dẫn lập trình firmware cũ trái với Event-Only. | PR #134 đang mở trên branch `docs/129-event-only-guidance`. | Đang chờ nghiệm thu PR #134. | **KEEP / REVIEW_PR_134** (Thực hiện nghiệm thu PR #134 theo Native Fast Lane) | PR_OPEN (#134) |
| **#130** | [Migration][Sim/QA] Verify Static DATA and Maintenance timelines and Event replay (#125) | (Migration/QA) | Kiểm thử kịch bản Static DATA và Maintenance trên bộ mô phỏng; kiểm tra replay, drop, và retry. | Phụ thuộc vào hợp đồng MAC #127/PR #198 và MQTT #128. | Cần kiểm thử toàn diện trên mô hình phần mềm trước khi tiến hành trên phần cứng thật. | **KEEP / AWAIT_DEPENDENCY** (Triển khai song song với Backend #18/#19) | PENDING_CONTRACT_G4 |
| **#131** | [Migration][Firmware] Persistent Event queue, own-slot ACK retry and Maintenance execution (#125) | (Migration/Firmware) | Hiện thực hàng đợi sự kiện NVS FIFO, retry trong slot tĩnh riêng, và thực thi Maintenance trên firmware. | Kế thừa mã nguồn components đã merge (#183, #184, #185) và pinmap #150/PR #166. | **Chủ sở hữu giải quyết nợ tương thích:** Cập nhật `tdma_common` (bỏ PCSS) và `lora_mac` (lên V2 wire) trong firmware thật. | **KEEP / ACTIVE_FIRMWARE_MIGRATION** (Là đơn vị thực thi sửa mã nguồn firmware legacy debt trên main) | BLOCKED_ON_#169_HIL_MEASUREMENT |
| **#132** | [Migration][Backend] Event-only ingest, durable dedup and approved Maintenance planning (#125) | (Migration/Backend) | Hiện thực Backend tiếp nhận Event, chống trùng bền vững theo (gateway_id, event_id), và quản lý lịch Maintenance. | Kế thừa Issue #18 và #19. | Đảm bảo tính nhất quán giữa module Storage và Planner của Backend Go. | **KEEP / COORDINATE** (Điều phối chung cho hai nhánh thực thi chi tiết #18 và #19) | READY_FOR_IMPLEMENTATION |
| **#135** | [GO][V2 Join] Authenticate UP_JOIN_HELLO 68B with HMAC, anti-replay and durable PostgreSQL idempotency | (Backend/Security) | Hiện thực module Backend xác thực bản tin UP_JOIN_HELLO 68B bằng HMAC, kiểm tra replay và lưu trữ idempotency. | Căn cứ Quyết định phê duyệt thiết kế DEC-SEC-01..07 trong hồ sơ #182/PR #193. | Cần tuân thủ phạm vi allowed paths: `backend-go/internal/domain/`, `storage/`, `mqtt/`. | **KEEP / IMPLEMENT** (Triển khai logic xác thực phía Backend theo format 68B đã duyệt) | OWNER_APPROVED_DESIGN / READY |
| **#149** | [Firmware][Node] Button Wake-up, Debounce and Event Trigger | layer:fw-node, type:feature, ai:human-audit-req, risk:reliability, flag:needs-hil-test, wave:2 | Hiện thực thức dậy từ Deep-sleep bằng nút bấm GPIO (HW-001 pin 33/39), chống rung phần cứng, đẩy 1 event vào hàng đợi. | Căn cứ Pinmap HW-001 trong PR #166; mã nguồn SX1276 driver PR #170. | Cần thực hiện kiểm thử trên phần cứng thật (HIL); không thay đổi ranh giới RF. | **KEEP / IMPLEMENT** (Thực hiện logic ngắt nút bấm và Deep-sleep trên Node) | READY_FOR_IMPLEMENTATION / NEEDS_HIL |
| **#154** | [Backend][RF] PostgreSQL VN920 channel registry and exclusive Gateway allocation | layer:backend-go, type:feature, risk:reliability, wave:2 | Migration DB khởi tạo bảng kênh CH00..CH10 (920.250–922.750 MHz); phân bổ độc quyền kênh cho Gateway; kiểm tra tranh chấp. | Quyết định Owner phê duyệt yêu cầu kỹ thuật VN920. | Ràng buộc: Không tự cấp quyền phát xạ RF thực tế; chỉ là bảng dữ liệu phân bổ của Backend. | **KEEP / IMPLEMENT** (Hiện thực bảng cơ sở dữ liệu và API phân bổ kênh) | OWNER_APPROVED_REQUIREMENT / READY |
| **#169** | [RF][HIL] Đo timing thực tế trên ESP32–SX1276 và xác nhận Guard Time từ dữ liệu | layer:hw-rf, layer:mac-tdma, type:research, flag:needs-hil-test, wave:1 | Đo đạc vật lý trên bàn thử nghiệm ESP32 + SX1276; ghi nhận ToA thực tế, RX↔TX turnaround, jitter; đề xuất Guard Time từ số liệu. | Kế thừa công cụ tính toán và harness từ Issue #11 / PR #171. | **CHẶN QUAN TRỌNG:** Chưa có số liệu đo đạc thực tế thì mọi mốc Guard Time, 400ms slot hay G1/G3 gate đều là `NOT_VERIFIED`. | **KEEP / CRITICAL_PHYSICAL_GATE** (Điểm chốt vật lý bắt buộc do kỹ sư phần cứng thực hiện trên thiết bị thật) | PENDING_PHYSICAL_BENCH_EXECUTION |
| **#173** | [Security][Contract Test] Verify MQTT Session Key AES-GCM/HMAC Golden Vectors across Go and ESP-IDF mbedTLS | ai:human-audit-req, risk:security | Kiểm thử tương thích mật mã chéo giữa Go (crypto/cipher) và ESP32 (mbedTLS) cho các vector AES-256-GCM và HMAC-SHA256 của khóa phiên. | Xuất phát từ hợp đồng PR #123 và hồ sơ DEC-SEC-01..07 (PR #193). | Bắt buộc kiểm thử byte-exact thực tế, không dùng giả lập Python để kết luận pass. | **KEEP / VERIFY** (Thực hiện bộ test vectors tương thích chéo hai ngôn ngữ) | READY_FOR_VERIFICATION |
| **#174** | [Integration][MQTT] Runtime Session Key Install/ACK over Mosquitto mTLS and per-Gateway ACL | layer:mqtt-infra, ai:human-audit-req, risk:security | Kiểm thử tích hợp runtime: cài đặt khóa phiên qua broker Mosquitto mTLS thật; kiểm tra ACL 2 lớp (TLS CN + MQTT topic). | Xuất phát từ hợp đồng PR #123 và ADR-0002. | Yêu cầu kiểm thử với broker thật và cấu hình mTLS hoàn chỉnh. | **KEEP / VERIFY** (Tiến hành test tích hợp hạ tầng MQTT với TLS mTLS) | READY_FOR_VERIFICATION |
| **#175** | [Firmware][HIL][Security] Verify Gateway NVS INSTALLED_INACTIVE key-slot atomicity under power-loss injection | layer:hw-rf, ai:human-audit-req, risk:security, flag:needs-hil-test | Kiểm thử tính nguyên tử khi lưu khóa vào NVS flash trên Gateway thật dưới điều kiện mất nguồn đột ngột / sụt áp (fault injection). | Căn cứ nguyên tắc fail-closed DEC-SEC-05 và DEC-SEC-06 trong PR #193. | Cần thiết bị ngắt nguồn lập trình được và board Gateway thật; không thay thế bằng phần mềm. | **KEEP / CRITICAL_SECURITY_HIL** (Cổng kiểm thử an ninh phần cứng bắt buộc trước khi cấp quyền vận hành phiên) | PENDING_HIL_FAULT_INJECTION |

---

## 5. Đề Xuất Xử Lý Kỹ Thuật Chi Tiết Cho Từng Nhóm Issue (Owner Disposition Dossier)

### 5.1. Nhóm Đề Xuất Hủy / Đóng Vì Đã Bị Thay Thế (SUPERSEDE / CLOSE_AS_NOT_PLANNED)

Tuyệt đối không đóng âm thầm hoặc xóa issue; dưới đây là lập luận chi tiết và nội dung comment đề xuất gửi tới Project Owner để phê duyệt trước khi đóng:

#### Issue #77: `[Design][Edge] Event-Driven Trigger & Optional Periodic Reporting — Architecture Draft`
- **Lý do thay thế:** Quyết định Owner #125 và PR #133 (commit `a5467d498dc`) đã phê duyệt chính thức loại bỏ hoàn toàn việc phát sóng telemetry định kỳ trên RF ("Zero Periodic Telemetry RF TX"). Khái niệm "Optional Periodic Reporting" trong #77 trực tiếp vi phạm nguyên tắc tiết kiệm năng lượng và airtime của mạng MVP.
- **Phần kế thừa hợp lệ:** Cơ chế ngắt nút bấm vật lý (Edge Trigger) đã được tách thành **Issue #149** (`[Firmware][Node] Button Wake-up, Debounce and Event Trigger`); cơ chế quản lý hàng đợi Event FIFO bền vững đã được giao cho **Issue #131**.
- **Dự thảo comment trước khi đóng:**
  > *"Issue #77 được đề xuất đóng lại dưới dạng `not_planned` theo kết quả rà soát Source-Bound Rebaseline (Issue #199). Khái niệm truyền định kỳ tùy chọn (Periodic Reporting) đã bị bãi bỏ chính thức theo Quyết định Owner #125 và PR #133 đã merge vào main (kiến trúc Event-Only Static TDMA). Các phần giá trị kỹ thuật còn lại đã được kế thừa trọn vẹn: logic đánh thức phần cứng và chống rung nút bấm chuyển giao cho Issue #149; hàng đợi sự kiện NVS FIFO và quản lý bộ đếm chuyển giao cho Issue #131. Lịch sử thảo luận tại #77 được lưu giữ nguyên vẹn phục vụ truy vết."*

#### Issue #78: `[Design][MAC] Hybrid TDMA Event-Only Mode & Priority Access — Protocol Proposal`
- **Lý do thay thế:** Cơ chế truy cập ưu tiên (Priority Access / Contention / PCSS Window / CAD backoff) đề xuất trong #78 đã bị loại bỏ hoàn toàn bởi Quyết định Owner #125 và PR #198 (commit `270888a0`). Kiến trúc V2 quy định 100% bản tin sự kiện của Node chỉ được truyền trong khe tĩnh riêng biệt được phân bổ trước (own static slot) và nhận phản hồi tức thì (`DOWN_EVENT_ACK`) trong cùng khe đó, loại bỏ hoàn toàn va chạm RF và cạnh tranh khe.
- **Phần kế thừa hợp lệ:** Toàn bộ đặc tả khe tĩnh và chu kỳ bảo trì đã được chuẩn hóa trong `contracts/radio-mac/tdma-schedule.md` (v2.0.0-DRAFT) thông qua PR #198 (sở hữu bởi Issue #127). Logic truyền và retry trong khe tĩnh phía firmware được giao cho **Issue #131**.
- **Dự thảo comment trước khi đóng:**
  > *"Issue #78 được đề xuất đóng lại dưới dạng `not_planned` theo kết quả rà soát Source-Bound Rebaseline (Issue #199). Mô hình tranh chấp khe (Priority Contention / CAD backoff) đã bị bãi bỏ bởi Quyết định Owner #125 / PR #133 và hợp đồng Radio MAC V2 đã merge trong PR #198. Hệ thống áp dụng hoàn toàn khe tĩnh Static DATA slot riêng cho từng Node, triệt tiêu nguy cơ xung đột trên không gian vô tuyến. Quy trình truyền nhận sự kiện được chuẩn hóa tại Issue #127 (PR #198) và hiện thực firmware tại Issue #131."*

---

### 5.2. Nhóm Cần Tái Thiết Lập Tiêu Chí Chấp Nhận (REBASELINE / REWRITE AC)

Các issue này có mục tiêu giá trị nhưng tiêu chí chấp nhận ban đầu còn mang tàn dư của kiến trúc cũ (telemetry định kỳ, Flutter, khe PCSS). Cần điều chỉnh AC theo các nguồn đã merge trên `main`:

#### Issue #79: `[Thiết kế][Onboarding] Phát hiện Node → Phê duyệt → Cấp cấu hình → Kích hoạt`
- **AC cũ cần loại bỏ:** Mọi quy định về `periodic_enabled`, cấu hình khoảng thời gian gửi tin định kỳ (`telemetry_interval`), và cơ chế cấp phát khe tranh chấp.
- **AC mới đề xuất:**
  1. Quy trình onboarding tuân thủ nghiêm ngặt mô hình 4 bước gắn với hồ sơ bảo mật V2 Join (DEC-SEC-01..07): Phát hiện qua `UP_JOIN_HELLO` (0x45, 68B) $\to$ Gateway chuyển tiếp MQTT $\to$ Phê duyệt Backend $\to$ Cấp `DOWN_JOIN_GRANT` (0x46, 141B) $\to$ Kích hoạt bằng `UP_JOIN_READY` (0x49, 31B).
  2. Bỏ hoàn toàn cấu hình chu kỳ báo cáo định kỳ; cấu hình bàn giao cho Node chỉ bao gồm: Node ID, Network ID, Static DATA Slot index trong Superframe, và thông số Maintenance SF (~300s).
  3. Cập nhật nhánh PR #114 hoặc đóng PR #114 để mở PR mới bám sát hồ sơ thiết kế PR #168 và PR #193 đã merge.

#### Issue #80: `[Design][Mobile Android] Kotlin MVP UI Layouts & Approval Gate — No Code`
- **AC cũ cần điều chỉnh:** Loại bỏ màn hình/toggle bật tắt báo cáo định kỳ ("Periodic Telemetry ON/OFF") và trường nhập chu kỳ phát sóng.
- **AC mới đề xuất:**
  1. Khẳng định công nghệ thực hiện duy nhất là **Kotlin native Android**, kết nối Backend qua REST/WSS an toàn (theo Quyết định #111 / PR #112).
  2. Thiết kế giao diện tập trung vào 4 luồng nghiệp vụ cốt lõi: (a) Dashboard trạng thái Gateway/Node (online/offline/holdover dựa trên kết quả Maintenance SF); (b) Hàng đợi phê duyệt kích hoạt Node mới (Node Onboarding Approval Gate); (c) Nhật ký sự kiện thời gian thực (Real-time Event Feed từ WebSocket) và nút xác nhận cảnh báo của người vận hành (Operator Alert Acknowledgement); (d) Trực quan hóa sơ đồ phân bổ khe tĩnh (Static TDMA Slot Map viewer).
  3. Không thiết kế bất kỳ chức năng nào liên quan đến Flutter hoặc cấu hình chu kỳ telemetry RF.

#### Issue #90 & #91: `Onboarding Node/Gateway Downlink Coordination & Backend Provisioning`
- **AC điều chỉnh:**
  - Loại bỏ các trường định dạng bản tin cũ; áp dụng 100% cấu trúc bản tin đã được Owner phê duyệt:
    - Hello: 68 byte (Ed25519 Ephemeral Key $PK_{\text{Node}}$ + Random Nonce + Join Counter).
    - Grant: 141 byte (Chữ ký Ed25519 Gateway + Session Key $K_{\text{SESSION}}$ mã hóa AES-KeyWrap).
    - Ready: 31 byte (Mang thẻ xác thực kép `GW_READY_TAG` 8B và `BACKEND_READY_PROOF` 16B).
  - Phía Backend (#91): Triển khai lưu trữ bền vững trạng thái cấp phép trong PostgreSQL theo cơ chế Session Binding Ticket (DEC-SEC-02), không lưu các cờ định kỳ.

#### Issue #117: `[Contracts] Đồng bộ Radio MAC, TDMA, MQTT, API với kiến trúc C01–C08`
- **AC điều chỉnh:** Không tạo thêm đề xuất kiến trúc mới. Nhiệm vụ chuyển thành: Rà soát và kiểm tra tính nhất quán giữa các hợp đồng vừa merge trên `main`:
  1. Kiểm tra đối chiếu mã byte và trường dữ liệu giữa `contracts/radio-mac/specification.md` (PR #198) với `contracts/mqtt/` (chuẩn bị cập nhật qua #128).
  2. Xác minh tính toàn vẹn của mô hình chuyển lịch 3 nhịp $3 \to 2 \to 1$ qua ranh giới MQTT và TDMA schedule.

---

### 5.3. Nhóm Issue Thực Thi & Kiểm Thử Cần Tiếp Tục Giữ Nguyên (KEEP / VERIFY)

Các Issue sau đây hoàn toàn phù hợp với kiến trúc trên `main`, đang giữ vai trò chủ chốt trong lộ trình thực hiện và cần được bảo vệ:

1. **#169: `[RF][HIL] Đo timing thực tế trên ESP32–SX1276 và xác nhận Guard Time từ dữ liệu`**
   - **Tầm quan trọng:** Là **chốt chặn vật lý duy nhất** để chuyển đổi từ mô hình lý thuyết (Issue #11) sang thông số sản xuất. Không một thay đổi nào về độ dài khe TDMA (hiện đang tạm tính 400ms) hay đóng băng G1/G3 được phép tự kết luận PASS nếu thiếu số liệu đo đạc thực tế từ bench test #169.
2. **#131: `[Migration][Firmware] Persistent Event queue, own-slot ACK retry and Maintenance execution`**
   - **Tầm quan trọng:** Là đơn vị thực thi trực tiếp việc giải quyết nợ kỹ thuật (Legacy Debt) trong mã nguồn firmware: nâng cấp `tdma_common` (xóa bỏ tàn dư PCSS window) và `lora_mac` (chuyển đổi từ framing V1 0x01..0x04 sang framing V2 0x41..0x49).
3. **#128: `[Migration][G4] Version Event-only MQTT/API schemas, examples and contract checks`**
   - **Tầm quan trọng:** Đơn vị cập nhật chính thức các hợp đồng giao tiếp MQTT và API sau khi hợp đồng MAC V2 đã merge trong PR #198.
4. **#18, #19, #132, #135, #154:** Các Issue backend Go đã có kiến trúc rõ ràng, allowed paths cô lập và sẵn sàng triển khai mã nguồn hoặc kiểm thử tích hợp.
5. **#149: `[Firmware][Node] Button Wake-up, Debounce and Event Trigger`:** Hiện thực ngắt nút bấm vật lý trên phần cứng thật HW-001.
6. **#173, #174, #175:** Các bài kiểm tra an ninh và kiểm thử HIL bơm lỗi nguồn điện để xác thực tính nguyên tử của flash NVS và mật mã học.

---

## 6. Lộ Trình Xóa Nợ Tương Thích Firmware (Firmware Debt Transition Plan)

Mã nguồn C trên `main` hiện đang có sự sai lệch giữa hợp đồng thiết kế V2 và hiện thực thực tế:

```
[contracts/radio-mac/ (PR #198 Merged)]          [firmware/components/ on main]
-----------------------------------------          -------------------------------------
UP_EVENT (0x41) / DOWN_EVENT_ACK (0x42)     vs     LORA_MAC_FRAME_TYPE_DATA (0x01)
Static DATA Slot only (No Contention)       vs     TDMA_PCSS_WINDOW_DURATION_MS (1000ms)
DOWN_SYNC_BEACON (0x43) / HEALTH_REPLY (0x44) vs   LORA_MAC_FRAME_TYPE_PRIORITY_ALERT (0x04)
AES-128-CCM-8 Authenticated Payload         vs     Unauthenticated 8B Header + CRC-16
```

### Kế hoạch chuyển đổi có kiểm soát:
1. **Giai đoạn 1 (Hiện tại - Issue #199):** Ghi nhận đầy đủ hiện trạng nợ tương thích vào Authority Ledger; không sửa mã nguồn C để tránh phá vỡ các bài unit test hiện hành (`test_lora_mac_framing.c`, `test_tdma_common.c`).
2. **Giai đoạn 2 (Issue #169 HIL Timing & Bench Data):** Đo đạc thời gian thực thi thực tế của hàm tính toán ToA và trễ ngắt SX1276 trên phần cứng ESP32 thật để xác định xem khe 400ms có cần nới rộng/thu hẹp.
3. **Giai đoạn 3 (Issue #131 Scoped Firmware Refactor):** 
   - Tạo branch riêng `feature/131-firmware-v2-migration` từ `main`.
   - Cập nhật `tdma_common.h`: Xóa bỏ các hằng số PCSS, tái cấu trúc bảng slot theo Static DATA + Maintenance SF.
   - Cập nhật `lora_mac.h`: Cập nhật mã bản tin V2 (0x41..0x49), tích hợp hàm đóng gói mbedTLS AES-128-CCM-8.
   - Chạy bộ kiểm thử giả lập ESP-IDF v6.1 và kiểm thử vật lý xác nhận trước khi mở PR.

---

## 7. Báo Cáo Cổng Chất Lượng & Bằng Chứng Khách Quan (Quality Gates & Evidence Audit)

Tuân thủ nghiêm ngặt nguyên tắc: **Chỉ ghi nhận bằng chứng đo đạc thực tế; mọi cổng chưa đo đều là `NOT_VERIFIED`**:

| Cổng Kiểm Tra / Verification Gate | Trạng Thái Đánh Giá | Bằng Chứng Thực Tế / Ghi Nhận Khách Quan |
|---|---|---|
| **G0: Thẩm Quyền Tài Liệu & AGENTS.md** | **PASS** | Script `agent_context.py` chạy thành công tại HEAD `270888a`; hash AGENTS.md khớp 100% (`32a991b0...`); thứ tự thẩm quyền được tuân thủ. |
| **G1: Ngân Sách Thời Gian & Airtime Lý Thuyết** | **PASS (Theoretical)** | Đã nghiệm thu công cụ tính toán và mô hình lý thuyết trong PR #171 (Issue #11). |
| **G2: Đóng Băng Thiết Kế & Hợp Đồng Wire V2** | **PASS (Design Contracts)** | PR #198 đã merge Radio MAC specification v2.0.0-DRAFT và TDMA schedule v2.0.0-DRAFT vào `main`. Wire codepoints 0x41..0x49 và crypto DEC-SEC-01..07 đã đóng băng thiết kế. |
| **G3: Đo Đạc HIL Timing Vật Lý Trên Sóng** | **NOT_VERIFIED / BLOCKED** | Phụ thuộc hoàn toàn vào kết quả chạy thiết bị thật từ Issue #169. Chưa có bench test thực tế, tuyệt đối không tự tuyên bố PASS. |
| **G4: Hợp Đồng Tích Hợp MQTT & Backend API** | **IN_PROGRESS / PENDING** | PR #123 đã merge Session Keys V1; Issue #128 đang giữ quyền cập nhật schemas V2 sau khi PR #198 hoàn tất. |
| **G5: Kiểm Thử Tích Hợp Hệ Thống & Bảo Mật NVS** | **NOT_VERIFIED** | Phụ thuộc vào kết quả fault-injection trên Gateway thật của Issue #175 và kiểm thử tương thích mật mã Go↔mbedTLS của #173. |
| **G6: Thử Nghiệm Thực Địa (RF Field Pilot)** | **NOT_VERIFIED** | Chưa triển khai thực địa; chỉ thực hiện khi toàn bộ Wave 1–3 hoàn tất. |

---

## 8. Kết Luận & Định Nghĩa Hoàn Thành (Definition of Done)

1. **Toàn bộ 42 Open Issues ngoài Harness** đã được đối chiếu chi tiết với các quyết định kỹ thuật của Owner và các PR đã merge vào `main` tại commit `270888a`.
2. Bảng **Source of Truth / Decision Ledger** và **Conflict Register** đã được thiết lập minh bạch, khẳng định nguyên tắc bất biến: **Không merge vào main = Không dùng làm hợp đồng chính thức**.
3. Độ lệch tài liệu về công nghệ Mobile (**Flutter vs Kotlin native**) tại `docs/architecture/system-overview.md` đã được xử lý triệt để dựa trên Quyết định Owner #111 / PR #112.
4. Nợ tương thích mã nguồn firmware (`tdma_common` PCSS và `lora_mac` V1) đã được cách ly an toàn, phân định rõ quyền sở hữu chuyển đổi cho Issue #131 và kiểm thử vật lý #169, không xóa hoặc phá vỡ mã nguồn hiện có.
5. Các Issue chứa AC định kỳ (#77, #78) đã có hồ sơ đề xuất hủy rõ ràng kèm successor mapping; các Issue onboarding (#79, #80, #90, #91, #117) đã có phương án cập nhật AC bám sát hồ sơ V2 Join đã duyệt.

*Tài liệu này đóng vai trò là cơ sở pháp lý và kỹ thuật duy nhất để Project Owner và đội ngũ phát triển điều phối các nhánh công việc tiếp theo trong kho mã nguồn.*
