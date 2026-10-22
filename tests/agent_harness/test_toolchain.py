"""ESP-IDF auto-detection, exact version, no-network Docker and fallback policies."""
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from toolchains import resolver as tc

HASH = "sha256:" + "a" * 64


class ToolchainTests(unittest.TestCase):
    def test_version_must_be_an_exact_release(self):
        self.assertEqual(tc.normalize_version("v5.4.4"), "5.4.4")
        self.assertEqual(tc.normalize_version("5.4.4"), "5.4.4")
        for version in ("latest", "release-v5.4", "5.4", "v6.1-dev",
                        "5.4.4; touch /tmp/bad", "", "v5.4.4.1"):
            with self.subTest(version=version):
                with self.assertRaises(tc.ToolchainError):
                    tc.normalize_version(version)

    def test_actual_version_requires_exact_match(self):
        self.assertEqual(tc.actual_version("ESP-IDF v5.4.4", "5.4.4"), "5.4.4")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v5.4.40", "5.4.4")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v6.1.0", "5.4.4")

    def test_docker_command_uses_sha_and_restricted_network(self):
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d)
            project = repo / "firmware" / "gateway_master"
            project.mkdir(parents=True)
            idf = tc.ResolvedIDF("docker", "5.4.4", HASH, image="espressif/idf:v5.4.4")
            args = idf.command(repo, project, "build")
            self.assertIn("--network=none", args)
            self.assertIn("--cap-drop=ALL", args)
            self.assertIn("--read-only", args)
            self.assertIn("--pull=never", args)
            self.assertIn("--security-opt=no-new-privileges", args)
            self.assertIn("HOME=/tmp", args)
            self.assertIn(HASH, args)
            self.assertNotIn("espressif/idf:v5.4.4", args)
            self.assertNotIn("--privileged", args)
            self.assertEqual(args[-2:], ["idf.py", "build"])
            self.assertEqual(args[args.index("--workdir") + 1],
                             "/workspace/firmware/gateway_master")
            with self.assertRaises(tc.ToolchainError):
                idf.command(repo, pathlib.Path(d).parent, "build")

    def test_container_first_uses_existing_pinned_image_without_pull(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value="/usr/bin/docker"), patch(
                "toolchains.resolver.check") as check:
            check.side_effect = lambda args, **kwargs: (
                HASH if "inspect" in args else "ESP-IDF v5.4.4")
            chosen = tc.resolve(pathlib.Path(d), version="5.4.4")
            self.assertEqual(chosen.provider, "docker")
            self.assertEqual(chosen.identity, HASH)
            first_args = check.call_args_list[0].args[0]
            self.assertEqual(first_args[-1], "espressif/idf:v5.4.4")
            self.assertFalse(any("pull" == a for c in check.call_args_list
                                 for a in c.args[0]))

    def test_container_first_no_silent_native_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver._docker", side_effect=tc.ToolchainError("Docker missing")
        ), patch("toolchains.resolver._native") as native:
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="v5.4.4")
            native.assert_not_called()

    def test_native_fallback_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver._docker", side_effect=tc.ToolchainError("Docker missing")
        ), patch("toolchains.resolver._native") as native:
            native.return_value = tc.ResolvedIDF("native-path", "5.4.4", "/usr/bin/idf.py",
                                                 executable="/usr/bin/idf.py")
            chosen = tc.resolve(pathlib.Path(d), version="v5.4.4",
                                allow_native_fallback=True)
            self.assertEqual(chosen.provider, "native-path")
            native.assert_called_once()

    def test_native_auto_activation_via_idf_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value=None), patch(
                "toolchains.resolver.check", return_value="ESP-IDF v5.4.4") as check:
            root = pathlib.Path(d)
            installed = root / "toolchains with spaces" / "esp-idf"
            (installed / "tools").mkdir(parents=True)
            (installed / "export.sh").write_text("# stub")
            (installed / "tools" / "idf.py").write_text("# stub")
            result = tc.resolve(root, version="5.4.4", mode="native_only",
                                environment={"IDF_PATH": str(installed)})
            self.assertEqual(result.provider, "native-export")
            invoked = check.call_args.args[0]
            self.assertEqual(invoked[0], "bash")
            self.assertIn('source "$1/export.sh"', invoked)
            self.assertIn(str(installed), invoked)
            self.assertEqual(invoked[-2:], ["idf.py", "--version"])

    def test_native_path_version_mismatch_blocked(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value="/wrong/idf.py"), patch(
                "toolchains.resolver.check", return_value="ESP-IDF v6.1.0"):
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="5.4.4", mode="native_only",
                           environment={})

    def test_reject_unverified_image_id(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value="/usr/bin/docker"), patch(
                "toolchains.resolver.check", return_value="not a sha256"):
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="5.4.4")

    def test_host_build_command_does_not_flash(self):
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d)
            idf = tc.ResolvedIDF("native-path", "5.4.4", "/opt/idf.py",
                                 executable="/opt/idf.py")
            self.assertEqual(idf.command(repo, repo, "build"), ["/opt/idf.py", "build"])
            self.assertNotIn("flash", idf.command(repo, repo, "build"))


if __name__ == "__main__":
    unittest.main()
