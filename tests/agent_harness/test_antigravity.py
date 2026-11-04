"""Mock-envelope tests; do not make billable requests to AGY."""
import json
import pathlib
import sys
import unittest
import subprocess
import tempfile
import copy
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from adapters.antigravity import AuditError, check_report, parse_result, invoke, scoped_schema

PATHS = {"firmware/components/sx1276_driver/sx1276.c"}


def envelope(report, status="SUCCESS"):
    return json.dumps({"status": status, "structured_output": report})


def good():
    return {"status": "PASS", "findings": [], "limitations": [],
            "reviewed_scope": sorted(PATHS)}


class AntigravityTests(unittest.TestCase):
    def test_valid_complete_audit(self):
        self.assertEqual(parse_result(0, envelope(good()), "", PATHS)["status"], "PASS")

    def test_soft_denial_even_with_exit_zero(self):
        with self.assertRaises(AuditError):
            parse_result(0, envelope(good()), "tool run_command permission denied", PATHS)

    def test_status_error_even_with_exit_zero(self):
        with self.assertRaises(AuditError):
            parse_result(0, envelope(good(), "WAITING"), "", PATHS)

    def test_exit_nonzero(self):
        with self.assertRaises(AuditError):
            parse_result(2, envelope(good()), "", PATHS)

    def test_legacy_response_instead_of_structured_output(self):
        with self.assertRaises(AuditError):
            parse_result(0, json.dumps({"status": "SUCCESS", "response": json.dumps(good())}), "", PATHS)

    def test_missing_changed_file_review(self):
        report = good()
        report["reviewed_scope"] = []
        with self.assertRaises(AuditError):
            check_report(report, PATHS)

    def test_pass_cannot_carry_findings(self):
        report = good()
        report["findings"] = [{"severity": "HIGH", "file": next(iter(PATHS)),
                               "line": 1, "rule": "MEM-1",
                               "explanation": "out of bounds", "fix": "bound the copy"}]
        with self.assertRaises(AuditError):
            check_report(report, PATHS)

    def test_malformed_json(self):
        with self.assertRaises(AuditError):
            parse_result(0, "{", "", PATHS)

    def test_fail_review_preserved(self):
        report = good()
        report["status"] = "FAIL"
        report["findings"] = [{"severity": "HIGH", "file": next(iter(PATHS)),
                               "line": 1, "rule": "RAD-1",
                               "explanation": "incorrect IRQ mapping", "fix": "follow datasheet"}]
        self.assertEqual(parse_result(0, envelope(report), "", PATHS)["status"], "FAIL")


