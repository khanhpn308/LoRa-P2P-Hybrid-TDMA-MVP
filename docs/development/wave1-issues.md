# Wave 1 — 8 Issues sau Wave Rebaseline (24/10/2026)

> **Lịch sử:** 12 Issues #8–#19 được tạo ban đầu cho Wave 1. Theo quyết định rebaseline 24/10/2026, #13, #17, #18, #19 được chuyển sang Wave 2, giữ nguyên Issue Number, Acceptance Criteria và assignees. Xem [danh mục Wave 2](wave2-issues.md).
> **Trạng thái Wave 1:** 8 Issues: #8–#12, #14–#16; #8 Closed và 7 Issues Open tại thời điểm rebaseline. Trạng thái có thể thay đổi sau đó.
> **Project #1:** `scripts/sync_wave1_project.sh` chỉ đồng bộ tám Issues còn thuộc Wave 1 và trường Gate G0–G6. Cần chạy bằng tài khoản có quyền `project` và xác minh kết quả; script KHÔNG cập nhật Custom Field `Wave`.
> **Phạm vi Wave 1 mới:** Governance, RF Bring-up/Timing, Shared SX1276 Driver Baseline, Radio MAC/MQTT/API Contracts và Local Infrastructure. Core MAC, Simulator hoàn chỉnh, Backend Ingestion và Scheduler thuộc Wave 2.
>
> **Quy ước quản lý:** `W1-05` là Issue thứ 05 của Wave 1, **không** phải bước thực hiện thứ năm. `Workstream` phân loại miền kỹ thuật; `Gate` G0–G6 là cổng nghiệm thu; dependencies và mức sẵn sàng quyết định thứ tự thực thi. Không sử dụng tiền tố Phase trong Task ID hoặc Issue title.

## 1. Danh mục Issues chính thức

| ID | GitHub Issue | Workstream | Project Gate | Priority đề xuất | Điều kiện phụ thuộc chính |
|---|---|---|---|---|---|
| W1-01 | [#8 Repo Governance](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/8) | Repo | G0: Scope | P1 | Không |
| W1-02 | [#9 Hardware/RF Bring-up](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/9) | RF | G1: RF | P0 | W1-01 (governance), thực nghiệm có thể song song |
| W1-03 | [#10 ESP-IDF Components + Driver](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) | Driver | G1: RF | P0 | W1-02 xác nhận pinout |
| W1-04 | [#11 Timing/ToA/Guard](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) | RF | G1: RF | P0 | W1-02, W1-03 |
| W1-05 | [#12 Radio MAC Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) | Contract | G2: Protocol | P0 | W1-04, security review |
| W1-07 | [#14 MQTT Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) | Contract | G2: Protocol | P1 | W1-01; W1-05 phiên bản và session |
| W1-08 | [#15 OpenAPI/WebSocket](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15) | Contract | G4: Integration | P1 | W1-07 data semantics |
| W1-09 | [#16 Local Infrastructure/TLS](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/16) | Infra | G4: Integration | P1 | W1-01; W1-07 topic ACL |

**Lưu ý:** Priority P0/P1 là khuyến nghị, không có nghĩa đã gán Custom Field. Assignees xem trực tiếp tại từng Issue vì có thể đã thay đổi so với bản khởi tạo. Mỗi Issue vẫn giữ `Target Directories (allowed paths)` và Acceptance Criteria. Mã W1-01..05, W1-07..09 có khoảng trống có chủ đích; không đánh lại ID lịch sử.

**Migration mapping (24/10/2026):** W1-06 → [W2-01 #13](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/13), W1-10 → [W2-02 #17](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/17), W1-11 → [W2-03 #18](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18), W1-12 → [W2-04 #19](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19).

## 2. Các hiệu chỉnh so với Bash ban đầu

- **Firmware bootstrap:** Issue #10 tạo đủ bốn CMake components có mã/interface khả dụng trước khi đòi build cả hai ESP-IDF apps, thay vì chỉ xem `EXTRA_COMPONENT_DIRS` là đủ.
- **IRQ:** Cấu hình SX1276 `RegDioMapping1/2` được kiểm tra theo mode; phân biệt `CadDone` và `CadDetected`; không gắn `CadDone` cố định với DIO1.
- **Đo RF:** Issue #11 tách `RF ToA`, `TX-command→TxDone`, turnaround, drift, timestamp uncertainty.
- **Airtime/compliance:** Không hardcode Node 1% / Gateway 10% trước G1. Frame khẩn cấp cũng phải tuân RF policy.
- **Security:** CRC không là authentication. MAC v1 cần thiết kế nonce, tag và anti-replay, kiểm thử Golden Vectors semantic chứ không chỉ JSON syntax.
- **MQTT:** `event_id` bền vững qua reboot/replay; schedule Stage khác Activate, retained stale schedule phải bị từ chối.
- **API:** REST OpenAPI và các WebSocket event schemas có quy tắc riêng.
- **Backend:** Planner được kiểm thử với simulator, không tuyên bố Gateway RF đã ACTIVE.
- **Quản lý:** Gate là Custom Field G0–G6, mỗi Issue có đúng một Gate mục tiêu. Script tạo Issue hàng loạt ban đầu không chạy lại để tránh tạo trùng.

## 3. Công việc còn thiếu ngoài Wave 1

Ngoài bốn Issues đã chuyển sang Wave 2 (#13, #17, #18, #19), các đầu việc dưới đây vẫn cần được Task Breakdown thành Issues độc lập, không tự coi là đã nghiệm thu:

1. Gateway Beacon + TDMA Master Executor + local fallback.
2. Node Beacon Synchronization + TDMA Client.
3. Gateway MQTT/TLS Transport/Bridge + outage/recovery.
4. Radio-network simulator (mô hình RF/MAC riêng với Gateway MQTT simulator).
5. Multi-node HIL/System Integration, safety/reliability/field RF evidence.

Khi các module này còn thiếu, **không** chấp nhận trạng thái `END_TO_END_RF_PASS`.

## 4. Đồng bộ GitHub Project #1

Dùng **WSL Ubuntu** trong root của repo **sau khi PR rebaseline được review/merge**. Script chỉ kiểm tra/liên kết tám Issue Wave 1 (#8–#12, #14–#16) với Project và cập nhật Gate, không tạo Issue mới, không xóa Project item và không thao tác #13/#17/#18/#19.

```bash
git fetch origin
git switch main
git pull --ff-only
bash scripts/sync_wave1_project.sh
```

Đầu ra thành công phải có đúng 8 dòng `VERIFIED: Issue #... belongs to Project #1` và kết thúc:

```text
SUCCESS: 8/8 Wave 1 Issues linked and Gate VERIFIED on GitHub Project #1.
```

Nếu thất bại giữa chừng, chạy lại được; script tìm Project Item đã có trước khi thêm, không thay đổi Label/Issue Body/Assignee. Nó chỉ gán `Gate`, chưa cập nhật `Status`, `Priority`, `Sprint`, `Estimate` — hãy cấu hình các field đó trong Project theo kế hoạch sprint đã được phê duyệt.

Xem [Pre-Task-Breakdown Readiness](task-breakdown-readiness.md) và [Monorepo Guide](monorepo-guide.md).
