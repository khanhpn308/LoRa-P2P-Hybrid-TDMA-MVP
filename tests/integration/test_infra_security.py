"""Credential boundaries and subscriber process regressions without Docker."""

import contextlib
import io
import subprocess
import unittest
from pathlib import Path
from unittest import mock

import test_local_infra as infra


class ClientCredentialTests(unittest.TestCase):
    def test_only_selected_identity_files_are_mounted_read_only(self):
        case = infra.LocalInfrastructureTest("test_local_infrastructure")
        case.certs = Path("/private/test-certificates")
        case.project = "unit-test"
        for identity in (None, "gw-a", "gw-b", "backend", "unknown", "wrong"):
            with self.subTest(identity=identity):
                command = case.client(identity, "mosquitto_pub")
                mounts = [command[index + 1] for index, arg in enumerate(command) if arg == "--mount"]
                names = ["ca.crt"] + ([] if identity is None else [f"{identity}.crt", f"{identity}.key"])
                self.assertEqual(mounts, [
                    f"type=bind,src={case.certs / name},dst=/certs/{name},readonly" for name in names])


class SubscriberProcessTests(unittest.TestCase):
    def setUp(self):
        self.output = self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.case = infra.LocalInfrastructureTest("test_local_infrastructure")
        self.case.project = "unit-test"
        self.case.certs = Path("/private/test-certificates")
        self.case.publish = mock.Mock()
        self.process = mock.Mock()
        self.process.returncode = 27
        self.process.poll.return_value = 27
        self.process.communicate.return_value = (b"Timed out\n", None)
        self.popen = self.enterContext(mock.patch.object(infra.subprocess, "Popen", return_value=self.process))
        self.remove = self.enterContext(mock.patch.object(
            infra.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "", "")))
        self.enterContext(mock.patch.object(infra.select, "select", return_value=([self.process.stdout], [], [])))
        self.read = self.enterContext(mock.patch.object(
            infra.os, "read", return_value=b"received SUBACK\nSubscribed (mid: 1): 1\n"))

    def exchange(self, allowed=False):
        self.case.exchange("gw-b", "backend", "iot/v1/gw/gw-a/downlink/command", allowed)

    def assert_owned_container_removed(self):
        command = self.popen.call_args.args[0]
        name = command[command.index("--name") + 1]
        self.assertTrue(name.startswith("unit-test-sub-"))
        self.remove.assert_called_once_with(["docker", "rm", "-f", name],
                                            capture_output=True, text=True, timeout=10)
        self.process.stdout.close.assert_called_once()

    def test_docker_teardown_can_outlast_old_process_deadline(self):
        completed = False

        def communicate(timeout):
            nonlocal completed
            if not completed and timeout < 12:
                raise subprocess.TimeoutExpired("docker run", timeout)
            completed = True
            return b"Timed out\n", None

        self.process.communicate.side_effect = communicate
        self.exchange()
        command = self.popen.call_args.args[0]
        self.assertEqual(command[command.index("-W") + 1], "45")
        self.assert_owned_container_removed()

    def test_process_timeout_is_not_authorization_success_and_cleans_owned_container(self):
        self.process.poll.return_value = None
        self.process.communicate.side_effect = [
            subprocess.TimeoutExpired("docker run", 60, output=b"partial debug output\n"), (b"", None)]
        with self.assertRaisesRegex(AssertionError, "Docker subscriber process timeout.*gw-b") as error:
            self.exchange()
        self.assertIn("NOT_VERIFIED", str(error.exception))
        self.assertIn("partial debug output", str(error.exception))
        self.process.kill.assert_called_once()
        self.process.communicate.assert_has_calls([mock.call(timeout=60), mock.call(timeout=10)])
        self.assert_owned_container_removed()

    def test_slow_publisher_cannot_turn_an_expired_window_into_negative_success(self):
        elapsed = 0

        def publish(*args):
            nonlocal elapsed
            elapsed = 38

        self.case.publish.side_effect = publish
        with mock.patch.object(infra.time, "monotonic", side_effect=lambda: elapsed):
            with self.assertRaisesRegex(AssertionError, "consumed the negative receive window"):
                self.exchange()
        self.assert_owned_container_removed()
        self.assertNotIn("PASS:", self.output.getvalue())

    def test_negative_receive_rejects_payload_and_unexpected_exit_codes(self):
        for code, output in ((0, b"issue16-smoke\n"), (27, b"issue16-smoke\n"),
                             (1, b"TLS failure\n"), (125, b"Docker failure\n")):
            with self.subTest(code=code):
                self.process.returncode = code
                self.process.communicate.return_value = (output, None)
                with self.assertRaises(AssertionError):
                    self.exchange()

    def test_missing_suback_does_not_publish_and_still_cleans_process(self):
        self.read.return_value = b""
        self.process.poll.return_value = None
        with self.assertRaisesRegex(AssertionError, "received SUBACK"):
            self.exchange()
        self.case.publish.assert_not_called()
        self.process.kill.assert_called_once()
        self.assert_owned_container_removed()

    def test_publisher_failure_still_cleans_subscriber(self):
        self.case.publish.side_effect = RuntimeError("publisher failed")
        self.process.poll.return_value = None
        with self.assertRaisesRegex(RuntimeError, "publisher failed"):
            self.exchange()
        self.process.kill.assert_called_once()
        self.assert_owned_container_removed()

    def test_positive_receive_still_requires_payload_and_success(self):
        for code, output in ((0, b"issue16-smoke\n"), (0, b""), (27, b"issue16-smoke\n")):
            with self.subTest(code=code, output=output):
                self.process.returncode = code
                self.process.communicate.return_value = (output, None)
                if code == 0 and output:
                    self.exchange(allowed=True)
                else:
                    with self.assertRaises(AssertionError):
                        self.exchange(allowed=True)

    def test_container_cleanup_error_is_not_ignored(self):
        self.remove.return_value = subprocess.CompletedProcess([], 1, "", "permission denied")
        with self.assertRaisesRegex(AssertionError, "Subscriber container cleanup failed"):
            self.exchange()
        self.assertNotIn("PASS:", self.output.getvalue())

    def test_container_removal_timeout_fails_with_a_bounded_wait(self):
        self.remove.side_effect = subprocess.TimeoutExpired("docker rm", 10)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.exchange()
        self.assert_owned_container_removed()
        self.assertNotIn("PASS:", self.output.getvalue())

    def test_container_removal_still_runs_when_local_reap_times_out(self):
        self.process.communicate.side_effect = [(b"Timed out\n", None),
                                               subprocess.TimeoutExpired("docker run", 10)]
        with self.assertRaises(subprocess.TimeoutExpired):
            self.exchange()
        self.assert_owned_container_removed()


if __name__ == "__main__":
    unittest.main()
