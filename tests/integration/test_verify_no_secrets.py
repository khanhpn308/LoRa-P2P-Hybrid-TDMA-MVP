"""Exercise the scanner in disposable Git repositories, with synthetic markers."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCANNER = Path(__file__).resolve().parents[2] / "scripts/verify_no_secrets.py"


class SecretScanTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.git("init", "-q")
        self.git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "baseline")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.root, check=True, capture_output=True)

    def scan(self, expected):
        result = subprocess.run([sys.executable, str(SCANNER)], cwd=self.root,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result.stdout

    def stage(self, name, content):
        (self.root / name).write_text(content)
        self.git("add", name)

    def test_public_cert_and_env_template_allowed(self):
        self.stage("ca.pem", "-----BEGIN CERTIFICATE-----\nsynthetic\n")
        self.stage(".env.example", "POSTGRES_PASSWORD=REPLACE_WITH_LOCAL_PASSWORD\n")
        self.scan(0)

    def test_schema_and_scanner_source_are_not_credentials(self):
        self.stage("schema.yaml", "password:\n  type: string\n")
        self.stage("scanner.py", 'marker = "-----BEGIN ' + 'PRIVATE KEY-----"\n')
        self.scan(0)

    def test_forbidden_paths(self):
        for name in (".env", ".env.local", "server.key", "identity.p12", "mosquitto.passwd"):
            with self.subTest(name=name):
                self.stage(name, "synthetic")
                self.assertIn(name, self.scan(1))
                self.git("rm", "-f", name)

    def test_private_key_under_innocent_name_in_index(self):
        marker = "-----BEGIN " + "RSA PRIVATE KEY-----\nsynthetic\n"
        self.stage("notes.txt", marker)
        (self.root / "notes.txt").write_text("removed from worktree only\n")
        output = self.scan(1)
        self.assertIn("index", output)
        self.assertNotIn(marker.strip(), output)

    def test_unstaged_password_and_staged_diff(self):
        self.stage("config.txt", "safe\n")
        (self.root / "config.txt").write_text("POSTGRES_PASSWORD=synthetic-password\n")
        output = self.scan(1)
        self.assertIn("Git diff", output)
        self.assertNotIn("synthetic-password", output)
        self.git("add", "config.txt")
        self.scan(1)

    def test_ignored_untracked_secrets_not_read(self):
        self.stage(".gitignore", "secrets/\n")
        (self.root / "secrets").mkdir()
        (self.root / "secrets/server.key").write_text("private local test material")
        self.scan(0)

    def test_symlink_rejected(self):
        (self.root / "link").symlink_to("/etc/passwd")
        self.git("add", "link")
        self.scan(1)


if __name__ == "__main__":
    unittest.main()
