# TDMA Schedule Interface — Đặc tả Vận hành Lịch và Đồng bộ Thời gian

**Revision 0.2.0-draft · Hybrid TDMA & Maintenance Superframe · Issue #127 / Umbrella #125 · Gate G2: NOT_VERIFIED.**

---

## 1. Phân loại lại Profile Cũ P-10S-15 (OBSOLETE_HISTORICAL_BASELINE)

Profile cũ `P-10S-15` (5 subframes $\times$ 2000ms, mỗi subframe chứa 400ms khe tranh chấp PCSS và 3 khe dữ liệu) chính thức được đánh dấu là **`OBSOLETE_HISTORICAL_BASELINE`**.

**Lý do bãi bỏ:**
1. Kiến trúc hệ thống đã chuyển dịch hoàn toàn sang mô hình **Event-Only và Báo động tại chỗ (Local Alarm Autonomy)** theo Quyết định Owner (2026-11-04). Mọi khe tranh chấp PCSS và cơ chế thử lại ngẫu nhiên qua CAD đều bị triệt tiêu khỏi luồng dữ liệu chính.
2. Dữ liệu sự kiện khẩn cấp được báo động bằng còi/đèn tại chỗ ngay lập tức và được truyền tin RF độc quyền trong **Khe Dữ liệu Tĩnh (Static DATA Slot)** của Node.
3. Cơ chế xác nhận gói tin theo lô `ACK_BITMAP` (15 bit) trong Beacon chu kỳ sau bị hủy bỏ; thay vào đó là xác nhận tức thì trong khe `DOWN_EVENT_ACK` (0x42).

---

## 2. Kiến trúc Phân kỳ Superframe V2 (V2 Dual-Superframe Structure)

Hệ thống phân tách không gian thời gian RF thành hai cấu trúc Superframe luân phiên có chức năng chuyên biệt:

```
+-------------------------------------------------------------------------------------------------------+
|                                  KIẾN TRÚC PHÂN KỲ SUPERFRAME V2                                      |
+-------------------------------------------------------------------------------------------------------+
| 1. STATIC DATA SUPERFRAME (Chu kỳ danh định ~10s, thực thi liên tục):                                 |
|                                                                                                       |
|  [ Slot 0: SYNC/GUARD ] [ Slot 1: DATA N1 ] [ Slot 2: DATA N2 ] ... [ Slot N: DATA Nn ] [ GUARD ]     |
|                                                                                                       |
|  * Trong từng Slot DATA tĩnh:                                                                         |
|    - [ 0..25ms ]: Leading Guard Time (bù trừ jitter ngắt và trôi dạt đồng hồ)                        |
|    - [ 25..125ms ]: Node phát `UP_EVENT` (0x41, 26B, SF7 ToA ~61.7ms)                                 |
|    - [ 125..145ms ]: Gateway chuyển chế độ bán song công (RX -> TX turnaround) & ghi WAL             |
|    - [ 145..245ms ]: Gateway phát `DOWN_EVENT_ACK` (0x42, 19B, SF7 ToA ~51.5ms)                      |
|    - [ 245..400ms ]: Trailing Guard Time & Node chuyển trạng thái radio                              |
+-------------------------------------------------------------------------------------------------------+
| 2. MAINTENANCE SUPERFRAME (Chu kỳ danh định ~300s, xen kẽ định kỳ):                                   |
|                                                                                                       |
|  [ Slot 0: BEACON ] [ Slot 1: HEALTH N1 ] [ Slot 2: HEALTH N2 ] ... [ Slot N+1: CTRL_WINDOW ]         |
|                                                                                                       |
|  * Slot 0 (0..250ms): Gateway phát `DOWN_SYNC_BEACON` (0x43, 80B, ký số Ed25519)                      |
|  * Slot 1..N: Từng Node đang hoạt động phát `UP_HEALTH_REPLY` (0x44, 21B, AES-CCM) theo lịch chỉ định |
|  * Slot N+1 (Cuối chu kỳ): Cửa sổ kiểm soát chung (`CTRL_WINDOW`) phục vụ Join Handshake               |
|    (0x45 Hello) và bản tin xác nhận sẵn sàng `UP_JOIN_READY` (0x49)                                   |
+-------------------------------------------------------------------------------------------------------+
```

---

## 3. Rào chắn Vận hành (Operational Fences) & 8 Tầng Bảo vệ (8-Fold Guards)

Nhằm triệt tiêu tuyệt đối nguy cơ phát sóng sai khe gây xung đột hoặc sử dụng khóa chưa kích hoạt, mọi Node và Gateway bắt buộc phải tuân thủ 3 Rào chắn Vận hành:

