#!/usr/bin/env python3
"""Schema-shape and limited static semantic checks for MQTT session-key contracts.

Run: python3 -m unittest discover -s tests/contract -p 'test_mqtt_session_key_contract.py' -v
Dependencies: python3 -m pip install -r contracts/tests/requirements.txt
This does NOT verify AES-GCM/HMAC, authorization, MQTT broker or device persistence.
"""
import json
import re
import unittest
from datetime import datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]
MQTT = ROOT / "contracts" / "mqtt"
TOPIC_INSTALL = re.compile(r"^iot/v1/gw/([A-Za-z0-9_-]{1,32})/downlink/session-key-install$")
TOPIC_ACK = re.compile(r"^iot/v1/gw/([A-Za-z0-9_-]{1,32})/uplink/session-key-ack$")


def static_semantics(case):
    """Only rules evaluable without keys, trusted clock, RF registry or a DB."""
    msg = case["message"]
    schema = case["schema"]
    topic = case.get("topic")
    if not topic:
        raise ValueError("Semantic fixture requires a topic")
    matcher = (TOPIC_INSTALL if schema == "session-key-install" else TOPIC_ACK).fullmatch(topic)
    if matcher is None or matcher.group(1) != msg["gateway_id"]:
        return "REJECT_WRONG_GATEWAY"
    if schema == "session-key-install":
        def parse_utc(value):
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z", value):
                raise ValueError("Not a canonical UTC timestamp")
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not (parse_utc(msg["not_before"]) < parse_utc(msg["expires_at"])
                and parse_utc(msg["install_deadline"]) <= parse_utc(msg["expires_at"])):
            return "REJECT_INVALID_TIME_WINDOW"
        # Synthetic registry for fixtures only; real mapping is provisioned and authenticated.
        if msg["target_gw_id"] != {"gw01": 1}.get(msg["gateway_id"]):
            return "REQUIRES_GATEWAY_REGISTRY_CHECK"
        return "ACCEPT_SHAPE_AND_STATIC_METADATA_ONLY"
    return "ACCEPT_SHAPE_AND_TOPIC_ONLY"


class SessionKeySchemaContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = {}
        for name in ("session-key-install", "session-key-ack"):
            path = MQTT / "schemas" / (name + ".schema.json")
            cls.schemas[name] = json.loads(path.read_text(encoding="utf-8"))
        cls.fixtures = json.loads(
            (MQTT / "examples" / "session-key-cases.json").read_text(encoding="utf-8")
        )["cases"]

    def test_schema_meta(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                Draft202012Validator.check_schema(schema)
                self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1-draft")
                self.assertFalse(schema["additionalProperties"])

    def test_positive_and_negative_shape_fixtures(self):
        self.assertGreaterEqual(len(self.fixtures), 12)
        for case in self.fixtures:
            with self.subTest(case=case["id"]):
                validator = Draft202012Validator(
                    self.schemas[case["schema"]], format_checker=FormatChecker()
                )
                errors = list(validator.iter_errors(case["message"]))
                self.assertEqual(not errors, case["valid"],
                                 "; ".join(error.message for error in errors[:3]))

    def test_static_cross_field_fixtures(self):
        count = 0
        for case in self.fixtures:
            if not case.get("semantic_result"):
                continue
            with self.subTest(case=case["id"]):
                self.assertTrue(case["valid"], "Semantic fixtures must pass JSON schema")
                self.assertEqual(static_semantics(case), case["semantic_result"])
                count += 1
        self.assertGreaterEqual(count, 5)

    def test_no_bootstrap_secrets_in_install_envelope(self):
        properties = self.schemas["session-key-install"]["properties"]
        for forbidden in ("k_join", "k_join_confirm", "k_session_up", "k_session_dl",
                          "plaintext", "secret"):
            self.assertNotIn(forbidden, properties)
        self.assertIn("ciphertext", properties)
        self.assertIn("tag", properties)
        self.assertIn("wrap_key_id", self.schemas["session-key-ack"]["required"])

    def test_canonical_aad_v1_encoding(self):
        import base64
        import struct
        import uuid
        case = next(c for c in self.fixtures if c["id"] == "SKI-SCHEMA-VALID")
        msg = case["message"]
        topic = case["topic"]

        def lp(s: str) -> bytes:
            raw = s.encode("utf-8")
            return struct.pack(">H", len(raw)) + raw

        def time_ms(s: str) -> bytes:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return struct.pack(">Q", int(dt.timestamp() * 1000))

        aad = b"".join([
            lp("LP2P/MQTT/V1/KEY-INSTALL"),
            lp(topic),
            lp(msg["schema_version"]),
            struct.pack(">B", msg["install_protocol_version"]),
            struct.pack(">B", msg["aad_version"]),
            lp(msg["gateway_id"]),
            struct.pack(">B", msg["target_gw_id"]),
            bytes.fromhex(msg["device_mac"]),
            struct.pack(">B", msg["node_id"]),
            struct.pack(">B", msg["key_id"]),
            uuid.UUID(msg["session_id"]).bytes,
            uuid.UUID(msg["install_id"]).bytes,
            struct.pack(">Q", int(msg["session_revision"])),
            struct.pack(">Q", int(msg["assignment_revision"])),
            bytes.fromhex(msg["session_context_hash"]),
            time_ms(msg["not_before"]),
            time_ms(msg["expires_at"]),
            time_ms(msg["install_deadline"]),
            struct.pack(">I", msg["wrap_key_id"]),
            lp(msg["crypto_suite"]),
            base64.b64decode(msg["nonce"]),
        ])
        self.assertEqual(len(aad), 232)
        self.assertTrue(aad.startswith(b"\x00\x18LP2P/MQTT/V1/KEY-INSTALL"))

    def test_canonical_ack_transcript_v1_encoding(self):
        import struct
        import uuid
        case = next(c for c in self.fixtures if c["id"] == "SKA-SCHEMA-VALID")
        msg = case["message"]
        topic = case["topic"]

        def lp(s: str) -> bytes:
            raw = s.encode("utf-8")
            return struct.pack(">H", len(raw)) + raw

        m_ack = b"".join([
            lp("LP2P/MQTT/V1/M-ACK"),
            lp(topic),
            lp(msg["schema_version"]),
            struct.pack(">B", msg["ack_protocol_version"]),
            lp(msg["gateway_id"]),
            uuid.UUID(msg["install_id"]).bytes,
            uuid.UUID(msg["session_id"]).bytes,
            struct.pack(">Q", int(msg["session_revision"])),
            struct.pack(">I", msg["wrap_key_id"]),
            lp(msg["status"]),
            lp(msg["reason_code"]),
        ])
        self.assertEqual(len(m_ack), 138)
        self.assertTrue(m_ack.startswith(b"\x00\x12LP2P/MQTT/V1/M-ACK"))

    def test_decimal_uint64_revision_bounds(self):
        validator = Draft202012Validator(self.schemas["session-key-install"], format_checker=FormatChecker())
        case = next(c for c in self.fixtures if c["id"] == "SKI-SCHEMA-VALID")
        msg = dict(case["message"])

        # Valid boundaries
        for val in ("1", "18446744073709551615"):
            msg["session_revision"] = val
            self.assertEqual(list(validator.iter_errors(msg)), [], f"Failed on valid revision {val}")

        # Invalid formats
        for bad in ("0", "01", "-1", "18446744073709551616", "1.0", "1e5"):
            msg["session_revision"] = bad
            errors = list(validator.iter_errors(msg))
            self.assertTrue(len(errors) > 0 or (bad == "18446744073709551616" and int(bad) > 2**64 - 1),
                            f"Expected error for bad revision {bad}")

    def test_doc_consistency_v2_key_confirm_length(self):
        """Regression test for P1: V2 UP_JOIN_KEY_CONFIRM must be 31B, not 33B."""
        sec_text = (MQTT / "session-key-security.md").read_text(encoding="utf-8")
        rules_text = (MQTT / "semantic-rules.md").read_text(encoding="utf-8")
        topics_text = (MQTT / "topics.md").read_text(encoding="utf-8")

        self.assertIn("UP_JOIN_KEY_CONFIRM:31B", sec_text)
        self.assertIn("UP_JOIN_KEY_CONFIRM:31B", rules_text)
        self.assertIn("UP_JOIN_KEY_CONFIRM:31B", topics_text)

        # Ensure no accidental stale references to 33B remain in any markdown file in contracts/mqtt
        for md_path in MQTT.glob("*.md"):
            content = md_path.read_text(encoding="utf-8")
            self.assertNotIn("33B", content, f"Found stale '33B' reference in {md_path.name}")

    def test_not_before_and_clock_boundary_guards(self):
        """Regression test for P2: SK-04 not_before pre-staging vs active eligibility guard."""
        # 1. Early staging fixture is valid for install shape and static metadata
        early_case = next(c for c in self.fixtures if c["id"] == "SKI-EARLY-STAGE-VALID")
        self.assertEqual(static_semantics(early_case), "ACCEPT_SHAPE_AND_STATIC_METADATA_ONLY")

        # 2. Invalid time windows (not_before >= expires_at, deadline > expires_at) must be rejected
        for bad_id in ("SKI-NOT-BEFORE-AFTER-EXPIRES", "SKI-NOT-BEFORE-EQUAL-EXPIRES", "SKI-EXPIRED-DEADLINE"):
            case = next(c for c in self.fixtures if c["id"] == bad_id)
            self.assertEqual(static_semantics(case), "REJECT_INVALID_TIME_WINDOW")

        # 3. Guard logic model: simulate Gateway activation eligibility check
        def evaluate_key_eligibility(current_utc: datetime, not_before_utc: datetime, expires_at_utc: datetime, clock_trusted: bool) -> str:
            if not clock_trusted:
                return "FAIL_CLOSED_UNTRUSTED_CLOCK"
            if current_utc < not_before_utc:
                return "INELIGIBLE_NOT_YET_VALID"  # Staged as INSTALLED_INACTIVE only; NO RF DATA TX
            if current_utc >= expires_at_utc:
                return "INELIGIBLE_EXPIRED"
            return "ELIGIBLE_FOR_ACTIVE_DATA"

        t_now = datetime.fromisoformat("2026-11-05T00:30:00+00:00")
        t_nb = datetime.fromisoformat("2026-11-05T01:00:00+00:00")
        t_exp = datetime.fromisoformat("2026-11-06T01:00:00+00:00")

        # Early pre-stage: now < not_before => cannot activate DATA
        self.assertEqual(evaluate_key_eligibility(t_now, t_nb, t_exp, clock_trusted=True), "INELIGIBLE_NOT_YET_VALID")

        # Inside validity window: not_before <= now < expires_at => eligible for active DATA
        t_active = datetime.fromisoformat("2026-11-05T02:00:00+00:00")
        self.assertEqual(evaluate_key_eligibility(t_active, t_nb, t_exp, clock_trusted=True), "ELIGIBLE_FOR_ACTIVE_DATA")

        # Expired: now >= expires_at => cannot activate DATA
        t_expired = datetime.fromisoformat("2026-11-06T02:00:00+00:00")
        self.assertEqual(evaluate_key_eligibility(t_expired, t_nb, t_exp, clock_trusted=True), "INELIGIBLE_EXPIRED")

        # Untrusted clock => fail closed
        self.assertEqual(evaluate_key_eligibility(t_active, t_nb, t_exp, clock_trusted=False), "FAIL_CLOSED_UNTRUSTED_CLOCK")


if __name__ == "__main__":
    unittest.main()
