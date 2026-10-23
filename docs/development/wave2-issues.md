# Wave 2 — Core Development (Initial Rebaseline, 24/10/2026)

> **Trạng thái:** INITIAL / PARTIAL TASK BREAKDOWN. Bốn Issues dưới đây đã được chuyển từ Wave 1 theo quyết định Project Lead. Đây không phải toàn bộ backlog Wave 2 và không chứng minh core implementation đã PASS.
> **Quy tắc:** Wave phân loại mục tiêu triển khai; Workstream xác định nhóm; Gate G0–G6 là bước nghiệm thu, không phải Wave. Các Workstreams được triển khai song song khi dependencies được đáp ứng.
> **GitHub Project #1:** Chưa xác minh/cập nhật được trường Custom Field `Wave` bằng kết nối hiện tại. Giữ nguyên Project items, Gate, labels và assignees trước khi rebaseline.

## 1. Danh mục bốn Issues đã chuyển

| ID mới | Issue | Mã cũ | Workstream | Gate | Phụ thuộc chính |
|---|---|---|---|---|---|
| W2-01 | [#13 MAC / TDMA Common / Airtime](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/13) | W1-06 | Firmware/MAC | G3: Embedded | W1-03 (#10), W1-04 (#11), W1-05 (#12) |
| W2-02 | [#17 Gateway MQTT Simulator](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/17) | W1-10 | Simulator/Backend | G4: Integration | W1-07 (#14), W1-09 (#16) |
| W2-03 | [#18 PostgreSQL / MQTT Ingestion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18) | W1-11 | Backend | G4: Integration | W1-07 (#14), W1-09 (#16); kiểm thử với W2-02 (#17) |
| W2-04 | [#19 Go TDMA Scheduler](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19) | W1-12 | Backend/Planner | G4: Integration | W1-04 (#11), W1-05 (#12), W1-07 (#14), W1-08 (#15), W2-02 (#17), W2-03 (#18) |

**Tình trạng ban đầu:** Cả bốn Issues đều Open tại thời điểm chuyển. Chỉ thay đổi Wave/Task ID và tham chiếu phụ thuộc. Không thay đổi Acceptance Criteria, owner, state, hoặc tiêu chuẩn test.

## 2. Công việc Wave 2 còn cần phân rã

Các hạng mục sau mới thuộc backlog dự kiến, **chưa phải Issues đã tạo**:

| Workstream | Hạng mục triển khai | Điều kiện cần |
|---|---|---|
| Hardware/RF | RF measurements mở rộng, chuẩn bị 2–5 Node HIL | Kết quả W1-02/W1-04, thiết bị và RF policy |
| Firmware Gateway | Beacon Engine, TDMA Master Executor, local fallback | W1-03/W1-04/W1-05, W2-01 |
| Firmware Node | Beacon Sync, TDMA Client, Priority Access | W1-03/W1-04/W1-05, W2-01 |
| Gateway Connectivity | Wi-Fi, MQTT/TLS bridge, disconnect/recovery | W1-07/W1-09, Gateway FW |
| Backend | Hoàn thiện các module API/Alert và domain theo contract | W1-07/W1-08, W2-02/W2-03/W2-04 |
| Mobile Flutter | Dashboard, devices, telemetry, alerts với mock/API | Flutter foundation Issues cần tạo ở Wave 1, W1-08 |
| QA/Simulation | Radio-network simulator và các kịch bản thử lỗi | MAC/TDMA contract và test fixtures |

**Không coi** Gateway MQTT Simulator (#17) là Radio-network Simulator và không suy diễn `SIMULATOR_PASS` thành `RF_HIL_PASS`.

## 3. Phát triển song song và nghiệm thu

- Wave 1 và Wave 2 được phép chồng lấn về lịch khi phụ thuộc của một Issue đã rõ ràng; không yêu cầu Wave 1 đóng toàn bộ mới bắt đầu Wave 2.
- Backend có thể dùng MQTT fixture/Simulator để phát triển độc lập radio thật; Scheduler chỉ được nghiệm thu simulation riêng.
- Mobile có thể phát triển với mock API theo contract đã review; không mặc định thiết bị hoặc hệ thống RF đã hoạt động.
- Các thay đổi Contract/API cần producer và consumer review trước khi freeze.
- Theo dõi tiến độ bằng Issues + evidence (Unit/Contract/Integration/HIL/RF), không bằng số commit/PR.

## 4. Kiểm tra đồng bộ

- [x] Bốn Issue đã chuyển mã trên GitHub: #13, #17, #18, #19.
- [x] Các dependencies W2 được cập nhật trong body của bốn Issues.
- [ ] PR cập nhật hai danh mục và script được review, merge vào `main`.
- [ ] GitHub Project Custom Field `Wave` được đọc/cấu hình và xác minh nếu có.
- [ ] Những nhiệm vụ Wave 2 còn thiếu được Task Breakdown bằng Issues độc lập.

Xem [Wave 1 sau rebaseline](wave1-issues.md) và [Acceptance Gates](../verification/acceptance-gates.md).
