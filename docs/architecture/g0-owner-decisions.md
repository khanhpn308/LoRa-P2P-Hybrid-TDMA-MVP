# G0 — Quyết định kiến trúc và phạm vi MVP do Owner phê duyệt

**Trạng thái:** `OWNER_APPROVED — ARCHITECTURE DIRECTION` (C01–C08 và chính sách phạm vi C09). **Chưa đạt:** `G0_SCOPE_FROZEN`, G0–G6 `PASS`, RF/HIL/Timing/Security `VERIFIED`.

**Nguồn quyết định:** các chỉ đạo trực tiếp của Project Owner trong phiên rà soát G0 ngày 2026-10-30. Khi tài liệu nháp cũ khác các quyết định dưới đây, dùng quyết định Owner làm cơ sở sửa tài liệu; thay đổi hợp đồng giao tiếp vẫn cần review và phiên bản tương thích.

## Kiến trúc đã chốt

| Mã | Quyết định |
|---|---|
| **C01** | Mạng hình sao nhiều Gateway (**1–4 Gateway** trong phạm vi MVP). Node liên lạc trực tiếp, một Gateway phục vụ tại một thời điểm. **Không Mesh, không chuyển Gateway tự động** trong phạm vi hiện tại. |
| **C02** | **4 kênh vô tuyến hoạt động riêng**, mỗi Gateway dùng một kênh khi vận hành đủ bốn Gateway; LoRa **BW = 125 kHz**. Node sử dụng tần số đã cấu hình của Gateway phục vụ. Backend quản lý kế hoạch kênh, User phê duyệt, Gateway thực thi; tần số trung tâm và pháp lý RF chưa chốt. |
| **C03** | **Backend duy nhất tạo/sửa lịch** và quản lý phiên bản, phân bổ khe, kế hoạch kênh; **User phê duyệt**. Gateway kiểm tra an toàn, từ chối lịch lỗi, có thể tạm ngưng phát không an toàn nhưng **không được tự sửa lịch**. Gateway điều khiển thời gian thực cục bộ; `STAGE_ACK` không phải `ACTIVE_REPORT`. |
| **C04** | **Chuẩn bị/xác nhận + quyền khe có thời hạn + chuyển lịch an toàn.** Backend/User phê duyệt khoảng kích hoạt; Gateway chọn ranh giới Superframe bên trong khoảng đó. Không tái cấp khe khi quyền phát cũ chưa chấm dứt an toàn. Lưu Active và Shadow riêng; không tự kích hoạt Shadow sau reboot. |
| **C05** | **Node tạo mã sự kiện gốc** và giữ nguyên khi gửi lại; Gateway ghi nhận lần tiếp nhận; Backend lưu bền vững và chống ghi trùng theo sự kiện gốc. Không đưa ra giả định nhiều Gateway cùng nhận một gói RF hoặc Node tự đổi tần số. |
| **C06** | **Node ID 8-bit theo từng Gateway**; mã Node có thể trùng giữa các Gateway. Phân biệt Node trong cấu hình bằng `(gateway_id, node_id)`; ID không thay xác thực mật mã. **Device UID 128-bit chỉ là đề xuất**; byte layout RF chờ G2. |
| **C07** | MVP bao gồm **tạm ngừng, khôi phục, thu hồi và cấp lại quyền Node**. Backend quản lý quyền; Gateway thực thi. Mất Internet chỉ tiếp tục chấp nhận Node khi **quyền còn hiệu lực và xác minh được**, không tự gia hạn. Thu hồi DATA Slot tuân C04. |
| **C08** | Cảnh báo ưu tiên dùng **cửa sổ tranh chấp + cơ hội gửi lại dự phòng** thuộc lịch Backend/User phê duyệt; có kiểm soát va chạm, xác nhận nhiều mức và gửi lại hữu hạn. Gateway không tự phân bổ lại Slot. Node **Periodic OFF vẫn gửi cảnh báo** nếu còn quyền. Mọi TX tuân chính sách RF. |
| **C09 — Chính sách** | **Mọi chức năng được Owner xác nhận thuộc yêu cầu sản phẩm đều phải triển khai và nghiệm thu trong MVP.** Không dùng phân loại «giai đoạn 2» để loại chức năng. **Mesh tạm ngoài phạm vi** theo quyết định riêng. Chưa khẳng định danh mục chức năng đã đầy đủ. |

## Ranh giới thực thi

- **Node:** cảm biến, phát hiện ngưỡng, mã sự kiện, đồng bộ và phát theo cơ hội được phép; chế độ báo cáo định kỳ **OFF mặc định**, bật/tắt riêng từng Node; OFF không tắt cảnh báo.
- **Gateway:** một radio SX1276 bán song công; Beacon/TDMA, kiểm tra quyền/phiên lịch, thu cảnh báo, lưu đệm có giới hạn và thực thi an toàn cục bộ.
- **Backend Go + PostgreSQL:** quản lý thiết bị/quyền, kế hoạch kênh/lịch, dữ liệu/cảnh báo, chống trùng, phân quyền, đối soát trạng thái. Mosquitto/MQTT 5.0 qua TLS làm đường truyền, không điều khiển từng khe RF.
- **Web/Mobile:** quản trị và theo dõi thông qua Backend, không truy cập trực tiếp MQTT hoặc cơ sở dữ liệu.

## Chưa được phép mặc định

- Chưa chốt: số Node toàn mạng hay mỗi Gateway; tần số trung tâm, SF/CR/công suất và áp dụng quy định RF tại Việt Nam; độ dài khung/khe, guard, trôi đồng hồ, thời hạn quyền truy cập/quyền khe, bộ đếm và mã hóa/xác thực.
- Chưa chốt: cấu trúc byte giao thức, độ dài mã sự kiện, thuật toán khóa/nonce, giới hạn retry/queue, thời gian chuyển lịch và ngưỡng nghiệm thu độ trễ; không coi số liệu `P-10S-15`, tỷ lệ phát hoặc SLA trong tài liệu gốc là kết quả đã đo.
- **Cần đối chiếu trước khi chốt danh mục:** quy mô Node; công nghệ Mobile (tài liệu gốc Flutter, repository mô tả Kotlin Android); toàn bộ chức năng UI/API/command; tính năng relay/actuator chỉ thực hiện khi được Owner xác nhận.
- `G0_SCOPE_FROZEN` chỉ được công bố khi danh mục chức năng có nguồn, mô tả hành vi và tiêu chí nghiệm thu đã được Owner xác nhận; phê duyệt C01–C09 **không tự tạo G0 PASS**. G1–G6 cần bằng chứng riêng.

## Quy tắc thay đổi

Quyết định đã chốt không được sửa ngầm. Nếu phát hiện xung đột, ghi rõ tác động và xin quyết định Owner trước khi thay đổi. Mọi sửa đổi RF/MAC, MQTT/API, DB hoặc bảo mật phải đánh giá tương thích, kiểm thử và được nhóm liên quan review.

**Nguồn đối chiếu:** [ADR-0001](../adr/0001-hybrid-tdma.md) · [Ma trận yêu cầu](../requirements/requirements.md) · [Radio MAC nháp](../../contracts/radio-mac/specification.md) · [MQTT nháp](../../contracts/mqtt/semantic-rules.md) · [Các cổng nghiệm thu](../verification/acceptance-gates.md).
