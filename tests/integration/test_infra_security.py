"""Fast regression checks for credential mount boundaries without Docker."""

import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
