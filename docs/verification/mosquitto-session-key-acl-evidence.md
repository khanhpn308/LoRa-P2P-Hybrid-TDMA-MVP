# Verification Evidence Dossier: Production Mosquitto ACL for Session Key Install & ACK (#228)

> **Authority:** Issue #228, Issue #174 / PR #227 (`docs/verification/session-key-mqtt-integration-evidence.md`), Issue #122 / PR #123 (`contracts/mqtt/session-key-security.md`, `contracts/mqtt/topics.md`), ADR-0002 (`MQTT 5.0`).
> **Target Systems:** Canonical Production Mosquitto ACL (`deploy/mosquitto/acl`), Mosquitto Container Image (`deploy/mosquitto/Dockerfile`), Backend Test Double, Gateway Test Double.
> **Scope:** `deploy/mosquitto/acl`, `tests/integration/`, `docs/verification/`.
> **Status:** `DONE_FOR_REVIEW` (Canonical ACL updated, image build verified, positive and negative MQTT 5.0 transport authorization verified against live Mosquitto 2.0 broker).

---

## 1. Executive Summary & Verification Classification

This dossier provides reproducible verification evidence for the follow-up infrastructure update from Issue #174 (PR #227). In PR #227, `deploy/**` was kept strictly **READ-ONLY**, using a dynamic test mount to prove Session Key broker transport. Issue #228 incorporates the canonical Session Key Install and ACK topics into the tracked production Mosquitto ACL (`deploy/mosquitto/acl`) so that provisioned Gateways (`gw-a`, `gw-b`) and Backend (`backend`) can exchange Session Key control messages in production deployments.

### Verification Classification
- **`BROKER_RUNTIME_VERIFIED`:**
  - Real Mosquitto 2.0 container image built from `deploy/mosquitto/Dockerfile` incorporates `deploy/mosquitto/acl` with ownership `1883:1883` and file mode `0600`.
  - Mosquitto broker starts cleanly with zero syntax, parsing, or directive errors.
  - Positive transport authorization: Backend publishes `downlink/session-key-install` (QoS 1, Message Expiry Interval=300s), Gateway receives and validates; Gateway publishes `uplink/session-key-ack` (QoS 1), Backend receives and validates.
  - Least-privilege negative authorization: Gateway A publishing/subscribing to Gateway B session-key topics rejected with MQTT 5.0 Reason Code 135 (`0x87` Not authorized).
  - Role reversal protection: Gateway publishing to `downlink/session-key-install` denied with PUBACK 135; Backend publishing to `uplink/session-key-ack` denied with PUBACK 135; Backend subscribing to `downlink/session-key-install` denied with SUBACK 135.
- **`CONTRACT_PAYLOAD_VERIFIED`:**
  - Two-layer identity binding verified: Certificate CN to ACL topic authorization at Layer 1; byte-exact topic string vs payload `gateway_id` and RF registry mapping `target_gw_id` checked by independent Layer 2 semantic validator.
  - QoS 1 idempotency, stale revision rejection, expired deadline rejection, and retained message rejection verified.
