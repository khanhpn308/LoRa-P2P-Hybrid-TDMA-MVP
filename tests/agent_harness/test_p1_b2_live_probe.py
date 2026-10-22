"""Live-provider integration boundary contract tests; no real model/Docker use."""
import contextlib
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from p1.provider_runtime import IsolatedCLI, RuntimeBlocked, evaluate_probe
from p1 import provider_probe

IMAGE = "sha256:" + "a" * 64
NETWORK = "lora-agent-egress-reviewed"
CODEX_VOLUME = "lora-agent-codex-auth-pilot"
AGY_VOLUME = "lora-agent-agy-auth-pilot"


class RuntimePlanTests(unittest.TestCase):
    def plan(self, provider, volume):
        with tempfile.TemporaryDirectory() as d:
            return IsolatedCLI(provider, IMAGE, NETWORK, volume).command(
                pathlib.Path(d), "lora-p1-probe-" + provider + "-1234abcd", "hello")

    def test_codex_plan_read_only_and_no_personal_home(self):
        args = self.plan("codex", CODEX_VOLUME)
        self.assertEqual(args[:2], ["docker", "run"])
        self.assertIn("--pull=never", args)
        self.assertIn("--read-only", args)
        self.assertIn("--security-opt=no-new-privileges", args)
        self.assertIn("--cap-drop=ALL", args)
        self.assertIn("--network", args)
        self.assertEqual(args[args.index("--network")+1], NETWORK)
        self.assertIn(IMAGE, args)
        self.assertEqual(args[-7:],
                         ["codex", "exec", "--sandbox", "read-only",
                          "--ask-for-approval", "never", "hello"])
        mounts = [args[i+1] for i, v in enumerate(args) if v == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(any("dst=/workspace,readonly" in x for x in mounts))
        self.assertTrue(any("type=volume" in x and CODEX_VOLUME in x for x in mounts))
        self.assertFalse(any("/var/run/docker.sock" in x or "/home/khanh" in x
                             for x in args))
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--dangerously-skip-permissions", args)

    def test_agy_plan_is_independent_and_structured(self):
        args = self.plan("agy", AGY_VOLUME)
        self.assertEqual(args[-8:],
                         ["agy", "--sandbox", "-p", "hello",
                          "--output-format", "json", "--print-timeout", "3m"])
        self.assertNotIn(CODEX_VOLUME, " ".join(args))
        self.assertIn(AGY_VOLUME, " ".join(args))
        self.assertNotIn("--dangerously-skip-permissions", args)

    def test_denies_wrong_provider_image_or_network(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            for conf in (
                IsolatedCLI("codex", "espressif/idf:latest", NETWORK, CODEX_VOLUME),
                IsolatedCLI("codex", IMAGE, "host", CODEX_VOLUME),
                IsolatedCLI("agy", IMAGE, NETWORK, CODEX_VOLUME),
                IsolatedCLI("agy", IMAGE, NETWORK, "personal-gemini-credentials"),
            ):
                with self.subTest(conf=conf), self.assertRaises(RuntimeBlocked):
                    conf.command(root, "lora-p1-probe-"+conf.provider+"-1234abcd", "hello")

    def test_read_only_snapshot_must_exist(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / "missing"
            with self.assertRaises(RuntimeBlocked):
                IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME).command(
                    path, "lora-p1-probe-codex-1234abcd", "hello")

    def test_probe_prompt_limits(self):
        with tempfile.TemporaryDirectory() as d:
            runner = IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME)
            for prompt in ("a" * 5000, "contains secrets\n" + "é"):
                with self.assertRaises(RuntimeBlocked):
                    runner.command(pathlib.Path(d),
                                   "lora-p1-probe-codex-1234abcd", prompt)


class ProviderOutputTests(unittest.TestCase):
    def test_codex_requires_exact_stdout_not_echoed_prompt(self):
        item = evaluate_probe("codex", 0, b"CODEX_SMOKE_OK\n")
        self.assertEqual(item.state, "READ_ONLY_MODEL_PROBE_PASS_ONLY")
        self.assertEqual(item.exit_code, 0)
        for out in (b"", b"model: CODEX_SMOKE_OK from prompt",
                    b"CODEX_SMOKE_OK plus instructions"):
            with self.assertRaises(RuntimeBlocked):
                evaluate_probe("codex", 0, out)

    def test_agy_requires_success_envelope_and_exact_response(self):
        packet = json.dumps({"status": "SUCCESS", "response": "AGY_SMOKE_OK"}).encode()
        self.assertEqual(evaluate_probe("agy", 0, packet).provider, "agy")
        for response in (
            b"not json",
            json.dumps({"status": "ERROR", "response": "AGY_SMOKE_OK"}).encode(),
            json.dumps({"status": "SUCCESS", "response": "AGY_SMOKE_OK other"}).encode(),
            json.dumps({"status": "SUCCESS", "response": "AGY_SMOKE_OK", "error": "bad"}).encode(),
        ):
            with self.assertRaises(RuntimeBlocked):
                evaluate_probe("agy", 0, response)

    def test_exit_zero_permission_denial_does_not_pass(self):
        packet = json.dumps({"status": "SUCCESS", "response": "AGY_SMOKE_OK"}).encode()
        for diagnostic in (b"approval required for run_command",
                           b"permission denied", b"authentication required"):
            with self.assertRaises(RuntimeBlocked):
                evaluate_probe("agy", 0, packet, diagnostic)

    def test_exit_code_and_output_limit(self):
        with self.assertRaises(RuntimeBlocked):
            evaluate_probe("codex", 1, b"CODEX_SMOKE_OK")
        with self.assertRaises(RuntimeBlocked):
            evaluate_probe("codex", 0, b"A" * 65_000)


class SmokeCliTests(unittest.TestCase):
    def argv(self, extra=()):
        return ["provider_probe.py", "--provider", "codex",
                "--image-id", IMAGE, "--network", NETWORK,
                "--profile-volume", CODEX_VOLUME, *extra]

    def test_default_dry_run_without_provider_calls(self):
        with patch.object(sys, "argv", self.argv()), \
             patch.object(provider_probe, "_run") as launched, \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 0)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "PLAN_ONLY")
        launched.assert_not_called()

    def test_execute_without_external_policy_confirmation_blocks(self):
        with patch.object(sys, "argv", self.argv(["--execute"])), \
             patch.object(provider_probe, "_run") as launched, \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 2)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "BLOCKED")
        launched.assert_not_called()

    def test_mocked_live_codex_probe(self):
        with patch.object(sys, "argv", self.argv([
                "--execute", "--confirm-external-egress-policy"])), \
             patch.object(provider_probe, "_run",
                          return_value=(0, b"CODEX_SMOKE_OK\n", b"")) as launched, \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 0)
        self.assertEqual(json.loads(buffer.getvalue())["status"],
                         "READ_ONLY_MODEL_PROBE_PASS_ONLY")
        launched.assert_called_once()

    def test_mocked_soft_denial_fails_closed(self):
        with patch.object(sys, "argv", self.argv([
                "--execute", "--confirm-external-egress-policy"])), \
             patch.object(provider_probe, "_run",
                          return_value=(0, b"CODEX_SMOKE_OK\n", b"permission denied")), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 2)
        self.assertEqual(json.loads(buffer.getvalue())["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
