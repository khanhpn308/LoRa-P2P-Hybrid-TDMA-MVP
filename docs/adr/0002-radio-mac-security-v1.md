# ADR-0002 — Radio MAC V1: Compact post-Join frames and security boundaries

- **Decision date:** 2026-11-02
- **Decision owner:** Project Owner — explicit instruction: "ok khóa, cập nhật lại docs, file docx cho tôi" after reviewing the proposed compact READY/Recovery and security layout.
- **Status:** OWNER_APPROVED_DESIGN (design lock, **not** G2 security / C↔Go / HIL PASS).
- **Issue:** [#12](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/12); [PR #124](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124); prior [Beacon Group HMAC approval](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6575398231).
- **Scope:** `contracts/radio-mac/`; no change to four approved Join frames, radio PHY, MQTT/REST/DB contracts or schedule authorization policy.

## Decision: minimize RF airtime without weakening authorization

1. **Keep V1 Join wire layouts:** `UP_JOIN_REQUEST:35B`, `DOWN_JOIN_ASSIGNMENT:23B`, `DOWN_JOIN_ACCEPT:22B`, `UP_JOIN_CONFIRM:19B`; retain approved J01/J02 canonical `M_UP/M_DL/M_ACCEPT/M_CONFIRM`, `JOIN_COUNTER:2B`, `JOIN_RANDOM:10B`, three separately derived session/confirm keys and Backend-only Join trust.
2. **Keep Beacon V1 base: 28B Group HMAC-SHA256/16B tag** (`0x21`, 11B fixed core, `BCN_KEY_ID:1B`, `BCN_AUTH_TAG:16B`). No Ed25519. `JOIN_OPEN:16B` is a separate optional extension **not yet wire-frozen** (illustrative extended length 44B).
3. **Keep joined-unicast shared Header 7B:** `VER_TYPE:1B | NODE_ID:1B | KEY_ID:1B | FRAME_COUNTER:4B BE`. Not applied to Beacon or Join.
4. **Common joined-unicast MAC proposed for implementation review:** `M_RF = ASCII("LP2P/RF/V1/MAC") || DIR_U8 || GW_ID_U8 || FRAME_WITHOUT_MIC`. `DIR_U8` `0x01` Node→Gateway; `0x02` Gateway→Node; `GW_ID_U8` uses authenticated Gateway/assigned context, **not extra on-air bytes**. `MIC = first8(HMAC-SHA256(K_SESSION_UP/DL, M_RF))` for Telemetry, Alert, Result, compact READY; `MIC = first16(...)` for schedule/commands. Constant-time comparison; no use of PHY CRC as authentication. Key selection/session lookup, reserved encodings, counters and canonical input byte lengths still need independent security review and vectors.
5. **Lock compact READY: `UP_SCHED_READY:19B` (`0x28`)** = Header 7B + `TXN_REF:4B BE` + `MIC:8B`. Exact offsets: `0..6` Header, `7..10` transaction ref, `11..18` tag. **Supersedes proposed 41B READY**; no `SCHED_VER/SCHED_HASH/ACTIVATION_SF` repeated on air. Gateway MUST find a single immutable authenticated transaction by `TXN_REF`, bind it to authenticated Node/session, ensure required Node membership, and accept READY only when Node has *durably persisted* shadow schedule + old-slot fence. Original rules **100% READY**, complete authenticated `3→2→1`, ACTIVE Beacon, old-slot TX fence and expiry remain unchanged. Gateway cannot infer persisted state solely from MIC if Node implementation misbehaves.
6. **Lock compact Recovery Grant: `DOWN_AUTH_UPDATE:48B` (`0x2C`)**, replacing proposed 61B frame. Recovery must be **created and authenticated by Backend**; Gateway is forwarding-only and has neither `K_JOIN` nor `K_BACKEND_AUTH`. Remove Gateway MIC 8B and use a **single Backend HMAC-SHA256/16B** covering all 32B pre-tag bytes, bound to `SESSION_CONTEXT`, `GW_ID`, direction and a domain-separated purpose. Key derivation proposal: `K_BACKEND_AUTH = HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/BACKEND-AUTH") || SESSION_CONTEXT, 32)`; this is an **additional purpose-separated key** held by Backend+Node only, requiring security/key-lifecycle review before implementation. Backend must allocate the grant `FRAME_COUNTER` in its own non-repeating namespace; Gateway MUST NOT rewrite any authenticated header/counter fields. Replay/expiry/transaction/authorization revision/slot bitmap checks and durable accept-before-unfence are mandatory.

### Compact Recovery Grant byte layout (48B)

| Offset | Field | Bytes | Meaning |
|---|---|---:|---|
| 0..6 | Joined-unicast Header | 7 | `VER_TYPE=0x2C`, Node, Key ID, Backend-owned `FRAME_COUNTER:4B BE` |
| 7 | `AUTH_OP` | 1 | Recovery operation code; registry OPEN |
| 8..11 | `AUTH_REF` | 4 | Backend-issued unique grant reference; BE |
| 12..15 | `FAILED_TXN_REF` | 4 | Failed schedule transaction; BE |
| 16..19 | `SCHED_REF` | 4 | Unique immutable, authenticated schedule reference; BE |
| 20..21 | `AUTH_REV` | 2 | Authorization revision; BE, wrap/revocation policy OPEN |
| 22..23 | `SLOT_BITMAP` | 2 | Only mapped slots with fixed 16-bit indexing; exact mapping OPEN |
| 24..27 | `EFFECTIVE_SF` | 4 | Effective superframe; BE |
| 28..31 | `EXPIRY_SF` | 4 | Expiry superframe; BE |
| 32..47 | `BACKEND_TAG` | 16 | Backend-only HMAC truncated to 16B over complete first 32B and bound context |
| **TOTAL** | | **48B** | No `GW_MIC`. The authenticated `SCHED_REF` must resolve to the correct full schedule, including hash/authorization and stable slot mapping. |

**Important caveat:** No generic 48B frame may restore arbitrary slot rights. `SLOT_BITMAP` represents only the fixed, previously defined compact slot-index space; if a planned schedule cannot be represented, **deny grant / use a separately versioned extension**, not silent truncation. A Gateway with `K_SESSION_DL` alone cannot forge `BACKEND_TAG`; a compromised Backend/Node secret remains a separate risk. The exact canonical Backend tag transcript, key provisioning/durability, special opcode values and independent C↔Go proof remain **G2 NOT_VERIFIED**; do not advertise them as completed security sign-off.

## Remaining security decisions / threat model

- **J06** Gateway identity: Group HMAC authenticates *group key possession*, **not unique Gateway origin**; compromised member Node could forge Beacon. Backend MQTT TLS identity ↔ RF `GW_ID`, Node's provisioned/observed gateway binding and exact Join `RELAY_GW_ID` proof must be designed against relay/cross-Gateway substitution without inflating `UP_JOIN_REQUEST:35B`.
- **J07** durable `JOIN_COUNTER:2B` lifecycle, random persistence, bounded reservation/high-water, exhaustion, rollback/rekey and protected ESP32 `K_JOIN` provisioning; per-session directional `FRAME_COUNTER:4B` and Backend-issued grant counters independently monotonic. No reused counters under one session key after reboot. A retry may retransmit the **same byte-identical authenticated frame**, not mutate payload under same counter.
- **Recovery** Backend-issued, Node-verified authorization and persistence; Gateway only forwards; explicit failure/slot coverage/expiry, safe SF boundary and durable TX fence supersession. Preserved schedule cutover and 100%-READY policy; a valid Beacon alone never enables RF DATA TX.
- **ADR / independent tests:** Full threat analysis (compromised Node with shared beacon key; rogue Gateway; replay and reboot; duplicate/late grants; counter wrap), executable C encoder↔Go decoder and Go encoder↔C decoder Golden Vectors with positive/negative expected results, RF ToA and guard, human Security/Gateway/Node/Backend review.

## Timing / design limitation

Calculated theoretical LoRa ToA with BW125, CR4/5, preamble 8, explicit header, PHY CRC ON, SX1276 formula (excluding guard/turnaround):

| MAC size | SF7 | SF8 | SF10 | SF12 (LDRO ON) |
|---|---:|---:|---:|---:|
| Beacon 28B | 66.82 ms | 123.39 ms | 411.65 ms | 1646.59 ms |
| READY 41B (superseded) | 87.30 ms | 154.11 ms | 534.53 ms | 2138.11 ms |
| READY 19B (locked) | 51.46 ms | 102.91 ms | 329.73 ms | 1318.91 ms |
| Recovery 61B (superseded) | 112.90 ms | 205.31 ms | 698.37 ms | 2793.47 ms |
| Recovery 48B (locked) | 97.54 ms | 174.59 ms | 575.49 ms | 2301.95 ms |

**P-10S-15 400ms DATA slot and 250ms Beacon zone are mock assumptions**; 19B READY at SF10 may still violate actual allowed TX budget/guard, 48B Recovery at SF10 exceeds even 400ms, and 28B Beacon at SF10 exceeds 250ms. Do not enable either transmission without a verified schedule/PHY profile. `G2/G3/HIL/Regulatory=NOT_VERIFIED`.

## Consequences and change control

- No change to Join 35/23/22/19B, owner-approved RF packet type assignments, original schedule/lease/activation trust decisions.
- Protocol compatibility break relative to previous 41B READY and 61B Recovery drafts. Update versioned radio encoder/decoder and tests before any deployment; previous draft fixtures are not authoritative.
- **G0: NOT_RUN** (GitHub connector edits only), **G2: NOT_VERIFIED**, CI/conformance/HIL not claimed PASS. **Issue #12 must remain OPEN** until mandatory review/evidence is attached.
