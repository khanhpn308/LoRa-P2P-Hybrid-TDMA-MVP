"""Audit snapshot invariants tested without an LLM or hardware."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "agent_harness"))
from snapshot import REFERENCES, assemble, digest, unchanged


class SnapshotTests(unittest.TestCase):
    def setup_repo(self, root):
        for ref in REFERENCES:
            p = root / ref
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("Approved reference data\n", encoding="utf-8")
        p = root / "firmware" / "components" / "sx1276_driver" / "sx1276.c"
        p.parent.mkdir(parents=True)
        p.write_text("int x = 42;\n", encoding="utf-8")
        return "firmware/components/sx1276_driver/sx1276.c"

    def test_full_snapshot_immutable(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo, dest = pathlib.Path(a), pathlib.Path(b)
            changed = self.setup_repo(repo)
            h = assemble(repo, dest, [changed], "+int x = 42;", [{"exit_code": 0}])
            schema = dest / "audit.schema.json"
            schema.write_text("{}")
            h["audit.schema.json"] = digest(schema.read_bytes())
            self.assertTrue(unchanged(dest, h))
            (dest / "changes.patch").chmod(0o644)
            (dest / "changes.patch").write_text("tampered")
            self.assertFalse(unchanged(dest, h))

    def test_extra_file_rejected(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo, dest = pathlib.Path(a), pathlib.Path(b)
            changed = self.setup_repo(repo)
            h = assemble(repo, dest, [changed], "+hello", [])
            schema = dest / "audit.schema.json"
            schema.write_text("{}")
            h["audit.schema.json"] = digest(schema.read_bytes())
            self.assertTrue(unchanged(dest, h))
            (dest / "unexpected.txt").write_text("modified by auditor")
            self.assertFalse(unchanged(dest, h))

    def test_binary_source_rejected(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo, dest = pathlib.Path(a), pathlib.Path(b)
            changed = self.setup_repo(repo)
            (repo / changed).write_bytes(b"\x00binary")
            with self.assertRaises(ValueError):
                assemble(repo, dest, [changed], "+binary", [])


if __name__ == "__main__":
    unittest.main()
