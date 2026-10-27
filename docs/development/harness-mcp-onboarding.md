# Hướng dẫn tích hợp Harness MCP — Codex + AGY (Issue #95)

> **Trạng thái:** Bản triển khai đề xuất; **chưa nghiệm thu** kết nối client thực tế trên WSL2 và chưa hoàn tất Human Security Review.  
> **Phụ thuộc:** MCP Python SDK v2.3.0, Python 3.11+, GitHub CLI (chỉ dùng khi kiểm tra preflight).  
> **Ranh giới bảo mật:** MCP chỉ cung cấp công cụ kiểm tra Host P1 ở chế độ **read-only**; không chạy nhiệm vụ lập trình qua Native Fast Lane và không kích hoạt signed execution từ Draft PR #84.

## 1. Cài đặt trên WSL2/Linux bằng một lệnh

Tại terminal Ubuntu trong WSL2 hoặc Linux, mở thư mục repository:

```bash
cd ~/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
bash scripts/setup_harness.sh
```

Nếu terminal đang ở chế độ tương tác, Codex hoặc AGY đã được cài và cấu hình MCP còn thiếu, script sẽ hiển thị kế hoạch cài đặt. Người dùng **phải nhập chính xác `INSTALL MCP`** trước khi script được phép thay đổi cấu hình. Nếu từ chối, chỉ tiếp tục các kiểm tra Doctor. Chế độ non-interactive và `--json` vẫn read-only.

Muốn chủ động yêu cầu cài MCP:

```bash
bash scripts/setup_harness.sh --install-mcp
```

Muốn **xem trước kế hoạch mà không thay đổi hệ thống**:

```bash
python3 scripts/harness_mcp_setup.py --plan
```

## 2. Thành phần được cài đặt và cách đăng ký

1. Tạo hoặc dùng lại Python virtual environment riêng tại `~/.local/share/lora-harness/mcp-venv`; không tạo venv bên trong Git working tree.
2. Sau khi người dùng xác nhận, dùng `pip --no-input` để cài SDK được pin `mcp==2.3.0`. Lần cài đầu có thể cần Internet; không dùng `sudo`. Cần review nguồn gốc và phụ thuộc trước khi xác nhận.
3. Khởi chạy tạm thời MCP Server qua **stdio** bằng Python trong venv. Kiểm tra protocol negotiation, đúng ba công cụ trong `tools/list`, và một yêu cầu không hợp lệ với Issue #0 phải trả về `BLOCKED`. Negative smoke test này phải chạy offline, không gọi GitHub.
4. Đăng ký `lora_harness` trong **Codex** qua `codex mcp add lora_harness -- <venv-python> <server.py>`, sau đó đọc lại cấu hình để xác minh. Giữ nguyên các MCP khác.
5. Đăng ký `lora_harness` trong **AGY** tại `~/.gemini/config/mcp_config.json`, chỉ chỉnh `mcpServers.lora_harness`. Giữ nguyên entry khác; tạo bản sao lưu với permission `0600` nếu cấu hình đã tồn tại và ghi file mới theo cơ chế atomic write, cũng với permission `0600`.
6. Nếu chưa cài Codex hoặc AGY, đánh dấu `SKIP` cho client tương ứng. Nếu `lora_harness` trùng tên nhưng khác launcher, JSON không hợp lệ hoặc cấu hình là symlink, đánh dấu `BLOCKED`; không tự động ghi đè.

**Installer không thực hiện:** cài Codex/AGY, yêu cầu mật khẩu/token, sửa shell profile, dùng quyền root, cấp quyền Docker, khởi tạo signer, bật dịch vụ Firmware/Go, push hoặc merge PR.

## 3. Ba công cụ MCP và giới hạn quyền

| Công cụ | Thao tác được phép | Không bao gồm |
|---|---|---|
| `harness_preflight(issue_number)` | Dry-run `prepare` cho Issue đang OPEN và đúng phạm vi P1; cần `gh auth` local | Không tạo worktree, sửa code hoặc tự phê duyệt |
| `harness_status(run_id)` | Đọc journal SQLite hiện có của Host (có thể chạm metadata WAL ngoài repository) | Không chạy Agent |
| `harness_verify_candidate(run_id)` | Đọc, kiểm tra phạm vi và hash qua `host_gate.py` đáng tin cậy | Không chứng nhận build, audit hoặc security PASS |

