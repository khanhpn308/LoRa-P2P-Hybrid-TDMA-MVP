"""Mock-envelope tests; do not make billable requests to AGY."""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from adapters.antigravity import AuditError, check_report, parse_result

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


if __name__ == "__main__":
    unittest.main()
