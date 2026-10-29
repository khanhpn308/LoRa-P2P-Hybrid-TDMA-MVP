# Firmware cá nhân — local bench foundation

Có source C thực cho Node và Gateway. Đây là bước nền có thể build để kiểm tra xử lý sự kiện trên console UART, chưa phải truyền thông LoRa Node→Gateway.

## Chức năng

- `quan_event`: debounce bằng thời gian monotonic, không lặp sự kiện khi giữ nút; nút đang giữ lúc boot không tạo false edge; từ chối clock quay ngược.
- FIFO dùng buffer caller cấp, không malloc, sao chép event theo giá trị; đầy thì drop newest, bộ đếm drop bão hòa; pop theo FIFO, wrap an toàn.
- Node: `p` đặt logical button pressed, `r` released; tạo event sau debounce; `d` lấy event đang chờ, `s` xem pending/drop.
- Gateway: `i` tạo một ingress event cục bộ để kiểm tra queue; `d` drain và `s` status.
- Demo cố ý chỉ giữ một pending event để quan sát backpressure. Dung lượng này không phải ngân sách queue production. `sequence` chỉ trong phiên chạy, không phải event ID bền vững hay replay counter.

Ứng dụng không ánh xạ GPIO. Giá trị debounce mặc định 30 ms chỉ là bench example, NOT_VERIFIED với nút vật lý; chỉnh qua menuconfig. Không tạo task/ISR riêng; app_main sở hữu state và stdin. Vòng polling nhường scheduler mỗi tick, không cam kết timing.

## Build

Trong terminal đã export ESP-IDF **v6.1**:

```powershell
idf.py -C firmware/quan/node build
idf.py -C firmware/quan/gateway build
powershell -File firmware/quan/tests/run-host-tests.ps1 -Compiler C:/MinGW/bin/gcc.exe -OutputDirectory C:/temp/quan-tests
```

Các build không tự flash/TX. Chỉ chạy monitor/flash sau xác nhận board/pin và review tương ứng. Console commands là bench input, không phải wire protocol.

## Tái sử dụng thư viện chung

Mặc định source chung trên main chưa có CMake/source driver nên dự án build riêng `quan_event`/`quan_console`. Khi driver dùng chung đã sẵn sàng, bật tùy chọn CMake:

```powershell
idf.py -C firmware/quan/node -DQUAN_LINK_SHARED_DRIVER=ON build
```

Mặc định tìm `firmware/components`. Có thể truyền `-DQUAN_SHARED_COMPONENTS_DIR=<absolute-path-to-reviewed-components>` để thử checkout driver đã review. Nếu thiếu driver thì cấu hình báo lỗi rõ, không giả vờ có thư viện. Source driver được liên kết trực tiếp, không sao chép.

Đường tích hợp chỉ gọi `sx1276_driver_component_name()`; không start owner, không chọn GPIO/PHY, không arm RF. Bản driver local hiện có là work-in-progress chưa merged; chưa coi đó là API được duyệt. Bước tiếp theo cần review #10 và chuẩn hóa public API trước khi đưa radio vào luồng event. MAC/security/ACK/retry còn phụ thuộc #12/#78, không viết wire format tạm rồi gọi production.

## Kiểm thử

Host tests kiểm tra null/capacity/overflow/empty/FIFO/wrap/drop saturation, debounce/bounce/hold/startup-held, clock rollback và biên UINT64_MAX. Đây là unit tests C, không HIL hay RF.

Quy chuẩn áp dụng: GOV-001..010; C-001..020; MEM-001..006; ERR-001..007; QA-001..008. API chỉ thêm namespace `quan_event`/`quan_console`; không thay public API chung, wire, persistence hay scheduling semantics. `app_main` và test `main` là ngoại lệ tên framework theo C-020. Không có API ISR, SPI, timer callback hay shared mutable task state mới.