class StrictAuditContractTests(unittest.TestCase):
    """Regression for Issue #43, synthetic inputs only (no provider calls)."""

    @staticmethod
    def _finding():
        return {"severity": "HIGH", "file": next(iter(PATHS)), "line": 1,
                "rule": "SEC-1", "explanation": "Synthetic failure", "fix": "Fix fixture"}

    def _reject(self, report, required=PATHS):
        with self.assertRaises(AuditError):
            check_report(report, required)

    def test_exact_scope_order_is_irrelevant(self):
        expected = {"tests/a.py", "tests/b.py"}
        report = good()
        report["reviewed_scope"] = ["tests/b.py", "tests/a.py"]
        self.assertEqual(check_report(report, expected)["status"], "PASS")

    def test_scope_extra_missing_and_duplicates_rejected(self):
        for scope in ([next(iter(PATHS)), "extra.py"], [],
                      [next(iter(PATHS))] * 2, ["unexpected.py", "unexpected.py"],
                      [1], [True], None, "firmware/a.c"):
            with self.subTest(scope=scope):
                r = good()
                r["reviewed_scope"] = scope
                self._reject(r)

    def test_unsafe_scope_paths_rejected(self):
        bad = ("/abs", r"C:\repo\file", r"\\server\file", "./a", "a/./b",
               "a/../b", "../a", "a//b", "a/", "", " a", "a ", "a\nfile",
               "a\x00file", "a\x7ffile")
        for path in bad:
            with self.subTest(path=repr(path)):
                r = good()
                r["reviewed_scope"] = [path]
                self._reject(r, {path})

    def test_invalid_host_required_path_rejected(self):
        for value in ("../up", 2, None, "/absolute", "a\\b"):
            with self.subTest(value=value):
                self._reject(good(), {value})

    def test_deleted_path_and_valid_dot_name_accepted(self):
        r = good()
        r["reviewed_scope"] = [".github/workflows/test.yml"]
        self.assertEqual(check_report(r, set(r["reviewed_scope"]))["status"], "PASS")
        r["reviewed_scope"] = ["a..b/file.c"]
        self.assertEqual(check_report(r, set(r["reviewed_scope"]))["status"], "PASS")

    def test_unknown_and_missing_root_keys_rejected(self):
        for key in ("status", "findings", "limitations", "reviewed_scope"):
            with self.subTest(missing=key):
                r = good(); del r[key]
                self._reject(r)
        r = good(); r["other"] = "untrusted"
        self._reject(r)

    def test_all_root_types_rejected(self):
        for status in (False, None, [], {}, "pass", 9):
            with self.subTest(status=repr(status)):
                r = good(); r["status"] = status
                self._reject(r)
        for key in ("findings", "limitations", "reviewed_scope"):
            for value in (None, {}, "", 1):
                with self.subTest(key=key, value=value):
                    r = good(); r[key] = value
                    self._reject(r)
        for value in (1, None, {}, True):
            r = good(); r["limitations"] = [value]
            self._reject(r)

    def test_finding_required_fields_and_extra_rejected(self):
        original = self._finding()
        for key in original:
            with self.subTest(missing=key):
                item = dict(original); del item[key]
                r = good(); r["status"] = "FAIL"; r["findings"] = [item]
                self._reject(r)
        item = dict(original); item["extra"] = 42
        r = good(); r["status"] = "FAIL"; r["findings"] = [item]
        self._reject(r)
        r["findings"] = [None]
        self._reject(r)

    def test_finding_types_values_and_paths_rejected(self):
        original = self._finding()
        for severity in (None, [], {}, 3, "high"):
            r = good(); r["status"] = "FAIL"
            r["findings"] = [dict(original, severity=severity)]
            self._reject(r)
        for key in ("file", "rule", "explanation", "fix"):
            for value in (None, 0, [], "", "   "):
                r = good(); r["status"] = "FAIL"
                r["findings"] = [dict(original, **{key: value})]
                self._reject(r)
        for bad in ("../secret", "/abs", "a/./b", "test\\evil"):
            r = good(); r["status"] = "FAIL"
            r["findings"] = [dict(original, file=bad)]
            self._reject(r)

    def test_finding_line_integer_only(self):
        for value in (True, False, 0, -1, 1.0, 1.5, "1", None, [], {}):
            with self.subTest(line=repr(value)):
                r = good(); r["status"] = "FAIL"
                r["findings"] = [dict(self._finding(), line=value)]
                self._reject(r)

    def test_fail_inconclusive_preserved(self):
        for verdict in ("FAIL", "INCONCLUSIVE"):
            r = good(); r["status"] = verdict
            r["findings"] = [self._finding()]
            self.assertEqual(check_report(r, PATHS)["status"], verdict)
        r = good(); r["status"] = "FAIL"
        r["findings"] = [dict(self._finding(), file="docs/reference.md")]
        self.assertEqual(check_report(r, PATHS)["status"], "FAIL")
        r = good(); r["limitations"] = ["Incomplete context"]
        self._reject(r)

    def test_strict_json_decoder_and_envelope(self):
        invalid = (
            '{"status":"SUCCESS","status":"SUCCESS","structured_output":{}}',
            '{"status":"SUCCESS","structured_output":{"status":"PASS","status":"PASS"}}',
            '{"status":"SUCCESS","metadata":{"x":1,"x":1},"structured_output":{}}',
            '{"status":"SUCCESS","structured_output":{},"error":NaN}',
            '{"status":"SUCCESS","structured_output":{},"error":Infinity}',
            '{"status":"SUCCESS","structured_output":{},"error":-Infinity}',
            '{"status":"SUCCESS","structured_output":{}} trailing',
        )
        for payload in invalid:
            with self.subTest(payload=payload[:50]):
                with self.assertRaises(AuditError):
                    parse_result(0, payload, "", PATHS)
        parsed = parse_result(0, json.dumps({"status": "SUCCESS",
            "provider_metadata": {"version": 1}, "structured_output": good()}), "", PATHS)
        self.assertEqual(parsed["status"], "PASS")

    def test_mocked_invoke_rejects_extra_audit_scope(self):
        report = good()
        report["reviewed_scope"].append("unapproved/path.py")
        payload = envelope(report)
        with tempfile.TemporaryDirectory() as tmp, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "")) as mocked:
            with self.assertRaises(AuditError):
                invoke("Review code", pathlib.Path(tmp), pathlib.Path(tmp) / "schema.json",
                       120, PATHS)
            argv = mocked.call_args.args[0]
            for flag in ("--sandbox", "--output-format", "--json-schema", "--print-timeout"):
                self.assertIn(flag, argv)

    def test_mocked_invoke_valid_success_and_provider_metadata(self):
        payload = json.dumps({"status": "SUCCESS", "metadata": {"model": "mock"},
                              "structured_output": good()})
        with tempfile.TemporaryDirectory() as tmp, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "")):
            report = invoke("Review code", pathlib.Path(tmp), pathlib.Path(tmp) / "schema.json",
                            120, PATHS)
            self.assertEqual(report["status"], "PASS")

    def test_mocked_invoke_denial_and_timeout(self):
        payload = envelope(good())
        with tempfile.TemporaryDirectory() as tmp, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, payload, "permission denied")):
            with self.assertRaises(AuditError):
                invoke("Review", pathlib.Path(tmp), pathlib.Path(tmp) / "schema.json", 120, PATHS)
        with tempfile.TemporaryDirectory() as tmp, patch(
                "adapters.antigravity.subprocess.run",
                side_effect=subprocess.TimeoutExpired("agy", 120)):
            with self.assertRaises(AuditError):
                invoke("Review", pathlib.Path(tmp), pathlib.Path(tmp) / "schema.json", 120, PATHS)

    def test_utf8_byte_budget(self):
        payload = envelope(good())
        self.assertEqual(parse_result(0, payload, "", PATHS)["status"], "PASS")
        with self.assertRaises(AuditError):
            parse_result(0, payload + " " * 160001, "", PATHS)
        with self.assertRaises(AuditError):
            parse_result(0, payload + "é" * 81000, "", PATHS)

    def test_schema_contract_requires_review(self):
        schema_path = pathlib.Path(__file__).resolve().parents[2] /             "scripts" / "agent_harness" / "adapters" / "audit.schema.json"
        schema = json.loads(schema_path.read_text())
        definitions = schema.pop("$defs")
        self.assertEqual(set(definitions), {"selection_sha256", "rule_results"})
        result = definitions["rule_results"]
        self.assertEqual(result["maxItems"], 96)
        self.assertFalse(result["items"]["additionalProperties"])
        self.assertEqual(set(result["items"]["required"]),
                         {"rule_id", "rule_sha256", "status", "evidence", "reason"})
        self.assertEqual(set(result["items"]["properties"]["status"]["enum"]),
                         {"PASS", "FAIL", "NOT_RUN", "NOT_VERIFIED", "WAIVED_WITH_REASON"})
        root_keys = ("status", "findings", "limitations", "reviewed_scope")
        finding_keys = ("severity", "file", "line", "rule", "explanation", "fix")
        expected = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "status": {"type": "string", "enum": ["PASS", "FAIL", "INCONCLUSIVE"]},
                "findings": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "severity": {"type": "string", "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
                        "file": {"type": "string", "minLength": 1},
                        "line": {"type": "integer", "minimum": 1},
                        "rule": {"type": "string", "minLength": 1},
                        "explanation": {"type": "string", "minLength": 1},
                        "fix": {"type": "string", "minLength": 1},
                    }, "required": list(finding_keys)}},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "reviewed_scope": {"type": "array", "items": {"type": "string"}},
            }, "required": list(root_keys),
        }
        self.assertEqual(schema, expected)




