"""Hermetic installer policy tests; no real pip, Docker, GitHub or AI CLI changes."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/harness_mcp_setup.py"
spec = importlib.util.spec_from_file_location("harness_mcp_setup", SCRIPT)
setup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = setup
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()

    def agy(self):
        return setup.agy_path(self.home)

    def test_launcher_is_absolute_and_no_shell(self):
        command = setup.command_line(self.home)
        self.assertTrue(Path(command[0]).is_absolute())
        self.assertTrue(Path(command[1]).is_absolute())
        self.assertEqual(len(command), 2)

    def test_agy_missing_file_readonly(self):
        self.assertEqual(setup.read_agy(self.agy(), self.home), {"mcpServers": {}})
        self.assertFalse(self.agy().exists())

    def test_agy_preserves_unrelated_servers(self):
        file = self.agy()
        file.parent.mkdir(parents=True)
        file.write_text(json.dumps({"mcpServers": {
            "other": {"command": "my-server", "args": []}},
            "unrelated": True}))
        with patch.object(setup.shutil, "which", side_effect=lambda x: "/usr/bin/agy" if x == "agy" else None):
            setup.write_agy(self.home, setup.command_line(self.home))
            data = setup.read_agy(file, self.home)
            self.assertTrue(data["unrelated"])
            self.assertEqual(data["mcpServers"]["other"]["command"], "my-server")
            self.assertEqual(setup.agy_config(setup.command_line(self.home), self.home)[0], "READY")
        self.assertEqual(file.stat().st_mode & 0o777, 0o600)

    def test_agy_conflict_does_not_overwrite(self):
        file = self.agy()
        file.parent.mkdir(parents=True)
        file.write_text(json.dumps({"mcpServers": {"lora_harness": {"command": "something-else"}}}))
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"):
            status, _ = setup.agy_config(setup.command_line(self.home), self.home)
            self.assertEqual(status, "BLOCKED")
            with self.assertRaises(RuntimeError):
                setup.write_agy(self.home, setup.command_line(self.home))
        self.assertIn("something-else", file.read_text())

    def test_agy_invalid_json_fail_closed(self):
        file = self.agy()
        file.parent.mkdir(parents=True)
        file.write_text("{invalid")
        with patch.object(setup.shutil, "which", return_value="/usr/bin/agy"):
            self.assertEqual(setup.agy_config(setup.command_line(self.home), self.home)[0], "BLOCKED")
            with self.assertRaises(RuntimeError):
                setup.write_agy(self.home, setup.command_line(self.home))

    def test_agy_symlink_rejected(self):
        file = self.agy()
        file.parent.mkdir(parents=True)
        original = self.home / "original.json"
        original.write_text('{"mcpServers": {}}')
        file.symlink_to(original)
        with self.assertRaises(RuntimeError):
            setup.read_agy(file, self.home)
        self.assertEqual(original.read_text(), '{"mcpServers": {}}')

    def test_codex_list_missing(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/codex"), \
             patch.object(setup, "run", return_value=subprocess.CompletedProcess([], 0, b"[]", b"")):
            self.assertEqual(setup.codex_config(setup.command_line(self.home))[0], "INSTALL")

    def test_codex_existing_good_and_conflicting(self):
        cmd = setup.command_line(self.home)
        payload = [{"name": "lora_harness",
                    "transport": {"type": "stdio", "command": cmd[0], "args": cmd[1:]}}]
        with patch.object(setup.shutil, "which", return_value="/usr/bin/codex"), \
             patch.object(setup, "run", return_value=subprocess.CompletedProcess(
                 [], 0, json.dumps(payload).encode(), b"")):
            self.assertEqual(setup.codex_config(cmd)[0], "READY")
            self.assertEqual(setup.codex_config(["/wrong/python", "server.py"])[0], "BLOCKED")

    def test_codex_unparseable_blocked(self):
        with patch.object(setup.shutil, "which", return_value="/usr/bin/codex"), \
             patch.object(setup, "run", return_value=subprocess.CompletedProcess([], 0, b"{}", b"")):
            self.assertEqual(setup.codex_config(setup.command_line(self.home))[0], "INSTALL")
        with patch.object(setup.shutil, "which", return_value="/usr/bin/codex"), \
             patch.object(setup, "run", return_value=subprocess.CompletedProcess([], 0, b"garbage", b"")):
            self.assertEqual(setup.codex_config(setup.command_line(self.home))[0], "BLOCKED")

    def test_plan_does_not_install_or_register(self):
        with patch.object(setup, "installed_sdk", return_value=False), \
             patch.object(setup, "codex_config", return_value=("INSTALL", "missing")), \
             patch.object(setup, "agy_config", return_value=("INSTALL", "missing")), \
             patch.object(setup, "run") as run:
            report = setup.plan(self.home)
            self.assertEqual(report["sdk"], "INSTALL")
            self.assertEqual(report["codex"]["status"], "INSTALL")
            self.assertEqual(report["agy"]["status"], "INSTALL")
            run.assert_not_called()

    def test_no_mutation_as_root_or_noninteractive(self):
        with patch.object(setup.os, "geteuid", return_value=0):
            self.assertEqual(setup.apply(self.home), 1)
        with patch.object(setup.os, "geteuid", return_value=1000), \
             patch.object(setup.sys.stdin, "isatty", return_value=False):
            self.assertEqual(setup.apply(self.home), 1)


if __name__ == "__main__":
    unittest.main()
