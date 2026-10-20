# Wave 1 — 12 GitHub Issues (bản đã hiệu chỉnh)

> **Trạng thái:** 12/12 GitHub Issues đã được tạo và kiểm tra trên repository.
> **Project #1:** Việc thêm Project Item/Gate cần chạy `scripts/sync_wave1_project.sh` bằng tài khoản GitHub có quyền `project`, sau đó nhận dòng `SUCCESS: 12/12...`. Chỉ sau bước đó mới xác nhận chúng thực sự nằm trong Project.
> **Phạm vi Wave 1:** Repository Governance, RF/Driver Feasibility, Protocol/Shared MAC, Backend/Simulator Preparation. **Không** có nghĩa đã hoàn thành toàn bộ Gateway Master, Node TDMA Client hoặc hệ thống RF end-to-end.
>
> **Quy ước quản lý:** `W1-05` là Issue thứ 05 của Wave 1, **không** phải bước thực hiện thứ năm. `Workstream` phân loại miền kỹ thuật; `Gate` G0–G6 là cổng nghiệm thu; dependencies và mức sẵn sàng quyết định thứ tự thực thi. Không sử dụng mã Phase `F0–F3` trong Task ID/Issue title.

## 1. Danh mục Issues chính thức

| ID | GitHub Issue | Workstream | Project Gate | Priority đề xuất | Điều kiện phụ thuộc chính |
|---|---|---|---|---|---|
| W1-01 | [#8 Repo Governance](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/8) | Repo | G0: Scope | P1 | Không |
| W1-02 | [#9 Hardware/RF Bring-up](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/9) | RF | G1: RF | P0 | W1-01 (governance), thực nghiệm có thể song song |
| W1-03 | [#10 ESP-IDF Components + Driver](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) | Driver | G1: RF | P0 | W1-02 xác nhận pinout |
| W1-04 | [#11 Timing/ToA/Guard](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/11) | RF | G1: RF | P0 | W1-02, W1-03 |
| W1-05 | [#12 Radio MAC Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12) | Contract | G2: Protocol | P0 | W1-04, security review |
| W1-06 | [#13 MAC/Airtime implementation](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/13) | MAC | G3: Embedded | P0 | W1-03, W1-04, W1-05 |
| W1-07 | [#14 MQTT Contract](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/14) | Contract | G2: Protocol | P1 | W1-01; W1-05 phiên bản và session |
| W1-08 | [#15 OpenAPI/WebSocket](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/15) | Contract | G4: Integration | P1 | W1-07 data semantics |
| W1-09 | [#16 Local Infrastructure/TLS](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/16) | Infra | G4: Integration | P1 | W1-01; W1-07 topic ACL |
| W1-10 | [#17 Gateway MQTT Simulator](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/17) | Sim | G4: Integration | P1 | W1-07, W1-09 |
| W1-11 | [#18 Storage/MQTT Idempotency](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/18) | Backend | G4: Integration | P1 | W1-07, W1-09, W1-10 |
| W1-12 | [#19 Go Scheduler/Simulation](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/19) | Backend | G4: Integration | P1 | W1-04, W1-05, W1-07, W1-08, W1-10, W1-11 |

**Lưu ý:** Priority P0/P1 trong bảng mới là khuyến nghị, chưa khẳng định đã gán vào Custom Field. Chưa gán assignee khi 5 tài khoản khác chưa được xác minh. Mỗi Issue đã có mục `Target Directories (allowed paths)` và điều kiện nghiệm thu.

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

Đưa vào backlog Wave 2 bằng Issue độc lập, không gộp lẫn vào nghiệm thu #8–#19:

1. Gateway Beacon + TDMA Master Executor + local fallback.
2. Node Beacon Synchronization + TDMA Client.
3. Gateway MQTT/TLS Transport/Bridge + outage/recovery.
4. Radio-network simulator (mô hình RF/MAC riêng với Gateway MQTT simulator).
5. Multi-node HIL/System Integration, safety/reliability/field RF evidence.

Khi các module này còn thiếu, **không** chấp nhận trạng thái `END_TO_END_RF_PASS`.

## 4. Đồng bộ GitHub Project #1

Dùng **WSL Ubuntu** trong root của repo; script chỉ thao tác với những Issue đã tồn tại #8–#19, không tạo mới hay xóa.

```bash
git fetch origin
git switch research/ready-for-taskbreakdown
git pull --ff-only
bash scripts/sync_wave1_project.sh
```

Đầu ra thành công phải có đúng 12 dòng `VERIFIED: Issue #... belongs to Project #1` và kết thúc:

```text
SUCCESS: 12/12 Wave 1 Issues linked and Gate VERIFIED on GitHub Project #1.
```

Nếu thất bại giữa chừng, chạy lại được; script tìm Project Item đã có trước khi thêm, không thay đổi Label/Issue Body/Assignee. Nó chỉ gán `Gate`, chưa cập nhật `Status`, `Priority`, `Sprint`, `Estimate` — hãy cấu hình các field đó trong Project theo kế hoạch sprint đã được phê duyệt.

Xem [Pre-Task-Breakdown Readiness](task-breakdown-readiness.md) và [Monorepo Guide](monorepo-guide.md).
