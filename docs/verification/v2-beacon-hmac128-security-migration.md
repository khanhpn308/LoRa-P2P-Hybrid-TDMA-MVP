# V2 Beacon HMAC-128 Security, Key Lifecycle & Wire Migration Dossier

**Document ID:** `DOC-VERIF-V2-BEACON-HMAC128-001`
**Status:** `OWNER_APPROVED_MVP_SECURITY_DESIGN` (2026-11-07) · `IMPLEMENTATION_NOT_VERIFIED` · `G2_HIL_NOT_VERIFIED`
**Authority:** [Issue #209](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/209), [Issue #208](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/issues/208), DEC-MH-01, DEC-MH-07, merged PR #206 (`4f2fcb3aaa11bf5011c0db15e5ee1ec4968e2280`), PR #205 (`5b711d07b1390e31db3614752689cd55596500e0`), PR #107 (`38e532d747d71a52933d11e36ac6ea3c57f19475`).
**Contract Coordination:** #127 (Radio MAC V2), #128 (MQTT/API), #131 (Firmware V2), #19 (Backend Schedule), #126 (Event-Only), #169 (LAB HIL & Physical RF Timing).
**Hardware-First Plan:** Simulator workstreams (#17, #130) retired and superseded by real ESP32+SX1276 multi-board verification under #169.
**Scope Boundary:** Design-only dossier for Issue #209. Normative contracts (`contracts/**`), firmware, ADR, and test suites are strictly READ-ONLY in this phase.

---

## 1. Executive Summary & Cryptographic Transition Context

### 1.1 The Architectural Transition from Ed25519-80B to HMAC32
Under **DEC-MH-01** (superseding cryptographic direction approved by Project Owner on 2026-11-06 / 2026-11-07), the V2 `DOWN_SYNC_BEACON` replaces the 64-byte Ed25519 asymmetric signature with a 16-byte **HMAC-SHA256-128** authentication tag. Retaining the 16-byte information header and packet type `0x43`, the total wire frame length is reduced from **80 octets to exactly 32 octets**:

$$\text{Wire Length} = 16\text{B Header} + 16\text{B Tag} = 32\text{ octets}$$

```
+-------------------------------------------------------------------------------+
|                    HISTORICAL PROPOSAL: Ed25519-80B (SUPERSEDED)              |
|  [Header16: 0x43 | GW_ID | EPOCH_SEC | SF_SEQ | SCHED_VER | FLAGS | RSV]     |
|  [Ed25519 Signature: 64 Octets]                                               |
|  Total Wire: 80 Bytes | SF7 ToA: 143.6 ms | SF8 ToA: 256.5 ms                 |
+-------------------------------------------------------------------------------+
                                        │
                                        ▼  DEC-MH-01 (Owner Approved 2026-11-07)
+-------------------------------------------------------------------------------+
|               OWNER-APPROVED MVP WIRE BASELINE: HMAC-SHA256-128 (32B)         |
|  [Header16: 0x43 | GW_ID | EPOCH_SEC | SF_SEQ | SCHED_VER | FLAGS | KEY_ID]   |
|  [HMAC-SHA256-128 Tag: 16 Octets]                                             |
|  Total Wire: 32 Bytes | SF7 ToA: 71.9 ms (-50%) | SF8 ToA: 133.6 ms (-48%)    |
+-------------------------------------------------------------------------------+
```

### 1.2 Transition Rationale & Core Invariants
1. **Airtime & Duty Cycle Halving:** 32B frame cuts theoretical Time on Air (ToA) by ~50% (71.936 ms vs 143.616 ms at SF7; 133.632 ms vs 256.512 ms at SF8), significantly reducing RF spectrum footprint, collision probability with asynchronous Join CAD, and receiver battery drain.
2. **Resource-Constrained Microcontroller Optimization:** Eliminates asymmetric cryptographic verification overhead (Ed25519 point multiplication) on ESP32-WROOM-32E sensor nodes during tight TDMA superframe windows.
3. **Strict Invariant — Time Synchronization Only:** `DOWN_SYNC_BEACON` carries authoritative network time, epoch counters, and gateway liveness only. It **CANNOT** authorize schedule COMMIT, node activation, or join completion.
4. **Decoupling from Schedule Migration (#208):** In accordance with closed Issue #208, the historical `3→2→1` countdown in `FLAGS[7:6]` is obsolete and set to `RESERVED=0`. Schedule migration is an on-demand, explicit two-phase commit: Backend-signed `DOWN_SCHED_PREPARE` (80B) $\to$ per-Node `UP_SCHED_READY` (41B, 0x4C) with 100% verified affected nodes $\to$ Backend-signed `DOWN_SCHED_DECISION` (80B) committing at common $K_{\text{TARGET}}$. Beacon authentication does not authorize new schedule cutover.
5. **Decoupling from Initial Join:** Join via CAD is permitted at any time without requiring prior Beacon synchronization or an installed Beacon key. Nodes without `K_BEACON` can execute Join, but will not trust Beacon timing or become eligible for DATA slot transmission until provisioned.

---

## 2. Explicit Security Consequence & Threat Model Analysis

### 2.1 Symmetric Group Key vs Asymmetric Origin Authentication
An asymmetric signature (Ed25519) provides non-repudiation: only the Gateway holding the private signing key can generate a valid signature, verifiable by all nodes holding the public key.

In contrast, **HMAC-SHA256-128 is a symmetric primitive**. An HMAC tag proves possession of the shared secret $K_{\text{BEACON}}$, **not** that the transmitter is uniquely the physical Gateway hardware. Because all authorized Nodes associated with a Gateway must possess $K_{\text{BEACON}}$ to verify broadcast Beacons, this represents a fundamental shift in the cryptographic trust boundary:

| Security Attribute | Historical Ed25519 (80B) | Owner-Approved HMAC-SHA256-128 (32B) |
|---|---|---|
| **Cryptographic Class** | Asymmetric Digital Signature | Symmetric Message Authentication Code (MAC) |
| **Key Distribution** | Gateway: Private Key; Nodes: Public Key | Gateway & All Associated Nodes: Shared Group Secret $K_{\text{BEACON}}$ |
| **Origin Authenticity** | Unique Gateway Origin Guaranteed | Group Membership Proven (Gateway OR any Node with $K_{\text{BEACON}}$) |
| **Node Compromise Consequence** | Public key exposed; zero ability to forge Beacons | Group key exposed; compromised Node can forge Beacons for that Gateway |
| **Computation Complexity** | High (~10–15 ms Ed25519 verify) | Minimal (<0.1 ms SHA-256 block hash) |
| **Wire Overhead** | 64-byte signature (80B frame) | 16-byte tag (32B frame) |

### 2.2 Threat Model & Impact of Compromised Group Secret
If an authorized sensor node is physically captured, stolen from the field, or compromised via memory readout, the attacker extracts $K_{\text{BEACON}}$.

```
                             +-----------------------+
                             |  Compromised Node     |
                             |  Extracts K_BEACON    |
                             +-----------+-----------+
                                         |
               +-------------------------+-------------------------+
               |                                                   |
               ▼                                                   ▼
    [WHAT ATTACKER CAN DO]                              [WHAT ATTACKER CANNOT DO]
  - Forge 0x43 DOWN_SYNC_BEACON                       - Cannot authorize Schedule COMMIT (Ed25519)
  - Cause clock drift / desync                        - Cannot decrypt unicast Events (K_SESSION_UP)
  - Trigger holdover lockout (DoS)                    - Cannot forge Event ACKs (K_SESSION_DOWN)
  - Claim fake emergency in FLAGS                     - Cannot hijack Join handshakes (X25519 ECDH)
                                                      - Cannot reactivate rebooted Nodes
```

#### Detailed Impact Assessment:
1. **Clock Desynchronization & TDMA Disruption:** The attacker can broadcast forged Beacons with perturbed timestamps or invalid `SF_SEQ`, tricking neighboring nodes into shifting their TDMA slot boundaries, resulting in RF packet collisions or desynchronization lockout.
2. **Denial-of-Service via Stale Sequence:** Broadcasting an artificially high `SF_SEQ` causes nodes to advance their replay high-water mark, ignoring legitimate Gateway Beacons with lower sequences.
3. **Emergency Flag Spoofing:** The attacker can set `FLAGS[5]` (Emergency), triggering unnecessary local node alerts or panic behavior if not cross-validated.

#### Cryptographic Containment Boundaries (Why the Network Survives):
1. **Schedule Migration Immunity:** Schedule changes require Backend Ed25519 signatures (`DOWN_SCHED_PREPARE` and `DOWN_SCHED_DECISION`). Possession of $K_{\text{BEACON}}$ grants **zero capability** to forge schedule modifications or alter slot allocations.
2. **Unicast Event Data Secrecy:** Application data (`UP_EVENT` 0x41) and acknowledgments (`DOWN_EVENT_ACK` 0x42) are encrypted and authenticated using pairwise session keys ($K_{\text{SESSION\_UP}}$, $K_{\text{SESSION\_DOWN}}$) derived from ephemeral X25519 ECDH during Join. A compromised Beacon key cannot decrypt or inject sensor telemetry.
3. **Reboot Protection:** Rebooted nodes enter `RX_ONLY / DATA_TX_DISABLED`. Receiving a forged Beacon does not re-enable DATA transmissions; only a Backend-authorized reactivation workflow can clear the transmission lock.

---

## 3. Key Topology, Governance & Lifecycle

### 3.1 Key Generation & Isolation
Each Gateway is assigned a distinct, cryptographically secure 256-bit key:

$$K_{\text{BEACON}} \xleftarrow{\$} \text{CSPRNG}(256\text{ bits})$$

**Key Separation Invariants:**
- $K_{\text{BEACON}}$ MUST be generated completely independently of all other network secrets.
- MUST NOT be derived from, or mathematically related to:
  * Backend Join Pre-shared Key $K_{\text{JOIN}}$ (`DEC-SEC-03`).
  * Unicast session keys $K_{\text{SESSION\_UP}}$ or $K_{\text{SESSION\_DOWN}}$ (`DEC-SEC-01`).
  * Backend Ed25519 private schedule signing key.
  * Node/Gateway X25519 ephemeral private keys or AES-CCM nonces.

### 3.2 Component Knowledge Matrix
In strict adherence to the Backend Zero-Knowledge architectural principle (`DEC-SEC-01`):

| Network Entity | Possesses $K_{\text{BEACON}}$? | Storage Mechanism | Operational Role |
|---|:---:|---|---|
| **Gateway** | **YES** | Encrypted NVS (`nvs_sec_provider`) | Generates HMAC tag for Slot 0 Beacon broadcast |
| **Authorized Node** | **YES** | Encrypted NVS (`nvs_sec_provider`) | Verifies HMAC tag in received Beacon broadcast |
| **Backend Monolith** | **NO** | Zero-Knowledge (metadata only: `GW_ID`, `KEY_ID`) | Plans TDMA schedules; does NOT hold group MAC key |
| **Attacker / Candidate** | **NO** | None | Denied access |

### 3.3 Out-of-Band (OOB) Provisioning Workflow
For the MVP baseline, $K_{\text{BEACON}}$ is provisioned exclusively **out-of-band under a trusted local provisioning workflow**:

```
+---------------------------------------------------------------------------------+
|                   TRUSTED LOCAL PROVISIONING WORKFLOW (OOB)                     |
|                                                                                 |
|   1. Provisioning Tool generates CSPRNG 256-bit K_BEACON and assigns KEY_ID     |
|   2. Secure UART / JTAG flashes K_BEACON into Gateway Encrypted NVS             |
|   3. Secure UART / JTAG flashes K_BEACON into Authorized Nodes Encrypted NVS    |
|   4. Backend registry logs (GW_ID, KEY_ID, Timestamp) — NO SECRET BYTES         |
+---------------------------------------------------------------------------------+
```

- **Initial Join Decoupling:** Initial Join via CAD at any time does not require pre-provisioned $K_{\text{BEACON}}$. A newly manufactured node can join using its factory $K_{\text{JOIN}}$. However, until $K_{\text{BEACON}}$ is provisioned, the node cannot verify Beacons, cannot track network time, and remains in `DATA_TX_DISABLED`.
- **Zeroization Constraints:** On detected physical tampering, repeated failed authentication traps, or decommission command, firmware securely overwrites $K_{\text{BEACON}}$ storage with zeros before erasing the NVS sector (`memset_s` followed by sector erase).

### 3.4 Key Rotation & Compromise Recovery Runbook
1. **MVP Policy — No Automatic In-Band RF Key Rotation:** Dynamic over-the-air key rotation is explicitly **OUT OF SCOPE** for MVP. Re-keying via broadcast HMAC would be insecure if the existing group key is compromised.
2. **Compromise Response Runbook:**
   - **Step 1 (Revocation):** Operator marks affected `KEY_ID` as revoked in Backend metadata and logs an audit security event.
   - **Step 2 (Local Reprovisioning):** Field technician visits site or brings devices to a secure staging environment.
   - **Step 3 (Re-Keying):** A fresh random 256-bit key $K_{\text{BEACON}}'$ with incremented $\text{KEY\_ID}'$ is flashed into Gateway and remaining trustworthy Nodes via secure local interface.
   - **Step 4 (Network Reactivation):** Gateway begins broadcasting Beacons with $\text{KEY\_ID}'$; authorized nodes update their key table and restore synchronization. Stolen node remains locked out.

---

## 4. Canonical Wire Format & MAC Transcript Specification

### 4.1 32-Octet Frame Layout
Multi-byte integers are encoded in **network byte order (Big-Endian)**.

| Offset | Field Name | Width | Type | Semantics & Verification Rules |
|:---:|---|:---:|:---:|---|
| **0** | `MAGIC` | 1B | `u8` | Fixed constant `0x43` (`DOWN_SYNC_BEACON`). Drop packet if mismatch. |
| **1** | `GW_ID` | 1B | `u8` | Gateway identifier ($1..255$). Must match Node's associated Gateway. |
| **2–5** | `EPOCH_SEC` | 4B | `u32be` | Monotonic Unix epoch timestamp (seconds). Used for absolute time anchor. |
| **6–9** | `SF_SEQ` | 4B | `u32be` | Monotonic superframe sequence counter. Strictly checked for anti-replay. |
| **10** | `SCHED_VER` | 1B | `u8` | Informational schedule generation hint. **DOES NOT authorize schedule change.** |
| **11** | `FLAGS` | 1B | `u8` | Bitmask: Bit 5 = `EMERGENCY_FLAG`; Bits 7:6 = `0` (reserved); Bits 4:0 = `0` (reserved). |
| **12** | `KEY_ID` | 1B | `u8` | Identifies $K_{\text{BEACON}}$ generation ($1..255$). Node selects matching key. |
| **13–15** | `RESERVED` | 3B | `bytes` | Reserved for future alignment. MUST be set to `0x000000`. Drop if non-zero. |
| **16–31** | `TAG16` | 16B | `bytes` | Leftmost 16 bytes of HMAC-SHA256 across canonical transcript. Constant-time match. |
| **Total** | | **32B** | | |

### 4.2 Canonical MAC Transcript Definition
To ensure strict domain separation and prevent cross-protocol collision (e.g. against Join tags or session packets), the MAC is computed across an unambiguous, length-prefixed canonical transcript:

$$\text{TRANSCRIPT} = \text{DOMAIN} \parallel \text{NETWORK\_ID} \parallel \text{HEADER16}$$

```
+------------------------------------+------------------+-----------------------------+
| DOMAIN (24 Bytes)                  | NETWORK_ID (2B)  | HEADER16 (16 Bytes)         |
| "LP2P_V2_BEACON_AUTH_v01\0"        | u16 Big-Endian   | Offset 0..15 of Beacon Frame|
+------------------------------------+------------------+-----------------------------+
```

1. **Domain String (24 octets):** ASCII string with null terminator:
   `"LP2P_V2_BEACON_AUTH_v01\0"` (`4c 50 32 50 5f 56 32 5f 42 45 41 43 4f 4e 5f 41 55 54 48 5f 76 30 31 00`).
2. **Network Identifier (2 octets):** 16-bit unsigned integer in Big-Endian format (`u16be`), binding the beacon to the specific LP2P network installation (e.g. `0x0001`).
3. **Header Block (16 octets):** Exact raw bytes of Offsets 0..15 from the wire frame.
4. **Transcript Total Length:** $24 + 2 + 16 = 42\text{ octets}$.

### 4.3 Tag Computation & Truncation
$$\text{FULL\_TAG} = \text{HMAC-SHA256}(K_{\text{BEACON}}, \text{TRANSCRIPT}) \quad (32\text{ octets})$$
$$\text{TAG16} = \text{FULL\_TAG}[0 \dots 15] \quad (\text{leftmost } 16\text{ octets})$$

### 4.4 Constant-Time Verification Requirement
Nodes MUST verify the received `TAG16` against their locally computed tag using a **constant-time byte comparison** function to eliminate timing side-channel leakage:
- **ESP-IDF / C:** `mbedtls_ct_memcmp(received_tag, computed_tag, 16) == 0`.
- **Backend / Go:** `subtle.ConstantTimeCompare(received_tag, computed_tag) == 1`.

---

## 5. Anti-Replay, Epoch Monotonicity & Reboot Recovery

### 5.1 Node Ingestion & Verification Pipeline
Upon demodulation of a 32-octet packet on Slot 0 during the Maintenance window, the Node radio driver executes the following deterministic 7-step gate:

```
[Packet Demodulated (32B)]
          │
          ▼
   [1. Length == 32 & MAGIC == 0x43?] ──NO──► DROP (Ignore)
          │ YES
          ▼
   [2. GW_ID == ASSIGNED_GW_ID?]     ──NO──► DROP (Foreign Gateway)
          │ YES
          ▼
   [3. KEY_ID provisioned in NVS?]    ──NO──► DROP & Increment UNKNOWN_KEY_ERR
          │ YES
          ▼
   [4. Constant-Time TAG16 Matches?]  ──NO──► DROP & Log AUTH_FAIL_TRAP
          │ YES
          ▼
   [5. SF_SEQ > LAST_SEEN_SF_SEQ?]    ──NO──► DROP & Log REPLAY_TRAP
          │ YES
          ▼
   [6. |EPOCH_SEC - LOCAL_TIME| < T?] ──NO──► DROP & Log TIME_SKEW_ERR
          │ YES
          ▼
   [7. Update NVS High-Water Mark]
   [Synchronize TDMA Slot Clocks]
   [Reset Consecutive Miss Count N_MISSED = 0]
```

### 5.2 Persistent Anti-Replay High-Water Mark
To prevent replay attacks across power cycles, brownouts, or watchdog resets:
1. **Durable Storage:** The Node maintains `LAST_SEEN_SF_SEQ` in non-volatile storage (NVS).
2. **Wear-Leveling Policy:** If writing NVS on every ~300s Maintenance superframe causes flash wear concerns over a 10-year lifespan (~105,000 writes, well within typical ESP32 flash endurance of 100k cycles, but conservative engineering applies), firmware may commit `LAST_SEEN_SF_SEQ` with a step margin (e.g. write $\text{SF\_SEQ} + 10$ upon cold start, maintaining volatile tracking until boundary crossing).
3. **Reboot High-Water Fence:** Upon reboot, Node loads the stored threshold. Any received Beacon with $\text{SF\_SEQ} \le \text{STORED\_HIGH\_WATER}$ is unconditionally rejected.

### 5.3 32-Bit Sequence Wrap-Around Analysis
At a nominal Maintenance superframe recurrence of 300 seconds:

$$\text{Time to Wrap} = \frac{2^{32} \times 300\text{ seconds}}{3600 \times 24 \times 365.25} \approx 40,845\text{ years}$$

Counter overflow of `SF_SEQ` is mathematically impossible within the operational lifespan of the hardware. Any wrap detection indicates either deliberate malicious tampering or firmware corruption, resulting in fail-closed rejection.

### 5.4 Reboot State Invariant (`RX_ONLY / DATA_TX_DISABLED`)
In accordance with system-wide fail-closed rules:
- Following power-on or reset, a Node enters `RX_ONLY / DATA_TX_DISABLED`.
- Successfully receiving and verifying `DOWN_SYNC_BEACON 0x43` synchronizes physical timers and clears clock uncertainty, but **DOES NOT** transition the node into `ACTIVE_TX` mode.
- DATA slot transmission remains strictly locked until an authorized Backend resynchronization/reactivation exchange completes.

---

## 6. PHY Modeling & Theoretical Time on Air (ToA) Recomputation

### 6.1 SX1276 LoRa PHY Parameters
Calculations are based on the Semtech SX1276 Datasheet Rev 7 (March 2015), Sections 4.1.1.5 through 4.1.1.7:

- Bandwidth ($BW$): $125\text{ kHz}$ ($125,000\text{ Hz}$).
- Spreading Factor ($SF$): $7$ and $8$.
- Coding Rate ($CR$): $1$ ($4/5$).
- Explicit Header Mode ($H$): $0$ (Header Enabled).
- Payload CRC ($CRC$): $1$ (CRC Enabled, 16 bits).
- Low Data Rate Optimize ($DE$): $0$ (Disabled for SF7 and SF8 at 125 kHz, since $T_s < 16\text{ ms}$).
- Preamble Symbols ($N_{\text{preamble}}$): $8$ symbols.

### 6.2 Mathematical Equations
$$\text{Symbol Duration: } T_s = \frac{2^{SF}}{BW}$$
$$\text{Preamble Duration: } T_{\text{preamble}} = (N_{\text{preamble}} + 4.25) \times T_s = 12.25 \times T_s$$
$$\text{Payload Symbol Count: } N_{\text{payload}} = 8 + \max\left(\left\lceil \frac{8 \times PL - 4 \times SF + 28 + 16 \times CRC - 20 \times H}{4 \times (SF - 2 \times DE)} \right\rceil \times (CR + 4), 0\right)$$
$$\text{Total Packet Time on Air: } T_{\text{packet}} = T_{\text{preamble}} + (N_{\text{payload}} \times T_s)$$

### 6.3 Exact ToA Comparison: 32B HMAC vs 80B Ed25519

| Metric | SF7 (32B HMAC) | SF7 (80B Ed25519) | SF8 (32B HMAC) | SF8 (80B Ed25519) |
|---|:---:|:---:|:---:|:---:|
| **Symbol Duration ($T_s$)** | $1.024\text{ ms}$ | $1.024\text{ ms}$ | $2.048\text{ ms}$ | $2.048\text{ ms}$ |
| **Preamble Time ($T_{\text{preamble}}$)** | $12.544\text{ ms}$ | $12.544\text{ ms}$ | $25.088\text{ ms}$ | $25.088\text{ ms}$ |
| **Payload Symbols ($N_{\text{payload}}$)** | $58\text{ symbols}$ | $128\text{ symbols}$ | $53\text{ symbols}$ | $113\text{ symbols}$ |
| **Payload Duration ($T_{\text{payload}}$)** | $59.392\text{ ms}$ | $131.072\text{ ms}$ | $108.544\text{ ms}$ | $231.424\text{ ms}$ |
| **Total ToA ($T_{\text{packet}}$)** | **71.936 ms** | **143.616 ms** | **133.632 ms** | **256.512 ms** |
| **Airtime Reduction** | **-71.68 ms (-49.9%)** | *Baseline* | **-122.88 ms (-47.9%)** | *Baseline* |

### 6.4 Slot 0 Maintenance Window Sizing (DEC-MH-07)
With theoretical ToA confirmed at **71.94 ms (SF7)** and **133.63 ms (SF8)**:
- **Recommended Slot 0 Window:** **250 ms for SF7**; **350 ms for SF8**.
- **Guard Margins:**
  * At SF7: $250\text{ ms} - 71.94\text{ ms} = 178.06\text{ ms}$ remaining margin, providing $>85\text{ ms}$ leading and trailing guards for crystal drift, RX preamble search, and SPI turnaround.
  * At SF8: $350\text{ ms} - 133.63\text{ ms} = 216.37\text{ ms}$ remaining margin.
- **Half-Duplex Radio Transition:** Gateway finishes TX at $T_0 + \text{ToA}$, allows $2\text{ ms}$ PA ramp-down, and enters Standby/RX mode well before Slot 1 Scheduled Health uplinks commence.

---

## 7. Wire Migration & Compatibility Roadmap

### 7.1 Contract Impact Analysis
1. **`contracts/OPEN_DECISIONS.md`:**
   - **`DEC-MH-01`**: Status updated to `OWNER_APPROVED_MVP_DESIGN / READY_FOR_CONTRACT_FREEZE`. Formally locks 32B HMAC-SHA256-128 wire layout.
   - **`DEC-MH-07`**: Status updated to `OWNER_APPROVED_MVP_CONFIG`. Locks 250ms/350ms Beacon slot window based on 32B ToA.
2. **`contracts/radio-mac/specification.md`:**
   - Update Section 3 (`DOWN_SYNC_BEACON`) with finalized 32B layout, field table, and canonical transcript definition.
   - Reaffirm that `0x43` is dedicated strictly to 32B HMAC-128; mark 80B Ed25519 as superseded.
3. **`contracts/radio-mac/tdma-schedule.md`:**
   - Reconcile Section 4 Maintenance Superframe geometry to reflect 32B Beacon ToA and removed countdown flags.
4. **Historical Provenance Protection:**
   - V1 28B Group-HMAC (`0x01/0x21`) in PR #124 remains archived as `SUPERSEDED_HISTORICAL`.
   - V2 80B Ed25519 design in historical PRs remains in Git audit history; no ambiguous dual-format sniffing on the RF channel is permitted.

---

## 8. Cryptographic Golden Vectors

The following deterministic test vectors provide unambiguous verification for Go backend test suites and ESP-IDF C mbedTLS unit tests.

### Common Vector Parameters
- **Domain Separator (24B):** `LP2P_V2_BEACON_AUTH_v01\0` (`4c5032505f56325f424541434f4e5f415554485f76303100`)
- **Network ID (2B):** `0x0001` (`0001`)
- **Gateway ID (`GW_ID`):** `0x01` (`01`)
- **Key 1 ($K_{\text{BEACON\_1}}$, 32B):**
  `0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef`
- **Key 2 ($K_{\text{BEACON\_2}}$, 32B, Rotated Key):**
  `fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210`

---

### Vector 1: Standard Valid Baseline Beacon
- **Description:** Normal periodic Beacon broadcast, time = 1772880000 (2026-03-07 10:40:00 UTC), superframe sequence = 42, schedule version = 1, emergency = 0, key ID = 1.
- **Header 16B (hex):**
  `430169ac00800000002a010001000000`
- **Canonical Transcript 42B (hex):**
  `4c5032505f56325f424541434f4e5f415554485f763031000001430169ac00800000002a010001000000`
- **Full HMAC-SHA256 (32B):**
  `468af1cdb2facaa3c2b31e6e8d955696faa01040c41de3ac98dcc03d2eb0aa54`
- **Truncated TAG16 (16B):**
  `468af1cdb2facaa3c2b31e6e8d955696`
- **Final 32B Wire Frame (hex):**
  `430169ac00800000002a010001000000468af1cdb2facaa3c2b31e6e8d955696`

---

### Vector 2: Emergency Broadcast Beacon
- **Description:** Emergency flag active (`FLAGS = 0x20`, bit 5 set). All other fields identical to Vector 1. Demonstrates flag binding into MAC transcript.
- **Header 16B (hex):**
  `430169ac00800000002a012001000000`
- **Truncated TAG16 (16B):**
  `b2b6bb88996922fe6b6cf6ff366b7016`
- **Final 32B Wire Frame (hex):**
  `430169ac00800000002a012001000000b2b6bb88996922fe6b6cf6ff366b7016`

---

### Vector 3: Multi-Gateway Isolation (`GW_ID = 0x02`)
- **Description:** Adjacent Gateway broadcast (`GW_ID = 0x02`). Demonstrates that a Beacon from an unassociated Gateway fails MAC check even under identical network parameters.
- **Header 16B (hex):**
  `430269ac00800000002a010001000000`
- **Truncated TAG16 (16B):**
  `fada9898e0048b782a069da63ead0a76`
- **Final 32B Wire Frame (hex):**
  `430269ac00800000002a010001000000fada9898e0048b782a069da63ead0a76`

---

### Vector 4: Rotated Key Identification (`KEY_ID = 0x02`)
- **Description:** Key rotation event; `KEY_ID = 0x02`, superframe sequence advanced to 43, computed under Key 2 ($K_{\text{BEACON\_2}}$).
- **Header 16B (hex):**
  `430169ac00800000002b010002000000`
- **Truncated TAG16 (16B):**
  `2483a2a9353fca1e80f1132851a7d1a3`
- **Final 32B Wire Frame (hex):**
  `430169ac00800000002b0100020000002483a2a9353fca1e80f1132851a7d1a3`

---

### Vector 5: Tamper Rejection (Negative Vector)
- **Description:** Attacker captures Vector 1 wire frame and tampers with timestamp by 1 second (`EPOCH_SEC` altered from `0x69ac0080` to `0x69ac0081`) while preserving the original `TAG16`.
- **Tampered Frame (32B):**
  `430169ac00810000002a010001000000468af1cdb2facaa3c2b31e6e8d955696`
- **Expected Outcome:** Verification fails (`mbedtls_ct_memcmp != 0`). Frame dropped, trap logged.

---

## 9. Comprehensive Verification & Test Matrix

| Test ID | Test Scenario | Preconditions | Stimulus / Input | Expected System Behavior | Compliance Assertion |
|---|---|---|---|---|---|
| **TM-BCN-01** | 32B Frame Geometry | Radio driver initialized | Wire packet $\ne 32$ octets (e.g. 31B or 33B) | Packet rejected immediately by PHY length filter before cryptographic processing. | Bounded memory buffer integrity |
| **TM-BCN-02** | Golden Vector Parity | Node has $K_{\text{BEACON\_1}}$ installed | Feed Vector 1 wire bytes | HMAC tag matches perfectly; `SF_SEQ=42` accepted; clock updated. | Go $\leftrightarrow$ ESP-IDF mbedTLS parity |
| **TM-BCN-03** | Constant-Time Tamper Rejection | Node active | Feed Vector 5 (tampered timestamp) | Constant-time check fails; frame dropped; zero clock modification. | Timing side-channel immunity |
| **TM-BCN-04** | Gateway Binding Isolation | Node assigned `GW_ID=0x01` | Feed Vector 3 (`GW_ID=0x02`) | Node drops packet at Gateway ID check or MAC mismatch; no sync. | Co-channel multi-gateway isolation |
| **TM-BCN-05** | Anti-Replay Monotonicity | Node recorded `SF_SEQ=42` | Re-transmit Vector 1 (`SF_SEQ=42`) or older | Node verifies MAC, checks $\text{SF\_SEQ} \le 42$, drops packet with `REPLAY_DETECTED`. | Anti-replay enforcement |
| **TM-BCN-06** | Reboot High-Water Persistence | Node rebooted; NVS has `SF_SEQ=42` | Feed Vector 1 (`SF_SEQ=42`) | Node rejects packet; high-water mark survives power loss. | Brownout & watchdog anti-replay |
| **TM-BCN-07** | Unknown `KEY_ID` Rejection | Node has only `KEY_ID=1` | Feed Vector 4 (`KEY_ID=2`) | Node cannot find matching key in NVS; frame dropped; error counter incremented. | Key lifecycle integrity |
| **TM-BCN-08** | Group MAC Scope Containment | Attacker possesses $K_{\text{BEACON}}$ | Attacker crafts forged Beacon with altered `SCHED_VER=2` | Node syncs time but DOES NOT alter TDMA schedule; migration requires signed PREPARE/DECISION. | Compromise containment proof |
| **TM-BCN-09** | Reboot TX-Lock Invariant | Node rebooted into `RX_ONLY` | Node receives valid Vector 1 | Node synchronizes clock but DATA TX remains locked; `DATA_TX_DISABLED` unchanged. | Fail-closed silence guarantee |
| **TM-BCN-10** | Physical ToA & Half-Duplex Guard | SF7/SF8 RF model | 32B packet on-air | Measured/calculated ToA $\le 72\text{ ms}$ (SF7) and $\le 134\text{ ms}$ (SF8); $>80\text{ ms}$ guard intact. | Half-duplex turnaround clearance |
| **TM-BCN-11** | Emergency Flag Recognition | Node active in normal state | Feed Vector 2 (`FLAGS=0x20`) | Node parses `EMERGENCY_FLAG=1`, raises local application alert while maintaining TDMA slot. | Protocol semantics compliance |

---

## 10. Explicit Open Decisions & Review Handoff

### 10.1 Resolved Architectural Decisions (Owner Approved)
- **DEC-MH-01 RESOLUTION:** `DOWN_SYNC_BEACON 0x43` is formally approved as a 32-octet authenticated frame: 16B header + 16B HMAC-SHA256-128 tag.
- **DEC-MH-07 RESOLUTION:** Beacon slot window sized to 250ms (SF7) / 350ms (SF8) with $>80\text{ ms}$ turnaround guards.
- **KEY TOPOLOGY RESOLUTION:** Per-Gateway random 256-bit CSPRNG key $K_{\text{BEACON}}$ provisioned out-of-band; Backend Zero-Knowledge preserved (`DEC-SEC-01`).
- **SCHEDULE DECOUPLING RESOLUTION:** Beacon does not authorize schedule changes; historical countdown removed (`FLAGS[7:6] = 0`).

### 10.2 Downstream Review & Implementation Handoff
1. **Contract Synchronization PR (Coordination with #127):** Formally apply the 32B Beacon specification and canonical transcript to `contracts/radio-mac/specification.md` and `contracts/radio-mac/tdma-schedule.md`.
2. **Firmware Implementation (Issue #131):** Implement the 32B parser and HMAC-SHA256-128 validator in `firmware/gateway` and `firmware/node` using mbedTLS.
3. **Backend Integration (Issue #19):** Ensure Go modular monolith schedules Maintenance superframes without generating individual RF slot TX commands or storing $K_{\text{BEACON}}$ secret bytes.
4. **Hardware Verification (Issue #169):** Perform bench measurements with real ESP32+SX1276 boards to empirically validate the 71.9ms / 133.6ms theoretical ToA and half-duplex SPI turnaround.

> **Final Verification Gate Notice:** This document completes the design phase for Issue #209. In accordance with project policy, status remains `IMPLEMENTATION_NOT_VERIFIED` and `G2_HIL_NOT_VERIFIED` until hardware bench evidence is collected under #169.
