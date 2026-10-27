# Harness Onboarding — WSL2/Linux (Native Fast Lane)

> **Status:** onboarding tooling, không phải chứng nhận security/HIL/RF.  
> **Scope:** thành viên mới của `khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP`.  
> **Authority:** `AGENTS.md`, `docs/development/harness-fast-lane.md` và các Issue/ADR/contracts đã được duyệt.

## 1. Sau khi clone/pull: một lệnh

Mở terminal **Ubuntu trong WSL2** hoặc Linux (không dùng Windows PowerShell cho những lệnh Bash):

```bash
cd ~/projects/iot/LoRa-P2P-Hybrid-TDMA-MVP
bash scripts/setup_harness.sh
```

Trong terminal tương tác, nếu phát hiện thiếu Harness MCP và đã có Codex/AGY, script đề xuất plan MCP và yêu cầu nhập `INSTALL MCP` trước khi cài SDK/cấu hình MCP. Nếu từ chối, script chỉ chạy diagnostics. Trong chế độ noninteractive hoặc `--json`, mọi bước mặc định vẫn read-only, không cài package, sửa Git, gọi sudo, khởi động container hoặc yêu cầu token. Kết quả `READY` chứng tỏ **các điều kiện local cho role core** đã được phát hiện; không bảo đảm credentials còn hợp lệ trên GitHub, agent có Full Access, worker isolation, hay E2E task PASS.

Nếu cần kiểm tra môi trường theo vai trò:

```bash
bash scripts/setup_harness.sh --profile core       # Git, Python, gh, Agent, SOP
bash scripts/setup_harness.sh --profile firmware   # Core + Docker + local ESP-IDF v6.1 image
bash scripts/setup_harness.sh --profile infra      # Core + Docker engine + Compose
bash scripts/setup_harness.sh --profile all --json # Kết quả máy đọc được
```

Chỉ khi chấp nhận dùng mạng để kiểm tra GitHub session:

```bash
bash scripts/setup_harness.sh --check-auth
```

**Exit codes:** 0 khi mọi `required` check PASS; 1 khi thiếu/sai required check; 2 nếu CLI args không hợp lệ. `WARN` không làm block, `SKIP` là chưa chạy, không phải PASS. `--json` có các trường `schema_version`, `profile`, `ready`, `failed_required_checks`, `checks` và `limitations`.

## 2. Cài core tools có xác nhận, không tự ý thay đổi máy

Trên **Ubuntu/Debian** có `apt-get`, dùng:

```bash
bash scripts/setup_harness.sh --install-core
```

Chế độ này chỉ đề xuất các package còn thiếu trong danh sách cố định `python3`, `git`, `gh`. Trước khi gọi `sudo apt-get update` và `sudo apt-get install`, script liệt kê chính xác các package và bắt nhập **INSTALL**. Không cài Docker, Codex, AGY, thay đổi group membership hoặc login GitHub. Không chạy chế độ này trên máy chưa được quản trị viên cho phép cài packages; sử dụng doctor read-only và chuyển đề xuất cho quản trị viên.

**GitHub authentication (tự thao tác):**

```bash
gh auth login
gh auth status
```

Dùng user bình thường của WSL/Linux. Doctor mặc định chỉ phát hiện **sự tồn tại** của cấu hình `~/.config/gh/hosts.yml` hoặc biến môi trường auth; không mở, in hoặc xác minh giá trị token. Dùng `--check-auth` khi cần xác nhận phiên thật. Không chụp màn hình hoặc đính kèm token/key, file `hosts.yml` hoặc credentials.

## 3. Cấu hình Harness MCP cho Codex + AGY (tùy chọn)

Sau khi cài Codex và/hoặc AGY, chạy lại lệnh setup thông thường để nhận plan và xác nhận một lần. Hoặc chủ động yêu cầu:

```bash
bash scripts/setup_harness.sh --install-mcp
```

Lệnh này tạo Python venv dưới `~/.local/share/lora-harness/`, cài MCP SDK v2 đã pin sau xác nhận, smoke giao thức stdio, rồi đăng ký `lora_harness` cho **các CLI đã cài**. Các MCP hiện có được bảo toàn; cấu hình trùng tên nhưng khác launcher sẽ bị BLOCKED. Có thể chỉ xem plan bằng `python3 scripts/harness_mcp_setup.py --plan` mà không sửa môi trường.

**MCP hiện chỉ cung cấp ba công cụ đọc Host P1:** `harness_preflight`, `harness_status`, `harness_verify_candidate`. Nó **không** tự khởi chạy Worker/Build/Auditor hay signed execution. Native Fast Lane `Chạy Issue #N` vẫn sử dụng Coordinator và SOP độc lập. Sau cài đặt cần mở lại Codex/AGY và dùng `/mcp` xác nhận live client connection. Chi tiết và security checklist: [Harness MCP Onboarding](harness-mcp-onboarding.md).

## 4. Cài một AI CLI và kích hoạt Native Harness

