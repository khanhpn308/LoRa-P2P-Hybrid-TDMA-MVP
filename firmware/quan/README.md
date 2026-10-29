# Không gian làm việc của Quân — tuần 2

Thời gian: 26–30/10/2026. Wave 1 — Foundation.

Đây là bộ bàn giao thiết kế và báo cáo cá nhân; chưa có firmware ứng dụng chạy radio.
Mã dùng chung thuộc `../components/`; không sao chép hoặc sửa các component trong phần bàn giao này.

- [Báo cáo tuần 2](BAO_CAO_TUAN_2.md)
- [Kiểm kê thư viện và phương án tích hợp](TICH_HOP_THU_VIEN.md)
- [Kế hoạch RF/HIL #10, #11](KE_HOACH_RF_HIL.md)
- [Đóng góp thiết kế Priority Access #78](THIET_KE_PRIORITY_ACCESS.md)
- [Minh chứng và quy chuẩn](MINH_CHUNG.md)

Phạm vi `firmware/quan/**` được Quân yêu cầu trực tiếp trong chat. Đây là phạm vi cá nhân bổ sung, không tự mở rộng allowlist của #10/#11/#78 và không thay thế đầu ra chính thức của những Issue đó.

## Trình tự tiếp tục

1. Review/merge driver dùng chung qua #10; xác minh pin map và RF profile theo owner.
2. Bổ sung project cá nhân `gateway/` và `node/`, tham chiếu `../../components` từ từng project; không đặt một bản driver riêng trong `quan/`.
3. Build cả hai project bằng ESP-IDF v6.1; ghi SHA, toolchain, command và logs.
4. Chạy HIL theo kế hoạch; sau review #11/#12/#78 mới triển khai MAC/TDMA.

Không lấy bản driver chưa commit ở các checkout khác làm thư viện đã được review trên GitHub.
