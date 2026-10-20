#!/usr/bin/env python3
"""Validate proposed contracts. Schema PASS is not RF/MQTT/HTTP integration PASS."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate_spec

ROOT = Path(__file__).resolve().parents[1]
FORMAT = FormatChecker()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def validate_examples(directory: str, fixture_name: str, schema_folder: str) -> int:
    fixture = read_json(ROOT / directory / "examples" / fixture_name)
    tested = 0
    for case in fixture["cases"]:
        schema_path = ROOT / directory / "schemas" / (
            "realtime-event.schema.json" if directory == "api"
            else case["schema"] + ".schema.json"
        )
        schema = read_json(schema_path)
        Draft202012Validator.check_schema(schema)
        problems = list(Draft202012Validator(schema, format_checker=FORMAT).iter_errors(case["message"]))
        actual_valid = not problems
        expected_valid = case["valid"]
        if actual_valid != expected_valid:
            detail = "; ".join(str(p.message) for p in problems[:3])
            raise AssertionError(
                f"{case['id']}: expected JSON Schema valid={expected_valid}, "
                f"got {actual_valid}; errors={detail}"
            )
        if "semantic_result" in case:
            assert directory == "mqtt" and case["schema"] == "schedule"
            assert actual_valid, "Semantic fixture must be syntactically/schema valid"
            result = validate_schedule_slots(case["message"])
            assert result == case["semantic_result"], (case["id"], result)
        print(f"PASS {case['id']} (schema={actual_valid})")
        tested += 1
    return tested


def validate_schedule_slots(schedule: dict) -> str:
    """Candidate P-10S-15 semantic checks beyond JSON Schema (not full G2 validation)."""
    if schedule["profile_id"] != "P-10S-15":
        return "REJECT_UNSUPPORTED_PROFILE"
    owners = [item["node_id"] for item in schedule["slots"]]
    slots = [item["slot_id"] for item in schedule["slots"]]
    if len(set(owners)) != len(owners) or len(set(slots)) != len(slots):
        return "REJECT_OVERLAPPING_SLOT"
    for item in schedule["slots"]:
        slot = item["slot_id"]
        expected_offset = 2000 * ((slot - 1) // 3) + 650 + 400 * ((slot - 1) % 3)
        if item["offset_ms"] != expected_offset or item["duration_ms"] != 400:
            return "REJECT_OVERLAPPING_SLOT"
    return "ACCEPT_CANDIDATE_GEOMETRY_ONLY"


def validate_openapi() -> int:
    file = ROOT / "api" / "openapi.yaml"
    with file.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    if document.get("openapi") != "3.0.3":
        raise AssertionError("Unexpected OpenAPI version")
    validate_spec(document)
    count = 0
    for path, item in document["paths"].items():
        for method, op in item.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if path not in ("/healthz", "/api/v1/auth/login"):
                assert "x-roles" in op and op["x-roles"], (path, method)
                assert {"401", "403"}.issubset(op["responses"]), (path, method)
            count += 1
    print(f"PASS OpenAPI semantic spec + {count} HTTP operations")
    return count


def main() -> None:
    paths = sorted((ROOT / "mqtt" / "schemas").glob("*.schema.json"))
    paths += sorted((ROOT / "api" / "schemas").glob("*.schema.json"))
    for path in paths:
        Draft202012Validator.check_schema(read_json(path))
    num_mqtt = validate_examples("mqtt", "cases.json", "schemas")
    num_ws = validate_examples("api", "realtime-cases.json", "schemas")
    num_http = validate_openapi()
    print(f"PASS: {len(paths)} schemas, {num_mqtt} MQTT cases, "
          f"{num_ws} WS cases, {num_http} REST operations")
    print("NOT VERIFIED: device/auth/nonce/timing/RF, MQTT roundtrip, HTTP/WSS implementation.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"CONTRACT VALIDATION FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
