"""Unit tests for Codex and AGY Native Fast Lane configuration bootstrap."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import harness_native_setup as setup


class NativeSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve() / "user_home"
        self.home.mkdir(parents=True)
        self.repo = Path(self.tmp.name).resolve() / "test_repo"
        self.repo.mkdir(parents=True)

    def test_root_execution_blocked(self):
        with patch("os.geteuid", return_value=0):
            code = setup.main(["--plan", "--repo", str(self.repo), "--home", str(self.home)])
            self.assertEqual(code, 1)

    def test_secure_parent_rejects_symlink(self):
        real_dir = self.home / "real_config"
        real_dir.mkdir(parents=True)
        symlink_dir = self.home / "symlink_dir"
        symlink_dir.symlink_to(real_dir)
        target_file = symlink_dir / "settings.json"
        with self.assertRaises(RuntimeError) as ctx:
            setup.secure_parent(target_file, self.home)
        self.assertIn("Symlinked", str(ctx.exception))

    def test_plan_neither_installed(self):
        with patch.object(setup.shutil, "which", return_value=None):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "BLOCKED_UNSUPPORTED_RUNTIME")
            self.assertIn("Neither Codex nor AGY", plan["message"])
            self.assertEqual(plan["total_actions"], 0)

    def test_plan_codex_and_agy_both_installed_unconfigured(self):
        with patch.object(setup.shutil, "which", side_effect=lambda x: f"/usr/bin/{x}"):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "CHANGES_REQUIRED")
            self.assertTrue(plan["codex"]["installed"])
            self.assertTrue(plan["agy"]["installed"])
            self.assertEqual(len(plan["codex"]["actions"]), 1)
            self.assertGreaterEqual(len(plan["agy"]["actions"]), 1)
            self.assertIn("Set agentMode to 'auto'", plan["agy"]["actions"])
            self.assertEqual(plan["total_actions"], len(plan["codex"]["actions"]) + len(plan["agy"]["actions"]))

    def test_plan_idempotent_when_already_configured(self):
        # Configure both clients
        codex_cfg = setup.codex_config_path(self.home)
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text(f'[projects."{self.repo.resolve()}"]\ntrust_level = "trusted"\n', encoding="utf-8")

        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text(json.dumps({
            "agentMode": "auto",
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [str(self.repo.resolve())],
        }), encoding="utf-8")

        with patch.object(setup.shutil, "which", side_effect=lambda x: f"/usr/bin/{x}"):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "READY")
            self.assertEqual(plan["total_actions"], 0)

    def test_plan_accept_edits_existing_config_plans_migration_to_auto(self):
        # Config currently has accept-edits; setup plan must propose migration to auto
        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text(json.dumps({
            "agentMode": "accept-edits",
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [str(self.repo.resolve())],
        }), encoding="utf-8")

        with patch.object(setup.shutil, "which", side_effect=lambda x: f"/usr/bin/{x}" if x == "agy" else None):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "CHANGES_REQUIRED")
            self.assertEqual(plan["total_actions"], 1)
            self.assertIn("Set agentMode to 'auto'", plan["agy"]["actions"])

    def test_apply_codex_atomic_write_and_0600_backup(self):
        codex_cfg = setup.codex_config_path(self.home)
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text('model = "gpt-5"\n', encoding="utf-8")
        codex_cfg.chmod(0o600)

        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/codex" if x == "codex" else None):
            bak = setup.apply_codex(self.home, self.repo)
            self.assertIsNotNone(bak)
            self.assertTrue(bak.is_file())
            self.assertEqual(bak.stat().st_mode & 0o777, 0o600)
            self.assertEqual(bak.read_text(encoding="utf-8"), 'model = "gpt-5"\n')

            updated = codex_cfg.read_text(encoding="utf-8")
            self.assertIn('model = "gpt-5"', updated)
            self.assertIn(f'[projects."{self.repo.resolve()}"]', updated)
            self.assertEqual(codex_cfg.stat().st_mode & 0o777, 0o600)

    def test_apply_agy_preserves_unrelated_settings_and_backs_up(self):
        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        initial_data = {
            "agentMode": "accept-edits",
            "model": "Gemini 3.8 Flash (High)",
            "unrelatedSetting": True,
            "trustedWorkspaces": ["/other/workspace"],
        }
        agy_cfg.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
        agy_cfg.chmod(0o600)

        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None):
            bak = setup.apply_agy(self.home, self.repo)
            self.assertIsNotNone(bak)
            self.assertTrue(bak.is_file())
            self.assertEqual(bak.stat().st_mode & 0o777, 0o600)

            updated = json.loads(agy_cfg.read_text(encoding="utf-8"))
            self.assertEqual(updated["model"], "Gemini 3.8 Flash (High)")
            self.assertTrue(updated["unrelatedSetting"])
            self.assertIn("/other/workspace", updated["trustedWorkspaces"])
            self.assertIn(str(self.repo.resolve()), updated["trustedWorkspaces"])
            self.assertEqual(updated["toolPermission"], "always-proceed")
            self.assertEqual(updated["agentMode"], "auto")
            self.assertEqual(agy_cfg.stat().st_mode & 0o777, 0o600)

    def test_apply_agy_idempotent_when_already_auto(self):
        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        initial_data = {
            "agentMode": "auto",
            "toolPermission": "always-proceed",
            "trustedWorkspaces": [str(self.repo.resolve())],
        }
        agy_cfg.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
        agy_cfg.chmod(0o600)

        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None):
            bak = setup.apply_agy(self.home, self.repo)
            self.assertIsNone(bak)
            # Verify no backup files created
            baks = list(agy_cfg.parent.glob("*.bak"))
            self.assertEqual(len(baks), 0)

    def test_apply_agy_new_config_creates_auto(self):
        agy_cfg = setup.agy_config_path(self.home)
        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None):
            bak = setup.apply_agy(self.home, self.repo)
            self.assertIsNone(bak)  # no prior file to backup
            self.assertTrue(agy_cfg.is_file())
            data = json.loads(agy_cfg.read_text(encoding="utf-8"))
            self.assertEqual(data["agentMode"], "auto")
            self.assertEqual(data["toolPermission"], "always-proceed")
            self.assertIn(str(self.repo.resolve()), data["trustedWorkspaces"])

    def test_unsupported_platform_blocked(self):
        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None), \
             patch("sys.platform", "darwin"):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "BLOCKED_UNSUPPORTED_RUNTIME")
            self.assertIn("Unsupported platform", plan["message"])

    def test_unsupported_agy_version_blocked(self):
        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None), \
             patch.object(setup, "check_agy_support", return_value=(False, "1.4.0", "AGY version 1.4.0 is below minimum supported 1.5.0")):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "BLOCKED_UNSUPPORTED_RUNTIME")
            self.assertIn("below minimum supported 1.5.0", plan["message"])

    def test_corrupted_agy_account_blocked(self):
        gemini_dir = self.home / ".gemini"
        gemini_dir.mkdir(parents=True)
        accts_file = gemini_dir / "google_accounts.json"
        accts_file.write_text("{bad json", encoding="utf-8")

        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None):
            plan = setup.generate_plan(self.home, self.repo)
            self.assertEqual(plan["status"], "BLOCKED_UNSUPPORTED_RUNTIME")
            self.assertIn("Failed to parse AGY account file", plan["message"])

    def test_apply_rollback_on_failure(self):
        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text('{"original": true}', encoding="utf-8")

        codex_cfg = setup.codex_config_path(self.home)
        codex_cfg.parent.mkdir(parents=True, exist_ok=True)
        codex_cfg.write_text('original = true\n', encoding="utf-8")

        with patch.object(setup.shutil, "which", side_effect=lambda x: f"/usr/bin/{x}"), \
             patch.object(setup, "apply_agy", side_effect=RuntimeError("Disk write error")):
            with self.assertRaises(RuntimeError) as ctx:
                setup.apply_configuration(self.home, self.repo)
            self.assertIn("Setup failed and was rolled back", str(ctx.exception))
            # Verify codex was rolled back
            self.assertEqual(codex_cfg.read_text(encoding="utf-8"), 'original = true\n')

    def test_cli_plan_flag_does_not_mutate(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"):
            code = setup.main(["--plan", "--repo", str(self.repo), "--home", str(self.home)])
            self.assertEqual(code, 0)
            self.assertFalse(setup.agy_config_path(self.home).exists())

    def test_cli_non_interactive_apply_without_tty_blocked(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"), \
             patch("sys.stdin.isatty", return_value=False), \
             patch("sys.stdout.isatty", return_value=False):
            code = setup.main(["--apply", "--repo", str(self.repo), "--home", str(self.home)])
            self.assertEqual(code, 1)
            self.assertFalse(setup.agy_config_path(self.home).exists())

    def test_cli_interactive_apply_confirmed(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=True), \
             patch("sys.stdin.readline", return_value="CONFIGURE NATIVE\n"):
            code = setup.main(["--apply", "--repo", str(self.repo), "--home", str(self.home)])
            self.assertEqual(code, 0)
            cfg_path = setup.agy_config_path(self.home)
            self.assertTrue(cfg_path.exists())
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            self.assertEqual(data["agentMode"], "auto")
            self.assertEqual(data["toolPermission"], "always-proceed")

    def test_cli_interactive_apply_cancelled(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch("sys.stdout.isatty", return_value=True), \
             patch("sys.stdin.readline", return_value="CANCEL\n"):
            code = setup.main(["--apply", "--repo", str(self.repo), "--home", str(self.home)])
            self.assertEqual(code, 1)
            self.assertFalse(setup.agy_config_path(self.home).exists())

    def test_agy_invalid_json_fails_closed(self):
        agy_cfg = setup.agy_config_path(self.home)
        agy_cfg.parent.mkdir(parents=True, exist_ok=True)
        agy_cfg.write_text("{broken json", encoding="utf-8")

        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"):
            with self.assertRaises(RuntimeError) as ctx:
                setup.plan_agy(self.home, self.repo)
            self.assertIn("Cannot parse AGY settings.json", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
