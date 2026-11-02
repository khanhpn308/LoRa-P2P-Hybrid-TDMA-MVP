# TDMA Schedule Interface — profile P-10S-15 (đề xuất, chưa freeze)

**Nguồn:** kiến trúc đính kèm §5.1–5.3, §7.3–7.4 · #12, #14. **Giá trị thời gian chỉ là baseline để làm mock/simulator; G1/G2/G3 chưa PASS.**

## Owner-approved TDMA and Recovery rules — design level only (2026-11-02)

The following decisions supersede conflicting mock/simulator assumptions in the P-10S-15 baseline. They **do not** prove the selected schedule can fit one SX1276 RF airtime/guard budget.

- **SS-01**: Gateway requires authenticated `UP_SCHED_READY` from **100% of its required Nodes** before cutover; every Node must durably persist Shadow Schedule and `OLD_TX_FENCE_SF=E` before READY. Missing any READY ⇒ **ABORT**. [Owner decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6542745470).
- **SS-02**: Node requires all three authenticated announcements `3→2→1` bound to the same transaction and an authenticated ACTIVE Beacon; missing proof ⇒ **SUSPENDED/RESYNC**, no affected TX at/from E. [Owner decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6542745470).
- **RF-SCHED-READY-02**: READY replaces Telemetry in the Node's **own valid old-schedule DATA slot**. No fabricated slot; lease, fence, guard and airtime are mandatory. [Owner decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6561024504).
- **SF-RESYNC-01 / SF-RECOVERY-01–03**: Abnormal authenticated `SF_EPOCH` triggers safe RESYNC; unchanged Active Schedule may be restored after verified reboot; ambiguous interrupted cutover fails closed, with Backend-controlled authenticated Recovery Grant for affected rights. [Decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6559234872).
- **SF-RECOVERY-04/05**: Backend plans and User approves a fixed Shared CTRL Window for Join/Recovery, logically after Beacon and before Alert/DATA, with nonoverlapping DL/UL. One SX1276 is half-duplex. **P-10S-15 has no verified spare CTRL capacity**; no silent schedule changes. Join defaults CLOSED. [Decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6559992609).

**OPEN / NOT_VERIFIED**: exact timing, control packet layouts, schedule membership snapshot, legal RF, ToA, guard, security, implementation, simulation and HIL. These approvals are design principles, not production timing sign-off.

## Compact MAC v1 lengths and airtime impact — Owner decision (2026-11-02)

[ADR-0002](../../docs/adr/0002-radio-mac-security-v1.md) supersedes the earlier **41B** `UP_SCHED_READY` with **19B**, and **61B** `DOWN_AUTH_UPDATE` Recovery Grant with **48B**. Beacon base remains **28B Group HMAC**. All lengths are MAC payload only (no PHY overhead). No change to the Owner-approved 100%-READY, authenticated 3→2→1, ACTIVE Beacon, persistent OLD_TX_FENCE_SF and immutable Backend-planned schedule.

**READY is transmitted by Node within its own old-schedule authorized DATA slot** (replaces Telemetry), never in free CTRL; Recovery Grant is Backend-authored, Gateway-forwarded in an explicitly approved DOWN CTRL opportunity. Do not invent an extra slot because the RF message is smaller.

Theoretical SX1276 airtime (BW=125kHz, CR=4/5, preamble=8, explicit header, PHY CRC on, LDRO on SF11/SF12) **excluding guard, turnaround, contention**:

| Frame | SF7 | SF8 | SF10 | SF12 |
|---|---:|---:|---:|---:|
| Beacon 28B | 66.82ms | 123.39ms | 411.65ms | 1646.59ms |
| READY prior 41B | 87.30ms | 154.11ms | 534.53ms | 2138.11ms |
| **READY locked 19B** | **51.46ms** | **102.91ms** | **329.73ms** | **1318.91ms** |
| Recovery prior 61B | 112.90ms | 205.31ms | 698.37ms | 2793.47ms |
| **Recovery locked 48B** | **97.54ms** | **174.59ms** | **575.49ms** | **2301.95ms** |

**Warning:** mock P-10S-15 allocates 250ms Beacon and 400ms DATA, but it is not RF-verified: SF10 Beacon requires 411.65ms, SF10 Recovery needs 575.49ms, and SF10 READY leaves only ~70ms before a 400ms-slot end without accounting for guard/turnaround (may still violate actual usable TX budget). Larger SF profiles cannot assume these short windows. Apply ToA+guard+driver turnaround and preapproved PHY/schedule before enabling any radio TX. `G2/G3/HIL = NOT_VERIFIED`.

## 1. Mẫu superframe danh định

