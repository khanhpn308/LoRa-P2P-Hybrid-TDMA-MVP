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


if __name__ == "__main__":
    unittest.main()