**Phân biệt MCP và Native Fast Lane:** MCP không tự tạo hoặc khởi chạy Agent. Người dùng vẫn có thể gõ **`Chạy Issue #N`** trong Codex/AGY để kích hoạt Native Fast Lane Coordinator theo `AGENTS.md` và SOP. Đó là luồng riêng, **không phải** ba MCP read-only tools ở trên. Khả năng thực thi task qua MCP chưa được merge hoặc cấp phép trong Issue #95.

## 4. Xác minh kết nối sau cài đặt

Đóng các phiên CLI đang mở và **khởi động lại Codex/AGY** để tải cấu hình MCP mới.

- **Codex:** chạy `codex mcp list`, sau đó mở `/mcp` trong giao diện TUI để kiểm tra `lora_harness`.
- **AGY:** mở `/mcp` và kiểm tra mục `lora_harness`.

Smoke test trong installer chỉ chứng minh MCP Server giao tiếp được với MCP SDK client riêng. **Nó không chứng minh** Codex hoặc AGY đã kết nối thành công trong phiên tương tác thực tế. Giữ trạng thái `NOT_VERIFIED` đến khi kiểm tra độc lập từng client.

Chạy lại smoke test cục bộ:

```bash
~/.local/share/lora-harness/mcp-venv/bin/python scripts/agent_harness/mcp_smoke.py scripts/agent_harness/mcp_server.py
```

Kết quả kỳ vọng: `MCP_STDIO_SMOKE_PASS`. Test này không thay đổi Issue, chỉnh code, chạy Docker hoặc kiểm thử RF.

## 5. Xử lý sự cố và lưu ý bảo mật

- **`python3 -m venv` lỗi:** kiểm tra gói `python3-venv`; cài theo chính sách quản trị máy, tuyệt đối không dùng `sudo pip`.
- **Thiếu `codex` hoặc `agy`:** cài theo hướng dẫn chính thức của nhà cung cấp rồi chạy lại installer.
- **Xung đột cấu hình:** kiểm tra entry hiện có và xử lý thủ công; không reset hay xóa MCP không liên quan.
- **Thiếu `gh auth`:** chỉ `harness_preflight` cần xác thực GitHub. Offline smoke vẫn có thể chạy.
- **Installer dừng sau khi cài SDK:** venv được giữ lại để dùng tiếp; cấu hình client chưa được ghi trước khi smoke PASS.
- **Rủi ro dependency:** chỉ pin trực tiếp `mcp==2.3.0`; **chưa** có lockfile hash cho toàn bộ transitive dependencies. Phải review riêng khi nâng version.
- **Giới hạn cách ly:** MCP Server chạy dưới quyền người dùng hệ điều hành hiện tại. Hai phiên CLI khác nhau **không đồng nghĩa** được cô lập filesystem, credentials hay provider.
- **Giới hạn bằng chứng:** cài đặt/handshake thành công không chứng minh CI, Firmware Build, HIL, RF hoặc penetration test đã PASS.

## 6. Checklist kiểm tra trước merge

Chạy trên checkout đã được review:

```bash
bash -n scripts/setup_harness.sh
python3 -m unittest discover -s tests/agent_harness -p test_mcp_host.py -v
python3 -m unittest discover -s tests/agent_harness -p test_harness_mcp_setup.py -v
python3 -m unittest discover -s tests/agent_harness -v
python3 scripts/harness_mcp_setup.py --plan
git diff --check
```

Ngoài các lệnh trên, **Acceptance Criteria** còn yêu cầu: kiểm tra WSL2 thực tế với Codex/AGY đã cài; stdio handshake thực; xác minh backup và permissions của cấu hình; Human Security Review độc lập; cùng evidence `/mcp` từ từng CLI.

**Chưa được đánh dấu PASS chỉ vì file test hoặc hướng dẫn đã tồn tại.** Trạng thái GitHub Actions `OWNER_WAIVED` không tương đương `CI_PASS`. Chưa merge khi thiếu nghiệm thu và phê duyệt của con người.
