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
from p1.provider_runtime import (IsolatedCLI, RuntimeBlocked, evaluate_probe,
                                 safe_probe_diagnostic, verify_preinstalled_resources)
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
        for proxy_env in (
            "HTTP_PROXY=http://lora-egress-proxy:3128",
            "HTTPS_PROXY=http://lora-egress-proxy:3128",
            "http_proxy=http://lora-egress-proxy:3128",
            "https_proxy=http://lora-egress-proxy:3128",
            "NO_PROXY=", "no_proxy=",
        ):
            self.assertIn(proxy_env, args)
        self.assertIn(IMAGE, args)
        self.assertIn("CODEX_HOME=/home/agent/.codex-clean-pilot", args)
        self.assertIn("CODEX_CA_CERTIFICATE=/etc/ssl/certs/ca-certificates.crt", args)
        self.assertLess(args.index("CODEX_HOME=/home/agent/.codex-clean-pilot"),
                        args.index(IMAGE))
        self.assertLess(args.index("CODEX_CA_CERTIFICATE=/etc/ssl/certs/ca-certificates.crt"),
                        args.index(IMAGE))
        self.assertEqual(args[-8:],
                         ["codex", "--ask-for-approval", "never",
                          "exec", "--sandbox", "read-only",
                          "--skip-git-repo-check", "hello"])
        mounts = [args[i+1] for i, v in enumerate(args) if v == "--mount"]
        self.assertEqual(len(mounts), 2)
        self.assertTrue(any("dst=/workspace,readonly" in x for x in mounts))
        self.assertTrue(any("type=volume" in x and CODEX_VOLUME in x for x in mounts))
        self.assertFalse(any("/var/run/docker.sock" in x or "/home/khanh" in x
                             for x in args))
        self.assertNotIn("--privileged", args)
        self.assertNotIn("--dangerously-skip-permissions", args)

    def test_docker_only_codex_is_opt_in_and_keeps_outer_guardrails(self):
        with tempfile.TemporaryDirectory() as d:
            args = IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME).command(
                pathlib.Path(d), "lora-p1-probe-codex-1234abcd", "hello",
                docker_only_isolation=True)
        self.assertEqual(args[-8:],
                         ["codex", "--ask-for-approval", "never",
                          "exec", "--sandbox", "danger-full-access",
                          "--skip-git-repo-check", "hello"])
        for flag in ("--read-only", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges",
                     "--network", "--user"):
            self.assertIn(flag, args)
        self.assertIn("10001:10001", args)
        self.assertTrue(any("dst=/workspace,readonly" in x for x in args))
        self.assertNotIn("--privileged", args)

    def test_docker_only_override_rejects_agy(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(RuntimeBlocked):
            IsolatedCLI("agy", IMAGE, NETWORK, AGY_VOLUME).command(
                pathlib.Path(d), "lora-p1-probe-agy-1234abcd", "hello",
                docker_only_isolation=True)

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
        self.assertEqual(item.status, "READ_ONLY_MODEL_PROBE_PASS_ONLY")
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

    def test_safe_diagnostic_classifies_namespace_failure_without_raw_logs(self):
        log = b"bwrap: operation not permitted; token=SECRET_123"
        info = safe_probe_diagnostic("codex", 0, b"", log)
        self.assertFalse(info["stdout_exact_expected_marker"])
        self.assertIn("sandbox_backend", info["stderr_signals"])
        self.assertNotIn("SECRET_123", json.dumps(info))
        self.assertEqual(info["exit_code"], 0)

    def test_exit_code_and_output_limit(self):
        with self.assertRaises(RuntimeBlocked):
            evaluate_probe("codex", 1, b"CODEX_SMOKE_OK")
        with self.assertRaises(RuntimeBlocked):
            evaluate_probe("codex", 0, b"A" * 65_000)


class DockerInspectTests(unittest.TestCase):
    def test_requires_pinned_matching_existing_resources(self):
        spec = IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME)

        def fake_run(argv, **kw):
            which = argv[1]
            value = (IMAGE if which == "image"
                     else "bridge|true" if which == "network" else CODEX_VOLUME)
            return subprocess.CompletedProcess(argv, 0, value + "\n", "")

        with patch("p1.provider_runtime.subprocess.run", side_effect=fake_run) as calls:
            verify_preinstalled_resources(spec)
        self.assertEqual(calls.call_count, 3)
        self.assertFalse(any("pull" in c.args[0] for c in calls.call_args_list))

    def test_noninternal_bridge_network_is_blocked(self):
        spec = IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME)

        def fake_run(argv, **kwargs):
            kind = argv[1]
            output = (IMAGE if kind == "image"
                      else "bridge|false" if kind == "network"
                      else CODEX_VOLUME)
            return subprocess.CompletedProcess(argv, 0, output + "\n", "")

        with patch("p1.provider_runtime.subprocess.run", side_effect=fake_run):
            with self.assertRaises(RuntimeBlocked):
                verify_preinstalled_resources(spec)

    def test_wrong_local_image_id_is_blocked(self):
        spec = IsolatedCLI("codex", IMAGE, NETWORK, CODEX_VOLUME)
        with patch("p1.provider_runtime.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "sha256:" + "f"*64, "")):
            with self.assertRaises(RuntimeBlocked):
                verify_preinstalled_resources(spec)


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
             patch.object(provider_probe, "verify_preinstalled_resources"), \
             patch.object(provider_probe, "_run",
                          return_value=(0, b"CODEX_SMOKE_OK\n", b"")) as launched, \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 0)
        self.assertEqual(json.loads(buffer.getvalue())["status"],
                         "READ_ONLY_MODEL_PROBE_PASS_ONLY")
        launched.assert_called_once()

    def test_docker_only_requires_execute_and_egress_confirmation(self):
        for flags in (
            ["--accept-docker-only-isolation"],
            ["--execute", "--accept-docker-only-isolation"],
        ):
            with self.subTest(flags=flags), patch.object(
                    sys, "argv", self.argv(flags)), patch.object(
                    provider_probe, "_run") as launched, contextlib.redirect_stdout(
                    io.StringIO()) as buffer:
                self.assertEqual(provider_probe.main(), 2)
                self.assertEqual(json.loads(buffer.getvalue())["status"], "BLOCKED")
                launched.assert_not_called()

    def test_mocked_docker_only_success_reports_boundary(self):
        with patch.object(sys, "argv", self.argv([
                "--execute", "--confirm-external-egress-policy",
                "--accept-docker-only-isolation"])), patch.object(
                provider_probe, "verify_preinstalled_resources"), patch.object(
                provider_probe, "_run", return_value=(
                    0, b"CODEX_SMOKE_OK\n", b"")) as launched, contextlib.redirect_stdout(
                io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "READ_ONLY_MODEL_PROBE_PASS_ONLY")
        self.assertEqual(payload["sandbox_boundary"], "docker_outer_only")
        self.assertIn("danger-full-access", launched.call_args.args[0])

    def test_mocked_soft_denial_fails_closed(self):
        with patch.object(sys, "argv", self.argv([
                "--execute", "--confirm-external-egress-policy"])), \
             patch.object(provider_probe, "verify_preinstalled_resources"), \
             patch.object(provider_probe, "_run",
                          return_value=(0, b"CODEX_SMOKE_OK\n", b"permission denied")), \
             contextlib.redirect_stdout(io.StringIO()) as buffer:
            self.assertEqual(provider_probe.main(), 2)
        receipt = json.loads(buffer.getvalue())
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("filesystem_permission", receipt["diagnostic"]["stderr_signals"])
        self.assertNotIn("permission denied", json.dumps(receipt["diagnostic"]))


if __name__ == "__main__":
    unittest.main()
