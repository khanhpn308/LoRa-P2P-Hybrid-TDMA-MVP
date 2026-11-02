# Radio MAC golden vector plan — BLOCKED G2

**Chưa có khung hex hợp lệ đã được duyệt.** Không tạo vectors byte-level giả trước khi quyết định AEAD/tag, key/nonce, field widths, endian và CRC; 8B legacy header không an toàn cho production.

Sau khi G2 đóng băng, mỗi vector phải ghi `spec_revision`, `case_id`, `node/gw direction`, `key_id` (test key **không** phải production), `nonce`, `AAD`, `plaintext`, `wire_hex`, `expected_decoded`, `expected_result` và điều kiện reset/replay. Ít nhất:

| Case | Expected |
|---|---|
| data/beacon/alert/ack/command valid | ACCEPT |
| frame truncated / forged length / unsupported version / reserved bits | REJECT trước dispatch |
| CRC PHY hoặc CRC app sai | REJECT (không thay MIC) |
| altered ciphertext/MIC, forged Beacon/ACK/schedule | REJECT_BAD_AUTH |
| duplicate frame cùng crypto session | REJECT_REPLAY (nhưng RF ACK retry policy có thể xử lý riêng) |
| nonce reused with differing plaintext same key | REJECT / FAIL GENERATION |
| 8-bit seq wrap, superframe counter wrap, reboot without persisted nonce epoch | FAIL_CLOSED, không cho phát |
| lost-beacon and stale schedule version | NO_UNSAFE_PERIODIC_TX |
| exhausted airtime (gồm emergency) | DENY_TX |

Yêu cầu C encoder ↔ Go decoder và Go encoder ↔ C decoder so sánh bytes chính xác. Kết quả CI JSON syntax, nếu có, **không phải** golden conformance, G2 PASS, hay RF/HIL PASS.

Nguồn quyết định/chặn: [specification.md](../specification.md), [OPEN_DECISIONS.md](../../OPEN_DECISIONS.md), [Issue #12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12).

## Bootstrap Join structural fixtures — NOT Golden Vectors

[bootstrap-join-v1.md](../bootstrap-join-v1.md) consolidates Owner-locked Join frame widths, offsets and crypto intent, and [bootstrap-join-gates.md](../bootstrap-join-gates.md) tracks unresolved decisions. [bootstrap-join-structural.json](bootstrap-join-structural.json) contains **synthetic structural-only** sample bytes and intentional **zero-filled 16B unauthenticated tags**, with expected results such as `HEADER_OK_AUTH_UNVERIFIED` or `REJECT_BAD_LENGTH`. The `UP_JOIN_REQUEST:35B` layout is **CANDIDATE**. Never broadcast these samples, use them as valid HMAC, or treat passing a structural unit test as `Golden Vector PASS`, `G2 PASS`, `RF/HIL PASS`, or `IMPLEMENTATION_READY`.

Static test (standard Python): `python3 -m unittest discover -s tests/contract -p 'test_bootstrap_join_contract.py' -v`. Independent C and Go KDF/HMAC vectors require canonical `M_ACCEPT` and complete G2 review; the old Python HMAC fixtures under obsolete packet type bytes `0x21/0x22` are **not valid production vectors** for current `0x22/0x23` codes.
