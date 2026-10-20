# MODULE 01 — BÀI TẬP 1.11–1.12, KIỂM TRA VÀ ĐÁP ÁN

[← Quay lại lý thuyết và Bài tập 1.1–1.10](./Module_01_PHY_LoRa.md)

---

### 🛠️ BÀI TẬP 1.11: TÍNH TỐC ĐỘ TRUNG BÌNH DÀI HẠN VỚI QUY ĐỊNH 1% DUTY CYCLE (USMB Cuốn 1, Chương 3.2.6, Trang 30)

- **[Đề bài gốc & Bối cảnh kỹ thuật]:**
  *Nguồn:* Giáo trình USMB Cuốn 1, Trang 30.
  Tiếp tục với bài toán truyền $`1\text{ byte}`$ cảm biến trong mạng LoRaWAN ở Bài tập 1.10. Hãy tính tốc độ truyền dữ liệu trung bình dài hạn ($`\text{bitrate}_{\text{average 1\%}}`$) khi thiết bị bắt buộc phải tuân thủ quy định pháp lý $`1\%`$ Duty Cycle trên băng tần EU868 cho cả hai trường hợp SF7 và SF12.

- **[Phân tích & Công thức áp dụng]:**
  Quy định $`1\%`$ Duty Cycle yêu cầu tỷ lệ thời gian phát sóng không vượt quá $`1/100`$ tổng thời gian:
  $`\displaystyle \text{bitrate}_{\text{average 1\%}} = \frac{\text{bitrate}_{\text{LoRaWAN useful}}}{100}`$
  Hoặc tính theo chu kỳ phát tối thiểu:
  $`\displaystyle T_{\text{period}} = T_{\text{ToA}} \times 100 \implies \text{bitrate}_{\text{average 1\%}} = \frac{8\text{ bits}}{T_{\text{period}}}`$
- **[Lời giải chi tiết từng bước (Step-by-step)]:**
  1. *Trường hợp 1 (SF7):*
     - Thời gian phát: $`T_{\text{on}} = 46.3\text{ ms} = 0.0463\text{ s}`$.
     - Thời gian im lặng bắt buộc: $`T_{\text{off}} = 99 \times 0.0463\text{ s} = 4.5837\text{ s}`$.
     - Chu kỳ phát tối thiểu: $`T_{\text{period}} = 46.3\text{ ms} + 4583.7\text{ ms} = 4.63\text{ s}`$.
     - Tốc độ bit trung bình dài hạn:
       $`\displaystyle \text{bitrate}_{\text{average (SF7)}} = \frac{172.7\text{ bps}}{100} = \mathbf{1.73\text{ bps}} \quad \left(\text{hoặc } \frac{8\text{ bits}}{4.63\text{ s}} \approx 1.728\text{ bps}\right)`$
  2. *Trường hợp 2 (SF12):*
     - Thời gian phát: $`T_{\text{on}} = 1155.1\text{ ms} = 1.1551\text{ s}`$.
     - Thời gian im lặng bắt buộc: $`T_{\text{off}} = 99 \times 1.1551\text{ s} = 114.3549\text{ s}`$ ($`\approx 1.9\text{ phút}`$).
     - Chu kỳ phát tối thiểu: $`T_{\text{period}} = 1.1551 \times 100 = 115.51\text{ s}`$.
     - Tốc độ bit trung bình dài hạn:
       $`\displaystyle \text{bitrate}_{\text{average (SF12)}} = \frac{6.9\text{ bps}}{100} = \mathbf{0.07\text{ bps}}`$
- **[Đáp số chuẩn & Bài học kỹ thuật rút ra]:**
  $`\displaystyle \mathbf{\text{SF7 average: } 1.73\text{ bps} \quad\mid\quad \text{SF12 average: } 0.07\text{ bps}}`$
  *Bài học kỹ thuật:* Khi thiết bị chạy ở SF12, sau khi phát một gói tin $`14\text{ bytes}`$ mất $`1.15\text{ giây}`$, nó bắt buộc phải im lặng tuyệt đối gần $`2\text{ phút}`$ trên phân băng đó. Nếu thiết kế hệ thống yêu cầu gửi dữ liệu liên tục mỗi 30 giây thì bắt buộc phải chuyển sang SF7 hoặc dùng kỹ thuật nhảy kênh.

---

### 🛠️ BÀI TẬP 1.12: TÍNH TOÁN GIẢI TÍCH SỐ SYMBOL VÀ TOA GÓI 14 BYTES (USMB Cuốn 1, Chương 3.3.1, Trang 31–32)

- **[Đề bài gốc & Bối cảnh kỹ thuật]:**
  *Nguồn:* Giáo trình USMB Cuốn 1, Trang 31–32.
  Kiểm chứng lại giá trị Time on Air $`46.3\text{ ms}`$ của khung tin $`14\text{ bytes}`$ (SF7, BW 125 kHz, CR 4/5) bằng công thức giải tích chuẩn của Semtech. 
  Các tham số đầu vào gồm:
  - Số symbol preamble: $`n_{\text{preamble}} = 8`$.
  - Kích thước tải trọng PHY: $`\text{Payload} = 14\text{ bytes}`$.
  - Hệ số trải phổ: $`\text{SF} = 7`$.
  - Băng thông: $`\text{BW} = 125\text{ kHz}`$.
  - Chế độ Header: Explicit Header ($`H = 0`$).
  - Tối ưu hóa tốc độ thấp: $`\text{DE} = 0`$.
  - Tỷ lệ mã hóa: $`\text{CR} = 1`$ (ứng với phân số $`4/5`$).
  - Cờ kiểm tra toàn vẹn: $`\text{CRC} = 1`$ (gói Uplink có CRC $`16\text{ bits}`$).

- **[Phân tích & Công thức áp dụng]:**
  1. Công thức tính tổng số symbol $`n_{\text{symbol}}`$:
     $`\displaystyle n_{\text{symbol}} = (n_{\text{preamble}} + 4.25) + 8 + \max\left( \left\lceil \frac{8 \cdot \text{Payload} - 4 \cdot \text{SF} + 28 + 16 \cdot \text{CRC} - 20 \cdot H}{4(\text{SF} - 2 \cdot \text{DE})} \right\rceil (\text{CR} + 4), \; 0 \right)`$
  2. Thời gian truyền 1 symbol:
     $`\displaystyle T_{\text{symbol}} = \frac{2^{\text{SF}}}{\text{BW}}`$
  3. Tổng thời gian chiếm sóng:
     $`\displaystyle T_{\text{ToA}} = n_{\text{symbol}} \cdot T_{\text{symbol}}`$
- **[Lời giải chi tiết từng bước (Step-by-step)]:**
  1. *Tính toán số học trong biểu thức Ceiling:*
     - Tử số:
       $`\displaystyle \text{Tử số} = 8 \cdot 14 - 4 \cdot 7 + 28 + 16 \cdot 1 - 20 \cdot 0`$
       $`\displaystyle \text{Tử số} = 112 - 28 + 28 + 16 - 0 = 112 + 16 = \mathbf{128}`$
     - Mẫu số:
       $`\displaystyle \text{Mẫu số} = 4 \cdot (\text{SF} - 2 \cdot \text{DE}) = 4 \cdot (7 - 2 \cdot 0) = 4 \cdot 7 = \mathbf{28}`$
     - Phép chia và làm tròn lên:
       $`\displaystyle \frac{\text{Tử số}}{\text{Mẫu số}} = \frac{128}{28} \approx 4.5714`$
       $`\displaystyle \left\lceil 4.5714 \right\rceil = \mathbf{5}`$
  2. *Tính số symbol phần Payload:*
     $`\displaystyle n_{\text{payload-core}} = 5 \cdot (\text{CR} + 4) = 5 \cdot (1 + 4) = 5 \cdot 5 = \mathbf{25\text{ symbols}}`$
     $`\displaystyle n_{\text{payload}} = 8 + 25 = \mathbf{33\text{ symbols}}`$
  3. *Tính tổng số symbol của toàn bộ khung LoRa ($`n_{\text{symbol}}`$):*
     $`\displaystyle n_{\text{preamble-total}} = 8 + 4.25 = \mathbf{12.25\text{ symbols}}`$
     $`\displaystyle n_{\text{symbol}} = 12.25 + 33 = \mathbf{45.25\text{ symbols}}`$
  4. *Tính thời gian truyền 1 symbol ($`T_{\text{symbol}}`$):*
     $`\displaystyle T_{\text{symbol}} = \frac{2^7}{125\,000} = \frac{128}{125\,000} = 0.001024\text{ s} = \mathbf{1.024\text{ ms}}`$
  5. *Tính tổng thời gian Time on Air ($`T_{\text{ToA}}`$):*
     $`\displaystyle T_{\text{ToA}} = 45.25 \times 1.024\text{ ms} = \mathbf{46.336\text{ ms}} \approx \mathbf{46.3\text{ ms}}`$
