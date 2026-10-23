# Wave 1 — 8 Issues sau Wave Rebaseline (24/10/2026)

> **Lịch sử:** 12 Issues #8–#19 được tạo ban đầu cho Wave 1. Theo quyết định rebaseline 24/10/2026, #13, #17, #18, #19 được chuyển sang Wave 2, giữ nguyên Issue Number, Acceptance Criteria và assignees. Xem [danh mục Wave 2](wave2-issues.md).
> **Trạng thái Wave 1:** 8 Issues: #8–#12, #14–#16; #8 Closed và 7 Issues Open tại thời điểm rebaseline. Trạng thái có thể thay đổi sau đó.
> **Project #1:** `scripts/sync_wave1_project.sh` kiểm tra label `wave:1`, đồng bộ tám Issues thuộc Wave 1 và trường Gate G0–G6. Cần chạy bằng tài khoản có quyền `project` và xác minh kết quả; script KHÔNG cập nhật Custom Field `Wave`.
> **Phạm vi Wave 1 mới:** Governance, RF Bring-up/Timing, Shared SX1276 Driver Baseline, Radio MAC/MQTT/API Contracts và Local Infrastructure. Core MAC, Simulator hoàn chỉnh, Backend Ingestion và Scheduler thuộc Wave 2.
>
> **Quy ước mới:** Chỉ sử dụng số GitHub Issue (`#8`, `#14`, ...). Label `wave:1` phân loại Wave; nhãn `layer:*` thể hiện Workstream và Project Gate G0–G6 là cổng nghiệm thu. Không dùng mã W1/W2 trong tiêu đề hoặc body Issue.

## 1. Danh mục Issues chính thức — Label `wave:1`

| GitHub Issue | Workstream | Project Gate | Priority đề xuất | Điều kiện phụ thuộc chính |
|---|---|---|---|---|
| [#8 Repo Governance](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/8) | Repo | G0: Scope | P1 | Không |
| [#9 Hardware/RF Bring-up](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/9) | RF | G1: RF | P0 | #8 (governance), thực nghiệm có thể song song |
| [#10 ESP-IDF Components + Driver](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) | Driver | G1: RF | P0 | #9 xác nhận pinout |
| [#11 Timing/ToA/Guard](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) | RF | G1: RF | P0 | #9, #10 |
| [#12 Radio MAC Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) | Contract | G2: Protocol | P0 | #11, security review |
| [#14 MQTT Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) | Contract | G2: Protocol | P1 | #8; #12 phiên bản và session |
| [#15 OpenAPI/WebSocket](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15) | Contract | G4: Integration | P1 | #14 data semantics |
| [#16 Local Infrastructure/TLS](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/16) | Infra | G4: Integration | P1 | #8; #14 topic ACL |

**Lưu ý:** Priority P0/P1 là khuyến nghị, không có nghĩa đã gán Custom Field. Assignees và trạng thái xem trực tiếp tại GitHub. Các Issues giữ nguyên `Target Directories (allowed paths)` và Acceptance Criteria. Tiến độ Wave được lọc bằng `label:wave:1`.

**Lịch sử rebaseline (24/10/2026):** Issues #13, #17, #18, #19 được phân loại lại vào Wave 2. GitHub Edit History lưu các tiêu đề cũ; ID Issue không thay đổi.

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

Dùng **WSL Ubuntu** trong root của repo **sau khi PR rebaseline được review/merge**. Script xác minh label `wave:1` và chỉ kiểm tra/liên kết tám Issue Wave 1 (#8–#12, #14–#16) với Project và cập nhật Gate, không tạo Issue mới, không xóa Project item và không thao tác #13/#17/#18/#19.

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
