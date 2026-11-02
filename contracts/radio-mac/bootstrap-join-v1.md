# Bootstrap Join v1 — Design-to-Contract consolidation

> **Status: DESIGN CONSOLIDATED / CONTRACT DRAFT / IMPLEMENTATION_READY = NO / G2 NOT_VERIFIED.** Scope: only LoRa **P2P Custom MAC** Join/Assignment/Accept/Confirm, key derivation, and dependency on Gateway↔Backend key installation. **NOT LoRaWAN.** This document **transcribes Owner-locked decisions** from PR #116, not an independent new Owner approval, security review, or license to deploy on RF.
>
> **Precedence:** [PR #116 Owner decisions](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116) for their specific approved scope → this consolidation → old [specification.md](specification.md) legacy 0.1.0-draft. Do not infer that the PR discussion supersedes all legacy contracts or that merged `main` already implements it. Explicitly unresolved fields/semantics below **MUST NOT be guessed by an Agent**. [Decision/gate register](bootstrap-join-gates.md).

## 1. Terminology, source and scope

| Classification | Meaning |
|---|---|
| `OWNER_APPROVED_DESIGN` | Owner locked named fields, widths, rules or cryptographic formulas **only as recorded** |
| `CANDIDATE` | Candidate discussed but **not** locked as an entire frame/codec |
| `OPEN_G2` | Missing or incompatible details require explicit decision + Security/Radio/Backend review |
| `NOT_VERIFIED` | No trustworthy cross-language/HIL/production security evidence |
| `IMPLEMENTATION_READY` | Must have no remaining blocking gaps for the specific slice and a versioned reviewed contract |

The approved `VER_TYPE` is 1B: bits 7..5 = `PROTO_VER`, bits 4..0 = `PACKET_TYPE`, V1 `PROTO_VER=1`. Reject unknown/reserved `0x20`, `0x3F`, wrong direction and length. The old `MAGIC:0xA5 + 8B header + CRC16` in [specification.md](specification.md) is **legacy candidate**, NOT part of the current Bootstrap RF frame, and must not be prepended, treated as auth, or concatenated to these lengths. LoRa PHY Preamble/Header/CRC airtime is **separate**. Relevant Owner record: [RF-VER-TYPE-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568296930).

## 2. RF MAC Join frame registry

Every offset is zero-based **within the MAC payload passed to SX1276 FIFO**. Sizes below EXCLUDE LoRa PHY overhead; **no second 8B MIC/CRC is implicitly appended**.

### 2.1 `UP_JOIN_REQUEST` — **35B CANDIDATE; full frame NOT OWNER-FROZEN**

| Offset | Field | Width | Value/rule |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1B | `0x22` (**code point LOCKED**) |
| 1–6 | `DEVICE_MAC` | 6B | Provisioned Node identity; not a secret |
| 7–8 | `JOIN_COUNTER` | 2B | Unsigned, big-endian, durable monotonic |
| 9–18 | `JOIN_RANDOM` | 10B | Fresh 80-bit CSPRNG bytes |
| 19–34 | `JOIN_PROOF` | 16B | First 16B HMAC-SHA-256 under derived `K_JOIN_REQ` |
| **Total** | | **35B** | Candidate structure; do NOT label entire uplink frame `OWNER_APPROVED` |

The 12B request nonce `JOIN_COUNTER[2] || JOIN_RANDOM[10]` is OWNER_APPROVED. New discovery request/channel or relay Gateway ⇒ fresh counter, random and proof. Retrying the *same* request with the *same relay context* may reuse exact RF bytes within authorized opportunity. Do not wrap counter in same key/replay domain. Sources: [RF-BOOT-NONCE-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567306330), [RF-HMAC/REPLAY](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568170563).

### 2.2 `DOWN_JOIN_ASSIGNMENT` — **23B OWNER_APPROVED_DESIGN**

| Offset | Field | Width | Value/rule |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1B | `0x23` |
| 1–2 | `REQUEST_REF` | 2B | First 2 bytes of outstanding `JOIN_RANDOM`, copied unchanged (uint16 BE if interpreted); hint only |
| 3 | `TARGET_GW_ID` | 1B | User/Backend authorized RF Gateway ID |
| 4–5 | `FREQ_OFFSET_KHZ` | 2B | uint16 BE, 1 kHz resolution from `F_BASE=920,000,000 Hz` |
| 6 | `PHY_PROFILE_ID` | 1B | Versioned profile registry, 0x01..0x06 only for approved plan |
| 7–22 | `AUTH_TAG` | 16B | First 16B HMAC-SHA-256 under `K_JOIN_ASSIGN_DL` |
| **Total** | | **23B** | No `ASSIGNMENT_REV` or `ASSIGNMENT_ID` on RF |

`REQUEST_REF` is neither identity nor anti-replay. A matching ref without validated full Join context/HMAC MUST be rejected. Assignment does not confer DATA rights. It may arrive through the **latest observing Gateway**; relaying Gateway differs from `TARGET_GW_ID`. Source: [RF-JOIN-ASSIGN-FRAME-02](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567010014) + [RF-HMAC](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568170563).

### 2.3 `DOWN_JOIN_ACCEPT` — **22B OWNER_APPROVED_DESIGN**

| Offset | Field | Width | Value/rule |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1B | `0x24` |
| 1–2 | `REQUEST_REF` | 2B | Latest pending **target-Gateway** authenticated request |
| 3 | `TARGET_GW_ID` | 1B | Must match authorized target |
| 4 | `NODE_ID` | 1B | Backend-allocated, scoped to Gateway |
| 5 | `KEY_ID` | 1B | Radio key selector, not Session ID |
| 6–21 | `AUTH_TAG` | 16B | First 16B HMAC-SHA-256 under `K_JOIN_ASSIGN_DL`, **distinct M_ACCEPT transcript** |
| **Total** | | **22B** | **No `BACKEND_RANDOM`** |

**BLOCKER:** Owner approved a purpose-separated candidate domain `ASCII("LP2P/JOIN/V1/M-ACCEPT")`, authentication covering the first 6 transmitted bytes, `DEVICE_MAC`, full request nonce, relay/target context and RF plan, but **exact M_ACCEPT field order/byte-level transcript is NOT frozen**. Agent MUST NOT invent one and call it production. Preserve exact accepted 22B RF bytes in durable Backend Join transaction to compute Confirm. Source: [RF-JOIN-ACCEPT-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568432331).

### 2.4 `UP_JOIN_CONFIRM` — **19B OWNER_APPROVED_DESIGN**

| Offset | Field | Width | Value/rule |
|---:|---|---:|---|
| 0 | `VER_TYPE` | 1B | `0x25` |
| 1 | `NODE_ID` | 1B | From authenticated Accept |
| 2 | `KEY_ID` | 1B | From authenticated Accept |
| 3–18 | `CONFIRM_TAG` | 16B | First 16B HMAC-SHA-256 under `K_JOIN_CONFIRM` |
| **Total** | | **19B** | No duplicated `JOIN_COUNTER` on RF |

Gateway is a bounded **untrusted relay for Node-origin proof**, and never receives `K_JOIN_CONFIRM`. Backend finds **exactly one** pending `WAIT_CONFIRM` by authenticated receiving Gateway + `NODE_ID, KEY_ID`, checks expiry/revision/freshness and verifies MAC constant-time. A repeated valid Confirm can be idempotent for **the same durable transaction only**, never grant new rights. Source: [RF-JOIN-CONFIRM-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568810810).

## 3. Cryptography: approved key derivation and transcripts

All strings are exact ASCII (no trailing `NUL` or separators unless explicitly part of the literal), `||` is raw concatenation, HMAC truncation takes the *first 16 bytes*, and tag comparisons are constant-time. `K_JOIN` is a unique CSPRNG-generated 32B per-device secret held **only by Node and Backend**; Gateway must not hold it.

```text
SALT            = ASCII("LP2P/JOIN/V1/SALT")                    // 17B
PRK             = HMAC-SHA256(SALT, K_JOIN)                     // 32B
K_JOIN_REQ      = HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/K-REQ")    || DEVICE_MAC[6], 32)
K_JOIN_ASSIGN_DL= HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/K-ASN-DL") || DEVICE_MAC[6], 32)
JOIN_PROOF      = first16(HMAC-SHA256(K_JOIN_REQ, M_UP))
ASSIGN_AUTH_TAG = first16(HMAC-SHA256(K_JOIN_ASSIGN_DL, M_DL))
```

`M_UP` **byte-exact approved construction**:

| Sequence | Components | Width |
|---:|---|---:|
| 1 | `ASCII("LP2P/JOIN/V1/M-REQ")` | 18B |
| 2 | `UP_JOIN_REQUEST[0..18]`: `VER_TYPE,DEVICE_MAC,JOIN_COUNTER,JOIN_RANDOM` | 19B |
| 3 | `RELAY_GW_ID` from current receiving Gateway context | 1B |
| 4 | `ASCII("RF-VN920-V1")` | 11B |
| **Total** | | **49B** |

`M_DL` **byte-exact approved construction**:

| Sequence | Components | Width |
|---:|---|---:|
| 1 | `ASCII("LP2P/JOIN/V1/M-ASN")` | 18B |
| 2 | `DOWN_JOIN_ASSIGNMENT[0..6]` | 7B |
| 3 | `DEVICE_MAC` | 6B |
| 4 | `JOIN_COUNTER` BE | 2B |
| 5 | `JOIN_RANDOM` | 10B |
| 6 | `RELAY_GW_ID` tied to outstanding request | 1B |
| 7 | `ASCII("RF-VN920-V1")` | 11B |
| **Total** | | **55B** |

**Critical context invariant:** Neither frame carries `RELAY_GW_ID` on-air. Node and Backend must agree on authenticated current relay identity; whether discovery Beacon gives Node enough trustworthy context is an **OPEN_G2 threat-model/security integration gate** (GATE-J06). The HMAC binding does not by itself make an unauthenticated Beacon trustworthy.

`M_ACCEPT`: **UNRESOLVED_CANONICAL_TRANSCRIPT**, see §2.3. Do not treat its 22B frame size as an approved tag-byte implementation.

`SESSION_CONTEXT` **exact 32B**:

| Offset | Bytes | Meaning |
|---:|---:|---|
| 0–5 | 6B | `DEVICE_MAC` |
| 6 | 1B | `TARGET_GW_ID` |
| 7 | 1B | `NODE_ID` |
| 8 | 1B | `KEY_ID` |
| 9–10 | 2B | `JOIN_COUNTER` BE |
| 11–20 | 10B | `JOIN_RANDOM` |
| 21–31 | 11B | `ASCII("RF-VN920-V1")` |

Three 32B keys, distinct HKDF-Expand domains:
```text
K_SESSION_UP    = HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/SESSION-UP")      || SESSION_CONTEXT, 32)
K_SESSION_DL    = HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/SESSION-DL")      || SESSION_CONTEXT, 32)
K_JOIN_CONFIRM  = HKDF-Expand(PRK, ASCII("LP2P/JOIN/V1/SESSION-CONFIRM") || SESSION_CONTEXT, 32)
```
`K_SESSION_UP/DL` go to **target Gateway only** after Backend verifies Node Confirm; `K_JOIN_CONFIRM` stays on Node+Backend only. This KDF gives **no forward secrecy** if long-term `K_JOIN` is later compromised. Source: [RF-SESSION-KEY-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568716035).

`M_CONFIRM` **exact 79B OWNER_APPROVED_DESIGN**:

| Sequence | Field | Width |
|---:|---|---:|
| 1 | `ASCII("LP2P/JOIN/V1/M-CONFIRM")` | 22B |
| 2 | `UP_JOIN_CONFIRM[0..2]` | 3B |
| 3 | `SESSION_CONTEXT` | 32B |
| 4 | **Exact authenticated** `DOWN_JOIN_ACCEPT[0..21]` including its tag | 22B |
| **Total** | | **79B** |

`CONFIRM_TAG=first16(HMAC-SHA256(K_JOIN_CONFIRM, M_CONFIRM))`. Exact Accept bytes MUST be durable in the Pending Backend transaction and Node memory. An unknown or ambiguous pending transaction ⇒ reject; never search through multiple K_JOIN secrets or accept a first-matching tag.

## 4. RF plan and PHY profile binding (Owner-approved design)

For `RF-VN920-V1`, `F_BASE=920000000 Hz`. `FREQ_OFFSET_KHZ:uint16 BE`, `F_target = F_BASE + 1000*offset`. `0x0578` means **921400000 Hz** (not evidence of legal authorization).

| `PHY_PROFILE_ID` | SF | BW | CR | LDRO |
|---|---:|---:|---|---|
| `0x01` | 7 | 125kHz | 4/5 | OFF |
| `0x02` | 8 | 125kHz | 4/5 | OFF |
| `0x03` | 9 | 125kHz | 4/5 | OFF |
| `0x04` | 10 | 125kHz | 4/5 | OFF |
| `0x05` | 11 | 125kHz | 4/5 | ON |
| `0x06` | 12 | 125kHz | 4/5 | ON |

Shared **initial candidate** PHY settings: 8-symbol preamble, explicit header, PHY CRC ON, IQ inversion OFF. **Numeric SyncWord, TX power, final allowed RF channel list, hardware/antenna validation and Vietnam regulatory review remain OPEN**. Version mismatch ⇒ fail closed. Do not infer every representable offset is legal. Source: [RF-FREQ-01 / RF-PHY-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567194577).

## 5. Bootstrap Join lifecycle: three independently controlled sides

| Step | Node state / action | Gateway action | Backend transaction |
|---:|---|---|---|
| 1 | `UNASSIGNED` scans provisioned Discovery frequencies/profiles | Advertise/receive in approved CTRL | Stores User-authorized assignment/revision/expiry |
| 2 | Reserve fresh high-water Counter, CSPRNG Random, send `UP_JOIN_REQUEST` in allowed CTRL UL | Capture raw RF bytes + current authenticated GW channel/identity, relay to Backend | Authenticate Proof, persistent anti-replay, check approval |
| 3 | Stay RX on **same relay frequency** for permitted Response Window | Relay Backend-selected `DOWN_JOIN_ASSIGNMENT` only within approved CTRL DL | Select latest valid observing Gateway; avoid MQTT-arrival-order ambiguity |
| 4 | Validate authentic fresh Assignment; retune to target GW/profile | No autonomous ID allocation | `ASSIGNMENT_PENDING`; no DATA lease |
| 5 | Send **new** `UP_JOIN_REQUEST` to target GW with fresh counter/random/proof | Target GW relays to Backend | Revalidate current assignment, capacity/revision, persist pending Join & exact Accept bytes |
| 6 | Accept only matching `DOWN_JOIN_ACCEPT`; derive Session Context/Keys | Send Backend-authored Accept in valid DL RX Window | `PENDING_ACCEPT / WAIT_CONFIRM` |
| 7 | Send `UP_JOIN_CONFIRM` 19B in valid CTRL UL, then wait | Relay exact bytes, cannot verify Node proof | Verify `K_JOIN_CONFIRM`, ensure unique pending session, persist `NODE_CONFIRMED` atomically |
| 8 | Stay `WAIT_JOIN_COMPLETION / WAIT_TDMA` (not DATA) | Receive provisioned `K_SESSION_UP/DL` encrypted, persist `INSTALLED_INACTIVE`, send application ACK | MQTT key install/ACK state; only advance to `KEY_INSTALLED` after authenticated ACK |
| 9 | Only operate after authenticated timing/schedule/lease and activation | Enforce radio-owner half-duplex, approved slots, lease expiry | Approve schedule/lease; no MQTT PUBACK = activation |

This is a **logical flow**, not a complete executable state machine. Status labels at the Node, Gateway and Backend are not necessarily identical. Must implement explicit timeouts, retries, cancellation precedence, durable state/version, lost-result reconciliation and Node Join Completion/TDMA activation contract after security review. Source: [RF-JOIN-ASSIGNMENT-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562684029), [RF-JOIN-RESPONSE-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562516222), [RF-JOIN-CONFIRM-01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568810810).

### Timing and authorization invariants

- Shared CTRL is fixed/Backend-planned/User-approved, logically after Beacon and before Priority Alert/DATA, with non-overlapping scheduled RX/TX opportunities; **one SX1276/Gateway, never simultaneous TX/RX**. `JOIN_CLOSED` by default; cannot spontaneously open due to loss of backhaul. [SF-RECOVERY-05](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6559992609).
- After each `UP_JOIN_REQUEST`, Node must stay RX at *the same frequency* over the approved response window before channel hopping. Timing/number of DL slots is **OPEN**.
- On Node reboot, pending Join invalidated and a **new** durable monotonic Counter required. On Active Node reboot, V1 fail closed and fresh Join (unless separate authorized resume contract). No counter wrap/rollback/reuse. Backend transactionally tracks highest authenticated counter and exact retry identity; Gateway cannot advance that state.
- ACK Bitmap inside Beacon is **for Telemetry only**, not Join/Alert/Confirm ACK. RF response TX, Gateway MQTT PUBACK, and Install ACK each have distinct meanings and never prove final Node DATA eligibility.
- Gateway never knows `K_JOIN` or `K_JOIN_CONFIRM`. Never log raw secret/session keys; HMAC authentication is not encryption. An authenticated Assignment/Accept/Confirm alone NEVER grants data entitlement.
- Any outdated assignment/revocation, ambiguous Pending, replay, mismatched Gateway/PHY/RF plan, untrusted time/invalid schedule, incomplete security storage or CTRL airtime budget must **fail closed**.

## 6. Interface boundaries and upstream dependencies

- **Node↔Gateway RF** uses frames above and separate authenticated Beacon/CTRL scheduling (Beacon auth still OPEN).
- **Gateway↔Backend Join relay and Assignment/Accept dispatch MQTT**: **NOT YET SCHEMA-LOCKED**. Existing `downlink/command` (requires assigned Node ID) is NOT automatically valid for unjoined request. A versioned MQTT discovery/join contract and transactional Backend DB schema are required; do NOT invent topic or fields.
- **Backend→Gateway Session Key**: `MQTT-SESSION-KEY-01`, `MQTT-KEY-WRAP-01`, `MQTT-KEY-ACK-01` design OWNER_APPROVED. Versioned **DRAFT** schemas live in [PR #123](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/123) (`contracts/mqtt/schemas/session-key-install.schema.json`, `session-key-ack.schema.json`), not yet integrated to main. Cross-repo/branch build must pin compatible versions.
- **Node-ready schedule/lease/Join Completion** and secure independent Downlink ACK: OPEN, not made up in this contract. No DATA before actual approved schedule and Beacon sync.

## 7. Test and agent implementation boundary

See [bootstrap-join-gates.md](bootstrap-join-gates.md) and [bootstrap-join-structural.json](test-vectors/bootstrap-join-structural.json). Structural fixtures **cannot produce valid HMACs without all locked canonical transcripts**, and are explicitly **NOT cryptographic Golden Vectors**.

**Agents MAY** develop pure serializers/deserializers, length/version/offset guards, 32B Session Context construction, RFC5869 HKDF and HMAC building blocks and tests for already defined `M_UP`, `M_DL`, `M_CONFIRM`, using independently checked vectors with correct codes 0x22/0x23/0x25. Any provisional code must remain isolated behind `DRAFT` boundaries.

**Agents MUST NOT**: silently finalize `UP_JOIN_REQUEST` candidate, `M_ACCEPT` transcript, Gateway/Node states, MQTT Join topics, timing/expiry/retries, RF channels/SyncWord/power, or enable production Join/DATA TX; they must raise gaps and request review. Security and timing-affecting implementation requires human technical review, integration/HIL and G2 evidence.

**Release verdict:** `IMPLEMENTATION_READY = NO` for end-to-end Join; `G2_SECURITY = NOT_VERIFIED`; `RF_HIL = NOT_VERIFIED`; `MQTT_JOIN_CONTRACT = OPEN`. Owner decision approval in PR comments is distinct from contract/CI/security gate approval.