- **[Đáp số chuẩn & Bài học kỹ thuật rút ra]:**
  $`\displaystyle \mathbf{n_{\text{symbol}} = 45.25\text{ symbols} \quad\mid\quad T_{\text{symbol}} = 1.024\text{ ms} \quad\mid\quad T_{\text{ToA}} = 46.3\text{ ms}}`$
  *Bài học kỹ thuật:* Phép tính giải tích chứng minh sự chính xác tuyệt đối của công thức Semtech. Nắm vững công thức này cho phép kỹ sư nhúng lập trình tính toán ToA ngay trên vi điều khiển ESP32/STM32 mà không cần kết nối mạng.

---
## 5. BÀI TEST KIỂM TRA CUỐI MODULE (END-OF-MODULE ASSESSMENT)

---

### PHẦN A: 5 CÂU HỎI TRẮC NGHIỆM TÌNH HUỐNG KỸ THUẬT (SCENARIO-BASED MCQS)

#### Câu 1: Khắc phục sự cố thu tín hiệu dưới tầng nhiễu nền
Một kỹ sư IoT triển khai trạm quan trắc sạt lở đất trên vùng núi cao, kết nối về Gateway đặt tại trụ sở cách đó $`12\text{ km}`$. Thiết bị đang phát ở cấu hình $`\text{SF} = 9`$, $`\text{BW} = 125\text{ kHz}`$, công suất phát $`+14\text{ dBm}`$. Tại trạm Gateway, kỹ sư kiểm tra nhật ký bắt gói (Packet Log) thì thấy mức công suất thu đo được là $`\text{RSSI} = -118\text{ dBm}`$ và tỷ số tín hiệu trên nhiễu là $`\text{SNR} = -16.2\text{ dB}`$. Tuy nhiên, Gateway báo lỗi giải điều chế và **rớt toàn bộ 100% các gói tin** từ nút cảm biến này. Biết độ nhạy thu của chip SX1276 ở SF9 là $`-128.5\text{ dBm}`$. 

Nguyên nhân kỹ thuật cốt lõi khiến Gateway không thể giải mã được gói tin là gì?
A. Mức tín hiệu $`\text{RSSI} = -118\text{ dBm}`$ đã rơi xuống dưới ngưỡng độ nhạy thu tối thiểu của máy thu.  
B. Tỷ số $`\text{SNR} = -16.2\text{ dB}`$ đã vượt quá giới hạn chịu nhiễu tối thiểu của SF9 ($`\text{SNR}_{\text{limit}} = -12.5\text{ dB}`$).  
C. Khoảng cách $`12\text{ km}`$ đã vượt quá giới hạn suy hao không gian tự do tối đa của sóng vô tuyến $`868\text{ MHz}`$.  
D. Gateway bị nghẽn kênh do nút cảm biến vi phạm quy định $`1\%`$ Duty Cycle của Liên minh Châu Âu.

---

#### Câu 2: Lỗi phần cứng và thanh ghi khi chuyển sang SF cao
Một kỹ sư lập trình firmware cho module thu phát Semtech SX1276 giao tiếp với ESP32 qua bus SPI. Khi thử nghiệm truyền nhận ở các cấu hình $`\text{SF} = 7`$, $`\text{SF} = 8`$ và $`\text{SF} = 10`$ trên kênh $`868.1\text{ MHz}`$ ($`\text{BW} = 125\text{ kHz}`$), thiết bị hoạt động hoàn hảo với tỷ lệ nhận gói $`100\%`$. Tuy nhiên, khi chuyển sang cấu hình $`\text{SF} = 12`$ để tăng cự ly truyền, Gateway đặt cách đó $`50\text{ mét}`$ hoàn toàn không nhận được bất kỳ bản tin nào, Gateway log không ghi nhận được sự hiện diện của gói tin dù đèn LED báo phát trên mạch vẫn sáng.

Thao tác cấu hình nào kỹ sư đã bỏ sót trong thanh ghi của chip SX1276?
A. Chưa tăng công suất phát trong thanh ghi `RegPaConfig` lên mức tối đa $`+20\text{ dBm}`$.  
B. Chưa bật cờ `LowDataRateOptimize` (Bit 3 trong thanh ghi `RegModemConfig3`) khi thời gian truyền symbol $`T_{\text{symbol}} > 16.38\text{ ms}`$.  
C. Chưa kích hoạt chế độ Implicit Header Mode vì SF12 không hỗ trợ Explicit Header.  
D. Chưa nạp giá trị Sync Word `0x34` vì SF12 bắt buộc phải dùng mạng Private với Sync Word `0x12`.

---

#### Câu 3: Kỹ thuật xử lý cảnh báo khẩn cấp tuân thủ Duty Cycle
Một trạm đo thủy văn quan trắc mực nước hồ đập thủy điện hoạt động trên băng tần EU868. Thiết bị vừa gửi xong một gói tin định kỳ trên kênh $`868.1\text{ MHz}`$ (thuộc phân băng Sub-band g: $`868.0 - 868.6\text{ MHz}`$) với thời gian phát sóng $`\text{ToA} = 100\text{ ms}`$. Đúng $`1\text{ giây}`$ sau khi phát xong, cảm biến phát hiện mực nước vượt ngưỡng báo động lũ và cần gửi ngay lập tức một gói tin khẩn cấp về trung tâm điều hành.

Theo quy định pháp lý ETSI EN 300 220 và thiết kế kỹ thuật tối ưu, firmware của thiết bị phải xử lý như thế nào để gửi được cảnh báo tức thì mà **không vi phạm luật viễn thông**?
A. Tiếp tục phát ngay trên kênh $`868.1\text{ MHz}`$ vì các gói tin cảnh báo khẩn cấp (Emergency Alarm) được miễn trừ hoàn toàn quy định Duty Cycle.  
B. Bắt buộc vi điều khiển phải chờ đủ thời gian nghỉ $`T_{\text{off}} = 99 \times 100\text{ ms} = 9.9\text{ giây}`$ trên kênh $`868.1\text{ MHz}`$ rồi mới được phát tin cảnh báo.  
C. Chuyển tần số phát sóng sang một kênh thuộc phân băng khác, ví dụ kênh $`867.1\text{ MHz}`$ (thuộc Sub-band g1) hoặc kênh $`869.525\text{ MHz}`$ (thuộc Sub-band g3 có Duty Cycle $`10\%`$).  
D. Giảm công suất phát xuống $`0\text{ dBm}`$ để được phép phát sóng tự do mà không bị ràng buộc bởi Duty Cycle.

---

