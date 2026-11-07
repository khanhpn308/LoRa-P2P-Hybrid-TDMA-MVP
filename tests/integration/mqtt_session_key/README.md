# Real Mosquitto mTLS Session Key Integration Tests

> **Authority:** Issue #174, #122 / PR #123 (`contracts/mqtt/session-key-security.md`, `contracts/mqtt/topics.md`), ADR-0002.
> **Scope:** `tests/integration/mqtt_session_key/`
> **Status:** `BROKER_RUNTIME_VERIFIED` / `CONTRACT_PAYLOAD_VERIFIED` / `APP_END_TO_END_NOT_VERIFIED`.

---

## 1. Purpose and Architecture

This test suite verifies real Mosquitto MQTT 5.0 broker behavior over mutual TLS (mTLS) for the versioned Session Key Install/ACK topics:
- `downlink/session-key-install`: `iot/v1/gw/{gateway_id}/downlink/session-key-install` (QoS 1, Message Expiry Interval, Retain=false)
- `uplink/session-key-ack`: `iot/v1/gw/{gateway_id}/uplink/session-key-ack` (QoS 1, Retain=false)

### Two-Layer Identity Binding Architecture
1. **Layer 1: Broker mTLS & Topic ACL:**
   - Broker verifies client certificate against test CA (`require_certificate true`).
   - Broker sets authenticated username from certificate Subject CN (`use_identity_as_username true`).
   - Broker enforces per-Gateway ACL: Gateway `gw-a` can only subscribe to `downlink/session-key-install` for `gw-a` and publish `uplink/session-key-ack` for `gw-a`. Cross-Gateway access is denied with MQTT 5.0 PUBACK Reason Code 135 (`0x87` Not authorized).
2. **Layer 2: Application Semantic Validation:**
   - Evaluates whether the payload `gateway_id` matches the subscribed topic and authenticated principal identity.
   - Evaluates whether the numeric RF code `target_gw_id` matches the provisioned registry for the Gateway identity.
   - Validates time windows, expiry deadlines (`install_deadline <= expires_at`), idempotency of duplicate QoS 1 deliveries, and monotonicity of `session_revision`.

---

## 2. Test Execution

From the repository root:

```bash
python3 -m unittest discover -s tests/integration/mqtt_session_key -p "test_mqtt_session_key_integration.py" -v
```

### Prerequisites
- Docker Engine with Compose (`eclipse-mosquitto:2.0` image).
- OpenSSL (used to generate ephemeral 1-day certificates under gitignored `tests/integration/secrets/`).
- Python 3.10+ standard library.

---

## 3. Test Cases Overview

| Test Name | Verification Focus | Expected Outcome |
| :--- | :--- | :--- |
| `test_01_tls_mutual_authentication_and_rejection` | Broker mTLS handshakes | Authorized CNs (`backend`, `gw-a`, `gw-b`) connect; anonymous and untrusted certs rejected by TLS; unknown CN denied publish by ACL (PUBACK 135). |
| `test_02_positive_session_key_install_and_ack_flow` | End-to-end positive flow | Backend publishes install at QoS 1; Gateway receives, validates payload, and replies with ACK; Backend receives ACK at QoS 1. |
| `test_03_negative_broker_acl_cross_gateway_denials` | Per-Gateway ACL isolation | Gateway A cross-writes, role reversals, unlisted topics, and ClientID spoofing rejected with PUBACK 135. Cross-subscribing delivers no messages. |
| `test_04_cross_layer_identity_binding_and_spoofing` | Layer 2 semantic checks | Broker transports topic-allowed messages, but application validator rejects forged payload `gateway_id`, RF `target_gw_id` mismatch, and ACK mismatch. |
| `test_05_resilience_and_qos1_delivery` | Protocol resilience | Duplicate delivery accepted idempotently; stale session revision rejected; expired deadline rejected; retained message rejected; Clean Start reconnect verified. |
| `test_06_provenance_and_clean_audit` | Security & clean audit | Asserts real `eclipse-mosquitto:2.0` image ID; verifies no private key material leaked into broker logs. |

---

## 4. Evidence Boundaries

- **`BROKER_RUNTIME_VERIFIED`:** Real Mosquitto 2.0 broker executed with mTLS and per-principal ACL. Positive and negative transport flows verified.
- **`CONTRACT_PAYLOAD_VERIFIED`:** Two-layer identity binding, time windows, and idempotency verified using reviewed contract schema (`1.1-draft`).
- **`APP_END_TO_END_NOT_VERIFIED`:** Test doubles are used for Gateway and Backend clients. No claim is made of integrated production Go Backend services, ESP32 firmware binary execution, or hardware flash persistence (reserved for follow-up HIL and end-to-end issues).