- **`APP_END_TO_END_NOT_VERIFIED`:**
  - No claim of integrated production Go Backend service process execution, ESP32 firmware binary compilation, NVS flash persistence, or RF HIL transmission (reserved for follow-up hardware integration under #169).

---

## 2. Pinned Toolchains & Artifact Hashes

| Component | Specification / Version | Environment / Identity |
| :--- | :--- | :--- |
| **Mosquitto Image** | `eclipse-mosquitto:2.0` | `sha256:212f89e1eaeb2c322d6441b64396e3346026674db8fa9c27beac293405c32b3c` |
| **Mosquitto Binary** | `mosquitto version 2.0.22` | Running inside container as non-root UID/GID `1883:1883` |
| **Docker Engine** | `29.8.0` / Compose `v5.5.1` | Local WSL2 Ubuntu 24.04 Linux daemon |
| **Host Toolchain** | Python 3.12.3 / OpenSSL 3.0.13 | WSL2 Host test driver (`tests/integration/`) |
| **Base Commit SHA** | `c2fc8da2293ef6ad3b1fb25c2c782145efbbeade` | Tracked `origin/main` baseline (Merge PR #227) |

### Tracked File Hashes (SHA-256)

#### Modified Allowed Paths
- `deploy/mosquitto/acl`: `b06ad6b7492371217f75e1676b507885416b056065544051c19f594ccd4d9296`
- `tests/integration/mqtt_session_key/test_fixtures.py`: `3b0c1b716e26c20a8d074d951864955f1ebada6eb180829fbb0f2e91ad3ebb0c`
- `tests/integration/mqtt_session_key/test_mqtt_session_key_integration.py`: `635d7278b0347e5a8f8b5aafe81b4392e20cfcaff36734660bbf19e152e16cdb`
- `tests/integration/test_local_infra.py`: `f690670e5688d622a8f28403fd9f9fe7eefd46b527e124f3bef35dabcefa5cb5`
- `docs/verification/mosquitto-session-key-acl-evidence.md`: Scoped verification evidence dossier

#### Authority Contracts & Configurations (READ-ONLY)
- `contracts/mqtt/topics.md`: `3d0cc895dbba06648e9c50d27d656042b92bb7f54a2223d9163399770482d264`
- `contracts/mqtt/schemas/session-key-install.schema.json`: `6451d31c761a53ae7764db54f36aad0ada33fdcfeb6f263e697b7e14a001ca14`
- `contracts/mqtt/schemas/session-key-ack.schema.json`: `ffdb5c08ecaa3ea25c36f4faf890b5a08a2558d3acf9a60f69d8bb9b3dbd69e0`
- `contracts/mqtt/session-key-security.md`: `88298faa06c0bce59b4bc28ddd5eabcec5b2bbb224eaeb51a16eda64a3af3794`
- `deploy/mosquitto/Dockerfile`: `11ce3dbe927c3ee1ccfeef8324e4d5885065be9fcfd2b86beba329b3ee92f8dc`
- `deploy/compose.yaml`: `b3e54cbee81d894be1efeaf9503bab597d36c685bbe980668124051f18417a32`

---

## 3. Mosquitto Production ACL Configuration Diff

```diff
--- a/deploy/mosquitto/acl
+++ b/deploy/mosquitto/acl
@@ -8,6 +8,9 @@ topic write iot/v1/gw/gw-a/uplink/schedule-ack
 topic write iot/v1/gw/gw-a/uplink/command-ack
 topic read iot/v1/gw/gw-a/downlink/schedule
 topic read iot/v1/gw/gw-a/downlink/command
+# Session Key Install & ACK
+topic read iot/v1/gw/gw-a/downlink/session-key-install
+topic write iot/v1/gw/gw-a/uplink/session-key-ack
 
 user gw-b
 topic write iot/v1/gw/gw-b/uplink/telemetry
@@ -17,6 +20,9 @@ topic write iot/v1/gw/gw-b/uplink/schedule-ack
 topic write iot/v1/gw/gw-b/uplink/command-ack
 topic read iot/v1/gw/gw-b/downlink/schedule
 topic read iot/v1/gw/gw-b/downlink/command
+# Session Key Install & ACK
+topic read iot/v1/gw/gw-b/downlink/session-key-install
+topic write iot/v1/gw/gw-b/uplink/session-key-ack
 
 user backend
 topic read iot/v1/gw/+/uplink/telemetry
@@ -26,3 +32,6 @@ topic read iot/v1/gw/+/uplink/schedule-ack
 topic read iot/v1/gw/+/uplink/command-ack
 topic write iot/v1/gw/+/downlink/schedule
 topic write iot/v1/gw/+/downlink/command
+# Session Key Install & ACK
+topic write iot/v1/gw/+/downlink/session-key-install
+topic read iot/v1/gw/+/uplink/session-key-ack
```

### Least Privilege & Role Isolation Rules
- **Gateway Principals (`gw-a`, `gw-b`):**
  - Read permission granted only for `iot/v1/gw/{gateway_id}/downlink/session-key-install`.
  - Write permission granted only for `iot/v1/gw/{gateway_id}/uplink/session-key-ack`.
  - Role reversal blocked: Gateway cannot publish to `downlink/session-key-install`.
  - Cross-gateway isolation: Gateway A cannot read or write Gateway B topics.
- **Backend Principal (`backend`):**
  - Write permission granted for `iot/v1/gw/+/downlink/session-key-install`.
  - Read permission granted for `iot/v1/gw/+/uplink/session-key-ack`.
  - Role reversal blocked: Backend cannot publish to `uplink/session-key-ack` or subscribe to `downlink/session-key-install`.

---

## 4. Executed Integration Test Suite Results

### 4.1. Secret Scanner & Static Infra Security Tests

```bash
python3 -m unittest discover -s tests/integration -p "test_verify_no_secrets.py"
```
```text
.......
----------------------------------------------------------------------
Ran 7 tests in 0.536s

OK
```

```bash
python3 -m unittest discover -s tests/integration -p "test_infra_security.py"
```
```text
...........
----------------------------------------------------------------------
Ran 11 tests in 0.014s

OK
```

### 4.2. MQTT Session Key mTLS & ACL Integration Suite

```bash
python3 -m unittest discover -s tests/integration/mqtt_session_key -p "test_mqtt_session_key_integration.py" -v
```
```text
test_00_canonical_acl_structure_and_broker_syntax (test_mqtt_session_key_integration.TestMqttSessionKeyIntegration.test_00_canonical_acl_structure_and_broker_syntax)
Assert deploy/mosquitto/acl contains canonical Session Key topics and broker loaded cleanly. ... ok
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
Ran 7 tests in 14.025s

OK
```

### 4.3. Local Infrastructure Smoke Test Suite (Direct Docker Image Build)

```bash
python3 -m unittest discover -s tests/integration -p "test_local_infra.py"
```
```text
PASS: Compose profiles, loopback-only bindings and dev network isolation
PASS: missing/empty PostgreSQL environment rejected
PASS: broker uid1883, ACL owner1883:1883 mode0600, server-only key mount; no ownership/startup warnings
PASS: each client sees only public CA and its own certificate/key; anonymous sees CA only
PASS: PostgreSQL healthcheck and persistence after container recreation
PASS: separate-network client reaches non-loopback control listener on 192.168.88.113
PASS: postgres reachable via localhost, rejected via non-loopback 192.168.88.113:44639
PASS: mqtt-dev reachable via localhost, rejected via non-loopback 192.168.88.113:44638
PASS: mqtt-tls reachable via localhost, rejected via non-loopback 192.168.88.113:44636
PASS: published TLS port verifies server CA and hostname
PASS: anonymous/no certificate rejected by TLS
PASS: untrusted certificate rejected by TLS
PASS: both Gateways and Backend exchange every allowlisted topic at MQTT5 QoS1
PASS: cross-Gateway writes, ClientID/username spoof, reversed roles, unknown CN and unlisted topic denied with PUBACK 135
PASS: denied receive gw-a on iot/v1/gw/gw-b/downlink/command: MQTT exit27, no payload; Docker process completed in 46.20s
PASS: denied receive gw-b on iot/v1/gw/gw-a/downlink/command: MQTT exit27, no payload; Docker process completed in 46.39s
PASS: denied receive gw-a on iot/v1/gw/#: MQTT exit27, no payload; Docker process completed in 46.51s
PASS: denied receive backend on iot/v1/gw/gw-a/downlink/command: MQTT exit27, no payload; Docker process completed in 46.47s
PASS: cross-Gateway reads, wildcard leakage and Backend downlink reads deliver no messages
----------------------------------------------------------------------
Ran 1 test in 281.467s

OK
```

---

## 5. Security & Isolation Matrix

| Authenticated Certificate CN | Authorized Subscriptions | Authorized Publications | Prohibited Actions (Denied with PUBACK / SUBACK 135) |
| :--- | :--- | :--- | :--- |
| `backend` | `iot/v1/gw/+/uplink/session-key-ack`<br>`iot/v1/gw/+/uplink/*` (telemetry, alert, status, acks) | `iot/v1/gw/+/downlink/session-key-install`<br>`iot/v1/gw/+/downlink/*` (schedule, command) | Publishing to `uplink/*`, subscribing to `downlink/*`. |
| `gw-a` | `iot/v1/gw/gw-a/downlink/session-key-install`<br>`iot/v1/gw/gw-a/downlink/*` (schedule, command) | `iot/v1/gw/gw-a/uplink/session-key-ack`<br>`iot/v1/gw/gw-a/uplink/*` (telemetry, alert, status, acks) | Reading/writing any `gw-b` topic, publishing to `downlink/*`. |
| `gw-b` | `iot/v1/gw/gw-b/downlink/session-key-install`<br>`iot/v1/gw/gw-b/downlink/*` (schedule, command) | `iot/v1/gw/gw-b/uplink/session-key-ack`<br>`iot/v1/gw/gw-b/uplink/*` (telemetry, alert, status, acks) | Reading/writing any `gw-a` topic, publishing to `downlink/*`. |
| `unknown` (valid CA, unknown CN) | None | None | Denied all publishes with `PUBACK 135`; receives zero subscriptions. |
| Anonymous (no cert) | N/A | N/A | TLS handshake aborted: `peer did not return a certificate`. |
| Untrusted CA (`wrong`) | N/A | N/A | TLS handshake aborted: `certificate verify failed`. |

---

## 6. Quality Gate Checklist (G0 - G6)

- [x] **G0 Context Validation:** Tracked `AGENTS.md` SHA-256 validated by Host context runner (`32a991b015bd2815ed55b8bba7bd3b13277003b14f323afb8c5694d047a5942e`).
- [x] **G1 Branch/Scope Check:** Isolated worktree on `feature/228-mosquitto-session-key-acl`. Edits strictly confined to allowed paths (`deploy/mosquitto/acl`, `tests/integration/`, `docs/verification/`).
- [x] **G2 Standards Compliance:** Infra and Python test modifications conform to zero-secret, least-privilege, and fail-closed security standards.
- [x] **G3 Secret Scan:** `test_verify_no_secrets.py` passed with 0 findings; no credentials or certificates tracked.
- [x] **G4 Integration Test Pass:** Real Mosquitto mTLS test suite (`test_mqtt_session_key_integration.py`) and local infra suite (`test_local_infra.py`) both passed 100%.
- [x] **G5 Evidence Dossier:** Complete report recorded with test commands, logs, and SHA-256 digests.
- [x] **G6 Human Review:** PR prepared for technical review and merge.
