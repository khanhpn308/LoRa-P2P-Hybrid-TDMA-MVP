# Contract verification & acceptance — plan

**Scope:** Contract files generated under `contracts/` only. **No claimed CI/HIL PASS** without captured run log. Owners: #12 Gateway/Node/RF/Security, #14 Gateway/Backend/Infrastructure, #15 Backend/Web/Mobile.

## 1. Chạy kiểm thử tĩnh

```bash
python3 -m pip install -r contracts/tests/requirements.txt
python3 contracts/tests/check_contracts.py
```

Bộ test gồm:
- JSON Schema Draft 2020-12 meta-validation cho toàn bộ MQTT/WebSocket schemas.
- Dùng `jsonschema.FormatChecker` để từ chối UUID và timestamp lỗi.
- MQTT fixture valid/invalid theo từng topic; một negative case trùng slot vẫn *schema valid* nhưng phải bị validator miền TDMA từ chối.
- WebSocket fixture đủ bốn loại event và các trường hợp sai.
- OpenAPI 3.0.3 được parse với `PyYAML`, kiểm semantic bởi `openapi-spec-validator`; kiểm operation `x-roles` và phản hồi 401/403.

**Quan trọng:** Workflow `.github/workflows/ci-contracts.yml` của repo hiện chỉ kiểm *cú pháp JSON*, **không tự chạy script này**. Để chạy thường trực trên CI cần mở rộng scope của Issue sang `.github/workflows/` và được phê duyệt. Không sửa workflow âm thầm trong PR chỉ có scope `contracts/`.

## 2. Các phép thử chưa thay được bằng kiểm tra tĩnh

| Interface | Positive / negative integration cases | Phải có bằng chứng |
|---|---|---|
| Radio MAC | C↔Go golden bytes sau ADR crypto; MIC corruption, replay, nonce collision sau reset, wrap, truncated frame | G2, HIL G3, security G5 |
| TDMA | 15 Node, guard/drift, half-duplex, schedule K activation, missing Beacon, join/recovery, RF duty guard | G1/G2/G3 |
| MQTT | Real TLS/ACL; QoS1 duplicate, offline buffered replay, stale schedule, status/LWT, out-of-order ACK, buffer overflow | G4/G5 |
| REST | 401/403/404/409/422, Viewer denied write, pagination, optimistic conflict, 202 queue status | G4 |
| WebSocket | auth handshake, unauthorized subscribe, reconnect REST resync, backpressure, dedup, all four events | G4/G5 |

Mỗi bằng chứng tối thiểu cần Issue, commit/hash, môi trường, thời gian, thiết bị/tool versions, testcase, expected/actual, artifact link, người xác minh và verdict.

## 3. Quy trình đổi contract

1. Mở/chỉnh Issue #12 / #14 / #15 với Target Directories đã cho phép.
2. Thay schema/spec + fixture + review impact trên producer **và** consumer; với thay đổi phá vỡ giao thức phải có ADR và tăng protocol version.
3. Chạy script, lưu output trong PR. Chạy E2E/HIL và gắn chứng cứ nếu claim tính tương thích hoạt động hay hiệu năng.
4. Review CODEOWNERS + owner của Gateway, Node, Backend, Web/Mobile đúng phần phụ thuộc.
5. Không nhầm các mức: **DRAFT** → REVIEWED → APPROVED contract; riêng **G1–G6 PASS** yêu cầu chứng cứ ngoài contract.

## 4. Nguồn và giới hạn

Kiến trúc chi tiết `esp32_sx1762.md` §§5–9, 11 là nguồn xây dựng profile đề xuất; repository `docs/architecture/system-overview.md`, `docs/requirements/requirements.md` và `docs/verification/acceptance-gates.md` là baseline kiểm chứng/gates. Các sai khác được ghi ở [OPEN_DECISIONS.md](OPEN_DECISIONS.md). Bộ test chỉ dùng **fixture giả lập**; không phải dữ liệu thực nghiệm.