### 3.1 Rào chắn 1: Khoanh vùng Khóa Phiên chưa kích hoạt (Fence 1 — `SESSION_READY_NOT_ACTIVE`)
- Khi hoàn tất bắt tay Join 4 bước và truyền `UP_JOIN_READY` (0x49), cặp khóa phiên mới sinh $K_{\text{SESSION\_UP}}$ và $K_{\text{SESSION\_DOWN}}$ được lưu vào bộ nhớ đệm Gateway và Node ở trạng thái **`INSTALLED_INACTIVE`**.
- Node tuyệt đối **CẤM** phát dữ liệu sự kiện (`UP_EVENT`) dưới bộ khóa mới cho đến khi bước qua ranh giới superframe kích hoạt $K_{\text{target}}$ được Gateway chỉ định.

### 3.2 Rào chắn 2: Đếm ngược Thông báo Lịch 3 chu kỳ (Fence 2 — $3 \to 2 \to 1$ Horizon)
- Khi Gateway nhận được lịch TDMA mới từ Backend hoặc cần kích hoạt phiên của Node mới, Gateway chọn mốc superframe kích hoạt $K_{\text{target}} \ge K_{\text{current}} + 3$.
- Gateway phát thông báo chuyển đổi lịch thông qua cờ đếm ngược trong `DOWN_SYNC_BEACON`:
  - Superframe $K$: Cờ `COUNTDOWN = 3`
  - Superframe $K+1$: Cờ `COUNTDOWN = 2`
  - Superframe $K+2$: Cờ `COUNTDOWN = 1`
  - Superframe $K+3$: Lịch mới chính thức trở thành `ACTIVE` (`COUNTDOWN = 0`).
- **Hàng rào 100%-READY:** Toàn bộ các Node bị ảnh hưởng bởi việc đổi lịch phải xác nhận đã sẵn sàng trước mốc cắt chuyển; nếu bất kỳ Node nào chưa sẵn sàng, Gateway giữ nguyên lịch cũ để bảo đảm an toàn.

### 3.3 Rào chắn 3: 8 Tầng Bảo vệ Fail-Closed trước khi Phát sóng (Fence 3 — 8-Fold Guards)
Trước khi bộ điều khiển radio chuyển chip SX1276 sang trạng thái phát sóng `FSTX` $\to$ `TX`, Node bắt buộc phải đánh giá tuần tự và vượt qua trọn vẹn 8 điều kiện:

1. **`GUARD_JOIN_ACTIVE` (Cổng 1):** Node phải ở trạng thái `NODE_ACTIVE_DATA_ELIGIBLE`. Node ở trạng thái `UNJOINED`, `JOINING` hoặc `SESSION_READY_NOT_ACTIVE` bị cấm phát sóng dữ liệu. Mã lỗi: `ERR_GUARD_NOT_JOINED`.
2. **`GUARD_SESSION_VALID` (Cổng 2):** Khóa $K_{\text{SESSION\_UP}}$ đã nạp, thời hạn phiên (lease) còn hiệu lực, và bộ đếm `FRAME_COUNTER < 0xFFFFFFFE`. Mã lỗi: `ERR_GUARD_SESSION_INVALID`.
3. **`GUARD_SLOT_OWNERSHIP` (Cổng 3):** Bảng lịch hoạt động hiện hành xác nhận khe thời gian hiện tại (`current_slot`) thuộc quyền sở hữu của chính Node. Cấm phát sóng trong khe của Node khác hoặc khe chưa gán. Mã lỗi: `ERR_GUARD_UNASSIGNED_SLOT`.
4. **`GUARD_TIMING_WINDOW` (Cổng 4):** Bộ đếm thời gian khe $t_{\text{offset}}$ nằm trong cửa sổ cho phép: $t_{\text{offset}} \in [25\text{ms}, 125\text{ms}]$. Nếu trễ ngắt ISR vượt quá 125ms, lập tức hủy phát sóng để tránh đè sang khe tiếp theo. Mã lỗi: `ERR_GUARD_TIMING_WINDOW_VIOLATION`.
5. **`GUARD_CLOCK_SYNC` (Cổng 5):** Số lượng Beacon bị mất liên tiếp $N_{\text{MISSED}} < 3$, và sai số trôi dạt đồng hồ tích lũy ước tính $\tau_{\text{drift}} \le 25\text{ms}$. Mã lỗi: `ERR_GUARD_CLOCK_DESYNC`.
6. **`GUARD_AIRTIME_DUTY` (Cổng 6):** Hạn mức phát sóng tích lũy trong 1 giờ không vượt quá $1.0\%$ (quy định pháp lý thiết bị IoT), và bộ tích lũy token bucket đủ cho ToA gói tin hiện tại ($\ge 61.7\text{ms}$ tại SF7). Mã lỗi: `ERR_GUARD_AIRTIME_EXHAUSTED`.
7. **`GUARD_HALF_DUPLEX` (Cổng 7):** Đài SX1276 đang ở trạng thái `STANDBY`, không bận nhận gói tin khác, và không nằm trong ranh giới chuyển giao Superframe. Mã lỗi: `ERR_GUARD_HALF_DUPLEX_COLLISION`.
8. **`GUARD_RF_SAFETY` (Cổng 8):** Cấu hình tần số nằm trong dải VN920, công suất phát $\le +14\text{ dBm}$, và cờ phê duyệt an toàn RF vật lý đang tích cực (`#169_RF_SIGNED_OFF == TRUE`). Mã lỗi: `ERR_GUARD_RF_UNVERIFIED`.

