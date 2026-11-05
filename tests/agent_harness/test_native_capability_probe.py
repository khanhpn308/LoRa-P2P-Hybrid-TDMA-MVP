"""Unit tests for Native Capability Probe and Disposable Safe Smoke."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
import native_capability_probe as probe


class NativeCapabilityProbeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "user_home"
        self.home.mkdir(parents=True)
        self.repo = Path(self.tmp.name).resolve() / "test_repo"
        self.repo.mkdir(parents=True)

    def test_probe_ready_when_configured(self):
        # Setup mock configured AGY and Codex
        agy_cfg = self.home / ".gemini/antigravity-cli/settings.json"
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text(json.dumps({
            "model": "Gemini 3.8 Flash (High)",
            "agentMode": "accept-edits",
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [str(self.repo.resolve())],
        }), encoding="utf-8")

        codex_cfg = self.home / ".codex/config.toml"
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(f'[projects."{self.repo.resolve()}"]\ntrust_level = "trusted"\n', encoding="utf-8")

        with patch.object(probe.shutil, "which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch.object(probe, "check_gh_version", return_value=("PASS", "2.45.0", "PASS", "ok")), \
             patch.object(probe, "run_cmd", return_value=(0, json.dumps({
                 "status": "HOST_CONTEXT_LOADED",
                 "agents_sha256": "f" * 64,
             }), "")):
            res = probe.probe_environment(self.repo, self.home)
            self.assertEqual(res["status"], "READY")
            self.assertEqual(len(res["blockers"]), 0)
            self.assertEqual(res["clients"]["agy"]["status"], "READY")
            self.assertEqual(res["clients"]["codex"]["status"], "READY")

    def test_negative_missing_clis(self):
        with patch.object(probe.shutil, "which", side_effect=lambda x: "/usr/bin/git" if x in ("git", "python3") else None), \
             patch.object(probe, "run_cmd", return_value=(0, json.dumps({"status": "HOST_CONTEXT_LOADED"}), "")):
            res = probe.probe_environment(self.repo, self.home)
            self.assertEqual(res["status"], "BLOCKED")
            self.assertIn("Neither Codex nor AGY CLI installed on PATH", res["blockers"])

    def test_negative_readonly_gemini_without_permissions(self):
        # AGY configured with read-only model and restricted permissions
        agy_cfg = self.home / ".gemini/antigravity-cli/settings.json"
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text(json.dumps({
            "model": "Gemini 3.8 Flash (High)",
            "agentMode": "plan",
            "toolPermission": "ask-first",
            "trustedWorkspaces": [],
        }), encoding="utf-8")

        with patch.object(probe.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else "/usr/bin/git"), \
             patch.object(probe, "run_cmd", return_value=(0, json.dumps({"status": "HOST_CONTEXT_LOADED"}), "")):
            res = probe.probe_environment(self.repo, self.home)
            self.assertEqual(res["status"], "BLOCKED")
            self.assertEqual(res["clients"]["agy"]["status"], "PARTIAL")
            self.assertFalse(res["clients"]["agy"]["tool_permission_ok"])
            self.assertFalse(res["clients"]["agy"]["repo_trusted"])

    def test_negative_bad_config_fails_closed(self):
        agy_cfg = self.home / ".gemini/antigravity-cli/settings.json"
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text("{malformed json", encoding="utf-8")

        with patch.object(probe.shutil, "which", return_value="/usr/bin/agy"):
            res = probe.inspect_agy(self.home, self.repo)
            self.assertFalse(res["config_exists"])
            self.assertEqual(res["status"], "PARTIAL")

    def test_negative_stale_source_or_g0_failure(self):
        agy_cfg = self.home / ".gemini/antigravity-cli/settings.json"
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text(json.dumps({
            "agentMode": "accept-edits",
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [str(self.repo.resolve())],
        }), encoding="utf-8")

        with patch.object(probe.shutil, "which", return_value="/usr/bin/agy"), \
             patch.object(probe, "run_cmd", return_value=(1, "", "AGENTS.md hash drift detected")):
            res = probe.probe_environment(self.repo, self.home)
            self.assertEqual(res["status"], "BLOCKED")
            self.assertEqual(res["host_g0"]["status"], "BLOCKED")
            self.assertTrue(any("Host G0 Context" in b for b in res["blockers"]))

    def test_negative_gh_unauthenticated(self):
        with patch.object(probe.shutil, "which", return_value="/usr/bin/gh"), \
             patch.object(probe, "run_cmd", side_effect=[
                 (0, "gh version 2.45.0", ""),  # gh --version
                 (1, "", "Logged out"),         # gh auth status
             ]):
            _, _, auth_status, _ = probe.check_gh_version(check_online=True)
            self.assertEqual(auth_status, "FAIL")

    def test_smoke_safety_rejects_target_inside_repo(self):
        inside_target = self.repo / "disposable_smoke"
        res = probe.run_smoke(inside_target, self.repo, consent=True)
        self.assertEqual(res["smoke_status"], "BLOCKED")
        self.assertIn("strictly outside repository", res["reason"])

    def test_smoke_safety_rejects_without_consent(self):
        smoke_dir = Path(self.tmp.name).resolve() / "smoke_dir"
        res = probe.run_smoke(smoke_dir, self.repo, consent=False)
        self.assertEqual(res["smoke_status"], "BLOCKED")
        self.assertIn("Operator consent required", res["reason"])

    def test_smoke_happy_path(self):
        smoke_dir = Path(self.tmp.name).resolve() / "smoke_dir"
        with patch.object(probe, "run_cmd") as mock_run:
            def fake_run(argv, cwd=None, timeout=15, input_text=None):
                if "PY_SMOKE" in str(argv):
                    return 0, "PY_SMOKE:3.12\n", ""
                if argv[0] == "git":
                    return 0, "", ""
                if "agent_context.py" in str(argv):
                    return 0, json.dumps({"status": "HOST_CONTEXT_LOADED", "agents_sha256": "1" * 64}), ""
                return 0, "", ""

            mock_run.side_effect = fake_run
            res = probe.run_smoke(smoke_dir, self.repo, consent=True)
            self.assertEqual(res["smoke_status"], "SMOKE_PASS")
            self.assertEqual(len(res["steps"]), 5)
            self.assertTrue(all(s["status"] == "PASS" for s in res["steps"]))
            summary_file = Path(res["receipts_dir"]) / "smoke_summary.json"
            self.assertTrue(summary_file.is_file())

    def test_smoke_step_failure_marks_failed(self):
        smoke_dir = Path(self.tmp.name).resolve() / "smoke_dir"
        with patch.object(probe, "run_cmd") as mock_run:
            # Step 1 fails
            mock_run.return_value = (1, "", "Permission denied")
            res = probe.run_smoke(smoke_dir, self.repo, consent=True)
            self.assertEqual(res["smoke_status"], "SMOKE_FAILED")
            self.assertEqual(res["failed_step"], "shell_execution")


if __name__ == "__main__":
    unittest.main()