#### Câu 4: Phân bổ Ngân sách đường truyền và Cự ly truyền
Một hệ thống IoT truyền thông điểm-điểm (P2P) ngoài trời sử dụng hai module LoRa SX1262 ở tần số $`868\text{ MHz}`$ với cấu hình $`\text{SF} = 12`$, $`\text{BW} = 125\text{ kHz}`$. Các thông số phần cứng được đo đạc như sau:
- Công suất phát hiệu dụng tại đầu ra chip: $`P_T = +14\text{ dBm}`$.
- Độ nhạy thu của chip ở SF12/BW125: $`\text{Sensitivity} = -148\text{ dBm}`$.
- Ăng-ten phát có độ lợi: $`G_T = +3\text{ dBi}`$, suy hao cáp nối phát: $`L_{\text{cable1}} = 1\text{ dB}`$.
- Ăng-ten thu có độ lợi: $`G_R = +3\text{ dBi}`$, suy hao cáp nối thu: $`L_{\text{cable2}} = 1\text{ dB}`$.

Hỏi tổng quỹ suy hao đường truyền trong không gian tự do tối đa ($`L_{\text{air-max}}`$) mà hệ thống có thể chịu đựng được là bao nhiêu để tín hiệu vẫn đến được đầu vào máy thu ở mức tối thiểu bằng độ nhạy thu?
A. $`162\text{ dB}`$  
B. $`164\text{ dB}`$  
C. $`166\text{ dB}`$  
D. $`158\text{ dB}`$

---

#### Câu 5: Tác động của việc tăng Spreading Factor lên Tài nguyên mạng
Một kỹ sư mạng quyết định cấu hình cố định toàn bộ $`1000`$ cảm biến công tơ điện trong một khu đô thị chạy ở $`\text{SF} = 12`$ thay vì sử dụng giải thuật thích ứng ADR (vốn phân bổ phần lớn node về $`\text{SF} = 7`$). Kỹ sư lập luận rằng: *"Chạy SF12 sẽ giúp toàn bộ mạng đạt tầm xa tối đa và không bao giờ bị mất kết nối"*.

Đánh giá nào sau đây phản ánh chính xác nhất hậu quả kỹ thuật của quyết định này?
A. Không có hậu quả nào vì các gói tin LoRa có khả năng trực giao hoàn hảo nên $`1000`$ thiết bị phát đồng thời không thể gây xung đột.  
B. Thời gian chiếm sóng (Time on Air) của mỗi gói tin tăng gấp khoảng $`25`$ lần, dẫn đến xác suất va chạm xung đột gói (Collision Rate) tăng vọt, mạng bị nghẽn dung lượng và tuổi thọ pin của các nút giảm sút nghiêm trọng.  
C. Tốc độ truyền dữ liệu của mạng tăng lên vì SF12 mã hóa được $`12\text{ bits}`$ trên mỗi symbol thay vì chỉ $`7\text{ bits}`$ như SF7.  
D. Gateway sẽ tự động từ chối kết nối vì chuẩn LoRaWAN quốc tế cấm tuyệt đối việc sử dụng SF12 cho các thiết bị đầu cuối thông thường.

---

### PHẦN B: 3 BÀI TOÁN TỰ LUẬN TÍNH TOÁN & THIẾT KẾ THỰC TẾ (PROBLEM SOLVING)

#### Bài toán 1: Thiết kế Ngân sách đường truyền cho Hệ thống Phao biển Quan trắc
Một trạm phao hải văn trên biển cách đất liền $`22\text{ km}`$ cần truyền dữ liệu khí tượng về Gateway đặt trên ngọn hải đăng ở độ cao $`50\text{ m}`$. Hệ thống sử dụng công nghệ LoRa ở kênh $`868\text{ MHz}`$, băng thông $`\text{BW} = 125\text{ kHz}`$.
1. Tính công suất phát tối đa hợp chuẩn EU868 ($`P_T = +14\text{ dBm}`$) sang đơn vị mili-Watt ($`\text{mW}`$).
2. Sử dụng mô hình suy hao không gian tự do đơn giản hóa của giáo trình USMB ($`\text{Loss} = 10 \log_{10}(D^2 \cdot F^2 \cdot 1755)`$, với $`D`$ tính bằng km, $`F`$ tính bằng MHz), hãy tính toán độ suy hao không gian $`L_{\text{air}}`$ trên cự ly $`D = 22\text{ km}`$ ở tần số $`F = 868\text{ MHz}`$.
3. Giả sử ăng-ten phao biển có độ lợi $`G_T = +2\text{ dBi}`$, ăng-ten hải đăng có độ lợi $`G_R = +6\text{ dBi}`$, suy hao tổng của hai đầu cáp nối là $`L_{\text{cable}} = 2\text{ dB}`$. Hãy tính mức công suất thu $`P_R`$ (RSSI) tại đầu vào máy thu Gateway.
4. Để đảm bảo hệ thống hoạt động ổn định với biên độ dự trữ suy hao do thời tiết xấu (Fade Margin) tối thiểu là $`\mathbf{M \ge 12\text{ dB}}`$, hãy tra cứu bảng độ nhạy thu của chip SX1262 (SF7: $`-123\text{ dBm}`$, SF8: $`-126\text{ dBm}`$, SF9: $`-128.5\text{ dBm}`$, SF10: $`-131\text{ dBm}`$, SF11: $`-133.5\text{ dBm}`$, SF12: $`-136\text{ dBm}`$) và chỉ ra Spreading Factor tối thiểu ($`\text{SF}_{\min}`$) cần phải cấu hình.

---

#### Bài toán 2: Tính toán Time on Air và Lập lịch phát sóng chuẩn Duty Cycle & TTN FAP
Một công tơ nước thông minh (Smart Water Meter) sử dụng modem LoRaWAN truyền định kỳ gói tin trạng thái. Mỗi lần truyền, ứng dụng gửi $`18\text{ bytes}`$ dữ liệu người dùng (User Data Payload). Biết giao thức LoRaWAN chèn thêm $`13\text{ bytes}`$ tiêu đề MAC. Modem hoạt động ở băng thông $`\text{BW} = 125\text{ kHz}`$, tỷ lệ mã hóa $`\text{CR} = 4/5`$ ($`\text{CR} = 1`$), số symbol preamble $`n_{\text{preamble}} = 8`$, chế độ Explicit Header ($`H = 0`$), có cờ $`\text{CRC} = 1`$.
1. Hãy tính kích thước toàn phần của LoRa PHY Payload ($`\text{PL}`$).
2. Áp dụng công thức giải tích Semtech, hãy tính toán chi tiết số lượng symbol của Payload ($`n_{\text{payload}}`$), tổng số symbol ($`n_{\text{symbol}}`$), và thời gian phát sóng toàn phần ($`T_{\text{ToA}}`$ tính bằng mili-giây) khi thiết bị hoạt động ở cấu hình $`\mathbf{\text{SF} = 7}`$ ($`\text{DE} = 0`$).
3. Cũng với gói tin trên, hãy tính lại $`T_{\text{ToA}}`$ khi thiết bị hoạt động ở cấu hình $`\mathbf{\text{SF} = 12}`$ (Lưu ý: Bắt buộc kích hoạt cờ $`\text{DE} = 1`$).
4. Nếu thiết bị kết nối vào mạng cộng đồng The Things Network (TTN) với ràng buộc Fair Access Policy (tối đa $`30\text{ giây}`$ Uplink Airtime mỗi $`24\text{ giờ}`$):
   - Ở $`\text{SF} = 7`$, thiết bị được phép gửi tối đa bao nhiêu gói tin mỗi ngày? Khoảng thời gian tối thiểu giữa hai lần gửi là bao nhiêu phút?
   - Ở $`\text{SF} = 12`$, thiết bị được phép gửi tối đa bao nhiêu gói tin mỗi ngày? Khoảng thời gian tối thiểu giữa hai lần gửi là bao nhiêu phút?

