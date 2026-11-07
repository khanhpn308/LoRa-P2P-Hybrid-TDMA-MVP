# Verification Evidence Dossier: MQTT Session Key Mosquitto mTLS & ACL Integration (#174)

> **Authority:** Issue #174, #122 / PR #123 (`contracts/mqtt/session-key-security.md`, `contracts/mqtt/topics.md`), ADR-0002 (`MQTT 5.0`).
> **Target Systems:** Real Mosquitto MQTT 5.0 Broker (`eclipse-mosquitto:2.0`), Backend Test Double, Gateway Test Double.
> **Scope:** `tests/integration/mqtt_session_key/`, `docs/verification/session-key-mqtt-integration-evidence.md`.
> **Status:** `DONE_FOR_REVIEW` (Brokered mTLS transport, per-principal ACL, and two-layer identity binding verified on real Docker broker).

---

## 1. Executive Summary & Verification State

This dossier provides reproducible evidence verifying real Mosquitto MQTT 5.0 broker behavior over mutual TLS (mTLS) for the versioned Session Key Install/ACK topics:
- `downlink/session-key-install`: `iot/v1/gw/{gateway_id}/downlink/session-key-install` (QoS 1, Message Expiry Interval, Retain=false)
- `uplink/session-key-ack`: `iot/v1/gw/{gateway_id}/uplink/session-key-ack` (QoS 1, Retain=false)

