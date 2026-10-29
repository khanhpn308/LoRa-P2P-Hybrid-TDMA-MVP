# Minh chứng và đối chiếu quy chuẩn

**Snapshot:** phần dưới là minh chứng bản docs-only PR113 ban đầu. Firmware bổ sung được mô tả tại [FIRMWARE.md](FIRMWARE.md); kết quả build/test mới được ghi riêng trong PR để không đánh đồng với RF/HIL.

## Nguồn

- Kế hoạch tuần 2.docx, Kiến trúc LoRa.docx, Note.md và C_CODING_STANDARD_V2.md do Quân cung cấp; trích xuất text trực tiếp từ DOCX.
- [Issue #10](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/10) và [Issue #78](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/78), đọc trực tiếp ngày 29/10/2026.
- Baseline `08e86af2fda8e40b89c0cf01b98e08311f03b7a9`; `AGENTS.md`; `contracts/OPEN_DECISIONS.md`; `docs/development/firmware/C_CODING_STANDARD_V2.md`.

## Intake

Branch: `codex/quan-week2-personal`. Source ban đầu sạch. Phạm vi do người dùng cho phép: `firmware/event_bench/**`; không sửa shared code hoặc output chính thức của Issue design-only.
Context loader thực chạy: `scripts/agent_harness/agent_context.py --repo quan-week2-work`, trả `HOST_CONTEXT_LOADED` sau checkout giữ LF.
AGENTS SHA256: `aaa4a63bb551346fbd998f5cea868d97086d52b21fece21933f23fa4fafc8f89`.
Coordinator thực hiện fallback; không khẳng định Host isolation, hard enforcement hoặc G0 project approval PASS.

## Quy chuẩn áp dụng

| Rule IDs | Áp dụng trong bộ bàn giao |
|---|---|
| GOV-001/002/004/005/006/007/009/010 | Scope cá nhân trực tiếp từ user; branch riêng; không sửa RF/pin/wire; custom P2P; không bịa kết quả; Draft PR/human review |
| C-001..020 | Đã tham khảo; source mới có namespace, ownership/bounds/context, header guards và test biên |
| MEM-001..006, ERR-003/004/007 | event_input có caller-owned FIFO, drop-newest và lý do lỗi rõ ràng; không có RF retry/recovery implementation |
| RTOS-001..010, RAD-001..009 | Single owner, ISR tối thiểu, DIO/PHY cần review/HIL; chưa sửa driver |
| QA-001..008 | Tách text inspection, build, simulation, audit, HIL/RF; chỉ báo kết quả thực |
| §12 D01–D13 | Giữ quyết định mở; không freeze wire/RF/security/timing |

Quân yêu cầu tuân thủ quy chuẩn C bắt buộc cho công việc của mình. Trạng thái technical approval/enforcement của repository vẫn theo metadata, không tự đổi từ yêu cầu cá nhân này.

## Trạng thái bằng chứng

CODE_WRITTEN: có event_input, bench_console và hai project Node/Gateway local bench.
BUILD_VERIFIED: Node/Gateway ESP-IDF v6.1 PASS; host C tests PASS (-std=c99 -Wall -Wextra -Werror -pedantic). Node liên kết driver local PASS, chỉ identity API, chưa start radio. SIMULATION/HIL/RF/SECURITY: NOT_VERIFIED. Logs thực: output/event-bench-host.log, event-bench-node.log, event-bench-gateway.log, event-bench-shared.log ngoài candidate.
codegraph_explore: NOT_RUN, không có tool trong phiên; dùng kiểm kê source/read-only call-site review, không có caller/callee driver vì chưa có implementation trên baseline.
Review mã chỉ đọc đã thực hiện: sửa baseline UART và kiểm tra tag SDK/CMake; không còn finding được báo. Không chứng minh auditor isolation hoặc human technical sign-off.

Các báo cáo kiểm tra tự động được lưu ngoài candidate để không thay đổi fingerprint. Không dùng docs hay build để suy ra RF/legal/security PASS.