---

#### Bài toán 3: Tối ưu hóa Năng lượng và Tuổi thọ Pin Thiết bị Đầu cuối
Một nút cảm biến đo độ ẩm đất trong nông nghiệp thông minh được cấp nguồn bởi một cell pin công nghiệp $`\text{Li-SOCl}_2`$ có điện áp danh định $`V_{dd} = 3.6\text{ V}`$, dung lượng danh định $`C = 2400\text{ mAh}`$. Sau khi trừ hệ số tự xả của pin ($`1\%/\text{năm}`$ trong 10 năm) và hệ số an toàn phóng điện, dung lượng hữu ích thực tế là $`C_{\text{eff}} = 1920\text{ mAh}`$.
Quy trình hoạt động của node cứ mỗi $`\mathbf{15\text{ phút}}`$ thức giấc một lần:
- Giai đoạn 1 (Đọc cảm biến): Mất $`T_{\text{sensor}} = 100\text{ ms}`$, dòng tiêu thụ $`I_{\text{sensor}} = 5\text{ mA}`$.
- Giai đoạn 2 (Phát sóng LoRa Uplink): Công suất phát $`+14\text{ dBm}`$, dòng tiêu thụ $`I_{\text{TX}} = 45\text{ mA}`$. Thời gian phát là $`T_{\text{ToA}}`$.
- Giai đoạn 3 (Mở 2 cửa sổ nhận RX1 và RX2): Tổng thời gian mở thu $`T_{\text{RX}} = 120\text{ ms}`$, dòng tiêu thụ $`I_{\text{RX}} = 11\text{ mA}`$.
- Giai đoạn 4 (Ngủ sâu Deep Sleep): Thời gian còn lại trong chu kỳ 15 phút, dòng rò ngủ sâu toàn mạch là $`I_{\text{sleep}} = 2.0\text{ }\mu\text{A}`$.

Yêu cầu:
1. Xét kịch bản A: Node ở gần Gateway, được cấu hình chạy ở $`\mathbf{\text{SF} = 7}`$ với $`T_{\text{ToA}} = 51.5\text{ ms}`$. Hãy tính điện lượng tiêu thụ trung bình trong một chu kỳ 15 phút ($`Q_{\text{cycle}}`$ tính bằng $`\text{mA}\cdot\text{s}`$) và dòng điện trung bình dài hạn ($`I_{\text{avg}}`$ tính bằng $`\mu\text{A}`$). Ước tính tuổi thọ hoạt động của pin (tính bằng năm).
2. Xét kịch bản B: Node ở xa Gateway, bị ép chạy ở $`\mathbf{\text{SF} = 12}`$ với $`T_{\text{ToA}} = 1318.9\text{ ms}`$. Hãy tính lại điện lượng tiêu thụ trung bình ($`Q_{\text{cycle}}`$), dòng trung bình ($`I_{\text{avg}}`$) và ước tính tuổi thọ pin (tính bằng năm).
3. Rút ra kết luận thiết kế hệ thống về lợi ích của thuật toán Adaptive Data Rate (ADR) đối với bài toán năng lượng.

---

### PHẦN C: ĐÁP ÁN & GIẢI THÍCH CHI TIẾT (ANSWER KEY)

#### Đáp án Phần A (Trắc nghiệm Tình huống):

- **Câu 1: Đáp án đúng là B**
  * *Tại sao B đúng:* Điều kiện thu nhận sóng LoRa đòi hỏi đồng thời cả hai yếu tố: $`\text{RSSI} \ge \text{Sensitivity}`$ VÀ $`\text{SNR} \ge \text{SNR}_{\text{limit}}`$. Ở cấu hình SF9, ngưỡng SNR tối thiểu để bộ giải điều chế có thể khôi phục tín hiệu là $`\text{SNR}_{\text{limit}} = -12.5\text{ dB}`$. Giá trị đo được thực tế là $`\text{SNR} = -16.2\text{ dB} < -12.5\text{ dB}`$, nghĩa là tín hiệu bị chìm quá sâu dưới tầng nhiễu môi trường so với năng lực giải mã của SF9. Để giải mã được mức $`\text{SNR} = -16.2\text{ dB}`$, thiết bị bắt buộc phải tăng lên $`\text{SF} = 11`$ (ngưỡng chịu đựng $`-17.5\text{ dB}`$) hoặc $`\text{SF} = 12`$ (ngưỡng chịu đựng $`-20.0\text{ dB}`$).
  * *Tại sao các phương án khác sai:*
    - Phương án A sai vì $`\text{RSSI} = -118\text{ dBm}`$ vẫn lớn hơn nhiều so với độ nhạy thu tối thiểu của SF9 ($`-128.5\text{ dBm}`$).
    - Phương án C sai vì cự ly $`12\text{ km}`$ hoàn toàn nằm trong tầm phủ của LoRa với Link Budget $`150 - 160\text{ dB}`$.
    - Phương án D sai vì vi phạm Duty Cycle chỉ bị xử lý trên máy chủ hoặc quản lý kênh, không làm cho modem vật lý tại Gateway mất khả năng giải điều chế một gói tin đang bay tới.

- **Câu 2: Đáp án đúng là B**
  * *Tại sao B đúng:* Khi chạy ở $`\text{SF} = 12`$ và $`\text{BW} = 125\text{ kHz}`$, thời gian truyền 1 symbol là $`T_{\text{symbol}} = \frac{2^{12}}{125\,000} = 32.768\text{ ms} > 16.38\text{ ms}`$. Đặc tả của Semtech quy định bắt buộc phải bật cờ `LowDataRateOptimize` (Bit 3 trong thanh ghi `RegModemConfig3` của SX1276) để bộ giải mã kích hoạt cơ chế bù trôi dạt tần số thạch anh. Nếu thiếu cờ này, bộ đồng bộ giải điều chế sẽ tính toán sai cấu trúc bit dẫn đến lỗi CRC hoặc không thể khóa được khung truyền. Ở SF7, SF8 và SF10, $`T_{\text{symbol}} \le 8.192\text{ ms} < 16.38\text{ ms}`$ nên không cần bật cờ này, giải thích vì sao thiết bị vẫn chạy bình thường ở SF thấp.
  * *Tại sao các phương án khác sai:*
    - Phương án A sai vì khoảng cách test chỉ $`50\text{ mét}`$, công suất thấp $`+2\text{ dBm}`$ vẫn thu nhận tốt.
    - Phương án C sai vì SF12 hoàn toàn hỗ trợ và mặc định sử dụng Explicit Header trong chuẩn LoRaWAN.
    - Phương án D sai vì Sync Word `0x34` là chuẩn chung cho LoRaWAN công cộng ở mọi mức SF.

- **Câu 3: Đáp án đúng là C**
  * *Tại sao C đúng:* Quy định Duty Cycle 1% của ETSI được áp dụng độc lập cho từng phân băng (Sub-band). Kênh $`868.1\text{ MHz}`$ thuộc Sub-band g ($`868.0 - 868.6\text{ MHz}`$). Trong khi thiết bị đang chịu thời gian im lặng bắt buộc $`T_{\text{off}}`$ trên Sub-band g, nó hoàn toàn được phép phát sóng ngay lập tức trên Sub-band g1 ($`863.0 - 868.0\text{ MHz}`$) hoặc Sub-band g3 ($`869.4 - 869.65\text{ MHz}`$) mà không vi phạm pháp luật viễn thông.
  * *Tại sao các phương án khác sai:*
    - Phương án A sai vì luật ETSI không có ngoại lệ miễn trừ Duty Cycle cho tin khẩn cấp dân sự trong băng tần ISM dùng chung.
    - Phương án B sai vì chờ $`9.9\text{ giây}`$ sẽ làm mất tính thời khắc của cảnh báo lũ khẩn cấp, trong khi có giải pháp kỹ thuật chuyển kênh cho phép phát ngay.
    - Phương án D sai vì Duty Cycle áp dụng cho mọi mức công suất trong dải phân băng, giảm công suất không giúp miễn trừ Duty Cycle.

