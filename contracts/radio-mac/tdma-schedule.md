# TDMA Schedule Interface — profile P-10S-15 (đề xuất, chưa freeze)

**Nguồn:** kiến trúc đính kèm §5.1–5.3, §7.3–7.4 · #12, #14. **Giá trị thời gian chỉ là baseline để làm mock/simulator; G1/G2/G3 chưa PASS.**

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