- `superframe_ms = 10000`; 5 subframe × 2000ms; mỗi subframe có 250ms BCN/DL + 400ms PCSS + 3 data slot × 400ms + 150ms guard.
- Slot data #1..#15 theo thứ tự: tại subframe i (0..4) và slot c (0..2), `start_ms = 2000*i + 650 + 400*c`. Trong slot: leading guard 0..25ms; TX budget 25..125ms; turnaround 125..145ms; ACK 145..245ms; trailing guard 245..400ms.
- Tại subframe 0, 0..250ms dành Beacon. Tại subframe 1..4, 0..250ms là downlink. PCSS subframe i = `2000*i + [250,650)`. Kết thúc SF4 `[9850,10000)` là candidate JOIN window; 4 subframe trước là guard.
- `ACK_BITMAP` (candidate 15 bit) phản ánh thành công từ chu kỳ trước; bản tin khẩn cấp yêu cầu ACK sớm trong PCSS nếu có thời gian và RF budget. Không khẳng định ACK luôn đủ thời gian nếu va chạm hoặc radio đang TX.
- LoRa PHY không cấp "guaranteed free" trong CAD; collision/retry/radio turnaround làm thay đổi worst-case latency. Không sử dụng <3 s làm SLA.

## 2. Hợp đồng trao đổi lịch

Payload Backend→Gateway: `contracts/mqtt/schemas/schedule.schema.json`. Gateway phải kiểm `gateway_id`, auth transport, request ID, `expires_at`, lịch trùng/rollback, vẹn toàn cấu trúc thời gian, slot ownership, giới hạn airtime và phiên bản protocol. `schedule_version` rộng hơn `SCHED_VER` 8-bit trên bản candidate RF; **không được truncate** để tự quyết lịch mới.

| Trạng thái | Chủ sở hữu | Điều kiện chuyển | Báo cáo MQTT |
|---|---|---|---|
| PROPOSED | Backend | Planner tạo lịch chưa gửi | không |
| SENT | Backend | publish yêu cầu chưa xác nhận | không |
| STAGED | Gateway | shadow hợp lệ và persist, chọn activation horizon còn đủ quảng bá | `STAGE_ACK` (không phải ACTIVE) |
| REJECTED | Gateway/Backend | invalid/expired/conflict/airtime | `VERIFY_NACK` kèm code |
| ACTIVE | Gateway | **thực sự** kích hoạt tại đầu superframe đã định; beacon/active state được commit | `ACTIVE_REPORT` |
| EXPIRED | Backend | hết hạn trước activate / không có xác nhận kịp | trạng thái reconciliation; không tự cho là ACTIVE |

Không được thực thi lịch nhận qua MQTT lập tức giữa một superframe. `STAGE_ACK` không chứng minh các Node đều nhận được lịch. Gateway phải chọn `activate_at_superframe_seq` đủ xa để phát **tối thiểu 3 thông báo hoàn chỉnh** (nếu lựa chọn horizon =3), không chỉ tính `K+3` từ lúc vừa nhận MQTT ở giữa SF. Nên đòi Node xác nhận/quan sát epoch nếu thiết kế bảo mật cho phép; thiếu bằng chứng cập nhật thì Node phải bảo toàn an toàn bằng cách không phát khe lỗi thời.

## 3. Các bất biến và xử lý lỗi

- **Node chỉ TX DATA** nếu đã xác thực Beacon và phiên lịch, còn lease/slot hợp lệ, timer drift dưới guard đã thẩm định, airtime còn đủ.
- Beacon loss 1–2 lần: holdover **chỉ khi** drift/guard được chứng minh; từ lần thứ 3 (candidate) hoặc không thể xác thực: listen-only + recovery, không TX định kỳ theo slot cũ.
- Beacon báo phiên bản khác khi Node chưa có đầy đủ mapping hợp lệ: Node phải ngừng TX đến khi xác thực lịch mới; không đoán slot.
- Sau reset Gateway: nạp **active** được xác thực từ NVS; shadow chưa active không được kích hoạt âm thầm; bật beacon cục bộ không phụ thuộc MQTT. Sequence/epoch phải không khiến replay cũ thành hợp lệ.
- Gateway mất backend: tiếp tục lịch active nếu vẫn hợp lệ và tuân TX airtime, lưu buffer có giới hạn; không phát lịch hoặc lệnh đã hết hạn khi reconnect.
- Uniqueness: một slot data có nhiều nhất một Node chủ; offset/duration không giao nhau hoặc chèn lên Beacon, PCSS, guard. Các trường ID phải hợp lệ; semantic validation ngoài JSON Schema là bắt buộc.
- Half-duplex: TX Beacon/DL/ACK chỉ trong cửa sổ phù hợp, không vừa TX vừa nhận PCSS/data.

## 4. Kiểm thử chưa thực hiện

Các tình huống HIL bắt buộc: slot collision, late schedule arrival, duplicate MQTT, retained stale schedule, schedule rollover, mất một hoặc ba Beacon, reboot GW/Node trong staging, mất Wi-Fi, nhiều Alert cùng PCSS, ISR jitter, RF duty exhausted. **Kết quả: NOT_VERIFIED**; bản mô tả không phải test log.