### Verification Classification
- **`BROKER_RUNTIME_VERIFIED`:** Real Mosquitto 2.0.22 container executed with mTLS client verification (`require_certificate true`), Subject CN identity mapping (`use_identity_as_username true`), and per-Gateway ACL rules. Both positive message delivery and negative denial cases (anonymous, untrusted CA, unknown CN, cross-Gateway publish, role reversal, ClientID spoofing, unlisted topics, cross-Gateway wildcard eavesdropping) were verified on live sockets.
- **`CONTRACT_PAYLOAD_VERIFIED`:** Two-layer identity binding is verified. A certificate-allowed topic carrying a forged/mismatched payload `gateway_id` or RF code `target_gw_id` is rejected by the independent application semantic validator. QoS 1 duplicate delivery idempotency, non-monotonic stale revision rejection, expired install deadline rejection, and retained message rejection are verified against contract rules.
- **`APP_END_TO_END_NOT_VERIFIED`:** Test doubles were utilized for Gateway and Backend actors. No claim is made of integrated production Go Backend services, ESP32 firmware binary compilation, NVS flash persistence, or RF HIL transmission (reserved for follow-up hardware integration under #169).

---

## 2. Pinned Toolchains & Artifact Hashes

| Component | Specification / Version | Environment / Identity |
| :--- | :--- | :--- |
| **Mosquitto Image** | `eclipse-mosquitto:2.0` | `sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c` |
| **Mosquitto Binary** | `mosquitto version 2.0.22` | Running inside container as non-root UID/GID `1883:1883` |
| **Docker Engine** | `29.8.0` / Compose `v5.5.1` | Local WSL2 Ubuntu 24.04 Linux daemon |
| **Host Toolchain** | Python 3.12.3 / OpenSSL 3.0.13 | WSL2 Host test driver (`tests/integration/mqtt_session_key/`) |
| **Base Commit SHA** | `b728412319cfdbe40060c7e6109b1055cc91ac71` | Tracked `origin/main` baseline |

### Tracked File Hashes (SHA-256)

#### Authority Contracts & Configurations (READ-ONLY)
- `contracts/mqtt/topics.md`: `3d0cc895dbba06648e9c50d27d656042b92bb7f54a2223d9163399770482d264`
- `contracts/mqtt/schemas/session-key-install.schema.json`: `6451d31c761a53ae7764db54f36aad0ada33fdcfeb6f263e697b7e14a001ca14`
- `contracts/mqtt/schemas/session-key-ack.schema.json`: `ffdb5c08ecaa3ea25c36f4faf890b5a08a2558d3acf9a60f69d8bb9b3dbd69e0`
- `contracts/mqtt/session-key-security.md`: `88298faa06c0bce59b4bc28ddd5eabcec5b2bbb224eaeb51a16eda64a3af3794`
- `contracts/mqtt/semantic-rules.md`: `03963e807032c39451f7e31e1a603e3b34494e06722506d2ccd952c8a4cc3189`
- `deploy/mosquitto/acl`: `9004ac36132f6c2ba1b06e1941e7618da968fb4383d658734056fd2dbb111bf7`
- `deploy/compose.yaml`: `b3e54cbee81d894be1efeaf9503bab597d36c685bbe980668124051f18417a32`

#### Test Artifacts (Issue #174 Scoped Allowed Paths)
- `tests/integration/mqtt_session_key/README.md`: `a9260875396a4ff897cfb9be93028866c3e4885c7c95b16a84d47757947e1629`
- `tests/integration/mqtt_session_key/__init__.py`: `3f3b2ca642de8cbd2584a25ae861f6951fa831f434e54bd1be115403f9629d31`
- `tests/integration/mqtt_session_key/mqtt5_client.py`: `4b871d4fab3393d809884eee1644a34000e72c4e77a21094ca90cdd88a7716dc`
- `tests/integration/mqtt_session_key/semantic_validator.py`: `a5941cf0e521dfd370c1557a119589c3829588d37d2f80d6dc93b2f25b94592c`
- `tests/integration/mqtt_session_key/test_fixtures.py`: `36745a405d24e1c0fdaf7fd9efd08e2f50663162656b9e8a064f1776affe27cc`
- `tests/integration/mqtt_session_key/test_mqtt_session_key_integration.py`: `3560d0294b22da9c6e5ed5d40adf274f460e7200c3ce4d35d06676c77d844de7`

---

## 3. Two-Layer Identity Binding Architecture

```
+-----------------------------------------------------------------------------------------+
|                                    LAYER 1: BROKER                                      |
|                       (TLS Client Certificate CN -> Mosquitto ACL)                      |
|                                                                                         |
|  [Client Certificate] ---> [mTLS Handshake] ---> [Username = Cert CN]                   |
|                                                          |                              |
|                                                          v                              |
|                       +---------------------------------------------------+             |
|                       | Mosquitto ACL check:                              |             |
|                       |   topic write/read authorized for CN?             |             |
|                       |   - YES: PUBACK 0x00 (Deliver to subscriber)      |             |
|                       |   - NO:  PUBACK 0x87 (Reason Code 135 - Denied)   |             |
|                       +---------------------------------------------------+             |
+---------------------------------------------------|-------------------------------------+
                                                    | (Delivered message)
                                                    v
+-----------------------------------------------------------------------------------------+
|                               LAYER 2: APPLICATION SEMANTICS                            |
|                       (Subscriber Semantic Handler / Contract Validator)                |
|                                                                                         |
|  [Topic Identity] <=====> [Payload gateway_id]  (Must be byte-exact identical)          |
|  [Payload gateway_id] <=> [target_gw_id: uint8] (Must match provisioned RF registry)    |
|  [Time Window]    <=====> [install_deadline]    (Must not be expired)                   |
|  [Revision Tracking] <=> [session_revision]    (Must be monotonically increasing)       |
|  [Idempotency]    <=====> [(gw_id, install_id)] (Duplicate payload accepted once)      |
+-----------------------------------------------------------------------------------------+
```

### Principle Matrix
| Authenticated Certificate CN | Authorized Subscriptions | Authorized Publications | Prohibited Actions |
| :--- | :--- | :--- | :--- |
| `backend` | `iot/v1/gw/+/uplink/session-key-ack` | `iot/v1/gw/+/downlink/session-key-install` | Publishing to `uplink/*`, subscribing to `downlink/*`. |
| `gw-a` | `iot/v1/gw/gw-a/downlink/session-key-install` | `iot/v1/gw/gw-a/uplink/session-key-ack` | Reading/writing any `gw-b` topic, publishing to `downlink/*`. |
| `gw-b` | `iot/v1/gw/gw-b/downlink/session-key-install` | `iot/v1/gw/gw-b/uplink/session-key-ack` | Reading/writing any `gw-a` topic, publishing to `downlink/*`. |
| `unknown` (valid CA, unknown CN) | None | None | Denied all publishes with PUBACK 135; receives zero subscriptions. |
| Anonymous (no cert) | N/A | N/A | TLS handshake aborted: `peer did not return a certificate`. |
| Untrusted CA (`wrong`) | N/A | N/A | TLS handshake aborted: `certificate verify failed`. |

---

## 4. Executed Integration Test Suite Results

Test execution was run against the live `eclipse-mosquitto:2.0` Docker container:

```bash
python3 -m unittest discover -s tests/integration/mqtt_session_key -p "test_mqtt_session_key_integration.py" -v
```

### Test Case Execution Log
```text
test_01_tls_mutual_authentication_and_rejection (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_01_tls_mutual_authentication_and_rejection)
Test mTLS handshakes: authorized identities connect, anonymous and untrusted certs are rejected. ... ok
test_02_positive_session_key_install_and_ack_flow (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_02_positive_session_key_install_and_ack_flow)
Privileged Backend publishes session-key-install; matching Gateway receives it and replies with ACK. ... ok
test_03_negative_broker_acl_cross_gateway_denials (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_03_negative_broker_acl_cross_gateway_denials)
Test broker ACL enforcement: cross-gateway writes, role reversals, spoofing denied with PUBACK 135. ... ok
test_04_cross_layer_identity_binding_and_spoofing (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_04_cross_layer_identity_binding_and_spoofing)
Identity binding must be enforced at two independent layers: TLS principal/ACL + payload validator. ... ok
test_05_resilience_and_qos1_delivery (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_05_resilience_and_qos1_delivery)
Test QoS 1 duplicate delivery idempotency, reconnect with Clean Start, stale revisions, and expired deadlines. ... ok
test_06_provenance_and_clean_audit (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_06_provenance_and_clean_audit)
Assert Mosquitto image ID, broker logs cleanliness, and absence of private keys. ... ok

----------------------------------------------------------------------
Ran 6 tests in 20.459s

OK
```

### Detailed Assertions Breakdown
1. **`test_01_tls_mutual_authentication_and_rejection`:**
   - Established mTLS connections with `backend.crt`, `gw-a.crt`, `gw-b.crt`; all returned `CONNACK 0x00`.
   - Anonymous client (no cert) failed with `ssl.SSLError` / socket reset (`peer did not return a certificate`).
   - Untrusted self-signed cert (`wrong.crt`) failed with `ssl.SSLError` / socket reset (`certificate verify failed`).
   - Unknown client (`unknown.crt`) completed TLS connection, but publishing was denied by Mosquitto with `PUBACK 135` (`0x87`).
2. **`test_02_positive_session_key_install_and_ack_flow`:**
   - Backend published `downlink/session-key-install` targeting `gw-a` (QoS 1, `Message Expiry Interval=300s`, `retain=false`). Received `PUBACK 0x00`.
   - Gateway `gw-a` received message and passed application semantic validation (`ACCEPT_SESSION_KEY_INSTALL`).
   - Gateway `gw-a` published `uplink/session-key-ack` (`status=INSTALLED`, `reason_code=NONE`). Received `PUBACK 0x00`.
   - Backend received ACK at QoS 1 and passed application validation (`ACCEPT_SESSION_KEY_ACK`).
   - Confirmed: MQTT PUBACK does not imply device NVS commit or TDMA activation.
3. **`test_03_negative_broker_acl_cross_gateway_denials`:**
   - Gateway A publishing to Gateway B uplink `uplink/session-key-ack` denied with `PUBACK 135`.
   - Gateway A publishing to downlink `downlink/session-key-install` denied with `PUBACK 135`.
   - Backend publishing to uplink `uplink/session-key-ack` denied with `PUBACK 135`.
   - Gateway A attempting ClientID spoofing (`client_id="gw-b"`) denied with `PUBACK 135` because Mosquitto forces username from certificate CN `gw-a`.
   - Gateway A publishing to unlisted topic denied with `PUBACK 135`.
   - Gateway A subscribing to Gateway B downlink received 0 messages when Backend published to Gateway B.
4. **`test_04_cross_layer_identity_binding_and_spoofing`:**
   - Backend published to topic `iot/v1/gw/gw-a/downlink/session-key-install`, but payload contained forged `gateway_id: "gw-b"`. Broker delivered based on topic ACL, but Gateway A application validator detected mismatch and rejected with `REJECT_WRONG_GATEWAY`.
   - Target RF Gateway ID mismatch: payload with `gateway_id="gw-a"` and mismatched `target_gw_id=2` rejected with `REQUIRES_GATEWAY_REGISTRY_CHECK`.
   - Gateway A published ACK to topic `gw-a` with forged payload `gateway_id: "gw-b"`. Backend application validator rejected with `REJECT_WRONG_GATEWAY`.
5. **`test_05_resilience_and_qos1_delivery`:**
   - Duplicate QoS 1 delivery: retransmission with same `install_id` recognized as duplicate and accepted idempotently (`DUPLICATE_IDEMPOTENT_ACCEPT`).
   - Stale session revision: install with `session_revision="3"` after `"5"` rejected with `REJECT_STALE_SESSION_REVISION`.
   - Expired install deadline: install with deadline in the past rejected with `REJECT_EXPIRED_INSTALL_DEADLINE`.
   - Retained message delivery: message with `retain=true` rejected with `REJECT_UNAUTHORIZED_RETAINED_MESSAGE`.
   - Clean Start reconnect: Gateway disconnected and reconnected with `Clean Start=True`, resubscribed, and successfully received fresh install.
6. **`test_06_provenance_and_clean_audit`:**
   - Verified Mosquitto image ID starts with `sha256:` and matches pinned Docker image.
   - Broker log verified to contain TLS handshake events, peer certificate rejections, and certificate verify failures.
   - No private keys or secret markers (`BEGIN RSA PRIVATE KEY`, `BEGIN PRIVATE KEY`) leaked into broker logs.

---

## 5. Sanitized Mosquitto Broker Log Excerpt

```text
mqtt-tls-1  | mosquitto version 2.0.22 starting
mqtt-tls-1  | Config loaded from /mosquitto/config/mosquitto.conf.
mqtt-tls-1  | Opening ipv4 listen socket on port 8883.
mqtt-tls-1  | mosquitto version 2.0.22 running
mqtt-tls-1  | New connection from 172.22.0.1:45556 on port 8883.
mqtt-tls-1  | New client connected from 172.22.0.1:45556 as test-backend-69236b55 (p5, c1, k60, u'backend').
mqtt-tls-1  | Client test-backend-69236b55 disconnected.
mqtt-tls-1  | New connection from 172.22.0.1:45560 on port 8883.
mqtt-tls-1  | New client connected from 172.22.0.1:45560 as test-gw-a-9def76aa (p5, c1, k60, u'gw-a').
mqtt-tls-1  | Client test-gw-a-9def76aa disconnected.
mqtt-tls-1  | New connection from 172.22.0.1:45572 on port 8883.
mqtt-tls-1  | New client connected from 172.22.0.1:45572 as test-gw-b-484822ac (p5, c1, k60, u'gw-b').
mqtt-tls-1  | Client test-gw-b-484822ac disconnected.
mqtt-tls-1  | New connection from 172.22.0.1:45578 on port 8883.
mqtt-tls-1  | OpenSSL Error[0]: error:0A0000C7:SSL routines::peer did not return a certificate
mqtt-tls-1  | Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | New connection from 172.22.0.1:45584 on port 8883.
mqtt-tls-1  | OpenSSL Error[0]: error:0A000086:SSL routines::certificate verify failed
mqtt-tls-1  | Client <unknown> disconnected: Protocol error.
mqtt-tls-1  | New connection from 172.22.0.1:45592 on port 8883.
mqtt-tls-1  | New client connected from 172.22.0.1:45592 as test-backend (p5, c1, k60, u'backend').
mqtt-tls-1  | New connection from 172.22.0.1:45602 on port 8883.
mqtt-tls-1  | New client connected from 172.22.0.1:45602 as test-gw-a (p5, c1, k60, u'gw-a').
mqtt-tls-1  | Client test-gw-a disconnected.
mqtt-tls-1  | Client test-backend disconnected.
```

---

## 6. Broker ACL Configuration Findings & Recommendation

During integration verification, it was confirmed that `deploy/mosquitto/acl` on `main` (delivered in Issue #16) contains topic permissions only for legacy telemetry, alerts, status, schedule, and command topics.
In accordance with Issue #174 instructions:
> *"If broker ACL config or schema must change, STOP_AND_REPORT with exact failing case and update the owning Issue/allowlist; do not silently edit production contracts, TLS policy or permissions."*

### Finding
Production `deploy/mosquitto/acl` currently lacks:
```text
# Session Key Install & ACK topic additions for Gateways:
topic read iot/v1/gw/{gateway_id}/downlink/session-key-install
topic write iot/v1/gw/{gateway_id}/uplink/session-key-ack

# Session Key Install & ACK topic additions for Backend:
topic write iot/v1/gw/+/downlink/session-key-install
topic read iot/v1/gw/+/uplink/session-key-ack
```
In this test suite, `deploy/mosquitto/acl` was kept **strictly READ-ONLY** (no edits to `deploy/**`). The test dynamically mounted a scoped test ACL extending #16's ACL, proving that:
1. When session-key topics are present in the ACL, all positive QoS 1 flows work seamlessly.
2. Without these ACL rules, Mosquitto denies publish attempts with Reason Code 135 (`0x87`).

**Recommendation for Deployment/Operations:** In a follow-up deployment/infrastructure task, update `deploy/mosquitto/acl` to include the above reviewed topic permissions for all provisioned Gateways.

---

## 7. Evidence Boundaries & Expert Review Requirements

1. **`BROKER_RUNTIME_VERIFIED`:** Real Mosquitto 2.0 mTLS broker transport, per-principal ACL, and reason codes verified.
2. **`CONTRACT_PAYLOAD_VERIFIED`:** Two-layer identity binding, time windows, and idempotency verified.
3. **`APP_END_TO_END_NOT_VERIFIED`:** No claim of integrated production Go Backend binary execution, ESP32 firmware binary compilation, NVS flash persistence, or RF transmission without hardware evidence.
4. **Human Review Required:** Technical Infra/Security review of mTLS certificate principal extraction and ACL rules.
