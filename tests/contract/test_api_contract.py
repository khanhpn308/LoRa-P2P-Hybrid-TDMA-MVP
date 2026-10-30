#!/usr/bin/env python3
"""Issue #15: REST/OpenAPI and WSS schema conformance (not integration or G4 PASS).

Run: python3 -m unittest discover -s tests/contract -p 'test_*.py' -v
Dependencies: python3 -m pip install -r contracts/tests/requirements.txt
Do NOT interpret contract-level tests as approved AuthN, runtime, RF or real WSS success.
"""
import json
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "contracts" / "api"
FORMAT = FormatChecker()


class ApiContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.openapi = yaml.safe_load((API / "openapi.yaml").read_text(encoding="utf-8"))
        cls.wss_schema = json.loads((API / "schemas" / "realtime-event.schema.json").read_text(encoding="utf-8"))

    def test_openapi_spec_and_protected_operations(self):
        self.assertEqual(self.openapi["openapi"], "3.0.3")
        validate_spec(self.openapi)
        operations = {}
        for path, item in self.openapi["paths"].items():
            for method, op in item.items():
                if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                    continue
                self.assertNotIn(op["operationId"], operations)
                operations[op["operationId"]] = op
                if path not in ("/healthz", "/api/v1/auth/login"):
                    self.assertTrue(op["x-roles"], (path, method))
                    self.assertTrue({"401", "403"}.issubset(op["responses"]), (path, method))
        self.assertEqual(len(operations), 14)
        expected = {
            "schedules_review": "post",
            "schedules_request_activation": "post",
            "nodes_command_get": "get",
        }
        for name in expected:
            self.assertIn(name, operations)
        self.assertEqual(operations["schedules_review"]["x-roles"], ["ADMIN"])
        self.assertEqual(operations["schedules_request_activation"]["x-roles"], ["ADMIN"])
        self.assertEqual(operations["nodes_command_get"]["x-roles"], ["ADMIN", "OPERATOR", "VIEWER"])
        self.assertIn("WWW-Authenticate", self.openapi["components"]["responses"]["Unauthorized"]["headers"])

    def test_post_idempotency_and_async_contract(self):
        paths = self.openapi["paths"]
        for endpoint in (
            "/api/v1/gateways/{gw_id}/nodes/{node_id}/commands",
            "/api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests",
        ):
            op = paths[endpoint]["post"]
            self.assertIn("202", op["responses"])
            refs = [p.get("$ref") for p in op.get("parameters", [])]
            self.assertIn("#/components/parameters/IdempotencyKey", refs)
        self.assertTrue(self.openapi["components"]["parameters"]["IdempotencyKey"]["required"])
        self.assertNotIn("/api/v1/auth/ws-ticket", paths, "D13 auth ticket remains unapproved")

    def test_wss_examples_with_official_json_schema_validator(self):
        Draft202012Validator.check_schema(self.wss_schema)
        casebook = json.loads((API / "examples" / "realtime-cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(casebook["cases"]), 14)
        validator = Draft202012Validator(self.wss_schema, format_checker=FORMAT)
        for case in casebook["cases"]:
            with self.subTest(case=case["id"]):
                errors = list(validator.iter_errors(case["message"]))
                self.assertEqual(not errors, case["valid"],
                                 "; ".join(str(e.message) for e in errors[:3]))
        self.assertIn("COMMAND_STATE_CHANGED", self.wss_schema["properties"]["type"]["enum"])

    def test_rest_component_examples(self):
        casebook = json.loads((API / "examples" / "rest-cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(casebook["cases"]), 16)
        for case in casebook["cases"]:
            with self.subTest(case=case["id"]):
                component = self.openapi["components"]["schemas"][case["schema"]]
                # The selected component schemas have no OpenAPI 3.0 nullable extension.
                validator = Draft202012Validator(component, format_checker=FORMAT)
                errors = list(validator.iter_errors(case["message"]))
                self.assertEqual(not errors, case["valid"],
                                 "; ".join(str(e.message) for e in errors[:3]))

    def test_owner_radio_mac_contract_invariants(self):
        mqtt = ROOT / "contracts" / "mqtt"
        t = json.loads((mqtt / "schemas" / "telemetry.schema.json").read_text(encoding="utf-8"))
        a = json.loads((mqtt / "schemas" / "alert.schema.json").read_text(encoding="utf-8"))
        schedule = json.loads((mqtt / "schemas" / "schedule.schema.json").read_text(encoding="utf-8"))
        for schema in (t, a):
            Draft202012Validator.check_schema(schema)
            self.assertIn("Gateway-origin", schema["properties"]["event_id"]["description"])
            self.assertEqual(schema["properties"]["data"]["required"], ["temp_x10"])
            self.assertEqual(set(schema["properties"]["data"]["properties"]), {"temp_x10"})
            self.assertIn("frame_counter", schema["required"])
            self.assertNotIn("seq_num", schema["properties"])
            self.assertEqual(schema["properties"]["frame_counter"]["maximum"], 4294967295)
        self.assertNotIn("radio_ack_sent", a["required"], "Alert ACK has not been decided")
        self.assertEqual(schedule["properties"]["min_announce_superframes"]["const"], 3)
        self.assertEqual(
            self.openapi["components"]["schemas"]["GenerateScheduleRequest"]
            ["properties"]["min_announce_superframes"]["enum"], [3]
        )
        book = json.loads((mqtt / "examples" / "cases.json").read_text(encoding="utf-8"))
        for case in book["cases"]:
            schema = json.loads(
                (mqtt / "schemas" / (case["schema"] + ".schema.json")).read_text(encoding="utf-8")
            )
            validator = Draft202012Validator(schema, format_checker=FORMAT)
            with self.subTest(mqtt_case=case["id"]):
                errors = list(validator.iter_errors(case["message"]))
                self.assertEqual(not errors, case["valid"],
                                 "; ".join(e.message for e in errors[:3]))

    def test_identity_and_state_invariants_are_explicit(self):
        telemetry_branch = next(
            b for b in self.wss_schema["allOf"]
            if b["if"]["properties"]["type"].get("const") == "TELEMETRY_UPDATE"
        )
        source_id = telemetry_branch["then"]["properties"]["payload"]["properties"]["event_id"]
        self.assertIn("Gateway-origin", source_id["description"])
        self.assertNotIn("pattern", source_id)
        self.assertIn("Gateway", source_id["description"])
        self.assertIn("/api/v1/gateways/{gw_id}/nodes/{node_id}/telemetry", self.openapi["paths"])
        ticket_required = self.openapi["components"]["schemas"]["CommandTicket"]["required"]
        self.assertIn("gateway_id", ticket_required)
        command_branch = next(
            b for b in self.wss_schema["allOf"]
            if b["if"]["properties"]["type"].get("const") == "COMMAND_STATE_CHANGED"
        )
        required = command_branch["then"]["properties"]["payload"]["required"]
        self.assertIn("state_revision", required)
        self.assertIn("command_id", required)
        schedule_state = self.openapi["components"]["schemas"]["ScheduleSummary"]["properties"]["state"]["enum"]
        self.assertEqual(schedule_state, ["PROPOSED", "SENT", "STAGED", "ACTIVE", "REJECTED", "EXPIRED"])


if __name__ == "__main__":
    unittest.main()
