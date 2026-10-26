"""Daemon lifecycle: exhaustive mocked failures, no Docker daemon required."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/agent_harness"))
from mcp_docker import DockerLifecycle


class DockerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scratch = self.root / "scratch"
        (self.scratch / "firmware/gateway_master").mkdir(parents=True)
        self.out = self.root / "evidence"
        self.out.mkdir()
        self.runner = DockerLifecycle()
        self.pin = "sha256:"+"a"*64
        self.run = "b"*32

    def invoke(self, runner):
        return self.runner.build(run_id=self.run, app="gateway_master",
                                 image_id=self.pin, scratch=self.scratch,
                                 evidence=self.out, command_runner=runner)

    def test_reject_arbitrary_binary_and_arguments(self):
        with self.assertRaises(ValueError):
            DockerLifecycle(docker="/bin/bash")
        for app, pin in (("../../../etc", self.pin), ("gateway_master", "latest")):
            with self.assertRaises(ValueError):
                self.runner.build(run_id=self.run, app=app, image_id=pin,
                                  scratch=self.scratch, evidence=self.out,
                                  command_runner=lambda *_: None)

    def test_no_host_repo_mount_only_disposable_scratch(self):
        def capture(argv, outfile, timeout):
            self.assertEqual(argv[:2], ["/usr/bin/docker", "run"])
            self.assertIn("--network=none", argv)
            self.assertIn("--read-only", argv)
            self.assertIn("--cap-drop=ALL", argv)
            self.assertIn("--security-opt=no-new-privileges", argv)
            self.assertIn("--pull=never", argv)
            self.assertIn("type=bind,src=%s,dst=/workspace/firmware" % (self.scratch/"firmware"), argv)
            self.assertIn(self.pin, argv)
            self.assertNotIn("/var/run/docker.sock", " ".join(argv))
            self.assertEqual(timeout, 1800)
            return {"exit_code": 0, "log": outfile.name, "log_sha256": "c"*64}
        with patch.object(self.runner, "_list", return_value=set()):
            receipt = self.invoke(capture)
        self.assertEqual(receipt["cleanup_verified"], True)
        self.assertEqual(receipt["exit_code"], 0)

    def test_cleanup_after_failed_build_or_timeout(self):
        cid = "d"*64
        for exception in (RuntimeError("Build crashed"), subprocess.TimeoutExpired("docker", 2)):
            cidfile = self.out / "gateway_master.cid"
            if cidfile.exists():
                cidfile.unlink()
            def fail(*_):
                cidfile.write_text(cid)
                raise exception
            with patch.object(self.runner, "_list", return_value={cid}), \
                 patch.object(self.runner, "_call", return_value=subprocess.CompletedProcess([], 0, b"", b"")) as cmd:
                with self.assertRaises(type(exception)):
                    self.invoke(fail)
                self.assertTrue(any("rm" in call.args[0] for call in cmd.call_args_list))

    def test_cleanup_on_daemon_query_failure_blocks_success(self):
        with patch.object(self.runner, "_list", side_effect=ValueError("daemon unavailable")):
            with self.assertRaises(ValueError):
                self.invoke(lambda *_: {"exit_code": 0})

    def test_container_id_receipt_cannot_be_symlink(self):
        (self.out/"gateway_master.cid").symlink_to("/etc/passwd")
        with self.assertRaises(ValueError):
            self.invoke(lambda *_: {"exit_code": 0})

    def test_container_id_receipt_and_label_validated(self):
        path = self.out/"gateway_master.cid"
        path.write_text("rm -rf")
        with self.assertRaises(ValueError):
            self.runner._cleanup("lora.harness.run="+self.run+"-gateway_master", path)

    def test_daemon_leak_causes_no_build_pass(self):
        cid = "d"*64
        with patch.object(self.runner, "_list", return_value={cid}), \
                patch.object(self.runner, "_call",
                             return_value=subprocess.CompletedProcess([], 0, b"", b"")):
            with self.assertRaises(ValueError):
                self.invoke(lambda *_: {"exit_code": 0})

    def test_fails_when_docker_run_nonzero_even_if_cleaned(self):
        with patch.object(self.runner, "_list", return_value=set()):
            with self.assertRaises(ValueError):
                self.invoke(lambda *_: {"exit_code": 126})


if __name__ == "__main__":
    unittest.main()
