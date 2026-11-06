# LP2P V2 Join, X25519 Session Key Authority & READY Security Compatibility Decisions

**Document ID:** `DOC-VERIF-V2-JOIN-CRYPTO-DEC-001`
**Status:** `DRAFT_FOR_OWNER_REVIEW` · `IMPLEMENTATION_READY=NO` · `G2=NOT_VERIFIED`
**Parent Tracking:** Issue #182 (Agent 3 Work Package), Parent Issue #127 (Migration Integration Gate), Umbrella Issue #125, Architecture Child Issue #126.
**Parallel Work Packages:** Agent 1 (#177, V2 Event DATA/ACK Compatibility Review), Agent 2 (#178, V2 Maintenance Superframe, Beacon & Health Compatibility).
**Downstream Verification Dependencies:** #173 (Go ↔ ESP-IDF mbedTLS AES-256-GCM / HMAC Interop Vectors), #174 (Mosquitto MQTT Broker Integration), #175 (ESP32 Gateway NVS Power-Loss HIL).
**Related Documents:**
- [V2 Post-Join Activation Design (Issue #136)](join-v2-ready-tdma-activation-design.md)
- [V2 Post-Join Test Matrix (Issue #136)](join-v2-ready-tdma-activation-test-matrix.md)
- [V2 Maintenance Beacon & Health Compatibility (Issue #178)](v2-maintenance-beacon-health-compatibility.md)
- [V2 Event DATA & ACK Review (Issue #177)](v2-event-ack-compatibility-review.md)
- [MQTT Session Key Install Schema (PR #123)](../../contracts/mqtt/schemas/session-key-install.schema.json)
- [MQTT Session Key ACK Schema (PR #123)](../../contracts/mqtt/schemas/session-key-ack.schema.json)
- [Radio MAC Specification](../../contracts/radio-mac/specification.md)
- [TDMA Schedule Contract](../../contracts/radio-mac/tdma-schedule.md)
- [Open Decisions](../../contracts/OPEN_DECISIONS.md)
- [ADR-0001: Hybrid TDMA Architecture](../../docs/adr/0001-hybrid-tdma.md)
- [ADR-0002: MQTT 5.0 Transport & Encoding](../../docs/adr/0002-mqtt-5.md)

---

## 1. Governance, Authority & Scope Boundary

### 1.1 Authority & Project Policy
In accordance with **Owner Decision #137 (2026-11-04)** and project [AGENTS.md](../../AGENTS.md):
1. **Self-Contained Decision Dossier:** This document constitutes a formal cryptographic trust-boundary analysis, architectural compatibility review, and decision dossier for technical Owner, Radio MAC, Gateway, Node, Backend, and Security review. It does **not** authorize production firmware coding, live radio frequency (RF) transmissions, database schema alterations, or normative contract wire standard freezes.
2. **Strict Read-Only Boundary:** The common normative contracts (`contracts/radio-mac/specification.md`, `contracts/radio-mac/tdma-schedule.md`, `contracts/OPEN_DECISIONS.md`), the versioned MQTT contracts (`contracts/mqtt/**`), firmware sources (`firmware/**`), backend sources (`backend-go/**`), test suites (`tests/**`), historical V1 PR #124, and existing #136 documents remain strictly **read-only** for this child package. All normative updates are delivered as recommendations to parent Issue #127 for coordinated integration.
3. **No Automatic Agent Approvals:** The Agent does not possess authority to approve protocol modifications, wire codepoints, or cryptographic primitives. All proposed resolutions and schema evolutions are submitted as `CANDIDATE_FOR_OWNER_DECISION`.
4. **V1 Provenance Protection:** Owner-approved V1 design artifacts in PR #124 (Bootstrap Join, compact V1 READY, 28B Group-HMAC Beacon) and PR #123 (V1 MQTT Session Key Install/ACK schemas) are preserved as historical audit provenance and are **not** retroactively reinterpreted, silently overwritten, or merged into V2 without versioned demarcation.
5. **Separation of Concerns:**
   - **Agent 1 (Issue #177):** Owns V2 Event DATA and ACK codepoints, own-slot retry semantics, local `EVENT_REF` mapping, and V1 telemetry/bitmap deprecation.
   - **Agent 2 (Issue #178):** Owns V2 Maintenance Superframe (~300 s cadence), `DOWN_SYNC_BEACON` (0x43), `UP_HEALTH_REPLY` (0x44), and clock drift holdover fences.
   - **Agent 3 (This Dossier, Issue #182):** Owns V2 Join trust-boundary matrix, ephemeral X25519 ECDH key authority reconciliation, `UP_JOIN_READY` (0x49 candidate) verifier architecture, V1 64B Key Install vs V2 local derivation conflict resolution, and the security decision package.

```
       +---------------------------------------------------------------------------------+
       |                           PARENT ISSUE #127 INTEGRATION GATE                    |
       |       Owns: contracts/radio-mac/specification.md, tdma-schedule.md, OPEN_DECISIONS |
       +---------------------------------------------------------------------------------+
                                 ▲                          ▲                          ▲
                                 │                          │                          │
        +------------------------+                          │                          +------------------------+
        │                                                   │                                                   │
+-------------------------------+       +---------------------------------------+       +-------------------------------+
|     AGENT 1 (ISSUE #177)      |       |         AGENT 2 (ISSUE #178)          |       |     AGENT 3 (ISSUE #182)      |
|  - UP_EVENT (0x41, 26B)       |       |  - DOWN_SYNC_BEACON (0x43, 80B)       |       |  - Trust-Boundary Matrix      |
|  - DOWN_EVENT_ACK (0x42, 19B) |       |  - UP_HEALTH_REPLY (0x44, 21B)        |       |  - V1 MQTT vs V2 ECDH Conflict|
|  - Local EVENT_REF mapping    |       |  - Maintenance SF (~300s cadence)     |       |  - UP_JOIN_READY (0x49) Proof |
|  - Own-slot retry semantics   |       |  - Clock Drift / Holdover Lockout     |       |  - State Inactive Key Fence   |
|  - Status: DESIGN CANDIDATE   |       |  - Status: DESIGN CANDIDATE           |       |  - Status: DESIGN DOSSIER     |
+-------------------------------+       +---------------------------------------+       +-------------------------------+
```

---

## 2. Executive Summary & Cryptographic Transition Context

### 2.1 The Architectural Paradigm Shift from V1 to V2
Under approved architecture child **#126** (PR #133), parent **#127**, and Owner Directives ([Comment 6623219854](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6623219854), [Comment 6623475221](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6623475221)), the LoRa-P2P network transitions from a centralized, pre-distributed key model (V1) to an **authenticated ephemeral Diffie-Hellman (X25519) key exchange (V2)**:

1. **Historical V1 Bootstrap Architecture (PR #124, PR #123):**
   - The Backend acts as a traditional Key Distribution Center (KDC).
   - In V1, the Backend derives or possesses both master session keys: $K_{\text{SESSION\_UP}}$ (32B) and $K_{\text{SESSION\_DL}}$ (32B).
   - The Backend packages these two keys into a 64-byte plaintext payload ($K_{\text{SESSION\_UP}} \parallel K_{\text{SESSION\_DL}}$), wraps them with AES-256-GCM under a long-lived Gateway wrap key $K_{\text{GW\_WRAP}}$, and transmits them to the Gateway via MQTT `downlink/session-key-install`.
   - The Gateway decrypts the envelope, stores the session keys in an inactive slot, and transmits `uplink/session-key-ack`.
2. **Owner-Approved V2 Secure MAC Handshake (Issue #127):**
   - The Owner explicitly rejected repurposing V1 key mechanics in favor of a modern, forward-secure handshake:
     - `UP_JOIN_HELLO` (0x45, 68B, [Comment 6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)): Node generates ephemeral X25519 keypair and presents authenticated `NODE_X25519_PUB`.
     - `DOWN_JOIN_GRANT` (0x46, 66B, [Comment 6629863066](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6629863066)): Gateway generates ephemeral X25519 keypair and presents `GW_X25519_PUB`. Backend verifies Hello proof and issues `GRANT_PROOF` under $K_{\text{JOIN}}$.
     - `UP_JOIN_KEY_CONFIRM` (0x47, 31B, [Comment 6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)): Node computes shared secret $Z = \text{X25519}(\text{priv}_{\text{node}}, \text{pub}_{\text{gw}})$, derives session key confirmation tag `GW_KC_TAG` (8B), and Backend proof `BACKEND_PROOF` (16B).
     - `DOWN_JOIN_FINISH` (0x48, 31B, [Comment 6630280648](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630280648)): Gateway and Backend provide reverse confirmation tags (`GW_FINISH_TAG` 8B under $K_{\text{KC\_DOWN}}$, `BACKEND_FINISH_PROOF` 16B under $K_{\text{JFINISH}}$).

### 2.2 The Fundamental Cryptographic Conflict
The shift to V2 ephemeral ECDH introduces an irreconcilable conflict with the recently merged V1 MQTT Session Key Install contract (Issue #122 / PR #123):
- **Non-Possession of $Z$:** In V2, the raw Diffie-Hellman secret $Z$ is computed strictly between the Node's ephemeral private key and the Gateway's ephemeral private key. **The Backend does not possess either ephemeral private key and therefore cannot compute $Z$.**
- **Inability to Derive Session Keys at Backend:** Because $Z$ is never revealed to the Backend, the Backend **cannot compute `PRK_SESSION`** and **cannot derive $K_{\text{SESSION\_ROOT}}$, $K_{\text{SESSION\_UP}}$, or $K_{\text{SESSION\_DOWN}}$**.
- **The Wrapper Semantic Collapse:** The V1 MQTT schema `session-key-install.schema.json` explicitly mandates:
  `"ciphertext": "Canonical RFC4648 Base64 of exact 64B ciphertext; plaintext is K_SESSION_UP[32] || K_SESSION_DL[32]."`.
  In V2, the Backend cannot populate this field without either:
  1. Forcing the Gateway or Node to transmit their private keys or $Z$ over MQTT/TLS (violating Perfect Forward Secrecy and the security boundary).
  2. Abandoning the Owner-locked X25519 handshake and silently retrofitting a centralized KDC scheme (strictly forbidden by AGENTS.md).
- **Resolution Mandate:** A clear, version-separated decision must be presented to the Owner to reconcile the V1 MQTT contract with the V2 ECDH architecture, without breaking existing V1 provenance or invalidating PR #123.

---

## 3. Deliverable 1: Exact Join Trust-Boundary & Cryptographic Derivation Matrix

This section establishes the definitive repository trust boundary for all cryptographic keys, secrets, and transcripts across the Sensor Node, Gateway edge, and Backend cloud.

### 3.1 Cryptographic Knowledge & Authority Matrix

| Cryptographic Material | Size | Node Knowledge | Gateway Knowledge | Backend Knowledge | Producer | Consumer | Permitted Verification Paths | Status / Authority |
|:---|:---:|:---:|:---:|:---:|:---|:---|:---|:---|
| **$K_{\text{JOIN}}$** | 32B | Holds in secure eFuse/NVS | **NEVER POSSESSES** (Zero knowledge) | Holds in encrypted Key Vault / DB | Provisioning Tool / Factory | Node, Backend | Backend verifies `JOIN_PROOF`, `GRANT_PROOF`, `BACKEND_PROOF`, `BACKEND_FINISH_PROOF`, `BACKEND_READY_PROOF`. Gateway is completely bypassed. | `OWNER_APPROVED_DESIGN` ([#127 C6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)) |
| **Node Ephemeral Pair** $(\text{priv}_{\text{node}}, \text{pub}_{\text{node}})$ | 32B/32B | Generates fresh per Join; zeroes priv after confirm | Receives `pub_node` via `UP_JOIN_HELLO` | Receives `pub_node` via MQTT relay from GW | Node CSPRNG / mbedTLS | Gateway (computes $Z$), Backend (binds transcript) | Gateway checks curve format; Backend verifies `JOIN_PROOF` binding `pub_node`. Node private key never leaves Node. | `OWNER_APPROVED_DESIGN` ([#127 C6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)) |
| **Gateway Ephemeral Pair** $(\text{priv}_{\text{gw}}, \text{pub}_{\text{gw}})$ | 32B/32B | Receives `pub_gw` via `DOWN_JOIN_GRANT` | Generates fresh per Grant; zeroes priv after finish | Receives `pub_gw` via MQTT from GW | Gateway CSPRNG / mbedTLS | Node (computes $Z$), Backend (binds transcript) | Node verifies `GRANT_PROOF` before using `pub_gw`. Node & Gateway reject all-zero $Z$. Gateway private key never leaves Gateway. | `OWNER_APPROVED_DESIGN` ([#127 C6629863066](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6629863066)) |
| **Raw Shared Secret $Z$** | 32B | Computes $Z = \text{X25519}(\text{priv}_{\text{n}}, \text{pub}_{\text{gw}})$ | Computes $Z = \text{X25519}(\text{priv}_{\text{gw}}, \text{pub}_{\text{n}})$ | **DOES NOT POSSESS** (Zero knowledge) | Node & Gateway local ECDH | Node, Gateway | Constant-time check: $Z \ne 0^{32}$. Never transmitted over RF or MQTT. | `OWNER_APPROVED_DESIGN` ([#127 C6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)) |
| **Transcript Hash $TH$** | 32B | Computes locally from Hello + Grant | Computes locally from Hello + Grant | Computes locally from Hello + Grant | SHA-256 of canonical wire bytes | Node, Gateway, Backend | Exact byte match across all three parties. Salt for `PRK_SESSION` and AAD for tags. | `OWNER_APPROVED_DESIGN` ([#127 C6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)) |
| **Root Join PRK** $\text{PRK}_{\text{JOIN}}$ | 32B | Derives via HKDF-Extract($K_{\text{JOIN}}$) | **DOES NOT POSSESS** | Derives via HKDF-Extract($K_{\text{JOIN}}$) | HKDF-Extract with `SALT_JOIN` | Node, Backend | Root for all Backend authentication keys (`K_JREQ`, `K_JGRANT`, `K_JCONF`, `K_JFINISH`, `K_JREADY`). | `OWNER_APPROVED_DESIGN` ([#127 C6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)) |
| **Session PRK** $\text{PRK}_{\text{SESSION}}$ | 32B | Derives via HKDF-Extract(salt=$TH$, IKM=$Z$) | Derives via HKDF-Extract(salt=$TH$, IKM=$Z$) | **DOES NOT POSSESS** | HKDF-Extract with $TH$ and $Z$ | Node, Gateway | Root for all edge verification and unicast data session keys (`K_KC_UP`, `K_KC_DOWN`, `K_SESSION_ROOT`). | `OWNER_APPROVED_DESIGN` ([#127 C6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)) |
| **Uplink Confirm Key** $K_{\text{KC\_UP}}$ | 32B | Derives from $\text{PRK}_{\text{SESSION}}$ | Derives from $\text{PRK}_{\text{SESSION}}$ | **DOES NOT POSSESS** | HKDF-Expand("LP2P/V2/KC-UP") | Node, Gateway | Gateway verifies `GW_KC_TAG` in Confirm (8B) and `GW_READY_TAG` in READY (8B). | `OWNER_APPROVED_DESIGN` ([#127 C6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)) |
| **Downlink Finish Key** $K_{\text{KC\_DOWN}}$ | 32B | Derives from $\text{PRK}_{\text{SESSION}}$ | Derives from $\text{PRK}_{\text{SESSION}}$ | **DOES NOT POSSESS** | HKDF-Expand("LP2P/V2/KC-DOWN") | Gateway, Node | Node verifies `GW_FINISH_TAG` in `DOWN_JOIN_FINISH` (8B). | `OWNER_APPROVED_DESIGN` ([#127 C6630280648](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630280648)) |
| **Backend Ready Key** $K_{\text{JREADY}}$ | 32B | Derives from $\text{PRK}_{\text{JOIN}}$ | **DOES NOT POSSESS** | Derives from $\text{PRK}_{\text{JOIN}}$ | HKDF-Expand("LP2P/V2/JOIN-READY") | Node, Backend | Backend verifies `BACKEND_READY_PROOF` in `UP_JOIN_READY` (16B). Gateway cannot forge. | `CANDIDATE_FOR_OWNER_DECISION` ([Issue #136 Doc](join-v2-ready-tdma-activation-design.md)) |
| **Session Root Key** $K_{\text{SESSION\_ROOT}}$ | 32B | Derives from $\text{PRK}_{\text{SESSION}}$ | Derives from $\text{PRK}_{\text{SESSION}}$ | **DOES NOT POSSESS** | HKDF-Expand("LP2P/V2/SESSION-ROOT")| Node, Gateway | Root key stored in `INSTALLED_INACTIVE` state until superframe activation boundary $K_{\text{target}}$. | `OWNER_APPROVED_DESIGN` ([#127 C6630055809](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6630055809)) |
| **Candidate Unicast Data Keys** ($K_{\text{ENC\_UP}}$, $K_{\text{ENC\_DN}}$, Nonce Prefix) | 16B/16B/8B | Derives from $K_{\text{SESSION\_ROOT}}$ | Derives from $K_{\text{SESSION\_ROOT}}$ | **DOES NOT POSSESS** | HKDF-Expand with direction labels | Node, Gateway | Used for AES-128-CCM encryption/tagging of `UP_EVENT` (0x41), `DOWN_EVENT_ACK` (0x42), `UP_HEALTH_REPLY` (0x44). | `CANDIDATE` (Agent 1 IF-REQ-01 / [#127 C6623475221](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6623475221)) |

### 3.2 Key Derivation Path Hierarchy

```text
                                  +-----------------------+
                                  |   K_JOIN (32B PSK)    |  [Node & Backend Only]
                                  +-----------------------+
                                              |
                                              v  HKDF-Extract(SALT_JOIN)
                                  +-----------------------+
                                  |       PRK_JOIN        |
                                  +-----------------------+
                                     /      |     \     \
                                    /       |      \     \
                                   v        v       v     v
                             K_JREQ     K_JGRANT  K_JCONF  K_JFINISH  K_JREADY (Candidate)
                             (0x45)      (0x46)    (0x47)   (0x48)     (0x49)
                             [Hello]     [Grant]  [Confirm] [Finish]   [Ready]

========================================================================================

   +--------------------------+                         +--------------------------+
   |   Node Ephemeral Priv    |                         |  Gateway Ephemeral Priv  |
   +--------------------------+                         +--------------------------+
                 \                                                   /
                  \----->  Z = X25519(local_priv, peer_pub)  <------/
                               [Node & Gateway Only!]
                               [Backend HAS NO ACCESS]
                                         |
                                         v  HKDF-Extract(TH)
                               +-------------------+
                               |    PRK_SESSION    |
                               +-------------------+
                                  /       |       \
                                 /        |        \
                                v         v         v
                            K_KC_UP   K_KC_DOWN  K_SESSION_ROOT (32B)
                            (0x47/49)   (0x48)      |
                                                    v  HKDF-Expand (Candidate)
                                         +------------------------------+
                                         | K_SESSION_UP (16B AES-CCM)   |
                                         | K_SESSION_DOWN (16B AES-CCM) |
                                         | SESSION_NONCE_PREFIX (8B)    |
                                         +------------------------------+
```

---

## 4. Deliverable 2: V1↔V2 MQTT Session Key Conflict & Decision Analysis

### 4.1 Incompatibility Breakdown
The versioned MQTT contract implemented in PR #123 (`contracts/mqtt/schemas/session-key-install.schema.json`) was formulated under the V1 architectural assumption that the Backend generates and owns the master session keys. The core structural incompatibilities between that contract and V2 are:

1. **Semantic Inversion of Authority:**
   - **V1 Model:** Backend dictates keys $\to$ Gateway consumes keys. Gateway has no cryptographic agency during key generation.
   - **V2 Model:** Gateway co-generates keys via local ECDH with Node $\to$ Gateway possesses keys before Backend is even informed. Backend acts as an **Authorization & Admission Authority**, not a Key Generator.
2. **Ciphertext & Wrap Key Field Obsolescence:**
   - V1 schema requires `ciphertext` (Base64 of 64B encrypted keys) and `wrap_key_id`.
   - In V2, because Backend does not know $Z$, Backend cannot generate the 64B plaintext $K_{\text{SESSION\_UP}} \parallel K_{\text{SESSION\_DL}}$ to wrap. Transmitting dummy bytes or an empty string violates the merged schema constraint `"pattern": "^(?:[A-Za-z0-9+/]{4}){21}[A-Za-z0-9+/]{2}==$"`.
3. **Loss of Forward Secrecy if Backend Were Given Keys:**
   - If a scheme were designed where Gateway encrypts its ephemeral private key or $Z$ back to Backend to allow Backend to wrap the keys, the Perfect Forward Secrecy (PFS) of the X25519 handshake would be destroyed. A compromise of Backend's storage would expose all historical edge session keys.
4. **AAD Transcript Mismatch:**
   - The V1 AAD construction binds `install_id`, `session_id`, `session_revision`, and `session_context_hash`. It does not bind the V2 RF transcript hash $TH$ or the ephemeral public keys $(\text{pub}_{\text{node}}, \text{pub}_{\text{gw}})$.

---

### 4.2 Architectural Alternatives Comparison

To resolve this conflict without breaking V1 historical provenance, three mutually exclusive options are evaluated:

```
+---------------------------------------------------------------------------------------------------+
| ALTERNATIVE A: Retain V1 Envelope Only (Deprecate MQTT Session Key Install for V2)                |
| - contracts/mqtt/schemas/session-key-install.schema.json frozen as V1-only.                       |
| - V2 uses NO MQTT session key topic; Gateway relies entirely on local ECDH and schedule approval.|
+---------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
| ALTERNATIVE B: V2 Local Derivation with Authenticated Backend Authorization Contract (RECOMMENDED)|
| - Introduce versioned schema: session-binding.schema.json (or install_protocol_version: 2).      |
| - Backend authorizes confirmed transcript (TH, session_id, lease) without handling raw keys.     |
| - Gateway activates locally derived keys only upon matching Backend authorization.               |
+---------------------------------------------------------------------------------------------------+

+---------------------------------------------------------------------------------------------------+
| ALTERNATIVE C: Centralized Backend-Mediated Key Transport (KDC Model)                             |
| - Abandon V2 X25519 ECDH; Backend generates session keys and wraps to Node and Gateway.           |
| - Preserves V1 MQTT wrapper schema directly.                                                      |
+---------------------------------------------------------------------------------------------------+
```

#### Detailed Comparison Matrix

| Evaluation Dimension | Alternative A: V1 Envelope Only | Alternative B: V2 Local ECDH + Auth Binding (Recommended) | Alternative C: Centralized KDC Scheme |
|:---|:---|:---|:---|
| **Cryptographic Trust & PFS** | High for RF; Low for Gateway state synchronization (no Backend binding). | **Highest.** Preserves true X25519 Perfect Forward Secrecy; Backend never touches edge keys; Gateway bound by Backend ticket. | **Lowest.** Zero forward secrecy; Backend holds all edge keys; single point of compromise. |
| **Backend Authorization & Admission** | Implicit (Backend admits node by allocating slot in schedule). Risk of desync. | **Explicit & Strong.** Backend explicitly issues cryptographically bound authorization ticket containing lease and permissions. | Explicit (Backend issues keys). |
| **Replay & Rollback Defense** | Relies solely on RF `JOIN_COUNTER`. No MQTT-level replay detection for session. | **Dual-Layer.** RF `JOIN_COUNTER` + Backend monotonic `session_revision` and canonical $TH$ binding. | Relies on Backend nonce and `wrap_key_id`. |
| **Impact on PR #123 Contract** | Zero churn (schema frozen for V1). Leaves V2 unmodeled in MQTT. | **Clean Versioning.** Leaves V1 schema intact; adds `session-binding.schema.json` or `install_protocol_version: 2`. | Zero schema churn; requires rewriting RF V2 handshake. |
| **RF Airtime & Bandwidth** | Lowest (no change to V2 RF). | Lowest (no change to V2 RF). | **Negative.** Requires enlarging RF Grant to deliver wrapped keys to Node (exceeds 66B). |
| **Implementation Complexity** | Minimal. | Moderate (new Go handler & ESP32 binding verifier). | High (requires redesigning Node crypto and abandoning Owner locks). |
| **Conformance with Owner Locks** | Complies with RF locks; omits MQTT contract. | **Strictly Conforms.** Aligns perfectly with locked 0x45..0x48 packets and AGENTS.md. | **Violates Owner Locks.** Breaks approved V2 handshake ([Issue #127 C6628167582](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/127#issuecomment-6628167582)). |

---

### 4.3 Recommended Resolution & Decision Text

> [!TIP]
> **Coordinator Recommendation:** Adopt **Alternative B (V2 Local ECDH + Backend Authorization Contract)**.
> This preserves the cryptographic integrity of Owner-approved X25519 ECDH while providing the Backend with full operational authority over session admission, node activation, lease lifetimes, and revocation, without exposing data keys.

#### Proposed Owner Decision Record (for Parent #127 & Contract Issue #128)
```text
DECISION ID: DEC-SEC-02 (Parent Integration Handoff)
TITLE: Adoption of V2 Local Derivation with Authenticated Backend Authorization Contract
AUTHORITY: Project Owner / Security Review
RESOLUTION:
1. The merged MQTT schema contracts/mqtt/schemas/session-key-install.schema.json (PR #123) is designated strictly for Protocol Version 1 (V1) networks and historical audit provenance. Its install_protocol_version: 1 and 64B ciphertext constraints shall remain untouched.
2. For Protocol Version 2 (V2), the Gateway derives K_SESSION_ROOT, K_SESSION_UP, and K_SESSION_DOWN locally from X25519 shared secret Z. The Backend DOES NOT possess Z and SHALL NOT transmit raw session keys.
3. A distinct versioned contract contracts/mqtt/schemas/session-binding.schema.json (or install_protocol_version: 2) shall be defined for V2. Under this contract, the Backend transmits a cryptographically bound Session Authorization Ticket containing:
   - session_id (UUID)
   - node_id (1..254)
   - device_mac (12-hex)
   - session_revision (uint64 string)
   - transcript_hash_th (SHA-256 hex)
   - not_before, expires_at, lease_duration_sec
   - authorized_flags (allowed slot classes, event-only permissions)
   - backend_auth_signature / hmac
4. The Gateway validates the Backend ticket against its local handshake state (matching TH and node_id). If valid, it commits the locally derived keys to INSTALLED_INACTIVE and returns uplink/session-binding-ack. If mismatched or expired, it wipes ephemeral keys and fails closed.
```

#### Affected Monorepo Files (Parent Follow-Up Work)
- `contracts/mqtt/schemas/session-key-install.schema.json` (Add header comment: V1-only).
- `contracts/mqtt/schemas/session-binding.schema.json` (New V2 contract in #128).
- `contracts/mqtt/schemas/session-binding-ack.schema.json` (New V2 contract in #128).
- `contracts/mqtt/topics.md` & `semantic-rules.md` (Document V2 binding topic semantics).
- `backend-go/internal/service/join/` (Implement V2 binding ticket generator).
- `firmware/` (Gateway mbedTLS local derivation and ticket validator).

---

## 5. Deliverable 3: `UP_JOIN_READY` (0x49) Wire Layout, Verifier & Transcript Analysis

### 5.1 Verification of Candidate 31-Byte Wire Layout
Issue #136 proposed candidate frame `UP_JOIN_READY` (0x49, 31 bytes) to resolve the post-join operational gap. This dossier formally audits its byte offsets, entropy, and verifier responsibilities.

```
Candidate UP_JOIN_READY Layout (31 Octets):
+---------------------------------------------------------------------------------------------------+
| Offset 0 | Offset 1 | Offset 2 | Offsets 3..6    | Offsets 7..14    | Offsets 15..30              |
| VER_TYPE | GW_ID    | NODE_ID  | JOIN_COUNTER    | GW_READY_TAG     | BACKEND_READY_PROOF         |
| 1 Byte   | 1 Byte   | 1 Byte   | 4 Bytes (BE)    | 8 Bytes (Tag)    | 16 Bytes (Proof)            |
| (0x49)   | (0x01..FE| (0x01..FE| (Monotonic uint)| (Under K_KC_UP)  | (Under K_JREADY)            |
+---------------------------------------------------------------------------------------------------+
```

#### Field-by-Field Audit

| Offset | Field Name | Type | Constraint | Cryptographic Purpose |
|:---:|:---|:---:|:---|:---|
| `0` | `VER_TYPE` | `uint8` | Fixed `0x49` (`01001001b`) | Proto V2 (bits 7..5 = `010b`), Type `JOIN_READY` (`01001b`). Disjoint from V1 (`0x20..0x3F`) and V2 Join (`0x45..0x48`). |
| `1` | `GW_ID` | `uint8` | `0x01`..`0xFE` (`0x00`/`0xFF` reserved) | Destination Gateway ID. Must match authorized Gateway from `DOWN_JOIN_GRANT`. |
| `2` | `NODE_ID` | `uint8` | `0x01`..`0xFE` (`0x00`/`0xFF` reserved) | Assigned Node ID. Must match `NODE_ID` granted in `DOWN_JOIN_GRANT`. |
| `3..6` | `JOIN_COUNTER` | `uint32_t` BE | Monotonic counter | Must match exact counter of live Join transaction. Prevents cross-transaction replays. |
| `7..14` | `GW_READY_TAG` | `byte[8]` | First 8 bytes of HMAC-SHA256 | Edge verification tag keyed with $K_{\text{KC\_UP}}$ (derived from $Z$). Verified locally by Gateway. |
| `15..30` | `BACKEND_READY_PROOF` | `byte[16]`| First 16 bytes of HMAC-SHA256 | End-to-end proof keyed with $K_{\text{JREADY}}$ (derived from $K_{\text{JOIN}}$). Verified by Backend. |

---

### 5.2 Cryptographic Transcript & Verifier Differentiation

```text
# 1. Backend-Bound Derivation (Node & Backend Only)
SALT_JOIN             = ASCII("LP2P/V2/JOIN-ROOT") || NETWORK_ID_BE4 || DEVICE_MAC6 || DEVICE_GENERATION_BE2
PRK_JOIN              = HKDF-Extract-SHA256(salt=SALT_JOIN, IKM=K_JOIN)
K_JREADY              = HKDF-Expand-SHA256(PRK_JOIN, info=ASCII("LP2P/V2/JOIN-READY"), L=32)

# 2. Gateway-Bound Derivation (Node & Gateway Only)
TH                    = SHA256(ASCII("LP2P/V2/TH-JOIN") || NETWORK_ID_BE4 || HELLO68 || GRANT66)
PRK_SESSION           = HKDF-Extract-SHA256(salt=TH, IKM=Z)
K_KC_UP               = HKDF-Expand-SHA256(PRK_SESSION, info=ASCII("LP2P/V2/KC-UP"), L=32)

# 3. Payload Prefixes & Authentication Messages
READY_PREFIX7         = 0x49 || GW_ID1 || NODE_ID1 || JOIN_COUNTER_BE4
M_GW_READY            = ASCII("LP2P/V2/M-GW-READY") || TH || FINISH31 || READY_PREFIX7
GW_READY_TAG8         = HMAC-SHA256(K_KC_UP, M_GW_READY)[0..7]

M_BE_READY            = ASCII("LP2P/V2/M-BACKEND-READY") || NETWORK_ID_BE4 || TH || FINISH31 || READY_PREFIX7 || GW_READY_TAG8
BACKEND_READY_PROOF16 = HMAC-SHA256(K_JREADY, M_BE_READY)[0..15]
```

#### Dual-Verifier Security Analysis

1. **Gateway Edge Verification (`GW_READY_TAG8`):**
   - **Verifier:** Gateway SX1276 Host.
   - **Key Used:** $K_{\text{KC\_UP}}$ (derived from $Z$).
   - **Verification Timing:** Immediately upon RF reception during Subframe 4 `CTRL_WINDOW`.
   - **Purpose:** Immediate edge filtration. If an attacker injects random RF noise or a corrupted frame, the Gateway drops it in milliseconds without forwarding it over cellular/WAN backhaul to the Backend.
   - **Key Separation:** $K_{\text{KC\_UP}}$ is distinct from data session keys ($K_{\text{SESSION\_UP}}$). Verifying readiness does not exercise or expose application data keys.
2. **Backend End-to-End Verification (`BACKEND_READY_PROOF16`):**
   - **Verifier:** Backend Join Service.
   - **Key Used:** $K_{\text{JREADY}}$ (derived from provisioned $K_{\text{JOIN}}$).
   - **Verification Timing:** Upon receiving MQTT `uplink/join-ready` (or `uplink/ready-report`).
   - **Untrusted Gateway Protection:** **A compromised or rogue Gateway possessing $Z$ and $K_{\text{KC\_UP}}$ CANNOT forge `BACKEND_READY_PROOF16`.** The Gateway has zero knowledge of $K_{\text{JOIN}}$ or $K_{\text{JREADY}}$. Thus, the Gateway cannot trick the Backend into activating an unauthorized node.
3. **Cryptographic Proof of Delivery for `DOWN_JOIN_FINISH`:**
   - Both `M_GW_READY` and `M_BE_READY` include the exact 31 bytes of `FINISH31` (which contains `BACKEND_FINISH_PROOF`).
   - A Node could only compute `BACKEND_READY_PROOF16` if it successfully received and parsed `DOWN_JOIN_FINISH`.
   - This provides the Backend with **unimpeachable cryptographic proof of downlink delivery**, solving the delivery uncertainty trap.

---

### 5.3 Candidate Status & Governance
- **Current Status:** `CANDIDATE_FOR_OWNER_DECISION`.
- **Preemptive Lock Prohibition:** In accordance with AGENTS.md, this dossier **does NOT declare codepoint 0x49 or its byte layout frozen**. It proposes formal decision record `DEC-SEC-03` to parent Issue #127 for technical Owner review.

---

## 6. Deliverable 4: Join → Ready → Schedule → Active State & Authorization Pipeline

### 6.1 Formal State Machine Progression & Fencing

```
       SENSOR NODE                           GATEWAY SX1276                       BACKEND (GO CLUSTER)
            |                                      |                                       |
    [NODE_UNJOINED]                           [GW_ONLINE]                         [BE_SESSION_PENDING]
            |                                      |                                       |
            |--- UP_JOIN_HELLO (0x45, 68B) ------->|--- MQTT: uplink/join-hello ---------->|
            |                                      |<-- MQTT: downlink/join-grant ---------|
            |<-- DOWN_JOIN_GRANT (0x46, 66B) ------|                                       |
    [Computes Z & Keys]                     [Computes Z & Keys]                            |
            |--- UP_JOIN_KEY_CONFIRM (0x47, 31B) ->|--- MQTT: uplink/join-confirm -------->|
            |                                      |<-- MQTT: downlink/join-finish --------|
            |<-- DOWN_JOIN_FINISH (0x48, 31B) -----|                                       |
            |                                      |                                       |
+-----------------------------------------------------------------------------------------------------+
| FENCE 1: SESSION_READY_NOT_ACTIVE (Keys Derived & Inactive; ZERO DATA TRANSMISSION PERMITTED!)      |
+-----------------------------------------------------------------------------------------------------+
            |                                      |                                       |
    (Await CTRL Window)                            |                                       |
            |--- UP_JOIN_READY (0x49, 31B) ------->|                                       |
            |                                [Verifies GW_TAG]                             |
            |                                      |--- MQTT: uplink/join-ready ---------->|
            |                                      |                                 [Verifies BE_PROOF]
            |                                      |                             [NODE_READY_PENDING_SCHED]
            |                                      |                                       |
            |                                      |                               (TDMA Planner Run)
            |                                      |<-- MQTT: downlink/schedule -----------|
            |                                [Stages Shadow]                               |
            |                                      |--- MQTT: uplink/schedule-ack -------->|
            |                                      |    (STAGE_ACK, Horizon K+3)           |
+-----------------------------------------------------------------------------------------------------+
| FENCE 2: 3 -> 2 -> 1 ANNOUNCEMENT HORIZON (Shadow Staged; Node Receives Schedule Map in Downlink)   |
+-----------------------------------------------------------------------------------------------------+
            |<-- SYNC_BEACON (SF K, Count=3) ------|                                       |
            |<-- SYNC_BEACON (SF K+1, Count=2) ----|                                       |
            |<-- SYNC_BEACON (SF K+2, Count=1) ----|                                       |
            |                                      |                                       |
+-----------------------------------------------------------------------------------------------------+
| FENCE 3: SUPERFRAME K+3 BOUNDARY (8-Fold Guard Evaluated; Keys Promoted to ACTIVE)                  |
+-----------------------------------------------------------------------------------------------------+
            |                                [Promotes Shadow]                       [Marks ACTIVE]
            |<-- SYNC_BEACON (SF K+3, Count=0) ----|--- MQTT: uplink/schedule-ack -------->|
            |                                      |    (ACTIVE_REPORT, K+3)               |
    [Evaluates 8 Guards]                           |                                       |
    [ACTIVE_DATA_ELIGIBLE]                         |                                       |
            |                                      |                                       |
            |--- Authenticated Unicast DATA Slot ->|                                       |
```

### 6.2 The Three Critical Operational Fences

#### Fence 1: `SESSION_READY_NOT_ACTIVE` & Inactive Key Containment
- **Trigger:** Successful verification of `DOWN_JOIN_FINISH` at Node.
- **Rule:** The Node possesses valid session keys ($K_{\text{SESSION\_ROOT}}$, $K_{\text{SESSION\_UP}}$, $K_{\text{SESSION\_DOWN}}$), but they are locked in `INSTALLED_INACTIVE` state.
- **Enforcement:** The Node radio driver blocks all application DATA frame transmission. If any firmware task attempts to queue an event for RF TX, the radio MAC returns `ERR_MAC_SESSION_NOT_ACTIVE`. The event remains safely buffered in local NVS flash.
- **Gateway Fencing:** If the Gateway receives any unicast DATA frame from a Node before the schedule cutover boundary $K_{\text{target}}$, the Gateway radio engine drops the packet immediately as `UNSCHEDULED_FRAME_VIOLATION`.

#### Fence 2: The $3 \to 2 \to 1$ Announcement Horizon & 100%-READY Barrier
- **Trigger:** Backend proposes schedule version $V_{\text{new}}$ allocating Slot $S$ to the Node.
- **100%-READY Barrier:** The Backend TDMA Planner **SHALL NOT include any node in a proposed schedule revision unless that node has a verified `NODE_READY` state in the database**. Unverified nodes are never pre-allocated slots.
- **Three Superframe Horizon:** The Gateway commits the proposal to NVS as `SHADOW_SCHEDULE` and broadcasts countdown $3 \to 2 \to 1$ across three complete consecutive superframes in `DOWN_SYNC_BEACON`.
- **Node Schedule Acquisition:** The Node listens to the Downlink Control slot during the announcement superframes, acquires the schedule mapping, verifies its authenticity, and stages the schedule locally.

#### Fence 3: The 8-Fold Fail-Closed Node DATA TX Guard
At superframe boundary $K_{\text{target}}$, the Node transitions to `ACTIVE_DATA_ELIGIBLE` **if and only if all eight of the following independent guards evaluate to TRUE**:
1. `G1 (Join Completed):` Valid `DOWN_JOIN_FINISH` processed with matching counter.
2. `G2 (Dual Key Confirmations Valid):` Gateway tag and Backend proof were both verified.
3. `G3 (Schedule Authentic):` Staged schedule matches active `schedule_version` announced in Beacon.
4. `G4 (Session Lease Active):` Monotonic clock $T_{\text{now}} < T_{\text{lease\_expiry}}$.
5. `G5 (Timing & Clock Drift Safe):` Synchronized with valid Beacon within last 2 superframes; calculated drift $\tau_{\text{drift}} \le 25\text{ ms}$; consecutive lost beacons $< 3$.
6. `G6 (Exclusive Slot Ownership):` Radio transmission permitted strictly within pre-assigned static slot boundaries $[T_{\text{slot\_start}} + T_{\text{guard}},\, T_{\text{slot\_end}} - T_{\text{slack}}]$.
7. `G7 (Airtime Budget Available):` Rolling 1-hour duty cycle $\sum \text{ToA} \le 36{,}000\text{ ms}$ (1.0% regulatory cap).
8. `G8 (Monotonic Counter Valid):` Frame counter `FCnt_UP` strictly increasing and $< 2^{32}-1$.

---

### 6.3 Cross-Agent Boundary Constraints

1. **Constraint with Agent 1 (Issue #177 — Event DATA/ACK):**
   - Agent 1 defines the wire structure and retry semantics for `UP_EVENT` (0x41) and `DOWN_EVENT_ACK` (0x42).
   - **Agent 3 Constraint:** Agent 1's Event frames **SHALL NOT be transmitted over the air until Agent 3's Fence 3 is completely traversed** (Node reaches `ACTIVE_DATA_ELIGIBLE`).
   - **Key Handoff:** Agent 3 provides the derived 16B $K_{\text{SESSION\_UP}}$ and 8B `SESSION_NONCE_PREFIX` to Agent 1's AES-128-CCM engine upon activation boundary $K_{\text{target}}$.
2. **Constraint with Agent 2 (Issue #178 — Maintenance SF, Beacon & Health):**
   - Agent 2 defines the ~300 s Maintenance Superframe and `DOWN_SYNC_BEACON` (0x43).
   - **Agent 3 Constraint:** `UP_JOIN_READY` (0x49) transmission is strictly prohibited during normal DATA slots and during Agent 2's scheduled `UP_HEALTH_REPLY` slots.
   - **Window Restriction:** `UP_JOIN_READY` is permitted **strictly within the Subframe 4 `CTRL_WINDOW`** (nominal offset 1850..2000 ms) of normal DATA superframes, subject to random CSMA/CA backoff to prevent collisions between simultaneously joining nodes.

---

## 7. Deliverable 6: Owner Decision Package & Parent #127 Integration Registry

This section consolidates the formal decisions formulated by this dossier for submission to parent Issue #127 and technical Owner review.

### 7.1 Formally Numbered Security Decisions (`DEC-SEC-01` .. `DEC-SEC-07`)

| Decision ID | Scope | Candidate Version | Source / Authority | Producer | Consumer | Dependencies | Proposed Rule | Explicit Owner Question | Downstream Test IDs |
|:---|:---|:---:|:---|:---|:---|:---|:---|:---|:---|
| **DEC-SEC-01** | Crypto Trust | Ephemeral ECDH Key Authority | V2 (#127 C6630055809) | Node & Gateway | Backend | RFC 7748 / X25519 | Backend possesses zero knowledge of $Z$ and edge data session keys. Edge keys are derived strictly at Node & Gateway. | Confirm that Backend shall not possess $Z$ or unicast session keys in V2. | `SEC-TM-01`, `SEC-TM-11`, `SEC-TM-12` |
| **DEC-SEC-02** | MQTT Contract | V1/V2 MQTT Key Reconciliation | Issue #182 Dossier | Backend Join | Gateway MQTT | PR #123 Merged Schema | Retain PR #123 schema strictly for V1; adopt Alternative B (Session Binding Ticket) for V2 in follow-up #128. | Approve Alternative B architecture and separate V2 session-binding schema. | `SEC-TM-21`, `SEC-TM-22` |
| **DEC-SEC-03** | Wire Codepoint | `UP_JOIN_READY` (0x49, 31B) | Issue #136 / #182 | Sensor Node | Gateway & Backend | Issue #127 Finish (0x48)| Adopt 31B layout for 0x49 with dual tags: `GW_READY_TAG` (8B) and `BACKEND_READY_PROOF` (16B). | Approve candidate 0x49 wire layout and dual-verifier model. | `SEC-TM-06`, `SEC-TM-07` |
| **DEC-SEC-04** | Security Proof | Cryptographic Proof of Delivery | Issue #182 Dossier | Sensor Node | Backend Join | `DOWN_JOIN_FINISH` (0x48)| `BACKEND_READY_PROOF` must incorporate `FINISH31` and $TH$, proving Node received valid Finish. | Confirm that Backend requires cryptographic delivery proof before slot planning. | `SEC-TM-03`, `SEC-TM-04` |
| **DEC-SEC-05** | State Machine | Inactive Key Fencing & 8-Fold Guard | Issue #136 / #182 | Node Radio MAC | Gateway Scheduler | TDMA Engine | Derived keys remain in `INSTALLED_INACTIVE` until boundary $K_{\text{target}}$; all 8 guards must pass. | Formalize the 8-fold fail-closed guard as mandatory firmware policy. | `SEC-TM-17`, `SEC-TM-18` |
| **DEC-SEC-06** | Hardware / NVS | Monotonic Counter Rollback Guard | Issue #127 C6628167582 | Node NVS | Backend Registry | ESP32 eFuse / NVS | Node must commit incremented `JOIN_COUNTER` before transmitting Hello. Corrupt NVS halts radio. | Approve fail-closed policy on NVS counter read failure or rollback detection. | `SEC-TM-15`, `SEC-TM-16` |
| **DEC-SEC-07** | Cryptography | All-Zero ECDH Rejection Policy | Issue #127 C6630055809 | Node & Gateway | Radio Crypto Driver | RFC 7748 Section 6.1 | If $\text{X25519}(\text{priv}, \text{pub}) == 0^{32}$, immediately terminate handshake and wipe state. | Reaffirm mandatory rejection of all-zero ECDH output points. | `SEC-TM-11`, `SEC-TM-12` |

---

### 7.2 Explicit Proposed Changes to Parent Normative Contracts
Upon Owner approval, parent Issue #127 will apply the following exact modifications:
1. **`contracts/radio-mac/specification.md`:**
   - Register candidate `0x49` as `UP_JOIN_READY` (31 octets).
   - Document dual-verifier tag derivations ($K_{\text{KC\_UP}}$ for Gateway, $K_{\text{JREADY}}$ for Backend).
   - Document $Z$ non-possession boundary by Backend.
2. **`contracts/radio-mac/tdma-schedule.md`:**
   - Formalize Fence 1 (`SESSION_READY_NOT_ACTIVE`), Fence 2 ($3 \to 2 \to 1$ horizon), and Fence 3 (8-fold guard).
   - Define Subframe 4 `CTRL_WINDOW` contention rules for `UP_JOIN_READY`.
3. **`contracts/OPEN_DECISIONS.md`:**
   - Register decisions `DEC-SEC-01` through `DEC-SEC-07` as `CANDIDATE_FOR_OWNER_DECISION`.

---

### 7.3 Downstream Verification Dependencies

The decisions in this dossier directly govern and unblock the following downstream verification issues:
- **Issue #173 (Golden Vectors):** Cross-language verification (Go ↔ ESP-IDF mbedTLS) of HKDF-SHA256 derivations for `PRK_JOIN`, `PRK_SESSION`, `K_KC_UP`, `K_KC_DOWN`, `K_JREADY`, and X25519 RFC 7748 vectors.
- **Issue #174 (Mosquitto Integration):** Verification of per-principal mTLS client certificate ACLs, ensuring Gateway `gw01` cannot publish to topics reserved for `gw02` or bypass session authorization topics.
- **Issue #175 (Gateway NVS HIL):** Power-loss fault injection testing verifying that the Gateway safely preserves `INSTALLED_INACTIVE` keys and `SHADOW_SCHEDULE` across unexpected reboots without corrupting memory or leaking uncommitted sessions.

---

## 8. Summary & Acceptance Sign-Off Checklist

- [x] Exact Join trust-boundary matrix completed with all 12 key materials, knowledge mappings, and status labels.
- [x] Incompatibility between merged PR #123 (64B wrapped keys) and V2 ECDH analyzed; three alternatives compared; Alternative B recommended with decision wording.
- [x] Candidate `UP_JOIN_READY` (0x49, 31B) audited; edge verifier vs Backend verifier roles differentiated; cryptographic delivery proof established.
- [x] Three-party state machine progression and 3 critical operational fences specified with 8-fold fail-closed guard.
- [x] Cross-agent constraints for Agent 1 (Event DATA) and Agent 2 (Maintenance SF) defined.
- [x] Owner decision package (`DEC-SEC-01` .. `DEC-SEC-07`) prepared with explicit Owner questions and downstream traceability.
- [x] No normative contract files overwritten; changes delivered as recommendations to parent #127.
