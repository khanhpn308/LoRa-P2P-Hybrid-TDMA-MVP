"""P0 MCP Host boundary tests. No live GitHub/Docker or local state mutation."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2] / "scripts" / "agent_harness" / "mcp_host.py"
spec = importlib.util.spec_from_file_location("mcp_host", SRC)
mod = importlib.util.module_from_spec(spec)
sys.modules["mcp_host"] = mod
spec.loader.exec_module(mod)
HarnessMCPHost = mod.HarnessMCPHost


class HostMCPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "project"
        (self.repo / "scripts/agent_harness/p1").mkdir(parents=True)
        for name in ("cli.py", "host_gate.py"):
            (self.repo / "scripts/agent_harness/p1" / name).write_text("# fixture\n")
        self.host = HarnessMCPHost(self.repo)

    def test_rejects_invalid_issue_inputs_without_spawning(self):
        with patch.object(mod.subprocess, "run") as runner:
            for value in (0, -1, 2**40, True, "82", None):
                self.assertEqual(self.host.preflight(value)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_rejects_injected_and_noncanonical_run_ids(self):
        with patch.object(mod.subprocess, "run") as runner:
            for value in ("1; rm -rf", "A"*32, "a"*31, "a"*32+"/", ""):
                self.assertEqual(self.host.status(value)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_preflight_uses_fixed_trusted_argv(self):
        payload = {"state": "PREFLIGHT_ONLY", "issue": 81}
        done = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b"")
        with patch.object(mod.subprocess, "run", return_value=done) as runner:
            self.assertEqual(self.host.preflight(81), payload)
            cmd = runner.call_args.args[0]
            self.assertEqual(cmd[1], str(self.repo / "scripts/agent_harness/p1/cli.py"))
            self.assertEqual(cmd[2:], ["prepare", "--issue", "81", "--source", str(self.repo)])
            self.assertEqual(runner.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_fail_closed_on_nonzero_exit_timeout_and_malformed_output(self):
        with patch.object(mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 1)):
            self.assertEqual(self.host.preflight(8)["status"], "BLOCKED")
        for done in (
            subprocess.CompletedProcess([], 1, b'{"state":"PREPARED"}', b"token SECRET"),
            subprocess.CompletedProcess([], 0, b"not json", b""),
            subprocess.CompletedProcess([], 0, b"x"*65537, b""),
            subprocess.CompletedProcess([], 0, b"[]", b""),
        ):
            with patch.object(mod.subprocess, "run", return_value=done):
                value = self.host.preflight(8)
                self.assertEqual(value["status"], "BLOCKED")
                self.assertNotIn("SECRET", json.dumps(value))

    def test_status_and_candidate_gate_need_external_journal(self):
        with patch.object(mod.subprocess, "run") as runner:
            self.assertEqual(self.host.status("a"*32)["status"], "BLOCKED")
            self.assertEqual(self.host.verify_candidate("a"*32)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_status_uses_journal_and_verify_fixed_host_gate(self):
        self.host.state.parent.mkdir(mode=0o700)
        self.host.state.write_bytes(b"stub")
        done = subprocess.CompletedProcess([], 0, b'{"status":"SCOPE_SCAN_PASS_ONLY"}', b"")
        with patch.object(mod.subprocess, "run", return_value=done) as runner:
            self.assertEqual(self.host.verify_candidate("a"*32)["status"], "SCOPE_SCAN_PASS_ONLY")
            argv = runner.call_args.args[0]
            self.assertEqual(argv[1], str(self.repo / "scripts/agent_harness/p1/host_gate.py"))
            self.assertNotIn("--image-id", argv)


if __name__ == "__main__":
    unittest.main()
