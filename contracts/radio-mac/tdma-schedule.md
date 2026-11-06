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
|  * Trong từng Slot DATA tĩnh (Hình minh họa SF7 — NON_NORMATIVE / NOT_VALID_FOR_SF8):                 |
|    - [ 0..25ms ]: Leading Guard Time (bù trừ jitter ngắt và trôi dạt đồng hồ)                        |
|    - [ 25..125ms ]: Node phát `UP_EVENT` (0x41, 26B, SF7 ToA 61.696ms; SF8 KHÔNG PHÙ HỢP)            |
|    - [ 125..145ms ]: Gateway chuyển chế độ bán song công (RX -> TX turnaround) & ghi WAL             |
|    - [ 145..245ms ]: Gateway phát `DOWN_EVENT_ACK` (0x42, 19B, SF7 ToA 51.456ms; SF8 KHÔNG PHÙ HỢP)  |
|    - [ 245..400ms ]: Trailing Guard Time & Node chuyển trạng thái radio                              |
+-------------------------------------------------------------------------------------------------------+
| 2. MAINTENANCE SUPERFRAME (Chu kỳ danh định ~300s, xen kẽ định kỳ):                                   |
|                                                                                                       |
|  [ Slot 0: BEACON ] [ Slot 1: HEALTH N1 ] [ Slot 2: HEALTH N2 ] ... [ Slot N+1: CTRL_WINDOW ]         |
|                                                                                                       |
|  * Slot 0 [0..250ms] (Hình minh họa SF7 — NON_NORMATIVE / NOT_VALID_FOR_SF8):                         |
|    Gateway phát `DOWN_SYNC_BEACON` (0x43, 80B, ký số Ed25519; SF7 ToA 143.616ms; SF8 KHÔNG PHÙ HỢP)  |
|  * Slot 1..N: Từng Node đang hoạt động phát `UP_HEALTH_REPLY` (0x44, 21B, AES-CCM) theo lịch chỉ định |
|  * Slot N+1 (Cuối chu kỳ): Cửa sổ kiểm soát chung (`CTRL_WINDOW`) phục vụ Join Handshake               |
|    (0x45 Hello) và bản tin xác nhận sẵn sàng `UP_JOIN_READY` (0x49)                                   |
+-------------------------------------------------------------------------------------------------------+
```

### 2.1 Bảng Đối chiếu Thời gian Chiếm sóng Lý thuyết (Theoretical ToA Baseline)

Tất cả số liệu dưới đây được tính toán từ công thức giải tích chuẩn Semtech SX1276 (Datasheet Rev 7, Mục 4.1.1.5–4.1.1.7) với tham số: **BW 125 kHz, CR 4/5 ($CR=1$), Preamble 8 symbols, Explicit PHY Header, PHY CRC Enabled**.

> [!IMPORTANT]
> **Phân loại xuất xứ (Provenance):** Các giá trị ToA này mang nhãn `CALCULATED` (kết quả giải tích lý thuyết thuần túy), **KHÔNG** phải số liệu đo kiểm RF thực tế từ bench test. Toàn bộ các độ trễ phần cứng ($\tau_{\text{turnaround}}$, $\tau_{\text{WAL}}$, $\tau_{\text{jitter}}$, $\tau_{\text{drift}}$) là giả định kỹ thuật chờ kiểm chứng thực địa tại Issue #169.

| Loại bản tin | Mã Hex | Cỡ (B) | SF | Preamble (ms) | Payload (ms) | ToA Lý thuyết (ms) | Cửa sổ hình minh họa (ms) | Độ lệch / Đánh giá Khả thi |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `UP_EVENT` | `0x41` | 26 | SF7 | 12.544 | 49.152 | **61.696** | 100 ([25, 125)) | Dư +38.304ms $\to$ **FEASIBLE (SF7)** |
| `UP_EVENT` | `0x41` | 26 | SF8 | 25.088 | 88.064 | **113.152** | 100 ([25, 125)) | **Vượt -13.152ms $\to$ INFEASIBLE (SF8)** |
| `DOWN_EVENT_ACK` | `0x42` | 19 | SF7 | 12.544 | 38.912 | **51.456** | 100 ([145, 245)) | Dư +48.544ms $\to$ **FEASIBLE (SF7)** |
| `DOWN_EVENT_ACK` | `0x42` | 19 | SF8 | 25.088 | 77.824 | **102.912** | 100 ([145, 245)) | **Vượt -2.912ms $\to$ INFEASIBLE (SF8)** |
| `DOWN_SYNC_BEACON` | `0x43` | 80 | SF7 | 12.544 | 131.072 | **143.616** | 250 ([0, 250)) | Dư +106.384ms $\to$ **FEASIBLE (SF7)** |
| `DOWN_SYNC_BEACON` | `0x43` | 80 | SF8 | 25.088 | 231.424 | **256.512** | 250 ([0, 250)) | **Vượt -6.512ms $\to$ INFEASIBLE (SF8)** |
| `UP_HEALTH_REPLY` | `0x44` | 21 | SF7 | 12.544 | 44.032 | **56.576** | Phân bổ theo slot | **FEASIBLE (SF7)** |
| `UP_HEALTH_REPLY` | `0x44` | 21 | SF8 | 25.088 | 77.824 | **102.912** | Phân bổ theo slot | **FEASIBLE nếu slot $\ge 150\text{ms}$** |

### 2.2 Phân tích Mâu thuẫn Thời gian & Tính Khả thi (Inconsistency Analysis)

1. **Mâu thuẫn TIM-01 (Static DATA Slot tại SF8):**
   - **Cửa sổ con đơn lẻ:** `UP_EVENT` (26B) tại SF8 có $\text{ToA} = 113.152\text{ms}$, vượt quá cửa sổ con 100ms $[25, 125)\text{ms}$. `DOWN_EVENT_ACK` (19B) tại SF8 có $\text{ToA} = 102.912\text{ms}$, vượt quá cửa sổ con 100ms $[145, 245)\text{ms}$.
   - **Phong bì truyền tin hai chiều:** Phong bì minh họa cũ $[25, 245)\text{ms}$ (tổng thời lượng 220ms) phân bổ cho cả Event TX, ACK TX và chuyển đổi RX $\leftrightarrow$ TX. Tại SF8:
     $$\text{ToA}_{\text{EVENT}}(\text{SF8}) + \tau_{\text{turnaround}} + \text{ToA}_{\text{ACK}}(\text{SF8}) = 113.152 + 20 + 102.912 = 236.064\text{ms} > 220.0\text{ms}$$
     Vượt quá phong bì **16.064ms** ngay cả khi chưa tính đến độ trễ ghi bền vững SQLite WAL tại Gateway ($\tau_{\text{WAL}}$), jitter ngắt và khoảng bảo vệ dự phòng.
   - **Kết luận TIM-01:** Phân bổ cửa sổ con $100\text{ms} / 20\text{ms} / 100\text{ms}$ và phong bì 220ms là **HOÀN TOÀN KHÔNG KHẢ THI TẠI SF8**. Hình minh họa cũ được chính thức dán nhãn `NON_NORMATIVE_EXAMPLE / SF7_ONLY_ILLUSTRATION (NOT_VALID_FOR_SF8)`.

2. **Mâu thuẫn TIM-02 (Maintenance Slot 0 Beacon 80B tại SF8):**
   - Bản tin `DOWN_SYNC_BEACON` (80B, mang chữ ký số Ed25519 64B theo `DEC-MH-01`) có $\text{ToA} = 256.512\text{ms}$ tại SF8.
   - Thời gian này vượt quá độ dài cửa sổ Slot 0 (250ms) là **6.512ms** khi chưa hề tính đến khoảng bảo vệ (Guard Time) hay độ trễ khởi động modem.
   - **Kết luận TIM-02:** Khẳng định "Beacon 80B truyền an toàn trong cửa sổ 250ms" là **SAI LẦM KHI VẬN HÀNH TẠI SF8**. Cửa sổ 250ms chỉ khả thi khi Beacon được phát tại SF7 ($\text{ToA} = 143.616\text{ms}$, biên an toàn 106.384ms).

### 2.3 Bất đẳng thức Biểu tượng và Ràng buộc Thẩm định Khe (Symbolic Inequalities)

Để bảo đảm tính an toàn fail-closed, bộ lập lịch TDMA và các bộ thẩm định (validators) bắt buộc phải kiểm tra hệ bất đẳng thức biểu tượng sau cho mỗi cấu hình khe TDMA danh định $T_{\text{slot}}$ (ví dụ 400ms):

$$\begin{cases}
W_{\text{UP\_EVENT}} \ge \text{ToA}_{\text{UP\_EVENT}}(\text{SF}) + \tau_{\text{jitter\_Node}} \\
W_{\text{GAP}} \ge \tau_{\text{turnaround\_GW}} + \tau_{\text{WAL\_GW}} \\
W_{\text{DOWN\_ACK}} \ge \text{ToA}_{\text{DOWN\_ACK}}(\text{SF}) + \tau_{\text{jitter\_GW}} \\
W_{\text{lead}} + W_{\text{UP\_EVENT}} + W_{\text{GAP}} + W_{\text{DOWN\_ACK}} + W_{\text{trail}} \le T_{\text{slot}} \\
T_{\text{slot}} \ge W_{\text{lead}} + \text{ToA}_{\text{EVENT}} + \tau_{\text{turnaround\_GW}} + \tau_{\text{WAL\_GW}} + \text{ToA}_{\text{ACK}} + \tau_{\text{turnaround\_Node}} + W_{\text{trail}} + 2 \cdot \tau_{\text{drift\_max}}
\end{cases}$$

- **Quy tắc Fail-Closed:** Nếu thông số $\tau_{\text{WAL\_GW}}$ (độ trễ ghi SQLite/WAL tại Gateway) chưa được đo đạc chính thức hoặc vượt quá $W_{\text{GAP}} - \tau_{\text{turnaround}}$, bộ thẩm định lịch **bắt buộc phải từ chối lịch (`FAIL_CLOSED`)**.

### 2.4 Định hướng Kỹ thuật Được Duyệt & Phương án Ứng viên (DEC-127-06 & DEC-MH-07)

Theo Quyết định Định hướng của Project Owner (2026-11-06, Issue #201 / PR #202):

1. **Khắc phục TIM-01 — Cấu trúc Hình học Khe DATA Tham số hóa (`DEC-127-06` — `OWNER_APPROVED_DIRECTION / NOT_HIL_VERIFIED`):**
   - **Chủ trương được duyệt:** Giữ nguyên khả năng vận hành SF7 và SF8 cho hệ thống. Thời gian khe TDMA và các cửa sổ con **không bị đóng băng thành các hằng số số học cố định** ở giai đoạn này, mà được đặc tả dưới dạng **hệ thức tham số hóa được thẩm định tự động (parameterized, validator-checkable slot geometry)**.
   - **Phân định trách nhiệm kiến trúc:**
     - **Backend Go:** Lập kế hoạch phân bổ lịch, tham số hóa các cửa sổ con ($W_{\text{lead}}, W_{\text{UP\_EVENT}}, W_{\text{GAP}}, W_{\text{DOWN\_ACK}}, W_{\text{trail}}$) linh hoạt dựa trên cấu hình PHY thực tế (SF, BW, CR, preamble, payload) và phiên bản hóa lịch qua MQTT.
     - **Gateway:** Thẩm định tính khả thi của lịch nhận được bằng hệ bất đẳng thức biểu tượng; từ chối fail-closed nếu thiếu tham số đo đạc ($\tau_{\text{WAL}}$) hoặc vi phạm ngân sách; phát thông báo đếm ngược $3 \to 2 \to 1$ có chữ ký Ed25519 qua Beacon; thực thi đóng ngắt TX/RX theo lịch.
     - **Sensor Node:** Tuân thủ nghiêm ngặt lịch active; đánh giá 8 tầng bảo vệ fail-closed trước khi phát sóng.
     - **Bảo lưu an toàn:** Giữ nguyên hàng rào đếm ngược 3 chu kỳ ($3 \to 2 \to 1$) và yêu cầu 100%-READY (`DEC-SEC-05`).
   - **Ví dụ ứng viên (Candidate Example Only — Tuyệt đối không phải profile cố định):**
     Ví dụ khe 400ms với phân bổ $25\text{ms} \text{ lead} + 125\text{ms } (\text{UP\_EVENT}) + 35\text{ms } (\text{GW Turnaround \& WAL}) + 115\text{ms } (\text{DOWN\_ACK}) + 100\text{ms} \text{ trail} = 400\text{ms}$ chỉ mang tính chất minh họa chứng minh tính khả thi về mặt số học lý thuyết cho SF8; **chưa được phê duyệt làm profile cố định**. Việc chốt hằng số bắt buộc chờ số liệu đo đạc thực tế từ Issue #169.

2. **Khắc phục TIM-02 — Tham số hóa Cửa sổ Beacon 80B (`DEC-MH-07` — `OWNER_APPROVED_DIRECTION / NOT_HIL_VERIFIED`):**
   - **Chủ trương được duyệt:** Giữ nguyên bố cục wire của gói tin đồng bộ `DOWN_SYNC_BEACON` (80B Ed25519, `DEC-MH-01`).
   - **Tham số hóa cửa sổ Beacon:** Cửa sổ phát Beacon trong Maintenance Superframe được tham số hóa theo SF đang áp dụng. Cửa sổ 400ms tại SF8 là ví dụ ứng viên (candidate example), không phải hằng số đóng băng; tùy chọn phát Beacon cố định ở SF7 ($\text{ToA} = 143.616\text{ms}$) là phương án dự phòng ứng viên. Cần đánh giá ngân sách thời gian Maintenance Superframe (~300s) và đo đạc HIL thực địa tại Issue #169.

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
4. **`GUARD_TIMING_WINDOW` (Cổng 4):** Bộ đếm thời gian khe $t_{\text{offset}}$ nằm trong cửa sổ truyền tin hợp lệ của cấu hình khe hiện hành: $t_{\text{offset}} \in [t_{\text{tx\_start}}, t_{\text{tx\_end}}]$ (với hình minh họa SF7 danh định là $[25\text{ms}, 125\text{ms}]$, còn với ứng viên SF8 là $[25\text{ms}, 150\text{ms}]$ theo `DEC-127-06`). Nếu trễ ngắt ISR vượt quá $t_{\text{tx\_end}}$, Node lập tức hủy phát sóng fail-closed để tránh đè sang khoảng turnaround và khe tiếp theo. Mã lỗi: `ERR_GUARD_TIMING_WINDOW_VIOLATION`.
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

1. **Giới hạn Vận hành MVP V1 (DEC-127-03 Lựa chọn A — Owner Phê duyệt 2026-11-06; Bổ chính TIM-01/TIM-02):**
   - Toàn bộ luồng vận hành dữ liệu thời gian thực của MVP V1 **giới hạn nghiêm ngặt ở SF7 và SF8**.
   - **Đối chiếu ToA khứ hồi hai chiều:**
     - **Tại SF7:** $\text{ToA}_{\text{EVENT}} (61.696\text{ms}) + \tau_{\text{turnaround}} (20\text{ms}) + \text{ToA}_{\text{ACK}} (51.456\text{ms}) \approx 133.152\text{ms} < 250\text{ms}$. Hoàn toàn vừa vặn trong phong bì minh họa $[25, 245)\text{ms}$ (220ms) và khe 400ms.
     - **Tại SF8:** $\text{ToA}_{\text{EVENT}} (113.152\text{ms}) + \tau_{\text{turnaround}} (20\text{ms}) + \text{ToA}_{\text{ACK}} (102.912\text{ms}) \approx 236.064\text{ms} > 220\text{ms}$. Vượt quá phong bì $[25, 245)\text{ms}$, dù tổng ToA RF lý thuyết ($216.064\text{ms}$) vẫn nằm trong giới hạn khe 400ms (biên còn lại $183.936\text{ms}$).
   - **Bổ chính (`DEC-127-06` — `OWNER_APPROVED_DIRECTION / NOT_HIL_VERIFIED`):** Hình minh họa cửa sổ con cũ $100\text{ms} / 20\text{ms} / 100\text{ms}$ không áp dụng cho SF8. Theo Quyết định Định hướng của Owner, cấu trúc hình học khe TDMA không đóng băng cứng nhắc ở hằng số 400ms hay bộ số cố định, mà được đặc tả dưới dạng hệ thức tham số hóa được thẩm định tự động fail-closed. Bộ số ví dụ minh họa ($25+125+35+115+100=400\text{ms}$) là hình minh họa ứng viên, không phải profile cố định. Việc chốt hằng số bắt buộc kiểm chứng thực tế tại Issue #169.
   - Độ dài khe và các cửa sổ con sẽ được tái đánh giá và điều chỉnh sau khi có kết quả đo đạc vật lý thực địa từ Issue #169.
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
