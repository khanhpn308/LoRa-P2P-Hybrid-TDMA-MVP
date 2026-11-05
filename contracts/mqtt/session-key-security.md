# MQTT session-key installation — wire contract and semantic rules

**Status:** `DRAFT / CROSS-TEAM REVIEW PENDING`. Design basis: OWNER_APPROVED `MQTT-SESSION-KEY-01`, `MQTT-KEY-WRAP-01`, `MQTT-KEY-ACK-01` in [PR #116 discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568895005). This document proposes precise implementation encoding; the proposed exact byte codec still requires **G2 security review, Go↔ESP-IDF golden vectors and integration verification**. It does not retroactively approve runtime code.

## 1. Interfaces, identities and scope

| Message | MQTT 5 topic | Publisher | Consumer | QoS | Retain |
|---|---|---|---|---:|---|
| `SESSION_KEY_INSTALL` | `iot/v1/gw/{gateway_id}/downlink/session-key-install` | Backend | Gateway | 1 | false |
| `SESSION_KEY_ACK` | `iot/v1/gw/{gateway_id}/uplink/session-key-ack` | Gateway | Backend | 1 | false |

JSON UTF-8 payloads use `schema_version="1.1-draft"`, `install_protocol_version=1` / `ack_protocol_version=1`, and `aad_version=1` for Install. See `schemas/session-key-install.schema.json` and `schemas/session-key-ack.schema.json`. Unknown fields/versions are rejected. `gateway_id` is the **MQTT string principal/topic identity** (e.g. `gw01`), consistent with existing `topics.md`; `target_gw_id` is the distinct **uint8 RF Gateway ID**. A versioned, authorized Backend↔Gateway mapping must equate them. A numeric RF code must never be silently parsed from arbitrary MQTT string. The Node/Backend `SESSION_CONTEXT` is exactly the previously locked 32 bytes; `session_context_hash` = lowercase hex SHA-256 of that context.

Gateway installs **only** `K_SESSION_UP[32] || K_SESSION_DL[32]` from one pending, Backend-authorized, Node-confirmed session (triggered upon authentic Node key confirmation: `UP_JOIN_CONFIRM:19B` in V1 or `UP_JOIN_KEY_CONFIRM:33B` / `DOWN_JOIN_FINISH:31B` in V2 #136). Gateway MUST NEVER be sent `K_JOIN` or `K_JOIN_CONFIRM`. `KEY_ID:1B` is not the unique session identity; `session_id` UUID plus authorization/revision is Backend/Gateway management metadata, absent from radio frames. Success means key slot durably `INSTALLED_INACTIVE` only; not DATA permission, not an active TDMA Lease.

## 2. JSON wire encoding

- `device_mac`: exactly 12 lowercase hexadecimal digits, no separators (decode to 6 bytes).
- `session_id`, `install_id`: canonical lowercase UUID strings, decoded to 16 network-order bytes for binary authentication transcripts. Consumers MUST reject noncanonical variants even if a generic UUID format checker tolerates them.
- `session_revision`, `assignment_revision`: canonical **decimal strings** representing uint64 (no leading zeros except single `"0"`, no negative sign), validated with exact upper bound `18446744073709551615`. `session_revision >= 1`; parse with uint64/BigInt, **not IEEE-754 floating-point**.
- `not_before`, `expires_at`, `install_deadline`: RFC3339 UTC strings with `Z`. For canonical cryptographic encoding accept `YYYY-MM-DDTHH:MM:SSZ` or `YYYY-MM-DDTHH:MM:SS.sssZ`; reject other precision, leap-second/invalid values and pre-1970 times; convert to nonnegative **uint64 Unix epoch milliseconds**. Parsing must not use local timezone.
- `nonce`, `ciphertext`, `tag`, `ack_tag`: canonical RFC 4648 *standard* Base64, including `=` padding where required; decoded lengths **12B, 64B, 16B, 16B** respectively. Reject whitespace, URL-safe alphabet and noncanonical pad-bit variants; verify decode-then-reencode equality.
- `target_gw_id: uint8`; `node_id: uint8` in current legacy candidate 1..254; `key_id: uint8`; `wrap_key_id: uint32`. RF code-point reservation and mapping need Gateway/RF review before production.
- Cryptographic tags are **synthetic placeholders only** in `examples/session-key-cases.json`; schema-valid case is NOT an authentic AES-GCM/HMAC message.

## 3. Canonical binary encoding V1 (proposal)

Never authenticate raw JSON serialization; object key order, escaping and whitespace are not canonical. Let:
- `U8/U32/U64`: fixed-width unsigned integer in big-endian.
- `LP(s)`: `U16(byte_length(UTF8(s))) || UTF8(s)`; reject lengths >65535 and invalid UTF-8. Required protocol strings are ASCII.
- `UUID(s)`: 16 bytes from the canonical UUID hex digits (without separators).
- `MAC(s)`: 6 decoded bytes.
- `SHA(s)`: 32 decoded bytes from the exact 64 lower-hex characters.
- `B64(s)`: canonical Base64-decoded bytes.
- `TIME(s)`: `U64(UnixMillisecondsUTC(s))`.

**Install AAD V1:** Concatenate the following fields **exactly in this order**. Missing or additional values must not be silently tolerated:

| # | Bytes appended |
|---:|---|
| 1 | `LP("LP2P/MQTT/V1/KEY-INSTALL")` |
| 2 | `LP(exact canonical MQTT topic)` |
| 3 | `LP(schema_version)` |
| 4 | `U8(install_protocol_version)` |
| 5 | `U8(aad_version)` |
| 6 | `LP(gateway_id)` |
| 7 | `U8(target_gw_id)` |
| 8 | `MAC(device_mac)` |
| 9 | `U8(node_id)` |
| 10 | `U8(key_id)` |
| 11 | `UUID(session_id)` |
| 12 | `UUID(install_id)` |
| 13 | `U64(session_revision)` |
| 14 | `U64(assignment_revision)` |
| 15 | `SHA(session_context_hash)` |
| 16 | `TIME(not_before)` |
| 17 | `TIME(expires_at)` |
| 18 | `TIME(install_deadline)` |
| 19 | `U32(wrap_key_id)` |
| 20 | `LP(crypto_suite)` |
| 21 | `B64(nonce)` (12B, also provided to AES-GCM as IV) |

**Wrap:** `K_GW_WRAP:32B` is an independently provisioned per-Gateway secret held only by Backend and its designated Gateway. `wrap_key_id` identifies the valid active/rotating wrapping key. `AES-256-GCM(key=K_GW_WRAP, iv=nonce[12], plaintext=K_SESSION_UP[32] || K_SESSION_DL[32], aad=InstallAAD)` yields `ciphertext[64]` and `tag[16]`. Reject GCM tag failure **before using or persisting decrypted key bytes**. The AEAD encryptor/decryptor must not emit plaintext or key dumps to logs. Secure storage and zeroization rules require implementation review.

**Nonce:** 12B = `WRAP_KEY_EPOCH:U32 || WRAP_SEQUENCE:U64`. For a given `(Gateway,K_GW_WRAP)`, every fresh encryption MUST have a unique nonce, including after crashes, backup restores, migrations and key rotation. Atomically reserve persistent sequence/epoch; collision, overflow, rollback or missing state ⇒ stop encryption and rekey/reconcile. A byte-identical retry uses its **original install_id, nonce, ciphertext, tag and unchanged AAD**: never re-encrypt at the same nonce. Changing any metadata requires a new install operation and fresh nonce; this may also require new authorization/revision.

## 4. Application ACK authenticity (proposal)

Gateway sends an authenticated ACK **only after** its security/authorization/expiry checks. For `status=INSTALLED`, the durable protected inactive key slot and idempotency mapping must be committed **before** sending ACK. If `K_GW_WRAP` is unknown/invalid, Gateway cannot produce a valid HMAC ACK; report operational failure without fabricating an authenticated rejection.

To prevent cross-purpose key use, propose:
`ACK_PRK = HKDF-Extract(salt=ASCII("LP2P/MQTT/V1/ACK-SALT"), IKM=K_GW_WRAP)`
`K_ACK = HKDF-Expand(ACK_PRK, LP("LP2P/MQTT/V1/KEY-INSTALL-ACK") || U32(wrap_key_id) || LP(gateway_id), 32)`.

**ACK transcript V1** `M_ACK` is the exact concatenation:

| # | Bytes appended |
|---:|---|
| 1 | `LP("LP2P/MQTT/V1/M-ACK")` |
| 2 | `LP(exact canonical ACK topic)` |
| 3 | `LP(schema_version)` |
| 4 | `U8(ack_protocol_version)` |
| 5 | `LP(gateway_id)` |
| 6 | `UUID(install_id)` |
| 7 | `UUID(session_id)` |
| 8 | `U64(session_revision)` |
| 9 | `U32(wrap_key_id)` |
| 10 | `LP(status)` |
| 11 | `LP(reason_code)` |

`ack_tag = first16(HMAC-SHA256(K_ACK, M_ACK))`, compare constant-time. `INSTALLED` requires `reason_code=NONE`; `REJECTED` requires non-NONE reason, limited by schema enum. Backend MUST match the *currently authorized* pending install record, Gateway/topic/principal, session ID, revision and wrap key. Even authenticated old/duplicate ACKs cannot resurrect expired/revoked sessions, extend lease, or advance another transaction. A valid HMAC proves a party holding the Gateway wrapping key signed an ACK; **it is not a cryptographic proof that Flash/NVS persistence actually succeeded**. That property requires trustworthy Gateway implementation and fault-injection testing.

## 5. Cross-field and environment rules (must enforce outside JSON Schema)

| ID | Producer/consumer | Required check | Failure / state |
|---|---|---|---|
| SK-01 | Mosquitto, both apps | MQTT 5.0, TLS, per-principal ACL; topic suffix, principal and payload `gateway_id` match | reject `WRONG_GATEWAY` |
| SK-02 | Gateway | Map MQTT `gateway_id` ↔ authorized `target_gw_id`, bound to provisioned RF plan/identity; in MVP each Gateway holds one exclusive VN920 channel CH00–CH10 (920.250–922.750 MHz) registered persistently in PostgreSQL (#154) | reject `WRONG_GATEWAY` |
| SK-03 | Backend | Only authenticated Node key-confirmed session (`UP_JOIN_CONFIRM` in V1 or `UP_JOIN_KEY_CONFIRM`/`DOWN_JOIN_FINISH` in V2 #136) with current User-approved target and assignment revision may be installed | never emit unauthorized install |
| SK-04 | Gateway | `not_before < expires_at`; `install_deadline <= expires_at`; trusted UTC at processing < deadline; MQTT5 Message Expiry ≤ deadline; non-retained | reject `EXPIRED` or `UNTRUSTED_CLOCK` |
| SK-05 | Gateway | Parse canonical fields/Base64/UUID/uint64 exactly, enforce 64B ciphertext/16B tag/12B nonce, reconstruct AAD from authenticated topic | `BAD_SCHEMA` or `BAD_AUTH` |
| SK-06 | Gateway | AES-GCM tag valid with matching `wrap_key_id` and provisioned K_GW_WRAP; session context hash matches Backend-authorized 32B context digest | reject `BAD_AUTH` |
| SK-07 | Backend | Nonce uniqueness under same wrap key across restart/restore; fail closed on exhausted/uncertain epoch/sequence | do not encrypt |
| SK-08 | Gateway | `(GW_ID,NODE_ID,KEY_ID)` resolves unambiguously; at most one ACTIVE + one PENDING per Node/Gateway, never ambiguous key selection | reject `KEY_SLOT_CONFLICT` |
| SK-09 | Gateway | `session_revision` monotonic, `install_id` stable, exact-message idempotency; same ID different message = conflict | `STALE_REVISION` / `DUPLICATE_CONFLICT` |
| SK-10 | Gateway | Persist protected inactive keys + installation/dedup/expiry/revision metadata atomically before `INSTALLED` ACK; restore check after reboot | `PERSIST_FAILED`; never mark ACTIVE |
| SK-11 | Backend | Authenticate ACK HMAC (separate HKDF key); bind topic/principal and pending install/session/revision/expiry/current authority | ignore/quarantine stale, bad or conflicting ACK |
| SK-12 | Both | No key-install action or successful ACK by MQTT PUBACK alone; reconnect replay/reorder safe; bounded retry same envelope and `install_id` | reconcile persisted state |
| SK-13 | Gateway/Backend | Loss of backhaul/revocation/expiry never extends device privileges; in Event-Only V2 architecture (#125, #136), Node readiness `UP_JOIN_READY` (0x49), TDMA staging/countdown (3→2→1), boundary activation K+H, and all 8 DATA TX guards are also required before DATA transmission | keep inactive/suspend |
| SK-14 | Security | Secrets absent from RF, plaintext MQTT, logs, telemetry, exceptions and fixture data; verify wrap key provisioning/rotation | block release |
| SK-15 | Gateway | Unknown protocol/AAD version, unsupported crypto, untrusted clock, counter rollback or invalid storage ⇒ fail closed | reject with specific reason if authenticated ACK possible |

`SESSION_KEY_INSTALL` and `SESSION_KEY_ACK` are **new versioned MQTT topics**. Do not silently change existing `downlink/command` or `uplink/command-ack` semantics. Implementer must reconcile common `schema_version` evolution separately (legacy examples remain `1.0-draft` while new schemas adopt `1.1-draft` per topics.md).

## 6. Persistence, concurrency, state transitions

| Backend state | Trigger | Next state / invariants |
|---|---|---|
| `NODE_CONFIRMED` | Authorized session (V1 `UP_JOIN_CONFIRM` or V2 `UP_JOIN_KEY_CONFIRM` + `DOWN_JOIN_FINISH`), insert install intent with stable ID and fresh AEAD envelope | `INSTALL_PENDING` |
| `INSTALL_PENDING` | Publish QoS1 Retain=false, valid TTL and current authority | `INSTALL_SENT` |
| `INSTALL_SENT` | Authenticated `INSTALLED` ACK matching durable record | `KEY_INSTALLED` (Gateway holds `INSTALLED_INACTIVE`, not ACTIVE) |
| `INSTALL_SENT` | Authenticated `REJECTED` ACK | `INSTALL_REJECTED` |
| `INSTALL_SENT` | Deadline or authorization expiration | `INSTALL_EXPIRED` |
| `KEY_INSTALLED` | In V2 (#136), Node transmits `UP_JOIN_READY` (0x49); Gateway verifies `GW_READY_TAG` using installed keys; Backend verifies `BACKEND_READY_PROOF` | `NODE_READY_PENDING_SCHEDULE` (`WAIT_TDMA`) |
| `WAIT_TDMA` | Backend stages TDMA schedule via `downlink/schedule` with 3→2→1 countdown; activates at superframe boundary K+H with 8 DATA TX guards satisfied | `ACTIVE` (`NODE_ACTIVE_DATA_ELIGIBLE`) |
| `ANY` | Revocation, conflict, invalid clock/secure state | `SUSPENDED/REVOKED` fail-closed |

Store `install_id`, `session_id`, Gateway mapping, revisions, immutable envelope digest, granted expiry, key-install status and authoritative assignment state durably on Backend; Gateway stores matching bounded key slots and installation receipts in protected nonvolatile storage. One successful authenticated ACK is application evidence from a trusted Gateway, not storage attestation. Maintain irrevocable tombstone/high-water-mark for revoked revisions (do not delete history in a way that allows old installs). Concurrent installs/revoke under same Node require serialized transactional validation or version compare-and-swap.

An ACK can arrive before Backend marks `INSTALL_SENT`; avoid dropping it merely due to ordering by first persisting `INSTALL_PENDING` and allowing an authenticated matching pending ACK to advance state after commit. MQTT QoS1 duplicates do not mint new IDs or rotate AES-GCM nonce. Wrong principal, stale retained, clock uncertainty, failed Flash write or missing reconciliation => do not progress.

## 7. Verification boundaries

`examples/session-key-cases.json` supplies positive/negative **schema-shape fixtures only** (placeholders are not authentic ciphertext/Tag). Contract tests may verify JSON Schema and topic/time formatting; actual Go↔ESP-IDF canonical binary AAD/HMAC test vectors, GCM decrypt/tamper tests, broker TLS/ACL/QoS/reconnect tests, power-loss injection, anti-replay, Gateway secure storage, security G2 and RF/HIL all remain **NOT_VERIFIED** until executed and evidenced. Reviewers: Gateway/Node, Backend Go, Infrastructure/Security, Owner/CODEOWNERS.

## 8. Alignment with Event-Only Architecture and V2 Join Protocol (#125, #126, #127, #128, #136, #154)

This specification explicitly reconciles the MQTT session-key lifecycle with active repository architecture decisions:

1. **V2 Post-Join Lifecycle Integration (#136, PR #168):**
   - **Trigger:** The Backend initiates `downlink/session-key-install` only after Node-Backend mutual key confirmation is verified (`UP_JOIN_KEY_CONFIRM:33B` / `DOWN_JOIN_FINISH:31B` in V2; historical `UP_JOIN_CONFIRM:19B` in V1).
   - **Edge Protection:** Gateway installs only derived operational session keys `K_SESSION_UP:32B || K_SESSION_DL:32B`. Root secret `K_JOIN` and confirm secret `K_JOIN_CONFIRM` are strictly withheld from the Gateway.
   - **State Isolation:** Gateway persists keys into `INSTALLED_INACTIVE` key slot and acknowledges via `uplink/session-key-ack` (`INSTALLED`). This state confers **no radio transmission rights**.
   - **Readiness Verification:** Once the Gateway holds the verified session keys, the Node emits `UP_JOIN_READY` (0x49) in the authorized Maintenance/CTRL window. The Gateway validates `GW_READY_TAG:8B` using installed session keys and relays the frame to the Backend. The Backend verifies `BACKEND_READY_PROOF:16B` using $K_{\text{JREADY}}$.
   - **TDMA Staging & 3→2→1 Activation:** Upon valid Node readiness proof, the Backend advances to `NODE_READY_PENDING_SCHEDULE` (`WAIT_TDMA`) and dispatches `downlink/schedule`. The Gateway stages shadow memory and broadcasts `SYNC_BEACON` with announcement countdown (3→2→1). Activation occurs strictly on superframe boundary $K+H$, transitioning the Node to `NODE_ACTIVE_DATA_ELIGIBLE` after satisfying all 8 DATA TX guards.

2. **Event-Only Data Plane Invariants (#125, #126):**
   - Periodic application telemetry (`uplink/telemetry`) is superseded. Key installation provisions encryption for event-triggered logging frames (`Event TX → Gateway durable acceptance → ACK RX`) within statically assigned TDMA slots.
   - Health and synchronization traffic is confined to dedicated Maintenance Superframes (~300s target interval) via authenticated `SYNC_BEACON` and scheduled per-Node `HEALTH_REPLY`.

3. **Multi-Gateway Exclusive VN920 Channel Assignment (#154, #125):**
   - Each Gateway is bound to an exclusive channel from VN920 CH00–CH10 (920.250–922.750 MHz, 125 kHz BW), managed transactionally in PostgreSQL.
   - The mapping between MQTT string identity `gateway_id` and RF uint8 `target_gw_id` is maintained by the Backend registry. Channel allocation is decoupled from schedule activation and does not grant unscheduled RF rights.