- **Codex:** cài từ hướng dẫn chính thức của nhà cung cấp; mở trong root repo, tự chọn Full Access qua permissions UI của Codex. Không cần tạo một `harness-coordinator` giả trong Codex `/agents`.
- **AGY:** cài từ hướng dẫn chính thức; mở `agy` trong root repo, vào `/agents` và chọn profile `harness-coordinator`, rồi tự chọn mức quyền của CLI. Profile nằm ở `.agents/agents/harness-coordinator.md` trong repo.
- Chỉ cần **một** trong hai CLI để chạy. Doctor chỉ kiểm tra binary trên PATH và sự tồn tại của config, không đăng nhập/cấp quyền thay user.
- Khi môi trường sẵn sàng, giao `Chạy Issue #N`. Agent đọc scope và tiêu chuẩn repo, tạo branch/worktree riêng, code, thu receipts, chạy Quality Gates, fresh audit và tạo Draft PR; giữ human review trước merge.

**Native Fast Lane** không bắt dùng signed MCP signer. Không coi việc agent CLI có Full Access là chứng minh security isolation hoặc quyền thực thi của Host/MCP.

## 5. Docker Engine và ESP-IDF v6.1 trong WSL2

Docker Desktop **không bắt buộc**. Có thể cài Docker Engine trực tiếp trong Ubuntu WSL2 bằng nguồn package tin cậy và chạy systemd, theo hướng dẫn chính thức phù hợp phiên bản Ubuntu. Doctor không tự cài, `sudo systemctl start docker`, kéo image hoặc `usermod`:

```bash
docker version
docker info --format '{{.ServerVersion}}'
docker compose version
docker image inspect espressif/idf:v6.1
```

Docker socket là bề mặt đặc quyền cao. **Không dùng `chmod 666 /var/run/docker.sock`**, không tự động thêm user vào group `docker` và không mặc định bật TCP Docker API. Nếu daemon chưa chạy, hãy kiểm tra systemd, service, nhóm/quyền socket và chính sách IT. Thành viên firmware chỉ pull `espressif/idf:v6.1` sau khi chấp nhận dung lượng tải/xuất xứ image; trong workflow build có kiểm tra pinned image SHA theo evidence. `firmware/esp-idf-version.txt` hiện pin `v6.1`, nhưng việc doctor phát hiện tag không chứng minh image digest/firmware build PASS.

Go Backend dùng toolchain theo `.go-version` và `backend-go/go.mod`; phiên bản này được xử lý trong module-specific tests, không được suy ra từ preflight core.

## 6. Troubleshooting

| Triệu chứng | Nguyên nhân hay gặp | Xử lý |
|---|---|---|
| `python3: command not found` | Ubuntu thiếu Python | Dùng `--install-core` sau khi được phép, hoặc yêu cầu IT |
| `gh_auth_config: FAIL` | Chưa có tài khoản GitHub trong WSL | `gh auth login` dưới user hiện tại |
| `gh_auth_online: SKIP` | Mặc định offline | Chỉ là `NOT_VERIFIED`; dùng `--check-auth` nếu cần |
| `ai_provider: FAIL` | Cả `codex` và `agy` không trên PATH | Cài ít nhất một CLI chính thức, mở terminal mới |
| `docker_daemon: FAIL` | Engine chưa chạy, sai context hoặc thiếu quyền socket | Kiểm tra `docker context ls`, service và chính sách quyền; không `sudo docker` làm bằng chứng chạy non-root |
| `docker_compose: FAIL` | Chưa cài Compose plugin | Cài plugin theo nguồn Docker hỗ trợ |
| `esp_idf_image: FAIL` | Chưa cache image, Docker không hoạt động | Sau khi xác minh Docker: `docker pull espressif/idf:v6.1` |
| `working_tree: WARN` | Có file local chưa commit | Giữ nguyên; tạo branch/worktree sạch cho Issue, không reset tự động |
| `config:... FAIL` | Clone thiếu file/checkout không phải bản mong muốn | Kiểm tra branch, `git fetch`, chỉ dùng `git pull --ff-only` khi safe |

## 7. Trạng thái và bằng chứng

Đừng đưa `READY` của doctor thành `BUILD_VERIFIED`, `HIL_VERIFIED`, `RF_VERIFIED` hoặc `HUMAN_SECURITY_REVIEW_PASS`. Có đủ core tools chỉ chứng minh khả năng **bắt đầu** workflow. Infrastructure profile cần integration receipts thật; firmware profile cần ESP-IDF build receipts và kiểm thử phần cứng riêng khi Issue yêu cầu. GitHub Actions theo quyết định chủ repo hiện `OWNER_WAIVED`, không tương đương `CI_PASS`.

Thành viên mở **GitHub Issue → Harness onboarding checklist** khi cần ghi nhận môi trường, chỉ chia sẻ kết quả kiểm tra đã bỏ thông tin nhạy cảm. Không chia sẻ key/cert private, access token, session ID, file auth hay mật khẩu.

## 8. Kiểm thử thay đổi của công cụ onboarding

```bash
bash -n scripts/setup_harness.sh
python3 -m py_compile scripts/harness_doctor.py
python3 -m unittest discover -s tests/agent_harness -p test_harness_doctor.py -v
python3 scripts/harness_doctor.py --profile core --json
git diff --check
```

Các kiểm tra bên trên là local checks, không thay thế review bảo mật của script cài package. Không tự chạy script từ PR chưa review dưới quyền root.
