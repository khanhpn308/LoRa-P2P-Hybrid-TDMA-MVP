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
        self.assertEqual(tc.normalize_version("v6.1"), "6.1")
        self.assertEqual(tc.normalize_version("6.1"), "6.1")
        for version in ("latest", "release-v6.1", "6", "v6.1-dev",
                        "6.1; touch /tmp/bad", "", "v6.1.0.1"):
            with self.subTest(version=version):
                with self.assertRaises(tc.ToolchainError):
                    tc.normalize_version(version)

    def test_actual_version_requires_exact_match(self):
        self.assertEqual(tc.actual_version("ESP-IDF v6.1", "6.1"), "6.1")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v6.10", "6.1")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v6.1.0", "6.1")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v6.1-dirty", "6.1")
        with self.assertRaises(tc.ToolchainError):
            tc.actual_version("ESP-IDF v6.1-14-gabcdef", "6.1")

    def test_docker_command_uses_sha_and_restricted_network(self):
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d)
            project = repo / "firmware" / "gateway_master"
            project.mkdir(parents=True)
            idf = tc.ResolvedIDF("docker", "6.1", HASH, image="espressif/idf:v6.1")
            args = idf.command(repo, project, "build")
            self.assertIn("--network=none", args)
            self.assertIn("--cap-drop=ALL", args)
            self.assertIn("--read-only", args)
            self.assertIn("--pull=never", args)
            self.assertIn("--security-opt=no-new-privileges", args)
            self.assertIn("HOME=/tmp", args)
            self.assertIn(HASH, args)
            self.assertNotIn("espressif/idf:v6.1", args)
            mount = args[args.index("--mount") + 1]
            self.assertIn("type=bind,src=", mount)
            self.assertIn(",dst=/workspace", mount)
            self.assertNotIn(",rw", mount)  # Docker --mount is read-write by default
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
                HASH if "inspect" in args else "ESP-IDF v6.1")
            chosen = tc.resolve(pathlib.Path(d), version="6.1")
            self.assertEqual(chosen.provider, "docker")
            self.assertEqual(chosen.identity, HASH)
            first_args = check.call_args_list[0].args[0]
            self.assertEqual(first_args[-1], "espressif/idf:v6.1")
            self.assertFalse(any("pull" == a for c in check.call_args_list
                                 for a in c.args[0]))

    def test_container_first_no_silent_native_fallback(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver._docker", side_effect=tc.ToolchainError("Docker missing")
        ), patch("toolchains.resolver._native") as native:
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="v6.1")
            native.assert_not_called()

    def test_native_fallback_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver._docker", side_effect=tc.ToolchainError("Docker missing")
        ), patch("toolchains.resolver._native") as native:
            native.return_value = tc.ResolvedIDF("native-path", "6.1", "/usr/bin/idf.py",
                                                 executable="/usr/bin/idf.py")
            chosen = tc.resolve(pathlib.Path(d), version="v6.1",
                                allow_native_fallback=True)
            self.assertEqual(chosen.provider, "native-path")
            native.assert_called_once()

    def test_native_auto_activation_via_idf_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value=None), patch(
                "toolchains.resolver.check", return_value="ESP-IDF v6.1") as check:
            root = pathlib.Path(d)
            installed = root / "toolchains with spaces" / "esp-idf"
            (installed / "tools").mkdir(parents=True)
            (installed / "export.sh").write_text("# stub")
            (installed / "tools" / "idf.py").write_text("# stub")
            result = tc.resolve(root, version="6.1", mode="native_only",
                                environment={"IDF_PATH": str(installed)})
            self.assertEqual(result.provider, "native-export")
            invoked = check.call_args.args[0]
            self.assertEqual(invoked[0], "bash")
            self.assertIn('source "$1/export.sh"', invoked[4])
            self.assertIn(str(installed), invoked)
            self.assertEqual(invoked[-2:], ["idf.py", "--version"])

    def test_native_path_version_mismatch_blocked(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value="/wrong/idf.py"), patch(
                "toolchains.resolver.check", return_value="ESP-IDF v6.0"):
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="6.1", mode="native_only",
                           environment={})

    def test_reject_unverified_image_id(self):
        with tempfile.TemporaryDirectory() as d, patch(
                "toolchains.resolver.shutil.which", return_value="/usr/bin/docker"), patch(
                "toolchains.resolver.check", return_value="not a sha256"):
            with self.assertRaises(tc.ToolchainError):
                tc.resolve(pathlib.Path(d), version="6.1")

    def test_host_build_command_does_not_flash(self):
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d)
            idf = tc.ResolvedIDF("native-path", "6.1", "/opt/idf.py",
                                 executable="/opt/idf.py")
            self.assertEqual(idf.command(repo, repo, "build"), ["/opt/idf.py", "build"])
            self.assertNotIn("flash", idf.command(repo, repo, "build"))


    def test_repo_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            (root / "firmware").mkdir()
            version_file = root / "firmware" / "esp-idf-version.txt"
            version_file.write_text("v6.1\n")
            self.assertEqual(tc.load_project_version(root), "6.1")
            version_file.write_text("release-v6.1\n")
            with self.assertRaises(tc.ToolchainError):
                tc.load_project_version(root)

    def test_minor_release_does_not_accept_patch_or_rc(self):
        for version in ("ESP-IDF v6.1.0", "ESP-IDF v6.1-rc1",
                        "ESP-IDF v6.1-dirty"):
            with self.subTest(version=version):
                with self.assertRaises(tc.ToolchainError):
                    tc.actual_version(version, "6.1")


    def test_docker_exit_125_shows_bounded_stderr(self):
        """Docker startup failures must retain actionable diagnostics."""
        with patch("toolchains.resolver.subprocess.run", return_value=subprocess.CompletedProcess(
                ["docker", "run"], 125, "", "docker: invalid mount config: invalid key rw")):
            with self.assertRaises(tc.ToolchainError) as caught:
                tc.check(["docker", "run", "image", "idf.py", "--version"])
            self.assertIn("exit 125", str(caught.exception))
            self.assertIn("invalid mount config", str(caught.exception))

    def test_docker_error_redacts_sensitive_output(self):
        with patch("toolchains.resolver.subprocess.run", return_value=subprocess.CompletedProcess(
                ["docker", "run"], 125, "", "docker: token=private_example_value")):
            with self.assertRaises(tc.ToolchainError) as caught:
                tc.check(["docker", "run", "image", "idf.py", "--version"])
            self.assertNotIn("private_example_value", str(caught.exception))
            self.assertIn("token=[REDACTED]", str(caught.exception))

if __name__ == "__main__":
    unittest.main()
