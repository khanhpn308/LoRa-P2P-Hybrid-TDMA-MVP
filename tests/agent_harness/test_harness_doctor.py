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
            "AGENTS.md",
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
        secret = "SENTINEL_DO_NOT_DISCLOSE_123"
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

    def test_backend_profile_detects_go_version_drift_and_uses_pinned_docker(self):
        (self.repo / ".go-version").write_text("1.27.3\n", encoding="utf-8")
        (self.repo / "backend-go").mkdir()
        (self.repo / "backend-go/go.mod").write_text("module example\n\ngo 1.27.3\n", encoding="utf-8")

        def mock_stdout(argv, timeout=10):
            if Path(argv[0]).name == "go" and argv[1:] == ["version"]:
                return (0, "go version go1.27.1 linux/amd64")
            return (1, "")

        with patch.object(doctor.shutil, "which", side_effect=self.which), \
             patch.object(doctor, "probe", return_value=True), \
             patch.object(doctor, "probe_stdout", side_effect=mock_stdout), \
             patch.object(doctor, "auth_configured", return_value=True), \
             patch.object(doctor.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b""
            report = doctor.collect(repo=self.repo, profile="backend")
        self.assertTrue(report["ready"])
        host_chk = next(x for x in report["checks"] if x["check"] == "go_host_version")
        self.assertEqual(host_chk["status"], "WARN")
        self.assertIn("drift", host_chk["detail"].lower())

        # If neither host Go matches nor Docker image is cached, go_toolchain fails.
        def mock_probe(args, *rest):
            return "golang:1.27.3-alpine" not in args

        with patch.object(doctor.shutil, "which", side_effect=self.which), \
             patch.object(doctor, "probe", side_effect=mock_probe), \
             patch.object(doctor, "probe_stdout", side_effect=mock_stdout), \
             patch.object(doctor, "auth_configured", return_value=True), \
             patch.object(doctor.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b""
            blocked = doctor.collect(repo=self.repo, profile="backend")
        self.assertIn("go_toolchain", blocked["failed_required_checks"])

    def test_web_and_firmware_dependency_caches_fail_closed_when_missing(self):
        (self.repo / "clients/web-dashboard").mkdir(parents=True)
        (self.repo / "clients/web-dashboard/package.json").write_text("{}\n", encoding="utf-8")
        (self.repo / "clients/web-dashboard/package-lock.json").write_text("{}\n", encoding="utf-8")
        web_missing, _ = self.report(profile="web")
        self.assertIn("web_deps_cache", web_missing["failed_required_checks"])

        (self.repo / "clients/web-dashboard/node_modules").mkdir()
        (self.repo / "clients/web-dashboard/node_modules/.package-lock.json").write_text("{}\n", encoding="utf-8")
        web_ok, _ = self.report(profile="web")
        self.assertNotIn("web_deps_cache", web_ok["failed_required_checks"])

        (self.repo / "firmware/gateway_master").mkdir(parents=True)
        (self.repo / "firmware/gateway_master/dependencies.lock").write_text(
            "dependencies:\n  espressif/mqtt:\n    version: 1.1.0\n", encoding="utf-8"
        )
        fw_missing, _ = self.report(profile="firmware")
        self.assertIn("firmware_deps_cache", fw_missing["failed_required_checks"])

        (self.repo / "firmware/gateway_master/managed_components/espressif__mqtt").mkdir(parents=True)
        fw_ok, _ = self.report(profile="firmware")
        self.assertNotIn("firmware_deps_cache", fw_ok["failed_required_checks"])

    def test_symlinked_agents_md_unsafe_git_filter_and_prod_env_blocked(self):
        agents = self.repo / "AGENTS.md"
        agents.unlink()
        other = self.repo / "OTHER.md"
        other.write_text("x\n", encoding="utf-8")
        agents.symlink_to(other)
        res_sym, _ = self.report()
        self.assertIn("agents_context_integrity", res_sym["failed_required_checks"])

        agents.unlink()
        agents.write_text("fixture\n", encoding="utf-8")
        with patch.object(doctor.shutil, "which", side_effect=self.which), \
             patch.object(doctor, "probe", return_value=True), \
             patch.object(doctor, "probe_stdout", return_value=(0, "filter.evil.clean cat")), \
             patch.object(doctor, "auth_configured", return_value=True), \
             patch.object(doctor.subprocess, "run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = b""
            res_flt = doctor.collect(repo=self.repo)
        self.assertIn("git_clean_filters", res_flt["failed_required_checks"])

        with patch.dict(doctor.os.environ, {"LORA_ALLOW_PROD_DB": "1"}):
            res_env, _ = self.report()
        self.assertIn("env_isolation", res_env["failed_required_checks"])

    def test_capabilities_matrix_never_claims_full_access_is_os_sandbox(self):
        report, _ = self.report()
        roles = {c["role"]: c for c in report["capabilities"]}
        self.assertIn("coordinator", roles)
        self.assertIn("auditor", roles)
        self.assertIn("no_os_sandbox", roles["coordinator"]["isolation_mode"])
        self.assertIn("read_only", roles["auditor"]["isolation_mode"])

    def test_smoke_mode_fails_closed_on_smoke_failure(self):
        result, _ = self.report()
        fake_smoke = {"executed": True, "passed": False,
                      "checks": [{"smoke": "quality_gates_head", "status": "FAIL", "exit_code": 1}]}
        stream = io.StringIO()
        with patch.object(doctor, "collect", return_value=result), \
             patch.object(doctor, "run_smoke_checks", return_value=fake_smoke), \
             contextlib.redirect_stdout(stream):
            code = doctor.main(["--json", "--smoke"])
        self.assertEqual(code, 1)
        payload = json.loads(stream.getvalue())
        self.assertFalse(payload["ready"])
        self.assertIn("smoke:quality_gates_head", payload["failed_required_checks"])

    def test_setup_harness_script_valid_and_read_only_by_default(self):
        setup_sh = Path(__file__).resolve().parents[2] / "scripts" / "setup_harness.sh"
        text = setup_sh.read_text(encoding="utf-8")
        self.assertNotIn("--needs-setup", text)
        res = doctor.subprocess.run(["bash", "-n", str(setup_sh)],
                                    capture_output=True, text=True, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