- **Câu 4: Đáp án đúng là C**
  * *Tại sao C đúng:* Phương trình ngân sách đường truyền tại biên thu tối thiểu:
    $`\displaystyle P_R = P_T + G_T - L_{\text{cable1}} - L_{\text{air-max}} + G_R - L_{\text{cable2}} = \text{Sensitivity}`$
    Suy ra:
    $`\displaystyle L_{\text{air-max}} = P_T - \text{Sensitivity} + (G_T - L_{\text{cable1}}) + (G_R - L_{\text{cable2}})`$
    Thay số:
    $`\displaystyle L_{\text{air-max}} = 14 - (-148) + (3 - 1) + (3 - 1) = 162 + 2 + 2 = \mathbf{166\text{ dB}}`$
  * *Tại sao các phương án khác sai:*
    - Phương án A ($`162\text{ dB}`$) sai vì bỏ quên độ lợi ròng của hệ thống ăng-ten hai đầu ($`+4\text{ dB}`$).
    - Phương án B ($`164\text{ dB}`$) sai do chỉ cộng độ lợi của một đầu ăng-ten.
    - Phương án D ($`158\text{ dB}`$) sai do trừ nhầm độ lợi ăng-ten thay vì cộng.

- **Câu 5: Đáp án đúng là B**
  * *Tại sao B đúng:* Khi chuyển từ SF7 lên SF12, thời gian chiếm sóng ToA tăng từ $`\approx 46\text{ ms}`$ lên $`\approx 1155\text{ ms}`$ (tăng gấp gần $`25`$ lần). Theo lý thuyết hàng đợi và mô hình truy cập ngẫu nhiên ALOHA thuần túy, xác suất xảy ra xung đột va chạm giữa các gói tin tỷ lệ thuận với thời gian chiếm sóng ($`P_{\text{collision}} \propto 1 - e^{-2 \cdot G \cdot \text{ToA}}`$). Việc $`1000`$ thiết bị cùng phát ở SF12 sẽ làm môi trường vô tuyến bị nghẽn nghẹt, tỷ lệ rớt gói tăng vọt lên trên $`60 - 80\%`$, đồng thời năng lượng tiêu thụ trên mỗi nút tăng $`25`$ lần làm cạn kiệt pin nhanh chóng.
  * *Tại sao các phương án khác sai:*
    - Phương án A sai vì tính trực giao trong thực tế không hoàn hảo (hiệu ứng Near-Far) và các node cùng dùng SF12 sẽ va chạm trực tiếp với nhau.
    - Phương án C sai vì dù 1 symbol mang 12 bits nhưng thời gian phát 1 symbol lại dài gấp 32 lần, khiến tốc độ bit thực tế giảm đi 19 lần.
    - Phương án D sai vì LoRaWAN vẫn hỗ trợ SF12 bình thường nhưng chỉ khuyến nghị dùng cho các node ở cự ly rìa cực xa.

---

#### Đáp án Phần B (Tự luận & Tính toán Thực tế):

#### Lời giải Bài toán 1: Thiết kế Phao biển Quan trắc
1. **Đổi công suất phát sang mili-Watt:**
   $`\displaystyle P_T(\text{mW}) = 10^{\frac{P_T(\text{dBm})}{10}} = 10^{\frac{14}{10}} = 10^{1.4} \approx \mathbf{25.12\text{ mW}} \approx \mathbf{25\text{ mW}}`$
2. **Tính suy hao không gian tự do $`L_{\text{air}}`$ trên cự ly $`D = 22\text{ km}`$:**
   Áp dụng công thức USMB:
   $`\displaystyle L_{\text{air}} = 10 \log_{10}\left(D^2 \cdot F^2 \cdot 1755\right)`$
   Với $`D = 22\text{ km}`$, $`F = 868\text{ MHz}`$:
   $`\displaystyle D^2 = 22^2 = 484`$
   $`\displaystyle F^2 = 868^2 = 753\,424`$
   $`\displaystyle \text{Tích số} = 484 \times 753\,424 \times 1755 \approx 6.4002 \times 10^{11}`$
   $`\displaystyle L_{\text{air}} = 10 \log_{10}\left(6.4002 \times 10^{11}\right) = 10 \cdot (11 + \log_{10} 6.4002) = 10 \cdot (11 + 0.8062) = \mathbf{118.06\text{ dB}}`$
3. **Tính mức công suất thu $`P_R`$ (RSSI) tại Gateway:**
   $`\displaystyle P_R = P_T + G_T + G_R - L_{\text{cable}} - L_{\text{air}}`$
   $`\displaystyle P_R = 14\text{ dBm} + 2\text{ dBi} + 6\text{ dBi} - 2\text{ dB} - 118.06\text{ dB} = 20 - 118.06 = \mathbf{-98.06\text{ dBm}}`$
4. **Xác định Spreading Factor tối thiểu đảm bảo Fade Margin $`\ge 12\text{ dB}`$:**
   Yêu cầu:
   $`\displaystyle \text{Margin} = P_R - \text{Sensitivity} \ge 12\text{ dB} \implies \text{Sensitivity} \le P_R - 12\text{ dB}`$
   $`\displaystyle \text{Sensitivity} \le -98.06\text{ dBm} - 12\text{ dB} = \mathbf{-110.06\text{ dBm}}`$
   Tra cứu bảng độ nhạy thu của SX1262:
   - Ở **SF7**: Độ nhạy thu là $`-123.0\text{ dBm}`$.
   Vì $`-123.0\text{ dBm} \le -110.06\text{ dBm}`$, cấu hình **SF7** hoàn toàn thỏa mãn và đem lại Fade Margin thực tế lên tới:
   $`\displaystyle \text{Margin}_{\text{SF7}} = -98.06 - (-123.0) = \mathbf{+24.94\text{ dB}} \ge 12\text{ dB}`$
   $`\implies`$ **Kết luận:** Spreading Factor tối thiểu cần chọn là **$`\text{SF} = 7`$**. Việc chọn SF7 giúp tối ưu thời gian phát sóng, giảm thiểu điện năng tiêu thụ và giảm tối đa nguy cơ xung đột trên biển.

---

#### Lời giải Bài toán 2: Tính Time on Air & Quy chế TTN FAP
1. **Tính kích thước LoRa PHY Payload:**
   $`\displaystyle \text{PL} = 18\text{ bytes (User Data)} + 13\text{ bytes (LoRaWAN Header)} = \mathbf{31\text{ bytes}}`$
2. **Tính toán ToA tại cấu hình $`\text{SF} = 7`$ ($`\text{DE} = 0, H = 0, \text{CRC} = 1, \text{CR} = 1`$):**
   - Số symbol phần mở đầu:
     $`\displaystyle n_{\text{preamble-total}} = 8 + 4.25 = \mathbf{12.25\text{ symbols}}`$
   - Tính biểu thức số nguyên trong hàm trần (Ceiling):
     $`\displaystyle \text{Tử số} = 8 \cdot 31 - 4 \cdot 7 + 28 + 16 \cdot 1 - 20 \cdot 0 = 248 - 28 + 28 + 16 = \mathbf{264}`$
     $`\displaystyle \text{Mẫu số} = 4 \cdot (7 - 2 \cdot 0) = \mathbf{28}`$
     $`\displaystyle \frac{\text{Tử số}}{\text{Mẫu số}} = \frac{264}{28} \approx 9.4286 \implies \lceil 9.4286 \rceil = \mathbf{10}`$
   - Số symbol phần payload:
     $`\displaystyle n_{\text{payload}} = 8 + 10 \cdot (1 + 4) = 8 + 50 = \mathbf{58\text{ symbols}}`$
   - Tổng số symbol khung:
     $`\displaystyle n_{\text{symbol}} = 12.25 + 58 = \mathbf{70.25\text{ symbols}}`$
   - Thời gian 1 symbol ở SF7/BW125:
     $`\displaystyle T_{\text{symbol}} = \frac{2^7}{125\,000} = \mathbf{1.024\text{ ms}}`$
   - Thời gian Time on Air ở SF7:
     $`\displaystyle T_{\text{ToA (SF7)}} = 70.25 \times 1.024\text{ ms} = \mathbf{71.936\text{ ms}} \approx \mathbf{71.94\text{ ms}}`$
