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
        expected_operation_ids = {
            "alerts_acknowledge",
            "alerts_list",
            "audit_list",
            "auth_login",
            "channels_get_assignment",
            "channels_list",
            "channels_release",
            "channels_request",
            "devices_provision",
            "gateways_status",
            "health_liveness",
            "nodes_command",
            "nodes_command_get",
            "nodes_list",
            "nodes_telemetry",
        }
        self.assertEqual(set(operations.keys()), expected_operation_ids)
        self.assertEqual(len(operations), 15)

        # Removed TDMA schedule endpoints must remain absent per ADR-0004
        removed_schedule_endpoints = (
            "/api/v1/gateways/{gw_id}/schedules/generate",
            "/api/v1/gateways/{gw_id}/schedules/{schedule_id}",
            "/api/v1/gateways/{gw_id}/schedules/{schedule_id}/review",
            "/api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests",
        )
        for endpoint in removed_schedule_endpoints:
            self.assertNotIn(
                endpoint,
                self.openapi["paths"],
                f"Superseded TDMA endpoint must remain absent: {endpoint}",
            )
        self.assertNotIn("schedules_review", operations)
        self.assertNotIn("schedules_request_activation", operations)
        self.assertNotIn("schedules_generate", operations)
        self.assertNotIn("schedules_get", operations)

        expected = {
            "nodes_command_get": "get",
            "channels_list": "get",
            "channels_request": "post",
            "channels_get_assignment": "get",
            "channels_release": "delete",
        }
        for name in expected:
            self.assertIn(name, operations)
        self.assertEqual(operations["nodes_command_get"]["x-roles"], ["ADMIN", "OPERATOR", "VIEWER"])
        self.assertEqual(operations["channels_list"]["x-roles"], ["ADMIN", "OPERATOR", "VIEWER"])
        self.assertEqual(operations["channels_request"]["x-roles"], ["ADMIN", "OPERATOR"])
        self.assertEqual(operations["channels_get_assignment"]["x-roles"], ["ADMIN", "OPERATOR", "VIEWER"])
        self.assertEqual(operations["channels_release"]["x-roles"], ["ADMIN"])
        self.assertIn("WWW-Authenticate", self.openapi["components"]["responses"]["Unauthorized"]["headers"])
        telemetry_get = self.openapi["paths"]["/api/v1/nodes/{node_id}/telemetry"]["get"]
        self.assertTrue(telemetry_get.get("deprecated"), "Legacy telemetry must be marked deprecated")

    def test_post_idempotency_and_async_contract(self):
        paths = self.openapi["paths"]
        for endpoint in (
            "/api/v1/nodes/{node_id}/commands",
        ):
            op = paths[endpoint]["post"]
            self.assertIn("202", op["responses"])
            refs = [p.get("$ref") for p in op.get("parameters", [])]
            self.assertIn("#/components/parameters/IdempotencyKey", refs)
        self.assertNotIn(
            "/api/v1/gateways/{gw_id}/schedules/{schedule_id}/activation-requests",
            paths,
            "Superseded TDMA schedule activation endpoint must remain absent per ADR-0004",
        )
        # Channel request requires IdempotencyKey and returns 201
        channel_op = paths["/api/v1/gateways/{gw_id}/channels/request"]["post"]
        self.assertIn("201", channel_op["responses"])
        channel_refs = [p.get("$ref") for p in channel_op.get("parameters", [])]
        self.assertIn("#/components/parameters/IdempotencyKey", channel_refs)
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
        self.assertGreaterEqual(len(casebook["cases"]), 24)
        for case in casebook["cases"]:
            with self.subTest(case=case["id"]):
                component = self.openapi["components"]["schemas"][case["schema"]]
                # The selected component schemas have no OpenAPI 3.0 nullable extension.
                validator = Draft202012Validator(component, format_checker=FORMAT)
                errors = list(validator.iter_errors(case["message"]))
                self.assertEqual(not errors, case["valid"],
                                 "; ".join(str(e.message) for e in errors[:3]))

    def test_identity_and_state_invariants_are_explicit(self):
        telemetry_branch = next(
            b for b in self.wss_schema["allOf"]
            if b["if"]["properties"]["type"].get("const") == "TELEMETRY_UPDATE"
        )
        source_id = telemetry_branch["then"]["properties"]["payload"]["properties"]["event_id"]
        self.assertIn("pattern", source_id)
        self.assertIn("gateway_epoch", source_id["description"])
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
