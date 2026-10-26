"""P0 MCP Host boundary tests. No live GitHub/Docker or local state mutation."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import os
import time
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
        with patch.object(mod, "bounded_run") as runner:
            for value in (0, -1, 2**40, True, "82", None):
                self.assertEqual(self.host.preflight(value)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_rejects_injected_and_noncanonical_run_ids(self):
        with patch.object(mod, "bounded_run") as runner:
            for value in ("1; rm -rf", "A"*32, "a"*31, "a"*32+"/", ""):
                self.assertEqual(self.host.status(value)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_preflight_uses_fixed_trusted_argv(self):
        payload = {"state": "PREFLIGHT_ONLY", "issue": 81}
        done = subprocess.CompletedProcess([], 0, json.dumps(payload).encode(), b"")
        with patch.object(mod, "bounded_run", return_value=done) as runner:
            self.assertEqual(self.host.preflight(81), payload)
            cmd = runner.call_args.args[0]
            self.assertEqual(cmd[1], str(self.repo / "scripts/agent_harness/p1/cli.py"))
            self.assertEqual(cmd[2:], ["prepare", "--issue", "81", "--source", str(self.repo)])
            self.assertEqual(runner.call_args.kwargs["timeout"], 100)

    def test_fail_closed_on_nonzero_exit_timeout_and_malformed_output(self):
        with patch.object(mod, "bounded_run", side_effect=subprocess.TimeoutExpired("python", 1)):
            self.assertEqual(self.host.preflight(8)["status"], "BLOCKED")
        for done in (
            subprocess.CompletedProcess([], 1, b'{"state":"PREPARED"}', b"token SECRET"),
            subprocess.CompletedProcess([], 0, b"not json", b""),
            subprocess.CompletedProcess([], 0, b"x"*65537, b""),
            subprocess.CompletedProcess([], 0, b"[]", b""),
        ):
            with patch.object(mod, "bounded_run", return_value=done):
                value = self.host.preflight(8)
                self.assertEqual(value["status"], "BLOCKED")
                self.assertNotIn("SECRET", json.dumps(value))

    def test_status_and_candidate_gate_need_external_journal(self):
        with patch.object(mod, "bounded_run") as runner:
            self.assertEqual(self.host.status("a"*32)["status"], "BLOCKED")
            self.assertEqual(self.host.verify_candidate("a"*32)["status"], "BLOCKED")
            runner.assert_not_called()

    def test_status_uses_journal_and_verify_fixed_host_gate(self):
        self.host.state.parent.mkdir(mode=0o700)
        self.host.state.write_bytes(b"stub")
        self.host.state.chmod(0o600)
        done = subprocess.CompletedProcess([], 0, b'{"status":"SCOPE_SCAN_PASS_ONLY"}', b"")
        with patch.object(mod, "bounded_run", return_value=done) as runner:
            self.assertEqual(self.host.verify_candidate("a"*32)["status"], "SCOPE_SCAN_PASS_ONLY")
            argv = runner.call_args.args[0]
            self.assertEqual(argv[1], str(self.repo / "scripts/agent_harness/p1/host_gate.py"))
            self.assertNotIn("--image-id", argv)


    def test_unsafe_journal_permissions_and_symlink_fail_before_spawning(self):
        self.host.state.parent.mkdir(mode=0o700)
        self.host.state.write_text("fixture")
        self.host.state.chmod(0o644)
        with patch.object(mod, "bounded_run") as runner:
            self.assertEqual(self.host.status("a" * 32)["status"], "BLOCKED")
            self.host.state.chmod(0o600)
            self.host.state.parent.chmod(0o755)
            self.assertEqual(self.host.status("a" * 32)["status"], "BLOCKED")
            self.host.state.parent.chmod(0o700)
            self.host.state.unlink()
            self.host.state.symlink_to("/etc/passwd")
            self.assertEqual(self.host.status("a" * 32)["status"], "BLOCKED")
            runner.assert_not_called()


class ProcessLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def run_fixture(self, code, **kwargs):
        return mod.bounded_run([sys.executable, "-c", code], self.root, **kwargs)

    def test_both_pipes_count_toward_live_output_limit(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                with self.assertRaises(ValueError):
                    self.run_fixture("import os\nwhile True: os.write(%d,b'x'*4096)" % descriptor,
                                     timeout=2, limit=1024)

    def test_disk_log_never_exceeds_limit(self):
        path = self.root / "log"
        with path.open("wb") as log:
            with self.assertRaises(ValueError):
                self.run_fixture("import os\nwhile True: os.write(1,b'x'*4096)",
                                 timeout=2, limit=1024, log=log)
        self.assertEqual(path.stat().st_size, 1024)

    def test_exact_limit_succeeds_and_stderr_is_not_returned(self):
        result = self.run_fixture("import os; os.write(1,b'x'*512); os.write(2,b's'*512)",
                                  timeout=2, limit=1024)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"x" * 512)
        self.assertEqual(result.stderr, b"")

    def test_timeout_with_open_pipes_and_after_early_eof(self):
        for close in ("", "os.close(1); os.close(2);"):
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_fixture("import os,time; " + close + "time.sleep(10)", timeout=0.1)
            self.assertLess(time.monotonic() - start, 2)

    def test_background_descendant_is_killed_even_on_success(self):
        pidfile = self.root / "child.pid"
        code = ("import os,time; child=os.fork(); "
                "open('child.pid','w').write(str(child)) if child else None; "
                "(os.close(1),os.close(2),time.sleep(10)) if not child else None")
        result = self.run_fixture(code, timeout=2)
        self.assertEqual(result.returncode, 0)
        pid = int(pidfile.read_text())
        for _ in range(50):
            proc = Path('/proc') / str(pid) / 'stat'
            if not proc.exists() or proc.read_text().split()[2] == 'Z':
                break
            time.sleep(0.01)
        else:
            self.fail("Background descendant survived supervisor cleanup")

    def test_timeout_kills_sigterm_ignoring_child_and_parent(self):
        pidfile = self.root / "child.pid"
        code = ("import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "child=os.fork(); "
                "open('child.pid','w').write(str(child)) if child else None; time.sleep(10)")
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_fixture(code, timeout=0.2)
        pid = int(pidfile.read_text())
        for _ in range(50):
            proc = Path('/proc') / str(pid) / 'stat'
            if not proc.exists() or proc.read_text().split()[2] == 'Z':
                break
            time.sleep(0.01)
        else:
            self.fail("Child survived timeout")

    def test_interrupt_cleans_up_process_group(self):
        with patch.object(mod.selectors.EpollSelector, "select", side_effect=KeyboardInterrupt), \
                patch.object(mod.os, "killpg", wraps=os.killpg) as kill:
            with self.assertRaises(KeyboardInterrupt):
                self.run_fixture("import time; time.sleep(10)", timeout=2)
            kill.assert_called_once()

    def test_failed_spawn_and_nonzero_exit(self):
        with self.assertRaises(OSError):
            mod.bounded_run(["/nonexistent/pr84-fixture"], self.root, timeout=1)
        self.assertEqual(self.run_fixture("raise SystemExit(7)", timeout=1).returncode, 7)

    def test_invalid_bounds_never_spawn(self):
        with patch.object(mod.subprocess, "Popen") as proc:
            for bounds in ({"timeout": 0}, {"timeout": 1801}, {"timeout": 1, "limit": 0}):
                with self.assertRaises(ValueError):
                    self.run_fixture("pass", **bounds)
            proc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