3. **Tính toán ToA tại cấu hình $`\text{SF} = 12`$ ($`\text{DE} = 1, H = 0, \text{CRC} = 1, \text{CR} = 1`$):**
   - Biểu thức số học trong hàm trần (Lưu ý $`\text{DE} = 1`$):
     $`\displaystyle \text{Tử số} = 8 \cdot 31 - 4 \cdot 12 + 28 + 16 \cdot 1 - 20 \cdot 0 = 248 - 48 + 28 + 16 = \mathbf{244}`$
     $`\displaystyle \text{Mẫu số} = 4 \cdot (12 - 2 \cdot 1) = 4 \cdot 10 = \mathbf{40}`$
     $`\displaystyle \frac{\text{Tử số}}{\text{Mẫu số}} = \frac{244}{40} = 6.1 \implies \lceil 6.1 \rceil = \mathbf{7}`$
   - Số symbol phần payload:
     $`\displaystyle n_{\text{payload}} = 8 + 7 \cdot (1 + 4) = 8 + 35 = \mathbf{43\text{ symbols}}`$
   - Tổng số symbol khung:
     $`\displaystyle n_{\text{symbol}} = 12.25 + 43 = \mathbf{55.25\text{ symbols}}`$
   - Thời gian 1 symbol ở SF12/BW125:
     $`\displaystyle T_{\text{symbol}} = \frac{2^{12}}{125\,000} = \mathbf{32.768\text{ ms}}`$
   - Thời gian Time on Air ở SF12:
     $`\displaystyle T_{\text{ToA (SF12)}} = 55.25 \times 32.768\text{ ms} = \mathbf{1810.432\text{ ms}} \approx \mathbf{1810.43\text{ ms}} \quad (1.81\text{ s})`$
4. **Đánh giá theo chính sách TTN Fair Access Policy ($`30\text{ giây / ngày}`$):**
   - **Kịch bản SF7 ($`T_{\text{ToA}} = 0.07194\text{ s}`$):**
     * Số gói tin tối đa được gửi mỗi ngày:
       $`\displaystyle N_{\max \text{ (SF7)}} = \left\lfloor \frac{30\text{ s}}{0.07194\text{ s}} \right\rfloor = \mathbf{417\text{ gói / ngày}}`$
     * Khoảng thời gian giãn cách tối thiểu giữa 2 lần gửi:
       $`\displaystyle T_{\text{interval (SF7)}} = \frac{24 \times 60\text{ phút}}{417} \approx \mathbf{3.45\text{ phút / lần}}`$
   - **Kịch bản SF12 ($`T_{\text{ToA}} = 1.81043\text{ s}`$):**
     * Số gói tin tối đa được gửi mỗi ngày:
       $`\displaystyle N_{\max \text{ (SF12)}} = \left\lfloor \frac{30\text{ s}}{1.81043\text{ s}} \right\rfloor = \mathbf{16\text{ gói / ngày}}`$
     * Khoảng thời gian giãn cách tối thiểu giữa 2 lần gửi:
       $`\displaystyle T_{\text{interval (SF12)}} = \frac{24 \times 60\text{ phút}}{16} = \mathbf{90.0\text{ phút / lần}} \quad (1.5\text{ giờ / lần})`$
---

#### Lời giải Bài toán 3: Tối ưu Hóa Năng lượng và Tuổi thọ Pin
Chu kỳ hoạt động: $`T_{\text{cycle}} = 15\text{ phút} = 900\text{ giây}`$.
Dung lượng pin hữu ích: $`C_{\text{eff}} = 1920\text{ mAh} = 1920 \times 3600\text{ mA}\cdot\text{s} = 6\,912\,000\text{ mA}\cdot\text{s}`$.

1. **Kịch bản A (Cấu hình SF7, $`T_{\text{ToA}} = 51.5\text{ ms} = 0.0515\text{ s}`$):**
   - Thời gian ngủ: $`T_{\text{sleep}} = 900\text{ s} - (0.1\text{ s} + 0.0515\text{ s} + 0.12\text{ s}) = 900 - 0.2715 = 899.7285\text{ s}`$.
   - Điện lượng tiêu thụ trong 1 chu kỳ ($`Q_{\text{cycle}}`$):
     $`\displaystyle Q_{\text{sensor}} = 5\text{ mA} \times 0.1\text{ s} = 0.500\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{TX}} = 45\text{ mA} \times 0.0515\text{ s} = 2.3175\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{RX}} = 11\text{ mA} \times 0.12\text{ s} = 1.320\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{sleep}} = 0.002\text{ mA} \times 899.7285\text{ s} \approx 1.7995\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{cycle (SF7)}} = 0.500 + 2.3175 + 1.320 + 1.7995 = \mathbf{5.937\text{ mA}\cdot\text{s}}`$
   - Dòng điện trung bình dài hạn:
     $`\displaystyle I_{\text{avg (SF7)}} = \frac{Q_{\text{cycle}}}{T_{\text{cycle}}} = \frac{5.937\text{ mA}\cdot\text{s}}{900\text{ s}} \approx 0.006597\text{ mA} = \mathbf{6.60\text{ }\mu\text{A}}`$
   - Tuổi thọ pin dự kiến:
     $`\displaystyle \text{Tuổi thọ (SF7)} = \frac{6\,912\,000\text{ mA}\cdot\text{s}}{5.937\text{ mA}\cdot\text{s / chu kỳ}} = 1\,164\,224\text{ chu kỳ}`$
     $`\displaystyle \text{Tuổi thọ (SF7)} = \frac{1\,164\,224 \times 15\text{ phút}}{60 \times 24 \times 365.25} \approx \mathbf{33.2\text{ năm}} \implies \text{Bị giới hạn bởi tuổi thọ hóa học của pin: } \mathbf{10 - 15\text{ năm}}.`$
2. **Kịch bản B (Cấu hình SF12, $`T_{\text{ToA}} = 1318.9\text{ ms} = 1.3189\text{ s}`$):**
   - Thời gian ngủ: $`T_{\text{sleep}} = 900 - (0.1 + 1.3189 + 0.12) = 900 - 1.5389 = 898.4611\text{ s}`$.
   - Điện lượng tiêu thụ trong 1 chu kỳ:
     $`\displaystyle Q_{\text{sensor}} = 0.500\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{TX}} = 45\text{ mA} \times 1.3189\text{ s} = \mathbf{59.3505\text{ mA}\cdot\text{s}}`$
     $`\displaystyle Q_{\text{RX}} = 1.320\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{sleep}} = 0.002\text{ mA} \times 898.4611\text{ s} \approx 1.7969\text{ mA}\cdot\text{s}`$
     $`\displaystyle Q_{\text{cycle (SF12)}} = 0.500 + 59.3505 + 1.320 + 1.7969 = \mathbf{62.9674\text{ mA}\cdot\text{s}}`$
   - Dòng điện trung bình dài hạn:
     $`\displaystyle I_{\text{avg (SF12)}} = \frac{62.9674\text{ mA}\cdot\text{s}}{900\text{ s}} \approx 0.06996\text{ mA} = \mathbf{69.96\text{ }\mu\text{A}}`$
   - Tuổi thọ pin dự kiến:
     $`\displaystyle \text{Tuổi thọ (SF12)} = \frac{6\,912\,000}{62.9674} \approx 109\,771\text{ chu kỳ}`$
     $`\displaystyle \text{Tuổi thọ (SF12)} = \frac{109\,771 \times 15}{60 \times 24 \times 365.25} \approx \mathbf{3.13\text{ năm}}.`$
