# Source-Bound Backlog Rebaseline & Authority Ledger (Issue #199)

**Trạng thái tài liệu:** `OWNER_BOUND_AUDIT_REPORT` / `CANONICAL_REBASELINE`  
**Ngày thực hiện:** 2026-11-06 (Remediated)  
**Live main HEAD snapshot:** `270888a076f4234ea3b59f38ef7f1c01e6435c22`  
**Commit cơ sở:** `Merge pull request #198 from khanhpn308/feature/127-g2-integration-review`  
**Mã băm AGENTS.md được xác thực (SHA-256):** `32a991b015bd2815ed55b8bba7bd3b13277003b14f323afb8c5694d047a5942e` (7,142 bytes)  
**Quyền hạn & Phạm vi:** Thực thi theo yêu cầu của Issue #199 và yêu cầu remediation. Báo cáo này đối chiếu toàn bộ các GitHub Issues đang mở ngoài Harness với các quyết định kỹ thuật của Project Owner, ADR, Requirements và các PR đã thực sự merge vào branch `main`. Tuyệt đối không tự ý thiết kế lại kiến trúc, không tự đóng hàng loạt issue, không tự ý sửa đổi binary wire contract hay xóa mã nguồn firmware khi chưa có Issue migration được duyệt.

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

### Phân định Ranh giới Thuật ngữ & Trạng thái Kỹ thuật
Để tránh hiểu nhầm và đảm bảo tính trung thực tuyệt đối của hồ sơ kỹ thuật:
- **`OWNER_APPROVED_DESIGN`**: Quyết định hoặc định hướng thiết kế đã được Project Owner chính thức thông qua (qua comment Issue, commit ADR, hoặc Requirements). Định hướng này là kim chỉ nam để xây dựng hợp đồng và triển khai, nhưng **chưa đồng nghĩa với mã nguồn đã hoàn thành hay Gate đã đạt**.
- **`MERGED_IMPLEMENTATION`**: Các đoạn mã nguồn, module hoặc cấu hình đã thực sự merge vào branch `main`. Cần lưu ý các module merge ở giai đoạn khởi đầu có thể mang nợ kỹ thuật (legacy debt) so với thiết kế mới nhất.
- **`DRAFT_CONTRACT`**: Các văn bản giao tả giao diện nằm trong thư mục `contracts/` nhưng mang nhãn DRAFT (như `contracts/radio-mac/specification.md` v0.2.0-draft). Đây là hợp đồng đang trong quá trình tích hợp, chưa đóng băng test vectors và **chưa phải là production contract**.
- **`NOT_VERIFIED`**: Mọi cổng nghiệm thu (Gate G0–G6), tính năng hoặc chỉ số kỹ thuật chưa được chứng minh bằng bằng chứng thực nghiệm khách quan (log đo thực tế, biên bản kiểm thử, phê duyệt văn bản). Không chấp nhận giả lập hoặc dự đoán của AI làm bằng chứng thay thế.
- **`BLOCKED`**: Trạng thái của một hạng mục kỹ thuật bị chặn bởi một phụ thuộc tiên quyết chưa được giải quyết (ví dụ: việc chốt khe thời gian TDMA bị chặn bởi việc đo đạc vật lý HIL #169).

---

## 2. Bảng Quyết định Nguồn Gốc Đã Tích Hợp (Authoritative Decision Ledger)

Bảng dưới đây tổng hợp toàn bộ các quyết định kỹ thuật cốt lõi đã được Project Owner phê duyệt và các PR đã thực sự merge vào branch `main` tính đến commit `270888a`:

| Quyết định / Hợp phần | Issue & PR Merged to Main | Commit Merge SHA & Nguồn file trên Main | Tóm tắt Quyết định Được Duyệt | Trạng thái Thẩm quyền | Cơ quan Kiểm thử / Evidence Owner |
|---|---|---|---|---|---|
| **Multi-Gateway Star C01–C09** | [#115](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/115) / [PR #116](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116) | Commit merge to main; `docs/architecture/system-overview.md`, `docs/requirements/requirements.md`, `docs/adr/0001-hybrid-tdma.md` | Hệ thống Star 1–4 Gateway; kênh BW125 cô lập; Gateway làm TDMA Master cục bộ; Backend lập lịch nhưng không can thiệp thời gian thực RF. | `OWNER_APPROVED` / Architecture Baseline | Backend & Gateway Architecture |
| **Event-Only Static TDMA + Maintenance SF** | [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125), [#126](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/126) / [PR #133](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/133) | `a5467d498dc359570b8716158376f79fbf931fe6`<br>`docs/architecture/system-overview.md`, `docs/requirements/requirements.md` | Bãi bỏ hoàn toàn phát sóng telemetry định kỳ trên RF; chỉ truyền sự kiện trong khe tĩnh Static DATA Slot; bổ sung Maintenance SF (~300s); báo động tại chỗ tự chủ. | `OWNER_APPROVED_DESIGN_DIRECTION` / Architecture Baseline | System Architecture Team |
| **Presentation Stack: Web Next.js + Mobile Kotlin** | [#111](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/111) / [PR #112](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/112) | `5f5868ec37d8ca7398593dcbebf27818f755aa30`<br>`docs/architecture/interfaces.md`, `docs/development/client-scaffold-plan.md`, `AGENTS.md` | Chốt chính thức công nghệ Client: Web dùng **Next.js + TypeScript**, Mobile dùng **Kotlin native Android**, qua REST/WSS của Backend. Flutter là doc drift lịch sử bị bãi bỏ. | `OWNER_APPROVED` / Architecture Decision | Web & Mobile Frontend Team |
| **MQTT 5.0 / TLS & Backend Boundary** | [#14](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) / [PR #26](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/26) | `8f84bc44`<br>`docs/adr/0002-mqtt-5.md`, `contracts/mqtt/` | Broker Mosquitto MQTT 5.0 + mTLS; QoS 1 cho Event và Command; Backend không định thời khe slot RF; xác thực ACL 2 lớp. | `OWNER_APPROVED_DESIGN` / ADR-0002 Baseline | Backend & MQTT Team |
| **ESP-IDF v6.1 & SX1276 Hardware Target** | [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) | `firmware/esp-idf-version.txt`, `docs/adr/0003-esp-idf-v6-1.md` | Bắt buộc ESP-IDF v6.1, FreeRTOS native, chip SX1276, SPI serialized, non-blocking ISR tối giản. | `OWNER_APPROVED` / ADR-0003 Baseline | Firmware Team |
| **Theoretical ToA & Guard Budget Model** | [#11](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) / [PR #171](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/171) | `ff5c51aa`<br>`docs/adr/0004-theoretical-timing-guard-budget.md`, `docs/verification/rf-timing-methodology-and-harness.md` | Công cụ tính toán ToA lý thuyết và mô hình ngân sách bảo vệ (guard budget). Xác nhận Guard Time thực tế chuyển giao cho đo đạc vật lý #169. | `OWNER_APPROVED` / Theoretical Baseline (Gate G1: NOT_VERIFIED) | RF / Modeling Team |
| **V2 Post-Join READY & Activation Design** | [#136](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/136) / [PR #168](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/168) | `51157d26`<br>`docs/verification/join-v2-ready-tdma-activation-design.md`, `test-matrix.md` | Thiết kế handshake UP_JOIN_READY (0x49) và giao thức chuyển lịch 3 chu kỳ đếm ngược $3 \to 2 \to 1$. | `OWNER_APPROVED_DESIGN` / Implementation Ready: NO (Gate G2: NOT_VERIFIED) | G2 Integration / Test Team |
| **V2 Event DATA / ACK Specification** | [#177](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/177) / [PR #189](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/189) | `ed3e29c9`<br>`docs/verification/v2-event-ack-compatibility-review.md`, `negative-test-matrix.md` | Phê duyệt `DEC-127-01` (`UP_EVENT` 0x41 26B, `DOWN_EVENT_ACK` 0x42 19B), `DEC-127-02` (CCM tag 8B), `DEC-127-03` (SF7/SF8), `DEC-127-04` (DROP_OLDEST FIFO). | `OWNER_APPROVED_DESIGN` (Gate G2: NOT_VERIFIED) | MAC / Security QA |
| **V2 Maintenance SF & Sync/Health** | [#178](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/178) / [PR #190](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/190) | `7f490154`<br>`docs/verification/v2-maintenance-beacon-health-compatibility.md`, `test-matrix.md` | Phê duyệt `DEC-MH-01` (`DOWN_SYNC_BEACON` 0x43 80B Ed25519), `DEC-MH-02` (`UP_HEALTH_REPLY` 0x44 21B CCM-8); chu kỳ mục tiêu 300s. | `OWNER_APPROVED_DESIGN` (Gate G2: NOT_VERIFIED) | MAC / Gateway Team |
| **V2 Cryptographic Trust & X25519 Session Keys** | [#182](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/182) / [PR #193](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/193) | `949f7d31`<br>`docs/verification/v2-join-session-key-compatibility-decisions.md`, `security-test-matrix.md` | Phê duyệt `DEC-SEC-01` đến `DEC-SEC-07`: Ephemeral X25519 ECDH, Backend Zero-Knowledge, dual-auth READY, INSTALLED_INACTIVE fail-closed, NVS counter. | `OWNER_APPROVED_DESIGN` (Gate G2: NOT_VERIFIED) | Crypto / Security Team |
| **V2 MAC Specification & TDMA Integration** | [#127](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127) / [PR #198](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/198) | `270888a0`<br>`contracts/radio-mac/specification.md`, `tdma-schedule.md`, `contracts/OPEN_DECISIONS.md` | Cập nhật Radio MAC Specification v2.0.0-DRAFT và TDMA Schedule v2.0.0-DRAFT; tích hợp mã gói tin V2 (0x41..0x49), lưu danh mục V1 candidate làm historical provenance. | `OWNER_APPROVED_DESIGN` / Draft Contract Integrated (Gate G2: NOT_VERIFIED) | MAC / TDMA Team |
| **MQTT Session Key Install/ACK V1 Contract** | [#122](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/122) / [PR #123](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/123) | `9ab052e2`<br>`contracts/mqtt/session-key-security.md`, schemas | Hợp đồng cài đặt khóa phiên cho Gateway qua MQTT mTLS; V2 sẽ dùng Session Binding Ticket (#128). | `OWNER_APPROVED_DESIGN` (V1 Historic Baseline) | Security / MQTT Team (#173, #174) |
| **PCB HW-001 & SX1276 Pinmap** | [#150](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/150) / [PR #166](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/166) | `481afac5`<br>`docs/verification/pcb-hw001-pinmap.md`, `docs/hardware/sx1276/*` | Khóa cố định pinmap HW-001 cho ESP32 + SX1276 (SCK=18, MISO=19, MOSI=27, NSS=5, DIO0=26, RST=14, Wake=33/39). | `LOCKED_HARDWARE_PINMAP` | Hardware & Embedded Team |
| **Shared Firmware Components Merged** | [#10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) / [PR #170](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/170); [#179](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/179) / [PR #183](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/183); [#180](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/180) / [PR #184](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/184); [#181](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/181) / [PR #185](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/185) | `20204b9f`, `5a146dc0`, `3f338724`, `be823653`<br>`firmware/components/*` | Tích hợp các module dùng chung: SX1276 non-blocking driver, airtime_policy, lora_mac và tdma_common. | `ACTUAL: PARTIAL_MERGED` / Mang nợ tương thích P-10S-15 & V1 framing | Firmware Implementation Team |
| **VN920 Channel Registry & 200kHz Raster** | [#154](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/154) | `docs/requirements/requirements.md`, `contracts/radio-mac/specification.md` | Bảng tần số VN920: 920.250–922.750 MHz (raster 200kHz); Backend quản lý phân bổ kênh độc quyền cho từng Gateway. | `OWNER_APPROVED_REQUIREMENT` | Backend & RF Team |

---

## 3. Sổ Đăng Ký Xung Đột & Độ Lệch Hệ Thống (Conflict Register & System Drift)

### 3.1. Độ Lệch Tài Liệu Presentation (Presentation Doc Drift — Đã Khắc Phục)
- **Nguồn xung đột:** `docs/architecture/system-overview.md` (dòng 32) trước đây ghi: *"Công nghệ Mobile trong các tài liệu cũ chưa thống nhất (Flutter/Kotlin), cần quyết định riêng trước implementation."*
- **Quyết định có thẩm quyền:** Quyết định Owner #111 / PR #112 (commit `5f5868ec37d8ca7398593dcbebf27818f755aa30`) đã phê duyệt chính thức: **Next.js + TypeScript cho Web** và **Kotlin native Android cho Mobile**, giao tiếp thông qua REST/WSS của Backend. `docs/architecture/interfaces.md` và `AGENTS.md` trên `main` đã ghi nhận đầy đủ.
- **Biện pháp xử lý trong PR này:** Đã chỉnh sửa dòng 32 `docs/architecture/system-overview.md` để đồng bộ hoàn toàn với #111/#112. Mọi tài liệu hoặc Issue nhắc đến Flutter được xác định là doc drift lịch sử và không có giá trị thi hành.

### 3.2. Nợ Tương Thích Triển Khai Firmware (Firmware Implementation Legacy Debt)
- **Hiện trạng mã nguồn C thực tế trên `main`:**
  - `firmware/components/tdma_common/include/tdma_common.h`: Mã nguồn C đã merge hiện thực cấu hình Profile P-10S-15:
    - Superframe 10,000 ms (`TDMA_SUPERFRAME_MS = 10000U`), gồm 5 subframe (`TDMA_SUBFRAME_COUNT = 5U`), mỗi subframe 2,000 ms (`TDMA_SUBFRAME_MS = 2000U`).
    - Mỗi subframe chứa 3 khe DATA 400 ms (`TDMA_DATA_SLOTS_PER_SUBFRAME = 3U`, `TDMA_TOTAL_DATA_SLOTS = 15U`, `TDMA_SLOT_DURATION_MS = 400U`).
    - Cửa sổ Beacon/Downlink: 0..250 ms (`TDMA_BCN_DL_WINDOW_START_MS = 0U`, `TDMA_BCN_DL_WINDOW_END_MS = 250U`).
    - **Cửa sổ khe ưu tiên (PCSS Window)**: 250..650 ms (`TDMA_PCSS_WINDOW_START_MS = 250U`, `TDMA_PCSS_WINDOW_END_MS = 650U`, thời lượng 400 ms), loại khe `TDMA_SLOT_TYPE_PCSS = 2`.
    - Vùng DATA bắt đầu từ 650 ms (`TDMA_DATA_SECTION_START_MS = 650U`).
    - Phân chia trong từng khe 400 ms: `TDMA_SLOT_LEADING_GUARD_MS = 25U`, `TDMA_SLOT_TX_BUDGET_MS = 100U`, `TDMA_SLOT_TURNAROUND_MS = 20U`, `TDMA_SLOT_ACK_BUDGET_MS = 100U`, `TDMA_SLOT_TRAILING_GUARD_MS = 155U`.
  - `firmware/components/lora_mac/include/lora_mac.h`: Mã nguồn C hiện thực phong bì candidate 0.1.0-draft:
    - Header không mã hóa 8 byte (`LORA_MAC_HEADER_LEN = 8U`), sync byte `0xA5` (`LORA_MAC_MAGIC_BYTE`), phiên bản candidate `0x01` (`LORA_MAC_PROTOCOL_VERSION_DRAFT`), tải trọng tối đa 48 byte (`LORA_MAC_MAX_PAYLOAD_LEN = 48U`), kiểm tra lỗi bằng CRC-16 unauthenticated.
    - Các loại bản tin candidate (`lora_mac_msg_type_t`): `0x01` LORA_MAC_TYPE_BEACON, `0x02` LORA_MAC_TYPE_SCHED_ANNOUNCE, `0x03` LORA_MAC_TYPE_DATA_TELEMETRY, `0x04` LORA_MAC_TYPE_PRIORITY_ALERT, `0x05` LORA_MAC_TYPE_ACK_PACKET, `0x06` LORA_MAC_TYPE_CMD_DOWNLINK, `0x07` LORA_MAC_TYPE_JOIN_SLOT_REQ, `0x08` LORA_MAC_TYPE_JOIN_SLOT_RSP.
- **Ràng buộc tương thích:** Tuyệt đối không xóa hoặc tự ý viết lại mã nguồn này trong Issue #199. Việc chuyển đổi mã nguồn firmware sang cấu trúc V2 (0x41..0x49, Unicast Header 7B, AES-128-CCM-8, Ed25519 cho Beacon, Static DATA và Maintenance SF) thuộc phạm vi sở hữu của Issue chuyển đổi **#131** và phải có kết quả đo đạc vật lý từ **#169**.

### 3.3. Độ Lệch Hợp Đồng MQTT & API (MQTT/API Contract Drift)
- **Hiện trạng trên `main`:** `contracts/mqtt/topics.md` vẫn còn chứa các định nghĩa `uplink/telemetry` định kỳ và các trường dữ liệu kinh doanh cũ.
- **Ràng buộc tương thích:** Issue **#128** (`[Migration][G4] Version Event-only MQTT/API schemas`) là đơn vị chịu trách nhiệm phiên bản hóa và đồng bộ hợp đồng MQTT/API theo Event-Only sau khi PR #198 đã tích hợp MAC contract. Các file contract DRAFT trên `main` không tự động trở thành normative V2 nếu chưa hoàn tất G4 review.

### 3.4. Trạng Thái PR Đang Mở Đối Chiếu Với Hợp Đồng Main
- **PR #198 (Đã merge tại HEAD `270888a`):** Đã hoàn tất việc tích hợp Radio MAC Specification v2.0.0-DRAFT và TDMA Schedule v2.0.0-DRAFT vào `contracts/radio-mac/`.
- **PR #124 (Open - cho Issue #12):** Đề xuất tài liệu V1 Bootstrap/Join; là tài liệu ứng viên lịch sử, **không** được merge đè lên hợp đồng V2.
- **PR #134 (Open - cho Issue #129):** Đề xuất cập nhật tài liệu hướng dẫn chuyển đổi firmware; đang chờ review.
- **PR #114 (Open - cho Issue #79):** Nhánh cũ `codex/phong-week2` chứa các giả định onboarding cũ; cần rebaseline theo hồ sơ V2 Join (#136/#182).

---

## 4. Danh Mục Toàn Bộ 40 Issues Mở Ngoài Harness & Ma Trận Thẩm Quyền

Dưới đây là bảng đối chiếu chi tiết 40 Open Issues ngoài Harness trên repository tại thời điểm baseline (loại trừ các issue nội bộ Harness tooling/governance như #43, #45, #144... không thuộc phạm vi thực thi hệ thống; bao gồm 36 issue kỹ thuật thuộc các tầng domain và 4 tracker epics cấp Wave #73, #74, #75, #76):

| Issue # | Tiêu Đề | Labels | Trích dẫn AC Cốt Lõi / Tóm tắt Scope | Nguồn Thẩm Quyền & PR Merged | Độ Lệch / Xung Đột Hệ Thống | Đề Xuất Xử Lý (Disposition) | Trạng Thái Phê Duyệt / Gate |
|---|---|---|---|---|---|---|---|
| **#12** | [Contract] Đặc tả Radio MAC v1 an toàn và bộ Golden Test Vectors | layer:mac-tdma, type:contract, ai:human-audit-req, risk:security, wave:1 | Đặc tả Radio MAC v1, cơ chế xác thực/replay, Golden Vectors giải mã mong đợi, đánh giá airtime/guard. | Thay thế bởi PR #198 (V2 MAC Contract); PR #124 đang open. | Mang nội dung V1 candidate cũ; V2 đã có hồ sơ #177/#182 và PR #198. | **KEEP / HISTORICAL RECONCILIATION** (Khép lại hoặc ghi nhận làm V1 baseline, không dùng làm V2 contract) | DRAFT / CONTRACT_GATE (NOT_VERIFIED) |
| **#13** | [MAC] Hiện thực lora_mac, tdma_common và airtime_policy an toàn | layer:fw-gateway, layer:fw-node, layer:mac-tdma, type:feature, wave:2 | Hiện thực 100% Golden Vectors, policy từ chối phát quá hạn ngạch airtime, build pass cả Gateway và Node. | PR #183 (airtime), PR #184 (lora_mac), PR #185 (tdma_common) đã merge to main. | Đã merge một phần mã nguồn khung; còn mang nợ tương thích P-10S-15. | **KEEP / VERIFY** (Duy trì để nghiệm thu integration test thực tế sau khi cập nhật V2) | ACTUAL: PARTIAL_MERGED (HIL_NOT_VERIFIED) |
| **#17** | [Sim] Giả lập Gateway MQTT 10–15 Nodes để kiểm thử Backend | layer:mqtt-infra, layer:backend-go, type:test, wave:2 | Outbound event đạt JSON Schema validation; kịch bản 15 nodes có kết quả tái lập; log báo SIMULATOR_PASS, không báo RF_HIL_PASS. | Phụ thuộc hợp đồng Event-only #128; kế thừa ADR-0002. | Cần điều chỉnh fixture giả lập theo Event-only thay vì periodic telemetry. | **KEEP / UPDATE FIXTURES** (Đồng bộ payload với #128 khi #128 merge) | READY_FOR_REVIEW (SIM_PASS_ONLY) |
| **#18** | [Backend][Event-only] PostgreSQL migrations, MQTT Event ingest và durable idempotent storage (#125) | layer:backend-go, type:feature, risk:reliability, wave:2 | DB migration chạy trên PostgreSQL thật; deduplication (gateway_id, event_id); RF ACK $
eq$ DB commit. | Căn cứ Quyết định #125/PR #133; tuân thủ Go Standard v2. | Hoàn toàn phù hợp với kiến trúc Event-only trên main. | **KEEP / IMPLEMENT** (Tiếp tục triển khai theo phạm vi backend đã duyệt) | OWNER_APPROVED_DESIGN / UNIMPLEMENTED |
| **#19** | [Backend][Static TDMA] Event-only Schedule Planner, Maintenance SF và schedule lifecycle/API (#125) | layer:mac-tdma, layer:backend-go, type:feature, risk:reliability, wave:2 | Planner tạo lịch Static DATA + Maintenance SF (~300s); vòng đời PROPOSED/STAGED/ACTIVE; Gateway Shadow cutover. | Căn cứ Quyết định #125/PR #133; kế thừa PR #198 (TDMA Schedule). | Cần liên kết chặt với TDMA schedule specification v2.0.0-DRAFT vừa merge trong PR #198. | **KEEP / IMPLEMENT** (Tiến hành theo hợp đồng TDMA mới nhất) | OWNER_APPROVED_DESIGN / UNIMPLEMENTED |
| **#49** | [Docs] Chuẩn hóa Wave Labels, Issue Numbers và Project sync script | type:docs | Gắn nhãn wave:1..wave:4; bỏ tiền tố W1/W2 trên title; script lint project verification. | Đã hoàn tất phần lớn trong các đợt rebaseline trước. | Script verify cần được cập nhật theo danh mục Issue mới sau #199. | **UPDATE / CLOSE_POST_VERIFICATION** (Cập nhật script kiểm tra sau khi chốt #199) | DOCS_READY |
| **#60** | [Docs][Architecture] Architecture & Requirements Baseline Remediation — R1 | (Docs/G0) | Phân loại nguồn bắt buộc; giải quyết thiếu sót tài liệu kiến trúc R1. | Đã có PR #61 và các văn bản R2 kế thừa (#64). | Đã được thay thế bởi các đợt cập nhật R2 và quyết định mới hơn. | **HISTORICAL / SUPERSEDED** (Lưu vết quyết định, khép lại sau khi kiểm tra) | HISTORICAL_RECORD |
| **#63** | [G0][Review] Requirements & Architecture Technical Review — after PR #61 | (Review/G0) | Review kỹ thuật độc lập cho Requirements và Kiến trúc sau PR #61; xác minh tính nhất quán của G0. | Đã thực hiện qua các checkpoint của Owner trên main. | Các nội dung đánh giá đã được phản ánh trong ADR-0001 và requirements.md. | **HISTORICAL / SUPERSEDED** (Lưu vết quyết định, khép lại sau khi kiểm tra) | HISTORICAL_RECORD |
| **#64** | [G0][Docs] Requirements & ADR-0001 Remediation — R2 | (G0/Docs) | Hoàn thiện Requirements và ADR-0001 phiên bản R2. | Đã được cập nhật trực tiếp trong PR #116 và PR #133 trên main. | Không còn thay đổi mở; main đã chứa requirements.md và ADR-0001 mới nhất. | **HISTORICAL / SUPERSEDED** (Đề xuất đóng vì nội dung đã merge vào main) | MERGED_COVERAGE |
| **#68** | [Firmware][AI] C Coding Standard v2.0.0-DRAFT — Agent-First | layer:fw-common, type:docs | Hoàn thiện C Coding Standard v2.0.0, bộ quy tắc MUST/SHOULD, kiểm thử static analyzer. | Đã ban hành chính thức qua Quyết định Owner #137 (2026-11-04). | `docs/development/firmware/C_CODING_STANDARD_V2.md` đã có trên main. | **CLOSE_AS_COMPLETED** (Tiêu chuẩn đã ban hành và ràng buộc toàn dự án) | OWNER_APPROVED_STANDARD |
| **#70** | [Backend][AI] Go Engineering Standard v2.0.0-DRAFT — Google Go Style Agent-First | layer:backend-go, type:docs | Hoàn thiện Go Engineering Standard v2.0.0, quy tắc kiến trúc Modular Monolith. | Đã ban hành chính thức qua Quyết định Owner #137 (2026-11-04). | `docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md` đã có trên main. | **CLOSE_AS_COMPLETED** (Tiêu chuẩn đã ban hành và ràng buộc toàn dự án) | OWNER_APPROVED_STANDARD |
| **#73** | Wave 1 – Foundation | wave:1 | Issue Epic theo dõi tiến độ tổng thể Wave 1 (Nền tảng, tài liệu, driver, contract). | Kế hoạch dự án; được cập nhật qua các đợt sync script. | Cần điều chỉnh danh mục issue con theo kết quả rebaseline #199. | **KEEP / TRACKER** (Duy trì làm Issue theo dõi tiến độ Wave 1) | EPIC_TRACKER |
| **#74** | Wave 2 – AI Core Development | wave:2 | Issue Epic theo dõi tiến độ tổng thể Wave 2 (Hiện thực logic firmware, backend, mqtt). | Kế hoạch dự án; kích hoạt sau khi Wave 1 đóng các chốt chặn then chốt. | Phụ thuộc vào việc giải quyết nợ tương thích #131 và schemas #128. | **KEEP / TRACKER** (Duy trì làm Issue theo dõi tiến độ Wave 2) | EPIC_TRACKER |
| **#75** | Wave 3 – System Integration | wave:3 | Issue Epic theo dõi tiến độ tích hợp hệ thống đa thành phần và kiểm thử bảo mật. | Kế hoạch dự án; yêu cầu hoàn thành Wave 2. | Chờ kích hoạt. | **KEEP / TRACKER** (Duy trì làm Issue theo dõi tiến độ Wave 3) | EPIC_TRACKER |
| **#76** | Wave 4 – Verification & Pilot | wave:4 | Issue Epic theo dõi giai đoạn thử nghiệm thực địa và nghiệm thu hiện trường (Pilot). | Kế hoạch dự án; phụ thuộc Gate G6. | Chờ kích hoạt sau Wave 3. | **KEEP / TRACKER** (Duy trì làm Issue theo dõi tiến độ Wave 4) | EPIC_TRACKER |
| **#77** | [Design][Edge] Event-Driven Trigger & Optional Periodic Reporting — Architecture Draft | layer:fw-node, layer:mac-tdma, type:design, wave:1 | Kiến trúc trigger sự kiện cảm biến và tùy chọn gửi định kỳ (Periodic Reporting). | Quyết định Owner #125 / PR #133 đã loại bỏ hoàn toàn truyền định kỳ RF. | Xung đột trực tiếp với nguyên tắc "Zero Periodic Telemetry RF TX" của kiến trúc V2. | **SUPERSEDE / CLOSE_AS_NOT_PLANNED** (Đề xuất đóng; logic nút bấm kế thừa bởi #149, NVS queue bởi #131) | SUPERSEDED_BY_V2 |
| **#78** | [Design][MAC] Hybrid TDMA Event-Only Mode & Priority Access — Protocol Proposal | layer:fw-gateway, layer:fw-node, layer:mac-tdma, type:design, wave:1 | Đề xuất chế độ Event-Only kết hợp khe ưu tiên (Priority Contention Slot / CAD). | Quyết định #125 và PR #198 bãi bỏ khe tranh chấp; áp dụng Static DATA Slot. | Khái niệm khe tranh chấp (PCSS/CAD) bị bãi bỏ hoàn toàn trong hợp đồng V2. | **SUPERSEDE / CLOSE_AS_NOT_PLANNED** (Đề xuất đóng; khe tĩnh chuẩn hóa tại #127/PR #198, firmware tại #131) | SUPERSEDED_BY_V2 |
| **#79** | [Thiết kế][Onboarding] Phát hiện Node → Phê duyệt → Cấp cấu hình → Kích hoạt | layer:fw-gateway, layer:fw-node, layer:backend-go, type:design, wave:1 | Quy trình 4 bước onboarding; cấp phát khe và kích hoạt; chứa cờ `periodic_enabled`. | Kế thừa hồ sơ bảo mật DEC-SEC-01..07 (PR #193) và Join handshake (PR #168/#198). | Tiêu chí cũ có cấu hình chu kỳ định kỳ; cần viết lại AC theo V2 Join handshake. | **REBASELINE / REWRITE AC** (Cập nhật AC theo Join V2 0x45..0x49; loại bỏ tham số chu kỳ định kỳ) | REBASELINE_REQUIRED |
| **#80** | [Design][Mobile Android] Kotlin MVP UI Layouts & Approval Gate — No Code | layer:mobile-app, type:design, wave:1 | Thiết kế layout UI/UX cho Android native (Kotlin); không code; duyệt layout trước khi code. | Quyết định #111 / PR #112 đã xác nhận Kotlin Android; PR #133 bãi bỏ telemetry định kỳ. | Cần loại bỏ toggle bật/tắt báo cáo định kỳ khỏi layout; giữ đúng phạm vi 8 nhóm màn hình MVP của Issue. | **REBASELINE / REWRITE AC** (Giữ nguyên Kotlin; loại bỏ toggle periodic; duy trì đúng 8 nhóm màn hình MVP) | REBASELINE_REQUIRED |
| **#90** | [Thiết kế][Onboarding][Node/Gateway] Phát hiện Node và điều phối Downlink — #79 | layer:fw-gateway, layer:fw-node, type:design, wave:1 | Điều phối Downlink giữa Gateway và Node trong quá trình Join; định dạng khung tin Join. | Hợp đồng MAC V2 tại PR #198 (`UP_JOIN_HELLO` 0x45 68B, `DOWN_JOIN_GRANT` 0x46 66B, `UP_JOIN_READY` 0x49 31B). | AC cũ chưa đồng bộ với cấu trúc gói tin V2; cần cập nhật định dạng khung theo specification.md. | **REBASELINE / REWRITE AC** (Cập nhật định dạng khung tin theo đúng contract V2 tại PR #198) | REBASELINE_REQUIRED |
| **#91** | [Thiết kế][Onboarding][Backend] Phê duyệt, cấp cấu hình và kích hoạt Node — #79 | layer:backend-go, layer:mqtt-infra, type:design, wave:1 | Backend tiếp nhận yêu cầu Join, lưu trữ trạng thái phê duyệt, đẩy cấu hình qua MQTT. | Căn cứ nguyên tắc DEC-SEC-02 (Session Binding Ticket) và Zero-Knowledge Backend. | Cần điều chỉnh AC để Backend không xử lý cấu hình chu kỳ định kỳ; áp dụng ticket binding. | **REBASELINE / REWRITE AC** (Đồng bộ với Session Binding Ticket và Zero-Knowledge) | REBASELINE_REQUIRED |
| **#97** | [Docs][Firmware] Record owner approval and define ESP32 Skill Gap Analysis review plan | type:docs | Ghi nhận phê duyệt tài liệu phân tích khoảng cách kỹ năng ESP32 và kế hoạch review. | Tài liệu `docs/development/firmware/ESP32_SKILL_GAP_ANALYSIS_PLAN.md` là read-only. | Thuộc mảng tài liệu đào tạo / kỹ năng kỹ thuật. | **KEEP / REVIEW_DOCS** (Duy trì tài liệu tham khảo theo dõi khoảng cách kỹ năng) | DOCS_REFERENCE |
| **#102** | [Firmware][Docs] Build indexed ESP32 + SX1276 engineering playbook from five selected skills | layer:fw-common, type:docs | Xây dựng sổ tay kỹ thuật ESP32 + SX1276 từ các kỹ năng chọn lọc. | Bị ràng buộc bởi quy định AGENTS.md: không tự động kích hoạt kỹ năng bên thứ ba. | Cần điều chỉnh để tài liệu thuần túy là tài liệu tham khảo tĩnh. | **KEEP / STANDARDIZE_DOCS** (Hoàn thiện tài liệu tham khảo nội bộ theo tiêu chuẩn) | DOCS_IN_PROGRESS |
| **#106** | docs(adr): fix retired embedded-instructions link and C Standard v2 draft status | type:docs | Sửa các đường dẫn cũ và cập nhật trạng thái C Standard v2 trong ADR. | Đã được xử lý một phần trong các commit tài liệu gần đây. | Cần rà soát lại liên kết sau khi merge #198. | **KEEP / POLISH_DOCS** (Kiểm tra lại broken links và đóng sau khi fix) | DOCS_POLISH |
| **#108** | docs(firmware): owner-approve and freeze five Hot/Cold firmware documents | type:docs | Phê duyệt và đóng băng 5 tài liệu firmware Hot/Cold; kiểm soát kích thước context pack. | Liên quan mật thiết đến cấu trúc tài liệu SX1276 tại `docs/hardware/sx1276/`. | Cần tuân thủ quy tắc định tuyến nhẹ nhàng (selective MVP routing) của AGENTS.md. | **KEEP / FINALIZE** (Hoàn tất phân loại tài liệu Hot/Cold mà không vi phạm AGENTS.md) | DOCS_READY_FOR_REVIEW |
| **#117** | [Contracts] Đồng bộ Radio MAC, TDMA, MQTT, API với kiến trúc C01–C08 | layer:mac-tdma, layer:mqtt-infra, layer:backend-go, type:contract, wave:1 | Kiểm tra tính nhất quán giữa các tầng hợp đồng MAC, TDMA, MQTT, API sau các quyết định C01–C08. | PR #198 đã merge Radio MAC & TDMA contracts; PR #123 đã merge Session Keys V1. | Phạm vi ban đầu rộng; nay chuyển trọng tâm sang kiểm tra chéo (consistency validation) giữa các contract. | **REBASELINE / CONTRACT_ALIGNMENT** (Chuyển thành task kiểm tra nhất quán giữa contracts/radio-mac và contracts/mqtt) | CONTRACT_AUDIT_TASK |
| **#125** | [Migration][G0/G2/G4] Replace periodic telemetry/alert contention with Event-Only Static TDMA + Maintenance SF | (Migration/Epic) | Issue Epic điều phối toàn bộ chiến dịch chuyển đổi sang Event-Only Static TDMA và Maintenance Superframe. | PR #133 đã merge phần kiến trúc và requirements; các issue con (#127..#132) đang xử lý từng lớp. | Là gốc thẩm quyền cho toàn bộ đợt chuyển đổi kiến trúc 04/11. | **KEEP / EPIC_TRACKER** (Duy trì làm Epic quản lý tiến độ chuyển đổi, đóng khi các issue con hoàn tất) | OWNER_APPROVED_EPIC |
| **#127** | [Migration][G2] Version Event ACK, Health and Maintenance SF compatibility (#125) | layer:mac-tdma, type:contract, wave:2 | Phiên bản hóa hợp đồng Radio MAC và TDMA Schedule theo Event-Only, Health và Maintenance SF. | Đã hoàn thành cốt lõi qua PR #198 (`contracts/radio-mac/specification.md` v2.0.0-DRAFT). | Hợp đồng đã tích hợp vào main; cần nghiệm thu Golden Test Vectors trước khi đóng băng G2. | **KEEP / VERIFY_VECTORS** (Chờ bổ sung Golden Vectors và test suite trước khi khép lại) | DRAFT_CONTRACT_INTEGRATED (G2: NOT_VERIFIED) |
| **#128** | [Migration][G4] Version Event-only MQTT/API schemas, examples and contract checks (#125) | layer:mqtt-infra, layer:backend-go, type:contract, wave:2 | Phiên bản hóa các JSON Schemas MQTT và REST/WSS API theo Event-Only, bỏ các topic telemetry cũ. | Kế thừa trực tiếp từ hợp đồng Radio MAC vừa merge tại PR #198. | Cần tạo PR cập nhật các file schemas trong `contracts/mqtt/` và `contracts/api/`. | **KEEP / HIGH_PRIORITY_CONTRACT** (Nhiệm vụ trọng tâm tiếp theo để mở đường cho backend implementation) | READY_FOR_IMPLEMENTATION |
| **#129** | [Migration][Docs] Supersede legacy firmware guidance and implementation roadmaps (#125) | layer:fw-common, type:docs, wave:2 | Đánh dấu superseded cho các hướng dẫn firmware cũ (hướng dẫn P-10S-15, PCSS); cập nhật roadmap. | Đang có PR #134 mở đề xuất nội dung. | PR #134 cần được review và merge để dọn sạch các chỉ dẫn kỹ thuật lỗi thời. | **KEEP / REVIEW_PR134** (Review và cập nhật PR #134 theo các contract vừa merge) | PR_IN_REVIEW |
| **#130** | [Migration][Sim/QA] Verify Static DATA and Maintenance timelines and Event replay (#125) | layer:mac-tdma, layer:mqtt-infra, type:test, wave:2 | Kiểm tra mô phỏng dòng thời gian Static DATA, Maintenance SF và khả năng chống phát lại gói tin. | Phụ thuộc vào hợp đồng MAC #127 (PR #198) và schemas #128. | Cần cập nhật bộ kịch bản kiểm thử giả lập theo đúng cấu trúc slot mới. | **KEEP / QA_VERIFICATION** (Thực hiện kiểm thử mô phỏng sau khi hợp đồng hoàn tất) | QA_TASK |
| **#131** | [Migration][Firmware] Persistent Event queue, own-slot ACK retry and Maintenance execution (#125) | layer:fw-gateway, layer:fw-node, layer:mac-tdma, type:feature, wave:2 | Nâng cấp mã nguồn firmware: xóa bỏ PCSS trong `tdma_common`, đổi gói tin sang V2 trong `lora_mac`, hiện thực NVS queue. | Là đơn vị chịu trách nhiệm xử lý nợ tương thích mã nguồn C đã được nhận diện tại Mục 3.2. | Cần chờ kết quả đo timing từ #169 và chốt Golden Vectors trước khi sửa mã nguồn C. | **KEEP / CORE_FIRMWARE_MIGRATION** (Đơn vị giải quyết nợ kỹ thuật firmware chính thức) | PENDING_PRE_REQUISITES |
| **#132** | [Migration][Backend] Event-only ingest, durable dedup and approved Maintenance planning (#125) | layer:backend-go, type:feature, wave:2 | Backend Go tiếp nhận Event, chống trùng lặp qua Gateway Event ID, lập kế hoạch Maintenance SF. | Kế thừa trực tiếp từ Quyết định #125/PR #133 và schemas #128. | Cần schemas từ #128 trước khi viết mã nguồn hoàn chỉnh. | **KEEP / BACKEND_MIGRATION** (Triển khai backend Event-only sau khi có schemas #128) | PENDING_SCHEMAS_128 |
| **#135** | [GO][V2 Join] Authenticate UP_JOIN_HELLO 68B with HMAC, anti-replay and durable PostgreSQL idempotency | layer:backend-go, ai:human-audit-req, risk:security | Hiện thực module xác thực gói `UP_JOIN_HELLO` (68B) tại Backend: kiểm tra HMAC-SHA256, chống replay, lưu idempotent. | Tuân thủ quy định DEC-SEC-01 và DEC-SEC-02 trong PR #193. | Mã nguồn Go sạch, đã có quy chuẩn rõ ràng; sẵn sàng triển khai. | **KEEP / BACKEND_SECURITY** (Tiến hành triển khai module xác thực Join tại Backend) | READY_FOR_DEV |
| **#149** | [Firmware][Node] Button Wake-up, Debounce and Event Trigger | layer:fw-node, type:feature, wave:2 | Hiện thực ngắt nút bấm vật lý (Wake-up GPIO), chống rung phím (debounce) và kích hoạt tạo sự kiện trên Node HW-001. | Kế thừa phần giá trị cốt lõi từ Issue cũ #77; bám sát pinmap HW-001 đã khóa (#150). | Mã nguồn cô lập trong `firmware/Node_RA-02/`; không phụ thuộc vào việc sửa MAC contract. | **KEEP / HARDWARE_FEATURE** (Sẵn sàng triển khai trên phần cứng thật) | READY_FOR_DEV |
| **#154** | [Backend][RF] PostgreSQL VN920 channel registry and exclusive Gateway allocation | layer:backend-go, type:feature, wave:2 | Thiết kế bảng lưu trữ và API phân bổ kênh VN920 (920.250–922.750 MHz) độc quyền cho từng Gateway. | Đã có Owner phê duyệt yêu cầu kỹ thuật VN920. | Ràng buộc: Không tự cấp quyền phát xạ RF thực tế; chỉ là bảng dữ liệu phân bổ của Backend. | **KEEP / IMPLEMENT** (Hiện thực bảng cơ sở dữ liệu và API phân bổ kênh) | OWNER_APPROVED_REQUIREMENT / READY |
| **#169** | [RF][HIL] Đo timing thực tế trên ESP32–SX1276 và xác nhận Guard Time từ dữ liệu | layer:hw-rf, layer:mac-tdma, type:research, flag:needs-hil-test, wave:1 | Đo đạc vật lý trên bàn thử nghiệm ESP32 + SX1276; ghi nhận ToA thực tế, RX↔TX turnaround, jitter; đề xuất Guard Time từ số liệu. | Kế thừa công cụ tính toán và harness từ Issue #11 / PR #171. | **CHẶN QUAN TRỌNG:** Chưa có số liệu đo đạc thực tế thì mọi mốc Guard Time, 400ms slot hay G1/G3 gate đều là `NOT_VERIFIED`. | **KEEP / CRITICAL_PHYSICAL_GATE** (Điểm chốt vật lý bắt buộc do kỹ sư phần cứng thực hiện trên thiết bị thật) | PENDING_PHYSICAL_BENCH_EXECUTION (G1/G3: NOT_VERIFIED) |
| **#173** | [Security][Contract Test] Verify MQTT Session Key AES-GCM/HMAC Golden Vectors across Go and ESP-IDF mbedTLS | ai:human-audit-req, risk:security | Kiểm thử tương thích mật mã chéo giữa Go (crypto/cipher) và ESP32 (mbedTLS) cho các vector AES-256-GCM và HMAC-SHA256 của khóa phiên. | Xuất phát từ hợp đồng PR #123 và hồ sơ DEC-SEC-01..07 (PR #193). | Bắt buộc kiểm thử byte-exact thực tế, không dùng giả lập Python để kết luận pass. | **KEEP / VERIFY** (Thực hiện bộ test vectors tương thích chéo hai ngôn ngữ) | READY_FOR_VERIFICATION (Gate G5: NOT_VERIFIED) |
| **#174** | [Integration][MQTT] Runtime Session Key Install/ACK over Mosquitto mTLS and per-Gateway ACL | layer:mqtt-infra, ai:human-audit-req, risk:security | Kiểm thử tích hợp runtime: cài đặt khóa phiên qua broker Mosquitto mTLS thật; kiểm tra ACL 2 lớp (TLS CN + MQTT topic). | Xuất phát từ hợp đồng PR #123 và ADR-0002. | Yêu cầu kiểm thử với broker thật và cấu hình mTLS hoàn chỉnh. | **KEEP / VERIFY** (Tiến hành test tích hợp hạ tầng MQTT với TLS mTLS) | READY_FOR_VERIFICATION (Gate G4: NOT_VERIFIED) |
| **#175** | [Firmware][HIL][Security] Verify Gateway NVS INSTALLED_INACTIVE key-slot atomicity under power-loss injection | layer:hw-rf, ai:human-audit-req, risk:security, flag:needs-hil-test | Kiểm thử tính nguyên tử khi lưu khóa vào NVS flash trên Gateway thật dưới điều kiện mất nguồn đột ngột / sụt áp (fault injection). | Căn cứ nguyên tắc fail-closed DEC-SEC-05 và DEC-SEC-06 trong PR #193. | Cần thiết bị ngắt nguồn lập trình được và board Gateway thật; không thay thế bằng phần mềm. | **KEEP / CRITICAL_SECURITY_HIL** (Cổng kiểm thử an ninh phần cứng bắt buộc trước khi cấp quyền vận hành phiên) | PENDING_HIL_FAULT_INJECTION (Gate G5: NOT_VERIFIED) |

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

Các issue này có mục tiêu giá trị nhưng tiêu chí chấp nhận ban đầu còn mang tàn dư của kiến trúc cũ (telemetry định kỳ, Flutter, khe PCSS). Cần điều chỉnh AC bám sát các quyết định và hợp đồng đã có trên `main`, không tự ý thêm các giao thức, giao diện hay hành vi bảo mật chưa có nguồn:

#### Issue #79: `[Thiết kế][Onboarding] Phát hiện Node → Phê duyệt → Cấp cấu hình → Kích hoạt`
- **AC cũ cần loại bỏ:** Mọi quy định về `periodic_enabled`, cấu hình khoảng thời gian gửi tin định kỳ (`telemetry_interval`), và cơ chế cấp phát khe tranh chấp.
- **AC mới đề xuất:**
  1. Quy trình onboarding tuân thủ nghiêm ngặt mô hình 4 bước gắn với hồ sơ bảo mật V2 Join (DEC-SEC-01..07) và hợp đồng `contracts/radio-mac/specification.md`:
     - Bước 1: Node phát `UP_JOIN_HELLO` (0x45, 68 byte: X25519 Ephemeral Pub 32B + Hello Tag 16B HMAC $K_{\text{JOIN}}$).
     - Bước 2: Gateway chuyển tiếp yêu cầu lên Backend qua MQTT; Backend xác thực và cấp `DOWN_JOIN_GRANT` (0x46, 66 byte: X25519 Ephemeral Pub 32B + Backend Grant Proof 16B).
     - Bước 3: Node và Gateway hoàn tất xác thực khóa qua `UP_JOIN_KEY_CONFIRM` (0x47, 31 byte) và `DOWN_JOIN_FINISH` (0x48, 31 byte).
     - Bước 4: Node kích hoạt và gửi bằng chứng sẵn sàng `UP_JOIN_READY` (0x49, 31 byte mang `GW_READY_TAG` 8B và `BACKEND_READY_PROOF` 16B).
  2. Bỏ hoàn toàn cấu hình chu kỳ báo cáo định kỳ; cấu hình bàn giao cho Node chỉ bao gồm: Node ID, Network ID, chỉ số khe tĩnh (Static DATA Slot Index) trong Superframe, và tham số Maintenance SF (~300s).
  3. Cập nhật nhánh PR #114 hoặc đóng PR #114 để mở PR mới bám sát hồ sơ thiết kế PR #168, PR #193 và PR #198 đã merge.

#### Issue #80: `[Design][Mobile Android] Kotlin MVP UI Layouts & Approval Gate — No Code`
- **AC cũ cần điều chỉnh:** Loại bỏ màn hình/toggle bật tắt báo cáo định kỳ ("Periodic Telemetry ON/OFF") và trường nhập chu kỳ phát sóng định kỳ.
- **AC mới đề xuất:**
  1. Khẳng định công nghệ thực hiện duy nhất là **Kotlin native Android**, kết nối Backend qua REST/WSS an toàn (theo Quyết định Owner #111 / PR #112).
  2. Thiết kế layout bám sát đúng 8 nhóm màn hình MVP ban đầu của Issue #80 (không thêm chức năng ngoài luồng chưa có nguồn):
     - (1) *Login/Session (provisional)*: Đăng nhập, hết phiên làm việc.
     - (2) *Home Dashboard*: Trạng thái Gateway, tổng số Node, cảnh báo mới nhất.
     - (3) *Node List*: Tìm kiếm/lọc cơ bản, trạng thái Node, loading/empty/error.
     - (4) *Node Detail & Event History*: Thông tin Node, lịch sử sự kiện đã ghi nhận (không có đồ thị telemetry định kỳ liên tục).
     - (5) *Alert List / Alert Detail*: Mức độ nghiêm trọng, thời điểm, trạng thái ghi nhận; phân biệt rõ Alert Acknowledge trên Backend với RF ACK.
     - (6) *Discovery & Node Approval*: Danh sách thiết bị chờ duyệt (Pending Devices) $\to$ Duyệt/Từ chối $\to$ Trạng thái cấp phát (Pending/Applied/Failed).
     - (7) *Node Configuration*: Cấu hình ngưỡng cảnh báo phần cứng (threshold, debounce, hysteresis); loại bỏ hoàn toàn toggle Periodic Reporting.
     - (8) *Connection/System State*: Trạng thái kết nối REST/WSS (connected, stale, offline, resync).
  3. Duy trì tính chất **DESIGN ONLY – NO CODE**; mọi API chưa có trên `main` phải đánh dấu `CONTRACT_GAP / MOCK_ONLY`.

#### Issue #90 & #91: `Onboarding Node/Gateway Downlink Coordination & Backend Provisioning`
- **AC điều chỉnh:**
  - Loại bỏ các trường định dạng bản tin cũ; áp dụng 100% cấu trúc bản tin chuẩn hóa theo `contracts/radio-mac/specification.md` (PR #198):
    - `UP_JOIN_HELLO` (0x45): 68 byte (X25519 Ephemeral Pub 32B + Hello Tag 16B HMAC $K_{\text{JOIN}}$).
    - `DOWN_JOIN_GRANT` (0x46): 66 byte (X25519 Ephemeral Pub 32B + Backend Grant Proof 16B).
    - `UP_JOIN_READY` (0x49): 31 byte (mang thẻ kép `GW_READY_TAG` 8B và `BACKEND_READY_PROOF` 16B).
  - Phía Backend (#91): Triển khai lưu trữ bền vững trạng thái cấp phép trong PostgreSQL theo cơ chế Session Binding Ticket (DEC-SEC-02), nguyên tắc Zero-Knowledge Backend (DEC-SEC-01), tuyệt đối không lưu trữ các trường chu kỳ định kỳ.

#### Issue #117: `[Contracts] Đồng bộ Radio MAC, TDMA, MQTT, API với kiến trúc C01–C08`
- **AC điều chỉnh:** Không tạo thêm đề xuất kiến trúc mới. Nhiệm vụ chuyển thành: Rà soát và kiểm tra tính nhất quán chéo giữa các tầng hợp đồng đã merge trên `main`:
  1. Kiểm tra đối chiếu mã byte và trường dữ liệu giữa `contracts/radio-mac/specification.md` (PR #198) với `contracts/mqtt/` (đang cập nhật qua #128) và `contracts/api/`.
  2. Xác minh tính toàn vẹn của mô hình chuyển lịch 3 chu kỳ đếm ngược $3 \to 2 \to 1$ qua ranh giới MQTT và TDMA schedule.

---

### 5.3. Nhóm Issue Thực Thi & Kiểm Thử Cần Tiếp Tục Giữ Nguyên (KEEP / VERIFY)

Các Issue sau đây hoàn toàn phù hợp với kiến trúc trên `main`, đang giữ vai trò chủ chốt trong lộ trình thực hiện và cần được bảo vệ:

1. **#169: `[RF][HIL] Đo timing thực tế trên ESP32–SX1276 và xác nhận Guard Time từ dữ liệu`**
   - **Tầm quan trọng:** Là **chốt chặn vật lý duy nhất** để chuyển đổi từ mô hình lý thuyết (Issue #11) sang thông số sản xuất. Không một thay đổi nào về độ dài khe TDMA (hiện đang tạm tính 400ms) hay đóng băng G1/G3 được phép tự kết luận PASS nếu thiếu số liệu đo đạc thực tế từ bench test #169.
2. **#131: `[Migration][Firmware] Persistent Event queue, own-slot ACK retry and Maintenance execution`**
   - **Tầm quan trọng:** Là đơn vị thực thi trực tiếp việc giải quyết nợ kỹ thuật (Legacy Debt) trong mã nguồn firmware: nâng cấp `tdma_common` (xóa bỏ tàn dư PCSS window) và `lora_mac` (chuyển đổi từ framing V1 0x01..0x08 sang framing V2 0x41..0x49).
3. **#128: `[Migration][G4] Version Event-only MQTT/API schemas, examples and contract checks`**
   - **Tầm quan trọng:** Đơn vị cập nhật chính thức các hợp đồng giao tiếp MQTT và API sau khi hợp đồng MAC V2 đã merge trong PR #198.
4. **#18, #19, #132, #135, #154:** Các Issue backend Go đã có kiến trúc rõ ràng, allowed paths cô lập và sẵn sàng triển khai mã nguồn hoặc kiểm thử tích hợp.
5. **#149: `[Firmware][Node] Button Wake-up, Debounce and Event Trigger`:** Hiện thực ngắt nút bấm vật lý trên phần cứng thật HW-001.
6. **#173, #174, #175:** Các bài kiểm tra an ninh và kiểm thử HIL bơm lỗi nguồn điện để xác thực tính nguyên tử của flash NVS và mật mã học.

---

## 6. Lộ Trình Xóa Nợ Tương Thích Firmware (Firmware Debt Transition Plan)

Mã nguồn C trên `main` hiện đang có sự sai lệch giữa hợp đồng thiết kế V2 và hiện thực thực tế:

```
[contracts/radio-mac/ (PR #198 Merged, DRAFT)]          [firmware/components/ on main (Actual C Code)]
--------------------------------------------------          --------------------------------------------------
UP_EVENT (0x41, 26B) / DOWN_EVENT_ACK (0x42, 19B)    vs     LORA_MAC_TYPE_DATA_TELEMETRY (0x03) / ACK (0x05)
Static DATA Slot only (No Contention)              vs     Profile P-10S-15: PCSS Window (250..650ms, Type 2)
DOWN_SYNC_BEACON (0x43, 80B Ed25519)               vs     LORA_MAC_TYPE_BEACON (0x01, Unsigned Header)
UP_HEALTH_REPLY (0x44, 21B CCM-8)                  vs     LORA_MAC_TYPE_PRIORITY_ALERT (0x04)
UP_JOIN_HELLO (0x45, 68B) / GRANT (0x46, 66B)       vs     LORA_MAC_TYPE_JOIN_SLOT_REQ (0x07) / RSP (0x08)
7B Unicast Header + AES-128-CCM-8 Tag (8B)         vs     8B Candidate Header (Magic 0xA5, Ver 0x01) + CRC-16
```

### Kế hoạch chuyển đổi có kiểm soát:
1. **Giai đoạn 1 (Hiện tại - Issue #199):** Ghi nhận đầy đủ hiện trạng nợ tương thích vào Authority Ledger; không sửa mã nguồn C để tránh phá vỡ các bài unit test hiện hành (`test_lora_mac_framing.c`, `test_tdma_common.c`).
2. **Giai đoạn 2 (Issue #169 HIL Timing & Bench Data):** Đo đạc thời gian thực thi thực tế của hàm tính toán ToA và trễ ngắt SX1276 trên phần cứng ESP32 thật để xác định xem khe 400ms có cần nới rộng/thu hẹp.
3. **Giai đoạn 3 (Issue #131 Scoped Firmware Refactor):** 
   - Tạo branch riêng `feature/131-firmware-v2-migration` từ `main`.
   - Cập nhật `tdma_common.h`: Xóa bỏ cửa sổ PCSS (250..650ms), tái cấu trúc bảng slot theo Static DATA + Maintenance SF.
   - Cập nhật `lora_mac.h`: Cập nhật mã bản tin V2 (0x41..0x49), tích hợp hàm đóng gói mbedTLS AES-128-CCM-8 và cấu trúc Header 7B.
   - Chạy bộ kiểm thử giả lập ESP-IDF v6.1 và kiểm thử vật lý xác nhận trước khi mở PR.

---

## 7. Báo Cáo Cổng Chất Lượng & Bằng Chứng Khách Quan (Quality Gates & Evidence Audit)

Tuân thủ nghiêm ngặt nguyên tắc: **Chỉ ghi nhận bằng chứng đo đạc thực tế; mọi cổng chưa đo hoặc chưa có phê duyệt chính thức bằng văn bản đều là `NOT_VERIFIED`**:

| Cổng Kiểm Tra / Verification Gate | Trạng Thái Đánh Giá | Bằng Chứng Thực Tế / Ghi Nhận Khách Quan |
|---|---|---|
| **G0: Thẩm Quyền Tài Liệu & AGENTS.md** | **NOT_VERIFIED / PENDING_FORMAL_APPROVAL** | Script `agent_context.py` chạy thành công tại HEAD `270888a` (hash `32a991b0...`) là kiểm tra intake context của Host Harness, **không phải** verdict nghiệm thu của Release Gate G0. Theo `requirements.md` (INT-001 AC4) và `acceptance-gates.md`, Gate G0 đòi hỏi phê duyệt chính thức bằng văn bản của Project Owner với đầy đủ biên bản phân bổ phạm vi và ma trận truy vết (RTM). |
| **G1: Ngân Sách Thời Gian & Airtime Lý Thuyết** | **NOT_VERIFIED / PENDING_PHYSICAL_MEASUREMENT** | PR #171 (Issue #11) đã tích hợp công cụ tính toán ToA và mô hình ngân sách bảo vệ lý thuyết. Tuy nhiên, Gate G1 theo quy chuẩn bắt buộc phải có số liệu đo đạc thực tế trên phần cứng thật (ToA thực tế, suy hao, airtime). Mô hình lý thuyết không cấp quyền PASS cho G1; phụ thuộc vào bench test từ Issue #169. |
| **G2: Đóng Băng Thiết Kế & Hợp Đồng Wire V2** | **NOT_VERIFIED / DRAFT_CONTRACT_INTEGRATED** | PR #198 đã tích hợp Radio MAC specification v2.0.0-DRAFT và TDMA schedule v2.0.0-DRAFT vào `contracts/radio-mac/`. Các mã bản tin (0x41..0x49) và quyết định mật mã (DEC-SEC-01..07) thuộc diện `OWNER_APPROVED_DESIGN`, nhưng trạng thái hợp đồng vẫn là `DRAFT` (Gate G2: NOT_VERIFIED, chưa đóng băng golden test vectors hay hoàn tất kiểm thử tương thích mật mã). Tuyệt đối không tự ý nâng lên G2 PASS. |
| **G3: Đo Đạc HIL Timing Vật Lý Trên Sóng** | **NOT_VERIFIED / BLOCKED** | Phụ thuộc hoàn toàn vào kết quả chạy thiết bị thật từ Issue #169. Chưa có bench test thực tế, tuyệt đối không tự tuyên bố PASS. |
| **G4: Hợp Đồng Tích Hợp MQTT & Backend API** | **NOT_VERIFIED / IN_PROGRESS** | PR #123 đã merge Session Keys V1; schemas V2 và hợp đồng Event-only đang chờ hoàn tất tại Issue #128. Chưa có end-to-end integration test thực tế giữa Gateway và Backend. |
| **G5: Kiểm Thử Tích Hợp Hệ Thống & Bảo Mật NVS** | **NOT_VERIFIED** | Phụ thuộc vào kết quả fault-injection trên Gateway thật của Issue #175 và kiểm thử tương thích mật mã Go↔mbedTLS của #173. Chưa có kết quả thử nghiệm thực tế. |
| **G6: Thử Nghiệm Thực Địa (RF Field Pilot)** | **NOT_VERIFIED** | Chưa triển khai thực địa; chỉ thực hiện khi toàn bộ Wave 1–3 hoàn tất. |

---

## 8. Kết Luận & Định Nghĩa Hoàn Thành (Definition of Done)

1. **Toàn bộ 40 Open Issues ngoài Harness** (36 issue kỹ thuật thuộc các tầng domain và 4 tracker epics cấp Wave) đã được đối chiếu chi tiết với các quyết định kỹ thuật của Owner và các PR đã merge vào `main` tại commit `270888a`. Các issue nội bộ Harness tooling/governance (#43, #45, #144...) đã được tách riêng khỏi phạm vi thực thi hệ thống.
2. Bảng **Source of Truth / Decision Ledger** và **Conflict Register** đã được thiết lập minh bạch, khẳng định nguyên tắc bất biến: **Không merge vào main = Không dùng làm hợp đồng chính thức; Hợp đồng DRAFT không tự coi là production contract**.
3. Độ lệch tài liệu về công nghệ Mobile (**Flutter vs Kotlin native**) tại `docs/architecture/system-overview.md` đã được xử lý triệt để dựa trên Quyết định Owner #111 / PR #112.
4. Nợ tương thích mã nguồn firmware (`tdma_common` Profile P-10S-15 với cửa sổ PCSS 250..650ms, và `lora_mac` V1 candidate envelope 8B với các mã bản tin 0x01..0x08) đã được ghi nhận chính xác theo mã nguồn C thực tế và cách ly an toàn, phân định rõ quyền sở hữu chuyển đổi cho Issue #131 và kiểm thử vật lý #169.
5. Các Issue chứa AC định kỳ (#77, #78) đã có hồ sơ đề xuất hủy rõ ràng kèm successor mapping; các Issue onboarding (#79, #80, #90, #91, #117) đã có phương án cập nhật AC bám sát các quyết định đã duyệt, không bịa đặt thêm giao thức hay hành vi UI ngoài nguồn.
6. Toàn bộ các cổng nghiệm thu G0–G6 được xác định trung thực ở trạng thái `NOT_VERIFIED` (hoặc `NOT_VERIFIED / BLOCKED`), phản ánh đúng thực tế chưa có biên bản nghiệm thu vật lý hoặc phê duyệt văn bản chính thức.

*Tài liệu này đóng vai trò là cơ sở pháp lý và kỹ thuật duy nhất để Project Owner và đội ngũ phát triển điều phối các nhánh công việc tiếp theo trong kho mã nguồn.*
