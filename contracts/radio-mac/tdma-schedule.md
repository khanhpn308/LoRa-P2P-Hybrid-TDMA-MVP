# TDMA Schedule — Backend Planner ↔ Gateway Executor ↔ Node

**Trạng thái:** `DRAFT / G1–G3 NOT_VERIFIED`. Các quy tắc C03/C04/C08 đã được Owner phê duyệt; thông số Superframe/Slot/Guard/ToA chưa được duyệt.

## 1. Quyền và phạm vi

- **Backend** tạo/version lịch và phân bổ khe; **User phê duyệt** lịch cùng **activation window**. Mỗi lịch thuộc đúng `gateway_id`, đúng kênh RF đã provision. `node_id` chỉ có nghĩa trong Gateway đó.
- **Gateway** kiểm tra auth/topic/identity, monotonic version, expiry, RF/half-duplex/airtime, xung đột slot và thời gian có thể tin cậy; chỉ được **từ chối/chặn TX không an toàn**, không được sửa `Slot Assignment` hoặc tự thay kênh.
- **Node** chỉ sử dụng lịch và cơ hội truyền đã xác thực; `Periodic OFF` không gửi dữ liệu chu kỳ nhưng vẫn được dùng cửa sổ cảnh báo nếu còn quyền C07.

## 2. Transaction chuyển lịch (C04)

| Pha | Điều kiện bắt buộc | Báo cáo |
|---|---|---|
| `PROPOSED` | Backend tạo version/epoch và lịch chưa kích hoạt | Không |
| `APPROVED` (review state) | User có quyền phê duyệt nội dung lịch **và activation window**; chưa kích hoạt | Backend lưu quyết định |
| `SENT` | Backend dispatch proposal còn hạn | MQTT PUBACK chỉ xác nhận vận chuyển |
| `STAGED` | Gateway kiểm tra và **persist Shadow**; ACK chuẩn bị của Node chịu ảnh hưởng/lease sẽ được kiểm chứng trước cutover | `STAGE_ACK` |
| `ACTIVE` | Gateway đã xác nhận affected Node chuẩn bị, old slot lease kết thúc an toàn và chuyển tại đầu Superframe **trong activation window** | `ACTIVE_REPORT` |
| `REJECTED/EXPIRED` | Không đủ auth/ACK/lease/timing/expiry/window hoặc lịch lỗi; không kích hoạt Shadow | `VERIFY_NACK`/Backend reconcile |

- **Owner-decided countdown:** Gateway phát **3 nhịp thông báo lịch hoàn chỉnh 3 → 2 → 1** trong các Superframe trước mốc chuyển, không tính nhịp bắt đầu giữa Superframe. Chỉ cutover tại ranh giới Superframe trong activation window khi đã có affected Node prepare ACK và old Slot Lease an toàn. Thiếu ACK, clock tin cậy, quyền hoặc lease safety thì **không** cutover; phải báo Backend, không tự dời mốc hoặc đổi slot.
- `STAGE_ACK` **không phải** Node prepare ACK hay bằng chứng kích hoạt. Ba Beacon/thông báo **không thay** affected Node prepare ACK và old lease safety.
- Sau reboot, Active/Shadow riêng; không tự promote Shadow. Nếu không chứng minh continuity identity/version/lease/time thì suppress affected TX; không cấp khe cũ cho Node mới sớm.
- Gateway lựa chọn mốc Superframe nội bộ trong khoảng đã duyệt, **không** chọn lại kế hoạch hoặc mở rộng khoảng. `expires_at` của đề xuất là deadline nhận/kích hoạt, **không phải** thời hạn của Active Schedule hay quyền thiết bị.
- Cơ chế prepare ACK, lease expiry, trust clock, activation-report reconciliation và rollback đầy đủ còn **OPEN G2/G3/G4**.

## 3. Phân xử các cơ hội truyền (C08)

- Một radio SX1276 bán song công: Beacon/downlink (Beacon gộp `ACK_BITMAP` Telemetry 2B theo CT-01-ACK-01), cửa sổ Alert tranh chấp, DATA, retry, Join và guard **không được chồng lấn TX/RX trái phép**. Không đặt `RF_ACK` Telemetry riêng sau mỗi DATA.
- Alert ưu tiên sử dụng cửa sổ contention với bounded backoff/CAD khi phù hợp; retry chỉ tại những cơ hội dự phòng hợp lệ trong lịch Backend/User đã duyệt. Gateway không được tự giành DATA Slot của Node khác.
- Beacon của Superframe `N+1` ACK Telemetry hợp lệ được Gateway persist trong Superframe `N`; tối đa một Telemetry uplink đang chờ ACK trên mỗi Node cho cơ chế này. Mất Beacon/bit ACK = 0 chỉ có nghĩa chưa được xác nhận; retry phải theo lịch đã phê duyệt. `PRIORITY_ALERT` không bị vô hiệu hóa bởi `Periodic OFF` hoặc Telemetry chờ ACK; cơ chế ACK Alert riêng còn OPEN G2.
- Quản hàng đợi/airtime/retry hữu hạn, theo dõi fairness và các trường hợp mất cảnh báo. Gói đang phát không thể bị ngắt tùy tiện; kênh có thể có hidden terminal/collision.

## 4. Profile thử nghiệm, không phải baseline production

`P-10S-15` mô tả **10.000 ms/Superframe, 5 subframe × 2.000 ms, 15 DATA slots**, trong bản nháp có Beacon/DL 250 ms, PCSS 400 ms, 3 DATA slots × 400 ms, guard 150 ms mỗi subframe. Các con số này **chỉ dành mock/simulation**, không được hardcode như contract đã phê duyệt. Các khung cần tính lại sau khi có frame authentication, ACK, ToA và guard thực tế.

## 5. Verification bắt buộc

- **Static/Contract:** validation version/identity, activation window, affected Node ACK, lease overlap/reuse, schedule conflict, malformed/wrong-scope/replayed reports.
- **Simulation:** 1–4 Gateway độc lập, 10–15 Node/cấu hình kiểm thử, nhiều Alert, OFF/ON, contention/fairness, retry/missing ACK.
- **HIL/RF:** ToA/guard/turnaround/jitter, sync loss/reboot, long offline, RF airtime/collision, legal limits.
- **Trạng thái:** `NOT_VERIFIED`; mọi giới hạn số học, SLA và acceptance threshold chờ evidence.

Xem [Radio MAC](specification.md), [MQTT Schedule](../mqtt/topics.md) và [Architecture](../../docs/architecture/system-overview.md).
