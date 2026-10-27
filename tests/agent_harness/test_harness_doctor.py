"""Offline, hermetic checks for the Native Harness onboarding doctor."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import harness_doctor as doctor


class HarnessDoctorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        for path in (
            "AGENTS.md", ".github/copilot-instructions.md",
            "docs/development/harness-fast-lane.md",
            "docs/development/harness-quality-gates.md",
            ".agents/agents/harness-coordinator.md",
        ):
            f = self.repo / path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("fixture\n", encoding="utf-8")
        version = self.repo / "firmware/esp-idf-version.txt"
        version.parent.mkdir(parents=True, exist_ok=True)
        version.write_text("v6.1\n", encoding="utf-8")

    @staticmethod
    def which(name):
        return None if name == "agy" else "/usr/bin/" + name

    def report(self, profile="core", probe=None, auth=True, which=None,
               check_auth=False):
        with patch.object(doctor.shutil, "which", side_effect=which or self.which), \
             patch.object(doctor, "probe", side_effect=probe or (lambda *a, **k: True)) as called, \
             patch.object(doctor, "auth_configured", return_value=auth), \
             patch.object(doctor.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b""
            value = doctor.collect(repo=self.repo, profile=profile,
                                   check_auth=check_auth)
            return value, called.call_args_list

    def test_core_ready_without_docker_or_agy(self):
        result, calls = self.report()
        self.assertTrue(result["ready"])
        self.assertIn("docker_daemon",
                      [x["check"] for x in result["checks"] if x["status"] == "SKIP"])
        self.assertFalse(any("docker" in str(call) for call in calls))

    def test_does_not_validate_github_auth_online_by_default(self):
        result, calls = self.report()
        self.assertEqual(next(x for x in result["checks"]
                              if x["check"] == "gh_auth_online")["status"], "SKIP")
        self.assertFalse(any("auth" in str(call) for call in calls))

    def test_optional_online_auth_is_explicit(self):
        _, calls = self.report(check_auth=True)
        self.assertTrue(any("auth" in str(call) for call in calls))

    def test_missing_python_status_uses_version_check(self):
        with patch.object(doctor.sys, "version_info", (3, 9, 0)):
            result, _ = self.report()
        self.assertIn("python", result["failed_required_checks"])

    def test_missing_agent_config_blocks_core(self):
        (self.repo / "AGENTS.md").unlink()
        result, _ = self.report()
        self.assertIn("config:AGENTS.md", result["failed_required_checks"])

    def test_no_ai_cli_blocks_core(self):
        result, _ = self.report(which=lambda n: None if n in ("agy", "codex")
                                else "/usr/bin/" + n)
        self.assertIn("ai_provider", result["failed_required_checks"])

    def test_missing_gh_auth_config_blocks_core(self):
        result, _ = self.report(auth=False)
        self.assertIn("gh_auth_config", result["failed_required_checks"])

    def test_firmware_requires_engine_and_pinned_image(self):
        def mock_probe(args, *rest):
            return "docker" not in args[0] or args[1] != "info"
        result, _ = self.report(profile="firmware", probe=mock_probe)
        self.assertIn("docker_daemon", result["failed_required_checks"])
        self.assertIn("esp_idf_image", result["failed_required_checks"])
        self.assertNotIn("esp_idf_pin", result["failed_required_checks"])

    def test_infra_requires_compose(self):
        def mock_probe(args, *rest):
            return args[:3] != ["docker", "compose", "version"]
        result, _ = self.report(profile="infra", probe=mock_probe)
        self.assertIn("docker_compose", result["failed_required_checks"])
        self.assertNotIn("esp_idf_image", result["failed_required_checks"])

    def test_missing_pin_blocks_firmware(self):
        (self.repo / "firmware/esp-idf-version.txt").write_text("v5.4\n")
        result, _ = self.report(profile="firmware")
        self.assertIn("esp_idf_pin", result["failed_required_checks"])

    def test_dirty_worktree_warns_without_discarding_files(self):
        sentinel = self.repo / "uncommitted.txt"
        sentinel.write_text("preserve", encoding="utf-8")
        with patch.object(doctor.shutil, "which", side_effect=self.which), \
             patch.object(doctor, "probe", return_value=True), \
             patch.object(doctor, "auth_configured", return_value=True), \
             patch.object(doctor.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b"?? uncommitted.txt\n"
            result = doctor.collect(repo=self.repo)
        self.assertTrue(result["ready"])
        self.assertEqual(next(x for x in result["checks"]
                              if x["check"] == "working_tree")["status"], "WARN")
        self.assertEqual(sentinel.read_text(), "preserve")

    def test_token_never_printed_or_serialized(self):
        secret = "ghp_SECRET_SHOULD_NEVER_BE_PRINTED_123"
        with patch.dict(doctor.os.environ, {"GH_TOKEN": secret}):
            result, _ = self.report()
        self.assertNotIn(secret, json.dumps(result))
        self.assertNotIn(secret, str(result))

    def test_json_schema_machine_readable(self):
        report, _ = self.report()
        payload = json.loads(json.dumps(report, ensure_ascii=False))
        self.assertEqual(payload["schema_version"], 1)
        self.assertIsInstance(payload["checks"], list)
        self.assertIsInstance(payload["failed_required_checks"], list)
        self.assertIn("ready", payload)

    def test_invalid_profile_rejected(self):
        with self.assertRaises(ValueError):
            doctor.collect(repo=self.repo, profile="production")

    def test_main_json_exit_code_and_output(self):
        result, _ = self.report()
        stream = io.StringIO()
        with patch.object(doctor, "collect", return_value=result), \
             contextlib.redirect_stdout(stream):
            code = doctor.main(["--json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(stream.getvalue())["ready"])


if __name__ == "__main__":
    unittest.main()