3. **Bài học Kỹ thuật & Giá trị Cốt lõi của ADR:**
   - Dòng tiêu thụ trung bình ở SF12 cao gấp hơn **$`10.6`$ lần** so với SF7 ($`69.96\text{ }\mu\text{A}`$ so với $`6.60\text{ }\mu\text{A}`$).
   - Năng lượng phát sóng RF ở SF12 chiếm tới **$`94.3\%`$** tổng năng lượng toàn chu kỳ, trong khi ở SF7 nó chỉ chiếm $`39\%`$.
   - Kích hoạt cơ chế ADR để tự động kéo các node về SF7 khi điều kiện kênh truyền cho phép là giải pháp sống còn giúp kéo dài tuổi thọ thiết bị từ $`3`$ năm lên trên $`10`$ năm.

---

## 6. CHECKLIST KIẾN THỨC BẮT BUỘC & CẨM NANG ĐÁP ÁN (MANDATORY PASS CHECKLIST & FULL KEY)

Dưới đây là bảng đối chiếu kiểm định năng lực hoàn thành Module 1 trích xuất nguyên văn từ tệp chuẩn `lorawan_learning_roadmap_checklists.md`, tích hợp đầy đủ cẩm nang đáp án chuẩn công nghiệp:

---

### - [x] **Đơn vị & Ngân sách đường truyền (Link Budget):**
- Phân biệt rõ $`\text{dB}`$ (tỷ lệ tương đối) và $`\text{dBm}`$ (công suất tuyệt đối so với $`1\text{ mW}`$).
- Tự tính nhẩm nhanh các mốc: $`+3\text{ dB}`$ (tăng gấp đôi công suất), $`-3\text{ dB}`$ (giảm một nửa công suất), $`+10\text{ dB}`$ (tăng gấp 10 lần).
- Tính được Link Budget từ công suất phát ($`P_T`$) và độ nhạy thu (Sensitivity):
  $`\displaystyle \text{Link Budget} = P_T - \text{Sensitivity}`$
> 🔑 **[KEY & GIẢI THÍCH CHUẨN]:**
> 1. **Bản chất đại lượng:**
>    - $`\text{dB}`$ là đơn vị logarit không thứ nguyên biểu thị tỷ số giữa hai mức công suất: $`\text{Ratio(dB)} = 10 \log_{10}(P_R / P_T)`$. Đại lượng này dùng để đo độ lợi (khuếch đại) hoặc độ suy hao trên đường truyền.
>    - $`\text{dBm}`$ là đơn vị công suất tuyệt đối quy chiếu theo mốc $`1\text{ mW}`$: $`P(\text{dBm}) = 10 \log_{10}(P(\text{mW}) / 1\text{ mW})`$. Quy ước: $`0\text{ dBm} = 1\text{ mW}`$, $`+30\text{ dBm} = 1\text{ W}`$, $`+14\text{ dBm} \approx 25\text{ mW}`$.
> 2. **Mốc tính nhẩm logarit vàng:**
>    - Cộng $`+3\text{ dB} \iff \times 2`$ công suất. Trừ $`-3\text{ dB} \iff \div 2`$ công suất.
>    - Cộng $`+10\text{ dB} \iff \times 10`$ công suất. Trừ $`-10\text{ dB} \iff \div 10`$ công suất.
>    - Ví dụ: Một máy phát có công suất $`2\text{ W} = 2000\text{ mW} = 1\text{ mW} \times 10 \times 10 \times 10 \times 2 \implies 0\text{ dBm} + 10 + 10 + 10 + 3 = \mathbf{33\text{ dBm}}`$.
> 3. **Công thức Link Budget:**
>
$`\displaystyle \text{Link Budget (dB)} = P_T(\text{dBm}) - \text{Sensitivity}(\text{dBm})`$
>
>    - Chip Semtech SX1272 ($`P_T = +20\text{ dBm}`$, Sensitivity = $`-137\text{ dBm}`$) cho $`\text{Link Budget} = 20 - (-137) = \mathbf{157\text{ dB}}`$.
>    - Chip Semtech SX1262 ($`P_T = +22\text{ dBm}`$, Sensitivity = $`-148\text{ dBm}`$) cho $`\text{Link Budget} = 22 - (-148) = \mathbf{170\text{ dB}}`$.
>    - Tại EU868 giới hạn $`P_T = +14\text{ dBm}`$, $`\text{Link Budget} = 14 - (-148) = \mathbf{162\text{ dB}}`$, vượt trội hoàn toàn so với 4G LTE ($`\approx 130\text{ dB}`$).

---

### - [x] **Thông số SNR & RSSI:**
- Hiểu bản chất RSSI là công suất thu thực tế và SNR là tỷ số tín hiệu trên nhiễu.
- Giải thích được tại sao sóng LoRa có thể giải điều chế thành công ngay cả khi tín hiệu chìm dưới nền nhiễu ($`\text{SNR} < 0\text{ dB}`$, xuống tới $`-20\text{ dB}`$ ở $`\text{SF12}`$).

> 🔑 **[KEY & GIẢI THÍCH CHUẨN]:**
> 1. **Bản chất RSSI & SNR:**
>    - **RSSI (Received Signal Strength Indication):** Là tổng công suất tín hiệu vô tuyến mà máy thu đo được tại cổng ăng-ten, bao gồm cả tín hiệu hữu ích $`P_R`$ và tạp âm môi trường $`P_N`$ (đơn vị $`\text{dBm}`$).
>    - **SNR (Signal-to-Noise Ratio):** Là tỷ số giữa công suất tín hiệu mong muốn $`P_R`$ và công suất nhiễu nền $`P_N`$: $`\text{SNR(dB)} = 10 \log_{10}(P_R / P_N) = P_{R(\text{dBm})} - P_{N(\text{dBm})}`$.
> 2. **Cơ chế giải mã tín hiệu dưới nền nhiễu ($`\text{SNR} < 0\text{ dB}`$):**
>    - Trong điều chế truyền thống (FSK/BPSK), $`\text{SNR} < 0\text{ dB}`$ đồng nghĩa với tín hiệu bị nhiễu vùi lấp hoàn toàn, máy thu không thể phân biệt được bit $`0`$ hay $`1`$.
>    - Trong LoRa CSS, tín hiệu được trải phổ trên toàn bộ băng thông $`\text{BW}`$ với $`2^{\text{SF}}`$ chips/symbol. Khi qua bộ giải điều chế (De-chirping), tín hiệu thu được nhân với Down-chirp chuẩn:
>      * Năng lượng của ký hiệu LoRa được **nén phổ (Despreading)** tập trung lại thành một xung đỉnh nhọn duy nhất (Peak) trong miền tần số (qua thuật toán FFT).
>      * Trong khi đó, tạp âm nhiệt môi trường và nhiễu ngẫu nhiên không có tính tương quan quét tần sẽ bị **trải rộng phổ ra toàn dải $`\text{BW}`$**, biên độ nhiễu bị san bằng xuống mức thấp.
>    - Độ lợi xử lý trải phổ (Processing Gain): $`G_p = 10 \log_{10}\left(\frac{\text{BW}}{R_{\text{bit}}}\right) \approx 10 \log_{10}(2^{\text{SF}})`$. Độ lợi này cho phép đỉnh phổ tín hiệu LoRa nhô cao vượt lên trên sàn nhiễu, giúp giải điều chế thành công ở mức $`\text{SNR} = -7.5\text{ dB}`$ (SF7), $`-10\text{ dB}`$ (SF8), $`-15\text{ dB}`$ (SF10) và xuống tới $`\mathbf{-20\text{ dB}}`$ ở **SF12** (tín hiệu yếu hơn nhiễu $`100`$ lần).