---

## 4. Đồng bộ Đồng hồ, Giới hạn Trôi dạt & Chính sách Holdover

1. **Chuẩn hóa Ngưỡng Holdover Mất Beacon:**
   - **Mất 1 hoặc 2 Beacon liên tiếp ($N_{\text{MISSED}} \in \{1, 2\}$):** Node chuyển sang chế độ **Tạm duy trì an toàn (Graceful Holdover)** nếu ước tính độ trôi dạt thạch anh tích lũy $\tau_{\text{drift}} \le 25\text{ms}$. Node tiếp tục được phép truyền sự kiện trong khe tĩnh của mình.
   - **Mất từ 3 Beacon liên tiếp ($N_{\text{MISSED}} \ge 3$):** Độ trôi dạt đồng hồ tích lũy có nguy cơ vượt quá khoảng bảo vệ Guard Time 25ms. Node lập tức **khóa cứng phát sóng fail-closed**, chuyển sang trạng thái `RECOVERY_HOLD`, chỉ duy trì chế độ lắng nghe (listen-only) để thu nhận Beacon đồng bộ lại nhịp mạng.
2. **Quy tắc Thử lại Dữ liệu (Retry Rule):**
   - Nếu phát `UP_EVENT` mà không nhận được `DOWN_EVENT_ACK` hợp lệ trong cùng khe (do mất gói hoặc hỏng thẻ CCM), Node **CẤM** phát lại ngay lập tức hoặc phát trong khe tiếp theo của Node khác.
   - Bản tin sự kiện được giữ nguyên trong NVS FIFO và **chỉ được phép thử lại trong đúng Khe Tĩnh của chính Node ở Superframe dữ liệu kế tiếp**.
   - Khi vượt quá số lần thử lại tối đa (`MAX_RETRY_COUNT`), Node duy trì sự kiện trong FIFO theo chính sách `RING_BUFFER_DROP_OLDEST` (`DEC-127-04`).

---

## 5. Ràng buộc Spreading Factor và Đo đạc Vật lý (#169)

1. **Giới hạn Vận hành MVP V1 (DEC-127-03 Lựa chọn A — Owner Phê duyệt 2026-11-06):**
   - Toàn bộ luồng vận hành dữ liệu thời gian thực của MVP V1 **giới hạn nghiêm ngặt ở SF7 và SF8**.
   - Tại SF7 và SF8, thời gian chiếm sóng khứ hồi được kiểm soát an toàn tuyệt đối trong khe 400ms:
     $$\text{ToA}_{\text{roundtrip}} = \text{ToA}_{\text{EVENT}} (61.7\text{ms}) + \tau_{\text{turnaround}} (20\text{ms}) + \text{ToA}_{\text{ACK}} (51.5\text{ms}) \approx 133.2\text{ms} < 250\text{ms}$$
   - Độ dài khe 400ms sẽ được tái đánh giá và điều chỉnh sau khi có kết quả đo đạc vật lý thực địa từ Issue #169.
2. **Khóa Hằng số Số học Chờ Bằng chứng Vật lý:**
   - Tuyệt đối cấm tuyên bố vượt qua cổng G1/G2 hoặc đóng băng các hằng số Guard Time số học trước khi hoàn tất đo đạc trên phần cứng thật tại Issue #169.

---

## 6. Máy Trạng thái Vòng đời Lịch trên MQTT

| Trạng thái | Chủ sở hữu | Điều kiện chuyển tiếp | Bản tin MQTT phản hồi |
|---|---|---|---|
| `PROPOSED` | Backend | Lập lịch mới trong DB, chưa đẩy xuống Gateway | Không |
| `SENT` | Backend | Đã xuất bản lịch qua topic downlink MQTT QoS1 | Không |
| `STAGED` | Gateway | Nhận lịch hợp lệ, ghi nhớ bền vững, tính toán mốc kích hoạt $\ge K+3$ | `STAGE_ACK` (chưa phải ACTIVE) |
| `REJECTED` | Gateway | Lịch sai định dạng, hết hạn, xung đột sở hữu slot hoặc vượt airtime | `VERIFY_NACK` kèm mã lỗi |
| `ACTIVE` | Gateway | Chính thức kích hoạt tại đầu Superframe $K_{\text{target}}$ sau khi đủ 3 lần đếm ngược | `ACTIVE_REPORT` |
| `EXPIRED` | Backend | Lịch không được kích hoạt kịp thời hoặc mất kết nối quá hạn | Trạng thái điều hòa (Reconciliation) |
