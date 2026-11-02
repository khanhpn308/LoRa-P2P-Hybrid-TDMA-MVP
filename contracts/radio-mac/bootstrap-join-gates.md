# Bootstrap Join — Agent Gate Register

**DRAFT · END-TO-END CODE BLOCKED · G2/G3/G4=NOT_VERIFIED**

**OWNER APPROVED DESIGN:** [J01](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570037473) freezes `UP_JOIN_REQUEST:35B`; [J02](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570268130) freezes canonical `M_ACCEPT:57B` and 16B HMAC for `DOWN_JOIN_ACCEPT:22B`. These are scoped design approvals, **not production/interop/security PASS**. [Historical decision pack](bootstrap-join-j01-j02-proposal.md), [Python-only fixture](test-vectors/bootstrap-join-j02-proposed.json). **J06/J07/J10/G2 and end-to-end Join remain OPEN.**

**Agent:** Check J01–J12. Do not infer approval from fixtures, comments or CI syntax. Only isolated already-specified code/tests are allowed. No Join/DATA TX enablement. [Contract](bootstrap-join-v1.md) · [Owner record](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116).

## Owner-approved design and remaining gates — before end-to-end Join

| Gate | Missing or disputed contract item | Responsibility | Blocked scope |
|---|---|---|---|
| **J01** | **OWNER_APPROVED_DESIGN** ([decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570037473)): exact 35B Request fields, offsets, mandatory validation; J06/J07 and independent G2 verification remain separate | Node / Backend / Security | Production RF Join TX still blocked by J06/J07/J10 and other gates |
| **J02** | **OWNER_APPROVED_DESIGN** ([decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/124#issuecomment-6570268130)): 57B `M_ACCEPT` ordered transcript and first16 HMAC tag, validation/rejection invariants; J06 identity and J10/G2 vectors/security review still OPEN | Security / Node / Backend | Production Accept/Confirm end-to-end blocked by other gates |
| **J03** | MQTT Join discovery relay, assignment/accept dispatch, Confirm forwarding, durable message IDs, expiry and idempotency in canonical namespace | Backend / Gateway / Infra | End-to-end Join routing |
| **J04** | Precise shared CTRL UL/DL allocation, Response Window delay/length, retry budget, queue pressure, half-duplex, timing and legal RF airtime | RF / Gateway / Node | Real on-air Join TX |
| **J05** | Complete Node/Gateway/Backend state-transition matrix incl. expired assignment/rejoin race, reboot & rollback, resource admission, completion/activation ACK | Node / Gateway / Backend | Autonomously active Join |
| **J06** | How Node obtains authenticated **`RELAY_GW_ID`** consistently with Backend when computing M_UP/M_DL, before trusting Beacon; cross-Gateway scan/relay mismatch | Security / RF / Node / Backend | Bootstrap origin/auth |
| **J07** | K_JOIN factory provisioning, ESP32 protected key storage, high-water reservation algorithm and 16-bit exhaustion/rekey/rollback recovery | Security / Node / Backend | Safe counter/key lifecycle |
| **J08** | Exact allowed RF channel list, PHY SyncWord, RF plan management, regulatory validation of deployed Vietnam band/power/module | RF owner / Compliance | Deployment/RF legality |
| **J09** | Authenticated Node Join Completion, initial TDMA Schedule/Lease issuance and strict DATA gate. **Beacon Group HMAC/28B Owner-selected** ([decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6575398231)); canonical HMAC transcript, shared-key lifecycle, replay, trusted Gateway/J06 and Beacon sync still OPEN | Gateway / Backend / Node / Security | `ACTIVE` authorization; valid Group HMAC alone does not grant DATA TX |
| **J10** | Cross-language C↔Go crypto golden vectors for new `VER_TYPE`, M_ACCEPT, M_CONFIRM, negative tamper/replay; independent conformance evidence | Security / QA / Node / Backend | G2 security contract approval |
| **J11** | MQTT Key Install DRAFT PR #123 review/integration and encrypted wrap-key provisioning/rotation | Backend / Gateway / Infra | Gateway session key installation |
| **J12** | Full G2 human review, G3 HIL RF timing/power/reboot evidence, G4 MQTT integration & failure injection | Security / RF / QA | Verified production |

No Agent may substitute an **Assumption** for a gate, mark it OWNER_APPROVED, commit secrets, or merge based only on passing JSON tests. Pure bounded parser/unit test development using explicitly approved widths/formulas may proceed in isolation.

## Implementation-ready acceptance

| Criterion | Expected evidence |
|---|---|
| AC-J01 | J01 35B field layout and scoped validation **Owner design approved**; J07 reserved Counter values and J10/G2 cross-language conformance still NOT_VERIFIED |
| AC-J02 | Canonical 57B `M_ACCEPT` and tag **Owner design approved**; J06 authenticated identity, compatibility/migration, C↔Go vectors and G2 review still NOT_VERIFIED |
| AC-J03 | Node / Gateway / Backend formal transition+timeout table with durable DB/NVS ownership |
| AC-J04 | MQTT Join schemas versioned, producer/consumer reviewed, topic identity/auth/idempotent dispatch |
| AC-J05 | Per-Node anti-replay high-water and CSPRNG/rekey/reboot rollback tests |
| AC-J06 | 3-key session proof cannot be forged by Gateway; no key leakage |
| AC-J07 | Independent C and Go same bytes/HMAC, positive/negative Golden Vectors with expected cryptographic results |
| AC-J08 | Simulation/HIL proves SX1276 RX Response Window, guard/ToA and legal policy for selected hardware/environment |
| AC-J09 | Zero DATA TX until authentic completed Join + Gateway key install + valid TDMA schedule/lease/sync |
| AC-J10 | Cross-team security/Radio MAC owner review, ADR for nontrivial security choices, CI logs and PR evidence |

**Current verdict:** AC-J01..AC-J10 **NOT FULLY SATISFIED**. Structural-only fixtures and static tests do **not** constitute Golden Vector interoperability or G2/HIL PASS. `main` retains its old legacy `0.1.0-draft` content until these changes are reviewed and merged.

## Decision references (on demand)

| ID | Scope of approval | Link / caution |
|---|---|---|
| `RF-HW-01` | Exactly one SX1276 per Gateway | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562208078) |
| `SF-RECOVERY-05` | Fixed shared CTRL Join+Recovery, Backend planned/User approved | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6559992609); timing still open |
| `RF-JOIN-RESPONSE-01` | Request-specific same-channel RX Response Window | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562516222) |
| `RF-JOIN-ASSIGNMENT-01` | Assignment via latest authenticated observing Gateway; Backend authority | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6562684029) |
| `RF-JOIN-PAYLOAD-01` | No `ASSIGNMENT_REV` on RF | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6563192168) |
| `RF-JOIN-PHY-01` | Keep `PHY_PROFILE_ID:1B` | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6563408032) |
| `RF-JOIN-ASSIGN-FRAME-02` | Assignment 23B [1,2,1,2,1,16] | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567010014) |
| `RF-FREQ-01 / RF-PHY-01` | F_BASE 920MHz, 1kHz uint16 BE, IDs 0x01..0x06 | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567194577); not RF compliance |
| `RF-BOOT-COUNTER-01 / RF-BOOT-NONCE-01` | Counter 2B BE + CSPRNG random 10B = 12B | [counter](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567288985), [nonce](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6567306330) |
| `RF-KJOIN/HKDF/HMAC/REPLAY-01` | Per-Node K_JOIN 32B, exact M_UP/M_DL, 16B HMAC tags and anti-replay invariants | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568170563) |
| `RF-VER-TYPE-01` | Version bits/packet registry 0x22–0x25 | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568296930); old Python sample tag used obsolete code bytes |
| `RF-JOIN-ACCEPT-01` | 22B Accept, no BACKEND_RANDOM, purpose-separated AUTH_TAG | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568432331); final M_ACCEPT byte transcript open |
| `RF-SESSION-KEY-01` | 32B context and three KDF-derived session/confirm keys, key ownership + lifecycle | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568716035) |
| `RF-JOIN-CONFIRM-01` | 19B Confirm, exact 79B HMAC transcript and Node↔Backend proof | [discussion](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568810810) |
| `MQTT-SESSION-KEY/KEY-WRAP/KEY-ACK-01` | Authenticated, encrypted, durable Gateway key install/ACK | [decision](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/116#issuecomment-6568895005); versioned Draft [PR #123](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/pull/123) |

**Important supersessions:** obsolete 4B Join Counter → **2B**; 30B Accept → **22B**; 21B Confirm → **19B**; previous `VER_TYPE` fixture bytes 0x21/0x22 → actual **0x22/0x23** for Join Request/Assignment; 8B legacy MAC Header+CRC16 is not this frame format. Legacy Beacon fixed-fields were revised to **11B** independently; do not treat Beacon full authentication as approved.