---

### - [x] **Điều chế CSS (Chirp Spread Spectrum):**
- Phân biệt Up-chirp và Down-chirp; giải thích được cơ chế trải phổ bằng chirp thay vì mã giả ngẫu nhiên thông thường.
- Hiểu mối quan hệ giữa **Spreading Factor ($`\text{SF7} \rightarrow \text{SF12}`$)**, **Bandwidth ($`\text{BW}`$)** và **Coding Rate ($`\text{CR}`$)**.
- Thuộc lòng và giải thích được công thức thời gian truyền 1 symbol:
  $`\displaystyle T_{\text{symbol}} = \frac{2^{\text{SF}}}{\text{BW}}`$
> 🔑 **[KEY & GIẢI THÍCH CHUẨN]:**
> 1. **Up-chirp vs Down-chirp & Trải phổ CSS:**
>    - **Up-chirp:** Xung quét tần có tần số tăng tuyến tính từ $`F_{\text{channel}} - \text{BW}/2`$ đến $`F_{\text{channel}} + \text{BW}/2`$. Dùng để mã hóa dữ liệu và dẫn đường trong preamble.
>    - **Down-chirp:** Xung quét tần có tần số giảm tuyến tính từ $`F_{\text{channel}} + \text{BW}/2`$ về $`F_{\text{channel}} - \text{BW}/2`$. Dùng để đánh dấu kết thúc preamble (2.25 symbol) và làm tín hiệu chuẩn hạ tần de-chirping tại máy thu.
>    - Khác với DSSS/CDMA dùng chuỗi bit giả ngẫu nhiên (yêu cầu đồng bộ thời gian khắt khe cỡ nano-giây), CSS trải phổ bằng tần số quét liên tục, có khả năng miễn nhiễm tự nhiên cực cao với hiệu ứng dịch tần Doppler và hiện tượng đa đường (Multipath Fading) mà không đòi hỏi phần cứng phức tạp.
> 2. **Tam giác tham số: SF, BW và CR:**
>    - **Spreading Factor (SF):** Số bit nhị phân mã hóa trong 1 symbol ($`7 \le \text{SF} \le 12`$). SF tăng thêm 1 bậc làm thời gian truyền tăng gấp đôi, cự ly truyền tăng xa hơn, nhưng tốc độ dữ liệu giảm một nửa.
>    - **Bandwidth (BW):** Độ rộng dải thông kênh ($`125, 250, 500\text{ kHz}`$). BW tỷ lệ thuận với tốc độ truyền và tốc độ chip: $`R_c = \text{BW}`$.
>    - **Coding Rate (CR):** Tỷ lệ sửa lỗi Hamming FEC ($`4/5, 4/6, 4/7, 4/8`$). CR tăng cường độ tin cậy khi đường truyền có nhiễu xung nhưng làm tăng phụ phí thời gian phát từ $`25\%`$ đến $`100\%`$.
> 3. **Công thức thời gian truyền 1 symbol:**
>
$`\displaystyle T_{\text{symbol}} = \frac{2^{\text{SF}}}{\text{BW}}`$
>
>    - Ý nghĩa vật lý: Một symbol gồm chính xác $`2^{\text{SF}}`$ chips, và mỗi chip có độ rộng thời gian là $`T_{\text{chip}} = 1/\text{BW}`$. Do đó, thời gian quét hết một symbol là $`2^{\text{SF}} \times (1/\text{BW}) = 2^{\text{SF}} / \text{BW}`$.
>    - Tại $`\text{BW} = 125\text{ kHz}`$: $`\text{SF7} \implies T_{\text{sym}} = 1.024\text{ ms}`$; $`\text{SF8} \implies 2.048\text{ ms}`$; $`\text{SF12} \implies 32.768\text{ ms}`$.

---

### - [x] **Time on Air (ToA) & Quy định Duty Cycle:**
- Biết cách sử dụng công cụ *LoRa Modem Calculator* hoặc công thức tổng quát để tính ToA dựa trên số lượng symbol preamble, header, payload và CRC.
- Nắm vững quy định pháp lý **1% Duty Cycle** trên băng tần EU868 (ví dụ: phát gói tin mất $`46.3\text{ ms}`$ thì phải chờ tối thiểu $`4.58\text{ s}`$ trên sub-band đó trước khi phát tiếp).

> 🔑 **[KEY & GIẢI THÍCH CHUẨN]:**
> 1. **Công thức giải tích tính Time on Air (ToA):**
>
$`\displaystyle T_{\text{ToA}} = (n_{\text{preamble}} + 4.25 + n_{\text{payload}}) \cdot \left(\frac{2^{\text{SF}}}{\text{BW}}\right)`$
>
>    Với số symbol Payload được xác định chính xác theo công thức Semtech:
>
$`\displaystyle n_{\text{payload}} = 8 + \max\left( \left\lceil \frac{8 \cdot \text{PL} - 4 \cdot \text{SF} + 28 + 16 \cdot \text{CRC} - 20 \cdot H}{4(\text{SF} - 2 \cdot \text{DE})} \right\rceil (\text{CR} + 4), \; 0 \right)`$
>
>    - Ví dụ tính mẫu: Gói Uplink LoRaWAN $`14\text{ bytes}`$ (SF7, BW125, CR4/5, Preamble 8, Explicit Header $`H=0`$, $`\text{CRC}=1`$, $`\text{DE}=0`$):
>      * Tử số: $`8\cdot 14 - 4\cdot 7 + 28 + 16 - 0 = 128`$.
>      * Mẫu số: $`4\cdot(7 - 0) = 28`$.
>      * $`\lceil 128 / 28 \rceil = \lceil 4.571 \rceil = 5`$.
>      * $`n_{\text{payload}} = 8 + 5 \cdot (1 + 4) = 33\text{ symbols}`$.
>      * Tổng số symbol: $`n_{\text{symbol}} = (8 + 4.25) + 33 = \mathbf{45.25\text{ symbols}}`$.
>      * $`T_{\text{ToA}} = 45.25 \times 1.024\text{ ms} = \mathbf{46.336\text{ ms}} \approx \mathbf{46.3\text{ ms}}`$ (khớp tuyệt đối với LoRa Modem Calculator).
> 2. **Quy định 1% Duty Cycle trên EU868:**
>    - Viện Tiêu chuẩn ETSI EN 300 220 bắt buộc thiết bị phát không quá $`1\%`$ thời gian trên mỗi phân băng tần ($`868.0 - 868.6\text{ MHz}`$ và $`863.0 - 868.0\text{ MHz}`$).
>    - Công thức tính thời gian im lặng bắt buộc:
>
$`\displaystyle T_{\text{off}} = T_{\text{on}} \cdot \left(\frac{1 - 0.01}{0.01}\right) = \mathbf{99 \cdot T_{\text{on}}}`$
>
>    - Khi truyền gói tin mất $`T_{\text{on}} = 46.3\text{ ms}`$, thời gian nghỉ tối thiểu trên kênh/phân băng đó là:
>
$`\displaystyle T_{\text{off}} = 99 \times 46.3\text{ ms} = 4583.7\text{ ms} \approx \mathbf{4.58\text{ giây}}`$
>
>    - Trong thời gian $`4.58\text{ s}`$ này, nếu cần phát tin khẩn cấp, thiết bị có thể áp dụng cơ chế nhảy kênh (Channel Hopping) sang phân băng khác (Sub-band g1 hoặc g3) mà không vi phạm pháp luật.
