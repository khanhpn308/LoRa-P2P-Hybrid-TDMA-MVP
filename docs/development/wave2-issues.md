# Wave 2 — Core Development (Initial Rebaseline, 24/10/2026)

> **Trạng thái:** INITIAL / PARTIAL TASK BREAKDOWN. Bốn Issues dưới đây đã được chuyển từ Wave 1 theo quyết định Project Lead. Đây không phải toàn bộ backlog Wave 2 và không chứng minh core implementation đã PASS.
> **Quy tắc:** Wave phân loại mục tiêu triển khai; Workstream xác định nhóm; Gate G0–G6 là bước nghiệm thu, không phải Wave. Các Workstreams được triển khai song song khi dependencies được đáp ứng.
> **GitHub Labels:** `wave:1`, `wave:2`, `wave:3`, `wave:4` đã được tạo. Bốn Issues thuộc tài liệu này được gắn `wave:2`; các nhãn chuyên môn và assignees giữ nguyên. GitHub Project Custom Field `Wave` (nếu có) chưa được xác minh/cập nhật.
> **Amendment 2026-11-04 theo [#125](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/125):** định hướng chuyển sang Event-only Static TDMA + Maintenance SF (~300s). Bãi bỏ telemetry định kỳ và contention/PCSS; các migration issues tương ứng là #127 (contract G2), #128 (contract G4), #129 (docs roadmap), #130 (sim), #131 (firmware) và #132 (backend).

## 1. Danh mục bốn Issues đã chuyển — Label `wave:2`

| GitHub Issue | Workstream | Gate | Phụ thuộc chính |
|---|---|---|---|
| [#13 MAC / TDMA Common / Airtime](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/13) | Firmware/MAC | G3: Embedded | #10, #11, #12 |
| [#17 Gateway MQTT Simulator](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/17) | Simulator/Backend | G4: Integration | #14, #16 |
| [#18 PostgreSQL / MQTT Ingestion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18) | Backend | G4: Integration | #14, #16; integration với #17 |
| [#19 Go TDMA Scheduler](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19) | Backend/Planner | G4: Integration | #11, #12, #14, #15, #17, #18 |

**Tình trạng ban đầu:** Bốn Issues đều Open tại thời điểm rebaseline. Đã bỏ tiền tố mã Wave trên tiêu đề và thay các tham chiếu Task ID bằng GitHub Issue Number (`#`). Giữ nguyên Acceptance Criteria, Gate, owners, state và tiêu chuẩn test.

## 2. Công việc Wave 2 còn cần phân rã

Các hạng mục sau thuộc backlog triển khai; một số đã có Issue được dẫn trong bảng, các mục còn lại cần phân rã phạm vi trước khi thực hiện:

| Workstream | Hạng mục triển khai | Điều kiện cần |
|---|---|---|
| Hardware/RF | RF measurements mở rộng, chuẩn bị 2–5 Node HIL | Kết quả #9/#11, thiết bị và RF policy |
| Firmware Gateway | Static DATA/ACK Executor, durable Event receipt, Maintenance/Health, local fallback | #10/#11/#12, #13, #127/#131 |
| Firmware Node | Local alarm, persistent bounded Event FIFO, own-slot ACK/retry, Maintenance Sync/Health | #10/#11/#12, #13, #127/#131 |
| Gateway Connectivity | Wi-Fi, MQTT/TLS bridge, disconnect/recovery | #14/#16, Gateway FW |
| Backend | Event-only ingest/durable dedup, static DATA/Maintenance planning và API theo contract | #14/#15, #17/#18/#19, #128/#132 |
| Mobile Flutter | Dashboard, devices, Event history, alerts với mock/API | Flutter foundation Issues cần tạo ở Wave 1, #15, contract migration #128 |
| QA/Simulation | DATA/Maintenance/Join/Recovery timeline, ACK/replay/Health/reboot/overflow fault cases | Reviewed MAC/TDMA contracts, timing evidence và #130 |

**Không coi** Gateway MQTT Simulator (#17) là Radio-network Simulator và không suy diễn `SIMULATOR_PASS` thành `RF_HIL_PASS`.

## 3. Phát triển song song và nghiệm thu

- Wave 1 và Wave 2 được phép chồng lấn về lịch khi phụ thuộc của một Issue đã rõ ràng; không yêu cầu Wave 1 đóng toàn bộ mới bắt đầu Wave 2.
- Backend có thể dùng MQTT fixture/Simulator để phát triển độc lập radio thật; Scheduler chỉ được nghiệm thu simulation riêng.
- Mobile có thể phát triển với mock API theo contract đã review; không mặc định thiết bị hoặc hệ thống RF đã hoạt động.
- Các thay đổi Contract/API cần producer và consumer review trước khi freeze.
- Theo dõi tiến độ bằng Issues + evidence (Unit/Contract/Integration/HIL/RF), không bằng số commit/PR.

## 4. Kiểm tra đồng bộ

- [x] Bốn Issues đã được gắn `wave:2`: #13, #17, #18, #19.
- [x] Các dependencies được cập nhật theo `#Issue`, tiêu đề không còn mã W1/W2.
- [ ] PR cập nhật hai danh mục và script được review, merge vào `main`.
- [x] Labels `wave:1` đến `wave:4` đã được tạo; Wave 1/2 đã gắn cho 12 Issues nền tảng.
- [ ] GitHub Project Custom Field `Wave` được đọc/cấu hình và xác minh nếu có (độc lập GitHub Issue Labels).
- [ ] Những nhiệm vụ Wave 2 còn thiếu được Task Breakdown bằng Issues độc lập.

Xem [Wave 1 sau rebaseline](wave1-issues.md) và [Acceptance Gates](../verification/acceptance-gates.md).
