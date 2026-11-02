# Bootstrap Join J01/J02 — Agent decision pack

**PROPOSED · OWNER_APPROVAL_REQUIRED · G2 NOT_VERIFIED**

**Agent:** Do **not** treat J01/J02 as closed. Implement only isolated, test-only candidate codecs; no production RF Join TX, no merged contract, no security PASS. Resolve [J06 relay identity](bootstrap-join-gates.md) independently.

## J01 — `UP_JOIN_REQUEST` whole-frame freeze proposal

**Proposal:** lock the existing **35-byte MAC frame** with **no extra 8B MIC/CRC**. Owners have locked the type code, nonce and derivation, **not the full frame or this new proposal**.

| MAC offset | Field | Bytes | Validation/encoding |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1 | Exactly `0x22`, V1 type 2, Node→Gateway |
| 1–6 | `DEVICE_MAC` | 6 | Exact provisioned factory MAC bytes; no implicit 128-bit UID |
| 7–8 | `JOIN_COUNTER` | 2 | uint16 BE; Backend verifies durable monotonic high-water |
| 9–18 | `JOIN_RANDOM` | 10 | Fresh CSPRNG output per new request |
| 19–34 | `JOIN_PROOF` | 16 | first16 HMAC-SHA256(`K_JOIN_REQ`, exact approved `M_UP:49B`) |
| | **Total** | **35** | Excludes LoRa PHY preamble/header/CRC; no old 8B MAC header |

**Required checks:** frame exactly 35B; authenticated Gateway context and authorized CTRL UL; provisioned and currently allowed `DEVICE_MAC`; fresh Counter and Random against Backend persistent state; constant-time proof check **before updating** high-water; correct RF_PLAN_ID and current relay identity; replays with identical tuple may be treated idempotently for the **same** pending transaction and current authorization only. A packet with the same Counter but different Random, context or bytes is rejected. For same `K_JOIN` replay domain, Counter wrap/rollback or uncertain durable persistence => fail closed. `0x0000`/other reserved Counter codes remain **unassigned until a Counter policy is approved**; avoid guessing reserved values.

**Result classification for security:** reject missing or unknown device as `UNKNOWN_DEVICE` (internal only), invalid proof as `BAD_AUTH`, old counter as `REPLAY`, changed bytes under same counter as `COUNTER_CONFLICT`, unauthorized RF window as `AIRTIME_DENIED`; **error code names are proposal**, no new on-air NACK. Avoid device enumeration or HMAC oracle on RF/MQTT errors.

**Unresolved prerequisite J06:** `M_UP` requires `RELAY_GW_ID:1B` but Request does not transmit it. Node must obtain an *unambiguous* expected Gateway ID from provisioned channel/Gateway registry or another separately approved bootstrap mechanism. Backend must use authenticated Gateway principal mapped to same RF ID. Spoofed/disputed channel identity must reject, not silently omit the byte. This proposal **does not** approve the registry or imply untrusted Beacon is authenticated.

## J02 — `M_ACCEPT` canonical bytes proposal

**Proposal:** Keep the Owner-locked **22-byte** `DOWN_JOIN_ACCEPT` frame and independently approved `K_JOIN_ASSIGN_DL`, define exactly how its 16B `AUTH_TAG` is computed.

`DOWN_JOIN_ACCEPT[0..5]` = `0x24 || REQUEST_REF[2] || TARGET_GW_ID[1] || NODE_ID[1] || KEY_ID[1]`.

```text
M_ACCEPT =
  ASCII("LP2P/JOIN/V1/M-ACCEPT")           # 21B (no NUL)
  || DOWN_JOIN_ACCEPT[0..5]                #  6B
  || DEVICE_MAC[6]                         #  6B
  || JOIN_COUNTER[2]                       #  2B, uint16 BE
  || JOIN_RANDOM[10]                       # 10B
  || RELAY_GW_ID[1]                        #  1B, authenticated current target receiving Gateway
  || ASCII("RF-VN920-V1")                  # 11B
# TOTAL = 57B
AUTH_TAG = first16(HMAC-SHA256(K_JOIN_ASSIGN_DL, M_ACCEPT))
```

For **target Join Accept**, require `RELAY_GW_ID == TARGET_GW_ID` and bind the latest pending **target-Gateway** Request; this is distinct from earlier Discovery/Assignment that may pass through another relay. `REQUEST_REF` is the first two bytes of the outstanding `JOIN_RANDOM` and is a filter **only**, not an authenticator. Reject stale/ambiguous Request, different Gateway, reserved/unauthorized Node IDs, unknown KEY_ID mapping, expired/revoked assignment or invalid radio/CTRL window. Verify tag constant-time before deriving session keys, persisting Accept, or sending Confirm. Backend must persist the **exact 22 RF bytes** of its authorized Accept, and Node must retain those bytes to form approved `M_CONFIRM:79B`.

**No new BACKEND_RANDOM, nonce, padding, CRC16 or extra MIC.** The 12-byte authenticated Request Nonce provides fresh session KDF context. The HMAC domain `M-ACCEPT` differs from `M-ASN`; tags must not be interchangeable.

**Cross-Gateway edge:** Device must issue a **new** Request at the target Gateway with a new durable Counter/Random. Never reuse original Discovery nonce as a target Join nonce. If target Gateway is not currently authenticated/mapped, accept stays blocked; the above `M_ACCEPT` is not sufficient to resolve J06.

## Candidate deterministic Python test fixture — NOT owner approved

See [bootstrap-join-j02-proposed.json](test-vectors/bootstrap-join-j02-proposed.json) and [test_bootstrap_join_j02_proposed.py](../../tests/contract/test_bootstrap_join_j02_proposed.py). Values use public test-only `K_JOIN = 00..1f`, `DEVICE_MAC=24 6f 28 12 34 56`, **target Gateway=09**, `JOIN_COUNTER=01 24`, `JOIN_RANDOM=b1 c2 d3 e4 f5 06 17 28 39 4a`, `NODE_ID=0e`, `KEY_ID=01`. This is a **new target-Gateway Request**, not reuse of the earlier Discovery example with Counter 0x0123/relay 0x07.

Expected lengths: `M_UP:49B`, `M_ACCEPT:57B`, `SESSION_CONTEXT:32B`, `M_CONFIRM:79B`. Expected frames: Request 35B, Accept 22B, Confirm 19B. After J01/J02 Owner approval and Security review, independently reproduce in C and Go; Python-only fixture **is not** interoperability PASS.

## Review decision needed

| ID | Suggested approval scope | Does this close the gate immediately? |
|---|---|---|
| J01 | Freeze 35B Request exact fields, widths and mandatory checks **subject to J06 and G2** | **NO** until Owner approval and complete security review |
| J02 | Freeze 57B `M_ACCEPT` exact field order, tag and target-relay binding **subject to J06** | **NO** until Owner approval and G2 vectors |
| J06 | Provisioned Node-visible relay ID ↔ Backend authenticated Gateway ID, including scan/reboot/spoofing | **NO**, independent blocking design |

**Change control:** Any approval must name `J01` and `J02` explicitly; a PR review on a proposed test fixture does not silently make it the production crypto contract. [Owner decision history](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116), [current Join draft](bootstrap-join-v1.md).