class ScopedRuleReportTests(unittest.TestCase):
    def setUp(self):
        self.rules = [{"rule_id": "MEM-001", "rule_sha256": "a" * 64}]
        self.selection = "b" * 64
        self.inventory = {"unit.log": "c" * 64}
        self.report = dict(good(), selection_sha256=self.selection, rule_results=[{
            "rule_id": "MEM-001", "rule_sha256": "a" * 64, "status": "PASS",
            "evidence": [{"receipt_path": "unit.log", "receipt_sha256": "c" * 64}],
            "reason": "Host test evidence and inspected bounds cover this rule."}])

    def check(self, report):
        return check_report(report, PATHS, self.rules, self.selection, self.inventory)

    def test_exact_rule_and_trusted_evidence_accepted(self):
        self.assertEqual(self.check(self.report)["rule_results"][0]["status"], "PASS")
        schema = scoped_schema(self.rules, self.selection, PATHS)
        self.assertEqual(set(schema["required"]), set(self.report))
        self.assertEqual(schema["properties"]["rule_results"]["minItems"], 1)
        self.assertEqual(schema["properties"]["selection_sha256"]["enum"], [self.selection])

    def test_missing_extra_duplicate_and_changed_rule_rejected(self):
        mutations = [[], self.report["rule_results"] * 2,
                     [dict(self.report["rule_results"][0], rule_id="SEC-001")],
                     [dict(self.report["rule_results"][0], rule_sha256="d" * 64)]]
        for results in mutations:
            with self.subTest(results=len(results)), self.assertRaises(AuditError):
                self.check(dict(self.report, rule_results=results))
        rules = self.rules + [{"rule_id": "MEM-002", "rule_sha256": "d" * 64}]
        with self.assertRaises(AuditError):
            check_report(dict(self.report, rule_results=self.report["rule_results"] * 2),
                         PATHS, rules, self.selection, self.inventory)

    def test_missing_extra_malformed_and_stale_scoped_fields_rejected(self):
        for key in self.report:
            report = copy.deepcopy(self.report)
            del report[key]
            with self.subTest(key=key), self.assertRaises(AuditError):
                self.check(report)
        for change in ({"selection_sha256": "e" * 64}, {"extra": True},
                       {"rule_results": None}, {"rule_results": {}}):
            with self.subTest(change=next(iter(change))), self.assertRaises(AuditError):
                self.check(dict(self.report, **change))
        for key in self.report["rule_results"][0]:
            report = copy.deepcopy(self.report)
            del report["rule_results"][0][key]
            with self.subTest(rule_key=key), self.assertRaises(AuditError):
                self.check(report)

    def test_missing_fabricated_changed_duplicate_and_unsafe_evidence_rejected(self):
        for evidence in ([], [{"receipt_path": "invented.log", "receipt_sha256": "c" * 64}],
                         [{"receipt_path": "unit.log", "receipt_sha256": "d" * 64}],
                         [{"receipt_path": "../unit.log", "receipt_sha256": "c" * 64}],
                         self.report["rule_results"][0]["evidence"] * 2,
                         [{"receipt_path": "unit.log"}]):
            report = copy.deepcopy(self.report)
            report["rule_results"][0]["evidence"] = evidence
            with self.subTest(count=len(evidence)), self.assertRaises(AuditError):
                self.check(report)

    def test_waiver_incomplete_and_failed_rule_cannot_grant_overall_pass(self):
        for status in ("FAIL", "NOT_RUN", "NOT_VERIFIED", "WAIVED_WITH_REASON", "UNKNOWN", True):
            report = copy.deepcopy(self.report)
            report["rule_results"][0]["status"] = status
            with self.subTest(status=status), self.assertRaises(AuditError):
                self.check(report)
        report["status"] = "INCONCLUSIVE"
        report["rule_results"][0].update(status="NOT_VERIFIED", evidence=[])
        self.assertEqual(self.check(report)["status"], "INCONCLUSIVE")

    def test_oversize_secret_and_deep_report_rejected_without_leak(self):
        for text in ("x" * 160001, "ghp_" + "A" * 30,
                     "Untrusted dump: -----BEGIN " + "PRIVATE KEY-----",
                     "Untrusted dump token=" + "synthetic-value"):
            report = copy.deepcopy(self.report)
            report["rule_results"][0]["reason"] = text
            with self.assertRaises(AuditError) as error:
                self.check(report)
            self.assertNotIn(text, str(error.exception))
        with self.assertRaises(AuditError):
            parse_result(0, "[" * 2000 + "]" * 2000, "", PATHS)

    def test_strict_invocation_does_not_fall_back_to_legacy_report(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
                "adapters.antigravity.subprocess.run",
                return_value=subprocess.CompletedProcess([], 0, envelope(good()), "")):
            with self.assertRaises(AuditError):
                invoke("Review scoped rules", pathlib.Path(tmp), pathlib.Path(tmp) / "schema.json",
                       120, PATHS, self.rules, self.selection, self.inventory)


if __name__ == "__main__":
    unittest.main()
