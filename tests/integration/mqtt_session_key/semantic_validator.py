"""Application-level semantic validator for MQTT Session Key contracts.
Enforces Layer-2 identity binding, time windows, monotonicity, idempotency, and cryptographic integrity.
Authority: contracts/mqtt/session-key-security.md, contracts/mqtt/topics.md, Issue #174.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Dict, Any, Optional, Tuple, Set


TOPIC_INSTALL = re.compile(r"^iot/v1/gw/([A-Za-z0-9_-]{1,32})/downlink/session-key-install$")
TOPIC_ACK = re.compile(r"^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/session-key-ack$")
HEX_MAC = re.compile(r"^[0-9a-f]{12}$")
CANONICAL_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DECIMAL_UINT64 = re.compile(r"^(?:0|[1-9][0-9]{0,19})$")

# Known provisioned Gateway string ID <-> numeric RF code mapping
PROVISIONED_GATEWAY_REGISTRY = {
    "gw-a": 1,
    "gw-b": 2,
    "gw01": 1,
}

VALID_ACK_STATUS = {"INSTALLED", "REJECTED"}
VALID_ACK_REASONS = {
    "NONE",
    "ERR_DECRYPT_FAIL",
    "ERR_VERSION_MISMATCH",
    "ERR_EXPIRED",
    "ERR_IDEMPOTENCY_CONFLICT",
    "ERR_STORAGE_FAIL",
}


def parse_utc_timestamp(ts: str) -> datetime:
    """Parse strict ISO 8601 UTC timestamp."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z", ts):
        raise ValueError(f"Non-canonical UTC timestamp format: {ts}")
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class SessionKeySemanticValidator:
    """Application-level semantic handler maintaining state for duplicate/reorder tracking."""

    def __init__(self, expected_principal: Optional[str] = None):
        self.expected_principal = expected_principal
        # (gateway_id, install_id) -> payload_hash (for idempotency tracking)
        self._processed_installs: Dict[Tuple[str, str], str] = {}
        # (gateway_id, session_id) -> highest seen session_revision uint64
        self._session_revisions: Dict[Tuple[str, str], int] = {}

    def validate_install(
        self,
        topic: str,
        payload_bytes: bytes,
        retained: bool = False,
        current_time: Optional[datetime] = None,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Validate an incoming downlink/session-key-install message."""
        if retained:
            return False, "REJECT_UNAUTHORIZED_RETAINED_MESSAGE", None

        # 1. Parse JSON
        try:
            msg = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"MALFORMED_JSON: {e}", None

        # 2. Check Topic vs Payload Identity Binding (Layer 2)
        matcher = TOPIC_INSTALL.fullmatch(topic)
        if not matcher:
            return False, "MALFORMED_TOPIC", msg
        topic_gw_id = matcher.group(1)

        payload_gw_id = msg.get("gateway_id")
        if topic_gw_id != payload_gw_id:
            return False, f"REJECT_WRONG_GATEWAY: topic={topic_gw_id} payload={payload_gw_id}", msg

        if self.expected_principal and self.expected_principal != payload_gw_id:
            return False, f"REJECT_PRINCIPAL_MISMATCH: expected={self.expected_principal} actual={payload_gw_id}", msg

        # 3. Check schema version and protocol constants
        if msg.get("schema_version") != "1.1-draft":
            return False, "REJECT_UNSUPPORTED_SCHEMA_VERSION", msg
        if msg.get("install_protocol_version") != 1 or msg.get("aad_version") != 1:
            return False, "REJECT_UNSUPPORTED_PROTOCOL_VERSION", msg

        # 4. Check Target RF Gateway ID binding against Registry
        target_gw_id = msg.get("target_gw_id")
        expected_rf_id = PROVISIONED_GATEWAY_REGISTRY.get(payload_gw_id)
        if expected_rf_id is None or target_gw_id != expected_rf_id:
            return False, f"REQUIRES_GATEWAY_REGISTRY_CHECK: gw={payload_gw_id} expected_rf={expected_rf_id} got={target_gw_id}", msg

        # 5. Field formats
        dev_mac = msg.get("device_mac", "")
        if not HEX_MAC.fullmatch(dev_mac):
            return False, "REJECT_INVALID_DEVICE_MAC", msg

        for id_field in ("session_id", "install_id"):
            val = msg.get(id_field, "")
            if not CANONICAL_UUID.fullmatch(val):
                return False, f"REJECT_INVALID_UUID_{id_field}", msg

        rev_str = msg.get("session_revision", "")
        if not DECIMAL_UINT64.fullmatch(rev_str) or int(rev_str) > 18446744073709551615 or int(rev_str) < 1:
            return False, "REJECT_INVALID_SESSION_REVISION", msg
        revision_int = int(rev_str)

        # 6. Time windows & Expiry
        try:
            nb = parse_utc_timestamp(msg["not_before"])
            exp = parse_utc_timestamp(msg["expires_at"])
            deadline = parse_utc_timestamp(msg["install_deadline"])
        except Exception as e:
            return False, f"REJECT_INVALID_TIME_FORMAT: {e}", msg

        if not (nb < exp and deadline <= exp):
            return False, "REJECT_INVALID_TIME_WINDOW", msg

        now = current_time or datetime.now(timezone.utc)
        if now > deadline:
            return False, "REJECT_EXPIRED_INSTALL_DEADLINE", msg

        # 7. Base64 decoded lengths
        try:
            nonce_b = base64.b64decode(msg["nonce"], validate=True)
            ct_b = base64.b64decode(msg["ciphertext"], validate=True)
            tag_b = base64.b64decode(msg["tag"], validate=True)
        except Exception as e:
            return False, f"REJECT_INVALID_BASE64: {e}", msg

        if len(nonce_b) != 12:
            return False, f"REJECT_INVALID_NONCE_LENGTH_{len(nonce_b)}", msg
        if len(ct_b) != 64:
            return False, f"REJECT_INVALID_CIPHERTEXT_LENGTH_{len(ct_b)}", msg
        if len(tag_b) != 16:
            return False, f"REJECT_INVALID_TAG_LENGTH_{len(tag_b)}", msg

        # 8. Idempotency and Monotonicity
        key_install = (payload_gw_id, msg["install_id"])
        payload_hash = hashlib.sha256(payload_bytes).hexdigest()

        if key_install in self._processed_installs:
            if self._processed_installs[key_install] == payload_hash:
                return True, "DUPLICATE_IDEMPOTENT_ACCEPT", msg
            else:
                return False, "REJECT_IDEMPOTENCY_CONFLICT_PAYLOAD_ALTERED", msg

        key_session = (payload_gw_id, msg["session_id"])
        last_rev = self._session_revisions.get(key_session, 0)
        if revision_int <= last_rev:
            return False, f"REJECT_STALE_SESSION_REVISION: current={revision_int} last={last_rev}", msg

        # Accept
        self._processed_installs[key_install] = payload_hash
        self._session_revisions[key_session] = revision_int
        return True, "ACCEPT_SESSION_KEY_INSTALL", msg

    def validate_ack(
        self,
        topic: str,
        payload_bytes: bytes,
        retained: bool = False,
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Validate an incoming uplink/session-key-ack message at Backend."""
        if retained:
            return False, "REJECT_UNAUTHORIZED_RETAINED_MESSAGE", None

        try:
            msg = json.loads(payload_bytes.decode("utf-8"))
        except Exception as e:
            return False, f"MALFORMED_JSON: {e}", None

        matcher = TOPIC_ACK.fullmatch(topic)
        if not matcher:
            return False, "MALFORMED_TOPIC", msg
        topic_gw_id = matcher.group(1)

        payload_gw_id = msg.get("gateway_id")
        if topic_gw_id != payload_gw_id:
            return False, f"REJECT_WRONG_GATEWAY: topic={topic_gw_id} payload={payload_gw_id}", msg

        if msg.get("schema_version") != "1.1-draft" or msg.get("ack_protocol_version") != 1:
            return False, "REJECT_UNSUPPORTED_ACK_VERSION", msg

        status = msg.get("status")
        if status not in VALID_ACK_STATUS:
            return False, f"REJECT_INVALID_STATUS_{status}", msg

        reason = msg.get("reason_code")
        if reason not in VALID_ACK_REASONS:
            return False, f"REJECT_INVALID_REASON_{reason}", msg

        if status == "INSTALLED" and reason != "NONE":
            return False, "REJECT_INSTALLED_STATUS_WITH_NON_NONE_REASON", msg

        if status == "REJECTED" and reason == "NONE":
            return False, "REJECT_REJECTED_STATUS_WITH_NONE_REASON", msg

        try:
            ack_tag = base64.b64decode(msg.get("ack_tag", ""), validate=True)
            if len(ack_tag) != 16:
                return False, f"REJECT_INVALID_ACK_TAG_LENGTH_{len(ack_tag)}", msg
        except Exception as e:
            return False, f"REJECT_INVALID_BASE64_ACK_TAG: {e}", msg

        return True, "ACCEPT_SESSION_KEY_ACK", msg
